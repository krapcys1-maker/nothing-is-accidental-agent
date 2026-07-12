"""Wspólne fixtury testów — deterministyczne Settings na katalogu tymczasowym."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.models import Account, AccountMode, AutonomyLevel
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


@pytest.fixture
def account() -> Account:
    return make_account(active=True)


@pytest.fixture
def settings(tmp_path: Path, account: Account) -> Settings:
    data_dir = tmp_path / "data"
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
