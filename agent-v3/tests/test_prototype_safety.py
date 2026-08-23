"""Hermetyczne kontrdowody dla izolacji prototypu Agent V3.

Test nie otwiera gniazd, przeglądarki ani bazy projektu. Nie wywołuje modeli.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
AGENT = REPO / "agent-v3"
sys.path.insert(0, str(AGENT))

# Import testu jest zawsze fixture, niezależnie od powłoki uruchamiającej.
os.environ["AGENT_V3_MODE"] = "fixture"
os.environ["AGENT_V3_KILL_SWITCH"] = "1"
os.environ["AGENT_V3_DRY_RUN"] = "1"

import browser
import capabilities


POLICY_ENV = (
    "AGENT_V3_MODE",
    "AGENT_V3_KILL_SWITCH",
    "AGENT_V3_DRY_RUN",
    "AGENT_V3_TEST_ACCOUNT_HANDLE",
    "AGENT_V3_SUBSTACK_HANDLE",
    "AGENT_V3_LIVE_TEST_CONFIRM",
)


class PrototypeCapabilitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = {key: os.environ.get(key) for key in POLICY_ENV}
        for key in POLICY_ENV:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _mode(self, mode: str, *, target: str = "nia-v3-sandbox",
              confirm: bool = False) -> None:
        os.environ["AGENT_V3_MODE"] = mode
        os.environ["AGENT_V3_KILL_SWITCH"] = "0"
        os.environ["AGENT_V3_TEST_ACCOUNT_HANDLE"] = target
        os.environ["AGENT_V3_SUBSTACK_HANDLE"] = target
        if confirm:
            os.environ["AGENT_V3_LIVE_TEST_CONFIRM"] = (
                capabilities.LIVE_TEST_CONFIRMATION
            )

    def test_default_fixture_denies_every_external_capability(self) -> None:
        self.assertEqual(capabilities.current_mode(), capabilities.Mode.FIXTURE)
        self.assertTrue(capabilities.kill_switch_active())
        for capability in capabilities.Capability:
            with self.subTest(capability=capability.value):
                with self.assertRaises(capabilities.CapabilityDenied):
                    capabilities.require(capability)

    def test_model_test_allows_only_model_and_public_read(self) -> None:
        self._mode("model_test")
        capabilities.require(capabilities.Capability.MODEL_CALL)
        capabilities.require(capabilities.Capability.PUBLIC_WEB_READ)
        for denied in (
            capabilities.Capability.SUBSTACK_READ,
            capabilities.Capability.PUBLISH_NOTE,
            capabilities.Capability.ALERT_SEND,
        ):
            with self.assertRaises(capabilities.CapabilityDenied):
                capabilities.require(denied)

    def test_live_read_only_cannot_mutate(self) -> None:
        self._mode("live_read_only")
        capabilities.require(capabilities.Capability.SUBSTACK_READ)
        for mutation in capabilities.MUTATIONS:
            with self.subTest(mutation=mutation.value):
                with self.assertRaises(capabilities.CapabilityDenied):
                    capabilities.require(mutation)

    def test_live_test_allows_mutations_only_with_full_contract(self) -> None:
        self._mode("live_test", confirm=True)
        for mutation in capabilities.MUTATIONS:
            with self.subTest(mutation=mutation.value):
                capabilities.require(mutation)
        capabilities.require(capabilities.Capability.SESSION_WRITE)
        capabilities.require(capabilities.Capability.ALERT_SEND)

    def test_live_test_without_confirmation_is_denied(self) -> None:
        self._mode("live_test")
        with self.assertRaises(capabilities.CapabilityDenied):
            capabilities.require(capabilities.Capability.PUBLISH_NOTE)

    def test_live_test_requires_prototype_marker(self) -> None:
        self._mode("live_test", confirm=True)
        old_marker = capabilities.PROTOTYPE_MARKER
        try:
            capabilities.PROTOTYPE_MARKER = AGENT / "missing-prototype-marker"
            with self.assertRaises(capabilities.CapabilityDenied):
                capabilities.require(capabilities.Capability.PUBLISH_NOTE)
        finally:
            capabilities.PROTOTYPE_MARKER = old_marker

    def test_production_target_is_unconditionally_denied(self) -> None:
        self._mode("live_test", target=capabilities.PRODUCTION_HANDLE, confirm=True)
        for mutation in capabilities.MUTATIONS:
            with self.subTest(mutation=mutation.value):
                with self.assertRaises(capabilities.CapabilityDenied):
                    capabilities.require(mutation)

    def test_runtime_account_must_match_test_target(self) -> None:
        self._mode("live_test", confirm=True)
        capabilities.assert_runtime_account("nia-v3-sandbox")
        with self.assertRaises(capabilities.CapabilityDenied):
            capabilities.assert_runtime_account("different-account")

    def test_kill_switch_is_dynamic(self) -> None:
        self._mode("model_test")
        capabilities.require(capabilities.Capability.MODEL_CALL)
        os.environ["AGENT_V3_KILL_SWITCH"] = "1"
        with self.assertRaises(capabilities.CapabilityDenied):
            capabilities.require(capabilities.Capability.MODEL_CALL)


class LocalPreviewTest(unittest.TestCase):
    def test_every_mutating_entrypoint_stops_before_browser(self) -> None:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("próba uruchomienia sesji lub przeglądarki")

        old_connect = browser.podlacz_sie
        old_session = browser.wymagaj_sesji
        browser.podlacz_sie = forbidden
        browser.wymagaj_sesji = forbidden
        try:
            with tempfile.TemporaryDirectory() as temp:
                article = Path(temp) / "article.md"
                article.write_text(
                    "# Test title\n\n*Test subtitle*\n\nLocal body.",
                    encoding="utf-8",
                )
                results = [
                    browser.polub_w_kanale(1, wyslij=False),
                    browser.obserwuj_profil("reader", wyslij=False),
                    browser.zasubskrybuj("reader", wyslij=False),
                    browser.ustaw_oswiadczenie_ai(wyslij=False),
                    browser.wystaw_odpowiedz_pod_artykulem(
                        "https://example.test/post", "reader", "reply",
                        wyslij=False,
                    ),
                    browser.wystaw_artykul(article, wyslij=False),
                    browser.wystaw_odpowiedz(123, "reply", wyslij=False),
                    browser.wystaw_notke("note", wyslij=False),
                    browser.wystaw_komentarz(
                        "https://example.test/post", "comment", wyslij=False,
                    ),
                    browser.restackuj_w_kanale(
                        1, lambda _note: {"restack": True, "sentence": "x"},
                        wyslij=False,
                    ),
                ]
        finally:
            browser.podlacz_sie = old_connect
            browser.wymagaj_sesji = old_session

        self.assertEqual(len(results), 10)
        self.assertTrue(all(item.get("preview_only") for item in results))
        self.assertTrue(all(not item.get("wyslane", False) for item in results))
        self.assertTrue(all(not item.get("zrobione", False) for item in results))


class SecretIsolationTest(unittest.TestCase):
    def _config_probe(self, mode: str) -> dict[str, object]:
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("AGENT_V3_") or key in {
                "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
            }:
                env.pop(key, None)
        env.update({
            "AGENT_V3_MODE": mode,
            "AGENT_V3_ANTHROPIC_API_KEY": "V3_SENTINEL",
            "ANTHROPIC_API_KEY": "PRODUCTION_SENTINEL",
            "AGENT_V3_TEST_ACCOUNT_HANDLE": "nia-v3-sandbox",
            "AGENT_V3_SUBSTACK_HANDLE": "nia-v3-sandbox",
            "PYTHONPATH": str(AGENT),
        })
        code = (
            "import json, config; "
            "print(json.dumps({"
            "'v3': config.ANTHROPIC_API_KEY == 'V3_SENTINEL', "
            "'empty': config.ANTHROPIC_API_KEY == '', "
            "'mode': config.BOOT_MODE, "
            "'session_under_v3': str(config.SESSION_FILE).startswith(str(config.DATA_DIR)), "
            "'session_name': config.SESSION_FILE.name"
            "}))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return json.loads(completed.stdout)

    def test_fixture_does_not_read_even_namespaced_secret(self) -> None:
        result = self._config_probe("fixture")
        self.assertTrue(result["empty"])
        self.assertFalse(result["v3"])
        self.assertEqual(result["mode"], "fixture")

    def test_model_mode_reads_only_namespaced_secret(self) -> None:
        result = self._config_probe("model_test")
        self.assertTrue(result["v3"])
        self.assertFalse(result["empty"])
        self.assertEqual(result["mode"], "model_test")
        self.assertTrue(result["session_under_v3"])
        self.assertIn("nia-v3-sandbox", result["session_name"])


class ExecutableIsolationTest(unittest.TestCase):
    def test_v3_executables_do_not_reference_v2(self) -> None:
        files = [
            AGENT / "config.py",
            AGENT / "browser.py",
            AGENT / "alarm.py",
            AGENT / "pomiary" / "korpus_fedreg.py",
            AGENT / "kopia_subskrybentow.py",
            AGENT / "uruchom-dzien.cmd",
            AGENT / "wdroz.sh",
            *(AGENT / "systemd").glob("*.service"),
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("agent-v2", text)
                self.assertNotIn("AGENT_V2", text)

    def test_deployment_artifacts_are_inert(self) -> None:
        deployment = (AGENT / "wdroz.sh").read_text(encoding="utf-8")
        self.assertIn("exit 64", deployment)
        self.assertNotIn("git ", deployment)
        self.assertNotIn("systemctl", deployment)
        for service in (AGENT / "systemd").glob("*.service"):
            text = service.read_text(encoding="utf-8")
            with self.subTest(service=service.name):
                self.assertIn("ExecStart=/usr/bin/false", text)
                self.assertNotIn("--wyslij", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
