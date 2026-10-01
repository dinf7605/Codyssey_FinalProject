"""학습 알림 4종 (FR-ALARM-01~04) — 알림 설정(FR-MY-03/05)을 지켜 notification_logs 에 남긴다.

앱 안 알림이다. 화면(/notifications)과 머리글의 종 아이콘이 이 기록을 보여 주고,
블록 알림에서는 바로 시작하거나 다음 빈 시간으로 미룰 수 있다 (FR-ALARM-03).
메일·푸시는 보내지 않는다.

| 종류      | type           | 언제                                             | 강도             |
|-----------|----------------|--------------------------------------------------|------------------|
| 시작 전   | 10min_before   | 블록 시작 N분 전 (N = reminder_minutes_before)   | low·normal·high  |
| 미완료    | after_block    | 블록이 끝나고 30분이 지나도 완료하지 않음        | normal·high      |
| 하루 마감 | daily_nightly  | 21:00, 오늘 못 끝낸 블록이 있으면 하루 한 번     | high             |
| 주간 요약 | weekly_summary | 일요일 20:00, 한 주 한 번                         | low·normal·high  |

공통 규칙
  - 알림을 끈 사람(enabled=false)에게는 아무것도 보내지 않는다
  - 방해금지 시간(한국 시각)에는 보내지 않는다. 그 사이에 지나간 알림은 나중에 몰아 보내지 않는다
  - 같은 블록·같은 종류는 한 번만 (DB 고유 인덱스 notification_logs_user_block_type_unique 도 막는다)
  - 문구는 사실만 말하고 재촉하거나 탓하지 않는다

시간은 시간대 없는 한국 시각(plan_store 와 같음)으로 다루고, DB 에는 +09:00 을 붙여 비교한다.
실행: workers/notification_worker.py (주기 실행) 또는 POST /batch/alarm/* (X-Batch-Key).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta

from services.plan_store import KST, from_db_time, to_db_time

BEFORE_BLOCK = "10min_before"  # 예전 이름 그대로 둔다 — 이미 쌓인 기록·고유 인덱스와 맞춘다
AFTER_BLOCK = "after_block"
DAILY_NIGHTLY = "daily_nightly"
WEEKLY_SUMMARY = "weekly_summary"
BLOCK_TYPES = (BEFORE_BLOCK, AFTER_BLOCK)  # 블록 하나에 대한 알림 — 화면에서 시작·미루기를 붙인다

MAX_REMINDER_MINUTES = 120
AFTER_BLOCK_DELAY = timedelta(minutes=30)
AFTER_BLOCK_WINDOW = timedelta(hours=3)  # 이보다 오래 지난 블록은 독촉하지 않는다 — 야간 재조정이 옮긴다

DEFAULTS = {
    "enabled": True,
    "reminder_minutes_before": 10,
    "quiet_start": None,
    "quiet_end": None,
    "intensity": "normal",
}
JOBS_BY_INTENSITY = {
    "low": {"before_block", "weekly_summary"},
    "normal": {"before_block", "after_block", "weekly_summary"},
    "high": {"before_block", "after_block", "daily_nightly", "weekly_summary"},
}


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


# ── 설정 ──────────────────────────────────────────────

def settings_for(db, user_ids) -> dict[str, dict]:
    """사용자별 알림 설정. 저장한 적 없으면 기본값 (알림 켬 · 10분 전 · 보통 · 방해금지 없음)."""
    user_ids = list(dict.fromkeys(str(u) for u in user_ids))
    if not user_ids:
        return {}
    rows = db.table("user_notification_settings").select("*").in_("user_id", user_ids).execute().data
    found = {}
    for row in rows:
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in row.items() if v is not None})
        found[str(row["user_id"])] = merged
    return {u: found.get(u, dict(DEFAULTS)) for u in user_ids}


def _hhmm(value) -> tuple[int, int]:
    hh, mm = str(value)[:5].split(":")
    return int(hh), int(mm)


def in_quiet_hours(settings: dict, now: datetime) -> bool:
    start, end = settings.get("quiet_start"), settings.get("quiet_end")
    if not start or not end:
        return False
    current, s, e = (now.hour, now.minute), _hhmm(start), _hhmm(end)
    if s == e:
        return False
    if s > e:  # 22:00 ~ 07:00 처럼 자정을 넘는다
        return current >= s or current < e
    return s <= current < e


def allowed(settings: dict, job: str, now: datetime) -> bool:
    if settings.get("enabled") is False:
        return False
    jobs = JOBS_BY_INTENSITY.get(settings.get("intensity") or "normal", JOBS_BY_INTENSITY["normal"])
    return job in jobs and not in_quiet_hours(settings, now)


# ── 공통 ──────────────────────────────────────────────

def _active_plans(db) -> dict[str, dict]:
    rows = db.table("study_plans").select("id,user_id,goal_title").eq("status", "active").execute().data
    return {str(r["id"]): r for r in rows}


def _blocks(db, plans: dict[str, dict], *, field: str, since: datetime, until: datetime) -> list[dict]:
    if not plans:
        return []
    return (
        db.table("plan_blocks").select("id,plan_id,title,start_at,end_at,done")
        .in_("plan_id", list(plans)).eq("done", False)
        .gte(field, to_db_time(since)).lte(field, to_db_time(until))
        .execute().data
    )


def _already(db, user_id: str, type_: str, *, block_id: str | None = None, since: datetime | None = None) -> bool:
    query = db.table("notification_logs").select("id").eq("user_id", user_id).eq("type", type_)
    if block_id is not None:
        query = query.eq("block_id", block_id)
    if since is not None:
        query = query.gte("sent_at", to_db_time(since))
    return bool(query.limit(1).execute().data)


def _insert(db, user_id: str, type_: str, message: str, now: datetime, block_id: str | None = None) -> bool:
    try:
        db.table("notification_logs").insert({
            "user_id": user_id, "block_id": block_id, "type": type_,
            "message": message, "sent_at": to_db_time(now),
        }).execute()
    except Exception:  # noqa: BLE001 - 동시에 두 번 돌아 고유 인덱스에 걸린 경우 — 이미 보낸 것
        return False
    return True


def _send_for_block(db, user_id: str, type_: str, message: str, now: datetime, block_id: str) -> bool:
    if _already(db, user_id, type_, block_id=block_id):
        return False
    return _insert(db, user_id, type_, message, now, block_id)


# ── FR-ALARM-01 시작 전 ───────────────────────────────

def run_before_block(db, now: datetime | None = None) -> dict:
    """블록 시작 N분 전 (사용자 설정, 기본 10분). 1분마다 돌린다."""
    now = now or now_kst()
    plans = _active_plans(db)
    blocks = _blocks(db, plans, field="start_at", since=now, until=now + timedelta(minutes=MAX_REMINDER_MINUTES))
    owners = {b["id"]: str(plans[str(b["plan_id"])]["user_id"]) for b in blocks}
    settings = settings_for(db, owners.values())
    sent = 0
    for block in blocks:
        user_id = owners[block["id"]]
        s = settings[user_id]
        left = (from_db_time(block["start_at"]) - now).total_seconds() / 60
        if left <= 0 or left > int(s.get("reminder_minutes_before") or 10) or not allowed(s, "before_block", now):
            continue
        message = f"{math.ceil(left)}분 후 '{block.get('title') or '학습'}' 학습이 시작돼요."
        sent += _send_for_block(db, user_id, BEFORE_BLOCK, message, now, block["id"])
    return {"job": "before_block", "checked": len(blocks), "sent": sent}


# ── FR-ALARM-02 미완료 ────────────────────────────────

def run_after_block(db, now: datetime | None = None) -> dict:
    """끝나고 30분이 지났는데 완료하지 않은 블록. 5분마다 돌린다."""
    now = now or now_kst()
    plans = _active_plans(db)
    blocks = _blocks(db, plans, field="end_at", since=now - AFTER_BLOCK_WINDOW, until=now - AFTER_BLOCK_DELAY)
    owners = {b["id"]: str(plans[str(b["plan_id"])]["user_id"]) for b in blocks}
    settings = settings_for(db, owners.values())
    sent = 0
    for block in blocks:
        user_id = owners[block["id"]]
        if not allowed(settings[user_id], "after_block", now):
            continue
        title = block.get("title") or "학습"
        message = f"'{title}' 블록을 아직 완료하지 않았어요. 지금 시작하거나 다른 시간으로 미룰 수 있어요."
        sent += _send_for_block(db, user_id, AFTER_BLOCK, message, now, block["id"])
    return {"job": "after_block", "checked": len(blocks), "sent": sent}


# ── 하루 마감 (21:00) ─────────────────────────────────

def run_daily_nightly(db, now: datetime | None = None) -> dict:
    """오늘 못 끝낸 블록 수를 하루 한 번 알린다 (강도 '높음'만)."""
    now = now or now_kst()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    plans = _active_plans(db)
    blocks = _blocks(db, plans, field="end_at", since=today, until=now)
    left: dict[str, int] = defaultdict(int)
    for block in blocks:
        left[str(plans[str(block["plan_id"])]["user_id"])] += 1
    settings = settings_for(db, left)
    sent = 0
    for user_id, count in left.items():
        if not allowed(settings[user_id], "daily_nightly", now) or _already(db, user_id, DAILY_NIGHTLY, since=today):
            continue
        message = f"오늘 끝내지 못한 블록이 {count}개 있어요. 밤사이 남은 기간에 다시 놓아 드려요."
        sent += _insert(db, user_id, DAILY_NIGHTLY, message, now)
    return {"job": "daily_nightly", "checked": len(left), "sent": sent}


# ── FR-ALARM-04 주간 요약 (일요일 20:00) ──────────────

def _duration(minutes: int) -> str:
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}시간 {mins}분"
    return f"{hours}시간" if hours else f"{mins}분"


def run_weekly_summary(db, now: datetime | None = None) -> dict:
    """이번 주(월~일) 블록 완료 수와 공부 시간을 한 주 한 번 알린다."""
    now = now or now_kst()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    plans = _active_plans(db)
    if not plans:
        return {"job": "weekly_summary", "checked": 0, "sent": 0}
    rows = (
        db.table("plan_blocks").select("plan_id,done")
        .in_("plan_id", list(plans))
        .gte("start_at", to_db_time(week_start)).lt("start_at", to_db_time(week_start + timedelta(days=7)))
        .execute().data
    )
    total: dict[str, int] = defaultdict(int)
    done: dict[str, int] = defaultdict(int)
    for row in rows:
        user_id = str(plans[str(row["plan_id"])]["user_id"])
        total[user_id] += 1
        done[user_id] += bool(row.get("done"))
    users = list(dict.fromkeys(str(p["user_id"]) for p in plans.values()))
    minutes: dict[str, int] = defaultdict(int)
    sessions = (
        db.table("study_sessions").select("user_id,minutes")
        .in_("user_id", users).gte("started_at", to_db_time(week_start))
        .execute().data
    )
    for row in sessions:
        minutes[str(row["user_id"])] += int(row.get("minutes") or 0)

    settings = settings_for(db, users)
    sent = 0
    for user_id in users:
        if not total[user_id] and not minutes[user_id]:
            continue
        if not allowed(settings[user_id], "weekly_summary", now) or _already(db, user_id, WEEKLY_SUMMARY, since=week_start):
            continue
        message = (
            f"이번 주 요약: 블록 {done[user_id]}/{total[user_id]}개 완료, "
            f"공부 시간 {_duration(minutes[user_id])}. 다음 주 일정은 일정 화면에서 확인할 수 있어요."
        )
        sent += _insert(db, user_id, WEEKLY_SUMMARY, message, now)
    return {"job": "weekly_summary", "checked": len(users), "sent": sent}
