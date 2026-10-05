"""스케줄 배치 엔진 (FR-PLAN-03) — LLM을 쓰지 않는다.

왜 LLM을 안 쓰는가 (기획서 4-2절):
  같은 입력에 항상 같은 결과가 나와야 검증이 가능하다.
  "어제와 다른 일정표"는 신뢰할 수 없고, 마감 초과·선행 위반 0건을 보장할 수도 없다.
  그래서 쪼개는 일(분해)만 AI가 하고, 놓는 일(배치)은 규칙으로 한다.

난수를 쓰지 않으므로 같은 입력이면 항상 같은 결과가 나온다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from schemas.plan import (
    BREAK_MINUTES,
    MAX_BLOCK_MINUTES,
    MAX_BLOCKS_PER_DAY,
    MIN_UNIT_MINUTES,
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


def subtract_busy(
    windows: list[tuple[date, datetime, datetime]], busy: list[tuple[datetime, datetime]]
) -> list[tuple[date, datetime, datetime]]:
    """빈 시간 창에서 바쁜 시간(구글 캘린더 일정, FR-PLAN-01)을 잘라 낸다. 순서는 그대로."""
    if not busy:
        return windows
    spans = sorted((s, e) for s, e in busy if e > s)
    out: list[tuple[date, datetime, datetime]] = []
    for day, start, end in windows:
        cursor = start
        for b_start, b_end in spans:
            if b_end <= cursor or b_start >= end:
                continue
            if b_start > cursor:
                out.append((day, cursor, b_start))
            cursor = max(cursor, b_end)
            if cursor >= end:
                break
        if cursor < end:
            out.append((day, cursor, end))
    return out


def longest_slot_minutes(availability: Availability) -> int:
    """가장 긴 공부 칸(분). 칸이 없으면 0."""
    def minutes(hhmm: str) -> int:
        t = _parse_hhmm(hhmm)
        return t.hour * 60 + t.minute

    return max((minutes(s.end) - minutes(s.start) for s in availability.slots), default=0)


def needs_split(minutes: int, longest_slot: int) -> bool:
    """빈칸 길이에 맞춰 나눠 놓을 단위인가 — 120분이 넘거나, 가장 긴 칸에도 통째로 안 들어가면.

    '하루 최대 1시간'을 고른 사람의 1시간 칸에는 90분 단위가 통째로 들어갈 수 없어 하나도 배치되지 않았다
    (10-05 사전 점검 2차). 그런 단위도 칸에 맞춰 60분 + 30분처럼 나눈다.
    """
    return minutes > MAX_BLOCK_MINUTES or (longest_slot > 0 and minutes > longest_slot)


def split_minutes(total: int) -> list[int]:
    """단위 시간을 블록(최대 MAX_BLOCK_MINUTES분) 여러 개로 고르게 나눈다. 5분 단위로 맞춘다.

    250분 → [85, 85, 80]. 120분 이하면 나누지 않는다. 둘 이상으로 나누면 한 블록이 60분을 넘는다.
    """
    n = max(1, math.ceil(total / MAX_BLOCK_MINUTES))
    if n == 1:
        return [total]
    steps, rest = divmod(total, 5)
    base, extra = divmod(steps, n)
    parts = [(base + (1 if i < extra else 0)) * 5 for i in range(n)]
    parts[-1] += rest
    return parts


@dataclass
class _Piece:
    """놓을 블록 하나 — 새로 나눈 조각이거나(처음 배치), 옮길 기존 블록이다(재조정)."""

    unit: StudyUnit
    block_id: str
    title: str
    minutes: int


def build_schedule(
    units: list[StudyUnit],
    availability: Availability,
    start_day: date,
    deadline: date,
    fixed_blocks: list[Block] | None = None,
    busy: list[tuple[datetime, datetime]] | None = None,
) -> SchedulePlan:
    """학습 단위를 빈 시간에 놓는다.

    지키는 규칙
      - 선행 단위가 끝난 뒤에만 시작한다 (단위의 마지막 블록이 끝난 뒤)
      - 120분이 넘는 단위는 블록 여러 개로 나눠 순서대로 놓는다 — 제목에 (1/3) 처럼 순서를 붙인다
      - 하루 최대 3블록
      - 블록 사이 최소 10분 휴식 (블록이 최대 120분이므로 연속 2시간을 넘지 않는다)
      - 마감일을 넘기지 않는다 — 블록 하나라도 못 넣은 단위는 통째로 unplaced 로 남긴다
      - 이미 고정된 블록(수동 이동·완료)은 그 자리를 비켜서 배치한다. 블록이 하나라도 있는 단위는 배치된 것으로 본다
      - 바쁜 시간(busy, 캘린더 일정)에는 놓지 않는다. 블록이 아니므로 하루 상한에 세지 않고 결과에도 넣지 않는다
    """
    fixed_blocks = fixed_blocks or []
    windows = subtract_busy(iter_day_windows(availability, start_day, deadline), busy or [])

    has_block = {b.unit_id for b in fixed_blocks}
    pieces: dict[str, list[_Piece]] = {}
    flex: dict[str, int] = {}  # 나눠 놓을 단위(needs_split) → 순번. 빈칸 길이에 맞춰 나눈다 (_fill_unit)
    longest = longest_slot_minutes(availability)
    for seq, unit in enumerate(topological_order(units), start=1):
        if unit.id in has_block:
            continue  # 고정 블록으로 이미 배치됨
        if needs_split(unit.estimated_minutes, longest):
            flex[unit.id] = seq
            continue
        pieces[unit.id] = [_Piece(unit=unit, block_id=f"blk-{unit.id}-{seq}", title=unit.title,
                                  minutes=unit.estimated_minutes)]

    placed, unplaced = _place_pieces(pieces, units, windows, start_day, fixed_blocks, whole_units=True, flex=flex)
    blocks = sorted(list(fixed_blocks) + placed, key=lambda b: b.start)

    notes: list[str] = []
    if unplaced:
        total = sum(u.estimated_minutes for u in unplaced)
        notes.append(
            f"남은 기간에 {len(unplaced)}개 학습 단위({total}분)를 배치하지 못했습니다. "
            "기한을 늘리거나 범위를 줄여 주세요."
        )

    return SchedulePlan(blocks=blocks, unplaced=unplaced, notes=notes)


def place_blocks(
    moving: list[Block],
    units: list[StudyUnit],
    availability: Availability,
    start_day: date,
    deadline: date,
    fixed_blocks: list[Block] | None = None,
) -> SchedulePlan:
    """이미 있는 블록을 같은 id·길이 그대로 다시 놓는다 (재조정 · 미루기 · 가용시간 바꾸기).

    다시 나누지 않는다 — 학습 기록·변경 내역이 같은 블록을 계속 가리키게.
    자리를 못 찾은 블록은 결과에 넣지 않는다(호출부가 원래 자리에 둔다). 그 단위에 기대는 블록도 놓지 않는다.
    선행 관계는 이번에 옮기는 단위끼리만 따진다 — 블록이 없는 단위(미배치·직접 지움)를 기다리지 않는다.
    """
    fixed_blocks = fixed_blocks or []
    by_id = {u.id: u for u in units}
    pieces: dict[str, list[_Piece]] = {}
    for b in sorted(moving, key=lambda x: x.start):
        unit = by_id.get(b.unit_id)
        if unit is not None:
            pieces.setdefault(unit.id, []).append(_Piece(unit=unit, block_id=b.id, title=b.title, minutes=b.minutes))
    involved = [u for u in units if u.id in pieces]
    windows = iter_day_windows(availability, start_day, deadline)
    placed, unplaced = _place_pieces(pieces, involved, windows, start_day, fixed_blocks, whole_units=False)
    return SchedulePlan(blocks=sorted(list(fixed_blocks) + placed, key=lambda b: b.start), unplaced=unplaced)


def _place_pieces(
    pieces: dict[str, list[_Piece]],
    units: list[StudyUnit],
    windows: list[tuple[date, datetime, datetime]],
    start_day: date,
    fixed_blocks: list[Block],
    whole_units: bool,
    flex: dict[str, int] | None = None,
) -> tuple[list[Block], list[StudyUnit]]:
    """조각들을 선행 순서대로 놓는다. (놓은 블록, 못 놓은 단위).

    whole_units=True 면 한 단위의 조각을 전부 놓거나 하나도 놓지 않는다 (처음 배치 — 반쪽 단위를 만들지 않는다).
    flex 의 단위는 미리 자르지 않고 빈칸 길이에 맞춰 나눈다 (_fill_unit).
    """
    day_blocks: dict[date, list[Block]] = {}
    finish_at: dict[str, datetime] = {}
    for b in fixed_blocks:
        day_blocks.setdefault(b.start.date(), []).append(b)
        finish_at[b.unit_id] = max(finish_at.get(b.unit_id, b.end), b.end)

    unit_ids = {u.id for u in units}
    failed: set[str] = set()
    placed: list[Block] = []
    unplaced: list[StudyUnit] = []

    flex = flex or {}
    for unit in topological_order(units):
        todo = pieces.get(unit.id)
        if not todo and unit.id not in flex:
            continue

        earliest = datetime.combine(start_day, time.min)
        missing_prereq = False
        for p in unit.prerequisites:
            if p in failed:
                missing_prereq = True
            elif p in finish_at:
                earliest = max(earliest, finish_at[p] + timedelta(minutes=BREAK_MINUTES))
            elif p in unit_ids:
                missing_prereq = True  # 선행이 아직 안 놓임 = 이번엔 못 놓는다
        if missing_prereq:
            failed.add(unit.id)
            unplaced.append(unit)
            continue

        if unit.id in flex:
            filled = _fill_unit(unit, flex[unit.id], windows, day_blocks, earliest)
            if filled is None:
                failed.add(unit.id)
                unplaced.append(unit)
                continue
            placed.extend(filled)
            finish_at[unit.id] = max([finish_at.get(unit.id, filled[-1].end)] + [b.end for b in filled])
            continue

        mine: list[Block] = []
        ok = True
        for piece in todo:
            block = _place_one(piece, windows, day_blocks, earliest)
            if block is None:
                ok = False
                if whole_units:
                    break
                continue
            day_blocks.setdefault(block.start.date(), []).append(block)
            mine.append(block)
            earliest = block.end + timedelta(minutes=BREAK_MINUTES)  # 같은 단위의 다음 조각은 그 뒤에

        if not ok and whole_units:
            for block in mine:
                day_blocks[block.start.date()].remove(block)
            mine = []
        if not ok:
            failed.add(unit.id)
            unplaced.append(unit)
        placed.extend(mine)
        for block in mine:
            finish_at[unit.id] = max(finish_at.get(unit.id, block.end), block.end)

    return placed, unplaced


MIN_PIECE_MINUTES = 60  # 긴 단위를 나눌 때 조각 최소 길이 (마지막 조각은 남은 만큼)


def _near_window(today: list[Block], win_start: datetime, win_end: datetime) -> list[Block]:
    """창과 겹치거나 창 앞뒤 휴식 시간 안에 붙어 있는 블록.

    창과 겹치는 블록만 보면, 칸이 시작하는 22:00 에 딱 끝나는 앞 칸(다른 목표·저녁 칸)의 블록을 놓쳐
    20:40~22:00 다음에 22:00~23:00 을 휴식 없이 붙였다 — 저장 검증(연속 2시간)에 걸려 확정이 막혔다 (10-06 사전 점검 2차).
    """
    gap = timedelta(minutes=BREAK_MINUTES)
    return [b for b in today if b.start < win_end + gap and b.end > win_start - gap]


def _free_gaps(
    win_start: datetime, win_end: datetime, today: list[Block], earliest: datetime
) -> list[tuple[datetime, datetime]]:
    """창 안에서 블록을 놓을 수 있는 빈 구간 — 앞뒤 블록과는 10분 휴식을 둔다."""
    occupied = sorted(_near_window(today, win_start, win_end), key=lambda b: b.start)
    gaps: list[tuple[datetime, datetime]] = []
    cursor = max(win_start, earliest)
    for b in occupied:
        end = b.start - timedelta(minutes=BREAK_MINUTES)
        if end > cursor:
            gaps.append((cursor, end))
        cursor = max(cursor, b.end + timedelta(minutes=BREAK_MINUTES))
    if win_end > cursor:
        gaps.append((cursor, win_end))
    return gaps


def _chunk_for(gap: int, remaining: int) -> int:
    """빈 구간(gap분)에 이번 조각을 몇 분으로 놓을지. 0 이면 이 구간은 건너뛴다.

    같은 길이로 미리 자르면 3시간 칸에 120분 하나만 들어가고 50분이 버려졌다 (10-02 실측: 주 9시간 중 6시간만 쓰임).
    구간에 두 조각이 들어가면 반씩 나눠 칸을 채운다 — 3시간 칸 → 85분 + 85분.
    """
    if remaining <= min(gap, MAX_BLOCK_MINUTES):
        return remaining
    if gap >= 2 * MIN_PIECE_MINUTES + BREAK_MINUTES:
        size = (gap - BREAK_MINUTES) // 2 // 5 * 5
    else:
        size = gap // 5 * 5
    size = min(size, MAX_BLOCK_MINUTES, remaining)
    left = remaining - size
    if 0 < left < MIN_UNIT_MINUTES:
        size = remaining - MIN_UNIT_MINUTES  # 너무 짧은 꼬리 조각을 남기지 않는다
    return size if size >= MIN_PIECE_MINUTES else 0


def _fill_unit(
    unit: StudyUnit,
    seq: int,
    windows: list[tuple[date, datetime, datetime]],
    day_blocks: dict[date, list[Block]],
    earliest: datetime,
) -> list[Block] | None:
    """120분이 넘는 단위를 빈칸에 맞춰 나눠 놓는다. 다 못 놓으면 하나도 남기지 않고 None."""
    remaining = unit.estimated_minutes
    mine: list[Block] = []
    for day, win_start, win_end in windows:
        if remaining <= 0:
            break
        while remaining > 0:
            today = day_blocks.setdefault(day, [])
            if len(today) >= MAX_BLOCKS_PER_DAY:
                break
            spot = None
            for gap_start, gap_end in _free_gaps(win_start, win_end, today, earliest):
                size = _chunk_for(int((gap_end - gap_start).total_seconds() // 60), remaining)
                if size:
                    spot = (gap_start, size)
                    break
            if spot is None:
                break
            start, size = spot
            block = Block(id="", unit_id=unit.id, title=unit.title, start=start,
                          end=start + timedelta(minutes=size), minutes=size)
            today.append(block)
            mine.append(block)
            remaining -= size
            earliest = block.end + timedelta(minutes=BREAK_MINUTES)  # 같은 단위의 다음 조각은 그 뒤에

    if remaining > 0:
        for block in mine:
            day_blocks[block.start.date()].remove(block)
        return None

    n = len(mine)
    out = [
        b.model_copy(update={
            "id": f"blk-{unit.id}-{seq}" if n == 1 else f"blk-{unit.id}-{seq}-{k}",
            "title": unit.title if n == 1 else f"{unit.title} ({k}/{n})",
        })
        for k, b in enumerate(mine, start=1)
    ]
    for old, new in zip(mine, out):  # 하루 목록 안의 임시 블록을 이름 붙인 블록으로 바꾼다
        lst = day_blocks[old.start.date()]
        lst[lst.index(old)] = new
    return out


def _place_one(
    piece: _Piece,
    windows: list[tuple[date, datetime, datetime]],
    day_blocks: dict[date, list[Block]],
    earliest: datetime,
) -> Block | None:
    """이 조각을 놓을 수 있는 가장 이른 자리를 찾는다. 없으면 None."""
    need = timedelta(minutes=piece.minutes)

    for day, win_start, win_end in windows:
        today = day_blocks.get(day, [])
        if len(today) >= MAX_BLOCKS_PER_DAY:
            continue

        cursor = max(win_start, earliest)
        if cursor >= win_end:
            continue

        occupied = sorted(_near_window(today, win_start, win_end), key=lambda b: b.start)
        for b in occupied:
            if cursor + need <= b.start - timedelta(minutes=BREAK_MINUTES):
                break  # 앞쪽 빈틈에 들어간다
            cursor = max(cursor, b.end + timedelta(minutes=BREAK_MINUTES))

        if cursor + need <= win_end:
            return Block(
                id=piece.block_id,
                unit_id=piece.unit.id,
                title=piece.title,
                start=cursor,
                end=cursor + need,
                minutes=piece.minutes,
            )

    return None


def blocks_to_redo(blocks: list[Block], units: list[StudyUnit], today: date) -> list[Block]:
    """재조정할 블록 — 지난 날짜의 미완료 블록 + 그 단위에 (간접적으로라도) 기대는 뒤 블록.

    지난 블록만 앞으로 옮기면, 그 단위를 선행으로 둔 뒤 블록보다 늦게 놓여 순서가 뒤집힌다.
    그래서 기대는 블록도 함께 다시 놓는다. 완료·수동 고정(locked) 블록은 건드리지 않는다.
    """
    movable = [b for b in blocks if not b.done and not b.locked]
    pushed = {b.unit_id for b in movable if b.start.date() < today}
    if not pushed:
        return []
    grew = True
    while grew:
        grew = False
        for u in units:
            if u.id not in pushed and pushed.intersection(u.prerequisites):
                pushed.add(u.id)
                grew = True
    return [b for b in movable if b.unit_id in pushed]


def reschedule_incomplete(
    blocks: list[Block],
    units: list[StudyUnit],
    availability: Availability,
    today: date,
    deadline: date,
) -> SchedulePlan:
    """야간 재조정 (FR-PLAN-06).

    지난 날짜의 미완료 블록과, 그 블록에 기대는 뒤 블록을 다시 놓는다 (blocks_to_redo).
      - 완료한 블록, 수동으로 옮긴 블록(locked)은 건드리지 않는다
      - 실패해도 기존 일정이 깨지지 않아야 하므로, 호출부에서 예외 시 원본을 유지한다
    저장된 계획에 적용·기록하는 일은 services/replan.py 가 한다.
    """
    redo_blocks = blocks_to_redo(blocks, units, today)
    redo_ids = {b.id for b in redo_blocks}
    keep = [b for b in blocks if b.id not in redo_ids]

    if not redo_blocks:
        return SchedulePlan(
            blocks=sorted(keep, key=lambda b: b.start), notes=["재조정할 블록이 없습니다."]
        )

    # 블록 id·길이는 그대로 두고 자리만 옮긴다. 못 놓은 블록은 원래 자리에 남긴다
    plan = place_blocks(redo_blocks, units, availability, today, deadline, fixed_blocks=keep)
    moved = {b.id for b in plan.blocks}
    plan.blocks = sorted(plan.blocks + [b for b in redo_blocks if b.id not in moved], key=lambda b: b.start)
    plan.notes.insert(0, f"미완료 블록과 그 뒤 순서 {len(redo_blocks)}개를 남은 기간에 다시 배치했습니다.")
    if plan.unplaced:
        plan.notes.append(f"{len(plan.unplaced)}개 학습 단위는 자리가 없어 원래 자리에 두었습니다.")
    return plan
