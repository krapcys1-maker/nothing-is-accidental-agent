"""Offline WAVE 1A tests for the manual durable reconciliation resolver."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.core.clock import FixedClock
from app.core.config import ConfigError, REAL_PROVIDER_PRICING_KEYS
from app.models import (
    ExecutionResolution, FinancialResolution, Job, JobExecutionContext, JobKind,
    JobStatus, ModelUsage, ProviderAttemptStatus, ReconciliationEvent,
    ReconciliationEventType, ReconciliationFaultPoint, ResearchCard, RunStatus,
    Topic, TopicStatus, WorkflowType,
)
from app.ports.storage import (
    BudgetReservationError,
    ProviderAttemptReconciliationError,
    ProviderAttemptReconciliationRequired,
    ReconciliationPreviewStaleError,
    StaleJobExecutionError,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect
from app.storage.repositories import SqliteStorage, _STALE_RUN_REAPER_REASON
from app.main import main


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def _execution(storage, account, suffix: str) -> JobExecutionContext:
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title=f"Reconcile {suffix}", question="Why?", score=90,
        status=TopicStatus.SELECTED,
    ))
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="reconciliation-model", research_timeout_seconds=60,
        ),
        account_id=account.id, topic_id=int(topic.id), cap_usd=0.2,
        max_web_searches=1, question="Why?", niche=account.niche,
    )
    job = storage.enqueue_job(Job(
        id=f"reconcile-job-{suffix}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"reconcile-key-{suffix}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW,
        max_attempts=1, payload={
            "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
            "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
    ))
    lease = storage.claim_next_job(f"resolver-{suffix}", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(job.id, lease.lease_owner, f"reconcile-run-{suffix}", now=NOW)
    return JobExecutionContext(job_id=job.id, lease_owner=lease.lease_owner, run_id=initialized.run.id, clock=FixedClock(NOW))


def _needs_reconciliation(storage, account, suffix: str) -> tuple[JobExecutionContext, str]:
    execution = _execution(storage, account, suffix)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.mark_provider_attempt_needs_reconciliation(execution, attempt.request_id, error_code="UNKNOWN")
    storage.mark_job_needs_verification(execution.job_id, execution.lease_owner, "UNKNOWN", now=NOW)
    return execution, attempt.request_id


def _extract_token(preview_output: str) -> str:
    for line in preview_output.splitlines():
        if line.startswith("version_token="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("preview did not print a version_token")


def _preview_token(storage, request_id: str, account_id: str) -> str:
    return storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account_id,
    ).version_token


def test_charged_known_is_atomic_idempotent_and_uses_model_usage(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "charged")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.0123455", reconciled_by="operator-1", note="Provider invoice verified.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert result.usage_id is not None
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 1
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert storage.get_run(execution.run_id).status.value == "FAILED"
    assert storage.get_research_run(execution.run_id).status.value == "FAILED"
    same = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.012346", reconciled_by="operator-1", note="Provider invoice verified.",
    )
    assert same.idempotent is True
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator-1", note="Different decision.",
        )


def test_not_charged_execution_failed_releases_attempt_and_fails_job(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "released")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator-2", note="Provider confirmed no charge.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert result.event is not None and result.event.event_type is ReconciliationEventType.FINAL_RESOLUTION
    # No MANUAL dead-end: a terminal financial outcome always terminalizes the job.
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM provider_attempts WHERE status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')").fetchone()[0] == 0


def test_terminal_financial_outcomes_reject_manual_review(storage, account):
    for financial in (FinancialResolution.NOT_CHARGED, FinancialResolution.CHARGED_KNOWN):
        _execution, request_id = _needs_reconciliation(storage, account, f"nomanual-{financial.value}")
        with pytest.raises(ProviderAttemptReconciliationError, match="may not use"):
            storage.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id, financial_resolution=financial,
                execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                actual_cost_usd="0.02" if financial is FinancialResolution.CHARGED_KNOWN else None,
                reconciled_by="operator", note="MANUAL is not terminal.",
            )
        # The attempt and job are untouched: no terminal-attempt/stuck-job dead-end.
        assert storage.conn.execute(
            "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
        ).fetchone()[0] == "NEEDS_RECONCILIATION"


def test_charge_unknown_only_records_note_and_cannot_close_lifecycle(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "unknown")
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="operator-3", note="Invoice unavailable.",
    )
    assert result.attempt.status is ProviderAttemptStatus.NEEDS_RECONCILIATION
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator-3", note="Invalid close.",
        )


@pytest.mark.parametrize("fault", list(ReconciliationFaultPoint))
def test_reconciliation_fault_points_roll_back_every_related_row(storage, account, monkeypatch, fault):
    execution, request_id = _needs_reconciliation(storage, account, f"fault-{fault.value}")

    def interrupt(point):
        if point is fault:
            raise RuntimeError(f"forced reconciliation fault: {point.value}")

    monkeypatch.setattr(storage, "_reconciliation_fault_point", interrupt)
    with pytest.raises(RuntimeError, match="forced reconciliation fault"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.020000", reconciled_by="operator-fault", note="Rollback proof.",
        )

    attempt = storage.conn.execute(
        "SELECT status,reconciled_at,reconciliation_resolution FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()
    assert tuple(attempt) == ("NEEDS_RECONCILIATION", None, None)
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.get_run(execution.run_id).status is RunStatus.RUNNING
    assert storage.get_research_run(execution.run_id).status.value == "PENDING"


def test_not_charged_rejects_existing_nonlegacy_usage_and_does_not_release(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "usage-conflict")
    storage.add_model_usage(ModelUsage(
        run_id=execution.run_id, model="reconciliation-model", task="research",
        estimated_cost_usd=0.02, dry_run=False, request_id=request_id, created_at=NOW,
    ))
    with pytest.raises(ProviderAttemptReconciliationError, match="NOT_CHARGED is forbidden"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator-usage", note="Must remain charged.",
        )
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"


def test_result_already_finalized_requires_card_and_refreshes_canonical_cost(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "finalized")
    topic_id = storage.get_job(execution.job_id).topic_id
    assert topic_id is not None
    card = storage.add_research_card(ResearchCard(
        topic_id=topic_id, question="Why?", working_thesis="Already persisted.",
    ))
    assert card.id is not None
    storage.finalize_research_success(
        execution.run_id, card.id, 0.0, stage_b_completed=False,
        terminal_run_status=RunStatus.SUCCESS,
    )

    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.RESULT_ALREADY_FINALIZED,
        actual_cost_usd="0.020000", reconciled_by="operator-final", note="Final card verified.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert storage.get_job(execution.job_id).status is JobStatus.DONE
    assert storage.get_run(execution.run_id).cost_usd == pytest.approx(0.02)
    assert storage.get_research_run(execution.run_id).total_cost_usd == pytest.approx(0.02)


def test_tampered_execution_intent_fingerprint_fails_closed_before_usage(storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "fingerprint")
    row = storage.conn.execute(
        "SELECT j.payload_json,j.id AS job_id FROM jobs j JOIN provider_attempts p ON p.job_id=j.id "
        "WHERE p.request_id=?",
        (request_id,),
    ).fetchone()
    payload = json.loads(row["payload_json"])
    payload["execution_intent"]["model"] = "tampered-model"
    storage.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?", (json.dumps(payload), row["job_id"]),
    )
    storage.conn.commit()
    with pytest.raises(
        ProviderAttemptReconciliationError,
        match="fingerprint|identity",
    ):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.020000", reconciled_by="operator-fingerprint", note="Tamper proof.",
        )
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0


def test_two_operator_connections_yield_one_atomic_resolution(settings, storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "concurrent")

    def resolve_once(_: int) -> bool:
        local = SqliteStorage.open(settings.db_path)
        try:
            result = local.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id,
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd="0.020000", reconciled_by="operator-concurrent", note="Same decision.",
            )
            return result.idempotent
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(resolve_once, range(2)))
    assert sorted(outcomes) == [False, True]
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 1


def test_0014_migration_rolls_back_when_its_ledger_entry_is_rejected(tmp_path):
    migration_dir = tmp_path / "migrations-through-0013"
    migration_dir.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if source.stem <= "0013_provider_attempt_usage_integrity":
            shutil.copy2(source, migration_dir / source.name)
    conn = connect(tmp_path / "rollback-0014.db")
    assert apply_migrations(conn, migration_dir)[-1] == "0013_provider_attempt_usage_integrity"
    assert "reconciled_at" not in {row["name"] for row in conn.execute("PRAGMA table_info(provider_attempts)")}
    shutil.copy2(
        MIGRATIONS_DIR / "0014_provider_attempt_reconciliation.sql",
        migration_dir / "0014_provider_attempt_reconciliation.sql",
    )
    conn.execute(
        "CREATE TRIGGER reject_0014_ledger BEFORE INSERT ON schema_migrations "
        "WHEN NEW.version='0014_provider_attempt_reconciliation' "
        "BEGIN SELECT RAISE(ABORT, 'forced 0014 ledger failure'); END"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="forced 0014 ledger failure"):
        apply_migrations(conn, migration_dir)
    assert "reconciled_at" not in {row["name"] for row in conn.execute("PRAGMA table_info(provider_attempts)")}
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0014_provider_attempt_reconciliation'"
    ).fetchone()[0] == 0
    conn.execute("DROP TRIGGER reject_0014_ledger")
    conn.commit()
    assert apply_migrations(conn, migration_dir) == ["0014_provider_attempt_reconciliation"]
    assert {"reconciled_at", "reconciled_by", "reconciliation_resolution"} <= {
        row["name"] for row in conn.execute("PRAGMA table_info(provider_attempts)")
    }
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_reconciliation_cli_preview_then_confirm_with_version_token(
    settings, storage, account, monkeypatch, capsys,
):
    _execution, request_id = _needs_reconciliation(storage, account, "cli")
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main(["list-reconciliations", "--account-id", account.id]) == 0
    assert request_id in capsys.readouterr().out
    base_args = [
        "reconcile-attempt", "--request-id", request_id, "--account-id", account.id,
        "--financial-resolution", "charged-known", "--execution-resolution", "execution-failed",
        "--actual-cost-usd", "0.020000", "--reconciled-by", "operator-cli", "--note", "CLI preview.",
    ]
    assert main(base_args) == 0
    preview_out = capsys.readouterr().out
    assert "RECONCILIATION PREVIEW" in preview_out and "PREVIEW ONLY" in preview_out
    assert "attempt_status=NEEDS_RECONCILIATION" in preview_out
    token = _extract_token(preview_out)
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    # --confirm without a fresh token is a controlled input error (exit 4).
    assert main([*base_args, "--confirm"]) == 4
    assert "requires --version-token" in capsys.readouterr().err
    # --confirm with the preview's token performs the single atomic write.
    assert main([*base_args, "--confirm", "--version-token", token]) == 0
    assert "RECONCILED: status=RECONCILED_SETTLED" in capsys.readouterr().out
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 1


def test_two_concurrent_conflicting_operator_decisions_fail_closed(settings, storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "conflicting")
    barrier = Barrier(2)

    def resolve(financial: FinancialResolution) -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            try:
                local.resolve_provider_attempt_reconciliation(
                    request_id=request_id, account_id=account.id, financial_resolution=financial,
                    execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                    actual_cost_usd="0.020000" if financial is FinancialResolution.CHARGED_KNOWN else None,
                    reconciled_by="operator-conflict", note="Conflicting concurrent decision.",
                )
                return "resolved"
            except ProviderAttemptReconciliationError:
                return "rejected"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(resolve, [FinancialResolution.CHARGED_KNOWN, FinancialResolution.NOT_CHARGED]))
    assert sorted(outcomes) == ["rejected", "resolved"]
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0]
    usage_count = storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0]
    assert (attempt, usage_count) in {("RECONCILED_SETTLED", 1), ("RECONCILED_RELEASED", 0)}


def test_resolver_races_attempt_two_and_neither_path_retries(settings, storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "attempt-two")
    barrier = Barrier(2)

    def reconcile() -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            local.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id,
                financial_resolution=FinancialResolution.NOT_CHARGED,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=None, reconciled_by="operator-attempt-two", note="No retry allowed.",
            )
            return "resolved"
        finally:
            local.close()

    def attempt_two() -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            with pytest.raises((ProviderAttemptReconciliationRequired, StaleJobExecutionError)):
                local.begin_provider_attempt(
                    execution, stage="research", attempt_no=2, max_cost_usd=0.2,
                    daily_limit_usd=2.0, monthly_limit_usd=40.0,
                )
            return "blocked"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda fn: fn(), [reconcile, attempt_two]))
    assert sorted(outcomes) == ["blocked", "resolved"]
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (execution.job_id,),
    ).fetchone()[0] == 1


@pytest.mark.parametrize(
    "bad_cost", [float("nan"), float("inf"), float("-inf"), -0.000001, 0.0, "0.0", "0.0000001"],
)
def test_charged_known_rejects_nonfinite_zero_or_negative_cost_without_mutation(storage, account, bad_cost):
    # CHARGED_KNOWN demands a strictly positive canonical charge; zero or below
    # must use NOT_CHARGED (P2).  Every rejection is fail-closed, zero mutation.
    _execution, request_id = _needs_reconciliation(storage, account, f"bad-cost-{bad_cost}")
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=bad_cost, reconciled_by="operator-money", note="Invalid money input.",
        )
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"


def test_missing_or_foreign_attempt_and_non_reconcilable_states_fail_closed(storage, account):
    execution = _execution(storage, account, "non-reconcilable")
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    for request_id, account_id in [("missing:research:1", account.id), (attempt.request_id, "other-account")]:
        with pytest.raises(ProviderAttemptReconciliationError):
            storage.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account_id,
                financial_resolution=FinancialResolution.NOT_CHARGED,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=None, reconciled_by="operator-state", note="Must fail closed.",
            )
    with pytest.raises(ProviderAttemptReconciliationError, match="Only NEEDS_RECONCILIATION"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=attempt.request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator-state", note="Reserved is not reconcilable.",
        )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    with pytest.raises(ProviderAttemptReconciliationError, match="Only NEEDS_RECONCILIATION"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=attempt.request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator-state", note="Started is not reconcilable.",
        )


def test_duplicate_usage_and_stale_cli_confirmation_fail_closed(settings, storage, account, monkeypatch, capsys):
    execution, request_id = _needs_reconciliation(storage, account, "duplicate")
    existing_usage = ModelUsage(
        run_id=execution.run_id, model="reconciliation-model", task="research",
        estimated_cost_usd=0.02, dry_run=False, request_id=request_id, created_at=NOW,
    )
    storage.add_model_usage(existing_usage)
    with pytest.raises(sqlite3.IntegrityError, match="model_usage.request_id"):
        storage.add_model_usage(existing_usage.model_copy(update={"id": None}))
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator-duplicate", note="Existing usage proof.",
    )
    assert result.usage_id == existing_usage.id
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,)).fetchone()[0] == 1

    cli_execution, cli_request_id = _needs_reconciliation(storage, account, "stale-cli")
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    cli_args = [
        "reconcile-attempt", "--request-id", cli_request_id, "--account-id", account.id,
        "--financial-resolution", "not-charged", "--execution-resolution", "execution-failed",
        "--reconciled-by", "operator-stale", "--note", "Stale preview.",
    ]
    assert main(cli_args) == 0
    stale_token = _extract_token(capsys.readouterr().out)
    # A different operator resolves the attempt after the preview token was taken.
    storage.resolve_provider_attempt_reconciliation(
        request_id=cli_request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator-other", note="Changed after preview.",
    )
    # The stale token now fails closed with the dedicated stale exit code (5).
    assert main([*cli_args, "--confirm", "--version-token", stale_token]) == 5
    assert "stale preview" in capsys.readouterr().err
    assert storage.get_job(cli_execution.job_id).status is JobStatus.FAILED


def test_terminal_reconciliation_survives_reopen_recovery_and_reaper(settings, storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "restart-reaper")
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator-restart", note="Financially closed as no charge.",
    )
    reopened = SqliteStorage.open(settings.db_path)
    try:
        reopened.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
        reopened.reap_orphaned_stale_runs(
            NOW + timedelta(days=1), now=NOW + timedelta(days=2),
        )
        row = reopened.conn.execute(
            "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
        ).fetchone()
        assert row["status"] == "RECONCILED_RELEASED"
        assert reopened.list_provider_attempts_needing_reconciliation(account_id=account.id) == []
        # Terminal financial outcome terminalizes the job; maintenance never revives it.
        assert reopened.get_job(execution.job_id).status is JobStatus.FAILED
    finally:
        reopened.close()


# ---- W1A-VERIFY-01: resolver EXECUTION_FAILED vs maintenance reaper STOPPED -----
# The reaper terminalizes an orphaned stale run to STOPPED while the job stays
# NEEDS_VERIFICATION.  EXECUTION_FAILED must accept STOPPED (alongside RUNNING and
# FAILED) and still drive attempt/job/run/research_run to a coherent failure.
# These scenarios are deterministic and never depend on thread ordering.


def _run_status(store, run_id):
    return store.conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()[0]


def _research_status(store, run_id):
    return store.conn.execute("SELECT status FROM research_runs WHERE id=?", (run_id,)).fetchone()[0]


def _attempt_status(store, request_id):
    return store.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0]


def _attempt_count(store, job_id):
    return store.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job_id,),
    ).fetchone()[0]


def _reap_run_to_stopped(store, execution):
    """Deterministically drive the attempt's run to the maintenance STOPPED state."""
    store.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
    reaped = store.reap_orphaned_stale_runs(NOW + timedelta(days=1), now=NOW + timedelta(days=2))
    assert reaped.stopped_count == 1
    assert _run_status(store, execution.run_id) == "STOPPED"
    return reaped


def test_execution_failed_resolves_a_reaper_stopped_run_not_charged(settings, storage, account):
    # Scenario 1 (reaper wins first, no charge): STOPPED run is resolved to FAILED.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-nc")
    _reap_run_to_stopped(storage, execution)
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION

    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="Reaped run; no charge.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert _run_status(storage, execution.run_id) == "FAILED"
    assert _research_status(storage, execution.run_id) == "FAILED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    # Reaper/maintenance history is preserved, run never resurrected, no retry/attempt #2.
    run_row = storage.conn.execute(
        "SELECT error, finished_at FROM runs WHERE id=?", (execution.run_id,),
    ).fetchone()
    assert run_row["error"] == _STALE_RUN_REAPER_REASON
    assert run_row["finished_at"] is not None
    assert _attempt_count(storage, execution.job_id) == 1


def test_execution_failed_resolves_a_reaper_stopped_run_charged_known(settings, storage, account):
    # Scenario 1b (reaper wins first, provider charged): STOPPED->FAILED, one canonical usage.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-ck")
    _reap_run_to_stopped(storage, execution)

    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator", note="Reaped run; provider charged.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert result.usage_id is not None
    assert _run_status(storage, execution.run_id) == "FAILED"
    assert _research_status(storage, execution.run_id) == "FAILED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    # Ledger == both caches (the resolver also asserts this inside its transaction).
    canonical = storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0 AND is_legacy_usage=0", (execution.run_id,),
    ).fetchone()[0]
    assert abs(canonical - 0.02) < 1e-9
    assert abs(storage.get_run(execution.run_id).cost_usd - 0.02) < 1e-9
    assert _attempt_count(storage, execution.job_id) == 1


def test_execution_failed_before_reaper_leaves_reaper_a_noop(settings, storage, account):
    # Scenario 2 (resolver wins first): run is FAILED, so the later reaper changes nothing.
    execution, request_id = _needs_reconciliation(storage, account, "resolve-first")
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="Closed before maintenance.",
    )
    assert _run_status(storage, execution.run_id) == "FAILED"
    # The run had no prior error, so the resolver stamped its own reason.
    assert storage.conn.execute(
        "SELECT error FROM runs WHERE id=?", (execution.run_id,),
    ).fetchone()[0] == "OPERATOR_RECONCILIATION_EXECUTION_FAILED"

    storage.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
    reaped = storage.reap_orphaned_stale_runs(NOW + timedelta(days=1), now=NOW + timedelta(days=2))
    assert reaped.stopped_count == 0
    assert _run_status(storage, execution.run_id) == "FAILED"
    assert _attempt_status(storage, request_id) == "RECONCILED_RELEASED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED


def test_resolver_interleaves_with_recovery_and_reaper_without_reviving_attempt(settings, storage, account):
    # Scenario 3 (simultaneous race): order-independent.  Resolver-first drives
    # RUNNING->FAILED (reaper then no-ops); reaper-first drives RUNNING->STOPPED
    # (resolver then accepts STOPPED->FAILED).  Either way both succeed and the
    # terminal state is identical, so the suite is no longer flaky.
    execution, request_id = _needs_reconciliation(storage, account, "maintenance-race")
    barrier = Barrier(2)

    def resolve() -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            local.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id,
                financial_resolution=FinancialResolution.NOT_CHARGED,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=None, reconciled_by="operator-maintenance", note="No charge; execution failed.",
            )
            return "resolved"
        finally:
            local.close()

    def maintain() -> str:
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            local.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
            local.reap_orphaned_stale_runs(
                NOW + timedelta(days=1), now=NOW + timedelta(days=2),
            )
            return "maintained"
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda fn: fn(), [resolve, maintain])) == ["maintained", "resolved"]
    assert _attempt_status(storage, request_id) == "RECONCILED_RELEASED"
    assert _run_status(storage, execution.run_id) == "FAILED"
    assert _research_status(storage, execution.run_id) == "FAILED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert _attempt_count(storage, execution.job_id) == 1


def test_execution_failed_resolves_stopped_run_after_reopen(settings, storage, account):
    # Scenario 4 (reopen after STOPPED): a fresh process/connection still resolves it.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-reopen")
    _reap_run_to_stopped(storage, execution)
    reopened = SqliteStorage.open(settings.db_path)
    try:
        result = reopened.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator", note="Resolved after restart.",
        )
        assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
        assert _run_status(reopened, execution.run_id) == "FAILED"
        assert reopened.get_job(execution.job_id).status is JobStatus.FAILED
    finally:
        reopened.close()


def test_result_already_finalized_rejects_a_reaper_stopped_run(settings, storage, account):
    # Scenario 5: a STOPPED run has no durable success proof, so RESULT_ALREADY_FINALIZED
    # must fail closed — STOPPED can never become DONE.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-raf")
    _reap_run_to_stopped(storage, execution)
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.RESULT_ALREADY_FINALIZED,
            actual_cost_usd=None, reconciled_by="operator", note="No durable proof.",
        )
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    assert _run_status(storage, execution.run_id) == "STOPPED"
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION


def test_execution_failed_on_stopped_run_rejects_foreign_account(settings, storage, account):
    # Scenario 6: a STOPPED run belonging to another account is rejected before any mutation.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-foreign")
    _reap_run_to_stopped(storage, execution)
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id="a-different-account",
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="intruder", note="wrong account",
        )
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    assert _run_status(storage, execution.run_id) == "STOPPED"


def test_execution_failed_on_stopped_run_rejects_conflicting_research_run(settings, storage, account):
    # Scenario 7: a STOPPED run whose research_run already holds a finalized card is a
    # contradictory lifecycle; EXECUTION_FAILED must fail closed and leave it STOPPED.
    execution, request_id = _needs_reconciliation(storage, account, "stopped-conflict")
    _reap_run_to_stopped(storage, execution)
    topic_id = storage.get_job(execution.job_id).topic_id
    card = storage.add_research_card(ResearchCard(
        topic_id=topic_id, question="Why?", working_thesis="Conflicting card.",
    ))
    storage.conn.execute(
        "UPDATE research_runs SET research_card_id=? WHERE id=?", (card.id, execution.run_id),
    )
    storage.conn.commit()
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator", note="conflicting research_run",
        )
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    assert _run_status(storage, execution.run_id) == "STOPPED"


# ===========================================================================
# WAVE 1A repair coverage: usage identity, exclusive card ownership, append-only
# history, lifecycle matrix, ledger/cache invariant, raw SQLite floor, and
# provider/legacy containment.
# ===========================================================================


def _seed_usage_row(storage, request_id, run_id, **overrides):
    """Insert one non-legacy usage row directly (honors the DB relation trigger)."""
    fields = {
        "provider": "anthropic", "model": "reconciliation-model", "task": "research",
        "estimated_cost_usd": 0.02,
    }
    fields.update(overrides)
    storage.conn.execute(
        "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,output_tokens,"
        "cache_read_tokens,cache_write_tokens,web_search_requests,estimated_cost_usd,dry_run,"
        "request_id,is_legacy_usage,created_at) VALUES (?,?,?,?,0,0,0,0,0,?,0,?,0,?)",
        (run_id, fields["provider"], fields["model"], fields["task"],
         float(fields["estimated_cost_usd"]), request_id, "2026-07-15 12:00:00"),
    )
    storage.conn.commit()


def _finalize_card(storage, execution, cost=0.0):
    topic_id = storage.get_job(execution.job_id).topic_id
    card = storage.add_research_card(ResearchCard(
        topic_id=topic_id, question="Why?", working_thesis="Already persisted.",
    ))
    storage.finalize_research_success(
        execution.run_id, card.id, cost, stage_b_completed=False,
        terminal_run_status=RunStatus.SUCCESS,
    )
    return card.id


def _reconciled_released(storage, account, suffix):
    execution, request_id = _needs_reconciliation(storage, account, suffix)
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="released terminal",
    )
    return execution, request_id


def _reconciled_settled(storage, account, suffix):
    execution, request_id = _needs_reconciliation(storage, account, suffix)
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator", note="settled terminal",
    )
    return execution, request_id


# ---- RR-01: full existing-usage identity, never cost alone --------------------


@pytest.mark.parametrize("mutation,field", [
    ({"provider": "openai"}, "provider"),
    ({"model": "other-model"}, "model"),
    ({"task": "chat"}, "task"),
    ({"estimated_cost_usd": 0.05}, "cost"),
])
def test_charged_known_existing_usage_identity_mismatch_fails_closed(storage, account, mutation, field):
    execution, request_id = _needs_reconciliation(storage, account, f"identity-{field}")
    _seed_usage_row(storage, request_id, execution.run_id, **mutation)
    with pytest.raises(ProviderAttemptReconciliationError, match="identity mismatch"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.020000", reconciled_by="operator-id", note="Identity must match.",
        )
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"


def test_charged_known_accepts_fully_matching_existing_usage(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "identity-ok")
    _seed_usage_row(storage, request_id, execution.run_id)  # matches intent exactly
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator-id", note="Matches existing usage.",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 1


# ---- RR-02: exclusive durable Research Card ownership -------------------------


def test_result_already_finalized_requires_finalized_card(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "nocard")
    with pytest.raises(ProviderAttemptReconciliationError, match="finalized Research Card"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.RESULT_ALREADY_FINALIZED,
            actual_cost_usd="0.020000", reconciled_by="operator", note="No finalized card.",
        )
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 0


def test_research_card_cannot_be_shared_across_research_runs(storage, account):
    owner, _owner_request = _needs_reconciliation(storage, account, "card-owner")
    card_id = _finalize_card(storage, owner)
    other, _other_request = _needs_reconciliation(storage, account, "card-thief")
    # The UNIQUE partial index makes a shared card unrepresentable.
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE research_runs SET research_card_id=? WHERE id=?", (card_id, other.run_id),
        )
    storage.conn.rollback()
    owners = storage.conn.execute(
        "SELECT count(*) FROM research_runs WHERE research_card_id=?", (card_id,),
    ).fetchone()[0]
    assert owners == 1


def test_result_already_finalized_rejects_inconsistent_relation(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "reltamper")
    other_topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Other", question="Q?", score=50, status=TopicStatus.SELECTED,
    ))
    storage.conn.execute(
        "UPDATE research_runs SET topic_id=? WHERE id=?", (int(other_topic.id), execution.run_id),
    )
    storage.conn.commit()
    with pytest.raises(ProviderAttemptReconciliationError, match="lineage is inconsistent"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator", note="Topic relation mismatch.",
        )


# ---- RR-03: append-only observation history ----------------------------------


def test_charge_unknown_appends_observation_follow_up_and_final(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "history")
    first = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op-a", note="First observation.",
    )
    assert first.observed and first.event.event_type is ReconciliationEventType.UNRESOLVED_OBSERVATION
    second = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op-b", note="Follow-up detail.",
    )
    assert second.event.event_type is ReconciliationEventType.FOLLOW_UP
    final = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="op-c", note="Final release.",
    )
    assert final.event.event_type is ReconciliationEventType.FINAL_RESOLUTION
    events = storage.list_reconciliation_events(request_id=request_id, account_id=account.id)
    assert [e.event_type for e in events] == [
        ReconciliationEventType.UNRESOLVED_OBSERVATION,
        ReconciliationEventType.FOLLOW_UP,
        ReconciliationEventType.FINAL_RESOLUTION,
    ]
    assert [e.sequence_number for e in events] == [1, 2, 3]
    assert [e.operator for e in events] == ["op-a", "op-b", "op-c"]


def test_charge_unknown_identical_is_idempotent_and_different_is_new_event(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "idem")

    def observe(operator, note):
        return storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
            execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
            actual_cost_usd=None, reconciled_by=operator, note=note,
        )

    first = observe("op", "same note")
    repeat = observe("op", "same note")
    assert repeat.idempotent and repeat.event.sequence_number == first.event.sequence_number
    other_note = observe("op", "different note")
    assert not other_note.idempotent and other_note.event.sequence_number == first.event.sequence_number + 1
    other_op = observe("other-op", "same note")
    assert not other_op.idempotent
    assert len(storage.list_reconciliation_events(request_id=request_id, account_id=account.id)) == 3


def test_two_different_charge_unknown_observations_append_two_events(settings, storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "obs-race")
    barrier = Barrier(2)

    def observe(operator):
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            local.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id,
                financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
                execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                actual_cost_usd=None, reconciled_by=operator, note=f"note from {operator}",
            )
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(observe, ["op-x", "op-y"]))
    events = storage.list_reconciliation_events(request_id=request_id, account_id=account.id)
    assert [e.sequence_number for e in events] == [1, 2]
    assert {e.operator for e in events} == {"op-x", "op-y"}
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"


# ---- Lifecycle matrix: every allowed combination is resolvable ----------------


def test_lifecycle_matrix_every_allowed_combination_is_consistent(storage, account):
    # CHARGED_KNOWN / NOT_CHARGED x EXECUTION_FAILED / RESULT_ALREADY_FINALIZED
    # plus the CHARGE_UNKNOWN observation path.  None strands a terminal attempt.
    cases = [
        (FinancialResolution.CHARGED_KNOWN, ExecutionResolution.EXECUTION_FAILED, "0.02",
         False, "RECONCILED_SETTLED", JobStatus.FAILED),
        (FinancialResolution.CHARGED_KNOWN, ExecutionResolution.RESULT_ALREADY_FINALIZED, "0.02",
         True, "RECONCILED_SETTLED", JobStatus.DONE),
        (FinancialResolution.NOT_CHARGED, ExecutionResolution.EXECUTION_FAILED, None,
         False, "RECONCILED_RELEASED", JobStatus.FAILED),
        (FinancialResolution.NOT_CHARGED, ExecutionResolution.RESULT_ALREADY_FINALIZED, None,
         True, "RECONCILED_RELEASED", JobStatus.DONE),
    ]
    for index, (financial, execution_res, cost, needs_card, attempt_status, job_status) in enumerate(cases):
        execution, request_id = _needs_reconciliation(storage, account, f"matrix-{index}")
        if needs_card:
            _finalize_card(storage, execution)
        result = storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id, financial_resolution=financial,
            execution_resolution=execution_res, actual_cost_usd=cost,
            reconciled_by="operator-matrix", note=f"matrix case {index}",
        )
        assert result.attempt.status.value == attempt_status
        assert storage.get_job(execution.job_id).status is job_status
        # No terminal attempt may leave the job unresolvable (NEEDS_VERIFICATION).
        assert storage.get_job(execution.job_id).status is not JobStatus.NEEDS_VERIFICATION

    unknown_execution, unknown_request = _needs_reconciliation(storage, account, "matrix-unknown")
    observed = storage.resolve_provider_attempt_reconciliation(
        request_id=unknown_request, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="operator-matrix", note="still unknown",
    )
    assert observed.attempt.status is ProviderAttemptStatus.NEEDS_RECONCILIATION
    assert storage.get_job(unknown_execution.job_id).status is JobStatus.NEEDS_VERIFICATION


# ---- NEW-02 / Section 6: ledger <-> cache stay consistent --------------------


def test_charged_known_keeps_ledger_and_cache_consistent(storage, account):
    execution, request_id = _needs_reconciliation(storage, account, "ledger")
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.017500", reconciled_by="operator-ledger", note="Ledger equals cache.",
    )
    canonical = storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage WHERE run_id=? AND dry_run=0",
        (execution.run_id,),
    ).fetchone()[0]
    assert canonical == pytest.approx(0.0175)
    assert storage.get_run(execution.run_id).cost_usd == pytest.approx(canonical)
    assert storage.get_research_run(execution.run_id).total_cost_usd == pytest.approx(canonical)


# ---- Section 14: raw SQLite enforcement floor --------------------------------


def test_reconciliation_events_reject_blank_operator_note_and_unknown_enums(storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "raw-events")
    base = (request_id, 1, "UNRESOLVED_OBSERVATION", "CHARGE_UNKNOWN",
            "MANUAL_REVIEW_REMAINS_REQUIRED", "op", "note", "NEEDS_RECONCILIATION",
            "NEEDS_RECONCILIATION", "2026-07-15 12:00:00", "k-valid")
    columns = ("request_id,sequence_number,event_type,financial_resolution,execution_resolution,"
               "operator,note,previous_attempt_status,resulting_attempt_status,created_at,idempotency_key")
    insert = f"INSERT INTO reconciliation_events ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?)"

    def attempt(**overrides):
        row = list(base)
        order = columns.split(",")
        for key, value in overrides.items():
            row[order.index(key)] = value
        row[order.index("idempotency_key")] = "k-" + "-".join(str(v) for v in overrides.values())
        with pytest.raises(sqlite3.IntegrityError):
            storage.conn.execute(insert, tuple(row))
        storage.conn.rollback()

    attempt(operator="")
    attempt(operator="   ")
    attempt(note="")
    attempt(note="\t  ")
    attempt(event_type="BOGUS")
    attempt(financial_resolution="MAYBE")
    attempt(execution_resolution="WHATEVER")
    # No event of any kind may be appended once the attempt is terminal
    # (the FINAL_RESOLUTION event is written before the flip, in the same
    # transaction; afterwards the history is closed).
    _terminal_execution, terminal_request = _reconciled_released(storage, account, "raw-events-terminal")
    with pytest.raises(sqlite3.IntegrityError, match="NEEDS_RECONCILIATION"):
        storage.conn.execute(insert, (
            terminal_request, 2, "FOLLOW_UP", "CHARGE_UNKNOWN", "MANUAL_REVIEW_REMAINS_REQUIRED",
            "op", "late note", "NEEDS_RECONCILIATION", "NEEDS_RECONCILIATION",
            "2026-07-15 12:00:00", "k-after-terminal",
        ))
    storage.conn.rollback()


def test_reconciliation_events_are_append_only_and_monotonic(storage, account):
    _execution, request_id = _needs_reconciliation(storage, account, "raw-append")
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op", note="observed",
    )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute("UPDATE reconciliation_events SET note='tampered' WHERE request_id=?", (request_id,))
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute("DELETE FROM reconciliation_events WHERE request_id=?", (request_id,))
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO reconciliation_events (request_id,sequence_number,event_type,"
            "financial_resolution,execution_resolution,operator,note,previous_attempt_status,"
            "resulting_attempt_status,created_at,idempotency_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, 9, "FOLLOW_UP", "CHARGE_UNKNOWN", "MANUAL_REVIEW_REMAINS_REQUIRED",
             "op", "gap", "NEEDS_RECONCILIATION", "NEEDS_RECONCILIATION", "2026-07-15 12:00:00", "k-gap"),
        )
    storage.conn.rollback()


def test_reconciled_terminal_attempt_is_immutable_and_undeletable(storage, account):
    _settled_execution, settled_request = _reconciled_settled(storage, account, "raw-settled")
    _released_execution, released_request = _reconciled_released(storage, account, "raw-released")
    for request_id in (settled_request, released_request):
        with pytest.raises(sqlite3.IntegrityError):
            storage.conn.execute(
                "UPDATE provider_attempts SET reconciliation_note='tampered' WHERE request_id=?", (request_id,),
            )
        storage.conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            storage.conn.execute("DELETE FROM provider_attempts WHERE request_id=?", (request_id,))
        storage.conn.rollback()


def test_raw_reconciled_settled_requires_usage_and_released_forbids_usage(storage, account):
    # Several independent terminal triggers may fire first (usage coupling,
    # lifecycle, FINAL_RESOLUTION event, cost caches); each raw write must be
    # blocked by at least one of them with zero mutation.
    blocked = "canonical|terminal reconciliation|FINAL_RESOLUTION|cost caches"
    no_usage_execution, no_usage_request = _needs_reconciliation(storage, account, "raw-need-usage")
    _raw_terminal_lifecycle(storage, no_usage_execution)
    with pytest.raises(sqlite3.IntegrityError, match=blocked):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_SETTLED',settled_at='2026-07-15 12:00:00',"
            "reconciled_at='2026-07-15 12:00:00',reconciled_by='op',reconciliation_note='n',"
            "reconciliation_resolution='CHARGED_KNOWN:EXECUTION_FAILED' WHERE request_id=?",
            (no_usage_request,),
        )
    storage.conn.rollback()

    usage_execution, usage_request = _needs_reconciliation(storage, account, "raw-forbid-usage")
    _seed_usage_row(storage, usage_request, usage_execution.run_id)
    _raw_terminal_lifecycle(storage, usage_execution)
    with pytest.raises(sqlite3.IntegrityError, match=blocked):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at='2026-07-15 12:00:00',"
            "reconciled_at='2026-07-15 12:00:00',reconciled_by='op',reconciliation_note='n',"
            "reconciliation_resolution='NOT_CHARGED:EXECUTION_FAILED' WHERE request_id=?",
            (usage_request,),
        )
    storage.conn.rollback()


def test_raw_attempt_cannot_start_in_a_terminal_state(storage, account):
    execution = _execution(storage, account, "raw-initial")
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
            "reserved_amount_usd,reserved_at) VALUES (?,?,?,?,?,?,?)",
            (execution.job_id, "research", 1, f"{execution.job_id}:research:1",
             "RECONCILED_SETTLED", 0.2, "2026-07-15 12:00:00"),
        )
    storage.conn.rollback()


def test_fresh_migration_passes_integrity_and_foreign_key_checks(tmp_path):
    conn = connect(tmp_path / "fresh-1a.db")
    try:
        apply_migrations(conn)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "reconciliation_events" in tables
        indexes = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "ux_research_runs_research_card" in indexes
    finally:
        conn.close()


# ---- Section 16: provider and legacy containment -----------------------------


def test_dispatcher_is_the_only_real_client_construction_root():
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    roots = set()
    for py in app_dir.rglob("*.py"):
        for line in py.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if "AnthropicResearchClient(" in stripped and not stripped.startswith("class "):
                roots.add(py.relative_to(app_dir).as_posix())
    assert roots == {"scheduler/dispatcher.py"}


def test_resolver_module_never_imports_sdk_or_constructs_a_client():
    import app.storage.repositories as repositories_module

    source = pathlib.Path(repositories_module.__file__).read_text(encoding="utf-8")
    assert "import anthropic" not in source
    assert "AnthropicResearchClient" not in source


def test_reconcile_cli_confirm_subprocess_refuses_protected_db_with_scrubbed_env():
    project_root = pathlib.Path(__file__).resolve().parents[1]
    protected_db = project_root / "data" / "agent.db"
    scrubbed_env = {
        "NIA_TEST_MODE": "1",
        "NIA_TEST_PROTECTED_DB": str(protected_db),
        "PATH": os.environ.get("PATH", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "PYTHONPATH": str(project_root),
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "reconcile-attempt",
         "--request-id", "missing:research:1", "--account-id", "nothing_is_accidental",
         "--financial-resolution", "not-charged", "--execution-resolution", "execution-failed",
         "--reconciled-by", "op", "--note", "scrubbed env", "--confirm", "--version-token", "x"],
        cwd=project_root, capture_output=True, text=True, env=scrubbed_env, check=False,
    )
    # Fails closed (config or storage refusal) without touching the protected DB.
    assert result.returncode in (3, 6)
    assert "ANTHROPIC_API_KEY" not in result.stdout


# ---- Section 17: W1A-AUD — controlled CLI errors ------------------------------


def test_list_reconciliations_cli_reports_controlled_config_and_storage_errors(
    settings, tmp_path, monkeypatch, capsys,
):
    # W1A-AUD-01: the read-only queue command uses the same controlled exit
    # codes as reconcile-attempt instead of an unhandled traceback.
    def broken_settings():
        raise ConfigError("audit: configuration is unavailable")

    monkeypatch.setattr("app.main.load_settings", broken_settings)
    assert main(["list-reconciliations"]) == 3
    assert "config error" in capsys.readouterr().err

    blocked = tmp_path / "db-path-is-a-directory"
    blocked.mkdir()
    monkeypatch.setattr("app.main.load_settings", lambda: replace(settings, db_path=blocked))
    assert main(["list-reconciliations"]) == 6
    assert "storage error" in capsys.readouterr().err


def test_list_reconciliations_cli_reports_controlled_query_and_close_errors(
    settings, storage, account, monkeypatch, capsys,
):
    # W1A-AUD-01 (full repair): failures during the queue query itself, during
    # result formatting and during close are controlled exit 6, not tracebacks.
    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    def broken_query(self, *, account_id=None):
        raise sqlite3.OperationalError("audit: forced query-time failure")

    monkeypatch.setattr(SqliteStorage, "list_provider_attempts_needing_reconciliation", broken_query)
    assert main(["list-reconciliations"]) == 6
    assert "storage error" in capsys.readouterr().err
    monkeypatch.undo()

    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    def broken_runtime_query(self, *, account_id=None):
        raise RuntimeError("audit: forced runtime failure during iteration")

    monkeypatch.setattr(SqliteStorage, "list_provider_attempts_needing_reconciliation", broken_runtime_query)
    assert main(["list-reconciliations"]) == 6
    assert "storage error" in capsys.readouterr().err
    monkeypatch.undo()

    monkeypatch.setattr("app.main.load_settings", lambda: settings)

    def broken_close(self):
        raise sqlite3.OperationalError("audit: forced close-time failure")

    monkeypatch.setattr(SqliteStorage, "close", broken_close)
    assert main(["list-reconciliations"]) == 6
    assert "storage error" in capsys.readouterr().err


# ---- Section 18: W1A-AUD-04 — crash-window escalation contract ----------------
# A hard crash can persist a RESERVED or REQUEST_STARTED attempt whose job then
# reaches NEEDS_VERIFICATION through expired-lease recovery.  Recovery now
# atomically escalates both windows to NEEDS_RECONCILIATION (enumerated reason,
# append-only AUTO_ESCALATION event), so the operator queue sees them, the
# resolver can settle them, and no reservation stays invisible forever.


def _crashed_attempt(storage, account, suffix, *, start_request):
    execution = _execution(storage, account, suffix)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    if start_request:
        storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    # Hard crash simulated: no further lifecycle write.
    return execution, attempt.request_id


def _escalate(storage):
    return storage.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))


def _events(storage, request_id):
    return storage.conn.execute(
        "SELECT event_type, previous_attempt_status, resulting_attempt_status, operator,"
        " sequence_number FROM reconciliation_events WHERE request_id=? ORDER BY sequence_number",
        (request_id,),
    ).fetchall()


def _attempt_row(storage, request_id):
    return storage.conn.execute(
        "SELECT status, error_code, request_started_at FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()


def test_escalation_ignores_attempts_with_a_live_lease(settings, storage, account):
    # H1 + H3: while the job lease is alive, recovery must not touch the attempt.
    _res_execution, reserved_request = _crashed_attempt(storage, account, "live-res", start_request=False)
    _req_execution, started_request = _crashed_attempt(storage, account, "live-req", start_request=True)
    result = storage.release_or_requeue_expired_leases(now=NOW + timedelta(seconds=1))
    assert result.escalated_reconciliation_count == 0
    assert _attempt_status(storage, reserved_request) == "RESERVED"
    assert _attempt_status(storage, started_request) == "REQUEST_STARTED"
    assert _events(storage, reserved_request) == []
    assert _events(storage, started_request) == []


def test_reserved_attempt_with_dead_lease_escalates_with_before_reason(settings, storage, account):
    # H2: RESERVED + dead lease -> NEEDS_RECONCILIATION, enumerated reason, event.
    execution, request_id = _crashed_attempt(storage, account, "esc-res", start_request=False)
    result = _escalate(storage)
    assert result.needs_verification_count == 1
    assert result.escalated_reconciliation_count == 1
    row = _attempt_row(storage, request_id)
    assert row["status"] == "NEEDS_RECONCILIATION"
    assert row["error_code"] == "LEASE_EXPIRED_BEFORE_REQUEST_STARTED"
    assert row["request_started_at"] is None
    events = _events(storage, request_id)
    assert [(e["event_type"], e["previous_attempt_status"], e["sequence_number"]) for e in events] == [
        ("AUTO_ESCALATION", "RESERVED", 1),
    ]
    assert storage.get_job(execution.job_id).status is JobStatus.NEEDS_VERIFICATION


def test_request_started_attempt_with_dead_lease_escalates_with_after_reason(settings, storage, account):
    # H4: REQUEST_STARTED + dead lease -> NEEDS_RECONCILIATION, "after" reason.
    execution, request_id = _crashed_attempt(storage, account, "esc-req", start_request=True)
    result = _escalate(storage)
    assert result.escalated_reconciliation_count == 1
    row = _attempt_row(storage, request_id)
    assert row["status"] == "NEEDS_RECONCILIATION"
    assert row["error_code"] == "LEASE_EXPIRED_AFTER_REQUEST_STARTED"
    assert row["request_started_at"] is not None
    events = _events(storage, request_id)
    assert [(e["event_type"], e["previous_attempt_status"]) for e in events] == [
        ("AUTO_ESCALATION", "REQUEST_STARTED"),
    ]


def test_two_concurrent_maintenance_runs_escalate_exactly_once(settings, storage, account):
    # H5: two maintenance runners serialize on BEGIN IMMEDIATE; one escalates.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-race", start_request=True)
    barrier = Barrier(2)

    def run_recovery(_):
        local = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            return local.release_or_requeue_expired_leases(
                now=NOW + timedelta(days=1)).escalated_reconciliation_count
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(run_recovery, range(2)))
    assert sum(counts) == 1
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    assert len(_events(storage, request_id)) == 1


def test_escalation_survives_reopen_and_is_idempotent(settings, storage, account):
    # H6 + H7: a fresh connection escalates the persisted crash state, a second
    # maintenance pass changes nothing, and the state survives another reopen.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-reopen", start_request=True)
    reopened = SqliteStorage.open(settings.db_path)
    try:
        first = reopened.release_or_requeue_expired_leases(now=NOW + timedelta(days=1))
        assert first.escalated_reconciliation_count == 1
        second = reopened.release_or_requeue_expired_leases(now=NOW + timedelta(days=2))
        assert second.escalated_reconciliation_count == 0
    finally:
        reopened.close()
    again = SqliteStorage.open(settings.db_path)
    try:
        assert _attempt_status(again, request_id) == "NEEDS_RECONCILIATION"
        assert len(_events(again, request_id)) == 1
    finally:
        again.close()


def test_escalated_attempts_are_visible_in_queue_and_cli(settings, storage, account, monkeypatch, capsys):
    # H8: both escalated crash windows appear in the operator queue and the CLI.
    _r, reserved_request = _crashed_attempt(storage, account, "esc-see-res", start_request=False)
    _s, started_request = _crashed_attempt(storage, account, "esc-see-req", start_request=True)
    _escalate(storage)
    listed = {a.request_id for a in storage.list_provider_attempts_needing_reconciliation(account_id=account.id)}
    assert {reserved_request, started_request} <= listed
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main(["list-reconciliations", "--account-id", account.id]) == 0
    out = capsys.readouterr().out
    assert reserved_request in out and started_request in out


def test_preview_works_on_escalated_attempts_and_pre_escalation_token_goes_stale(settings, storage, account):
    # H9 + H18: preview resolves the escalated state; a token taken before the
    # escalation can never confirm afterwards.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-token", start_request=True)
    stale_token = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
    ).version_token
    _escalate(storage)
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
    )
    assert preview.attempt_status is ProviderAttemptStatus.NEEDS_RECONCILIATION
    assert preview.reservation_active is True
    assert preview.event_count == 1
    with pytest.raises(ReconciliationPreviewStaleError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="operator", note="stale after escalation",
            expected_version_token=stale_token,
        )
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    fresh = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="fresh token works",
        expected_version_token=preview.version_token,
    )
    assert fresh.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED


def test_former_reserved_can_only_be_not_charged(settings, storage, account):
    # H10: a never-started attempt has a provable financial outcome, so
    # CHARGED_KNOWN and CHARGE_UNKNOWN fail closed; NOT_CHARGED resolves fully.
    execution, request_id = _crashed_attempt(storage, account, "esc-nc", start_request=False)
    _escalate(storage)
    for financial, cost in (
        (FinancialResolution.CHARGED_KNOWN, "0.020000"),
        (FinancialResolution.CHARGE_UNKNOWN, None),
    ):
        execution_res = (
            ExecutionResolution.EXECUTION_FAILED
            if financial is FinancialResolution.CHARGED_KNOWN
            else ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED
        )
        with pytest.raises(ProviderAttemptReconciliationError, match="can only be resolved NOT_CHARGED"):
            storage.resolve_provider_attempt_reconciliation(
                request_id=request_id, account_id=account.id, financial_resolution=financial,
                execution_resolution=execution_res, actual_cost_usd=cost,
                reconciled_by="operator", note="never-started must stay truthful",
            )
        assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="released after crash",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert result.attempt.request_started_at is None
    assert result.attempt.released_at is not None
    assert _run_status(storage, execution.run_id) == "FAILED"
    assert _research_status(storage, execution.run_id) == "FAILED"
    assert storage.get_job(execution.job_id).status is JobStatus.FAILED
    assert _attempt_count(storage, execution.job_id) == 1
    assert [e["event_type"] for e in _events(storage, request_id)] == [
        "AUTO_ESCALATION", "FINAL_RESOLUTION",
    ]
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 0


def test_charge_unknown_on_former_request_started_stays_visible(settings, storage, account):
    # H11: the operator may keep an escalated started attempt unresolved; it
    # remains in the queue and the observation history grows append-only.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-unknown", start_request=True)
    _escalate(storage)
    observed = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="operator", note="provider console pending",
    )
    assert observed.observed and not observed.idempotent
    assert observed.event.event_type is ReconciliationEventType.UNRESOLVED_OBSERVATION
    assert observed.event.sequence_number == 2
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"
    assert request_id in {
        a.request_id for a in storage.list_provider_attempts_needing_reconciliation(account_id=account.id)
    }


def test_charged_known_on_former_request_started_settles_ledger(settings, storage, account):
    # H12: a possibly-billed crash window settles into the canonical ledger.
    execution, request_id = _crashed_attempt(storage, account, "esc-ck", start_request=True)
    _escalate(storage)
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="operator", note="console shows a charge",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_SETTLED
    assert result.usage_id is not None
    canonical = storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE run_id=? AND dry_run=0 AND is_legacy_usage=0", (execution.run_id,),
    ).fetchone()[0]
    assert canonical == pytest.approx(0.02)
    assert storage.get_run(execution.run_id).cost_usd == pytest.approx(0.02)
    assert storage.get_research_run(execution.run_id).total_cost_usd == pytest.approx(0.02)
    assert _attempt_count(storage, execution.job_id) == 1


def test_escalated_reservation_blocks_budget_until_terminal_resolution(settings, storage, account):
    # H13 + H14: before resolution the escalated reservation still consumes the
    # global budget; after NOT_CHARGED it stops.  Proven functionally through
    # begin_provider_attempt with a tight monthly limit.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-budget", start_request=False)
    _escalate(storage)
    second = _execution(storage, account, "esc-budget-second")
    with pytest.raises(BudgetReservationError):
        storage.begin_provider_attempt(
            second, stage="research", attempt_no=1, max_cost_usd=0.1,
            daily_limit_usd=0.25, monthly_limit_usd=0.25,
        )
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="release the reservation",
    )
    active = storage.conn.execute(
        "SELECT COALESCE(SUM(reserved_amount_usd),0) FROM provider_attempts "
        "WHERE status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')",
    ).fetchone()[0]
    assert active == pytest.approx(0.0)
    attempt = storage.begin_provider_attempt(
        second, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=0.25, monthly_limit_usd=0.25,
    )
    assert attempt.status is ProviderAttemptStatus.RESERVED


def test_attempt_two_remains_blocked_after_escalation_and_resolution(settings, storage, account):
    # H15 + H16 + H17: escalation and resolution never authorize a retry, an
    # attempt #2 or any provider call.
    execution, request_id = _crashed_attempt(storage, account, "esc-attempt2", start_request=True)
    _escalate(storage)
    with pytest.raises((ProviderAttemptReconciliationRequired, StaleJobExecutionError)):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=2, max_cost_usd=0.2,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="operator", note="terminal after escalation",
    )
    with pytest.raises((ProviderAttemptReconciliationRequired, StaleJobExecutionError)):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=2, max_cost_usd=0.2,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
    assert _attempt_count(storage, execution.job_id) == 1


@pytest.mark.parametrize("fault", ["AFTER_ESCALATION_UPDATE", "AFTER_ESCALATION_EVENT", "BEFORE_COMMIT"])
def test_escalation_failure_rolls_back_the_whole_recovery(settings, storage, account, monkeypatch, fault):
    # H19: a fault inside the escalation leaves no partial durable state — the
    # job transition of the same recovery pass rolls back too.
    execution, request_id = _crashed_attempt(storage, account, f"esc-fault-{fault}", start_request=True)

    def interrupt(point):
        if point == fault:
            raise RuntimeError(f"forced escalation fault: {point}")

    monkeypatch.setattr(storage, "_recovery_fault_point", interrupt)
    with pytest.raises(RuntimeError, match="forced escalation fault"):
        _escalate(storage)
    assert storage.get_job(execution.job_id).status is JobStatus.RUNNING
    assert _attempt_status(storage, request_id) == "REQUEST_STARTED"
    assert _events(storage, request_id) == []
    monkeypatch.setattr(storage, "_recovery_fault_point", lambda point: None)
    result = _escalate(storage)
    assert result.escalated_reconciliation_count == 1
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"


def test_auto_escalation_event_is_append_only(settings, storage, account):
    # H20: the escalation audit record can be neither rewritten nor deleted.
    _execution_ctx, request_id = _crashed_attempt(storage, account, "esc-append", start_request=True)
    _escalate(storage)
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE reconciliation_events SET note='rewritten' WHERE request_id=?", (request_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "DELETE FROM reconciliation_events WHERE request_id=?", (request_id,),
        )
    storage.conn.rollback()


# ---- Section 19: W1A-SQLITE-01/02 — raw terminalization and ledger floor ------


def _raw_terminal_lifecycle(storage, execution, *, job_status="FAILED",
                            run_status="FAILED", research_status="FAILED"):
    """Craft a terminal-consistent lifecycle with raw SQL (no app involvement)."""
    storage.conn.execute(
        "UPDATE jobs SET status=?, lease_owner=NULL, lease_expires_at=NULL, "
        "reserved_cost_usd=0.0, budget_reserved_at=NULL WHERE id=?",
        (job_status, execution.job_id),
    )
    storage.conn.execute(
        "UPDATE runs SET status=?, finished_at='2026-07-15 12:00:00' WHERE id=?",
        (run_status, execution.run_id),
    )
    storage.conn.execute(
        "UPDATE research_runs SET status=? WHERE id=?", (research_status, execution.run_id),
    )


_RAW_RELEASE_SQL = (
    "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at='2026-07-15 12:00:00',"
    "reconciled_at='2026-07-15 12:00:00',reconciled_by=?,reconciliation_note=?,"
    "reconciliation_resolution='NOT_CHARGED:EXECUTION_FAILED' WHERE request_id=?"
)


def test_raw_terminalization_without_lifecycle_is_blocked(settings, storage, account):
    # I1: attempt flip with a live NEEDS_VERIFICATION job / RUNNING run.
    _execution_ctx, request_id = _needs_reconciliation(storage, account, "raw-nolife")
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(_RAW_RELEASE_SQL, ("op", "raw", request_id))
    storage.conn.rollback()
    assert _attempt_status(storage, request_id) == "NEEDS_RECONCILIATION"


def test_raw_terminalization_without_final_event_is_blocked(settings, storage, account):
    # I2: even with a fully consistent terminal lifecycle, the flip is rejected
    # without its exact FINAL_RESOLUTION event.
    execution, request_id = _needs_reconciliation(storage, account, "raw-noevent")
    _raw_terminal_lifecycle(storage, execution)
    with pytest.raises(sqlite3.IntegrityError, match="FINAL_RESOLUTION"):
        storage.conn.execute(_RAW_RELEASE_SQL, ("op", "raw", request_id))
    storage.conn.rollback()


def test_raw_terminalization_with_mismatched_final_event_is_blocked(settings, storage, account):
    # I3: a FINAL_RESOLUTION event that does not match operator/note/resolution
    # does not satisfy the terminal flip.
    execution, request_id = _needs_reconciliation(storage, account, "raw-badevent")
    _raw_terminal_lifecycle(storage, execution)
    storage.conn.execute(
        "INSERT INTO reconciliation_events (request_id,sequence_number,event_type,financial_resolution,"
        "execution_resolution,operator,note,previous_attempt_status,resulting_attempt_status,created_at,"
        "idempotency_key) VALUES (?,1,'FINAL_RESOLUTION','NOT_CHARGED','EXECUTION_FAILED','op',"
        "'a different note','NEEDS_RECONCILIATION','RECONCILED_RELEASED','2026-07-15 12:00:00','k-mismatch')",
        (request_id,),
    )
    with pytest.raises(sqlite3.IntegrityError, match="FINAL_RESOLUTION"):
        storage.conn.execute(_RAW_RELEASE_SQL, ("op", "raw", request_id))
    storage.conn.rollback()


def test_raw_settled_with_diverged_cost_cache_is_blocked(settings, storage, account):
    # I6: lifecycle + event + usage all consistent, but a cache that disagrees
    # with the canonical ledger blocks the terminal flip.
    execution, request_id = _needs_reconciliation(storage, account, "raw-cache")
    _seed_usage_row(storage, request_id, execution.run_id, estimated_cost_usd=0.05)
    _raw_terminal_lifecycle(storage, execution)
    storage.conn.execute(
        "UPDATE research_runs SET total_cost_usd=0.05 WHERE id=?", (execution.run_id,),
    )
    storage.conn.execute(
        "UPDATE runs SET cost_usd=0.999 WHERE id=?", (execution.run_id,),
    )
    storage.conn.execute(
        "INSERT INTO reconciliation_events (request_id,sequence_number,event_type,financial_resolution,"
        "execution_resolution,operator,note,previous_attempt_status,resulting_attempt_status,created_at,"
        "idempotency_key) VALUES (?,1,'FINAL_RESOLUTION','CHARGED_KNOWN','EXECUTION_FAILED','op','raw',"
        "'NEEDS_RECONCILIATION','RECONCILED_SETTLED','2026-07-15 12:00:00','k-cache')",
        (request_id,),
    )
    with pytest.raises(sqlite3.IntegrityError, match="cost caches"):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_SETTLED',settled_at='2026-07-15 12:00:00',"
            "reconciled_at='2026-07-15 12:00:00',reconciled_by='op',reconciliation_note='raw',"
            "reconciliation_resolution='CHARGED_KNOWN:EXECUTION_FAILED' WHERE request_id=?",
            (request_id,),
        )
    storage.conn.rollback()


def test_canonical_usage_is_immutable_after_reconciled_settled(settings, storage, account):
    # I7 + I9: cost, tokens and identity of the settled canonical usage are frozen.
    _execution_ctx, request_id = _reconciled_settled(storage, account, "raw-frozen")
    for mutation in (
        "UPDATE model_usage SET estimated_cost_usd=0.123456 WHERE request_id=?",
        "UPDATE model_usage SET input_tokens=999 WHERE request_id=?",
        "UPDATE model_usage SET provider='openai' WHERE request_id=?",
        "UPDATE model_usage SET model='other-model' WHERE request_id=?",
        "UPDATE model_usage SET task='chat' WHERE request_id=?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            storage.conn.execute(mutation, (request_id,))
        storage.conn.rollback()


def test_canonical_usage_cannot_be_deleted_after_reconciled_settled(settings, storage, account):
    # I8: the reviewer's exact counterprobe — delete after settlement.
    _execution_ctx, request_id = _reconciled_settled(storage, account, "raw-delete")
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        storage.conn.execute("DELETE FROM model_usage WHERE request_id=?", (request_id,))
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 1


def test_second_canonical_usage_cannot_be_added_after_reconciled_settled(settings, storage, account):
    # I10: a terminal attempt never gains new usage.
    execution, request_id = _reconciled_settled(storage, account, "raw-second")
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,output_tokens,"
            "cache_read_tokens,cache_write_tokens,web_search_requests,estimated_cost_usd,dry_run,"
            "request_id,is_legacy_usage,created_at) VALUES (?,?,?,?,0,0,0,0,0,?,0,?,0,?)",
            (execution.run_id, "anthropic", "reconciliation-model", "research",
             0.01, request_id, "2026-07-15 12:00:00"),
        )
    storage.conn.rollback()


def test_cost_caches_are_frozen_after_terminal_reconciliation(settings, storage, account):
    # I11: neither cache can drift away from the ledger after the terminal flip.
    execution, _request_id = _reconciled_settled(storage, account, "raw-cachefrozen")
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        storage.conn.execute(
            "UPDATE runs SET cost_usd=0.999 WHERE id=?", (execution.run_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        storage.conn.execute(
            "UPDATE research_runs SET total_cost_usd=0.999 WHERE id=?", (execution.run_id,),
        )
    storage.conn.rollback()


def test_qa_disproof_script_cleans_up_its_temp_directories():
    # W1A-QA-01: a full fresh-process run leaves no temp directories behind and
    # reports the cleanup explicitly (a leak flips the exit code to 1).
    import tempfile as _tempfile

    project_root = pathlib.Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "qa" / "reconciliation_lineage_disproof.py"
    result = subprocess.run(
        [sys.executable, str(script)], cwd=project_root,
        capture_output=True, text=True, env={**os.environ}, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEMP CLEANUP OK" in result.stdout
    assert list(pathlib.Path(_tempfile.gettempdir()).glob("nia-lineage-disproof-*")) == []


def test_preview_accepts_relative_and_absolute_db_paths(settings, storage, account, monkeypatch, tmp_path):
    _execution, request_id = _needs_reconciliation(storage, account, "paths")
    absolute_token = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
    ).version_token
    monkeypatch.chdir(tmp_path)
    relative = SqliteStorage.open(pathlib.Path("data") / "agent.db")
    try:
        relative_token = relative.preview_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
        ).version_token
    finally:
        relative.close()
    assert absolute_token == relative_token
