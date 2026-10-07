"""운영 모니터링 (평가 #3 보완, 10-07) — 오류 기록 · 워커 생존 신호 · 준비 상태 · 가동률.

| 무엇                  | 어디에                              | 누가 남기나 / 누가 보나                                       |
|-----------------------|-------------------------------------|---------------------------------------------------------------|
| 서버 오류 (5xx·예외)  | error_logs                          | utils/error_monitor.py (API) · workers/notification_worker.py |
| 워커 생존 신호        | service_heartbeats                  | 알림 워커가 1분마다                                           |
| 준비 상태             | GET /health/ready                   | Railway 배포 헬스체크 · uptime.yml · deploy-check.yml         |
| 가동률 · 장애 이력    | GitHub Actions uptime.yml 실행 기록 | 관리자 화면 '운영 상태' · scripts/ops_report.py               |

가동률을 서버 안이 아니라 **밖(GitHub Actions)** 에서 재는 이유 — 서버가 죽으면 스스로는 기록을 못 남긴다.
기록 쓰기가 실패해도 서비스는 멈추지 않는다 (모니터링 장애로 본 기능을 막지 않는다).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
WORKER = "notification_worker"
STALE_AFTER = timedelta(minutes=10)   # 워커는 1분마다 신호를 남긴다 — 10분 소식이 없으면 멈춘 것
MESSAGE_LIMIT = 300
STARTED_AT = datetime.now(timezone.utc)


def version() -> str:
    """지금 돌고 있는 커밋 (앞 7자리). Railway 가 넣어 주는 RAILWAY_GIT_COMMIT_SHA — 배포 확인(deploy-check.yml)이 비교한다."""
    sha = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GIT_COMMIT_SHA") or "").strip()
    return sha[:7] or "local"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── 오류 기록 ──

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_LONG_NUMBER = re.compile(r"\d{6,}")


def scrub(text) -> str | None:
    """오류 메시지에서 이메일 · id · 긴 숫자를 가리고 300자로 자른다. 사용자 정보가 운영 로그에 남지 않게."""
    if text is None:
        return None
    s = _EMAIL.sub("<email>", str(text))
    s = _UUID.sub("<id>", s)
    s = _LONG_NUMBER.sub("<num>", s)
    return s[:MESSAGE_LIMIT]


def route_template(path: str) -> str:
    """경로에 섞인 id 를 {id} 로 바꾼다 — 라우트 틀(/plan/{plan_id})을 못 얻었을 때만 쓴다."""
    parts = ["{id}" if _UUID.fullmatch(p) or p.isdigit() else p[:40] for p in path.split("/")]
    return "/".join(parts)[:200] or "/"


# 같은 오류가 쏟아져도 DB 에는 분당 30건까지만 쓴다 — DB 장애 때 기록 시도가 장애를 키우지 않게. 서버 로그에는 모두 남는다
RATE_PER_MINUTE = 30
_window = {"start": 0.0, "count": 0}
_lock = threading.Lock()


def _allow(now: float) -> bool:
    with _lock:
        if now - _window["start"] >= 60:
            _window["start"], _window["count"] = now, 0
        if _window["count"] >= RATE_PER_MINUTE:
            return False
        _window["count"] += 1
        return True


def record_error(db, *, source: str, route: str, error_type: str, status_code: int | None = None,
                 method: str | None = None, message: str | None = None, request_id: str | None = None) -> bool:
    """오류 한 건을 error_logs 에 남긴다. 남겼으면 True — 쓰기 실패 · 분당 한도 초과 · 020 적용 전이면 조용히 False."""
    if not _allow(time.monotonic()):
        return False
    try:
        if db is None:
            from db import get_supabase_client
            db = get_supabase_client()
        db.table("error_logs").insert({
            "source": source,
            "method": method,
            "route": route[:200],
            "status_code": status_code,
            "error_type": error_type[:100],
            "message": scrub(message),
            "request_id": request_id,
        }).execute()
        return True
    except Exception:  # noqa: BLE001 - 기록 실패로 요청·작업을 실패시키지 않는다
        return False


def beat(db, service: str = WORKER, now: datetime | None = None) -> bool:
    """'살아 있음' 신호 (서비스마다 한 행을 덮어쓴다)."""
    try:
        db.table("service_heartbeats").upsert({
            "service": service,
            "beat_at": (now or datetime.now(timezone.utc)).isoformat(),
            "started_at": STARTED_AT.isoformat(),
            "version": version(),
        }, on_conflict="service").execute()
        return True
    except Exception:  # noqa: BLE001
        return False


# ── 준비 상태 (GET /health/ready) ──

READY_CACHE_SECONDS = 10   # 누가 연달아 불러도 DB 를 10초에 한 번만 두드린다
_ready_cache: dict = {"at": 0.0, "value": None}


def readiness(db_factory, now: datetime | None = None, *, use_cache: bool = True) -> tuple[int, dict]:
    """(HTTP 코드, 본문). DB 를 실제로 읽어 본다 — 10차 점검에서 /health 200 인데 DB 키가 없어 전부 503 이었다.

    status: ok · degraded(워커 멈춤) · down(DB 못 읽음 → 503).
    워커 신호 테이블이 없거나(020 적용 전) 기록이 없으면 worker=unknown 이고 실패로 보지 않는다.
    """
    if use_cache and _ready_cache["value"] and time.monotonic() - _ready_cache["at"] < READY_CACHE_SECONDS:
        return _ready_cache["value"]
    from db import DatabaseNotConfigured

    now = now or datetime.now(timezone.utc)
    checks: dict[str, str] = {}
    worker: dict = {"status": "unknown"}
    db = None
    try:
        db = db_factory()
        db.table("contests").select("id").limit(1).execute()
        checks["db"] = "ok"
    except DatabaseNotConfigured:
        checks["db"] = "not_configured"
    except Exception:  # noqa: BLE001
        checks["db"] = "error"

    if checks["db"] == "ok":
        try:
            rows = (
                db.table("service_heartbeats").select("beat_at,version")
                .eq("service", WORKER).limit(1).execute().data
            )
            if rows:
                age = now - parse_time(rows[0]["beat_at"])
                worker = {
                    "status": "ok" if age <= STALE_AFTER else "stale",
                    "last_beat_minutes": round(age.total_seconds() / 60, 1),
                    "version": rows[0].get("version"),
                }
        except Exception:  # noqa: BLE001 - 020 적용 전
            pass
    checks["worker"] = worker["status"]

    status = "down" if checks["db"] != "ok" else ("degraded" if worker["status"] == "stale" else "ok")
    body = {
        "status": status,
        "checks": checks,
        "worker": worker,
        "version": version(),
        "started_at": STARTED_AT.isoformat(),
    }
    value = (200 if checks["db"] == "ok" else 503, body)
    _ready_cache.update(at=time.monotonic(), value=value)
    return value


# ── 오류 요약 (관리자 화면 · 보고서) ──

SUMMARY_LIMIT = 2000


def error_summary(db, days: int = 7, now: datetime | None = None, recent: int = 20) -> dict:
    """최근 days 일(한국 날짜) 오류 — 날짜별 건수 · 많이 난 경로 · 유형 · 최근 목록."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(KST).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=KST)
    try:
        rows = (
            db.table("error_logs")
            .select("occurred_at,source,method,route,status_code,error_type,message,request_id")
            .gte("occurred_at", since.astimezone(timezone.utc).isoformat())
            .order("occurred_at", desc=True).limit(SUMMARY_LIMIT).execute().data
        ) or []
    except Exception:  # noqa: BLE001 - 020 적용 전이거나 DB 장애
        return {"status": "unavailable", "days": days}

    by_day = Counter(parse_time(r["occurred_at"]).astimezone(KST).date().isoformat() for r in rows)
    by_route = Counter(f"{r.get('method') or ''} {r['route']}".strip() for r in rows)
    by_type = Counter(r["error_type"] for r in rows)
    return {
        "status": "ok" if rows else "empty",
        "days": days,
        "total": len(rows),
        "truncated": len(rows) >= SUMMARY_LIMIT,
        "by_day": [
            {"day": d.isoformat(), "count": by_day.get(d.isoformat(), 0)}
            for d in (first_day + timedelta(days=i) for i in range(days))
        ],
        "by_source": dict(Counter(r["source"] for r in rows)),
        "by_route": [{"name": k, "count": v} for k, v in by_route.most_common(5)],
        "by_type": [{"name": k, "count": v} for k, v in by_type.most_common(5)],
        "recent": rows[:recent],
    }


# ── 가동률 (GitHub Actions uptime.yml 실행 기록) ──

GITHUB_API = "https://api.github.com"
DEFAULT_REPO = "dinf7605/Codyssey_FinalProject"
UPTIME_WORKFLOW = "uptime.yml"
FINISHED = ("success", "failure", "timed_out")   # 취소·건너뜀은 점검이 아니라 빼고 센다


def repo_name() -> str:
    return os.getenv("OPS_GITHUB_REPO", DEFAULT_REPO).strip() or DEFAULT_REPO


def fetch_runs(workflow: str, since: datetime, *, repo: str | None = None, token: str | None = None,
               max_pages: int = 10, opener=urllib.request.urlopen) -> list[dict]:
    """워크플로 실행 기록. 공개 저장소라 토큰 없이 읽힌다 (시간당 60회 — 그래서 결과를 30분 저장해 둔다)."""
    repo = repo or repo_name()
    token = token if token is not None else os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "studypace-ops"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    created = urllib.parse.quote(f">={since.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}")
    runs: list[dict] = []
    for page in range(1, max_pages + 1):
        url = (f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/runs"
               f"?per_page=100&page={page}&created={created}")
        try:
            with opener(urllib.request.Request(url, headers=headers), timeout=10) as resp:
                batch = json.load(resp).get("workflow_runs", [])
        except urllib.error.HTTPError as exc:
            if exc.code == 404:   # 워크플로 파일이 아직 main 에 없다 = 기록 없음
                return []
            raise
        runs += [{
            "created_at": r["created_at"],
            "conclusion": r.get("conclusion"),
            "event": r.get("event"),
            "head_sha": (r.get("head_sha") or "")[:7],
            "html_url": r.get("html_url"),
        } for r in batch]
        if len(batch) < 100:
            break
    return runs


def uptime_from_runs(runs: list[dict], since: datetime | None = None) -> dict:
    """점검 기록 → 가동률과 장애 구간.

    가동률 = 정상 점검 / 끝난 점검. 장애 구간 = 연달아 실패한 점검의 첫 실패 ~ 다음 정상 점검 (15분 단위라 최대 15분 길게 잡힌다).
    """
    done = sorted(
        (r for r in runs if r.get("conclusion") in FINISHED and (since is None or parse_time(r["created_at"]) >= since)),
        key=lambda r: r["created_at"],
    )
    ok = sum(r["conclusion"] == "success" for r in done)
    incidents: list[dict] = []
    current: dict | None = None
    for r in done:
        if r["conclusion"] != "success":
            if current is None:
                current = {"start": r["created_at"], "end": None, "minutes": None, "failed_checks": 0, "url": r.get("html_url")}
            current["failed_checks"] += 1
        elif current is not None:
            current["end"] = r["created_at"]
            current["minutes"] = round((parse_time(r["created_at"]) - parse_time(current["start"])).total_seconds() / 60)
            incidents.append(current)
            current = None
    if current is not None:   # 아직 복구되지 않음
        incidents.append(current)
    return {
        "checks": len(done),
        "ok": ok,
        "uptime_percent": round(ok / len(done) * 100, 2) if done else None,
        "first_check": done[0]["created_at"] if done else None,
        "last_check": done[-1]["created_at"] if done else None,
        "last_result": done[-1]["conclusion"] if done else None,
        "incidents": incidents,
    }


UPTIME_CACHE_SECONDS = 1800
_uptime_cache: dict = {"at": 0.0, "value": None}


def uptime_status(now: datetime | None = None, fetch=fetch_runs) -> dict:
    """최근 24시간 · 7일 가동률 (관리자 화면). GitHub 을 못 읽으면 status=unavailable — 5분 뒤 다시 시도."""
    if _uptime_cache["value"] is not None and time.monotonic() < _uptime_cache["at"]:
        return _uptime_cache["value"]
    now = now or datetime.now(timezone.utc)
    links = {
        "source": f"GitHub Actions {UPTIME_WORKFLOW} (15분마다 외부 점검)",
        "workflow_url": f"https://github.com/{repo_name()}/actions/workflows/{UPTIME_WORKFLOW}",
    }
    try:
        runs = fetch(UPTIME_WORKFLOW, now - timedelta(days=7))
        week = uptime_from_runs(runs)
        day = uptime_from_runs(runs, since=now - timedelta(days=1))
        week["incidents"] = week["incidents"][-10:]
        day.pop("incidents")
        value, keep = {"status": "ok" if week["checks"] else "empty", "day": day, "week": week, **links}, UPTIME_CACHE_SECONDS
    except Exception:  # noqa: BLE001 - GitHub 장애 · 호출 한도
        value, keep = {"status": "unavailable", **links}, 300
    _uptime_cache.update(at=time.monotonic() + keep, value=value)
    return value
