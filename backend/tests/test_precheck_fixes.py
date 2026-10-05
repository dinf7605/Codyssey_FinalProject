"""10-05 사전 점검(AI 사용자 역할)에서 찾아 고친 규칙들 — docs/user-test/리포트.md 0절."""

from datetime import date

from routers.contests import CANDIDATE_LIMIT, recommendation_candidates
from schemas.contest import Contest
from services.contest_repository import ContestSearch, PreparationHours
from services.contest_service import estimate_preparation
from services.decomposer import parse_units, short_title


def contest(i: int, title: str, deadline=date(2026, 11, 1)) -> Contest:
    return Contest(id=f"c{i}", source="wevity", source_id=str(i), title=title, host="주최",
                   deadline=deadline, status="open", source_url="https://example.org")


class Repo:
    """최신 공고 20건은 키워드와 무관하고, 키워드로 찾아야 데이터 공모전이 나온다."""

    def __init__(self):
        self.latest = [contest(i, f"최신 공고 {i}") for i in range(30)]
        self.data = [contest(100, "빅데이터 경진대회"), contest(101, "AI 활용 데이터 분석 공모전")]

    def search(self, filters: ContestSearch):
        if filters.query:
            hits = [c for c in self.data if filters.query in c.title]
            return hits[: filters.limit], len(hits)
        return self.latest[: filters.limit], len(self.latest)


# 2번 — AI 추천 후보가 최신 20건뿐이라 키워드에 맞는 공고를 놓쳤다
def test_추천_후보는_키워드가_든_공고를_먼저_넣고_최신_공고로_채운다():
    ids = [c.id for c in recommendation_candidates(Repo(), ["데이터"])]
    assert ids[:2] == ["c100", "c101"]
    assert len(ids) == CANDIDATE_LIMIT and len(set(ids)) == len(ids)


def test_키워드가_없으면_예전처럼_최신_공고만():
    assert [c.id for c in recommendation_candidates(Repo(), [])] == [f"c{i}" for i in range(CANDIDATE_LIMIT)]


# 4번 — 필요한 주를 올림(28일)해 비교해서 26.25일이면 되는 공고를 '어렵습니다'로 봤다
def test_준비_기간은_날짜로_판정한다():
    c = contest(1, "제천시 데이터 분석 공모전", deadline=date(2026, 11, 1))
    result = estimate_preparation(c, 8, PreparationHours(30, "exact"), today=date(2026, 10, 5))
    assert result.days_left == 27 and result.weeks_needed == 4
    assert result.verdict != "impossible"
    too_short = estimate_preparation(c, 8, PreparationHours(30, "exact"), today=date(2026, 10, 10))
    assert too_short.verdict == "impossible"  # 22일 < 26.25일


# 2차 — '하루 최대 1시간'의 1시간 칸에 90분 단위가 하나도 놓이지 않았다
def test_가장_긴_칸보다_긴_단위는_칸에_맞춰_나눠_놓는다():
    from schemas.plan import Availability, StudyUnit, TimeSlot
    from services.scheduler import build_schedule
    from services.scope import check_scope

    hour = Availability(slots=[TimeSlot(weekday=w, start="22:00", end="23:00") for w in range(5)], rest_weekday=6)
    units = [StudyUnit(id=f"u{i}", title=f"단원 {i}", estimated_minutes=90) for i in range(3)]
    plan = build_schedule(units, hour, date(2026, 10, 6), date(2026, 10, 24))
    assert plan.unplaced == []
    assert all(b.minutes <= 60 for b in plan.blocks) and sum(b.minutes for b in plan.blocks) == 270
    assert check_scope(units, hour, date(2026, 10, 6), date(2026, 10, 24))["available_minutes"] > 0


def test_세션_연장은_새_토큰을_돌려주고_잘못된_토큰은_401(monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from main import app
    from routers import auth

    class FakeAuth:
        def refresh_session(self, token):
            if token != "good":
                raise RuntimeError("invalid")
            return SimpleNamespace(session=SimpleNamespace(access_token="new-a", refresh_token="new-r"),
                                   user=SimpleNamespace(id="u1"))

    monkeypatch.setattr(auth, "new_auth_client", lambda: SimpleNamespace(auth=FakeAuth()))
    client = TestClient(app)
    res = client.post("/auth/refresh", json={"refresh_token": "good"})
    assert res.status_code == 200 and res.json() == {"access_token": "new-a", "refresh_token": "new-r", "user_id": "u1"}
    assert client.post("/auth/refresh", json={"refresh_token": "old"}).status_code == 401


def test_추천_이유_조사():
    from services.goal_recommender import _and
    assert (_and("마케팅"), _and("데이터"), _and("SQL")) == ("과", "와", "와(과)")


# 12번 — AI 가 묶은 단위 이름이 너무 길었다
def test_묶은_단위_이름을_줄인다():
    long = "관계와 조인의 이해 + Null 속성의 이해 + 본질식별자와 인조식별자 (개념 반복 포함)"
    assert short_title(long) == "관계와 조인의 이해·Null 속성의 이해 외 1개"
    assert short_title("엔터티 + 속성") == "엔터티·속성"
    assert short_title("데이터 모델의 이해") == "데이터 모델의 이해"
    [unit] = parse_units({"units": [{"id": "u01", "title": long, "estimated_minutes": 90}]})
    assert unit.title == "관계와 조인의 이해·Null 속성의 이해 외 1개"
