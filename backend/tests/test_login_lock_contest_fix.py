"""로그인 5회 실패 잠금 (FR-AUTH-01 · NFR-SEC-01) · 관리자 공고 고치기 (FR-ADMIN-01)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import admin_contests
from routers import auth as auth_router
from services import login_guard
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

CONTEST_ID = "00000000-0000-0000-0000-000000000010"


# ── 로그인 잠금 ───────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_guard():
    login_guard.reset()
    yield
    login_guard.reset()


def test_5회_연속_실패하면_60초_잠근다():
    for _ in range(4):
        login_guard.record_failure("Me@Example.com", now=0)
    assert login_guard.locked_for("me@example.com", now=1) == 0
    login_guard.record_failure("me@example.com", now=1)
    assert login_guard.locked_for("ME@example.com", now=2) == 59
    assert login_guard.locked_for("me@example.com", now=61.5) == 0, "60초가 지나면 풀린다"
    login_guard.record_failure("me@example.com", now=62)
    assert login_guard.locked_for("me@example.com", now=62) == 0, "풀린 뒤에는 다시 0부터 센다"


def test_성공하면_실패_횟수가_사라진다():
    for _ in range(4):
        login_guard.record_failure("me@example.com", now=0)
    login_guard.record_success("me@example.com")
    login_guard.record_failure("me@example.com", now=0)
    assert login_guard.locked_for("me@example.com", now=0) == 0


def test_로그인_API는_다섯_번_틀리면_429(monkeypatch):
    calls = []
    client_mock = MagicMock()

    def refuse(_):
        calls.append(1)
        raise RuntimeError("invalid credentials")

    client_mock.auth.sign_in_with_password.side_effect = refuse
    monkeypatch.setattr(auth_router, "new_auth_client", lambda: client_mock)
    client = TestClient(app)
    body = {"email": "nobody@example.com", "password": "wrong-pass-1!"}

    codes = [client.post("/auth/login", json=body).status_code for _ in range(6)]

    assert codes == [401] * 5 + [429]
    assert len(calls) == 5, "잠긴 동안에는 Supabase 에 묻지도 않는다"
    assert "초 뒤에 다시" in client.post("/auth/login", json=body).json()["detail"]


# ── 관리자 공고 고치기 ────────────────────────────────

@pytest.fixture
def admin(monkeypatch):
    db = FakeSupabase()
    db.table("contests").insert({
        "id": CONTEST_ID, "title": "잘못 읽은 제목", "host": "", "source": "wevity", "fields": [],
        "start_date": "2026-10-01", "deadline": "2026-10-31", "status": "open",
        "collected_at": "2026-09-30T05:00:00+09:00",
    }).execute()
    monkeypatch.setattr(admin_contests, "get_supabase_client", lambda: db)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="admin", app_metadata={"role": "admin"})
    yield TestClient(app), db
    app.dependency_overrides.clear()


def test_관리자는_보낸_항목만_고친다(admin):
    client, db = admin
    res = client.patch(f"/admin/contests/{CONTEST_ID}",
                       json={"title": "  제3회 AI 경진대회 ", "host": "과기정통부", "fields": ["AI", "AI", " 웹 "]})
    assert res.status_code == 200
    [row] = db.rows("contests")
    assert (row["title"], row["host"], row["fields"], row["deadline"]) == ("제3회 AI 경진대회", "과기정통부", ["AI", "웹"], "2026-10-31")
    assert row["updated_at"]


def test_잘못된_고치기는_거절한다(admin):
    client, _ = admin
    url = f"/admin/contests/{CONTEST_ID}"
    assert client.patch(url, json={}).status_code == 400
    assert client.patch(url, json={"title": "   "}).status_code == 400
    assert client.patch(url, json={"status": "deleted"}).status_code == 422
    assert client.patch(url, json={"start_date": "2026-11-05"}).status_code == 400, "시작일이 마감일보다 늦다"
    assert client.patch("/admin/contests/00000000-0000-0000-0000-000000000099", json={"host": "x"}).status_code == 404


def test_관리자가_아니면_고칠_수_없다(admin):
    client, db = admin
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user", app_metadata={})
    assert client.patch(f"/admin/contests/{CONTEST_ID}", json={"host": "x"}).status_code == 403
    assert db.rows("contests")[0]["host"] == ""
