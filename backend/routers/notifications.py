from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from utils.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/ping")
def notifications_ping():
    return {"message": "notifications 라우터 살아있음"}


# ── 공통 발송 함수 (알림 4종이 전부 이거 재사용!) ──
def send_notification(user_id: str, type: str, message: str):
    """알림 1건을 DB에 기록. 실제 푸시/메일은 여기서 확장."""
    res = (
        get_supabase_client().table("notification_logs")
        .insert({
            "user_id": user_id,
            "type": type,
            "message": message,
        })
        .execute()
    )
    return res.data


# ── 내 알림 목록 조회 (FR-ALARM 공통) ──
@router.get("")
def get_my_notifications(user=Depends(get_current_user)):
    res = (
        get_supabase_client().table("notification_logs")
        .select("*")
        .eq("user_id", user.id)          # 서비스 키는 RLS 를 통과하므로 본인 조건을 반드시 건다
        .order("sent_at", desc=True)
        .execute()
    )
    return res.data


# ── 알림 읽음 처리 ──
@router.patch("/{noti_id}/read")
def mark_as_read(noti_id: int, user=Depends(get_current_user)):
    res = (
        get_supabase_client().table("notification_logs")
        .update({"is_read": True})
        .eq("id", noti_id)
        .eq("user_id", user.id)          # 본인 것만! (보안)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    return {"message": "읽음 처리 완료"}


# 테스트용 — /ping 아래에 잠깐 추가했다가 지우기
@router.post("/test")
def test_send(user=Depends(get_current_user)):
    return send_notification(user.id, "test", "테스트 알림입니다")
