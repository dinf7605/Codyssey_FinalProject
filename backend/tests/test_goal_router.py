"""목표 탐색 라우터 테스트 — 화면에서 실제로 누르는 API 경로를 확인한다."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from main import app
from services.goal_limiter import _reset_for_tests
from utils.auth import get_optional_user

client = TestClient(app)


def setup_function():
    _reset_for_tests()
    import services.goal_feedback as goal_feedback

    goal_feedback._reset_for_tests()


def teardown_function():
    # 회원 흉내(override)가 다른 테스트로 새어나가지 않게 매번 정리한다.
    app.dependency_overrides.pop(get_optional_user, None)


def _login_as(user_id: str = "u1") -> None:
    """get_optional_user 가 로그인된 사용자를 돌려주도록 흉내낸다.

    conftest._no_real_db 가 Supabase 환경변수를 지워 두므로, 테스트에서는 실제
    토큰 발급·검증(네트워크 호출)을 거칠 수 없다 — FastAPI 의존성을 바로 주입해
    "이 요청은 로그인된 사용자가 보낸 것"이라고 치는 표준 테스트 패턴이다.
    """
    app.dependency_overrides[get_optional_user] = lambda: SimpleNamespace(id=user_id)


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


def test_직접입력_이름이_조금_달라도_카탈로그_목표를_찾는다():
    res = client.post(
        "/goal/manual/check",
        json={"title": "토익 900점", "due_date": "2026-12-01", "weekly_hours": 15},
    )
    assert res.json()["severity"] != "unknown"  # '토익 900+' 로 계산한다


def test_짧은_이름은_앞부분만_같아도_엉뚱한_목표로_잇지_않는다():
    from services.goal_catalog import find_by_title

    assert find_by_title("정보") is None
    assert find_by_title("SQLD").title == "SQLD (SQL 개발자)"


def test_피드백은_DB_없어도_성공():
    # conftest._no_real_db 가 Supabase 환경변수를 지워 두므로, 이 테스트는 DB 미설정
    # 상황에서도 온보딩 흐름이 끊기지 않는지를 확인한다 (FR-GOAL-08).
    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t4"},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_비회원_피드백은_로컬파일에_저장된다():
    import services.goal_feedback as goal_feedback

    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t5"},
    )
    assert res.status_code == 200
    # 비회원은 session_id 를 서버 DB(Supabase)에 남기지 않는다 — 로컬 파일에만 쌓인다.
    assert goal_feedback._nonmember_dismissed_goal_ids("t5") == {"g1"}


def test_비회원_관심있음_피드백은_저장하지_않는다():
    import services.goal_feedback as goal_feedback

    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": True, "session_id": "t5b"},
    )
    assert res.status_code == 200
    # "관심있음"은 제외 목적이 없으니 로컬 파일에 쌓을 이유가 없다.
    assert goal_feedback._nonmember_dismissed_goal_ids("t5b") == set()


def test_회원_피드백을_저장한다(monkeypatch):
    import routers.goal as goal_router
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    _login_as("u1")

    res = client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t5c"},
    )
    assert res.status_code == 200

    rows = db.rows("goal_feedback")
    assert len(rows) == 1
    assert rows[0]["session_id"] == "t5c"
    assert rows[0]["goal_id"] == "g1"
    assert rows[0]["interested"] is False
    assert rows[0]["reason"] == "too_long"
    assert rows[0]["user_id"] == "u1"


def test_비회원_피드백을_취소하면_지워진다():
    import services.goal_feedback as goal_feedback

    client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t6"},
    )
    assert goal_feedback._nonmember_dismissed_goal_ids("t6") == {"g1"}

    res = client.request("DELETE", "/goal/feedback/g1", params={"session_id": "t6"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert goal_feedback._nonmember_dismissed_goal_ids("t6") == set()


def test_비회원_피드백_취소는_다른_세션기록을_못지운다():
    import services.goal_feedback as goal_feedback

    client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "owner"},
    )

    res = client.request("DELETE", "/goal/feedback/g1", params={"session_id": "someone-else"})
    assert res.status_code == 200
    # 세션이 다르면 지워지지 않는다 — 조회 결과만으로는 성공/실패를 구분하지 않는다
    # (POST /goal/feedback과 동일하게 항상 ok:true를 준다).
    assert goal_feedback._nonmember_dismissed_goal_ids("owner") == {"g1"}


def test_회원_피드백_취소는_Supabase에서_지운다(monkeypatch):
    import routers.goal as goal_router
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    _login_as("u1")

    client.post(
        "/goal/feedback",
        json={"goal_id": "g1", "interested": False, "reason": "too_long", "session_id": "t6b"},
    )
    assert len(db.rows("goal_feedback")) == 1

    res = client.request("DELETE", "/goal/feedback/g1")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert db.rows("goal_feedback") == []


def test_피드백_취소에_session_id가_없으면_400():
    res = client.request("DELETE", "/goal/feedback/g1")
    assert res.status_code == 400


def test_비회원_최근_관심없음_목표는_추천에서_빠진다():
    # 토익(cert-toeic)은 deadline 이 없어 "기한 적합성" 판정이 항상 통과한다 —
    # 자격증 시험일(SQLD 등)을 쓰면 오늘 날짜가 마감에 가까워질수록 feasibility
    # 자체가 깨져 추천 후보가 아예 0개가 될 수 있어, 관심없음 필터링과 무관한
    # 이유로 테스트가 흔들린다. 날짜에 흔들리지 않도록 토익으로 고정한다.
    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "tfilter1", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    client.post(
        "/goal/feedback",
        json={"goal_id": goal_id, "interested": False, "reason": "too_long", "session_id": "tfilter1"},
    )

    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "tfilter1"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id not in ids


def test_24시간_지난_비회원_관심없음은_다시_추천된다():
    import services.goal_feedback as goal_feedback

    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "tfilter1b", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    goal_feedback.record_nonmember_dismiss("tfilter1b", goal_id)
    # 기록 시각을 24시간(NONMEMBER_LIMIT_WINDOW_HOURS) 이전으로 되돌려 제외 기간이
    # 지난 상황을 흉내낸다.
    old_ts = goal_feedback._dismissed["tfilter1b"][goal_id] - goal_feedback.NONMEMBER_WINDOW_SECONDS - 1
    goal_feedback._dismissed["tfilter1b"][goal_id] = old_ts

    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "tfilter1b"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids


def test_회원_최근_관심없음_목표는_추천에서_빠진다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)
    _login_as("u1")

    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "tfilter2", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    # FakeSupabase 는 created_at 을 안 넣으면 "2026-01-01" 로 고정해서 채운다 — 30일
    # 이내인지 비교할 땐 실제 "지금"이어야 하니 명시적으로 넣는다.
    now_ts = datetime.now(timezone.utc).isoformat()
    db.table("goal_feedback").insert(
        {
            "session_id": "tfilter2",
            "user_id": "u1",
            "goal_id": goal_id,
            "interested": False,
            "reason": "too_long",
            "created_at": now_ts,
        }
    ).execute()

    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "tfilter2"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id not in ids


def test_30일_지난_회원_관심없음은_다시_추천된다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)
    _login_as("u1")

    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "tfilter3", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.table("goal_feedback").insert(
        {
            "session_id": "tfilter3",
            "user_id": "u1",
            "goal_id": goal_id,
            "interested": False,
            "reason": "too_long",
            "created_at": old_ts,
        }
    ).execute()

    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "tfilter3"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids


def test_다른_세션의_비회원_관심없음은_영향을_주지_않는다():
    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "owner2", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    client.post(
        "/goal/feedback",
        json={"goal_id": goal_id, "interested": False, "reason": "too_long", "session_id": "owner2"},
    )

    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "다른세션"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids


def test_다른_회원의_관심없음은_영향을_주지_않는다(monkeypatch):
    import routers.goal as goal_router
    import services.goal_feedback as goal_feedback
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    monkeypatch.setattr(goal_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(goal_feedback, "get_supabase_client", lambda: db)

    res = client.post("/goal/match", json={"tags": ["토익"], "session_id": "owner3", "k": 5})
    goal_id = res.json()["candidates"][0]["goal_id"]

    db.table("goal_feedback").insert(
        {"session_id": "owner3", "user_id": "u1", "goal_id": goal_id, "interested": False, "reason": "too_long"}
    ).execute()

    _login_as("u2")
    res2 = client.post(
        "/goal/recommend", json={"tags": ["토익"], "weekly_hours": 6, "session_id": "owner3"}
    )
    ids = [c["goal_id"] for c in res2.json()["candidates"]]
    assert goal_id in ids
