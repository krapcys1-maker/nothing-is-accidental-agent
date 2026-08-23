"""Kontrdowody dla jednej doby redakcyjnej i trwałych limitów V3."""

from __future__ import annotations

import pathlib
import tempfile
import threading
import unittest
from datetime import date, datetime, timezone

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import browser
import config
import db
import mutation_ledger
import operational_day


ACCOUNT = "nia-v3-sandbox"


class OperationalDayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.temp.name) / "operational-day.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def connect(self):
        return db.connect(self.db_path)

    def test_utc_midnight_does_not_split_new_york_editorial_day(self) -> None:
        before = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
        after = datetime(2026, 1, 16, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(operational_day.editorial_date(before), date(2026, 1, 15))
        self.assertEqual(operational_day.editorial_date(after), date(2026, 1, 15))
        conn = self.connect()
        try:
            one = operational_day.get_or_create(conn, account=ACCOUNT, at=before)
            two = operational_day.get_or_create(conn, account=ACCOUNT, at=after)
            self.assertEqual(one["id"], two["id"])
        finally:
            conn.close()

    def test_local_midnight_creates_a_new_operational_day(self) -> None:
        before = datetime(2026, 1, 16, 4, 59, tzinfo=timezone.utc)
        after = datetime(2026, 1, 16, 5, 1, tzinfo=timezone.utc)
        conn = self.connect()
        try:
            one = operational_day.get_or_create(conn, account=ACCOUNT, at=before)
            two = operational_day.get_or_create(conn, account=ACCOUNT, at=after)
            self.assertNotEqual(one["id"], two["id"])
            self.assertEqual(one["day_key"], "2026-01-15")
            self.assertEqual(two["day_key"], "2026-01-16")
        finally:
            conn.close()

    def test_dst_days_have_real_23_and_25_hour_boundaries(self) -> None:
        spring_start, spring_end = operational_day.boundaries(date(2026, 3, 8))
        fall_start, fall_end = operational_day.boundaries(date(2026, 11, 1))
        self.assertEqual((spring_end - spring_start).total_seconds(), 23 * 3600)
        self.assertEqual((fall_end - fall_start).total_seconds(), 25 * 3600)

    def test_month_boundary_uses_editorial_timezone_across_dst(self) -> None:
        start, end = operational_day.month_boundaries(date(2026, 3, 15))
        self.assertEqual(start.isoformat(), "2026-03-01T05:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-04-01T04:00:00+00:00")

    def test_cost_interval_follows_editorial_day_not_utc_prefix(self) -> None:
        conn = self.connect()
        try:
            for at, amount in (
                ("2026-01-16T02:00:00+00:00", 1.25),  # 15 stycznia w NY
                ("2026-01-16T06:00:00+00:00", 2.50),  # 16 stycznia w NY
            ):
                conn.execute(
                    "INSERT INTO calls "
                    "(at, provider, model, purpose, cost_usd) "
                    "VALUES (?, 'fixture', 'fixture', 'note', ?)",
                    (at, amount))
            conn.commit()
            start, end = operational_day.boundaries(date(2026, 1, 15))
            spent = db.spent_usd_between(
                conn, start.isoformat(timespec="seconds"),
                end.isoformat(timespec="seconds"))
            self.assertEqual(spent, 1.25)
        finally:
            conn.close()

    def test_existing_plan_is_frozen_across_connections_and_policy_change(self) -> None:
        at = datetime(2026, 2, 10, 12, tzinfo=timezone.utc)
        first_conn = self.connect()
        try:
            first = operational_day.get_or_create(
                first_conn, account=ACCOUNT, at=at)
        finally:
            first_conn.close()

        original = config.LAJKI_DZIENNIE
        original_version = operational_day.POLICY_VERSION
        try:
            config.LAJKI_DZIENNIE = (99, 99)
            operational_day.POLICY_VERSION = original_version + 1
            second_conn = self.connect()
            try:
                second = operational_day.get_or_create(
                    second_conn, account=ACCOUNT, at=at)
            finally:
                second_conn.close()
        finally:
            config.LAJKI_DZIENNIE = original
            operational_day.POLICY_VERSION = original_version

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["budgets"], second["budgets"])
        self.assertNotEqual(second["budgets"]["lajki"], 99)

    def test_monthly_allocations_are_exact_and_deterministic(self) -> None:
        for ramp_up, follow_bounds, subscription_bounds in (
            (False, (20, 30), (6, 12)),
            (True, (20, 25), (6, 9)),
        ):
            plans = [
                operational_day.build_budget(
                    ACCOUNT, date(2026, 8, day), ramp_up=ramp_up)
                for day in range(1, 32)
            ]
            repeated = [
                operational_day.build_budget(
                    ACCOUNT, date(2026, 8, day), ramp_up=ramp_up)
                for day in range(1, 32)
            ]
            self.assertEqual(plans, repeated)
            self.assertIn(sum(p["follow"] for p in plans),
                          range(follow_bounds[0], follow_bounds[1] + 1))
            self.assertIn(sum(p["subskrypcje"] for p in plans),
                          range(subscription_bounds[0], subscription_bounds[1] + 1))

    def test_every_mutation_kind_has_an_explicit_budget_category(self) -> None:
        expected = {
            "article", "article_publish", "draft_write", "note", "comment",
            "discussion_reply", "reply", "article_reply", "like", "restack",
            "obserwacja", "subskrypcja", "settings",
        }
        self.assertEqual(set(operational_day.KIND_TO_CATEGORY), expected)
        self.assertIsNone(operational_day.category_for("draft_write"))
        self.assertEqual(
            operational_day.category_for("article_publish"), "artykuly")
        self.assertEqual(
            operational_day.category_for("discussion_reply"), "komentarze")
        self.assertEqual(operational_day.category_for("reply"), "odpowiedzi")
        with self.assertRaises(operational_day.BudgetPolicyError):
            operational_day.category_for("new-unclassified-mutation")

    def test_confirmed_action_consumes_limit_and_blocks_next_action(self) -> None:
        first = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:a",
            payload="one")
        first.dispatch()
        first.confirm("settings-version-1")

        with self.assertRaises(operational_day.BudgetExhausted) as caught:
            mutation_ledger.reserve(
                self.db_path, account=ACCOUNT, kind="settings",
                target="profile:b", payload="two")
        self.assertEqual(caught.exception.category, "ustawienia")
        self.assertEqual(caught.exception.limit, 1)

    def test_failed_action_releases_the_reserved_unit(self) -> None:
        first = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:a",
            payload="one")
        first.fail("selector missing")
        second = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:b",
            payload="two")
        self.assertEqual(second.status, "PENDING")
        second.fail("cleanup")

    def test_unknown_quarantines_unit_and_blocks_all_further_mutations(self) -> None:
        first = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:a",
            payload="one")
        first.dispatch()
        first.unknown("verification timeout")
        conn = self.connect()
        try:
            snap = operational_day.snapshot(conn, account=ACCOUNT)
            self.assertEqual(snap["accounted"]["ustawienia"], 1)
            row = conn.execute(
                "SELECT status FROM action_budget_reservations "
                "WHERE attempt_id = ?", (first.id,)).fetchone()
            self.assertEqual(row["status"], "QUARANTINED")
        finally:
            conn.close()
        with self.assertRaises(mutation_ledger.MutationBlocked) as caught:
            mutation_ledger.reserve(
                self.db_path, account=ACCOUNT, kind="like", target="note:2",
                payload="")
        self.assertEqual(caught.exception.status, "UNKNOWN")

    def test_restart_before_and_after_dispatch_update_budget_atomically(self) -> None:
        before = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:a",
            payload="one")
        mutation_ledger.recover_pending(self.db_path)
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT status FROM action_budget_reservations "
                "WHERE attempt_id = ?", (before.id,)).fetchone()
            self.assertEqual(row["status"], "RELEASED")
        finally:
            conn.close()

        after = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:b",
            payload="two")
        after.dispatch()
        mutation_ledger.recover_pending(self.db_path)
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT status FROM action_budget_reservations "
                "WHERE attempt_id = ?", (after.id,)).fetchone()
            self.assertEqual(row["status"], "QUARANTINED")
        finally:
            conn.close()

    def test_sqlite_serializes_competing_reservations_at_exact_limit(self) -> None:
        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()

        def worker(number: int) -> None:
            conn = self.connect()
            try:
                barrier.wait(timeout=5)
                conn.execute("BEGIN IMMEDIATE")
                day = operational_day.get_or_create(conn, account=ACCOUNT)
                operational_day.reserve_units(
                    conn, day=day, attempt_id=f"parallel-{number}",
                    category="ustawienia")
                conn.commit()
                result = "reserved"
            except operational_day.BudgetExhausted:
                if conn.in_transaction:
                    conn.rollback()
                result = "exhausted"
            finally:
                conn.close()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["reserved", "exhausted"])

    def test_jsonl_failure_cannot_reset_sqlite_budget(self) -> None:
        attempt = mutation_ledger.reserve(
            self.db_path, account=ACCOUNT, kind="settings", target="profile:a",
            payload="one")
        attempt.dispatch()
        attempt.confirm("settings-version-1")
        original = browser.DZIENNIK
        try:
            browser.DZIENNIK = pathlib.Path(self.temp.name)  # katalog, nie plik
            browser.zapisz_w_dzienniku("ustawienia", udane=True)
            self.assertEqual(browser.z_dziennika_dzis()["komentarze"], 0)
        finally:
            browser.DZIENNIK = original
        conn = self.connect()
        try:
            snap = operational_day.snapshot(conn, account=ACCOUNT)
            self.assertEqual(snap["accounted"]["ustawienia"], 1)
            self.assertEqual(snap["remaining"]["ustawienia"], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
