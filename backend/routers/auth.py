import logging
import os
from urllib.parse import urlsplit
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import get_supabase_client, new_auth_client
from schemas.user import (
    LoginRequest,
    SignupRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from services import login_guard
from utils.auth import get_current_user

# 비밀번호는 Supabase Auth 가 해싱·저장한다. 우리 DB 에는 저장하지 않는다 (기능명세서 K15).

# 가입은 요청된 UX에 맞춰 중복 이메일을 구분한다. 로그인 실패는 통합 문구 유지.
SIGNUP_FAILED = "가입하지 못했습니다. 입력한 정보를 확인하고 다시 시도해 주세요."
LOGIN_FAILED = "이메일 또는 비밀번호가 틀렸습니다."
DUPLICATE_EMAIL = "이미 가입된 이메일입니다. 로그인하거나 비밀번호를 재설정해 주세요."
PASSWORD_INVALID = "비밀번호가 보안 조건에 맞지 않습니다. 8~64자, 영문·숫자·특수문자를 확인해 주세요."
RESET_SENT = "가입된 이메일이라면 비밀번호 재설정 메일이 발송됩니다. 메일함과 스팸함을 확인해 주세요."


def _provider_code(error):
    return getattr(error, "code", None)


def _rate_limited(error):
    return _provider_code(error) in {"over_email_send_rate_limit", "over_request_rate_limit"} or str(getattr(error, "status", "")) == "429"


def _recovery_redirect():
    # 요청자가 전달한 주소나 Origin/Host를 신뢰하지 않는다. 운영자가 정한 주소만 사용.
    url = os.getenv("PASSWORD_RESET_REDIRECT_URL", "").strip()
    try:
        parsed = urlsplit(url)
        valid = (
            bool(parsed.hostname) and parsed.username is None and parsed.password is None
            and parsed.path == "/reset-password" and not parsed.query and not parsed.fragment
            and "\\" not in url and not any(ch.isspace() for ch in url)
            and (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}))
        )
        parsed.port  # 잘못된 포트도 설정 오류로 처리한다.
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=503, detail="비밀번호 재설정 연결 설정이 필요합니다. 관리자에게 문의해 주세요.")
    return url


# ── 라우터 설정 ────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/ping")
def auth_ping():
    return {"message": "auth 라우터 살아있음"}


# ── 회원가입 ───────────────────────────────────────
@router.post("/signup")
def signup(req: SignupRequest):
    # ① 필수 약관 체크
    if not req.agree_privacy or not req.agree_ai_notice:
        raise HTTPException(status_code=400, detail="필수 약관에 동의해야 합니다.")

    # ② Supabase Auth로 계정 생성 — 요청마다 새 클라이언트 (db.py 설명 참고)
    #    설정이 비었을 때 나는 503 이 가입 실패 문구에 묻히지 않게 try 밖에서 만든다
    db = get_supabase_client()  # 프로필 저장 불가라면 Auth 계정을 만들기 전에 중단
    auth_client = new_auth_client()
    try:
        auth_res = auth_client.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })
    except Exception as error:
        code = _provider_code(error)
        if code in {"email_exists", "user_already_exists"}:
            raise HTTPException(status_code=409, detail=DUPLICATE_EMAIL) from None
        if code == "weak_password":
            raise HTTPException(status_code=400, detail=PASSWORD_INVALID) from None
        if _rate_limited(error):
            raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.") from None
        raise HTTPException(status_code=400, detail=SIGNUP_FAILED) from None

    if not auth_res.user:
        raise HTTPException(status_code=400, detail=SIGNUP_FAILED)
    if getattr(auth_res.user, "identities", None) == []:
        raise HTTPException(status_code=409, detail=DUPLICATE_EMAIL)

    # ③ users 테이블에 프로필 + 동의정보 저장 (서비스 키)
    try:
        db.table("users").insert({
            "user_id": auth_res.user.id,  # DB 기준: 사용자는 user_id → auth.users (004)
            "email": req.email,
            "nickname": req.nickname,
            "agree_privacy": req.agree_privacy,
            "agree_ai_notice": req.agree_ai_notice,
            "agree_marketing": req.agree_marketing,
            "agreed_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as error:
        # 미인증 계정 재가입에서는 Supabase가 동일 user.id를 돌려줄 수 있다.
        # SQL 중복 오류만으로 이메일 중복이라 단정하지 않고 해당 계정 프로필을 확인한다.
        if _provider_code(error) == "23505":
            try:
                existing = db.table("users").select("user_id").eq("user_id", auth_res.user.id).limit(1).execute()
            except Exception:
                existing = None
            if existing is not None and existing.data:
                raise HTTPException(status_code=409, detail=DUPLICATE_EMAIL) from None
        # 프로필 저장 실패만으로 Auth 계정의 소유권/신규 생성 여부를 단정하지 않는다.
        # 기존 계정 손상을 방지하기 위해 여기서 자동 삭제하지 않는다.
        logger.exception("가입 중 프로필 저장 실패")
        raise HTTPException(status_code=503, detail=SIGNUP_FAILED)

    session = auth_res.session
    return {
        "message": "회원가입 성공!" if session else "이메일 인증 후 로그인해 주세요.",
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
        "user_id": auth_res.user.id,
        "requires_email_confirmation": session is None,
    }


@router.post("/login")
def login(req: LoginRequest):
    # ⓪ 같은 이메일로 5회 연속 실패하면 60초 잠금 (FR-AUTH-01 · services/login_guard.py)
    wait = login_guard.locked_for(req.email)
    if wait:
        raise HTTPException(status_code=429, detail=f"로그인 시도가 많아 잠시 막았습니다. {wait}초 뒤에 다시 시도해 주세요.")

    # ① Supabase Auth에 로그인 요청 — 요청마다 새 클라이언트
    auth_client = new_auth_client()
    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
    except Exception:
        login_guard.record_failure(req.email)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)

    # ② 성공하면 세션(출입증)이 담겨 옴
    session = auth_res.session
    if not session:
        login_guard.record_failure(req.email)
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)
    login_guard.record_success(req.email)

    # ③ 프론트에 토큰 전달
    return {
        "message": "로그인 성공!",
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": auth_res.user.id,
    }


@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
    }


# ── 비밀번호 재설정 메일 요청 ─────────────────────
@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    redirect = _recovery_redirect()
    auth_client = new_auth_client()
    try:
        auth_client.auth.reset_password_for_email(req.email, {"redirect_to": redirect})
    except Exception as error:
        if _rate_limited(error):
            raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.") from None
        # 가입 여부는 밝히지 않지만 실제 발송 장애를 성공으로 표시하지 않는다.
        if _provider_code(error) != "user_not_found":
            logger.warning("비밀번호 재설정 메일 요청 실패")
            raise HTTPException(status_code=503, detail="메일 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None

    return {"message": RESET_SENT}


# ── 새 비밀번호 설정 ──────────────────────────────
@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    auth_client = new_auth_client()
    try:
        # 메일 링크의 토큰 2개로 세션 복원 → 비밀번호 변경
        auth_client.auth.set_session(req.access_token, req.refresh_token)
        auth_client.auth.update_user({"password": req.new_password})
    except Exception as error:
        code = _provider_code(error)
        if code == "same_password":
            raise HTTPException(status_code=400, detail="기존 비밀번호와 다른 새 비밀번호를 입력해 주세요.") from None
        if code == "weak_password":
            raise HTTPException(status_code=400, detail=PASSWORD_INVALID) from None
        if _rate_limited(error):
            raise HTTPException(status_code=429, detail="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.") from None
        if code in {"bad_jwt", "session_expired", "session_not_found", "refresh_token_not_found", "refresh_token_already_used", "otp_expired", "reauthentication_needed", "reauthentication_not_valid"} or str(getattr(error, "status", "")) in {"400", "401", "403"}:
            raise HTTPException(status_code=400, detail="링크가 만료되었거나 유효하지 않습니다. 새 메일을 요청해 주세요.") from None
        raise HTTPException(status_code=503, detail="비밀번호를 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None

    return {"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요."}
