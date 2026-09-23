"""비회원 AI 호출 한도 테스트 (FR-GOAL-12)."""

import pytest

from services.goal_limiter import RateLimitExceeded, _reset_for_tests, consume, usage_for


@pytest.fixture(autouse=True)
def _clean():
    _reset_for_tests()
    yield
    _reset_for_tests()


def test_세_번까지는_통과():
    for _ in range(3):
        consume("s1", is_member=False)  # 예외 없이 통과해야 한다


def test_네_번째는_막힌다():
    for _ in range(3):
        consume("s1", is_member=False)
    with pytest.raises(RateLimitExceeded):
        consume("s1", is_member=False)


def test_세션이_다르면_따로_센다():
    for _ in range(3):
        consume("s1", is_member=False)
    consume("s2", is_member=False)  # 다른 세션이라 통과해야 한다


def test_회원은_제한이_없다():
    for _ in range(10):
        consume("member-session", is_member=True)


def test_사용량_조회는_소비하지_않는다():
    consume("s1", is_member=False)
    before = usage_for("s1", is_member=False)
    after = usage_for("s1", is_member=False)
    assert before.used == after.used == 1
    assert before.remaining == 2
