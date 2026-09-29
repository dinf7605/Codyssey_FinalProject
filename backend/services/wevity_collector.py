"""위비티 목록에서 최대 20개 제목·공고 링크·출처만 저장한다.

수신 확인은 이용 허락이 아니다. 실행은 WEVITY_CRAWLING_ENABLED=true일 때만
가능하며, 운영자는 출처 정책을 직접 확인해야 한다. 상세 페이지는 요청하지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import httpx

from services.wevity_parser import WevityLink, parse_wevity_links

SOURCE = "wevity"
JOB_NAME = "contest.collect"
BASE_URL = "https://www.wevity.com"
USER_AGENT = "StudyPace/0.1 (non-commercial student project; codyssey final project)"
REQUEST_GAP_SECONDS = 3.0
MAX_ITEMS = 20
KST = timezone(timedelta(hours=9))

# 학습 목표와 이어지기 쉬운 분야만 본다 (위비티 분야 번호 → 이름)
CATEGORIES: dict[int, str] = {22: "과학/공학"}


def crawling_enabled() -> bool:
    return os.getenv("WEVITY_CRAWLING_ENABLED", "false").lower() == "true"


def list_url(category: int, page: int = 1) -> str:
    return f"{BASE_URL}/?c=find&s=1&gub=1&cidx={category}&gp={page}"


def fetch_html(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def today_kst() -> date:
    return datetime.now(KST).date()


def _content_hash(item: WevityLink) -> str:
    key = "|".join([item.title, item.source_url])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def to_row(item: WevityLink, now: datetime) -> dict:
    """저장 대상은 목록 제목·링크·출처뿐이다. 나머지는 비어 있는 호환 필드."""
    return {
        "source": SOURCE,
        "source_id": item.source_id,
        "title": item.title,
        "host": "",
        "fields": [],
        "eligibility_text": None,
        "start_date": None,
        "deadline": None,
        "status": "unknown",
        "source_url": item.source_url,
        "official_url": None,
        "summary": None,
        "raw_text": None,
        "content_hash": _content_hash(item),
        "collected_at": now.isoformat(),
    }


@dataclass
class CollectResult:
    listed: int = 0
    skipped_known: int = 0
    skipped_closed: int = 0
    saved: int = 0
    failed: int = 0
    indexed: int = 0
    run_id: str | None = None
    errors: list[str] = field(default_factory=list)


def collect(
    db,
    *,
    categories: list[int] | None = None,
    pages: int = 1,
    refresh: bool = False,
    dry_run: bool = False,
    fetch: Callable[[str], str] = fetch_html,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
) -> CollectResult:
    """목록 상위 20건까지만 조회·저장한다. 상세 페이지는 열지 않는다."""
    if fetch is fetch_html and not crawling_enabled():
        raise RuntimeError("WEVITY_CRAWLING_ENABLED=true일 때만 수집할 수 있습니다")
    now = now or datetime.now(KST)
    result = CollectResult()
    run_id = None
    if not dry_run:
        run_id = db.table("batch_runs").insert({
            "job_name": JOB_NAME, "source": SOURCE, "status": "running", "started_at": now.isoformat(),
        }).execute().data[0]["id"]
        result.run_id = run_id

    known = set() if (refresh or dry_run) else {
        r["source_id"] for r in db.table("contests").select("source_id").eq("source", SOURCE).execute().data
    }
    seen: set[str] = set()
    rows: list[dict] = []
    first_request = True

    def polite_fetch(url: str) -> str:
        nonlocal first_request
        if not first_request:
            sleep(REQUEST_GAP_SECONDS)
        first_request = False
        return fetch(url)

    for category in categories or list(CATEGORIES):
        for page in range(1, pages + 1):
            if result.listed >= MAX_ITEMS:
                break
            try:
                items = parse_wevity_links(polite_fetch(list_url(category, page)), base_url=BASE_URL)
            except Exception as exc:  # noqa: BLE001 - 한 분야가 실패해도 다른 분야는 계속한다
                result.failed += 1
                result.errors.append(f"목록 {category}-{page}: {type(exc).__name__}")
                continue
            for item in items:
                if result.listed >= MAX_ITEMS:
                    break
                if item.source_id in seen:
                    continue
                seen.add(item.source_id)
                result.listed += 1
                if item.source_id in known:
                    result.skipped_known += 1
                    continue
                rows.append(to_row(item, now))

    if rows and not dry_run:
        try:
            db.table("contests").upsert(rows, on_conflict="source,source_id").execute()
        except Exception as exc:  # noqa: BLE001
            result.failed += len(rows)
            result.errors.append(f"저장: {type(exc).__name__}")
            rows = []
    result.saved = len(rows)

    if run_id is not None:
        status = "failed" if result.failed and not result.saved else "partial" if result.failed else "success"
        db.table("batch_runs").update({
            "status": status,
            "collected_count": result.saved,
            "failed_count": result.failed,
            "error_message": "; ".join(result.errors)[:500] or None,
            "finished_at": datetime.now(KST).isoformat(),
        }).eq("id", run_id).execute()
    return result


def running(db, now: datetime) -> bool:
    """1시간 안에 시작해 아직 끝나지 않은 수집이 있는가 — 스케줄러가 두 번 불러도 겹쳐 돌지 않게."""
    rows = (
        db.table("batch_runs").select("started_at")
        .eq("job_name", JOB_NAME).eq("status", "running")
        .order("started_at", desc=True).limit(1).execute().data
    )
    if not rows:
        return False
    started = datetime.fromisoformat(rows[0]["started_at"].replace("Z", "+00:00"))
    if started.tzinfo is None:
        started = started.replace(tzinfo=KST)
    return started > now - timedelta(hours=1)


def run_daily(db, now: datetime | None = None) -> CollectResult:
    """배치 호출: 허용 설정을 확인하고 목록 수집 후 제목 색인을 시도한다."""
    if not crawling_enabled():
        raise RuntimeError("위비티 수집이 비활성화되어 있습니다")
    now = now or datetime.now(KST)
    result = collect(db, now=now)
    from services import contest_vector

    if contest_vector.enabled():
        try:
            indexed, failed = contest_vector.index_titles(db)
            result.indexed = indexed
            result.failed += failed
            if result.run_id:
                db.table("batch_runs").update({
                    "indexed_count": indexed, "failed_count": result.failed,
                    "status": "partial" if result.failed else "success",
                }).eq("id", result.run_id).execute()
        except Exception as exc:  # noqa: BLE001 - 수집 성공분은 유지하고 다음 실행에서 재시도
            result.failed += 1
            result.errors.append(f"색인: {type(exc).__name__}")
            if result.run_id:
                db.table("batch_runs").update({
                    "status": "partial" if result.saved else "failed",
                    "failed_count": result.failed,
                    "error_message": "; ".join(result.errors)[:500],
                }).eq("id", result.run_id).execute()
    return result


def close_expired(db, today: date) -> None:
    """마감이 지난 공고를 closed 로 돌린다. 검색은 이미 마감일로 거르지만 상태도 맞춰 둔다."""
    db.table("contests").update({"status": "closed"}).eq("source", SOURCE).in_(
        "status", ["upcoming", "open"]
    ).lt("deadline", today.isoformat()).execute()
