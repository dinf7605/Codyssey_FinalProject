"""위비티 목록 수집 경계: 20건, 제목·링크·출처, 상세 요청 없음."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import contests as contests_router
from services import wevity_collector as wc
from tests.fake_supabase import FakeSupabase

NOW = datetime(2026, 9, 28, 5, 0, tzinfo=wc.KST)


def list_html(count=25):
    return "<ul>" + "".join(
        f'<li><div class="tit"><a href="?c=find&amp;gbn=view&amp;ix={n}">공모전 {n}</a>'
        f'</div><div class="organ">주최 {n}</div><div class="day">D-10</div></li>'
        for n in range(count)
    ) + "</ul>"


def test_최대_20건이고_상세_페이지를_요청하거나_저장하지_않는다():
    db = FakeSupabase()
    calls = []

    def fetch(url):
        calls.append(url)
        assert "gbn=view" not in url
        return list_html()

    result = wc.collect(db, fetch=fetch, sleep=lambda _: None, now=NOW)
    rows = db.rows("contests")
    assert result.listed == result.saved == len(rows) == 20
    assert len(calls) == 1 and "cidx=22" in calls[0]
    assert all(row["source"] == "wevity" and row["source_url"].startswith("https://www.wevity.com/?") for row in rows)
    assert all(row["host"] == "" and row["fields"] == [] and row["deadline"] is None
               and row["eligibility_text"] is None and row["raw_text"] is None for row in rows)


def test_중복_수집은_추가하지_않는다():
    db = FakeSupabase()
    fetch = lambda _: list_html(2)
    wc.collect(db, fetch=fetch, sleep=lambda _: None, now=NOW)
    result = wc.collect(db, fetch=fetch, sleep=lambda _: None, now=NOW)
    assert result.skipped_known == 2
    assert len(db.rows("contests")) == 2


def test_같은_공고의_제목이_바뀌면_다시_저장한다():
    db = FakeSupabase()
    wc.collect(db, fetch=lambda _: list_html(1), sleep=lambda _: None, now=NOW)
    changed = list_html(1).replace("공모전 0", "수정된 공모전 0")
    result = wc.collect(db, fetch=lambda _: changed, sleep=lambda _: None, now=NOW)
    assert result.saved == 1 and result.skipped_known == 0
    assert len(db.rows("contests")) == 1
    assert db.rows("contests")[0]["title"] == "수정된 공모전 0"


def test_기본_상태에서_실제_네트워크_수집은_시작하지_않는다(monkeypatch):
    monkeypatch.delenv("WEVITY_CRAWLING_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="WEVITY_CRAWLING_ENABLED"):
        wc.collect(FakeSupabase())
    with pytest.raises(RuntimeError, match="비활성화"):
        wc.run_daily(FakeSupabase())


def test_robots_금지_경로는_목록도_요청하지_않는다():
    calls = []
    result = wc.collect(FakeSupabase(), fetch=lambda url: calls.append(url) or list_html(1),
                        allowed=lambda url: False, sleep=lambda _: None, now=NOW)
    assert calls == []
    assert result.saved == 0 and result.failed == 1


def test_수집_API는_설정과_배치키_모두_필요하다(monkeypatch):
    calls = []
    db = FakeSupabase()
    monkeypatch.setattr(contests_router, "get_supabase_client", lambda: db)
    monkeypatch.setattr(wc, "run_daily", lambda d, now: calls.append(now))
    monkeypatch.setenv("BATCH_SECRET", "secret")
    monkeypatch.delenv("WEVITY_CRAWLING_ENABLED", raising=False)
    client = TestClient(app)
    assert client.post("/contests/collect", headers={"X-Batch-Key": "secret"}).status_code == 503
    monkeypatch.setenv("WEVITY_CRAWLING_ENABLED", "true")
    assert client.post("/contests/collect", headers={"X-Batch-Key": "wrong"}).status_code == 401
    assert client.post("/contests/collect", headers={"X-Batch-Key": "secret"}).status_code == 202
    assert len(calls) == 1
