"""알림 4종 (FR-ALARM-01~04) · 알림 설정 (FR-MY-03/05) · 알림에서 바로 처리 (FR-ALARM-03).

실제 DB 없이 FakeSupabase 로 본다. 시각은 시간대 없는 한국 시각.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import batch as batch_router
from routers import notifications as notifications_router
from routers import settings as settings_router
from services import alarms
from services.plan_store import to_db_time
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

USER = "00000000-0000-0000-0000-00000000000a"
OTHER = "00000000-0000-0000-0000-00000000000b"
NOW = datetime(2026, 10, 5, 18, 50)  # 월요일 저녁


def block(id_, start, end, *, plan="p1", done=False, title="SQL 기본"):
    return {"id": id_, "plan_id": plan, "unit_key": "u1", "title": title, "start_at": to_db_time(start),
            "end_at": to_db_time(end), "minutes": 60, "locked": False, "done": done}


@pytest.fixture
def db():
    d = FakeSupabase()
    d.table("study_plans").insert([
        {"id": "p1", "user_id": USER, "goal_title": "SQLD", "status": "active"},
        {"id": "p2", "user_id": OTHER, "goal_title": "토익", "status": "active"},
        {"id": "old", "user_id": USER, "goal_title": "끝난 목표", "status": "archived"},
    ]).execute()
    return d


def logs(db, type_=None):
    return [r for r in db.rows("notification_logs") if type_ is None or r["type"] == type_]


# ── FR-ALARM-01 시작 전 ───────────────────────────────

def test_시작_10분_전에_한_번만_보낸다(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0)),
        block("b2", datetime(2026, 10, 5, 20, 0), datetime(2026, 10, 5, 21, 0)),  # 70분 뒤 — 아직
    ]).execute()

    first = alarms.run_before_block(db, NOW)
    again = alarms.run_before_block(db, NOW.replace(minute=51))

    assert (first["sent"], again["sent"]) == (1, 0)
    [row] = logs(db, alarms.BEFORE_BLOCK)
    assert (row["user_id"], row["block_id"]) == (USER, "b1")
    assert row["message"] == "10분 후 'SQL 기본' 학습이 시작돼요."


def test_N분_전_설정을_따른다(db):
    db.table("user_notification_settings").insert({"user_id": USER, "reminder_minutes_before": 30}).execute()
    db.table("plan_blocks").insert(block("b1", datetime(2026, 10, 5, 19, 20), datetime(2026, 10, 5, 20, 0))).execute()
    assert alarms.run_before_block(db, NOW)["sent"] == 1  # 30분 전


def test_끝낸_목표와_완료한_블록에는_보내지_않는다(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0), plan="old"),
        block("b2", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0), done=True),
    ]).execute()
    assert alarms.run_before_block(db, NOW)["sent"] == 0


def test_알림을_끄거나_방해금지면_보내지_않는다(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0)),
        block("b2", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0), plan="p2"),
    ]).execute()
    db.table("user_notification_settings").insert([
        {"user_id": USER, "enabled": False},
        {"user_id": OTHER, "quiet_start": "18:00:00", "quiet_end": "23:00:00"},
    ]).execute()
    assert alarms.run_before_block(db, NOW)["sent"] == 0


# ── FR-ALARM-02 미완료 ────────────────────────────────

def test_끝나고_30분이_지나도_완료하지_않으면_알린다(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0)),               # 50분 지남
        block("b2", datetime(2026, 10, 5, 17, 30), datetime(2026, 10, 5, 18, 30)),             # 20분 — 아직
        block("b3", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0), done=True),   # 완료
        block("b4", datetime(2026, 10, 5, 10, 0), datetime(2026, 10, 5, 11, 0)),               # 너무 오래됨
    ]).execute()

    assert alarms.run_after_block(db, NOW)["sent"] == 1
    assert [r["block_id"] for r in logs(db, alarms.AFTER_BLOCK)] == ["b1"]


def test_강도_낮음은_미완료_알림을_보내지_않는다(db):
    db.table("user_notification_settings").insert({"user_id": USER, "intensity": "low"}).execute()
    db.table("plan_blocks").insert(block("b1", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0))).execute()
    assert alarms.run_after_block(db, NOW)["sent"] == 0


# ── 하루 마감 · 주간 요약 ─────────────────────────────

def test_하루_마감은_강도_높음에게만_하루_한_번(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 10, 0)),
        block("b2", datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 10, 0), plan="p2"),
    ]).execute()
    db.table("user_notification_settings").insert({"user_id": USER, "intensity": "high"}).execute()
    night = NOW.replace(hour=21, minute=0)

    assert alarms.run_daily_nightly(db, night)["sent"] == 1
    assert alarms.run_daily_nightly(db, night.replace(minute=5))["sent"] == 0
    [row] = logs(db, alarms.DAILY_NIGHTLY)
    assert row["user_id"] == USER and "1개" in row["message"]


def test_주간_요약은_완료_수와_공부_시간을_한_주_한_번(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 6, 19, 0), datetime(2026, 10, 6, 20, 0), done=True),
        block("b2", datetime(2026, 10, 8, 19, 0), datetime(2026, 10, 8, 20, 0)),
        block("b3", datetime(2026, 10, 13, 19, 0), datetime(2026, 10, 13, 20, 0)),  # 다음 주
    ]).execute()
    db.table("study_sessions").insert(
        {"user_id": USER, "minutes": 75, "started_at": to_db_time(datetime(2026, 10, 6, 19, 0))}
    ).execute()
    sunday = datetime(2026, 10, 11, 20, 0)

    assert alarms.run_weekly_summary(db, sunday)["sent"] == 1  # OTHER 는 블록·기록이 없다
    assert alarms.run_weekly_summary(db, sunday.replace(minute=30))["sent"] == 0
    [row] = logs(db, alarms.WEEKLY_SUMMARY)
    assert "블록 1/2개 완료" in row["message"] and "1시간 15분" in row["message"]


def test_방해금지는_자정을_넘어도_한국_시각으로_본다():
    s = {**alarms.DEFAULTS, "quiet_start": "22:00:00", "quiet_end": "07:00:00"}
    assert alarms.in_quiet_hours(s, datetime(2026, 10, 5, 23, 0))
    assert alarms.in_quiet_hours(s, datetime(2026, 10, 6, 6, 59))
    assert not alarms.in_quiet_hours(s, datetime(2026, 10, 6, 7, 0))


# ── API ───────────────────────────────────────────────

@pytest.fixture
def client(db, monkeypatch):
    for module in (batch_router, notifications_router, settings_router):
        monkeypatch.setattr(module, "get_supabase_client", lambda: db)
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": USER})()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_배치_API는_배치_키가_있어야_돈다(client, monkeypatch):
    monkeypatch.delenv("BATCH_SECRET", raising=False)
    assert client.post("/batch/alarm/after-block").status_code == 503
    monkeypatch.setenv("BATCH_SECRET", "s3cret")
    assert client.post("/batch/alarm/after-block", headers={"X-Batch-Key": "nope"}).status_code == 401
    res = client.post("/batch/alarm/weekly-summary", headers={"X-Batch-Key": "s3cret"})
    assert res.status_code == 200 and res.json()["job"] == "weekly_summary"


def test_블록_알림에만_시작_미루기_버튼이_붙는다(client, db):
    db.table("notification_logs").insert([
        {"id": 1, "user_id": USER, "type": alarms.AFTER_BLOCK, "message": "a", "is_read": False,
         "sent_at": to_db_time(NOW), "block_id": "b1"},
        {"id": 2, "user_id": USER, "type": alarms.WEEKLY_SUMMARY, "message": "b", "is_read": False,
         "sent_at": to_db_time(NOW), "block_id": None},
        {"id": 3, "user_id": OTHER, "type": alarms.AFTER_BLOCK, "message": "남의 알림", "is_read": False,
         "sent_at": to_db_time(NOW), "block_id": "b9"},
    ]).execute()

    rows = {r["id"]: r for r in client.get("/notifications").json()}
    assert set(rows) == {1, 2}
    assert rows[1]["actions"] == ["start", "postpone"] and rows[2]["actions"] == []

    assert client.patch("/notifications/read-all").status_code == 200
    assert [r["is_read"] for r in db.rows("notification_logs")] == [True, True, False]


def test_테스트용_알림_API는_없다(client):
    assert client.post("/notifications/test").status_code in (404, 405)


def test_알림_설정_저장과_조회(client, db):
    assert client.get("/settings/notifications").json() == {
        "enabled": True, "reminder_minutes_before": 10, "quiet_start": None, "quiet_end": None, "intensity": "normal",
    }
    body = {"enabled": True, "reminder_minutes_before": 15, "quiet_start": "23:00", "quiet_end": "07:00",
            "intensity": "high"}
    assert client.put("/settings/notifications", json=body).json() == body
    assert client.put("/settings/notifications", json={**body, "intensity": "loud"}).status_code == 422
    assert client.put("/settings/notifications", json={**body, "quiet_end": None}).status_code == 422
    assert client.put("/settings/notifications", json={**body, "reminder_minutes_before": 0}).status_code == 422
    [row] = db.rows("user_notification_settings")
    assert (row["user_id"], row["intensity"], row["quiet_start"]) == (USER, "high", "23:00")
    assert client.get("/settings/notifications").json() == body
