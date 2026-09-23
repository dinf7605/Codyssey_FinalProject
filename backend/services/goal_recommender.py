"""목표 추천 카드 (FR-GOAL-05) — 담당 B.

decomposer.py 와 같은 원칙을 따른다 — ANTHROPIC_API_KEY 가 있으면 Claude Haiku 로
2문장 이내 추천 이유를 만들고, 없거나 실패하면 규칙 기반 문구로 대체한다.
문구 생성이 실패해도 추천 카드 자체는 항상 나온다 (AI기능명세: 이유 생성 20초
타임아웃 시 이유 없이 카드만 표시와 같은 정신).
"""

from __future__ import annotations

import os

from schemas.goal import RECOMMEND_MAX, SIMILARITY_THRESHOLD, FeasibleCandidate
from services.goal_catalog import popular_goals, search_catalog
from services.goal_feasibility import evaluate_all

REASON_TIMEOUT_SECONDS = 20  # AI기능명세와 동일한 타임아웃
REASON_MAX_TOKENS = 120
REASON_MODEL_ENV = "ANTHROPIC_HAIKU_MODEL"
DEFAULT_HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _template_reason(candidate: FeasibleCandidate, tags: list[str]) -> str:
    overlap = sorted(set(t.lower() for t in tags) & set(candidate.tags))
    if overlap:
        tag_part = f"관심 태그 '{overlap[0]}'와 가장 유사해요."
    else:
        tag_part = "지금 인기 있는 목표예요."
    if candidate.min_weeks >= 0 and candidate.min_weeks <= candidate.recommended_weeks:
        time_part = "지금 가용시간이면 기한 안에 준비할 수 있어요."
    else:
        time_part = "가용시간을 조금 늘리면 여유 있게 준비할 수 있어요."
    return f"{tag_part} {time_part}"


def _ai_reason(candidate: FeasibleCandidate, tags: list[str], client, model: str) -> str | None:
    prompt = (
        f"사용자 관심 태그: {', '.join(tags) or '없음'}\n"
        f"추천 목표: {candidate.title} ({candidate.field})\n"
        f"예상 기간: 최소 {candidate.min_weeks}주 · 권장 {candidate.recommended_weeks}주 · "
        f"주당 {candidate.weekly_hours}시간\n"
        "위 정보로 이 목표를 추천하는 이유를 2문장 이내, 한국어 존댓말로 짧게 써 주세요. "
        "설명 문장 없이 추천 이유 본문만 출력하세요."
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=REASON_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
        ).strip()
        return text or None
    except Exception:  # noqa: BLE001 - 이유 생성 실패는 추천 자체를 막지 않는다
        return None


def _make_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=REASON_TIMEOUT_SECONDS)
        model = os.getenv(REASON_MODEL_ENV, DEFAULT_HAIKU_MODEL)
        return client, model
    except Exception:  # noqa: BLE001
        return None, None


def recommend_goals(tags: list[str], weekly_hours: float):
    """FR-GOAL-05 — 관심 태그 + 가용시간으로 추천 카드 3~5개를 만든다.

    반환값: (추천 목록, 실제 검색에 쓴 값 "tags"/"fallback_popular", 전부 기한초과 여부,
             기한을 못 맞춰 빠진 후보 목록)
    """
    candidates = search_catalog(tags, k=20)
    candidates = [c for c in candidates if c.similarity >= SIMILARITY_THRESHOLD]

    query_used = "tags"
    if not candidates:
        # FR-GOAL-03 세부사항: 최고 유사도가 낮으면 인기 목록으로 대체한다
        query_used = "fallback_popular"
        candidates = popular_goals(k=RECOMMEND_MAX)

    evaluated = evaluate_all(candidates, weekly_hours)
    feasible = [c for c in evaluated if c.feasible]
    excluded = [c for c in evaluated if not c.feasible]
    all_exceeded = bool(evaluated) and not feasible

    if all_exceeded:
        return [], query_used, True, excluded

    feasible.sort(key=lambda c: (c.similarity, c.popularity), reverse=True)
    top = feasible[:RECOMMEND_MAX]

    client, model = _make_client()
    for candidate in top:
        reason = None
        if client is not None:
            reason = _ai_reason(candidate, tags, client, model)
        if reason:
            candidate.reason = reason
            candidate.ai_generated = True
        else:
            candidate.reason = _template_reason(candidate, tags)
            candidate.ai_generated = False

    return top, query_used, False, excluded
