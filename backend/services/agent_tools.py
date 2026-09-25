"""학습 분해 에이전트가 쓰는 도구 6종 (AI기능명세 1).

각 도구는 두 부분으로 되어 있다.
  TOOL_SCHEMAS — Claude 에게 넘기는 도구 설명 (무엇을 하는지, 어떤 값을 받는지)
  run_tool()   — 실제로 실행하는 파이썬 함수

도구가 읽는 곳 (목업 없음)
  get_goal_catalog     목표 카탈로그 — services/goal_catalog.py (담당 B)
  get_available_slots  이번 요청의 사용자 가용시간 (context) — 구글 캘린더는 FR-PLAN-01 에서
  search_curriculum    표준 커리큘럼 — curriculum_units 테이블 (마이그레이션 009)
  estimate_effort      위 커리큘럼의 권장 시간, 없으면 이름 길이로 어림
  search_contests      공모전 — contests 테이블 (담당 D 의 contest_repository)

DB 에 닿지 못하면 빈 결과와 안내(note)를 돌려준다 — 모델은 그 단위를 '추정'으로 표시하거나
상한에 걸려 표준 템플릿으로 넘어간다. 도구 하나 때문에 계획 만들기가 멈추지 않는다.
"""

from __future__ import annotations

from datetime import date

from services import curriculum

# strict=True 를 쓰려면 additionalProperties: false 와 required 가 있어야 한다.
# 이걸 걸어두면 Claude 가 넘기는 인자가 스키마를 반드시 통과하므로
# "JSON 스키마 검증 실패" 폴백이 걸릴 일 자체가 줄어든다.
TOOL_SCHEMAS = [
    {
        "name": "get_goal_catalog",
        "description": "관심분야에 맞는 자격증·공모전 후보를 찾는다. 표준 학습시간과 시험일을 함께 돌려준다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "interest_tags": {"type": "array", "items": {"type": "string"}},
                "k": {"type": "integer", "description": "최대 개수"},
            },
            "required": ["interest_tags", "k"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_available_slots",
        "description": "캘린더와 수동 입력에서 공부할 수 있는 빈 시간대를 가져온다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                "min_minutes": {"type": "integer"},
            },
            "required": ["from_date", "to_date", "min_minutes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_curriculum",
        "description": "목표의 표준 커리큘럼과 출제 범위를 검색한다. 분해의 근거가 되는 도구다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string"},
                "query": {"type": "string"},
                "k": {"type": "integer"},
            },
            "required": ["goal_id", "query", "k"],
            "additionalProperties": False,
        },
    },
    {
        "name": "estimate_effort",
        "description": "학습 단위별 예상 소요시간(분)을 추정한다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "units": {"type": "array", "items": {"type": "string"}},
                "level": {"type": "string", "description": "beginner / intermediate / advanced"},
            },
            "required": ["units", "level"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_contests",
        "description": "관심 태그나 목표로 공모전 공고를 검색한다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "deadline_before": {"type": "string", "description": "YYYY-MM-DD"},
                "k": {"type": "integer"},
            },
            "required": ["query", "deadline_before", "k"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_plan",
        "description": (
            "확정된 학습 블록을 일정에 저장한다. "
            "되돌리기 어려운 동작이라 에이전트가 직접 실행하지 않고 사용자 확인을 받는다."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "string"},
                "block_count": {"type": "integer"},
            },
            "required": ["goal_id", "block_count"],
            "additionalProperties": False,
        },
    },
]

# 사용자 확인 없이는 실행하지 않는 도구 (AI기능명세 2)
CONFIRM_REQUIRED = {"save_plan"}


def _db(context: dict):
    """요청이 넘긴 DB, 없으면 서비스 키 클라이언트. 설정이 없으면 None."""
    if context.get("db") is not None:
        return context["db"]
    try:
        from db import get_supabase_client  # 순환 import 를 피하려고 여기서 부른다

        return get_supabase_client()
    except Exception:  # noqa: BLE001 - 로컬 개발(키 없음)에서도 에이전트는 돈다
        return None


DB_UNAVAILABLE = "DB 에 연결하지 못했습니다. 근거 없이 나눈 단위는 estimated=true 로 표시하세요."


def _goal_catalog(args: dict) -> dict:
    from services.goal_catalog import popular_goals, search_catalog

    k = max(1, int(args.get("k", 5)))
    found = search_catalog(args.get("interest_tags", []), k=k) or popular_goals(k=k)
    return {
        "candidates": [
            {"goal_id": c.goal_id, "title": c.title, "standard_hours": c.standard_hours, "exam_date": c.deadline}
            for c in found
        ]
    }


def _available_slots(context: dict) -> dict:
    availability = context.get("availability")
    if availability is None or not availability.slots:
        return {"slots": [], "note": "사용자가 가용시간을 입력하지 않았습니다. 평일 저녁을 가정하지 말고 단위만 나누세요."}
    return {
        "slots": [s.model_dump() for s in availability.slots],
        "rest_weekday": availability.rest_weekday,
        "note": "사용자가 입력한 주간 가용시간입니다. 캘린더 일정의 제목·참석자는 읽지 않습니다.",
    }


def _contests(args: dict) -> dict:
    from services.contest_repository import ContestSearch, get_contest_repository

    before = args.get("deadline_before")
    items, _total = get_contest_repository().search(ContestSearch(
        query=args.get("query") or None,
        deadline_before=date.fromisoformat(before) if before else None,
        limit=max(1, min(int(args.get("k", 5)), 20)),
    ))
    return {"contests": [
        {"title": c.title, "host": c.host, "deadline": c.deadline.isoformat(), "url": c.official_url or c.source_url}
        for c in items
    ]}


def run_tool(name: str, args: dict, context: dict | None = None) -> dict:
    """도구를 실행한다. 실패해도 예외를 던지지 않고 빈 결과를 돌려준다.

    에이전트 루프가 도구 하나 때문에 멈추면 안 되기 때문이다 —
    빈 결과를 받으면 모델이 다른 경로를 찾거나, 상한에 걸려 템플릿으로 넘어간다.
    context: {"availability": Availability | None, "goal_id": str, "goal_title": str, "db": 클라이언트(테스트용)}
    """
    context = context or {}
    try:
        if name == "get_goal_catalog":
            return _goal_catalog(args)

        if name == "get_available_slots":
            # 구글 캘린더 연동(FR-PLAN-01) 전까지는 사용자가 입력한 가용시간만 쓴다
            return _available_slots(context)

        if name == "search_curriculum":
            db = _db(context)
            if db is None:
                return {"chunks": [], "note": DB_UNAVAILABLE}
            return curriculum.search(db, args.get("goal_id", ""), args.get("query", ""))

        if name == "estimate_effort":
            return {"estimates": curriculum.estimate(
                _db(context), args.get("units", []), args.get("level", ""),
                goal_id=context.get("goal_id", ""), goal_title=context.get("goal_title", ""),
            )}

        if name == "search_contests":
            return _contests(args)

        if name == "save_plan":
            return {"error": "save_plan 은 사용자 확인 후에만 실행됩니다"}

        return {"error": f"알 수 없는 도구: {name}"}

    except Exception as exc:  # noqa: BLE001 - 도구 하나가 루프를 멈추게 하지 않는다
        return {"error": f"{name} 실행 실패: {type(exc).__name__}", "note": DB_UNAVAILABLE}


def today_iso() -> str:
    return date.today().isoformat()
