"""동시 진행 목표 2개 (FR-GOAL-07) — 두 계획이 서로의 블록을 피하는지 확인한다 (담당 C)."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers import plan as plan_router
from routers.study import week_progress
from schemas.plan import Availability, Block, TimeSlot
from services import replan
from services.plan_store import PlanLimitReached, active_plan_rows, plan_blocks, save_plan
from services.scheduler import build_schedule
from services.template import template_units
from services.validator import validate_schedule
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user, get_optional_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")
AVAIL = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
START, DEADLINE = date(2026, 10, 5), date(2026, 12, 20)


def save(db, goal, blocks=None, units=None):
    units = units or template_units(goal)
    blocks = blocks if blocks is not None else build_schedule(units, AVAIL, START, DEADLINE).blocks
    return save_plan(db, ME.id, goal_title=goal, goal_id=goal, deadline=DEADLINE,
                     source="template", units=units, blocks=blocks, availability=AVAIL)


def all_blocks(db):
    return [b for p in active_plan_rows(db, ME.id) for b in plan_blocks(db, p["id"])]


def no_clash(blocks):
    """두 목표를 합쳐도 겹침·하루 상한·연속 시간 위반이 없어야 한다 (단위 id 가 겹칠 수 있어 단위는 빼고 본다)."""
    tagged = [b.model_copy(update={"unit_id": f"{i}"}) for i, b in enumerate(blocks)]
    return validate_schedule(tagged, [], date(2099, 1, 1))


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def client(db, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_optional_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(plan_router, "get_supabase_client", lambda: db)
    yield TestClient(app)
    app.dependency_overrides.clear()


def body(goal, blocks, units=None):
    units = units or template_units(goal)
    return {
        "goal_title": goal, "goal_id": goal, "deadline": DEADLINE.isoformat(), "source": "template",
        "units": [u.model_dump(mode="json") for u in units],
        "blocks": [b if isinstance(b, dict) else b.model_dump(mode="json") for b in blocks],
        "availability": AVAIL.model_dump(),
    }


def schedule_second(client, goal="정보처리기사"):
    units = template_units(goal)
    res = client.post("/plan/schedule", json={
        "units": [u.model_dump(mode="json") for u in units], "availability": AVAIL.model_dump(),
        "start_day": START.isoformat(), "deadline": DEADLINE.isoformat(), "goal_title": goal,
    }).json()
    return units, res


# ── 배치 · 저장 ────────────────────────────────────────

def test_두번째_목표는_첫_목표_블록을_피해서_놓인다(client, db):
    save(db, "SQLD")

    units, res = schedule_second(client)

    new_blocks = [Block(**b) for b in res["blocks"]]
    assert {b.unit_id for b in new_blocks} <= {u.id for u in units}, "다른 목표 블록이 결과에 섞이지 않는다"
    assert len(new_blocks) == len(units)
    assert no_clash(all_blocks(db) + new_blocks) == []
    assert any("다른 목표" in n for n in res["notes"])

    assert client.post("/plan/save", json=body("정보처리기사", res["blocks"], units)).status_code == 200
    assert len(client.get("/plan/active").json()["plans"]) == 2


def test_다른_목표와_겹치는_일정은_저장하지_않는다(client, db):
    save(db, "SQLD")
    units = template_units("정보처리기사")
    clashing = build_schedule(units, AVAIL, START, DEADLINE).blocks  # 첫 목표를 모르고 놓은 일정

    res = client.post("/plan/save", json=body("정보처리기사", clashing, units))

    assert res.status_code == 400 and "다른 목표" in res.json()["detail"]
    assert len(active_plan_rows(db, ME.id)) == 1


def test_세번째_목표는_막고_같은_목표는_교체한다(db):
    save(db, "SQLD")
    save(db, "ADsP", blocks=[])
    with pytest.raises(PlanLimitReached):
        save(db, "정보처리기사", blocks=[])

    save(db, "SQLD")  # 같은 목표 다시 만들기 = 교체
    assert sorted(p["goal_title"] for p in active_plan_rows(db, ME.id)) == ["ADsP", "SQLD"]


def test_세번째_목표_저장은_409(client, db):
    save(db, "SQLD")
    save(db, "ADsP", blocks=[])
    res = client.post("/plan/save", json=body("정보처리기사", []))
    assert res.status_code == 409 and "2개" in res.json()["detail"]


def test_목표를_끝내면_자리가_생긴다(client, db):
    save(db, "SQLD")
    other = save(db, "ADsP", blocks=[])

    assert client.post(f"/plan/{other}/archive").status_code == 200
    assert [p["goal_title"] for p in client.get("/plan/active").json()["plans"]] == ["SQLD"]
    assert client.post(f"/plan/{other}/archive").status_code == 404, "이미 끝낸 목표"
    assert client.post("/plan/not-mine/archive").status_code == 404


# ── 재조정 · 편집 ──────────────────────────────────────

def _two_plans(client, db):
    save(db, "SQLD")
    units, res = schedule_second(client)
    assert client.post("/plan/save", json=body("정보처리기사", res["blocks"], units)).status_code == 200


def test_야간_재조정은_다른_목표_블록과_겹치지_않는다(client, db):
    _two_plans(client, db)

    result = replan.run_nightly(db, datetime(2026, 10, 8, 3, 0), use_ai=False)

    assert result["status"] == "success" and result["plans"] == 2 and result["moved"] > 0
    assert no_clash(all_blocks(db)) == []


def test_변경_내역은_두_목표를_함께_보여주고_되돌리기는_목표마다(client, db, monkeypatch):
    _two_plans(client, db)
    # 두 번째 목표는 첫 목표를 피해 10/15 부터 놓인다 — 둘 다 지난 블록이 생기는 날로
    replan.run_nightly(db, datetime(2026, 10, 17, 3, 0), use_ai=False)
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 17, 9, 0))

    runs = client.get("/plan/changes").json()["runs"]

    assert {r["goal_title"] for r in runs} == {"SQLD", "정보처리기사"}
    assert all(r["can_undo"] for r in runs), "목표마다 가장 최근 재조정을 되돌릴 수 있다"
    assert client.post(f"/plan/changes/{runs[1]['id']}/undo").status_code == 200


def test_먼저_만든_목표의_블록도_옮기고_다른_목표_블록_자리로는_못_옮긴다(client, db, monkeypatch):
    _two_plans(client, db)
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    plans = active_plan_rows(db, ME.id)
    older, newer = plans[1], plans[0]
    mine = plan_blocks(db, older["id"])[-1]
    theirs = plan_blocks(db, newer["id"])[-1]

    free = datetime(2026, 12, 5, 10, 0)  # 토요일 — 두 목표 모두 블록이 없는 날
    assert client.patch(f"/plan/blocks/{mine.id}", json={"start": free.isoformat()}).json()["applied"] is True

    clash = client.patch(f"/plan/blocks/{mine.id}", json={"start": theirs.start.isoformat(), "force": True}).json()
    assert clash["applied"] is False and clash["forceable"] is False


def test_주간_달성률은_두_목표를_합친다(client, db):
    _two_plans(client, db)
    week = [b for b in all_blocks(db) if b.start.date() <= date(2026, 10, 11)]

    got = week_progress(db, ME.id, date(2026, 10, 7))

    assert got["week_planned_minutes"] == sum(b.minutes for b in week)
