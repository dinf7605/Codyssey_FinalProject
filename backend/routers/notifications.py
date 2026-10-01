"""내 알림 (FR-ALARM-01~04 공통) — 알림을 만드는 일은 services/alarms.py 가 한다.

블록 알림(시작 전·미완료)에는 actions 를 붙인다 — 화면이 '지금 시작'·'미루기'·'오늘 쉬기' 버튼을 그린다 (FR-ALARM-03).
미루기는 POST /plan/blocks/{block_id}/postpone 이다. 블록당 2번까지라 다 쓴 블록에는 'postpone' 을 빼고 보낸다.
오늘 쉬기는 POST /notifications/rest-today — 그날 남은 학습 알림을 멈추고, 남은 블록은 야간 재조정이 옮긴다.
이미 끝낸 블록이나 알림 뒤에 옮겨진 블록의 알림은 버튼 없이 handled 문구만 붙인다 — 지난 안내로 다시 누르지 않게.
"""

from fastapi import APIRouter, Depends, HTTPException

from db import get_supabase_client
from services import alarms
from services.alarms import BLOCK_TYPES
from services.plan_store import from_db_time
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


def _handled(db, user_id: str, block_ids: list[str]) -> tuple[set[str], dict[str, str]]:
    """끝낸 블록 id 들, 블록별 마지막으로 옮긴 시각(ISO)."""
    if not block_ids:
        return set(), {}
    done = {
        str(r["id"]) for r in db.table("plan_blocks").select("id,done").in_("id", block_ids).execute().data
        if r.get("done")
    }
    moved: dict[str, str] = {}
    for r in db.table("plan_changes").select("block_id,created_at").eq("user_id", user_id).in_("block_id", block_ids).execute().data:
        key = str(r["block_id"])
        if r.get("created_at") and r["created_at"] > moved.get(key, ""):
            moved[key] = r["created_at"]
    return done, moved


def _with_actions(row: dict, postponed: dict[str, int], done: set[str] = frozenset(),
                  moved: dict[str, str] | None = None) -> dict:
    if not (row.get("type") in BLOCK_TYPES and row.get("block_id")):
        return {**row, "actions": []}
    block_id = str(row["block_id"])
    if block_id in done:
        return {**row, "actions": [], "handled": "이 블록은 완료했어요."}
    last_move = (moved or {}).get(block_id)
    if last_move and from_db_time(last_move) > from_db_time(row["sent_at"]):
        return {**row, "actions": [], "handled": "이 블록은 알림 뒤에 다른 시간으로 옮겨졌어요. 일정에서 확인해 주세요."}
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
    done, moved = _handled(db, str(user.id), list(dict.fromkeys(block_ids)))
    return [_with_actions(row, postponed, done, moved) for row in res.data]


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
