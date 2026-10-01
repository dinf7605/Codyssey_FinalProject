"""비회원 AI 호출 제한 (FR-GOAL-12) — 담당 B.

세션 키 기준으로 24시간 3회까지만 AI 활용 엔드포인트(추천·매칭·유사분야 제안)를
쓸 수 있게 막는다. 원래는 서버 메모리에만 들고 있어 재배포·재시작(특히 uvicorn
--reload로 코드 바꿀 때마다)하면 초기화되는 문제가 있었다 — 완전한 해결은
PostgreSQL/Redis로 옮겨야 하지만(루트 README "실시간 집계: PostgreSQL(1차) →
Redis(확장 시)"), 그전까지 최소한 재시작에도 살아남도록 로컬 파일에 같이
적어 둔다 (담당 B, 2026-09-25).

같은 브라우저가 세션 키만 바꿔 한도를 피하지 못하게 IP 도 함께 센다. IP 는 원문을 두지 않고
솔트를 섞은 해시로만 키를 만들며, 24시간이 지난 기록은 세션 키와 똑같이 지운다 (FR-GOAL-12).
학교·회사처럼 여러 사람이 한 IP 를 쓰므로 IP 한도는 세션 한도보다 넉넉하게 둔다.
AI 하루 비용 한도의 80% 를 넘으면 비회원 추천을 먼저 막는다 (services/ai_budget.py).

회원은 이 제한을 받지 않는다. 다만 지금은 로그인 붙기 전이라 프론트가 보내는
is_member 값을 그대로 믿는다 — 인증이 붙으면 서버가 토큰으로 직접 판단하도록 바꾼다
(E 작업 대기 중).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time

from schemas.goal import NONMEMBER_DAILY_LIMIT, NONMEMBER_LIMIT_WINDOW_HOURS, UsageInfo

WINDOW_SECONDS = NONMEMBER_LIMIT_WINDOW_HOURS * 3600
IP_DAILY_LIMIT = NONMEMBER_DAILY_LIMIT * 5  # 한 IP(공용 와이파이 등)에서 24시간 동안
# .env 에 없으면 프로세스마다 새로 만든다 — 재시작하면 IP 기록은 이어지지 않지만 원문 IP 를 되돌릴 수 없다
_IP_SALT = os.getenv("IP_HASH_SALT") or secrets.token_hex(16)

# 재시작해도 최근 호출 기록을 잃지 않도록 같이 적어 두는 파일.
# 실사용 데이터가 아니라 임시 집계용이라 커밋 대상에서 제외한다 (.gitignore).
_STATE_PATH = os.path.join(os.path.dirname(__file__), "_goal_limiter_state.json")

# session_id -> 호출 타임스탬프 목록. 데모·테스트 규모(팀 5명 실사용자 5~10명)에서는
# 이 정도 메모리 구조로 충분하다.
_calls: dict[str, list[float]] = {}
_loaded = False


class RateLimitExceeded(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
        for session_id, timestamps in data.items():
            if isinstance(timestamps, list):
                _calls[session_id] = [t for t in timestamps if isinstance(t, (int, float))]


def _persist() -> None:
    """새 호출을 기록할 때만 파일에 다시 쓴다 — 조회(usage_for)는 건드리지 않는다."""
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(_calls, f)
    except OSError:
        pass  # 파일 저장에 실패해도 요청 자체는 막지 않는다


def _prune(session_id: str, now: float) -> list[float]:
    _load_once()
    timestamps = [t for t in _calls.get(session_id, []) if now - t < WINDOW_SECONDS]
    _calls[session_id] = timestamps
    return timestamps


def ip_key(ip: str | None) -> str | None:
    if not ip:
        return None
    return "ip:" + hashlib.sha256(f"{_IP_SALT}:{ip}".encode()).hexdigest()[:32]


def usage_for(session_id: str, is_member: bool) -> UsageInfo:
    if is_member:
        return UsageInfo(used=0, limit=-1, remaining=-1)
    timestamps = _prune(session_id, time.time())
    used = len(timestamps)
    return UsageInfo(used=used, limit=NONMEMBER_DAILY_LIMIT, remaining=max(NONMEMBER_DAILY_LIMIT - used, 0))


def consume(session_id: str, is_member: bool, ip: str | None = None) -> UsageInfo:
    """AI 호출 하나를 소비한다. 한도를 넘었으면 RateLimitExceeded 를 던진다.

    인기 목록·공모전 검색은 이 함수를 거치지 않는다 — 한도에 걸려도 계속 쓸 수 있어야 한다
    (FR-GOAL-12 세부사항).
    """
    if is_member:
        return UsageInfo(used=0, limit=-1, remaining=-1)

    from services import ai_budget

    if ai_budget.guests_blocked():
        raise RateLimitExceeded(
            "오늘은 AI 사용량이 많아 비회원 AI 추천을 잠시 멈췄어요. 로그인하면 계속 이용할 수 있고, "
            "인기 목표 목록과 공모전 검색은 그대로 쓸 수 있어요."
        )

    now = time.time()
    timestamps = _prune(session_id, now)
    by_ip = ip_key(ip)
    ip_times = _prune(by_ip, now) if by_ip else []
    if len(ip_times) >= IP_DAILY_LIMIT:
        raise RateLimitExceeded(
            "이 네트워크에서 비회원 AI 추천을 많이 받아 잠시 막았어요. 로그인하면 계속 이용할 수 있어요. "
            "인기 목표 목록과 공모전 검색은 계속 이용할 수 있어요."
        )

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
    if by_ip:
        _calls[by_ip] = ip_times + [now]
    _persist()
    return UsageInfo(
        used=len(timestamps),
        limit=NONMEMBER_DAILY_LIMIT,
        remaining=max(NONMEMBER_DAILY_LIMIT - len(timestamps), 0),
    )


def _reset_for_tests() -> None:
    """테스트에서만 쓴다 — 전역 상태와 저장 파일을 모두 비운다."""
    global _loaded
    _calls.clear()
    _loaded = True  # 파일에서 다시 불러오지 않게 막는다
    try:
        os.remove(_STATE_PATH)
    except OSError:
        pass
