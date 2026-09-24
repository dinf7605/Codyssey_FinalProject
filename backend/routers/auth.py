from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client, new_auth_client
from schemas.user import LoginRequest, SignupRequest
from utils.auth import get_current_user

# 비밀번호는 Supabase Auth 가 해싱·저장한다. 우리 DB 에는 저장하지 않는다 (기능명세서 K15).

# 실패 이유를 자세히 말하면 "이미 가입된 이메일"인지 드러난다 (NFR-SEC-01).
SIGNUP_FAILED = "가입하지 못했습니다. 입력한 정보를 확인하고 다시 시도해 주세요."
LOGIN_FAILED = "이메일 또는 비밀번호가 틀렸습니다."


# ── 라우터 설정 ────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])


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
    auth_client = new_auth_client()
    try:
        auth_res = auth_client.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })
    except Exception:
        raise HTTPException(status_code=400, detail=SIGNUP_FAILED)

    if not auth_res.user:
        raise HTTPException(status_code=400, detail=SIGNUP_FAILED)

    # ③ users 테이블에 프로필 + 동의정보 저장 (서비스 키)
    get_supabase_client().table("users").insert({
        "user_id": auth_res.user.id,
        "email": req.email,
        "nickname": req.nickname,
        "agree_privacy": req.agree_privacy,
        "agree_ai_notice": req.agree_ai_notice,
        "agree_marketing": req.agree_marketing,
        "agreed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {"message": "회원가입 성공!"}


@router.post("/login")
def login(req: LoginRequest):
    # ① Supabase Auth에 로그인 요청 — 요청마다 새 클라이언트
    auth_client = new_auth_client()
    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)

    # ② 성공하면 세션(출입증)이 담겨 옴
    session = auth_res.session
    if not session:
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)

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
