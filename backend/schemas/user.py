import re

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── 탈퇴 요청 시 받을 데이터 형식 ──
class WithdrawRequest(BaseModel):
    confirm: bool
    reason: str | None = None


# ── 회원가입 요청 시 받을 데이터 형식 ──
class SignupRequest(BaseModel):
    email: EmailStr          # 이메일 (형식 자동 검증됨!)
    nickname: str = Field(min_length=2, max_length=10)
    password: str = Field(min_length=8, max_length=64)

    # 약관 3종
    agree_privacy: bool      # ① 개인정보 수집·이용 (필수)
    agree_ai_notice: bool    # ② AI 생성 콘텐츠 고지 (필수)
    agree_marketing: bool    # ③ 학습 알림 메일 (선택)

    @field_validator("nickname")
    @classmethod
    def valid_nickname(cls, value: str) -> str:
        value = value.strip()
        if not 2 <= len(value) <= 10:
            raise ValueError("닉네임은 2~10자여야 합니다")
        return value

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        if not (
            re.search(r"[A-Za-z]", value)
            and re.search(r"[0-9]", value)
            and re.search(r"[^A-Za-z0-9]", value)
        ):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다")
        return value

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# ── 비밀번호 재설정 메일 요청 ──
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


# ── 새 비밀번호 설정 ──
class ResetPasswordRequest(BaseModel):
    access_token: str
    refresh_token: str
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        if not (
            re.search(r"[A-Za-z]", value)
            and re.search(r"[0-9]", value)
            and re.search(r"[^A-Za-z0-9]", value)
        ):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다")
        return value