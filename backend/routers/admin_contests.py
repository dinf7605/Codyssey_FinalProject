"""관리자용 공고 목록. 공고 원문과 내부 오류 메시지는 반환하지 않는다."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from db import get_supabase_client
from utils.admin import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


class ContestInspectionItem(BaseModel):
    id: UUID
    title: str
    host: str
    source: str
    deadline: date
    status: Literal["upcoming", "open", "closed", "unknown"]
    collected_at: datetime
    index_status: Literal["pending", "indexed", "failed", "missing"]
    indexed_at: datetime | None = None


class ContestInspectionPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ContestInspectionItem]


@router.get("/contests", response_model=ContestInspectionPage)
def list_contests(
    response: Response,
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """저장된 전체 공고를 최신 수집 순으로 조회한다. 마감 공고도 포함한다."""
    offset = (page - 1) * page_size
    try:
        db = get_supabase_client()
        result = (
            db.table("contests")
            .select(
                "id,title,host,source,deadline,status,collected_at",
                count="exact",
            )
            .order("collected_at", desc=True)
            .order("id", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if result.count is None:
            raise ValueError("Missing total count")

        rows = result.data or []
        embeddings = {}
        if rows:
            index_result = (
                db.table("contest_embeddings")
                .select("contest_id,index_status,indexed_at")
                .in_("contest_id", [row["id"] for row in rows])
                .execute()
            )
            embeddings = {
                str(row["contest_id"]): row
                for row in (index_result.data or [])
            }

        items = []
        for row in rows:
            index = embeddings.get(str(row["id"]))
            items.append(ContestInspectionItem(
                id=row["id"],
                title=row["title"],
                host=row["host"],
                source=row["source"],
                deadline=row["deadline"],
                status=row["status"],
                collected_at=row["collected_at"],
                index_status=index["index_status"] if index else "missing",
                indexed_at=index.get("indexed_at") if index else None,
            ))

        payload = ContestInspectionPage(
            page=page,
            page_size=page_size,
            total=result.count,
            items=items,
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="공고 점검 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return payload