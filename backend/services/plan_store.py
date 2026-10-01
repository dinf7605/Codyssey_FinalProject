"""일정·학습 저장소 (담당 C) — study_plans · study_units · plan_blocks · study_sessions · ai_call_logs.

DB 기준 (backend/README.md "DB 기준")
  - 서비스 키 클라이언트를 받는다 → RLS 를 통과하므로 모든 조회·수정에 user_id 조건을 직접 건다
  - 사용자는 user_id 로만 가리킨다

시간
  배치 엔진은 시간대 없는 한국 시각(19:00 = 저녁 7시)을 쓴다.
  DB(timestamptz)에는 +09:00 을 붙여 저장하고, 꺼낼 때 한국 시각으로 바꿔 시간대를 뗀다.
  그래야 서버가 어느 나라에 있든 "저녁 7시" 가 저녁 7시로 남는다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from schemas.goal import MAX_ACTIVE_GOALS
from schemas.plan import Availability, Block, StudyUnit

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분하다


class PlanLimitReached(ValueError):
    """진행 중 목표가 이미 최대 개수(FR-GOAL-07)라 새 목표의 계획을 저장할 수 없다."""


def to_db_time(value: datetime) -> str:
    """시간대 없는 한국 시각 → DB 저장용 ISO 문자열 (+09:00)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.isoformat()


def from_db_time(value: str) -> datetime:
    """DB 의 timestamptz 문자열 → 시간대 없는 한국 시각."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(KST).replace(tzinfo=None)


# ── 계획 ──────────────────────────────────────────────

def save_plan(
    db,
    user_id: str,
    *,
    goal_title: str,
    goal_id: str,
    deadline: date,
    source: str,
    units: list[StudyUnit],
    blocks: list[Block],
    availability: Availability | None = None,
) -> str:
    """계획 하나를 저장하고 plan_id 를 돌려준다.

    빈 시간표(availability)도 같이 남긴다 — 야간 재조정이 남은 기간에 다시 놓을 때 쓴다.

    같은 목표의 이전 계획은 보관(archived)으로 돌린다 — 지우지 않는다.
    Supabase REST 에는 트랜잭션이 없어서, 단위·블록 저장이 실패하면 방금 만든 계획을 지운다
    (외래키 cascade 로 딸린 행도 함께 지워진다). 반쯤 저장된 계획이 남지 않게 한다.
    이전 계획 보관은 새 계획이 다 저장된 뒤에 한다 — 저장이 실패했을 때 진행 중 계획이 사라지지 않게.

    동시에 진행하는 목표는 최대 MAX_ACTIVE_GOALS(2)개 (FR-GOAL-07). 다른 목표가 이미 그만큼 있으면
    PlanLimitReached — 목표 하나를 끝낸(archive_plan) 뒤 만든다. 같은 목표를 다시 만드는 것은 교체라 괜찮다.
    """
    active = active_plan_rows(db, user_id)
    previous = [r["id"] for r in active if r["goal_title"] == goal_title]
    if len(active) - len(previous) >= MAX_ACTIVE_GOALS:
        raise PlanLimitReached(f"진행 중인 목표가 이미 {MAX_ACTIVE_GOALS}개예요. 하나를 끝낸 뒤 새 계획을 만들어 주세요.")

    plan = db.table("study_plans").insert({
        "user_id": user_id,
        "goal_title": goal_title,
        "goal_id": goal_id,
        "deadline": deadline.isoformat(),
        "source": source,
        "availability": availability.model_dump(mode="json") if availability else None,
    }).execute().data[0]
    plan_id = plan["id"]

    try:
        if units:
            db.table("study_units").insert([
                {
                    "plan_id": plan_id,
                    "unit_key": u.id,
                    "title": u.title,
                    "estimated_minutes": u.estimated_minutes,
                    "prerequisites": u.prerequisites,
                    "estimated": u.estimated,
                    "position": i,
                }
                for i, u in enumerate(units)
            ]).execute()
        if blocks:
            db.table("plan_blocks").insert([
                {
                    "plan_id": plan_id,
                    "unit_key": b.unit_id,
                    "title": b.title,
                    "start_at": to_db_time(b.start),
                    "end_at": to_db_time(b.end),
                    "minutes": b.minutes,
                    "locked": b.locked,
                    "done": b.done,
                }
                for b in blocks
            ]).execute()
    except Exception:
        db.table("study_plans").delete().eq("id", plan_id).eq("user_id", user_id).execute()
        raise

    if previous:
        db.table("study_plans").update({"status": "archived"}).eq("user_id", user_id).in_(
            "id", previous
        ).execute()
    return plan_id


def active_plan_rows(db, user_id: str) -> list[dict]:
    """진행 중인 계획 행들, 최근 것부터 (목표는 최대 2개)."""
    return (
        db.table("study_plans").select("*")
        .eq("user_id", user_id).eq("status", "active")
        .order("created_at", desc=True)
        .execute().data
    )


def active_plan_row(db, user_id: str) -> dict | None:
    """가장 최근의 진행 중 계획 행. 없으면 None."""
    rows = active_plan_rows(db, user_id)
    return rows[0] if rows else None


def other_plan_blocks(db, user_id: str, *, except_plan_id: str | None = None,
                      except_goal_title: str | None = None) -> list[Block]:
    """다른 목표의 진행 중 계획에 놓인 블록 — 새로 놓거나 옮길 때 피해야 할 자리.

    unit_id 앞에 계획 id 를 붙여 돌려준다. 두 계획의 단위 id 가 같을 수 있어서(템플릿 tpl-01 등)
    그대로 섞으면 배치 엔진이 '이미 놓인 단위'로 착각해 이쪽 단위를 건너뛴다.
    """
    blocks: list[Block] = []
    for plan in active_plan_rows(db, user_id):
        if plan["id"] == except_plan_id or plan["goal_title"] == except_goal_title:
            continue
        blocks += [b.model_copy(update={"unit_id": f"{plan['id']}:{b.unit_id}"}) for b in plan_blocks(db, plan["id"])]
    return blocks


def archive_plan(db, user_id: str, plan_id: str) -> bool:
    """목표 끝내기 — 계획을 보관으로 돌린다. 지우지 않는다 (학습 기록·통계는 남는다)."""
    rows = (
        db.table("study_plans").update({"status": "archived"})
        .eq("id", plan_id).eq("user_id", user_id).eq("status", "active")
        .execute().data
    )
    return bool(rows)


def plan_blocks(db, plan_id: str) -> list[Block]:
    rows = db.table("plan_blocks").select("*").eq("plan_id", plan_id).order("start_at").execute().data
    return [
        Block(
            id=str(r["id"]),
            unit_id=r["unit_key"],
            title=r["title"],
            start=from_db_time(r["start_at"]),
            end=from_db_time(r["end_at"]),
            minutes=r["minutes"],
            locked=r.get("locked", False),
            done=r.get("done", False),
            done_at=from_db_time(r["done_at"]) if r.get("done_at") else None,
        )
        for r in rows
    ]


def _unit_rows(db, plan_id: str) -> list[dict]:
    return db.table("study_units").select("*").eq("plan_id", plan_id).order("position").execute().data


def _to_unit(r: dict) -> StudyUnit:
    return StudyUnit(
        id=r["unit_key"],
        title=r["title"],
        estimated_minutes=r["estimated_minutes"],
        prerequisites=r.get("prerequisites") or [],
        estimated=r.get("estimated", False),
    )


def plan_units(db, plan_id: str) -> list[StudyUnit]:
    return [_to_unit(r) for r in _unit_rows(db, plan_id)]


def removed_unit_keys(db, plan_id: str) -> set[str]:
    """사용자가 마지막 블록을 직접 지운 단위 — 미배치로 보지 않는다 (migration 012)."""
    return {r["unit_key"] for r in _unit_rows(db, plan_id) if r.get("removed_at")}


def unplaced_units(units: list[StudyUnit], blocks: list[Block], removed: set[str]) -> list[StudyUnit]:
    """FR-PLAN-04 미배치 — 블록이 하나도 없는 단위. 직접 지운 단위는 뺀다.

    처음 만들 때 기한 안에 자리가 없었거나, 선행 단위가 못 놓여서 함께 밀린 단위다.
    """
    placed = {b.unit_id for b in blocks}
    return [u for u in units if u.id not in placed and u.id not in removed]


def mark_unit_removed(db, plan_id: str, unit_key: str, now: datetime) -> None:
    db.table("study_units").update({"removed_at": to_db_time(now)}).eq("plan_id", plan_id).eq(
        "unit_key", unit_key
    ).execute()


def load_active_plans(db, user_id: str) -> list[dict]:
    """진행 중인 계획 전부 (단위·블록 포함), 최근 것부터."""
    return [_plan_payload(db, plan) for plan in active_plan_rows(db, user_id)]


def load_active_plan(db, user_id: str) -> dict | None:
    """가장 최근의 진행 중 계획 (단위·블록 포함). 없으면 None."""
    plan = active_plan_row(db, user_id)
    return _plan_payload(db, plan) if plan else None


def _plan_payload(db, plan: dict) -> dict:
    rows = _unit_rows(db, plan["id"])
    units = [_to_unit(r) for r in rows]
    blocks = plan_blocks(db, plan["id"])
    removed = {r["unit_key"] for r in rows if r.get("removed_at")}
    return {
        "plan_id": plan["id"],
        "goal_title": plan["goal_title"],
        "goal_id": plan["goal_id"],
        "deadline": plan["deadline"],
        "source": plan["source"],
        "units": units,
        "blocks": blocks,
        "unplaced": unplaced_units(units, blocks, removed),
        "availability": plan.get("availability"),  # FR-MY-01 화면이 지금 시간표를 보여 주고 고친다
    }


def owns_block(db, user_id: str, block_id: str) -> bool:
    """블록이 이 사용자의 계획에 속하는가. 서비스 키라서 코드로 확인해야 한다.

    저장 전 블록 id(배치 엔진이 붙인 문자열)는 uuid 가 아니다 — 그대로 조회하면 DB 가
    형식 오류(500)를 내므로 먼저 걸러 "내 블록 아님" 으로 본다.
    """
    try:
        uuid.UUID(str(block_id))
    except ValueError:
        return False
    rows = db.table("plan_blocks").select("id, plan_id").eq("id", block_id).limit(1).execute().data
    if not rows:
        return False
    plans = (
        db.table("study_plans").select("id")
        .eq("id", rows[0]["plan_id"]).eq("user_id", user_id).limit(1)
        .execute().data
    )
    return bool(plans)


# ── 학습 기록 ─────────────────────────────────────────

def record_session(
    db,
    user_id: str,
    *,
    block_id: str | None,
    started_at: datetime,
    ended_at: datetime,
    minutes: int,
    expected_minutes: int | None,
    note: str | None,
    mark_done: bool = True,
    now: datetime | None = None,
) -> bool:
    """학습 세션을 저장한다. 본인 블록이면 완료 처리하고 True 를 돌려준다.

    mark_done=False 면 시간만 블록에 묶어 남기고 블록은 그대로 둔다 (조금만 하고 멈춘 경우).

    완료 시각(done_at)을 같이 남긴다 — 완료 취소는 24시간 안에만 된다 (FR-STUDY-02).
    """
    mine = bool(block_id) and owns_block(db, user_id, block_id)

    db.table("study_sessions").insert({
        "user_id": user_id,
        "block_id": block_id if mine else None,
        "started_at": to_db_time(started_at),
        "ended_at": to_db_time(ended_at),
        "minutes": minutes,
        "expected_minutes": expected_minutes,
        "note": note,
    }).execute()

    if mine and mark_done:
        # 이미 완료한 블록이면 완료 시각을 덮어쓰지 않는다 — 덮으면 24시간 취소 기한이 계속 늘어난다
        done_at = now or datetime.now(KST).replace(tzinfo=None)
        db.table("plan_blocks").update({"done": True, "done_at": to_db_time(done_at)}).eq(
            "id", block_id
        ).eq("done", False).execute()
    return mine and mark_done


NOTES_LIMIT = 200  # 메모 모아보기에 한 번에 보여 줄 최대 개수


def study_notes(db, user_id: str) -> list[dict]:
    """FR-STUDY-05 목표별로 모아본 학습 메모, 최근 메모가 있는 목표부터.

    끝낸 목표의 메모도 보여 준다 — 회고는 목표를 끝낸 뒤에 더 찾게 된다.
    계획 블록 없이 적었거나 블록이 지워진 메모는 plan_id None 묶음으로 모은다.
    """
    sessions = (
        db.table("study_sessions").select("id, block_id, started_at, minutes, note")
        .eq("user_id", user_id).order("started_at", desc=True).limit(NOTES_LIMIT * 5)
        .execute().data
    )
    sessions = [s for s in sessions if (s.get("note") or "").strip()][:NOTES_LIMIT]

    block_ids = sorted({s["block_id"] for s in sessions if s.get("block_id")})
    blocks = (
        {r["id"]: r for r in db.table("plan_blocks").select("id, plan_id, title").in_("id", block_ids).execute().data}
        if block_ids else {}
    )
    plan_ids = sorted({b["plan_id"] for b in blocks.values()})
    plans = (
        {r["id"]: r for r in db.table("study_plans").select("id, goal_title, status")
         .eq("user_id", user_id).in_("id", plan_ids).execute().data}
        if plan_ids else {}
    )

    groups: dict[str | None, dict] = {}
    for s in sessions:
        block = blocks.get(s.get("block_id"))
        plan = plans.get(block["plan_id"]) if block else None
        key = plan["id"] if plan else None
        group = groups.setdefault(key, {
            "plan_id": key,
            "goal_title": plan["goal_title"] if plan else None,
            "active": plan["status"] == "active" if plan else False,
            "notes": [],
        })
        group["notes"].append({
            "id": str(s["id"]),
            "note": s["note"].strip(),
            "started_at": from_db_time(s["started_at"]),
            "minutes": s["minutes"],
            "block_title": block["title"] if plan else None,
        })
    return list(groups.values())  # 세션을 최근 순으로 돌았으므로 묶음도 최근 메모 순


def session_events(db, user_id: str) -> list[tuple[date, int]]:
    """집계용 (한국 날짜, 분) 목록 — aggregator.summarize 에 그대로 넣는다."""
    rows = (
        db.table("study_sessions").select("started_at, minutes")
        .eq("user_id", user_id).execute().data
    )
    return [(from_db_time(r["started_at"]).date(), r["minutes"]) for r in rows]


def session_starts(db, user_id: str) -> list[tuple[datetime, int]]:
    """(시작 한국 시각, 분) 목록 — 날짜별 기록·시간대 패턴(대시보드)을 한 번의 조회로 만든다."""
    rows = (
        db.table("study_sessions").select("started_at, minutes")
        .eq("user_id", user_id).execute().data
    )
    return [(from_db_time(r["started_at"]), r["minutes"]) for r in rows]


# ── AI 호출 기록 ───────────────────────────────────────

def log_ai_call(
    db,
    *,
    user_id: str | None,
    feature: str,
    model: str,
    source: str,
    tool_calls: int,
    latency_ms: int,
    message: str = "",
) -> None:
    """AI 호출 한 건을 남긴다 (FR-ADMIN-02). 기록이 실패해도 사용자 요청은 막지 않는다."""
    try:
        db.table("ai_call_logs").insert({
            "user_id": user_id,
            "feature": feature,
            "model": model,
            "source": source,
            "tool_calls": tool_calls,
            "latency_ms": latency_ms,
            "message": message or None,
        }).execute()
    except Exception:  # noqa: BLE001 - 로그 때문에 계획 만들기가 실패하면 안 된다
        pass
