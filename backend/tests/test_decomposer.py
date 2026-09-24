"""학습 분해 에이전트 테스트 — 실제 API 를 부르지 않고 가짜 클라이언트로 확인한다.

실제 Claude 로 돌려본 결과는 backend/README.md 의 실측 표에 있다.
"""

import json
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import plan
from services import decomposer
from services.decomposer import TIMEOUT_MESSAGE, decompose_goal

FINAL_JSON = json.dumps(
    {
        "units": [
            {"id": "u01", "title": "요구사항 확인", "estimated_minutes": 90,
             "prerequisites": [], "estimated": False},
            {"id": "u02", "title": "화면 설계", "estimated_minutes": 60,
             "prerequisites": ["u01"], "estimated": True},
        ]
    },
    ensure_ascii=False,
)


def tool_use(name, args, id_="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


def text(value):
    return SimpleNamespace(type="text", text=value)


class FakeClient:
    """정해 둔 응답을 차례로 돌려주고, 받은 요청을 기록한다."""

    def __init__(self, responses):
        self.messages = self
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class APITimeoutError(Exception):
    """SDK 의 타임아웃 예외와 이름만 같게 만든 가짜."""


def respond(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def test_도구를_쓰고_최종_JSON을_내면_agent_결과가_된다():
    client = FakeClient([
        respond("tool_use", tool_use("search_curriculum",
                                     {"goal_id": "cert-info-eng", "query": "설계", "k": 3})),
        respond("end_turn", text(FINAL_JSON)),
    ])
    events = []

    result = decompose_goal("정보처리기사 필기", "cert-info-eng", client=client,
                            model="m", on_event=events.append)

    assert result.source == "agent"
    assert [u.id for u in result.units] == ["u01", "u02"]
    assert result.tool_calls == 1
    kinds = [e["type"] for e in events]
    assert kinds == ["start", "thinking", "tool", "thinking", "done"]
    assert events[2]["name"] == "search_curriculum"


def test_도구_결과는_한_메시지에_모아서_돌려준다():
    client = FakeClient([
        respond("tool_use",
                tool_use("search_curriculum", {"goal_id": "g", "query": "a", "k": 1}, "t1"),
                tool_use("search_curriculum", {"goal_id": "g", "query": "b", "k": 1}, "t2")),
        respond("end_turn", text(FINAL_JSON)),
    ])

    decompose_goal("목표", "g", client=client, model="m")

    last_user = client.calls[1]["messages"][-1]
    assert last_user["role"] == "user"
    assert [r["tool_use_id"] for r in last_user["content"]] == ["t1", "t2"]


def test_save_plan은_실행하지_않고_확인을_요청한다():
    client = FakeClient([
        respond("tool_use", tool_use("save_plan", {"goal_id": "g", "block_count": 3})),
        respond("end_turn", text(FINAL_JSON)),
    ])

    decompose_goal("목표", "g", client=client, model="m")

    returned = json.loads(client.calls[1]["messages"][-1]["content"][0]["content"])
    assert returned["status"] == "confirmation_required"


def test_오늘_날짜를_프롬프트에_넣는다():
    # 실측에서 모델이 2024~2025년 날짜로 빈 시간을 조회했다 — 오늘을 모르기 때문이다
    client = FakeClient([respond("end_turn", text(FINAL_JSON))])

    decompose_goal("목표", "g", client=client, model="m", today=date(2026, 9, 24))

    assert "오늘 날짜: 2026-09-24" in client.calls[0]["messages"][0]["content"]


def test_각_호출에는_남은_시간만_준다():
    client = FakeClient([
        respond("tool_use", tool_use("search_curriculum", {"goal_id": "g", "query": "a", "k": 1})),
        respond("end_turn", text(FINAL_JSON)),
    ])

    decompose_goal("목표", "g", client=client, model="m", budget_seconds=60)

    first, second = (c["timeout"] for c in client.calls)
    assert 0 < second <= first <= 60


def test_타임아웃이면_템플릿으로_대체하고_안내한다():
    client = FakeClient([APITimeoutError("느림")])
    events = []

    result = decompose_goal("정보처리기사 필기", "g", client=client, model="m",
                            on_event=events.append)

    assert result.source == "template"
    assert result.message == TIMEOUT_MESSAGE
    assert result.units  # 일정은 항상 만들어진다
    assert events[-1]["type"] == "fallback"


def test_예산이_바닥나면_API를_부르지_않는다():
    client = FakeClient([])

    result = decompose_goal("목표", "g", client=client, model="m", budget_seconds=1)

    assert result.source == "template"
    assert client.calls == []


def test_스키마가_틀리면_1회_재시도하고_partial이_된다():
    bad = json.dumps({"units": [{"id": "u01", "title": "너무 김", "estimated_minutes": 500}]})
    client = FakeClient([
        respond("end_turn", text(bad)),
        respond("end_turn", text(FINAL_JSON)),
    ])

    result = decompose_goal("목표", "g", client=client, model="m")

    assert result.source == "partial"
    assert len(client.calls) == 2
    assert "tools" not in client.calls[1]  # 재시도에서는 도구를 주지 않는다


def test_반복_상한을_넘기면_더_부르지_않는다():
    loop = [respond("tool_use", tool_use("search_curriculum",
                                         {"goal_id": "g", "query": "a", "k": 1}))
            for _ in range(decomposer.MAX_TOOL_ITERATIONS)]
    client = FakeClient(loop + [respond("end_turn", text("JSON 아님"))])

    result = decompose_goal("목표", "g", client=client, model="m")

    assert len(client.calls) == decomposer.MAX_TOOL_ITERATIONS + 1  # 상한 + 재시도 1회
    assert result.source == "template"


def test_API_키가_없으면_바로_템플릿(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = decompose_goal("SQLD", "cert-sqld")

    assert result.source == "template"
    assert "API 키" in result.message


def test_스트림은_진행_이벤트_뒤에_결과를_마지막_줄로_보낸다(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(plan.router)

    res = TestClient(app).post("/plan/decompose/stream", json={"goal_title": "SQLD"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in res.text.strip().splitlines()]
    assert lines[0]["type"] == "start"
    assert lines[-1]["type"] == "result"
    assert lines[-1]["result"]["source"] == "template"
    assert lines[-1]["result"]["units"]
