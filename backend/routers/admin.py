from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, Query, Response
from pydantic import BaseModel

from db import get_supabase_client
from services.admin_log_summary import AdminLogSummary, try_summarize_ai_logs

from fastapi import APIRouter, Depends

from utils.admin import require_admin

# 앞으로 추가하는 관리자 API에도 권한 검사를 기본 적용한다.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/ping")
def admin_ping():
    return {"message": "admin 라우터 살아있음"}


@router.get("/me")
def admin_me():
    """관리자 화면에서 접근 권한을 확인하는 API."""
    return {"is_admin": True}


KST = timezone(timedelta(hours=9))


class AdminLogItem(BaseModel):
    id: int
    feature: str
    model: str | None = None
    source: str | None = None
    tool_calls: int
    latency_ms: int | None = None
    created_at: datetime


class AdminLogPage(BaseModel):
    day: date
    timezone: str
    page: int
    page_size: int
    total: int
    items: list[AdminLogItem]
    summary: AdminLogSummary | None = None


@router.get("/ai-logs", response_model=AdminLogPage)
def list_ai_logs(
    response: Response,
    day: date | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """한국 시간 기준 하루의 처리 기록을 조회한다."""
    selected_day = day or datetime.now(KST).date()

    try:
        start = datetime.combine(selected_day, time.min, tzinfo=KST)
        end = start + timedelta(days=1)
        start_utc = start.astimezone(timezone.utc).isoformat()
        end_utc = end.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="조회할 수 없는 날짜입니다")

    offset = (page - 1) * page_size
    columns = "id,feature,model,source,tool_calls,latency_ms,created_at"

    try:
        db = get_supabase_client()
        result = (
            db
            .table("ai_call_logs")
            .select(columns, count="exact")
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if result.count is None:
            raise ValueError("Missing total count")

        payload = AdminLogPage(
            day=selected_day,
            timezone="Asia/Seoul",
            page=page,
            page_size=page_size,
            total=result.count,
            items=result.data or [],
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="AI 처리 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    payload.summary = try_summarize_ai_logs(db, start_utc, end_utc, payload.total)
    response.headers["Cache-Control"] = "no-store"
    return payload

# 공고 점검 하위 라우터도 관리자 권한 검사를 적용한다.
from routers.admin_contests import router as contest_inspection_router

router.include_router(contest_inspection_router)

# DB 현황(테이블별 행 수 · 최근 행, 읽기 전용)도 같은 관리자 권한 검사를 받는다.
from routers.admin_db import router as db_status_router  # noqa: E402

router.include_router(db_status_router)


@router.get("/ai-request-metrics")
def ai_request_metrics(response: Response, day: date | None = Query(default=None)):
    """한국 시간 기준 저장된 학습 분해 요청 통계. 관리자 전용 읽기 API."""
    import os
    from services.admin_request_summary import request_metrics_payload

    selected_day = day or datetime.now(KST).date()
    enabled = os.getenv("AI_REQUEST_METRICS_ENABLED", "").strip() == "1"
    response.headers["Cache-Control"] = "no-store"
    try:
        return request_metrics_payload(get_supabase_client, selected_day, enabled)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="조회할 수 없는 날짜입니다")


@router.get("/ops")
def ops_status(response: Response, days: int = Query(default=7, ge=1, le=30)):
    """운영 상태 (평가 #3 보완) — 준비 상태 · 가동률(GitHub Actions 15분 외부 점검) · 최근 오류 요약. 관리자 전용 읽기 API."""
    from services import ops_monitor

    response.headers["Cache-Control"] = "no-store"
    _, ready = ops_monitor.readiness(get_supabase_client)
    try:
        errors = ops_monitor.error_summary(get_supabase_client(), days)
    except Exception:
        errors = {"status": "unavailable", "days": days}
    return {"ready": ready, "uptime": ops_monitor.uptime_status(), "errors": errors}


@router.get("/ai-budget")
def ai_budget_status(response: Response):
    """FR-ADMIN-02 — 오늘 AI 예상 사용액과 하루 한도. 80% 부터 비회원 추천을 막고, 100% 면 새 AI 호출을 막는다."""
    from services import ai_budget

    response.headers["Cache-Control"] = "no-store"
    try:
        return ai_budget.status(get_supabase_client())
    except Exception:
        raise HTTPException(status_code=503, detail="AI 사용량을 읽지 못했습니다")
