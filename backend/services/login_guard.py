"""로그인 잠금 (FR-AUTH-01 · NFR-SEC-01) — 같은 이메일로 5회 연속 실패하면 60초 동안 막는다.

  - 이메일(소문자) 기준으로 센다. 로그인에 성공하면 다시 0부터
  - 잠금 안내는 가입하지 않은 이메일에도 똑같이 나온다 — 계정이 있는지 드러내지 않는다
  - 서버 메모리에 둔다. 서버를 여러 대 띄우면 대마다 따로 센다 (그 위에 Supabase 자체 요청 제한이 한 겹 더 있다)
"""

from __future__ import annotations

import time
from threading import Lock

MAX_FAILURES = 5
LOCK_SECONDS = 60
MAX_TRACKED = 10_000  # 오래된 기록이 끝없이 쌓이지 않게

_state: dict[str, tuple[int, float]] = {}  # email → (연속 실패 수, 잠금 해제 시각)
_lock = Lock()


def _key(email: str) -> str:
    return (email or "").strip().casefold()


def locked_for(email: str, now: float | None = None) -> int:
    """잠겨 있으면 남은 초, 아니면 0."""
    now = time.monotonic() if now is None else now
    with _lock:
        _, until = _state.get(_key(email), (0, 0.0))
        if until and until > now:
            return max(1, int(until - now + 0.999))
        if until:  # 잠금이 끝났다 — 다시 0부터 센다
            _state.pop(_key(email), None)
        return 0


def record_failure(email: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _lock:
        if len(_state) >= MAX_TRACKED:
            _state.clear()
        failures, _ = _state.get(_key(email), (0, 0.0))
        failures += 1
        _state[_key(email)] = (failures, now + LOCK_SECONDS if failures >= MAX_FAILURES else 0.0)


def record_success(email: str) -> None:
    with _lock:
        _state.pop(_key(email), None)


def reset() -> None:
    """테스트에서만 쓴다."""
    with _lock:
        _state.clear()
