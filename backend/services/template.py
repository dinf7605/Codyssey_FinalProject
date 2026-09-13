"""표준 커리큘럼 템플릿 — AI가 실패했을 때 쓰는 대체 분해 (AI기능명세 6).

여기가 있어야 "LLM이 실패해도 일정은 항상 만들어진다"가 성립한다.
템플릿으로 만든 단위는 estimated=True 로 표시해서 화면에서 '추정'임을 밝힌다.
"""

from __future__ import annotations

from schemas.plan import StudyUnit

_TEMPLATES: dict[str, list[tuple[str, int]]] = {
    "정보처리기사": [
        ("소프트웨어 설계 - 요구사항 확인", 120),
        ("소프트웨어 설계 - 화면 설계", 90),
        ("소프트웨어 개발 - 데이터 입출력", 120),
        ("소프트웨어 개발 - 통합 구현", 90),
        ("데이터베이스 구축 - 논리 데이터베이스", 120),
        ("데이터베이스 구축 - 물리 데이터베이스", 120),
        ("프로그래밍 언어 활용 - 기본 문법", 120),
        ("프로그래밍 언어 활용 - 응용", 90),
        ("정보시스템 구축관리 - 보안", 120),
        ("기출문제 풀이 1회차", 90),
        ("기출문제 풀이 2회차", 90),
        ("오답 정리 및 복습", 60),
    ],
    "SQLD": [
        ("데이터 모델링의 이해", 90),
        ("엔터티와 속성", 60),
        ("관계와 식별자", 90),
        ("정규화와 반정규화", 120),
        ("SQL 기본 - SELECT", 90),
        ("SQL 기본 - 조인", 120),
        ("SQL 활용 - 서브쿼리", 120),
        ("SQL 활용 - 윈도우 함수", 90),
        ("기출문제 풀이", 90),
        ("오답 정리 및 복습", 60),
    ],
}

_GENERIC: list[tuple[str, int]] = [
    ("전체 범위 훑어보기", 90),
    ("핵심 개념 정리 1", 120),
    ("핵심 개념 정리 2", 120),
    ("핵심 개념 정리 3", 120),
    ("연습문제 풀이 1", 90),
    ("연습문제 풀이 2", 90),
    ("약점 보완", 90),
    ("최종 복습", 60),
]


def template_units(goal_title: str) -> list[StudyUnit]:
    """목표 이름으로 템플릿을 골라 학습 단위를 만든다.

    앞 단위를 끝내야 다음으로 넘어가도록 일렬 선행 관계를 건다 —
    근거 없이 병렬로 풀어 두면 배치가 뒤죽박죽이 된다.
    """
    rows = _GENERIC
    for key, value in _TEMPLATES.items():
        if key in goal_title:
            rows = value
            break

    units: list[StudyUnit] = []
    for i, (title, minutes) in enumerate(rows, start=1):
        units.append(
            StudyUnit(
                id=f"tpl-{i:02d}",
                title=title,
                estimated_minutes=minutes,
                prerequisites=[f"tpl-{i - 1:02d}"] if i > 1 else [],
                estimated=True,  # 표준 커리큘럼 기반 추정치임을 표시
            )
        )
    return units
