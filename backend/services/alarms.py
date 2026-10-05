"""학습 알림 (FR-ALARM-01~04) — 알림 설정(FR-MY-03/05)을 지켜 notification_logs 에 남긴다.

앱 안 알림이다. 화면(/notifications)과 머리글의 종 아이콘이 이 기록을 보여 주고, 화면을 열어 둔 브라우저는
알림 권한을 받은 경우 브라우저 알림으로도 띄운다 (frontend components/NotificationLink.js).
블록 알림에서는 바로 시작·미루기·오늘 쉬기를 할 수 있다 (FR-ALARM-03). 메일·푸시 서버는 쓰지 않는다.

| 종류          | type             | 언제                                              | 보내는 조건                      |
|---------------|------------------|---------------------------------------------------|----------------------------------|
| 시작 전       | 10min_before     | 블록 시작 N분 전 (N = reminder_minutes_before)    | 강도 약·보통·강                  |
| 미완료        | after_block      | 블록이 끝나고 30분이 지나도 완료하지 않음         | 강도 강 + '학습 독촉' 켬         |
| 하루 마감     | daily_nightly    | 21:00, 오늘 못 끝낸 블록이 있으면 하루 한 번      | 강도 강 + '학습 독촉' 켬         |
| 주간 요약     | weekly_summary   | 일요일 20:00, 한 주 한 번                          | 강도 보통·강                     |
| 재조정 결과   | replan_result    | 야간 재조정이 블록을 옮긴 뒤 (방해금지가 끝나면)  | 강도 보통·강 + '재조정 결과' 켬  |
| 공모전 마감   | contest_deadline | 관심 공모전 마감 24시간 전                         | '마감 임박' 켬 (전체 끄기와 별개)|
| 오늘 쉬기     | rest_today       | 사용자가 누른 기록 — 그날 남은 학습 알림을 멈춘다 | —                                |

공통 규칙
  - 알림을 끈 사람(enabled=false)에게는 공모전 마감 알림(별도 동의)만 보낸다
  - 방해금지 시간(한국 시각, 기본 23:00~07:00)에는 보내지 않는다. 그 사이 시작한 블록은
    방해금지가 끝난 뒤 첫 시작 알림에 '남은 블록 N개'로 합쳐 알린다 (FR-ALARM-01)
  - 같은 블록·같은 종류는 한 번만 (DB 고유 인덱스도 막는다). 기록이 실패하면 한 번 더 시도한다
  - 독촉(미완료·하루 마감)은 하루 최대 3번, 직전 독촉 2번을 읽지 않았으면 그날은 멈춘다 (FR-ALARM-02)
  - 문구는 사실만 말하고 재촉하거나 탓하지 않는다

재조정 결과·마감 임박·학습 독촉(FR-MY-03)은 아직 고른 적이 없으면 가입 때의 '학습 알림 수신(선택)' 동의를 따른다.
시간은 시간대 없는 한국 시각(plan_store 와 같음)으로 다루고, DB 에는 +09:00 을 붙여 비교한다.
실행: workers/notification_worker.py (주기 실행) 또는 POST /batch/alarm/* (X-Batch-Key).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from services.plan_store import KST, from_db_time, to_db_time

BEFORE_BLOCK = "10min_before"  # 예전 이름 그대로 둔다 — 이미 쌓인 기록·고유 인덱스와 맞춘다
AFTER_BLOCK = "after_block"
DAILY_NIGHTLY = "daily_nightly"
WEEKLY_SUMMARY = "weekly_summary"
REPLAN_RESULT = "replan_result"
CONTEST_DEADLINE = "contest_deadline"
REST_TODAY = "rest_today"
BLOCK_TYPES = (BEFORE_BLOCK, AFTER_BLOCK)  # 블록 하나에 대한 알림 — 화면에서 시작·미루기를 붙인다
NUDGE_TYPES = (AFTER_BLOCK, DAILY_NIGHTLY)
CONTEST_PREP_PREFIX = "contest-"  # 관심 공모전 준비 단위 (services/contest_interest._unit_key)

MAX_REMINDER_MINUTES = 120
AFTER_BLOCK_DELAY = timedelta(minutes=30)
AFTER_BLOCK_WINDOW = timedelta(hours=3)  # 이보다 오래 지난 블록은 독촉하지 않는다 — 야간 재조정이 옮긴다
NUDGE_DAILY_MAX = 3          # 독촉은 하루 최대 3번 (FR-ALARM-02)
NUDGE_UNANSWERED_STOP = 2    # 직전 독촉을 이만큼 연달아 읽지 않았으면 그날은 멈춘다
REPLAN_LOOKBACK = timedelta(hours=24)
CONTEST_DEADLINE_BEFORE = timedelta(hours=24)

DEFAULTS = {
    "enabled": True,
    "reminder_minutes_before": 10,
    "quiet_start": "23:00",   # FR-MY-05 기본 방해금지 23:00~07:00
    "quiet_end": "07:00",
    "intensity": "normal",
    # 재조정 결과는 내 일정이 바뀌었다는 서비스 안내라 기본으로 켠다 — 선택 동의를 따르면 핵심 기능인
    # 야간 재조정이 일어나도 대부분의 사용자가 몰랐다 (10-05 사전 점검 7번). 끄는 건 알림 설정에서
    "notify_replan": True,
    "notify_deadline": None,  # None = 가입 때 선택 동의(users.agree_marketing)를 따른다
    "notify_nudge": None,
}
OPTIONAL = ("notify_deadline", "notify_nudge")
JOBS_BY_INTENSITY = {
    "low": {"before_block"},                                                     # 약: 시작 알림만
    "normal": {"before_block", "weekly_summary", "replan_result"},               # 보통 (기본)
    "high": {"before_block", "weekly_summary", "replan_result", "after_block", "daily_nightly"},  # 강: 독촉 포함
}
TOGGLE_FOR_JOB = {"replan_result": "notify_replan", "after_block": "notify_nudge", "daily_nightly": "notify_nudge"}


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def _midnight(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ── 설정 ──────────────────────────────────────────────

def settings_for(db, user_ids) -> dict[str, dict]:
    """사용자별 알림 설정. 저장한 적 없으면 기본값, 고르지 않은 선택 항목은 가입 때 선택 동의를 따른다."""
    user_ids = list(dict.fromkeys(str(u) for u in user_ids))
    if not user_ids:
        return {}
    rows = db.table("user_notification_settings").select("*").in_("user_id", user_ids).execute().data
    consent = {
        str(r["user_id"]): bool(r.get("agree_marketing"))
        for r in db.table("users").select("user_id,agree_marketing").in_("user_id", user_ids).execute().data
    }
    found = {}
    for row in rows:
        merged = dict(DEFAULTS)
        # 방해금지는 '끔'(null)도 사용자가 고른 값이다 — 저장한 행이 있으면 그대로 쓴다
        merged.update({k: v for k, v in row.items() if v is not None or k in ("quiet_start", "quiet_end")})
        found[str(row["user_id"])] = merged
    result = {}
    for u in user_ids:
        s = found.get(u, dict(DEFAULTS))
        for key in OPTIONAL:
            if s.get(key) is None:
                s[key] = consent.get(u, False)
        result[u] = s
    return result


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
    if s > e:  # 23:00 ~ 07:00 처럼 자정을 넘는다
        return current >= s or current < e
    return s <= current < e


def last_quiet_window(settings: dict, now: datetime) -> tuple[datetime, datetime] | None:
    """지금이 방해금지가 아니라면, 가장 최근에 끝난 방해금지 구간 (시작, 끝). 방해금지가 없으면 None."""
    start, end = settings.get("quiet_start"), settings.get("quiet_end")
    if not start or not end or in_quiet_hours(settings, now):
        return None
    (sh, sm), (eh, em) = _hhmm(start), _hhmm(end)
    if (sh, sm) == (eh, em):
        return None
    q_end = datetime.combine(now.date(), time(eh, em))
    if q_end > now:
        q_end -= timedelta(days=1)
    q_start = datetime.combine(q_end.date(), time(sh, sm))
    if q_start >= q_end:
        q_start -= timedelta(days=1)
    return q_start, q_end


def allowed(settings: dict, job: str, now: datetime) -> bool:
    if job == "contest_deadline":  # FR-MY-05 — 알림 전체 끄기와 별개로 동의한 사람에게만
        return bool(settings.get("notify_deadline")) and not in_quiet_hours(settings, now)
    if settings.get("enabled") is False:
        return False
    jobs = JOBS_BY_INTENSITY.get(settings.get("intensity") or "normal", JOBS_BY_INTENSITY["normal"])
    toggle = TOGGLE_FOR_JOB.get(job)
    if toggle and not settings.get(toggle):
        return False
    return job in jobs and not in_quiet_hours(settings, now)


# ── 공통 ──────────────────────────────────────────────

def _active_plans(db) -> dict[str, dict]:
    rows = db.table("study_plans").select("id,user_id,goal_title,deadline").eq("status", "active").execute().data
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


def _logs(db, user_id: str, types, since: datetime) -> list[dict]:
    rows = (
        db.table("notification_logs").select("id,type,is_read,sent_at,block_id")
        .eq("user_id", user_id).in_("type", list(types)).gte("sent_at", to_db_time(since))
        .execute().data
    )
    return sorted(rows, key=lambda r: r["sent_at"])


def _already(db, user_id: str, type_: str, *, block_id: str | None = None, since: datetime | None = None,
             contest_id: str | None = None) -> bool:
    query = db.table("notification_logs").select("id").eq("user_id", user_id).eq("type", type_)
    if block_id is not None:
        query = query.eq("block_id", block_id)
    if contest_id is not None:
        query = query.eq("contest_id", contest_id)
    if since is not None:
        query = query.gte("sent_at", to_db_time(since))
    return bool(query.limit(1).execute().data)


def _insert(db, user_id: str, type_: str, message: str, now: datetime, block_id: str | None = None,
            contest_id: str | None = None, is_read: bool = False) -> bool:
    row = {"user_id": user_id, "block_id": block_id, "type": type_, "message": message, "sent_at": to_db_time(now),
           "is_read": is_read}
    if contest_id is not None:
        row["contest_id"] = contest_id
    for _ in range(2):  # 실패하면 한 번 더 (FR-ALARM-01). 고유 인덱스에 걸린 경우는 둘 다 실패 — 이미 보낸 것
        try:
            db.table("notification_logs").insert(row).execute()
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def resting_today(db, user_id: str, now: datetime) -> bool:
    """오늘 '오늘 쉬기'를 눌렀는가 — 그날 남은 학습 알림(시작·독촉)을 보내지 않는다."""
    return _already(db, user_id, REST_TODAY, since=_midnight(now))


def _days_left(plan: dict, now: datetime) -> int | None:
    deadline = plan.get("deadline")
    if not deadline:
        return None
    return (date.fromisoformat(str(deadline)[:10]) - now.date()).days


def _late_days(db, plan_id: str, now: datetime) -> int:
    """가장 오래 밀린(지났는데 완료하지 않은) 블록이 며칠 전 것인가. 없으면 0."""
    rows = (
        db.table("plan_blocks").select("start_at,end_at,done")
        .eq("plan_id", plan_id).eq("done", False).lt("end_at", to_db_time(now))
        .execute().data
    )
    if not rows:
        return 0
    oldest = min(from_db_time(r["start_at"]) for r in rows)
    return max((now.date() - oldest.date()).days, 0)


# ── FR-ALARM-01 시작 전 ───────────────────────────────

def _missed_in_quiet(db, user_id: str, plan_ids: list[str], settings: dict, now: datetime) -> int:
    """방해금지 동안 시작해 아직 안 끝낸 블록 수. 방해금지가 끝난 뒤 첫 시작 알림에만 합친다."""
    window = last_quiet_window(settings, now)
    if window is None or not plan_ids:
        return 0
    q_start, q_end = window
    if _already(db, user_id, BEFORE_BLOCK, since=q_end):
        return 0  # 이미 방해금지 뒤 첫 알림을 보냈다
    rows = (
        db.table("plan_blocks").select("id")
        .in_("plan_id", plan_ids).eq("done", False)
        .gte("start_at", to_db_time(q_start)).lt("start_at", to_db_time(q_end))
        .execute().data
    )
    return len(rows)


def run_before_block(db, now: datetime | None = None) -> dict:
    """블록 시작 N분 전 (사용자 설정, 기본 10분). 1분마다 돌린다."""
    now = now or now_kst()
    plans = _active_plans(db)
    blocks = _blocks(db, plans, field="start_at", since=now, until=now + timedelta(minutes=MAX_REMINDER_MINUTES))
    owners = {b["id"]: str(plans[str(b["plan_id"])]["user_id"]) for b in blocks}
    settings = settings_for(db, owners.values())
    plans_of: dict[str, list[str]] = defaultdict(list)
    for pid, p in plans.items():
        plans_of[str(p["user_id"])].append(pid)
    sent = 0
    for block in sorted(blocks, key=lambda b: b["start_at"]):
        user_id = owners[block["id"]]
        s = settings[user_id]
        left = (from_db_time(block["start_at"]) - now).total_seconds() / 60
        if left <= 0 or left > int(s.get("reminder_minutes_before") or 10) or not allowed(s, "before_block", now):
            continue
        if _already(db, user_id, BEFORE_BLOCK, block_id=block["id"]) or resting_today(db, user_id, now):
            continue
        message = f"{math.ceil(left)}분 후 '{block.get('title') or '학습'}' 학습이 시작돼요."
        missed = _missed_in_quiet(db, user_id, plans_of[user_id], s, now)
        if missed:
            message += f" 방해금지 시간에 시작한 블록 {missed}개도 아직 남아 있어요."
        sent += _insert(db, user_id, BEFORE_BLOCK, message, now, block["id"])
    return {"job": "before_block", "checked": len(blocks), "sent": sent}


# ── FR-ALARM-02 미완료 · 하루 마감 ────────────────────

def nudge_allowed(db, user_id: str, now: datetime) -> bool:
    """오늘 독촉을 더 보내도 되는가 — 하루 3번, 직전 2번을 읽지 않았으면 멈춤, 오늘 쉬기면 멈춤."""
    if resting_today(db, user_id, now):
        return False
    today = _logs(db, user_id, NUDGE_TYPES, _midnight(now))
    if len(today) >= NUDGE_DAILY_MAX:
        return False
    recent = today[-NUDGE_UNANSWERED_STOP:]
    return not (len(recent) == NUDGE_UNANSWERED_STOP and not any(r.get("is_read") for r in recent))


def _deadline_text(plan: dict, now: datetime) -> str:
    days = _days_left(plan, now)
    if days is None or days < 0:
        return ""
    return f" 목표 기한까지 {days}일 남았어요." if days else " 오늘이 목표 기한이에요."


def run_after_block(db, now: datetime | None = None) -> dict:
    """끝나고 30분이 지났는데 완료하지 않은 블록. 5분마다 돌린다."""
    now = now or now_kst()
    plans = _active_plans(db)
    blocks = _blocks(db, plans, field="end_at", since=now - AFTER_BLOCK_WINDOW, until=now - AFTER_BLOCK_DELAY)
    owners = {b["id"]: str(plans[str(b["plan_id"])]["user_id"]) for b in blocks}
    settings = settings_for(db, owners.values())
    sent = 0
    for block in sorted(blocks, key=lambda b: b["end_at"]):
        user_id = owners[block["id"]]
        if not allowed(settings[user_id], "after_block", now) or not nudge_allowed(db, user_id, now):
            continue
        if _already(db, user_id, AFTER_BLOCK, block_id=block["id"]):
            continue
        plan = plans[str(block["plan_id"])]
        title = block.get("title") or "학습"
        late = _late_days(db, plan["id"], now)
        message = (
            f"'{title}' 블록을 아직 완료하지 않았어요."
            + _deadline_text(plan, now)
            + (f" 가장 오래 밀린 블록은 {late}일 전 것이에요." if late else "")
            + " 지금 시작하거나 다른 시간으로 미룰 수 있어요."
        )
        sent += _insert(db, user_id, AFTER_BLOCK, message, now, block["id"])
    return {"job": "after_block", "checked": len(blocks), "sent": sent}


def run_daily_nightly(db, now: datetime | None = None) -> dict:
    """오늘 못 끝낸 블록 수를 하루 한 번 알린다 (강도 '강' + 학습 독촉)."""
    now = now or now_kst()
    today = _midnight(now)
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
        if not nudge_allowed(db, user_id, now):
            continue
        message = f"오늘 끝내지 못한 블록이 {count}개 있어요. 밤사이 남은 기간에 다시 놓아 드려요."
        sent += _insert(db, user_id, DAILY_NIGHTLY, message, now)
    return {"job": "daily_nightly", "checked": len(left), "sent": sent}


def rest_today(db, user_id: str, now: datetime | None = None) -> bool:
    """'오늘 쉬기' (FR-ALARM-02·03) — 그날 남은 학습 알림을 멈춘다.

    오늘 못 한 블록은 밤사이 야간 재조정(FR-PLAN-06)이 남은 기간에 다시 놓는다. 두 번 눌러도 기록은 하나.
    """
    now = now or now_kst()
    if resting_today(db, user_id, now):
        return False
    # 본인이 누른 기록이라 읽음으로 남긴다 — 안 읽은 알림 수를 늘리지 않는다
    return _insert(db, user_id, REST_TODAY, "오늘은 쉬기로 했어요. 남은 블록은 밤사이 다른 날로 옮겨 드려요.", now,
                   is_read=True)


# ── 재조정 결과 (FR-MY-03) ────────────────────────────

def run_replan_results(db, now: datetime | None = None) -> dict:
    """최근 24시간 야간 재조정이 블록을 옮겼으면 알린다. 재조정은 새벽(방해금지)에 돌기 때문에
    방해금지가 끝난 뒤 이 작업이 보낸다. 5분마다 돌린다."""
    now = now or now_kst()
    runs = (
        db.table("plan_reschedule_runs").select("id,user_id,plan_id,summary,moved,undone_at,created_at")
        .gte("created_at", to_db_time(now - REPLAN_LOOKBACK))
        .execute().data
    )
    runs = [r for r in runs if (r.get("moved") or 0) > 0 and not r.get("undone_at")]
    settings = settings_for(db, [r["user_id"] for r in runs])
    sent = 0
    for run in sorted(runs, key=lambda r: r["created_at"]):
        user_id = str(run["user_id"])
        if not allowed(settings[user_id], "replan_result", now):
            continue
        if _already(db, user_id, REPLAN_RESULT, since=from_db_time(run["created_at"])):
            continue
        message = f"밤사이 일정을 다시 맞췄어요 (블록 {run['moved']}개). {run.get('summary') or ''}".strip()
        sent += _insert(db, user_id, REPLAN_RESULT, message[:300], now)
    return {"job": "replan_result", "checked": len(runs), "sent": sent}


# ── 공모전 마감 24시간 전 (FR-MY-05 · FR-CONT-07) ─────

def run_contest_deadlines(db, now: datetime | None = None) -> dict:
    """관심 등록한 공모전의 마감이 24시간 안이면 한 번 알린다. 마감일은 그날 끝(24:00)으로 본다. 30분마다."""
    now = now or now_kst()
    interests = db.table("contest_interests").select("user_id,contest_id").execute().data
    if not interests:
        return {"job": "contest_deadline", "checked": 0, "sent": 0}
    contests = {
        str(c["id"]): c
        for c in db.table("contests").select("id,title,deadline,status")
        .in_("id", list({str(i["contest_id"]) for i in interests})).execute().data
    }
    settings = settings_for(db, [i["user_id"] for i in interests])
    sent = checked = 0
    for item in interests:
        contest = contests.get(str(item["contest_id"]))
        if not contest or not contest.get("deadline") or contest.get("status") == "closed":
            continue
        ends = datetime.combine(date.fromisoformat(str(contest["deadline"])[:10]) + timedelta(days=1), time.min)
        if not (now < ends <= now + CONTEST_DEADLINE_BEFORE):
            continue
        checked += 1
        user_id = str(item["user_id"])
        if not allowed(settings[user_id], "contest_deadline", now):
            continue
        if _already(db, user_id, CONTEST_DEADLINE, contest_id=str(contest["id"])):
            continue
        message = f"관심 공모전 '{contest['title']}' 마감이 {contest['deadline']} 이에요. 제출 조건은 원문에서 확인해 주세요."
        sent += _insert(db, user_id, CONTEST_DEADLINE, message, now, contest_id=str(contest["id"]))
    return {"job": "contest_deadline", "checked": checked, "sent": sent}


# ── FR-ALARM-04 주간 요약 (일요일 20:00) ──────────────

def _duration(minutes: int) -> str:
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}시간 {mins}분"
    return f"{hours}시간" if hours else f"{mins}분"


def next_checkpoint(blocks: list[dict], today: date) -> tuple[date, str] | None:
    """FR-PACE-01 중간 목표 — 주(월~일)마다 마지막 블록이 그 주의 체크포인트다 (frontend lib/pace.js 와 같은 규칙).
    아직 다 끝내지 않은 첫 체크포인트 중 오늘 이후 것 (일요일, 블록 이름)."""
    by_week: dict[date, list[dict]] = defaultdict(list)
    for b in blocks:
        if str(b.get("unit_key") or "").startswith(CONTEST_PREP_PREFIX):
            continue  # 관심 공모전 준비 블록은 목표의 중간 목표가 아니다
        day = from_db_time(b["start_at"]).date()
        by_week[day - timedelta(days=day.weekday())].append(b)
    for monday in sorted(by_week):
        sunday = monday + timedelta(days=6)
        upto = [b for w, items in by_week.items() if w <= monday for b in items]
        if sunday >= today and not all(b.get("done") for b in upto):
            last = max(by_week[monday], key=lambda b: b["start_at"])
            return sunday, last.get("title") or "학습"
    return None


def _top_contest(db, user_id: str, week_start: date) -> str | None:
    """이번 주 추천 공모전 중 점수가 가장 높은 1건의 제목 (FR-CONT-04 결과)."""
    rows = (
        db.table("contest_recommendations").select("contest_id,rerank_score")
        .eq("user_id", user_id).eq("recommendation_week", week_start.isoformat())
        .execute().data
    )
    if not rows:
        return None
    best = max(rows, key=lambda r: float(r.get("rerank_score") or 0))
    found = db.table("contests").select("title").eq("id", best["contest_id"]).limit(1).execute().data
    return found[0]["title"] if found else None


def run_weekly_summary(db, now: datetime | None = None) -> dict:
    """이번 주(월~일) 완료율·지연 일수·다음 중간 목표·추천 공모전 1건을 한 주 한 번 알린다.
    이번 주 학습 기록이 없으면 수치 대신 목표 다시 정하기 안내만 보낸다."""
    now = now or now_kst()
    week_start = _midnight(now - timedelta(days=now.weekday()))
    plans = _active_plans(db)
    if not plans:
        return {"job": "weekly_summary", "checked": 0, "sent": 0}
    rows = db.table("plan_blocks").select("plan_id,unit_key,title,start_at,done").in_("plan_id", list(plans)).execute().data
    blocks_of: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        blocks_of[str(plans[str(row["plan_id"])]["user_id"])].append(row)
    users = list(dict.fromkeys(str(p["user_id"]) for p in plans.values()))
    minutes: dict[str, int] = defaultdict(int)
    sessions = (
        db.table("study_sessions").select("user_id,minutes")
        .in_("user_id", users).gte("started_at", to_db_time(week_start))
        .execute().data
    )
    for row in sessions:
        minutes[str(row["user_id"])] += int(row.get("minutes") or 0)

    week_end = week_start + timedelta(days=7)
    settings = settings_for(db, users)
    sent = 0
    for user_id in users:
        if not allowed(settings[user_id], "weekly_summary", now) or _already(db, user_id, WEEKLY_SUMMARY, since=week_start):
            continue
        mine = blocks_of[user_id]
        this_week = [b for b in mine if week_start <= from_db_time(b["start_at"]) < week_end]
        done = sum(bool(b.get("done")) for b in this_week)
        if not minutes[user_id] and not done:
            message = ("이번 주에는 학습 기록이 없어요. 목표 기간이나 공부 시간이 지금 생활과 맞지 않다면 "
                       "마이페이지 → 목표 관리에서 다시 정할 수 있어요.")
            sent += _insert(db, user_id, WEEKLY_SUMMARY, message, now)
            continue
        rate = round(done / len(this_week) * 100) if this_week else 0
        parts = [f"이번 주 요약: 블록 {done}/{len(this_week)}개 완료({rate}%), 공부 시간 {_duration(minutes[user_id])}."]
        late = max((_late_days(db, pid, now) for pid, p in plans.items() if str(p["user_id"]) == user_id), default=0)
        parts.append(f"가장 오래 밀린 블록은 {late}일 전 것이에요." if late else "밀린 블록은 없어요.")
        checkpoint = next_checkpoint(mine, now.date())
        if checkpoint:
            parts.append(f"다음 중간 목표: {checkpoint[0].month}/{checkpoint[0].day}까지 '{checkpoint[1]}'.")
        contest = _top_contest(db, user_id, week_start.date())
        if contest:
            parts.append(f"이번 주 추천 공모전: '{contest}'.")
        sent += _insert(db, user_id, WEEKLY_SUMMARY, " ".join(parts)[:500], now)
    return {"job": "weekly_summary", "checked": len(users), "sent": sent}
