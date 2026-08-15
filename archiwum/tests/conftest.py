"""Wspólne fixtury testów — deterministyczne Settings na katalogu tymczasowym."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.testing.safety_kernel import activate


# ``sitecustomize`` applies this before collection and subprocesses inherit it.
# The idempotent call keeps direct/constrained pytest launchers fail-closed too.
activate()

from app.core.config import Settings
from app.models import Account, AccountMode, AutonomyLevel, Job, JobKind
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage

STANDARD_WEIGHTS = {
    "curiosity": 25.0,
    "source_quality": 20.0,
    "non_obvious": 15.0,
    "universality": 15.0,
    "discussion_potential": 10.0,
    "visual_potential": 10.0,
    "originality": 5.0,
}


def write_approved_pricing_profile(
    project_root: Path, *, model: str, profile_id: str = "test-approved-profile",
    version: str = "test-2026-01-01", status: str = "approved",
    prices: dict | None = None,
) -> tuple[str, Path]:
    """Write an authoritative pricing_profiles.yaml under a temp project root (LA-01-A).

    Offline helper only: real prices stay the owner's responsibility. Values here
    are deterministic test placeholders written into ``tmp_path`` config.
    """
    import yaml

    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "pricing_profiles.yaml"
    resolved_prices = prices if prices is not None else {
        "input_per_mtok": 3.0, "output_per_mtok": 15.0, "cache_read_per_mtok": 0.3,
        "cache_write_per_mtok": 3.75, "web_search_per_1k": 10.0,
    }
    document = {"version": 1, "profiles": [{
        "profile_id": profile_id, "version": version, "model": model,
        "currency": "USD", "unit": "usd_per_mtok__web_search_per_1k",
        "status": status, "approved_by": "test-owner", "prices": resolved_prices,
    }]}
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return profile_id, path


def make_account(active: bool = True) -> Account:
    return Account(
        id="nothing_is_accidental",
        display_name="Nothing Is Accidental",
        mode=AccountMode.FULL_PUBLICATION,
        autonomy_level=AutonomyLevel.LEVEL_1,
        active=active,
        niche=["hidden systems", "everyday economics"],
        languages=["en"],
        browser_profile_path="./data/browser-profiles/nothing_is_accidental",
        writing_profile_path="./config/prompts/nothing_is_accidental.md",
        allowed_actions=["research", "draft_article", "draft_note"],
    )


def seed_historical_real_usage(storage: SqliteStorage, usage):
    """Creates test spend through the same durable relation as new real usage.

    Despite its retained name, this fixture no longer writes migration-only
    legacy rows.  0012 deliberately makes that impossible after migration.
    For real test usage it builds a completed synthetic request->job->run
    relation, then uses the public storage API.  Dry-run fixtures remain dry.
    """
    if usage.dry_run:
        return storage.add_model_usage(usage)

    run = storage.get_run(usage.run_id)
    if run is None:
        raise AssertionError(f"Test usage requires existing run {usage.run_id!r}.")
    token = uuid4().hex
    job = storage.enqueue_job(Job(
        id=f"test-ledger-{token}", account_id=run.account_id, kind=JobKind.LOCAL,
        workflow=run.workflow, idempotency_key=f"test-ledger-{token}", run_id=run.id,
        payload={"test_fixture": "durable_usage"}, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=usage.created_at, max_attempts=1, created_at=usage.created_at,
    ))
    request_id = f"{job.id}:research:1"
    timestamp = usage.created_at.strftime("%Y-%m-%d %H:%M:%S")
    reserved_amount = max(float(usage.estimated_cost_usd), 0.000001)
    storage.conn.execute(
        "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
        "reserved_amount_usd,reserved_at) VALUES (?,?,?,?,?,?,?)",
        (job.id, "research", 1, request_id, "RESERVED", reserved_amount, timestamp),
    )
    storage.conn.execute(
        "UPDATE provider_attempts SET status='REQUEST_STARTED',request_started_at=? "
        "WHERE request_id=?", (timestamp, request_id),
    )
    storage.conn.commit()
    usage.request_id = request_id
    stored = storage.add_model_usage(usage)
    storage.conn.execute(
        "UPDATE provider_attempts SET status='SETTLED',settled_at=?,actual_cost_usd=? "
        "WHERE request_id=?",
        (timestamp, float(usage.estimated_cost_usd), request_id),
    )
    storage.conn.commit()
    return stored


@pytest.fixture
def account() -> Account:
    return make_account(active=True)


@pytest.fixture
def settings(tmp_path: Path, account: Account) -> Settings:
    data_dir = tmp_path / "data"
    initialize_database(data_dir / "agent.db")
    return Settings(
        project_root=tmp_path,
        data_dir=data_dir,
        db_path=data_dir / "agent.db",
        costs_csv_path=tmp_path / "COSTS.csv",
        dry_run=True,
        kill_switch=False,
        max_daily_cost_usd=2.00,
        max_monthly_cost_usd=40.00,
        monthly_limit_has_priority=True,
        model_fast="dry-run-fake",
        model_quality="dry-run-fake",
        pricing={
            "input_per_mtok": 3.0,
            "output_per_mtok": 15.0,
            "cache_read_per_mtok": 0.0,
            "cache_write_per_mtok": 0.0,
            "web_search_per_1k": 0.0,
        },
        article_min_score=75.0,
        note_min_score=65.0,
        topic_scoring_weights=dict(STANDARD_WEIGHTS),
        anthropic_api_key=None,
        accounts={account.id: account},
    )


@pytest.fixture
def storage(settings: Settings) -> SqliteStorage:
    store = SqliteStorage.open(settings.db_path)
    yield store
    store.close()
