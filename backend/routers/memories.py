"""FR-MEM-01/02: 계정별 메모리 조회·관심 태그 저장·즉시 삭제."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from schemas.memory import InterestTagsInput, Memory
from utils.auth import get_current_user

router = APIRouter(prefix="/memories", tags=["memories"])
User = Annotated[object, Depends(get_current_user)]
Db = Annotated[object, Depends(get_db)]


@router.get("", response_model=list[Memory])
def list_memories(user: User, db: Db) -> list[Memory]:
    rows = db.table("user_memories").select(
        "id,memory_type,memory_key,value,basis,updated_at,expires_at"
    ).eq("user_id", str(user.id)).order("updated_at", desc=True).execute().data
    now = datetime.now(timezone.utc)
    return [Memory.model_validate(row) for row in rows
            if datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) > now]


@router.put("/interest-tags", response_model=Memory)
def save_interest_tags(payload: InterestTagsInput, user: User, db: Db) -> Memory:
    now = datetime.now(timezone.utc)
    row = {
        "user_id": str(user.id), "memory_type": "interest_tags", "memory_key": "default",
        "value": {"tags": payload.tags}, "basis": "사용자가 직접 저장한 관심 분야",
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=365)).isoformat(),
    }
    saved = db.table("user_memories").upsert(
        row, on_conflict="user_id,memory_type,memory_key"
    ).execute().data[0]
    return Memory.model_validate(saved)


@router.delete("", status_code=204)
def delete_all_memories(user: User, db: Db) -> None:
    db.table("user_memories").delete().eq("user_id", str(user.id)).execute()


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str, user: User, db: Db) -> None:
    deleted = db.table("user_memories").delete().eq("id", memory_id).eq(
        "user_id", str(user.id)
    ).execute().data
    if not deleted:
        raise HTTPException(status_code=404, detail="저장된 정보를 찾을 수 없습니다")
