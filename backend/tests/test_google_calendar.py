"""구글 캘린더 연동 (FR-PLAN-01) — 바쁜 시간 읽기 · 토큰 폐기 · 바쁜 시간을 피한 배치. 실제 구글 없이 본다."""

from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import google_calendar as gc
from schemas.plan import Availability, StudyUnit, TimeSlot
from services.scheduler import build_schedule, subtract_busy

MON = date(2026, 10, 5)
AVAIL = Availability(slots=[TimeSlot(weekday=0, start="19:00", end="22:00")], rest_weekday=None)


def units(n, minutes=60):
    return [StudyUnit(id=f"u{i}", title=f"단원 {i}", estimated_minutes=minutes, prerequisites=[]) for i in range(n)]


# ── 배치 ──────────────────────────────────────────────

def test_바쁜_시간을_창에서_잘라낸다():
    windows = [(MON, datetime(2026, 10, 5, 19), datetime(2026, 10, 5, 22))]
    cut = subtract_busy(windows, [(datetime(2026, 10, 5, 20), datetime(2026, 10, 5, 21))])
    assert cut == [(MON, datetime(2026, 10, 5, 19), datetime(2026, 10, 5, 20)),
                   (MON, datetime(2026, 10, 5, 21), datetime(2026, 10, 5, 22))]
    assert subtract_busy(windows, [(datetime(2026, 10, 5, 18), datetime(2026, 10, 5, 23))]) == []


def test_바쁜_시간에는_놓지_않고_결과에도_넣지_않는다():
    busy = [(datetime(2026, 10, 5, 19), datetime(2026, 10, 5, 20, 30))]
    plan = build_schedule(units(1), AVAIL, MON, date(2026, 10, 5), busy=busy)
    [block] = plan.blocks
    assert block.start == datetime(2026, 10, 5, 20, 30)
    assert all(b.unit_id.startswith("u") for b in plan.blocks)


def test_바쁜_시간이_없으면_예전과_같다():
    assert build_schedule(units(2), AVAIL, MON, date(2026, 10, 5)).blocks == \
        build_schedule(units(2), AVAIL, MON, date(2026, 10, 5), busy=[]).blocks


def test_일정_API는_busy_를_받아_피해서_놓는다():
    client = TestClient(app)
    body = {
        "units": [u.model_dump() for u in units(1)], "availability": AVAIL.model_dump(),
        "start_day": "2026-10-05", "deadline": "2026-10-05",
        "busy": [{"start": "2026-10-05T10:00:00Z", "end": "2026-10-05T11:30:00Z"}],  # 한국 19:00~20:30
    }
    res = client.post("/plan/schedule", json=body).json()
    assert res["blocks"][0]["start"] == "2026-10-05T20:30:00"
    assert any("구글 캘린더" in note for note in res["notes"])


# ── 연동 API ──────────────────────────────────────────

@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")


def test_설정이_없으면_503(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert TestClient(app).get("/calendar/connect", params={"state": "x" * 20}).status_code == 503


def test_동의_주소는_바쁜_시간_권한만_묻고_토큰을_오래_두지_않는다(configured):
    url = TestClient(app).get("/calendar/connect", params={"state": "s" * 20}).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [gc.SCOPE] and q["access_type"] == ["online"]
    assert q["redirect_uri"] == ["http://localhost:3000/calendar/callback"] and q["state"] == ["s" * 20]


class Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeGoogle:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(url)
        if url == gc.TOKEN_URL:
            return Resp({"access_token": "tok"})
        if url == gc.FREEBUSY_URL:
            return Resp({"calendars": {"primary": {"busy": [
                {"start": "2026-10-05T10:00:00Z", "end": "2026-10-05T11:00:00Z"}]}}})
        return Resp({})


def test_바쁜_시간을_한국_시각으로_돌려주고_토큰을_폐기한다(configured, monkeypatch):
    google = FakeGoogle()
    monkeypatch.setattr(gc.httpx, "post", google.post)

    res = TestClient(app).post("/calendar/busy", json={
        "code": "4/0Afake-code", "start_day": "2026-10-05", "end_day": "2026-10-20"})

    assert res.status_code == 200
    assert res.json()["busy"] == [{"start": "2026-10-05T19:00:00", "end": "2026-10-05T20:00:00"}]
    assert google.calls == [gc.TOKEN_URL, gc.FREEBUSY_URL, gc.REVOKE_URL]


def test_만료된_코드는_400(configured, monkeypatch):
    def broken(url, **kwargs):
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(gc.httpx, "post", broken)
    res = TestClient(app).post("/calendar/busy", json={
        "code": "4/0Afake-code", "start_day": "2026-10-05", "end_day": "2026-10-20"})
    assert res.status_code == 400 and "test-secret" not in res.text
