"""일정 생성 API (FR-PLAN-*) — 담당 C

  POST /plan/decompose         목표 -> 학습 단위 (AI Agent)
  POST /plan/decompose/stream  위와 같지만 진행 단계를 한 줄씩 흘려보낸다
  POST /plan/schedule          학습 단위 -> 블록 배치 (결정론적)
  POST /plan/reschedule        야간 재조정
  POST /plan/validate          규칙 위반 검사
  POST /plan/save              계획 확정·저장 (로그인)
  GET  /plan/current           진행 중 계획 조회 (로그인)
  POST /plan/scope             공부량이 가용시간의 1.5배를 넘는지 + 범위 축소안
  GET  /plan/changes           최근 7일 재조정 내역 (로그인)
  POST /plan/changes/{id}/undo 가장 최근 재조정 되돌리기 1회 (로그인)
  POST /plan/replan-now        내 계획을 지금 재조정 (로그인 — 시연·사용자 테스트용)
  POST /plan/nightly           전체 야간 재조정 (매일 03:00, X-Batch-Key)
  PATCH  /plan/blocks/{id}     블록 옮기기 (로그인)
  DELETE /plan/blocks/{id}     블록 지우기 (로그인)

계획 만들기(decompose·schedule·validate)는 로그인 없이도 된다 — 비회원도 써 보고 가입하게.
저장부터 로그인이 필요하다.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import get_db, get_supabase_client
from schemas.plan import Availability, Block, DecomposeResult, SchedulePlan, StudyUnit, Violation
from services import llm
from services.decomposer import decompose_goal
from services import replan
from services.plan_store import active_plan_row, load_active_plan, log_ai_call, save_plan
from services.scope import check_scope
from services.scheduler import build_schedule, reschedule_incomplete
from services.validator import validate_schedule
from utils.auth import get_current_user, get_optional_user

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


class ScheduleRequest(BaseModel):
    units: list[StudyUnit]
    availability: Availability
    start_day: date
    deadline: date
    fixed_blocks: list[Block] = Field(default_factory=list)


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


@router.post("/schedule", response_model=SchedulePlan)
def schedule(req: ScheduleRequest) -> SchedulePlan:
    """FR-PLAN-03 — 학습 단위를 빈 시간에 놓는다. LLM을 쓰지 않는다."""
    return build_schedule(
        req.units, req.availability, req.start_day, req.deadline, req.fixed_blocks
    )


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

    plan_id = save_plan(
        db, user.id,
        goal_title=req.goal_title, goal_id=req.goal_id, deadline=req.deadline,
        source=req.source, units=req.units, blocks=req.blocks, availability=req.availability,
    )
    return SavePlanResponse(plan_id=plan_id, blocks=len(req.blocks), message="계획을 저장했습니다.")


@router.get("/current", response_model=CurrentPlanResponse | None)
def current(user=Depends(get_current_user), db=Depends(get_db)):
    """FR-PLAN-04 — 진행 중인 계획. 아직 없으면 null (화면이 "계획 만들기"를 보여준다)."""
    return load_active_plan(db, user.id)


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
    """내 계획만 지금 재조정한다 — 03:00 을 기다리지 않고 확인할 때 (시연·사용자 테스트)."""
    plan = active_plan_row(db, user.id)
    if not plan:
        raise HTTPException(status_code=404, detail="진행 중인 계획이 없어요.")
    try:
        result = replan.run_for_plan(db, plan, replan.now_kst())
    except replan.ReplanError as exc:
        _refuse(exc)
    return result or {"run_id": None, "moved": 0, "unplaced": 0, "summary": "다시 놓을 지난 블록이 없어요."}


@router.post("/nightly")
def nightly(x_batch_key: str | None = Header(default=None), db=Depends(get_db)) -> dict:
    """전체 야간 재조정 — 매일 03:00 스케줄러(Make·cron)가 부른다.

    사람이 부르는 API 가 아니라서 로그인 대신 X-Batch-Key 헤더를 확인한다 (.env 의 BATCH_SECRET).
    """
    expected = os.getenv("BATCH_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="BATCH_SECRET 환경변수가 없어 배치를 실행하지 않습니다.")
    if not replan.batch_key_ok(x_batch_key, expected):
        raise HTTPException(status_code=401, detail="배치 키가 맞지 않습니다.")
    return replan.run_nightly(db, replan.now_kst())


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
