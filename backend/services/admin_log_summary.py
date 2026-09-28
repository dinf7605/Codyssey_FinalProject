"""Read-only daily statistics for stored processing logs, not billable AI calls."""
from pydantic import BaseModel


class AdminLogSummary(BaseModel):
    record_count: int
    tool_calls_total: int
    latency_record_count: int
    average_latency_ms: float | None = None


def summarize_ai_logs(db, start_utc: str, end_utc: str) -> AdminLogSummary:
    # Explicitly page through the entire day: Supabase may cap each response.
    # Keep this temporary application-side aggregation bounded until a DB aggregate exists.
    batch_size = 500
    max_records = 20000
    offset = 0
    expected_total = None
    previous_id = None
    calls = latency_total = latency_count = 0
    requests = 0
    while True:
        requests += 1
        if requests > 100:
            raise ValueError("Daily aggregate request limit exceeded")
        result = (
            db.table("ai_call_logs")
            .select("id,tool_calls,latency_ms", count="exact")
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
            .order("id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        total = result.count
        if type(total) is not int or total < 0 or total > max_records:
            raise ValueError("Daily aggregate unavailable")
        if expected_total is None:
            expected_total = total
        if total != expected_total:
            raise ValueError("Log count changed during aggregation; refresh")
        rows = result.data or []
        if offset + len(rows) > total or (not rows and offset < total):
            raise ValueError("Incomplete daily log response")
        for row in rows:
            row_id = row.get("id")
            if type(row_id) is not int or (previous_id is not None and row_id <= previous_id):
                raise ValueError("Unstable log ordering")
            previous_id = row_id
            tool_calls = row.get("tool_calls")
            latency = row.get("latency_ms")
            if type(tool_calls) is not int or tool_calls < 0:
                raise ValueError("Invalid tool call measurement")
            calls += tool_calls
            if latency is not None:
                if type(latency) is not int or latency < 0:
                    raise ValueError("Invalid latency measurement")
                latency_total += latency
                latency_count += 1
        offset += len(rows)
        if offset == total:
            return AdminLogSummary(
                record_count=total,
                tool_calls_total=calls,
                latency_record_count=latency_count,
                average_latency_ms=round(latency_total / latency_count, 2) if latency_count else None,
            )


def try_summarize_ai_logs(db, start_utc: str, end_utc: str, expected_count: int):
    """Keep the existing log list available when optional statistics fail."""
    try:
        summary = summarize_ai_logs(db, start_utc, end_utc)
        return summary if summary.record_count == expected_count else None
    except Exception:
        return None
