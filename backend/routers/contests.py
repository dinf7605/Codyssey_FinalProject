"""공모전 공개 검색과 준비 기간 계산 API."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from schemas.contest import (
    Contest,
    ContestListResponse,
    ContestSort,
    PreparationEstimateRequest,
    PreparationEstimateResponse,
)
from services.contest_repository import (
    ContestRepository,
    ContestSearch,
    get_contest_repository,
)
from services.contest_service import estimate_preparation


router = APIRouter(prefix="/contests", tags=["contests"])


def _repository_or_503() -> ContestRepository:
    try:
        return get_contest_repository()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


RepositoryDependency = Annotated[ContestRepository, Depends(_repository_or_503)]


@router.get("", response_model=ContestListResponse, description="FR-CONT-03 공모전 검색·필터")
def search_contests(
    repository: RepositoryDependency,
    query: str | None = Query(default=None, max_length=100),
    field: str | None = Query(default=None, max_length=50),
    eligibility: str | None = Query(default=None, max_length=100),
    deadline_before: date | None = None,
    sort: ContestSort = "deadline",
    include_closed: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
) -> ContestListResponse:
    items, total = repository.search(
        ContestSearch(
            query=query,
            field=field,
            eligibility=eligibility,
            deadline_before=deadline_before,
            sort=sort,
            include_closed=include_closed,
            limit=limit,
        )
    )
    return ContestListResponse(items=items, total=total)


@router.get("/{contest_id}", response_model=Contest)
def get_contest(contest_id: str, repository: RepositoryDependency) -> Contest:
    contest = repository.get(contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="공모전을 찾을 수 없습니다")
    return contest


@router.post(
    "/{contest_id}/estimate",
    response_model=PreparationEstimateResponse,
    description="FR-CONT-10 공모전 준비 기간 산정",
)
def estimate_contest_preparation(
    contest_id: str,
    request: PreparationEstimateRequest,
    repository: RepositoryDependency,
) -> PreparationEstimateResponse:
    contest = repository.get(contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="공모전을 찾을 수 없습니다")

    standard = repository.get_preparation_hours(contest.fields)
    if standard is None:
        raise HTTPException(
            status_code=503,
            detail="준비시간 기준 데이터가 아직 등록되지 않았습니다",
        )

    return estimate_preparation(contest, request.weekly_hours, standard)
