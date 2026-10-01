"""AI 품질 평가 (기획서 4-9 · AI기능명세 ⑦ · 담당 A) — 정답셋으로 측정하고 결과를 남긴다.

실행 (backend 폴더에서):
    python -m evals.run_eval --round 3            # Claude 게이트웨이·공용 DB 사용 (Haiku 약 30회)
    python -m evals.run_eval --round 3 --no-ai    # 규칙 경로만 (키·DB 없이)

측정 항목 (자동으로 잴 수 있는 것)
  1. 목표 추천 적합도 — goldset goal_cases 20개. 유사도 0.60 이상 상위 3장에 적합 목표가
     min(2, 적합 목표 수)장 이상이면 통과. 무관 관심사(적합 목표 없음)는 아무것도 추천하지 않아야 통과.
     ※ 카탈로그가 10개라 '상위 3장 중 2장'을 그대로 쓰면 적합 목표가 1개뿐인 관심사는 늘 실패한다
     같은 정답셋을 태그 겹침(이전 방식)과 Claude 관련성(지금 방식)으로 나란히 재서 개선 전후를 남긴다.
  2. 일정 실현 가능성 — 카탈로그 목표 10개를 템플릿 단원으로 배치해 규칙 검증기 위반 0건이면 통과
  3. 공모전 추천 정확도 (Precision@5) — contest_cases 10개, 추천된 공고가 접수 중이고 마감이 지나지 않았는가.
     응모 자격은 원문을 읽지 않으므로 판정하지 않는다 (추천 이유에 '원문에서 확인'으로 안내)
  4. 추천 이유 사실성 — 이유 문장이 말한 것('제목에 X 포함', '분야에 X 포함', '입력한 관심 태그')이 실제와 맞는가

사람이 채점하는 항목(학습 분해 누락률·실사용자 일정 준수율 등)은 evals/RESULTS.md 에 따로 적는다.
결과: evals/results/<날짜>-round<N>.json · evals/RESULTS.md 에 표 한 줄씩 더한다.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDSET = HERE / "goldset.json"
RESULTS_DIR = HERE / "results"
SUMMARY = HERE / "RESULTS.md"

TARGETS = {"goal_fit": 0.80, "schedule_feasible": 1.00, "contest_precision": 0.90, "reason_factual": 0.95}


# ── 1. 목표 추천 적합도 ───────────────────────────────

def goal_fit(cases: list[dict], search) -> dict:
    from schemas.goal import SIMILARITY_THRESHOLD

    rows, passed = [], 0
    for case in cases:
        found = search(case["interests"])
        top = [c.goal_id for c in found if c.similarity >= SIMILARITY_THRESHOLD][:3]
        acceptable = set(case["acceptable"])
        if acceptable:
            ok = len(acceptable & set(top)) >= min(2, len(acceptable))
        else:
            ok = not top
        passed += ok
        rows.append({"id": case["id"], "interests": case["interests"], "top3": top, "pass": ok})
    return {"rate": passed / len(cases), "passed": passed, "total": len(cases), "cases": rows}


# ── 2. 일정 실현 가능성 ───────────────────────────────

def schedule_feasible(today: date) -> dict:
    from schemas.plan import Availability, TimeSlot
    from services.goal_catalog import _CATALOG
    from services.scheduler import build_schedule
    from services.template import template_units
    from services.validator import validate_schedule

    availability = Availability(slots=[TimeSlot(weekday=d, start="19:00", end="22:00") for d in range(5)])
    rows, passed = [], 0
    for item in _CATALOG:
        units = template_units(item["title"])
        deadline = today + timedelta(weeks=8)
        plan = build_schedule(units, availability, today, deadline)
        violations = validate_schedule(plan.blocks, units, deadline)
        ok = not violations
        passed += ok
        rows.append({"goal_id": item["goal_id"], "blocks": len(plan.blocks), "unplaced": len(plan.unplaced),
                     "violations": [v.kind for v in violations], "pass": ok})
    return {"rate": passed / len(rows), "passed": passed, "total": len(rows), "cases": rows}


# ── 3·4. 공모전 추천 정확도 · 이유 사실성 ────────────────

_TITLE = re.compile(r"제목에 ‘(.+?)’")
_FIELD = re.compile(r"분야에 관심 키워드 ‘(.+?)’")
_TAGS = re.compile(r"입력한 관심 태그 (.+?) 기준")


def reason_is_factual(row: dict, interests: list[str]) -> bool:
    contest, reason = row["contest"], row["reason"]
    if m := _TITLE.search(reason):
        return m.group(1).casefold() in contest.title.casefold()
    if m := _FIELD.search(reason):
        return any(m.group(1).casefold() in f.casefold() for f in contest.fields)
    if m := _TAGS.search(reason):
        return all(tag.strip() in interests for tag in m.group(1).split(","))
    return "응모 자격은 원문에서 확인" in reason  # 근거를 말하지 않는 문장은 자격을 단정하지 않아야 한다


def contest_quality(cases: list[dict], today: date, use_ai: bool) -> dict:
    from services import contest_claude
    from services.contest_recommender import rank_contests
    from services.contest_repository import ContestSearch, get_contest_repository

    candidates, _ = get_contest_repository().search(ContestSearch(sort="latest", limit=20))
    rows, recommended, valid, reasons, factual = [], 0, 0, 0, 0
    for case in cases:
        scores = contest_claude.score_titles(candidates, case["interests"]) if use_ai else None
        ranked = rank_contests(candidates, case["interests"], set(), today, similarities=scores)
        ok_items = [r for r in ranked if r["contest"].status in ("open", "upcoming")
                    and (r["contest"].deadline is None or r["contest"].deadline >= today)]
        fact_items = [r for r in ranked if reason_is_factual(r, case["interests"])]
        recommended += len(ranked)
        valid += len(ok_items)
        reasons += len(ranked)
        factual += len(fact_items)
        rows.append({
            "id": case["id"], "interests": case["interests"], "method": "claude" if scores is not None else "keywords",
            "titles": [r["contest"].title[:40] for r in ranked], "valid": len(ok_items), "factual": len(fact_items),
        })
    return {
        "precision": valid / recommended if recommended else None,
        "reason_factual": factual / reasons if reasons else None,
        "recommended": recommended, "candidates": len(candidates), "cases": rows,
    }


# ── 실행 ──────────────────────────────────────────────

def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="AI 품질 평가 (정답셋)")
    parser.add_argument("--round", type=int, required=True, help="측정 회차 (기획서 4-9: 1~4)")
    parser.add_argument("--no-ai", action="store_true", help="Claude·DB 없이 규칙 경로만")
    parser.add_argument("--note", default="", help="이번 회차의 개선 조치 (RESULTS.md 에 남김)")
    args = parser.parse_args()

    import config  # noqa: F401 - .env 로드
    from services.goal_catalog import search_catalog, search_catalog_ai

    gold = json.loads(GOLDSET.read_text(encoding="utf-8"))
    today = date.today()
    result = {"round": args.round, "measured_at": datetime.now().isoformat(timespec="seconds"),
              "goldset": gold["version"], "note": args.note}

    result["goal_fit_tags"] = goal_fit(gold["goal_cases"], lambda tags: search_catalog(tags))
    if not args.no_ai:
        result["goal_fit_claude"] = goal_fit(gold["goal_cases"], lambda tags: search_catalog_ai(tags)[0])
    result["schedule_feasible"] = schedule_feasible(today)
    if not args.no_ai:
        result["contest"] = contest_quality(gold["contest_cases"], today, use_ai=True)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{today.isoformat()}-round{args.round}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    claude = result.get("goal_fit_claude", {}).get("rate")
    contest = result.get("contest", {})
    line = (
        f"| {args.round}차 | {today.isoformat()} | {_pct(result['goal_fit_tags']['rate'])} → {_pct(claude)} "
        f"| {_pct(result['schedule_feasible']['rate'])} | {_pct(contest.get('precision'))} "
        f"| {_pct(contest.get('reason_factual'))} | {args.note or '—'} |"
    )
    if not SUMMARY.exists():
        SUMMARY.write_text(
            "# AI 품질 평가 결과 (evals/run_eval.py)\n\n"
            "목표: 목표 추천 적합도 80% · 일정 실현 가능성 100% · 공모전 Precision@5 90% · 추천 이유 사실성 95% (기획서 4-9)\n\n"
            "| 회차 | 날짜 | 목표 추천 적합도 (태그 → Claude) | 일정 실현 가능성 | 공모전 Precision@5 | 추천 이유 사실성 | 개선 조치 |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    # 표 아래에 '읽는 법' 설명이 있으면 그 앞(표의 끝)에 한 줄을 끼워 넣는다
    text = SUMMARY.read_text(encoding="utf-8")
    marker = "\n## 읽는 법"
    if marker in text:
        head, tail = text.split(marker, 1)
        text = head.rstrip("\n") + "\n" + line + "\n" + marker + tail
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    SUMMARY.write_text(text, encoding="utf-8")

    print(line)
    print(f"자세한 결과: {out.relative_to(HERE.parent)}")
    for case in result.get("goal_fit_claude", result["goal_fit_tags"])["cases"]:
        if not case["pass"]:
            print(f"  목표 추천 실패 {case['id']} {case['interests']} → {case['top3']}")


if __name__ == "__main__":
    main()
