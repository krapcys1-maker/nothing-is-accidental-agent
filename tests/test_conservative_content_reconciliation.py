"""Owner conservative adjudication over production-shaped fake effects only."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

import pytest

from app.content.conservative_reconciliation import ConservativeReconciliationError
from app.content.review_only import (
    ReviewOnlyAuthority,
    ReviewOnlyError,
    run_controlled_article_review_only,
)
from app.models import ModelUsage
from app.ports.storage import ContentFoundationError
from scripts.reconcile_conservative_content import main as reconcile_main
from tests.test_b3_production_reviewer import (
    NOW,
    ReviewerTransport,
    WriterTransport,
    _execution,
    _run,
)


class UnknownWriterTransport(WriterTransport):
    """The fake FINAL boundary times out after the durable effect marker."""

    def __call__(self, _client, _request):
        self.calls += 1
        raise TimeoutError("fake writer result is unknown")


def _resolve(storage, source_type: str, identity: str, amount: str, *, reason="owner max"):
    return storage.resolve_conservative_content_reconciliation(
        source_type=source_type,
        source_identity=identity,
        expected_reserved_amount_usd=amount,
        approved_by="owner-test",
        approved_at="2026-08-13T12:00:00.000000+00:00",
        reason=reason,
        now=datetime(2026, 8, 13, 12, 1, tzinfo=timezone.utc),
    )


def _dummy_review_authority(job_id: str) -> ReviewOnlyAuthority:
    return ReviewOnlyAuthority(
        job_id=job_id,
        content_id=1,
        draft_fingerprint="a" * 64,
        approval_ref="no-live-approval",
        initial_review_execution_ref=f"{job_id}:ARTICLE_REVIEWER:1",
        writer_execution_ref=f"{job_id}:content_draft:2",
        post_review_execution_ref=f"{job_id}:ARTICLE_REVIEWER:2",
        approved_by="owner-test",
        approved_at="2026-08-13T12:00:00.000000+00:00",
        expires_at="2026-08-13T12:30:00.000000+00:00",
        cost_ceiling_usd="0.500000",
    )


def test_three_ambiguous_effects_resolve_to_exact_conservative_checkpoint(
    storage, settings, account, monkeypatch,
):
    # Reproduce the persisted v1 envelope (8k input / 2048 output) that existed
    # when the historical timeout occurred.  This modifies test-module globals
    # only; production code and provider configuration remain untouched.
    import app.content.controlled_entrypoint as controlled_entrypoint

    monkeypatch.setattr(controlled_entrypoint, "ARTICLE_WRITER_MAX_INPUT_TOKENS", 8_000)
    monkeypatch.setattr(controlled_entrypoint, "ARTICLE_WRITER_MAX_OUTPUT_TOKENS", 2_048)
    writer = UnknownWriterTransport()
    _, writer_outcome = _run(
        storage, settings, account, job="conservative-writer-v1",
        writer=writer, reviewer=ReviewerTransport(),
    )
    assert writer.calls == 1
    writer_request = f"{writer_outcome.job_id}:content_draft:1"
    writer_row = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE request_id=?", (writer_request,),
    ).fetchone()
    assert writer_row["status"] == "NEEDS_RECONCILIATION"
    assert Decimal(str(writer_row["reserved_amount_usd"])) == Decimal("0.091200")
    assert writer_row["actual_cost_usd"] is None

    import tests.test_b3_production_reviewer as b3_root
    monkeypatch.setattr(b3_root, "_activate_article_roles", lambda _storage: None)
    role_rows = []
    for suffix in ("v4", "v5"):
        local_account = account.model_copy(update={"id": f"account-{suffix}"})
        local_settings = replace(
            settings, accounts={local_account.id: local_account},
        )
        reviewer = ReviewerTransport(raise_error=TimeoutError("fake unknown reviewer"))
        _, outcome = _run(
            storage, local_settings, local_account,
            job=f"conservative-reviewer-{suffix}",
            writer=WriterTransport(), reviewer=reviewer,
        )
        state = storage.get_content_pipeline_state(outcome.job_id)
        assert reviewer.calls == 1, (
            state["content"]["status"], state["content"]["reason_code"],
            state["job"]["status"], state["job"]["last_error"],
        )
        row = _execution(storage, outcome.job_id)
        assert row["outcome"] == "NEEDS_VERIFICATION"
        assert row["cost_usd"] is None
        assert Decimal(str(row["reserved_cost_usd"])) == Decimal("0.323840")
        role_rows.append(row)

    assert storage.unresolved_provider_exposure() == Decimal("0.738880")

    # The exact checkpoint is represented by confirmed local usage rows only;
    # this synthetic delta is a fake, temporary usage fixture, never a charge.
    actual_before = storage.actual_known_cost_usd()
    delta = Decimal("5.172339") - actual_before
    assert delta > 0
    run_id = str(role_rows[0]["run_id"])
    storage.add_model_usage(ModelUsage(
        run_id=run_id,
        provider="fake-confirmed-ledger",
        model="fake-confirmed-model",
        task="research",
        input_tokens=1,
        estimated_cost_usd=float(delta),
        dry_run=True,
        request_id="fake-known-cost-checkpoint",
        created_at=NOW,
    ))
    assert storage.actual_known_cost_usd() == Decimal("5.172339")

    secret_calls = 0

    def forbidden_secret():
        nonlocal secret_calls
        secret_calls += 1
        raise AssertionError("REVIEW-ONLY must stop before secret/SDK")

    with pytest.raises(ReviewOnlyError) as blocked:
        run_controlled_article_review_only(
            settings=settings,
            authority=_dummy_review_authority("missing-review-job"),
            api_key_provider=forbidden_secret,
        )
    assert blocked.value.code == "REVIEW_ONLY_RECONCILIATION_REQUIRED"
    assert secret_calls == 0

    first = _resolve(storage, "PROVIDER_ATTEMPT", writer_request, "0.091200")
    assert first.record.actual_cost_usd is None
    assert first.record.conservative_cost_usd == first.record.reserved_amount_usd
    assert storage.unresolved_provider_exposure() == Decimal("0.647680")

    second = _resolve(
        storage, "ROLE_EXECUTION", str(role_rows[0]["execution_ref"]), "0.323840",
    )
    assert storage.unresolved_provider_exposure() == Decimal("0.323840")
    third = _resolve(
        storage, "ROLE_EXECUTION", str(role_rows[1]["execution_ref"]), "0.323840",
    )
    assert second.record.source_identity != third.record.source_identity

    summary = storage.conservative_cost_summary()
    assert summary.actual_known_cost_usd == Decimal("5.172339")
    assert summary.conservative_adjudicated_cost_usd == Decimal("0.738880")
    assert summary.effective_budget_spend_usd == Decimal("5.911219")
    assert summary.unresolved_provider_exposure_usd == Decimal("0.000000")
    assert len(storage.list_conservative_content_reconciliations()) == 3

    # Source facts remain unknown and non-retryable; only the separate budget
    # adjudication is terminal.  REVIEW-ONLY can pass the exposure guard, but
    # this probe deliberately stops on missing local lineage before any SDK.
    assert storage.conn.execute(
        "SELECT status,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (writer_request,),
    ).fetchone()[0] == "NEEDS_RECONCILIATION"
    assert all(
        storage.conn.execute(
            "SELECT outcome FROM role_provider_executions WHERE execution_ref=?",
            (row["execution_ref"],),
        ).fetchone()[0] == "NEEDS_VERIFICATION"
        for row in role_rows
    )
    with pytest.raises(ContentFoundationError) as local_stop:
        run_controlled_article_review_only(
            settings=settings,
            authority=_dummy_review_authority("missing-review-job"),
            api_key_provider=forbidden_secret,
        )
    assert local_stop.value.code == "CONTENT_JOB_MISSING"
    assert secret_calls == 0

    identical = _resolve(storage, "PROVIDER_ATTEMPT", writer_request, "0.091200")
    assert identical.idempotent is True
    assert identical.record.reconciliation_id == first.record.reconciliation_id
    with pytest.raises(ConservativeReconciliationError, match="conflicting"):
        _resolve(
            storage, "PROVIDER_ATTEMPT", writer_request, "0.091200",
            reason="different owner payload",
        )
    for invalid in ("0", "-0.1", "0.010000", "0.100000"):
        with pytest.raises(ConservativeReconciliationError):
            storage.preview_conservative_content_reconciliation(
                source_type="PROVIDER_ATTEMPT",
                source_identity=writer_request,
                expected_reserved_amount_usd=invalid,
                approved_by="owner-test",
                approved_at="2026-08-13T12:00:00+00:00",
                reason="invalid amount",
            )
    with pytest.raises(ConservativeReconciliationError):
        storage.preview_conservative_content_reconciliation(
            source_type="ROLE_EXECUTION",
            source_identity=writer_request,
            expected_reserved_amount_usd="0.091200",
            approved_by="owner-test",
            approved_at="2026-08-13T12:00:00+00:00",
            reason="wrong source identity",
        )

    reconciliation_id = first.record.reconciliation_id
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        storage.conn.execute(
            "UPDATE conservative_content_reconciliations SET reason='changed' "
            "WHERE reconciliation_id=?", (reconciliation_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        storage.conn.execute(
            "DELETE FROM conservative_content_reconciliations WHERE reconciliation_id=?",
            (reconciliation_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE conservative_content_reconciliations "
            "SET resolution='NOT_CHARGED' WHERE reconciliation_id=?",
            (reconciliation_id,),
        )
    storage.conn.rollback()
    assert storage.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert storage.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_operator_entrypoint_previews_then_confirms_exactly_one_record(
    storage, settings, account, capsys,
):
    reviewer = ReviewerTransport(raise_error=TimeoutError("fake unknown reviewer"))
    _, outcome = _run(
        storage, settings, account, job="conservative-cli-role",
        writer=WriterTransport(), reviewer=reviewer,
    )
    row = _execution(storage, outcome.job_id)
    args = [
        "--db-path", str(settings.db_path),
        "--source-type", "ROLE_EXECUTION",
        "--execution-ref", str(row["execution_ref"]),
        "--expected-reserved-amount-usd", "0.323840",
        "--approved-by", "owner-test",
        "--approved-at", "2026-08-13T12:00:00+00:00",
        "--reason", "panel is aggregate-only",
    ]
    storage.close()
    assert reconcile_main(args) == 0
    assert "PREVIEW ONLY" in capsys.readouterr().out
    check = sqlite3.connect(settings.db_path)
    assert check.execute(
        "SELECT count(*) FROM conservative_content_reconciliations"
    ).fetchone()[0] == 0
    check.close()

    assert reconcile_main(args + ["--confirm-conservative-max-charged"]) == 0
    output = capsys.readouterr().out
    assert "provider_call=false inference=false review_only=false publication=false" in output
    check = sqlite3.connect(settings.db_path)
    assert check.execute(
        "SELECT count(*) FROM conservative_content_reconciliations"
    ).fetchone()[0] == 1
    check.close()
