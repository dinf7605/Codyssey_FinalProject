"""공모전 데이터 접근 계층.

라우터가 Supabase 쿼리 문법을 직접 알지 않게 분리한다. 테스트에서는 같은
인터페이스의 메모리 저장소를 주입할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from statistics import median
from typing import Protocol

from db import get_supabase_client
from schemas.contest import Contest, ContestSort, PreparationHoursSource


CONTEST_COLUMNS = (
    "id,source,source_id,title,host,fields,eligibility_text,start_date,"
    "deadline,status,source_url,official_url,summary,collected_at"
)


@dataclass(frozen=True)
class ContestSearch:
    query: str | None = None
    field: str | None = None
    eligibility: str | None = None
    deadline_before: date | None = None
    sort: ContestSort = "deadline"
    include_closed: bool = False
    limit: int = 20


@dataclass(frozen=True)
class PreparationHours:
    hours: float
    source: PreparationHoursSource


class ContestRepository(Protocol):
    def search(self, filters: ContestSearch) -> tuple[list[Contest], int]: ...

    def get(self, contest_id: str) -> Contest | None: ...

    def get_preparation_hours(self, fields: list[str]) -> PreparationHours | None: ...


class SupabaseContestRepository:
    def __init__(self, client):
        self.client = client

    def search(self, filters: ContestSearch) -> tuple[list[Contest], int]:
        request = self.client.table("contests").select(CONTEST_COLUMNS, count="exact")

        if not filters.include_closed:
            request = request.in_("status", ["upcoming", "open"])
            request = request.gte("deadline", date.today().isoformat())

        if filters.deadline_before:
            request = request.lte("deadline", filters.deadline_before.isoformat())

        if filters.field:
            request = request.contains("fields", [filters.field])

        if filters.eligibility:
            request = request.ilike("eligibility_text", f"%{filters.eligibility}%")

        if filters.query:
            # PostgREST or_ 식을 깨는 구분자를 제거한다. 더 복잡한 검색은 추후
            # PostgreSQL 전문검색 RPC로 교체한다.
            safe_query = re.sub(r"[(),]", " ", filters.query).strip()
            if safe_query:
                pattern = f"%{safe_query}%"
                request = request.or_(
                    f"title.ilike.{pattern},host.ilike.{pattern},summary.ilike.{pattern}"
                )

        if filters.sort == "latest":
            request = request.order("collected_at", desc=True)
        else:
            request = request.order("deadline")

        response = request.limit(filters.limit).execute()
        items = [Contest.model_validate(row) for row in response.data]
        return items, response.count if response.count is not None else len(items)

    def get(self, contest_id: str) -> Contest | None:
        response = (
            self.client.table("contests")
            .select(CONTEST_COLUMNS)
            .eq("id", contest_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return Contest.model_validate(response.data[0])

    def get_preparation_hours(self, fields: list[str]) -> PreparationHours | None:
        if fields:
            exact = (
                self.client.table("preparation_time_standards")
                .select("field,category_group,standard_hours")
                .in_("field", fields)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            if exact.data:
                row = exact.data[0]
                return PreparationHours(float(row["standard_hours"]), "exact")

        # 분야명이 직접 일치하지 않으면 같은 분류군의 중앙값을 우선 사용한다.
        # 아직 분류군을 알 수 없는 신규 분야는 전체 중앙값으로 폴백한다.
        standards = (
            self.client.table("preparation_time_standards")
            .select("category_group,standard_hours")
            .eq("active", True)
            .execute()
        )
        if not standards.data:
            return None

        values = [float(row["standard_hours"]) for row in standards.data]
        return PreparationHours(float(median(values)), "global_median")


def get_contest_repository() -> ContestRepository:
    return SupabaseContestRepository(get_supabase_client())
