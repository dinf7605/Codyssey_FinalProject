"""학습 분해 에이전트 (FR-PLAN-02) — 이 프로젝트에서 AI Agent 를 쓰는 유일한 곳.

돌아가는 방식
  1. 목표와 제약을 주고 Claude 에게 묻는다
  2. Claude 가 도구를 부르면 실행해서 결과를 돌려준다
  3. 2번을 최대 5회까지 반복한다
  4. 최종 답을 고정 JSON 스키마로 검증한다

왜 상한이 5회인가 (AI기능명세 2)
  3회로는 "커리큘럼 검색 -> 소요시간 추정 -> 배치" 연계가 끊겼고,
  8회 이상은 결과 차이 없이 비용만 늘었다.
  상한이 없는 에이전트 루프는 API 비용 사고의 1순위 원인이다.

왜 시간 제한이 호출당이 아니라 전체 60초인가 (NFR-PERF-01)
  실측(claude-sonnet-4, Codyssey 게이트웨이): 도구 호출 3회 + 최종 답 1회에 약 41초.
  최종 JSON 을 쓰는 호출 하나만 24초가 걸려 호출당 20초로는 거의 항상 실패했다.
  게다가 SDK 가 타임아웃 때 스스로 2번 재시도해서 사용자는 2분 넘게 기다렸다.
  그래서 SDK 재시도를 끄고, 남은 예산만큼만 각 호출에 준다.

실패하면 어떻게 되나 (AI기능명세 6)
  타임아웃 / 스키마 검증 실패 / 도구 상한 초과 —
  어느 경우든 표준 커리큘럼 템플릿으로 대체한다. 일정은 항상 만들어진다.

진행 표시
  on_event 를 넘기면 실제로 일어난 일(도구 호출 등)을 그때그때 알려준다.
  화면은 이걸 받아 "커리큘럼 찾는 중" 같은 단계를 보여준다 — 가짜 타이머가 아니다.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from typing import Callable

from schemas.plan import (
    MAX_UNIT_MINUTES,
    MIN_UNIT_MINUTES,
    Availability,
    DecomposeResult,
    StudyUnit,
)
from services.agent_tools import CONFIRM_REQUIRED, TOOL_SCHEMAS, run_tool
from services.template import template_units

MAX_TOOL_ITERATIONS = 5     # AI기능명세 2
LLM_BUDGET_SECONDS = 60     # NFR-PERF-01 — 에이전트 전체에 주는 시간
MIN_CALL_SECONDS = 5        # 남은 시간이 이보다 적으면 호출해도 답이 안 온다
MAX_TOKENS = 4096
DEFAULT_MODEL = "claude-sonnet-4"  # Codyssey 게이트웨이의 모델 이름 (날짜 없는 형태)

TIMEOUT_MESSAGE = "시간이 걸려 기본 계획으로 시작합니다."

SYSTEM_PROMPT = """너는 학습 계획을 세우는 커리큘럼 설계자다.

역할
  주어진 목표를 공부할 수 있는 단위로 쪼갠다.

지켜야 할 것
  - 각 단위는 30분 이상 120분 이하로 만든다
  - 앞 단위를 끝내야 할 수 있는 것은 prerequisites 에 적는다
  - search_curriculum 으로 찾은 범위 안에서 만든다
  - 검색 범위 밖의 내용을 넣어야 하면 그 단위의 estimated 를 true 로 표시한다
  - 모르는 것을 아는 것처럼 쓰지 않는다
  - 날짜가 필요하면 사용자가 알려준 오늘 날짜를 기준으로 한다

끝낼 때
  도구를 더 부르지 말고, 아래 형식의 JSON 만 출력한다. 설명 문장을 붙이지 않는다.

  {"units": [
    {"id": "u01", "title": "...", "estimated_minutes": 90,
     "prerequisites": [], "estimated": false}
  ]}
"""

EventHandler = Callable[[dict], None]


def _extract_json(text: str) -> dict | None:
    """모델 응답에서 JSON 을 꺼낸다.

    설명을 덧붙이지 말라고 해도 가끔 붙는다. 중괄호 구간만 잘라 본다.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def parse_units(payload: dict) -> list[StudyUnit]:
    """고정 스키마로 검증한다. 하나라도 어긋나면 예외가 난다."""
    raw = payload.get("units")
    if not isinstance(raw, list) or not raw:
        raise ValueError("units 배열이 비어 있습니다")
    return [StudyUnit(**item) for item in raw]


def _is_timeout(exc: Exception) -> bool:
    return "Timeout" in type(exc).__name__


def _text_of(response) -> str:
    return "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
    )


def decompose_goal(
    goal_title: str,
    goal_id: str,
    availability: Availability | None = None,
    client=None,
    model: str | None = None,
    today: date | None = None,
    on_event: EventHandler | None = None,
    budget_seconds: float = LLM_BUDGET_SECONDS,
) -> DecomposeResult:
    """목표를 학습 단위로 쪼갠다.

    client 를 넘기지 않으면 환경변수로 Anthropic 클라이언트를 만든다.
    키가 없으면 API 를 부르지 않고 바로 템플릿으로 간다 — 로컬 개발에서 편하다.
    """
    model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
    today = today or date.today()
    emit = on_event or (lambda _event: None)
    deadline = time.monotonic() + budget_seconds

    def fallback(message: str, tool_calls: int = 0) -> DecomposeResult:
        emit({"type": "fallback", "message": message})
        return DecomposeResult(
            units=template_units(goal_title),
            source="template",
            message=message,
            tool_calls=tool_calls,
        )

    emit({"type": "start", "budget_seconds": budget_seconds})

    if client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return fallback("API 키가 없어 표준 커리큘럼으로 시작합니다.")
        try:
            import anthropic

            # 재시도는 SDK 가 아니라 우리가 정한다 (AI기능명세 6: 1회만)
            client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        except Exception as exc:  # noqa: BLE001
            return fallback(f"AI 호출을 준비하지 못했습니다: {exc}")

    slot_text = "정보 없음"
    if availability and availability.slots:
        slot_text = ", ".join(
            f"{'월화수목금토일'[s.weekday]} {s.start}~{s.end}" for s in availability.slots
        )

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"오늘 날짜: {today.isoformat()}\n"
                f"목표: {goal_title} (goal_id: {goal_id})\n"
                f"주간 가용 시간: {slot_text}\n"
                f"단위는 {MIN_UNIT_MINUTES}~{MAX_UNIT_MINUTES}분으로 쪼개 주세요."
            ),
        }
    ]

    tool_calls = 0

    for step in range(1, MAX_TOOL_ITERATIONS + 1):
        remaining = deadline - time.monotonic()
        if remaining < MIN_CALL_SECONDS:
            return fallback(TIMEOUT_MESSAGE, tool_calls)

        emit({"type": "thinking", "step": step})
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=messages,
                timeout=remaining,
            )
        except Exception as exc:  # 타임아웃·네트워크·요금 한도 등
            if _is_timeout(exc):
                return fallback(TIMEOUT_MESSAGE, tool_calls)
            return fallback(
                f"AI 응답을 받지 못해 기본 계획으로 시작합니다. ({type(exc).__name__})",
                tool_calls,
            )

        if response.stop_reason != "tool_use":
            # 도구를 더 쓰지 않겠다는 뜻 — 최종 답을 파싱한다
            payload = _extract_json(_text_of(response))
            if payload:
                try:
                    result = DecomposeResult(
                        units=parse_units(payload), source="agent", tool_calls=tool_calls
                    )
                    emit({"type": "done", "source": "agent"})
                    return result
                except Exception:  # noqa: BLE001 - 아래 재시도 1회로 넘어간다
                    pass
            break

        # 도구 호출 처리
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            tool_calls += 1
            emit({"type": "tool", "name": block.name})

            if block.name in CONFIRM_REQUIRED:
                # 되돌리기 어려운 동작은 에이전트가 실행하지 않는다 (AI기능명세 2)
                output = {"status": "confirmation_required", "message": "사용자 확인이 필요합니다."}
            else:
                output = run_tool(block.name, block.input or {})

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, ensure_ascii=False),
                }
            )

        # 병렬 호출 결과는 반드시 한 메시지에 모아서 돌려준다
        messages.append({"role": "user", "content": results})

    # 여기까지 왔다 = 스키마 검증 실패 또는 반복 상한 초과. 명세대로 1회만 더 시도한다.
    remaining = deadline - time.monotonic()
    if remaining >= MIN_CALL_SECONDS:
        emit({"type": "retry"})
        retry = _retry_once(client, model, messages, tool_calls, remaining)
        if retry is not None:
            emit({"type": "done", "source": "partial"})
            return retry
        return fallback("자동 생성에 실패해 기본 계획으로 시작합니다.", tool_calls)

    return fallback(TIMEOUT_MESSAGE, tool_calls)


def _retry_once(client, model: str, messages: list[dict], tool_calls: int, timeout: float):
    """도구 없이 한 번만 더 물어본다 (AI기능명세 6: 동일 프롬프트로 1회 재시도)."""
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages
            + [{"role": "user", "content": "도구를 더 쓰지 말고 JSON 만 출력해 주세요."}],
            timeout=timeout,
        )
        payload = _extract_json(_text_of(response))
        if payload:
            return DecomposeResult(
                units=parse_units(payload),
                source="partial",
                message="일부만 생성되어 중간 결과로 계획을 만들었습니다.",
                tool_calls=tool_calls,
            )
    except Exception:  # noqa: BLE001
        pass
    return None
