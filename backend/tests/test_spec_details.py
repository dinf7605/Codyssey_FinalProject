"""기능명세서 세부 사항 — 관심 공모전 준비 블록(FR-CONT-07) · 미루기 2회(FR-ALARM-03) · 비밀번호 규칙(FR-JOIN-01)
· AI 고지 재동의(FR-JOIN-03) · 재설정 후 전체 로그아웃(FR-AUTH-03) · AI 하루 비용 한도(FR-ADMIN-02 · FR-GOAL-12).

실제 DB·Claude 없이 FakeSupabase 와 가짜 클라이언트로 본다.
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db import get_db
from main import app
from routers import auth
from schemas.plan import Availability, TimeSlot
from services import ai_budget, goal_limiter, llm, password_policy, replan
from services.plan_store import active_plan_row, plan_blocks, plan_units, save_plan
from services.scheduler import build_schedule
from services.template import template_units
from services.validator import validate_schedule
from tests.fake_supabase import FakeSupabase
from utils.auth import get_current_user

ME = SimpleNamespace(id="00000000-0000-0000-0000-00000000000a", email="me@example.com")
AVAIL = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
START, DEADLINE = date(2026, 10, 5), date(2026, 12, 20)
NOW = datetime(2026, 10, 5, 18, 50)  # 월요일


@pytest.fixture
def db():
    db = FakeSupabase()
    units = template_units("SQLD")
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    save_plan(db, ME.id, goal_title="SQLD", goal_id="cert-sqld", deadline=DEADLINE,
              source="template", units=units, blocks=blocks, availability=AVAIL)
    db.table("contests").insert([
        {"id": "11111111-aaaa", "title": "공공데이터 활용 아이디어 공모전", "deadline": "2026-10-30", "status": "open"},
        {"id": "22222222-bbbb", "title": "곧 마감", "deadline": "2026-10-07", "status": "open"},
        {"id": "33333333-cccc", "title": "목표보다 늦은 마감", "deadline": "2027-03-01", "status": "open"},
    ]).execute()
    return db


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(replan, "now_kst", lambda: NOW)
    app.dependency_overrides[get_current_user] = lambda: ME
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def plan_id(db):
    return active_plan_row(db, ME.id)["id"]


# ── FR-CONT-07 관심 공모전 → D-7 · D-3 준비 블록 ──────

def test_미리보기는_저장하지_않고_D7_D3_자리를_보여준다(client, db):
    before = len(plan_blocks(db, plan_id(db)))
    res = client.post("/contest-interests/preview", json={"contest_id": "11111111-aaaa"})
    assert res.status_code == 200
    body = res.json()
    assert [b["start"][:10] for b in body["blocks"]] == ["2026-10-23", "2026-10-27"]  # 10/30 의 D-7 · D-3
    assert body["conflicts"] == [] and "_placed" not in body
    assert len(plan_blocks(db, plan_id(db))) == before


def test_등록하면_고정된_준비_블록이_생기고_해제하면_지워진다(client, db):
    pid = plan_id(db)
    before = len(plan_blocks(db, pid))
    assert client.post("/contest-interests", json={"contest_id": "11111111-aaaa"}).status_code == 201
    prep = [b for b in plan_blocks(db, pid) if b.unit_id.startswith("contest-")]
    assert len(prep) == 2 and all(b.locked for b in prep)
    assert all("[공모전 준비]" in b.title for b in prep)
    assert validate_schedule(plan_blocks(db, pid), plan_units(db, pid), DEADLINE) == []
    assert client.get("/contest-interests").json()["interests"][0]["prep_blocks"] == 2
    assert client.post("/contest-interests", json={"contest_id": "11111111-aaaa"}).status_code == 409  # 중복

    res = client.delete("/contest-interests/11111111-aaaa")
    assert res.status_code == 200 and res.json()["removed_blocks"] == 2
    assert len(plan_blocks(db, pid)) == before
    assert not [u for u in plan_units(db, pid) if u.id.startswith("contest-")]
    assert client.get("/contest-interests").json()["interests"] == []


def test_해제해도_끝낸_준비_블록은_학습_기록이라_남긴다(client, db):
    pid = plan_id(db)
    client.post("/contest-interests", json={"contest_id": "11111111-aaaa"})
    first = next(r for r in db.rows("plan_blocks") if str(r["unit_key"]).endswith("-d7"))
    first["done"] = True
    assert client.delete("/contest-interests/11111111-aaaa").json()["removed_blocks"] == 1
    assert [b.unit_id for b in plan_blocks(db, pid) if b.unit_id.startswith("contest-")] == [first["unit_key"]]


def test_목표를_끝내면_준비_블록을_남은_목표로_옮긴다(client, db):
    first = plan_id(db)
    client.post("/contest-interests", json={"contest_id": "11111111-aaaa"})
    units = template_units("ADsP")
    blocks = build_schedule(units, AVAIL, START, DEADLINE).blocks
    save_plan(db, ME.id, goal_title="ADsP", goal_id="cert-adsp", deadline=DEADLINE,
              source="template", units=units, blocks=blocks, availability=AVAIL)
    # 공모전 준비 블록이 든 목표를 끝낸다 → 남은 ADsP 일정으로 옮겨진다
    body = client.post(f"/plan/{first}/archive").json()
    assert body["contest_prep"] == {"moved": 1, "unplaced": 0}
    second = plan_id(db)
    assert len([b for b in plan_blocks(db, second) if b.unit_id.startswith("contest-")]) == 2
    assert client.get("/contest-interests").json()["interests"][0]["prep_blocks"] == 2


def test_옮길_목표가_없으면_관심_등록만_남긴다(client, db):
    pid = plan_id(db)
    client.post("/contest-interests", json={"contest_id": "11111111-aaaa"})
    body = client.post(f"/plan/{pid}/archive").json()
    assert body["contest_prep"] == {"moved": 0, "unplaced": 1}
    interest = client.get("/contest-interests").json()["interests"][0]
    assert interest["prep_blocks"] == 0 and interest["plan_id"] is None


def fill_evening(db, pid, day):
    for hour in (19, 20, 21):
        db.table("plan_blocks").insert({
            "plan_id": pid, "unit_key": f"busy-{day}-{hour}", "title": f"채운 블록 {hour}",
            "start_at": f"{day}T{hour}:00:00+09:00", "end_at": f"{day}T{hour}:50:00+09:00",
            "minutes": 50, "locked": True, "done": False,
        }).execute()


def test_정한_날이_꽉_차면_하루_이틀_앞당긴다(client, db):
    fill_evening(db, plan_id(db), "2026-10-23")  # D-7(금)
    body = client.post("/contest-interests/preview", json={"contest_id": "11111111-aaaa"}).json()
    assert body["conflicts"] == []
    first = body["blocks"][0]
    assert first["start"][:10] == "2026-10-22" and first["shifted_days"] == 1
    assert body["blocks"][1]["shifted_days"] == 0


def test_앞당겨도_자리가_없으면_그_블록만_빼고_등록한다(client, db):
    pid = plan_id(db)
    for day in ("2026-10-21", "2026-10-22", "2026-10-23"):  # D-7 과 그 앞 이틀
        fill_evening(db, pid, day)
    body = client.post("/contest-interests/preview", json={"contest_id": "11111111-aaaa"}).json()
    [conflict] = body["conflicts"]
    assert conflict["day"] == "2026-10-23" and conflict["blocks"]
    assert "차 있어요" in conflict["reason"]
    # 예전엔 409 로 등록 자체를 막았다 — 이제 D-3 만 넣고 관심 등록(마감 알림)은 한다 (10-05 사전 점검 3번)
    res = client.post("/contest-interests", json={"contest_id": "11111111-aaaa"})
    assert res.status_code == 201 and [b["start"][:10] for b in res.json()["blocks"]] == ["2026-10-27"]
    assert client.get("/contest-interests").json()["interests"][0]["prep_blocks"] == 1


def test_자리를_못_찾은_이유는_쉬는_날과_찬_날을_나눠_말한다():
    from services.contest_interest import _conflict_reason
    weekdays = Availability(slots=[TimeSlot(weekday=w, start="19:00", end="21:00") for w in range(5)], rest_weekday=6)
    # D-7 이 일요일(10/25) — 토·일은 공부하는 날이 아니고 금요일만 차 있다
    assert _conflict_reason(date(2026, 10, 25), date(2026, 10, 5), weekdays) == (
        "10/24(토)·10/25(일)은 공부하는 날이 아니고, 10/23(금)은 이미 다른 블록으로 차 있어요."
    )
    # 오늘이 그날이라 앞당길 날이 없으면 그날만 말한다
    assert _conflict_reason(date(2026, 10, 25), date(2026, 10, 25), weekdays) == "10/25(일)은 공부하는 날이 아니에요."


def test_마감이_가깝거나_목표_기한_밖이면_거절한다(client):
    assert client.post("/contest-interests/preview", json={"contest_id": "22222222-bbbb"}).status_code == 409
    res = client.post("/contest-interests/preview", json={"contest_id": "33333333-cccc"})
    assert res.status_code == 409 and "기한" in res.json()["detail"]
    assert client.post("/contest-interests/preview", json={"contest_id": "nope"}).status_code == 404


# ── FR-ALARM-03 미루기는 블록당 2번 ───────────────────

def test_같은_블록은_두_번까지만_미룰_수_있다(client, db):
    pid = plan_id(db)
    target = plan_blocks(db, pid)[0].id
    assert client.post(f"/plan/blocks/{target}/postpone").status_code == 200
    assert client.post(f"/plan/blocks/{target}/postpone").status_code == 200
    third = client.post(f"/plan/blocks/{target}/postpone")
    assert third.status_code == 409 and "2번" in third.json()["detail"]
    assert replan.postpone_counts(db, ME.id, [target]) == {target: 2}


# ── FR-JOIN-01 비밀번호 추가 규칙 ─────────────────────

@pytest.mark.parametrize("password, email, nickname", [
    ("Password1!", "", ""),         # 흔한 비밀번호 + 숫자·기호
    ("P@ssw0rd!!", "", ""),         # 기호로 바꾼 것
    ("Qwerty123!", "", ""),
    ("Minsu2026!!", "minsu@example.com", ""),   # 이메일 아이디
    ("공부왕Study1!", "x@example.com", "공부왕"),  # 닉네임
])
def test_흔하거나_개인정보가_들어간_비밀번호는_거부(password, email, nickname):
    assert password_policy.problem(password, email=email, nickname=nickname)


@pytest.mark.parametrize("password", ["Study2026!!", "Tq7#vLm2pz!", "북극곰Zx9!kq"])
def test_평범하지_않은_비밀번호는_통과(password):
    assert password_policy.problem(password, email="test@example.com", nickname="테스트") is None


@pytest.fixture
def auth_env(monkeypatch):
    db = MagicMock()
    auth_client = MagicMock()
    monkeypatch.setattr(auth, "get_supabase_client", lambda: db)
    monkeypatch.setattr(auth, "new_auth_client", lambda: auth_client)
    api = FastAPI()
    api.include_router(auth.router)
    api.dependency_overrides[get_current_user] = lambda: ME
    with TestClient(api) as c:
        yield c, db, auth_client


def signup(**changes):
    data = dict(email="test@example.com", nickname="테스트", password="Study2026!!",
                agree_privacy=True, agree_ai_notice=True, agree_marketing=False)
    return {**data, **changes}


def test_가입은_흔한_비밀번호를_Supabase_전에_막는다(auth_env):
    client, db, auth_client = auth_env
    res = client.post("/auth/signup", json=signup(password="Password1!"))
    assert res.status_code == 400 and "흔하게" in res.json()["detail"]
    auth_client.auth.sign_up.assert_not_called()


def test_가입하면_지금_AI_고지_버전을_남긴다(auth_env):
    client, db, auth_client = auth_env
    auth_client.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="u1", identities=[{"id": "i"}]),
        session=SimpleNamespace(access_token="a", refresh_token="r"),
    )
    assert client.post("/auth/signup", json=signup()).status_code == 200
    assert db.table.return_value.insert.call_args.args[0]["ai_notice_version"] == auth.AI_NOTICE_VERSION


def test_재설정하면_모든_기기에서_로그아웃한다(auth_env):
    client, db, auth_client = auth_env
    res = client.post("/auth/reset-password", json={"access_token": "a", "refresh_token": "r", "new_password": "Tq7#vLm2pz!"})
    assert res.status_code == 200
    auth_client.auth.sign_out.assert_called_once_with({"scope": "global"})
    weak = client.post("/auth/reset-password", json={"access_token": "a", "refresh_token": "r", "new_password": "Password1!"})
    assert weak.status_code == 400


# ── FR-JOIN-03 고지 문구가 바뀌면 재동의 ──────────────

def test_고지_버전이_다르면_다시_동의를_받는다(monkeypatch):
    fake = FakeSupabase()
    fake.table("users").insert({"user_id": ME.id, "agree_ai_notice": True, "ai_notice_version": "v0"}).execute()
    monkeypatch.setattr(auth, "get_supabase_client", lambda: fake)
    api = FastAPI()
    api.include_router(auth.router)
    api.dependency_overrides[get_current_user] = lambda: ME
    c = TestClient(api)
    assert c.get("/auth/consent").json()["needs_ai_notice"] is True
    assert c.post("/auth/consent/ai-notice").json()["needs_ai_notice"] is False
    assert fake.rows("users")[0]["ai_notice_version"] == auth.AI_NOTICE_VERSION
    assert c.get("/auth/consent").json()["needs_ai_notice"] is False


# ── AI 하루 비용 한도 · 비회원 IP 한도 ────────────────

def calls(n, model="claude-sonnet-4"):
    return [{"feature": "plan.decompose", "model": model, "created_at": "2026-10-05T01:00:00+00:00"} for _ in range(n)]


def test_비용은_모델별_예상치로_세고_80퍼센트부터_경고(monkeypatch):
    monkeypatch.setenv("AI_DAILY_BUDGET_USD", "1")
    fake = FakeSupabase()
    fake.table("ai_call_logs").insert(calls(20)).execute()        # 0.6 달러
    assert ai_budget.status(fake, NOW)["state"] == "ok"
    fake.table("ai_call_logs").insert(calls(10)).execute()        # 0.9
    assert ai_budget.status(fake, NOW)["state"] == "warning"
    fake.table("ai_call_logs").insert(calls(50, "claude-haiku-4")).execute()  # +0.1 = 1.0
    s = ai_budget.status(fake, NOW)
    assert s["state"] == "blocked" and s["calls"] == 80 and s["estimated"] is True
    # 어제 기록은 세지 않는다 (한국 시각 자정 = 전날 15:00 UTC)
    old = FakeSupabase()
    old.table("ai_call_logs").insert([{**c, "created_at": "2026-10-04T14:59:00+00:00"} for c in calls(100)]).execute()
    assert ai_budget.status(old, NOW)["calls"] == 0


def test_한도를_넘으면_AI_클라이언트를_주지_않는다(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(ai_budget, "_cached_state", lambda: "blocked")
    assert llm.get_client() is None


def test_80퍼센트부터_비회원_추천을_먼저_막는다(monkeypatch):
    goal_limiter._reset_for_tests()
    monkeypatch.setattr(ai_budget, "_cached_state", lambda: "warning")
    with pytest.raises(goal_limiter.RateLimitExceeded):
        goal_limiter.consume("s1", is_member=False)
    assert goal_limiter.consume("s1", is_member=True).limit == -1  # 회원은 그대로


def test_세션을_바꿔도_같은_IP는_넉넉한_한도에서_막힌다(monkeypatch):
    goal_limiter._reset_for_tests()
    monkeypatch.setattr(ai_budget, "_cached_state", lambda: "ok")
    for i in range(goal_limiter.IP_DAILY_LIMIT):
        goal_limiter.consume(f"session-{i}", is_member=False, ip="203.0.113.7")
    with pytest.raises(goal_limiter.RateLimitExceeded):
        goal_limiter.consume("session-new", is_member=False, ip="203.0.113.7")
    goal_limiter.consume("session-new", is_member=False, ip="198.51.100.1")  # 다른 IP 는 괜찮다
    assert not any("203.0.113.7" in key for key in goal_limiter._calls)  # IP 원문은 남기지 않는다
    goal_limiter._reset_for_tests()


# ── 실사용 피드백 (10-02) ─────────────────────────────

def _candidate(recommended_weeks, weeks_left):
    from datetime import timedelta

    from schemas.goal import FeasibleCandidate
    return FeasibleCandidate(
        goal_id="cert-sqld", title="SQLD", field="데이터", standard_hours=60,
        deadline=(date.today() + timedelta(weeks=weeks_left)).isoformat(),
        weekly_hours=19, min_weeks=recommended_weeks / 1.3, recommended_weeks=recommended_weeks, feasible=True,
    )


def test_계산과_반대로_말하는_AI_추천_이유는_버린다():
    from services.goal_recommender import reason_consistent
    roomy = _candidate(4, 6)   # 4주 필요 · 6주 남음 — 여유
    assert not reason_consistent("시험까지 6주로 예상 기간보다 짧으니 빠듯할 수 있습니다.", roomy)  # 10-02 실제 문장
    assert reason_consistent("데이터에 관심이 있으시다면 약 4주면 준비할 수 있어 여유가 있어요.", roomy)
    assert not reason_consistent("약 8주면 충분히 준비할 수 있어요.", roomy)  # 카드에 없는 숫자
    tight = _candidate(9, 6)   # 9주 필요 · 6주 남음 — 빠듯
    assert not reason_consistent("시간 여유가 충분합니다.", tight)
    assert reason_consistent("시험까지 6주라 빠듯하게 준비해야 해요.", tight)
    # 빠듯한데 낙관만 하는 문장 (10-02 test05: 4주 필요 · 3주 남음인데 "3주 내 준비 완료가 가능")
    assert not reason_consistent("주당 18시간 집중 학습하면 6주 내 준비 완료가 가능합니다.", tight)


def test_AI_이유가_틀리면_템플릿으로_바꾼다(monkeypatch):
    from services import goal_recommender
    roomy = _candidate(4, 6)
    monkeypatch.setattr(goal_recommender, "search_catalog_ai", lambda tags, k, on_call=None: ([roomy], "claude"))
    monkeypatch.setattr(goal_recommender, "evaluate_all", lambda cands, hours: cands)
    monkeypatch.setattr(goal_recommender, "_make_client", lambda: (object(), "m"))
    monkeypatch.setattr(goal_recommender, "_ai_reason", lambda *a: "예상 기간보다 짧아 빠듯해요.")
    roomy.similarity = 0.9
    [card], *_ = goal_recommender.recommend_goals(["데이터"], 19)
    assert card.ai_generated is False and "빠듯" not in card.reason


def test_공모전_준비_블록은_중간_목표에서_뺀다():
    from services import alarms
    from services.plan_store import to_db_time
    blocks = [
        {"unit_key": "u1", "title": "1단원", "start_at": to_db_time(datetime(2026, 10, 6, 19)), "done": True},
        {"unit_key": "contest-1a2b3c4d-d7", "title": "[공모전 준비] X · D-7", "start_at": to_db_time(datetime(2026, 10, 7, 19)), "done": False},
        {"unit_key": "u2", "title": "2단원", "start_at": to_db_time(datetime(2026, 10, 13, 19)), "done": False},
    ]
    assert alarms.next_checkpoint(blocks, date(2026, 10, 7)) == (date(2026, 10, 18), "2단원")
