from fastapi import APIRouter

router = APIRouter(prefix="/batch", tags=["batch"])


@router.get("/ping")
def batch_ping():
    return {"message": "batch 라우터 정상 작동"}


# FR-ALARM-01 학습 블록 10분 전 알림
@router.post("/alarm/before-block")
def alarm_before_block():
    return {"status": "success", "job": "alarm_before_block"}


# FR-ALARM-02 블록 종료 30분 후 알림
@router.post("/alarm/after-block")
def alarm_after_block():
    return {"status": "success", "job": "alarm_after_block"}


# FR-ALARM-03 21시 하루 마감 알림
@router.post("/alarm/daily-nightly")
def alarm_daily_nightly():
    return {"status": "success", "job": "alarm_daily_nightly"}


# FR-ALARM-04 주간 요약 메일 (일 20:00)
@router.post("/alarm/weekly-summary")
def alarm_weekly_summary():
    return {"status": "success", "job": "alarm_weekly_summary"}