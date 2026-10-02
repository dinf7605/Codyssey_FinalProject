"""일정 생성 API (FR-PLAN-*) — 담당 C

  POST /plan/decompose         목표 -> 학습 단위 (AI Agent)
  POST /plan/decompose/stream  위와 같지만 진행 단계를 한 줄씩 흘려보낸다
  POST /plan/schedule          학습 단위 -> 블록 배치 (결정론적)
  POST /plan/reschedule        야간 재조정
  POST /plan/validate          규칙 위반 검사
  POST /plan/save              계획 확정·저장 (로그인) — 진행 중 목표는 최대 2개
  GET  /plan/active            진행 중 계획 전부 (로그인) — 목표 최대 2개
  GET  /plan/current           가장 최근 계획 하나 (로그인, 예전 화면 호환)
  POST /plan/{id}/archive      목표 끝내기 (로그인)
  POST /plan/{id}/place-unplaced  미배치 단위를 빈 시간에 넣어 보기 (로그인)
  POST /plan/scope             공부량이 가용시간의 1.5배를 넘는지 + 범위 축소안
  GET  /plan/changes           최근 7일 재조정 내역 (로그인)
  POST /plan/changes/{id}/undo 가장 최근 재조정 되돌리기 1회 (로그인)
  POST /plan/replan-now        내 계획을 지금 재조정 (로그인 — 시연·사용자 테스트용)
  POST /plan/nightly           전체 야간 재조정 (매일 03:00, X-Batch-Key)
  PATCH  /plan/blocks/{id}     블록 옮기기 (로그인)
  DELETE /plan/blocks/{id}     블록 지우기 (로그인)
  POST /plan/blocks/{id}/postpone  알림에서 미루기 — 다음 날 이후 첫 빈 시간 (로그인)
  PUT  /plan/{id}/availability     공부 가능 시간 바꾸기 — 앞으로의 블록을 다시 놓음 (로그인)
  GET  /plan/{id}/calendar.ics     내 캘린더로 내보내기 (.ics, 로그인)

계획 만들기(decompose·schedule·validate)는 로그인 없이도 된다 — 비회원도 써 보고 가입하게.
저장부터 로그인이 필요하다.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from db import get_db, get_supabase_client
from schemas.plan import Availability, Block, DecomposeResult, SchedulePlan, StudyUnit, Violation
from services import llm
from services.decomposer import decompose_goal
from services import calendar_export, replan
from services.plan_store import (
    PlanLimitReached,
    active_plan_rows,
    archive_plan,
    load_active_plan,
    load_active_plans,
    log_ai_call,
    other_plan_blocks,
    plan_blocks,
    save_plan,
)
from services.scope import check_scope
from services.scheduler import build_schedule, reschedule_incomplete
from services.validator import validate_schedule
from utils.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plan", tags=["plan"])


def _log_decompose(user, result: DecomposeResult, started: float) -> None:
    """학습 분해 한 번을 ai_call_logs 에 남긴다. DB 가 없거나 실패해도 계획 만들기는 계속된다."""
    try:
        db = get_supabase_client()
    except Exception:  # noqa: BLE001 - DB 설정 전(로컬 개발)에도 계획 만들기는 된다
        return
    log_ai_call(
        db,
        user_id=getattr(user, "id", None),
        feature="plan.decompose",
        model=llm.model("main"),
        source=result.source,
        tool_calls=result.tool_calls,
        latency_ms=int((time.monotonic() - started) * 1000),
        message=result.message,
    )


class DecomposeRequest(BaseModel):
    goal_title: str
    goal_id: str = "custom"
    availability: Availability | None = None
    today: date | None = None  # 비우면 서버 날짜. 사용자 시간대가 다를 때 넘긴다


class BusyTime(BaseModel):
    """구글 캘린더의 바쁜 시간 하나 (FR-PLAN-01). 일정 제목·참석자는 없다."""

    start: datetime  # 한국 시각. 시간대가 붙어 오면 한국 시각으로 바꾼다
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _kst(cls, value: datetime) -> datetime:
        return value.astimezone(replan.KST).replace(tzinfo=None) if value.tzinfo else value


class ScheduleRequest(BaseModel):
    units: list[StudyUnit]
    availability: Availability
    start_day: date
    deadline: date
    fixed_blocks: list[Block] = Field(default_factory=list)
    # 로그인 상태면 다른 목표의 진행 중 계획 블록을 피해서 놓는다. 같은 목표(다시 만들기)의 옛 계획은 빼고
    goal_title: str | None = None
    # FR-PLAN-01 구글 캘린더의 바쁜 시간 (POST /calendar/busy 결과). 이 시간에는 놓지 않는다
    busy: list[BusyTime] = Field(default_factory=list, max_length=1000)


class RescheduleRequest(BaseModel):
    blocks: list[Block]
    units: list[StudyUnit]
    availability: Availability
    today: date
    deadline: date


class ValidateRequest(BaseModel):
    blocks: list[Block]
    units: list[StudyUnit]
    deadline: date


class ValidateResponse(BaseModel):
    ok: bool
    violations: list[Violation]


class SavePlanRequest(BaseModel):
    goal_title: str = Field(min_length=1, max_length=80)
    goal_id: str = "custom"
    deadline: date
    source: Literal["agent", "partial", "template"]
    units: list[StudyUnit] = Field(min_length=1)
    blocks: list[Block]
    availability: Availability | None = None  # 야간 재조정이 다시 놓을 때 쓴다


class SavePlanResponse(BaseModel):
    plan_id: str
    blocks: int
    message: str


class CurrentPlanResponse(BaseModel):
    plan_id: str
    goal_title: str
    goal_id: str
    deadline: date
    source: str
    units: list[StudyUnit]
    blocks: list[Block]
    unplaced: list[StudyUnit] = []  # FR-PLAN-04 블록이 없는 단위 (직접 지운 단위는 빠짐)
    availability: Availability | None = None  # FR-MY-01 저장한 빈 시간표 (예전 계획은 없을 수 있다)


@router.get("/ping")
def plan_ping():
    return {"message": "plan 라우터 살아있음"}


@router.post("/decompose", response_model=DecomposeResult)
def decompose(req: DecomposeRequest, user=Depends(get_optional_user)) -> DecomposeResult:
    """FR-PLAN-02 — 목표를 학습 단위로 쪼갠다.

    AI가 실패해도 표준 커리큘럼 템플릿으로 항상 결과를 돌려준다.
    어디서 온 결과인지는 응답의 source 로 알 수 있다 (agent / partial / template).
    """
    started = time.monotonic()
    result = decompose_goal(req.goal_title, req.goal_id, req.availability, today=req.today)
    _log_decompose(user, result, started)
    return result


@router.post("/decompose/stream")
def decompose_stream(req: DecomposeRequest, user=Depends(get_optional_user)) -> StreamingResponse:
    """FR-PLAN-02 + 진행 표시 — 에이전트가 실제로 한 일을 한 줄(JSON)씩 보낸다.

    최대 60초가 걸리는 작업이라, 화면이 멈춘 것처럼 보이지 않게 하려는 것이다.

      {"type": "start", "budget_seconds": 60}
      {"type": "thinking", "step": 1}
      {"type": "tool", "name": "search_curriculum"}
      ...
      {"type": "result", "result": {...DecomposeResult...}}   <- 항상 마지막 줄

    에이전트는 별도 스레드에서 돌고, 이벤트는 큐를 거쳐 응답으로 나간다.
    """
    events: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        started = time.monotonic()
        try:
            result = decompose_goal(
                req.goal_title, req.goal_id, req.availability,
                today=req.today, on_event=events.put,
            )
            events.put({"type": "result", "result": result.model_dump(mode="json")})
            _log_decompose(user, result, started)
        except Exception as exc:  # noqa: BLE001 - 스트림을 열어둔 채로 끝나면 화면이 계속 기다린다
            events.put({"type": "error", "message": f"계획을 만들지 못했습니다. ({type(exc).__name__})"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def lines():
        while (event := events.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    # 프록시가 응답을 모았다가 한 번에 보내지 않도록 버퍼링을 끈다
    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _others_for(user, goal_title: str | None) -> list[Block]:
    """로그인한 사용자의 다른 목표 블록. 비회원이거나 DB 가 없으면 빈 목록."""
    if user is None:
        return []
    try:
        return other_plan_blocks(get_supabase_client(), user.id, except_goal_title=goal_title)
    except Exception:  # noqa: BLE001 - 계획 만들기는 DB 없이도 된다 (저장할 때 한 번 더 검사한다)
        return []


@router.post("/schedule", response_model=SchedulePlan)
def schedule(req: ScheduleRequest, user=Depends(get_optional_user)) -> SchedulePlan:
    """FR-PLAN-03 — 학습 단위를 빈 시간에 놓는다. LLM을 쓰지 않는다.

    진행 중인 다른 목표가 있으면 그 블록 자리는 비켜 가고 하루 블록 수도 함께 센다 (목표 최대 2개).
    결과에는 이번 목표의 블록만 담는다 — 다른 목표 블록이 섞여 저장되지 않게.
    """
    others = _others_for(user, req.goal_title)
    plan = build_schedule(
        req.units, req.availability, req.start_day, req.deadline, req.fixed_blocks + others,
        busy=[(b.start, b.end) for b in req.busy],
    )
    if others:
        other_ids = {b.id for b in others}
        plan.blocks = [b for b in plan.blocks if b.id not in other_ids]
        plan.notes.append(f"진행 중인 다른 목표의 블록 {len(others)}개와 겹치지 않게 놓았습니다.")
    if req.busy:
        plan.notes.append(f"구글 캘린더의 바쁜 시간 {len(req.busy)}개를 피해서 놓았습니다.")
    return plan


@router.post("/reschedule", response_model=SchedulePlan)
def reschedule(req: RescheduleRequest) -> SchedulePlan:
    """FR-PLAN-06 — 야간 재조정.

    실패해도 기존 일정이 깨지지 않는 것이 최우선이다.
    예외가 나면 받은 블록을 그대로 돌려준다.
    """
    try:
        return reschedule_incomplete(
            req.blocks, req.units, req.availability, req.today, req.deadline
        )
    except Exception as exc:  # noqa: BLE001
        return SchedulePlan(
            blocks=req.blocks,
            notes=[f"재조정에 실패해 기존 일정을 유지했습니다. ({type(exc).__name__})"],
        )


@router.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest) -> ValidateResponse:
    """규칙 검증기 — AI 품질 평가의 '일정 실현 가능성 100%'를 재는 엔드포인트."""
    problems = validate_schedule(req.blocks, req.units, req.deadline)
    return ValidateResponse(ok=not problems, violations=problems)


@router.post("/save", response_model=SavePlanResponse)
def save(req: SavePlanRequest, user=Depends(get_current_user), db=Depends(get_db)) -> SavePlanResponse:
    """계획 확정 — 에이전트의 save_plan 도구가 "사용자 확인 필요"로 넘긴 동작을 사람이 누른다 (AI기능명세 2).

    저장 전에 규칙 검증기를 한 번 더 돌린다. 화면에서 온 블록을 그대로 믿지 않는다 —
    규칙을 어긴 일정은 저장하지 않는다 ("일정 실현 가능성 100%").
    """
    problems = validate_schedule(req.blocks, req.units, req.deadline)
    if problems:
        raise HTTPException(
            status_code=400,
            detail=f"규칙에 맞지 않는 블록이 {len(problems)}개 있어 저장하지 않았습니다. 다시 만들어 주세요.",
        )

    # 다른 목표의 블록과 겹치거나 하루 상한을 넘기면 안 된다 — 이번에 새로 생기는 위반만 본다
    others = other_plan_blocks(db, user.id, except_goal_title=req.goal_title)
    if others:
        key = lambda v: (v.kind, v.block_id, v.detail)  # noqa: E731
        before = {key(v) for v in validate_schedule(others, [], req.deadline)}
        clash = [v for v in validate_schedule(req.blocks + others, [], req.deadline)
                 if key(v) not in before and v.kind != "deadline_exceeded"]
        if clash:
            raise HTTPException(
                status_code=400,
                detail="진행 중인 다른 목표의 일정과 겹쳐 저장하지 않았습니다. 계획을 다시 만들어 주세요.",
            )

    try:
        plan_id = save_plan(
            db, user.id,
            goal_title=req.goal_title, goal_id=req.goal_id, deadline=req.deadline,
            source=req.source, units=req.units, blocks=req.blocks, availability=req.availability,
        )
    except PlanLimitReached as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:  # noqa: BLE001 - DB 제약 위반 등. 500 으로 끊기면 화면엔 'Failed to fetch' 만 보였다 (10-02)
        logger.exception("계획 저장 실패")
        raise HTTPException(status_code=503, detail="계획을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    return SavePlanResponse(plan_id=plan_id, blocks=len(req.blocks), message="계획을 저장했습니다.")


@router.get("/current", response_model=CurrentPlanResponse | None)
def current(user=Depends(get_current_user), db=Depends(get_db)):
    """가장 최근에 저장한 진행 중 계획 하나. 없으면 null. 목표가 둘이면 /plan/active 를 쓴다."""
    return load_active_plan(db, user.id)


class ActivePlansResponse(BaseModel):
    plans: list[CurrentPlanResponse]
    max_plans: int


@router.get("/active", response_model=ActivePlansResponse)
def active(user=Depends(get_current_user), db=Depends(get_db)):
    """FR-PLAN-04 · FR-GOAL-07 — 진행 중인 계획 전부 (최근 것부터). 목표는 동시에 최대 2개."""
    from schemas.goal import MAX_ACTIVE_GOALS

    return ActivePlansResponse(plans=load_active_plans(db, user.id), max_plans=MAX_ACTIVE_GOALS)


@router.post("/{plan_id}/archive")
def archive(plan_id: str, user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    """목표 끝내기 — 계획을 보관한다. 학습 기록·통계는 남고, 야간 재조정 대상에서 빠진다."""
    if not archive_plan(db, user.id, plan_id):
        raise HTTPException(status_code=404, detail="진행 중인 내 계획에서 찾지 못했어요.")
    # 이 목표에 넣어 둔 관심 공모전 준비 블록은 남은 목표로 옮긴다 (못 옮기면 몇 건인지 알린다)
    from services import contest_interest
    contests = contest_interest.move_after_archive(db, str(user.id), plan_id, replan.now_kst())
    return {"message": "목표를 끝냈어요. 학습 기록은 그대로 남아요.", "contest_prep": contests}


class PlaceUnplacedResponse(BaseModel):
    placed: int
    left: int                # 그래도 자리가 없어 남은 단위 수
    blocks: list[Block]


@router.post("/{plan_id}/place-unplaced", response_model=PlaceUnplacedResponse)
def place_unplaced(plan_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """FR-PLAN-04 — 미배치 단위를 오늘 이후 빈 시간에 넣어 본다. 이미 놓인 블록은 움직이지 않는다."""
    try:
        return replan.place_unplaced(db, user.id, plan_id, replan.now_kst())
    except replan.PlanNotFound:
        raise HTTPException(status_code=404, detail="진행 중인 내 계획에서 찾지 못했어요.")
    except replan.ReplanError as exc:
        _refuse(exc)


# ── 공부량 점검 (FR-PLAN-02) ───────────────────────────

class ScopeRequest(BaseModel):
    units: list[StudyUnit] = Field(min_length=1)
    availability: Availability
    start_day: date
    deadline: date


@router.post("/scope")
def scope(req: ScopeRequest) -> dict:
    """총 공부량이 기한까지 가용시간의 1.5배를 넘으면 범위 축소안(뺄 단위·늘릴 기한)을 준다. LLM 미사용."""
    return check_scope(req.units, req.availability, req.start_day, req.deadline)


# ── 야간 재조정 · 변경 내역 (FR-PLAN-06 / FR-PLAN-07) ──

def _refuse(exc: Exception):
    if isinstance(exc, replan.BlockNotFound):
        raise HTTPException(status_code=404, detail="내 계획에서 그 블록을 찾지 못했어요.")
    raise HTTPException(status_code=409, detail=str(exc))


@router.get("/changes")
def changes(user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    """최근 7일 동안 재조정이 무엇을 왜 바꿨는지. 없으면 runs 가 빈 목록 (화면은 영역을 숨긴다)."""
    return replan.recent_changes(db, user.id, replan.now_kst())


@router.post("/changes/{run_id}/undo")
def undo_changes(run_id: str, user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    """가장 최근 재조정을 한 번 되돌린다. 그 뒤에 끝냈거나 직접 옮긴 블록은 그대로 둔다."""
    try:
        return replan.undo_run(db, user.id, run_id, replan.now_kst())
    except replan.ReplanError as exc:
        _refuse(exc)


@router.post("/replan-now")
def replan_now(user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    """내 계획들만 지금 재조정한다 — 03:00 을 기다리지 않고 확인할 때 (시연·사용자 테스트)."""
    plans = active_plan_rows(db, user.id)
    if not plans:
        raise HTTPException(status_code=404, detail="진행 중인 계획이 없어요.")
    now = replan.now_kst()
    moved = unplaced = 0
    summaries: list[str] = []
    for plan in plans:
        try:
            result = replan.run_for_plan(db, plan, now)
        except replan.ReplanError as exc:
            summaries.append(f"{plan['goal_title']}: {exc}")
            continue
        if result:
            moved += result["moved"]
            unplaced += result["unplaced"]
            summaries.append(result["summary"] if len(plans) == 1 else f"{plan['goal_title']}: {result['summary']}")
    return {
        "moved": moved,
        "unplaced": unplaced,
        "summary": " ".join(summaries) or "다시 놓을 지난 블록이 없어요.",
    }


@router.post("/nightly", status_code=202)
def nightly(
    background: BackgroundTasks, x_batch_key: str | None = Header(default=None), db=Depends(get_db)
) -> dict:
    """전체 야간 재조정 — 매일 03:00 스케줄러(Make·cron)가 부른다.

    사람이 부르는 API 가 아니라서 로그인 대신 X-Batch-Key 헤더를 확인한다 (.env 의 BATCH_SECRET).
    사용자마다 AI 요약을 부르느라 오래 걸릴 수 있어서 바로 202 로 답하고 뒤에서 돈다 —
    스케줄러의 HTTP 시간 제한(Make 기본 40초)에 걸려 실패로 보이지 않게. 결과는 batch_runs 에 남는다.
    """
    expected = os.getenv("BATCH_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="BATCH_SECRET 환경변수가 없어 배치를 실행하지 않습니다.")
    if not replan.batch_key_ok(x_batch_key, expected):
        raise HTTPException(status_code=401, detail="배치 키가 맞지 않습니다.")
    now = replan.now_kst()
    if replan.nightly_running(db, now):
        raise HTTPException(status_code=409, detail="야간 재조정이 이미 실행 중입니다.")
    background.add_task(replan.run_nightly, db, now)
    return {"status": "started", "message": "결과는 batch_runs 에 남습니다."}


# ── 블록 직접 편집 (FR-PLAN-05) ────────────────────────

class MoveBlockRequest(BaseModel):
    start: datetime          # 한국 시각, 시간대 없이 (2026-10-05T19:00:00). 길이는 그대로
    force: bool = False      # 경고(선행 순서 등)를 보고도 옮길 때


class MoveBlockResponse(BaseModel):
    applied: bool
    forceable: bool          # False 면 겹침·기한 초과 — 강행할 수 없다
    violations: list[Violation]
    block: Block | None = None


@router.patch("/blocks/{block_id}", response_model=MoveBlockResponse)
def move_block(block_id: str, req: MoveBlockRequest, user=Depends(get_current_user), db=Depends(get_db)):
    """블록을 옮긴다. 옮긴 블록은 야간 재조정에서 고정된다.

    규칙에 걸리면 옮기지 않고 위반 목록을 돌려준다 (applied=false). 화면이 경고를 보여주고,
    사용자가 강행을 고르면 force=true 로 다시 부른다. 겹침·기한 초과는 강행할 수 없다.
    """
    start = req.start.astimezone(replan.KST).replace(tzinfo=None) if req.start.tzinfo else req.start
    try:
        return replan.move_block(db, user.id, block_id, start, replan.now_kst(), force=req.force)
    except (replan.ReplanError, replan.BlockNotFound) as exc:
        _refuse(exc)


@router.delete("/blocks/{block_id}", status_code=204)
def delete_block(block_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """블록을 지운다. 완료한 블록은 학습 기록이라 지우지 않는다."""
    try:
        replan.delete_block(db, user.id, block_id, replan.now_kst())
    except (replan.ReplanError, replan.BlockNotFound) as exc:
        _refuse(exc)


@router.post("/blocks/{block_id}/postpone", response_model=MoveBlockResponse)
def postpone_block(block_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """FR-ALARM-03 — 알림에서 '미루기'. 다음 날 이후 첫 빈 시간으로 옮긴다 (다른 블록은 그대로)."""
    try:
        return replan.postpone_block(db, user.id, block_id, replan.now_kst())
    except (replan.ReplanError, replan.BlockNotFound) as exc:
        _refuse(exc)


@router.get("/{plan_id}/calendar.ics")
def export_calendar(plan_id: str, user=Depends(get_current_user), db=Depends(get_db)) -> Response:
    """FR-PLAN-08 — 오늘 이후의 안 한 블록을 .ics 로 내려준다 (구글·애플·아웃룩 캘린더에서 가져오기)."""
    plan = next((p for p in active_plan_rows(db, user.id) if p["id"] == str(plan_id)), None)
    if plan is None:
        raise HTTPException(status_code=404, detail="진행 중인 내 계획에서 찾지 못했어요.")
    body = calendar_export.build_ics(plan["goal_title"], plan_blocks(db, plan["id"]), replan.now_kst())
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="studypace.ics"', "Cache-Control": "no-store"},
    )


class AvailabilityChangeResponse(BaseModel):
    moved: int   # 새 시간으로 옮긴 블록 수
    left: int    # 항상 0 — 자리가 모자라면 바꾸지 않고 409 로 알린다


@router.put("/{plan_id}/availability", response_model=AvailabilityChangeResponse)
def change_availability(plan_id: str, req: Availability, user=Depends(get_current_user), db=Depends(get_db)):
    """FR-MY-01 — 공부 가능 시간을 바꾸고, 아직 안 한 앞으로의 블록을 새 시간에 다시 놓는다."""
    try:
        return replan.change_availability(db, user.id, plan_id, req, replan.now_kst())
    except replan.PlanNotFound:
        raise HTTPException(status_code=404, detail="진행 중인 내 계획에서 찾지 못했어요.")
    except replan.ReplanError as exc:
        _refuse(exc)
