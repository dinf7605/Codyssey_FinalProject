"""목표 탐색 API (FR-GOAL-01~13) — 담당 B, 파이프라인 0.

  GET  /goal/tags               관심분야 칩 목록 (FR-GOAL-01)
  GET  /goal/popular             인기 목표 목록 — 한도에 걸려도 항상 열려 있다 (FR-GOAL-12)
  POST /goal/suggest             유사 분야 추천 (FR-GOAL-11) · AI 호출 한도 적용
  POST /goal/match               목표 후보 매칭 (FR-GOAL-03) · AI 호출 한도 적용
  POST /goal/recommend           목표 추천 카드 (FR-GOAL-05) · AI 호출 한도 적용
                                  · 최근 "관심없음"은 제외 (FR-GOAL-08, 30일 뒤 자동 재포함)
  POST /goal/feasibility         기간 적합성 판정 (FR-GOAL-04 · FR-GOAL-09) · LLM 미사용
  POST /goal/feedback            추천 피드백 (FR-GOAL-08)
  DELETE /goal/feedback/{goal_id} 추천 피드백 취소 (FR-GOAL-08)
  POST /goal/manual/check        기한 실현가능성 경고 (FR-GOAL-10)
  POST /goal/confirm             목표 확정 (FR-GOAL-07)

목표 확정 이후의 일정 생성(파이프라인 1)은 담당 C 의 POST /plan/decompose 가 잇는다 —
이 라우터는 그 호출을 대신 하지 않고, 프론트가 확정 응답을 받은 뒤 이어서 부른다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from schemas.goal import (
    MAX_ACTIVE_GOALS,
    SIMILARITY_THRESHOLD,
    ConfirmRequest,
    ConfirmResponse,
    FeasibilityRequest,
    FeasibilityResponse,
    FeedbackRequest,
    FeedbackResponse,
    InterestRequest,
    ManualGoalRequest,
    ManualGoalWarning,
    MatchRequest,
    MatchResponse,
    RecommendRequest,
    RecommendResponse,
    SuggestResponse,
)
from services import llm
from services.goal_catalog import (
    all_tags,
    popular_goals,
    search_catalog,
    search_catalog_ai,
    suggest_tags_from_history,
)
from services.plan_store import log_ai_call
from services.goal_feasibility import evaluate_all, evaluate_candidates, manual_goal_warning
from services.goal_feedback import recently_dismissed_goal_ids
from services.goal_limiter import RateLimitExceeded, consume, usage_for
from services.goal_recommender import recommend_goals
from utils.auth import get_optional_user

router = APIRouter(prefix="/goal", tags=["goal"])


@router.get("/ping")
def goal_ping():
    return {"message": "goal 라우터 살아있음"}


@router.get("/tags")
def get_tags():
    """FR-GOAL-01 — 관심분야 칩 목록. 카탈로그와 같은 태그를 쓴다."""
    return {"tags": all_tags()}


@router.get("/popular")
def get_popular(k: int = 3):
    """인기 목표 목록. 콜드스타트(FR-GOAL-11)와 한도 초과(FR-GOAL-12) 양쪽에서 쓴다.

    AI 를 부르지 않으므로 한도 검사를 거치지 않는다 — 한도에 걸려도 계속 쓸 수 있다.
    """
    return {"goals": popular_goals(k=k)}


@router.post("/suggest", response_model=SuggestResponse)
def suggest(req: InterestRequest) -> SuggestResponse:
    """FR-GOAL-11 — 관심분야를 안 적어도 유사 분야를 추천한다.

    이력이 전혀 없으면 추천을 만들지 않고 인기 목록으로 대체한다.
    """
    try:
        usage = consume(req.session_id, req.is_member)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=exc.message) from exc

    tags = suggest_tags_from_history(req.recent_goal_tags, req.recent_viewed_fields)
    if tags:
        return SuggestResponse(tags=tags, basis="history", popular=[], usage=usage)

    return SuggestResponse(
        tags=[], basis="cold_start", popular=popular_goals(k=3), usage=usage
    )


@router.post("/match", response_model=MatchResponse)
def match(req: MatchRequest) -> MatchResponse:
    """FR-GOAL-03 — 관심 태그로 목표 후보를 검색한다. 유사도가 낮으면 인기 목록으로 대체."""
    try:
        usage = consume(req.session_id, req.is_member)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=exc.message) from exc

    candidates, method = search_catalog_ai(req.tags, k=req.k, on_call=_log_search)
    strong = [c for c in candidates if c.similarity >= SIMILARITY_THRESHOLD]
    if strong:
        return MatchResponse(candidates=strong, query_used="tags", search_method=method, usage=usage)
    return MatchResponse(
        candidates=popular_goals(k=5), query_used="fallback_popular", search_method=method, usage=usage
    )


def _log_search(source: str, latency_ms: int, message: str) -> None:
    """카탈로그 검색의 Claude 호출을 ai_call_logs 에 남긴다 (FR-ADMIN-02).

    목표 탐색은 비회원도 쓰므로 user_id 없이 남긴다. DB 가 없거나 실패해도 추천은 계속된다.
    """
    try:
        db = get_supabase_client()
    except Exception:  # noqa: BLE001 - DB 설정 전(로컬 개발)에도 추천은 된다
        return
    log_ai_call(
        db, user_id=None, feature="goal.match", model=llm.model("fast"),
        source=source, tool_calls=0, latency_ms=latency_ms, message=message,
    )


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, user=Depends(get_optional_user)) -> RecommendResponse:
    """FR-GOAL-05 — 목표 추천 카드. 태그 매칭 + 기간 계산 + 추천 이유를 한 번에 묶는다.

    FR-GOAL-08 — 최근(FEEDBACK_DISMISS_COOLDOWN_DAYS일 이내) "관심없음"으로 남긴
    목표는 이 추천에서 뺀다. 별도로 지우지 않아도 그 기간이 지나면 조회 조건에서
    자연히 빠져 다시 추천 대상에 포함된다.
    """
    try:
        usage = consume(req.session_id, req.is_member)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=exc.message) from exc

    dismissed = recently_dismissed_goal_ids(req.session_id, user.id if user else None)
    top, query_used, all_exceeded, excluded, method = recommend_goals(
        req.tags, req.weekly_hours, exclude_ids=dismissed, on_call=_log_search
    )
    return RecommendResponse(
        candidates=top,
        query_used=query_used,
        all_exceeded=all_exceeded,
        excluded=excluded,
        search_method=method,
        usage=usage,
    )


@router.post("/feasibility", response_model=FeasibilityResponse)
def check_feasibility(req: FeasibilityRequest) -> FeasibilityResponse:
    """FR-GOAL-04 · FR-GOAL-09 — 기간 계산 모듈. LLM 을 쓰지 않아 한도 검사도 없다."""
    feasible, all_exceeded = evaluate_candidates(req.candidates, req.weekly_hours)
    # 탈락한 후보의 표준시간·최소기간·마감일을 화면에 보여주기 위해 별도로 전체 판정도 구한다.
    excluded = [c for c in evaluate_all(req.candidates, req.weekly_hours) if not c.feasible]
    return FeasibilityResponse(candidates=feasible, all_exceeded=all_exceeded, excluded=excluded)


@router.post("/manual/check", response_model=ManualGoalWarning)
def check_manual_goal(req: ManualGoalRequest) -> ManualGoalWarning:
    """FR-GOAL-10 — 직접 입력한 목표의 기한이 무리인지 확인한다.

    제목으로 카탈로그를 찾아보고, 걸리는 게 없으면 계산 없이 '계산 불가'를 알린다.
    """
    matched_list = search_catalog([req.title], k=1)
    matched = matched_list[0] if matched_list else None
    return manual_goal_warning(req.due_date, req.weekly_hours, matched)


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(req: FeedbackRequest, user=Depends(get_optional_user)) -> FeedbackResponse:
    """FR-GOAL-08 — 추천 피드백. goal_feedback 테이블에 저장한다 (마이그레이션 007).

    비회원도 쓰는 화면이라 로그인을 요구하지 않는다 — 로그인돼 있으면 user_id 도 같이
    남기고, 아니면 session_id 만 남긴다. DB가 아직 설정되지 않았거나 쓰기가 실패해도
    온보딩 흐름 자체는 막지 않는다 — 프론트는 이 응답을 저장 실패로 취급하지 않는다.
    """
    try:
        get_supabase_client().table("goal_feedback").insert(
            {
                "session_id": req.session_id,
                "user_id": user.id if user else None,
                "goal_id": req.goal_id,
                "interested": req.interested,
                "reason": req.reason,
            }
        ).execute()
    except Exception:  # noqa: BLE001 - DB 미설정·일시 장애여도 추천 흐름을 막지 않는다
        pass
    return FeedbackResponse(ok=True, message="피드백을 받았습니다. 다음 추천에 반영할게요.")


@router.delete("/feedback/{goal_id}", response_model=FeedbackResponse)
def delete_feedback(
    goal_id: str, session_id: str | None = None, user=Depends(get_optional_user)
) -> FeedbackResponse:
    """FR-GOAL-08 — 남긴 "관심없음" 피드백을 취소(삭제)한다.

    마이페이지 같은 별도 관리 화면이 없어도, 방금 "관심없음"을 누른 자리에서 바로
    "취소"할 수 있게 하기 위한 용도다. 회원이면 user_id로, 비회원이면 session_id로만
    자기 기록을 지운다 — 다른 사람 세션의 기록은 지울 수 없다. DB가 없거나 실패해도
    (POST /goal/feedback과 동일하게) 화면 흐름은 막지 않는다.
    """
    try:
        query = get_supabase_client().table("goal_feedback").delete().eq("goal_id", goal_id)
        if user:
            query = query.eq("user_id", user.id)
        elif session_id:
            query = query.eq("session_id", session_id)
        else:
            raise HTTPException(status_code=400, detail="session_id가 필요합니다.")
        query.execute()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - DB 미설정·일시 장애여도 흐름을 막지 않는다
        pass
    return FeedbackResponse(ok=True, message="피드백을 취소했어요.")


@router.post("/confirm", response_model=ConfirmResponse)
def confirm(req: ConfirmRequest) -> ConfirmResponse:
    """FR-GOAL-07 — 목표 확정. 동시 진행 목표는 최대 2개."""
    if req.active_goal_count >= MAX_ACTIVE_GOALS:
        return ConfirmResponse(
            ok=False,
            message=f"이미 목표 {MAX_ACTIVE_GOALS}개가 진행 중이에요. 하나를 먼저 종료해 주세요.",
            requires_closing_goal=True,
        )

    if not req.is_member:
        return ConfirmResponse(
            ok=True,
            message="가입하면 지금까지 고른 내용이 그대로 저장돼요.",
            requires_signup=True,
        )

    return ConfirmResponse(ok=True, message=f"'{req.goal_title}' 목표를 확정했어요.")


@router.get("/usage")
def get_usage(session_id: str, is_member: bool = False):
    """비회원 한도 사용 현황만 조회한다 (호출을 소비하지 않는다)."""
    return usage_for(session_id, is_member)
