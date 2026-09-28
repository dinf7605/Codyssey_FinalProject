"""관리자 DB 현황 API (읽기 전용) — services/admin_db.py

  GET /admin/db/tables          테이블별 행 수 · 마지막 기록 시각
  GET /admin/db/tables/{name}   한 테이블의 최근 행 (보여 줄 열만, 개인정보는 줄여서)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from db import get_supabase_client
from services import admin_db
from utils.admin import require_admin

router = APIRouter(prefix="/db", dependencies=[Depends(require_admin)])


@router.get("/tables")
def db_tables(response: Response) -> dict:
    """행 수가 늘어나는지로 기록이 쌓이는지 확인한다. 한 테이블이 실패해도 나머지는 보여 준다."""
    try:
        tables = admin_db.overview(get_supabase_client())
    except Exception:
        raise HTTPException(status_code=503, detail="DB 현황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    response.headers["Cache-Control"] = "no-store"
    return {"tables": tables}


@router.get("/tables/{name}")
def db_table_rows(
    name: str,
    response: Response,
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=admin_db.MAX_PAGE_SIZE),
) -> dict:
    try:
        payload = admin_db.recent_rows(get_supabase_client(), name, page, page_size)
    except admin_db.UnknownTable:
        raise HTTPException(status_code=404, detail="볼 수 없는 테이블입니다.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="행을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    response.headers["Cache-Control"] = "no-store"
    return payload
