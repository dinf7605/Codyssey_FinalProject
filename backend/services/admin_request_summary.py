"""Read-only daily metrics for saved plan.decompose requests; never billing data."""
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))
TOKEN_FIELDS = (
    "input_tokens", "output_tokens",
    "cache_creation_input_tokens", "cache_read_input_tokens",
)
MAX_RECORDS = 20000


class AggregateLimit(ValueError):
    pass


def day_bounds(day: date):
    start = datetime.combine(day, time.min, tzinfo=KST)
    end = start + timedelta(days=1)
    return (start.astimezone(timezone.utc).isoformat(),
            end.astimezone(timezone.utc).isoformat())


def summarize_requests(db, start_utc, end_utc):
    offset = 0
    expected = None
    seen = set()
    successes = 0
    tokens = {name: {"total": None, "record_count": 0} for name in TOKEN_FIELDS}
    for _ in range(100):
        result = (
            db.table("ai_request_logs")
            .select("id,succeeded," + ",".join(TOKEN_FIELDS), count="exact")
            .eq("feature", "plan.decompose")
            .gte("created_at", start_utc).lt("created_at", end_utc)
            .order("id")
            .range(offset, offset + 499).execute()
        )
        total = result.count
        if type(total) is not int or total < 0:
            raise ValueError("Missing count")
        if total > MAX_RECORDS:
            raise AggregateLimit("Daily limit exceeded")
        if expected is None:
            expected = total
        if expected != total:
            raise ValueError("Count changed during read")
        rows = result.data
        if not isinstance(rows, list) or offset + len(rows) > total:
            raise ValueError("Invalid response")
        if not rows and offset < total:
            raise ValueError("Incomplete response")
        for row in rows:
            key = row.get("id")
            if type(key) is not int or key <= 0 or key in seen:
                raise ValueError("Missing or repeated ID")
            seen.add(key)
            succeeded = row.get("succeeded")
            if type(succeeded) is not bool:
                raise ValueError("Invalid success flag")
            successes += int(succeeded)
            for field in TOKEN_FIELDS:
                value = row.get(field)
                if value is None:
                    continue
                if type(value) is not int or value < 0:
                    raise ValueError("Invalid token count")
                entry = tokens[field]
                entry["total"] = (entry["total"] or 0) + value
                entry["record_count"] += 1
        offset += len(rows)
        if offset == total:
            failures = total - successes
            return {
                "request_count": total,
                "succeeded_count": successes,
                "failed_count": failures,
                "failure_rate_percent": round(100 * failures / total, 2) if total else None,
                "tokens": tokens,
            }
    raise AggregateLimit("Read limit exceeded")


def request_metrics_payload(db_factory, day, enabled):
    # Validate dates even when collection is disabled.
    start, end = day_bounds(day)
    payload = {"day": day.isoformat(), "timezone": "Asia/Seoul",
               "collection_enabled": enabled, "summary": None}
    if not enabled:
        return {**payload, "status": "disabled"}
    try:
        summary = summarize_requests(db_factory(), start, end)
    except AggregateLimit:
        return {**payload, "status": "limit_exceeded"}
    except Exception:
        # Never expose database exception text, keys or query internals.
        return {**payload, "status": "unavailable"}
    return {**payload, "status": "ok" if summary["request_count"] else "empty",
            "summary": summary}
