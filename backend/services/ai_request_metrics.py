"""학습 분해의 실제 Messages 요청만 기록한다. 프롬프트·응답 본문은 저장하지 않는다."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import logging
import os
import time
from uuid import uuid4

logger = logging.getLogger(__name__)
_current: ContextVar[list[dict] | None] = ContextVar("ai_request_metrics", default=None)
TOKEN_FIELDS = (
    "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
)


def _field(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _count(value):
    # bool·음수·누락을 실제 사용량 0으로 취급하지 않는다.
    return value if type(value) is int and value >= 0 else None


def _error_kind(exc):
    if isinstance(exc, TimeoutError) or "Timeout" in type(exc).__name__:
        return "timeout"
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "authentication"
    if type(status) is int and 400 <= status <= 599:
        return "http_error"
    return "request_error"


def tracked_create(client, **kwargs):
    """원래 응답·예외를 그대로 전달한다. 저장은 루프 종료 후 한 번 수행한다."""
    rows = _current.get()
    if rows is None:
        return client.messages.create(**kwargs)
    row = {
        "id": str(uuid4()),
        "attempt_no": len(rows) + 1,
        "model": str(kwargs.get("model", ""))[:128],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "succeeded": False,
        "error_kind": None,
        **dict.fromkeys(TOKEN_FIELDS),
    }
    started = time.monotonic()
    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:
        row["error_kind"] = _error_kind(exc)
        raise
    else:
        row["succeeded"] = True
        # 사용량 누락은 무료라는 뜻이 아니다. 게이트웨이에서 받은 값만 저장한다.
        try:
            usage = _field(response, "usage")
            for name in TOKEN_FIELDS:
                row[name] = _count(_field(usage, name))
        except Exception:
            pass  # 기록 때문에 정상 응답을 버리지 않는다
        return response
    finally:
        row["latency_ms"] = max(0, int((time.monotonic() - started) * 1000))
        rows.append(row)


def _persist_rows(rows):
    if not rows or os.getenv("AI_REQUEST_METRICS_ENABLED", "").strip() != "1":
        return
    from db import get_supabase_client
    get_supabase_client().table("ai_request_logs").insert(rows).execute()


def track_decomposition(function):
    """일반·스트림에서 공통으로 쓰는 분해 함수를 감싼다. 실행별 기록을 격리한다."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        rows = []
        token = _current.set(rows)
        outcome = "error"
        try:
            result = function(*args, **kwargs)
            source = getattr(result, "source", None)
            outcome = source if source in ("agent", "partial", "template") else "error"
            return result
        finally:
            _current.reset(token)
            if rows:
                run_id = str(uuid4())
                for row in rows:
                    row.update(run_id=run_id, feature="plan.decompose", outcome=outcome)
                try:
                    _persist_rows(rows)
                except Exception:
                    # 예외 본문·키·사용자 입력은 서버 로그에도 출력하지 않는다.
                    logger.warning("AI request metrics were not saved (plan.decompose).")
    return wrapped
