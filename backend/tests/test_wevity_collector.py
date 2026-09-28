"""위비티 수집기 (FR-CONT-01) — 네트워크 없이 가짜 HTML 로 수집·저장 규칙을 확인한다."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import contests as contests_router
from services import wevity_collector as wc
from tests.fake_supabase import FakeSupabase

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=wc.KST)


def list_html(*items):
    rows = "".join(
        f"""<li><div class="tit"><a href="?c=find&amp;gbn=view&amp;gp=1&amp;ix={ix}">{title}</a>
        <div class="sub-tit">분야 : 웹/모바일/IT</div></div><div class="organ">주최 {ix}</div>
        <div class="day">{day} <span class="dday">접수중</span></div></li>"""
        for ix, title, day in items
    )
    return f"<ul>{rows}</ul>"


def detail_html(title, start, end, homepage="https://example.org/c"):
    return f"""
    <div class="tit-area"><h6 class="tit">{title}</h6></div>
    <ul class="cd-info-list">
      <li><span class="tit">분야</span>웹/모바일/IT, 게임/소프트웨어</li>
      <li><span class="tit">응모대상</span>대학생</li>
      <li><span class="tit">주최/주관</span>테스트 기관</li>
      <li><span class="tit">접수기간</span>{start} ~ {end} <span class="cil-dday">D-10</span></li>
      <li><span class="tit">홈페이지</span><a href="{homepage}">공식</a></li>
    </ul>
    <div id="viewContents">공고 원문 본문 — 저장하면 안 된다</div>"""


class FakeSite:
    """URL → HTML. 요청 순서와 쉬는 시간을 기록한다."""

    def __init__(self, pages):
        self.pages, self.requests, self.sleeps = pages, [], []

    def fetch(self, url):
        self.requests.append(url)
        for key, html in self.pages.items():
            if key in url:
                if isinstance(html, Exception):
                    raise html
                return html
        raise RuntimeError(f"404 {url}")

    def sleep(self, seconds):
        self.sleeps.append(seconds)


def site(**extra):
    return FakeSite({
        "cidx=20": list_html(("101", "AI 공모전", "D-10"), ("102", "마감된 공모전", "D+3"), ("103", "예정 공모전", "D-30")),
        "ix=101": detail_html("AI 공모전", "2026-09-01", "2026-10-08"),
        "ix=103": detail_html("예정 공모전", "2026-10-05", "2026-10-28"),
        **extra,
    })


@pytest.fixture
def db():
    return FakeSupabase()


def test_접수중_공고의_사실_정보만_저장하고_원문은_남기지_않는다(db):
    s = site()

    result = wc.collect(db, categories=[20], fetch=s.fetch, sleep=s.sleep, now=NOW)

    assert (result.saved, result.skipped_closed, result.failed) == (2, 1, 0)
    rows = {r["source_id"]: r for r in db.rows("contests")}
    ai = rows["101"]
    assert ai["source"] == "wevity" and ai["title"] == "AI 공모전" and ai["host"] == "테스트 기관"
    assert ai["fields"] == ["웹/모바일/IT", "게임/소프트웨어"] and ai["eligibility_text"] == "대학생"
    assert (ai["start_date"], ai["deadline"], ai["status"]) == ("2026-09-01", "2026-10-08", "open")
    assert ai["official_url"] == "https://example.org/c" and "ix=101" in ai["source_url"]
    assert ai["raw_text"] is None and ai["content_hash"]
    assert rows["103"]["status"] == "upcoming", "접수 시작 전이면 예정"


def test_요청_사이에_3초씩_쉰다(db):
    s = site()
    wc.collect(db, categories=[20], fetch=s.fetch, sleep=s.sleep, now=NOW)

    assert len(s.requests) == 3  # 목록 1 + 상세 2 (마감 공고는 상세를 받지 않는다)
    assert s.sleeps == [wc.REQUEST_GAP_SECONDS] * 2


def test_이미_저장한_공고는_상세를_다시_받지_않는다(db):
    wc.collect(db, categories=[20], fetch=site().fetch, sleep=lambda _: None, now=NOW)
    s = site()

    result = wc.collect(db, categories=[20], fetch=s.fetch, sleep=lambda _: None, now=NOW)

    assert result.skipped_known == 2 and len(s.requests) == 1
    assert len(db.rows("contests")) == 2, "upsert — 같은 공고가 두 줄이 되지 않는다"


def test_새로고침이면_기존_공고를_덮어쓴다(db):
    wc.collect(db, categories=[20], fetch=site().fetch, sleep=lambda _: None, now=NOW)
    s = site(**{"ix=101": detail_html("AI 공모전 (기한 연장)", "2026-09-01", "2026-10-20")})

    wc.collect(db, categories=[20], refresh=True, fetch=s.fetch, sleep=lambda _: None, now=NOW)

    ai = next(r for r in db.rows("contests") if r["source_id"] == "101")
    assert (ai["title"], ai["deadline"]) == ("AI 공모전 (기한 연장)", "2026-10-20")
    assert len(db.rows("contests")) == 2


def test_상세가_실패해도_나머지는_저장하고_부분_성공으로_남긴다(db):
    s = site(**{"ix=101": RuntimeError("timeout")})

    result = wc.collect(db, categories=[20], fetch=s.fetch, sleep=lambda _: None, now=NOW)

    assert (result.saved, result.failed) == (1, 1)
    run = db.rows("batch_runs")[-1]
    assert (run["job_name"], run["status"], run["collected_count"], run["failed_count"]) == (
        "contest.collect", "partial", 1, 1,
    )


def test_마감일이_지났거나_없는_공고는_넣지_않는다(db):
    s = site(**{"ix=101": detail_html("지난 공고", "2026-08-01", "2026-09-01")})

    result = wc.collect(db, categories=[20], fetch=s.fetch, sleep=lambda _: None, now=NOW)

    assert "101" not in {r["source_id"] for r in db.rows("contests")}
    assert result.skipped_closed == 2


def test_미리보기는_DB_에_쓰지_않는다():
    s = site()
    result = wc.collect(None, categories=[20], dry_run=True, fetch=s.fetch, sleep=lambda _: None, now=NOW)
    assert result.saved == 2


def test_마감_지난_공고는_닫는다(db):
    db.table("contests").insert([
        {"source": "wevity", "source_id": "1", "deadline": "2026-09-27", "status": "open"},
        {"source": "wevity", "source_id": "2", "deadline": "2026-09-28", "status": "open"},
    ]).execute()

    wc.close_expired(db, NOW.date())

    assert [r["status"] for r in db.rows("contests")] == ["closed", "open"]


def test_실행_중이면_겹쳐_돌지_않는다(db):
    db.table("batch_runs").insert({"job_name": wc.JOB_NAME, "status": "running",
                                   "started_at": "2026-09-28T04:30:00+09:00"}).execute()
    assert wc.running(db, NOW)
    assert not wc.running(db, NOW.replace(hour=7))  # 1시간이 지나 멈춘 기록은 무시


# ── 수집 API (POST /contests/collect) ──────────────────

def test_수집_API는_배치_키가_있어야_돈다(db, monkeypatch):
    calls = []
    monkeypatch.setattr(contests_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(wc, "run_daily", lambda d, now: calls.append(now))
    client = TestClient(app)

    monkeypatch.delenv("BATCH_SECRET", raising=False)
    assert client.post("/contests/collect").status_code == 503
    monkeypatch.setenv("BATCH_SECRET", "s3cret")
    assert client.post("/contests/collect", headers={"X-Batch-Key": "wrong"}).status_code == 401
    res = client.post("/contests/collect", headers={"X-Batch-Key": "s3cret"})
    assert res.status_code == 202 and len(calls) == 1
