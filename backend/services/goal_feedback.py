"""추천 피드백(goal_feedback) 조회 — FR-GOAL-08, 담당 B.

"관심없음"을 최근에 남긴 목표는 일정 기간만 추천에서 빼고, 기간이 지나면 별도
삭제 작업(배치·크론) 없이 자동으로 다시 추천 대상에 포함한다 — 조회 시점에
기록 시각 기준으로 거르기만 하면 되기 때문이다. 당시엔 관심없었지만 한참 지나
다시 관심사가 되거나 기간 부담이 없어질 수 있는 경우를 고려한 설계다.

회원과 비회원은 저장 위치가 다르다.
  - 회원: Supabase goal_feedback 테이블에 user_id로 저장. FEEDBACK_DISMISS_COOLDOWN_DAYS
    (30일) 동안 제외한다. DB 행 자체는 지우지 않는다(분석용으로 남겨 둔다).
  - 비회원: Supabase에는 저장하지 않는다 — session_id를 서버 DB에 남기고 싶지 않아서다.
    대신 goal_limiter.py(FR-GOAL-12)와 같은 방식으로 서버 로컬 파일에 session_id
    기준으로 저장한다. 제외 기간도 30일이 아니라 비회원 한도 리셋 주기
    (NONMEMBER_LIMIT_WINDOW_HOURS, 24시간)와 맞춘다 — 비회원은 애초에 그 주기로
    "새로 시작"하는 사용자라고 보기 때문이다.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from db import get_supabase_client
from schemas.goal import FEEDBACK_DISMISS_COOLDOWN_DAYS, NONMEMBER_LIMIT_WINDOW_HOURS

NONMEMBER_WINDOW_SECONDS = NONMEMBER_LIMIT_WINDOW_HOURS * 3600

# 비회원 "관심없음" 임시 저장 파일 — goal_limiter.py의 _goal_limiter_state.json과
# 같은 원칙(재시작에도 살아남되, 실사용 DB 데이터는 아니므로 커밋 대상에서 제외).
_STATE_PATH = os.path.join(os.path.dirname(__file__), "_goal_feedback_state.json")

# session_id -> {goal_id: 기록 시각(epoch seconds)}
_dismissed: dict[str, dict[str, float]] = {}
_loaded = False


def _load_once() -> None:
    """프로세스에서 처음 쓸 때 한 번만 파일에서 이전 기록을 불러온다."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if isinstance(data, dict):
        for session_id, goals in data.items():
            if isinstance(goals, dict):
                _dismissed[session_id] = {
                    goal_id: ts for goal_id, ts in goals.items() if isinstance(ts, (int, float))
                }


def _persist() -> None:
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(_dismissed, f)
    except OSError:
        pass  # 파일 저장에 실패해도 요청 자체는 막지 않는다


def record_nonmember_dismiss(session_id: str, goal_id: str) -> None:
    """비회원이 "관심없음"을 누른 목표를 로컬 파일에 기록한다."""
    _load_once()
    _dismissed.setdefault(session_id, {})[goal_id] = time.time()
    _persist()


def cancel_nonmember_dismiss(session_id: str, goal_id: str) -> None:
    """비회원이 남긴 "관심없음" 기록을 취소(삭제)한다. 기록이 없어도 조용히 끝난다."""
    _load_once()
    _dismissed.get(session_id, {}).pop(goal_id, None)
    _persist()


def _nonmember_dismissed_goal_ids(session_id: str) -> set[str]:
    """최근 NONMEMBER_LIMIT_WINDOW_HOURS 시간 안에 "관심없음"을 남긴 goal_id 목록."""
    _load_once()
    now = time.time()
    goals = _dismissed.get(session_id, {})
    return {goal_id for goal_id, ts in goals.items() if now - ts < NONMEMBER_WINDOW_SECONDS}


def recently_dismissed_goal_ids(session_id: str, user_id: str | None) -> set[str]:
    """최근 "관심없음"으로 남긴 goal_id 목록.

    회원(user_id 있음)이면 Supabase goal_feedback 테이블을 FEEDBACK_DISMISS_COOLDOWN_DAYS
    (30일) 기준으로 조회하고, 비회원이면 로컬 파일을 NONMEMBER_LIMIT_WINDOW_HOURS
    (24시간) 기준으로 조회한다. DB가 아직 설정되지 않았거나 조회가 실패해도 빈 집합을
    돌려줘 추천 흐름을 막지 않는다(POST /goal/feedback과 같은 원칙).
    """
    if user_id:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=FEEDBACK_DISMISS_COOLDOWN_DAYS)
        ).isoformat()
        try:
            rows = (
                get_supabase_client()
                .table("goal_feedback")
                .select("goal_id")
                .eq("interested", False)
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .execute()
                .data
                or []
            )
        except Exception:  # noqa: BLE001
            return set()
        return {r["goal_id"] for r in rows if r.get("goal_id")}

    return _nonmember_dismissed_goal_ids(session_id)


def recently_dismissed_candidates(session_id: str, user_id: str | None) -> list:
    """최근 "관심없음"으로 남긴 목표를 제목·분야까지 붙여서 돌려준다.

    "관심없음 목록 보기" 화면(FR-GOAL-08)에서 쓴다 — recently_dismissed_goal_ids가
    주는 goal_id만으로는 화면에 제목을 못 보여주니, 카탈로그에서 조회해 붙인다.
    """
    from services.goal_catalog import by_ids  # 순환 import 방지 — 지역 임포트

    ids = recently_dismissed_goal_ids(session_id, user_id)
    if not ids:
        return []
    catalog = by_ids(ids)
    return [catalog[goal_id] for goal_id in ids if goal_id in catalog]


def _reset_for_tests() -> None:
    """테스트에서만 쓴다 — 전역 상태와 저장 파일을 모두 비운다."""
    global _loaded
    _dismissed.clear()
    _loaded = True  # 파일에서 다시 불러오지 않게 막는다
    try:
        os.remove(_STATE_PATH)
    except OSError:
        pass
