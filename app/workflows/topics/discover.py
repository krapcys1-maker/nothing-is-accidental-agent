"""Przepływ: wygeneruj i oceń tematy dla konta.

[POLICY] can_run -> [POLICY] budget -> [LLM] jedno wywołanie -> [scoring wg wag]
-> [POLICY] progi -> [STORAGE] zapis tematów -> [USAGE] koszt. Bez akcji na Substacku.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.ids import new_run_id
from app.llm.base import LLMClient, Usage
from app.llm.usage_tracker import UsageTracker
from app.models import Account, Run, RunStatus, Topic, TopicStatus, WorkflowType
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import NotificationPort
from app.ports.storage import StoragePort
from app.workflows.topics.dedup import TopicDeduplicator


def compute_weighted_score(breakdown: dict[str, float], weights: dict[str, float]) -> float:
    """Suma waga * ocena(0..1); wagi sumują się do 100 -> wynik 0..100."""
    return round(sum(weights.get(k, 0.0) * float(v) for k, v in breakdown.items()), 2)


@dataclass
class TopicRunSummary:
    run_id: str | None
    account_id: str
    dry_run: bool
    model: str = ""
    total: int = 0
    selected: int = 0
    scored: int = 0
    rejected: int = 0
    duplicates: int = 0
    cost_usd: float = 0.0
    blocked: bool = False
    block_code: str | None = None
    block_reason: str | None = None
    topics: list[Topic] = field(default_factory=list)


def run_topic_discovery(
    account: Account,
    count: int,
    *,
    settings: Settings,
    storage: StoragePort,
    llm: LLMClient,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    notifier: NotificationPort,
    clock: Clock | None = None,
) -> TopicRunSummary:
    clock = clock or SystemClock()

    # 1. Bramka: czy w ogóle wolno działać?
    can_run = policy.check_can_run(account)
    if not can_run.allowed:
        notifier.notify("warning", "Workflow zablokowany", can_run.reason, account.id)
        return TopicRunSummary(run_id=None, account_id=account.id, dry_run=settings.dry_run,
                               blocked=True, block_code=can_run.code, block_reason=can_run.reason)

    # 2. Bramka budżetu (pre-estymacja przed wywołaniem).
    pre_estimate = usage_tracker.estimate_cost(Usage(input_tokens=1500, output_tokens=1000))
    budget = policy.check_budget(pre_estimate)
    if not budget.allowed:
        notifier.notify("warning", "Budżet — stop", budget.reason, account.id)
        return TopicRunSummary(run_id=None, account_id=account.id, dry_run=settings.dry_run,
                               blocked=True, block_code=budget.code, block_reason=budget.reason)

    # 3. Run.
    run_id = new_run_id()
    run_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.RUNNING
    storage.create_run(Run(id=run_id, account_id=account.id,
                           workflow=WorkflowType.TOPIC, status=run_status,
                           current_state="discover"))

    # 4. Jedno wywołanie LLM (Fake w dry_run, Anthropic poza dry_run).
    result = llm.generate_and_score_topics(account, count)

    # 5. Koszt.
    usage_row = usage_tracker.record(run_id, result.model, result.usage,
                                     task="topics", dry_run=settings.dry_run)

    # 6. Scoring wg wag + deduplikacja + progi + zapis.
    summary = TopicRunSummary(run_id=run_id, account_id=account.id,
                              dry_run=settings.dry_run, model=result.model,
                              cost_usd=usage_row.estimated_cost_usd)
    dedup = TopicDeduplicator(settings.topic_duplicate_threshold)
    # istniejące tematy konta (aktywne) + tematy dodane w tym runie (dedup wewnątrz batcha)
    existing: list[tuple[int, str]] = list(storage.list_topic_titles_for_dedup(account.id))
    source_label = "fake" if settings.dry_run else "anthropic"

    for idea in result.ideas:
        score = compute_weighted_score(idea.score_breakdown, settings.topic_scoring_weights)
        summary.total += 1

        match = dedup.find_duplicate(idea.title, existing)
        if match is not None:
            topic = storage.add_topic(account.id, Topic(
                account_id=account.id, title=idea.title, question=idea.question,
                score=score, score_breakdown=idea.score_breakdown,
                status=TopicStatus.DUPLICATE, source=source_label,
                duplicate_of=match.existing_id,
                rejection_reason=f"duplicate of topic #{match.existing_id} "
                                 f"('{match.existing_title}') — {match.reason} "
                                 f"(score={match.score})",
            ))
            summary.duplicates += 1
            summary.topics.append(topic)
            continue

        status = policy.decide_topic_status(score)
        topic = storage.add_topic(account.id, Topic(
            account_id=account.id, title=idea.title, question=idea.question,
            score=score, score_breakdown=idea.score_breakdown, status=status,
            source=source_label,
        ))
        existing.append((int(topic.id), topic.title))  # kolejne idee mogą się z tym zdedupować
        summary.topics.append(topic)
        if status == TopicStatus.SELECTED:
            summary.selected += 1
        elif status == TopicStatus.SCORED:
            summary.scored += 1
        else:
            summary.rejected += 1

    # 7. Zamknięcie runu. P0-1 (AUDYT 2026-07-12): terminal statusu sukcesu musi być
    # SUCCESS dla realnych runów — run_status (RUNNING/DRY_RUN) jest poprawny tylko
    # jako stan POCZĄTKOWY (create_run wyżej), nie końcowy.
    terminal_status = RunStatus.DRY_RUN if settings.dry_run else RunStatus.SUCCESS
    storage.finish_run(run_id, terminal_status.value, usage_row.estimated_cost_usd)
    notifier.notify("info", "Workflow tematów zakończony",
                    f"{summary.total} tematów, koszt~{summary.cost_usd:.6f} USD "
                    f"(dry_run={settings.dry_run})", account.id)
    return summary
