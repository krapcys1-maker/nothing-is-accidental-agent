"""Złożenie zależności i uruchomienie przepływu tematów (walking skeleton)."""
from __future__ import annotations

from dataclasses import replace

from app.core.clock import SystemClock
from app.core.config import Settings, load_settings
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.base import LLMClient
from app.llm.fake_client import FakeLLMClient
from app.llm.model_router import ModelRouter
from app.llm.usage_tracker import UsageTracker
from app.models import TopicStatus
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import ResearchClient
from app.research.fake_client import FakeResearchClient
from app.storage.repositories import SqliteStorage
from app.workflows.research.docs_writer import make_research_log_writer
from app.workflows.research.pipeline import (
    ResearchRunSummary,
    ensure_topic_can_start_research,
    run_research_pipeline,
)
from app.workflows.topics.discover import TopicRunSummary, run_topic_discovery

DEFAULT_ACCOUNT = "nothing_is_accidental"


def _build_llm(settings: Settings, force_real: bool) -> LLMClient:
    use_real = force_real or not settings.dry_run
    router = ModelRouter(settings)
    if use_real:
        if not settings.anthropic_api_key:
            raise RuntimeError("Brak ANTHROPIC_API_KEY w .env — nie mogę wołać realnego API.")
        return AnthropicLLMClient(settings.anthropic_api_key, router.model_for("topics"))
    # dry_run: klient zastępczy; etykieta modelu z env (jeśli jest), inaczej marker.
    return FakeLLMClient(model=settings.model_fast or "dry-run-fake")


def _build_research_client(settings: Settings, force_real: bool) -> ResearchClient:
    use_real = force_real or not settings.dry_run
    router = ModelRouter(settings)
    if use_real:
        if not settings.anthropic_api_key:
            raise RuntimeError("Brak ANTHROPIC_API_KEY w .env — nie mogę wołać realnego API.")
        return AnthropicResearchClient(
            settings.anthropic_api_key, router.model_for("research"),
            max_retries=settings.research_max_retries,
            timeout_seconds=settings.research_timeout_seconds,
        )
    return FakeResearchClient(scenario="good",
                              model=settings.model_quality or "dry-run-fake-research")


def run_topics(count: int = 6, account_id: str = DEFAULT_ACCOUNT,
               force_real: bool = False, settings: Settings | None = None) -> TopicRunSummary:
    settings = settings or load_settings()
    if force_real:
        settings = replace(settings, dry_run=False)  # realny run: koszt liczony jako realny
    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    account = settings.get_account(account_id)
    storage.ensure_account(account)

    llm = _build_llm(settings, force_real)
    usage_tracker = UsageTracker(settings, storage)
    policy = PolicyEngine(settings, storage, clock)
    notifier = LogNotification()

    return run_topic_discovery(
        account, count,
        settings=settings, storage=storage, llm=llm,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier, clock=clock,
    )


def run_research(topic_id: int | None = None, account_id: str = DEFAULT_ACCOUNT,
                  force_real: bool = False, force_re_research: bool = False,
                  settings: Settings | None = None) -> ResearchRunSummary:
    if force_real:
        # P0-3 (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md): ta ścieżka woła przestarzały,
        # jednoetapowy run_research_pipeline przez klienta zbudowanego BEZ max_web_searches
        # (brak max_uses -> nieograniczona liczba web searchy w jednym wywołaniu) i bez
        # capu kosztu per-run. Wszystkie zabezpieczenia z dwóch incydentów żyją wyłącznie
        # w scripts/run_capped_research.py — tam też należy uruchamiać realny research.
        raise RuntimeError(
            "run_research(force_real=True) / 'python -m app.main run-research --real' jest "
            "zablokowane (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md, P0-3): ta ścieżka nie ma "
            "limitu web searchy (max_uses) ani capu kosztu per-run. Użyj zamiast tego "
            "scripts/run_capped_research.py --topic-id <id> (ma pre-flight, cap kosztu, "
            "--estimate-only)."
        )
    settings = settings or load_settings()
    if force_real:
        settings = replace(settings, dry_run=False)  # realny run: koszt liczony jako realny
    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()

    account = settings.get_account(account_id)
    storage.ensure_account(account)

    # Wybór tematu: po id, albo najlepszy SELECTED z bazy.
    if topic_id is not None:
        topic = next((t for t in storage.list_topics(account.id) if t.id == topic_id), None)
        if topic is None:
            raise RuntimeError(f"Nie znaleziono tematu #{topic_id} dla konta {account.id}.")
    else:
        selected = list(storage.list_topics_by_status(account.id, TopicStatus.SELECTED))
        if not selected:
            raise RuntimeError(
                "Brak tematu SELECTED. Uruchom najpierw: python -m app.main run-topics")
        topic = selected[0]  # list_topics sortuje malejąco po score

    # Bramka musi poprzedzać nawet konstrukcję klienta dry-run — force nie omija
    # kontroli integralności, a bez force nie powstaje żaden klient ani run.
    ensure_topic_can_start_research(storage, account, topic, force_re_research)

    research_client = _build_research_client(settings, force_real)
    usage_tracker = UsageTracker(settings, storage)
    policy = PolicyEngine(settings, storage, clock)
    notifier = LogNotification()
    research_log = make_research_log_writer(settings.project_root / "docs" / "RESEARCH_LOG.md")

    return run_research_pipeline(
        account, topic,
        settings=settings, storage=storage, research_client=research_client,
        usage_tracker=usage_tracker, policy=policy, notifier=notifier,
        clock=clock, research_log=research_log,
        force_re_research=force_re_research,
    )
