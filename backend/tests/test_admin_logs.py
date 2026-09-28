from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import admin
from utils.auth import get_current_user


@pytest.fixture
def client():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        app_metadata={"role": "admin"}
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture
def summary_query():
    query = MagicMock()
    for name in ("select", "gte", "lt", "order", "range"):
        getattr(query, name).return_value = query
    query.execute.return_value = SimpleNamespace(data=[], count=0)
    return query


@pytest.fixture
def query(monkeypatch, summary_query):
    query = MagicMock()
    for name in ("select", "gte", "lt", "order", "range"):
        getattr(query, name).return_value = query

    query.execute.return_value = SimpleNamespace(data=[], count=0)
    db = MagicMock()
    db.table.side_effect = [query, summary_query]
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    return query


def test_empty_day(client, query):
    response = client.get("/admin/ai-logs?day=2026-09-27")

    assert response.status_code == 200
    assert response.json() == {
        "day": "2026-09-27",
        "timezone": "Asia/Seoul",
        "page": 1,
        "page_size": 20,
        "total": 0,
        "items": [],
        "summary": {
            "record_count": 0,
            "tool_calls_total": 0,
            "latency_record_count": 0,
            "average_latency_ms": None,
        },
    }
    assert response.headers["cache-control"] == "no-store"


def test_korean_day_and_pagination(client, query):
    response = client.get(
        "/admin/ai-logs?day=2026-09-27&page=2&page_size=10"
    )

    assert response.status_code == 200
    query.gte.assert_called_once_with(
        "created_at", "2026-09-26T15:00:00+00:00"
    )
    query.lt.assert_called_once_with(
        "created_at", "2026-09-27T15:00:00+00:00"
    )
    query.range.assert_called_once_with(10, 19)
    assert [call.args for call in query.order.call_args_list] == [
        ("created_at",), ("id",)
    ]
    assert all(
        call.kwargs == {"desc": True}
        for call in query.order.call_args_list
    )


def test_response_excludes_private_fields(client, query):
    query.execute.return_value = SimpleNamespace(
        count=1,
        data=[{
            "id": 1,
            "feature": "plan.decompose",
            "model": None,
            "source": "template",
            "tool_calls": 0,
            "latency_ms": 25,
            "created_at": "2026-09-27T01:00:00+00:00",
            "user_id": "private-user-id",
            "message": "private-message",
        }],
    )

    response = client.get("/admin/ai-logs?day=2026-09-27")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["source"] == "template"
    assert "user_id" not in item
    assert "message" not in item
    selected = query.select.call_args.args[0].split(",")
    assert "user_id" not in selected
    assert "message" not in selected


@pytest.mark.parametrize("params", [
    "day=not-a-date",
    "day=9999-12-31",
    "page=0",
    "page=10001",
    "page_size=0",
    "page_size=101",
])
def test_invalid_query(client, query, params):
    response = client.get("/admin/ai-logs?" + params)

    assert response.status_code == 422
    query.execute.assert_not_called()


def test_database_failure(client, query):
    query.execute.side_effect = RuntimeError("private database detail")

    response = client.get("/admin/ai-logs")

    assert response.status_code == 503
    assert "private database detail" not in response.text


def test_missing_count_is_not_reported_as_zero(client, query):
    query.execute.return_value = SimpleNamespace(data=[], count=None)

    response = client.get("/admin/ai-logs")

    assert response.status_code == 503


def test_normal_user_cannot_read_logs(client, query):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        app_metadata={}, user_metadata={"role": "admin"}
    )

    response = client.get("/admin/ai-logs")

    assert response.status_code == 403
    query.execute.assert_not_called()


def test_login_required(client, query):
    app.dependency_overrides.pop(get_current_user)

    response = client.get("/admin/ai-logs")

    assert response.status_code in (401, 403)
    query.execute.assert_not_called()


def test_summary_covers_whole_day(client, query, summary_query):
    query.execute.return_value = SimpleNamespace(
        count=3,
        data=[{
            "id": 2,
            "feature": "plan.decompose",
            "model": None,
            "source": "template",
            "tool_calls": 2,
            "latency_ms": 0,
            "created_at": "2026-09-27T01:00:00+00:00",
        }],
    )
    summary_query.execute.return_value = SimpleNamespace(
        count=3,
        data=[
            {"id": 1, "tool_calls": 1, "latency_ms": None},
            {"id": 2, "tool_calls": 2, "latency_ms": 0},
            {"id": 3, "tool_calls": 3, "latency_ms": 300},
        ],
    )

    response = client.get(
        "/admin/ai-logs?day=2026-09-27&page=2&page_size=1"
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["summary"] == {
        "record_count": 3,
        "tool_calls_total": 6,
        "latency_record_count": 2,
        "average_latency_ms": 150.0,
    }
    query.range.assert_called_once_with(1, 1)
    summary_query.range.assert_called_once_with(0, 499)
    summary_query.gte.assert_called_once_with(
        "created_at", "2026-09-26T15:00:00+00:00"
    )
    summary_query.lt.assert_called_once_with(
        "created_at", "2026-09-27T15:00:00+00:00"
    )
    summary_query.select.assert_called_once_with(
        "id,tool_calls,latency_ms", count="exact"
    )


def test_summary_failure_keeps_list_available(client, query, summary_query):
    summary_query.execute.side_effect = RuntimeError("private summary detail")

    response = client.get("/admin/ai-logs?day=2026-09-27")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert response.json()["summary"] is None
    assert response.headers["cache-control"] == "no-store"
    assert "private summary detail" not in response.text
