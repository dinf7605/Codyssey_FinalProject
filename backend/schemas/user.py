from pydantic import BaseModel

# 탈퇴 요청 시 받을 데이터 형식
class WithdrawRequest(BaseModel):
    confirm: bool          # "정말 탈퇴하시겠습니까?" 확인 여부
    reason: str | None = None   # 탈퇴 사유 (선택 입력)