"""내 알림 (FR-ALARM-01~04 공통) — 알림을 만드는 일은 services/alarms.py 가 한다.

블록 알림(시작 전·미완료)에는 actions 를 붙인다 — 화면이 '지금 시작'·'미루기'·'오늘 쉬기' 버튼을 그린다 (FR-ALARM-03).
미루기는 POST /plan/blocks/{block_id}/postpone 이다. 블록당 2번까지라 다 쓴 블록에는 'postpone' 을 빼고 보낸다.
오늘 쉬기는 POST /notifications/rest-today — 그날 남은 학습 알림을 멈추고, 남은 블록은 야간 재조정이 옮긴다.
"""

from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from services import alarms
from services.alarms import BLOCK_TYPES
from services.replan import POSTPONE_LIMIT, postpone_counts
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


def _with_actions(row: dict, postponed: dict[str, int]) -> dict:
    if not (row.get("type") in BLOCK_TYPES and row.get("block_id")):
        return {**row, "actions": []}
    actions = ["start"]
    if postponed.get(str(row["block_id"]), 0) < POSTPONE_LIMIT:
        actions.append("postpone")
    return {**row, "actions": actions + ["rest"]}


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
    db = get_supabase_client()
    block_ids = [str(r["block_id"]) for r in res.data if r.get("type") in BLOCK_TYPES and r.get("block_id")]
    postponed = postpone_counts(db, user.id, block_ids)
    return [_with_actions(row, postponed) for row in res.data]


# ── 오늘 쉬기 (FR-ALARM-02 · FR-ALARM-03) ──
@router.post("/rest-today")
def rest_today(user=Depends(get_current_user)):
    created = alarms.rest_today(get_supabase_client(), str(user.id))
    return {"rested": True, "created": created,
            "message": "오늘 남은 학습 알림을 멈췄어요. 남은 블록은 밤사이 다른 날로 옮겨 드려요."}


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
