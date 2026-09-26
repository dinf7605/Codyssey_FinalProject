"""표준 커리큘럼 조회 (담당 C) — curriculum_units 테이블 (마이그레이션 009).

학습 분해 에이전트의 search_curriculum · estimate_effort 도구가 쓴다.
테이블이 작아서(목표당 수십 줄) 한 번에 읽고 파이썬에서 고른다.
"""

from __future__ import annotations

from schemas.plan import MAX_UNIT_MINUTES, MIN_UNIT_MINUTES

NO_CURRICULUM_NOTE = (
    "이 목표의 표준 커리큘럼이 아직 없습니다. 일반적인 학습 순서로 나누고 모든 단위를 estimated=true 로 표시하세요."
)

# 수준별 소요시간 배율 — 초보는 같은 범위에 시간이 더 든다
LEVEL_FACTOR = {"beginner": 1.2, "intermediate": 1.0, "advanced": 0.8}


def load_rows(db) -> list[dict]:
    return db.table("curriculum_units").select("*").order("position").execute().data


def _keys(title: str) -> set[str]:
    """목표 이름에서 질의와 맞춰 볼 낱말. 'SQLD (SQL 개발자)' → {'sqld', 'sqld (sql 개발자)'}."""
    lowered = title.lower().strip()
    head = lowered.split("(")[0].strip()
    return {k for k in (lowered, head, head.split()[0] if head else "") if k}


def resolve_goal(rows: list[dict], goal_id: str, query: str) -> str | None:
    """goal_id 가 있으면 그대로, 'custom' 처럼 모르는 id 면 질의 속 목표 이름으로 찾는다."""
    titles = {r["goal_id"]: r["goal_title"] for r in rows}
    if goal_id in titles:
        return goal_id
    text = f"{goal_id} {query}".lower()
    hits = [gid for gid, title in titles.items() if any(k in text for k in _keys(title))]
    return hits[0] if len(hits) == 1 else None  # 둘 이상 걸리면 섣불리 고르지 않는다


def search(db, goal_id: str, query: str) -> dict:
    """과목별로 묶은 출제 범위. 없으면 빈 목록과 '추정으로 표시하라'는 안내."""
    rows = load_rows(db)
    gid = resolve_goal(rows, goal_id, query)
    if gid is None:
        return {"goal_id": None, "chunks": [], "note": NO_CURRICULUM_NOTE}

    chunks: list[dict] = []
    for r in (r for r in rows if r["goal_id"] == gid):
        if not chunks or chunks[-1]["chapter"] != r["subject"]:
            chunks.append({"chapter": r["subject"], "topics": [], "source": r["source"],
                           "verified": bool(r.get("verified"))})
        chunks[-1]["topics"].append({
            "title": r["topic"], "minutes": r["standard_minutes"], "review": bool(r.get("is_review")),
        })
    return {
        "goal_id": gid,
        "goal_title": next(r["goal_title"] for r in rows if r["goal_id"] == gid),
        "chunks": chunks,
        "note": (
            "minutes 는 한 번 앉아서 공부할 권장 시간(팀 추정)입니다. 이 값을 그대로 쓰면 되고 "
            "estimate_effort 로 다시 잴 필요가 없습니다. 짧은 항목은 같은 과목끼리 묶어도 됩니다."
        ),
    }


def _norm(text: str) -> str:
    return "".join(text.lower().split())


def _clamp(minutes: float) -> int:
    return int(min(MAX_UNIT_MINUTES, max(MIN_UNIT_MINUTES, round(minutes / 10) * 10)))


def estimate(db, units: list[str], level: str = "intermediate", goal_id: str = "", goal_title: str = "") -> list[dict]:
    """학습 단위별 예상 분. 커리큘럼에 같은 항목이 있으면 그 권장 시간, 없으면 이름 길이로 어림한다.

    이번 목표의 커리큘럼 안에서만 찾는다 — 'SQL 활용' 은 SQLD 에선 과목, 정보처리기사에선 세부 항목이라
    목표를 모르고 찾으면 다른 시험의 시간을 가져온다.
    """
    factor = LEVEL_FACTOR.get(level, 1.0)
    rows = load_rows(db) if db is not None else []
    gid = resolve_goal(rows, goal_id, goal_title)
    if gid:
        rows = [r for r in rows if r["goal_id"] == gid]
    topics = [(_norm(r["topic"]), r["standard_minutes"]) for r in rows]
    out = []
    for unit in units:
        key = _norm(unit)
        # 가장 길게 겹치는 항목을 쓴다 — '관계' 보다 '관계와 조인의 이해' 가 더 정확하다
        hits = [(len(t), m) for t, m in topics if t and (t in key or key in t)]
        match = max(hits)[1] if hits else None
        if match is not None:
            out.append({"unit": unit, "minutes": _clamp(match * factor), "basis": "curriculum"})
        else:
            out.append({"unit": unit, "minutes": _clamp((30 + len(unit) * 3) * factor), "basis": "heuristic"})
    return out
