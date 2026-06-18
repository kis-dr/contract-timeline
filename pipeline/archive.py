"""
archive.py
오래된 brief 데이터를 연도별로 묶어 zip 압축.

전략:
- briefs_by_stock/{code}.json 각 파일에서 N일 이전 항목을 추출
- 추출분을 briefs_archive/{YYYY}.json 으로 머지 후 zip 압축
- 원본 JSON에서는 해당 항목 제거 (용량 절감)

주의: 종목별 JSON에 남은 데이터가 0건이면 파일 자체는 그대로 두되 빈 배열로.
"""
from __future__ import annotations
import json
import logging
import shutil
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict

from config import BRIEFS_BY_STOCK, ARCHIVE_DIR, BRIEF_ARCHIVE_DAYS

log = logging.getLogger(__name__)


def _row_year(row: dict) -> str | None:
    raw = row.get("created_at") or row.get("date")
    if not raw or len(raw) < 4:
        return None
    return raw[:4]


def archive_old_briefs(threshold_days: int = None):
    """
    threshold_days 이전 brief 항목들을 연도별로 모아 zip 압축.
    호출 빈도: 매일 1회 권장 (양 적으면 거의 no-op).
    """
    threshold_days = threshold_days or BRIEF_ARCHIVE_DAYS
    cutoff = (date.today() - timedelta(days=threshold_days)).isoformat()
    log.info(f"아카이브 시작: cutoff={cutoff}")

    if not BRIEFS_BY_STOCK.exists():
        log.info("  briefs_by_stock 없음 - 스킵")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 연도별 수집
    year_buckets: dict[str, list[dict]] = defaultdict(list)
    n_moved = 0
    n_files_touched = 0

    for jf in BRIEFS_BY_STOCK.glob("*.json"):
        try:
            rows = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        keep, move = [], []
        for r in rows:
            key = (r.get("created_at") or r.get("date") or "")[:10]
            if key and key < cutoff:
                move.append(r)
            else:
                keep.append(r)

        if move:
            n_files_touched += 1
            n_moved += len(move)
            code = jf.stem
            for r in move:
                r["_code"] = code  # 종목 식별자 보존
                y = _row_year(r) or "unknown"
                year_buckets[y].append(r)

            jf.write_text(
                json.dumps(keep, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

    if not year_buckets:
        log.info("  이동 대상 없음")
        return

    # 연도별 zip 갱신 (기존 zip이 있으면 안의 JSON과 머지)
    for year, rows in year_buckets.items():
        zip_path = ARCHIVE_DIR / f"{year}.zip"
        inner_name = f"{year}.json"

        existing = []
        if zip_path.exists():
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    if inner_name in zf.namelist():
                        existing = json.loads(zf.read(inner_name).decode("utf-8"))
            except Exception as e:
                log.warning(f"  기존 zip 읽기 실패 {zip_path.name}: {e}")

        combined = existing + rows
        # dedup
        seen = set()
        deduped = []
        for r in combined:
            k = (r.get("_code"),
                 r.get("created_at") or r.get("date"),
                 (r.get("article_title") or "")[:60])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                inner_name,
                json.dumps(deduped, ensure_ascii=False, separators=(",", ":")),
            )
        log.info(f"  {zip_path.name}: {len(deduped)}건 (신규 {len(rows)})")

    log.info(f"아카이브 완료: {n_moved}건 이동, {n_files_touched}개 종목 파일 정리")
