"""규칙 검증기.

AI 품질 평가 항목 중 "일정 실현 가능성 100%"를 실제로 재는 도구다.
배치 결과가 규칙을 어기지 않았는지 기계적으로 확인한다 —
사람이 눈으로 보고 넘어가면 놓친다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from schemas.plan import (
    MAX_BLOCKS_PER_DAY,
    MAX_CONTINUOUS_MINUTES,
    Block,
    StudyUnit,
    Violation,
)


def validate_schedule(
    blocks: list[Block], units: list[StudyUnit], deadline: date
) -> list[Violation]:
    """위반 목록을 돌려준다. 빈 리스트면 통과."""
    problems: list[Violation] = []
    ordered = sorted(blocks, key=lambda b: b.start)

    # 1) 마감 초과
    for b in ordered:
        if b.end.date() > deadline:
            problems.append(
                Violation(
                    kind="deadline_exceeded",
                    block_id=b.id,
                    detail=f"{b.end.date()} 배치 — 마감 {deadline} 초과",
                )
            )

    # 2) 겹침
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.start < prev.end:
            problems.append(
                Violation(kind="overlap", block_id=cur.id, detail=f"{prev.id} 와 시간이 겹칩니다")
            )

    # 3) 선행 관계
    finish_at = {b.unit_id: b.end for b in ordered}
    by_id = {u.id: u for u in units}
    for b in ordered:
        unit = by_id.get(b.unit_id)
        if unit is None:
            continue
        for p in unit.prerequisites:
            if p not in finish_at:
                problems.append(
                    Violation(
                        kind="prerequisite_violation",
                        block_id=b.id,
                        detail=f"선행 단위 {p} 가 배치되지 않았습니다",
                    )
                )
            elif finish_at[p] > b.start:
                problems.append(
                    Violation(
                        kind="prerequisite_violation",
                        block_id=b.id,
                        detail=f"선행 단위 {p} 보다 먼저 시작합니다",
                    )
                )

    # 4) 하루 블록 수
    per_day: dict[date, list[Block]] = {}
    for b in ordered:
        per_day.setdefault(b.start.date(), []).append(b)
    for day, day_blocks in per_day.items():
        if len(day_blocks) > MAX_BLOCKS_PER_DAY:
            problems.append(
                Violation(
                    kind="daily_limit_exceeded",
                    block_id=day_blocks[MAX_BLOCKS_PER_DAY].id,
                    detail=f"{day} 에 {len(day_blocks)}블록 — 하루 {MAX_BLOCKS_PER_DAY}블록 초과",
                )
            )

    # 5) 연속 학습 시간
    for day_blocks in per_day.values():
        run_start: datetime | None = None
        run_end: datetime | None = None
        for b in sorted(day_blocks, key=lambda x: x.start):
            if run_end is not None and b.start <= run_end:
                run_end = max(run_end, b.end)
            else:
                run_start, run_end = b.start, b.end
            if run_start and (run_end - run_start) > timedelta(minutes=MAX_CONTINUOUS_MINUTES):
                minutes = int((run_end - run_start).total_seconds() // 60)
                problems.append(
                    Violation(
                        kind="continuous_limit_exceeded",
                        block_id=b.id,
                        detail=f"연속 {minutes}분 — {MAX_CONTINUOUS_MINUTES}분 초과",
                    )
                )

    return problems
