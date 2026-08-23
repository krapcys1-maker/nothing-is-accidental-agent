"""N-020: check limitów i insert RESERVED muszą być jedną transakcją."""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import config
import db
import llm


class AtomicModelBudgetTest(unittest.TestCase):
    AT = "2026-08-21T12:00:00.000000+00:00"
    DAY_START = "2026-08-21T04:00:00+00:00"
    DAY_END = "2026-08-22T04:00:00+00:00"
    MONTH_START = "2026-08-01T04:00:00+00:00"
    MONTH_END = "2026-09-01T04:00:00+00:00"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.temp.name) / "atomic-budget.db"
        conn = db.connect(self.db_path)
        self.run_id = db.start_run(conn, "n020")
        conn.close()
        self.old = {
            "NO_LIMIT": config.NO_LIMIT,
            "RUN_LIMIT_USD": config.RUN_LIMIT_USD,
            "DEEPSEEK_API_KEY": config.DEEPSEEK_API_KEY,
            "classify": config.MODEL_FOR["classify"],
        }
        config.NO_LIMIT = True
        config.RUN_LIMIT_USD = 0.25
        config.DEEPSEEK_API_KEY = "test-only"
        config.MODEL_FOR["classify"] = config.DEEPSEEK

    def tearDown(self) -> None:
        config.NO_LIMIT = self.old["NO_LIMIT"]
        config.RUN_LIMIT_USD = self.old["RUN_LIMIT_USD"]
        config.DEEPSEEK_API_KEY = self.old["DEEPSEEK_API_KEY"]
        config.MODEL_FOR["classify"] = self.old["classify"]
        self.temp.cleanup()

    def _new_run(self, label: str) -> int:
        conn = db.connect(self.db_path)
        try:
            return db.start_run(conn, label)
        finally:
            conn.close()

    def _reserve_db(
        self, conn, *, run_id: int, provider: str, purpose: str,
        run_limit: float = 0.25, day_limit: float | None = None,
        month_limit: float | None = None, fixed_price: float | None = None,
    ) -> tuple[int, float]:
        return db.reserve_model_budget(
            conn,
            run_id=run_id,
            provider=provider,
            model=(config.DEEPSEEK if provider == "deepseek" else config.SONNET),
            purpose=purpose,
            at=self.AT,
            run_limit_usd=run_limit,
            day_limit_usd=day_limit,
            day_start=(self.DAY_START if day_limit is not None else None),
            day_end=(self.DAY_END if day_limit is not None else None),
            month_limit_usd=month_limit,
            month_start=(self.MONTH_START if month_limit is not None else None),
            month_end=(self.MONTH_END if month_limit is not None else None),
            fixed_price_usd=fixed_price,
        )

    def test_two_connections_cannot_oversubscribe_one_run(self) -> None:
        barrier = threading.Barrier(2)
        successes: list[int] = []
        errors: list[BaseException] = []
        guard = threading.Lock()

        def worker(number: int) -> None:
            conn = db.connect(self.db_path)
            try:
                llm._preflight("classify", conn, self.run_id)
                barrier.wait(timeout=5)
                call_id = llm._reserve_model_call(
                    "classify", conn, self.run_id)
                with guard:
                    successes.append(call_id)
            except BaseException as exc:
                with guard:
                    errors.append(exc)
            finally:
                conn.close()

        threads = [threading.Thread(target=worker, args=(number,))
                   for number in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

        conn = db.connect(self.db_path)
        try:
            exposure = db.financial_exposure(conn, run_id=self.run_id)
        finally:
            conn.close()
        self.assertEqual(len(successes), 1, (successes, errors, exposure))
        self.assertEqual(len(errors), 1, (successes, errors, exposure))
        self.assertIsInstance(errors[0], llm.BudgetExceeded)
        self.assertLessEqual(exposure, config.RUN_LIMIT_USD)

    def test_separate_runs_still_share_atomic_day_limit(self) -> None:
        other_run = self._new_run("n020-other-day")
        first = db.connect(self.db_path)
        second = db.connect(self.db_path)
        try:
            self._reserve_db(
                first, run_id=self.run_id, provider="deepseek", purpose="one",
                day_limit=0.25, month_limit=1.0)
            with self.assertRaises(db.ModelBudgetExceeded):
                self._reserve_db(
                    second, run_id=other_run, provider="anthropic",
                    purpose="two", day_limit=0.25, month_limit=1.0)
        finally:
            first.close()
            second.close()

    def test_separate_runs_still_share_atomic_month_limit(self) -> None:
        other_run = self._new_run("n020-other-month")
        first = db.connect(self.db_path)
        second = db.connect(self.db_path)
        try:
            self._reserve_db(
                first, run_id=self.run_id, provider="deepseek", purpose="one",
                day_limit=1.0, month_limit=0.25)
            with self.assertRaises(db.ModelBudgetExceeded):
                self._reserve_db(
                    second, run_id=other_run, provider="anthropic",
                    purpose="two", day_limit=1.0, month_limit=0.25)
        finally:
            first.close()
            second.close()

    def test_unknown_provider_blocks_inside_the_same_transaction(self) -> None:
        conn = db.connect(self.db_path)
        try:
            call_id = db.reserve_call(
                conn, run_id=self.run_id, provider="deepseek",
                model=config.DEEPSEEK, purpose="unknown", reserved_usd=0.10)
            db.mark_call_cost_unknown(conn, call_id, note="fixture timeout")
            before = conn.execute("SELECT COUNT(*) AS n FROM calls").fetchone()["n"]
            with self.assertRaises(db.ModelBudgetExceeded):
                self._reserve_db(
                    conn, run_id=self.run_id, provider="deepseek",
                    purpose="blocked")
            after = conn.execute("SELECT COUNT(*) AS n FROM calls").fetchone()["n"]
            self.assertEqual((before, after), (1, 1))
        finally:
            conn.close()

    def test_insert_failure_rolls_back_without_dead_reserved_row(self) -> None:
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TRIGGER fail_reserved AFTER INSERT ON calls "
                "BEGIN SELECT RAISE(ABORT, 'forced insert failure'); END"
            )
            conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                self._reserve_db(
                    conn, run_id=self.run_id, provider="deepseek",
                    purpose="forced-failure")
            self.assertFalse(conn.in_transaction)
            count = conn.execute("SELECT COUNT(*) AS n FROM calls").fetchone()["n"]
            self.assertEqual(count, 0)
            conn.execute("DROP TRIGGER fail_reserved")
            conn.commit()
            call_id, reserved = self._reserve_db(
                conn, run_id=self.run_id, provider="deepseek",
                purpose="after-rollback")
            self.assertGreater(call_id, 0)
            self.assertEqual(reserved, 0.25)
        finally:
            conn.close()

    def test_fixed_price_never_crosses_exact_remaining_budget(self) -> None:
        conn = db.connect(self.db_path)
        try:
            db.record_call(
                conn=conn, run_id=self.run_id, provider="deepseek",
                model=config.DEEPSEEK, purpose="prior", cost_usd=0.24,
                price_verified=1, ok=1, note="fixture")
            with self.assertRaises(db.ModelBudgetExceeded):
                self._reserve_db(
                    conn, run_id=self.run_id, provider="openai",
                    purpose="image-too-expensive", fixed_price=0.04)
            call_id, reserved = self._reserve_db(
                conn, run_id=self.run_id, provider="openai",
                purpose="image-exact", fixed_price=0.01)
            self.assertGreater(call_id, 0)
            self.assertEqual(reserved, 0.01)
            self.assertAlmostEqual(
                db.financial_exposure(conn, run_id=self.run_id), 0.25)
        finally:
            conn.close()

    def test_runtime_has_no_split_check_and_insert_path(self) -> None:
        source = pathlib.Path(llm.__file__).read_text(encoding="utf-8")
        self.assertNotIn("db.reserve_call(", source)
        self.assertNotIn("_reservation_amount", source)
        self.assertIn("db.reserve_model_budget(", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
