"""공고 제목과 직접 입력한 관심 태그를 비교하는 검증 가능한 기본 추천.

위비티 원문·포스터·세부 자격을 추측하지 않는다. 향후 벡터 색인이 들어와도
근거 없는 자격 적합 판정과 생성된 공고를 반환하지 않도록 이 경계를 유지한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from schemas.contest import Contest


def matching_tags(contest: Contest, tags: list[str]) -> list[str]:
    # 위비티에는 제목과 링크만 수집하기로 한 사용자 범위를 적용한다.
    haystack = contest.title.casefold()
    if contest.source != "wevity":
        haystack += " " + " ".join(contest.fields).casefold()
    return [tag for tag in tags if tag.casefold() in haystack]


def rank_contests(
    contests: list[Contest], tags: list[str], rejected: set[str], today: date,
    similarities: dict[str, float] | None = None,
) -> list[dict]:
    if not tags:
        return []
    ranked = []
    for contest in contests:
        if contest.id in rejected or contest.status not in ("open", "upcoming", "unknown"):
            continue
        if contest.deadline is not None and contest.deadline < today:
            continue
        matched = matching_tags(contest, tags)
        if not matched and similarities is None:
            continue
        similarity = similarities.get(contest.id, 0) if similarities is not None else len(matched) / len(tags)
        if similarity < 0.62:
            continue
        days = (contest.deadline - today).days if contest.deadline else None
        deadline_score = 0.5 if days is None else 1.0 if 7 <= days <= 30 else 0.7 if days > 30 else 0.3
        # 응모자격은 공고 원문을 읽지 않았으므로 중립값. 충족 여부는 주장하지 않는다.
        eligibility_score = 0.5
        rerank_score = round(0.5 * similarity + 0.3 * deadline_score + 0.2 * eligibility_score, 5)
        ranked.append({
            "contest": contest, "matching_tags": matched,
            "similarity": round(similarity, 5), "deadline_score": deadline_score,
            "eligibility_score": eligibility_score, "rerank_score": rerank_score,
            "reason": (f"공고 제목에 관심 키워드 ‘{matched[0]}’가 포함되어 있습니다. 응모 자격은 원문에서 확인해 주세요."
                       if matched else "공고 제목이 관심 분야와 의미상 유사합니다. 응모 자격은 원문에서 확인해 주세요."),
            "ai_generated": False,
        })
    return sorted(ranked, key=lambda row: (-row["rerank_score"], row["contest"].deadline or date.max))[:5]


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
