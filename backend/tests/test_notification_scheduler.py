"""알림 스케줄러의 방해금지 판단 — 방해금지 시간은 한국 시각으로 비교해야 한다 (FR-ALARM-01 · FR-MY-05)."""

from datetime import datetime, timezone

import pytest

from services import notification_scheduler as ns
from tests.fake_supabase import FakeSupabase

USER = "00000000-0000-0000-0000-00000000000a"


def utc(hour, minute=0):
    return datetime(2026, 10, 5, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def db():
    d = FakeSupabase()
    d.table("user_notification_settings").insert(
        {"user_id": USER, "enabled": True, "quiet_start": "22:00:00", "quiet_end": "07:00:00"}
    ).execute()
    return d


def test_한국_밤_11시는_방해금지라_보내지_않는다(db):
    # UTC 14:00 = 한국 23:00. UTC 로 비교하면 14시라 방해금지가 아닌 것으로 잘못 본다
    assert ns._can_send_now(db, USER, utc(14)) is False


def test_한국_오후_3시는_보낸다(db):
    # UTC 06:00 = 한국 15:00. UTC 로 비교하면 06시라 방해금지로 잘못 막는다
    assert ns._can_send_now(db, USER, utc(6)) is True


def test_방해금지가_끝나는_한국_아침_7시부터_보낸다(db):
    assert ns._can_send_now(db, USER, utc(21, 59)) is False  # 한국 06:59
    assert ns._can_send_now(db, USER, utc(22, 0)) is True    # 한국 07:00


def test_설정이_없으면_보내고_꺼져_있으면_보내지_않는다():
    db = FakeSupabase()
    assert ns._can_send_now(db, USER, utc(14)) is True
    db.table("user_notification_settings").insert({"user_id": USER, "enabled": False}).execute()
    assert ns._can_send_now(db, USER, utc(6)) is False


def test_같은_날_안에서_끝나는_방해금지도_한국_시각으로_본다():
    db = FakeSupabase()
    db.table("user_notification_settings").insert(
        {"user_id": USER, "enabled": True, "quiet_start": "09:00:00", "quiet_end": "18:00:00"}
    ).execute()
    assert ns._can_send_now(db, USER, utc(1)) is False   # 한국 10:00 → 방해금지
    assert ns._can_send_now(db, USER, utc(10)) is True   # 한국 19:00 → 발송
