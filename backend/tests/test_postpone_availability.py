"""알림에서 미루기 (FR-ALARM-03) · 공부 가능 시간 바꾸기 (FR-MY-01) — 가짜 DB 로 확인한다."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db import get_db
from main import app
from schemas.plan import Availability, TimeSlot
from services import replan
from services.plan_store import active_plan_row, plan_blocks, plan_units, save_plan
from services.scheduler import build_schedule
from services.template import template_units
from services.validator import validate_schedule
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")
AVAIL = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
START, DEADLINE = date(2026, 10, 5), date(2026, 12, 20)   # 10-05 는 월요일
NOW = datetime(2026, 10, 5, 18, 50)                     # 첫 블록 10분 전


@pytest.fixture
def db():
    db = FakeSupabase()
    units = template_units("SQLD")  # tpl-01 → tpl-02 → … 선행 사슬
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    save_plan(db, ME.id, goal_title="SQLD", goal_id="cert-sqld", deadline=DEADLINE,
              source="template", units=units, blocks=blocks, availability=AVAIL)
    return db


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: NOW)
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def plan_of(db):
    return active_plan_row(db, ME.id)


def blocks_by_unit(db):
    return {b.unit_id: b for b in plan_blocks(db, plan_of(db)["id"])}


def no_violations(db):
    plan = plan_of(db)
    return validate_schedule(plan_blocks(db, plan["id"]), plan_units(db, plan["id"]), DEADLINE) == []


# ── 미루기 ────────────────────────────────────────────

def test_미루면_다음_날_이후로_가고_뒤_단원도_순서대로_밀린다(client, db):
    first = blocks_by_unit(db)["tpl-01"]

    res = client.post(f"/plan/blocks/{first.id}/postpone")

    assert res.status_code == 200 and res.json()["applied"] is True
    after = blocks_by_unit(db)
    assert after["tpl-01"].start.date() > first.start.date()
    assert after["tpl-02"].start >= after["tpl-01"].end, "앞 단원보다 뒤에 와야 한다"
    assert no_violations(db)
    reasons = [r["reason"] for r in db.rows("plan_changes")]
    assert any(r.startswith("알림에서 미뤄") for r in reasons)


def test_완료한_블록과_남의_블록은_미룰_수_없다(client, db):
    first = blocks_by_unit(db)["tpl-01"]
    db.table("plan_blocks").update({"done": True}).eq("id", first.id).execute()
    assert client.post(f"/plan/blocks/{first.id}/postpone").status_code == 409
    assert client.post("/plan/blocks/not-mine/postpone").status_code == 404


def test_직접_옮긴_블록은_미루기에도_그대로다(client, db):
    blocks = blocks_by_unit(db)
    db.table("plan_blocks").update({"locked": True}).eq("id", blocks["tpl-10"].id).execute()
    assert client.post(f"/plan/blocks/{blocks['tpl-01'].id}/postpone").status_code in (200, 409)
    assert blocks_by_unit(db)["tpl-10"].start == blocks["tpl-10"].start


# ── 공부 가능 시간 바꾸기 ─────────────────────────────

WEEKEND = {"slots": [{"weekday": d, "start": "09:00", "end": "13:00"} for d in (5, 6)], "rest_weekday": None}


def test_가용_시간을_바꾸면_앞으로의_블록이_새_시간에_놓인다(client, db):
    res = client.put(f"/plan/{plan_of(db)['id']}/availability", json=WEEKEND)

    assert res.status_code == 200, res.json()
    assert res.json()["moved"] > 0
    blocks = plan_blocks(db, plan_of(db)["id"])
    assert all(b.start.weekday() in (5, 6) and b.start.hour >= 9 for b in blocks)
    assert plan_of(db)["availability"]["slots"][0]["start"] == "09:00"
    assert no_violations(db)


def test_완료한_블록은_가용_시간을_바꿔도_그대로다(client, db):
    first = blocks_by_unit(db)["tpl-01"]
    db.table("plan_blocks").update({"done": True}).eq("id", first.id).execute()

    client.put(f"/plan/{plan_of(db)['id']}/availability", json=WEEKEND)

    assert blocks_by_unit(db)["tpl-01"].start == first.start


def test_너무_적은_시간이면_아무것도_바꾸지_않는다(client, db):
    before = {b.id: b.start for b in plan_blocks(db, plan_of(db)["id"])}
    tiny = {"slots": [{"weekday": 0, "start": "07:00", "end": "07:30"}], "rest_weekday": None}

    res = client.put(f"/plan/{plan_of(db)['id']}/availability", json=tiny)

    assert res.status_code == 409
    assert {b.id: b.start for b in plan_blocks(db, plan_of(db)["id"])} == before
    assert plan_of(db)["availability"]["slots"][0]["start"] == "19:00"


def test_빈_시간표와_남의_계획은_거절한다(client, db):
    assert client.put(f"/plan/{plan_of(db)['id']}/availability", json={"slots": []}).status_code == 409
    assert client.put("/plan/not-mine/availability", json={"slots": [
        {"weekday": 0, "start": "19:00", "end": "22:00"}]}).status_code == 404
