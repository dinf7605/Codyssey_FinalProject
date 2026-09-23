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
    # ① 필수 약관 체크 (이건 그대로!)
    if not req.agree_privacy or not req.agree_ai_notice:
        raise HTTPException(status_code=400, detail="필수 약관에 동의해야 합니다.")

    # ② Supabase Auth로 계정 생성 (bcrypt 대체!)
    #    → 해싱, 이메일 중복체크, 세션을 Supabase가 자동 처리
    try:
        auth_res = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"가입 실패: {str(e)}")

    # ③ Auth가 만들어준 user id 받기
    user_id = auth_res.user.id

    # ④ 프로필 정보는 users 테이블에 별도 저장
    #    (비밀번호는 이제 여기 저장 안 함!)
    supabase.table("users").insert({
        "id": user_id,          # auth.users의 id와 연결 (중요!)
        "email": req.email,
        "nickname": req.nickname,
    }).execute()

    # ⑤ 동의 이력은 consents 테이블로 분리 (기획서 원안!)
    supabase.table("consents").insert({
        "user_id": user_id,
        "agree_privacy": req.agree_privacy,
        "agree_ai_notice": req.agree_ai_notice,
        "agree_marketing": req.agree_marketing,
        "agreed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {"message": "회원가입 성공!"}

from schemas.user import WithdrawRequest, SignupRequest, LoginRequest


@router.post("/login")
def login(req: LoginRequest):
    # ① Supabase Auth에 로그인 요청
    #    → 이메일/비번 검증을 Supabase가 대신 해줌
    try:
        auth_res = supabase.auth.sign_in_with_password({
            "email": req.email,
            "password": req.password,
        })
    except Exception:
        # 비번 틀림, 없는 계정 등 → 401
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 틀렸습니다.")

    # ② 성공하면 세션(출입증)이 담겨 옴
    session = auth_res.session

    # ③ 프론트에 토큰 전달 (이걸로 이후 요청 인증)
    return {
        "message": "로그인 성공!",
        "access_token": session.access_token,    # 출입증 (짧은 수명)
        "refresh_token": session.refresh_token,  # 재발급용 (긴 수명)
        "user_id": auth_res.user.id,
    }