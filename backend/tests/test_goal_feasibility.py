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


# ── 다음 회차 (10-19) — 9월에 적은 시험일이 지나 주 10시간이면 토익만 추천되던 문제 ──

def test_해마다_있는_자격증은_이번_회차를_못_맞추면_다음_회차로_남는다():
    result = evaluate_candidate(
        cand(standard_hours=48, deadline="2026-11-15", recurring=True), weekly_hours=10, today=date(2026, 10, 19)
    )
    assert result.feasible is True
    assert result.next_round is True
    assert result.deadline is None  # 다음 회차 날짜는 공지 전 — 지어내지 않는다
    assert result.skipped_deadline == "2026-11-15"
    assert result.min_weeks == 4.8


def test_이번_회차를_맞출_수_있으면_그대로_이번_회차():
    result = evaluate_candidate(
        cand(standard_hours=40, deadline="2026-11-24", recurring=True), weekly_hours=10, today=TODAY
    )
    assert result.next_round is False
    assert result.deadline == "2026-11-24"


def test_시험일이_이미_지났으면_다음_회차():
    result = evaluate_candidate(
        cand(standard_hours=40, deadline="2026-09-01", recurring=True), weekly_hours=10, today=TODAY
    )
    assert (result.feasible, result.next_round) == (True, True)


def test_공모전은_마감을_못_맞추면_그대로_빠진다():
    result = evaluate_candidate(
        cand(kind="contest", standard_hours=40, deadline="2026-09-30"), weekly_hours=10, today=TODAY
    )
    assert (result.feasible, result.next_round) == (False, False)


def test_가용시간이_0이면_다음_회차로도_넘기지_않는다():
    result = evaluate_candidate(
        cand(standard_hours=40, deadline="2026-09-30", recurring=True), weekly_hours=0, today=TODAY
    )
    assert result.feasible is False


def test_시험일이_다_지나도_자격증_추천이_남는다():
    from services.goal_catalog import search_catalog

    feasible, all_exceeded = evaluate_candidates(search_catalog(["데이터분석"]), weekly_hours=6, today=date(2027, 1, 4))
    assert not all_exceeded
    assert {"cert-sqld", "cert-adsp", "cert-info-eng"} <= {c.goal_id for c in feasible}
    assert all(c.next_round for c in feasible if c.goal_id != "cert-toeic")


def test_다음_회차_추천_이유는_건너뛴_시험일을_말한다():
    from services.goal_recommender import _template_reason, reason_consistent

    c = evaluate_candidate(
        cand(standard_hours=48, deadline="2026-11-15", recurring=True, tags=["sqld"]), weekly_hours=10, today=date(2026, 10, 19)
    )
    text = _template_reason(c, ["sqld"])
    assert "다음 회차" in text and "2026-11-15" in text
    assert reason_consistent(text, c)
