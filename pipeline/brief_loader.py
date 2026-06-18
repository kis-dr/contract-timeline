"""
brief_loader.py
UNC 경로의 kr_brief(YYYY-MM-DD).csv 파일들을 읽어
종목별로 머지된 JSON(data/briefs_by_stock/{code}.json) 생성.

머지 전략: 기존 JSON 로드 → 새 행 추가 → (code, created_at) 기준 dedup → 저장
"""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import pandas as pd

from config import BRIEF_DIR, BRIEFS_BY_STOCK, DATA_START_DATE

log = logging.getLogger(__name__)

# 파일명 패턴: kr_brief(2026-06-16).csv
FNAME_RE = re.compile(r"kr_brief\((\d{4}-\d{2}-\d{2})\)\.csv$")


def list_brief_files(start_date: str = DATA_START_DATE) -> List[Path]:
    """UNC 경로에서 start_date 이후의 brief CSV 목록 (날짜순)"""
    if not BRIEF_DIR.exists():
        log.error(f"BRIEF_DIR 접근 불가: {BRIEF_DIR}")
        return []

    out = []
    for p in BRIEF_DIR.glob("kr_brief(*).csv"):
        m = FNAME_RE.search(p.name)
        if not m:
            continue
        d = m.group(1)
        if d >= start_date:
            out.append((d, p))
    out.sort()
    log.info(f"brief 파일 {len(out)}개 발견 ({start_date} 이후)")
    return [p for _, p in out]


def _safe(v):
    """NaN/NA -> None, 그 외 정상값 반환"""
    if pd.isna(v):
        return None
    return v


def load_one_brief(path: Path) -> List[dict]:
    """brief CSV 1개를 읽어 종목별 dict 리스트로 변환"""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str})
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp949", dtype={"code": str})
    df["code"] = df["code"].astype(str).str.zfill(6)

    # 파일명에서 날짜 추출 (행의 date 컬럼이 없을 가능성 대비)
    m = FNAME_RE.search(path.name)
    file_date = m.group(1) if m else None

    rows = []
    for _, r in df.iterrows():
        rd = r.to_dict()
        row_date = _safe(rd.get("date")) or file_date
        rows.append({
            "code": rd["code"],
            "date": row_date,
            "company_name":  _safe(rd.get("company_name")),
            "article_title": _safe(rd.get("article_title")),
            "briefing":      _safe(rd.get("briefing")),
            "content_url":   _safe(rd.get("content_url")),
            "publisher":     _safe(rd.get("publisher")),
            "polarity":      _safe(rd.get("polarity")),
            "change_rate":   _safe(rd.get("change_rate")),
            "created_at":    _safe(rd.get("created_at")) or row_date,
        })
    return rows


def merge_to_briefs_by_stock(start_date: str = DATA_START_DATE) -> int:
    """
    모든 brief CSV를 읽어 종목별 JSON 파일로 통합.
    기존 파일이 있으면 dedup 머지(키: created_at + article_title).
    반환: 갱신된 종목 수
    """
    BRIEFS_BY_STOCK.mkdir(parents=True, exist_ok=True)

    # 1) 모든 row 모으기
    files = list_brief_files(start_date)
    by_code: Dict[str, List[dict]] = {}
    for f in files:
        try:
            for row in load_one_brief(f):
                by_code.setdefault(row["code"], []).append(row)
        except Exception as e:
            log.error(f"brief 로드 실패 {f.name}: {e}")

    # 2) 기존 JSON 머지 + dedup + 저장
    updated = 0
    for code, new_rows in by_code.items():
        out_path = BRIEFS_BY_STOCK / f"{code}.json"
        existing = []
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        combined = existing + new_rows
        # dedup 키: (created_at, article_title) - article_title이 빈 경우 date+briefing 일부
        seen = set()
        deduped = []
        for r in combined:
            key = (r.get("created_at") or r.get("date"), (r.get("article_title") or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)

        # 날짜 내림차순
        deduped.sort(key=lambda x: (x.get("created_at") or x.get("date") or ""), reverse=True)

        out_path.write_text(
            json.dumps(deduped, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        updated += 1

    log.info(f"briefs_by_stock: {updated}개 종목 JSON 갱신")
    return updated
