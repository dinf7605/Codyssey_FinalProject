"""학습 집계·레벨·스트릭 테스트 (FR-STUDY-03 / FR-STUDY-04)."""

from datetime import date, timedelta

from services.aggregator import daily_totals, level_of, streak_days, summarize, week_minutes

TODAY = date(2026, 9, 14)  # 월요일


def test_5분_미만은_기록하지_않는다():
    totals = daily_totals([(TODAY, 3), (TODAY, 40)])
    assert totals[TODAY] == 40


def test_같은_날_여러_세션은_합산된다():
    totals = daily_totals([(TODAY, 30), (TODAY, 45)])
    assert totals[TODAY] == 75


def test_스트릭은_하루_20분_이상일_때_유지된다():
    totals = {TODAY - timedelta(days=i): 25 for i in range(5)}
    totals[TODAY - timedelta(days=2)] = 10  # 여기서 끊긴다
    assert streak_days(totals, TODAY) == 2


def test_오늘_안_했어도_어제까지_이어졌으면_유지된다():
    """하루가 끝나기 전에 0으로 보이면 사용자가 포기해 버린다."""
    totals = {TODAY - timedelta(days=i): 30 for i in range(1, 4)}
    assert streak_days(totals, TODAY) == 3


def test_아무_기록도_없으면_0():
    assert streak_days({}, TODAY) == 0


def test_레벨_구간():
    assert level_of(0)[0] == 1
    assert level_of(10 * 60)[0] == 2
    assert level_of(30 * 60)[0] == 3
    assert level_of(80 * 60)[0] == 4
    assert level_of(150 * 60)[0] == 5
    assert level_of(1000 * 60)[0] == 5


def test_이번_주는_월요일부터_센다():
    """주 경계에서 지난 주 기록이 섞이지 않아야 한다."""
    monday = date(2026, 9, 14)
    wednesday = date(2026, 9, 16)
    totals = {
        monday - timedelta(days=1): 999,  # 지난 주 일요일 — 세면 안 된다
        monday: 60,
        wednesday: 40,
    }
    assert week_minutes(totals, wednesday) == 100


def test_요약이_화면에_필요한_값을_모두_준다():
    events = [(TODAY - timedelta(days=i), 60) for i in range(10)]
    out = summarize(events, TODAY)
    assert out["total_minutes"] == 600
    assert out["streak_days"] == 10
    assert out["level"] >= 1
    assert out["level_name"]
