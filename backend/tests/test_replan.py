"""야간 재조정 · 변경 내역 · 블록 편집 · 완료 취소 · 주간 달성률 · 범위 점검 (담당 C) — 가짜 DB 로 확인한다."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers.study import week_progress
from schemas.plan import Availability, StudyUnit, TimeSlot
from services import replan
from services.plan_store import active_plan_row, plan_blocks, plan_units, record_session, save_plan
from services.scheduler import build_schedule, reschedule_incomplete
from services.scope import check_scope
from services.template import template_units
from services.validator import validate_schedule
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")

# 평일 저녁 19~22시, 일요일 휴식
AVAIL = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
START, DEADLINE = date(2026, 10, 5), date(2026, 12, 20)   # 10-05 는 월요일
NIGHT = datetime(2026, 10, 8, 3, 0)                      # 목요일 03:00 — 월·화·수 블록이 지났다


@pytest.fixture
def db():
    db = FakeSupabase()
    units = template_units("SQLD")  # tpl-01 → tpl-02 → … 선행 사슬
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    save_plan(db, ME.id, goal_title="SQLD", goal_id="cert-sqld", deadline=DEADLINE,
              source="template", units=units, blocks=blocks, availability=AVAIL)
    return db


def plan_of(db):
    return active_plan_row(db, ME.id)


def blocks_of(db):
    return plan_blocks(db, plan_of(db)["id"])


def by_unit(db):
    return {b.unit_id: b for b in blocks_of(db)}


@pytest.fixture
def client(db):
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 야간 재조정 (FR-PLAN-06) ──────────────────────────

def test_지난_미완료_블록을_남은_기간으로_옮기고_기록한다(db):
    before = by_unit(db)

    result = replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    after = by_unit(db)
    assert result["moved"] >= 4
    for uid in ("tpl-01", "tpl-02", "tpl-03", "tpl-04"):   # 월·화·수 블록
        assert after[uid].start >= NIGHT
        assert after[uid].id == before[uid].id, "블록 id 는 그대로 — 기록이 계속 같은 블록을 가리킨다"
    assert validate_schedule(blocks_of(db), plan_units(db, plan_of(db)["id"]), DEADLINE) == []
    (run,) = db.rows("plan_reschedule_runs")
    assert run["summary_source"] == "template"
    assert len(db.rows("plan_changes")) == result["moved"]
    assert all(c["origin"] == "nightly" for c in db.rows("plan_changes"))


def test_앞_단원이_밀리면_기대는_뒤_블록도_함께_밀린다(db):
    replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    after = by_unit(db)
    # tpl-05 는 목요일 블록(미래)이었지만 tpl-04 에 기댄다 → tpl-04 뒤로
    assert after["tpl-05"].start >= after["tpl-04"].end
    reasons = [c["reason"] for c in db.rows("plan_changes")]
    assert any("순서를 지키려고" in r for r in reasons)


def test_완료_블록과_직접_옮긴_블록은_그대로_둔다(db):
    first, second = sorted(blocks_of(db), key=lambda b: b.start)[:2]
    db.table("plan_blocks").update({"done": True}).eq("id", first.id).execute()
    db.table("plan_blocks").update({"locked": True}).eq("id", second.id).execute()

    replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    now = {b.id: b for b in blocks_of(db)}
    assert now[first.id].start == first.start
    assert now[second.id].start == second.start


def test_지난_블록이_없으면_아무것도_안_한다(db):
    assert replan.run_for_plan(db, plan_of(db), datetime(2026, 10, 5, 3, 0), use_ai=False) is None
    assert db.rows("plan_reschedule_runs") == []


def test_기한_안에_자리가_없으면_그대로_두고_알린다(db):
    db.table("study_plans").update({"deadline": "2026-10-07"}).eq("id", plan_of(db)["id"]).execute()
    before = by_unit(db)

    result = replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    assert result["moved"] == 0 and result["unplaced"] >= 1
    assert by_unit(db)["tpl-01"].start == before["tpl-01"].start
    assert {c["change_type"] for c in db.rows("plan_changes")} == {"unplaced"}
    assert "빈 시간이 없어" in db.rows("plan_reschedule_runs")[0]["summary"]


def test_규칙을_어기는_결과면_기존_일정을_유지한다(db, monkeypatch):
    before = by_unit(db)
    real = replan.validate_schedule
    calls = {"n": 0}

    def strict(blocks, units, deadline):
        calls["n"] += 1
        found = real(blocks, units, deadline)
        if calls["n"] == 2:  # 적용 후 검사에서만 위반을 만든다
            found.append(replan.Violation(kind="overlap", block_id=blocks[0].id, detail="가짜 겹침"))
        return found

    monkeypatch.setattr(replan, "validate_schedule", strict)

    with pytest.raises(replan.ReplanError):
        replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    assert by_unit(db) == before
    assert db.rows("plan_reschedule_runs") == []


def test_블록_갱신이_중간에_실패하면_원래대로_돌린다(db):
    before = by_unit(db)
    real_table = db.table
    count = {"n": 0}

    def table(name):
        q = real_table(name)
        if name == "plan_blocks":
            real_update = q.update

            def update(values):
                count["n"] += 1
                if count["n"] == 2:
                    raise RuntimeError("네트워크 끊김")
                return real_update(values)
            q.update = update
        return q

    db.table = table
    with pytest.raises(RuntimeError):
        replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    assert by_unit(db) == before


def test_시작_시간이_지났으면_내일부터_놓는다():
    assert replan._place_from(AVAIL, datetime(2026, 10, 8, 3, 0)) == date(2026, 10, 8)
    assert replan._place_from(AVAIL, datetime(2026, 10, 8, 20, 0)) == date(2026, 10, 9)


def test_빈_시간표가_없던_예전_계획은_블록_시간대로_추정한다(db):
    guessed = replan.availability_of({"availability": None}, blocks_of(db))
    assert {s.weekday for s in guessed.slots} <= {0, 1, 2, 3, 4}
    assert all(s.start >= "19:00" and s.end <= "22:00" for s in guessed.slots)


def test_상태없는_재조정도_선행_순서를_지킨다():
    units = template_units("SQLD")
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    after = reschedule_incomplete(blocks, units, AVAIL, date(2026, 10, 8), DEADLINE)
    assert validate_schedule(after.blocks, units, DEADLINE) == []


# ── 전체 배치 ─────────────────────────────────────────

def test_야간_배치는_키가_없으면_돌지_않는다(client, monkeypatch):
    monkeypatch.delenv("BATCH_SECRET", raising=False)
    assert client.post("/plan/nightly").status_code == 503

    monkeypatch.setenv("BATCH_SECRET", "s3cret")
    assert client.post("/plan/nightly", headers={"X-Batch-Key": "wrong"}).status_code == 401
    assert client.post("/plan/nightly", headers={"X-Batch-Key": "s3cret"}).status_code == 200


def test_야간_배치는_모든_계획을_돌고_관리자_로그를_남긴다(db):
    result = replan.run_nightly(db, NIGHT, use_ai=False)

    assert result["status"] == "success" and result["plans"] == 1 and result["moved"] >= 4
    (log,) = db.rows("batch_runs")
    assert log["job_name"] == "plan.nightly_reschedule" and log["status"] == "success"


def test_한_사람이_실패해도_배치는_계속하고_실패로_남긴다(db, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("망가진 계획")

    monkeypatch.setattr(replan, "run_for_plan", boom)
    result = replan.run_nightly(db, NIGHT, use_ai=False)

    assert result["status"] == "failed" and result["failed"] == 1
    assert "망가진 계획" in db.rows("batch_runs")[0]["error_message"]


def test_책망하는_AI_요약은_버리고_규칙_문구를_쓴다(monkeypatch):
    class Fake:
        class messages:
            @staticmethod
            def create(**_):
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="어제 왜 안 하셨어요? 다시 놓았어요.")])

    monkeypatch.setattr(replan.llm, "get_client", lambda timeout=0: Fake())
    text, source = replan.summarize(replan.Replan(today=date(2026, 10, 8)))
    assert source == "template" and "왜" not in text


# ── 변경 내역 · 되돌리기 (FR-PLAN-07) ───────────────────

def test_변경_내역과_되돌리기(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: NIGHT + timedelta(hours=6))
    before = by_unit(db)
    replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)

    data = client.get("/plan/changes").json()
    (run,) = data["runs"]
    assert run["can_undo"] and run["changes"]
    assert {c["type"] for c in run["changes"]} == {"move"}

    res = client.post(f"/plan/changes/{run['id']}/undo")
    assert res.status_code == 200 and res.json()["restored"] == run["moved"]
    assert by_unit(db) == before

    again = client.post(f"/plan/changes/{run['id']}/undo")
    assert again.status_code == 409, "되돌리기는 한 번만"
    assert client.get("/plan/changes").json()["runs"][0]["can_undo"] is False


def test_되돌리기는_그사이_끝낸_블록을_건드리지_않는다(db):
    replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)
    moved = by_unit(db)["tpl-01"]
    db.table("plan_blocks").update({"done": True}).eq("id", moved.id).execute()

    run_id = db.rows("plan_reschedule_runs")[0]["id"]
    result = replan.undo_run(db, ME.id, run_id, NIGHT + timedelta(hours=20))

    assert result["skipped"] == 1
    assert by_unit(db)["tpl-01"].start == moved.start


def test_사흘_연속_밀리면_기한_조정을_제안한다(db):
    for day in (8, 9, 10):
        replan.run_for_plan(db, plan_of(db), datetime(2026, 10, day, 3, 0), use_ai=False)

    data = replan.recent_changes(db, ME.id, datetime(2026, 10, 10, 9, 0))
    assert data["streak_days"] == 3 and data["suggest_extension"] is True
    assert [r["can_undo"] for r in data["runs"]] == [True, False, False], "가장 최근 것만 되돌릴 수 있다"


def test_7일이_지난_내역은_보이지_않는다(db):
    replan.run_for_plan(db, plan_of(db), NIGHT, use_ai=False)
    assert replan.recent_changes(db, ME.id, NIGHT + timedelta(days=8))["runs"] == []


# ── 블록 직접 편집 (FR-PLAN-05) ────────────────────────

def test_블록을_옮기면_고정되고_기록된다(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    target = by_unit(db)["tpl-10"]
    new_start = target.start + timedelta(days=7)

    res = client.patch(f"/plan/blocks/{target.id}", json={"start": new_start.isoformat()}).json()

    assert res["applied"] is True
    moved = by_unit(db)["tpl-10"]
    assert moved.start == new_start and moved.locked is True
    assert moved.end - moved.start == target.end - target.start
    (change,) = db.rows("plan_changes")
    assert change["origin"] == "manual" and change["change_type"] == "move"


def test_선행_순서를_어기면_경고하고_강행을_고르면_옮긴다(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    first, second = by_unit(db)["tpl-01"], by_unit(db)["tpl-02"]
    later = datetime.combine(second.start.date() + timedelta(days=1), datetime.min.time()).replace(hour=7)

    warn = client.patch(f"/plan/blocks/{first.id}", json={"start": later.isoformat()}).json()
    assert warn["applied"] is False and warn["forceable"] is True
    assert {v["kind"] for v in warn["violations"]} == {"prerequisite_violation"}
    assert by_unit(db)["tpl-01"].start == first.start, "경고만 하고 아직 옮기지 않는다"

    forced = client.patch(f"/plan/blocks/{first.id}", json={"start": later.isoformat(), "force": True}).json()
    assert forced["applied"] is True
    assert "경고를 확인하고" in db.rows("plan_changes")[0]["reason"]


def test_겹치는_자리로는_강행해도_옮기지_않는다(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    a, b = by_unit(db)["tpl-08"], by_unit(db)["tpl-09"]

    res = client.patch(f"/plan/blocks/{a.id}", json={"start": b.start.isoformat(), "force": True}).json()

    assert res["applied"] is False and res["forceable"] is False
    assert by_unit(db)["tpl-08"].start == a.start


def test_지난_시각이나_완료_블록은_옮길_수_없다(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    target = by_unit(db)["tpl-10"]
    assert client.patch(f"/plan/blocks/{target.id}", json={"start": "2026-09-30T19:00:00"}).status_code == 409

    db.table("plan_blocks").update({"done": True}).eq("id", target.id).execute()
    assert client.patch(f"/plan/blocks/{target.id}", json={"start": "2026-12-01T19:00:00"}).status_code == 409


def test_남의_블록이나_없는_블록은_404(client):
    assert client.patch("/plan/blocks/not-mine", json={"start": "2026-12-01T19:00:00"}).status_code == 404
    assert client.delete("/plan/blocks/not-mine").status_code == 404


def test_블록을_지우면_기록이_남는다(client, db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: datetime(2026, 10, 1, 12, 0))
    target = by_unit(db)["tpl-10"]

    assert client.delete(f"/plan/blocks/{target.id}").status_code == 204

    assert "tpl-10" not in by_unit(db)
    (change,) = db.rows("plan_changes")
    assert change["change_type"] == "delete" and change["title"] == target.title
    assert change["block_id"] is None, "블록이 지워지면 연결만 끊긴다"


# ── 완료 취소 (FR-STUDY-02) ───────────────────────────

def _complete(db, block, at):
    record_session(db, ME.id, block_id=block.id, started_at=at - timedelta(minutes=60), ended_at=at,
                   minutes=60, expected_minutes=60, note=None, now=at)


def test_완료는_24시간_안에만_취소된다(db):
    target = by_unit(db)["tpl-01"]
    done_at = datetime(2026, 10, 5, 20, 30)
    _complete(db, target, done_at)
    assert by_unit(db)["tpl-01"].done_at == done_at

    with pytest.raises(replan.ReplanError):
        replan.cancel_done(db, ME.id, target.id, done_at + timedelta(hours=25))

    replan.cancel_done(db, ME.id, target.id, done_at + timedelta(hours=2))
    assert by_unit(db)["tpl-01"].done is False
    assert len(db.rows("study_sessions")) == 1, "공부한 시간 기록은 남는다"


def test_완료_취소_API(client, db):
    target = by_unit(db)["tpl-01"]
    _complete(db, target, replan.now_kst())

    assert client.delete(f"/study/blocks/{target.id}/done").status_code == 204
    assert client.delete(f"/study/blocks/{target.id}/done").status_code == 409, "이미 취소됨"


# ── 주간 달성률 (FR-STUDY-03) ──────────────────────────

def test_주간_달성률은_이번_주_계획_대비_완료(db):
    week = [b for b in blocks_of(db) if b.start.date() <= date(2026, 10, 11)]
    db.table("plan_blocks").update({"done": True}).eq("id", week[0].id).execute()

    got = week_progress(db, ME.id, date(2026, 10, 7))

    assert got["week_planned_minutes"] == sum(b.minutes for b in week)
    assert got["week_done_minutes"] == week[0].minutes
    assert got["week_rate"] == round(week[0].minutes / got["week_planned_minutes"] * 100)


def test_이번_주_블록이_없으면_달성률은_비운다(db):
    assert week_progress(db, ME.id, date(2026, 9, 26))["week_rate"] is None


def test_통계에_주간_달성률이_함께_온다(client):
    stats = client.get("/study/stats").json()
    assert {"week_rate", "week_planned_minutes", "week_done_minutes", "level"} <= stats.keys()


# ── 범위 점검 (FR-PLAN-02) ─────────────────────────────

def test_가용시간의_1_5배를_넘으면_범위_축소안을_준다():
    units = template_units("SQLD")
    tight = Availability(slots=[TimeSlot(weekday=0, start="19:00", end="20:00")])

    got = check_scope(units, tight, START, date(2026, 10, 26))

    assert got["over"] is True and got["drop_unit_ids"]
    keep = set(got["keep_unit_ids"])
    for u in units:
        if u.id in keep:
            assert set(u.prerequisites) <= keep, "남는 단위의 선행 단위는 빼지 않는다"
    assert got["suggested_deadline"] > "2026-10-26"


def test_여유가_있으면_축소하지_않는다():
    got = check_scope(template_units("SQLD"), AVAIL, START, DEADLINE)
    assert got["over"] is False and got["drop_unit_ids"] == []


def test_범위_점검_API():
    body = {
        "units": [u.model_dump() for u in template_units("SQLD")],
        "availability": AVAIL.model_dump(),
        "start_day": "2026-10-05",
        "deadline": "2026-10-06",
    }
    res = TestClient(app).post("/plan/scope", json=body).json()
    assert res["over"] is True and res["ratio"] > 1.5


def test_축소안대로_하면_실제로_다_들어간다():
    # 3시간 칸에 90분 단위는 쉬는 시간 때문에 하나만 들어간다 — 빈 시간을 그냥 더하면 과대평가된다
    units = [StudyUnit(id=f"u{i:02d}", title=f"단원 {i}", estimated_minutes=90,
                       prerequisites=[f"u{i - 1:02d}"] if i > 1 else []) for i in range(1, 9)]
    monday = Availability(slots=[TimeSlot(weekday=0, start="19:00", end="22:00")])
    start, deadline = date(2026, 9, 26), date(2026, 10, 10)

    got = check_scope(units, monday, start, deadline)

    kept = [u for u in units if u.id in got["keep_unit_ids"]]
    assert build_schedule(kept, monday, start, deadline).unplaced == []
    extended = date.fromisoformat(got["suggested_deadline"])
    assert build_schedule(units, monday, start, extended).unplaced == []
