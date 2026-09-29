"""공모전 공개 검색과 준비 기간 계산 API.

  POST /contests/collect  위비티 공고 수집 (매일 05:00 스케줄러, X-Batch-Key) — services/wevity_collector.py
"""

from __future__ import annotations

import hmac
import os
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from db import get_db, get_supabase_client
from services import wevity_collector

from schemas.contest import (
    Contest,
    ContestListResponse,
    ContestRecommendationResponse,
    ContestFeedbackInput,
    ContestFeedbackResponse,
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
from services.contest_recommender import rank_contests, recommendation_week, rejection_weight
from services import contest_vector
from utils.auth import get_current_user, get_optional_user


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
    if not wevity_collector.crawling_enabled():
        raise HTTPException(status_code=503, detail="위비티 수집이 비활성화되어 있습니다.")
    db = get_supabase_client()
    now = datetime.now(wevity_collector.KST)
    if wevity_collector.running(db, now):
        raise HTTPException(status_code=409, detail="공고 수집이 이미 실행 중입니다.")
    background.add_task(wevity_collector.run_daily, db, now)
    return {"status": "started", "message": "결과는 batch_runs 에 남습니다."}


@router.get("/recommendations", response_model=ContestRecommendationResponse)
def recommend_contests(
    repository: RepositoryDependency,
    tags: str | None = Query(default=None, max_length=200),
    user=Depends(get_optional_user),
    db=Depends(get_db),
) -> ContestRecommendationResponse:
    """현재 저장된 공고 최대 20건을 제목 키워드로 재랭킹한다. 사용자 거절은 제외한다."""
    user_id = str(user.id) if user else None
    if tags is None and user_id:
        rows = db.table("user_memories").select("value").eq("user_id", user_id).eq(
            "memory_type", "interest_tags"
        ).eq("memory_key", "default").limit(1).execute().data
        interests = rows[0]["value"].get("tags", []) if rows else []
    else:
        interests = [value.strip() for value in (tags or "").split(",") if value.strip()]
    interests = list(dict.fromkeys(interests))[:10]
    if not interests:
        return ContestRecommendationResponse(items=[], message="관심 키워드를 입력하면 공고를 추천할 수 있습니다.")

    rejected: set[str] = set()
    if user_id:
        memories = db.table("user_memories").select("memory_key,value").eq("user_id", user_id).eq(
            "memory_type", "rejected_recommendations"
        ).execute().data
        rejected = {row["memory_key"] for row in memories
                    if isinstance(row.get("value"), dict) and row["value"].get("rated_at")
                    and rejection_weight(row["value"]["rated_at"]) >= 0.5}
    today = datetime.now(wevity_collector.KST).date()
    ranked = []
    method = "title_keywords"
    if contest_vector.enabled():
        try:
            matches = contest_vector.vector_candidates(db, interests)
            scores = {row["contest_id"]: float(row["similarity"]) for row in matches}
            candidates = [contest for contest_id in scores
                          if (contest := repository.get(contest_id)) is not None]
            ranked = rank_contests(candidates, interests, rejected, today, scores)
            if ranked:
                method = "title_vectors"
        except Exception:  # noqa: BLE001 - 벡터 서비스 장애 시 제목 일치 검색으로 복구
            pass
    if not ranked:
        candidates, _ = repository.search(ContestSearch(limit=20))
        ranked = rank_contests(candidates, interests, rejected, today)
    if user_id and ranked:
        week = recommendation_week(today)
        db.table("contest_recommendations").upsert([{
            "user_id": user_id, "contest_id": row["contest"].id,
            "recommendation_week": week, "similarity": row["similarity"],
            "deadline_score": row["deadline_score"],
            "eligibility_score": row["eligibility_score"],
            "rerank_score": row["rerank_score"], "reason": row["reason"],
            "matching_tags": row["matching_tags"],
        } for row in ranked], on_conflict="user_id,recommendation_week,contest_id").execute()
    return ContestRecommendationResponse(
        items=ranked,
        method=method,
        message=None if ranked else "관심 키워드와 일치하는 공고를 찾지 못했습니다.",
    )


@router.post("/{contest_id}/feedback", response_model=ContestFeedbackResponse)
def save_contest_feedback(
    contest_id: str,
    payload: ContestFeedbackInput,
    repository: RepositoryDependency,
    user=Depends(get_current_user),
    db=Depends(get_db),
) -> ContestFeedbackResponse:
    if repository.get(contest_id) is None:
        raise HTTPException(status_code=404, detail="공모전을 찾을 수 없습니다")
    user_id = str(user.id)
    snapshots = db.table("contest_recommendations").select(
        "similarity,rerank_score"
    ).eq("user_id", user_id).eq("contest_id", contest_id).order(
        "recommendation_week", desc=True
    ).limit(1).execute().data
    snapshot = snapshots[0] if snapshots else {}
    row = {
        "user_id": user_id, "contest_id": contest_id,
        "rating": payload.rating, "reason": payload.reason,
        "similarity": snapshot.get("similarity"),
        "rerank_score": snapshot.get("rerank_score"),
    }
    db.table("contest_feedback").upsert(row, on_conflict="user_id,contest_id").execute()
    if payload.rating == "not_relevant":
        now = datetime.now(timezone.utc)
        db.table("user_memories").upsert({
            "user_id": user_id, "memory_type": "rejected_recommendations",
            "memory_key": contest_id, "value": {"rated_at": now.isoformat()},
            "basis": "사용자가 추천에 '안 맞음'으로 평가",
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=365)).isoformat(),
        }, on_conflict="user_id,memory_type,memory_key").execute()
    else:
        db.table("user_memories").delete().eq("user_id", user_id).eq(
            "memory_type", "rejected_recommendations"
        ).eq("memory_key", contest_id).execute()
    return ContestFeedbackResponse(**row)


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

    if contest.deadline is None:
        raise HTTPException(status_code=422, detail="마감일 정보가 없어 준비 기간을 계산할 수 없습니다. 원문을 확인해 주세요.")

    standard = repository.get_preparation_hours(contest.fields)
    if standard is None:
        raise HTTPException(
            status_code=503,
            detail="준비시간 기준 데이터가 아직 등록되지 않았습니다",
        )

    return estimate_preparation(contest, request.weekly_hours, standard)
