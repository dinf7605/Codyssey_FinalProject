"""공부량 대비 가용시간 점검 (FR-PLAN-02, 담당 C) — LLM 미사용.

"총 소요시간이 가용시간의 1.5배를 넘으면 범위 축소안을 함께 제시"
  - 가용시간: 오늘부터 기한까지 날마다 "실제로 들어가는 블록" 만큼 더한다
    빈 시간을 그냥 합치면 안 된다 — 블록 사이 10분 휴식 때문에 3시간 칸에 90분 단위는 하나만 들어간다.
    그래서 평균 단위 길이로 칸마다 몇 개 들어가는지 세고, 하루 3블록 상한과 휴식일을 반영한다
  - 축소안 1: 뒤쪽 단위부터 빼서 가용시간 안에 맞춘다. 남는 단위가 선행으로 쓰는 단위는 빼지 않는다
  - 축소안 2: 전부 하려면 기한을 언제까지 늘려야 하는가
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from schemas.plan import BREAK_MINUTES, MAX_BLOCKS_PER_DAY, MAX_UNIT_MINUTES, Availability, StudyUnit
from services.scheduler import topological_order

OVER_RATIO = 1.5


def _slot_minutes(start: str, end: str) -> int:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return max(0, eh * 60 + em - sh * 60 - sm)


def _fit(slot: int, length: int) -> tuple[int, int]:
    """칸 하나에 length 분 블록이 몇 개 들어가는가 → (블록 수, 분). n 개에 필요한 시간 = n*길이 + (n-1)*휴식."""
    n = (slot + BREAK_MINUTES) // (length + BREAK_MINUTES)
    return n, n * length


def daily_capacity(availability: Availability, lengths: tuple[int, int] = (MAX_UNIT_MINUTES, MAX_UNIT_MINUTES)) -> dict[int, int]:
    """요일별로 실제로 들어가는 공부 분. lengths = (평균 단위 길이, 가장 짧은 단위 길이).

    칸마다 평균 길이로 채운 경우와 가장 짧은 단위로 채운 경우 중 큰 쪽을 쓴다 —
    1시간 칸에 평균 90분 단위는 안 들어가도 60분 단위는 들어간다.
    """
    blocks: dict[int, int] = {}
    minutes: dict[int, int] = {}
    for s in availability.slots:
        if availability.rest_weekday is not None and s.weekday == availability.rest_weekday:
            continue
        slot = _slot_minutes(s.start, s.end)
        n, m = max((_fit(slot, length) for length in lengths), key=lambda fit: fit[1])
        blocks[s.weekday] = blocks.get(s.weekday, 0) + n
        minutes[s.weekday] = minutes.get(s.weekday, 0) + m
    # 하루 3블록 상한
    return {
        wd: round(m * min(1, MAX_BLOCKS_PER_DAY / blocks[wd])) if blocks[wd] else 0
        for wd, m in minutes.items()
    }


def available_minutes(
    availability: Availability, start: date, deadline: date,
    lengths: tuple[int, int] = (MAX_UNIT_MINUTES, MAX_UNIT_MINUTES),
) -> int:
    cap = daily_capacity(availability, lengths)
    total, day = 0, start
    while day <= deadline:
        total += cap.get(day.weekday(), 0)
        day += timedelta(days=1)
    return total


def check_scope(units: list[StudyUnit], availability: Availability, start: date, deadline: date) -> dict:
    total = sum(u.estimated_minutes for u in units)
    lengths = (round(total / len(units)), min(u.estimated_minutes for u in units)) if units else (MAX_UNIT_MINUTES,) * 2
    available = available_minutes(availability, start, deadline, lengths)
    ratio = round(total / available, 2) if available else None
    over = available == 0 or total > available * OVER_RATIO

    result = {
        "total_minutes": total,
        "available_minutes": available,
        "ratio": ratio,
        "over": over,
        "keep_unit_ids": [u.id for u in units],
        "drop_unit_ids": [],
        "suggested_deadline": None,
    }
    if not over:
        return result

    # 축소안 1 — 순서상 뒤쪽부터 뺀다. 남는 단위가 선행으로 쓰는 단위는 빼지 않는다
    ordered = topological_order(units)
    keep = {u.id for u in ordered}
    kept_minutes = total
    for u in reversed(ordered):
        if kept_minutes <= available:
            break
        needed_by_kept = any(u.id in k.prerequisites for k in ordered if k.id in keep and k.id != u.id)
        if needed_by_kept:
            continue
        keep.discard(u.id)
        kept_minutes -= u.estimated_minutes
    result["keep_unit_ids"] = [u.id for u in units if u.id in keep]
    result["drop_unit_ids"] = [u.id for u in units if u.id not in keep]

    # 축소안 2 — 지금 빈 시간으로 전부 하려면 며칠이 필요한가
    per_week = sum(daily_capacity(availability, lengths).values())
    if per_week:
        days_needed = math.ceil(total / (per_week / 7))
        result["suggested_deadline"] = (start + timedelta(days=days_needed)).isoformat()
    return result
