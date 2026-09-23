from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import bcrypt

from schemas.user import WithdrawRequest, SignupRequest
from db import supabase


# ── 비밀번호 암호화 (bcrypt 직접 사용) ──────────────
# 비밀번호 → 해시(암호문)로 변환
def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

# 비밀번호 검증 (나중에 로그인 때 사용)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


# ── 라우터 설정 ────────────────────────────────────
# prefix: 이 부서의 주소는 전부 /auth 로 시작
# tags: /docs 에서 "auth" 그룹으로 묶어줌
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/ping")
def auth_ping():
    return {"message": "auth 라우터 살아있음"}


# ── 회원가입 ───────────────────────────────────────
@router.post("/signup")
def signup(req: SignupRequest):

    # ② 필수 약관 체크
    if not req.agree_privacy or not req.agree_ai_notice:
        raise HTTPException(status_code=400, detail="필수 약관에 동의해야 합니다.")

    # ③ 이메일 중복 체크
    existing = supabase.table("users").select("id").eq("email", req.email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    # ④ 비밀번호 암호화
    hashed = hash_password(req.password)

    # ⑤ DB 저장
    supabase.table("users").insert({
        "email": req.email,
        "nickname": req.nickname,
        "password_hash": hashed,
        "agree_privacy": req.agree_privacy,
        "agree_ai_notice": req.agree_ai_notice,
        "agree_marketing": req.agree_marketing,
        "agreed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    # ⑥ 성공 응답
    return {"message": "회원가입 성공!"}