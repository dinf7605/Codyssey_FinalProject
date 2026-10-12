"""블록 공부 방법 (10-12) — AI 가 한 단원의 블록들을 한 번에 받아 블록마다 다른 3단계를 만들고, 못 쓰면 규칙 안내로."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from services import study_guide
from tests.fake_supabase import FakeSupabase

ME, OTHER = "user-me", "user-other"
PLAN = "11111111-1111-4111-8111-111111111111"
B1, B2, B3, B4 = (f"2222222{i}-2222-4222-8222-222222222222" for i in range(1, 5))


@pytest.fixture(autouse=True)
def _clear_cache():
    study_guide._cache.clear()
    yield
    study_guide._cache.clear()


def seeded():
    db = FakeSupabase()
    db.table("study_plans").insert({"id": PLAN, "user_id": ME, "goal_title": "SQLD"}).execute()
    for bid, title, start in [
        (B4, "엔터티와 속성", "2026-10-13T19:00:00+09:00"),
        (B1, "데이터 모델링의 이해 (1/3)", "2026-10-12T19:00:00+09:00"),
        (B2, "데이터 모델링의 이해 (2/3)", "2026-10-12T21:10:00+09:00"),
        (B3, "데이터 모델링의 이해 (3/3)", "2026-10-13T10:00:00+09:00"),
    ]:
        db.table("plan_blocks").insert({"id": bid, "plan_id": PLAN, "unit_key": "u", "title": title,
                                        "start_at": start, "end_at": start, "minutes": 120}).execute()
    return db


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(json.loads(kwargs["messages"][0]["content"]))
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def steps(*texts, minutes=(25, 60, 30)):
    return [{"text": t, "minutes": m} for t, m in zip(texts, minutes)]


UNIT = {"blocks": [
    {"part": 1, "steps": steps("모델링의 정의와 목적을 읽고 정리", "개념 · 논리 · 물리 3단계 개요 파악", "단계별 산출물 이름 메모")},
    {"part": 2, "steps": steps("지난 메모로 3단계 되짚기", "단계별 다이어그램 표기법 익히기", "예제 ERD 를 단계별로 따라 그리기")},
    {"part": 3, "steps": steps("1 · 2 블록 요약 다시 읽기", "단원 전체를 한 장으로 정리", "관련 문제 풀고 헷갈린 곳 메모")},
]}
SINGLE = {"blocks": [{"part": 1, "steps": steps("엔터티의 정의와 종류 정리", "속성의 분류를 예시로 익히기", "예제 업무에서 엔터티 · 속성 뽑기")}]}


def test_제목에서_단원과_순서를_나눈다():
    assert study_guide.split_part("데이터 모델링의 이해 (2/3)") == ("데이터 모델링의 이해", 2, 3)
    assert study_guide.split_part("엔터티와 속성") == ("엔터티와 속성", None, None)


def test_한_단원의_블록들을_한_번에_묻고_블록마다_다른_안내를_준다(monkeypatch):
    client = FakeClient(UNIT)
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: client)
    calls = []
    db = seeded()
    out = study_guide.guide_for_block(db, ME, B2, on_call=lambda *a: calls.append(a))

    assert out["source"] == "ai" and out["steps"][2]["text"] == "예제 ERD 를 단계별로 따라 그리기"
    assert sum(s["minutes"] for s in out["steps"]) == 120   # 25+60+30=115 → 가운데가 5분 더 받는다
    assert out["steps"][1]["minutes"] == 65 and "tip" not in out
    assert client.calls[0] == {
        "goal": "SQLD", "unit": "데이터 모델링의 이해", "total": 3,
        "blocks": [{"part": 1, "minutes": 120}, {"part": 2, "minutes": 120}, {"part": 3, "minutes": 120}],
        "prev_unit": None, "next_unit": "엔터티와 속성", "other_units": ["엔터티와 속성"],
    }
    assert calls[0][0] == "claude"

    # 같은 단원의 다른 블록은 이미 받아 둔 안내 — 다시 묻지 않는다
    first = study_guide.guide_for_block(db, ME, B1)
    assert len(client.calls) == 1 and first["steps"][0]["text"] == "모델링의 정의와 목적을 읽고 정리"


def test_순서_표시가_없는_블록은_하나만_묻는다(monkeypatch):
    client = FakeClient(SINGLE)
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: client)
    out = study_guide.guide_for_block(seeded(), ME, B4)
    assert out["source"] == "ai"
    assert client.calls[0]["blocks"] == [{"part": 1, "minutes": 120}] and client.calls[0]["prev_unit"] == "데이터 모델링의 이해"


@pytest.mark.parametrize("reply", [
    "공부 방법은 다음과 같습니다",                                                    # JSON 아님
    {"blocks": UNIT["blocks"][:2]},                                                   # 3번째 블록 빠짐
    {"blocks": [{"part": p, "steps": steps("가" * 100, "b", "c")} for p in (1, 2, 3)]},  # 너무 긴 문장 (90자 넘음)
    {"blocks": [{"part": p, "steps": steps("a", "b", "c", minutes=(100, 100, 100))} for p in (1, 2, 3)]},  # 합을 맞추면 음수
])
def test_쓸_수_없는_응답이면_규칙_안내로_대신한다(monkeypatch, reply):
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: FakeClient(reply))
    calls = []
    assert study_guide.guide_for_block(seeded(), ME, B1, on_call=lambda *a: calls.append(a)) == {"source": "rule"}
    assert calls[0][0] == "fallback"


def test_AI_를_못_쓰면_규칙_안내(monkeypatch):
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: None)   # 키 없음 · 하루 비용 한도
    assert study_guide.guide_for_block(seeded(), ME, B1) == {"source": "rule"}


def test_남의_블록이나_형식이_틀린_id_는_없는_블록(monkeypatch):
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: FakeClient(UNIT))
    db = seeded()
    with pytest.raises(study_guide.BlockNotFound):
        study_guide.guide_for_block(db, OTHER, B1)
    with pytest.raises(study_guide.BlockNotFound):
        study_guide.guide_for_block(db, ME, "blk-temp-1")


def test_API_는_내_블록만_주고_AI_호출을_기록한다(monkeypatch):
    from db import get_db
    from main import app
    from utils.auth import get_current_user

    db = seeded()
    monkeypatch.setattr(study_guide.llm, "get_client", lambda timeout: FakeClient(UNIT))
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=ME, app_metadata={})
    try:
        with TestClient(app) as client:
            ok = client.get(f"/study/guide/{B3}")
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=OTHER, app_metadata={})
            missing = client.get(f"/study/guide/{B3}")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert ok.status_code == 200 and ok.json()["source"] == "ai"
    assert missing.status_code == 404
    logs = db.rows("ai_call_logs")
    assert len(logs) == 1 and logs[0]["feature"] == "study.guide" and logs[0]["user_id"] == ME
