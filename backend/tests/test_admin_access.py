from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from utils import auth as auth_utils


@pytest.fixture
def client(monkeypatch):
    # 예상하지 못한 실제 Supabase 호출도 차단한다.
    def unexpected_db():
        raise AssertionError("Unexpected database access")

    monkeypatch.setattr(
        auth_utils, "get_supabase_client", unexpected_db
    )

    with TestClient(app) as test_client:
        yield test_client


def install_auth(monkeypatch, app_metadata, user_metadata=None):
    user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000099",
        app_metadata=app_metadata,
        user_metadata=user_metadata or {},
    )

    def get_user(token):
        assert token == "test-access-token"
        return SimpleNamespace(user=user)

    db = SimpleNamespace(
        auth=SimpleNamespace(get_user=get_user)
    )
    monkeypatch.setattr(
        auth_utils, "get_supabase_client", lambda: db
    )


HEADERS = {"Authorization": "Bearer test-access-token"}
ENDPOINTS = ["/admin/ping", "/admin/me"]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_admin_requires_login(client, path):
    response = client.get(path)
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("path", ENDPOINTS)
@pytest.mark.parametrize("metadata", [{}, {"role": "user"}, None])
def test_normal_user_is_denied(client, monkeypatch, path, metadata):
    install_auth(monkeypatch, metadata)

    response = client.get(path, headers=HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"] == "관리자 권한이 필요합니다"


@pytest.mark.parametrize("path", ENDPOINTS)
def test_user_metadata_cannot_grant_admin(client, monkeypatch, path):
    install_auth(monkeypatch, {}, {"role": "admin"})

    response = client.get(path, headers=HEADERS)

    assert response.status_code == 403


@pytest.mark.parametrize("path", ENDPOINTS)
def test_admin_is_allowed(client, monkeypatch, path):
    install_auth(monkeypatch, {"role": "admin"})

    response = client.get(path, headers=HEADERS)

    assert response.status_code == 200
    if path == "/admin/me":
        assert response.json() == {"is_admin": True}


@pytest.mark.parametrize("path", ENDPOINTS)
def test_invalid_token_is_denied(client, monkeypatch, path):
    def reject_token(_):
        raise RuntimeError("Invalid token")

    db = SimpleNamespace(
        auth=SimpleNamespace(get_user=reject_token)
    )
    monkeypatch.setattr(
        auth_utils, "get_supabase_client", lambda: db
    )

    response = client.get(path, headers=HEADERS)

    assert response.status_code == 401
