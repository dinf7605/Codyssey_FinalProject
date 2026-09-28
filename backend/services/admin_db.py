"""관리자 DB 현황 (읽기 전용) — 테이블별 행 수 · 마지막 기록 시각 · 최근 행.

팀이 Supabase 대시보드 없이도 "기록이 쌓이는지" 확인하게 하려는 화면이다.
보여 줄 테이블과 열은 아래 CATALOG 에 적은 것만 — 새 테이블을 만들면 여기도 한 줄 추가한다.

개인정보는 줄여서 보여 준다 (관리자도 필요한 만큼만 본다)
  - 이메일 ks***@naver.com · 닉네임 첫 글자만 · 사용자 id 는 앞 8자리
  - 사용자가 직접 쓴 글(학습 메모 · 피드백 사유)은 "12자" 처럼 길이만
  - 학습 메모리 값 · 임베딩 벡터 · 공고 원문 같은 큰 값은 아예 뺀다
수정·삭제는 하지 않는다. 서비스 키로 읽으므로 이 모듈은 관리자 전용 라우터에서만 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_PAGE_SIZE = 50

# 열 표시 방식
SHORT = "short"      # uuid → 앞 8자리
EMAIL = "email"      # ks***@naver.com
NAME = "name"        # 김**
LENGTH = "length"    # 사용자가 쓴 글 → "12자"


@dataclass(frozen=True)
class TableSpec:
    name: str
    label: str
    owner: str
    order_by: str                    # 최근 순 정렬 기준 (시각 열이면 '마지막 기록' 으로도 쓴다)
    columns: tuple[str, ...]
    masks: dict[str, str] = field(default_factory=dict)
    order_is_time: bool = True


CATALOG: tuple[TableSpec, ...] = (
    # 사용자 · 계정 (E)
    TableSpec("users", "회원 프로필", "E", "created_at",
              ("user_id", "email", "nickname", "agree_marketing", "created_at"),
              {"user_id": SHORT, "email": EMAIL, "nickname": NAME}),
    TableSpec("user_notification_settings", "알림 설정", "E", "updated_at",
              ("user_id", "enabled", "reminder_minutes_before", "quiet_start", "quiet_end", "intensity", "updated_at"),
              {"user_id": SHORT}),
    TableSpec("notification_logs", "알림 기록", "E", "sent_at",
              ("id", "user_id", "type", "message", "is_read", "block_id", "sent_at"),
              {"user_id": SHORT, "block_id": SHORT}),
    TableSpec("ai_call_logs", "AI 처리 기록", "C", "created_at",
              ("id", "feature", "model", "source", "tool_calls", "latency_ms", "message", "created_at")),
    TableSpec("ai_request_logs", "AI 요청 기록", "E", "created_at",
              ("id", "run_id", "attempt_no", "model", "succeeded", "error_kind", "outcome", "latency_ms",
               "input_tokens", "output_tokens", "created_at"),
              {"run_id": SHORT}),
    # 목표 (B)
    TableSpec("goal_feedback", "목표 추천 피드백", "B", "created_at",
              ("id", "user_id", "goal_id", "interested", "reason", "created_at"),
              {"user_id": SHORT, "reason": LENGTH}),
    # 일정 · 학습 (C)
    TableSpec("study_plans", "학습 계획", "C", "created_at",
              ("id", "user_id", "goal_title", "deadline", "source", "status", "created_at"),
              {"id": SHORT, "user_id": SHORT}),
    TableSpec("study_units", "학습 단위", "C", "position",
              ("plan_id", "unit_key", "title", "estimated_minutes", "estimated", "removed_at"),
              {"plan_id": SHORT}, order_is_time=False),
    TableSpec("plan_blocks", "일정 블록", "C", "updated_at",
              ("id", "plan_id", "title", "start_at", "minutes", "locked", "done", "done_at", "updated_at"),
              {"id": SHORT, "plan_id": SHORT}),
    TableSpec("study_sessions", "학습 기록", "C", "created_at",
              ("id", "user_id", "block_id", "started_at", "minutes", "expected_minutes", "note", "created_at"),
              {"user_id": SHORT, "block_id": SHORT, "note": LENGTH}),
    TableSpec("plan_reschedule_runs", "재조정 실행", "C", "created_at",
              ("id", "user_id", "summary", "summary_source", "moved", "unplaced", "undone_at", "created_at"),
              {"id": SHORT, "user_id": SHORT}),
    TableSpec("plan_changes", "일정 변경 내역", "C", "created_at",
              ("id", "user_id", "origin", "change_type", "title", "reason", "created_at"),
              {"user_id": SHORT}),
    TableSpec("curriculum_units", "표준 커리큘럼", "C", "id",
              ("id", "goal_title", "subject", "topic", "standard_minutes", "verified"), order_is_time=False),
    # 공모전 (D)
    TableSpec("contests", "공모전 공고", "D", "collected_at",
              ("title", "host", "deadline", "status", "source", "collected_at")),
    TableSpec("contest_embeddings", "공고 색인", "D", "updated_at",
              ("contest_id", "index_status", "indexed_at", "error_message", "updated_at"),
              {"contest_id": SHORT}),
    TableSpec("contest_recommendations", "공모전 추천", "D", "created_at",
              ("user_id", "contest_id", "recommendation_week", "rerank_score", "created_at"),
              {"user_id": SHORT, "contest_id": SHORT}),
    TableSpec("contest_feedback", "공모전 피드백", "D", "created_at",
              ("user_id", "contest_id", "rating", "reason", "created_at"),
              {"user_id": SHORT, "contest_id": SHORT, "reason": LENGTH}),
    TableSpec("user_memories", "학습 메모리", "D", "updated_at",
              ("user_id", "memory_type", "memory_key", "updated_at", "expires_at"),
              {"user_id": SHORT}),
    TableSpec("preparation_time_standards", "준비시간 기준", "D", "id",
              ("field", "category_group", "standard_hours", "sample_size", "active"), order_is_time=False),
    # 무인 작업 (공통)
    TableSpec("batch_runs", "배치 실행", "공통", "started_at",
              ("job_name", "source", "status", "collected_count", "failed_count", "error_message", "started_at",
               "finished_at")),
)

BY_NAME = {spec.name: spec for spec in CATALOG}


class UnknownTable(LookupError):
    """CATALOG 에 없는 테이블 — 임의의 테이블 이름으로 조회하지 못하게 막는다."""


def mask(kind: str | None, value):
    if value is None or kind is None:
        return value
    text = str(value)
    if kind == SHORT:
        return text[:8]
    if kind == EMAIL:
        local, _, domain = text.partition("@")
        return f"{local[:2]}***@{domain}" if domain else "***"
    if kind == NAME:
        return text[:1] + "*" * max(len(text) - 1, 1)
    if kind == LENGTH:
        return f"{len(text)}자"
    return value


def _count_and_latest(db, spec: TableSpec) -> dict:
    try:
        res = (
            db.table(spec.name).select(spec.order_by, count="exact")
            .order(spec.order_by, desc=True).limit(1).execute()
        )
        latest = res.data[0].get(spec.order_by) if (res.data and spec.order_is_time) else None
        return {"name": spec.name, "label": spec.label, "owner": spec.owner,
                "rows": res.count, "latest_at": latest, "error": False}
    except Exception:  # noqa: BLE001 - 한 테이블이 실패해도 나머지 현황은 보여 준다
        return {"name": spec.name, "label": spec.label, "owner": spec.owner,
                "rows": None, "latest_at": None, "error": True}


def overview(db) -> list[dict]:
    """모든 테이블의 행 수와 마지막 기록 시각.

    하나씩 차례로 묻는다 (20개에 약 1초). 공용 클라이언트로 여러 스레드에서 동시에 물으면
    일부 요청이 간헐적으로 실패했다 (09-29 공용 DB 에서 확인).
    """
    return [_count_and_latest(db, spec) for spec in CATALOG]


def recent_rows(db, name: str, page: int = 1, page_size: int = 20) -> dict:
    """한 테이블의 최근 행 (보여 줄 열만, 개인정보는 줄여서)."""
    spec = BY_NAME.get(name)
    if spec is None:
        raise UnknownTable(name)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (max(page, 1) - 1) * page_size
    res = (
        db.table(spec.name).select(",".join(spec.columns), count="exact")
        .order(spec.order_by, desc=spec.order_is_time)
        .range(offset, offset + page_size - 1).execute()
    )
    rows = [{col: mask(spec.masks.get(col), row.get(col)) for col in spec.columns} for row in (res.data or [])]
    return {
        "name": spec.name, "label": spec.label, "owner": spec.owner,
        "columns": list(spec.columns), "masked": sorted(spec.masks),
        "total": res.count, "page": max(page, 1), "page_size": page_size, "rows": rows,
    }
