"""N-011: wersjonowana decyzja, ograniczona rewizja i kwarantanna."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import editorial
import gates
import pipeline_replay


def finding(gate: str, detail: str = "fixture") -> dict[str, str]:
    return {"gate": gate, "detail": detail}


class QualityPolicyTest(unittest.TestCase):
    def test_clean_text_is_ready_autonomously_with_versioned_policy(self) -> None:
        decision = editorial.quality_decision([])
        self.assertEqual(decision["action"], "READY_AUTONOMOUS")
        self.assertTrue(decision["can_publish"])
        self.assertEqual(decision["policy_version"], "autonomous-editorial@1")
        self.assertEqual(len(decision["policy_hash"]), 64)

    def test_one_instruction_leak_is_never_a_minor_ready_note(self) -> None:
        decision = editorial.quality_decision([finding("FRAZA_Z_INSTRUKCJI")])
        self.assertEqual(decision["action"], "REVISE")
        self.assertFalse(decision["can_publish"])
        self.assertEqual(decision["severity_score"], 80)

    def test_unsupported_fact_requires_evidence_revision(self) -> None:
        decision = editorial.quality_decision([finding("FAKT_BEZ_POKRYCIA")])
        self.assertEqual(decision["action"], "REVISE_FACTS")
        self.assertEqual(decision["factual_count"], 1)
        self.assertFalse(decision["can_publish"])

    def test_narrow_evidence_and_missing_control_are_terminal(self) -> None:
        evidence = editorial.quality_decision([finding("WASKA_PODSTAWA")])
        control = editorial.quality_decision([finding("KONTROLA_NIEDOSTEPNA")])
        self.assertEqual(evidence["action"], "QUARANTINED_EVIDENCE")
        self.assertEqual(control["action"], "QUARANTINED_EDITORIAL")
        self.assertFalse(evidence["can_publish"])
        self.assertFalse(control["can_publish"])

    def test_unknown_gate_fails_closed_until_policy_is_updated(self) -> None:
        decision = editorial.quality_decision([finding("NEW_UNVERSIONED_GATE")])
        self.assertEqual(decision["action"], "QUARANTINED_EDITORIAL")


class RevisionProgressTest(unittest.TestCase):
    def test_same_body_or_new_gate_stops_as_no_improvement_or_regression(self) -> None:
        before = editorial.quality_decision([finding("FRAZA_Z_INSTRUKCJI")])
        same = editorial.quality_decision([finding("FRAZA_Z_INSTRUKCJI", "other")])
        worse = editorial.quality_decision([
            finding("FRAZA_Z_INSTRUKCJI"), finding("ZAKAZANE_OTWARCIE"),
        ])
        self.assertEqual(
            editorial.revision_progress(before, same, body_changed=False)["outcome"],
            "NO_IMPROVEMENT",
        )
        regression = editorial.revision_progress(before, worse, body_changed=True)
        self.assertEqual(regression["outcome"], "REGRESSION")
        self.assertEqual(regression["new_gates"], ["ZAKAZANE_OTWARCIE"])

    def test_resolved_revision_and_terminal_quarantine(self) -> None:
        before = editorial.quality_decision([finding("FAKT_BEZ_POKRYCIA")])
        clean = editorial.quality_decision([])
        self.assertEqual(
            editorial.revision_progress(before, clean, body_changed=True)["outcome"],
            "RESOLVED",
        )
        stopped = editorial.quarantine_after_revision(
            before, reason="limit rewizji",
        )
        self.assertEqual(stopped["action"], "QUARANTINED_EVIDENCE")
        self.assertFalse(stopped["can_publish"])


class LengthContractTest(unittest.TestCase):
    def test_depth_length_is_an_executable_gate(self) -> None:
        card = {
            "confirmed_claims": [
                {"url": "https://one.example/a"},
                {"url": "https://two.example/b"},
            ],
            "citable_numbers": [],
        }
        short = gates.deterministic_floors(
            "plain " * 100, card, poprzednie=[], glebokosc="RICH",
        )
        in_range = gates.deterministic_floors(
            "plain " * 900, card, poprzednie=[], glebokosc="RICH",
        )
        self.assertTrue(any(
            item["gate"] == "DLUGOSC_POZA_KONTRAKTEM" for item in short
        ))
        self.assertFalse(any(
            item["gate"] == "DLUGOSC_POZA_KONTRAKTEM" for item in in_range
        ))


class ActiveContractTest(unittest.TestCase):
    def test_active_runtime_has_no_needs_review_fallback(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1]
        active = "\n".join(
            (root / name).read_text(encoding="utf-8")
            for name in ("run.py", "editorial.py", "stages.py")
        )
        self.assertNotIn("NEEDS_REVIEW", active)
        self.assertIn("MAX_AUTONOMOUS_REVISIONS", active)


class FullPipelineRevisionTest(unittest.TestCase):
    def run_scenario(self, name: str) -> pipeline_replay.ReplayResult:
        with tempfile.TemporaryDirectory() as temp:
            return pipeline_replay.run_fixture(
                pathlib.Path(temp), revision_scenario=name,
            )

    def test_fact_is_removed_then_all_gates_and_provenance_run_again(self) -> None:
        result = self.run_scenario("resolve_fact")
        self.assertEqual(result.exit_code, 0, result.stderr + result.stdout)
        self.assertEqual(result.article_status, "READY_AUTONOMOUS")
        self.assertEqual(result.revision_rows, 1)
        self.assertEqual(result.revision_statuses, ["RESOLVED"])
        self.assertEqual(result.purposes.count("review"), 2)
        self.assertEqual(result.purposes.count("forma"), 2)
        self.assertEqual(result.purposes.count("revise"), 1)
        self.assertFalse(result.browser_imported)

    def test_no_improvement_is_quarantined_without_second_rewrite(self) -> None:
        result = self.run_scenario("no_improvement")
        self.assertEqual(result.exit_code, 0, result.stderr + result.stdout)
        self.assertEqual(result.article_status, "QUARANTINED_EVIDENCE")
        self.assertEqual(result.revision_statuses, ["NO_IMPROVEMENT"])
        self.assertEqual(result.purposes.count("revise"), 1)
        self.assertEqual(result.remote_mutations, 0)

    def test_new_gate_is_regression_and_editorial_quarantine(self) -> None:
        result = self.run_scenario("regression")
        self.assertEqual(result.exit_code, 0, result.stderr + result.stdout)
        self.assertEqual(result.article_status, "QUARANTINED_EDITORIAL")
        self.assertEqual(result.revision_statuses, ["REGRESSION"])
        self.assertEqual(result.purposes.count("revise"), 1)

    def test_two_improvements_hit_limit_and_never_fall_through_to_ready(self) -> None:
        result = self.run_scenario("limit")
        self.assertEqual(result.exit_code, 0, result.stderr + result.stdout)
        self.assertEqual(result.article_status, "QUARANTINED_EVIDENCE")
        self.assertEqual(result.revision_rows, 2)
        self.assertEqual(result.revision_statuses, ["IMPROVED", "LIMIT_REACHED"])
        self.assertEqual(result.purposes.count("revise"), 2)
        self.assertFalse(result.browser_imported)


if __name__ == "__main__":
    unittest.main(verbosity=2)
