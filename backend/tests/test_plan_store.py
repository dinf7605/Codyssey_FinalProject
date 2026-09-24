"""계획 저장·학습 기록·AI 호출 기록 (담당 C) — 가짜 DB 로 확인한다."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers import plan as plan_router
from schemas.plan import Availability, TimeSlot
from services.plan_store import from_db_time, save_plan, to_db_time
from services.scheduler import build_schedule
from services.template import template_units
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")
OTHER = "00000000-0000-0000-0000-00000000000b"

AVAIL = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
START, DEADLINE = date(2026, 10, 5), date(2026, 12, 20)


def make_plan(goal="SQLD"):
    units = template_units(goal)
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    return {
        "goal_title": goal,
        "goal_id": "cert-sqld",
        "deadline": DEADLINE.isoformat(),
        "source": "template",
        "units": [u.model_dump(mode="json") for u in units],
        "blocks": [b.model_dump(mode="json") for b in blocks],
    }


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 시간 ──────────────────────────────────────────────

def test_한국_시각은_저장했다_꺼내도_같은_시각이다():
    local = datetime(2026, 10, 5, 19, 0)
    stored = to_db_time(local)
    assert stored.endswith("+09:00")
    assert from_db_time(stored) == local
    # DB 가 UTC 로 돌려줘도 한국 시각으로 돌아온다
    assert from_db_time("2026-10-05T10:00:00+00:00") == local


# ── 계획 저장 ─────────────────────────────────────────

def test_계획을_저장하면_단위와_블록이_함께_들어간다(client, db):
    body = make_plan()

    res = client.post("/plan/save", json=body)

    assert res.status_code == 200
    assert len(db.rows("study_plans")) == 1
    assert db.rows("study_plans")[0]["user_id"] == ME.id
    assert len(db.rows("study_units")) == len(body["units"])
    assert len(db.rows("plan_blocks")) == len(body["blocks"]) == res.json()["blocks"]
    assert all(r["start_at"].endswith("+09:00") for r in db.rows("plan_blocks"))


def test_저장한_계획을_그대로_다시_읽는다(client):
    body = make_plan()
    client.post("/plan/save", json=body)

    cur = client.get("/plan/current").json()

    assert cur["goal_title"] == "SQLD"
    assert [u["id"] for u in cur["units"]] == [u["id"] for u in body["units"]]
    assert [b["start"] for b in cur["blocks"]] == [b["start"] for b in body["blocks"]]


def test_같은_목표를_다시_저장하면_이전_계획은_보관된다(client, db):
    client.post("/plan/save", json=make_plan())
    client.post("/plan/save", json=make_plan())

    statuses = sorted(r["status"] for r in db.rows("study_plans"))
    assert statuses == ["active", "archived"]


def test_규칙을_어긴_일정은_저장하지_않는다(client, db):
    body = make_plan()
    body["deadline"] = "2026-10-06"  # 블록 대부분이 마감 뒤로 밀린다

    res = client.post("/plan/save", json=body)

    assert res.status_code == 400
    assert db.rows("study_plans") == []


def test_로그인하지_않으면_저장할_수_없다():
    res = TestClient(app).post("/plan/save", json=make_plan())
    assert res.status_code in (401, 403)


def test_계획이_없으면_null(client):
    assert client.get("/plan/current").json() is None


def test_블록_저장이_실패하면_계획도_남기지_않는다():
    class BrokenBlocks(FakeSupabase):
        def table(self, name):
            q = super().table(name)
            if name == "plan_blocks":
                def broken_insert(_values):
                    raise RuntimeError("네트워크 끊김")
                q.insert = broken_insert
            return q

    db = BrokenBlocks()
    units = template_units("SQLD")
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks

    with pytest.raises(RuntimeError):
        save_plan(db, ME.id, goal_title="SQLD", goal_id="x", deadline=DEADLINE,
                  source="template", units=units, blocks=blocks)

    assert db.rows("study_plans") == []
    assert db.rows("study_units") == []


# ── 학습 기록 ─────────────────────────────────────────

def _first_block_id(client):
    client.post("/plan/save", json=make_plan())
    return client.get("/plan/current").json()["blocks"][0]["id"]


def test_내_블록을_공부하면_기록되고_완료된다(client, db):
    block_id = _first_block_id(client)

    res = client.post("/study/sessions", json={
        "block_id": block_id,
        "started_at": "2026-10-05T19:00:00",
        "ended_at": "2026-10-05T20:12:00",
        "expected_minutes": 60,
    }).json()

    assert res["recorded"] and res["block_done"]
    assert res["minutes"] == 72 and res["deviation_percent"] == 20
    assert len(db.rows("study_sessions")) == 1
    assert next(r for r in db.rows("plan_blocks") if r["id"] == block_id)["done"] is True


def test_남의_블록은_완료_처리하지_않는다(client, db):
    block_id = _first_block_id(client)
    for r in db.rows("study_plans"):
        r["user_id"] = OTHER  # 계획 주인을 다른 사람으로 바꾼다

    res = client.post("/study/sessions", json={
        "block_id": block_id,
        "started_at": "2026-10-05T19:00:00",
        "ended_at": "2026-10-05T19:40:00",
    }).json()

    assert res["recorded"] and not res["block_done"]
    assert db.rows("study_sessions")[0]["block_id"] is None
    assert next(r for r in db.rows("plan_blocks") if r["id"] == block_id)["done"] is False


def test_5분_미만은_저장하지_않는다(client, db):
    res = client.post("/study/sessions", json={
        "started_at": "2026-10-05T19:00:00",
        "ended_at": "2026-10-05T19:03:00",
    }).json()

    assert not res["recorded"]
    assert db.rows("study_sessions") == []


def test_누적_통계는_저장된_기록으로_계산한다(client):
    for start, end in [("2026-09-20T19:00:00", "2026-09-20T21:00:00"),
                       ("2026-09-21T19:00:00", "2026-09-21T19:30:00")]:
        client.post("/study/sessions", json={"started_at": start, "ended_at": end})

    stats = client.get("/study/stats").json()

    assert stats["total_minutes"] == 150
    assert stats["studied_days"] == 2


# ── AI 호출 기록 ───────────────────────────────────────

def test_학습_분해를_부르면_AI_호출이_기록된다(db, monkeypatch):
    monkeypatch.setattr(plan_router, "get_supabase_client", lambda: db)

    res = TestClient(app).post("/plan/decompose", json={"goal_title": "SQLD"})

    assert res.status_code == 200
    (log,) = db.rows("ai_call_logs")
    assert log["feature"] == "plan.decompose"
    assert log["source"] == "template"   # 테스트는 키가 없어 템플릿으로 간다 (conftest)
    assert log["user_id"] is None        # 비로그인도 계획은 만들 수 있다
    assert log["latency_ms"] >= 0


def test_DB가_없어도_학습_분해는_된다(monkeypatch):
    def no_db():
        raise RuntimeError("환경변수가 필요합니다")

    monkeypatch.setattr(plan_router, "get_supabase_client", no_db)

    res = TestClient(app).post("/plan/decompose", json={"goal_title": "SQLD"})

    assert res.status_code == 200
    assert res.json()["units"]


def test_저장_전_블록_id_로_기록해도_오류_없이_자유_학습으로_남는다(client, db):
    # 배치 엔진이 붙인 id 는 uuid 가 아니다 — 실제 DB 는 형식 오류를 내므로 먼저 걸러야 한다
    res = client.post("/study/sessions", json={
        "block_id": "blk-tpl-01-0",
        "started_at": "2026-10-05T19:00:00",
        "ended_at": "2026-10-05T19:30:00",
    })

    assert res.status_code == 200
    assert res.json()["recorded"] and not res.json()["block_done"]
    assert db.rows("study_sessions")[0]["block_id"] is None
