"""Offline kontrakty bezpieczeństwa pełnego eksperymentu live."""

from __future__ import annotations

import ast
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
import editorial_live_experiment as experiment  # noqa: E402
import llm  # noqa: E402
import pipeline_replay  # noqa: E402
import style  # noqa: E402
import trafilatura  # noqa: E402


class CompleteFakeTransport(pipeline_replay._FixtureModels):
    """Pełna atrapa transportu; uruchamia prawdziwą orkiestrację harnessu."""

    def __call__(self, purpose, system, user, **kwargs):
        if purpose == "review" and "blind editorial-style evaluator" in system:
            return json.dumps({
                "A": {"scores": {"voice": 3}, "evidence": ["exact A"]},
                "B": {"scores": {"voice": 2}, "evidence": ["exact B"]},
                "winner": "A", "reason": "A is more concrete.",
            })
        if purpose == "revise":
            return json.dumps({
                "title": "The Board Inside the Broken Fixture",
                "subtitle": "A visible failure follows a written route.",
                "body": "\n\n".join(pipeline_replay.EXCERPTS.values()),
                "limits_paragraph_present": True,
                "changes": ["Removed the unsupported accident claim."],
            })
        if purpose == "note":
            text = (
                "Six minutes disappeared from Europe's kitchen clocks. The clocks "
                "were not broken: they counted grid cycles, and a prolonged dip "
                "below 50 hertz made those cycles arrive late. The wall clock was "
                "quietly displaying the condition of an electrical system."
            )
            return json.dumps({
                "note": text, "words": len(text.split()),
                "fact_used": "grid cycles", "source_url": "https://example.invalid",
            })
        if purpose == "factcheck":
            return json.dumps({
                "claims": [{
                    "claim": "Clocks count grid cycles.", "status": "confirmed",
                    "url": "https://www.entsoe.eu/", "what_the_source_says": "confirmed",
                }],
                "safe_to_post": True, "verdict": "The supplied claim is confirmed.",
            })
        return super().__call__(purpose, system, user, **kwargs)


class EditorialLiveExperimentTests(unittest.TestCase):
    def workspace(self, root: pathlib.Path) -> pathlib.Path:
        # Walidator wymaga ścieżki wewnątrz agent-v3. Nazwa nie może istnieć.
        return ROOT / ".live-tests" / root.name

    def good_preflight_patches(self):
        return (
            mock.patch.object(
                capabilities, "current_mode",
                return_value=capabilities.Mode.MODEL_TEST,
            ),
            mock.patch.object(capabilities, "kill_switch_active", return_value=False),
            mock.patch.object(config, "DRY_RUN", False),
            mock.patch.object(config, "CHEAP_MODE", False),
            mock.patch.object(config, "DEEPSEEK_API_KEY", "test-only"),
            mock.patch.object(config, "ANTHROPIC_API_KEY", "test-only"),
        )

    def test_exact_normal_routing_and_budget_math(self) -> None:
        self.assertEqual(
            {purpose: config.MODEL_FOR[purpose] for purpose in experiment.EXPECTED_ROUTING},
            experiment.EXPECTED_ROUTING,
        )
        self.assertEqual(sum(experiment.MAX_CALLS_BY_MODEL.values()), 32)
        self.assertEqual(experiment.MAX_LEDGERED_MODEL_CALLS, 32)
        self.assertLessEqual(
            experiment.HISTORICAL_COST_USD + experiment.LIVE_EXPERIMENT_MAX_USD,
            experiment.USER_GLOBAL_LIMIT_USD,
        )

    def test_real_style_corpus_passes_canonical_pin_on_windows(self) -> None:
        raw = config.STYLE_CORPUS.read_bytes()
        self.assertEqual(style.corpus_sha256(), config.STYLE_CORPUS_SHA256)
        self.assertEqual(len(style.load_examples()), 5)
        canonical = style.canonical_bytes(raw)
        self.assertEqual(
            style.canonical_bytes(canonical.replace(b"\n", b"\r\n")),
            canonical,
        )
        changed = canonical + b"x"
        self.assertNotEqual(
            __import__("hashlib").sha256(changed).hexdigest(),
            config.STYLE_CORPUS_SHA256,
        )

    def test_missing_keys_fail_before_workspace(self) -> None:
        target = ROOT / ".live-tests" / "missing-keys"
        self.assertFalse(target.exists())
        with mock.patch.object(
            capabilities, "current_mode", return_value=capabilities.Mode.MODEL_TEST
        ), mock.patch.object(
            capabilities, "kill_switch_active", return_value=False
        ), mock.patch.object(config, "DRY_RUN", False), mock.patch.object(
            config, "CHEAP_MODE", False
        ), mock.patch.object(config, "DEEPSEEK_API_KEY", ""), mock.patch.object(
            config, "ANTHROPIC_API_KEY", ""
        ):
            with self.assertRaisesRegex(RuntimeError, "brak lokalnych kluczy"):
                experiment.validate_preflight(target)
        self.assertFalse(target.exists())

    def test_wrong_mode_kill_switch_and_existing_workspace_fail(self) -> None:
        target = ROOT / ".live-tests" / "wrong-mode"
        with mock.patch.object(
            capabilities, "current_mode", return_value=capabilities.Mode.FIXTURE
        ):
            with self.assertRaisesRegex(RuntimeError, "MODE=model_test"):
                experiment.validate_preflight(target)

        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            existing = pathlib.Path(temp)
            patches = self.good_preflight_patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                with self.assertRaisesRegex(RuntimeError, "nie może istnieć"):
                    experiment.validate_preflight(existing)

    def test_preflight_accepts_only_new_path_inside_agent_v3(self) -> None:
        target = ROOT / ".live-tests" / "valid-new-path"
        patches = self.good_preflight_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            experiment.validate_preflight(target)
            with self.assertRaisesRegex(RuntimeError, "podkatalogiem agent-v3"):
                experiment.validate_preflight(ROOT.parent / "outside")

    def test_source_has_no_browser_or_platform_mutation_capability(self) -> None:
        source_path = ROOT / "editorial_live_experiment.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("browser", imports)
        self.assertNotIn("substack", imports)
        self.assertEqual(
            experiment.ALLOWED_CAPABILITIES,
            frozenset({
                capabilities.Capability.MODEL_CALL,
                capabilities.Capability.PUBLIC_WEB_READ,
            }),
        )
        for forbidden in (
            "PUBLISH_ARTICLE", "PUBLISH_NOTE", "COMMENT", "REPLY", "RESTACK",
            "FOLLOW", "LIKE", "SESSION_WRITE", "SUBSTACK_READ",
        ):
            self.assertNotIn(f"Capability.{forbidden}", source)

    def test_scout_assessment_measures_stability(self) -> None:
        first = [
            {"title": "The Hidden Rule in a Clock", "question": "Who sets the clock?",
             "nosny": True, "na_artykul": True, "nasycony": False},
            {"title": "A Different Machine", "question": "Why does it stop?",
             "nosny": True, "na_artykul": False, "nasycony": True},
        ]
        second = [
            {"title": "The Hidden Rule in the Clock", "question": "Who sets clocks?",
             "nosny": True, "na_artykul": True, "nasycony": False},
        ]
        assessed = experiment.assess_scout([first, second])
        self.assertTrue(assessed["stability"]["available"])
        # Drugi temat pierwszej próby celowo nie ma odpowiednika, więc średnia
        # ma zachować karę za niestabilność zamiast udawać dopasowanie 1:1.
        self.assertGreater(assessed["stability"]["mean_best_token_jaccard"], 0.4)
        self.assertEqual(assessed["runs"][0]["nasycone"], 1)

    def test_draft_features_include_the_depth_length_contract(self) -> None:
        _question, _evidence, card = experiment._controlled_fixture()
        features = experiment._draft_features(
            {"title": "Short", "subtitle": "", "body": "Far too short."},
            card,
            "RICH",
        )
        self.assertTrue(any(
            item["gate"] == "DLUGOSC_POZA_KONTRAKTEM"
            for item in features["deterministic_findings"]
        ))

    def test_complete_harness_executes_offline_with_fake_transport(self) -> None:
        fake = CompleteFakeTransport()
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            workspace = pathlib.Path(parent) / "new-workspace"
            patches = self.good_preflight_patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                    patches[5], mock.patch.object(llm, "call", side_effect=fake), \
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
                result = experiment.run_experiment(workspace, max_cost_usd=0.50)

            self.assertEqual(
                result["status"], "COMPLETE", result.get("failed_phases"),
            )
            self.assertEqual(len(result["calls_raw"]), 32)
            self.assertTrue((workspace / "result.json").is_file())
            self.assertFalse((workspace / "result.partial.json").exists())
            self.assertEqual(result["natural_chain"]["evidence_documents"], 4)
            self.assertEqual(len(result["notes_forms"]["outputs"]), 5)
            self.assertIn("revision_challenge", result, result["phases"])
            self.assertTrue(
                result["revision_challenge"]["injected_sentence_removed"]
            )
            self.assertFalse(result["browser_imported"])
            self.assertTrue(result["routing_unchanged"])


if __name__ == "__main__":
    unittest.main()
