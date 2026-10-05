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
import logging
import re
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
from services import llm
from services.ai_request_metrics import track_decomposition, tracked_create
from services.agent_tools import CONFIRM_REQUIRED, TOOL_SCHEMAS, run_tool
from services.template import template_units

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5     # AI기능명세 2
LLM_BUDGET_SECONDS = 60     # NFR-PERF-01 — 에이전트 전체에 주는 시간
MIN_CALL_SECONDS = 5        # 남은 시간이 이보다 적으면 호출해도 답이 안 온다
MAX_TOKENS = 4096

TIMEOUT_MESSAGE = "시간이 걸려 기본 계획으로 시작합니다."

SYSTEM_PROMPT = """너는 학습 계획을 세우는 커리큘럼 설계자다.

역할
  주어진 목표를 공부할 수 있는 단위로 쪼갠다.

지켜야 할 것
  - 단위는 하나의 공부 주제다. 각 단위는 30분 이상 600분 이하로 만든다
  - 120분이 넘는 단위는 배치할 때 120분 이하 블록 여러 개로 나뉜다. 같은 주제를 여러 번 앉아서
    공부해야 하면(기출 반복, 파트별 문제 풀이 등) 단위를 잘게 쪼개지 말고 estimated_minutes 를 늘린다
  - 사용자가 "목표 표준 학습시간"을 알려주면 단위 estimated_minutes 의 합을 그 시간에 맞춘다
  - 앞 단위를 끝내야 할 수 있는 것은 prerequisites 에 적는다
  - search_curriculum 으로 찾은 범위 안에서 만든다
  - 검색 범위 밖의 내용을 넣어야 하면 그 단위의 estimated 를 true 로 표시한다
  - 단위는 최대 25개. 짧은 항목은 같은 과목끼리만, 묶은 항목의 minutes 합이 600 이하일 때만 한 단위로 묶는다
  - title 은 30자 이내로 짧게 쓴다. 여러 항목을 묶었으면 '관계·조인·식별자'처럼 핵심어만 이어 쓴다
  - 커리큘럼 minutes 는 한 번 앉아서 공부할 시간이다. 표준 학습시간이 더 크면 반복·문제 풀이로 늘려 맞춘다.
    estimate_effort 는 커리큘럼에 없는 단위에만 쓴다
  - 첫 턴에 search_curriculum 과 get_available_slots 를 함께 부른다
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

    설명을 덧붙이지 말라고 해도 가끔 붙는다 — 실측(10-01)에서는 매번 JSON 앞에 마크다운 설명을 길게 썼다.
    '{' 마다 JSON 객체를 읽어 보고, "units" 가 든 객체를 답으로 고른다. 없으면 처음 읽힌 객체.
    예전엔 첫 '{' ~ 마지막 '}' 를 잘라 읽어서, 설명에 중괄호가 섞이면 멀쩡한 답을 버리고
    재시도(20초 이상)로 넘어갔다.
    """
    text = text or ""
    first = None
    start = text.find("{")
    while start != -1:
        try:
            obj, end = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            if "units" in obj:
                return obj
            first = first or obj
        start = text.find("{", start + end)
    return first


TITLE_MAX = 30
_TRAILING_NOTE = re.compile(r"\s*\([^()]*\)\s*$")


def short_title(title: str) -> str:
    """묶은 단위 이름을 화면에 맞게 줄인다.

    모델이 항목을 묶으며 "관계와 조인의 이해 + Null 속성의 이해 + 본질식별자와 인조식별자 (개념 반복 포함)"처럼
    이어 붙여, 일정 화면에서 무엇을 하는 블록인지 한눈에 안 들어왔다 (10-05 사전 점검 12번).
    길면 끝의 괄호 설명을 떼고 '+' 를 '·' 로, 그래도 길면 앞의 두 주제 + '외 N개'.
    """
    title = " ".join(str(title).split())
    if len(title) <= TITLE_MAX:
        return title.replace(" + ", "·")
    title = _TRAILING_NOTE.sub("", title)
    parts = [p.strip() for p in title.split("+") if p.strip()]
    joined = "·".join(parts)
    if len(joined) <= TITLE_MAX or len(parts) <= 2:
        return joined
    return f"{'·'.join(parts[:2])} 외 {len(parts) - 2}개"


def parse_units(payload: dict) -> list[StudyUnit]:
    """고정 스키마로 검증한다. 하나라도 어긋나면 예외가 난다."""
    raw = payload.get("units")
    if not isinstance(raw, list) or not raw:
        raise ValueError("units 배열이 비어 있습니다")
    return [StudyUnit(**{**item, "title": short_title(item.get("title", ""))}) for item in raw]


def standard_minutes(goal_title: str) -> int | None:
    """카탈로그의 표준 학습시간(분). 카탈로그에 없는 목표(공모전·직접 입력)는 None.

    이게 없으면 AI 가 단위를 얼마나 크게 잡을지 기준이 없어, 토익 900+(표준 100시간)를
    24시간짜리 계획으로 만들었다 (10-02 실사용).
    """
    from services.goal_catalog import find_by_title  # goal_catalog 는 llm 을 쓰지 않는다 — 가볍다

    found = find_by_title(goal_title)
    return found.standard_hours * 60 if found and found.standard_hours > 0 else None


def _is_timeout(exc: Exception) -> bool:
    return "Timeout" in type(exc).__name__


_text_of = llm.text_of


@track_decomposition
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
    model = model or llm.model("main")
    today = today or date.today()
    emit = on_event or (lambda _event: None)
    deadline = time.monotonic() + budget_seconds

    def fallback(message: str, tool_calls: int = 0) -> DecomposeResult:
        emit({"type": "fallback", "message": message})
        return DecomposeResult(
            units=template_units(goal_title, target_minutes=standard_minutes(goal_title)),
            source="template",
            message=message,
            tool_calls=tool_calls,
        )

    emit({"type": "start", "budget_seconds": budget_seconds})

    if client is None:
        # 게이트웨이 주소·재시도 끄기는 llm.get_client 가 맡는다. 시간은 호출마다 따로 준다.
        client = llm.get_client(timeout=budget_seconds)
        if client is None:
            return fallback("API 키가 없어 표준 커리큘럼으로 시작합니다.")

    slot_text = "정보 없음"
    if availability and availability.slots:
        slot_text = ", ".join(
            f"{'월화수목금토일'[s.weekday]} {s.start}~{s.end}" for s in availability.slots
        )

    target = standard_minutes(goal_title)
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"오늘 날짜: {today.isoformat()}\n"
                f"목표: {goal_title} (goal_id: {goal_id})\n"
                f"주간 가용 시간: {slot_text}\n"
                + (f"목표 표준 학습시간: 약 {target // 60}시간 — 단위 시간의 합을 여기에 맞춰 주세요.\n" if target else "")
                + f"단위는 {MIN_UNIT_MINUTES}~{MAX_UNIT_MINUTES}분으로 만들어 주세요 (120분이 넘으면 블록 여러 개로 나눠 놓습니다)."
            ),
        }
    ]

    tool_calls = 0
    exhausted = True  # 반복 상한까지 도구만 불렀다 (False 면 최종 답의 형식이 틀렸다)

    for step in range(1, MAX_TOOL_ITERATIONS + 1):
        remaining = deadline - time.monotonic()
        if remaining < MIN_CALL_SECONDS:
            return fallback(TIMEOUT_MESSAGE, tool_calls)

        emit({"type": "thinking", "step": step})
        try:
            response = tracked_create(client,
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
                except Exception as exc:  # noqa: BLE001 - 아래 재시도 1회로 넘어간다
                    # 재시도는 20초 넘게 든다 — 무엇이 틀렸는지 남겨야 프롬프트를 고칠 수 있다 (응답 본문은 남기지 않는다)
                    logger.warning("학습 분해 응답이 형식에 맞지 않아 재시도: %s", str(exc)[:300])
            else:
                logger.warning("학습 분해 응답에서 JSON 을 찾지 못해 재시도 (stop_reason=%s)", response.stop_reason)
            exhausted = False
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
                output = run_tool(
                    block.name, block.input or {},
                    {"availability": availability, "goal_id": goal_id, "goal_title": goal_title},
                )

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
        retry = _retry_once(client, model, messages, tool_calls, remaining, exhausted)
        if retry is not None:
            emit({"type": "done", "source": "partial"})
            return retry
        return fallback("자동 생성에 실패해 기본 계획으로 시작합니다.", tool_calls)

    return fallback(TIMEOUT_MESSAGE, tool_calls)


def _retry_once(
    client, model: str, messages: list[dict], tool_calls: int, timeout: float, exhausted: bool = True
):
    """도구 없이 한 번만 더 물어본다 (AI기능명세 6: 동일 프롬프트로 1회 재시도)."""
    try:
        response = tracked_create(client,
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
                # 반복 상한에 걸렸으면 정말 중간 결과다(기획서: '일부만 생성됨').
                # 형식만 틀렸던 거면 두 번째 응답으로 만든 온전한 계획이다 — '일부만'이라 쓰면 빠진 걸 찾게 된다
                message=(
                    "일부만 생성되어 중간 결과로 계획을 만들었습니다."
                    if exhausted
                    else "AI 응답을 한 번 더 받아 만든 계획입니다. 학습 단위를 한 번 훑어봐 주세요."
                ),
                tool_calls=tool_calls,
            )
    except Exception:  # noqa: BLE001
        pass
    return None
