"""실사용자 테스트 지표 계산 규칙 (services/user_test_metrics.py)."""

from datetime import date, datetime

from services import user_test_metrics as m

START, END = date(2026, 10, 5), date(2026, 10, 11)  # 월~일
NOW = datetime(2026, 10, 12, 9, 0)


def block(i, day, hour, done=False, done_at=None, unit="u1", plan="p1"):
    return {
        "id": f"b{i}", "plan_id": plan, "unit_key": unit,
        "start_at": f"2026-10-{day:02d}T{hour:02d}:00:00+09:00",
        "end_at": f"2026-10-{day:02d}T{hour + 1:02d}:00:00+09:00",
        "done": done, "done_at": done_at,
    }


def run(**kw):
    base = dict(plans=[{"id": "p1"}], blocks=[], changes=[], goal_feedback=[], contest_feedback=[],
                sessions=[], notifications=[], start=START, end=END, now=NOW)
    base.update(kw)
    return m.compute("u", "P1", **base)


def test_adherence_counts_only_past_goal_blocks():
    blocks = [
        block(1, 6, 19, done=True), block(2, 7, 19), block(3, 8, 19, done=True),
        block(4, 9, 19, unit="contest-abcd1234-d7"),  # 관심 공모전 준비 블록은 빼고
    ]
    r = run(blocks=blocks, now=datetime(2026, 10, 9, 23, 0))
    assert (r.adherence.hit, r.adherence.total) == (2, 3)


def test_block_not_finished_yet_is_not_counted():
    r = run(blocks=[block(1, 8, 19)], now=datetime(2026, 10, 8, 19, 30))
    assert r.adherence.total == 0


def test_checkpoint_needs_every_block_of_the_week_done_by_sunday():
    ok = [block(1, 6, 19, done=True, done_at="2026-10-06T20:00:00+09:00"),
          block(2, 11, 10, done=True, done_at="2026-10-11T23:00:00+09:00")]
    late = [block(3, 6, 19, done=True, done_at="2026-10-12T08:00:00+09:00", plan="p2")]
    r = run(plans=[{"id": "p1"}, {"id": "p2"}], blocks=ok + late)
    assert (r.checkpoint.hit, r.checkpoint.total) == (1, 2)


def test_week_whose_sunday_has_not_passed_is_not_judged():
    r = run(blocks=[block(1, 6, 19, done=True)], now=datetime(2026, 10, 11, 12, 0))
    assert r.checkpoint.total == 0


def test_replan_ratio_uses_nightly_moves_only():
    blocks = [block(i, 6 + i, 19) for i in range(4)]
    changes = [
        {"block_id": "b0", "origin": "nightly", "change_type": "move", "created_at": "2026-10-07T03:00:00+09:00"},
        {"block_id": "b0", "origin": "nightly", "change_type": "move", "created_at": "2026-10-08T03:00:00+09:00"},
        {"block_id": "b1", "origin": "manual", "change_type": "move", "created_at": "2026-10-07T12:00:00+09:00"},
    ]
    r = run(blocks=blocks, changes=changes)
    assert (r.replan_moved.hit, r.replan_moved.total) == (1, 4)


def test_feedback_sessions_and_nudges():
    r = run(
        goal_feedback=[{"interested": True}, {"interested": False}, {"interested": True}],
        contest_feedback=[{"rating": "helpful"}, {"rating": "not_relevant"}],
        sessions=[{"started_at": "2026-10-06T19:00:00+09:00", "minutes": 50},
                  {"started_at": "2026-10-06T21:00:00+09:00", "minutes": 30},
                  {"started_at": "2026-10-01T19:00:00+09:00", "minutes": 99}],  # 기간 밖
        notifications=[{"type": "after_block", "is_read": True, "sent_at": "2026-10-06T21:35:00+09:00"},
                       {"type": "daily_nightly", "is_read": False, "sent_at": "2026-10-06T21:00:00+09:00"},
                       {"type": "10min_before", "is_read": False, "sent_at": "2026-10-06T18:50:00+09:00"}],
    )
    assert (r.goal_fit.hit, r.goal_fit.total) == (2, 3)
    assert (r.contest_fit.hit, r.contest_fit.total) == (1, 2)
    assert (r.study_minutes, r.study_sessions, r.active_days) == (80, 2, 1)
    assert (r.nudges_read.hit, r.nudges_read.total) == (1, 2)
    assert sum(r.notifications.values()) == 3


def test_total_and_markdown_use_pooled_counts_and_targets():
    a = run(blocks=[block(1, 6, 19, done=True), block(2, 7, 19, done=True)])
    b = m.compute("u2", "P2", plans=[{"id": "p9"}], blocks=[block(3, 6, 19, plan="p9")], changes=[],
                  goal_feedback=[], contest_feedback=[], sessions=[], notifications=[],
                  start=START, end=END, now=NOW)
    t = m.total([a, b])
    assert (t.adherence.hit, t.adherence.total) == (2, 3)
    text = m.to_markdown([a, b], START, END, NOW)
    assert "| 일정 준수율 | 67% (2/3) | 60% 이상 | 달성 |" in text
    assert "| 목표 추천 적합 | — | 80% 이상 | 자료 없음 |" in text
    assert "| P2 |" in text and "@" not in text
