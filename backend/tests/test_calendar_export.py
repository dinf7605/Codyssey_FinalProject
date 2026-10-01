"""내 캘린더로 내보내기 (FR-PLAN-08) — .ics 파일 내용과 API."""

from datetime import date, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from db import get_db
from main import app
from schemas.plan import Availability, Block, TimeSlot
from services import replan
from services.calendar_export import build_ics
from services.plan_store import active_plan_row, plan_blocks, save_plan
from services.scheduler import build_schedule
from services.template import template_units
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")
NOW = datetime(2026, 10, 6, 12, 0)


def block(id_, start, *, done=False, title="SQL 기본, 조인; 정리"):
    return Block(id=id_, unit_id="u", title=title, start=start, end=start.replace(hour=start.hour + 1),
                 minutes=60, done=done)


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def test_오늘_이후의_안_한_블록만_UTC로_담는다():
    ics = build_ics("SQLD", [
        block("past", datetime(2026, 10, 5, 19, 0)),
        block("done", datetime(2026, 10, 7, 19, 0), done=True),
        block("next", datetime(2026, 10, 7, 19, 0)),
    ], NOW)
    lines = unfold(ics)

    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"
    assert lines.count("BEGIN:VEVENT") == 1
    assert "UID:next@studypace" in lines
    assert "DTSTART:20261007T100000Z" in lines  # 한국 19:00 = UTC 10:00
    assert "SUMMARY:SQL 기본\\, 조인\\; 정리" in lines


def test_긴_줄은_75바이트로_접는다():
    ics = build_ics("아주 긴 목표 이름" * 10, [block("b", datetime(2026, 10, 7, 19, 0), title="가" * 60)], NOW)
    assert all(len(line.encode("utf-8")) <= 75 for line in ics.split("\r\n"))
    assert "SUMMARY:" + "가" * 60 in unfold(ics)


def test_API는_내_진행_중_계획만_내려준다(monkeypatch):
    db = FakeSupabase()
    units = template_units("SQLD")
    avail = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
    blocks = build_schedule(units, avail, date(2026, 10, 7), date(2026, 12, 20)).blocks
    save_plan(db, ME.id, goal_title="SQLD", goal_id="cert-sqld", deadline=date(2026, 12, 20),
              source="template", units=units, blocks=blocks, availability=avail)
    monkeypatch.setattr(replan, "now_kst", lambda: NOW)
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        plan_id = active_plan_row(db, ME.id)["id"]
        res = client.get(f"/plan/{plan_id}/calendar.ics")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/calendar")
        assert "attachment" in res.headers["content-disposition"]
        assert res.text.count("BEGIN:VEVENT") == len(plan_blocks(db, plan_id))
        assert client.get("/plan/not-mine/calendar.ics").status_code == 404
    finally:
        app.dependency_overrides.clear()
