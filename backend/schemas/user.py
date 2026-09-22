from pydantic import BaseModel

# 탈퇴 요청 시 받을 데이터 형식
class WithdrawRequest(BaseModel):
    user_id: str           # ← 이 줄만 추가!
    confirm: bool
    reason: str | None = None