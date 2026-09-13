"""일정 생성에 쓰는 데이터 모양 (FR-PLAN-*).

Pydantic 모델을 쓰는 이유는 두 가지다.
1. API 요청·응답의 형식을 코드로 못박아 둔다.
2. AI가 만든 학습 분해 결과를 같은 모델로 검증한다 — 형식이 틀리면 여기서 걸린다.
   (AI기능명세 6: JSON 스키마 검증 실패 시 1회 재시도 후 템플릿 분해)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# 기능명세서에서 정한 값들. 코드 여기저기 흩어지지 않게 한곳에 둔다.
MIN_UNIT_MINUTES = 30
MAX_UNIT_MINUTES = 120
MAX_BLOCKS_PER_DAY = 3
MAX_CONTINUOUS_MINUTES = 120  # 연속 2시간 초과 금지
BREAK_MINUTES = 10            # 블록 사이 최소 쉬는 시간


class StudyUnit(BaseModel):
    """학습 단위 하나. 30~120분짜리로 쪼갠 결과물."""

    id: str
    title: str
    estimated_minutes: int = Field(ge=MIN_UNIT_MINUTES, le=MAX_UNIT_MINUTES)
    prerequisites: list[str] = Field(default_factory=list)
    # 검색된 커리큘럼 밖의 내용이면 추정임을 표시한다 (AI기능명세 4)
    estimated: bool = False


class TimeSlot(BaseModel):
    """요일별로 공부할 수 있는 시간대. weekday 0=월 ... 6=일."""

    weekday: int = Field(ge=0, le=6)
    start: str  # "HH:MM"
    end: str    # "HH:MM"

    @field_validator("start", "end")
    @classmethod
    def _check_time(cls, v: str) -> str:
        hh, _, mm = v.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError("시간은 HH:MM 형식이어야 합니다")
        return v


class Availability(BaseModel):
    """주간 가용 시간. rest_weekday 는 주 1일 휴식일(기본 일요일)."""

    slots: list[TimeSlot]
    rest_weekday: int | None = 6


class Block(BaseModel):
    """달력에 실제로 놓인 학습 블록."""

    id: str
    unit_id: str
    title: str
    start: datetime
    end: datetime
    minutes: int
    locked: bool = False  # 수동으로 옮긴 블록은 야간 재조정에서 건드리지 않는다 (FR-PLAN-05)
    done: bool = False


class Violation(BaseModel):
    """규칙 검증기가 찾아낸 문제 하나."""

    kind: Literal[
        "deadline_exceeded",
        "prerequisite_violation",
        "daily_limit_exceeded",
        "continuous_limit_exceeded",
        "overlap",
    ]
    block_id: str
    detail: str


class SchedulePlan(BaseModel):
    """배치 결과.

    마감 안에 다 넣지 못하면 초과분을 unplaced 에 남긴다.
    조용히 버리지 않는 것이 핵심이다 — 사용자가 범위를 줄일지 기한을 늘릴지 정해야 한다.
    """

    blocks: list[Block]
    unplaced: list[StudyUnit] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DecomposeResult(BaseModel):
    """학습 분해 결과 (FR-PLAN-02).

    source 로 이 결과가 어디서 왔는지 남긴다.
      agent    — 에이전트가 정상 분해
      partial  — 도구 호출 상한에 걸려 중간 결과로 마감
      template — 실패해서 표준 커리큘럼 템플릿으로 대체
    """

    units: list[StudyUnit]
    source: Literal["agent", "partial", "template"]
    message: str = ""
    tool_calls: int = 0
