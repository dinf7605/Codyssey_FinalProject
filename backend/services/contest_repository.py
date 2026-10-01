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
        def fetch(scope: str) -> tuple[list[Contest], int]:
            request = self.client.table("contests").select(CONTEST_COLUMNS, count="exact")
            if scope == "dated":
                request = request.in_("status", ["upcoming", "open"])
                request = request.gte("deadline", date.today().isoformat())
            elif scope == "links":
                request = request.eq("source", "wevity").eq("status", "unknown")
                request = request.is_("deadline", "null")

            if filters.deadline_before:
                request = request.lte("deadline", filters.deadline_before.isoformat())
            if filters.field:
                request = request.contains("fields", [filters.field])
            if filters.eligibility:
                request = request.ilike("eligibility_text", f"%{filters.eligibility}%")
            if filters.query:
                # 한 요청에 OR은 제목/주최/요약 검색 하나만 둔다.
                safe_query = re.sub(r"[(),]", " ", filters.query).strip()
                if safe_query:
                    pattern = f"%{safe_query}%"
                    request = request.or_(
                        f"title.ilike.{pattern},host.ilike.{pattern},summary.ilike.{pattern}"
                    )
            request = request.order("collected_at", desc=True) if filters.sort == "latest" else request.order("deadline")
            response = request.limit(filters.limit).execute()
            items = [Contest.model_validate(row) for row in response.data]
            return items, response.count if response.count is not None else len(items)

        if filters.include_closed:
            return fetch("all")
        dated, dated_total = fetch("dated")
        # 날짜/분야/자격 조건을 건 검색에는 세부 정보가 없는 링크 전용 행을 넣지 않는다.
        if filters.deadline_before or filters.field or filters.eligibility:
            return dated, dated_total
        links, links_total = fetch("links")
        items = dated + links
        if filters.sort == "latest":
            items.sort(key=lambda contest: contest.collected_at.isoformat() if contest.collected_at else "", reverse=True)
        else:
            items.sort(key=lambda contest: (contest.deadline is None, contest.deadline or date.max))
        return items[:filters.limit], dated_total + links_total

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
            .select("field,category_group,standard_hours")
            .eq("active", True)
            .execute()
        )
        if not standards.data:
            return None

        # 직접 등록되지 않은 분야는 이름 일부가 겹치는 분야의 분류군을 먼저 쓴다.
        # 분류군도 알 수 없는 경우에만 전체 중앙값으로 폴백한다.
        def parts(value: str) -> set[str]:
            return {part.casefold() for part in re.split(r"[/·,\s]+", value) if len(part) >= 2}

        requested = set().union(*(parts(field) for field in fields)) if fields else set()
        group_scores: dict[str, int] = {}
        for row in standards.data:
            group = row.get("category_group")
            if group:
                group_scores[group] = max(
                    group_scores.get(group, 0), len(requested & parts(row.get("field") or ""))
                )
        if group_scores and max(group_scores.values()) > 0:
            group = max(group_scores, key=group_scores.get)
            values = [float(row["standard_hours"]) for row in standards.data
                      if row.get("category_group") == group]
            return PreparationHours(float(median(values)), "group_median")

        values = [float(row["standard_hours"]) for row in standards.data]
        return PreparationHours(float(median(values)), "global_median")


def get_contest_repository() -> ContestRepository:
    return SupabaseContestRepository(get_supabase_client())
