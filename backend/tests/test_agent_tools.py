"""학습 분해 에이전트 도구 (담당 C) — 목업 대신 DB·팀 서비스에서 읽는지 확인한다.

커리큘럼은 마이그레이션 009 의 시드를 그대로 읽어 가짜 DB 에 넣는다 — 시드 자체도 함께 검사된다.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from schemas.plan import Availability, TimeSlot
from services.agent_tools import DB_UNAVAILABLE, run_tool
from services.decomposer import decompose_goal
from services.goal_catalog import _CATALOG
from tests.fake_supabase import FakeSupabase

SEED = Path(__file__).resolve().parent.parent / "migrations" / "009_curriculum.sql"
ROW = re.compile(
    r"\('([^']*)', '([^']*)',\s*(\d+), '([^']*)', '([^']*)', (\d+), (true|false), '([^']*)', (null|'[^']*')\)"
)


def seed_rows() -> list[dict]:
    return [
        {
            "goal_id": g, "goal_title": t, "position": int(p), "subject": s, "topic": tp,
            "standard_minutes": int(m), "is_review": r == "true", "source": src,
            "source_url": None if url == "null" else url.strip("'"), "verified": False,
        }
        for g, t, p, s, tp, m, r, src, url in ROW.findall(SEED.read_text(encoding="utf-8"))
    ]


@pytest.fixture
def db():
    db = FakeSupabase()
    db.table("curriculum_units").insert(seed_rows()).execute()
    return db


# ── 시드 ──────────────────────────────────────────────

def test_시드는_목표_카탈로그와_같은_id를_쓰고_규칙을_지킨다():
    rows = seed_rows()
    assert len(rows) == 24 + 33 + 13, "SQL 과 파서가 어긋나면 여기서 잡힌다"
    catalog_ids = {c["goal_id"] for c in _CATALOG}
    by_goal: dict[str, list[int]] = {}
    for r in rows:
        assert r["goal_id"] in catalog_ids
        assert 30 <= r["standard_minutes"] <= 120
        by_goal.setdefault(r["goal_id"], []).append(r["position"])
    for positions in by_goal.values():
        assert positions == list(range(1, len(positions) + 1)), "순서는 1부터 빈틈없이"


# ── search_curriculum ─────────────────────────────────

def test_목표_id로_과목별_출제_범위를_돌려준다(db):
    out = run_tool("search_curriculum", {"goal_id": "cert-sqld", "query": "전체", "k": 3}, {"db": db})

    assert out["goal_id"] == "cert-sqld"
    assert [c["chapter"] for c in out["chunks"]] == [
        "데이터 모델링의 이해", "데이터 모델과 SQL", "SQL 기본", "SQL 활용", "관리 구문", "기출·복습",
    ]
    assert sum(len(c["topics"]) for c in out["chunks"]) == 33, "k 와 상관없이 범위 전체를 준다"
    assert out["chunks"][0]["topics"][0] == {"title": "데이터 모델의 이해", "minutes": 60, "review": False}
    assert out["chunks"][0]["verified"] is False


def test_온보딩_목표처럼_id가_custom이면_이름으로_찾는다(db):
    out = run_tool("search_curriculum", {"goal_id": "custom", "query": "SQLD (SQL 개발자) 출제 범위", "k": 5}, {"db": db})
    assert out["goal_id"] == "cert-sqld"

    out = run_tool("search_curriculum", {"goal_id": "custom", "query": "정보처리기사 필기", "k": 5}, {"db": db})
    assert out["goal_id"] == "cert-info-eng"


def test_커리큘럼이_없는_목표는_추정으로_표시하라고_안내한다(db):
    out = run_tool("search_curriculum", {"goal_id": "cert-toeic", "query": "토익", "k": 5}, {"db": db})
    assert out["chunks"] == [] and "estimated=true" in out["note"]


def test_DB가_없어도_도구는_멈추지_않는다():
    # conftest 가 Supabase 환경변수를 지워 두었다
    out = run_tool("search_curriculum", {"goal_id": "cert-sqld", "query": "x", "k": 1})
    assert out["chunks"] == [] and out["note"] == DB_UNAVAILABLE


# ── estimate_effort ───────────────────────────────────

def test_커리큘럼_항목이면_권장_시간을_쓴다(db):
    out = run_tool("estimate_effort", {"units": ["SQL 활용 - 윈도우 함수", "나만의 정리 노트 만들기"],
                                       "level": "intermediate"},
                   {"db": db, "goal_id": "custom", "goal_title": "SQLD (SQL 개발자)"})["estimates"]
    assert out[0] == {"unit": "SQL 활용 - 윈도우 함수", "minutes": 90, "basis": "curriculum"}
    assert out[1]["basis"] == "heuristic" and 30 <= out[1]["minutes"] <= 120


def test_초보는_시간을_더_잡되_120분을_넘기지_않는다(db):
    def est(level):
        return run_tool("estimate_effort", {"units": ["윈도우 함수", "통계 분석"], "level": level},
                        {"db": db})["estimates"]  # 목표를 모르면 전체 커리큘럼에서 찾는다

    assert est("beginner")[0]["minutes"] > est("intermediate")[0]["minutes"]
    assert est("beginner")[1]["minutes"] == 120  # 120 * 1.2 → 상한


# ── 나머지 도구 ───────────────────────────────────────

AVAIL = Availability(slots=[TimeSlot(weekday=1, start="20:00", end="22:00")], rest_weekday=6)


def test_빈_시간은_이번_요청의_사용자_가용시간이다():
    out = run_tool("get_available_slots", {"from_date": "2026-10-01", "to_date": "2026-10-31", "min_minutes": 30},
                   {"availability": AVAIL})
    assert out["slots"] == [{"weekday": 1, "start": "20:00", "end": "22:00"}]

    empty = run_tool("get_available_slots", {"from_date": "x", "to_date": "y", "min_minutes": 30})
    assert empty["slots"] == [] and "입력하지 않았습니다" in empty["note"]


def test_목표_후보는_팀_목표_카탈로그에서_찾는다():
    out = run_tool("get_goal_catalog", {"interest_tags": ["sql"], "k": 3})
    assert out["candidates"][0]["goal_id"] == "cert-sqld"
    assert run_tool("get_goal_catalog", {"interest_tags": [], "k": 2})["candidates"], "태그가 없으면 인기 목표"


def test_공모전_검색이_실패해도_오류만_돌려준다():
    out = run_tool("search_contests", {"query": "데이터", "deadline_before": "2026-12-31", "k": 3})
    assert "error" in out and out["note"] == DB_UNAVAILABLE


def test_에이전트는_사용자_가용시간을_도구로_받는다():
    seen = []

    class Client:
        def __init__(self):
            self.messages = self
            self.step = 0

        def create(self, **kwargs):
            self.step += 1
            if self.step == 1:
                return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(
                    type="tool_use", name="get_available_slots", id="t1",
                    input={"from_date": "2026-10-01", "to_date": "2026-10-31", "min_minutes": 30})])
            seen.append(json.loads(kwargs["messages"][-1]["content"][0]["content"]))
            units = [{"id": "u01", "title": "윈도우 함수", "estimated_minutes": 90, "prerequisites": [], "estimated": False}]
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps({"units": units}))])

    result = decompose_goal("SQLD", "cert-sqld", availability=AVAIL, client=Client(), model="m")

    assert result.source == "agent"
    assert seen[0]["slots"] == [{"weekday": 1, "start": "20:00", "end": "22:00"}]
