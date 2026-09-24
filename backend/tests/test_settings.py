"""회원 탈퇴 (FR-MY-04) — 로그인 사용자와 DB 는 가짜로 바꿔 끼워 실제 계정을 지우지 않는다."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import settings
from utils.auth import get_current_user

FAKE_USER = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", email="me@example.com")


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, {}

    def delete(self):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def execute(self):
        self.db.calls.append((self.table, "delete", dict(self.filters)))
        deleted = [{"user_id": self.filters.get("user_id")}] if self.db.has_row else []
        return SimpleNamespace(data=deleted)


class FakeDB:
    def __init__(self, has_row=True):
        self.has_row = has_row
        self.calls = []
        self.deleted_auth_users = []
        self.auth = SimpleNamespace(admin=SimpleNamespace(delete_user=self.deleted_auth_users.append))

    def table(self, name):
        return FakeQuery(self, name)


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_withdraw_without_confirm(client, monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(settings, "get_supabase_client", lambda: db)

    res = client.request("DELETE", "/settings/withdraw", json={"confirm": False})

    assert res.status_code == 400
    assert db.calls == []  # 확인 없이는 아무것도 지우지 않는다


def test_withdraw_with_confirm(client, monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(settings, "get_supabase_client", lambda: db)

    res = client.request("DELETE", "/settings/withdraw", json={"confirm": True})

    assert res.status_code == 200
    # 본인 행만 지운다 — 서비스 키는 RLS 를 통과하므로 user_id 조건이 유일한 보호막
    assert db.calls == [("users", "delete", {"user_id": FAKE_USER.id})]
    assert db.deleted_auth_users == [FAKE_USER.id]


def test_withdraw_unknown_user_is_404(client, monkeypatch):
    db = FakeDB(has_row=False)
    monkeypatch.setattr(settings, "get_supabase_client", lambda: db)

    res = client.request("DELETE", "/settings/withdraw", json={"confirm": True})

    assert res.status_code == 404
    assert db.deleted_auth_users == []


def test_withdraw_requires_token():
    res = TestClient(app).request("DELETE", "/settings/withdraw", json={"confirm": True})
    assert res.status_code in (401, 403)
