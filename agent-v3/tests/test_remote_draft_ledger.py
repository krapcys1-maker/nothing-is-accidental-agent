"""Kontrdowody N-019: zdalny szkic ma ledger przed pierwszym zapisem."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import browser
import db
import mutation_ledger
import stages


class _Button:
    def __init__(self, page: "_Page", name: str, visible: bool) -> None:
        self.page = page
        self.name = name
        self.visible = visible

    @property
    def first(self) -> "_Button":
        return self

    def count(self) -> int:
        return int(self.visible)

    def is_visible(self) -> bool:
        return self.visible

    def click(self) -> None:
        if self.name == "Continue":
            self.page.events.append("continue")
            if self.page.assign_draft_id:
                self.page.url = (
                    "https://sandbox.substack.com/publish/post/12345"
                    "?type=newsletter"
                )
        elif self.name == "Publish now":
            self.page.events.append("publish-click")


class _Page:
    def __init__(
        self, db_path: pathlib.Path, *, assign_draft_id: bool = True,
    ) -> None:
        self.db_path = db_path
        self.assign_draft_id = assign_draft_id
        self.url = "about:blank"
        self.events: list[str] = []

    def goto(self, url: str, **_kwargs) -> None:
        if url.endswith("/publish/post?type=newsletter"):
            conn = db.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT kind, status, dispatched_at FROM mutation_attempts "
                    "ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if not row or row["kind"] != "draft_write":
                raise AssertionError("edytor otwarto przed ledgerem draft_write")
            if row["status"] != "PENDING" or not row["dispatched_at"]:
                raise AssertionError("edytor otwarto przed trwałym dispatch")
            self.events.append("new-editor-open")
        elif "/publish/post/12345" in url:
            self.events.append("existing-editor-open")
        self.url = url

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    def get_by_role(self, role: str, *, name: str, **_kwargs) -> _Button:
        visible = role == "button" and name in {"Continue", "Publish now"}
        return _Button(self, name, visible)

    def close(self) -> None:
        return None


class _Context:
    def __init__(self, page: _Page) -> None:
        self.page = page

    def new_page(self) -> _Page:
        return self.page


class _Closer:
    def close(self) -> None:
        return None

    def stop(self) -> None:
        return None


class RemoteDraftLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.db_path = self.root / "draft-ledger.db"
        self.article = self.root / "article.md"
        self.image = self.root / "article.png"
        self.article.write_text(
            "# Exact title\n\n*Exact subtitle*\n\n"
            "A documented paragraph.\n",
            encoding="utf-8",
        )
        self.image.write_bytes(b"fixture-png-bytes")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *, assign_draft_id: bool = True) -> tuple[dict, _Page]:
        page = _Page(self.db_path, assign_draft_id=assign_draft_id)

        def fake_fill(fake_page, _article, _image) -> None:
            fake_page.events.append("remote-content-write")

        with ExitStack() as stack:
            stack.enter_context(patch.object(browser.config, "DB_PATH", self.db_path))
            stack.enter_context(patch.object(
                browser.config, "TEST_ACCOUNT_HANDLE", "nia-v3-sandbox"))
            stack.enter_context(patch.object(
                browser.config, "SUBSTACK_HANDLE", "sandbox"))
            stack.enter_context(patch.object(
                browser.config, "WYLACZ_WYKRYWANIE_AI", False))
            stack.enter_context(patch.object(
                browser, "naprawde_wyslac", lambda *_args, **_kwargs: True))
            stack.enter_context(patch.object(browser, "wymagaj_sesji", lambda: None))
            stack.enter_context(patch.object(
                browser, "wymagaj_wlasciwego_konta", lambda _page: None))
            stack.enter_context(patch.object(
                browser, "podlacz_sie",
                lambda: (_Closer(), _Closer(), _Context(page))))
            stack.enter_context(patch.object(
                browser, "wypelnij_artykul", fake_fill))
            stack.enter_context(patch.object(
                browser, "potwierdz_artykul",
                lambda _page, _title, expected_id=None: expected_id))
            stack.enter_context(patch.object(
                browser, "potwierdz_adres_artykulu",
                lambda _page, _title, _draft_id=None:
                "https://sandbox.substack.com/p/exact-title"))
            stack.enter_context(patch.object(
                browser, "zapisz_w_dzienniku", lambda *_args, **_kwargs: None))
            stack.enter_context(patch.object(
                stages, "zapisz_do_promocji", lambda *_args, **_kwargs: None))
            result = browser.wystaw_artykul(
                self.article, sciezka_png=self.image, wyslij=True)
        return result, page

    def _rows(self):
        conn = db.connect(self.db_path)
        try:
            return conn.execute(
                "SELECT * FROM mutation_attempts ORDER BY created_at"
            ).fetchall()
        finally:
            conn.close()

    def test_draft_is_reserved_before_editor_and_publish_is_separate(self) -> None:
        result, page = self._run()
        self.assertTrue(result["wyslane"], result)
        self.assertEqual(page.events[0], "new-editor-open", page.events)
        self.assertLess(
            page.events.index("remote-content-write"),
            page.events.index("publish-click"),
        )

        rows = self._rows()
        self.assertEqual([row["kind"] for row in rows], [
            "draft_write", "article_publish"])
        self.assertEqual([row["status"] for row in rows], [
            "CONFIRMED", "CONFIRMED"])
        self.assertEqual(rows[0]["source_ref"], "12345")
        self.assertEqual(rows[1]["source_ref"], "12345")

        request = json.loads(rows[0]["request_json"])
        self.assertEqual(request["intent_schema"], "draft-write@1")
        self.assertEqual(
            request["image_sha256"],
            hashlib.sha256(self.image.read_bytes()).hexdigest(),
        )
        for name in ("title_sha256", "html_sha256", "image_sha256"):
            self.assertRegex(request[name], r"^[0-9a-f]{64}$")

        conn = db.connect(self.db_path)
        try:
            reservations = conn.execute(
                "SELECT category FROM action_budget_reservations"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual([row["category"] for row in reservations], ["artykuly"])

    def test_confirmed_draft_is_resumed_without_creating_a_second_draft(self) -> None:
        parsed = browser.rozbierz_artykul(self.article)
        payload, metadata = browser._draft_write_intent(parsed, self.image)
        first = mutation_ledger.reserve(
            self.db_path,
            account="nia-v3-sandbox",
            kind="draft_write",
            target="new-article-draft",
            payload=payload,
            metadata=metadata,
        )
        first.dispatch()
        first.confirm("12345")

        result, page = self._run()
        self.assertTrue(result["wyslane"], result)
        self.assertNotIn("new-editor-open", page.events)
        self.assertIn("existing-editor-open", page.events)
        self.assertEqual(
            [row["kind"] for row in self._rows()],
            ["draft_write", "article_publish"],
        )
        self.assertTrue(result["draft_reused"])

    def test_missing_draft_id_is_unknown_and_publish_is_never_reserved(self) -> None:
        result, page = self._run(assign_draft_id=False)
        self.assertFalse(result["wyslane"], result)
        self.assertNotIn("publish-click", page.events)
        rows = self._rows()
        self.assertEqual([row["kind"] for row in rows], ["draft_write"])
        self.assertEqual(rows[0]["status"], "UNKNOWN")
        self.assertIn("brak stabilnego ID", rows[0]["error"])

    def test_intent_is_stable_and_every_payload_part_changes_identity(self) -> None:
        parsed = browser.rozbierz_artykul(self.article)
        first_payload, first_metadata = browser._draft_write_intent(
            parsed, self.image)
        second_payload, second_metadata = browser._draft_write_intent(
            parsed, self.image)
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_metadata, second_metadata)

        changed_title = dict(parsed, tytul="Another exact title")
        changed_html = dict(parsed, html=parsed["html"] + "<p>More.</p>")
        other_image = self.root / "other.png"
        other_image.write_bytes(b"different-fixture-png-bytes")
        variants = [
            browser._draft_write_intent(changed_title, self.image)[0],
            browser._draft_write_intent(changed_html, self.image)[0],
            browser._draft_write_intent(parsed, other_image)[0],
        ]
        for variant in variants:
            self.assertNotEqual(first_payload, variant)


if __name__ == "__main__":
    unittest.main(verbosity=2)
