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
    deadline: date | None = None
    status: ContestStatus
    source_url: str
    official_url: str | None = None
    summary: str | None = None
    collected_at: datetime | None = None


class ContestListResponse(BaseModel):
    items: list[Contest]
    total: int


class ContestRecommendation(BaseModel):
    contest: Contest
    matching_tags: list[str]
    similarity: float
    deadline_score: float
    eligibility_score: float
    rerank_score: float
    reason: str
    ai_generated: bool = False


class ContestRecommendationResponse(BaseModel):
    items: list[ContestRecommendation]
    method: Literal["title_keywords", "title_claude"] = "title_keywords"
    message: str | None = None


class ContestFeedbackInput(BaseModel):
    rating: Literal["helpful", "not_relevant"]
    reason: Literal["field", "difficulty", "deadline"] | None = None


class ContestFeedbackResponse(BaseModel):
    contest_id: str
    rating: Literal["helpful", "not_relevant"]
    reason: str | None
    similarity: float | None
    rerank_score: float | None


class PreparationEstimateRequest(BaseModel):
    weekly_hours: float = Field(gt=0, le=168)
    # 링크 전용 공고는 출처에서 날짜·분야를 수집하지 않는다. 입력값은 저장하지 않는다.
    deadline: date | None = None
    field: str | None = Field(default=None, max_length=50)


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
