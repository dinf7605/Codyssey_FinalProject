from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from db import get_supabase_client
from schemas.user import WithdrawRequest
from services import alarms
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
        .select("email,nickname")
        .eq("user_id", user.id)         # 본인 것만 (DB 기준: user_id → auth.users)
        .limit(1)
        .execute()
    )

    # 2) 데이터 없으면 = 그런 유저 없음
    if not response.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 3) 프로필 반환
    return response.data[0]


# ── 알림 설정 (FR-MY-03 수신 여부 · FR-MY-05 강도·방해금지) ──
# 저장한 값은 services/alarms.py 가 알림을 보낼 때마다 읽는다.

class NotificationSettings(BaseModel):
    enabled: bool = True                                    # 알림 전체 끄기 (FR-MY-05)
    reminder_minutes_before: int = Field(default=10, ge=1, le=120)
    quiet_start: str | None = "23:00"   # 한국 시각. 둘 다 있어야 방해금지가 켜진다. 기본 23:00~07:00 (FR-MY-05)
    quiet_end: str | None = "07:00"
    intensity: Literal["low", "normal", "high"] = "normal"  # 약: 시작 알림만 · 보통 · 강: 독촉 포함
    # FR-MY-03 — 재조정 결과 · 마감 임박(관심 공모전 마감 24시간 전, 전체 끄기와 별개) · 학습 독촉
    # 저장한 적 없으면 가입 때 '학습 알림 수신(선택)' 동의를 따른다 (기본 꺼짐)
    notify_replan: bool = False
    notify_deadline: bool = False
    notify_nudge: bool = False

    @field_validator("quiet_start", "quiet_end", mode="before")
    @classmethod
    def _hhmm(cls, value):
        if value in (None, ""):
            return None
        text = str(value)[:5]
        hh, _, mm = text.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError("시간은 HH:MM 형식이어야 합니다")
        return f"{int(hh):02d}:{int(mm):02d}"

    @model_validator(mode="after")
    def _both_or_none(self):
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("방해금지 시작·끝 시간을 함께 넣어 주세요")
        return self


@router.get("/notifications", response_model=NotificationSettings)
def get_notification_settings(user=Depends(get_current_user)):
    # 알림을 보낼 때와 같은 규칙으로 읽는다 (저장한 값 · 기본값 · 가입 때 선택 동의)
    current = alarms.settings_for(get_supabase_client(), [str(user.id)])[str(user.id)]
    return NotificationSettings(**{k: current.get(k) for k in NotificationSettings.model_fields})


@router.put("/notifications", response_model=NotificationSettings)
def save_notification_settings(req: NotificationSettings, user=Depends(get_current_user)):
    get_supabase_client().table("user_notification_settings").upsert(
        {"user_id": str(user.id), **req.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="user_id",
    ).execute()
    return req


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

    # 설치되지 않은 DB에서는 Auth 계정을 먼저 삭제하지 않는다.
    try:
        ready = db.rpc("withdrawal_retention_ready", {}).execute()
        if ready.data is not True:
            raise RuntimeError("Retention migration is not ready")
    except Exception:
        raise HTTPException(status_code=503, detail="탈퇴 기능을 준비 중입니다. 잠시 후 다시 시도해 주세요.")

    # Auth 삭제 트리거가 프로필 보관과 서비스 데이터 삭제를 같은 트랜잭션에서 처리한다.
    # 여기서 users를 먼저 삭제하면 보관할 프로필을 잃으므로 삭제하지 않는다.
    try:
        db.auth.admin.delete_user(user.id)
    except Exception:
        raise HTTPException(status_code=503, detail="탈퇴 처리에 실패했습니다. 다시 시도해 주세요.")

    return {"message": "탈퇴가 완료되었습니다. 프로필은 별도로 1년간 보관 후 삭제됩니다."}
