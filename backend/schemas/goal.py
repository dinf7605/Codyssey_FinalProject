"""목표 탐색에 쓰는 데이터 모양 (FR-GOAL-01~13) — 담당 B.

가용 시간(Availability)은 schemas.plan 의 것을 그대로 쓴다.
일정 생성(파이프라인 1)과 같은 모양을 써야 목표 확정 이후 그대로 넘길 수 있다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 기능명세서에서 정한 값. 코드 여기저기 흩어지지 않게 한곳에 둔다.
MAX_INTEREST_TAGS = 5              # FR-GOAL-01
FREE_TEXT_MAX_LEN = 100            # FR-GOAL-01
MAX_CANDIDATES = 20                # FR-GOAL-03
SIMILARITY_THRESHOLD = 0.60        # FR-GOAL-03
RECOMMEND_MIN = 3                  # FR-GOAL-05
RECOMMEND_MAX = 5                  # FR-GOAL-05
RECOMMENDED_BUFFER = 1.3           # FR-GOAL-09 권장 기간 = 최소 기간 × 1.3
GOAL_TITLE_MIN_LEN = 2             # FR-GOAL-06
GOAL_TITLE_MAX_LEN = 40            # FR-GOAL-06
MAX_ACTIVE_GOALS = 2               # FR-GOAL-07
NONMEMBER_DAILY_LIMIT = 3          # FR-GOAL-12
NONMEMBER_LIMIT_WINDOW_HOURS = 24  # FR-GOAL-12
COLD_HISTORY_MONTHS = 12           # FR-GOAL-11 12개월 지난 태그는 제외


class GoalCandidate(BaseModel):
    """카탈로그에서 검색된 목표 후보 하나 (FR-GOAL-03)."""

    goal_id: str
    title: str
    field: str
    tags: list[str] = Field(default_factory=list)
    kind: Literal["cert", "contest", "custom"] = "cert"
    standard_hours: int
    deadline: str | None = None  # YYYY-MM-DD. 자격증 다음 회차 시험일 / 공모전 마감일
    similarity: float = 0.0
    estimated_hours: bool = False  # 표준 학습시간이 없어 카탈로그 중앙값으로 대체했으면 True
    popularity: int = 0


class FeasibleCandidate(GoalCandidate):
    """기간 계산까지 마친 후보 (FR-GOAL-04 적합성 판정 · FR-GOAL-09 최소·권장 기간)."""

    weekly_hours: float
    min_weeks: float
    recommended_weeks: float
    feasible: bool
    reason: str = ""
    ai_generated: bool = False


class UsageInfo(BaseModel):
    """비회원 AI 호출 한도 사용 현황 (FR-GOAL-12)."""

    used: int
    limit: int
    remaining: int


class InterestRequest(BaseModel):
    session_id: str
    recent_goal_tags: list[str] = Field(default_factory=list)      # 회원 최근 목표 태그
    recent_viewed_fields: list[str] = Field(default_factory=list)  # 비회원 세션 내 조회 분야
    is_member: bool = False


class SuggestResponse(BaseModel):
    """FR-GOAL-11 — 유사 분야 추천. 이력이 아예 없으면 인기 목록으로 대체한다."""

    tags: list[str] = Field(default_factory=list)
    basis: Literal["history", "cold_start"]
    popular: list[GoalCandidate] = Field(default_factory=list)
    usage: UsageInfo


class MatchRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
    session_id: str
    is_member: bool = False
    k: int = MAX_CANDIDATES


class MatchResponse(BaseModel):
    """FR-GOAL-03 — 목표 후보 매칭."""

    candidates: list[GoalCandidate] = Field(default_factory=list)
    query_used: Literal["tags", "fallback_popular"]
    usage: UsageInfo


class FeasibilityRequest(BaseModel):
    candidates: list[GoalCandidate]
    weekly_hours: float = Field(gt=0)


class FeasibilityResponse(BaseModel):
    """FR-GOAL-04 · FR-GOAL-09 — LLM 미사용, 결정론적 계산."""

    candidates: list[FeasibleCandidate]
    all_exceeded: bool
    # 기한을 못 맞춰 candidates 에서 빠진 후보들 (표준시간·최소기간·마감일 포함).
    # 화면에 "왜 기한을 맞추기 어려운지"를 보여줄 때 쓴다. 전부 기한초과가 아니어도
    # 일부만 탈락했을 수 있어 candidates 가 비어있지 않을 때도 채워질 수 있다.
    excluded: list[FeasibleCandidate] = Field(default_factory=list)


class RecommendRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
    weekly_hours: float = Field(gt=0)
    session_id: str
    is_member: bool = False


class RecommendResponse(BaseModel):
    """FR-GOAL-05 — 목표 추천 카드."""

    candidates: list[FeasibleCandidate] = Field(default_factory=list)
    query_used: Literal["tags", "fallback_popular"]
    all_exceeded: bool = False
    # FeasibilityResponse.excluded 와 같은 뜻 — 기한을 못 맞춰 candidates 에서 빠진 후보들.
    excluded: list[FeasibleCandidate] = Field(default_factory=list)
    usage: UsageInfo


class FeedbackRequest(BaseModel):
    """FR-GOAL-08 — 추천 피드백."""

    goal_id: str
    interested: bool
    reason: Literal["field_mismatch", "too_long", "already_have"] | None = None
    session_id: str


class FeedbackResponse(BaseModel):
    ok: bool
    message: str


class ManualGoalRequest(BaseModel):
    """FR-GOAL-06 — 목표 직접 입력."""

    title: str = Field(min_length=GOAL_TITLE_MIN_LEN, max_length=GOAL_TITLE_MAX_LEN)
    due_date: str  # YYYY-MM-DD
    weekly_hours: float = Field(gt=0)


class ManualGoalWarning(BaseModel):
    """FR-GOAL-10 — 기한 실현 가능성 경고.

    카탈로그에 없는 목표라 표준 학습시간을 찾지 못하면 severity 가 "unknown" 이 되고,
    계산 대신 계산할 수 없다는 안내만 담긴다 (명세: "계산 불가를 알리고 경고를 생략").
    """

    min_weeks: float | None = None
    recommended_weeks: float | None = None
    requested_weeks: float
    severity: Literal["ok", "warn", "danger", "unknown"]
    extra_weekly_hours_needed: float | None = None
    message: str


class ConfirmRequest(BaseModel):
    """FR-GOAL-07 — 목표 확정."""

    goal_title: str
    is_member: bool = False
    # TODO: 목표 저장소(Supabase)가 붙으면 서버에서 직접 조회하도록 바꾼다.
    # 지금은 저장된 목표를 조회할 곳이 없어 프론트가 세는 값을 그대로 받는다.
    active_goal_count: int = 0


class ConfirmResponse(BaseModel):
    ok: bool
    message: str
    requires_signup: bool = False
    requires_closing_goal: bool = False
