"""직접 만든 가상 공모전으로 목록과 키워드 추천을 연습하는 API."""

import re

from fastapi import APIRouter, Query


router = APIRouter(
    prefix="/demo/contests",
    tags=["contest-demo"],
)


# 아래 20개는 실제 공고가 아닌 가상 데이터입니다.
DEMO_TITLES = [
    "대학생 AI 아이디어 공모전",
    "AI 데이터 분석 공모전",
    "AI 교육 서비스 기획 공모전",
    "AI 환경 문제 해결 공모전",
    "공공 데이터 활용 공모전",
    "교통 데이터 시각화 공모전",
    "웹 서비스 개발 공모전",
    "모바일 앱 개발 공모전",
    "게임 개발 아이디어 공모전",
    "정보보안 아이디어 공모전",
    "로봇 활용 아이디어 공모전",
    "IoT 스마트 캠퍼스 공모전",
    "친환경 에너지 아이디어 공모전",
    "환경 보호 제품 디자인 공모전",
    "지역 문제 해결 서비스 기획 공모전",
    "교육 앱 디자인 공모전",
    "접근성 개선 웹 디자인 공모전",
    "과학 소통 영상 공모전",
    "우주 탐사 기술 아이디어 공모전",
    "바이오 헬스케어 아이디어 공모전",
]


def normalize_keywords(value: str) -> list[str]:
    """쉼표로 구분하고 공백·중복을 제거합니다."""
    terms = [
        term.strip().casefold()
        for term in value.split(",")
        if term.strip()
    ]
    return list(dict.fromkeys(terms))


def keyword_matches(keyword: str, title: str) -> bool:
    """영문은 단어 단위로, 한글은 포함 여부로 비교합니다."""
    normalized_title = title.casefold()

    if keyword.isascii() and keyword.isalnum():
        pattern = (
            rf"(?<![a-z0-9])"
            rf"{re.escape(keyword)}"
            rf"(?![a-z0-9])"
        )
        return re.search(pattern, normalized_title) is not None

    return keyword in normalized_title


@router.get("")
def get_demo_contests(
    keywords: str = Query(default="", max_length=200),
):
    terms = normalize_keywords(keywords)
    items = []

    for index, title in enumerate(DEMO_TITLES, start=1):
        matched = [
            term
            for term in terms
            if keyword_matches(term, title)
        ]

        # 관심 키워드가 있으면 일치하는 공모전만 반환합니다.
        if terms and not matched:
            continue

        reason = None
        if matched:
            reason = (
                f"관심 키워드 {', '.join(matched)}가 "
                "제목에 포함되어 있습니다."
            )

        items.append({
            "id": f"demo-{index:02d}",
            "title": f"[테스트용] {title}",
            "source": "직접 제작한 테스트 데이터",
            "source_url": None,
            "is_demo": True,
            "matched_keywords": matched,
            "score": len(matched),
            "recommendation_reason": reason,
        })

    # 점수가 같으면 원래 목록 순서를 유지합니다.
    items.sort(key=lambda item: -item["score"])

    return {
        "mode": "demo",
        "total": len(items),
        "keywords": terms,
        "items": items,
    }