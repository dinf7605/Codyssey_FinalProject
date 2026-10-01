"""저장된 계획 고치기 (담당 C) — 야간 재조정 · 변경 내역 · 수동 편집 · 완료 취소.

  FR-PLAN-06  매일 03:00 지난 미완료 블록을 남은 기간에 다시 놓는다
              - 실패하면 기존 일정을 그대로 둔다 (아침에 빈 일정표가 가장 나쁘다)
              - 결과는 확인 없이 반영하되 되돌리기 1회
              - 3일 연속 밀리면 기한 조정을 제안한다
  FR-PLAN-07  무엇이 왜 바뀌었는지 남긴다 (7일). 사유에 사용자를 책망하는 말을 쓰지 않는다
  FR-PLAN-05  블록을 직접 옮기거나 지운다. 옮긴 블록은 재조정이 건드리지 않는다(locked)
              선행 관계 등 규칙을 어기면 경고하고, 강행할지는 사용자가 고른다
  FR-STUDY-02 완료 취소는 24시간 안에만
  FR-PLAN-04  미배치 단위(블록이 없는 단위)를 사용자가 원할 때 빈 시간에 넣어 본다

배치(어디에 놓을지)는 여전히 scheduler.build_schedule 이 한다 — 여기는 저장된 계획에 적용하고 기록하는 일만.
시각은 전부 시간대 없는 한국 시각(datetime)으로 다룬다. DB 에 쓸 때만 to_db_time.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from schemas.plan import Availability, Block, StudyUnit, TimeSlot, Violation
from services import llm
from services.plan_store import (
    KST,
    active_plan_rows,
    from_db_time,
    mark_unit_removed,
    other_plan_blocks,
    plan_blocks,
    plan_units,
    removed_unit_keys,
    to_db_time,
    unplaced_units,
)
from services.scheduler import blocks_to_redo, build_schedule
from services.validator import validate_schedule

NIGHTLY_JOB = "plan.nightly_reschedule"
KEEP_DAYS = 7            # 변경 내역 보관 (FR-PLAN-07)
EXTEND_STREAK_DAYS = 3   # 이만큼 연속으로 밀리면 기한 조정 제안 (FR-PLAN-06)
CANCEL_DONE_HOURS = 24   # 완료 취소 가능 시간 (FR-STUDY-02)
POSTPONE_LIMIT = 2       # 알림에서 미루기는 블록당 2번까지 (FR-ALARM-03)
POSTPONE_REASON = "알림에서 미뤄"  # plan_changes.reason 머리말 — 미룬 횟수를 이것으로 센다

# 강행해도 되는 경고와 안 되는 위반. 겹침·기한 초과는 일정표가 성립하지 않는다.
HARD_VIOLATIONS = {"overlap", "deadline_exceeded"}

WEEKDAY = "월화수목금토일"

# AI 요약에 이런 말이 들어가면 버리고 규칙 문구를 쓴다 (AI 윤리: 압박하지 않는 표현)
_BLAME_WORDS = ("게으", "탓", "실패", "안 하셨", "하지 않으셨", "왜 ", "반성", "의지")


class ReplanError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 이유로 거절할 때."""


class PlanNotFound(LookupError):
    """진행 중인 내 계획이 아니다."""


class BlockNotFound(LookupError):
    pass


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def _day(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}({WEEKDAY[dt.weekday()]})"


def _when(dt: datetime) -> str:
    return f"{_day(dt)} {dt:%H:%M}"


# ── 준비 ──────────────────────────────────────────────

def availability_of(plan: dict, blocks: list[Block]) -> Availability | None:
    """계획에 저장한 빈 시간표. 예전에 저장한 계획이라 없으면 블록이 놓였던 요일·시간대로 추정한다."""
    raw = plan.get("availability")
    if raw:
        return Availability.model_validate(raw)
    spans: dict[int, tuple] = {}
    for b in blocks:
        lo, hi = spans.get(b.start.weekday(), (b.start.time(), b.end.time()))
        spans[b.start.weekday()] = (min(lo, b.start.time()), max(hi, b.end.time()))
    if not spans:
        return None
    return Availability(
        slots=[TimeSlot(weekday=wd, start=f"{s:%H:%M}", end=f"{e:%H:%M}") for wd, (s, e) in sorted(spans.items())],
        rest_weekday=None,  # 블록이 없던 요일은 애초에 빠져 있다
    )


def _place_from(availability: Availability, now: datetime) -> date:
    """오늘 빈 시간이 이미 시작됐으면 내일부터 놓는다 — 지나간 시각에 블록을 두지 않게."""
    today = now.date()
    starts = [s.start for s in availability.slots if s.weekday == today.weekday()]
    if not starts or f"{now:%H:%M}" <= min(starts):
        return today
    return today + timedelta(days=1)


def _plan_deadline(plan: dict) -> date:
    return date.fromisoformat(str(plan["deadline"])[:10])


# ── 야간 재조정 (FR-PLAN-06) ──────────────────────────

@dataclass
class Replan:
    moves: list[tuple[Block, Block]] = field(default_factory=list)  # (전, 후)
    unplaced: list[Block] = field(default_factory=list)             # 기한 안에 자리가 없어 그대로 둔 지난 블록
    blocks: list[Block] = field(default_factory=list)               # 적용 후 전체
    today: date | None = None

    @property
    def missed_moved(self) -> int:
        return sum(1 for old, _ in self.moves if old.start.date() < self.today)


def compute_replan(
    blocks: list[Block], units: list[StudyUnit], availability: Availability, deadline: date, now: datetime,
    others: list[Block] = (),
) -> Replan:
    """지난 미완료 블록(과 그 단위에 기대는 뒤 블록)을 남은 기간에 다시 놓는다. 저장은 하지 않는다.

    완료한 블록, 직접 옮긴 블록(locked)은 그대로 둔다.
    블록 id 는 그대로 두고 시각만 바꾼다 — 학습 기록·변경 내역이 같은 블록을 계속 가리키게.
    others 는 다른 목표의 블록 — 그 자리는 비켜 가고, 하루 블록 수 상한도 함께 센다.
    """
    today = now.date()
    redo_blocks = blocks_to_redo(blocks, units, today)
    if not redo_blocks:
        return Replan(blocks=list(blocks), today=today)

    redo_ids = {b.id for b in redo_blocks}
    keep = [b for b in blocks if b.id not in redo_ids]
    by_id = {u.id: u for u in units}
    redo = [by_id[b.unit_id] for b in redo_blocks if b.unit_id in by_id]
    placed = build_schedule(redo, availability, _place_from(availability, now), deadline,
                            fixed_blocks=keep + list(others))

    keep_ids = {b.id for b in keep} | {b.id for b in others}
    new_by_unit = {b.unit_id: b for b in placed.blocks if b.id not in keep_ids}

    result = Replan(blocks=list(keep), today=today)
    for old in redo_blocks:
        new = new_by_unit.get(old.unit_id)
        if new is None:
            # 뒤 블록이 자리를 못 찾으면 원래 자리에 남는다 — 순서가 어긋나면 아래 검증이 막는다
            if old.start.date() < today:
                result.unplaced.append(old)
            result.blocks.append(old)
        elif (new.start, new.end) == (old.start, old.end):
            result.blocks.append(old)
        else:
            moved = old.model_copy(update={"start": new.start, "end": new.end})
            result.moves.append((old, moved))
            result.blocks.append(moved)
    result.blocks.sort(key=lambda b: b.start)
    return result


def _template_summary(rp: Replan) -> str:
    missed, pushed, unplaced = rp.missed_moved, len(rp.moves) - rp.missed_moved, len(rp.unplaced)
    parts = []
    if missed:
        parts.append(f"지난 블록 {missed}개를 남은 기간에 다시 놓았어요.")
    if pushed:
        parts.append(f"순서를 지키려고 뒤 블록 {pushed}개도 함께 옮겼어요.")
    if unplaced:
        parts.append(f"{unplaced}개는 기한 안에 빈 시간이 없어 그대로 두었어요.")
    return " ".join(parts)


_SUMMARY_SYSTEM = (
    "학습 플래너가 밤사이 일정을 다시 맞춘 결과를 사용자에게 알리는 한 문장을 쓴다. "
    "존댓말 해요체, 60자 이내, 한 문장. 사실만 말하고 사용자를 책망하거나 재촉하지 않는다. "
    "'왜', '실패', '게으르다' 같은 말을 쓰지 않는다. 숫자는 주어진 그대로 쓴다."
)


def summarize(rp: Replan, *, use_ai: bool = True) -> tuple[str, str]:
    """변경 요약 한 줄과 출처('ai' | 'template'). AI 가 없거나 이상한 답이면 규칙 문구."""
    fallback = _template_summary(rp)
    if not use_ai:
        return fallback, "template"
    client = llm.get_client(timeout=15)
    if client is None:
        return fallback, "template"
    facts = "\n".join(
        [f"지난 블록 {rp.missed_moved}개를 다시 놓음, 순서를 지키려고 함께 옮긴 뒤 블록 "
         f"{len(rp.moves) - rp.missed_moved}개, 자리가 없어 그대로 둔 블록 {len(rp.unplaced)}개"]
        + [f"- {old.title}: {_when(old.start)} → {_when(new.start)}" for old, new in rp.moves[:5]]
    )
    try:
        resp = client.messages.create(
            model=llm.model("fast"),
            max_tokens=200,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": facts}],
        )
        text = " ".join(llm.text_of(resp).split())
    except Exception:  # noqa: BLE001 - 요약이 없어도 재조정 결과는 그대로 쓸 수 있다
        return fallback, "template"
    if not text or len(text) > 90 or any(w in text for w in _BLAME_WORDS):
        return fallback, "template"
    return text, "ai"


def run_for_plan(db, plan: dict, now: datetime, *, use_ai: bool = True) -> dict | None:
    """계획 하나를 재조정해 DB 에 반영하고 기록한다. 바꿀 것이 없으면 None.

    규칙 검증을 통과하지 못하면 ReplanError — 아무것도 바꾸지 않는다.
    블록 갱신 중 실패하면 이미 바꾼 블록을 원래대로 돌리고 예외를 다시 던진다.
    """
    user_id = plan["user_id"]
    blocks = plan_blocks(db, plan["id"])
    units = plan_units(db, plan["id"])
    availability = availability_of(plan, blocks)
    if availability is None:
        return None
    deadline = _plan_deadline(plan)
    if deadline < now.date():
        # 기한이 지난 계획은 옮길 자리가 없다 — 날마다 같은 '그대로 둠' 기록을 쌓지 않는다
        return None

    others = other_plan_blocks(db, user_id, except_plan_id=plan["id"])
    rp = compute_replan(blocks, units, availability, deadline, now, others)
    if not rp.moves and not rp.unplaced:
        return None

    # 이번 재조정으로 새로 생긴 위반만 본다 (다른 목표 블록과의 겹침·하루 상한 포함).
    # 사용자가 직접 옮긴(locked) 블록의 순서 경고는 이미 본인이 확인하고 고른 것이라 막지 않는다
    before = {_key(v) for v in validate_schedule(blocks + others, units, deadline)}
    locked = {b.id for b in rp.blocks if b.locked}
    bad = [
        v for v in validate_schedule(rp.blocks + others, units, deadline)
        if _key(v) not in before and not (v.kind == "prerequisite_violation" and v.block_id in locked)
    ]
    if bad:
        raise ReplanError(f"다시 놓은 일정이 규칙 {len(bad)}건을 어겨 기존 일정을 유지했습니다.")

    applied: list[Block] = []
    try:
        for old, new in rp.moves:
            db.table("plan_blocks").update(
                {"start_at": to_db_time(new.start), "end_at": to_db_time(new.end)}
            ).eq("id", old.id).eq("plan_id", plan["id"]).execute()
            applied.append(old)
    except Exception:
        for old in applied:  # 반쯤 바뀐 일정이 남지 않게
            db.table("plan_blocks").update(
                {"start_at": to_db_time(old.start), "end_at": to_db_time(old.end)}
            ).eq("id", old.id).eq("plan_id", plan["id"]).execute()
        raise

    summary, source = summarize(rp, use_ai=use_ai)
    run = db.table("plan_reschedule_runs").insert({
        "user_id": user_id,
        "plan_id": plan["id"],
        "summary": summary,
        "summary_source": source,
        "moved": len(rp.moves),
        "unplaced": len(rp.unplaced),
        "created_at": to_db_time(now),
    }).execute().data[0]

    rows = [
        {
            "user_id": user_id, "plan_id": plan["id"], "run_id": run["id"], "block_id": old.id,
            "origin": "nightly", "change_type": "move", "title": old.title,
            "before_start": to_db_time(old.start), "before_end": to_db_time(old.end),
            "after_start": to_db_time(new.start), "after_end": to_db_time(new.end),
            "reason": (
                f"{_day(old.start)} 블록을 {_when(new.start)}에 다시 놓았어요."
                if old.start.date() < now.date()
                else f"앞 단원이 뒤로 가서, 순서를 지키려고 {_when(new.start)}로 옮겼어요."
            ),
            "created_at": to_db_time(now),
        }
        for old, new in rp.moves
    ] + [
        {
            "user_id": user_id, "plan_id": plan["id"], "run_id": run["id"], "block_id": b.id,
            "origin": "nightly", "change_type": "unplaced", "title": b.title,
            "before_start": to_db_time(b.start), "before_end": to_db_time(b.end),
            "reason": "기한 안에 남은 빈 시간이 없어 원래 자리에 두었어요.",
            "created_at": to_db_time(now),
        }
        for b in rp.unplaced
    ]
    db.table("plan_changes").insert(rows).execute()
    return {"run_id": run["id"], "moved": len(rp.moves), "unplaced": len(rp.unplaced), "summary": summary}


def run_nightly(db, now: datetime, *, use_ai: bool = True) -> dict:
    """모든 진행 중 계획을 사용자별로 차례로 재조정한다 (매일 03:00, 무인 실행).

    한 사람이 실패해도 다음 사람은 계속한다. 결과는 batch_runs 에 남긴다 (관리자 로그).
    """
    started = datetime.now(KST)
    log = db.table("batch_runs").insert({
        "job_name": NIGHTLY_JOB, "source": "plan", "status": "running", "started_at": started.isoformat(),
    }).execute().data[0]

    plans = db.table("study_plans").select("*").eq("status", "active").execute().data
    done = moved = failed = 0
    errors: list[str] = []
    for plan in plans:
        try:
            result = run_for_plan(db, plan, now, use_ai=use_ai)
            done += 1
            moved += result["moved"] if result else 0
        except Exception as exc:  # noqa: BLE001 - 한 사람 실패로 전체 배치를 멈추지 않는다. 그 사람 일정은 그대로
            failed += 1
            errors.append(f"{plan['id']}: {exc}"[:200])

    status = "success" if not failed else ("partial" if done else "failed")
    db.table("batch_runs").update({
        "status": status,
        "collected_count": done,     # 처리한 계획 수
        "indexed_count": moved,      # 옮긴 블록 수
        "failed_count": failed,
        "error_message": "\n".join(errors)[:2000] or None,
        "finished_at": datetime.now(KST).isoformat(),
    }).eq("id", log["id"]).execute()
    return {"status": status, "plans": done, "moved": moved, "failed": failed,
            "seconds": round((datetime.now(KST) - started).total_seconds(), 2)}


def nightly_running(db, now: datetime) -> bool:
    """1시간 안에 시작해 아직 끝나지 않은 야간 배치가 있는가. 스케줄러가 두 번 불러도 겹쳐 돌지 않게.

    도중에 서버가 죽어 'running' 으로 남은 기록은 1시간이 지나면 무시한다.
    """
    rows = (
        db.table("batch_runs").select("started_at")
        .eq("job_name", NIGHTLY_JOB).eq("status", "running")
        .order("started_at", desc=True).limit(1).execute().data
    )
    return bool(rows) and from_db_time(rows[0]["started_at"]) > now - timedelta(hours=1)


def batch_key_ok(given: str | None, expected: str | None) -> bool:
    return bool(given and expected) and hmac.compare_digest(given, expected)


# ── 변경 내역 (FR-PLAN-07) ────────────────────────────

def _iso(value: str | None) -> str | None:
    return from_db_time(value).isoformat() if value else None


def _streak(runs: list[dict], today: date) -> int:
    """어제(또는 오늘)부터 거꾸로, 블록이 밀린 날이 며칠 이어졌는가."""
    days = sorted(
        {from_db_time(r["created_at"]).date() for r in runs
         if not r.get("undone_at") and (r["moved"] + r["unplaced"]) > 0},
        reverse=True,
    )
    if not days or days[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for newer, older in zip(days, days[1:]):
        if newer - older != timedelta(days=1):
            break
        streak += 1
    return streak


def recent_changes(db, user_id: str, now: datetime) -> dict:
    """진행 중인 모든 목표의 최근 7일 재조정 묶음과 블록별 변경.

    되돌리기는 목표마다 가장 최근 묶음 하나만. 기한 조정 제안도 목표별로 센다.
    """
    empty = {"runs": [], "streak_days": 0, "suggest_extension": False, "extension_goals": []}
    plans = {p["id"]: p for p in active_plan_rows(db, user_id)}
    if not plans:
        return empty

    since = now - timedelta(days=KEEP_DAYS)
    runs = [
        r for r in (
            db.table("plan_reschedule_runs").select("*")
            .eq("user_id", user_id).in_("plan_id", list(plans))
            .order("created_at", desc=True).limit(60).execute().data
        )
        if from_db_time(r["created_at"]) >= since
    ]
    if not runs:
        return empty

    changes = (
        db.table("plan_changes").select("*")
        .eq("user_id", user_id).in_("run_id", [r["id"] for r in runs])
        .order("before_start").execute().data
    )
    by_run: dict[str, list[dict]] = {}
    for c in changes:
        by_run.setdefault(c["run_id"], []).append({
            "type": c["change_type"],
            "title": c["title"],
            "before_start": _iso(c.get("before_start")),
            "after_start": _iso(c.get("after_start")),
            "reason": c["reason"],
        })

    latest_of_plan: dict[str, str] = {}
    for r in runs:  # 최근 것부터 — 목표마다 처음 만난 것이 가장 최근
        latest_of_plan.setdefault(r["plan_id"], r["id"])
    streaks = {pid: _streak([r for r in runs if r["plan_id"] == pid], now.date()) for pid in latest_of_plan}
    extension_goals = [plans[pid]["goal_title"] for pid, n in streaks.items() if n >= EXTEND_STREAK_DAYS]
    return {
        "runs": [
            {
                "id": r["id"],
                "plan_id": r["plan_id"],
                "goal_title": plans[r["plan_id"]]["goal_title"],
                "created_at": _iso(r["created_at"]),
                "summary": r["summary"],
                "ai_generated": r["summary_source"] == "ai",
                "moved": r["moved"],
                "unplaced": r["unplaced"],
                "undone": bool(r.get("undone_at")),
                "can_undo": latest_of_plan[r["plan_id"]] == r["id"] and not r.get("undone_at") and r["moved"] > 0,
                "changes": by_run.get(r["id"], []),
            }
            for r in runs
        ],
        "streak_days": max(streaks.values(), default=0),
        "suggest_extension": bool(extension_goals),
        "extension_goals": extension_goals,
    }


def undo_run(db, user_id: str, run_id: str, now: datetime) -> dict:
    """그 목표의 가장 최근 재조정을 한 번 되돌린다.

    그 뒤에 사용자가 끝냈거나 직접 옮긴 블록은 건드리지 않는다 — 사용자가 한 일이 우선이다.
    """
    plan_ids = [p["id"] for p in active_plan_rows(db, user_id)]
    found = (
        db.table("plan_reschedule_runs").select("*")
        .eq("id", run_id).eq("user_id", user_id).limit(1).execute().data
        if plan_ids else []
    )
    if not found or found[0]["plan_id"] not in plan_ids:
        raise ReplanError("가장 최근 재조정만 되돌릴 수 있어요.")
    plan_id = found[0]["plan_id"]
    latest = (
        db.table("plan_reschedule_runs").select("*")
        .eq("plan_id", plan_id).eq("user_id", user_id)
        .order("created_at", desc=True).limit(1).execute().data
    )
    if str(latest[0]["id"]) != str(run_id):
        raise ReplanError("가장 최근 재조정만 되돌릴 수 있어요.")
    if latest[0].get("undone_at"):
        raise ReplanError("이미 되돌렸어요. 되돌리기는 한 번만 됩니다.")

    current = {b.id: b for b in plan_blocks(db, plan_id)}
    moves = (
        db.table("plan_changes").select("*")
        .eq("run_id", run_id).eq("user_id", user_id).eq("change_type", "move").execute().data
    )
    restored = skipped = 0
    for c in moves:
        block = current.get(str(c["block_id"])) if c.get("block_id") else None
        if (block is None or block.done or block.locked
                or block.start != from_db_time(c["after_start"])):
            skipped += 1
            continue
        db.table("plan_blocks").update(
            {"start_at": c["before_start"], "end_at": c["before_end"]}
        ).eq("id", block.id).eq("plan_id", plan_id).execute()
        restored += 1

    db.table("plan_reschedule_runs").update({"undone_at": to_db_time(now)}).eq("id", run_id).execute()
    return {"restored": restored, "skipped": skipped}


# ── 블록 직접 편집 (FR-PLAN-05) ───────────────────────

def _load_for_edit(db, user_id: str, block_id: str):
    """진행 중인 목표 중 이 블록이 속한 계획을 찾는다. 남의 블록이나 끝낸 목표의 블록이면 BlockNotFound."""
    for plan in active_plan_rows(db, user_id):
        blocks = plan_blocks(db, plan["id"])
        target = next((b for b in blocks if b.id == str(block_id)), None)
        if target is not None:
            return plan, blocks, target
    raise BlockNotFound(block_id)


def _key(v: Violation) -> tuple:
    return (v.kind, v.block_id, v.detail)


def move_block(db, user_id: str, block_id: str, new_start: datetime, now: datetime, *, force: bool = False) -> dict:
    """블록을 옮긴다. 길이는 그대로. 옮긴 블록은 고정(locked)된다.

    이번 이동으로 새로 생긴 규칙 위반만 본다 (원래 있던 것까지 막으면 아무것도 못 옮긴다).
      - 겹침·기한 초과: 옮기지 않는다
      - 선행 순서·하루 상한 등: 경고 → force=True 면 옮긴다
    """
    plan, blocks, target = _load_for_edit(db, user_id, block_id)
    if target.done:
        raise ReplanError("완료한 블록은 옮길 수 없어요.")
    if new_start < now:
        raise ReplanError("지난 시각으로는 옮길 수 없어요.")

    units = plan_units(db, plan["id"])
    deadline = _plan_deadline(plan)
    moved = target.model_copy(update={
        "start": new_start, "end": new_start + (target.end - target.start), "locked": True,
    })
    # 다른 목표의 블록도 함께 본다 — 그 블록과 겹치거나 하루 상한을 넘기면 안 된다
    others = other_plan_blocks(db, user_id, except_plan_id=plan["id"])
    after = [moved if b.id == target.id else b for b in blocks]
    before = {_key(v) for v in validate_schedule(blocks + others, units, deadline)}
    new_problems = [v for v in validate_schedule(after + others, units, deadline) if _key(v) not in before]
    hard = [v for v in new_problems if v.kind in HARD_VIOLATIONS]

    if hard or (new_problems and not force):
        return {"applied": False, "forceable": not hard, "violations": new_problems, "block": None}

    db.table("plan_blocks").update({
        "start_at": to_db_time(moved.start), "end_at": to_db_time(moved.end), "locked": True,
    }).eq("id", target.id).eq("plan_id", plan["id"]).execute()
    db.table("plan_changes").insert({
        "user_id": user_id, "plan_id": plan["id"], "block_id": target.id,
        "origin": "manual", "change_type": "move", "title": target.title,
        "before_start": to_db_time(target.start), "before_end": to_db_time(target.end),
        "after_start": to_db_time(moved.start), "after_end": to_db_time(moved.end),
        "reason": "직접 옮겼어요" + (" (규칙 경고를 확인하고 옮김)" if new_problems else "") + ".",
        "created_at": to_db_time(now),
    }).execute()
    return {"applied": True, "forceable": True, "violations": new_problems, "block": moved}


def delete_block(db, user_id: str, block_id: str, now: datetime) -> None:
    """블록을 지운다. 완료한 블록은 학습 기록이라 지우지 않는다."""
    plan, blocks, target = _load_for_edit(db, user_id, block_id)
    if target.done:
        raise ReplanError("완료한 블록은 지울 수 없어요.")
    db.table("plan_changes").insert({
        "user_id": user_id, "plan_id": plan["id"], "block_id": target.id,
        "origin": "manual", "change_type": "delete", "title": target.title,
        "before_start": to_db_time(target.start), "before_end": to_db_time(target.end),
        "reason": "직접 지웠어요.", "created_at": to_db_time(now),
    }).execute()
    db.table("plan_blocks").delete().eq("id", target.id).eq("plan_id", plan["id"]).execute()
    if not any(b.unit_id == target.unit_id and b.id != target.id for b in blocks):
        # 단위의 마지막 블록이었다 — 미배치(자리가 없어 못 넣은 단위)와 구분해 둔다 (migration 012)
        mark_unit_removed(db, plan["id"], target.unit_id, now)


# ── 다시 놓기 공통 (미루기 · 가용 시간 바꾸기) ─────────

def _re_place(db, user_id: str, plan: dict, blocks: list[Block], units: list[StudyUnit], movable: list[Block],
              availability: Availability, start_day: date) -> tuple[list[tuple[Block, Block]], list[Block]]:
    """movable 블록을 start_day 부터 빈 시간에 순서대로 다시 놓는다. 저장은 하지 않는다.

    나머지 블록(완료·직접 옮김·이전 블록)과 다른 목표 블록은 그대로 두고 비켜 간다.
    새로 생기는 규칙 위반이 있으면 ReplanError — 반쯤 바뀐 일정을 만들지 않는다.
    """
    deadline = _plan_deadline(plan)
    moving = {b.id for b in movable}
    keep = [b for b in blocks if b.id not in moving]
    others = other_plan_blocks(db, user_id, except_plan_id=plan["id"])
    moves: list[tuple[Block, Block]] = []
    left: list[Block] = []
    after = list(keep)
    if movable and start_day <= deadline:
        by_id = {u.id: u for u in units}
        redo = [by_id[b.unit_id] for b in movable if b.unit_id in by_id]
        placed = build_schedule(redo, availability, start_day, deadline, fixed_blocks=keep + others)
        fixed_ids = {b.id for b in keep} | {b.id for b in others}
        new_by_unit = {b.unit_id: b for b in placed.blocks if b.id not in fixed_ids}
        for old in movable:
            new = new_by_unit.get(old.unit_id)
            if new is None:
                left.append(old)
                after.append(old)
            elif (new.start, new.end) == (old.start, old.end):
                after.append(old)
            else:
                moved = old.model_copy(update={"start": new.start, "end": new.end})
                moves.append((old, moved))
                after.append(moved)
    else:
        left = list(movable)
        after += movable

    before = {_key(v) for v in validate_schedule(blocks + others, units, deadline)}
    locked = {b.id for b in after if b.locked}
    bad = [
        v for v in validate_schedule(after + others, units, deadline)
        if _key(v) not in before and not (v.kind == "prerequisite_violation" and v.block_id in locked)
    ]
    if bad:
        raise ReplanError(
            f"기한 안에 순서대로 다시 놓을 자리가 없어요 (규칙 {len(bad)}건). "
            "일정에서 직접 옮기거나 기한을 조정해 주세요."
        )
    return moves, left


def _save_moves(db, user_id: str, plan: dict, moves: list[tuple[Block, Block]], now: datetime, reason) -> None:
    for old, new in moves:
        db.table("plan_blocks").update(
            {"start_at": to_db_time(new.start), "end_at": to_db_time(new.end)}
        ).eq("id", old.id).eq("plan_id", plan["id"]).execute()
    if moves:
        db.table("plan_changes").insert([
            {
                "user_id": user_id, "plan_id": plan["id"], "block_id": old.id,
                "origin": "manual", "change_type": "move", "title": old.title,
                "before_start": to_db_time(old.start), "before_end": to_db_time(old.end),
                "after_start": to_db_time(new.start), "after_end": to_db_time(new.end),
                "reason": reason(old, new), "created_at": to_db_time(now),
            }
            for old, new in moves
        ]).execute()


# ── 알림에서 미루기 (FR-ALARM-03) ─────────────────────

def postpone_counts(db, user_id: str, block_ids: list[str]) -> dict[str, int]:
    """블록별로 알림에서 미룬 횟수."""
    if not block_ids:
        return {}
    rows = (
        db.table("plan_changes").select("block_id,reason")
        .eq("user_id", user_id).in_("block_id", list(dict.fromkeys(block_ids)))
        .execute().data
    )
    counts: dict[str, int] = {}
    for r in rows:
        if str(r.get("reason") or "").startswith(POSTPONE_REASON):
            counts[str(r["block_id"])] = counts.get(str(r["block_id"]), 0) + 1
    return counts


def postpone_block(db, user_id: str, block_id: str, now: datetime) -> dict:
    """블록을 '다음 날 이후 첫 빈 시간' 으로 미룬다. 블록당 2번까지 (FR-ALARM-03).

    학습 단위는 앞뒤 순서가 있어서 이 블록만 옮기면 뒤 단원이 앞 단원보다 먼저 오게 된다.
    그래서 이 블록 뒤에 놓인, 아직 안 한 블록(직접 옮긴 것 제외)도 함께 순서대로 뒤로 민다.
    """
    plan, blocks, target = _load_for_edit(db, user_id, block_id)
    if target.done:
        raise ReplanError("완료한 블록은 미룰 수 없어요.")
    if postpone_counts(db, user_id, [target.id]).get(target.id, 0) >= POSTPONE_LIMIT:
        raise ReplanError(f"이 블록은 이미 {POSTPONE_LIMIT}번 미뤘어요. 일정에서 직접 옮기거나 오늘은 쉬어 가세요.")
    availability = availability_of(plan, blocks)
    if availability is None:
        raise ReplanError("빈 시간표가 없어 미룰 수 없어요.")
    movable = [target] + [b for b in blocks
                          if b.id != target.id and not b.done and not b.locked and b.start > target.start]
    start_day = max(_place_from(availability, now), target.start.date() + timedelta(days=1))
    moves, _ = _re_place(db, user_id, plan, blocks, plan_units(db, plan["id"]), movable, availability, start_day)
    moved = next((new for old, new in moves if old.id == target.id), None)
    if moved is None:
        raise ReplanError("기한 안에 미룰 빈 시간이 없어요. 일정에서 직접 옮기거나 기한을 조정해 주세요.")

    _save_moves(db, user_id, plan, moves, now, lambda old, new: (
        f"{POSTPONE_REASON} {_when(new.start)}로 옮겼어요." if old.id == target.id
        else f"앞 단원을 미뤄서, 순서를 지키려고 {_when(new.start)}로 옮겼어요."
    ))
    return {"applied": True, "forceable": True, "violations": [], "block": moved, "moved": len(moves)}


# ── 가용 시간 바꾸기 (FR-MY-01) ───────────────────────

def change_availability(db, user_id: str, plan_id: str, availability: Availability, now: datetime) -> dict:
    """계획의 빈 시간표를 바꾸고, 아직 안 한 앞으로의 블록을 새 시간에 다시 놓는다.

    완료한 블록·직접 옮긴 블록(locked)·이미 지난 블록은 그대로 둔다 (지난 것은 야간 재조정 몫).
    새 시간표로 다 넣을 수 없거나 규칙을 어기게 되면 아무것도 바꾸지 않는다 (일부만 옮기지 않는다).
    """
    plan = next((p for p in active_plan_rows(db, user_id) if p["id"] == str(plan_id)), None)
    if plan is None:
        raise PlanNotFound(plan_id)
    if not availability.slots:
        raise ReplanError("공부할 수 있는 시간을 하루 이상 넣어 주세요.")
    blocks = plan_blocks(db, plan["id"])
    movable = [b for b in blocks if not b.done and not b.locked and b.start >= now]
    moves, left = _re_place(db, user_id, plan, blocks, plan_units(db, plan["id"]), movable,
                            availability, _place_from(availability, now))
    if left:
        # 일부만 옮기면 새 시간표 밖에 블록이 남는다 — 다 들어갈 때만 바꾼다
        raise ReplanError(
            f"새 시간으로는 블록 {len(left)}개를 기한 안에 넣을 수 없어요. 시간을 더 넣거나 기한을 늘려 주세요."
        )

    db.table("study_plans").update({"availability": availability.model_dump()}).eq("id", plan["id"]).eq(
        "user_id", user_id
    ).execute()
    _save_moves(db, user_id, plan, moves, now,
                lambda old, new: f"공부 가능 시간을 바꿔 {_when(new.start)}로 옮겼어요.")
    return {"moved": len(moves), "left": len(left)}


# ── 완료 취소 (FR-STUDY-02) ───────────────────────────

def cancel_done(db, user_id: str, block_id: str, now: datetime) -> None:
    """완료 표시를 되돌린다. 학습 시간 기록은 남긴다 — 공부한 사실은 그대로이므로."""
    plan, _, target = _load_for_edit(db, user_id, block_id)
    if not target.done:
        raise ReplanError("완료하지 않은 블록이에요.")
    if target.done_at is None or now - target.done_at > timedelta(hours=CANCEL_DONE_HOURS):
        raise ReplanError(f"완료한 지 {CANCEL_DONE_HOURS}시간이 지나 취소할 수 없어요.")
    db.table("plan_blocks").update({"done": False, "done_at": None}).eq("id", target.id).eq(
        "plan_id", plan["id"]
    ).execute()


# ── 미배치 단위 넣기 (FR-PLAN-04) ─────────────────────

def place_unplaced(db, user_id: str, plan_id: str, now: datetime) -> dict:
    """블록이 없는 단위를 오늘 이후 빈 시간에 넣어 본다. 넣은 블록은 확인 없이 저장한다.

    이미 놓인 블록(이 목표·다른 목표 모두)은 움직이지 않고 비켜 간다 — 사용자가 누른 버튼이
    다른 일정을 흔들면 안 된다. 직접 지운 단위는 넣지 않는다. 자리가 없으면 그대로 미배치로 남는다.
    """
    plan = next((p for p in active_plan_rows(db, user_id) if p["id"] == str(plan_id)), None)
    if plan is None:
        raise PlanNotFound(plan_id)

    blocks = plan_blocks(db, plan["id"])
    units = plan_units(db, plan["id"])
    removed = removed_unit_keys(db, plan["id"])
    waiting = unplaced_units(units, blocks, removed)
    if not waiting:
        return {"placed": 0, "left": 0, "blocks": []}

    deadline = _plan_deadline(plan)
    if deadline < now.date():
        raise ReplanError("기한이 지난 목표라 넣을 자리가 없어요.")
    availability = availability_of(plan, blocks)
    if availability is None:
        raise ReplanError("빈 시간표가 없어 넣을 수 없어요. 계획을 다시 만들어 주세요.")

    others = other_plan_blocks(db, user_id, except_plan_id=plan["id"])
    live = [u for u in units if u.id not in removed]  # 지운 단위에 기대던 단위는 기다리지 않는다
    result = build_schedule(live, availability, _place_from(availability, now), deadline,
                            fixed_blocks=blocks + others)
    waiting_ids = {u.id for u in waiting}
    new = [b for b in result.blocks if b.unit_id in waiting_ids]
    if not new:
        return {"placed": 0, "left": len(waiting), "blocks": []}

    before = {_key(v) for v in validate_schedule(blocks + others, live, deadline)}
    bad = [v for v in validate_schedule(blocks + new + others, live, deadline) if _key(v) not in before]
    if bad:
        raise ReplanError(f"넣을 자리가 규칙 {len(bad)}건을 어겨 넣지 않았어요.")

    saved = db.table("plan_blocks").insert([
        {
            "plan_id": plan["id"], "unit_key": b.unit_id, "title": b.title,
            "start_at": to_db_time(b.start), "end_at": to_db_time(b.end),
            "minutes": b.minutes, "locked": False, "done": False,
        }
        for b in new
    ]).execute().data
    db.table("plan_changes").insert([
        {
            "user_id": user_id, "plan_id": plan["id"], "block_id": row["id"],
            "origin": "manual", "change_type": "add", "title": b.title,
            "after_start": to_db_time(b.start), "after_end": to_db_time(b.end),
            "reason": f"미배치였던 단원을 {_when(b.start)}에 넣었어요.",
            "created_at": to_db_time(now),
        }
        for row, b in zip(saved, new)
    ]).execute()
    placed = [b.model_copy(update={"id": str(row["id"])}) for row, b in zip(saved, new)]
    return {"placed": len(placed), "left": len(waiting) - len(placed), "blocks": placed}
