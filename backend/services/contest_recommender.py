"""공고 제목·분야와 직접 입력한 관심 태그를 비교하는 검증 가능한 기본 추천.

마감일은 수집한 값으로 마감 점수·목표 기한 필터를 계산한다.
위비티 원문·포스터·세부 자격을 추측하지 않는다. Claude가 제목 관련성을 판단해도
근거 없는 자격 적합 판정과 생성된 공고를 반환하지 않도록 이 경계를 유지한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from schemas.contest import Contest

# Claude 관련성 점수의 하한 (기획서 4-4 공고 검색 임계값)
MIN_CLAUDE_SIMILARITY = 0.62


def matching_tags(contest: Contest, tags: list[str]) -> list[str]:
    # 제목과 수집한 분야에서 찾는다 (분야가 비어 있는 옛 링크 전용 행은 제목만).
    haystack = (contest.title + " " + " ".join(contest.fields)).casefold()
    return [tag for tag in tags if tag.casefold() in haystack]


def rank_contests(
    contests: list[Contest], tags: list[str], rejected: set[str], today: date,
    similarities: dict[str, float] | None = None,
    previous_ids: set[str] | None = None,
    goal_deadline: date | None = None,
) -> list[dict]:
    if not tags:
        return []
    ranked = []
    for contest in contests:
        if contest.id in rejected or contest.status not in ("open", "upcoming", "unknown"):
            continue
        if contest.deadline is not None and contest.deadline < today:
            continue
        if goal_deadline and contest.deadline and contest.deadline > goal_deadline:
            continue
        matched = matching_tags(contest, tags)
        if similarities is not None:
            similarity = similarities.get(contest.id, 0)
            if similarity < MIN_CLAUDE_SIMILARITY:
                continue
        else:
            # 키워드 경로는 태그 하나만 제목에 있어도 근거가 된다.
            # 비율(일치 수 / 태그 수)에 0.62 를 걸면 관심 태그가 2개만 돼도 대부분 0건이 된다.
            # 비율은 키워드 추천끼리 순서를 정하는 데만 쓴다.
            if not matched:
                continue
            similarity = len(matched) / len(tags)
        days = (contest.deadline - today).days if contest.deadline else None
        deadline_score = 0.5 if days is None else 1.0 if 7 <= days <= 30 else 0.7 if days > 30 else 0.3
        # 응모자격은 공고 원문을 읽지 않았으므로 중립값. 충족 여부는 주장하지 않는다.
        eligibility_score = 0.5
        rerank_score = round(0.5 * similarity + 0.3 * deadline_score + 0.2 * eligibility_score, 5)
        ranked.append({
            "contest": contest, "matching_tags": matched,
            "similarity": round(similarity, 5), "deadline_score": deadline_score,
            "eligibility_score": eligibility_score, "rerank_score": rerank_score,
            "reason": _reason(matched, similarities is not None),
            "ai_generated": similarities is not None,
        })
    ordered = sorted(ranked, key=lambda row: (-row["rerank_score"], row["contest"].deadline or date.max))
    previous_ids = previous_ids or set()
    selected: list[dict] = []
    repeated = 0
    for row in ordered:
        was_recommended = row["contest"].id in previous_ids
        if was_recommended and repeated >= 3:
            continue
        selected.append(row)
        repeated += int(was_recommended)
        if len(selected) == 5:
            break
    return selected


def _reason(matched: list[str], by_claude: bool) -> str:
    """이유 문장은 규칙으로 만든다. 화면의 'AI 추천' 표시는 순위를 Claude 가 매겼다는 뜻이므로,
    Claude 가 판단한 경우에는 문장에서도 그렇게 밝힌다 — 규칙 문장이 AI 가 쓴 것처럼 읽히지 않게."""
    if by_claude:
        head = "Claude가 공고 제목과 관심 분야의 관련성을 높게 판단했습니다"
        head += f"(제목에 ‘{matched[0]}’ 포함). " if matched else ". "
    elif matched:
        head = f"공고 제목에 관심 키워드 ‘{matched[0]}’가 포함되어 있습니다. "
    else:
        head = ""
    return head + "응모 자격은 원문에서 확인해 주세요."


def recommendation_week(today: date) -> str:
    return (today - timedelta(days=today.weekday())).isoformat()


def rejection_weight(rated_at: str, now: datetime | None = None) -> float:
    """거절의 영향은 4주마다 절반으로 감소한다."""
    now = now or datetime.now(timezone.utc)
    rated = datetime.fromisoformat(rated_at.replace("Z", "+00:00"))
    if rated.tzinfo is None:
        rated = rated.replace(tzinfo=timezone.utc)
    days = max(0, (now - rated).total_seconds() / 86400)
    return 0.5 ** (days / 28)
