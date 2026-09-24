from fastapi import APIRouter, HTTPException
from schemas.user import WithdrawRequest
from db import get_supabase_client

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

    # 2) users 테이블에서 삭제
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    response = (
        supabase.table("users")
        .delete()
        .eq("id", req.user_id)
        .execute()
    )

    # 3) 삭제된 게 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return {"message": "탈퇴가 완료되었습니다"}
