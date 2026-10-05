"""목표 추천 카드 (FR-GOAL-05) — 담당 B.

decomposer.py 와 같은 원칙을 따른다 — ANTHROPIC_API_KEY 가 있으면 Claude Haiku 로
2문장 이내 추천 이유를 만들고, 없거나 실패하면 규칙 기반 문구로 대체한다.
문구 생성이 실패해도 추천 카드 자체는 항상 나온다 (AI기능명세: 이유 생성 20초
타임아웃 시 이유 없이 카드만 표시와 같은 정신).
"""

from __future__ import annotations

import math
import re
from datetime import date

from schemas.goal import RECOMMEND_MAX, SIMILARITY_THRESHOLD, FeasibleCandidate
from services import llm
from services.goal_catalog import popular_goals, search_catalog_ai
from services.goal_feasibility import _weeks_between, evaluate_all

REASON_TIMEOUT_SECONDS = 20  # AI기능명세와 동일한 타임아웃
# 120 토큰이면 2문장이 중간에 잘리는 경우가 있어 250으로 올림 (담당 B, 2026-09-25)
REASON_MAX_TOKENS = 250

# AI 이유가 계산 결과와 반대로 말하면 버리고 템플릿을 쓴다 (10-02 실사용: 4주 필요·6주 남음인데 "짧아 빠듯")
_TIGHT_WORDS = ("빠듯", "짧", "부족", "촉박", "어렵", "모자")
_ROOMY_WORDS = ("여유", "충분", "넉넉")
_WEEKS = re.compile(r"(\d+)\s*주")


def _is_tight(candidate: FeasibleCandidate) -> bool | None:
    """권장 기간이 시험일까지 남은 기간보다 길면 빠듯하다. 시험일이 없으면 None."""
    left = _weeks_between(date.today(), candidate.deadline)
    if left is None:
        return None
    return candidate.recommended_weeks > left


def reason_consistent(text: str, candidate: FeasibleCandidate) -> bool:
    """AI 추천 이유가 결정론 계산(카드에 보이는 기간·남은 기간)과 맞는가.

    - 여유가 있는데 빠듯하다고 하거나, 빠듯한데 여유 있다고 하면 안 된다
    - 'N주' 라고 쓴 숫자는 카드의 예상 기간이나 시험일까지 남은 주 수여야 한다
    """
    tight = _is_tight(candidate)
    if tight is False and any(w in text for w in _TIGHT_WORDS):
        return False
    if tight is True and any(w in text for w in _ROOMY_WORDS):
        return False
    # 빠듯하면 빠듯하다고 말해야 한다 — "3주 내 준비 완료가 가능합니다"처럼 반대말 없이 낙관만 하면 걸러지지 않았다 (10-02 실사용)
    if tight is True and not any(w in text for w in _TIGHT_WORDS):
        return False
    allowed = set()
    if candidate.recommended_weeks > 0:
        allowed.add(math.ceil(candidate.recommended_weeks))
    left = _weeks_between(date.today(), candidate.deadline)
    if left is not None:
        allowed |= {math.floor(left), math.ceil(left)}
    numbers = {int(n) for n in _WEEKS.findall(text)}
    return not numbers or numbers <= allowed


def _and(word: str) -> str:
    """받침에 맞는 '와/과' — "'마케팅'와"로 나왔다 (10-05 사전 점검 2차). 한글이 아니면 '와(과)'."""
    code = ord(word.strip()[-1]) - 0xAC00 if word.strip() else -1
    if not 0 <= code <= 11171:
        return "와(과)"
    return "과" if code % 28 else "와"


def _due_word(candidate: FeasibleCandidate) -> str:
    """공모전은 '시험일'이 아니라 '마감일'이다."""
    return "마감일" if candidate.kind == "contest" else "시험일"


def _template_reason(candidate: FeasibleCandidate, tags: list[str]) -> str:
    overlap = sorted(set(t.lower() for t in tags) & set(candidate.tags))
    if overlap:
        tag_part = f"관심 태그 '{overlap[0]}'{_and(overlap[0])} 가장 유사해요."
    else:
        tag_part = "지금 인기 있는 목표예요."
    left = _weeks_between(date.today(), candidate.deadline)
    if left is not None and candidate.recommended_weeks > left:
        time_part = f"{_due_word(candidate)}까지 권장 기간보다 짧아 빠듯하게 준비해야 해요."
    elif candidate.min_weeks >= 0 and candidate.min_weeks <= candidate.recommended_weeks:
        time_part = "지금 가용시간이면 기한 안에 준비할 수 있어요."
    else:
        time_part = "가용시간을 조금 늘리면 여유 있게 준비할 수 있어요."
    return f"{tag_part} {time_part}"


def _ai_reason(candidate: FeasibleCandidate, tags: list[str], client, model: str) -> str | None:
    # 카드에 보이는 기간과 같은 값(권장 주 수 올림)만 준다 — 예전엔 "6~8주"처럼 카드와 다른 숫자를 썼다.
    # 관심 단어는 사용자가 적은 문장을 쪼갠 것이라 실력·경력을 뜻하지 않는다 (10-01 실사용:
    # "SQL이 필요할 것 같다"는 입력에 "SQL 기초를 갖추신 분께"라고 씀). 목표 정보에 없는 사실도 지어냈다.
    weeks = math.ceil(candidate.recommended_weeks) if candidate.recommended_weeks > 0 else None
    # 시험일까지 남은 기간 — 권장 기간보다 짧으면 "충분하다"고 쓰면 안 된다 (정보처리기사: 권장 12주, 시험 9주 뒤)
    left = _weeks_between(date.today(), candidate.deadline)
    prompt = (
        f"사용자가 입력한 관심 단어: {', '.join(tags) or '없음'}\n"
        f"추천 목표: {candidate.title} ({candidate.field})\n"
        + (f"예상 준비 기간: 약 {weeks}주 (주당 {candidate.weekly_hours}시간 기준)\n" if weeks else "")
        + (f"다음 {_due_word(candidate)}까지: 약 {math.floor(left)}주\n" if left is not None else "")
        + ({True: f"기간 판정: 빠듯함 ({_due_word(candidate)}까지 남은 기간이 예상 기간보다 짧다)\n",
            False: f"기간 판정: 여유 있음 ({_due_word(candidate)}까지 남은 기간이 예상 기간보다 길다) — 빠듯하다고 쓰지 마세요\n"}
           .get(_is_tight(candidate), ""))
        + "위 정보로 이 목표를 추천하는 이유를 2문장 이내, 80자 이내, 한국어 존댓말로 짧게 써 주세요.\n"
        "지킬 것: 관심 단어는 사용자의 관심일 뿐이니 사용자의 실력·경력·보유 지식을 가정하지 마세요. "
        "시험 과목·공인 여부·난이도처럼 위에 없는 사실은 쓰지 마세요. 기간은 위 숫자만 쓰세요. "
        "설명 문장 없이 추천 이유 본문만 출력하세요."
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=REASON_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return llm.text_of(response) or None
    except Exception:  # noqa: BLE001 - 이유 생성 실패는 추천 자체를 막지 않는다
        return None


def _make_client():
    """Codyssey 게이트웨이 클라이언트와 빠른 모델(claude-haiku-4). 키가 없으면 (None, None)."""
    client = llm.get_client(timeout=REASON_TIMEOUT_SECONDS)
    if client is None:
        return None, None
    return client, llm.model("fast")


def recommend_goals(
    tags: list[str], weekly_hours: float, exclude_ids: frozenset[str] = frozenset(), on_call=None
):
    """FR-GOAL-05 — 관심 태그 + 가용시간으로 추천 카드 3~5개를 만든다.

    RAG ① 순서: 카탈로그 검색(Claude 관련성, 실패 시 태그 겹침) → 기간 적합성(결정론)
    → 검색된 카탈로그 항목을 근거로 이유 문장(Claude, 실패 시 템플릿).

    exclude_ids — FR-GOAL-08: 최근(FEEDBACK_DISMISS_COOLDOWN_DAYS일 이내) "관심없음"으로
    남긴 goal_id 집합. 호출부(router)가 goal_feedback 조회 결과를 넘겨준다 — 이 함수
    자체는 DB를 모른다. 기간이 지나 더 이상 넘어오지 않으면 자동으로 다시 섞인다.

    반환값: (추천 목록, 실제 검색에 쓴 값 "tags"/"fallback_popular", 전부 기한초과 여부,
             기한을 못 맞춰 빠진 후보 목록, 검색 방식 "claude"/"tags")
    """
    candidates, search_method = search_catalog_ai(tags, k=20, on_call=on_call)
    candidates = [c for c in candidates if c.similarity >= SIMILARITY_THRESHOLD]

    query_used = "tags"
    if not candidates:
        query_used = "fallback_popular"
        candidates = popular_goals(k=RECOMMEND_MAX)

    if exclude_ids:
        candidates = [c for c in candidates if c.goal_id not in exclude_ids]

    evaluated = evaluate_all(candidates, weekly_hours)
    feasible = [c for c in evaluated if c.feasible]
    excluded = [c for c in evaluated if not c.feasible]
    all_exceeded = bool(evaluated) and not feasible

    if all_exceeded:
        return [], query_used, True, excluded, search_method

    feasible.sort(key=lambda c: (c.similarity, c.popularity), reverse=True)
    top = feasible[:RECOMMEND_MAX]

    client, model = _make_client()
    for candidate in top:
        reason = None
        if client is not None:
            reason = _ai_reason(candidate, tags, client, model)
            if reason and not reason_consistent(reason, candidate):
                reason = None  # 계산과 반대로 말한 문장은 내보내지 않는다
        if reason:
            candidate.reason = reason
            candidate.ai_generated = True
        else:
            candidate.reason = _template_reason(candidate, tags)
            candidate.ai_generated = False

    return top, query_used, False, excluded, search_method
