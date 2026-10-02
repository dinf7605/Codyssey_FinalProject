"""스케줄 배치 엔진 테스트.

여기서 확인하는 것이 곧 AI 품질 평가의 "일정 실현 가능성 100%" 근거다.
"""

from datetime import date, datetime

from schemas.plan import Availability, Block, StudyUnit, TimeSlot
from services.scheduler import build_schedule, place_blocks, reschedule_incomplete, split_minutes, topological_order
from services.validator import validate_schedule

# 월·수·금 저녁, 일요일은 휴식
AVAIL = Availability(
    slots=[
        TimeSlot(weekday=0, start="20:00", end="22:00"),
        TimeSlot(weekday=2, start="20:00", end="22:00"),
        TimeSlot(weekday=4, start="19:00", end="22:00"),
    ],
    rest_weekday=6,
)

START = date(2026, 9, 14)      # 월요일
DEADLINE = date(2026, 10, 12)  # 4주 뒤


def units(n: int, minutes: int = 60, chain: bool = False) -> list[StudyUnit]:
    out = []
    for i in range(1, n + 1):
        out.append(
            StudyUnit(
                id=f"u{i:02d}",
                title=f"단위 {i}",
                estimated_minutes=minutes,
                prerequisites=[f"u{i - 1:02d}"] if chain and i > 1 else [],
            )
        )
    return out


def test_같은_입력이면_같은_결과가_나온다():
    """난수를 쓰지 않으므로 몇 번을 돌려도 같아야 한다."""
    a = build_schedule(units(8), AVAIL, START, DEADLINE)
    b = build_schedule(units(8), AVAIL, START, DEADLINE)
    assert [x.model_dump() for x in a.blocks] == [x.model_dump() for x in b.blocks]


def test_배치_결과가_규칙을_어기지_않는다():
    us = units(10, 60)
    plan = build_schedule(us, AVAIL, START, DEADLINE)
    assert validate_schedule(plan.blocks, us, DEADLINE) == []


def test_휴식일에는_배치하지_않는다():
    plan = build_schedule(units(12), AVAIL, START, DEADLINE)
    assert all(b.start.weekday() != 6 for b in plan.blocks)


def test_하루_세_블록을_넘기지_않는다():
    plan = build_schedule(units(20, 30), AVAIL, START, DEADLINE)
    per_day = {}
    for b in plan.blocks:
        per_day.setdefault(b.start.date(), []).append(b)
    assert all(len(v) <= 3 for v in per_day.values())


def test_선행_관계를_지킨다():
    us = units(6, 60, chain=True)
    plan = build_schedule(us, AVAIL, START, DEADLINE)
    finish = {b.unit_id: b.end for b in plan.blocks}
    for u in us:
        if u.id in finish:
            for p in u.prerequisites:
                assert finish[p] <= finish[u.id]


def test_마감_안에_못_넣으면_미배치로_남긴다():
    """조용히 버리지 않는 것이 핵심이다."""
    us = units(60, 120)
    short_deadline = date(2026, 9, 21)
    plan = build_schedule(us, AVAIL, START, short_deadline)
    assert plan.unplaced, "배치 못 한 단위가 unplaced 에 남아야 한다"
    assert plan.notes, "사용자에게 알릴 안내 문구가 있어야 한다"
    assert validate_schedule(plan.blocks, us, short_deadline) == []


def test_위상정렬은_입력_순서를_유지한다():
    us = [
        StudyUnit(id="c", title="C", estimated_minutes=60, prerequisites=["a"]),
        StudyUnit(id="a", title="A", estimated_minutes=60),
        StudyUnit(id="b", title="B", estimated_minutes=60),
    ]
    assert [u.id for u in topological_order(us)] == ["a", "b", "c"]


def test_순환_참조가_있어도_멈추지_않는다():
    us = [
        StudyUnit(id="x", title="X", estimated_minutes=60, prerequisites=["y"]),
        StudyUnit(id="y", title="Y", estimated_minutes=60, prerequisites=["x"]),
    ]
    assert len(topological_order(us)) == 2


def test_야간_재조정은_완료·고정_블록을_건드리지_않는다():
    us = units(4, 60)
    plan = build_schedule(us, AVAIL, START, DEADLINE)

    plan.blocks[0].done = True
    plan.blocks[1].locked = True
    today = date(2026, 9, 21)  # 1주 뒤 — 앞의 블록들은 과거가 된다

    after = reschedule_incomplete(plan.blocks, us, AVAIL, today, DEADLINE)
    kept = {b.id for b in after.blocks}
    assert plan.blocks[0].id in kept, "완료 블록은 유지된다"
    assert plan.blocks[1].id in kept, "수동 고정 블록은 유지된다"


def test_고정_블록과_시간이_겹치지_않는다():
    fixed = [
        Block(
            id="fixed-1",
            unit_id="ext",
            title="이미 잡힌 일정",
            start=datetime(2026, 9, 14, 20, 0),
            end=datetime(2026, 9, 14, 21, 0),
            minutes=60,
            locked=True,
        )
    ]
    us = units(5, 60)
    plan = build_schedule(us, AVAIL, START, DEADLINE, fixed_blocks=fixed)
    assert validate_schedule(plan.blocks, us, DEADLINE) == []


# ── 단위와 블록 분리 (10-02) — 긴 단위는 120분 이하 블록 여러 개로 ─────

def test_120분이_넘는_단위는_고르게_나눈다():
    assert split_minutes(90) == [90]
    assert split_minutes(250) == [85, 85, 80]
    assert all(m <= 120 for m in split_minutes(600)) and sum(split_minutes(600)) == 600


def test_긴_단위는_블록_여러_개로_순서대로_놓고_규칙을_지킨다():
    long = [StudyUnit(id="u01", title="기출 반복", estimated_minutes=360),
            StudyUnit(id="u02", title="오답 정리", estimated_minutes=60, prerequisites=["u01"])]
    plan = build_schedule(long, AVAIL, START, DEADLINE)

    parts = [b for b in plan.blocks if b.unit_id == "u01"]
    assert [b.title for b in parts] == ["기출 반복 (1/3)", "기출 반복 (2/3)", "기출 반복 (3/3)"]
    assert sum(b.minutes for b in parts) == 360 and all(b.minutes <= 120 for b in parts)
    assert parts == sorted(parts, key=lambda b: b.start)
    # 뒤 단위는 앞 단위의 마지막 블록이 끝난 뒤에 시작한다
    after = next(b for b in plan.blocks if b.unit_id == "u02")
    assert after.start >= parts[-1].end
    assert validate_schedule(plan.blocks, long, DEADLINE) == []


def test_조각_하나라도_못_넣으면_단위를_통째로_미배치로_남긴다():
    tight = date(2026, 9, 16)  # 월·수 저녁 2시간씩 = 블록 2개뿐
    plan = build_schedule([StudyUnit(id="u01", title="큰 단위", estimated_minutes=360)], AVAIL, START, tight)
    assert plan.blocks == [] and [u.id for u in plan.unplaced] == ["u01"]


def test_다시_놓기는_블록_id와_길이를_그대로_두고_자리만_옮긴다():
    long = [StudyUnit(id="u01", title="기출 반복", estimated_minutes=240)]
    first = build_schedule(long, AVAIL, START, DEADLINE).blocks
    moved = place_blocks(first, long, AVAIL, date(2026, 9, 21), DEADLINE).blocks
    assert sorted(b.id for b in moved) == sorted(b.id for b in first)
    assert [b.minutes for b in moved] == [b.minutes for b in first]
    assert min(b.start for b in moved).date() >= date(2026, 9, 21)
