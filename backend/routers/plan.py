"""일정 생성 API (FR-PLAN-*) — 담당 C

  POST /plan/decompose         목표 -> 학습 단위 (AI Agent)
  POST /plan/decompose/stream  위와 같지만 진행 단계를 한 줄씩 흘려보낸다
  POST /plan/schedule          학습 단위 -> 블록 배치 (결정론적)
  POST /plan/reschedule        야간 재조정
  POST /plan/validate          규칙 위반 검사
"""

from __future__ import annotations

import json
import queue
import threading
from datetime import date

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from schemas.plan import Availability, Block, DecomposeResult, SchedulePlan, StudyUnit, Violation
from services.decomposer import decompose_goal
from services.scheduler import build_schedule, reschedule_incomplete
from services.validator import validate_schedule

router = APIRouter(prefix="/plan", tags=["plan"])


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


@router.get("/ping")
def plan_ping():
    return {"message": "plan 라우터 살아있음"}


@router.post("/decompose", response_model=DecomposeResult)
def decompose(req: DecomposeRequest) -> DecomposeResult:
    """FR-PLAN-02 — 목표를 학습 단위로 쪼갠다.

    AI가 실패해도 표준 커리큘럼 템플릿으로 항상 결과를 돌려준다.
    어디서 온 결과인지는 응답의 source 로 알 수 있다 (agent / partial / template).
    """
    return decompose_goal(req.goal_title, req.goal_id, req.availability, today=req.today)


@router.post("/decompose/stream")
def decompose_stream(req: DecomposeRequest) -> StreamingResponse:
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
        try:
            result = decompose_goal(
                req.goal_title, req.goal_id, req.availability,
                today=req.today, on_event=events.put,
            )
            events.put({"type": "result", "result": result.model_dump(mode="json")})
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
