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
