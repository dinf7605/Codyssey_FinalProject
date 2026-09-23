"""비회원 AI 호출 제한 (FR-GOAL-12) — 담당 B.

세션 키 기준으로 24시간 3회까지만 AI 활용 엔드포인트(추천·매칭·유사분야 제안)를
쓸 수 있게 막는다. 지금은 서버 메모리에만 들고 있어 재배포하면 초기화된다 —
Redis 로 옮기기 전까지의 임시 구현이다 (루트 README "실시간 집계: PostgreSQL(1차)
→ Redis(확장 시)" 와 같은 단계적 접근).

회원은 이 제한을 받지 않는다. 다만 지금은 로그인 붙기 전이라 프론트가 보내는
is_member 값을 그대로 믿는다 — 인증이 붙으면 서버가 토큰으로 직접 판단하도록 바꾼다.
"""

from __future__ import annotations

import time

from schemas.goal import NONMEMBER_DAILY_LIMIT, NONMEMBER_LIMIT_WINDOW_HOURS, UsageInfo

WINDOW_SECONDS = NONMEMBER_LIMIT_WINDOW_HOURS * 3600

# session_id -> 호출 타임스탬프 목록. 데모·테스트 규모(팀 5명 실사용자 5~10명)에서는
# 이 정도 메모리 구조로 충분하다.
_calls: dict[str, list[float]] = {}


class RateLimitExceeded(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _prune(session_id: str, now: float) -> list[float]:
    timestamps = [t for t in _calls.get(session_id, []) if now - t < WINDOW_SECONDS]
    _calls[session_id] = timestamps
    return timestamps


def usage_for(session_id: str, is_member: bool) -> UsageInfo:
    if is_member:
        return UsageInfo(used=0, limit=-1, remaining=-1)
    timestamps = _prune(session_id, time.time())
    used = len(timestamps)
    return UsageInfo(used=used, limit=NONMEMBER_DAILY_LIMIT, remaining=max(NONMEMBER_DAILY_LIMIT - used, 0))


def consume(session_id: str, is_member: bool) -> UsageInfo:
    """AI 호출 하나를 소비한다. 한도를 넘었으면 RateLimitExceeded 를 던진다.

    인기 목록·공모전 검색은 이 함수를 거치지 않는다 — 한도에 걸려도 계속 쓸 수 있어야 한다
    (FR-GOAL-12 세부사항).
    """
    if is_member:
        return UsageInfo(used=0, limit=-1, remaining=-1)

    now = time.time()
    timestamps = _prune(session_id, now)

    if len(timestamps) >= NONMEMBER_DAILY_LIMIT:
        oldest = min(timestamps)
        hours_left = max((oldest + WINDOW_SECONDS - now) / 3600, 0)
        raise RateLimitExceeded(
            f"비회원은 24시간 동안 AI 추천을 {NONMEMBER_DAILY_LIMIT}번까지 받을 수 있어요. "
            f"약 {hours_left:.0f}시간 후 다시 시도해 주세요. "
            "인기 목표 목록과 공모전 검색은 계속 이용할 수 있어요."
        )

    timestamps.append(now)
    _calls[session_id] = timestamps
    return UsageInfo(
        used=len(timestamps),
        limit=NONMEMBER_DAILY_LIMIT,
        remaining=max(NONMEMBER_DAILY_LIMIT - len(timestamps), 0),
    )


def _reset_for_tests() -> None:
    """테스트에서만 쓴다 — 전역 상태를 비운다."""
    _calls.clear()
