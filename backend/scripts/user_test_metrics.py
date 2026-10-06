"""실사용자 테스트 지표를 공용 DB 에서 읽어 리포트용 표로 출력한다 (읽기 전용).

    cd backend
    python -m scripts.user_test_metrics --start 2026-10-02 --end 2026-10-06 --emails a@x.com,b@y.com
    python -m scripts.user_test_metrics --start 2026-10-02 --end 2026-10-06 --emails-file participants.txt
    python -m scripts.user_test_metrics --start 2026-10-02 --end 2026-10-06 --joined-since 2026-10-01

참여자는 P1, P2 … 로만 표시한다 (리포트에 이메일이 남지 않게). 짝을 보려면 --show-emails.
계산 규칙은 services/user_test_metrics.py.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db import get_supabase_client  # noqa: E402
from services import user_test_metrics  # noqa: E402
from services.replan import now_kst  # noqa: E402

TEST_ACCOUNT_DOMAIN = "@test.com"  # 팀 점검용 test01~05 — 참여자가 아니다


def _participants(db, args) -> list[dict]:
    rows = db.table("users").select("user_id,email,created_at").execute().data
    if args.emails or args.emails_file:
        wanted = set()
        if args.emails:
            wanted |= {e.strip().lower() for e in args.emails.split(",") if e.strip()}
        if args.emails_file:
            text = Path(args.emails_file).read_text(encoding="utf-8")
            wanted |= {line.strip().lower() for line in text.splitlines() if line.strip() and not line.startswith("#")}
        found = [r for r in rows if (r.get("email") or "").lower() in wanted]
        missing = wanted - {(r.get("email") or "").lower() for r in found}
        if missing:
            print(f"가입 기록이 없는 이메일 {len(missing)}개 (앱에서 가입했는지 확인)", file=sys.stderr)
        return found
    since = args.joined_since.isoformat()
    return [
        r for r in rows
        if (r.get("created_at") or "") >= since and not (r.get("email") or "").endswith(TEST_ACCOUNT_DOMAIN)
    ]


def _rows(db, table: str, columns: str, user_id: str) -> list[dict]:
    return db.table(table).select(columns).eq("user_id", user_id).execute().data


def main() -> None:
    parser = argparse.ArgumentParser(description="실사용자 테스트 지표 (읽기 전용)")
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="테스트 첫날 (YYYY-MM-DD)")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="테스트 마지막 날 (포함)")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--emails", help="참여자 이메일, 쉼표로 구분")
    who.add_argument("--emails-file", help="참여자 이메일 파일 (한 줄에 하나, # 은 주석)")
    who.add_argument("--joined-since", type=date.fromisoformat, help="이 날 이후 앱에서 가입한 사람 전부 (@test.com 제외)")
    parser.add_argument("--show-emails", action="store_true", help="P1… 과 이메일 짝을 표준 오류로 출력")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # Windows 콘솔 기본(cp949)은 '—' 같은 문자를 못 쓴다

    db = get_supabase_client()
    now = now_kst()
    people = sorted(_participants(db, args), key=lambda r: r.get("created_at") or "")
    if not people:
        parser.error("참여자를 찾지 못했습니다")

    results = []
    for i, person in enumerate(people, start=1):
        uid = person["user_id"]
        label = f"P{i}"
        if args.show_emails:
            print(f"{label} = {person.get('email')}", file=sys.stderr)
        plans = _rows(db, "study_plans", "id,status,created_at", uid)
        plan_ids = [p["id"] for p in plans]
        blocks = (
            db.table("plan_blocks").select("id,plan_id,unit_key,start_at,end_at,done,done_at")
            .in_("plan_id", plan_ids).execute().data if plan_ids else []
        )
        results.append(user_test_metrics.compute(
            uid, label,
            plans=plans,
            blocks=blocks,
            changes=_rows(db, "plan_changes", "block_id,origin,change_type,created_at", uid),
            goal_feedback=_rows(db, "goal_feedback", "interested", uid),
            contest_feedback=_rows(db, "contest_feedback", "rating", uid),
            sessions=_rows(db, "study_sessions", "started_at,minutes", uid),
            notifications=_rows(db, "notification_logs", "type,is_read,sent_at", uid),
            start=args.start, end=args.end, now=now,
        ))
    print(user_test_metrics.to_markdown(results, args.start, args.end, now))


if __name__ == "__main__":
    main()
