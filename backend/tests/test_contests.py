from datetime import date, datetime

from fastapi.testclient import TestClient

from main import app
from routers.contests import _repository_or_503
from schemas.contest import Contest
from services.contest_repository import ContestSearch, PreparationHours


SAMPLE_CONTEST = Contest(
    id="contest-1",
    source="fixture",
    source_id="111155",
    title="AI 공모전",
    host="테스트 기관",
    fields=["과학/공학"],
    eligibility_text="대학생 및 일반인",
    start_date=date(2026, 9, 1),
    deadline=date(2026, 12, 31),
    status="open",
    source_url="https://example.org/source",
    official_url="https://example.org/official",
    summary="AI 서비스를 만드는 공모전",
    collected_at=datetime(2026, 9, 23, 5, 0),
)


class FakeContestRepository:
    def __init__(self):
        self.last_search: ContestSearch | None = None

    def search(self, filters: ContestSearch):
        self.last_search = filters
        return [SAMPLE_CONTEST], 1

    def get(self, contest_id: str):
        return SAMPLE_CONTEST if contest_id == SAMPLE_CONTEST.id else None

    def get_preparation_hours(self, fields: list[str]):
        return PreparationHours(40.0, "exact")


def test_search_contests_passes_filters_and_returns_items():
    repository = FakeContestRepository()
    app.dependency_overrides[_repository_or_503] = lambda: repository
    try:
        response = TestClient(app).get(
            "/contests",
            params={"query": "AI", "field": "과학/공학", "sort": "latest", "limit": 5},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "AI 공모전"
    assert repository.last_search is not None
    assert repository.last_search.query == "AI"
    assert repository.last_search.field == "과학/공학"
    assert repository.last_search.sort == "latest"
    assert repository.last_search.limit == 5


def test_estimate_contest_preparation():
    app.dependency_overrides[_repository_or_503] = FakeContestRepository
    try:
        response = TestClient(app).post(
            "/contests/contest-1/estimate",
            json={"weekly_hours": 8},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["standard_hours"] == 40.0
    assert body["weeks_needed"] == 5
    assert body["hours_source"] == "exact"
    assert body["estimated"] is False


def test_estimate_rejects_zero_weekly_hours():
    app.dependency_overrides[_repository_or_503] = FakeContestRepository
    try:
        response = TestClient(app).post(
            "/contests/contest-1/estimate",
            json={"weekly_hours": 0},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_estimate_returns_404_for_unknown_contest():
    app.dependency_overrides[_repository_or_503] = FakeContestRepository
    try:
        response = TestClient(app).post(
            "/contests/missing/estimate",
            json={"weekly_hours": 8},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


class RecordingRepository(FakeContestRepository):
    """get 이 돌려줄 공고를 바꾸고, 준비시간 조회에 쓴 분야를 기록한다."""

    def __init__(self, **update):
        super().__init__()
        self.contest = SAMPLE_CONTEST.model_copy(update=update)
        self.fields = None

    def get(self, contest_id):
        return self.contest if contest_id == "contest-1" else None

    def get_preparation_hours(self, fields):
        self.fields = fields
        return PreparationHours(40.0, "global_median")


def _estimate(repository, body):
    app.dependency_overrides[_repository_or_503] = lambda: repository
    try:
        return TestClient(app).post("/contests/contest-1/estimate", json=body)
    finally:
        app.dependency_overrides.clear()


def test_wevity_estimate_uses_collected_deadline_and_fields():
    repository = RecordingRepository(source="wevity", fields=["웹/모바일/IT"])

    # 수집한 마감일이 있으면 사용자가 보낸 값은 쓰지 않는다
    response = _estimate(repository, {"weekly_hours": 8, "deadline": "2026-10-01", "field": "다른 분야"})

    assert response.status_code == 200
    assert response.json()["weeks_needed"] == 5
    assert repository.fields == ["웹/모바일/IT"]


def test_link_only_row_without_deadline_needs_user_deadline():
    repository = RecordingRepository(source="wevity", deadline=None, fields=[])

    assert _estimate(repository, {"weekly_hours": 8}).status_code == 422
    supplied = _estimate(repository, {"weekly_hours": 8, "deadline": "2026-12-31", "field": "과학/공학"})

    assert supplied.status_code == 200
    assert supplied.json()["weeks_needed"] == 5
    assert repository.fields == ["과학/공학"], "분야가 비어 있을 때만 사용자가 적은 분야를 쓴다"
