"""공모전 공개 검색과 준비 기간 계산 API.

  POST /contests/collect  위비티 공고 수집 (매일 05:00 스케줄러, X-Batch-Key) — services/wevity_collector.py
"""

from __future__ import annotations

import hmac
import os
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
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
    SupabaseContestRepository,
    get_contest_repository,
)
from services.contest_service import estimate_preparation
from services.contest_recommender import rank_contests, recommendation_week, rejection_weight
from services import contest_claude, llm
from services.plan_store import log_ai_call
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
    """현재 저장된 공고 최대 20건을 Claude 또는 제목 키워드로 재랭킹한다."""
    user_id = str(user.id) if user else None
    plans = db.table("study_plans").select("goal_title,deadline").eq(
        "user_id", user_id
    ).eq("status", "active").execute().data if user_id else []
    if tags is None and user_id:
        rows = db.table("user_memories").select("value").eq("user_id", user_id).eq(
            "memory_type", "interest_tags"
        ).eq("memory_key", "default").limit(1).execute().data
        interests = rows[0]["value"].get("tags", []) if rows else []
        if not interests:
            interests = [word for plan in plans
                         for word in re.findall(r"[\w가-힣]{2,}", plan.get("goal_title", ""))
                         if word not in {"공부", "준비", "목표"}]
    else:
        interests = [value.strip() for value in (tags or "").split(",") if value.strip()]
    interests = list(dict.fromkeys(interests))[:10]
    if not interests:
        return ContestRecommendationResponse(items=[], message="관심 키워드를 입력하면 공고를 추천할 수 있습니다.")

    rejected: set[str] = set()
    previous_ids: set[str] = set()
    goal_deadline = None
    if user_id:
        memories = db.table("user_memories").select("memory_key,value").eq("user_id", user_id).eq(
            "memory_type", "rejected_recommendations"
        ).execute().data
        rejected = {row["memory_key"] for row in memories
                    if isinstance(row.get("value"), dict) and row["value"].get("rated_at")
                    and rejection_weight(row["value"]["rated_at"]) >= 0.5}
    today = datetime.now(wevity_collector.KST).date()
    if user_id:
        last_week = recommendation_week(today - timedelta(days=7))
        previous = db.table("contest_recommendations").select("contest_id").eq(
            "user_id", user_id
        ).eq("recommendation_week", last_week).execute().data
        previous_ids = {str(row["contest_id"]) for row in previous}
        dates = [date.fromisoformat(row["deadline"]) for row in plans if row.get("deadline")]
        goal_deadline = max(dates) if dates else None
    candidates = recommendation_candidates(repository, interests)
    def log_call(source: str, latency_ms: int, message: str) -> None:
        # 관리자 AI 통계(FR-ADMIN-02)에 공고 추천 호출도 보이게 한다. 게스트는 user_id 없이 남긴다.
        log_ai_call(
            db, user_id=user_id, feature="contest.recommend", model=llm.model("fast"),
            source=source, tool_calls=0, latency_ms=latency_ms, message=message,
        )

    scores = contest_claude.score_titles(candidates, interests, on_call=log_call)
    method = "title_claude" if scores is not None else "title_keywords"
    ranked = rank_contests(
        candidates, interests, rejected, today,
        similarities=scores, previous_ids=previous_ids, goal_deadline=goal_deadline,
    )
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


CANDIDATE_LIMIT = 20  # contest_claude.MAX_CANDIDATES 와 같다 — 그 이상은 Claude 가 보지 않는다
KEYWORD_CANDIDATES = 12  # 키워드가 들어간 공고를 먼저 이만큼, 나머지는 최신 공고로 채운다


def recommendation_candidates(repository, interests: list[str]) -> list:
    """추천 후보 — 관심 키워드가 제목·주최·요약에 든 공고를 먼저, 남는 자리는 최신 공고.

    예전엔 최신 20건만 봐서, 공고가 147건으로 늘자 '데이터'로 검색하면 나오는 데이터 분석 공모전 2건을
    추천이 놓치고 무관한 1건만 냈다 (10-05 사전 점검 2번).
    """
    picked: dict[str, object] = {}
    for word in interests[:5]:
        matches, _ = repository.search(ContestSearch(query=word, sort="deadline", limit=KEYWORD_CANDIDATES))
        for contest in matches:
            if len(picked) >= KEYWORD_CANDIDATES:
                break
            picked.setdefault(contest.id, contest)
    latest, _ = repository.search(ContestSearch(sort="latest", limit=CANDIDATE_LIMIT))
    for contest in latest:
        if len(picked) >= CANDIDATE_LIMIT:
            break
        picked.setdefault(contest.id, contest)
    return list(picked.values())


def run_weekly_recommendations(db, at: datetime) -> None:
    """월요일 09:00 외부 스케줄러가 호출한다. 사용자별 실패는 다른 사용자를 막지 않는다."""
    run = db.table("batch_runs").insert({
        "job_name": "contest.recommend", "status": "running", "started_at": at.isoformat(),
    }).execute().data[0]
    completed = failed = 0
    repository = SupabaseContestRepository(db)
    try:
        offset = 0
        while True:
            # 공용 DB 의 users 는 user_id 로 가리킨다 (004 에서 auth_id -> user_id)
            users = db.table("users").select("user_id").range(offset, offset + 99).execute().data
            for row in users:
                try:
                    recommend_contests(repository, tags=None, user=SimpleNamespace(id=row["user_id"]), db=db)
                    completed += 1
                except Exception:  # noqa: BLE001 - 한 계정의 추천 장애는 나머지 계정과 분리
                    failed += 1
            if len(users) < 100:
                break
            offset += 100
    except Exception:  # noqa: BLE001 - 배치 실패는 batch_runs에 남긴다
        failed += 1
    db.table("batch_runs").update({
        "status": "failed" if failed and not completed else "partial" if failed else "success",
        "collected_count": completed, "failed_count": failed,
        "finished_at": datetime.now(wevity_collector.KST).isoformat(),
    }).eq("id", run["id"]).execute()


@router.post("/recommend-weekly", status_code=202, description="FR-CONT-04 월요일 09:00 주간 추천 배치")
def start_weekly_recommendations(background: BackgroundTasks, x_batch_key: str | None = Header(default=None)) -> dict:
    expected = os.getenv("BATCH_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="BATCH_SECRET 환경변수가 없어 추천 배치를 실행하지 않습니다.")
    if not (x_batch_key and hmac.compare_digest(x_batch_key, expected)):
        raise HTTPException(status_code=401, detail="배치 키가 맞지 않습니다.")
    db = get_supabase_client()
    background.add_task(run_weekly_recommendations, db, datetime.now(wevity_collector.KST))
    return {"status": "started"}


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

    # 수집한 마감일·분야를 쓴다. 마감일이 비어 있는 옛 링크 전용 행만 사용자가 원문에서 확인한 값을 받는다
    if contest.deadline is None:
        if request.deadline is None:
            raise HTTPException(status_code=422, detail="마감일 정보가 없어 준비 기간을 계산할 수 없습니다. 원문에서 마감일을 확인해 입력해 주세요.")
        contest = contest.model_copy(update={"deadline": request.deadline})
    fields = contest.fields
    if not fields and request.field and request.field.strip():
        fields = [request.field.strip()]

    standard = repository.get_preparation_hours(fields)
    if standard is None:
        raise HTTPException(
            status_code=503,
            detail="준비시간 기준 데이터가 아직 등록되지 않았습니다",
        )

    return estimate_preparation(contest, request.weekly_hours, standard)
