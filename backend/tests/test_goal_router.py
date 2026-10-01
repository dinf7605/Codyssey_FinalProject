"""목표 탐색 라우터 테스트 — 화면에서 실제로 누르는 API 경로를 확인한다."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from main import app
from services.goal_limiter import _reset_for_tests

client = TestClient(app)


def setup_function():
    _reset_for_tests()


def test_ping():
    res = client.get("/goal/ping")
    assert res.status_code == 200


def test_태그_매칭_성공():
    res = client.post(
        "/goal/match", json={"tags": ["SQLD"], "session_id": "t1", "k": 5}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["query_used"] == "tags"
    assert body["candidates"]


def test_유사도_낮으면_인기목록으로_대체():
    res = client.post(
        "/goal/match", json={"tags": ["없는분야xyz"], "session_id": "t2", "k": 5}
    )
    assert res.status_code == 200
    assert res.json()["query_used"] == "fallback_popular"


def test_한도를_넘으면_429():
    for _ in range(3):
        client.post("/goal/recommend", json={"tags": ["SQLD"], "weekly_hours": 6, "session_id": "t3"})
    res = client.post(
        "/goal/recommend", json={"tags": ["SQLD"], "weekly_hours": 6, "session_id": "t3"}
    )
    assert res.status_code == 429


def test_목표_2개_진행중이면_확정_거부():
    res = client.post(
        "/goal/confirm",
        json={"goal_title": "SQLD", "is_member": True, "active_goal_count": 2},
    )
    body = res.json()
    assert body["ok"] is False
    assert body["requires_closing_goal"] is True


def test_비회원_확정은_가입을_요구():
    res = client.post(
        "/goal/confirm",
        json={"goal_title": "SQLD", "is_member": False, "active_goal_count": 0},
    )
    body = res.json()
    assert body["ok"] is True
    assert body["requires_signup"] is True


def test_카탈로그에_없는_직접입력은_경고_생략():
    res = client.post(
        "/goal/manual/check",
        json={"title": "완전히새로운목표12345", "due_date": "2026-12-01", "weekly_hours": 5},
    )
    assert res.status_code == 200
    assert res.json()["severity"] == "unknown"


def test_피드백은_DB_없어도_성공():
    # conftest._no_real_db 가 Supabase 환경변수를 지워 두므로, 이 테스트는 DB 미설정
    # 상황에서도 온보딩 흐름이 끊기지 않는지를 확인한다 (FR-GOAL-08).
    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t4"},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_피드백을_저장한다(monkeypatch):
    import routers.goal as goal_router
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)

    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t5"},
    )
    assert res.status_code == 200

    rows = db.rows("goal_feedback")
    assert len(rows) == 1
    assert rows[0]["session_id"] == "t5"
    assert rows[0]["goal_id"] == "g1"
    assert rows[0]["interested"] is False
    assert rows[0]["reason"] == "too_long"
    assert rows[0]["user_id"] is None


def test_비회원_피드백을_취소하면_지워진다(monkeypatch):
    import routers.goal as goal_router
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)

    client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t6"},
    )
    assert len(db.rows("goal_feedback")) == 1

    res = client.request("DELETE", "/goal/feedback/g1", params={"session_id": "t6"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert db.rows("goal_feedback") == []


def test_비회원_피드백_취소는_다른_세션기록을_못지운다(monkeypatch):
    import routers.goal as goal_router
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)

    client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "owner"},
    )

    res = client.request("DELETE", "/goal/feedback/g1", params={"session_id": "someone-else"})
    assert res.status_code == 200
    # 세션이 다르면 지워지지 않는다 — 조회 결과만으로는 성공/실패를 구분하지 않는다
    # (POST /goal/feedback과 동일하게 항상 ok:true를 준다).
    assert len(db.rows("goal_feedback")) == 1


def test_피드백_취소에_session_id가_없으면_400():
    res = client.request("DELETE", "/goal/feedback/g1")
    assert res.status_code == 400


def test_최근_관심없음_목표는_추천에서_빠진다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)

    res = client.post("/goal/match", json={"tags": ["SQLD"], "session_id": "tfilter1", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    db.table("goal_feedback").insert(
        {"session_id": "tfilter1", "user_id": None, "goal_id": goal_id, "interested": False, "reason": "too_long"}
    ).execute()

    res2 = client.post(
        "/goal/recommend", json={"tags": ["SQLD"], "weekly_hours": 6, "session_id": "tfilter1"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id not in ids


def test_30일_지난_관심없음은_다시_추천된다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)

    res = client.post("/goal/match", json={"tags": ["SQLD"], "session_id": "tfilter2", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.table("goal_feedback").insert(
        {
            "session_id": "tfilter2",
            "user_id": None,
            "goal_id": goal_id,
            "interested": False,
            "reason": "too_long",
            "created_at": old_ts,
        }
    ).execute()

    res2 = client.post(
        "/goal/recommend", json={"tags": ["SQLD"], "weekly_hours": 6, "session_id": "tfilter2"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids


def test_다른_세션의_관심없음은_영향을_주지_않는다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)

    res = client.post("/goal/match", json={"tags": ["SQLD"], "session_id": "owner2", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    db.table("goal_feedback").insert(
        {"session_id": "owner2", "user_id": None, "goal_id": goal_id, "interested": False, "reason": "too_long"}
    ).execute()

    res2 = client.post(
        "/goal/recommend", json={"tags": ["SQLD"], "weekly_hours": 6, "session_id": "다른세션"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids
