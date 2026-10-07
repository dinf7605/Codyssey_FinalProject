"""운영 보고서 (평가 #3 보완, 10-07) — 가동률 · 장애 이력 · 배포 확인 · 정해진 시각 작업 · 서버 오류 요약을 마크다운으로.

실행 (backend 폴더에서):
    python -m scripts.ops_report                                   # 최근 7일, GitHub 기록만
    python -m scripts.ops_report --days 14 --with-db --out ../docs/ops-report.md

  - GitHub 실행 기록은 공개 저장소라 토큰 없이 읽는다 (GITHUB_TOKEN 이 있으면 쓴다 — 시간당 호출 한도가 늘어난다)
  - --with-db 는 .env 의 Supabase 키로 error_logs 를 읽는다 (메시지는 저장할 때 이미 이메일·id 를 가렸다)
  - 계산 규칙은 services/ops_monitor.py (가동률 = 정상 점검 / 끝난 점검, 취소·건너뜀 제외)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from services import ops_monitor
from services.ops_monitor import KST, fetch_runs, parse_time, uptime_from_runs

WORKFLOWS = (
    ("uptime.yml", "외부 점검 (15분)"),
    ("deploy-check.yml", "배포 후 확인"),
    ("contest-jobs.yml", "공고 수집 · 추천"),
    ("plan-jobs.yml", "야간 재조정 (03:00)"),
    ("ci.yml", "CI (테스트 · lint · build)"),
)


def _kst(ts: str | None) -> str:
    return parse_time(ts).astimezone(KST).strftime("%m-%d %H:%M") if ts else "—"


def _uptime_section(runs) -> list[str]:
    lines = ["## 1. 가동률 — 외부 점검 (`uptime.yml`, 15분마다)", ""]
    if isinstance(runs, Exception):
        return lines + [f"GitHub 기록을 읽지 못했다 ({type(runs).__name__}).", ""]
    u = uptime_from_runs(runs)
    if not u["checks"]:
        return lines + ["아직 점검 기록이 없다 — `uptime.yml` 이 main 에 올라간 뒤부터 15분마다 쌓인다.", ""]
    lines += [
        "| 항목 | 값 |",
        "|---|---|",
        f"| 점검 | {u['checks']}회 ({_kst(u['first_check'])} ~ {_kst(u['last_check'])} KST) |",
        f"| 정상 | {u['ok']}회 |",
        f"| **가동률** | **{u['uptime_percent']}%** |",
        f"| 장애 | {len(u['incidents'])}건 |",
        "",
    ]
    if u["incidents"]:
        lines += ["| 시작 (KST) | 복구 | 길이 | 실패한 점검 |", "|---|---|---|---|"]
        for i in u["incidents"]:
            length = f"{i['minutes']}분" if i["minutes"] is not None else "—"
            lines.append(f"| {_kst(i['start'])} | {_kst(i['end']) if i['end'] else '복구 전'} | {length} | "
                         f"[{i['failed_checks']}회]({i['url']}) |")
        lines.append("")
    return lines


def _workflow_section(runs_by: dict) -> list[str]:
    lines = [
        "## 2. 배포 확인 · 정해진 시각 작업 · CI",
        "",
        "| 워크플로 | 실행 | 성공 | 실패 | 성공률 | 마지막 실패 (KST) |",
        "|---|---|---|---|---|---|",
    ]
    for workflow, label in WORKFLOWS[1:]:
        runs = runs_by[workflow]
        if isinstance(runs, Exception):
            lines.append(f"| {label} (`{workflow}`) | 읽기 실패 | | | | |")
            continue
        done = sorted((r for r in runs if r.get("conclusion") in ops_monitor.FINISHED),
                      key=lambda r: r["created_at"], reverse=True)
        bad = [r for r in done if r["conclusion"] != "success"]
        rate = f"{(len(done) - len(bad)) / len(done) * 100:.1f}%" if done else "—"
        last = f"[{_kst(bad[0]['created_at'])}]({bad[0]['html_url']})" if bad else "—"
        lines.append(f"| {label} (`{workflow}`) | {len(done)} | {len(done) - len(bad)} | {len(bad)} | {rate} | {last} |")
    return lines + [""]


def _error_section(db, days: int, now: datetime) -> list[str]:
    lines = ["## 3. 서버 오류 · 예외 (`error_logs`)", ""]
    if db is None:
        return lines + ["`--with-db` 를 주면 Supabase 의 error_logs 를 요약한다.", ""]
    s = ops_monitor.error_summary(db, days=days, now=now, recent=10)
    if s["status"] == "unavailable":
        return lines + ["error_logs 를 읽지 못했다 — migration 020 적용 여부 확인.", ""]
    if s["status"] == "empty":
        return lines + [f"최근 {days}일 기록된 5xx 응답 · 처리되지 않은 예외 · 워커 작업 실패 없음.", ""]
    source = " · ".join(f"{'API' if k == 'api' else '알림 워커'} {v}건" for k, v in s["by_source"].items())
    lines += [f"총 **{s['total']}건** ({source}){' — 2000건에서 잘림' if s['truncated'] else ''}", ""]
    lines += ["| 날짜 | 건수 |", "|---|---|"] + [f"| {d['day']} | {d['count']} |" for d in s["by_day"] if d["count"]]
    lines += ["", "| 많이 난 경로 | 건수 |", "|---|---|"] + [f"| `{r['name']}` | {r['count']} |" for r in s["by_route"]]
    lines += ["", "| 오류 유형 | 건수 |", "|---|---|"] + [f"| {r['name']} | {r['count']} |" for r in s["by_type"]]
    lines += ["", "최근 10건", "", "| 시각 (KST) | 경로 | 상태 | 유형 | 요청 번호 |", "|---|---|---|---|---|"]
    for r in s["recent"]:
        route = f"{r.get('method') or ''} {r['route']}".strip()
        lines.append(f"| {_kst(r['occurred_at'])} | `{route}` | {r.get('status_code') or '—'} | {r['error_type']} | "
                     f"{r.get('request_id') or '—'} |")
    return lines + [""]


def build(days: int, now: datetime, *, fetch=fetch_runs, db=None) -> str:
    since = now - timedelta(days=days)
    runs_by: dict = {}
    for workflow, _ in WORKFLOWS:
        try:
            runs_by[workflow] = fetch(workflow, since)
        except Exception as exc:  # noqa: BLE001 - 한 워크플로를 못 읽어도 나머지는 보고한다
            runs_by[workflow] = exc
    head = [
        f"# 운영 보고서 — {since.astimezone(KST):%Y-%m-%d %H:%M} ~ {now.astimezone(KST):%Y-%m-%d %H:%M} KST",
        "",
        f"> `python -m scripts.ops_report --days {days}{' --with-db' if db is not None else ''}` 로 만들었다. "
        "원본: GitHub Actions 실행 기록 · Supabase error_logs. 기준과 대응 절차는 [operations.md](operations.md).",
        "",
    ]
    return "\n".join(head + _uptime_section(runs_by["uptime.yml"]) + _workflow_section(runs_by)
                     + _error_section(db, days, now))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="운영 보고서 (가동률 · 장애 · 배포 확인 · 오류 요약)")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--with-db", action="store_true", help="Supabase error_logs 도 요약한다 (.env 필요)")
    parser.add_argument("--out", help="마크다운 파일로 저장 (없으면 화면에)")
    args = parser.parse_args(argv)

    db = None
    if args.with_db:
        from db import get_supabase_client
        db = get_supabase_client()
    report = build(args.days, datetime.now(timezone.utc), db=db)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"저장: {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report)


if __name__ == "__main__":
    main()
