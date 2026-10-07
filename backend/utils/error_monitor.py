"""API 오류 감시 미들웨어 (평가 #3 보완, 10-07) — 5xx 응답과 처리되지 않은 예외를 남긴다.

  - 서버 로그(Railway Logs): 모든 5xx 한 줄씩, 처리되지 않은 예외는 traceback 까지
  - error_logs (services/ops_monitor.record_error): 경로 틀 · 상태 코드 · 오류 유형 · 가린 메시지 · request_id
  - 모든 응답에 X-Request-ID — 사용자가 오류를 알려 오면 이 값으로 로그를 찾는다
  - 처리되지 않은 예외는 사용자에게 traceback 대신 짧은 안내와 request_id 만 돌려준다

DB 쓰기는 응답을 붙잡지 않게 스레드로 보낸다 (dispatch). 순수 ASGI 로 짜서 BackgroundTasks · 스트리밍 응답을 건드리지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from services import ops_monitor

logger = logging.getLogger("studypace.errors")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[오류] %(asctime)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def dispatch(fn) -> None:
    """기록 쓰기를 스레드로 보낸다 — 응답을 붙잡지 않게. 테스트는 이 함수를 바꿔 바로 실행한다."""
    try:
        asyncio.get_running_loop().run_in_executor(None, fn)
    except RuntimeError:
        fn()


class ErrorMonitorMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        sent = {"status": None}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            logger.exception("%s %s → 처리되지 않은 예외 request_id=%s", scope.get("method"), scope.get("path"), request_id)
            _report(scope, 500, type(exc).__name__, str(exc), request_id)
            if sent["status"] is not None:   # 응답을 이미 보내기 시작했으면 바꿀 수 없다
                raise
            response = JSONResponse(
                {"detail": "서버에서 오류가 났습니다. 잠시 후 다시 시도해 주세요.", "request_id": request_id},
                status_code=500,
                headers={"X-Request-ID": request_id},
            )
            await response(scope, receive, send)
            return

        status = sent["status"]
        if status is not None and status >= 500:
            logger.error("%s %s → %s request_id=%s", scope.get("method"), scope.get("path"), status, request_id)
            _report(scope, status, f"HTTP {status}", None, request_id)


def _report(scope, status: int, error_type: str, message: str | None, request_id: str) -> None:
    route = getattr(scope.get("route"), "path", None) or ops_monitor.route_template(scope.get("path", ""))
    method = scope.get("method")
    dispatch(lambda: ops_monitor.record_error(
        None, source="api", route=route, method=method, status_code=status,
        error_type=error_type, message=message, request_id=request_id,
    ))
