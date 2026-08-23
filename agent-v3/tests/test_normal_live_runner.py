"""Offline kontrakty uprzęży normalnego segmentowego testu live."""

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
import normal_live_runner as runner  # noqa: E402
import pipeline_replay  # noqa: E402
import run  # noqa: E402


class NormalLiveRunnerTests(unittest.TestCase):
    def patches(self):
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

    @staticmethod
    def artifact(path: pathlib.Path) -> pathlib.Path:
        topic = {
            "title": "The Board Hidden Inside a Fixture Record",
            "question": "Who decides what happens after a fixture fails?",
            "kind": "BROKEN_BELIEF",
            "already_written": [],
            "scale": "AN_INDUSTRY",
            "precedents": [{
                "when": "1998",
                "what_happened": "the written route was used",
                "what_changed": "the responsible body became visible",
            }, {
                "when": "2007",
                "what_happened": "a second public failure stopped normal operations",
                "what_changed": "the escalation sequence was formally rewritten",
            }],
            "threads": ["inspection", "custody", "final decision", "appeal", "incentives"],
            "article_routes": [
                f"How this system creates a separate institutional question number {route}"
                for route in range(20)
            ],
            "broken_belief": "Everyone assumes the first observer decides.",
            "why_they_believe_it": "The route is invisible.",
            "nosny": True,
            "nasycony": False,
            "na_artykul": True,
            "nosny": True,
            "pozycja": 1,
            "ile_watkow": 3,
            "ile_drog_artykulowych": 20,
            "pole_redakcyjne": True,
        }
        value = [dict(topic, title=f"Fixture topic {index}") for index in range(6)]
        path.write_text(json.dumps({
            "phases": {
                "scout_replication_1": {"status": "PASS", "value": value}
            }
        }), encoding="utf-8")
        return path

    def test_preflight_rejects_routing_override_and_outside_workspace(self) -> None:
        patches = self.patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with self.assertRaisesRegex(runner.LiveRunnerError, "podkatalogiem"):
                runner.validate_preflight(
                    ROOT.parent / "outside", stage_cap_usd=0.1,
                    require_existing=False,
                )
            with mock.patch.dict(
                config.MODEL_FOR, {"write": config.DEEPSEEK_PRO}, clear=False,
            ), self.assertRaisesRegex(runner.LiveRunnerError, "routing"):
                runner.validate_preflight(
                    ROOT / ".live-tests" / "new", stage_cap_usd=0.1,
                    require_existing=False,
                )

    def test_seeded_real_run_main_reaches_live_feasibility_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            root = pathlib.Path(parent)
            workspace = root / "experiment"
            artifact = self.artifact(root / "scout.json")
            patches = self.patches()
            fake = pipeline_replay._FixtureModels()
            def traced_fake(purpose, system, user, **kwargs):
                response = fake(purpose, system, user, **kwargs)
                trace = kwargs.get("collect_trace")
                if purpose == "discovery" and isinstance(trace, list):
                    trace.extend([
                        {
                            "request_kind": "web_search", "system": system,
                            "user": user, "response": "draft",
                        },
                        {
                            "request_kind": "exact_url_selector",
                            "system": system, "user": "selector",
                            "response": response,
                        },
                    ])
                return response
            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                    patches[5], mock.patch.object(
                        runner.llm, "call", side_effect=traced_fake,
                    ):
                manifest = runner.seed_scout(workspace, artifact)
                result = runner.run_article_segment(
                    workspace, "feasibility", stage_cap_usd=0.10,
                )
                discovery_result = runner.run_article_segment(
                    workspace, "discovery", stage_cap_usd=0.30,
                )

            self.assertEqual(manifest["topic_count"], 6)
            self.assertTrue(result["pass"], result)
            self.assertEqual(result["actual_logical_calls"], {"feasibility": 1})
            self.assertEqual(result["requested_capabilities"], [])
            self.assertFalse(result["browser_imported"])
            self.assertFalse(result["substack_requested"])
            self.assertTrue(result["routing_unchanged"])
            captures = json.loads(
                (workspace / "model-captures.json").read_text(encoding="utf-8")
            )
            self.assertEqual(captures[0]["purpose"], "feasibility")
            self.assertIn("system", captures[0])
            self.assertIn("response", captures[0])
            self.assertTrue(discovery_result["pass"], discovery_result)
            self.assertEqual(captures[1]["purpose"], "discovery")
            self.assertEqual(captures[1]["search_result_urls"],
                             list(pipeline_replay.URLS))
            self.assertEqual(captures[1]["search_result_url_count"],
                             len(pipeline_replay.URLS))
            self.assertEqual(captures[1]["provider_request_count"], 2)
            self.assertEqual(discovery_result["provider_request_count"], 2)
            self.assertIn("response_sha256",
                          captures[1]["provider_trace"][0])

    def test_seed_accepts_exact_raw_capture_and_replays_current_scout(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            root = pathlib.Path(parent)
            workspace = root / "experiment"
            raw = pipeline_replay._FixtureModels()(
                "scout", "system", "Propose exactly 6 final topics"
            )
            capture = root / "model-captures.json"
            capture.write_text(json.dumps([{
                "purpose": "scout", "response": raw, "error": None,
            }]), encoding="utf-8")
            patches = self.patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                    patches[5]:
                manifest = runner.seed_scout(workspace, capture)

            self.assertEqual(manifest["scout_source_kind"],
                             "exact_raw_capture_replay")
            self.assertEqual(manifest["topic_count"], 6)
            self.assertEqual(manifest["topic_titles"][0],
                             "The Board Hidden Inside a Fixture Record 1")

    def test_source_has_no_browser_or_substack_capability(self) -> None:
        source = (ROOT / "normal_live_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("import browser", source)
        for forbidden in (
            "SUBSTACK_READ", "SESSION_WRITE", "PUBLISH_ARTICLE", "PUBLISH_NOTE",
            "COMMENT", "REPLY", "RESTACK", "LIKE", "FOLLOW",
        ):
            self.assertNotIn(f"Capability.{forbidden}", source)

    def test_scout_cache_does_not_depend_on_feasibility_prompt(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            prompts = pathlib.Path(temp)
            (prompts / "skaut.md").write_text("scout", encoding="utf-8")
            feasibility_path = prompts / "wykonalnosc.md"
            feasibility_path.write_text("feasibility v1", encoding="utf-8")
            with mock.patch.object(run.config, "PROMPTS_DIR", prompts):
                scout_before = run._prompt_fingerprint("scout")
                feasibility_before = run._prompt_fingerprint("feasibility")
                feasibility_path.write_text("feasibility v2", encoding="utf-8")
                self.assertEqual(run._prompt_fingerprint("scout"), scout_before)
                self.assertNotEqual(
                    run._prompt_fingerprint("feasibility"), feasibility_before
                )

    @staticmethod
    def live_scout_payload() -> str:
        topics = []
        for index in range(6):
            topics.append({
                "title": f"Universe {index}",
                "central_question": (
                    f"What changes when a familiar premise {index} stops shaping choices?"
                ),
                "mode": "COUNTERFACTUAL" if index % 2 else "CULTURAL_CONFLICT",
                "why_fascinating": (
                    "Each answer changes several other questions and creates opposing outcomes."
                ),
                "reader_entry_point": "A reader must choose what to trust after change arrives.",
                "obvious_coverage": ["the standard headline treatment"],
                "underexplored_connections": [
                    f"Connection {n} changes who carries risk after the premise disappears"
                    for n in range(3)
                ],
                "dimensions": [{
                    "name": f"dimension {n}",
                    "question_opened": f"What separate question does dimension {n} create?",
                    "why_independent": f"Its conclusion survives after dimension {n + 1} is answered.",
                } for n in range(3)],
                "tensions": [{
                    "force_a": f"pressure toward adaptation {n}",
                    "force_b": f"pressure toward preservation {n}",
                    "why_unresolved": f"Both forces reward different actors over timescale {n}.",
                } for n in range(2)],
                "open_branches": [{
                    "possibility": f"A separate outcome develops through branch {n}",
                    "logic": f"Feedback {n} rewards a different response.",
                    "what_would_change_our_mind": f"Observed behaviour contradicts feedback {n}.",
                } for n in range(3)],
                "article_routes": [{
                    "question": f"How would route {n} change a separate consequence of this premise?",
                    "distinct_engine": f"mechanism number {n} changes incentives differently",
                    "evidence_needed": f"evidence family {n} from a separate historical record",
                } for n in range(6)],
                "note_test": {
                    "can_be_exhausted_in_three_sentences": False,
                    "why": "Different evidence can support incompatible conclusions.",
                },
                "fatal_weakness": "The branches may share one hidden premise that research refutes.",
            })
        return json.dumps({
            "discarded_seeds": [{
                "title": "Small procedural fact",
                "rejection": "One short answer would exhaust all useful branches of this seed.",
            }],
            "topics": topics,
            "ranking": {
                "largest_article_universe": [0, 1, 2],
                "most_compelling": [1, 2, 3],
                "most_original_angle": [2, 3, 4],
                "most_likely_to_collapse": [3, 4, 5],
            },
        })

    def test_scout_live_is_one_call_only_and_has_four_cent_cap(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            workspace = pathlib.Path(parent) / "scout-live"
            patches = self.patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                    patches[5], mock.patch.object(
                        runner.llm, "call", return_value=self.live_scout_payload(),
                    ), mock.patch.dict(config.MAX_TOKENS, {"scout": 100}):
                result = runner.run_scout_live(
                    workspace, stage_cap_usd=0.01,
                )
            self.assertTrue(result["pass"], result)
            self.assertEqual(result["actual_logical_calls"], {"scout": 1})
            self.assertEqual(len(result["topics"]), 6)
            self.assertEqual(result["requested_capabilities"], [])
            self.assertFalse(result["substack_requested"])
            self.assertTrue((workspace / "model-captures.json").is_file())

        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            workspace = pathlib.Path(parent) / "too-expensive"
            with self.assertRaisesRegex(runner.LiveRunnerError, "twardy cap"):
                runner.run_scout_live(workspace, stage_cap_usd=0.041)

        with tempfile.TemporaryDirectory(dir=ROOT) as parent:
            workspace = pathlib.Path(parent) / "ceiling-costs-more-than-cap"
            patches = self.patches()
            fake_call = mock.Mock(return_value=self.live_scout_payload())
            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                    patches[5], mock.patch.object(runner.llm, "call", fake_call):
                result = runner.run_scout_live(workspace, stage_cap_usd=0.04)
            self.assertFalse(result["pass"])
            self.assertIn("odmowa przed dispatch", result["execution_error"])
            fake_call.assert_not_called()
            self.assertEqual(result["new_call_rows"], [])

    def test_discovery_worst_case_includes_url_selection_fallback(self) -> None:
        system = "source selector"
        user = "find public records"
        one_request = runner._deepseek_worst_case_usd(
            "discovery", system, user, web_search=False
        )
        with_fallback = runner._deepseek_worst_case_usd(
            "discovery", system, user, web_search=True
        )
        self.assertGreater(with_fallback, one_request * 2)
        self.assertLess(with_fallback, 0.30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
