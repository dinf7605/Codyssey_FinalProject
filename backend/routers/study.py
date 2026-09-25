"""학습 실행 API (FR-STUDY-*) — 담당 C

  POST /study/sessions  학습 세션 기록 + 블록 완료 (로그인)
  GET  /study/stats     내 누적·주간·연속·레벨 + 이번 주 달성률 (로그인, DB 기준)
  POST /study/stats     받은 기록으로 계산만 (DB 없이 화면 시험용)
  DELETE /study/blocks/{id}/done  완료 취소 — 24시간 안에만 (로그인)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_db
from services.aggregator import MIN_RECORDED_MINUTES, summarize
from services import replan
from services.plan_store import KST, active_plan_row, plan_blocks, record_session, session_events
from utils.auth import get_current_user

router = APIRouter(prefix="/study", tags=["study"])


class SessionRequest(BaseModel):
    block_id: str | None = None  # 계획 블록 없이 자유 학습도 기록할 수 있다
    started_at: datetime
    ended_at: datetime
    expected_minutes: int | None = None
    note: str | None = Field(default=None, max_length=200)  # FR-STUDY-05 메모 200자


class SessionResponse(BaseModel):
    recorded: bool
    minutes: int
    deviation_percent: int | None = None
    block_done: bool = False
    message: str


class StudyEvent(BaseModel):
    date: date
    minutes: int


class StatsRequest(BaseModel):
    events: list[StudyEvent]
    today: date


@router.get("/ping")
def study_ping():
    return {"message": "study 라우터 살아있음"}


@router.post("/sessions", response_model=SessionResponse)
def record(req: SessionRequest, user=Depends(get_current_user), db=Depends(get_db)) -> SessionResponse:
    """FR-STUDY-01 / FR-STUDY-02 — 학습 시간을 기록하고 블록을 완료 처리한다.

    5분 미만은 기록하지 않는다. 잠깐 열었다 닫은 것까지 학습으로 세면
    누적 시간과 레벨이 실제 학습량과 어긋난다.
    블록 완료는 본인 계획의 블록일 때만 한다.
    """
    minutes = int((req.ended_at - req.started_at).total_seconds() // 60)

    if minutes < MIN_RECORDED_MINUTES:
        return SessionResponse(
            recorded=False,
            minutes=max(minutes, 0),
            message=f"{MIN_RECORDED_MINUTES}분 이상 학습해야 기록됩니다.",
        )

    deviation = None
    if req.expected_minutes:
        # 예상 대비 실제 편차 — Long-term Memory 의 재료가 된다 (AI기능명세 5)
        deviation = round((minutes - req.expected_minutes) / req.expected_minutes * 100)

    block_done = record_session(
        db, user.id,
        block_id=req.block_id,
        started_at=req.started_at,
        ended_at=req.ended_at,
        minutes=minutes,
        expected_minutes=req.expected_minutes,
        note=req.note,
    )

    return SessionResponse(
        recorded=True,
        minutes=minutes,
        deviation_percent=deviation,
        block_done=block_done,
        message="학습 시간을 기록했습니다.",
    )


@router.get("/stats")
def my_stats(user=Depends(get_current_user), db=Depends(get_db)) -> dict:
    """FR-STUDY-03 / FR-STUDY-04 — 저장된 기록으로 누적·주간·연속·레벨을 계산한다 (한국 날짜 기준)."""
    today = datetime.now(KST).date()
    return {**summarize(session_events(db, user.id), today), **week_progress(db, user.id, today)}


def week_progress(db, user_id: str, today: date) -> dict:
    """이번 주(월~일) 계획 대비 완료 — "주간 달성률" (FR-STUDY-03).

    분모는 이번 주에 놓인 블록 전체(오늘 이후 포함), 분자는 그중 완료한 블록. 분 단위로 잰다.
    계획이 없거나 이번 주 블록이 없으면 달성률은 None (0% 로 보이면 안 하고 있는 것처럼 읽힌다).
    """
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    plan = active_plan_row(db, user_id)
    blocks = plan_blocks(db, plan["id"]) if plan else []
    week = [b for b in blocks if monday <= b.start.date() <= sunday]
    planned = sum(b.minutes for b in week)
    done = sum(b.minutes for b in week if b.done)
    return {
        "week_planned_minutes": planned,
        "week_done_minutes": done,
        "week_rate": round(done / planned * 100) if planned else None,
    }


@router.post("/stats")
def stats(req: StatsRequest) -> dict:
    """계산만 한다 — DB 없이 화면·테스트에서 레벨 구간을 확인할 때."""
    events = [(e.date, e.minutes) for e in req.events]
    return summarize(events, req.today)


@router.delete("/blocks/{block_id}/done", status_code=204)
def cancel_done(block_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    """FR-STUDY-02 — 완료 취소. 완료한 지 24시간 안에만 된다. 공부한 시간 기록은 남긴다."""
    try:
        replan.cancel_done(db, user.id, block_id, replan.now_kst())
    except replan.BlockNotFound:
        raise HTTPException(status_code=404, detail="내 계획에서 그 블록을 찾지 못했어요.")
    except replan.ReplanError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
