"""알림 배치 (FR-ALARM-01~04) — 실제 일은 services/alarms.py 가 한다.

평소에는 workers/notification_worker.py 가 주기적으로 돌린다. 이 API 는 외부 스케줄러(GitHub Actions)나
수동 확인용이다. 사람이 부르는 API 가 아니므로 로그인 대신 X-Batch-Key(.env 의 BATCH_SECRET)를 본다.
"""

import os

from fastapi import APIRouter, Header, HTTPException

from db import get_supabase_client
from services import alarms
from services.replan import batch_key_ok

router = APIRouter(prefix="/batch", tags=["batch"])


@router.get("/ping")
def batch_ping():
    # 배치 현황을 한눈에 보여준다
    return {
        "status": "ok",
        "module": "batch",
        "alarm_jobs": 6,
        "jobs": [
            "before-block",
            "after-block",
            "daily-nightly",
            "weekly-summary",
            "replan-result",
            "contest-deadline",
        ],
    }


def _run(job, x_batch_key: str | None) -> dict:
    expected = os.getenv("BATCH_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="BATCH_SECRET 환경변수가 없어 배치를 실행하지 않습니다.")
    if not batch_key_ok(x_batch_key, expected):
        raise HTTPException(status_code=401, detail="배치 키가 맞지 않습니다.")
    return {"status": "success", **job(get_supabase_client())}


# FR-ALARM-01 학습 블록 시작 N분 전 알림 (사용자 설정, 기본 10분)
@router.post("/alarm/before-block", description="FR-ALARM-01 학습 블록 시작 전 알림 (1분마다)")
def alarm_before_block(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_before_block, x_batch_key)


# FR-ALARM-02 블록 종료 30분 후 미완료 알림
@router.post("/alarm/after-block", description="FR-ALARM-02 블록 종료 30분 후 미완료 알림 (5분마다)")
def alarm_after_block(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_after_block, x_batch_key)


# 21시 하루 마감 알림 (알림 강도 '강' + 학습 독촉)
@router.post("/alarm/daily-nightly", description="21시 하루 마감 알림 — 알림 강도 '강' + 학습 독촉")
def alarm_daily_nightly(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_daily_nightly, x_batch_key)


# FR-ALARM-04 주간 진도 요약 (일 20:00)
@router.post("/alarm/weekly-summary", description="FR-ALARM-04 주간 진도 요약 (일요일 20시)")
def alarm_weekly_summary(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_weekly_summary, x_batch_key)


# FR-MY-03 재조정 결과 — 야간 재조정이 블록을 옮겼으면 방해금지가 끝난 뒤 알린다
@router.post("/alarm/replan-result", description="FR-MY-03 재조정 결과 알림 (5분마다)")
def alarm_replan_result(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_replan_results, x_batch_key)


# FR-MY-05 관심 공모전 마감 24시간 전 — 알림 전체 끄기와 별개 동의
@router.post("/alarm/contest-deadline", description="FR-MY-05 관심 공모전 마감 24시간 전 알림 (30분마다)")
def alarm_contest_deadline(x_batch_key: str | None = Header(default=None)):
    return _run(alarms.run_contest_deadlines, x_batch_key)
