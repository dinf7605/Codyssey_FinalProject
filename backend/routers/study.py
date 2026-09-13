"""학습 실행 API (FR-STUDY-*) — 담당 C

  POST /study/sessions  학습 세션 기록 (타이머 종료 시)
  POST /study/stats     누적·연속·레벨 집계
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from services.aggregator import MIN_RECORDED_MINUTES, summarize

router = APIRouter(prefix="/study", tags=["study"])


class SessionRequest(BaseModel):
    block_id: str
    started_at: datetime
    ended_at: datetime
    expected_minutes: int | None = None
    note: str | None = None


class SessionResponse(BaseModel):
    recorded: bool
    minutes: int
    deviation_percent: int | None = None
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
def record_session(req: SessionRequest) -> SessionResponse:
    """FR-STUDY-01 / FR-STUDY-02 — 학습 시간을 기록하고 블록을 완료 처리한다.

    5분 미만은 기록하지 않는다. 잠깐 열었다 닫은 것까지 학습으로 세면
    누적 시간과 레벨이 실제 학습량과 어긋난다.
    """
    minutes = int((req.ended_at - req.started_at).total_seconds() // 60)

    if minutes < MIN_RECORDED_MINUTES:
        return SessionResponse(
            recorded=False,
            minutes=minutes,
            message=f"{MIN_RECORDED_MINUTES}분 이상 학습해야 기록됩니다.",
        )

    deviation = None
    if req.expected_minutes:
        # 예상 대비 실제 편차 — Long-term Memory 의 재료가 된다 (AI기능명세 5)
        deviation = round((minutes - req.expected_minutes) / req.expected_minutes * 100)

    return SessionResponse(
        recorded=True,
        minutes=minutes,
        deviation_percent=deviation,
        message="학습 시간을 기록했습니다.",
    )


@router.post("/stats")
def stats(req: StatsRequest) -> dict:
    """FR-STUDY-03 / FR-STUDY-04 — 누적·주간·연속·레벨을 계산한다."""
    events = [(e.date, e.minutes) for e in req.events]
    return summarize(events, req.today)
