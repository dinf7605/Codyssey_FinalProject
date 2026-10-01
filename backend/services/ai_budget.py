"""AI 하루 비용 한도 (FR-ADMIN-02 · FR-GOAL-12 · NFR-COST-01).

오늘(한국 시각) ai_call_logs 기록 수에 모델별 1회 예상 비용을 곱해 오늘 쓴 금액을 어림한다.
게이트웨이가 토큰·청구액을 돌려주지 않아 정확한 금액이 아니라 '예상치'다 — 한도는 넉넉하게 잡는다.

  - 한도의 80% 를 넘으면 비회원 AI 추천을 먼저 막는다 (services/goal_limiter.consume)
  - 100% 를 넘으면 새 AI 호출을 막는다 (services/llm.get_client 가 None → 각 기능이 규칙·템플릿으로 대체)
  - 관리자 화면(GET /admin/ai-budget)이 상태를 보여 준다 — 80% 부터 경고

한도는 .env 의 AI_DAILY_BUDGET_USD (기본 5달러). 0 이하면 한도를 쓰지 않는다.
DB 를 못 읽으면 막지 않는다 — 집계 장애로 서비스 전체를 멈추지 않는다.
"""

from __future__ import annotations

import os
import time as _time
from datetime import datetime, timedelta

DEFAULT_BUDGET_USD = 5.0
GUEST_BLOCK_RATIO = 0.8
CACHE_SECONDS = 60  # 호출마다 DB 를 세지 않는다

# 1회 예상 비용 (달러). 학습 분해는 도구 호출 3~5번 + 긴 답이라 크게 잡는다.
COST_BY_MODEL = (("sonnet", 0.03), ("opus", 0.15), ("haiku", 0.002))
DEFAULT_COST = 0.01

_cache: dict = {"at": 0.0, "value": None}


def budget_usd() -> float:
    try:
        return float(os.getenv("AI_DAILY_BUDGET_USD", DEFAULT_BUDGET_USD))
    except ValueError:
        return DEFAULT_BUDGET_USD


def cost_of(model: str | None) -> float:
    name = (model or "").lower()
    return next((cost for key, cost in COST_BY_MODEL if key in name), DEFAULT_COST)


def _today_start_utc_iso(now_kst: datetime) -> str:
    start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    return (start - timedelta(hours=9)).isoformat() + "+00:00"


def status(db=None, now_kst: datetime | None = None) -> dict:
    """오늘 예상 사용액과 상태. state: ok · warning(80%~) · blocked(100%~) · off(한도 없음)."""
    from services.plan_store import KST

    now_kst = now_kst or datetime.now(KST).replace(tzinfo=None)
    limit = budget_usd()
    if db is None:
        from db import get_supabase_client
        db = get_supabase_client()
    rows = (
        db.table("ai_call_logs").select("feature,model")
        .gte("created_at", _today_start_utc_iso(now_kst)).execute().data
    )
    spent = round(sum(cost_of(r.get("model")) for r in rows), 4)
    by_feature: dict[str, int] = {}
    for r in rows:
        by_feature[r.get("feature") or "unknown"] = by_feature.get(r.get("feature") or "unknown", 0) + 1
    if limit <= 0:
        state = "off"
    elif spent >= limit:
        state = "blocked"
    elif spent >= limit * GUEST_BLOCK_RATIO:
        state = "warning"
    else:
        state = "ok"
    return {"state": state, "spent_usd": spent, "limit_usd": limit, "calls": len(rows),
            "by_feature": by_feature, "guest_block_ratio": GUEST_BLOCK_RATIO, "estimated": True}


def _cached_state() -> str:
    now = _time.monotonic()
    if _cache["value"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["value"]
    try:
        value = status()["state"]
    except Exception:  # noqa: BLE001 - DB 미설정·장애면 막지 않는다
        value = "ok"
    _cache.update(at=now, value=value)
    return value


def ai_blocked() -> bool:
    """새 AI 호출을 막아야 하는가 (한도 100%)."""
    return budget_usd() > 0 and _cached_state() == "blocked"


def guests_blocked() -> bool:
    """비회원 AI 추천을 막아야 하는가 (한도 80%)."""
    return budget_usd() > 0 and _cached_state() in ("warning", "blocked")


def reset_cache() -> None:
    _cache.update(at=0.0, value=None)
