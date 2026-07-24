"""Konfiguracja aplikacji.

Zasady:
- brak ścieżek absolutnych w kodzie — PROJECT_ROOT liczony z położenia pliku,
- nazwy modeli pochodzą z .env (nie z kodu),
- limity i wagi pochodzą z config/growth_policy(.example).yaml,
- konta z config/accounts(.example).yaml,
- sekrety (klucz API) z .env, ładowane przez python-dotenv.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from app.models import Account, AccountMode, AccountPolicy, AutonomyLevel

# app/core/config.py -> parents[0]=core, [1]=app, [2]=root projektu
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    pass


REAL_PROVIDER_PRICING_KEYS = (
    "input_per_mtok",
    "output_per_mtok",
    "cache_read_per_mtok",
    "cache_write_per_mtok",
    "web_search_per_1k",
)


@dataclass
class Settings:
    project_root: Path
    data_dir: Path
    db_path: Path
    costs_csv_path: Path

    # tryb
    dry_run: bool = True
    kill_switch: bool = False

    # budżet
    max_daily_cost_usd: float = 2.00
    max_monthly_cost_usd: float = 40.00
    monthly_limit_has_priority: bool = True

    # modele (z env)
    model_fast: str = ""
    model_quality: str = ""

    # cennik (z env)
    pricing: dict[str, float] = field(default_factory=dict)

    # progi i wagi (z growth_policy)
    article_min_score: float = 75.0
    note_min_score: float = 65.0
    topic_scoring_weights: dict[str, float] = field(default_factory=dict)
    topic_duplicate_threshold: float = 0.72

    # WAVE C4 — offline, provider-independent decision thresholds.
    content_decision_policy_version: str = "content_decision_policy_v1"
    content_article_auto_approve_min_score: float = 0.90
    content_note_auto_approve_min_score: float = 0.85

    # research (z growth_policy.research_policy)
    research_min_sources: int = 3
    research_min_confidence: float = 0.60
    research_min_source_quality: float = 0.50
    research_max_retries: int = 2
    research_timeout_seconds: int = 60

    # Globalna dostępność prawdziwego transportu controlled fetch. To nie jest
    # zgoda na request: każdy request nadal wymaga trwałego, jednorazowego L1.
    # Źródłem jest wyłącznie jawna konfiguracja YAML, nigdy zwykłe ENV.
    controlled_fetch_real_enabled: bool = False

    # Trwała kolejka. Dotyczy wyłącznie bezpiecznych enqueue z composition root
    # aplikacji; durable paid research zachowuje osobny, twardy max_attempts=1.
    worker_default_max_attempts: int = 1

    # growth_policy.editorial_schedule; brak konfiguracji blokuje tylko enqueue CLI.
    editorial_schedule: dict[str, Any] = field(default_factory=dict)

    # sekrety
    anthropic_api_key: str | None = None

    # konta
    accounts: dict[str, Account] = field(default_factory=dict)

    def get_account(self, account_id: str) -> Account:
        acc = self.accounts.get(account_id)
        if acc is None:
            raise ConfigError(f"Nie znaleziono konta o id={account_id!r} w konfiguracji.")
        return acc


def require_valid_real_provider_pricing(settings: Settings) -> None:
    """Fail closed before constructing a paid provider client.

    Dry-run calculations intentionally keep accepting an incomplete price table:
    they are useful offline and must never be confused with permission to make a
    paid call.  A real request, on the other hand, needs every cost component
    that its provider can report, including cache and server-side web search.
    """
    invalid: list[str] = []
    for key in REAL_PROVIDER_PRICING_KEYS:
        value = settings.pricing.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            invalid.append(key)
            continue
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0:
            invalid.append(key)
    if invalid:
        raise ConfigError(
            "Realny provider zablokowany: brakujący, niepoprawny albo niedodatni "
            f"cennik dla: {', '.join(invalid)}. Nie tworzę klienta ani nie wołam API."
        )


def _first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{label} musi być dodatnią liczbą całkowitą.")
    return value


def _unit_interval(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} musi być liczbą z przedziału [0, 1].")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ConfigError(f"{label} musi być skończoną liczbą z przedziału [0, 1].")
    return result


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_accounts(config_dir: Path) -> dict[str, Account]:
    path = _first_existing(config_dir / "accounts.yaml", config_dir / "accounts.example.yaml")
    if path is None:
        return {}
    data = _load_yaml(path)
    accounts: dict[str, Account] = {}
    for raw in data.get("accounts", []):
        policies_raw = raw.get("policies", {}) or {}
        account = Account(
            id=raw["id"],
            display_name=raw.get("display_name", raw["id"]),
            mode=AccountMode(raw.get("mode", "DRAFT_ONLY")),
            autonomy_level=AutonomyLevel(raw.get("autonomy_level", "LEVEL_1")),
            active=bool(raw.get("active", False)),
            niche=list(raw.get("niche", []) or []),
            languages=list(raw.get("languages", ["en"]) or ["en"]),
            browser_profile_path=raw.get("browser_profile_path", ""),
            writing_profile_path=raw.get("writing_profile_path", ""),
            allowed_actions=list(raw.get("allowed_actions", []) or []),
            policies=AccountPolicy(**{k: v for k, v in policies_raw.items()
                                      if k in AccountPolicy.model_fields}),
        )
        accounts[account.id] = account
    return accounts


def load_settings() -> Settings:
    """Buduje Settings z .env + config/*.yaml. Nie tworzy plików."""
    if not os.environ.get("NIA_TEST_MODE"):
        load_dotenv(PROJECT_ROOT / ".env")

    config_dir = PROJECT_ROOT / "config"
    gp_path = _first_existing(
        config_dir / "growth_policy.yaml", config_dir / "growth_policy.example.yaml"
    )
    growth = _load_yaml(gp_path) if gp_path else {}
    limits = growth.get("global_limits", {}) or {}
    topic_policy = growth.get("topic_policy", {}) or {}
    weights = growth.get("topic_scoring_weights", {}) or {}
    research_policy = growth.get("research_policy", {}) or {}
    controlled_fetch_policy = growth.get("controlled_fetch_policy", {}) or {}
    if not isinstance(controlled_fetch_policy, dict):
        raise ConfigError("controlled_fetch_policy musi być mapą konfiguracji.")
    controlled_fetch_real_enabled = controlled_fetch_policy.get(
        "real_transport_enabled", False,
    )
    if not isinstance(controlled_fetch_real_enabled, bool):
        raise ConfigError(
            "controlled_fetch_policy.real_transport_enabled musi być boolean."
        )
    worker_policy = growth.get("worker_policy", {}) or {}
    if not isinstance(worker_policy, dict):
        raise ConfigError("worker_policy musi być mapą konfiguracji.")
    editorial_schedule = growth.get("editorial_schedule", {}) or {}
    if not isinstance(editorial_schedule, dict):
        raise ConfigError("editorial_schedule musi być mapą konfiguracji.")
    content_decision_policy = growth.get("content_decision_policy", {}) or {}
    if not isinstance(content_decision_policy, dict):
        raise ConfigError("content_decision_policy musi być mapą konfiguracji.")
    content_decision_policy_version = content_decision_policy.get(
        "version", "content_decision_policy_v1",
    )
    if (
        not isinstance(content_decision_policy_version, str)
        or not content_decision_policy_version.strip()
        or len(content_decision_policy_version) > 100
    ):
        raise ConfigError("content_decision_policy.version musi być niepustym tekstem.")

    data_dir = PROJECT_ROOT / "data"

    pricing = {
        "input_per_mtok": float(os.getenv("PRICE_INPUT_USD_PER_MTOK", "0") or 0),
        "output_per_mtok": float(os.getenv("PRICE_OUTPUT_USD_PER_MTOK", "0") or 0),
        "cache_read_per_mtok": float(os.getenv("PRICE_CACHE_READ_USD_PER_MTOK", "0") or 0),
        "cache_write_per_mtok": float(os.getenv("PRICE_CACHE_WRITE_USD_PER_MTOK", "0") or 0),
        "web_search_per_1k": float(os.getenv("PRICE_WEB_SEARCH_USD_PER_1K", "0") or 0),
    }

    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        db_path=data_dir / "agent.db",
        costs_csv_path=PROJECT_ROOT / "docs" / "COSTS.csv",
        dry_run=_as_bool(os.getenv("DRY_RUN"), bool(limits.get("dry_run", True))),
        kill_switch=_as_bool(os.getenv("KILL_SWITCH"), bool(limits.get("kill_switch", False))),
        max_daily_cost_usd=float(limits.get("max_daily_cost_usd", 2.00)),
        max_monthly_cost_usd=float(limits.get("max_monthly_cost_usd", 40.00)),
        monthly_limit_has_priority=bool(limits.get("monthly_limit_has_priority", True)),
        model_fast=os.getenv("ANTHROPIC_MODEL_FAST", "") or "",
        model_quality=os.getenv("ANTHROPIC_MODEL_QUALITY", "") or "",
        pricing=pricing,
        article_min_score=float(topic_policy.get("article_min_score", 75)),
        note_min_score=float(topic_policy.get("note_min_score", 65)),
        topic_scoring_weights={k: float(v) for k, v in weights.items()},
        topic_duplicate_threshold=float(
            topic_policy.get("duplicate_title_similarity_threshold", 0.72)),
        content_decision_policy_version=content_decision_policy_version.strip(),
        content_article_auto_approve_min_score=_unit_interval(
            content_decision_policy.get("article_auto_approve_min_score", 0.90),
            label="content_decision_policy.article_auto_approve_min_score",
        ),
        content_note_auto_approve_min_score=_unit_interval(
            content_decision_policy.get("note_auto_approve_min_score", 0.85),
            label="content_decision_policy.note_auto_approve_min_score",
        ),
        research_min_sources=int(research_policy.get("minimum_sources", 3)),
        research_min_confidence=float(research_policy.get("min_confidence_score", 0.60)),
        research_min_source_quality=float(research_policy.get("min_source_quality_score", 0.50)),
        research_max_retries=int(research_policy.get("max_retries", 2)),
        research_timeout_seconds=int(research_policy.get("timeout_seconds", 60)),
        controlled_fetch_real_enabled=controlled_fetch_real_enabled,
        worker_default_max_attempts=_positive_int(
            worker_policy.get("default_max_attempts", 1),
            label="worker_policy.default_max_attempts",
        ),
        editorial_schedule=dict(editorial_schedule),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        accounts=_load_accounts(config_dir),
    )
