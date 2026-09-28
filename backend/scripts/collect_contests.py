"""위비티 공고를 지금 한 번 수집한다 (FR-CONT-01) — 매일 05:00 배치와 같은 일을 손으로 돌릴 때.

    cd backend
    python -m scripts.collect_contests --dry-run         # DB 에 쓰지 않고 몇 건이 들어올지만 본다
    python -m scripts.collect_contests                   # 분야 8개 · 목록 1쪽씩 수집해 contests 에 저장
    python -m scripts.collect_contests --categories 20 21 --pages 2

요청 사이 3초씩 쉬므로 분야 8개면 몇 분 걸린다. 사용 조건은 services/wevity_collector.py 맨 위를 본다.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from db import get_supabase_client
from services import wevity_collector


def main() -> None:
    parser = argparse.ArgumentParser(description="위비티 공고 수집")
    parser.add_argument("--categories", type=int, nargs="*", help=f"분야 번호 (기본: {list(wevity_collector.CATEGORIES)})")
    parser.add_argument("--pages", type=int, default=1, help="분야마다 볼 목록 쪽 수 (기본 1)")
    parser.add_argument("--refresh", action="store_true", help="이미 저장한 공고도 상세를 다시 받는다")
    parser.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    args = parser.parse_args()

    db = None if args.dry_run else get_supabase_client()
    now = datetime.now(wevity_collector.KST)
    if db is not None:
        wevity_collector.close_expired(db, now.date())
    result = wevity_collector.collect(
        db, categories=args.categories, pages=args.pages, refresh=args.refresh, dry_run=args.dry_run, now=now,
    )
    print(
        f"목록 {result.listed}건 · 저장 {result.saved}건 · 이미 있음 {result.skipped_known}건 · "
        f"마감 {result.skipped_closed}건 · 실패 {result.failed}건"
    )
    for error in result.errors:
        print("  -", error)


if __name__ == "__main__":
    main()
