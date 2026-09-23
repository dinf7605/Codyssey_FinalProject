"""목표 카탈로그 검색 (FR-GOAL-03 · FR-GOAL-11) — 담당 B.

AI기능명세의 RAG ① "목표 카탈로그" 자리다. 지금은 Supabase + pgvector 임베딩이
아직 붙지 않았으므로, 태그 겹침 기반의 결정론적 유사도로 자리를 채운다.
decomposer.py 가 ANTHROPIC_API_KEY 없으면 템플릿으로 도는 것과 같은 이유다 —
키·인프라가 없어도 로컬에서 온보딩 전체 흐름을 끝까지 눌러볼 수 있어야 한다.

실제 임베딩 검색으로 바꿀 때는 이 파일의 search_catalog() 안쪽만 바꾸면 되고,
라우터·프론트는 건드릴 필요가 없다 (services/agent_tools.py 가 잡아둔 것과 같은 경계).
"""

from __future__ import annotations

from statistics import median

from schemas.goal import GoalCandidate

# ── 목업 카탈로그 ──────────────────────────────────────────
# 실제로는 Supabase 의 목표 카탈로그 테이블 + pgvector 로 대체한다.
_CATALOG: list[dict] = [
    {
        "goal_id": "cert-info-eng",
        "title": "정보처리기사 필기",
        "field": "IT·개발",
        "tags": ["정보처리기사", "it·개발", "데이터분석", "백엔드"],
        "kind": "cert",
        "standard_hours": 120,
        "deadline": "2026-12-06",
        "popularity": 982,
    },
    {
        "goal_id": "cert-sqld",
        "title": "SQLD (SQL 개발자)",
        "field": "데이터",
        "tags": ["sqld", "sql", "데이터분석", "db", "정보처리기사"],
        "kind": "cert",
        "standard_hours": 48,
        "deadline": "2026-11-15",
        "popularity": 1204,
    },
    {
        "goal_id": "cert-adsp",
        "title": "ADsP (데이터분석 준전문가)",
        "field": "데이터",
        "tags": ["adsp", "데이터분석", "통계"],
        "kind": "cert",
        "standard_hours": 40,
        "deadline": "2026-11-22",
        "popularity": 511,
    },
    {
        "goal_id": "cert-comp1",
        "title": "컴퓨터활용능력 1급",
        "field": "사무·자동화",
        "tags": ["컴활", "컴활1급", "엑셀", "사무"],
        "kind": "cert",
        "standard_hours": 60,
        "deadline": "2026-11-08",
        "popularity": 733,
    },
    {
        "goal_id": "cert-toeic",
        "title": "토익 900+",
        "field": "어학",
        "tags": ["토익", "어학", "영어"],
        "kind": "cert",
        "standard_hours": 100,
        "deadline": None,
        "popularity": 640,
    },
    {
        "goal_id": "cert-hist",
        "title": "한국사능력검정 1급",
        "field": "인문",
        "tags": ["한국사", "한국사능력검정", "인문"],
        "kind": "cert",
        "standard_hours": 50,
        "deadline": "2026-10-25",
        "popularity": 402,
    },
    {
        "goal_id": "cert-elec",
        "title": "전기기사",
        "field": "공학",
        "tags": ["전기기사", "전기", "공학"],
        "kind": "cert",
        "standard_hours": 200,
        "deadline": "2027-02-14",
        "popularity": 355,
    },
    {
        "goal_id": "contest-ux",
        "title": "UX 아이디어 공모전",
        "field": "디자인·기획",
        "tags": ["공모전", "ux", "디자인", "기획", "마케팅"],
        "kind": "contest",
        "standard_hours": 20,
        "deadline": "2026-10-13",
        "popularity": 640,
    },
    {
        "goal_id": "contest-publicdata",
        "title": "공공데이터 활용 아이디어 공모전",
        "field": "IT·데이터",
        "tags": ["공모전", "공공데이터", "데이터분석", "it·개발"],
        "kind": "contest",
        "standard_hours": 24,
        "deadline": "2026-10-05",
        "popularity": 588,
    },
    {
        "goal_id": "contest-marketing",
        "title": "대학생 마케팅 공모전",
        "field": "마케팅",
        "tags": ["공모전", "마케팅", "기획"],
        "kind": "contest",
        "standard_hours": 18,
        "deadline": "2026-10-24",
        "popularity": 470,
    },
]

_STANDARD_HOURS_MEDIAN = median(item["standard_hours"] for item in _CATALOG)


def _normalize(tags: list[str]) -> list[str]:
    return [t.strip().lower() for t in tags if t and t.strip()]


def _match_pool(item: dict) -> set[str]:
    """이 항목과 매칭할 때 비교 대상이 되는 태그 전체(세부 tags + 상위 field)."""
    return set(item["tags"]) | {item["field"].strip().lower()}


def _similarity(query_tags: list[str], item_tags: list[str]) -> float:
    """선택한 태그 중 이 항목과 겹치는 비율(재현율)로 0~1 사이 점수를 만든다.

    처음엔 자카드 유사도(교집합/합집합)를 썼는데, 관심분야는 보통 1~2개만
    고르는 반면 카탈로그 항목은 tags를 3~5개씩 갖고 있어서 분모(합집합)가
    항상 커져 버려 아무리 정확히 골라도 임계값을 못 넘는 문제가 있었다.
    "고른 태그가 이 항목 태그에 얼마나 들어있나"만 보는 재현율로 바꿔서,
    태그 하나를 정확히 골랐으면 그 항목은 확실히 매칭되도록 한다.
    """
    q, t = set(query_tags), set(item_tags)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


def _to_candidate(item: dict, similarity: float = 0.0) -> GoalCandidate:
    estimated = item["standard_hours"] <= 0
    return GoalCandidate(
        goal_id=item["goal_id"],
        title=item["title"],
        field=item["field"],
        tags=item["tags"],
        kind=item["kind"],
        standard_hours=item["standard_hours"] if not estimated else int(_STANDARD_HOURS_MEDIAN),
        deadline=item["deadline"],
        similarity=round(similarity, 3),
        estimated_hours=estimated,
        popularity=item["popularity"],
    )


def search_catalog(tags: list[str], k: int = 20) -> list[GoalCandidate]:
    """FR-GOAL-03 — 관심 태그로 후보를 검색한다. 후보 최대 k건, 유사도 내림차순."""
    q = _normalize(tags)
    if not q:
        return []
    scored = [(_similarity(q, _match_pool(item)), item) for item in _CATALOG]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [_to_candidate(item, sim) for sim, item in scored[:k]]


def popular_goals(k: int = 3, exclude_ids: list[str] | None = None) -> list[GoalCandidate]:
    """FR-GOAL-11 / FR-GOAL-03 폴백 — 이력이 없을 때 보여줄 인기 목표 목록."""
    exclude = set(exclude_ids or [])
    items = [item for item in _CATALOG if item["goal_id"] not in exclude]
    items.sort(key=lambda item: item["popularity"], reverse=True)
    return [_to_candidate(item) for item in items[:k]]


def suggest_tags_from_history(recent_tags: list[str], recent_fields: list[str], k: int = 5) -> list[str]:
    """FR-GOAL-11 — 최근 태그·조회 분야에서 유사 분야 태그를 뽑는다.

    실제로는 임베딩 유사도로 카탈로그를 훑지만, 여기서는 이력 자체에 담긴 태그와
    그 태그를 가진 카탈로그 항목들의 다른 태그를 모아 상위 k개를 반환한다.
    """
    seed = set(_normalize(recent_tags)) | set(_normalize(recent_fields))
    if not seed:
        return []
    related: dict[str, int] = {}
    for item in _CATALOG:
        item_tags = _match_pool(item)  # tags + field 둘 다 매칭 대상(all_tags()와 일관성 유지)
        if not (item_tags & seed):
            continue
        for tag in item_tags - seed:
            related[tag] = related.get(tag, 0) + item["popularity"]
    ranked = sorted(related.items(), key=lambda kv: kv[1], reverse=True)
    return [tag for tag, _ in ranked[:k]] or sorted(seed)[:k]


def all_tags() -> list[str]:
    """관심분야 입력 화면(FR-GOAL-01)의 칩 목록.

    카탈로그 항목의 title(예: "정보처리기사 필기")을 그대로 칩으로 보여준 적이
    있었는데, 그 문자열은 어느 항목의 tags에도 정확히 안 들어있어서 뭘 골라도
    유사도가 항상 0이 되어 매번 인기 목록 폴백으로 빠지는 버그가 있었다.
    그렇다고 세부 tags(sqld, db, 백엔드 ...)를 그대로 다 보여주면 20개 넘게
    나열돼 관심분야 칩치고 너무 잡다해진다. 그래서 항목의 상위 분류인 field
    (예: "IT·개발", "데이터")를 칩으로 쓴다 — search_catalog()가 tags뿐 아니라
    field도 매칭 대상에 포함하므로(_match_pool) 여기서 고른 값은 항상 실제로
    검색된다. 인기도 합산 기준 내림차순으로 정렬한다.
    """
    counts: dict[str, int] = {}
    for item in _CATALOG:
        field = item["field"]
        counts[field] = counts.get(field, 0) + item["popularity"]
    return [field for field, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]
