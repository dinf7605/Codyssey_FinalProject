"""목표 카탈로그 RAG ① — Claude 관련성 검색과 태그 검색 대체 경로."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app
from services import goal_claude, llm
from services.goal_catalog import search_catalog_ai
from services.goal_limiter import _reset_for_tests

ITEMS = [
    {"goal_id": "cert-sqld", "title": "SQLD (SQL 개발자)", "field": "데이터", "tags": ["sqld", "sql"]},
    {"goal_id": "cert-adsp", "title": "ADsP", "field": "데이터", "tags": ["adsp", "통계"]},
]


def setup_function():
    _reset_for_tests()


def response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def fake_client(monkeypatch, text):
    client = MagicMock()
    client.messages.create.return_value = response(text)
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    return client


def test_카탈로그_문서와_관심사만_보내고_허용된_ID만_받는다(monkeypatch):
    client = fake_client(monkeypatch, '```json\n{"matches":[{"id":"cert-sqld","score":0.9}]}\n```')
    assert goal_claude.score_catalog(ITEMS, ["데이터 다루는 일"]) == {"cert-sqld": 0.9}
    sent = json.loads(client.messages.create.call_args.kwargs["messages"][0]["content"])
    assert sent["interests"] == ["데이터 다루는 일"]
    assert [doc["id"] for doc in sent["catalog"]] == ["cert-sqld", "cert-adsp"]


def test_지어낸_목표나_범위_밖_점수는_응답_전체를_버린다(monkeypatch):
    for text in (
        '{"matches":[{"id":"cert-invented","score":0.9}]}',
        '{"matches":[{"id":"cert-sqld","score":1.5}]}',
        '{"matches":[{"id":"cert-sqld","score":true}]}',
        '추천할 목표가 없습니다',
    ):
        fake_client(monkeypatch, text)
        assert goal_claude.score_catalog(ITEMS, [f"검증 {text}"]) is None


def test_JSON_뒤에_설명이_붙어도_읽는다(monkeypatch):
    # 09-29 실측 — 관련 목표가 없을 때 Haiku 가 코드블록 뒤에 이유를 덧붙였다
    fake_client(monkeypatch, '```json\n{\n  "matches": []\n}\n```\n\n요리와 관련된 목표가 없습니다.')
    assert goal_claude.score_catalog(ITEMS, ["요리 설명 붙음"]) == {}


def test_실제_호출만_기록한다(monkeypatch):
    client = fake_client(monkeypatch, '{"matches":[]}')
    calls = []
    for _ in range(2):
        goal_claude.score_catalog(ITEMS, ["요리"], on_call=lambda *args: calls.append(args[0]))
    assert calls == ["claude"]  # 두 번째는 캐시
    assert client.messages.create.call_count == 1


def test_키가_없으면_태그_검색으로_대신한다():
    # conftest 가 ANTHROPIC_API_KEY 를 지운다
    candidates, method = search_catalog_ai(["SQLD"])
    assert method == "tags"
    assert candidates[0].goal_id == "cert-sqld"


def test_태그와_글자가_안_겹쳐도_의미로_찾는다(monkeypatch):
    fake_client(monkeypatch, '{"matches":[{"id":"cert-sqld","score":0.82},{"id":"cert-adsp","score":0.4}]}')
    candidates, method = search_catalog_ai(["데이터베이스 공부"])
    assert method == "claude"
    assert [(c.goal_id, c.similarity) for c in candidates] == [("cert-sqld", 0.82), ("cert-adsp", 0.4)]


def test_추천_API는_검색_방식을_알려준다(monkeypatch):
    fake_client(monkeypatch, '{"matches":[{"id":"cert-sqld","score":0.9}]}')
    res = TestClient(app).post(
        "/goal/recommend",
        json={"tags": ["쿼리 짜는 법"], "weekly_hours": 10, "session_id": "rag-1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["search_method"] == "claude"
    assert body["query_used"] == "tags"
    assert body["candidates"][0]["goal_id"] == "cert-sqld"


def test_기준_아래_점수만_오면_인기_목록으로_대체한다(monkeypatch):
    fake_client(monkeypatch, '{"matches":[{"id":"cert-adsp","score":0.3}]}')
    res = TestClient(app).post("/goal/match", json={"tags": ["애매한 관심사"], "session_id": "rag-2", "k": 5})
    body = res.json()
    assert (body["search_method"], body["query_used"]) == ("claude", "fallback_popular")
