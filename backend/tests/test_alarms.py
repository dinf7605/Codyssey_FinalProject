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


def nudging(db, user=USER):
    """독촉을 받는 설정 — 강도 '강' + 학습 독촉 켬 (FR-MY-03/05)."""
    db.table("user_notification_settings").insert({"user_id": user, "intensity": "high", "notify_nudge": True}).execute()


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
    nudging(db)
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0)),               # 50분 지남
        block("b2", datetime(2026, 10, 5, 17, 30), datetime(2026, 10, 5, 18, 30)),             # 20분 — 아직
        block("b3", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0), done=True),   # 완료
        block("b4", datetime(2026, 10, 5, 10, 0), datetime(2026, 10, 5, 11, 0)),               # 너무 오래됨
    ]).execute()

    assert alarms.run_after_block(db, NOW)["sent"] == 1
    [row] = logs(db, alarms.AFTER_BLOCK)
    assert row["block_id"] == "b1"
    assert "가장 오래 밀린 블록은" not in row["message"]  # 오늘 블록이라 밀린 날수는 0


def test_독촉은_기본으로_보내지_않는다(db):
    """FR-MY-03 학습 독촉은 기본 꺼짐 · FR-MY-05 강도 '보통'은 독촉을 뺀다."""
    db.table("plan_blocks").insert(block("b1", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0))).execute()
    assert alarms.run_after_block(db, NOW)["sent"] == 0
    db.table("user_notification_settings").insert({"user_id": USER, "intensity": "normal", "notify_nudge": True}).execute()
    assert alarms.run_after_block(db, NOW)["sent"] == 0


def test_가입_때_선택_동의하면_선택_알림이_켜진다(db):
    db.table("users").insert({"user_id": USER, "agree_marketing": True}).execute()
    s = alarms.settings_for(db, [USER, OTHER])
    assert (s[USER]["notify_replan"], s[USER]["notify_nudge"], s[USER]["notify_deadline"]) == (True, True, True)
    assert (s[OTHER]["notify_replan"], s[OTHER]["notify_nudge"]) == (False, False)
    assert (s[OTHER]["quiet_start"], s[OTHER]["quiet_end"]) == ("23:00", "07:00")  # FR-MY-05 기본 방해금지


def test_독촉은_하루_3번까지_직전_2번을_안_읽으면_멈춘다(db):
    nudging(db)
    for i, read in enumerate((True, False, False)):
        db.table("notification_logs").insert({"user_id": USER, "type": alarms.AFTER_BLOCK, "message": "m",
                                              "is_read": read, "sent_at": to_db_time(NOW.replace(hour=10 + i))}).execute()
    assert not alarms.nudge_allowed(db, USER, NOW)  # 3번 — 하루 상한

    db.tables["notification_logs"] = db.rows("notification_logs")[1:]  # 안 읽은 2번만 남김
    assert not alarms.nudge_allowed(db, USER, NOW)  # 연달아 2번 무응답
    db.rows("notification_logs")[-1]["is_read"] = True
    assert alarms.nudge_allowed(db, USER, NOW)


def test_오늘_쉬기를_누르면_그날_학습_알림이_멈춘다(db):
    nudging(db)
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 19, 0), datetime(2026, 10, 5, 20, 0)),
        block("b2", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0)),
    ]).execute()
    assert alarms.rest_today(db, USER, NOW) is True
    assert alarms.rest_today(db, USER, NOW) is False  # 두 번 눌러도 기록은 하나
    assert alarms.run_before_block(db, NOW)["sent"] == 0
    assert alarms.run_after_block(db, NOW)["sent"] == 0
    # 다음 날은 다시 보낸다
    db.table("plan_blocks").insert(block("b3", datetime(2026, 10, 6, 19, 0), datetime(2026, 10, 6, 20, 0))).execute()
    assert alarms.run_before_block(db, datetime(2026, 10, 6, 18, 50))["sent"] == 1


def test_방해금지_동안_시작한_블록은_끝난_뒤_첫_알림에_합친다(db):
    """FR-ALARM-01 — 기본 방해금지 23:00~07:00 사이 블록은 따로 보내지 않고 07시 이후 첫 알림에 합친다."""
    db.table("plan_blocks").insert([
        block("q1", datetime(2026, 10, 6, 6, 0), datetime(2026, 10, 6, 6, 50)),
        block("b1", datetime(2026, 10, 6, 8, 0), datetime(2026, 10, 6, 9, 0)),
        block("b2", datetime(2026, 10, 6, 10, 0), datetime(2026, 10, 6, 11, 0)),
    ]).execute()
    assert alarms.run_before_block(db, datetime(2026, 10, 6, 5, 55))["sent"] == 0  # 방해금지
    assert alarms.run_before_block(db, datetime(2026, 10, 6, 7, 50))["sent"] == 1
    assert alarms.run_before_block(db, datetime(2026, 10, 6, 9, 50))["sent"] == 1
    first, second = logs(db, alarms.BEFORE_BLOCK)
    assert "방해금지 시간에 시작한 블록 1개" in first["message"]
    assert "방해금지" not in second["message"]


def test_강도_낮음은_미완료_알림을_보내지_않는다(db):
    db.table("user_notification_settings").insert({"user_id": USER, "intensity": "low", "notify_nudge": True}).execute()
    db.table("plan_blocks").insert(block("b1", datetime(2026, 10, 5, 17, 0), datetime(2026, 10, 5, 18, 0))).execute()
    assert alarms.run_after_block(db, NOW)["sent"] == 0


# ── 하루 마감 · 주간 요약 ─────────────────────────────

def test_하루_마감은_독촉을_켠_강도_강에게만_하루_한_번(db):
    db.table("plan_blocks").insert([
        block("b1", datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 10, 0)),
        block("b2", datetime(2026, 10, 5, 9, 0), datetime(2026, 10, 5, 10, 0), plan="p2"),
    ]).execute()
    nudging(db)
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

    assert alarms.run_weekly_summary(db, sunday)["sent"] == 2
    assert alarms.run_weekly_summary(db, sunday.replace(minute=30))["sent"] == 0
    rows = {r["user_id"]: r["message"] for r in logs(db, alarms.WEEKLY_SUMMARY)}
    assert "블록 1/2개 완료(50%)" in rows[USER] and "1시간 15분" in rows[USER]
    assert "가장 오래 밀린 블록은 3일 전" in rows[USER]          # 10/8 블록을 아직 안 했다
    assert "다음 중간 목표: 10/11까지" in rows[USER]
    # FR-ALARM-04 — 기록이 0건이면 수치 대신 목표 다시 정하기 안내만
    assert "학습 기록이 없어요" in rows[OTHER] and "완료" not in rows[OTHER]


def test_주간_요약에_이번_주_추천_공모전_1건(db):
    db.table("plan_blocks").insert(block("b1", datetime(2026, 10, 6, 19, 0), datetime(2026, 10, 6, 20, 0), done=True)).execute()
    db.table("contests").insert([{"id": "c1", "title": "낮은 점수"}, {"id": "c2", "title": "AI 아이디어 공모전"}]).execute()
    db.table("contest_recommendations").insert([
        {"user_id": USER, "contest_id": "c1", "recommendation_week": "2026-10-05", "rerank_score": 0.4},
        {"user_id": USER, "contest_id": "c2", "recommendation_week": "2026-10-05", "rerank_score": 0.9},
    ]).execute()
    alarms.run_weekly_summary(db, datetime(2026, 10, 11, 20, 0))
    mine = [r for r in logs(db, alarms.WEEKLY_SUMMARY) if r["user_id"] == USER]
    assert "이번 주 추천 공모전: 'AI 아이디어 공모전'" in mine[0]["message"]


def test_재조정_결과는_켠_사람에게_방해금지가_끝난_뒤_보낸다(db):
    db.table("user_notification_settings").insert({"user_id": USER, "notify_replan": True}).execute()
    db.table("plan_reschedule_runs").insert([
        {"user_id": USER, "plan_id": "p1", "summary": "지난 블록 2개를 옮겼어요.", "moved": 2,
         "created_at": to_db_time(datetime(2026, 10, 6, 3, 0))},
        {"user_id": OTHER, "plan_id": "p2", "summary": "x", "moved": 1,  # OTHER 는 선택 동의 없음 → 기본 꺼짐
         "created_at": to_db_time(datetime(2026, 10, 6, 3, 0))},
    ]).execute()
    assert alarms.run_replan_results(db, datetime(2026, 10, 6, 3, 5))["sent"] == 0  # 방해금지
    assert alarms.run_replan_results(db, datetime(2026, 10, 6, 7, 5))["sent"] == 1
    assert alarms.run_replan_results(db, datetime(2026, 10, 6, 7, 10))["sent"] == 0
    [row] = logs(db, alarms.REPLAN_RESULT)
    assert row["user_id"] == USER and "블록 2개" in row["message"]


def test_관심_공모전_마감_24시간_전_알림은_전체_끄기와_별개(db):
    db.table("user_notification_settings").insert({"user_id": USER, "enabled": False, "notify_deadline": True}).execute()
    db.table("contests").insert([
        {"id": "c1", "title": "데이터 공모전", "deadline": "2026-10-05", "status": "open"},  # 오늘 24:00 마감
        {"id": "c2", "title": "먼 공모전", "deadline": "2026-10-20", "status": "open"},
    ]).execute()
    db.table("contest_interests").insert([
        {"user_id": USER, "contest_id": "c1"}, {"user_id": USER, "contest_id": "c2"},
        {"user_id": OTHER, "contest_id": "c1"},  # OTHER 는 동의 안 함
    ]).execute()
    assert alarms.run_contest_deadlines(db, NOW)["sent"] == 1
    assert alarms.run_contest_deadlines(db, NOW.replace(minute=55))["sent"] == 0
    [row] = logs(db, alarms.CONTEST_DEADLINE)
    assert (row["user_id"], row["contest_id"]) == (USER, "c1") and "데이터 공모전" in row["message"]


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
    assert rows[1]["actions"] == ["start", "postpone", "rest"] and rows[2]["actions"] == []

    assert client.patch("/notifications/read-all").status_code == 200
    assert [r["is_read"] for r in db.rows("notification_logs")] == [True, True, False]

    # 미루기는 블록당 2번까지 (FR-ALARM-03) — 다 쓰면 버튼을 빼고 보낸다
    db.table("plan_changes").insert([
        {"user_id": USER, "plan_id": "p1", "block_id": "b1", "reason": "알림에서 미뤄 10/6(화) 19:00로 옮겼어요."},
        {"user_id": USER, "plan_id": "p1", "block_id": "b1", "reason": "알림에서 미뤄 10/7(수) 19:00로 옮겼어요."},
    ]).execute()
    rows = {r["id"]: r for r in client.get("/notifications").json()}
    assert rows[1]["actions"] == ["start", "rest"]


def test_테스트용_알림_API는_없다(client):
    assert client.post("/notifications/test").status_code in (404, 405)


def test_오늘_쉬기_API(client, db):
    res = client.post("/notifications/rest-today")
    assert res.status_code == 200 and res.json()["created"] is True
    assert client.post("/notifications/rest-today").json()["created"] is False
    assert [r["type"] for r in db.rows("notification_logs")] == [alarms.REST_TODAY]


def test_알림_설정_저장과_조회(client, db):
    assert client.get("/settings/notifications").json() == {
        "enabled": True, "reminder_minutes_before": 10, "quiet_start": "23:00", "quiet_end": "07:00",
        "intensity": "normal", "notify_replan": False, "notify_deadline": False, "notify_nudge": False,
    }
    body = {"enabled": True, "reminder_minutes_before": 15, "quiet_start": "22:30", "quiet_end": "07:00",
            "intensity": "high", "notify_replan": True, "notify_deadline": False, "notify_nudge": True}
    assert client.put("/settings/notifications", json=body).json() == body
    assert client.put("/settings/notifications", json={**body, "intensity": "loud"}).status_code == 422
    assert client.put("/settings/notifications", json={**body, "quiet_end": None}).status_code == 422
    assert client.put("/settings/notifications", json={**body, "reminder_minutes_before": 0}).status_code == 422
    [row] = db.rows("user_notification_settings")
    assert (row["user_id"], row["intensity"], row["quiet_start"]) == (USER, "high", "22:30")
    assert client.get("/settings/notifications").json() == body

    off = {**body, "quiet_start": None, "quiet_end": None}  # 방해금지를 끈 것도 그대로 남는다
    client.put("/settings/notifications", json=off)
    assert client.get("/settings/notifications").json() == off
