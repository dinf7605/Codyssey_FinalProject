"""구글 로그인 (FR-AUTH-02) — 실제 Supabase·Google 없이 주소 검사와 프로필 생성 규칙을 본다."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import auth_google
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

CALLBACK = "http://localhost:3000/auth/callback"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(auth_google, "google_enabled", lambda: True)
    db = FakeSupabase()
    monkeypatch.setattr(auth_google, "get_supabase_client", lambda: db)
    user = SimpleNamespace(id="google-user", email="study@gmail.com",
                           user_metadata={"full_name": "김스터디"})
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app), db, user
    app.dependency_overrides.clear()


def consent(**changes):
    body = {"nickname": "김스터디", "agree_privacy": True, "agree_ai_notice": True, "agree_marketing": False}
    body.update(changes)
    return body


def test_시작_주소는_Supabase_구글_인증으로_간다(env):
    client, _, _ = env
    response = client.get("/auth/google/start", params={"redirect_to": CALLBACK})

    assert response.status_code == 200
    url = urlparse(response.json()["url"])
    assert (url.netloc, url.path) == ("project.supabase.co", "/auth/v1/authorize")
    query = parse_qs(url.query)
    assert query["provider"] == ["google"] and query["redirect_to"] == [CALLBACK]
    assert "scopes" not in query, "로그인에서 캘린더 권한을 요구하지 않는다"


@pytest.mark.parametrize("redirect", [
    "https://evil.example/auth/callback",
    "http://localhost:3000/schedule",
    "http://localhost:3000/auth/callback?x=1",
])
def test_허용된_콜백_주소가_아니면_거절한다(env, redirect):
    client, _, _ = env
    assert client.get("/auth/google/start", params={"redirect_to": redirect}).status_code == 400


def test_공급자가_꺼져_있으면_준비_안_됨으로_안내한다(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setattr(auth_google, "google_enabled", lambda: False)
    response = client.get("/auth/google/start", params={"redirect_to": CALLBACK})
    assert response.status_code == 503 and "이메일로 로그인" in response.json()["detail"]


def test_처음_온_계정은_프로필이_없고_닉네임을_제안한다(env):
    client, _, _ = env
    body = client.get("/auth/google/profile").json()
    assert body == {"has_profile": False, "email": "study@gmail.com", "suggested_nickname": "김스터디"}


@pytest.mark.parametrize("field", ["agree_privacy", "agree_ai_notice"])
def test_필수_동의가_없으면_프로필을_만들지_않는다(env, field):
    client, db, _ = env
    assert client.post("/auth/google/complete", json=consent(**{field: False})).status_code == 400
    assert db.rows("users") == []


def test_동의하면_프로필을_한_번만_만든다(env):
    client, db, _ = env
    first = client.post("/auth/google/complete", json=consent(agree_marketing=True))
    second = client.post("/auth/google/complete", json=consent(nickname="다른이름"))

    assert first.json() == {"created": True} and second.json() == {"created": False}
    rows = db.rows("users")
    assert len(rows) == 1
    row = rows[0]
    assert (row["user_id"], row["email"], row["nickname"]) == ("google-user", "study@gmail.com", "김스터디")
    assert row["agree_privacy"] and row["agree_ai_notice"] and row["agree_marketing"] and row["agreed_at"]
    assert client.get("/auth/google/profile").json()["has_profile"] is True


@pytest.mark.parametrize("metadata, email, expected", [
    ({"full_name": "  홍길동  "}, "a@b.com", "홍길동"),
    ({"name": "Alexander Hamilton"}, "a@b.com", "Alexander"),
    ({}, "studypace@gmail.com", "studypace"),
    ({"full_name": "김"}, "x@b.com", ""),
])
def test_닉네임_제안은_2에서_10자(metadata, email, expected):
    assert auth_google.suggested_nickname(metadata, email) == expected
