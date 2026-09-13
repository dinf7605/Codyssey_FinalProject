"""학습 분해 에이전트가 쓰는 도구 6종 (AI기능명세 1).

각 도구는 두 부분으로 되어 있다.
  TOOL_SCHEMAS — Claude 에게 넘기는 도구 설명 (무엇을 하는지, 어떤 값을 받는지)
  run_tool()   — 실제로 실행하는 파이썬 함수

지금은 목업 데이터를 돌려준다. Supabase 가 붙으면 이 함수 안만 바꾸면 되고
에이전트 쪽 코드는 건드릴 필요가 없다.
"""

from __future__ import annotations

from datetime import date

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


# ── 목업 데이터 ────────────────────────────────────────────
_CATALOG = [
    {"goal_id": "cert-info-eng", "title": "정보처리기사 필기", "standard_hours": 120, "exam_date": "2026-12-06"},
    {"goal_id": "cert-sqld", "title": "SQLD (SQL 개발자)", "standard_hours": 48, "exam_date": "2026-11-15"},
    {"goal_id": "cert-adsp", "title": "ADsP (데이터분석 준전문가)", "standard_hours": 40, "exam_date": "2026-11-22"},
]

_CURRICULUM = {
    "cert-info-eng": [
        {"chapter": "소프트웨어 설계", "topics": ["요구사항 확인", "화면 설계"], "source": "출제기준 2026"},
        {"chapter": "소프트웨어 개발", "topics": ["데이터 입출력", "통합 구현"], "source": "출제기준 2026"},
        {"chapter": "데이터베이스 구축", "topics": ["논리 설계", "물리 설계"], "source": "출제기준 2026"},
        {"chapter": "프로그래밍 언어 활용", "topics": ["기본 문법", "응용"], "source": "출제기준 2026"},
        {"chapter": "정보시스템 구축관리", "topics": ["보안", "신기술"], "source": "출제기준 2026"},
    ]
}


def run_tool(name: str, args: dict) -> dict:
    """도구를 실행한다. 실패해도 예외를 던지지 않고 빈 결과를 돌려준다.

    에이전트 루프가 도구 하나 때문에 멈추면 안 되기 때문이다 —
    빈 결과를 받으면 모델이 다른 경로를 찾거나, 상한에 걸려 템플릿으로 넘어간다.
    """
    try:
        if name == "get_goal_catalog":
            k = int(args.get("k", 20))
            tags = [t.lower() for t in args.get("interest_tags", [])]
            hits = [c for c in _CATALOG if not tags or any(t in c["title"].lower() for t in tags)]
            return {"candidates": (hits or _CATALOG)[:k]}

        if name == "get_available_slots":
            # 실제로는 캘린더 API + 수동 입력을 합친다 (FR-PLAN-01)
            return {
                "slots": [
                    {"weekday": 0, "start": "20:00", "end": "22:00"},
                    {"weekday": 2, "start": "20:00", "end": "22:00"},
                    {"weekday": 4, "start": "19:00", "end": "22:00"},
                    {"weekday": 5, "start": "10:00", "end": "13:00"},
                ],
                "note": "캘린더 일정의 제목·참석자는 읽지 않고 빈 시간대만 사용합니다.",
            }

        if name == "search_curriculum":
            goal_id = args.get("goal_id", "")
            chunks = _CURRICULUM.get(goal_id, [])
            return {"chunks": chunks[: int(args.get("k", 5))]}

        if name == "estimate_effort":
            units = args.get("units", [])
            return {
                "estimates": [
                    {"unit": u, "minutes": max(30, min(120, 30 + len(u) * 3))} for u in units
                ]
            }

        if name == "search_contests":
            return {"contests": []}  # 분해 단계에서는 보통 쓰지 않는다

        if name == "save_plan":
            return {"error": "save_plan 은 사용자 확인 후에만 실행됩니다"}

        return {"error": f"알 수 없는 도구: {name}"}

    except Exception as exc:  # noqa: BLE001 - 도구 하나가 루프를 멈추게 하지 않는다
        return {"error": f"{name} 실행 실패: {exc}"}


def today_iso() -> str:
    return date.today().isoformat()
