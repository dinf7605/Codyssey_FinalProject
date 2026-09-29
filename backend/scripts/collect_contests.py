"""위비티 공고를 지금 한 번 수집한다 (FR-CONT-01) — 제목·주최·분야·접수기간·응모대상·링크. WEVITY_CRAWLING_ENABLED=true 필요."""

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

    if not wevity_collector.crawling_enabled():
        parser.error("WEVITY_CRAWLING_ENABLED=true로 설정된 경우에만 수집할 수 있습니다")

    db = None if args.dry_run else get_supabase_client()
    now = datetime.now(wevity_collector.KST)
    result = wevity_collector.collect(
        db, categories=args.categories, pages=args.pages, refresh=args.refresh, dry_run=args.dry_run, now=now,
    )
    print(
        f"목록 {result.listed}건 · 저장 {result.saved}건 · 이미 있음 {result.skipped_known}건 · "
        f"마감 {result.skipped_closed}건 · 다음 실행으로 미룸 {result.skipped_limit}건 · 실패 {result.failed}건"
    )
    for error in result.errors:
        print("  -", error)


if __name__ == "__main__":
    main()
