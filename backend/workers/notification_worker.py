"""알림 자동 발송 워커.

main.py를 수정하지 않고 별도 프로세스로 실행한다.

실행:
    python workers/notification_worker.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# backend 루트를 import 경로에 추가
# workers 폴더 안에서 실행해도 services, db import가 되도록 처리
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

import config  # noqa: F401 - .env 로드
from apscheduler.schedulers.blocking import BlockingScheduler

from services.notification_scheduler import run_10min_before_notifications


def main():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        run_10min_before_notifications,
        trigger="interval",
        minutes=1,
        id="notify_10min_before",
        replace_existing=True,
    )

    print("[알림 워커] 시작됨 - 1분마다 10분 전 알림 검사")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("[알림 워커] 종료됨")


if __name__ == "__main__":
    main()