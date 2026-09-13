"""학습 집계 (FR-STUDY-03) 와 레벨·스트릭 판정 (FR-STUDY-04).

기능명세서 규칙
  - 스트릭은 하루 20분 이상 학습하면 유지된다
  - 레벨은 누적 학습시간 기준 5단계이며 하락시키지 않는다
  - 하루 경계는 사용자 로컬 타임존 기준 (여기서는 이미 로컬 날짜로 들어온다고 본다)
  - 5분 미만은 기록하지 않는다 (FR-STUDY-01)
"""

from __future__ import annotations

from datetime import date, timedelta

MIN_RECORDED_MINUTES = 5   # 이보다 짧으면 기록하지 않는다
STREAK_MIN_MINUTES = 20    # 이 이상 해야 연속이 유지된다

# 프론트의 lib/growth.js 와 같은 기준을 쓴다. 둘이 어긋나면 화면과 서버가 다른 말을 하게 된다.
LEVELS = [
    (1, "입문", 0),
    (2, "초급", 10),
    (3, "중급", 30),
    (4, "상급", 80),
    (5, "최상급", 150),
]


def daily_totals(events: list[tuple[date, int]]) -> dict[date, int]:
    """(날짜, 분) 이벤트를 날짜별 합계로 모은다. 5분 미만은 버린다."""
    totals: dict[date, int] = {}
    for day, minutes in events:
        if minutes < MIN_RECORDED_MINUTES:
            continue
        totals[day] = totals.get(day, 0) + minutes
    return totals


def streak_days(totals: dict[date, int], today: date) -> int:
    """오늘(또는 어제)부터 거꾸로 세어 연속 학습일을 구한다.

    오늘 아직 공부하지 않았어도 어제까지 이어졌다면 끊긴 것으로 보지 않는다 —
    하루가 끝나기 전에 스트릭이 0으로 보이면 사용자가 포기해 버린다.
    """
    if totals.get(today, 0) >= STREAK_MIN_MINUTES:
        cursor = today
    elif totals.get(today - timedelta(days=1), 0) >= STREAK_MIN_MINUTES:
        cursor = today - timedelta(days=1)
    else:
        return 0

    count = 0
    while totals.get(cursor, 0) >= STREAK_MIN_MINUTES:
        count += 1
        cursor -= timedelta(days=1)
    return count


def level_of(total_minutes: int) -> tuple[int, str]:
    """누적 학습시간(분) -> (레벨, 이름). 레벨은 내려가지 않는다."""
    hours = total_minutes / 60
    current = LEVELS[0]
    for level in LEVELS:
        if hours >= level[2]:
            current = level
    return current[0], current[1]


def week_minutes(totals: dict[date, int], today: date) -> int:
    """이번 주(월~일) 학습 분."""
    monday = today - timedelta(days=today.weekday())
    return sum(m for d, m in totals.items() if monday <= d <= today)


def summarize(events: list[tuple[date, int]], today: date) -> dict:
    """화면에 필요한 값을 한 번에 만들어 준다."""
    totals = daily_totals(events)
    total = sum(totals.values())
    level, level_name = level_of(total)
    return {
        "total_minutes": total,
        "week_minutes": week_minutes(totals, today),
        "streak_days": streak_days(totals, today),
        "level": level,
        "level_name": level_name,
        "studied_days": len(totals),
    }
