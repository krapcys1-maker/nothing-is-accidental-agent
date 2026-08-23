"""N-017: koszt po dispatch nie może stać się zerem ani cichym retry."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import httpx

sys.path.insert(0, "agent-v3")
import config  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402


class ModelCallAccountingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = pathlib.Path(self.temp.name) / "calls.db"
        self.conn = db.connect(self.db_path)
        self.addCleanup(lambda: self.conn.close())
        self.run_id = db.start_run(self.conn, "n017")

        self.old_env = os.environ.copy()
        self.addCleanup(self._restore_env)
        os.environ["AGENT_V3_MODE"] = "model_test"
        os.environ["AGENT_V3_KILL_SWITCH"] = "0"

        self.old_config = {
            "DRY_RUN": config.DRY_RUN,
            "NO_LIMIT": config.NO_LIMIT,
            "DEEPSEEK_API_KEY": config.DEEPSEEK_API_KEY,
            "PONOWIENIA": config.PONOWIENIA,
            "PONOWIENIE_ODSTEP_S": config.PONOWIENIE_ODSTEP_S,
            "RUN_LIMIT_USD": config.RUN_LIMIT_USD,
            "classify_model": config.MODEL_FOR["classify"],
        }
        self.addCleanup(self._restore_config)
        config.DRY_RUN = False
        config.NO_LIMIT = True
        config.DEEPSEEK_API_KEY = "test-only"
        config.PONOWIENIA = 2
        config.PONOWIENIE_ODSTEP_S = 0
        config.RUN_LIMIT_USD = 0.25
        config.MODEL_FOR["classify"] = config.DEEPSEEK

    def _restore_env(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)

    def _restore_config(self) -> None:
        config.DRY_RUN = self.old_config["DRY_RUN"]
        config.NO_LIMIT = self.old_config["NO_LIMIT"]
        config.DEEPSEEK_API_KEY = self.old_config["DEEPSEEK_API_KEY"]
        config.PONOWIENIA = self.old_config["PONOWIENIA"]
        config.PONOWIENIE_ODSTEP_S = self.old_config["PONOWIENIE_ODSTEP_S"]
        config.RUN_LIMIT_USD = self.old_config["RUN_LIMIT_USD"]
        config.MODEL_FOR["classify"] = self.old_config["classify_model"]

    @staticmethod
    def _request() -> httpx.Request:
        return httpx.Request("POST", "https://api.deepseek.com/chat/completions")

    def test_post_dispatch_error_is_unknown_without_retry_and_survives_restart(self) -> None:
        error = httpx.RemoteProtocolError(
            "incomplete chunked read", request=self._request()
        )
        with mock.patch.object(llm, "_call_deepseek", side_effect=error) as transport:
            with self.assertRaises(httpx.RemoteProtocolError):
                llm.call(
                    "classify", "system", "user", conn=self.conn,
                    run_id=self.run_id,
                )
        self.assertEqual(transport.call_count, 1)

        row = self.conn.execute(
            "SELECT id, cost_usd, cost_status, reserved_usd, ok FROM calls "
            "WHERE purpose='classify'"
        ).fetchone()
        self.assertEqual(row["cost_usd"], 0)
        self.assertEqual(row["cost_status"], "UNKNOWN")
        self.assertEqual(row["reserved_usd"], 0.25)
        self.assertEqual(row["ok"], 0)
        self.assertEqual(db.financial_exposure(self.conn, run_id=self.run_id), 0.25)

        self.conn.close()
        self.conn = db.connect(self.db_path)
        with mock.patch.object(llm, "_call_deepseek") as transport:
            with self.assertRaises(llm.BudgetExceeded):
                llm.call(
                    "classify", "system", "user", conn=self.conn,
                    run_id=self.run_id,
                )
        transport.assert_not_called()

    def test_connect_error_can_retry_and_settles_one_reservation(self) -> None:
        error = httpx.ConnectError("dns unavailable", request=self._request())
        result = ("{\"ok\":true}", 100, 20, 0, 0)
        with mock.patch.object(
            llm, "_call_deepseek", side_effect=[error, result]
        ) as transport:
            text = llm.call(
                "classify", "system", "user", conn=self.conn,
                run_id=self.run_id,
            )
        self.assertEqual(text, "{\"ok\":true}")
        self.assertEqual(transport.call_count, 2)
        rows = self.conn.execute(
            "SELECT cost_status, reserved_usd, ok FROM calls "
            "WHERE purpose='classify'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), ("KNOWN", 0, 1))

    def test_exhausted_connect_failures_are_known_zero(self) -> None:
        config.PONOWIENIA = 1
        error = httpx.ConnectTimeout("connect timeout", request=self._request())
        with mock.patch.object(llm, "_call_deepseek", side_effect=error) as transport:
            with self.assertRaises(httpx.ConnectTimeout):
                llm.call(
                    "classify", "system", "user", conn=self.conn,
                    run_id=self.run_id,
                )
        self.assertEqual(transport.call_count, 2)
        row = self.conn.execute(
            "SELECT cost_usd, cost_status, reserved_usd FROM calls "
            "WHERE purpose='classify'"
        ).fetchone()
        self.assertEqual(tuple(row), (0, "KNOWN", 0))
        self.assertFalse(db.provider_has_unresolved_cost(self.conn, "deepseek"))

    def test_reconciliation_is_atomic_and_releases_provider(self) -> None:
        call_id = db.reserve_call(
            self.conn, run_id=self.run_id, provider="deepseek",
            model=config.DEEPSEEK_PRO, purpose="synthesis", reserved_usd=0.24,
        )
        db.mark_call_cost_unknown(
            self.conn, call_id, note="RemoteProtocolError: incomplete body"
        )
        db.reconcile_unknown_call(
            self.conn, call_id, cost_usd=0.00855294,
            tokens_in=3038, tokens_out=3307,
            evidence_ref="E-007 DeepSeek hourly export 13:00+03:00",
        )
        row = self.conn.execute(
            "SELECT cost_usd, cost_status, reserved_usd, tokens_in, tokens_out, "
            "reconciled_at, note FROM calls WHERE id=?", (call_id,)
        ).fetchone()
        self.assertAlmostEqual(row["cost_usd"], 0.00855294)
        self.assertEqual(row["cost_status"], "KNOWN")
        self.assertEqual(row["reserved_usd"], 0)
        self.assertEqual((row["tokens_in"], row["tokens_out"]), (3038, 3307))
        self.assertTrue(row["reconciled_at"])
        self.assertIn("E-007", row["note"])
        self.assertFalse(db.provider_has_unresolved_cost(self.conn, "deepseek"))
        with self.assertRaises(RuntimeError):
            db.reconcile_unknown_call(
                self.conn, call_id, cost_usd=0, evidence_ref="duplicate"
            )

    def test_error_classification_is_fail_closed_after_dispatch(self) -> None:
        request = self._request()
        self.assertTrue(llm.przejsciowy(httpx.ConnectError("x", request=request)))
        self.assertTrue(llm.przejsciowy(httpx.ConnectTimeout("x", request=request)))
        self.assertFalse(llm.przejsciowy(httpx.ReadTimeout("x", request=request)))
        self.assertFalse(llm.przejsciowy(httpx.ReadError("x", request=request)))
        self.assertFalse(
            llm.przejsciowy(httpx.RemoteProtocolError("x", request=request))
        )

    def test_schema_distinguishes_real_zero_from_unknown(self) -> None:
        db.record_call(
            conn=self.conn, run_id=self.run_id, provider="deepseek",
            model=config.DEEPSEEK, purpose="known-zero", cost_usd=0,
            price_verified=1, ok=0, note="rejected before generation",
        )
        call_id = db.reserve_call(
            self.conn, run_id=self.run_id, provider="anthropic",
            model=config.SONNET, purpose="unknown", reserved_usd=0.12,
        )
        db.mark_call_cost_unknown(self.conn, call_id, note="read timeout")
        rows = self.conn.execute(
            "SELECT purpose, cost_status, reserved_usd FROM calls "
            "WHERE purpose IN ('known-zero', 'unknown') ORDER BY purpose"
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [("known-zero", "KNOWN", 0), ("unknown", "UNKNOWN", 0.12)],
        )

    def test_fixed_price_image_cannot_cross_remaining_run_budget(self) -> None:
        db.record_call(
            conn=self.conn, run_id=self.run_id, provider="deepseek",
            model=config.DEEPSEEK, purpose="prior", cost_usd=0.24,
            price_verified=1, ok=1, note="",
        )
        with self.assertRaises(llm.BudgetExceeded):
            llm._reserve_model_call("obraz", self.conn, self.run_id)

    def test_search_limit_violation_is_known_failed_cost_not_unknown(self) -> None:
        config.PONOWIENIA = 0
        with mock.patch.object(
            llm, "_call_deepseek_anthropic_search",
            return_value=(
                '{"sources":[]}', 1000, 200, config.DISCOVERY_MAX_SEARCHES + 1,
                ["https://records.example/a"],
            ),
        ) as transport:
            with self.assertRaisesRegex(llm.SearchLimitExceeded, "9.*limicie 8"):
                llm.call(
                    "discovery", "system", "user", conn=self.conn,
                    run_id=self.run_id, web_search=True,
                )
        transport.assert_called_once()
        row = self.conn.execute(
            "SELECT cost_status, reserved_usd, ok, tokens_in, tokens_out, "
            "web_searches, cost_usd, note FROM calls WHERE purpose='discovery'"
        ).fetchone()
        self.assertEqual(row["cost_status"], "KNOWN")
        self.assertEqual(row["reserved_usd"], 0)
        self.assertEqual(row["ok"], 0)
        self.assertEqual((row["tokens_in"], row["tokens_out"]), (1000, 200))
        self.assertEqual(row["web_searches"], 9)
        self.assertGreater(row["cost_usd"], 0)
        self.assertIn("SearchLimitExceeded", row["note"])
        self.assertFalse(db.provider_has_unresolved_cost(self.conn, "deepseek"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
