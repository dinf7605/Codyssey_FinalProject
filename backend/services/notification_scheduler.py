"""알림 자동 발송 스케줄러 (FR-ALARM-01).

역할:
- 10분 뒤 시작하는 학습 블록 조회
- 중복 발송 방지
- 사용자 알림 설정 확인
- 방해금지 시간 확인
- notification_logs에 알림 기록
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from db import get_supabase_client


NOTIFICATION_TYPE_10MIN = "10min_before"


def run_10min_before_notifications() -> None:
    """10분 뒤 시작하는 학습 블록에 대해 알림을 생성한다.

    APScheduler가 주기적으로 호출할 함수.
    """
    try:
        db = get_supabase_client()

        now = datetime.now(timezone.utc)

        # 스케줄러가 1분마다 돈다고 가정하고, 약간의 여유 범위를 둔다.
        target_from = now + timedelta(minutes=9)
        target_to = now + timedelta(minutes=11)

        blocks_res = (
            db.table("plan_blocks")
            .select("id, plan_id, title, start_at, done")
            .gte("start_at", target_from.isoformat())
            .lte("start_at", target_to.isoformat())
            .eq("done", False)
            .execute()
        )

        blocks = blocks_res.data or []

        for block in blocks:
            _handle_block_notification(db, block, now)

    except Exception as e:
        # 백그라운드 작업 예외가 서버 전체를 죽이지 않도록 막는다.
        print(f"[알림 스케줄러] 실행 실패: {e}")


def _handle_block_notification(db: Any, block: dict, now: datetime) -> None:
    """학습 블록 1개에 대해 알림 발송 여부를 판단하고 기록한다."""

    plan_id = block.get("plan_id")
    block_id = block.get("id")

    if not plan_id or not block_id:
        return

    # plan_blocks에는 user_id가 없으므로 study_plans에서 user_id 조회
    plan_res = (
        db.table("study_plans")
        .select("user_id")
        .eq("id", plan_id)
        .limit(1)
        .execute()
    )

    if not plan_res.data:
        return

    user_id = plan_res.data[0]["user_id"]

    # 사용자 알림 설정 확인
    if not _can_send_now(db, user_id, now):
        return

    # 이미 같은 블록에 대해 같은 타입의 알림을 보냈는지 확인
    dup_res = (
        db.table("notification_logs")
        .select("id")
        .eq("user_id", user_id)
        .eq("block_id", block_id)
        .eq("type", NOTIFICATION_TYPE_10MIN)
        .limit(1)
        .execute()
    )

    if dup_res.data:
        return

    title = block.get("title") or "학습"
    message = f"10분 후 '{title}' 학습이 시작됩니다."

    try:
        db.table("notification_logs").insert(
            {
                "user_id": user_id,
                "block_id": block_id,
                "type": NOTIFICATION_TYPE_10MIN,
                "message": message,
            }
        ).execute()

        print(f"[알림 스케줄러] 10분 전 알림 생성: user={user_id}, block={block_id}")

    except Exception as e:
        # unique index 때문에 동시에 insert되면 중복 오류가 날 수 있다.
        # 이 경우 서버를 죽이지 않고 로그만 남긴다.
        print(f"[알림 스케줄러] 알림 저장 실패: {e}")


def _can_send_now(db: Any, user_id: str, now: datetime) -> bool:
    """사용자의 알림 설정을 보고 지금 발송 가능한지 판단한다."""

    res = (
        db.table("user_notification_settings")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    # 설정이 없으면 기본값: 알림 허용
    if not res.data:
        return True

    settings = res.data[0]

    # 전체 알림 OFF
    if settings.get("enabled") is False:
        return False

    quiet_start = settings.get("quiet_start")
    quiet_end = settings.get("quiet_end")

    # 방해금지 시간이 둘 다 있을 때만 검사
    if quiet_start and quiet_end:
        if _is_quiet_time(now.time(), quiet_start, quiet_end):
            return False

    return True


def _parse_db_time(value: str) -> time:
    """DB time 값을 Python time으로 변환한다.

    Supabase/Postgres time은 보통 '22:00:00' 형태로 온다.
    """
    hh, mm = value[:5].split(":")
    return time(hour=int(hh), minute=int(mm))


def _is_quiet_time(now_time: time, quiet_start: str, quiet_end: str) -> bool:
    """현재 시간이 방해금지 시간대인지 확인한다.

    예:
    - 22:00 ~ 07:00 처럼 자정을 넘는 경우
    - 09:00 ~ 18:00 처럼 같은 날짜 안에서 끝나는 경우
    모두 처리한다.
    """
    start = _parse_db_time(quiet_start)
    end = _parse_db_time(quiet_end)

    # 자정을 넘는 경우: 22:00 ~ 07:00
    if start > end:
        return now_time >= start or now_time < end

    # 같은 날짜 안에서 끝나는 경우: 09:00 ~ 18:00
    return start <= now_time < end