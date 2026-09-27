from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import admin_contests
from utils.auth import get_current_user

CONTEST_ID = "00000000-0000-0000-0000-000000000010"


@pytest.fixture
def client():
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="admin-test", app_metadata={"role": "admin"}
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture
def database(monkeypatch):
    db = MagicMock()
    queries = {}
    for name in ("contests", "contest_embeddings"):
        query = MagicMock()
        for method in ("select", "order", "range", "in_"):
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=[], count=0)
        queries[name] = query
    db.table.side_effect = lambda name: queries[name]
    factory = MagicMock(return_value=db)
    monkeypatch.setattr(admin_contests, "get_supabase_client", factory)
    return queries, factory


def contest_row():
    return {
        "id": CONTEST_ID,
        "title": "Test contest",
        "host": "Test host",
        "source": "test",
        "deadline": "2026-10-31",
        "status": "open",
        "collected_at": "2026-09-27T12:00:00+00:00",
        "raw_text": "PRIVATE RAW TEXT",
    }


def test_empty_list(client, database):
    queries, _ = database
    response = client.get("/admin/contests")
    assert response.status_code == 200
    assert response.json() == {
        "page": 1, "page_size": 20, "total": 0, "items": []
    }
    assert response.headers["cache-control"] == "no-store"
    queries["contest_embeddings"].execute.assert_not_called()


@pytest.mark.parametrize("status", ["pending", "indexed", "failed", "missing"])
def test_index_status_and_pagination(client, database, status):
    queries, _ = database
    queries["contests"].execute.return_value = SimpleNamespace(
        data=[contest_row()], count=21
    )
    index_rows = [] if status == "missing" else [{
        "contest_id": CONTEST_ID,
        "index_status": status,
        "indexed_at": None,
        "error_message": "PRIVATE INTERNAL ERROR",
    }]
    queries["contest_embeddings"].execute.return_value = SimpleNamespace(
        data=index_rows
    )

    response = client.get("/admin/contests?page=2&page_size=20")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 21
    assert body["items"][0]["index_status"] == status
    assert "PRIVATE" not in response.text
    queries["contests"].range.assert_called_once_with(20, 39)
    queries["contest_embeddings"].in_.assert_called_once_with(
        "contest_id", [CONTEST_ID]
    )
    assert "raw_text" not in queries["contests"].select.call_args.args[0]
    assert "error_message" not in (
        queries["contest_embeddings"].select.call_args.args[0]
    )


@pytest.mark.parametrize("table", ["contests", "contest_embeddings"])
def test_db_failure_is_not_empty_success(client, database, table):
    queries, _ = database
    queries["contests"].execute.return_value = SimpleNamespace(
        data=[contest_row()], count=1
    )
    queries[table].execute.side_effect = RuntimeError("PRIVATE DB ERROR")
    response = client.get("/admin/contests")
    assert response.status_code == 503
    assert "PRIVATE" not in response.text


def test_missing_count_is_error(client, database):
    queries, _ = database
    queries["contests"].execute.return_value = SimpleNamespace(
        data=[], count=None
    )
    assert client.get("/admin/contests").status_code == 503


@pytest.mark.parametrize("query", [
    "page=0", "page=10001", "page_size=0", "page_size=101"
])
def test_invalid_pagination(client, database, query):
    _, factory = database
    assert client.get("/admin/contests?" + query).status_code == 422
    factory.assert_not_called()


def test_normal_user_denied(client, database):
    _, factory = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="normal-test",
        app_metadata={"role": "user"},
        user_metadata={"role": "admin"},
    )
    assert client.get("/admin/contests").status_code == 403
    factory.assert_not_called()


def test_anonymous_denied(client, database):
    _, factory = database
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/admin/contests").status_code in (401, 403)
    factory.assert_not_called()