"""실사용자 테스트 지표 (기획서 8-2절) — DB 에 이미 쌓이는 기록만으로 계산한다.

| 지표 | 계산 | 목표 |
|---|---|---|
| 일정 준수율 | 기간 안에 끝난 시각이 지난 목표 블록 중 완료한 비율 | 60% |
| 체크포인트 달성률 | 일요일이 기간 안에 지난 주마다, 그 주에 놓인 목표 블록을 일요일까지 다 끝냈는지 | 70% |
| 재조정 안정성 | 기간 안에 놓인 블록 중 야간 재조정이 옮긴 블록 비율 | 30% 이하 |
| 목표 추천 평가 | 관심 있음 / 전체 평가 | 80% |
| 공모전 추천 평가 | 도움됨 / 전체 평가 | 90% |

관심 공모전 준비 블록(unit_key 'contest-')은 목표 진도가 아니라서 준수율·체크포인트에서 뺀다 (alarms.next_checkpoint 와 같은 규칙).
DB 접근은 scripts/user_test_metrics.py 가 하고, 여기는 받은 행으로 계산만 한다 (테스트하기 쉽게).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from services.alarms import CONTEST_PREP_PREFIX
from services.plan_store import from_db_time

TARGETS = {"adherence": 0.60, "checkpoint": 0.70, "replan_moved": 0.30, "goal_fit": 0.80, "contest_fit": 0.90}
NUDGE_TYPES = {"after_block", "daily_nightly"}  # 학습 독촉 (FR-ALARM-02) — 알림 강도 검증용


@dataclass
class Ratio:
    hit: int = 0
    total: int = 0

    @property
    def value(self) -> float | None:
        return self.hit / self.total if self.total else None

    def add(self, other: "Ratio") -> None:
        self.hit += other.hit
        self.total += other.total


@dataclass
class ParticipantMetrics:
    user_id: str
    label: str
    adherence: Ratio = field(default_factory=Ratio)
    checkpoint: Ratio = field(default_factory=Ratio)
    replan_moved: Ratio = field(default_factory=Ratio)
    goal_fit: Ratio = field(default_factory=Ratio)
    contest_fit: Ratio = field(default_factory=Ratio)
    study_minutes: int = 0
    study_sessions: int = 0
    active_days: int = 0
    plans: int = 0
    notifications: Counter = field(default_factory=Counter)
    nudges_read: Ratio = field(default_factory=Ratio)


def _is_goal_block(block: dict) -> bool:
    return not str(block.get("unit_key") or "").startswith(CONTEST_PREP_PREFIX)


def _done_by(block: dict, deadline: datetime) -> bool:
    if not block.get("done"):
        return False
    done_at = block.get("done_at")
    return done_at is None or from_db_time(done_at) <= deadline


def compute(
    user_id: str,
    label: str,
    *,
    plans: list[dict],
    blocks: list[dict],
    changes: list[dict],
    goal_feedback: list[dict],
    contest_feedback: list[dict],
    sessions: list[dict],
    notifications: list[dict],
    start: date,
    end: date,
    now: datetime,
) -> ParticipantMetrics:
    """한 참여자의 지표. start~end 는 테스트 기간(양 끝 포함, 한국 날짜), now 는 시간대 없는 한국 시각."""
    window_start = datetime.combine(start, time.min)
    window_end = min(datetime.combine(end + timedelta(days=1), time.min), now)
    m = ParticipantMetrics(user_id=user_id, label=label, plans=len(plans))

    in_window = [b for b in blocks if window_start <= from_db_time(b["start_at"]) < window_end]

    # 일정 준수율 — 끝난 시각이 지난 목표 블록만 센다 (아직 안 온 블록은 판단할 수 없다)
    for b in in_window:
        if _is_goal_block(b) and from_db_time(b["end_at"]) <= window_end:
            m.adherence.total += 1
            m.adherence.hit += bool(b.get("done"))

    # 체크포인트 — 계획마다, 일요일이 지난 주의 목표 블록을 일요일 밤까지 다 끝냈는가
    by_week: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for b in in_window:
        if _is_goal_block(b):
            day = from_db_time(b["start_at"]).date()
            by_week[(b["plan_id"], day - timedelta(days=day.weekday()))].append(b)
    for (_, monday), items in by_week.items():
        sunday_end = datetime.combine(monday + timedelta(days=7), time.min)
        if sunday_end <= window_end:
            m.checkpoint.total += 1
            m.checkpoint.hit += all(_done_by(b, sunday_end) for b in items)

    # 재조정 안정성 — 야간 재조정이 한 번이라도 옮긴 블록 / 기간 안에 놓였던 블록
    moved = {
        c["block_id"] for c in changes
        if c.get("origin") == "nightly" and c.get("change_type") == "move" and c.get("block_id")
        and window_start <= from_db_time(c["created_at"]) < window_end
    }
    placed = {b["id"] for b in in_window} | moved
    m.replan_moved = Ratio(hit=len(moved), total=len(placed))

    m.goal_fit = Ratio(
        hit=sum(1 for f in goal_feedback if f.get("interested")),
        total=len(goal_feedback),
    )
    m.contest_fit = Ratio(
        hit=sum(1 for f in contest_feedback if f.get("rating") == "helpful"),
        total=len(contest_feedback),
    )

    days = set()
    for s in sessions:
        started = from_db_time(s["started_at"])
        if window_start <= started < window_end:
            m.study_sessions += 1
            m.study_minutes += int(s.get("minutes") or 0)
            days.add(started.date())
    m.active_days = len(days)

    for n in notifications:
        if window_start <= from_db_time(n["sent_at"]) < window_end:
            m.notifications[n["type"]] += 1
            if n["type"] in NUDGE_TYPES:
                m.nudges_read.total += 1
                m.nudges_read.hit += bool(n.get("is_read"))
    return m


def total(rows: list[ParticipantMetrics]) -> ParticipantMetrics:
    """참여자 전체 합산 — 비율은 참여자 평균이 아니라 전체 블록·평가 수로 다시 나눈다."""
    t = ParticipantMetrics(user_id="", label="전체")
    for r in rows:
        for name in ("adherence", "checkpoint", "replan_moved", "goal_fit", "contest_fit", "nudges_read"):
            getattr(t, name).add(getattr(r, name))
        t.study_minutes += r.study_minutes
        t.study_sessions += r.study_sessions
        t.active_days += r.active_days
        t.plans += r.plans
        t.notifications.update(r.notifications)
    return t


def _pct(r: Ratio) -> str:
    return "—" if r.value is None else f"{r.value * 100:.0f}% ({r.hit}/{r.total})"


def _verdict(name: str, r: Ratio) -> str:
    if r.value is None:
        return "자료 없음"
    target = TARGETS[name]
    ok = r.value <= target if name == "replan_moved" else r.value >= target
    return "달성" if ok else "미달"


def to_markdown(rows: list[ParticipantMetrics], start: date, end: date, now: datetime) -> str:
    """테스트 리포트에 그대로 붙일 표."""
    t = total(rows)
    lines = [
        f"### 지표 ({start.isoformat()} ~ {end.isoformat()}, {now:%m-%d %H:%M} 기준 · 참여자 {len(rows)}명)",
        "",
        "| 지표 | 결과 | 목표 | 판정 |",
        "|---|---|---|---|",
        f"| 일정 준수율 | {_pct(t.adherence)} | 60% 이상 | {_verdict('adherence', t.adherence)} |",
        f"| 체크포인트 달성률 | {_pct(t.checkpoint)} | 70% 이상 | {_verdict('checkpoint', t.checkpoint)} |",
        f"| 재조정으로 옮긴 블록 | {_pct(t.replan_moved)} | 30% 이하 | {_verdict('replan_moved', t.replan_moved)} |",
        f"| 목표 추천 적합 | {_pct(t.goal_fit)} | 80% 이상 | {_verdict('goal_fit', t.goal_fit)} |",
        f"| 공모전 추천 도움됨 | {_pct(t.contest_fit)} | 90% 이상 | {_verdict('contest_fit', t.contest_fit)} |",
        "",
        "| 참여자 | 계획 | 학습 | 공부한 날 | 일정 준수 | 체크포인트 | 재조정 이동 | 목표 추천 | 공모전 추천 | 알림 (독촉 읽음) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        notes = sum(r.notifications.values())
        lines.append(
            f"| {r.label} | {r.plans} | {r.study_minutes}분 · {r.study_sessions}회 | {r.active_days}일 | "
            f"{_pct(r.adherence)} | {_pct(r.checkpoint)} | {_pct(r.replan_moved)} | "
            f"{_pct(r.goal_fit)} | {_pct(r.contest_fit)} | {notes}건 ({_pct(r.nudges_read)}) |"
        )
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(t.notifications.items())) or "없음"
    lines += ["", f"알림 종류별: {kinds}"]
    return "\n".join(lines)
