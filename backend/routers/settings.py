from fastapi import APIRouter, HTTPException, Depends
from schemas.user import WithdrawRequest
from db import supabase, supabase_admin          # ★ supabase_admin 추가
from utils.auth import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ping")
def settings_ping():
    return {"message": "settings 라우터 살아있음"}

# ── 내 프로필 조회 (FR-MY-01) ──
@router.get("/profile")
def get_my_profile(user = Depends(get_current_user)):
    # 1) 토큰에서 나온 '본인' 정보를 DB에서 조회
    response = (
        supabase.table("users")
        .select("*")                    # 모든 컬럼 조회
        .eq("auth_id", user.id)         # 본인 것만
        .single()                       # 딱 1개만 (없으면 에러)
        .execute()
    )

    # 2) 데이터 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 3) 프로필 반환
    return response.data

# ── 회원 탈퇴 (FR-MY-04) ──
@router.delete("/withdraw")
def withdraw_user(
    req: WithdrawRequest,
    user = Depends(get_current_user)
):
    # 1) 확인 안 했으면 거부
    if not req.confirm:
        raise HTTPException(status_code=400, detail="탈퇴 확인이 필요합니다")

    # 2) 토큰에서 나온 '본인'만 DB에서 삭제
    response = (
        supabase.table("users")
        .delete()
        .eq("auth_id", user.id)
        .execute()
    )

    # 3) 삭제된 게 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 4) ★ Supabase Auth에서도 계정 삭제 (관리자 권한 사용) ★
    try:
        supabase_admin.auth.admin.delete_user(user.id)
    except Exception as e:
        # DB는 이미 지워졌으므로, Auth 삭제 실패는 로그만 남기고 넘어감
        print(f"[탈퇴] Auth 계정 삭제 실패: {e}")

    return {"message": "탈퇴가 완료되었습니다"}
