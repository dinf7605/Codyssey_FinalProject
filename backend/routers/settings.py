from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from schemas.user import WithdrawRequest
from utils.auth import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ping")
def settings_ping():
    return {"message": "settings 라우터 살아있음"}


# ── 내 프로필 조회 (FR-MY-01) ──
@router.get("/profile")
def get_my_profile(user=Depends(get_current_user)):
    # 1) 토큰에서 나온 '본인' 정보를 DB에서 조회
    response = (
        get_supabase_client().table("users")
        .select("*")
        .eq("user_id", user.id)         # 본인 것만
        .limit(1)
        .execute()
    )

    # 2) 데이터 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 3) 프로필 반환
    return response.data[0]


# ── 회원 탈퇴 (FR-MY-04) ──
@router.delete("/withdraw")
def withdraw_user(
    req: WithdrawRequest,
    user=Depends(get_current_user),
):
    # 1) 확인 안 했으면 거부
    if not req.confirm:
        raise HTTPException(status_code=400, detail="탈퇴 확인이 필요합니다")

    db = get_supabase_client()

    # 2) 토큰에서 나온 '본인'만 DB에서 삭제
    response = db.table("users").delete().eq("user_id", user.id).execute()

    # 3) 삭제된 게 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 4) Supabase Auth 계정 삭제 — 일정·학습기록·메모리 등 user_id 를 가진 행은
    #    외래키 on delete cascade 로 함께 지워진다 (FR-MY-04)
    try:
        db.auth.admin.delete_user(user.id)
    except Exception as e:
        # DB는 이미 지워졌으므로, Auth 삭제 실패는 로그만 남기고 넘어감
        print(f"[탈퇴] Auth 계정 삭제 실패: {e}")

    return {"message": "탈퇴가 완료되었습니다"}
