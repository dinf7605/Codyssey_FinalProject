"""내 알림 (FR-ALARM-01~04 공통) — 알림을 만드는 일은 services/alarms.py 가 한다.

블록 알림(시작 전·미완료)에는 actions 를 붙인다 — 화면이 '지금 시작'·'미루기' 버튼을 그린다 (FR-ALARM-03).
미루기는 POST /plan/blocks/{block_id}/postpone 이다.
"""

from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from services.alarms import BLOCK_TYPES
from utils.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

LIST_LIMIT = 50


@router.get("/ping")
def notifications_ping():
    return {"message": "notifications 라우터 살아있음"}


# ── 공통 발송 함수 ──
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


def _with_actions(row: dict) -> dict:
    block = row.get("type") in BLOCK_TYPES and row.get("block_id")
    return {**row, "actions": ["start", "postpone"] if block else []}


# ── 내 알림 목록 조회 (최근 50건) ──
@router.get("")
def get_my_notifications(user=Depends(get_current_user)):
    res = (
        get_supabase_client().table("notification_logs")
        .select("id,type,message,is_read,sent_at,block_id")
        .eq("user_id", user.id)          # 서비스 키는 RLS 를 통과하므로 본인 조건을 반드시 건다
        .order("sent_at", desc=True)
        .limit(LIST_LIMIT)
        .execute()
    )
    return [_with_actions(row) for row in res.data]


# ── 모두 읽음 ──
@router.patch("/read-all")
def mark_all_as_read(user=Depends(get_current_user)):
    (
        get_supabase_client().table("notification_logs")
        .update({"is_read": True})
        .eq("user_id", user.id)
        .eq("is_read", False)
        .execute()
    )
    return {"message": "모두 읽음 처리 완료"}


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
