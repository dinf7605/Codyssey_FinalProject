"""계정 격리, 즉시 삭제, 제목 기반 추천, 평가 점수 스냅샷."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers.contests import _repository_or_503
from schemas.contest import Contest
from services.contest_recommender import rank_contests, rejection_weight
from services import contest_vector
from services.contest_repository import ContestSearch, SupabaseContestRepository
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user, get_optional_user


class Repository:
    def __init__(self, contest):
        self.contest = contest

    def search(self, filters):
        return [self.contest], 1

    def get(self, contest_id):
        return self.contest if contest_id == self.contest.id else None


CONTEST = Contest(
    id="contest-1", source="wevity", source_id="1", title="대학생 AI 아이디어 공모전",
    host="", fields=[], deadline=None, status="unknown",
    source_url="https://www.wevity.com/?c=find&gbn=view&ix=1",
)


def client_for(db, user_id="user-a"):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[get_optional_user] = lambda: SimpleNamespace(id=user_id)
    app.dependency_overrides[_repository_or_503] = lambda: Repository(CONTEST)
    return TestClient(app)


def test_관심_태그는_본인만_조회하고_즉시_삭제된다():
    db = FakeSupabase()
    client = client_for(db)
    try:
        saved = client.put("/memories/interest-tags", json={"tags": ["AI", "ai", "데이터"]})
        assert saved.status_code == 200
        assert saved.json()["value"] == {"tags": ["AI", "데이터"]}
        assert len(client.get("/memories").json()) == 1

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-b")
        assert client.get("/memories").json() == []
        assert client.delete(f'/memories/{saved.json()["id"]}').status_code == 404

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-a")
        assert client.delete(f'/memories/{saved.json()["id"]}').status_code == 204
        assert client.get("/memories").json() == []
    finally:
        app.dependency_overrides.clear()


def test_제목_일치_추천과_피드백_점수_저장():
    db = FakeSupabase()
    client = client_for(db)
    try:
        result = client.get("/contests/recommendations", params={"tags": "AI"})
        assert result.status_code == 200
        body = result.json()
        assert body["method"] == "title_keywords"
        assert body["items"][0]["contest"]["title"] == CONTEST.title
        assert body["items"][0]["ai_generated"] is False

        response = client.post("/contests/contest-1/feedback", json={"rating": "not_relevant", "reason": "field"})
        assert response.status_code == 200
        assert response.json()["similarity"] == 1
        assert response.json()["rerank_score"] is not None
        assert client.get("/contests/recommendations", params={"tags": "AI"}).json()["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_위비티는_제목만_비교하고_날짜가_없어도_추천한다():
    rows = rank_contests([CONTEST], ["AI"], set(), date(2026, 9, 29))
    assert len(rows) == 1
    assert rows[0]["deadline_score"] == 0.5
    assert rank_contests([CONTEST], ["주최"], set(), date(2026, 9, 29)) == []


def test_거절_기억은_4주마다_절반으로_줄어든다():
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    assert rejection_weight(now.isoformat(), now) == 1
    assert rejection_weight((now - timedelta(days=28)).isoformat(), now) == 0.5
    assert rejection_weight((now - timedelta(days=56)).isoformat(), now) == 0.25


def test_제목만_색인하고_변경없으면_다시_호출하지_않는다():
    db = FakeSupabase()
    db.table("contests").insert({
        "source": "wevity", "title": "AI 공모전", "content_hash": "hash-1",
        "source_url": "https://www.wevity.com/?ix=1", "raw_text": "색인 금지 원문",
        "collected_at": "2026-09-29T00:00:00+00:00",
    }).execute()
    calls = []

    def embed(text):
        calls.append(text)
        return [0.1] * 1536

    assert contest_vector.index_titles(db, embed=embed) == (1, 0)
    assert calls == ["AI 공모전"]
    assert contest_vector.index_titles(db, embed=embed) == (0, 0)
    assert calls == ["AI 공모전"]


def test_벡터_검색은_제목_부분문자열이_없어도_근거있는_공고만_반환한다(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(contest_vector, "enabled", lambda: True)
    monkeypatch.setattr(contest_vector, "vector_candidates", lambda _db, _tags: [
        {"contest_id": CONTEST.id, "similarity": 0.8},
    ])
    client = client_for(db)
    try:
        response = client.get("/contests/recommendations", params={"tags": "로봇"})
        assert response.status_code == 200
        assert response.json()["method"] == "title_vectors"
        assert response.json()["items"][0]["contest"]["id"] == CONTEST.id
    finally:
        app.dependency_overrides.clear()


def test_공개_검색은_기한있는_공고와_링크전용_공고를_함께_조회한다():
    dated = CONTEST.model_copy(update={"id": "dated", "source": "other", "deadline": date(2026, 12, 31), "status": "open"})
    client = MagicMock()
    queries = []
    for row in (dated, CONTEST):
        query = MagicMock()
        for method in ("select", "in_", "gte", "eq", "is_", "order", "limit", "or_"):
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=[row.model_dump(mode="json")], count=1)
        queries.append(query)
    client.table.side_effect = queries
    items, total = SupabaseContestRepository(client).search(ContestSearch(limit=20))
    assert total == 2
    assert [item.id for item in items] == ["dated", "contest-1"]
    queries[1].is_.assert_called_once_with("deadline", "null")
