"""Stage 1 typed worker policy and the two approved Unicode regressions."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import config
from app.core.config import ConfigError, Settings, require_valid_real_provider_pricing
from app.llm.anthropic_client import AnthropicLLMClient


def _minimal_settings() -> Settings:
    return Settings(
        project_root=Path("."), data_dir=Path("data"), db_path=Path("data/agent.db"),
        costs_csv_path=Path("docs/COSTS.csv"), pricing={},
    )


def test_real_pricing_failure_has_exact_polish_unicode_and_no_mojibake():
    with pytest.raises(ConfigError) as caught:
        require_valid_real_provider_pricing(_minimal_settings())
    message = str(caught.value)
    assert "brakujący" in message
    assert "Nie tworzę klienta ani nie wołam API." in message
    assert "brakujÄ" not in message


def test_llm_timeout_failure_has_exact_polish_unicode_and_no_mojibake():
    with pytest.raises(ValueError) as caught:
        AnthropicLLMClient("unused", "unused", timeout_seconds=0)
    assert str(caught.value) == "timeout_seconds musi być skończoną liczbą dodatnią."
    assert "byÄ" not in str(caught.value)


def test_typed_worker_max_attempts_is_loaded_and_invalid_values_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    policy = config_dir / "growth_policy.yaml"
    policy.write_text("worker_policy:\n  default_max_attempts: 2\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("NIA_TEST_MODE", "1")
    assert config.load_settings().worker_default_max_attempts == 2

    policy.write_text("worker_policy:\n  default_max_attempts: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="worker_policy.default_max_attempts"):
        config.load_settings()
