"""기간 계산 모듈 (FR-GOAL-04 기간 적합성 판정 · FR-GOAL-09 최소·권장 기간 산정) — 담당 B.

LLM 을 쓰지 않는다. 같은 입력이면 항상 같은 결과가 나와야 검증할 수 있기 때문이다
(scheduler.py · validator.py 와 같은 원칙 — 루트 README "판정·계산 구간은 결정론적").

FR-GOAL-04 와 FR-GOAL-09 는 기능명세서 비고란에 "같은 계산 모듈 사용" 이라고 적혀 있어
한 파일로 합쳤다.
"""

from __future__ import annotations

from datetime import date, datetime

from schemas.goal import RECOMMENDED_BUFFER, FeasibleCandidate, GoalCandidate

# 주당 최대 투입 가능 시간을 가용시간의 몇 %로 볼지.
# 기능명세서 FR-GOAL-09 기타의견: "확정 필요" 라고 남겨둔 값이라, 우선 100%로 잡고
# 여기 한 곳만 고치면 전체에 반영되게 해 둔다.
WEEKLY_MAX_RATIO = 1.0


def _weeks_between(today: date, deadline_str: str | None) -> float | None:
    if not deadline_str:
        return None
    try:
        deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    days = (deadline - today).days
    return max(days, 0) / 7


def evaluate_candidate(
    candidate: GoalCandidate, weekly_hours: float, today: date | None = None
) -> FeasibleCandidate:
    """후보 하나의 최소·권장 기간을 구하고 기한 안에 되는지 판정한다."""
    today = today or date.today()
    weekly_max = weekly_hours * WEEKLY_MAX_RATIO

    if weekly_max <= 0:
        min_weeks = float("inf")
    else:
        min_weeks = candidate.standard_hours / weekly_max
    recommended_weeks = min_weeks * RECOMMENDED_BUFFER

    weeks_to_deadline = _weeks_between(today, candidate.deadline)
    feasible = weeks_to_deadline is None or min_weeks <= weeks_to_deadline

    return FeasibleCandidate(
        **candidate.model_dump(),
        weekly_hours=weekly_hours,
        min_weeks=round(min_weeks, 1) if min_weeks != float("inf") else -1,
        recommended_weeks=round(recommended_weeks, 1) if recommended_weeks != float("inf") else -1,
        feasible=feasible,
    )


def evaluate_all(
    candidates: list[GoalCandidate], weekly_hours: float, today: date | None = None
) -> list[FeasibleCandidate]:
    """후보 전부를 판정해서 feasible/infeasible 구분 없이 그대로 돌려준다.

    evaluate_candidates 는 화면에 보여줄 후보만 남기고 탈락한 후보의 상세(표준시간·
    최소기간·마감일)를 버리는데, "왜 기한을 맞추기 어려운지" 를 보여주려면(FR-GOAL-04
    UX 보완) 탈락한 후보의 상세도 필요하다. 그래서 라우터에서 별도로 이 함수를 불러
    evaluate_candidates 의 결과와 나눠서(§ feasible / infeasible) 함께 응답에 담는다.
    """
    return [evaluate_candidate(c, weekly_hours, today) for c in candidates]


def evaluate_candidates(
    candidates: list[GoalCandidate], weekly_hours: float, today: date | None = None
) -> tuple[list[FeasibleCandidate], bool]:
    """FR-GOAL-04 — 후보별로 판정하고, 기한 안에 드는 후보만 남긴다.

    전부 기한을 초과하면(all_exceeded) 빈 목록과 함께 True 를 돌려준다.
    프론트는 이 값으로 '기간 늘리기 / 범위 줄이기' 선택지를 보여준다.
    """
    evaluated = evaluate_all(candidates, weekly_hours, today)
    feasible_ones = [c for c in evaluated if c.feasible]
    if evaluated and not feasible_ones:
        return [], True
    return feasible_ones, False


def manual_goal_warning(
    due_date_str: str,
    weekly_hours: float,
    matched: GoalCandidate | None,
    today: date | None = None,
):
    """FR-GOAL-10 — 직접 입력한 기한이 무리인지 경고한다.

    카탈로그에서 비슷한 항목을 찾지 못하면(matched=None) 계산 없이 severity="unknown" 을 돌려준다.
    """
    from schemas.goal import ManualGoalWarning  # 순환 임포트 방지용 지역 임포트

    today = today or date.today()
    try:
        due = datetime.strptime(due_date_str, "%Y-%m-%d").date()
    except ValueError:
        return ManualGoalWarning(
            requested_weeks=0,
            severity="unknown",
            message="기한 형식을 확인할 수 없어 계산하지 못했습니다.",
        )
    requested_weeks = round(max((due - today).days, 0) / 7, 1)

    if matched is None:
        return ManualGoalWarning(
            requested_weeks=requested_weeks,
            severity="unknown",
            message="카탈로그에 없는 목표라 필요 기간을 계산하지 못했습니다. 기한은 직접 판단해 주세요.",
        )

    evaluated = evaluate_candidate(matched, weekly_hours, today)
    min_weeks, recommended_weeks = evaluated.min_weeks, evaluated.recommended_weeks

    if requested_weeks < min_weeks:
        severity = "danger"
        weekly_max = matched.standard_hours / requested_weeks if requested_weeks > 0 else float("inf")
        extra = round(max(weekly_max - weekly_hours, 0), 1)
        message = "입력하신 기한은 최소 필요 기간보다 짧아요."
    elif requested_weeks < recommended_weeks:
        severity = "warn"
        extra = 0.0
        message = "빠듯해요. 복습·이탈 여유 없이 딱 맞는 일정이 될 수 있어요."
    else:
        severity = "ok"
        extra = 0.0
        message = "이 기한이면 충분히 여유가 있어요."

    return ManualGoalWarning(
        min_weeks=min_weeks,
        recommended_weeks=recommended_weeks,
        requested_weeks=requested_weeks,
        severity=severity,
        extra_weekly_hours_needed=extra,
        message=message,
    )
