"""계정 격리, 즉시 삭제, 제목 기반 추천, 평가 점수 스냅샷."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers import contests as contest_routes
from routers.contests import _repository_or_503
from schemas.contest import Contest
from services.contest_recommender import rank_contests, rejection_weight
from services import contest_claude
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


def test_키워드_추천은_관심_태그가_여러_개여도_하나만_겹치면_나온다():
    # 비율에 0.62 를 걸던 때는 태그 2개부터 0건이었다
    for tags in (["AI", "데이터"], ["AI", "데이터", "디자인"]):
        rows = rank_contests([CONTEST], tags, set(), date(2026, 9, 29))
        assert len(rows) == 1
        assert rows[0]["matching_tags"] == ["AI"]
        assert rows[0]["ai_generated"] is False


def test_키워드_추천은_더_많이_겹친_공고가_앞에_온다():
    both = CONTEST.model_copy(update={"id": "both", "title": "AI 데이터 분석 공모전"})
    rows = rank_contests([CONTEST, both], ["AI", "데이터"], set(), date(2026, 9, 29))
    assert [row["contest"].id for row in rows] == ["both", CONTEST.id]


def test_클로드_추천의_이유_문장은_클로드_판단임을_밝힌다():
    rows = rank_contests([CONTEST], ["로봇"], set(), date(2026, 9, 29), similarities={CONTEST.id: 0.8})
    assert rows[0]["reason"].startswith("Claude가")
    assert rows[0]["matching_tags"] == ["로봇"]
    assert "입력한 관심 태그 로봇 기준" in rows[0]["reason"]
    assert "제목에 ‘로봇’ 포함" not in rows[0]["reason"]
    assert rank_contests([CONTEST], ["로봇"], set(), date(2026, 9, 29), similarities={CONTEST.id: 0.5}) == []


def test_분야_키워드_추천은_제목에_있다고_잘못_설명하지_않는다():
    contest = CONTEST.model_copy(update={"fields": ["과학/공학"]})
    row = rank_contests([contest], ["과학"], set(), date(2026, 9, 29))[0]
    assert "공고 분야에" in row["reason"]


def test_등록되지_않은_분야는_같은_분류군_중앙값을_쓴다():
    db = FakeSupabase()
    db.table("preparation_time_standards").insert([
        {"field": "웹/모바일/IT", "category_group": "tech", "standard_hours": 80, "active": True},
        {"field": "과학/공학", "category_group": "tech", "standard_hours": 60, "active": True},
        {"field": "영상/UCC/사진", "category_group": "media", "standard_hours": 40, "active": True},
    ]).execute()
    repository = SupabaseContestRepository(db)
    result = repository.get_preparation_hours(["앱/모바일"])
    assert (result.hours, result.source) == (70, "group_median")
    assert repository.get_preparation_hours(["인공지능"]).source == "global_median"


def test_클로드_호출은_관리자_AI_기록에_남는다(monkeypatch):
    db = FakeSupabase()

    def fake_score(_candidates, _tags, on_call=None):
        on_call("claude", 120, "")
        return {CONTEST.id: 0.8}

    monkeypatch.setattr(contest_claude, "score_titles", fake_score)
    client = client_for(db)
    try:
        assert client.get("/contests/recommendations", params={"tags": "로봇"}).status_code == 200
    finally:
        app.dependency_overrides.clear()
    logs = db.rows("ai_call_logs")
    assert [(row["feature"], row["source"], row["user_id"]) for row in logs] == [
        ("contest.recommend", "claude", "user-a")
    ]


def test_거절_기억은_4주마다_절반으로_줄어든다():
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    assert rejection_weight(now.isoformat(), now) == 1
    assert rejection_weight((now - timedelta(days=28)).isoformat(), now) == 0.5
    assert rejection_weight((now - timedelta(days=56)).isoformat(), now) == 0.25


def test_지난주_공고는_최대_3건만_반복하고_다음_순위로_채운다():
    contests = [CONTEST.model_copy(update={"id": str(i), "title": f"AI 공모전 {i}"}) for i in range(6)]
    rows = rank_contests(contests, ["AI"], set(), date(2026, 9, 29),
                         previous_ids={str(i) for i in range(4)})
    assert [row["contest"].id for row in rows] == ["0", "1", "2", "4", "5"]


def test_주간_추천_배치는_사용자별_실패를_분리하고_기록한다(monkeypatch):
    db = FakeSupabase()
    db.table("users").insert([{"user_id": "u1"}, {"user_id": "u2"}]).execute()
    called = []

    def recommend(_repository, *, tags, user, db):
        called.append(user.id)
        if user.id == "u2":
            raise RuntimeError("한 사용자의 추천 실패")

    monkeypatch.setattr(contest_routes, "recommend_contests", recommend)
    contest_routes.run_weekly_recommendations(db, datetime(2026, 9, 28, 9, tzinfo=timezone.utc))
    assert called == ["u1", "u2"]
    run = db.rows("batch_runs")[0]
    assert (run["status"], run["collected_count"], run["failed_count"]) == ("partial", 1, 1)


def test_클로드_추천은_제목_부분문자열이_없어도_검증한_공고만_반환한다(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(contest_claude, "score_titles", lambda _candidates, _tags, **_: {CONTEST.id: 0.8})
    client = client_for(db)
    try:
        response = client.get("/contests/recommendations", params={"tags": "로봇"})
        assert response.status_code == 200
        assert response.json()["method"] == "title_claude"
        assert response.json()["items"][0]["contest"]["id"] == CONTEST.id
        assert response.json()["items"][0]["ai_generated"] is True
    finally:
        app.dependency_overrides.clear()


def test_클로드가_빈_결과를_주면_키워드_추천으로_우회하지_않는다(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(contest_claude, "score_titles", lambda _candidates, _tags, **_: {})
    client = client_for(db)
    try:
        result = client.get("/contests/recommendations", params={"tags": "AI"})
        assert result.status_code == 200
        assert result.json()["method"] == "title_claude"
        assert result.json()["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_클로드_장애면_제목_키워드로_복구한다(monkeypatch):
    db = FakeSupabase()
    monkeypatch.setattr(contest_claude, "score_titles", lambda _candidates, _tags, **_: None)
    client = client_for(db)
    try:
        result = client.get("/contests/recommendations", params={"tags": "AI"})
        assert result.status_code == 200
        assert result.json()["method"] == "title_keywords"
        assert result.json()["items"][0]["ai_generated"] is False
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
