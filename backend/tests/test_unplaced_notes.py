"""미배치 단위 표시·넣기 (FR-PLAN-04) · 학습 메모 모아보기 (FR-STUDY-05) — 담당 C."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from db import get_db
from main import app
from services import replan
from services.plan_store import (
    active_plan_rows,
    archive_plan,
    other_plan_blocks,
    plan_blocks,
    record_session,
    save_plan,
)
from services.scheduler import build_schedule
from services.template import template_units
from tests.fake_supabase import FakeSupabase
from tests.test_multiplan import AVAIL, DEADLINE, ME, START, all_blocks, no_clash, save
from utils.auth import get_current_user

NOW = datetime(2026, 10, 4, 12, 0)  # 첫 블록(10/5 월) 전날


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def save_partial(db, goal="SQLD", keep=3, deadline=DEADLINE):
    """앞 단위 몇 개만 놓인 계획 — 나머지는 미배치."""
    units = template_units(goal)
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks[:keep]
    plan_id = save_plan(db, ME.id, goal_title=goal, goal_id=goal, deadline=deadline,
                        source="template", units=units, blocks=blocks, availability=AVAIL)
    return plan_id, units, blocks


def active_plan(client, plan_id):
    return next(p for p in client.get("/plan/active").json()["plans"] if p["plan_id"] == plan_id)


# ── 미배치 표시 ────────────────────────────────────────

def test_블록이_없는_단위를_미배치로_돌려준다(client, db):
    plan_id, units, blocks = save_partial(db)

    plan = active_plan(client, plan_id)

    placed = {b.unit_id for b in blocks}
    assert [u["id"] for u in plan["unplaced"]] == [u.id for u in units if u.id not in placed]


def test_다_놓인_계획은_미배치가_없다(client, db):
    plan_id = save(db, "SQLD")
    assert active_plan(client, plan_id)["unplaced"] == []


def test_직접_지운_단위는_미배치로_보이지_않는다(client, db):
    plan_id = save(db, "SQLD")
    target = plan_blocks(db, plan_id)[-1]

    assert client.delete(f"/plan/blocks/{target.id}").status_code == 204

    assert active_plan(client, plan_id)["unplaced"] == []
    unit = next(r for r in db.rows("study_units") if r["unit_key"] == target.unit_id)
    assert unit["removed_at"], "마지막 블록을 지우면 단위에 지운 시각을 남긴다"


# ── 미배치 넣기 ────────────────────────────────────────

def test_미배치_단위를_빈_시간에_넣고_기록한다(client, db):
    plan_id, units, _ = save_partial(db)
    waiting = len(units) - 3

    res = replan.place_unplaced(db, ME.id, plan_id, NOW)

    assert (res["placed"], res["left"]) == (waiting, 0)
    assert active_plan(client, plan_id)["unplaced"] == []
    assert no_clash(all_blocks(db)) == []
    adds = [r for r in db.rows("plan_changes") if r["change_type"] == "add"]
    assert len(adds) == waiting and all(r["origin"] == "manual" for r in adds)
    assert all(r["block_id"] for r in adds), "변경 내역이 새 블록을 가리킨다"


def test_넣을_때_이미_놓인_블록은_움직이지_않는다(db):
    plan_id, _, _ = save_partial(db)
    before = {(b.id, b.start) for b in plan_blocks(db, plan_id)}

    replan.place_unplaced(db, ME.id, plan_id, NOW)

    after = {(b.id, b.start) for b in plan_blocks(db, plan_id)}
    assert before <= after


def test_다른_목표_블록을_피해서_넣는다(db):
    first, _, _ = save_partial(db, "SQLD")
    # 두 번째 목표는 저장 규칙대로 첫 목표를 피해, 첫 목표가 비워 둔 저녁부터 차지한다
    fixed = other_plan_blocks(db, ME.id)
    units = template_units("정보처리기사")
    second = [b for b in build_schedule(units, AVAIL, START, DEADLINE, fixed_blocks=fixed).blocks
              if b.unit_id in {u.id for u in units}]
    save(db, "정보처리기사", blocks=second, units=units)
    assert no_clash(all_blocks(db)) == []

    res = replan.place_unplaced(db, ME.id, first, NOW)

    assert res["placed"] > 0
    assert no_clash(all_blocks(db)) == []


def test_지운_단위는_도로_넣지_않는다(client, db):
    plan_id = save(db, "SQLD")
    target = plan_blocks(db, plan_id)[-1]
    client.delete(f"/plan/blocks/{target.id}")

    res = replan.place_unplaced(db, ME.id, plan_id, NOW)

    assert res == {"placed": 0, "left": 0, "blocks": []}
    assert target.unit_id not in {b.unit_id for b in plan_blocks(db, plan_id)}


def test_자리가_없으면_미배치로_남긴다(db):
    plan_id, units, _ = save_partial(db, keep=2, deadline=date(2026, 10, 6))

    res = replan.place_unplaced(db, ME.id, plan_id, NOW)

    assert res["left"] == len(units) - 2 - res["placed"] and res["left"] > 0


def test_넣기_API(client, db):
    plan_id, units, _ = save_partial(db)

    res = client.post(f"/plan/{plan_id}/place-unplaced")

    assert res.status_code == 200
    assert res.json()["placed"] == len(units) - 3


def test_기한이_지난_목표나_남의_계획은_넣지_않는다(client, db):
    plan_id, _, _ = save_partial(db, deadline=date(2026, 9, 1))
    assert client.post(f"/plan/{plan_id}/place-unplaced").status_code == 409

    assert client.post("/plan/00000000-0000-0000-0000-000000000000/place-unplaced").status_code == 404
    archive_plan(db, ME.id, plan_id)
    assert client.post(f"/plan/{plan_id}/place-unplaced").status_code == 404


# ── 학습 메모 모아보기 ──────────────────────────────────

def _study(db, block_id, day, note):
    start = datetime(2026, 10, day, 19, 0)
    record_session(db, ME.id, block_id=block_id, started_at=start, ended_at=start.replace(hour=20),
                   minutes=60, expected_minutes=60, note=note, now=start.replace(hour=20))


def test_메모를_목표별로_최근순으로_모은다(client, db):
    sqld, info = save(db, "SQLD"), save(db, "정보처리기사")
    a, b = plan_blocks(db, sqld)[0], plan_blocks(db, info)[0]
    _study(db, a.id, 5, "조인이 헷갈림")
    _study(db, b.id, 6, "정규화 다시 보기")
    _study(db, a.id, 7, "  서브쿼리 정리  ")
    _study(db, None, 8, "자유 학습 메모")
    _study(db, a.id, 9, None)      # 메모 없는 기록은 빠진다
    _study(db, a.id, 10, "   ")    # 빈칸뿐인 메모도 빠진다

    groups = client.get("/study/notes").json()["groups"]

    assert [g["goal_title"] for g in groups] == [None, "SQLD", "정보처리기사"]
    sqld_notes = groups[1]["notes"]
    assert [n["note"] for n in sqld_notes] == ["서브쿼리 정리", "조인이 헷갈림"]
    assert sqld_notes[0]["block_title"] == a.title
    assert groups[0]["notes"][0]["block_title"] is None


def test_끝낸_목표의_메모도_남는다(client, db):
    plan_id = save(db, "SQLD")
    _study(db, plan_blocks(db, plan_id)[0].id, 5, "회고")
    archive_plan(db, ME.id, plan_id)

    groups = client.get("/study/notes").json()["groups"]

    assert groups[0]["goal_title"] == "SQLD" and groups[0]["active"] is False
    assert active_plan_rows(db, ME.id) == []


def test_메모가_없으면_빈_목록(client):
    assert client.get("/study/notes").json() == {"groups": []}
