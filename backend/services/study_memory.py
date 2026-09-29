"""학습 세션과 계획 블록에서 근거 있는 계정 메모리만 만든다."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

KST = timezone(timedelta(hours=9))
MEMORY_TYPES = ("preferred_study_time", "effort_deviation", "four_week_completion_rate")


def _local_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)).astimezone(KST)


def _time_band(hour: int) -> str:
    if 5 <= hour < 12:
        return "오전"
    if 12 <= hour < 18:
        return "오후"
    if 18 <= hour < 22:
        return "저녁"
    return "밤"


def derive_study_memories(sessions: list[dict], blocks: list[dict]) -> dict[str, tuple[dict, str]]:
    """최근 4주 기록에 근거가 있는 항목만 만든다."""
    result: dict[str, tuple[dict, str]] = {}
    if len(sessions) >= 3:
        minutes_by_band: dict[str, int] = defaultdict(int)
        for session in sessions:
            band = _time_band(_local_datetime(session["started_at"]).hour)
            minutes_by_band[band] += int(session["minutes"])
        preferred = max(("오전", "오후", "저녁", "밤"), key=lambda band: minutes_by_band[band])
        result["preferred_study_time"] = (
            {"band": preferred, "session_count": len(sessions)},
            f"최근 4주 학습 기록 {len(sessions)}건의 시작 시간과 학습량",
        )

    ratios = [
        (int(row["minutes"]) - int(row["expected_minutes"])) / int(row["expected_minutes"]) * 100
        for row in sessions if row.get("expected_minutes") and int(row["expected_minutes"]) > 0
    ]
    if len(ratios) >= 3:
        result["effort_deviation"] = (
            {"percent": round(mean(ratios)), "session_count": len(ratios)},
            f"최근 4주 예상·실제 시간이 모두 있는 학습 기록 {len(ratios)}건",
        )

    if blocks:
        completed = sum(1 for block in blocks if block.get("done") is True)
        result["four_week_completion_rate"] = (
            {"percent": round(completed / len(blocks) * 100), "completed": completed, "planned": len(blocks)},
            f"최근 4주에 예정된 계획 블록 {len(blocks)}건",
        )
    return result


def refresh_study_memories(db, user_id: str, now: datetime | None = None) -> None:
    """새 학습 기록 직후에만 갱신한다. 조회나 삭제 자체는 재집계하지 않는다."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=28)
    sessions = (
        db.table("study_sessions").select("started_at,minutes,expected_minutes")
        .eq("user_id", user_id).gte("started_at", since.isoformat())
        .order("started_at", desc=True).limit(300).execute().data
    )
    plans = db.table("study_plans").select("id").eq("user_id", user_id).execute().data
    blocks: list[dict] = []
    if plans:
        blocks = (
            db.table("plan_blocks").select("start_at,done")
            .in_("plan_id", [row["id"] for row in plans])
            .gte("start_at", since.isoformat()).lte("start_at", now.isoformat())
            .execute().data
        )
    derived = derive_study_memories(sessions, blocks)
    for memory_type, (value, basis) in derived.items():
        db.table("user_memories").upsert({
            "user_id": user_id, "memory_type": memory_type, "memory_key": "default",
            "value": value, "basis": basis, "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(days=365)).isoformat(),
        }, on_conflict="user_id,memory_type,memory_key").execute()
    for memory_type in set(MEMORY_TYPES) - derived.keys():
        db.table("user_memories").delete().eq("user_id", user_id).eq(
            "memory_type", memory_type
        ).execute()
