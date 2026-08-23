"""Pełny, hermetyczny replay normalnej orkiestracji artykułu V3."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pipeline_replay


class LivePreflightTest(unittest.TestCase):
    def valid_context(self):
        return (
            mock.patch.object(
                pipeline_replay.capabilities, "current_mode",
                return_value=pipeline_replay.capabilities.Mode.MODEL_TEST),
            mock.patch.object(
                pipeline_replay.capabilities, "kill_switch_active", return_value=False),
            mock.patch.object(pipeline_replay.config, "DRY_RUN", False),
            mock.patch.object(pipeline_replay.config, "CHEAP_MODE", False),
            mock.patch.object(
                pipeline_replay.config, "DEEPSEEK_API_KEY", "fixture-sentinel"),
            mock.patch.object(
                pipeline_replay.config, "ANTHROPIC_API_KEY", "fixture-sentinel"),
        )

    def test_exact_normal_routing_and_cap_pass_preflight_without_dispatch(self) -> None:
        contexts = self.valid_context()
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
            pipeline_replay.validate_live_preflight(1.50)

    def test_missing_credentials_fail_before_workspace_or_dispatch(self) -> None:
        contexts = self.valid_context()
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], \
                mock.patch.object(pipeline_replay.config, "ANTHROPIC_API_KEY", ""):
            with self.assertRaisesRegex(RuntimeError, "AGENT_V3_ANTHROPIC_API_KEY"):
                pipeline_replay.validate_live_preflight(1.50)

    def test_dry_run_wrong_mode_and_excessive_cap_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "MODE=model_test"):
            pipeline_replay.validate_live_preflight(1.50)

        contexts = self.valid_context()
        with contexts[0], contexts[1], mock.patch.object(
                pipeline_replay.config, "DRY_RUN", True), contexts[3], contexts[4], contexts[5]:
            with self.assertRaisesRegex(RuntimeError, "DRY_RUN=false"):
                pipeline_replay.validate_live_preflight(1.50)

        contexts = self.valid_context()
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
            with self.assertRaisesRegex(RuntimeError, r"\(0, 1\.50\]"):
                pipeline_replay.validate_live_preflight(1.51)

    def test_any_model_override_is_rejected(self) -> None:
        contexts = self.valid_context()
        with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5], \
                mock.patch.dict(
                    pipeline_replay.config.MODEL_FOR,
                    {"write": pipeline_replay.config.DEEPSEEK_PRO}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "routing differs"):
                pipeline_replay.validate_live_preflight(1.50)

    def test_paid_launcher_is_scoped_to_core_models_and_has_no_substack_import(self) -> None:
        source = (pathlib.Path(__file__).parent / "platne" /
                  "test_full_pipeline_live.py").read_text(encoding="utf-8")
        self.assertNotIn("import browser", source)
        self.assertNotIn("MODEL_FOR.update", source)
        self.assertNotIn("MODEL_FOR[", source)
        self.assertIn("base_dispatches\": 8", source)
        self.assertIn("worst_case_dispatches\": 11", source)
        self.assertIn("max_cost_usd", source)


class FullPipelineReplayTest(unittest.TestCase):
    def test_full_pipeline_uses_real_orchestration_and_only_fixture_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = pipeline_replay.run_fixture(pathlib.Path(temp))

        self.assertEqual(result.exit_code, 0, result.stderr + result.stdout)
        self.assertEqual(
            result.purposes,
            [
                "scout", "feasibility", "discovery",
                "classify", "classify", "classify", "classify",
                "synthesis", "warto_pisac", "write", "review", "forma",
            ],
        )
        self.assertEqual(result.requested_capabilities, ["public_web_read"])
        self.assertFalse(result.browser_imported)
        self.assertEqual(result.run_status, ("DONE", "editorial_complete"))
        self.assertEqual(result.article_status, "READY_AUTONOMOUS")
        self.assertEqual(result.call_rows, 0)
        self.assertEqual(result.contract_checks, 12)
        self.assertEqual(result.contract_failures, 0)
        self.assertEqual(result.source_rows, 4)
        self.assertEqual(result.fetched_rows, 4)
        self.assertGreaterEqual(result.document_rows, 4)
        self.assertGreaterEqual(result.fragment_rows, 4)
        self.assertGreaterEqual(result.claim_rows, 4)
        self.assertGreaterEqual(result.sentence_rows, 4)
        self.assertGreaterEqual(result.citation_rows, 4)
        self.assertEqual(len(result.article_files), 1)
        self.assertEqual(result.remote_mutations, 0)

    def test_fixture_failure_is_durable_and_never_falls_through_to_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = pipeline_replay.run_fixture(
                pathlib.Path(temp), fail_purpose="write")

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.run_status, ("FAILED", "write"))
        self.assertIsNone(result.article_status)
        self.assertEqual(result.article_files, [])
        self.assertFalse(result.browser_imported)
        self.assertEqual(result.remote_mutations, 0)
        self.assertIn("fixture failure at write", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
