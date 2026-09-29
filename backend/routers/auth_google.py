"""구글 로그인 (FR-AUTH-02) — Supabase Auth 의 Google 공급자를 쓴다.

흐름
  1. 화면이 GET /auth/google/start?redirect_to=<프론트>/auth/callback 으로 이동할 주소를 받는다
  2. 브라우저가 그 주소(Supabase → Google 계정 선택)로 갔다가 redirect_to 로 돌아온다.
     토큰은 주소의 # 뒤에 붙어 온다 — 서버에는 전달되지 않는다
  3. 화면이 GET /auth/google/profile 로 우리 users 프로필이 있는지 본다
  4. 처음 온 계정이면 필수 동의 2개를 받고 POST /auth/google/complete 로 프로필을 만든다

지키는 것
  - 캘린더 권한은 로그인에서 요구하지 않는다 (기본 email·profile 만 · 로그인 화면 안내 문구)
  - redirect_to 는 FRONTEND_ORIGIN 의 /auth/callback 하나만 받는다 — 다른 사이트로 토큰이 가지 않게
  - 필수 동의 없이 프로필을 만들지 않는다 (FR-JOIN-02/03, 이메일 가입과 같은 기준)

Supabase 대시보드에서 Google 공급자를 켜야 동작한다 (backend/README.md "구글 로그인 설정").
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from db import get_supabase_client
from utils.auth import get_current_user

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger(__name__)

CALLBACK_PATH = "/auth/callback"
NOT_READY = "구글 로그인이 아직 설정되지 않았습니다. 이메일로 로그인해 주세요."


class GoogleProfileRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=10)
    agree_privacy: bool      # ① 개인정보 수집·이용 (필수)
    agree_ai_notice: bool    # ② AI 생성 콘텐츠 고지 (필수)
    agree_marketing: bool = False  # ③ 학습 알림 메일 (선택)

    @field_validator("nickname")
    @classmethod
    def valid_nickname(cls, value: str) -> str:
        value = value.strip()
        if not 2 <= len(value) <= 10:
            raise ValueError("닉네임은 2~10자여야 합니다")
        return value


def callback_url() -> str:
    return os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/") + CALLBACK_PATH


def google_enabled() -> bool:
    """Supabase Auth 설정에서 Google 공급자가 켜져 있는가. 확인하지 못하면 False."""
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return False
    try:
        response = httpx.get(f"{url.rstrip('/')}/auth/v1/settings", headers={"apikey": key}, timeout=5.0)
        response.raise_for_status()
        return bool(response.json().get("external", {}).get("google"))
    except Exception:  # noqa: BLE001 - 확인 실패는 '아직 준비 안 됨'으로 안내한다
        logger.exception("Supabase Auth 설정 확인 실패")
        return False


def suggested_nickname(metadata: dict | None, email: str | None) -> str:
    """구글 이름 → 없으면 이메일 앞부분. 2~10자로 맞추고, 못 맞추면 빈 문자열 (화면에서 입력)."""
    metadata = metadata or {}
    for value in (metadata.get("full_name"), metadata.get("name"), (email or "").split("@")[0]):
        value = (value or "").strip()[:10].strip()
        if len(value) >= 2:
            return value
    return ""


@router.get("/start")
def start(redirect_to: str = Query(max_length=300)) -> dict:
    if redirect_to != callback_url():
        raise HTTPException(status_code=400, detail="허용되지 않은 돌아올 주소입니다.")
    base = os.getenv("SUPABASE_URL")
    if not base or not google_enabled():
        raise HTTPException(status_code=503, detail=NOT_READY)
    query = urlencode({"provider": "google", "redirect_to": redirect_to})
    return {"url": f"{base.rstrip('/')}/auth/v1/authorize?{query}"}


def _profile_exists(db, user_id: str) -> bool:
    rows = db.table("users").select("user_id").eq("user_id", user_id).limit(1).execute().data
    return bool(rows)


@router.get("/profile")
def profile(user=Depends(get_current_user)) -> dict:
    db = get_supabase_client()
    return {
        "has_profile": _profile_exists(db, str(user.id)),
        "email": user.email,
        "suggested_nickname": suggested_nickname(getattr(user, "user_metadata", None), user.email),
    }


@router.post("/complete")
def complete(req: GoogleProfileRequest, user=Depends(get_current_user)) -> dict:
    if not req.agree_privacy or not req.agree_ai_notice:
        raise HTTPException(status_code=400, detail="필수 약관에 동의해야 합니다.")
    if not user.email:
        raise HTTPException(status_code=400, detail="구글 계정의 이메일을 확인하지 못했습니다.")
    db = get_supabase_client()
    user_id = str(user.id)
    # 이미 프로필이 있으면 덮어쓰지 않는다 (두 번 눌러도 한 줄)
    if _profile_exists(db, user_id):
        return {"created": False}
    try:
        db.table("users").insert({
            "user_id": user_id,
            "email": user.email,
            "nickname": req.nickname,
            "agree_privacy": req.agree_privacy,
            "agree_ai_notice": req.agree_ai_notice,
            "agree_marketing": req.agree_marketing,
            "agreed_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        # 동시에 두 번 들어와 user_id 고유 키에 걸린 경우는 이미 만들어진 것
        if _profile_exists(db, user_id):
            return {"created": False}
        logger.exception("구글 가입 프로필 저장 실패")
        raise HTTPException(status_code=503, detail="프로필을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
    return {"created": True}
