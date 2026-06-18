"""
build_data.py
전체 파이프라인 메인 진입점.

실행 흐름:
  1. 어제까지 누적된 contracts.json 로드 (없으면 빈 리스트)
  2. KOSCOM: 오늘 날짜 공시 목록 (gongsi_basic) -> 판매ㆍ공급 필터
  3. 기존 contracts에 없는 신규 공시만 본문 fetch -> Gemini 분석
  4. contracts.json 갱신 저장
  5. brief CSV 머지 -> briefs_by_stock/{code}.json
  6. stock_check 최신본 -> stock_info.json
  7. meta.json 갱신
  8. 1년 이상 지난 brief 아카이브

CLI:
  python build_data.py                 # 오늘 데이터 처리
  python build_data.py --date 2026-06-16   # 특정 날짜
  python build_data.py --backfill 2026-06-01 2026-06-16   # 기간 일괄
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import config
from config import DATA_DIR, ensure_dirs
from koscom_client import KoscomClient, normalize_basic_row
from gemini_client import GeminiClient, ContractAIFields
from brief_loader import merge_to_briefs_by_stock
from stock_info_loader import build_stock_info_json, get_stock_snapshot_for_date

# ─── 로깅 ───────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("build_data")


CONTRACTS_PATH = DATA_DIR / "contracts.json"
META_PATH      = DATA_DIR / "meta.json"


# ─────────────────────────────────────────────────
# contracts.json 로드/저장
# ─────────────────────────────────────────────────
def load_contracts() -> list[dict]:
    if not CONTRACTS_PATH.exists():
        return []
    try:
        return json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"contracts.json 파싱 실패: {e}")
        return []


def save_contracts(contracts: list[dict]):
    # 최신순 정렬 후 저장
    contracts.sort(key=lambda c: (c.get("date", ""), c.get("id", "")), reverse=True)
    CONTRACTS_PATH.write_text(
        json.dumps(contracts, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info(f"contracts.json 저장: {len(contracts)}건")


# ─────────────────────────────────────────────────
# 1일치 처리
# ─────────────────────────────────────────────────
def process_one_day(target_date: str, contracts: list[dict],
                    koscom: KoscomClient, gemini: GeminiClient) -> int:
    """
    target_date(YYYY-MM-DD)의 공급계약 공시 수집 + 분석.
    contracts 리스트에 in-place로 신규 추가. 추가된 개수 반환.
    """
    log.info(f"=== {target_date} 처리 시작 ===")
    sdate = target_date.replace("-", "")
    edate = sdate

    # 1) 공시 목록
    df = koscom.fetch_supply_contracts(sdate, edate)
    if df.empty:
        log.info(f"  {target_date} 판매ㆍ공급 공시 0건")
        return 0

    # 2) 기존 id set
    existing_ids = {c.get("id") for c in contracts}

    # 3) 종목 스냅샷 (당일 종가/시총)
    stock_snap = get_stock_snapshot_for_date(target_date)
    log.info(f"  stock_snapshot: {len(stock_snap)}개 종목")

    # 4) 행별 처리
    added = 0
    for idx, row in df.iterrows():
        base = normalize_basic_row(row.to_dict())
        cid = base["id"]
        if cid in existing_ids:
            continue  # 이미 처리됨

        log.info(f"  [{idx+1}/{len(df)}] {base['code']} {base['title'][:40]}")

        # 종목 스냅샷 머지 (현재가/시가총액)
        snap = stock_snap.get(base["code"], {})
        base["name"] = snap.get("name", "")
        base["market_cap_at_disclosure"] = snap.get("market_cap")
        base["price_at_disclosure"]      = snap.get("price")

        # 5) 본문 fetch + Gemini 분석
        body = koscom.fetch_body(ndate=sdate, ncode=base["ncode"])
        ai: Optional[ContractAIFields] = None
        if body:
            ai = gemini.analyze_contract(title=base["title"], body=body)

        if ai is not None:
            base.update({
                "counterparty":   ai.counterparty,
                "amount":         ai.amount_won,
                "revenue_ratio":  ai.revenue_ratio,
                "period_start":   ai.period_start,
                "period_end":     ai.period_end,
                "ai_importance":  ai.ai_importance,
                "ai_summary":     ai.ai_summary,
                "ai_status":      "ok",
            })
        else:
            # AI 분석 실패해도 기본 메타는 보존
            base.update({
                "counterparty":   "",
                "amount":         None,
                "revenue_ratio":  None,
                "period_start":   "",
                "period_end":     "",
                "ai_importance":  0,
                "ai_summary":     "(AI 분석 실패)",
                "ai_status":      "failed",
            })

        contracts.append(base)
        existing_ids.add(cid)
        added += 1

    log.info(f"=== {target_date} 신규 {added}건 추가 ===")
    return added


# ─────────────────────────────────────────────────
# meta.json 갱신
# ─────────────────────────────────────────────────
def update_meta(contracts: list[dict], n_stocks: int):
    meta = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "n_contracts": len(contracts),
        "n_stocks": n_stocks,
        "data_start": config.DATA_START_DATE,
    }
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(f"meta.json 갱신: {meta}")


# ─────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--date", help="단일 날짜 처리 (YYYY-MM-DD). 미지정 시 오늘.")
    g.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                   help="기간 일괄 처리 (YYYY-MM-DD YYYY-MM-DD)")
    ap.add_argument("--skip-brief", action="store_true", help="brief 머지 스킵")
    ap.add_argument("--skip-stock-info", action="store_true", help="stock_info 갱신 스킵")
    return ap.parse_args()


def daterange(start: str, end: str):
    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    d = s
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)


def main():
    args = parse_args()
    log.info("=" * 60)
    log.info("Contract Timeline 데이터 빌드 시작")
    log.info(config.summary())
    log.info("=" * 60)

    ensure_dirs()

    # 처리 대상 날짜
    if args.backfill:
        dates = list(daterange(*args.backfill))
    elif args.date:
        dates = [args.date]
    else:
        dates = [date.today().isoformat()]

    # 1) 공급계약 (KOSCOM + Gemini)
    contracts = load_contracts()
    koscom = KoscomClient()
    gemini = GeminiClient()

    total_added = 0
    for d in dates:
        # 주말 스킵 (KOSCOM 응답 0건이지만 빠르게)
        if datetime.strptime(d, "%Y-%m-%d").weekday() >= 5:
            log.info(f"  {d} 주말 스킵")
            continue
        try:
            total_added += process_one_day(d, contracts, koscom, gemini)
        except Exception as e:
            log.exception(f"  {d} 처리 중 오류: {e}")

    if not config.DRY_RUN:
        save_contracts(contracts)

    # 2) stock_info.json
    n_stocks = 0
    if not args.skip_stock_info:
        n_stocks = build_stock_info_json() if not config.DRY_RUN else 0

    # 3) briefs_by_stock
    if not args.skip_brief and not config.DRY_RUN:
        merge_to_briefs_by_stock()

    # 4) meta.json
    if not config.DRY_RUN:
        update_meta(contracts, n_stocks)

    # 5) 아카이브 (별도 모듈)
    if not config.DRY_RUN:
        try:
            from archive import archive_old_briefs
            archive_old_briefs()
        except Exception as e:
            log.warning(f"아카이브 스킵: {e}")

    log.info("=" * 60)
    log.info(f"완료. 신규 공급계약 {total_added}건 추가. 총 {len(contracts)}건.")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
