"""회원가입 라우터 회귀 테스트: 실제 Supabase 호출 없이 검증한다."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import auth


@pytest.fixture
def signup_env(monkeypatch):
    db = MagicMock()
    auth_client = MagicMock()
    auth_client.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="new-user-id", identities=[{"id": "identity"}]),
        session=SimpleNamespace(access_token="test-access", refresh_token="test-refresh"),
    )
    monkeypatch.setattr(auth, "get_supabase_client", lambda: db)
    monkeypatch.setattr(auth, "new_auth_client", lambda: auth_client)
    app = FastAPI()
    app.include_router(auth.router)
    with TestClient(app) as client:
        yield client, db, auth_client


def payload(**changes):
    data = dict(email="test@example.com", nickname="테스트", password="Study2026!!",
                agree_privacy=True, agree_ai_notice=True, agree_marketing=False)
    data.update(changes)
    return data


@pytest.mark.parametrize("field", ["agree_privacy", "agree_ai_notice"])
def test_signup_requires_mandatory_consent(signup_env, field):
    client, db, auth_client = signup_env
    response = client.post("/auth/signup", json=payload(**{field: False}))
    assert response.status_code in (400, 422)
    auth_client.auth.sign_up.assert_not_called()
    db.table.assert_not_called()


def test_signup_rejects_short_password(signup_env):
    client, db, auth_client = signup_env
    response = client.post("/auth/signup", json=payload(password="Ab1!"))
    assert response.status_code == 422
    auth_client.auth.sign_up.assert_not_called()
    db.table.assert_not_called()


def test_signup_saves_profile_and_returns_session(signup_env):
    client, db, auth_client = signup_env
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 200
    db.table.assert_called_once_with("users")
    saved = db.table.return_value.insert.call_args.args[0]
    assert saved["auth_id"] == "new-user-id"
    assert "user_id" not in saved
    assert saved["email"] == "test@example.com"
    assert saved["nickname"] == "테스트"
    assert saved["agree_privacy"] is True
    assert saved["agree_ai_notice"] is True
    assert saved["agree_marketing"] is False
    assert saved["agreed_at"]
    assert "password" not in saved and "password_hash" not in saved
    db.table.return_value.insert.return_value.execute.assert_called_once()
    body = response.json()
    assert body["access_token"] == "test-access"
    assert body["refresh_token"] == "test-refresh"
    assert body["user_id"] == "new-user-id"
    assert body["requires_email_confirmation"] is False
    db.auth.admin.delete_user.assert_not_called()


def test_signup_without_session_requires_email_confirmation(signup_env):
    client, db, auth_client = signup_env
    auth_client.auth.sign_up.return_value.session = None
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["requires_email_confirmation"] is True
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    db.auth.admin.delete_user.assert_not_called()


def test_signup_profile_failure_does_not_delete_auth_user(signup_env):
    client, db, auth_client = signup_env
    db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("DB unavailable")
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 503
    assert response.json()["detail"] == auth.SIGNUP_FAILED
    db.auth.admin.delete_user.assert_not_called()


def test_signup_empty_identities_does_not_write_or_delete(signup_env):
    client, db, auth_client = signup_env
    auth_client.auth.sign_up.return_value.user.identities = []
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 400
    db.table.assert_not_called()
    db.auth.admin.delete_user.assert_not_called()


def test_signup_auth_error_does_not_write_or_delete(signup_env):
    client, db, auth_client = signup_env
    auth_client.auth.sign_up.side_effect = RuntimeError("Auth unavailable")
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 400
    assert response.json()["detail"] == auth.SIGNUP_FAILED
    db.table.assert_not_called()
    db.auth.admin.delete_user.assert_not_called()


def test_signup_missing_user_does_not_write_or_delete(signup_env):
    client, db, auth_client = signup_env
    auth_client.auth.sign_up.return_value.user = None
    response = client.post("/auth/signup", json=payload())
    assert response.status_code == 400
    db.table.assert_not_called()
    db.auth.admin.delete_user.assert_not_called()
