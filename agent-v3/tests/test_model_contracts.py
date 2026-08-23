"""Kontrdowody wersjonowanych i zamkniętych odpowiedzi LLM V3."""

from __future__ import annotations

import ast
import copy
import json
import pathlib
import tempfile
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import db
import llm
import model_contracts
import stages


VALID = {
    "review": {"sentences": [], "summary": "ok"},
    "forma": {
        "beliefs": [], "support_only": [],
        "hardest_fact": {"quote": "q", "why": "w"},
        "procedural_nearby": {"quote": "q"}, "same_register": True,
        "reader_moment": None,
        "opening_claim": {"quote": "q", "already_familiar": False},
        "summary": "ok",
    },
    "write": {
        "title": "t", "subtitle": "s", "body": "b", "numbers_used": [],
        "limits_paragraph_present": False,
    },
    "revise": {
        "title": "t", "subtitle": "s", "body": "b",
        "limits_paragraph_present": False, "changes": [],
    },
    "wybor": {"choices": [], "skipped_because": "none"},
    "reply": {"reply": "text", "reason_if_silent": "", "kind": "answer"},
    "grafika": {"subject": "object", "why_this_object": "because", "prompt": "p"},
    "cele": {"targets": []},
    "curiosity": {"facts": []},
    "note": {"note": "n", "words": 1, "fact_used": "f", "source_url": "u"},
    "restack": {
        "restack": False, "reason": "no", "sentence": "", "mechanism_named": "",
    },
    "fact_search": {"facts": []},
    "verification": {"claims": [], "safe_to_post": True, "verdict": "ok"},
    "comment": {"comment": "c", "reason_if_silent": "", "what_it_adds": "x"},
    "synthesis": {
        "working_thesis": "t", "main_mechanism": "m", "confirmed_claims": [],
        "citable_numbers": [], "parallel_mechanisms": [], "uncertain_claims": [],
        "contradictions": [], "not_established": [],
    },
    "classify": {
        "class": "PRIMARY", "relevance": 0.5, "excerpts": [], "note": "n",
    },
    "discovery": {"sources": []},
    "feasibility": {"assessments": []},
    "scout": {
        "discarded_seeds": [],
        "topics": [],
        "ranking": {
            "largest_article_universe": [], "most_compelling": [],
            "most_original_angle": [], "most_likely_to_collapse": [],
        },
    },
    "bibliotekarz": {"groups": [], "loners": [], "note": "n"},
    "warto_pisac": {
        "contradicted_belief": {"present": False, "the_belief": "", "evidence": ""},
        "named_decider": {"present": False, "evidence": ""},
        "felt_number": {"present": False, "evidence": ""},
        "second_domain": {"present": False, "evidence": ""},
        "unsettled_outcome": {
            "present": False, "the_question": "", "the_situation": "",
            "governed_by": "",
        },
        "what_would_rescue_it": "x", "one_line_verdict": "v",
    },
    "fedreg": {"candidates": []},
}


class RegistryTest(unittest.TestCase):
    def test_every_contract_has_a_valid_versioned_example(self) -> None:
        self.assertEqual(set(VALID), set(model_contracts.CONTRACTS))
        for name, value in VALID.items():
            with self.subTest(contract=name):
                self.assertIs(model_contracts.validate(name, value), value)
                self.assertRegex(
                    model_contracts.contract_id(name),
                    rf"^{name}@{model_contracts.CONTRACTS[name].version}:[0-9a-f]{{12}}$",
                )

    def test_every_contract_rejects_missing_wrong_and_extra_root_field(self) -> None:
        for name, value in VALID.items():
            key = next(iter(value))
            missing = copy.deepcopy(value)
            del missing[key]
            wrong = copy.deepcopy(value)
            wrong[key] = object()
            extra = copy.deepcopy(value)
            extra["unexpected_model_field"] = True
            for label, candidate in (
                ("missing", missing), ("wrong", wrong), ("extra", extra),
            ):
                with self.subTest(contract=name, defect=label), self.assertRaises(
                        model_contracts.ContractError):
                    model_contracts.validate(name, candidate)

    def test_bool_is_not_a_number_and_ranges_are_hard(self) -> None:
        value = copy.deepcopy(VALID["classify"])
        value["relevance"] = True
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("classify", value)
        value["relevance"] = 1.01
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("classify", value)

    def test_conditional_fields_are_enforced(self) -> None:
        review = copy.deepcopy(VALID["review"])
        review["sentences"] = [{
            "sentence_id": "sent_v1_x", "class": "FACT",
            "support": "UNSUPPORTED", "claim_ids": [], "why": "",
        }]
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("review", review)

        comment = copy.deepcopy(VALID["comment"])
        comment.update(comment=None, reason_if_silent="")
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("comment", comment)

        scout = copy.deepcopy(VALID["scout"])
        scout["topics"] = [{
            "title": "t", "question": "q", "kind": "SYSTEM_UNDER_TEST",
            "already_written": [], "scale": "A_COUNTRY", "precedents": [],
            "threads": [], "article_routes": ["route"] * 20,
            "broken_belief": "wrong kind",
        }]
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("scout", scout)

        feasibility = {"assessments": [{
            "index": 0, "feasible": True, "confidence": 0.9,
            "expected_primary_sources": 4, "depth": "RICH",
            "parallels": [], "note": "Records exist.",
            "route_assessments": [{
                "route_index": 0, "feasible": False, "confidence": 0.4,
                "expected_primary_sources": 1, "depth": "THIN",
                "second_act": "No second act exists.", "note": "Too weak.",
            }],
            "selected_route_index": 0,
            "selected_route_reason": "Incorrect selection.",
        }]}
        with self.assertRaisesRegex(model_contracts.ContractError, "niewykonalna"):
            model_contracts.validate("feasibility", feasibility)

        verification = copy.deepcopy(VALID["verification"])
        verification["claims"] = [{
            "claim": "x", "status": "refuted", "url": "u",
            "what_the_source_says": "",
        }]
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("verification", verification)

    def test_discovery_requires_dated_unique_evidence_roles(self) -> None:
        source = {
            "url": "https://example.com/record", "title": "record",
            "publisher": "Authority", "class": "PRIMARY",
            "host_role": "ORIGINATING_AUTHORITY",
            "access_claim": "FULL_TEXT_NO_LOGIN", "published_at": "2026",
            "evidence_status": "OBSERVED_CURRENT_RECORD",
            "evidence_roles": ["MECHANISM"], "answers_why": True,
            "has_numbers": True, "note": "fixture",
        }
        model_contracts.validate("discovery", {"sources": [source]})
        duplicate = copy.deepcopy(source)
        duplicate["evidence_roles"] = ["MECHANISM", "MECHANISM"]
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("discovery", {"sources": [duplicate]})
        undated = copy.deepcopy(source)
        undated["published_at"] = ""
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("discovery", {"sources": [undated]})

    def test_parallel_mechanism_has_one_canonical_shape(self) -> None:
        canonical = copy.deepcopy(VALID["synthesis"])
        canonical["parallel_mechanisms"] = [{
            "domain": "aviation", "how_it_matches": "same rule",
            "origin": "evidence_bank",
        }]
        model_contracts.validate("synthesis", canonical)
        legacy = copy.deepcopy(VALID["synthesis"])
        legacy["parallel_mechanisms"] = [{
            "domain": "aviation", "mechanism": "same rule", "z_banku": True,
        }]
        with self.assertRaises(model_contracts.ContractError):
            model_contracts.validate("synthesis", legacy)


class StrictJSONTest(unittest.TestCase):
    def test_bare_and_fenced_objects_are_accepted(self) -> None:
        self.assertEqual(llm.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_prose_array_duplicate_nan_and_unclosed_fence_are_rejected(self) -> None:
        bad = (
            'Here: {"a": 1}', '{"a": 1} trailing', '[{"a": 1}]',
            '{"a": 1, "a": 2}', '{"a": NaN}', '```json\n{"a": 1}',
        )
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                llm.parse_json(text)


class IntegrationTest(unittest.TestCase):
    def test_every_stage_parse_site_uses_a_registered_contract(self) -> None:
        source = pathlib.Path(stages.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        direct = []
        contracts = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "llm"
                    and node.func.attr == "parse_json"):
                direct.append(node.lineno)
            if isinstance(node.func, ast.Name) and node.func.id == "_model_json":
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    contracts.append(node.args[1].value)
        self.assertEqual(len(direct), 1)
        self.assertEqual(len(contracts), 22)
        self.assertEqual(set(contracts), set(model_contracts.CONTRACTS))

    def test_contract_pass_and_failure_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            conn = db.connect(pathlib.Path(temp) / "contracts.db")
            try:
                good = json.dumps(VALID["synthesis"])
                stages._model_json(
                    good, "synthesis", conn=conn, run_id=7, purpose="synthesis")
                bad = copy.deepcopy(VALID["synthesis"])
                bad["unexpected"] = True
                with self.assertRaises(model_contracts.ContractError):
                    stages._model_json(
                        json.dumps(bad), "synthesis", conn=conn, run_id=7,
                        purpose="synthesis")
                rows = conn.execute(
                    "SELECT contract_id, ok, error FROM model_contract_checks "
                    "ORDER BY id").fetchall()
                expected = model_contracts.contract_id("synthesis")
                self.assertEqual([(r["contract_id"], r["ok"]) for r in rows],
                                 [(expected, 1), (expected, 0)])
                self.assertIn("nadmiarowe pola", rows[1]["error"])
            finally:
                conn.close()

    def test_evidence_bank_uses_the_canonical_parallel_fields(self) -> None:
        source = pathlib.Path(stages.__file__).with_name("run.py").read_text(
            encoding="utf-8")
        block = source[source.index("dolozone ="):source.index(
            "if dolozone:", source.index("dolozone ="))]
        self.assertIn('"how_it_matches"', block)
        self.assertIn('"origin": "evidence_bank"', block)
        self.assertNotIn('"mechanism":', block)
        self.assertNotIn('"z_banku":', block)
        fallback = stages.fallback_card("question", [])
        self.assertEqual(fallback["parallel_mechanisms"], [])

    def test_invalid_verification_and_selection_fail_closed(self) -> None:
        original_call = stages.llm.call
        try:
            stages.llm.call = lambda *_args, **_kwargs: '{"unexpected": true}'
            verdict = stages.zweryfikuj(None, 0, "A factual sentence.")
            self.assertFalse(verdict["safe_to_post"])
            self.assertFalse(verdict["verification_available"])

            comments = [
                {"autor": f"a{i}", "tekst": "question", "reakcje": 0,
                 "odpowiedzi": 0}
                for i in range(stages.config.ODPOWIADAJ_WSZYSTKIM_DO + 1)
            ]
            self.assertEqual(stages.wybierz_do_odpowiedzi(None, 0, comments), [])
        finally:
            stages.llm.call = original_call


if __name__ == "__main__":
    unittest.main(verbosity=2)
