"""관리자 DB 현황 (읽기 전용) — 행 수 · 최근 행 · 개인정보 가리기 · 관리자만."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import admin_db as admin_db_router
from services import admin_db
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ADMIN = SimpleNamespace(id="admin-test", app_metadata={"role": "admin"})
MEMBER = SimpleNamespace(id="member-test", app_metadata={})
USER_ID = "5716efef-866b-447d-8fc9-70a7d7beb124"


@pytest.fixture
def db(monkeypatch):
    d = FakeSupabase()
    monkeypatch.setattr(admin_db_router, "get_supabase_client", lambda: d)
    return d


@pytest.fixture
def as_user():
    previous = dict(app.dependency_overrides)

    def use(user):
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield use
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def test_테이블마다_행_수와_마지막_기록_시각을_보여_준다(db, as_user):
    db.table("users").insert([
        {"user_id": USER_ID, "email": "ksg9228@naver.com", "nickname": "김철수", "created_at": "2026-09-28T16:50:00+00:00"},
        {"user_id": "u2", "email": "b@example.com", "nickname": "이", "created_at": "2026-09-29T01:00:00+00:00"},
    ]).execute()

    res = as_user(ADMIN).get("/admin/db/tables")

    assert res.status_code == 200
    tables = {t["name"]: t for t in res.json()["tables"]}
    assert set(tables) == {spec.name for spec in admin_db.CATALOG}
    assert (tables["users"]["rows"], tables["users"]["latest_at"]) == (2, "2026-09-29T01:00:00+00:00")
    assert tables["contests"]["rows"] == 0 and tables["contests"]["latest_at"] is None


def test_최근_행은_보여_줄_열만_개인정보는_가려서(db, as_user):
    db.table("users").insert({
        "id": 1, "user_id": USER_ID, "email": "ksg9228@naver.com", "nickname": "김철수",
        "agree_marketing": False, "agree_privacy": True, "created_at": "2026-09-28T16:50:00+00:00",
    }).execute()
    db.table("study_sessions").insert({
        "id": 7, "user_id": USER_ID, "block_id": None, "started_at": "2026-09-29T10:00:00+00:00",
        "minutes": 50, "expected_minutes": 60, "note": "조인이 헷갈림", "created_at": "2026-09-29T10:50:00+00:00",
    }).execute()
    client = as_user(ADMIN)

    users = client.get("/admin/db/tables/users").json()
    sessions = client.get("/admin/db/tables/study_sessions").json()

    row = users["rows"][0]
    assert row == {"user_id": "5716efef", "email": "ks***@naver.com", "nickname": "김**",
                   "agree_marketing": False, "created_at": "2026-09-28T16:50:00+00:00"}
    assert "agree_privacy" not in row and "id" not in row, "CATALOG 에 없는 열은 보내지 않는다"
    assert sessions["rows"][0]["note"] == "7자", "사용자가 쓴 메모는 길이만"
    assert "email" in users["masked"] and "note" in sessions["masked"]


def test_최근_순으로_쪽을_나눠_보여_준다(db, as_user):
    db.table("ai_call_logs").insert([
        {"id": i, "feature": "plan.decompose", "tool_calls": 0, "created_at": f"2026-09-29T0{i}:00:00+00:00"}
        for i in range(1, 6)
    ]).execute()
    client = as_user(ADMIN)

    first = client.get("/admin/db/tables/ai_call_logs", params={"page_size": 2}).json()
    third = client.get("/admin/db/tables/ai_call_logs", params={"page_size": 2, "page": 3}).json()

    assert first["total"] == 5 and [r["id"] for r in first["rows"]] == [5, 4]
    assert [r["id"] for r in third["rows"]] == [1]


def test_목록에_없는_테이블은_볼_수_없다(db, as_user):
    client = as_user(ADMIN)
    assert client.get("/admin/db/tables/pg_shadow").status_code == 404
    assert client.get("/admin/db/tables/withdrawn_profiles").status_code == 404


def test_관리자가_아니면_볼_수_없다(db, as_user):
    client = as_user(MEMBER)
    assert client.get("/admin/db/tables").status_code == 403
    assert client.get("/admin/db/tables/users").status_code == 403


def test_한_테이블이_실패해도_나머지_현황은_보여_준다():
    class Broken(FakeSupabase):
        def table(self, name):
            if name == "contests":
                raise RuntimeError("PGRST205")
            return super().table(name)

    tables = {t["name"]: t for t in admin_db.overview(Broken())}

    assert tables["contests"]["error"] is True and tables["contests"]["rows"] is None
    assert tables["users"]["error"] is False and tables["users"]["rows"] == 0


@pytest.mark.parametrize("kind,value,expected", [
    (admin_db.EMAIL, "ab@x.com", "ab***@x.com"),
    (admin_db.EMAIL, "not-an-email", "***"),
    (admin_db.NAME, "A", "A*"),
    (admin_db.SHORT, USER_ID, "5716efef"),
    (admin_db.LENGTH, "", "0자"),
    (admin_db.EMAIL, None, None),
])
def test_가리기_규칙(kind, value, expected):
    assert admin_db.mask(kind, value) == expected
