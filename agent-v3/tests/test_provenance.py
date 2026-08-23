"""Kontrdowody pełnego łańcucha źródło–fragment–twierdzenie–zdanie."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import db
import gates
import model_contracts
import provenance
import stages


TEXT = (
    "The agency counted 68% of the inspected units. "
    "A later rule set a 12-month threshold."
)
SOURCE = {
    "url": "https://example.gov/report",
    "host": "example.gov",
    "title": "Official report",
    "publisher": "Example Agency",
    "class": "PRIMARY",
    "text": TEXT,
}
EXCERPTS = [
    "The agency counted 68% of the inspected units.",
    "A later rule set a 12-month threshold.",
]


def evidence_fixture() -> list[dict]:
    bound = provenance.fragments_from_excerpts(SOURCE, EXCERPTS)
    bound["class"] = "PRIMARY"
    bound["relevance"] = 1.0
    bound["note"] = "fixture"
    return [bound]


def card_fixture(evidence: list[dict]) -> dict:
    fragments = evidence[0]["fragments"]
    numbers = evidence[0]["numbers"]
    by_value = {item["value"]: item for item in numbers}
    raw = {
        "working_thesis": "A rule changed the threshold.",
        "main_mechanism": "Measurement becomes a rule.",
        "confirmed_claims": [
            {"claim": "The agency counted 68% of units.",
             "fragment_ids": [fragments[0]["fragment_id"]]},
            {"claim": "The later threshold was 12 months.",
             "fragment_ids": [fragments[1]["fragment_id"]]},
        ],
        "citable_numbers": [
            {"number_id": by_value["68%"]["number_id"],
             "means": "share of inspected units", "claim_index": 0},
            {"number_id": by_value["12"]["number_id"],
             "means": "threshold in months", "claim_index": 1},
        ],
        "parallel_mechanisms": [], "uncertain_claims": [],
        "contradictions": [], "not_established": [],
    }
    return provenance.bind_card(raw, evidence)


def supported_review(body: str, card: dict) -> dict:
    units = provenance.sentence_units(body)
    rows = []
    for index, unit in enumerate(units):
        if index == 0:
            rows.append({
                "sentence_id": unit["sentence_id"], "class": "FACT",
                "support": "SUPPORTED",
                "claim_ids": [card["confirmed_claims"][0]["claim_id"]],
                "why": "",
            })
        else:
            rows.append({
                "sentence_id": unit["sentence_id"], "class": "INFERENCE",
                "support": "NOT_APPLICABLE", "claim_ids": [], "why": "",
            })
    return provenance.bind_review(
        {"sentences": rows, "summary": "fixture"}, units, card
    )


class IdentityAndExcerptTest(unittest.TestCase):
    def test_document_identity_is_stable_and_content_sensitive(self) -> None:
        first = provenance.documentize(SOURCE)
        second = provenance.documentize(dict(SOURCE))
        changed = provenance.documentize({**SOURCE, "text": TEXT + " Changed."})
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertNotEqual(first["document_id"], changed["document_id"])
        self.assertNotEqual(first["content_sha256"], changed["content_sha256"])

    def test_only_verbatim_excerpt_receives_fragment_id(self) -> None:
        result = provenance.fragments_from_excerpts(SOURCE, [EXCERPTS[0]])
        self.assertEqual(result["excerpts"], [EXCERPTS[0]])
        self.assertTrue(result["fragments"][0]["fragment_id"].startswith("frag_v1_"))
        with self.assertRaises(provenance.ProvenanceError):
            provenance.fragments_from_excerpts(
                SOURCE, ["The agency counted sixty-eight percent of units."]
            )

    def test_numbers_are_derived_from_accepted_fragments(self) -> None:
        evidence = evidence_fixture()
        self.assertEqual([item["value"] for item in evidence[0]["numbers"]],
                         ["68%", "12"])
        self.assertTrue(all(item["fragment_id"].startswith("frag_v1_")
                            for item in evidence[0]["numbers"]))


class CardBindingTest(unittest.TestCase):
    def test_card_binds_claim_number_fragment_document_and_url(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        claim = card["confirmed_claims"][0]
        number = card["citable_numbers"][0]
        self.assertTrue(claim["claim_id"].startswith("claim_v1_"))
        self.assertEqual(number["claim_id"], claim["claim_id"])
        self.assertEqual(number["fragment_id"], claim["fragment_ids"][0])
        self.assertEqual(number["url"], SOURCE["url"])

    def test_foreign_fragment_number_and_wrong_claim_are_rejected(self) -> None:
        evidence = evidence_fixture()
        fragments = evidence[0]["fragments"]
        number = evidence[0]["numbers"][0]
        base = {
            "working_thesis": "t", "main_mechanism": "m",
            "confirmed_claims": [
                {"claim": "c", "fragment_ids": [fragments[0]["fragment_id"]]},
            ],
            "citable_numbers": [], "parallel_mechanisms": [],
            "uncertain_claims": [], "contradictions": [], "not_established": [],
        }
        foreign_fragment = copy.deepcopy(base)
        foreign_fragment["confirmed_claims"][0]["fragment_ids"] = ["frag_v1_foreign"]
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_card(foreign_fragment, evidence)

        foreign_number = copy.deepcopy(base)
        foreign_number["citable_numbers"] = [{
            "number_id": "num_v1_foreign", "means": "x", "claim_index": 0,
        }]
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_card(foreign_number, evidence)

        wrong_claim = copy.deepcopy(base)
        wrong_claim["confirmed_claims"].append({
            "claim": "other", "fragment_ids": [fragments[1]["fragment_id"]],
        })
        wrong_claim["citable_numbers"] = [{
            "number_id": number["number_id"], "means": "x", "claim_index": 1,
        }]
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_card(wrong_claim, evidence)

    def test_cached_evidence_tampering_and_incomplete_number_inventory_are_rejected(self) -> None:
        evidence = evidence_fixture()
        raw = {
            "working_thesis": "t", "main_mechanism": "m",
            "confirmed_claims": [{
                "claim": "c",
                "fragment_ids": [evidence[0]["fragments"][0]["fragment_id"]],
            }],
            "citable_numbers": [], "parallel_mechanisms": [],
            "uncertain_claims": [], "contradictions": [], "not_established": [],
        }
        tampered = copy.deepcopy(evidence)
        tampered[0]["fragments"][0]["text"] = "tampered"
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_card(raw, tampered)
        incomplete = copy.deepcopy(evidence)
        incomplete[0]["numbers"].pop()
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_card(raw, incomplete)

    def test_versions_changed_only_for_changed_model_shapes(self) -> None:
        self.assertEqual(model_contracts.CONTRACTS["review"].version, 2)
        self.assertEqual(model_contracts.CONTRACTS["synthesis"].version, 2)
        self.assertEqual(model_contracts.CONTRACTS["classify"].version, 2)
        self.assertEqual(model_contracts.CONTRACTS["write"].version, 1)


class SentenceLedgerTest(unittest.TestCase):
    def test_sentence_splitter_preserves_abbreviation_decimal_and_offsets(self) -> None:
        body = "Dr. Lee measured 2.5 units.\n\nThe result changed policy."
        units = provenance.sentence_units(body)
        self.assertEqual([item["text"] for item in units], [
            "Dr. Lee measured 2.5 units.", "The result changed policy.",
        ])
        for item in units:
            self.assertEqual(body[item["start_offset"]:item["end_offset"]],
                             item["text"])

    def test_review_requires_every_sentence_exactly_once(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "The agency counted 68%. This looks like a feedback loop."
        units = provenance.sentence_units(body)
        one = [{
            "sentence_id": units[0]["sentence_id"], "class": "FACT",
            "support": "SUPPORTED",
            "claim_ids": [card["confirmed_claims"][0]["claim_id"]], "why": "",
        }]
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_review({"sentences": one, "summary": ""}, units, card)
        duplicate = one + [dict(one[0])]
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_review(
                {"sentences": duplicate, "summary": ""}, units[:1], card
            )

    def test_mixed_unsupported_is_a_factual_failure(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "My reading is that the agency counted everyone, so the rule is circular."
        units = provenance.sentence_units(body)
        raw = {"sentences": [{
            "sentence_id": units[0]["sentence_id"], "class": "MIXED",
            "support": "UNSUPPORTED", "claim_ids": [],
            "why": "the card does not establish everyone",
        }], "summary": "unsupported premise"}
        model_contracts.validate("review", raw)
        report = provenance.bind_review(raw, units, card)
        self.assertEqual(report["unsupported_facts"][0]["class"], "MIXED")
        self.assertFalse(report["sentences"][0]["supported"])

    def test_unknown_claim_id_is_rejected(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        units = provenance.sentence_units("The agency counted 68%.")
        raw = {"sentences": [{
            "sentence_id": units[0]["sentence_id"], "class": "FACT",
            "support": "SUPPORTED", "claim_ids": ["claim_v1_foreign"],
            "why": "",
        }], "summary": ""}
        with self.assertRaises(provenance.ProvenanceError):
            provenance.bind_review(raw, units, card)


class UsageAndPersistenceTest(unittest.TestCase):
    def test_metadata_digit_is_not_a_number_corpus(self) -> None:
        card = {
            "confirmed_claims": [{"url": "https://example.org/report/2026"}],
            "citable_numbers": [],
        }
        self.assertEqual(gates.numbers_outside_corpus("The report says 2026.", card),
                         ["2026"])

    def test_used_and_unused_are_computed_from_final_sentence_ledger(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "The agency counted 68%. This looks like a feedback loop."
        report = supported_review(body, card)
        final, findings = provenance.finalize_card(card, evidence, report, body)
        self.assertEqual(findings, [])
        self.assertEqual(final["used_claim_ids"],
                         [card["confirmed_claims"][0]["claim_id"]])
        self.assertEqual(final["used_number_ids"],
                         [card["citable_numbers"][0]["number_id"]])
        unused = final["unused_evidence"][0]
        self.assertEqual(unused["excerpts"], [EXCERPTS[1]])
        self.assertNotIn(EXCERPTS[0], unused["excerpts"])
        self.assertEqual(final["citations"][0]["document_id"],
                         evidence[0]["document_id"])

    def test_number_bound_to_another_claim_is_flagged(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "The agency used a 12-month threshold."
        units = provenance.sentence_units(body)
        report = provenance.bind_review({"sentences": [{
            "sentence_id": units[0]["sentence_id"], "class": "FACT",
            "support": "SUPPORTED",
            "claim_ids": [card["confirmed_claims"][0]["claim_id"]], "why": "",
        }], "summary": ""}, units, card)
        result = provenance.analyze_usage(card, evidence, report, body)
        self.assertEqual([item["gate"] for item in result["findings"]],
                         ["LICZBA_BEZ_LANCUCHA"])

    def test_normalized_chain_is_durable_in_sqlite(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "The agency counted 68%. This looks like a feedback loop."
        report = supported_review(body, card)
        final, _ = provenance.finalize_card(card, evidence, report, body)
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "lineage.db")
            try:
                provenance.persist_article_lineage(conn, 7, final)
                expected = {
                    "provenance_documents": 1,
                    "provenance_fragments": 2,
                    "article_claims": 2,
                    "claim_fragments": 2,
                    "article_numbers": 2,
                    "article_sentences": 2,
                    "sentence_claims": 1,
                    "article_citations": 1,
                }
                for table, count in expected.items():
                    with self.subTest(table=table):
                        value = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        self.assertEqual(value, count)
                used = conn.execute(
                    "SELECT used FROM article_claims ORDER BY claim_id"
                ).fetchall()
                self.assertEqual(sorted(row[0] for row in used), [0, 1])
            finally:
                conn.close()

    def test_persistence_revalidates_final_graph(self) -> None:
        evidence = evidence_fixture()
        card = card_fixture(evidence)
        body = "The agency counted 68%. This looks like a feedback loop."
        report = supported_review(body, card)
        final, _ = provenance.finalize_card(card, evidence, report, body)
        final["citations"][0]["document_id"] = "doc_v1_foreign"
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "tampered.db")
            try:
                with self.assertRaises(provenance.ProvenanceError):
                    provenance.persist_article_lineage(conn, 8, final)
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM article_citations").fetchone()[0],
                    0,
                )
            finally:
                conn.close()

    def test_bank_ignores_historical_unproven_unused_label(self) -> None:
        old = {"unused_evidence": [{
            "url": "https://old.example/1", "publisher": "old",
            "excerpts": ["x" * 90],
        }]}
        new = {"provenance_version": provenance.LINEAGE_VERSION,
               "unused_evidence": [{
                   "url": "https://new.example/1", "publisher": "new",
                   "fragments": [{
                       "fragment_id": "frag_v1_unused",
                       "document_id": "doc_v1_unused", "text": "y" * 90,
                   }],
               }]}
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "bank.db")
            try:
                for index, card in enumerate((old, new), 1):
                    conn.execute(
                        "INSERT INTO articles "
                        "(run_id, created_at, title, evidence, status) "
                        "VALUES (?, ?, ?, ?, 'SAVED')",
                        (index, db.now(), f"article {index}", json.dumps(card)),
                    )
                conn.commit()
                bank = stages.bank_fragmentow(conn)
                self.assertEqual(len(bank), 1)
                self.assertEqual(bank[0]["fragment_id"], "frag_v1_unused")
                self.assertEqual(bank[0]["url"], "https://new.example/1")
            finally:
                conn.close()


class StageBoundaryTest(unittest.TestCase):
    def test_synthesis_and_review_record_contextual_passes(self) -> None:
        evidence = evidence_fixture()
        fragment = evidence[0]["fragments"][0]
        number = next(item for item in evidence[0]["numbers"]
                      if item["value"] == "68%")
        raw_card = {
            "working_thesis": "t", "main_mechanism": "m",
            "confirmed_claims": [{
                "claim": "The agency counted 68% of units.",
                "fragment_ids": [fragment["fragment_id"]],
            }],
            "citable_numbers": [{
                "number_id": number["number_id"], "means": "share", "claim_index": 0,
            }],
            "parallel_mechanisms": [], "uncertain_claims": [],
            "contradictions": [], "not_established": [],
        }
        original = stages.llm.call
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "boundaries.db")
            try:
                stages.llm.call = lambda *_args, **_kwargs: json.dumps(raw_card)
                card = stages.synthesis(conn, 9, "question", evidence)
                body = "The agency counted 68%."
                unit = provenance.sentence_units(body)[0]
                raw_review = {"sentences": [{
                    "sentence_id": unit["sentence_id"], "class": "FACT",
                    "support": "SUPPORTED",
                    "claim_ids": [card["confirmed_claims"][0]["claim_id"]],
                    "why": "",
                }], "summary": "ok"}
                stages.llm.call = lambda *_args, **_kwargs: json.dumps(raw_review)
                report = stages.review(conn, 9, card, {"body": body})
                self.assertEqual(report["sentences"][0]["text"], body)
                checks = conn.execute(
                    "SELECT stage, ok FROM provenance_checks ORDER BY id"
                ).fetchall()
                self.assertEqual([(row["stage"], row["ok"]) for row in checks],
                                 [("synthesis", 1), ("review", 1)])
            finally:
                stages.llm.call = original
                conn.close()

    def test_classify_rejects_non_verbatim_model_excerpt_and_records_failure(self) -> None:
        original = stages.llm.call
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "stage.db")
            try:
                stages.llm.call = lambda *_args, **_kwargs: json.dumps({
                    "class": "PRIMARY", "relevance": 1.0,
                    "excerpts": ["A paraphrase absent from the document."],
                    "note": "fixture",
                })
                with self.assertRaises(ValueError):
                    stages.classify(conn, 3, "question", [SOURCE])
                row = conn.execute(
                    "SELECT ok, stage FROM provenance_checks ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertEqual((row["ok"], row["stage"]),
                                 (0, "classify_fragments"))
            finally:
                stages.llm.call = original
                conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
