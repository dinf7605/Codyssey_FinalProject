"""관리자용 공고 목록. 공고 원문과 내부 오류 메시지는 반환하지 않는다."""

from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from db import get_supabase_client
from utils.admin import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


class ContestInspectionItem(BaseModel):
    id: UUID
    title: str
    host: str
    source: str
    deadline: date | None
    status: Literal["upcoming", "open", "closed", "unknown"]
    collected_at: datetime
    index_status: Literal["pending", "indexed", "failed", "missing"]
    indexed_at: datetime | None = None


class ContestInspectionPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ContestInspectionItem]
    collection_failure_streak: int = 0


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
        try:
            runs = db.table("batch_runs").select("status,failed_count").eq(
                "job_name", "contest.collect"
            ).order("started_at", desc=True).limit(3).execute().data
            payload.collection_failure_streak = next(
                (index for index, run in enumerate(runs)
                 if run["status"] == "success" and not run["failed_count"]), len(runs)
            )
        except Exception:  # noqa: BLE001 - 점검 로그 장애가 공고 목록을 막지 않는다
            pass
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="공고 점검 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return payload


# ── 수집 공고 고치기 (FR-ADMIN-01) ─────────────────────
# 수집기가 잘못 읽은 제목·주최·마감일·상태·분야를 관리자가 직접 고친다. 보낸 항목만 바꾼다.
# 다음 수집 때 같은 공고는 상세를 다시 받지 않으므로(이미 마감일이 있음) 고친 값이 덮어써지지 않는다.

class ContestFix(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    host: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    deadline: date | None = None
    status: Literal["upcoming", "open", "closed", "unknown"] | None = None
    fields: list[str] | None = Field(default=None, max_length=10)

    @field_validator("title", "host")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("fields")
    @classmethod
    def _clean_fields(cls, value):
        if value is None:
            return None
        cleaned = list(dict.fromkeys(v.strip() for v in value if v and v.strip()))
        if any(len(v) > 30 for v in cleaned):
            raise ValueError("분야 이름은 30자 이하여야 합니다")
        return cleaned


@router.patch("/contests/{contest_id}", response_model=ContestInspectionItem)
def fix_contest(contest_id: UUID, req: ContestFix):
    changes = req.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="고칠 항목이 없습니다.")
    if "title" in changes and not changes["title"]:
        raise HTTPException(status_code=400, detail="제목은 비울 수 없습니다.")
    for key in ("start_date", "deadline"):
        if changes.get(key) is not None:
            changes[key] = changes[key].isoformat()
    db = get_supabase_client()
    current = db.table("contests").select("start_date,deadline").eq("id", str(contest_id)).limit(1).execute().data
    if not current:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")
    start = changes.get("start_date", current[0].get("start_date"))
    deadline = changes.get("deadline", current[0].get("deadline"))
    if start and deadline and str(start) > str(deadline):
        raise HTTPException(status_code=400, detail="접수 시작일이 마감일보다 늦을 수 없습니다.")
    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    row = db.table("contests").update(changes).eq("id", str(contest_id)).execute().data[0]
    return ContestInspectionItem(
        id=row["id"], title=row["title"], host=row["host"], source=row["source"],
        deadline=row.get("deadline"), status=row["status"], collected_at=row["collected_at"],
        index_status="missing",
    )
