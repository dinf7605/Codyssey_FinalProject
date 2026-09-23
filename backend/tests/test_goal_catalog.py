"""목표 카탈로그 검색 테스트 (FR-GOAL-03 · FR-GOAL-11)."""

from services.goal_catalog import all_tags, popular_goals, search_catalog, suggest_tags_from_history


def test_태그로_검색하면_유사도_내림차순():
    results = search_catalog(["SQLD"], k=5)
    assert results
    assert results[0].goal_id == "cert-sqld"
    assert results[0].similarity > 0
    sims = [c.similarity for c in results]
    assert sims == sorted(sims, reverse=True)


def test_관련_없는_태그는_빈_결과():
    assert search_catalog(["우주공학이런거없음"], k=5) == []


def test_빈_태그는_빈_결과():
    assert search_catalog([], k=5) == []


def test_인기_목록은_인기순():
    goals = popular_goals(k=3)
    assert len(goals) == 3
    pops = [g.popularity for g in goals]
    assert pops == sorted(pops, reverse=True)


def test_인기_목록에서_제외_가능():
    top = popular_goals(k=1)[0]
    without_top = popular_goals(k=1, exclude_ids=[top.goal_id])
    assert without_top[0].goal_id != top.goal_id


def test_이력_기반_유사분야_추천():
    tags = suggest_tags_from_history(["SQLD"], [], k=3)
    assert tags  # SQLD와 겹치는 다른 태그(sql, 데이터분석 등)가 나와야 한다
    assert "sqld" not in tags  # 이미 가진 태그는 다시 추천하지 않는다


def test_이력이_전혀_없으면_빈_추천():
    assert suggest_tags_from_history([], [], k=3) == []


def test_칩_목록은_실제_검색에_쓰이는_분류다():
    tags = all_tags()
    assert "데이터" in tags
    assert len(tags) == len(set(tags))  # 중복 없음
    # 칩에서 아무거나 하나 골랐을 때 실제로 검색이 되어야 한다(전에는 카탈로그
    # title을 그대로 반환해서 뭘 골라도 매칭되는 항목이 하나도 없는 버그가 있었다).
    for tag in tags:
        assert search_catalog([tag], k=1)
