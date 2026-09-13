"""스케줄 배치 엔진 (FR-PLAN-03) — LLM을 쓰지 않는다.

왜 LLM을 안 쓰는가 (기획서 4-2절):
  같은 입력에 항상 같은 결과가 나와야 검증이 가능하다.
  "어제와 다른 일정표"는 신뢰할 수 없고, 마감 초과·선행 위반 0건을 보장할 수도 없다.
  그래서 쪼개는 일(분해)만 AI가 하고, 놓는 일(배치)은 규칙으로 한다.

난수를 쓰지 않으므로 같은 입력이면 항상 같은 결과가 나온다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from schemas.plan import (
    BREAK_MINUTES,
    MAX_BLOCKS_PER_DAY,
    Availability,
    Block,
    SchedulePlan,
    StudyUnit,
    TimeSlot,
)


def _parse_hhmm(value: str) -> time:
    hh, _, mm = value.partition(":")
    return time(int(hh), int(mm))


def topological_order(units: list[StudyUnit]) -> list[StudyUnit]:
    """선행 관계를 지키는 순서로 정렬한다.

    같은 조건이면 입력 순서를 유지한다(안정 정렬).
    순서가 입력마다 흔들리면 '같은 입력 = 같은 결과'가 깨지기 때문이다.

    순환 참조가 있으면 남은 것을 입력 순서대로 뒤에 붙인다 — 멈추지 않는 쪽을 택한다.
    """
    by_id = {u.id: u for u in units}
    index = {u.id: i for i, u in enumerate(units)}

    remaining = dict(index)
    placed: set[str] = set()
    ordered: list[StudyUnit] = []

    while remaining:
        ready = [
            uid
            for uid in remaining
            if all(p in placed or p not in by_id for p in by_id[uid].prerequisites)
        ]
        if not ready:
            ordered.extend(by_id[uid] for uid in sorted(remaining, key=lambda x: index[x]))
            break
        ready.sort(key=lambda x: index[x])
        for uid in ready:
            ordered.append(by_id[uid])
            placed.add(uid)
            del remaining[uid]

    return ordered


def iter_day_windows(
    availability: Availability, start_day: date, end_day: date
) -> list[tuple[date, datetime, datetime]]:
    """날짜순으로 (날짜, 시작, 끝) 창을 만든다. 휴식일은 건너뛴다."""
    windows: list[tuple[date, datetime, datetime]] = []
    by_weekday: dict[int, list[TimeSlot]] = {}
    for slot in availability.slots:
        by_weekday.setdefault(slot.weekday, []).append(slot)

    for slots in by_weekday.values():
        slots.sort(key=lambda s: s.start)

    day = start_day
    while day <= end_day:
        if availability.rest_weekday is None or day.weekday() != availability.rest_weekday:
            for slot in by_weekday.get(day.weekday(), []):
                windows.append(
                    (
                        day,
                        datetime.combine(day, _parse_hhmm(slot.start)),
                        datetime.combine(day, _parse_hhmm(slot.end)),
                    )
                )
        day += timedelta(days=1)

    return windows


def build_schedule(
    units: list[StudyUnit],
    availability: Availability,
    start_day: date,
    deadline: date,
    fixed_blocks: list[Block] | None = None,
) -> SchedulePlan:
    """학습 단위를 빈 시간에 놓는다.

    지키는 규칙
      - 선행 단위가 끝난 뒤에만 시작한다
      - 하루 최대 3블록
      - 블록 사이 최소 10분 휴식 (단위가 최대 120분이므로 연속 2시간을 넘지 않는다)
      - 마감일을 넘기지 않는다 — 못 넣은 것은 unplaced 로 남긴다
      - 이미 고정된 블록(수동 이동·완료)은 그 자리를 비켜서 배치한다
    """
    fixed_blocks = fixed_blocks or []
    windows = iter_day_windows(availability, start_day, deadline)

    day_blocks: dict[date, list[Block]] = {}
    for b in fixed_blocks:
        day_blocks.setdefault(b.start.date(), []).append(b)

    blocks: list[Block] = list(fixed_blocks)
    unplaced: list[StudyUnit] = []
    notes: list[str] = []
    finish_at: dict[str, datetime] = {b.unit_id: b.end for b in fixed_blocks}

    for seq, unit in enumerate(topological_order(units), start=1):
        if unit.id in finish_at:
            continue  # 고정 블록으로 이미 배치됨

        earliest = datetime.combine(start_day, time.min)
        missing_prereq = False
        for p in unit.prerequisites:
            if p in finish_at:
                earliest = max(earliest, finish_at[p] + timedelta(minutes=BREAK_MINUTES))
            elif any(u.id == p for u in units):
                missing_prereq = True  # 선행이 아직 안 놓임 = 이번엔 못 놓는다
        if missing_prereq:
            unplaced.append(unit)
            continue

        placed = _place_one(unit, seq, windows, day_blocks, earliest)
        if placed is None:
            unplaced.append(unit)
            continue

        blocks.append(placed)
        day_blocks.setdefault(placed.start.date(), []).append(placed)
        finish_at[unit.id] = placed.end

    blocks.sort(key=lambda b: b.start)

    if unplaced:
        total = sum(u.estimated_minutes for u in unplaced)
        notes.append(
            f"남은 기간에 {len(unplaced)}개 학습 단위({total}분)를 배치하지 못했습니다. "
            "기한을 늘리거나 범위를 줄여 주세요."
        )

    return SchedulePlan(blocks=blocks, unplaced=unplaced, notes=notes)


def _place_one(
    unit: StudyUnit,
    seq: int,
    windows: list[tuple[date, datetime, datetime]],
    day_blocks: dict[date, list[Block]],
    earliest: datetime,
) -> Block | None:
    """이 단위를 놓을 수 있는 가장 이른 자리를 찾는다. 없으면 None."""
    need = timedelta(minutes=unit.estimated_minutes)

    for day, win_start, win_end in windows:
        today = day_blocks.get(day, [])
        if len(today) >= MAX_BLOCKS_PER_DAY:
            continue

        cursor = max(win_start, earliest)
        if cursor >= win_end:
            continue

        occupied = sorted(
            (b for b in today if b.start < win_end and b.end > win_start),
            key=lambda b: b.start,
        )
        for b in occupied:
            if cursor + need <= b.start - timedelta(minutes=BREAK_MINUTES):
                break  # 앞쪽 빈틈에 들어간다
            cursor = max(cursor, b.end + timedelta(minutes=BREAK_MINUTES))

        if cursor + need <= win_end:
            return Block(
                id=f"blk-{unit.id}-{seq}",
                unit_id=unit.id,
                title=unit.title,
                start=cursor,
                end=cursor + need,
                minutes=unit.estimated_minutes,
            )

    return None


def reschedule_incomplete(
    blocks: list[Block],
    units: list[StudyUnit],
    availability: Availability,
    today: date,
    deadline: date,
) -> SchedulePlan:
    """야간 재조정 (FR-PLAN-06).

    지난 날짜의 미완료 블록만 다시 놓는다.
      - 완료한 블록, 수동으로 옮긴 블록(locked), 오늘 이후 블록은 건드리지 않는다
      - 실패해도 기존 일정이 깨지지 않아야 하므로, 호출부에서 예외 시 원본을 유지한다
    """
    keep: list[Block] = []
    redo_unit_ids: list[str] = []

    for b in blocks:
        if b.done or b.locked or b.start.date() >= today:
            keep.append(b)
        else:
            redo_unit_ids.append(b.unit_id)

    by_id = {u.id: u for u in units}
    redo = [by_id[uid] for uid in redo_unit_ids if uid in by_id]

    if not redo:
        return SchedulePlan(
            blocks=sorted(keep, key=lambda b: b.start), notes=["재조정할 블록이 없습니다."]
        )

    plan = build_schedule(redo, availability, today, deadline, fixed_blocks=keep)
    plan.notes.insert(0, f"미완료 {len(redo)}개 블록을 남은 기간에 다시 배치했습니다.")
    return plan
