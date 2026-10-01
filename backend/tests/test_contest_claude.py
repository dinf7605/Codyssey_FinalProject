"""공모전 제목 추천은 Codyssey Claude 게이트웨이만 사용하고 응답을 검증한다."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from schemas.contest import Contest
from services import contest_claude, llm


CONTEST = Contest(
    id="contest-1", source="wevity", source_id="1", title="대학생 AI 아이디어 공모전",
    host="", fields=[], deadline=None, status="unknown",
    source_url="https://www.wevity.com/?c=find&gbn=view&ix=1",
)


def response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_제목과_태그만_클로드로_보내고_허용된_ID만_반환한다(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = response('```json\n{"matches":[{"id":"contest-1","score":0.84}]}\n```')
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)

    assert contest_claude.score_titles([CONTEST], ["인공지능"]) == {"contest-1": 0.84}
    sent = json.loads(client.messages.create.call_args.kwargs["messages"][0]["content"])
    assert sent == {
        "interests": ["인공지능"],
        "contests": [{"id": "contest-1", "title": "대학생 AI 아이디어 공모전"}],
    }


def test_알수없는_ID와_잘못된_점수는_키워드_폴백으로_넘긴다(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    for text in (
        '{"matches":[{"id":"invented","score":0.9}]}',
        '{"matches":[{"id":"contest-1","score":1.3}]}',
        '공고 없음',
    ):
        client.messages.create.return_value = response(text)
        assert contest_claude.score_titles([CONTEST], ["AI"]) is None


def test_클로드가_정상적으로_관련_공고가_없다고_하면_빈_결과다(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = response('{"matches":[]}')
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    assert contest_claude.score_titles([CONTEST], ["요리"]) == {}


def test_같은_제목과_관심사_요청은_짧게_재사용한다(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = response('{"matches":[{"id":"contest-1","score":0.9}]}')
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    assert contest_claude.score_titles([CONTEST], ["반도체 설계"]) == {"contest-1": 0.9}
    assert contest_claude.score_titles([CONTEST], ["반도체 설계"]) == {"contest-1": 0.9}
    assert client.messages.create.call_count == 1


def test_JSON_뒤에_설명이_붙어도_읽는다(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = response(
        '```json\n{"matches":[{"id":"contest-1","score":0.8}]}\n```\n\nAI 관련 공모전입니다.'
    )
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    assert contest_claude.score_titles([CONTEST], ["설명 붙음"]) == {"contest-1": 0.8}


def test_실제_호출만_기록하고_캐시_재사용은_기록하지_않는다(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = response('{"matches":[{"id":"contest-1","score":0.7}]}')
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    calls = []
    log = lambda source, latency_ms, message: calls.append((source, message))  # noqa: E731

    contest_claude.score_titles([CONTEST], ["기록 확인"], on_call=log)
    contest_claude.score_titles([CONTEST], ["기록 확인"], on_call=log)
    assert calls == [("claude", "")]


def test_게이트웨이_장애도_사유와_함께_기록한다(monkeypatch):
    client = MagicMock()
    client.messages.create.side_effect = TimeoutError("secret-looking detail")
    monkeypatch.setattr(llm, "get_client", lambda timeout: client)
    calls = []

    assert contest_claude.score_titles(
        [CONTEST], ["장애 확인"], on_call=lambda *args: calls.append(args)
    ) is None
    assert [(source, message) for source, _ms, message in calls] == [
        ("fallback", "게이트웨이 오류 (TimeoutError)")
    ]
