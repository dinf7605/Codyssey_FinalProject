"""LLM을 사용하지 않는 공모전 준비 기간 계산."""

from __future__ import annotations

from datetime import date
from math import ceil, floor

from schemas.contest import Contest, PreparationEstimateResponse
from services.contest_repository import PreparationHours


TIGHT_BUFFER_RATIO = 1.3


def estimate_preparation(
    contest: Contest,
    weekly_hours: float,
    standard: PreparationHours,
    *,
    today: date | None = None,
) -> PreparationEstimateResponse:
    """표준 준비시간과 마감일을 이용해 최소 기간과 가능 여부를 계산한다."""

    if weekly_hours <= 0:
        raise ValueError("주당 투입 가능 시간은 0보다 커야 합니다")

    current_date = today or date.today()
    days_left = max(0, (contest.deadline - current_date).days)
    weeks_left = floor(days_left / 7)
    weeks_needed = ceil(standard.hours / weekly_hours)

    if days_left < weeks_needed * 7:
        verdict = "impossible"
        message = "이번 회차는 어렵습니다. 다음 회차 또는 유사 공고를 확인해 주세요."
    elif days_left < ceil(weeks_needed * 7 * TIGHT_BUFFER_RATIO):
        verdict = "tight"
        message = "준비 기간이 빠듯합니다. 주당 투입 시간을 확보해 주세요."
    else:
        verdict = "possible"
        message = "현재 입력한 시간으로 마감 전 준비가 가능합니다."

    return PreparationEstimateResponse(
        contest_id=contest.id,
        weekly_hours=weekly_hours,
        standard_hours=standard.hours,
        hours_source=standard.source,
        estimated=standard.source != "exact",
        weeks_needed=weeks_needed,
        days_left=days_left,
        weeks_left=weeks_left,
        verdict=verdict,
        message=message,
    )
