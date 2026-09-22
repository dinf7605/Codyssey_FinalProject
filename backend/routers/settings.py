from fastapi import APIRouter, HTTPException
from schemas.user import WithdrawRequest

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/ping")
def settings_ping():
    return {"message": "settings 라우터 살아있음"}


# ── 회원 탈퇴 (FR-MY-04) ──
@router.delete("/withdraw")
def withdraw_user(req: WithdrawRequest):
    # 1) 확인 안 했으면 거부
    if not req.confirm:
        raise HTTPException(status_code=400, detail="탈퇴 확인이 필요합니다")

    # ── 삭제 순서 (TODO: DB 연결 후 구현) ──
    # 2) 토큰 즉시 폐기 (보안 최우선)
    # TODO: 세션/토큰 무효화

    # 3) 사용자 데이터 삭제
    # TODO: 일정 삭제
    # TODO: 학습기록 삭제
    # TODO: 메모리/캘린더 삭제

    # 4) 계정 삭제
    # TODO: users 테이블에서 삭제

    return {"message": "탈퇴가 완료되었습니다"}