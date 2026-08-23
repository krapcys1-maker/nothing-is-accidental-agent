"""Offline contracts for the provider-isolated E-014 live continuation."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capabilities  # noqa: E402
import config  # noqa: E402
import editorial_live_continuation as experiment  # noqa: E402
import llm  # noqa: E402
import pipeline_replay  # noqa: E402
import trafilatura  # noqa: E402


class ContinuationFake(pipeline_replay._FixtureModels):
    def __init__(self) -> None:
        super().__init__(revision_scenario="resolve_fact")

    def __call__(self, purpose, system, user, **kwargs):
        if purpose == "note":
            text = (
                "Six minutes disappeared from Europe's kitchen clocks.\n\n"
                "They were not broken. Grid-powered clocks count electrical cycles, "
                "and a prolonged dip below 50 Hz made those cycles arrive late.\n\n"
                "The wall clock was quietly displaying the condition of a continent."
            )
            return json.dumps({
                "note": text,
                "words": len(text.split()),
                "fact_used": "grid cycles",
                "source_url": "https://www.entsoe.eu/",
            })
        if purpose == "factcheck":
            return json.dumps({
                "claims": [{
                    "claim": "Grid-powered clocks count electrical cycles.",
                    "status": "confirmed",
                    "url": "https://www.entsoe.eu/",
                    "what_the_source_says": "The supplied claim is confirmed.",
                }],
                "safe_to_post": True,
                "verdict": "The supplied claim is confirmed.",
            })
        if purpose == "review" and "blind editorial-style evaluator" in system:
            return json.dumps({
                "A": {"scores": {"voice": 3}, "evidence": ["exact A"]},
                "B": {"scores": {"voice": 2}, "evidence": ["exact B"]},
                "winner": "A",
                "reason": "A is more concrete.",
            })
        return super().__call__(purpose, system, user, **kwargs)


class LiveContinuationTests(unittest.TestCase):
    def patches(self):
        return (
            mock.patch.object(
                capabilities, "current_mode", return_value=capabilities.Mode.MODEL_TEST
            ),
            mock.patch.object(capabilities, "kill_switch_active", return_value=False),
            mock.patch.object(config, "DRY_RUN", False),
            mock.patch.object(config, "CHEAP_MODE", False),
            mock.patch.object(config, "DEEPSEEK_API_KEY", "test-only"),
            mock.patch.object(config, "ANTHROPIC_API_KEY", "test-only"),
            mock.patch.object(
                experiment, "DEEPSEEK_LIVE_BLOCKED_AFTER_THREE_UNKNOWN", False
            ),
        )

    def test_budget_and_dispatch_math(self) -> None:
        self.assertEqual(experiment.MAX_CALLS[experiment.ARM_ANTHROPIC], 8)
        self.assertEqual(experiment.MAX_CALLS[experiment.ARM_DEEPSEEK], 23)
        self.assertEqual(
            experiment.MAX_CALLS_BY_ARM[experiment.ARM_ANTHROPIC],
            {config.FABLE: 3, config.CLAUDE: 5},
        )
        self.assertEqual(
            experiment.MAX_CALLS_BY_ARM[experiment.ARM_DEEPSEEK],
            {config.DEEPSEEK_PRO: 13, config.DEEPSEEK: 10},
        )
        self.assertAlmostEqual(experiment.BASELINE_EXPOSURE_USD, 4.87558670)
        self.assertAlmostEqual(experiment.PROGRAM_MAX_EXPOSURE_USD, 9.97558670)
        self.assertLess(experiment.PROGRAM_MAX_EXPOSURE_USD, 10.0)

    def test_scout_prompt_is_compact_without_losing_contract_fields(self) -> None:
        prompt = (ROOT / "prompts" / "skaut.md").read_text(encoding="utf-8")
        self.assertLess(len(prompt.splitlines()), 260)
        self.assertLess(len(prompt.split()), 2000)
        for placeholder in (
            "{count}", "{pytania_czytelnikow}",
            "{editorial_memory_json}", "{history_json}",
        ):
            self.assertIn(placeholder, prompt)
        for required in (
            "discarded_seeds", "central_question", "mode",
            "why_fascinating", "reader_entry_point", "obvious_coverage",
            "underexplored_connections", "dimensions", "tensions",
            "open_branches", "article_routes", "note_test",
            "fatal_weakness", "largest_article_universe",
            "most_compelling", "most_original_angle", "most_likely_to_collapse",
        ):
            self.assertIn(required, prompt)
        self.assertIn("There is deliberately no magic count", prompt)
        self.assertIn("does not have to be a system", prompt)

    def test_preflight_rejects_existing_workspace_and_missing_input(self) -> None:
        patches = self.patches()
        with tempfile.TemporaryDirectory(dir=ROOT) as temp, \
                patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], patches[6]:
            existing = pathlib.Path(temp)
            with self.assertRaisesRegex(RuntimeError, "must not exist"):
                experiment.validate_preflight(
                    existing, arm=experiment.ARM_ANTHROPIC, max_cost_usd=0.5
                )

    def test_real_deepseek_preflight_is_blocked_after_three_unknowns(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "three consecutive UNKNOWN"):
            experiment.validate_preflight(
                ROOT / ".live-tests" / "blocked-after-three-unknowns",
                arm=experiment.ARM_DEEPSEEK,
                max_cost_usd=0.5,
                anthropic_artifact=ROOT / "does-not-matter.json",
            )
            missing = existing / "new"
            with self.assertRaisesRegex(RuntimeError, "requires the completed"):
                experiment.validate_preflight(
                    missing, arm=experiment.ARM_DEEPSEEK, max_cost_usd=0.5,
                    anthropic_artifact=existing / "missing.json",
                )

    def test_complete_two_arm_fixture_executes_exact_contract(self) -> None:
        fake = ContinuationFake()
        patches = self.patches()
        with tempfile.TemporaryDirectory(dir=ROOT) as parent, \
                patches[0], patches[1], patches[2], patches[3], patches[4], \
                patches[5], patches[6], \
                mock.patch.object(llm, "call", side_effect=fake), \
                mock.patch.object(
                    experiment.safe_fetch, "get",
                    side_effect=lambda url, **_kwargs: pipeline_replay._FixtureResponse(
                        url=url,
                        text=pipeline_replay.SOURCE_TEXTS[url],
                        resolved_ips={"fixture": ["192.0.2.10"]},
                    ),
                ), mock.patch.object(
                    trafilatura, "extract", side_effect=lambda text, **_kwargs: text
                ):
            parent_path = pathlib.Path(parent)
            anthropic_workspace = parent_path / "anthropic"
            anthropic = experiment.run_arm(
                anthropic_workspace,
                arm=experiment.ARM_ANTHROPIC,
                max_cost_usd=0.50,
            )
            self.assertEqual(anthropic["status"], "COMPLETE")
            self.assertEqual(len(anthropic["calls_raw"]), 8)
            self.assertEqual(
                [item["model"] for item in anthropic["calls_raw"]].count(config.FABLE),
                3,
            )
            self.assertEqual(len(anthropic["notes"]["outputs"]), 5)
            self.assertFalse(any(
                note["safe_to_post"] for note in anthropic["notes"]["outputs"]
            ))

            deepseek_workspace = parent_path / "deepseek"
            deepseek = experiment.run_arm(
                deepseek_workspace,
                arm=experiment.ARM_DEEPSEEK,
                max_cost_usd=0.50,
                anthropic_artifact=anthropic_workspace / "result.json",
            )
            self.assertEqual(deepseek["status"], "COMPLETE")
            self.assertEqual(len(deepseek["calls_raw"]), 23)
            self.assertEqual(
                [item["model"] for item in deepseek["calls_raw"]].count(
                    config.DEEPSEEK_PRO
                ),
                13,
            )
            self.assertEqual(len(deepseek["note_factchecks"]), 5)
            self.assertEqual(deepseek["source_filter"]["substack_rejected"], 0)
            self.assertFalse(deepseek["browser_imported"])
            self.assertTrue(deepseek["routing_unchanged"])

    def test_atomic_checkpoint_survives_transient_windows_file_lock(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            target = pathlib.Path(parent) / "result.partial.json"
            real_replace = experiment.os.replace
            attempts = 0

            def transient_replace(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("transient file lock")
                return real_replace(source, destination)

            with mock.patch.object(
                experiment.os, "replace", side_effect=transient_replace
            ), mock.patch.object(experiment.time, "sleep") as sleep:
                experiment._atomic_json(target, {"status": "checkpoint"})

            self.assertEqual(attempts, 2)
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {"status": "checkpoint"},
            )
            sleep.assert_called_once_with(0.01)


if __name__ == "__main__":
    unittest.main()
