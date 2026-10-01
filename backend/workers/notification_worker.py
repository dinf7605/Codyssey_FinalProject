"""알림 자동 발송 워커 (FR-ALARM-01~04) — 실제 일은 services/alarms.py 가 한다.

main.py를 수정하지 않고 별도 프로세스로 실행한다.

실행:
    python workers/notification_worker.py

| 일             | 주기                 |
|----------------|----------------------|
| 시작 전 알림   | 1분마다              |
| 미완료 알림    | 5분마다              |
| 하루 마감 알림 | 매일 21:00 (한국)    |
| 주간 요약      | 일요일 20:00 (한국)  |
| 재조정 결과    | 5분마다              |
| 공모전 마감    | 30분마다             |
"""

from __future__ import annotations

import sys
from pathlib import Path

# backend 루트를 import 경로에 추가
# workers 폴더 안에서 실행해도 services, db import가 되도록 처리
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

import config  # noqa: F401,E402 - .env 로드
from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402

from db import get_supabase_client  # noqa: E402
from services import alarms  # noqa: E402


def _safe(job):
    """한 번의 실패가 워커 전체를 멈추지 않게 감싼다."""
    def run():
        try:
            result = job(get_supabase_client())
            if result.get("sent"):
                print(f"[알림 워커] {result['job']}: {result['sent']}건 보냄")
        except Exception as exc:  # noqa: BLE001 - 다음 주기에 다시 시도한다
            print(f"[알림 워커] {job.__name__} 실패: {type(exc).__name__}")
    run.__name__ = job.__name__
    return run


def main():
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(_safe(alarms.run_before_block), "interval", minutes=1,
                      id="alarm_before_block", replace_existing=True)
    scheduler.add_job(_safe(alarms.run_after_block), "interval", minutes=5,
                      id="alarm_after_block", replace_existing=True)
    scheduler.add_job(_safe(alarms.run_daily_nightly), "cron", hour=21, minute=0,
                      id="alarm_daily_nightly", replace_existing=True)
    scheduler.add_job(_safe(alarms.run_weekly_summary), "cron", day_of_week="sun", hour=20, minute=0,
                      id="alarm_weekly_summary", replace_existing=True)
    scheduler.add_job(_safe(alarms.run_replan_results), "interval", minutes=5,
                      id="alarm_replan_result", replace_existing=True)
    scheduler.add_job(_safe(alarms.run_contest_deadlines), "interval", minutes=30,
                      id="alarm_contest_deadline", replace_existing=True)

    print("[알림 워커] 시작됨 — 시작 전(1분) · 미완료(5분) · 하루 마감(21시) · 주간 요약(일 20시) · 재조정 결과(5분) · 공모전 마감(30분)")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("[알림 워커] 종료됨")


if __name__ == "__main__":
    main()
