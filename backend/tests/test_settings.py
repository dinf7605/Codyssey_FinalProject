"""설정 API 검증. 인증과 DB를 대체하여 실제 계정을 삭제하지 않는다."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import settings
from utils.auth import get_current_user

FAKE_USER = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", email="me@example.com")


@pytest.fixture
def client():
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture
def db(monkeypatch):
    db = Mock()
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=True)
    monkeypatch.setattr(settings, "get_supabase_client", lambda: db)
    return db


def withdraw(client, payload):
    return client.request("DELETE", "/settings/withdraw", json=payload)


def test_withdraw_without_confirm(client, db):
    assert withdraw(client, {"confirm": False}).status_code == 400
    db.rpc.assert_not_called()
    db.auth.admin.delete_user.assert_not_called()


def test_withdraw_missing_confirm(client, db):
    assert withdraw(client, {}).status_code == 422
    db.auth.admin.delete_user.assert_not_called()


def test_withdraw_with_confirm(client, db):
    res = withdraw(client, {"confirm": True, "user_id": "another-user"})
    assert res.status_code == 200
    assert "1년" in res.json()["message"]
    db.rpc.assert_called_once_with("withdrawal_retention_ready", {})
    db.auth.admin.delete_user.assert_called_once_with(FAKE_USER.id)
    db.table.assert_not_called()  # 프로필 보관 전에 직접 삭제하지 않는다.


@pytest.mark.parametrize("ready", [False, None, [], "true", 1])
def test_withdraw_unready_database_blocks_deletion(client, db, ready):
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=ready)
    assert withdraw(client, {"confirm": True}).status_code == 503
    db.auth.admin.delete_user.assert_not_called()
    db.table.assert_not_called()


def test_withdraw_missing_migration_blocks_deletion(client, db):
    db.rpc.return_value.execute.side_effect = RuntimeError("function unavailable")
    res = withdraw(client, {"confirm": True})
    assert res.status_code == 503
    assert "function unavailable" not in res.text
    db.auth.admin.delete_user.assert_not_called()


def test_withdraw_auth_failure_is_not_reported_as_success(client, db):
    db.auth.admin.delete_user.side_effect = RuntimeError("internal DB error")
    res = withdraw(client, {"confirm": True})
    assert res.status_code == 503
    assert "internal DB error" not in res.text
    db.table.assert_not_called()


def test_withdraw_requires_token(db):
    res = withdraw(TestClient(app), {"confirm": True})
    assert res.status_code in (401, 403)
    db.rpc.assert_not_called()
    db.auth.admin.delete_user.assert_not_called()


def test_profile_uses_auth_id_and_only_public_fields(client, db):
    query = db.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    profile = {"email": FAKE_USER.email, "nickname": "테스트"}
    query.execute.return_value = SimpleNamespace(data=[profile])
    res = client.get("/settings/profile")
    assert res.status_code == 200
    assert res.json() == profile
    db.table.assert_called_once_with("users")
    query.select.assert_called_once_with("email,nickname")
    query.eq.assert_called_once_with("auth_id", FAKE_USER.id)


def test_profile_missing_is_404(client, db):
    query = db.table.return_value.select.return_value.eq.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[])
    assert client.get("/settings/profile").status_code == 404
