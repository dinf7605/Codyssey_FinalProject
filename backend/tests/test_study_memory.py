from datetime import datetime, timezone

from services.study_memory import derive_study_memories, refresh_study_memories
from tests.fake_supabase import FakeSupabase


def test_학습_기록이_충분할_때만_근거_있는_메모리를_만든다():
    sessions = [
        {"started_at": "2026-09-27T19:00:00+09:00", "minutes": 60, "expected_minutes": 50},
        {"started_at": "2026-09-28T20:00:00+09:00", "minutes": 90, "expected_minutes": 60},
        {"started_at": "2026-09-29T09:00:00+09:00", "minutes": 30, "expected_minutes": 30},
    ]
    values = derive_study_memories(sessions, [{"done": True}, {"done": False}])
    assert values["preferred_study_time"][0] == {"band": "저녁", "session_count": 3}
    assert values["effort_deviation"][0]["percent"] == 23
    assert values["four_week_completion_rate"][0]["percent"] == 50
    assert derive_study_memories(sessions[:2], {}) == {}


def test_학습_저장_후_본인_메모리만_갱신하고_삭제는_즉시_반영된다():
    db = FakeSupabase()
    user = "user-a"
    for day in (26, 27, 28):
        db.table("study_sessions").insert({
            "user_id": user, "started_at": f"2026-09-{day}T10:00:00+00:00",
            "minutes": 60, "expected_minutes": 50,
        }).execute()
    db.table("study_sessions").insert({
        "user_id": "user-b", "started_at": "2026-09-28T10:00:00+00:00",
        "minutes": 600, "expected_minutes": 50,
    }).execute()
    db.table("study_plans").insert({"id": "plan-a", "user_id": user}).execute()
    db.table("plan_blocks").insert({
        "plan_id": "plan-a", "start_at": "2026-09-27T10:00:00+00:00", "done": True,
    }).execute()
    refresh_study_memories(db, user, datetime(2026, 9, 29, tzinfo=timezone.utc))
    rows = db.rows("user_memories")
    assert len(rows) == 3
    assert all(row["user_id"] == user for row in rows)
    assert next(row for row in rows if row["memory_type"] == "effort_deviation")["value"]["percent"] == 20
    memory_id = rows[0]["id"]
    db.table("user_memories").delete().eq("user_id", user).eq("id", memory_id).execute()
    assert all(row["id"] != memory_id for row in db.rows("user_memories"))
