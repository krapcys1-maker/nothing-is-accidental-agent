"""Kontrdowody maszyny stanów trwałych mutacji V3."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import mutation_ledger as ledger
import browser
import run as agent_run


class MutationLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.temp.name) / "ledger.db"
        self.kwargs = {
            "account": "nia-v3-sandbox",
            "kind": "comment",
            "target": "https://example.test/p/one",
            "payload": "A precise test comment.",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def reserve(self) -> ledger.Attempt:
        return ledger.reserve(self.db_path, **self.kwargs)

    def test_pending_is_durable_and_blocks_duplicate(self) -> None:
        attempt = self.reserve()
        stored = ledger.get_attempt(self.db_path, attempt.id)
        self.assertEqual(stored["status"], "PENDING")
        with self.assertRaises(ledger.MutationBlocked):
            self.reserve()

    def test_confirm_requires_dispatch_and_source_reference(self) -> None:
        attempt = self.reserve()
        with self.assertRaises(ledger.InvalidTransition):
            attempt.confirm("external-1")
        attempt.dispatch()
        with self.assertRaises(ledger.InvalidTransition):
            attempt.confirm("")
        attempt.confirm("external-1")
        stored = ledger.get_attempt(self.db_path, attempt.id)
        self.assertEqual(stored["status"], "CONFIRMED")
        self.assertEqual(stored["source_ref"], "external-1")
        with self.assertRaises(ledger.MutationBlocked):
            self.reserve()

    def test_unknown_after_dispatch_blocks_retry(self) -> None:
        attempt = self.reserve()
        attempt.dispatch()
        attempt.unknown("verification timeout")
        self.assertEqual(
            ledger.get_attempt(self.db_path, attempt.id)["status"], "UNKNOWN")
        with self.assertRaises(ledger.MutationBlocked):
            self.reserve()

    def test_unknown_quarantines_different_mutations_too(self) -> None:
        attempt = self.reserve()
        attempt.dispatch()
        attempt.unknown("verification timeout")
        other = dict(self.kwargs)
        other.update(kind="like", target="note-22", payload="")
        with self.assertRaises(ledger.MutationBlocked) as caught:
            ledger.reserve(self.db_path, **other)
        self.assertEqual(caught.exception.status, "UNKNOWN")
        self.assertEqual(caught.exception.attempt_id, attempt.id)

    def test_failed_before_dispatch_allows_next_sequence(self) -> None:
        first = self.reserve()
        first.fail("selector absent")
        second = self.reserve()
        self.assertEqual(second.sequence, 2)
        self.assertNotEqual(first.id, second.id)

    def test_exception_before_dispatch_becomes_failed(self) -> None:
        attempt = self.reserve()
        with self.assertRaisesRegex(RuntimeError, "before"):
            with attempt:
                raise RuntimeError("before")
        self.assertEqual(
            ledger.get_attempt(self.db_path, attempt.id)["status"], "FAILED")

    def test_exception_after_dispatch_becomes_unknown(self) -> None:
        attempt = self.reserve()
        with self.assertRaisesRegex(TimeoutError, "after"):
            with attempt:
                attempt.dispatch()
                raise TimeoutError("after")
        self.assertEqual(
            ledger.get_attempt(self.db_path, attempt.id)["status"], "UNKNOWN")

    def test_normal_exit_without_resolution_is_conservative(self) -> None:
        before = self.reserve()
        with before:
            pass
        self.assertEqual(
            ledger.get_attempt(self.db_path, before.id)["status"], "FAILED")

        after_kwargs = dict(self.kwargs)
        after_kwargs["payload"] = "different"
        after = ledger.reserve(self.db_path, **after_kwargs)
        with after:
            after.dispatch()
        self.assertEqual(
            ledger.get_attempt(self.db_path, after.id)["status"], "UNKNOWN")

    def test_restart_before_dispatch_recovers_as_failed(self) -> None:
        first = self.reserve()
        recovered = ledger.recover_pending(self.db_path)
        self.assertEqual(recovered, {"FAILED": 1, "UNKNOWN": 0})
        self.assertEqual(
            ledger.get_attempt(self.db_path, first.id)["status"], "FAILED")
        second = self.reserve()
        self.assertEqual(second.sequence, 2)

    def test_restart_after_dispatch_recovers_as_unknown(self) -> None:
        first = self.reserve()
        first.dispatch()
        recovered = ledger.recover_pending(self.db_path)
        self.assertEqual(recovered, {"FAILED": 0, "UNKNOWN": 1})
        self.assertEqual(
            ledger.get_attempt(self.db_path, first.id)["status"], "UNKNOWN")
        with self.assertRaises(ledger.MutationBlocked):
            self.reserve()

    def test_run_recognizes_every_unknown_shape(self) -> None:
        self.assertTrue(agent_run.mutacja_niepewna({"status": "UNKNOWN"}))
        self.assertTrue(agent_run.mutacja_niepewna({"status": "PENDING"}))
        self.assertTrue(agent_run.mutacja_niepewna(
            {"status": "BLOCKED", "blocked_by_status": "UNKNOWN"}))
        self.assertTrue(agent_run.mutacja_niepewna(
            {"attempts": [{"status": "CONFIRMED"}, {"status": "UNKNOWN"}]}))
        self.assertTrue(agent_run.mutacja_niepewna(
            {"attempts": [{"status": "PENDING"}]}))
        self.assertFalse(agent_run.mutacja_niepewna(
            {"attempts": [{"status": "CONFIRMED"}]}))

    def test_run_counts_only_new_confirmed_success(self) -> None:
        self.assertTrue(agent_run.nowy_sukces({"wyslane": True}))
        self.assertFalse(agent_run.nowy_sukces(
            {"wyslane": True, "pominiete": True}))
        self.assertFalse(agent_run.nowy_sukces({"wyslane": False}))
        self.assertTrue(agent_run.nowy_sukces(
            {"zrobione": True}, "zrobione"))
        self.assertFalse(agent_run.nowy_sukces(
            {"zrobione": True, "pominiete": True}, "zrobione"))

    def test_identity_is_stable_and_account_scoped(self) -> None:
        one = ledger.identity(**self.kwargs)
        two = ledger.identity(**self.kwargs)
        self.assertEqual(one, two)
        changed = dict(self.kwargs)
        changed["account"] = "another-sandbox"
        self.assertNotEqual(one, ledger.identity(**changed))

    def test_article_confirmation_requires_exact_attempt_id(self) -> None:
        old_api = browser.api_json
        try:
            browser.api_json = lambda *_args, **_kwargs: [
                {
                    "id": 41,
                    "title": "Nearly the same title from yesterday",
                    "post_date": "2026-08-20",
                },
                {
                    "id": 42,
                    "title": "Exact title",
                    "post_date": "2026-08-21",
                },
            ]
            self.assertIsNone(
                browser.potwierdz_artykul(None, "Nearly the same title", "42"))
            self.assertEqual(
                browser.potwierdz_artykul(None, "Exact title", "42"), "42")
            self.assertIsNone(
                browser.potwierdz_artykul(None, "Exact title", "41"))
            self.assertIsNone(
                browser.potwierdz_artykul(None, "Exact title", None))
        finally:
            browser.api_json = old_api

    def test_draft_id_is_read_from_editor_url(self) -> None:
        self.assertEqual(
            browser.id_szkicu_z_url(
                "https://sandbox.substack.com/publish/post/12345?type=newsletter"),
            "12345",
        )
        self.assertEqual(
            browser.id_szkicu_z_url("https://x.test/editor?draft_id=987"),
            "987",
        )
        self.assertIsNone(browser.id_szkicu_z_url("https://x.test/new"))

    def test_nested_source_object_yields_its_external_id(self) -> None:
        data = {
            "items": [
                {"id": "older", "body": "different"},
                {"wrapper": {"id": "note-77", "body": "Precise text here"}},
            ]
        }
        self.assertEqual(
            browser._id_obiektu_z_trescia(data, "Precise text here"),
            "note-77",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
