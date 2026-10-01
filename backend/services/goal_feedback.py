"""추천 피드백(goal_feedback) 조회 — FR-GOAL-08, 담당 B.

"관심없음"을 최근에 남긴 목표는 FEEDBACK_DISMISS_COOLDOWN_DAYS 기간 동안만 추천에서
빼고, 기간이 지나면 별도 삭제 작업(배치·크론) 없이 자동으로 다시 추천 대상에
포함한다 — 조회 시점에 created_at 을 기준으로 거르기만 하면 되기 때문이다. DB 행
자체는 지우지 않는다(분석용으로 남겨 둔다).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db import get_supabase_client
from schemas.goal import FEEDBACK_DISMISS_COOLDOWN_DAYS


def recently_dismissed_goal_ids(session_id: str, user_id: str | None) -> set[str]:
    """최근 FEEDBACK_DISMISS_COOLDOWN_DAYS일 안에 "관심없음"으로 남긴 goal_id 목록.

    회원이면 user_id로, 아니면 session_id로 본인 기록만 본다. DB가 아직 설정되지
    않았거나 조회가 실패해도 빈 집합을 돌려줘 추천 흐름을 막지 않는다(POST
    /goal/feedback과 같은 원칙).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=FEEDBACK_DISMISS_COOLDOWN_DAYS)).isoformat()
    try:
        query = get_supabase_client().table("goal_feedback").select("goal_id").eq("interested", False)
        query = query.eq("user_id", user_id) if user_id else query.eq("session_id", session_id)
        rows = query.gte("created_at", cutoff).execute().data or []
    except Exception:  # noqa: BLE001 - DB 미설정·일시 장애여도 추천 흐름을 막지 않는다
        return set()
    return {r["goal_id"] for r in rows if r.get("goal_id")}
