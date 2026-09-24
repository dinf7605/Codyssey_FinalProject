from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from fastapi import Depends          # 👈 Depends 추가! (기존 fastapi import에 붙이기)
from utils.auth import get_current_user   # 👈 방금 만든 함수 가져오기!
import bcrypt

from schemas.user import WithdrawRequest, SignupRequest, LoginRequest
from db import supabase


# ── 비밀번호 암호화 (bcrypt 직접 사용) ──────────────
def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


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

    # ② Supabase Auth로 계정 생성
    try:
        auth_res = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"가입 실패: {str(e)}")

    # ③ Auth가 만들어준 user id 받기
    user_id = auth_res.user.id

    # ④ users 테이블에 프로필 + 동의정보 한 번에 저장! ✨
    supabase.table("users").insert({
        "auth_id": user_id,
        "email": req.email,
        "nickname": req.nickname,
        "password_hash": hash_password(req.password),        # 비번 해시 저장
        "agree_privacy": req.agree_privacy,                  # 동의정보 통합!
        "agree_ai_notice": req.agree_ai_notice,
        "agree_marketing": req.agree_marketing,
        "agreed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    # ⑤ consents 테이블 insert 부분은 삭제됨! 🗑️

    return {"message": "회원가입 성공!"}


@router.post("/login")
def login(req: LoginRequest):
    # ① Supabase Auth에 로그인 요청
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
    except Exception:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 틀렸습니다.")

    # ② 성공하면 세션(출입증)이 담겨 옴
    session = auth_res.session

    # ③ 프론트에 토큰 전달
    return {
        "message": "로그인 성공!",
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": auth_res.user.id,
    }

@router.get("/me")
def get_me(user = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email
    }