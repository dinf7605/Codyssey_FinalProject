"""규칙 검증기 테스트 — 위반을 실제로 잡아내는지 확인한다."""

from datetime import date, datetime, timedelta

from schemas.plan import Block, StudyUnit
from services.validator import validate_schedule

DEADLINE = date(2026, 10, 12)


def blk(bid, unit_id, start, minutes):
    return Block(
        id=bid,
        unit_id=unit_id,
        title=unit_id,
        start=start,
        end=start + timedelta(minutes=minutes),
        minutes=minutes,
    )


def test_문제가_없으면_빈_목록():
    us = [StudyUnit(id="u1", title="A", estimated_minutes=60)]
    bs = [blk("b1", "u1", datetime(2026, 9, 14, 20, 0), 60)]
    assert validate_schedule(bs, us, DEADLINE) == []


def test_마감_초과를_잡는다():
    us = [StudyUnit(id="u1", title="A", estimated_minutes=60)]
    bs = [blk("b1", "u1", datetime(2026, 10, 20, 20, 0), 60)]
    kinds = [v.kind for v in validate_schedule(bs, us, DEADLINE)]
    assert "deadline_exceeded" in kinds


def test_겹치는_블록을_잡는다():
    us = [
        StudyUnit(id="u1", title="A", estimated_minutes=60),
        StudyUnit(id="u2", title="B", estimated_minutes=60),
    ]
    bs = [
        blk("b1", "u1", datetime(2026, 9, 14, 20, 0), 60),
        blk("b2", "u2", datetime(2026, 9, 14, 20, 30), 60),
    ]
    kinds = [v.kind for v in validate_schedule(bs, us, DEADLINE)]
    assert "overlap" in kinds


def test_선행_위반을_잡는다():
    us = [
        StudyUnit(id="u1", title="A", estimated_minutes=60),
        StudyUnit(id="u2", title="B", estimated_minutes=60, prerequisites=["u1"]),
    ]
    bs = [
        blk("b2", "u2", datetime(2026, 9, 14, 20, 0), 60),   # 먼저 배치됨
        blk("b1", "u1", datetime(2026, 9, 16, 20, 0), 60),
    ]
    kinds = [v.kind for v in validate_schedule(bs, us, DEADLINE)]
    assert "prerequisite_violation" in kinds


def test_하루_상한_초과를_잡는다():
    us = [StudyUnit(id=f"u{i}", title=f"U{i}", estimated_minutes=30) for i in range(1, 5)]
    bs = [
        blk("b1", "u1", datetime(2026, 9, 14, 9, 0), 30),
        blk("b2", "u2", datetime(2026, 9, 14, 11, 0), 30),
        blk("b3", "u3", datetime(2026, 9, 14, 14, 0), 30),
        blk("b4", "u4", datetime(2026, 9, 14, 17, 0), 30),
    ]
    kinds = [v.kind for v in validate_schedule(bs, us, DEADLINE)]
    assert "daily_limit_exceeded" in kinds


def test_연속_2시간_초과를_잡는다():
    us = [
        StudyUnit(id="u1", title="A", estimated_minutes=120),
        StudyUnit(id="u2", title="B", estimated_minutes=60),
    ]
    bs = [
        blk("b1", "u1", datetime(2026, 9, 14, 18, 0), 120),
        blk("b2", "u2", datetime(2026, 9, 14, 20, 0), 60),  # 쉬지 않고 이어짐
    ]
    kinds = [v.kind for v in validate_schedule(bs, us, DEADLINE)]
    assert "continuous_limit_exceeded" in kinds
