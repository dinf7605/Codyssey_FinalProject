"""학습 일정 내보내기 (FR-PLAN-08) — 표준 iCalendar(.ics) 파일.

구글 캘린더에 직접 쓰려면 캘린더 쓰기 권한(민감 권한)과 구글 심사가 필요하다.
.ics 파일은 구글·애플·아웃룩 캘린더 모두 '가져오기'로 넣을 수 있어 권한 없이 같은 목적을 이룬다.

  - 아직 안 한, 오늘 이후의 블록만 넣는다 (지난 블록·완료한 블록은 넣지 않는다)
  - UID 를 블록 id 로 둔다 — 다시 내보내 가져오면 캘린더 앱이 같은 일정으로 보고 시각만 고친다
  - 시각은 UTC(Z)로 쓴다 — 시간대 정의 없이 어느 캘린더에서나 한국 시각으로 맞게 보인다
"""

from __future__ import annotations

from datetime import datetime, timezone

from schemas.plan import Block
from services.plan_store import KST

PRODID = "-//StudyPace//Study Plan//KO"


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """한 줄 75바이트 제한 (RFC 5545 3.1). 이어지는 줄은 공백 한 칸으로 시작한다."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + rest for rest in out[1:]]


def _utc(value: datetime) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=KST)
    return aware.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(goal_title: str, blocks: list[Block], now: datetime) -> str:
    """now 는 시간대 없는 한국 시각. 오늘 이후의 안 한 블록만 담는다."""
    today = now.date()
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('StudyPace · ' + goal_title)}", "X-WR-TIMEZONE:Asia/Seoul",
    ]
    stamp = _utc(now)
    for block in sorted(blocks, key=lambda b: b.start):
        if block.done or block.start.date() < today:
            continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:{block.id}@studypace",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(block.start)}",
            f"DTEND:{_utc(block.end)}",
            f"SUMMARY:{_escape(block.title)}",
            f"DESCRIPTION:{_escape(f'StudyPace 학습 블록 · {goal_title} · {block.minutes}분')}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
