from datetime import date

from services.wevity_parser import parse_wevity_detail, parse_wevity_list


LIST_HTML = """
<ul>
  <li>
    <div class="tit">
      <a href="?c=find&amp;gbn=view&amp;gp=1&amp;ix=111155">
        N.O.V.A. 2026 대회 <span class="stat new">신규</span>
      </a>
      <div class="sub-tit">분야 : 웹/모바일/IT, 과학/공학</div>
    </div>
    <div class="organ">테스트 주최기관</div>
    <div class="day">D-11 <span class="dday ing">접수중</span></div>
  </li>
  <li>
    <div class="tit">
      <a href="?c=find&amp;gbn=view&amp;gp=1&amp;ix=222222">마감 공모전</a>
      <div class="sub-tit">분야 : 디자인</div>
    </div>
    <div class="organ">다른 기관</div>
    <div class="day">D+4 <span class="dday end">마감</span></div>
  </li>
  <li>
    <div class="tit">
      <a href="?c=find&amp;gbn=view&amp;gp=1&amp;ix=111155">중복 항목</a>
    </div>
  </li>
</ul>
"""


DETAIL_HTML = """
<div class="tit-area"><h6 class="tit">N.O.V.A. 2026 대회</h6></div>
<ul class="cd-info-list">
  <li><span class="tit">분야</span>웹/모바일/IT, 과학/공학</li>
  <li><span class="tit">응모대상</span>제한없음</li>
  <li><span class="tit">주최/주관</span>테스트 기관 / 테스트 기관</li>
  <li class="dday-area">
    <span class="tit">접수기간</span>2026-09-13 ~ 2026-10-03
    <span class="cil-dday">D-11</span>
  </li>
  <li><span class="tit">홈페이지</span><a href="https://example.org/contest">공식 사이트</a></li>
</ul>
<div id="viewContents"><div>공모 주제</div><div>지원 자격 안내</div></div>
"""


def test_parse_wevity_list_extracts_and_deduplicates_items():
    items = parse_wevity_list(LIST_HTML)

    assert len(items) == 2
    assert items[0].source_id == "111155"
    assert items[0].title == "N.O.V.A. 2026 대회"
    assert items[0].fields == ["웹/모바일/IT", "과학/공학"]
    assert items[0].host == "테스트 주최기관"
    assert items[0].d_day == 11
    assert items[0].status == "접수중"
    assert items[1].d_day == -4


def test_parse_wevity_detail_extracts_allowed_metadata():
    detail = parse_wevity_detail(
        DETAIL_HTML,
        source_url="https://www.wevity.com/?c=find&gbn=viewok&ix=111155",
    )

    assert detail.source_id == "111155"
    assert detail.title == "N.O.V.A. 2026 대회"
    assert detail.fields == ["웹/모바일/IT", "과학/공학"]
    assert detail.eligibility == "제한없음"
    assert detail.start_date == date(2026, 9, 13)
    assert detail.deadline == date(2026, 10, 3)
    assert detail.official_url == "https://example.org/contest"
    assert detail.raw_text == "공모 주제 지원 자격 안내"


def test_parse_wevity_detail_rejects_non_detail_html():
    try:
        parse_wevity_detail("<html></html>", source_url="https://www.wevity.com/")
    except ValueError as exc:
        assert "제목 또는 공고 ID" in str(exc)
    else:
        raise AssertionError("잘못된 상세 HTML은 거부해야 합니다")
