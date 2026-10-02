"""관심 공모전 등록 (FR-CONT-07) — 마감 D-7 · D-3 준비 블록을 진행 중인 목표에 넣는다.

  - 넣기 전에 어디에 놓일지 먼저 보여 주고(preview), 사용자가 확인하면 저장한다(register)
  - 그날 빈 시간이 모자라면(하루 3블록·빈 시간대·쉬는 날) 하루·이틀 앞당겨 본다. 그래도 없으면 넣지 않고
    그날 이미 있는 블록을 알려 준다 — 실사용 테스트에서 공부를 촘촘히 놓은 계정은 절반쯤 정확한 날에 자리가 없었다
  - 준비 블록은 계획의 학습 단위로 더하고 고정(locked)한다 — 야간 재조정이 옮기지 않는다
  - 관심을 해제하면 아직 안 한 준비 블록과 그 단위를 지운다. 이미 끝낸 블록은 학습 기록이라 남긴다
  - 공모전 마감 24시간 전 알림(services/alarms.run_contest_deadlines)은 이 목록을 본다

시각은 plan_store 와 같이 시간대 없는 한국 시각으로 다룬다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from schemas.plan import StudyUnit
from services.plan_store import active_plan_rows, other_plan_blocks, plan_blocks, plan_units, to_db_time
from services.replan import WEEKDAY, ReplanError, availability_of
from services.scheduler import build_schedule

PREP_DAYS = (7, 3)       # 마감 며칠 전에 준비 블록을 놓는가
PREP_MINUTES = 60
SHIFT_DAYS = 2           # 정한 날에 자리가 없으면 며칠까지 앞당겨 보는가 (늦추면 마감에 더 가까워진다)
TITLE_LIMIT = 30


class InterestNotFound(LookupError):
    pass


def _contest(db, contest_id: str) -> dict:
    rows = db.table("contests").select("id,title,deadline,status").eq("id", contest_id).limit(1).execute().data
    if not rows:
        raise InterestNotFound(contest_id)
    return rows[0]


def _interest(db, user_id: str, contest_id: str) -> dict | None:
    rows = (
        db.table("contest_interests").select("*")
        .eq("user_id", user_id).eq("contest_id", contest_id).limit(1).execute().data
    )
    return rows[0] if rows else None


def _unit_key(contest_id: str, days: int) -> str:
    return f"contest-{str(contest_id)[:8]}-d{days}"


def _label(day: date) -> str:
    return f"{day.month}/{day.day}({WEEKDAY[day.weekday()]})"


def preview(db, user_id: str, contest_id: str, now: datetime) -> dict:
    """준비 블록을 어디에 놓을지 계산만 한다. conflicts 가 있으면 넣을 수 없다."""
    contest = _contest(db, contest_id)
    if _interest(db, user_id, str(contest["id"])):
        raise ReplanError("이미 관심 등록한 공모전이에요.")
    if not contest.get("deadline"):
        raise ReplanError("마감일이 없는 공고라 준비 블록을 놓을 수 없어요. 원문에서 마감일을 확인해 주세요.")
    deadline = date.fromisoformat(str(contest["deadline"])[:10])
    today = now.date()
    if contest.get("status") == "closed" or deadline < today:
        raise ReplanError("마감이 지난 공모전이에요.")

    days = [(d, deadline - timedelta(days=d)) for d in PREP_DAYS if deadline - timedelta(days=d) >= today]
    if not days:
        raise ReplanError("마감이 3일 안이라 준비 블록을 놓을 날이 없어요.")

    plans = active_plan_rows(db, user_id)
    if not plans:
        raise ReplanError("진행 중인 목표가 있어야 준비 블록을 일정에 넣을 수 있어요. 먼저 계획을 만들어 주세요.")
    # 준비일이 기한 안에 드는 목표 중 가장 최근 것에 넣는다
    last_day = max(day for _, day in days)
    plan = next((p for p in plans if date.fromisoformat(str(p["deadline"])[:10]) >= last_day), None)
    if plan is None:
        raise ReplanError("진행 중인 목표의 기한이 공모전 준비일보다 먼저 끝나요. 목표 기한을 늘린 뒤 다시 시도해 주세요.")

    blocks = plan_blocks(db, plan["id"])
    availability = availability_of(plan, blocks)
    if availability is None:
        raise ReplanError("목표에 빈 시간표가 없어 준비 블록을 놓을 수 없어요.")
    fixed = blocks + other_plan_blocks(db, user_id, except_plan_id=plan["id"])
    title = str(contest["title"])[:TITLE_LIMIT]

    placed, conflicts = [], []
    for d, day in days:
        unit = StudyUnit(id=_unit_key(contest["id"], d), title=f"[공모전 준비] {title} · D-{d}",
                         estimated_minutes=PREP_MINUTES)
        new = None
        for shift in range(SHIFT_DAYS + 1):
            candidate = day - timedelta(days=shift)
            if candidate < today:
                break
            result = build_schedule([unit], availability, candidate, candidate,
                                    fixed_blocks=fixed + [b for _, b in placed])
            new = next((b for b in result.blocks if b.unit_id == unit.id), None)
            if new is not None:
                break
        if new is None:
            same_day = sorted((b for b in fixed if b.start.date() == day), key=lambda b: b.start)
            # 그날만 보면 '공부 가능 시간이 없다'고 잘못 말했다 — 앞 이틀에 공부 시간이 있는데 차 있었던 경우 (10-02 실사용)
            tried = [day - timedelta(days=s) for s in range(SHIFT_DAYS + 1)]
            has_slot = any(slot.weekday == t.weekday() for t in tried for slot in availability.slots)
            conflicts.append({
                "day": day.isoformat(), "label": f"D-{d} {_label(day)}",
                "reason": ("그날과 앞 이틀의 공부 시간이 이미 다른 블록으로 차 있어요." if has_slot or same_day
                           else "그날과 앞 이틀 모두 공부 가능 시간이 없어요."),
                "blocks": [{"title": b.title, "start": b.start.isoformat(), "end": b.end.isoformat()} for b in same_day],
            })
            continue
        placed.append((unit, new.model_copy(update={"locked": True})))

    return {
        "contest": {"id": str(contest["id"]), "title": contest["title"], "deadline": deadline.isoformat()},
        "plan_id": plan["id"], "goal_title": plan["goal_title"],
        "blocks": [{"unit_key": u.id, "title": b.title, "start": b.start.isoformat(), "end": b.end.isoformat(),
                    "shifted_days": (deadline - timedelta(days=int(u.id.rsplit("-d", 1)[1])) - b.start.date()).days}
                   for u, b in placed],
        "conflicts": conflicts,
        "_placed": placed,
    }


def register(db, user_id: str, contest_id: str, now: datetime) -> dict:
    """확인을 받은 뒤 저장한다. 그사이 일정이 바뀌어 자리가 없으면 넣지 않는다."""
    plan_view = preview(db, user_id, contest_id, now)
    if plan_view["conflicts"]:
        raise ReplanError("빈 시간이 모자라 준비 블록을 넣지 않았어요. 겹치는 일정을 먼저 확인해 주세요.")
    placed = plan_view.pop("_placed")
    plan_id = plan_view["plan_id"]
    position = len(plan_units(db, plan_id))
    db.table("study_units").insert([
        {"plan_id": plan_id, "unit_key": u.id, "title": u.title, "estimated_minutes": u.estimated_minutes,
         "prerequisites": [], "estimated": False, "position": position + i}
        for i, (u, _) in enumerate(placed)
    ]).execute()
    try:
        db.table("plan_blocks").insert([
            {"plan_id": plan_id, "unit_key": b.unit_id, "title": b.title, "start_at": to_db_time(b.start),
             "end_at": to_db_time(b.end), "minutes": b.minutes, "locked": True, "done": False}
            for _, b in placed
        ]).execute()
        db.table("contest_interests").insert({
            "user_id": user_id, "contest_id": plan_view["contest"]["id"], "plan_id": plan_id,
            "unit_keys": [u.id for u, _ in placed],
        }).execute()
    except Exception:
        _remove_prep(db, plan_id, [u.id for u, _ in placed])  # 반쯤 넣은 준비 블록을 남기지 않는다
        raise
    return plan_view


def _remove_prep(db, plan_id: str, unit_keys: list[str]) -> int:
    if not plan_id or not unit_keys:
        return 0
    blocks = (
        db.table("plan_blocks").select("id,unit_key,done")
        .eq("plan_id", plan_id).in_("unit_key", unit_keys).execute().data
    )
    removed = [b for b in blocks if not b.get("done")]
    kept = {b["unit_key"] for b in blocks if b.get("done")}
    for b in removed:
        db.table("plan_blocks").delete().eq("id", b["id"]).eq("plan_id", plan_id).execute()
    for key in unit_keys:
        if key not in kept:
            db.table("study_units").delete().eq("plan_id", plan_id).eq("unit_key", key).execute()
    return len(removed)


def unregister(db, user_id: str, contest_id: str) -> dict:
    """관심 해제 — 아직 안 한 준비 블록도 함께 지운다."""
    found = _interest(db, user_id, contest_id)
    if found is None:
        raise InterestNotFound(contest_id)
    removed = _remove_prep(db, found.get("plan_id"), list(found.get("unit_keys") or []))
    db.table("contest_interests").delete().eq("id", found["id"]).eq("user_id", user_id).execute()
    return {"removed_blocks": removed}


def move_after_archive(db, user_id: str, plan_id: str, now: datetime) -> dict:
    """목표를 끝낸 뒤, 그 계획에 넣어 둔 관심 공모전 준비 블록을 남은 목표로 다시 놓는다.

    준비 블록은 계획(plan_id)에 묶여 있어 목표를 끝내면 말없이 함께 사라졌다 (10-02 실사용).
    다시 놓을 목표·자리가 없으면 관심 등록은 남기고(블록 없이) 몇 건인지 돌려준다 — 화면이 알린다.
    """
    rows = (
        db.table("contest_interests").select("*")
        .eq("user_id", user_id).eq("plan_id", plan_id).execute().data
    )
    moved = unplaced = 0
    for r in rows:
        _remove_prep(db, plan_id, list(r.get("unit_keys") or []))
        db.table("contest_interests").delete().eq("id", r["id"]).eq("user_id", user_id).execute()
        try:
            register(db, user_id, str(r["contest_id"]), now)
            moved += 1
        except ReplanError:
            db.table("contest_interests").insert({
                "user_id": user_id, "contest_id": r["contest_id"], "plan_id": None, "unit_keys": [],
            }).execute()
            unplaced += 1
    return {"moved": moved, "unplaced": unplaced}


def list_interests(db, user_id: str) -> list[dict]:
    rows = db.table("contest_interests").select("*").eq("user_id", user_id).execute().data
    if not rows:
        return []
    contests = {
        str(c["id"]): c
        for c in db.table("contests").select("id,title,deadline,status")
        .in_("id", [str(r["contest_id"]) for r in rows]).execute().data
    }
    out = []
    for r in rows:
        c = contests.get(str(r["contest_id"]), {})
        out.append({"contest_id": str(r["contest_id"]), "title": c.get("title"), "deadline": c.get("deadline"),
                    "status": c.get("status"), "plan_id": r.get("plan_id"), "prep_blocks": len(r.get("unit_keys") or [])})
    return sorted(out, key=lambda x: str(x.get("deadline") or "9999"))
