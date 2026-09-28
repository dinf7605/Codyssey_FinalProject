from types import SimpleNamespace

import unittest

from services.admin_log_summary import summarize_ai_logs, try_summarize_ai_logs

START = "2026-09-27T15:00:00+00:00"
END = "2026-09-28T15:00:00+00:00"


class FakeDB:
    def __init__(self, rows, cap=500, totals=None):
        self.rows, self.cap, self.totals = rows, cap, totals
        self.requests = []

    def table(self, name):
        assert name == "ai_call_logs"
        return Query(self)


class Query:
    def __init__(self, db):
        self.db = db
        self.filters = {}

    def select(self, columns, count):
        assert columns == "id,tool_calls,latency_ms" and count == "exact"
        return self

    def gte(self, column, value):
        self.filters["start"] = (column, value)
        return self

    def lt(self, column, value):
        self.filters["end"] = (column, value)
        return self

    def order(self, column):
        assert column == "id"
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        assert self.filters == {"start": ("created_at", START), "end": ("created_at", END)}
        n = len(self.db.requests)
        self.db.requests.append(self.start)
        total = self.db.totals[n] if self.db.totals else len(self.db.rows)
        return SimpleNamespace(
            data=self.db.rows[self.start:min(self.end + 1, self.start + self.db.cap)],
            count=total,
        )


def row(i, latency=100, calls=2):
    return {"id": i, "latency_ms": latency, "tool_calls": calls}


class SummaryTests(unittest.TestCase):
    def test_entire_day_beyond_server_cap(self):
        db = FakeDB([row(i) for i in range(1205)], cap=200)
        summary = summarize_ai_logs(db, START, END)
        self.assertEqual(summary.record_count, 1205)
        self.assertEqual(summary.tool_calls_total, 2410)
        self.assertEqual(summary.average_latency_ms, 100)
        self.assertEqual(db.requests, [0, 200, 400, 600, 800, 1000, 1200])

    def test_null_latency_excluded_but_zero_included(self):
        summary = summarize_ai_logs(FakeDB([row(1, None), row(2, 0), row(3, 300)]), START, END)
        self.assertEqual(summary.average_latency_ms, 150)
        self.assertEqual(summary.latency_record_count, 2)
        self.assertEqual(summary.record_count, 3)

    def test_empty_day(self):
        summary = summarize_ai_logs(FakeDB([]), START, END)
        self.assertEqual((summary.record_count, summary.tool_calls_total, summary.latency_record_count), (0, 0, 0))
        self.assertIsNone(summary.average_latency_ms)

    def test_all_latency_missing(self):
        self.assertIsNone(summarize_ai_logs(FakeDB([row(1, None)]), START, END).average_latency_ms)

    def test_missing_excessive_or_changing_count(self):
        for totals in ([None], [20001], [2, 3]):
            with self.subTest(totals=totals):
                self.assertIsNone(try_summarize_ai_logs(FakeDB([row(1), row(2)], cap=1, totals=totals), START, END, 2))

    def test_incomplete_result(self):
        self.assertIsNone(try_summarize_ai_logs(FakeDB([row(1)], totals=[2, 2]), START, END, 2))

    def test_list_count_mismatch(self):
        self.assertIsNone(try_summarize_ai_logs(FakeDB([row(1)]), START, END, 2))

    def test_bad_measurement_is_not_zero(self):
        for bad_row in (row(1, -1), row(1, calls=-1), row(1, calls=None)):
            with self.subTest(row=bad_row):
                self.assertIsNone(try_summarize_ai_logs(FakeDB([bad_row]), START, END, 1))

    def test_duplicate_page_rows(self):
        self.assertIsNone(try_summarize_ai_logs(FakeDB([row(1), row(1)]), START, END, 2))

    def test_db_failure_does_not_escape_optional_summary(self):
        class BrokenDB:
            def table(self, name):
                raise RuntimeError("unavailable")
        self.assertIsNone(try_summarize_ai_logs(BrokenDB(), START, END, 1))


if __name__ == "__main__":
    unittest.main()
