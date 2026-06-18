"""
stock_info_loader.py
UNC stock_check(YYYY-MM-DD).csv -> data/stock_info.json

CSV 컬럼 (이미지 기반, 정확히 확인됨):
종목코드 | 한글종목명 | 현재가 | 등락율 | 거래량 | 거래대금 | 시가총액 |
유동주식수 | 상장주식수 | 발행주식수 | 외국인보유 | 52주최고가 | 52주최저가 |
거래대금_ | 고가 | 저가 | 기준가 | 1년전종가 | 시장
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime, date as date_cls, timedelta
from pathlib import Path
from typing import Optional
import pandas as pd

from config import STOCK_CHECK_DIR, DATA_DIR

log = logging.getLogger(__name__)

FNAME_RE = re.compile(r"stock_check\((\d{4}-\d{2}-\d{2})\)\.csv$")

CHOSUNG = ["ㄱ","ㄲ","ㄴ","ㄷ","ㄸ","ㄹ","ㅁ","ㅂ","ㅃ","ㅅ",
           "ㅆ","ㅇ","ㅈ","ㅉ","ㅊ","ㅋ","ㅌ","ㅍ","ㅎ"]

def extract_chosung(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in s:
        c = ord(ch)
        if 0xAC00 <= c <= 0xD7A3:
            out.append(CHOSUNG[(c - 0xAC00) // 588])
        else:
            out.append(ch)
    return "".join(out)


def find_stock_check_csv(target_date: str) -> Optional[Path]:
    """
    target_date(공시일, YYYY-MM-DD)와 같은 날의 stock_check 파일을 우선 찾고,
    없으면 가장 가까운 과거 영업일 파일을 폴백으로 사용 (최대 5일 거슬러).
    """
    if not STOCK_CHECK_DIR.exists():
        log.error(f"STOCK_CHECK_DIR 접근 불가: {STOCK_CHECK_DIR}")
        return None

    d = datetime.strptime(target_date, "%Y-%m-%d").date()
    for back in range(0, 6):
        cand = STOCK_CHECK_DIR / f"stock_check({(d - timedelta(days=back)).isoformat()}).csv"
        if cand.exists():
            if back > 0:
                log.warning(f"  {target_date} 파일 없음 -> {back}일 전 파일 사용: {cand.name}")
            return cand
    log.error(f"stock_check 파일 못 찾음: {target_date} ~ 5일 거슬러")
    return None


def latest_stock_check_csv() -> Optional[Path]:
    """가장 최근 stock_check 파일"""
    files = []
    for p in STOCK_CHECK_DIR.glob("stock_check(*).csv"):
        m = FNAME_RE.search(p.name)
        if m:
            files.append((m.group(1), p))
    if not files:
        return None
    files.sort(reverse=True)
    return files[0][1]


def load_stock_check(path: Path) -> pd.DataFrame:
    """stock_check CSV 로드 + 정규화"""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype={"종목코드": str})
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp949", dtype={"종목코드": str})
    df["종목코드"] = df["종목코드"].astype(str).str.zfill(6)
    return df


def to_stock_info_record(row: pd.Series) -> dict:
    """stock_check 한 행을 stock_info.json 스키마로 변환"""
    code = str(row["종목코드"]).zfill(6)
    name = str(row["한글종목명"]).strip()
    price = float(row["현재가"]) if pd.notna(row["현재가"]) else None
    prev1y = float(row["1년전종가"]) if pd.notna(row["1년전종가"]) else None
    yoy = None
    if price and prev1y and prev1y > 0:
        yoy = round((price / prev1y - 1) * 100, 2)

    mkt_raw = str(row.get("시장", "")).strip()
    market = {"KSP": "KOSPI", "KSQ": "KOSDAQ"}.get(mkt_raw, mkt_raw)

    return {
        "code":         code,
        "name":         name,
        "chosung":      extract_chosung(name),
        "price":        price,
        "change_rate":  float(row["등락율"]) if pd.notna(row.get("등락율")) else None,
        "market_cap":   float(row["시가총액"]) if pd.notna(row.get("시가총액")) else None,
        "high_52w":     float(row["52주최고가"]) if pd.notna(row.get("52주최고가")) else None,
        "low_52w":      float(row["52주최저가"]) if pd.notna(row.get("52주최저가")) else None,
        "yoy_return":   yoy,
        "market":       market,
    }


def build_stock_info_json() -> int:
    """가장 최근 stock_check로 stock_info.json 덮어쓰기. 반환: 종목 수"""
    path = latest_stock_check_csv()
    if path is None:
        log.error("stock_check CSV 없음 - stock_info.json 갱신 스킵")
        return 0

    log.info(f"stock_check 로드: {path.name}")
    df = load_stock_check(path)

    records = [to_stock_info_record(row) for _, row in df.iterrows()]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "stock_info.json"
    out.write_text(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info(f"stock_info.json: {len(records)}개 종목")
    return len(records)


def get_stock_snapshot_for_date(target_date: str) -> dict[str, dict]:
    """
    공시일(target_date)의 종목 스냅샷(코드->레코드) 반환.
    당일 파일이 없으면 가장 가까운 과거 영업일 폴백.
    """
    path = find_stock_check_csv(target_date)
    if path is None:
        return {}
    df = load_stock_check(path)
    snap = {}
    for _, row in df.iterrows():
        rec = to_stock_info_record(row)
        snap[rec["code"]] = rec
    return snap
