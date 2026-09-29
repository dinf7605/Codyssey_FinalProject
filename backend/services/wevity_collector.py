"""위비티 공모전 수집기 (FR-CONT-01) — 목록 → 새 공고 상세 → contests 저장.

마감일·주최·분야·응모대상·접수 시작일까지 저장해야 마감 필터, 준비 기간 계산(FR-CONT-10),
추천의 마감 점수·목표 기한 필터가 돌아간다 (09-29 팀장 결정 — 제목·링크만 모으던 방식을 되돌림).

지키는 것
  - WEVITY_CRAWLING_ENABLED=true 일 때만 실제로 요청한다
  - 한 번 받은 robots.txt 로 목록·상세 주소를 모두 확인한다. robots 를 못 읽으면 수집하지 않는다
  - 요청 사이 3초씩 쉬고, 한 번에 상세는 최대 MAX_DETAILS 건만 받는다
  - 공고 원문(raw_text)은 저장하지 않는다 — 사실 정보만 남기고 자세한 내용은 원문 링크로 보낸다
  - 이미 상세까지 저장한 공고는 다시 받지 않는다 (refresh 일 때만). 제목·링크만 있는 옛 행은 채운다
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.robotparser import RobotFileParser

import httpx

from services.wevity_parser import WevityDetail, WevityListItem, parse_wevity_detail, parse_wevity_list

SOURCE = "wevity"
JOB_NAME = "contest.collect"
BASE_URL = "https://www.wevity.com"
USER_AGENT = "StudyPace/0.1 (non-commercial student project; codyssey final project)"
REQUEST_GAP_SECONDS = 3.0
MAX_DETAILS = 100  # 한 번에 받는 상세 수 상한 — 3초 간격이면 약 5분
KST = timezone(timedelta(hours=9))

# 학습 목표와 이어지기 쉬운 분야만 본다 (위비티 분야 번호 → 이름)
CATEGORIES: dict[int, str] = {
    1: "기획/아이디어",
    2: "광고/마케팅",
    10: "영상/UCC/사진",
    19: "디자인/캐릭터/웹툰",
    20: "웹/모바일/IT",
    21: "게임/소프트웨어",
    22: "과학/공학",
    88: "취업/창업",
}


def crawling_enabled() -> bool:
    return os.getenv("WEVITY_CRAWLING_ENABLED", "false").lower() == "true"


def list_url(category: int, page: int = 1) -> str:
    return f"{BASE_URL}/?c=find&s=1&gub=1&cidx={category}&gp={page}"


def fetch_html(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def robots_checker() -> Callable[[str], bool]:
    """robots.txt 를 한 번 읽어 주소 검사 함수를 만든다. 읽기 실패는 예외 — 수집하지 않는다."""
    response = httpx.get(f"{BASE_URL}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=20.0)
    if response.status_code == 404:
        return lambda url: True
    response.raise_for_status()
    rules = RobotFileParser()
    rules.parse(response.text.splitlines())
    return lambda url: rules.can_fetch(USER_AGENT, url)


def today_kst() -> date:
    return datetime.now(KST).date()


def _content_hash(detail: WevityDetail) -> str:
    key = "|".join([
        detail.title, detail.host, str(detail.start_date), str(detail.deadline),
        ",".join(detail.fields), detail.eligibility or "", detail.official_url or "",
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def to_row(item: WevityListItem, detail: WevityDetail, today: date, now: datetime) -> dict | None:
    """저장할 행. 마감일을 모르거나 이미 지난 공고는 None — 마감 기준 로직에 쓸 수 없다."""
    if detail.deadline is None or detail.deadline < today:
        return None
    status = "upcoming" if detail.start_date and detail.start_date > today else "open"
    return {
        "source": SOURCE,
        "source_id": detail.source_id,
        "title": detail.title or item.title,
        "host": detail.host or item.host or "주최 미상",
        "fields": detail.fields or item.fields,
        "eligibility_text": detail.eligibility,
        "start_date": detail.start_date.isoformat() if detail.start_date else None,
        "deadline": detail.deadline.isoformat(),
        "status": status,
        "source_url": item.source_url,
        "official_url": detail.official_url,
        "summary": None,
        "raw_text": None,  # 원문은 저장하지 않는다
        "content_hash": _content_hash(detail),
        "collected_at": now.isoformat(),
    }


@dataclass
class CollectResult:
    listed: int = 0
    skipped_known: int = 0
    skipped_closed: int = 0
    skipped_limit: int = 0  # MAX_DETAILS 를 넘겨 다음 실행으로 미룬 공고
    saved: int = 0
    failed: int = 0
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
    allowed: Callable[[str], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
) -> CollectResult:
    """분야별 목록 → 새 공고 상세 → contests 에 저장(upsert). 결과는 batch_runs 에 남긴다.

    한 건이 실패해도 나머지는 계속한다. dry_run 이면 DB 에 쓰지 않고 결과만 센다.
    allowed 는 주소 허용 검사 (기본: 실제 요청이면 robots.txt, 테스트용 가짜 fetch 면 검사 없음).
    """
    if fetch is fetch_html and not crawling_enabled():
        raise RuntimeError("WEVITY_CRAWLING_ENABLED=true일 때만 수집할 수 있습니다")
    now = now or datetime.now(KST)
    today = now.astimezone(KST).date() if now.tzinfo else now.date()
    result = CollectResult()
    run_id = None
    if not dry_run:
        run_id = db.table("batch_runs").insert({
            "job_name": JOB_NAME, "source": SOURCE, "status": "running", "started_at": now.isoformat(),
        }).execute().data[0]["id"]
        result.run_id = run_id

    # 상세까지 저장한 공고만 '이미 있음'. 마감일이 비어 있는 옛 링크 전용 행은 상세를 받아 채운다
    known = set() if (refresh or dry_run) else {
        r["source_id"] for r in db.table("contests").select("source_id,deadline").eq(
            "source", SOURCE
        ).execute().data if r.get("deadline")
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

    checker = allowed
    if checker is None and fetch is fetch_html:
        try:
            checker = robots_checker()
        except Exception as exc:  # noqa: BLE001 - robots 를 못 읽으면 아무것도 요청하지 않는다
            result.failed += 1
            result.errors.append(f"robots.txt: {type(exc).__name__}")
            categories = []
    details = 0

    for category in list(CATEGORIES) if categories is None else categories:
        for page in range(1, pages + 1):
            url = list_url(category, page)
            if checker and not checker(url):
                result.failed += 1
                result.errors.append(f"목록 {category}-{page}: robots.txt에서 허용하지 않음")
                continue
            try:
                items = parse_wevity_list(polite_fetch(url), base_url=BASE_URL)
            except Exception as exc:  # noqa: BLE001 - 한 분야가 실패해도 다른 분야는 계속한다
                result.failed += 1
                result.errors.append(f"목록 {category}-{page}: {type(exc).__name__}")
                continue
            for item in items:
                if item.source_id in seen:
                    continue
                seen.add(item.source_id)
                result.listed += 1
                if item.d_day is not None and item.d_day < 0:
                    result.skipped_closed += 1
                    continue
                if item.source_id in known:
                    result.skipped_known += 1
                    continue
                if details >= MAX_DETAILS:
                    result.skipped_limit += 1
                    continue
                if checker and not checker(item.source_url):
                    result.failed += 1
                    result.errors.append(f"상세 {item.source_id}: robots.txt에서 허용하지 않음")
                    continue
                details += 1
                try:
                    detail = parse_wevity_detail(polite_fetch(item.source_url), source_url=item.source_url)
                except Exception as exc:  # noqa: BLE001
                    result.failed += 1
                    result.errors.append(f"상세 {item.source_id}: {type(exc).__name__}")
                    continue
                row = to_row(item, detail, today, now)
                if row is None:
                    result.skipped_closed += 1
                    continue
                rows.append(row)

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
    """매일 05:00 — 마감 지난 공고를 닫고 새 공고를 모은다."""
    if not crawling_enabled():
        raise RuntimeError("위비티 수집이 비활성화되어 있습니다")
    now = now or datetime.now(KST)
    close_expired(db, now.astimezone(KST).date())
    return collect(db, now=now)


def close_expired(db, today: date) -> None:
    """마감이 지난 공고를 closed 로 돌린다. 검색은 이미 마감일로 거르지만 상태도 맞춰 둔다."""
    db.table("contests").update({"status": "closed"}).eq("source", SOURCE).in_(
        "status", ["upcoming", "open"]
    ).lt("deadline", today.isoformat()).execute()
