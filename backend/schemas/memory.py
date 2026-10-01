"""사용자가 조회·삭제할 수 있는 장기 메모리와 관심 태그 입력."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MemoryType = Literal[
    "preferred_study_time", "effort_deviation", "interest_tags",
    "rejected_recommendations", "four_week_completion_rate",
]


class Memory(BaseModel):
    id: str
    memory_type: MemoryType
    memory_key: str
    value: Any
    basis: str
    updated_at: datetime
    expires_at: datetime


class InterestTagsInput(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=10)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in tags:
            tag = value.strip()
            if not tag or len(tag) > 40:
                raise ValueError("관심 태그는 각각 1~40자로 입력해 주세요")
            if tag.casefold() not in seen:
                result.append(tag)
                seen.add(tag.casefold())
        return result
