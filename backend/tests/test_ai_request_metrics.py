"""실제 AI·DB 없이 호출 기록과 학습 분해 연결을 확인한다."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from services import ai_request_metrics as metrics


class FakeClient:
    def __init__(self, responses):
        self.messages = self
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def response(usage=None):
    return SimpleNamespace(usage=usage)


class MetricsTests(unittest.TestCase):
    def run_calls(self, responses, outcome="agent"):
        client = FakeClient(responses)
        @metrics.track_decomposition
        def perform():
            for _ in responses:
                metrics.tracked_create(client, model="model", messages=[{"private": "secret"}])
            return SimpleNamespace(source=outcome)
        with patch.object(metrics, "_persist_rows") as save:
            result = perform()
        return result, save.call_args.args[0], client

    def test_records_each_call_and_keeps_zero(self):
        usage = SimpleNamespace(input_tokens=0, output_tokens=12,
                                cache_creation_input_tokens=5, cache_read_input_tokens=30)
        _, rows, client = self.run_calls([response(usage), response(usage)])
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["attempt_no"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["run_id"], rows[1]["run_id"])
        self.assertTrue(all("id" not in item for item in rows))  # DB identity supplies the ID
        self.assertEqual(rows[0]["input_tokens"], 0)
        self.assertEqual(rows[0]["cache_read_input_tokens"], 30)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(all(r["succeeded"] for r in rows))
        self.assertNotIn("secret", json.dumps(rows))
        self.assertNotIn("messages", rows[0])
        self.assertTrue(all(r["latency_ms"] >= 0 for r in rows))

    def test_missing_usage_is_unknown(self):
        _, rows, _ = self.run_calls([response()])
        self.assertTrue(all(rows[0][name] is None for name in metrics.TOKEN_FIELDS))

    def test_invalid_counts_are_unknown(self):
        _, rows, _ = self.run_calls([response(dict(input_tokens=-1, output_tokens=True,
            cache_creation_input_tokens="5", cache_read_input_tokens=1.5))])
        self.assertTrue(all(rows[0][name] is None for name in metrics.TOKEN_FIELDS))

    def test_request_exception_is_preserved_and_private(self):
        error = TimeoutError("private input and key")
        client = FakeClient([error])
        @metrics.track_decomposition
        def perform():
            return metrics.tracked_create(client, model="m")
        with patch.object(metrics, "_persist_rows") as save:
            with self.assertRaises(TimeoutError) as raised:
                perform()
        self.assertIs(raised.exception, error)
        row = save.call_args.args[0][0]
        self.assertFalse(row["succeeded"])
        self.assertEqual(row["error_kind"], "timeout")
        self.assertEqual(row["outcome"], "error")
        self.assertNotIn("private", json.dumps(row))
        self.assertIsNone(metrics._current.get())

    def test_error_classification(self):
        for status, expected in [(429, "rate_limit"), (401, "authentication"),
                                 (403, "authentication"), (500, "http_error")]:
            error = RuntimeError("private")
            error.status_code = status
            with self.subTest(status=status):
                self.assertEqual(metrics._error_kind(error), expected)
        self.assertEqual(metrics._error_kind(RuntimeError()), "request_error")

    def test_no_request_makes_no_row(self):
        @metrics.track_decomposition
        def perform():
            return SimpleNamespace(source="template")
        with patch.object(metrics, "_persist_rows") as save:
            self.assertEqual(perform().source, "template")
            save.assert_not_called()

    def test_persistence_failure_does_not_change_result(self):
        client = FakeClient([response()])
        expected = SimpleNamespace(source="agent")
        @metrics.track_decomposition
        def perform():
            metrics.tracked_create(client, model="m")
            return expected
        with patch.object(metrics, "_persist_rows", side_effect=RuntimeError("private")):
            with self.assertLogs(metrics.logger, "WARNING") as logs:
                self.assertIs(perform(), expected)
        self.assertNotIn("private", " ".join(logs.output))

    def test_persistence_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"db": None}):
                metrics._persist_rows([{"test": 1}])

    def test_persistence_enabled_is_single_batch(self):
        db = MagicMock()
        module = SimpleNamespace(get_supabase_client=lambda: db)
        rows = [{"attempt_no": 1}, {"attempt_no": 2}]
        with patch.dict(os.environ, {"AI_REQUEST_METRICS_ENABLED": "1"}):
            with patch.dict("sys.modules", {"db": module}):
                metrics._persist_rows(rows)
        db.table.assert_called_once_with("ai_request_logs")
        db.table.return_value.insert.assert_called_once_with(rows)
        db.table.return_value.insert.return_value.execute.assert_called_once_with()

    def test_concurrent_runs_are_isolated(self):
        barrier = Barrier(2)
        @metrics.track_decomposition
        def perform(model):
            barrier.wait(timeout=5)
            metrics.tracked_create(FakeClient([response()]), model=model)
            return SimpleNamespace(source="agent")
        with patch.object(metrics, "_persist_rows") as save:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(perform, ["first", "second"]))
        rows = [c.args[0] for c in save.call_args_list]
        self.assertEqual([len(r) for r in rows], [1, 1])
        self.assertEqual({r[0]["model"] for r in rows}, {"first", "second"})
        self.assertNotEqual(rows[0][0]["run_id"], rows[1][0]["run_id"])

    def test_direct_call_without_context_is_unchanged(self):
        expected = response()
        client = FakeClient([expected])
        self.assertIs(metrics.tracked_create(client, model="m"), expected)


class DecompositionMetricsTests(unittest.TestCase):
    def setUp(self):
        from services import decomposer
        self.decomposer = decomposer
        self.save_patch = patch.object(metrics, "_persist_rows")
        self.save = self.save_patch.start()
        self.addCleanup(self.save_patch.stop)

    def model_response(self, text):
        return SimpleNamespace(stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    def valid_response(self):
        return self.model_response(json.dumps({"units": [
            {"id": "u1", "title": "unit", "estimated_minutes": 30}]}))

    def test_success_records_once_without_changing_public_result(self):
        result = self.decomposer.decompose_goal("SQLD", "g",
            client=FakeClient([self.valid_response()]), model="m")
        self.assertEqual(result.source, "agent")
        rows = self.save.call_args.args[0]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "agent")
        self.assertEqual(set(result.model_dump()), {"units", "source", "message", "tool_calls"})

    def test_retry_is_recorded_separately(self):
        client = FakeClient([self.model_response("invalid"), self.valid_response()])
        result = self.decomposer.decompose_goal("SQLD", "g", client=client, model="m")
        self.assertEqual(result.source, "partial")
        rows = self.save.call_args.args[0]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["succeeded"] for row in rows))
        self.assertTrue(all(row["outcome"] == "partial" for row in rows))

    def test_timeout_fallback_is_not_transport_success(self):
        result = self.decomposer.decompose_goal("SQLD", "g",
            client=FakeClient([TimeoutError("private")]), model="m")
        self.assertEqual(result.source, "template")
        row = self.save.call_args.args[0][0]
        self.assertFalse(row["succeeded"])
        self.assertEqual(row["outcome"], "template")
        self.assertIsNone(row["input_tokens"])

    def test_exhausted_budget_does_not_fabricate_failure(self):
        self.decomposer.decompose_goal("SQLD", "g", client=FakeClient([]),
            model="m", budget_seconds=1)
        self.save.assert_not_called()

    def test_missing_key_does_not_fabricate_request(self):
        with patch.object(self.decomposer.llm, "get_client", return_value=None):
            result = self.decomposer.decompose_goal("SQLD", "g")
        self.assertEqual(result.source, "template")
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
