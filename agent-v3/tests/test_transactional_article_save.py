"""Kontrdowody transakcyjnego zapisu plik–DB–provenance–pamięć."""

from __future__ import annotations

import copy
import pathlib
import sqlite3
import tempfile
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import config
import db
import provenance
import stages


def final_card() -> tuple[dict, dict]:
    sources = []
    for index in (1, 2):
        text = f"Fixture authority {index} assigns the recorded decision to board {index}."
        source = provenance.documentize({
            "url": f"https://authority-{index}.example/rule",
            "publisher": f"Authority {index}", "title": f"Rule {index}",
            "class": "PRIMARY", "text": text,
        })
        sources.append(provenance.fragments_from_excerpts(source, [text]))
    raw = {
        "working_thesis": "Written authority is split.",
        "main_mechanism": "Each record assigns one decision.",
        "confirmed_claims": [
            {"claim": source["fragments"][0]["text"],
             "fragment_ids": [source["fragments"][0]["fragment_id"]]}
            for source in sources
        ],
        "citable_numbers": [], "parallel_mechanisms": [],
        "uncertain_claims": [], "contradictions": [], "not_established": [],
    }
    card = provenance.bind_card(raw, sources)
    body = "\n\n".join(claim["claim"] for claim in card["confirmed_claims"])
    units = provenance.sentence_units(body)
    report = provenance.bind_review({
        "sentences": [
            {"sentence_id": unit["sentence_id"], "class": "FACT",
             "support": "SUPPORTED",
             "claim_ids": [card["confirmed_claims"][index]["claim_id"]],
             "why": ""}
            for index, unit in enumerate(units)
        ],
        "summary": "fixture complete",
    }, units, card)
    final, findings = provenance.finalize_card(card, sources, report, body)
    if findings:
        raise AssertionError(findings)
    draft = {
        "title": "Transactional Fixture", "subtitle": "Two records, one save.",
        "body": body, "numbers_used": [], "limits_paragraph_present": True,
    }
    return final, draft


class TransactionalArticleSaveTest(unittest.TestCase):
    def test_insert_failure_never_leaves_final_markdown_without_database_row(self) -> None:
        card, draft = final_card()
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)
            conn.executescript("""
                CREATE TRIGGER force_article_insert_failure
                BEFORE INSERT ON articles
                BEGIN SELECT RAISE(ABORT, 'forced article insert failure'); END;
            """)
            conn.commit()
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    stages.save(
                        conn, run_id, {"title": "Fixture topic"}, card, draft,
                        "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                    )
                self.assertEqual(
                    list(config.ARTICLES_DIR.glob("*.md")), [],
                    "awaria DB zostawiła finalny plik bez rekordu",
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 0)
            finally:
                conn.close()
                config.ARTICLES_DIR = old_articles

    def test_every_precommit_fault_rolls_back_files_database_graph_and_revision(self) -> None:
        points = (
            "after_article_prepare", "after_notes_prepare", "after_intent_commit",
            "after_article_insert", "after_provenance", "after_content_item",
            "after_revisions", "after_article_replace", "after_notes_replace",
            "before_commit",
        )
        for point in points:
            with self.subTest(point=point), tempfile.TemporaryDirectory() as temp:
                root = pathlib.Path(temp)
                old_articles = config.ARTICLES_DIR
                config.ARTICLES_DIR = root / "articles"
                conn = db.connect(root / "save.db")
                run_id = db.start_run(conn)
                card, draft = final_card()
                revisions = [{
                    "iteration": 1, "trigger": {"action": "REVISE"},
                    "before": {**draft, "body": "before"}, "after": draft,
                    "status": "RESOLVED", "remaining": {"action": "READY"},
                }]

                def fault(name: str) -> None:
                    if name == point:
                        raise RuntimeError(f"forced {point}")

                try:
                    with self.assertRaisesRegex(RuntimeError, f"forced {point}"):
                        stages.save(
                            conn, run_id, {"title": "Fixture topic"}, card, draft,
                            "READY", None,
                            [{"gate": "FIXTURE", "detail": "test"}],
                            revisions=revisions, fault=fault,
                        )
                    for table in (
                        "articles", "content_items", "article_revisions",
                        "article_claims", "article_sentences", "article_citations",
                    ):
                        self.assertEqual(
                            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                            0, f"{point} zostawił wiersze w {table}",
                        )
                    self.assertEqual(
                        list(config.ARTICLES_DIR.glob("*.md")), [], point)
                    self.assertEqual(
                        list((config.ARTICLES_DIR / ".save-transactions").glob("*.tmp")),
                        [], point,
                    )
                    statuses = [row[0] for row in conn.execute(
                        "SELECT status FROM article_save_intents")]
                    self.assertTrue(
                        not statuses or statuses == ["ROLLED_BACK"],
                        (point, statuses),
                    )
                finally:
                    conn.close()
                    config.ARTICLES_DIR = old_articles

    def test_success_is_idempotent_and_revision_has_the_article_id_from_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)
            card, draft = final_card()
            revisions = [{
                "iteration": 1, "trigger": {"action": "REVISE_FACTS"},
                "before": {**draft, "body": "before"}, "after": draft,
                "status": "RESOLVED", "remaining": {"action": "READY"},
            }]
            try:
                args = (
                    conn, run_id, {"title": "Fixture topic"}, card, draft,
                    "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                )
                path = stages.save(*args, revisions=revisions)
                repeated = stages.save(*args, revisions=revisions)
                self.assertEqual(repeated, path)
                article = conn.execute(
                    "SELECT id, file_path, file_sha256, notes_path, notes_sha256 "
                    "FROM articles"
                ).fetchone()
                self.assertIsNotNone(article)
                article_id = int(article["id"])
                self.assertEqual(conn.execute(
                    "SELECT article_id FROM content_items").fetchone()[0], article_id)
                self.assertEqual(conn.execute(
                    "SELECT article_id FROM article_revisions").fetchone()[0], article_id)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM articles").fetchone()[0], 1)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM article_revisions").fetchone()[0], 1)
                self.assertEqual(conn.execute(
                    "SELECT status FROM article_save_intents").fetchone()[0], "COMPLETE")
                self.assertEqual(pathlib.Path(article["file_path"]), path)
                self.assertEqual(stages._path_sha256(path), article["file_sha256"])
                self.assertEqual(
                    stages._path_sha256(pathlib.Path(article["notes_path"])),
                    article["notes_sha256"],
                )
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM article_claims").fetchone()[0], 2)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM article_sentences").fetchone()[0], 2)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM article_citations").fetchone()[0], 2)
            finally:
                conn.close()
                config.ARTICLES_DIR = old_articles

    def test_invalid_final_graph_rolls_back_every_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)
            card, draft = final_card()
            broken = copy.deepcopy(card)
            broken["evidence_manifest"]["fragments"][0]["text_sha256"] = "0" * 64
            try:
                with self.assertRaises(provenance.ProvenanceError):
                    stages.save(
                        conn, run_id, {"title": "Fixture topic"}, broken, draft,
                        "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                    )
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM articles").fetchone()[0], 0)
                self.assertEqual(list(config.ARTICLES_DIR.glob("*.md")), [])
            finally:
                conn.close()
                config.ARTICLES_DIR = old_articles

    def test_restart_rolls_back_orphan_created_between_replace_and_commit(self) -> None:
        class SimulatedCrash(BaseException):
            pass

        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            card, draft = final_card()
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)

            def crash(name: str) -> None:
                if name == "after_article_replace":
                    raise SimulatedCrash()

            try:
                with self.assertRaises(SimulatedCrash):
                    stages.save(
                        conn, run_id, {"title": "Fixture topic"}, card, draft,
                        "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                        fault=crash,
                    )
            finally:
                conn.close()  # SQLite cofa niezacommitowaną część jak po śmierci.
            reopened = db.connect(root / "save.db")
            try:
                result = stages.recover_article_saves(reopened)
                self.assertEqual(result["rolled_back"], 1)
                self.assertEqual(reopened.execute(
                    "SELECT COUNT(*) FROM articles").fetchone()[0], 0)
                self.assertEqual(list(config.ARTICLES_DIR.glob("*.md")), [])
                self.assertEqual(list(
                    (config.ARTICLES_DIR / ".save-transactions").glob("*.tmp")), [])
            finally:
                reopened.close()
                config.ARTICLES_DIR = old_articles

    def test_restart_recognizes_commit_completed_before_process_death(self) -> None:
        class SimulatedCrash(BaseException):
            pass

        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            card, draft = final_card()
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)

            def crash(name: str) -> None:
                if name == "after_commit":
                    raise SimulatedCrash()

            try:
                with self.assertRaises(SimulatedCrash):
                    stages.save(
                        conn, run_id, {"title": "Fixture topic"}, card, draft,
                        "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                        fault=crash,
                    )
            finally:
                conn.close()
            reopened = db.connect(root / "save.db")
            try:
                result = stages.recover_article_saves(reopened)
                self.assertEqual(result["complete"], 1)
                self.assertEqual(reopened.execute(
                    "SELECT COUNT(*) FROM articles").fetchone()[0], 1)
                self.assertEqual(len(list(config.ARTICLES_DIR.glob("*.md"))), 2)
            finally:
                reopened.close()
                config.ARTICLES_DIR = old_articles

    def test_recovery_quarantines_completed_record_when_file_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            old_articles = config.ARTICLES_DIR
            config.ARTICLES_DIR = root / "articles"
            conn = db.connect(root / "save.db")
            run_id = db.start_run(conn)
            card, draft = final_card()
            try:
                path = stages.save(
                    conn, run_id, {"title": "Fixture topic"}, card, draft,
                    "READY", None, [{"gate": "FIXTURE", "detail": "test"}],
                )
                path.write_text("tampered", encoding="utf-8")
                with self.assertRaises(stages.ArticleSaveRecoveryError):
                    stages.recover_article_saves(conn)
                self.assertEqual(conn.execute(
                    "SELECT status FROM article_save_intents").fetchone()[0], "BROKEN")
                self.assertTrue(path.exists(), "recovery nie może usuwać zmienionego pliku")
            finally:
                conn.close()
                config.ARTICLES_DIR = old_articles


if __name__ == "__main__":
    unittest.main(verbosity=2)
