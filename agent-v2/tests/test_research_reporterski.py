"""Behavioural tests for bounded follow-up research; no network or paid calls."""
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import llm
import research
import stages

A = "https://lab.example/policy"
B = "https://lab.example/policy-previous"
C = "https://review.example/evaluation"
QA = "The company proposed a conditional slowdown for frontier development."
QB = "The previous policy contained no requirement for external evaluation."
QC = "The independent evaluation did not establish a reduction in risk."


def source(url=A, quote=QA):
    return {"url": url, "title": "Policy record", "publisher": "Lab",
            "host": research.urlsplit(url).hostname, "class": "PRIMARY",
            "excerpts": [quote], "numbers": [], "relevance": 1.0}


def assessment(query="earlier policy external review", answered=False, ident=1, quote=QA):
    ref = {"source_id": ident, "quote": quote}
    return {"hypotheses": [{"explanation": "The policy may reduce risk.",
             "status": "supported", "support": [ref], "against": [],
             "would_change_mind": "An independent evaluation showing no benefit."}],
            "actors": [{"actor": "Lab", "possible_gain": "Possible trust benefit",
                        "possible_cost": "Possible delay", "evidence": [ref]}],
            "questions": [{"question": "Does the evaluation support this policy?",
              "status": "answered" if answered else "partial", "answer": "The lab proposes a slowdown.",
              "evidence": [ref], "importance": "high", "next_query": query,
              "why_next": "This could contradict the preferred explanation."}],
            "counterargument": {"text": "The proposed safeguard may be ineffective.", "evidence": [ref]},
            "ready": answered}


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE calls (run_id INTEGER, purpose TEXT, cost_usd REAL)")
        self.addCleanup(self.conn.close)
        for name, value in {"DATA_DIR": self.data, "RESEARCH_ENABLED": True,
                            "RESEARCH_MAX_ROUNDS": 2, "RESEARCH_STOP_USD": .15}.items():
            p = patch.object(config, name, value); p.start(); self.addCleanup(p.stop)
        self.responses = []
        self.calls = []
        self.fetches = []
        self.docs = {B: QB, C: QC}
        p = patch.object(llm, "call", side_effect=self.call); p.start(); self.addCleanup(p.stop)
        p = patch.object(stages, "fetch", side_effect=self.fetch); p.start(); self.addCleanup(p.stop)

    def call(self, purpose, system, prompt, **kwargs):
        self.calls.append((purpose, prompt))
        if not self.responses:
            raise AssertionError("Unexpected extra paid stage: " + purpose)
        expected, response, urls = self.responses.pop(0)
        self.assertEqual(purpose, expected)
        if isinstance(response, BaseException):
            raise response
        if kwargs.get("collect_urls") is not None:
            kwargs["collect_urls"].extend(urls)
        self.conn.execute("INSERT INTO calls VALUES (?,?,?)", (kwargs["run_id"], purpose, .001))
        return json.dumps(response)

    def fetch(self, conn, run_id, sources):
        self.fetches.append([s["url"] for s in sources])
        return [{**s, "text": self.docs[s["url"]]} for s in sources]

    def queue(self, purpose, value, urls=()):
        self.responses.append((purpose, value, list(urls)))

    def round(self, url=B, quote=QB):
        self.queue("investigation_search", {"sources": [{"url": url, "class": "PRIMARY"}]}, [url])
        self.queue("investigation_extract", {"documents": [{"source_id": 1, "class": "PRIMARY",
                   "excerpts": [quote], "numbers": []}]})

    def run_research(self):
        return research.deepen(self.conn, 1, "Why propose a slowdown?", [source()],
                               [{"url": A, "text": QA}])

    def test_reads_evidence_then_changes_followup_question(self):
        self.queue("investigation", assessment())
        self.round()
        self.queue("investigation", assessment("independent evaluation effectiveness", ident=2, quote=QB))
        self.round(C, QC)
        self.queue("investigation", assessment(answered=True, ident=3, quote=QC))
        evidence, dossier = self.run_research()
        self.assertEqual([s["url"] for s in evidence], [A, B, C])
        self.assertEqual(dossier["stop_reason"], "answered")
        self.assertEqual(len(self.calls), 7)
        self.assertIn("independent evaluation effectiveness", self.calls[4][1])
        self.assertEqual(self.fetches, [[B], [C]])
        saved = json.loads(Path(dossier["path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["assessments"]), 3)
        self.assertEqual(saved["assessment"]["questions"][0]["evidence"][0]["url"], C)

    def test_satisfied_question_needs_no_search(self):
        self.queue("investigation", assessment(answered=True))
        _, dossier = self.run_research()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.fetches)
        self.assertEqual(dossier["stop_reason"], "answered")

    def test_two_rounds_are_a_real_ceiling(self):
        self.queue("investigation", assessment())
        self.round()
        self.queue("investigation", assessment("second query", ident=2, quote=QB))
        self.round(C, QC)
        self.queue("investigation", assessment("third query", ident=3, quote=QC))
        _, dossier = self.run_research()
        self.assertEqual(dossier["stop_reason"], "round_limit")
        self.assertEqual(len(self.fetches), 2)

    def test_unsupported_claims_cannot_mark_question_answered(self):
        raw = assessment(answered=True, quote="A fabricated passage proving that the lab is lying.")
        checked = research._assessment(raw, research._view([source()]))
        self.assertFalse(checked["ready"])
        self.assertEqual(checked["questions"][0]["status"], "open")
        self.assertEqual(checked["questions"][0]["answer"], "")
        self.assertEqual(checked["hypotheses"][0]["status"], "unresolved")
        self.assertFalse(checked["actors"])

    def test_search_must_really_return_the_exact_document(self):
        self.queue("investigation", assessment())
        self.queue("investigation_search", {"sources": [{"url": B}]}, [])
        evidence, dossier = self.run_research()
        self.assertEqual(dossier["stop_reason"], "no_search_results")
        self.assertEqual(len(evidence), 1)
        self.assertFalse(self.fetches)

    def test_invented_path_on_a_real_host_is_rejected(self):
        self.queue("investigation_search", {"sources": [{"url": B}]}, [A])
        self.assertEqual(research._search(self.conn, 1, "Why?", {}, set()), [])

    def test_duplicate_tracking_url_is_skipped_but_same_host_new_document_allowed(self):
        self.queue("investigation_search", {"sources": [{"url": A + "?utm_source=x"}, {"url": B}]}, [A, B])
        result = research._search(self.conn, 1, "Why?", {}, {A})
        self.assertEqual([s["url"] for s in result], [B])
        self.assertNotEqual(research.url_key(A + "?version=1"), research.url_key(A + "?version=2"))

    def test_invalid_quote_and_numbers_do_not_enter_evidence(self):
        self.queue("investigation", assessment())
        self.round(quote="The company secretly wants to eliminate all competitors.")
        evidence, dossier = self.run_research()
        self.assertEqual(dossier["stop_reason"], "no_new_verified_passages")
        self.assertEqual(len(evidence), 1)

    def test_copied_press_release_does_not_buy_another_round(self):
        self.docs[B] = QA
        self.queue("investigation", assessment())
        self.round(quote=QA)
        _, dossier = self.run_research()
        self.assertEqual(dossier["stop_reason"], "no_new_verified_passages")
        self.assertEqual(len(self.calls), 3)

    def test_cost_threshold_stops_before_next_call(self):
        self.conn.execute("INSERT INTO calls VALUES (1,'investigation',.15)")
        evidence, dossier = self.run_research()
        self.assertFalse(self.calls)
        self.assertEqual(dossier["stop_reason"], "cost_threshold")
        self.assertEqual(evidence, [source()])

    def test_global_budget_is_not_swallowed(self):
        self.queue("investigation", llm.BudgetExceeded("global limit"))
        with self.assertRaises(llm.BudgetExceeded):
            self.run_research()
        files = list(self.data.glob("research/*/run-1.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text())["stop_reason"], "global_budget_or_preflight")

    def test_failed_assessment_preserves_paid_evidence(self):
        self.queue("investigation", {"not": "an assessment"})
        evidence, dossier = self.run_research()
        self.assertEqual(dossier["stop_reason"], "failed:ValueError")
        self.assertEqual(evidence, [source()])

    def test_cache_requires_same_question_and_passages(self):
        self.queue("investigation", assessment(answered=True))
        research._assess(self.conn, 1, "Question one", [source()], [])
        _, cached = research._assess(self.conn, 2, "Question one", [source()], [])
        self.assertTrue(cached)
        self.assertEqual(len(self.calls), 1)
        self.queue("investigation", assessment(answered=True))
        _, cached = research._assess(self.conn, 2, "Question two", [source()], [])
        self.assertFalse(cached)
        self.queue("investigation", assessment(answered=True, quote=QB))
        _, cached = research._assess(self.conn, 2, "Question one", [source(A, QB)], [])
        self.assertFalse(cached)

    def test_cache_expiry_requires_new_assessment(self):
        self.queue("investigation", assessment(answered=True))
        research._assess(self.conn, 1, "Question", [source()], [])
        p = next(self.data.glob("research/cache/*.json")); saved = json.loads(p.read_text())
        saved["created_at"] = "2000-01-01T00:00:00+00:00";p.write_text(json.dumps(saved))
        self.queue("investigation", assessment(answered=True))
        _, cached = research._assess(self.conn, 2, "Question", [source()], [])
        self.assertFalse(cached)

    def test_unresolved_question_reaches_writer_card(self):
        d = {"assessment": research._assessment(assessment(), research._view([source()])),
             "stop_reason": "round_limit"}
        card = research.attach({"confirmed_claims": []}, d)
        self.assertIn("Does the evaluation support this policy?", card["not_established"])
        self.assertFalse(card["confirmed_claims"])
        self.assertIn("inferences are NOT confirmed facts", research.synthesis_question("Q", d))

    def test_private_and_credential_urls_rejected(self):
        for url in ["http://127.0.0.1/x", "http://localhost/x", "http://10.1.2.3/x", "https://user:pass@example.com"]:
            self.assertEqual(research.url_key(url), "")

    def test_models_and_search_ceiling(self):
        self.assertEqual(config.MODEL_FOR["write"], config.FABLE)
        for stage in research.PURPOSES:
            self.assertEqual(config.MODEL_FOR[stage], config.DEEPSEEK)
            self.assertLessEqual(config.MAX_TOKENS[stage], 8000)
        self.assertEqual(config.max_szukan("investigation_search"), 3)

    def test_live_json_delimiter_error_is_repaired_without_changing_content(self):
        raw = '{"refs": [{"quote": "Quoted ] and } stay unchanged", "source_id": 1]]}'
        self.assertEqual(research._parse(raw), {"refs": [{"quote": "Quoted ] and } stay unchanged", "source_id": 1}]})

    def test_json_repair_does_not_complete_truncated_or_rewrite_claims(self):
        for raw in ['{"claim": "unfinished', '{"claim": "x"', '{"a": unquoted}']:
            with self.assertRaises(ValueError):
                research._parse(raw)

    def test_quote_with_escaped_characters_survives_delimiter_repair(self):
        claim = 'He said "brackets ]" and \\ paths.'
        raw = '{"refs": [{"quote": ' + json.dumps(claim) + ']]}'
        self.assertEqual(research._parse(raw)["refs"][0]["quote"], claim)

    def test_model_selects_high_value_gap_instead_of_always_first_question(self):
        raw = assessment()
        second = copy.deepcopy(raw['questions'][0])
        second.update(question='Could competitors gain from this policy?', next_query='competitor compliance costs')
        raw['questions'].append(second); raw['next_question'] = 2
        self.queue('investigation', raw)
        self.queue('investigation_search', {'sources': []}, [B])
        _, dossier = self.run_research()
        self.assertEqual(dossier['rounds'][0]['question'], second['question'])
        self.assertEqual(dossier['rounds'][0]['query'], second['next_query'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
