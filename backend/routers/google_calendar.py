"""구글 캘린더 연동 (FR-PLAN-01 · NFR-PRIV-01) — 계획을 만들 때 캘린더의 '바쁜 시간'만 한 번 읽는다.

흐름
  1. 화면이 GET /calendar/connect 로 구글 동의 주소를 받는다 (state 는 화면이 만들어 탭 세션에 보관)
  2. 사용자가 구글에서 '바쁜 시간 보기' 권한(calendar.freebusy)을 허락하면 /calendar/callback?code=… 로 돌아온다
  3. 화면이 POST /calendar/busy 로 code 를 보낸다 → 서버가 토큰으로 바꿔 FreeBusy 를 한 번 읽고 토큰을 바로 돌려준다(revoke)
  4. 화면이 바쁜 시간을 계획 만들기(POST /plan/schedule 의 busy)에 넣는다 → 그 시간을 피해서 놓는다

지키는 것
  - 바쁜 시간대(시작·끝)만 읽는다. 일정 제목·참석자·장소는 이 권한(FreeBusy)으로는 받을 수도 없다
  - 토큰을 저장하지 않는다 (access_type=online · 읽은 뒤 즉시 revoke). 바쁜 시간도 서버에 저장하지 않는다
  - 연동하지 않아도 직접 고른 가용 시간으로 계획을 만들 수 있다 (기획서 R4)

설정: .env 의 GOOGLE_CLIENT_ID · GOOGLE_CLIENT_SECRET (backend/README.md "구글 캘린더 연동"). 없으면 503.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.plan_store import KST

router = APIRouter(prefix="/calendar", tags=["calendar"])

SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
CALLBACK_PATH = "/calendar/callback"
MAX_DAYS = 180       # 계획 기한이 길어도 반년까지만 읽는다
CHUNK_DAYS = 60      # FreeBusy 한 번에 묻는 기간
NOT_READY = "구글 캘린더 연동이 아직 설정되지 않았습니다. 공부 가능 시간을 직접 골라 주세요."


def _client() -> tuple[str, str]:
    client_id, secret = os.getenv("GOOGLE_CLIENT_ID", "").strip(), os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        raise HTTPException(status_code=503, detail=NOT_READY)
    return client_id, secret


def callback_url() -> str:
    return os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/") + CALLBACK_PATH


@router.get("/connect")
def connect(state: str = Query(min_length=16, max_length=128)) -> dict:
    """구글 동의 주소. state 는 화면이 만든 임의 값 — 돌아왔을 때 화면이 같은지 확인한다 (CSRF)."""
    client_id, _ = _client()
    query = urlencode({
        "client_id": client_id, "redirect_uri": callback_url(), "response_type": "code",
        "scope": SCOPE, "access_type": "online", "include_granted_scopes": "false",
        "prompt": "consent", "state": state,
    })
    return {"url": f"{AUTH_URL}?{query}"}


class BusyRequest(BaseModel):
    code: str = Field(min_length=10, max_length=2048)
    start_day: date
    end_day: date


class BusySpan(BaseModel):
    start: datetime  # 한국 시각 (시간대 없음)
    end: datetime


class BusyResponse(BaseModel):
    busy: list[BusySpan]
    start_day: date
    end_day: date


def _kst(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(KST).replace(tzinfo=None)


def read_busy(access_token: str, start_day: date, end_day: date, http=httpx) -> list[BusySpan]:
    """기본 캘린더의 바쁜 시간. 기간을 나눠 묻고 합친다."""
    spans: list[BusySpan] = []
    day = start_day
    while day <= end_day:
        last = min(end_day, day + timedelta(days=CHUNK_DAYS - 1))
        res = http.post(FREEBUSY_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15.0, json={
            "timeMin": datetime.combine(day, time.min, KST).isoformat(),
            "timeMax": datetime.combine(last + timedelta(days=1), time.min, KST).isoformat(),
            "timeZone": "Asia/Seoul",
            "items": [{"id": "primary"}],
        })
        res.raise_for_status()
        calendar = res.json().get("calendars", {}).get("primary", {})
        if calendar.get("errors"):
            raise ValueError("calendar errors")
        spans += [BusySpan(start=_kst(b["start"]), end=_kst(b["end"])) for b in calendar.get("busy", [])]
        day = last + timedelta(days=1)
    return sorted(spans, key=lambda s: s.start)


@router.post("/busy", response_model=BusyResponse)
def busy(req: BusyRequest) -> BusyResponse:
    """code → 토큰 → FreeBusy 한 번 → 토큰 폐기. 결과는 저장하지 않고 화면에만 돌려준다."""
    client_id, secret = _client()
    if req.end_day < req.start_day:
        raise HTTPException(status_code=400, detail="기간이 올바르지 않습니다.")
    end_day = min(req.end_day, req.start_day + timedelta(days=MAX_DAYS))
    try:
        token = httpx.post(TOKEN_URL, timeout=15.0, data={
            "code": req.code, "client_id": client_id, "client_secret": secret,
            "redirect_uri": callback_url(), "grant_type": "authorization_code",
        })
        token.raise_for_status()
        access_token = token.json()["access_token"]
    except Exception:  # noqa: BLE001 - 코드 만료·재사용·설정 오류. 내용(비밀값)은 응답에 싣지 않는다
        raise HTTPException(status_code=400, detail="구글 캘린더 연결이 만료되었습니다. 다시 연결해 주세요.") from None

    try:
        spans = read_busy(access_token, req.start_day, end_day)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="구글 캘린더를 읽지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    finally:
        try:  # 한 번 읽었으면 권한을 바로 돌려준다 (NFR-PRIV-02 토큰 즉시 폐기)
            httpx.post(REVOKE_URL, params={"token": access_token}, timeout=10.0)
        except Exception:  # noqa: BLE001 - 폐기 실패해도 online 토큰은 1시간 뒤 만료된다
            pass
    return BusyResponse(busy=spans, start_day=req.start_day, end_day=end_day)
