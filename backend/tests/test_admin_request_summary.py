"""No network or DB required: run with pytest or unittest."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from services.admin_request_summary import (
    TOKEN_FIELDS, day_bounds, request_metrics_payload, summarize_requests,
)


def row(key, succeeded=True, **values):
    return {"id": str(key), "succeeded": succeeded,
            **dict.fromkeys(TOKEN_FIELDS), **values}


class FakeDB:
    def __init__(self, rows=(), cap=500, counts=None, error=None):
        self.rows = list(rows)
        self.cap = cap
        self.counts = counts
        self.error = error
        self.calls = []
        self.executions = 0

    def __getattr__(self, name):
        def query(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == 'range':
                self.offset, self.end = args
            return self
        return query

    def execute(self):
        if self.error:
            raise self.error
        count = self.counts[min(self.executions, len(self.counts) - 1)] if self.counts else len(self.rows)
        self.executions += 1
        return SimpleNamespace(count=count, data=self.rows[self.offset:min(self.end + 1, self.offset + self.cap)])


class RequestSummaryTests(unittest.TestCase):
    def payload(self, db, enabled=True):
        return request_metrics_payload(lambda: db, date(2026, 9, 29), enabled)

    def test_kst_window(self):
        self.assertEqual(day_bounds(date(2026, 9, 29)),
                         ('2026-09-28T15:00:00+00:00', '2026-09-29T15:00:00+00:00'))

    def test_disabled_never_contacts_db(self):
        factory = Mock(side_effect=AssertionError('must not query'))
        data = request_metrics_payload(factory, date(2026, 9, 29), False)
        self.assertEqual(data['status'], 'disabled')
        self.assertIsNone(data['summary'])
        factory.assert_not_called()

    def test_empty_has_no_failure_rate_or_token_total(self):
        data = self.payload(FakeDB())
        self.assertEqual(data['status'], 'empty')
        self.assertIsNone(data['summary']['failure_rate_percent'])
        self.assertIsNone(data['summary']['tokens']['input_tokens']['total'])

    def test_mixed_failure_rate_and_partial_tokens(self):
        data = self.payload(FakeDB([row(1, input_tokens=10, output_tokens=0),
                                    row(2, False), row(3, input_tokens=20)]))['summary']
        self.assertEqual(data['request_count'], 3)
        self.assertEqual(data['succeeded_count'], 2)
        self.assertEqual(data['failed_count'], 1)
        self.assertEqual(data['failure_rate_percent'], 33.33)
        self.assertEqual(data['tokens']['input_tokens'], {'total': 30, 'record_count': 2})
        self.assertEqual(data['tokens']['output_tokens'], {'total': 0, 'record_count': 1})

    def test_cache_fields_stay_separate(self):
        data = self.payload(FakeDB([row(1, input_tokens=7, cache_creation_input_tokens=9,
                                        cache_read_input_tokens=13)]))['summary']['tokens']
        self.assertEqual(data['input_tokens']['total'], 7)
        self.assertEqual(data['cache_creation_input_tokens']['total'], 9)
        self.assertEqual(data['cache_read_input_tokens']['total'], 13)

    def test_all_failures(self):
        data = self.payload(FakeDB([row(1, False)]))['summary']
        self.assertEqual(data['failure_rate_percent'], 100)

    def test_all_successes(self):
        self.assertEqual(self.payload(FakeDB([row(1)]))['summary']['failure_rate_percent'], 0)

    def test_server_page_cap_is_respected(self):
        db = FakeDB([row(i) for i in range(7)], cap=2)
        self.assertEqual(self.payload(db)['summary']['request_count'], 7)
        self.assertEqual(db.executions, 4)

    def test_query_filters(self):
        db = FakeDB()
        self.payload(db)
        self.assertIn(('table', ('ai_request_logs',), {}), db.calls)
        self.assertIn(('eq', ('feature', 'plan.decompose'), {}), db.calls)
        self.assertIn(('gte', ('created_at', '2026-09-28T15:00:00+00:00'), {}), db.calls)
        self.assertIn(('lt', ('created_at', '2026-09-29T15:00:00+00:00'), {}), db.calls)

    def test_db_failure_is_not_zero_usage(self):
        data = self.payload(FakeDB(error=RuntimeError('private diagnostic')))
        self.assertEqual(data['status'], 'unavailable')
        self.assertIsNone(data['summary'])
        self.assertNotIn('private diagnostic', str(data))

    def test_factory_failure(self):
        factory = Mock(side_effect=RuntimeError())
        self.assertEqual(request_metrics_payload(factory, date(2026, 9, 29), True)['status'], 'unavailable')

    def test_record_limit(self):
        self.assertEqual(self.payload(FakeDB(counts=[20001]))['status'], 'limit_exceeded')

    def test_count_changes_discard_partial_summary(self):
        data = self.payload(FakeDB([row(1), row(2)], cap=1, counts=[2, 3]))
        self.assertEqual(data['status'], 'unavailable')
        self.assertIsNone(data['summary'])

    def test_incomplete_page(self):
        self.assertEqual(self.payload(FakeDB([row(1)], counts=[2]))['status'], 'unavailable')

    def test_duplicate_ids(self):
        self.assertEqual(self.payload(FakeDB([row(1), row(1)]))['status'], 'unavailable')

    def test_invalid_measurements(self):
        for value in [-1, True, '3', 1.5]:
            with self.subTest(value=value):
                self.assertEqual(self.payload(FakeDB([row(1, input_tokens=value)]))['status'], 'unavailable')

    def test_invalid_success_flag(self):
        self.assertEqual(self.payload(FakeDB([row(1, succeeded=1)]))['status'], 'unavailable')

    def test_missing_count(self):
        self.assertEqual(self.payload(FakeDB(counts=[None]))['status'], 'unavailable')

    def test_read_request_limit(self):
        data = self.payload(FakeDB([row(i) for i in range(101)], cap=1))
        self.assertEqual(data['status'], 'limit_exceeded')

    def test_invalid_date(self):
        with self.assertRaises(OverflowError):
            request_metrics_payload(Mock(), date.max, False)


if __name__ == '__main__':
    unittest.main()
