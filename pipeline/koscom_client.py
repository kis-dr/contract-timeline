"""
koscom_client.py
KOSCOM check API 래퍼.
- gongsi_basic: 기간 내 공시 목록
- gongsi_body : 공시 본문
필터: TITLE 에 '판매ㆍ공급' 포함 (정정공시 포함)
"""
from __future__ import annotations
import logging
import time
from datetime import datetime
import requests
import pandas as pd
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import KOSCOM_CUST_ID, KOSCOM_AUTH_KEY

log = logging.getLogger(__name__)

HOST_URL   = "https://checkapi.koscom.co.kr"
GONGSI_BASIC = f"{HOST_URL}/news/gongsi/gongsi_basic"
GONGSI_BODY  = f"{HOST_URL}/news/gongsi/gongsi_body"

# 송이님이 알려주신 필터 키워드 (특수문자 'ㆍ' 주의)
SUPPLY_CONTRACT_KW = "판매ㆍ공급"


class KoscomClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.verify = False
        self.auth = {"cust_id": KOSCOM_CUST_ID, "auth_key": KOSCOM_AUTH_KEY}

    # ─────────────────────────────────────────────────
    # 공시 목록
    # ─────────────────────────────────────────────────
    def fetch_basic(self, sdate: str, edate: str, dcnt: int = 10000) -> pd.DataFrame:
        """
        sdate/edate: 'YYYYMMDD'
        반환: 컬럼 = DATE, CODE, TIME, TITLE, BIGCD, LANGCD, SRCCD, MTVCD,
                   FUNCCD, SKCD, IMPCD, BONCD, SEQ, DSEQ, NCD
        """
        payload = {**self.auth, "sdate": sdate, "edate": edate, "dcnt": dcnt}
        log.info(f"gongsi_basic 호출: {sdate} ~ {edate}")
        res = self.session.post(GONGSI_BASIC, data=payload, timeout=60)
        res.raise_for_status()
        results = res.json().get("results", [])
        df = pd.DataFrame(results)
        log.info(f"  -> {len(df)}건 수신")
        return df

    def fetch_supply_contracts(self, sdate: str, edate: str) -> pd.DataFrame:
        """판매ㆍ공급계약 공시만 필터링 (정정공시 포함)"""
        df = self.fetch_basic(sdate, edate)
        if df.empty:
            return df
        mask = df["TITLE"].str.contains(SUPPLY_CONTRACT_KW, na=False)
        out = df[mask].copy()
        log.info(f"  -> 판매ㆍ공급 필터 후 {len(out)}건")
        return out.reset_index(drop=True)

    # ─────────────────────────────────────────────────
    # 공시 본문
    # ─────────────────────────────────────────────────
    def fetch_body(self, ndate: str, ncode: str, retries: int = 2) -> str:
        """
        ndate: 공시일 'YYYYMMDD' (gongsi_basic 결과의 DATE)
        ncode: 공시 고유코드 (gongsi_basic 결과의 CODE)
        반환: BODY 문자열 (빈 문자열일 수 있음)
        """
        payload = {**self.auth, "ndate": ndate, "ncode": ncode}
        last_err = None
        for attempt in range(retries + 1):
            try:
                res = self.session.post(GONGSI_BODY, data=payload, timeout=60)
                res.raise_for_status()
                results = res.json().get("results", [])
                if not results:
                    return ""
                return results[0].get("BODY", "") or ""
            except Exception as e:
                last_err = e
                wait = 1.5 ** attempt
                log.warning(f"  fetch_body 재시도 ({attempt+1}/{retries}) {ncode}: {e}")
                time.sleep(wait)
        log.error(f"  fetch_body 실패: ncode={ncode} - {last_err}")
        return ""


# ─────────────────────────────────────────────────
# 유틸: 우리 스키마로 정규화
# ─────────────────────────────────────────────────
def normalize_basic_row(row: dict) -> dict:
    """
    gongsi_basic 한 행을 contracts.json 스키마의 기본 필드로 변환.
    AI 필드(amount, counterparty, importance, summary)는 별도 단계에서 채움.
    """
    date_raw = str(row.get("DATE", ""))
    time_raw = str(row.get("TIME", "")).zfill(6)
    code     = str(row.get("NCD", "")).zfill(6)
    ncode    = str(row.get("CODE", ""))

    # 'YYYYMMDD' -> 'YYYY-MM-DD'
    date_iso = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}" if len(date_raw) == 8 else date_raw
    # 'HHMMSS' -> 'HH:MM:SS'
    time_iso = f"{time_raw[:2]}:{time_raw[2:4]}:{time_raw[4:6]}" if len(time_raw) == 6 else time_raw

    title = row.get("TITLE", "")
    is_amendment = "(정정)" in title  # 정정공시 표시

    # KIND 종목별 공시 페이지 (송이님 확인): repIsuSrtCd 는 'A' + 6자리 종목코드
    kind_url = (
        "https://kind.krx.co.kr/disclosureSimpleSearch.do"
        f"?method=disclosureSimpleSearchMain&repIsuSrtCd=A{code}"
    )

    return {
        "id": f"{date_raw}-{ncode}",   # 안정적인 id (정정공시도 ncode 다름)
        "date": date_iso,
        "time": time_iso,
        "code": code,
        "title": title,
        "is_amendment": is_amendment,
        "ncode": ncode,
        "mtvcd": str(row.get("MTVCD", "")),
        "url": kind_url,
    }
