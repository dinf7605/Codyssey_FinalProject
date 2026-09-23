"""기간 계산 모듈 테스트 (FR-GOAL-04 적합성 판정 · FR-GOAL-09 최소·권장 기간 · FR-GOAL-10 경고)."""

from datetime import date

from schemas.goal import GoalCandidate
from services.goal_feasibility import evaluate_candidate, evaluate_candidates, manual_goal_warning

TODAY = date(2026, 9, 22)


def cand(**over):
    base = dict(
        goal_id="g1",
        title="테스트 목표",
        field="테스트",
        tags=["테스트"],
        kind="cert",
        standard_hours=40,
        deadline=None,
    )
    base.update(over)
    return GoalCandidate(**base)


def test_같은_입력이면_같은_결과():
    a = evaluate_candidate(cand(), weekly_hours=10, today=TODAY)
    b = evaluate_candidate(cand(), weekly_hours=10, today=TODAY)
    assert a.min_weeks == b.min_weeks
    assert a.recommended_weeks == b.recommended_weeks


def test_최소_기간은_표준시간_나누기_주당시간():
    result = evaluate_candidate(cand(standard_hours=40), weekly_hours=10, today=TODAY)
    assert result.min_weeks == 4.0


def test_권장_기간은_최소기간의_1점3배():
    result = evaluate_candidate(cand(standard_hours=40), weekly_hours=10, today=TODAY)
    assert result.recommended_weeks == round(4.0 * 1.3, 1)


def test_마감일_안에_들면_feasible():
    result = evaluate_candidate(
        cand(standard_hours=40, deadline="2026-11-24"), weekly_hours=10, today=TODAY
    )
    assert result.feasible is True


def test_마감일을_넘기면_infeasible():
    result = evaluate_candidate(
        cand(standard_hours=200, deadline="2026-10-01"), weekly_hours=5, today=TODAY
    )
    assert result.feasible is False


def test_마감일이_없으면_항상_feasible():
    result = evaluate_candidate(cand(standard_hours=999, deadline=None), weekly_hours=1, today=TODAY)
    assert result.feasible is True


def test_전부_기한초과면_all_exceeded():
    candidates = [
        cand(goal_id="g1", standard_hours=500, deadline="2026-10-01"),
        cand(goal_id="g2", standard_hours=500, deadline="2026-10-05"),
    ]
    feasible, all_exceeded = evaluate_candidates(candidates, weekly_hours=2, today=TODAY)
    assert all_exceeded is True
    assert feasible == []


def test_하나라도_되면_all_exceeded_아님():
    candidates = [
        cand(goal_id="g1", standard_hours=500, deadline="2026-10-01"),
        cand(goal_id="g2", standard_hours=10, deadline="2026-12-01"),
    ]
    feasible, all_exceeded = evaluate_candidates(candidates, weekly_hours=10, today=TODAY)
    assert all_exceeded is False
    assert [c.goal_id for c in feasible] == ["g2"]


def test_카탈로그에_없으면_경고_대신_unknown():
    warning = manual_goal_warning("2026-12-01", 5, matched=None, today=TODAY)
    assert warning.severity == "unknown"
    assert warning.min_weeks is None


def test_최소기간보다_짧으면_danger():
    matched = cand(standard_hours=80)
    warning = manual_goal_warning("2026-09-29", 5, matched=matched, today=TODAY)  # 1주
    assert warning.severity == "danger"


def test_충분히_여유있으면_ok():
    matched = cand(standard_hours=20)
    warning = manual_goal_warning("2026-12-01", 10, matched=matched, today=TODAY)  # 약 10주
    assert warning.severity == "ok"
