"""공모전 검색과 준비 기간 계산 API의 요청·응답 모델."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


ContestStatus = Literal["upcoming", "open", "closed", "unknown"]
ContestSort = Literal["deadline", "latest"]
PreparationVerdict = Literal["possible", "tight", "impossible"]
PreparationHoursSource = Literal["exact", "group_median", "global_median"]


class Contest(BaseModel):
    id: str
    source: str
    source_id: str
    title: str
    host: str
    fields: list[str] = Field(default_factory=list)
    eligibility_text: str | None = None
    start_date: date | None = None
    deadline: date
    status: ContestStatus
    source_url: str
    official_url: str | None = None
    summary: str | None = None
    collected_at: datetime | None = None


class ContestListResponse(BaseModel):
    items: list[Contest]
    total: int


class PreparationEstimateRequest(BaseModel):
    weekly_hours: float = Field(gt=0, le=168)


class PreparationEstimateResponse(BaseModel):
    contest_id: str
    weekly_hours: float
    standard_hours: float
    hours_source: PreparationHoursSource
    estimated: bool
    weeks_needed: int
    days_left: int
    weeks_left: int
    verdict: PreparationVerdict
    message: str
