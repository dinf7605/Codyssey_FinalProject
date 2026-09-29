"""FR-CONT-02: 공고 제목만 1536차원 벡터로 색인·검색한다."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Callable

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536


def enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def embed_text(text: str) -> list[float]:
    from openai import OpenAI

    response = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=20.0).embeddings.create(
        model=MODEL, dimensions=DIMENSIONS, input=text[:200],
    )
    return response.data[0].embedding


def vector_literal(values: list[float]) -> str:
    if len(values) != DIMENSIONS or any(not math.isfinite(value) for value in values):
        raise ValueError("임베딩 차원 또는 값이 올바르지 않습니다")
    return "[" + ",".join(str(value) for value in values) + "]"


def index_titles(db, *, embed: Callable[[str], list[float]] = embed_text, limit: int = 20) -> tuple[int, int]:
    """변경된 최신 위비티 공고 최대 20개만 색인. 실패한 행은 다음 배치에서 재시도."""
    rows = db.table("contests").select("id,title,content_hash").eq(
        "source", "wevity"
    ).order("collected_at", desc=True).limit(min(limit, 20)).execute().data
    if not rows:
        return 0, 0
    existing = db.table("contest_embeddings").select(
        "contest_id,content_hash,index_status"
    ).in_("contest_id", [row["id"] for row in rows]).execute().data
    indexed = {row["contest_id"]: row for row in existing}
    saved = failed = 0
    for row in rows:
        old = indexed.get(row["id"])
        if old and old["content_hash"] == row["content_hash"] and old["index_status"] == "indexed":
            continue
        try:
            embedding = vector_literal(embed(row["title"]))
            now = datetime.now(timezone.utc).isoformat()
            db.table("contest_embeddings").upsert({
                "contest_id": row["id"], "content_hash": row["content_hash"],
                "embedding": embedding, "index_status": "indexed", "error_message": None,
                "indexed_at": now, "updated_at": now,
            }, on_conflict="contest_id").execute()
            saved += 1
        except Exception as exc:  # noqa: BLE001 - 다음 배치에서 다시 시도할 실패 기록
            now = datetime.now(timezone.utc).isoformat()
            db.table("contest_embeddings").upsert({
                "contest_id": row["id"], "content_hash": row["content_hash"],
                "embedding": None, "index_status": "failed",
                "error_message": type(exc).__name__[:100],
                "indexed_at": None, "updated_at": now,
            }, on_conflict="contest_id").execute()
            failed += 1
    return saved, failed


def vector_candidates(db, tags: list[str], *, embed: Callable[[str], list[float]] = embed_text) -> list[dict]:
    query = vector_literal(embed(" ".join(tags)))
    return db.rpc("match_contest_titles", {
        "query_embedding": query, "match_count": 20, "min_similarity": 0.62,
    }).execute().data
