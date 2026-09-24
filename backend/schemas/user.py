from pydantic import BaseModel, EmailStr


# ── 탈퇴 요청 시 받을 데이터 형식 ──
class WithdrawRequest(BaseModel):
    confirm: bool
    reason: str | None = None


# ── 회원가입 요청 시 받을 데이터 형식 ──
class SignupRequest(BaseModel):
    email: EmailStr          # 이메일 (형식 자동 검증됨!)
    nickname: str            # 닉네임
    password: str            # 비밀번호

    # 약관 3종
    agree_privacy: bool      # ① 개인정보 수집·이용 (필수)
    agree_ai_notice: bool    # ② AI 생성 콘텐츠 고지 (필수)
    agree_marketing: bool    # ③ 학습 알림 메일 (선택)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str