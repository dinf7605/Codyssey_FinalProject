"""위비티 HTML을 네트워크 요청 없이 해석하는 파서.

이 모듈은 HTML 문자열만 입력받는다. 실제 HTTP 요청과 실행 주기는 사용 허락을
확인한 뒤 별도 수집기에서 연결한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class WevityListItem:
    source_id: str
    title: str
    fields: list[str]
    host: str
    d_day: int | None
    status: str
    source_url: str


@dataclass(frozen=True)
class WevityDetail:
    source_id: str
    title: str
    fields: list[str] = field(default_factory=list)
    host: str = ""
    eligibility: str | None = None
    start_date: date | None = None
    deadline: date | None = None
    official_url: str | None = None
    raw_text: str = ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _source_id(url: str) -> str | None:
    return parse_qs(urlsplit(url).query).get("ix", [None])[0]


def _title_without_badges(link) -> str:
    direct_text = " ".join(str(value) for value in link.find_all(string=True, recursive=False))
    return _clean_text(direct_text) or _clean_text(link.get_text(" ", strip=True))


def parse_wevity_list(
    html: str,
    *,
    base_url: str = "https://www.wevity.com",
) -> list[WevityListItem]:
    """목록 HTML에서 공고를 추출하고 같은 ix 항목은 한 번만 반환한다."""

    soup = BeautifulSoup(html, "html.parser")
    items: list[WevityListItem] = []
    seen: set[str] = set()

    for row in soup.find_all("li"):
        link = row.select_one('.tit a[href*="gbn=view"][href*="ix="]')
        if link is None:
            continue

        source_url = urljoin(base_url, link.get("href", ""))
        source_id = _source_id(source_url)
        if source_id is None or source_id in seen:
            continue

        field_node = row.select_one(".sub-tit")
        field_text = _clean_text(field_node.get_text(" ", strip=True)) if field_node else ""
        field_text = re.sub(r"^분야\s*:\s*", "", field_text)
        fields = [_clean_text(value) for value in field_text.split(",") if _clean_text(value)]

        host_node = row.select_one(".organ")
        day_node = row.select_one(".day")
        status_node = row.select_one(".dday")
        day_text = _clean_text(day_node.get_text(" ", strip=True)) if day_node else ""
        day_match = re.search(r"D([+-])(\d+)", day_text)
        d_day = None
        if day_match:
            amount = int(day_match.group(2))
            d_day = amount if day_match.group(1) == "-" else -amount

        seen.add(source_id)
        items.append(
            WevityListItem(
                source_id=source_id,
                title=_title_without_badges(link),
                fields=fields,
                host=_clean_text(host_node.get_text(" ", strip=True)) if host_node else "",
                d_day=d_day,
                status=_clean_text(status_node.get_text(" ", strip=True)) if status_node else "unknown",
                source_url=source_url,
            )
        )

    return items


def parse_wevity_detail(html: str, *, source_url: str) -> WevityDetail:
    """상세 HTML에서 저장 대상으로 합의한 텍스트 정보만 추출한다."""

    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one(".tit-area h6.tit")
    source_id = _source_id(source_url)
    if title_node is None or source_id is None:
        raise ValueError("위비티 상세 페이지의 제목 또는 공고 ID를 찾지 못했습니다")

    metadata: dict[str, str] = {}
    official_url: str | None = None
    for row in soup.select(".cd-info-list li"):
        label_node = row.select_one("span.tit")
        if label_node is None:
            continue
        label = _clean_text(label_node.get_text(" ", strip=True))
        parts = list(row.stripped_strings)
        value_parts = parts[1:] if parts and parts[0] == label else parts
        value = _clean_text(" ".join(value_parts))
        if label == "접수기간":
            value = re.sub(r"\s+D[+-]\d+.*$", "", value).strip()
        metadata[label] = value
        if label == "홈페이지":
            link = row.find("a", href=True)
            if link:
                official_url = urljoin(source_url, link["href"])

    start_date = None
    deadline = None
    period = metadata.get("접수기간", "")
    date_values = re.findall(r"\d{4}-\d{2}-\d{2}", period)
    if len(date_values) >= 2:
        start_date = date.fromisoformat(date_values[0])
        deadline = date.fromisoformat(date_values[1])

    field_text = metadata.get("분야", "")
    fields = [_clean_text(value) for value in field_text.split(",") if _clean_text(value)]
    body = soup.select_one("#viewContents")

    return WevityDetail(
        source_id=source_id,
        title=_clean_text(title_node.get_text(" ", strip=True)),
        fields=fields,
        host=metadata.get("주최/주관", ""),
        eligibility=metadata.get("응모대상") or None,
        start_date=start_date,
        deadline=deadline,
        official_url=official_url,
        raw_text=_clean_text(body.get_text(" ", strip=True)) if body else "",
    )
