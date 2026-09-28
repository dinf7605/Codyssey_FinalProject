"""공모전 공개 검색과 준비 기간 계산 API.

  POST /contests/collect  위비티 공고 수집 (매일 05:00 스케줄러, X-Batch-Key) — services/wevity_collector.py
"""

from __future__ import annotations

import hmac
import os
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from db import get_supabase_client
from services import wevity_collector

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


@router.post("/collect", status_code=202, description="FR-CONT-01 위비티 공고 수집 (매일 05:00, X-Batch-Key)")
def collect_contests(background: BackgroundTasks, x_batch_key: str | None = Header(default=None)) -> dict:
    """사람이 부르는 API 가 아니라 스케줄러가 부른다 — 로그인 대신 X-Batch-Key(.env 의 BATCH_SECRET)를 본다.

    요청 사이 3초씩 쉬느라 몇 분 걸리므로 바로 202 로 답하고 뒤에서 돈다. 결과는 batch_runs 에 남는다.
    """
    expected = os.getenv("BATCH_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="BATCH_SECRET 환경변수가 없어 수집을 실행하지 않습니다.")
    if not (x_batch_key and hmac.compare_digest(x_batch_key, expected)):
        raise HTTPException(status_code=401, detail="배치 키가 맞지 않습니다.")
    db = get_supabase_client()
    now = datetime.now(wevity_collector.KST)
    if wevity_collector.running(db, now):
        raise HTTPException(status_code=409, detail="공고 수집이 이미 실행 중입니다.")
    background.add_task(wevity_collector.run_daily, db, now)
    return {"status": "started", "message": "결과는 batch_runs 에 남습니다."}


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
