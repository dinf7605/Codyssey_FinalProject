"""운영 모니터링 (평가 #3 보완) — 오류 기록 · 워커 생존 신호 · 준비 상태 · 가동률 · 오류 감시 미들웨어."""

import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from db import DatabaseNotConfigured
from services import ops_monitor
from tests.fake_supabase import FakeSupabase
from utils import error_monitor

NOW = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)   # 한국 12:00


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    ops_monitor._window.update(start=0.0, count=0)
    ops_monitor._ready_cache.update(at=0.0, value=None)
    ops_monitor._uptime_cache.update(at=0.0, value=None)
    monkeypatch.setattr(error_monitor, "dispatch", lambda fn: fn())   # 기록을 바로 실행해 확인한다
    yield


def iso(dt):
    return dt.isoformat()


# ── 가리기 ──

def test_오류_메시지에서_이메일_id_긴_숫자를_가리고_300자로_자른다():
    text = "user a.b@test.com plan 3f2b8c1e-1d2a-4c3b-9e8f-0a1b2c3d4e5f code 12345678 " + "x" * 400
    out = ops_monitor.scrub(text)
    assert "a.b@test.com" not in out and "<email>" in out
    assert "3f2b8c1e" not in out and "<id>" in out
    assert "12345678" not in out and "<num>" in out
    assert len(out) == ops_monitor.MESSAGE_LIMIT
    assert ops_monitor.scrub(None) is None


def test_라우트_틀을_못_얻으면_경로의_id_를_지운다():
    assert ops_monitor.route_template("/plan/3f2b8c1e-1d2a-4c3b-9e8f-0a1b2c3d4e5f/blocks/42") == "/plan/{id}/blocks/{id}"


# ── 오류 기록 ──

def test_오류를_기록하고_쓰기가_실패해도_예외를_내지_않는다():
    db = FakeSupabase()
    assert ops_monitor.record_error(db, source="api", route="/plan", error_type="RuntimeError",
                                    status_code=500, method="POST", message="x@y.com 실패", request_id="abc")
    row = db.rows("error_logs")[0]
    assert row["route"] == "/plan" and row["status_code"] == 500 and row["message"] == "<email> 실패"

    class Broken:
        def table(self, _name):
            raise RuntimeError("DB 끊김")

    assert ops_monitor.record_error(Broken(), source="api", route="/x", error_type="E") is False


def test_오류가_쏟아져도_DB_에는_분당_30건까지만_쓴다():
    db = FakeSupabase()
    results = [ops_monitor.record_error(db, source="api", route="/x", error_type="E") for _ in range(40)]
    assert sum(results) == ops_monitor.RATE_PER_MINUTE
    assert len(db.rows("error_logs")) == ops_monitor.RATE_PER_MINUTE


# ── 준비 상태 ──

def test_DB_를_읽고_워커가_1분_전에_신호를_남겼으면_ok():
    db = FakeSupabase()
    assert ops_monitor.beat(db, now=NOW - timedelta(minutes=1))
    code, body = ops_monitor.readiness(lambda: db, NOW, use_cache=False)
    assert code == 200 and body["status"] == "ok"
    assert body["checks"] == {"db": "ok", "worker": "ok"}


def test_워커가_10분_넘게_조용하면_degraded_지만_200():
    db = FakeSupabase()
    ops_monitor.beat(db, now=NOW - timedelta(minutes=11))
    ops_monitor.beat(db, now=NOW - timedelta(minutes=11))   # 같은 서비스는 한 행만
    assert len(db.rows("service_heartbeats")) == 1
    code, body = ops_monitor.readiness(lambda: db, NOW, use_cache=False)
    assert code == 200 and body["status"] == "degraded" and body["worker"]["status"] == "stale"


def test_워커_신호가_아직_없으면_unknown_이고_실패로_보지_않는다():
    code, body = ops_monitor.readiness(lambda: FakeSupabase(), NOW, use_cache=False)
    assert code == 200 and body["status"] == "ok" and body["checks"]["worker"] == "unknown"


def test_DB_키가_없거나_DB_를_못_읽으면_503():
    def not_configured():
        raise DatabaseNotConfigured("환경변수가 필요합니다")

    code, body = ops_monitor.readiness(not_configured, NOW, use_cache=False)
    assert code == 503 and body["status"] == "down" and body["checks"]["db"] == "not_configured"

    class Broken:
        def table(self, _name):
            raise RuntimeError("timeout")

    code, body = ops_monitor.readiness(lambda: Broken(), NOW, use_cache=False)
    assert code == 503 and body["checks"]["db"] == "error"


def test_배포_서버의_health_는_커밋_버전을_알려_준다(monkeypatch):
    from main import app

    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "93b1a5a0123456789")
    with TestClient(app) as client:
        res = client.get("/health")
        ready = client.get("/health/ready")   # 테스트는 DB 키를 지운다 (conftest)
    assert res.status_code == 200 and res.json()["version"] == "93b1a5a"
    assert res.headers["X-Request-ID"]
    assert ready.status_code == 503 and ready.json()["checks"]["db"] == "not_configured"


# ── 오류 요약 ──

def test_오류를_한국_날짜별_경로별_유형별로_묶는다():
    db = FakeSupabase()
    rows = [
        (NOW - timedelta(hours=1), "api", "POST", "/plan", "HTTP 503"),
        (NOW - timedelta(hours=2), "api", "POST", "/plan", "RuntimeError"),
        (NOW - timedelta(days=1), "worker", None, "worker:run_before_block", "APIError"),
        (NOW - timedelta(days=10), "api", "GET", "/old", "HTTP 500"),   # 기간 밖
    ]
    for at, source, method, route, kind in rows:
        db.table("error_logs").insert({"occurred_at": iso(at), "source": source, "method": method, "route": route,
                                       "status_code": None, "error_type": kind, "message": None,
                                       "request_id": None}).execute()

    s = ops_monitor.error_summary(db, days=7, now=NOW)
    assert s["status"] == "ok" and s["total"] == 3
    assert s["by_day"][-1] == {"day": "2026-10-07", "count": 2}
    assert s["by_day"][-2] == {"day": "2026-10-06", "count": 1}
    assert len(s["by_day"]) == 7
    assert s["by_route"][0] == {"name": "POST /plan", "count": 2}
    assert s["by_source"] == {"api": 2, "worker": 1}
    assert s["recent"][0]["error_type"] == "HTTP 503"


def test_오류_기록을_못_읽으면_unavailable():
    class Broken:
        def table(self, _name):
            raise RuntimeError("relation error_logs does not exist")

    assert ops_monitor.error_summary(Broken(), now=NOW)["status"] == "unavailable"
    assert ops_monitor.error_summary(FakeSupabase(), now=NOW)["status"] == "empty"


# ── 가동률 ──

def run(minutes_ago, conclusion):
    return {"created_at": (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conclusion": conclusion, "html_url": f"https://example/{minutes_ago}"}


def test_가동률은_끝난_점검_중_정상_비율이고_취소는_빼고_센다():
    runs = [run(90, "success"), run(75, "failure"), run(60, "failure"), run(45, "success"),
            run(30, "cancelled"), run(15, "success")]
    u = ops_monitor.uptime_from_runs(runs)
    assert u["checks"] == 5 and u["ok"] == 3 and u["uptime_percent"] == 60.0
    assert u["incidents"] == [{"start": runs[1]["created_at"], "end": runs[3]["created_at"], "minutes": 30,
                               "failed_checks": 2, "url": "https://example/75"}]
    assert u["last_result"] == "success"


def test_아직_복구되지_않은_장애는_끝_시각이_비어_있다():
    u = ops_monitor.uptime_from_runs([run(30, "success"), run(15, "timed_out")])
    assert u["incidents"][0]["end"] is None and u["last_result"] == "timed_out"
    assert ops_monitor.uptime_from_runs([])["uptime_percent"] is None


def test_GitHub_실행_기록을_페이지를_넘기며_읽는다():
    pages = [[run(i, "success") for i in range(100)], [run(200, "failure")]]
    seen = []

    def opener(request, timeout):
        seen.append(request.full_url)
        body = {"workflow_runs": [{**r, "event": "schedule", "head_sha": "93b1a5a0ff"} for r in pages[len(seen) - 1]]}
        return io.BytesIO(json.dumps(body).encode())

    runs = ops_monitor.fetch_runs("uptime.yml", NOW - timedelta(days=7), repo="o/r", token="", opener=opener)
    assert len(runs) == 101 and runs[0]["head_sha"] == "93b1a5a"
    assert "actions/workflows/uptime.yml/runs" in seen[0] and "created=%3E%3D2026-09-30" in seen[0]
    assert "page=2" in seen[1]


def test_가동률_요약은_24시간과_7일을_나누고_GitHub_장애면_unavailable():
    runs = [run(60 * 30, "failure"), run(60 * 29, "success"), run(15, "success")]
    u = ops_monitor.uptime_status(NOW, fetch=lambda *_: runs)
    assert u["status"] == "ok" and u["week"]["checks"] == 3 and u["day"]["checks"] == 1
    assert "incidents" not in u["day"] and len(u["week"]["incidents"]) == 1

    ops_monitor._uptime_cache.update(at=0.0, value=None)

    def broken(*_):
        raise OSError("rate limited")

    assert ops_monitor.uptime_status(NOW, fetch=broken)["status"] == "unavailable"


# ── 오류 감시 미들웨어 ──

@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(ops_monitor, "record_error", lambda db, **kw: calls.append(kw) or True)
    return calls


@pytest.fixture
def small_app():
    app = FastAPI()
    app.add_middleware(error_monitor.ErrorMonitorMiddleware)

    @app.get("/boom/{plan_id}")
    def boom(plan_id: str):
        raise RuntimeError(f"plan {plan_id} 저장 실패 owner a@b.com")

    @app.get("/busy")
    def busy():
        raise HTTPException(status_code=503, detail="잠시 후 다시")

    @app.get("/fine")
    def fine():
        return {"ok": True}

    return TestClient(app)


def test_처리되지_않은_예외는_500_과_요청_번호만_돌려주고_기록한다(small_app, recorded):
    res = small_app.get("/boom/3f2b8c1e-1d2a-4c3b-9e8f-0a1b2c3d4e5f")
    assert res.status_code == 500
    body = res.json()
    assert body["request_id"] == res.headers["X-Request-ID"]
    assert "RuntimeError" not in body["detail"] and "a@b.com" not in body["detail"]
    assert recorded == [{
        "source": "api", "route": "/boom/{plan_id}", "method": "GET", "status_code": 500,
        "error_type": "RuntimeError", "message": "plan 3f2b8c1e-1d2a-4c3b-9e8f-0a1b2c3d4e5f 저장 실패 owner a@b.com",
        "request_id": body["request_id"],
    }]   # 가리기는 record_error 가 한다 (위 테스트)


def test_5xx_응답은_기록하고_정상_응답은_기록하지_않는다(small_app, recorded):
    assert small_app.get("/busy").status_code == 503
    ok = small_app.get("/fine")
    assert ok.status_code == 200 and ok.headers["X-Request-ID"]
    assert [(c["route"], c["error_type"]) for c in recorded] == [("/busy", "HTTP 503")]


def test_워커_작업이_실패하면_오류를_기록하고_워커는_계속_돈다(monkeypatch, recorded):
    from workers import notification_worker

    monkeypatch.setattr(notification_worker, "get_supabase_client", lambda: SimpleNamespace())

    def run_before_block(_db):
        raise RuntimeError("알림 테이블 timeout")

    notification_worker._safe(run_before_block)()   # 예외가 밖으로 나오지 않는다
    assert recorded == [{"source": "worker", "route": "worker:run_before_block", "error_type": "RuntimeError",
                         "message": "알림 테이블 timeout"}]


# ── 관리자 운영 상태 ──

def test_관리자_운영_상태는_준비_가동률_오류를_한_번에_준다(monkeypatch):
    from main import app
    from routers import admin
    from utils.auth import get_current_user

    db = FakeSupabase()
    ops_monitor.beat(db)
    db.table("error_logs").insert({"occurred_at": iso(datetime.now(timezone.utc)), "source": "api", "method": "GET",
                                   "route": "/contests", "status_code": 503, "error_type": "HTTP 503",
                                   "message": None, "request_id": "r1"}).execute()
    monkeypatch.setattr(admin, "get_supabase_client", lambda: db)
    monkeypatch.setattr(ops_monitor, "uptime_status", lambda: {"status": "empty"})
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(app_metadata={"role": "admin"})
    try:
        with TestClient(app) as client:
            res = client.get("/admin/ops?days=3")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert res.status_code == 200 and res.headers["Cache-Control"] == "no-store"
    body = res.json()
    assert body["ready"]["checks"] == {"db": "ok", "worker": "ok"}
    assert body["uptime"] == {"status": "empty"}
    assert body["errors"]["total"] == 1 and len(body["errors"]["by_day"]) == 3


# ── 운영 보고서 ──

def test_운영_보고서는_가동률_장애_워크플로_오류를_마크다운으로_만든다():
    from scripts import ops_report

    runs = {
        "uptime.yml": [run(45, "success"), run(30, "failure"), run(15, "success")],
        "deploy-check.yml": [run(60, "success")],
        "plan-jobs.yml": [run(600, "failure"), run(120, "success")],
        "ci.yml": [],
    }

    def fetch(workflow, _since):
        if workflow == "contest-jobs.yml":
            raise OSError("rate limited")
        return runs[workflow]

    db = FakeSupabase()
    db.table("error_logs").insert({"occurred_at": iso(NOW - timedelta(hours=1)), "source": "api", "method": "GET",
                                   "route": "/contests", "status_code": 503, "error_type": "HTTP 503",
                                   "message": None, "request_id": "r1"}).execute()
    report = ops_report.build(7, NOW, fetch=fetch, db=db)
    assert "**가동률** | **66.67%**" in report and "| 장애 | 1건 |" in report
    assert "| 야간 재조정 (03:00) (`plan-jobs.yml`) | 2 | 1 | 1 | 50.0% |" in report
    assert "| 공고 수집 · 추천 (`contest-jobs.yml`) | 읽기 실패 |" in report
    assert "총 **1건** (API 1건)" in report and "`GET /contests`" in report

    assert "아직 점검 기록이 없다" in ops_report.build(7, NOW, fetch=lambda *_: [])


def test_워크플로가_아직_main_에_없으면_기록_없음으로_본다():
    import urllib.error

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    assert ops_monitor.fetch_runs("uptime.yml", NOW, repo="o/r", token="", opener=opener) == []
