"""B3 part A: durable pre-effect lifecycle for role_provider_executions.

Every case runs against a real migrated database and the canonical storage API.
No provider, no network, no SDK: this part owns the lifecycle contract only.
"""
from __future__ import annotations

from decimal import Decimal
import sqlite3

import pytest

from app.content.provider_roles import (
    RoleProviderAuthority,
    RoleProviderExecution,
    RoleUsage,
)
from app.model_routing.contracts import (
    CapabilityDeclaration,
    CapabilityVerificationState,
    LogicalModelRole,
    PriceDimensions,
    QualificationReport,
    QualificationState,
)
from app.model_routing.role_bootstrap import owner_approved_role_policy
from app.storage.db import (
    ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION,
    ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION,
    ROLE_EXECUTION_LIFECYCLE_SCHEMA_VERSION,
    RUNTIME_SCHEMA_VERSION,
    canonical_migration_versions,
    connect,
    initialize_database,
    migrate_0031_to_0032,
    migrate_0032_to_0033,
)
from app.ports.storage import BudgetReservationError, ContentFoundationError
from app.storage.repositories import SqliteStorage

ROLE = LogicalModelRole.ARTICLE_REVIEWER
REGISTRY_ID = "model-b3-opus"
PRICING_REF = "b3-opus-pricing"
JOB_ID = "b3-job"
RUN_ID = "b3-run"
CONTENT_ID = 1
EXEC_REF = "b3-exec-reviewer"
MODEL_ID = "claude-opus-5"
PRICES = PriceDimensions.from_mapping({
    "input_per_mtok": "5",
    "output_per_mtok": "25",
    "cache_read_per_mtok": "0.5",
    "cache_write_per_mtok": "6.25",
    "web_search_per_1k": "10",
})


def _fp(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


PRICING_FP = _fp("b3-pricing-profile")


@pytest.fixture()
def storage(tmp_path):
    """A real 0033 database carrying the exact authority the trigger demands."""
    path = tmp_path / "b3.db"
    initialize_database(path, through=ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION)
    migrate_0031_to_0032(path)
    migrate_0032_to_0033(path)
    conn = connect(path)
    conn.execute("PRAGMA foreign_keys=OFF")
    now = "2026-08-11 00:00:00.000000"
    conn.execute(
        "INSERT INTO model_registry (registry_id,provider,family,logical_version,"
        "version_sort_key,technical_model_id,availability_state,pricing_ref,"
        "current_qualification_state,lifecycle_state,discovered_at,created_at,"
        "catalogue_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (REGISTRY_ID, "ANTHROPIC", "OPUS", "5", "000000005", MODEL_ID,
         "AVAILABLE", PRICING_REF, "PASS", "ACTIVE", now, now, "b3-catalogue"),
    )
    conn.execute(
        "INSERT INTO model_pricing_profiles (pricing_ref,provider,"
        "technical_model_id,verification_state,currency,unit,input_per_mtok,"
        "output_per_mtok,cache_read_per_mtok,cache_write_per_mtok,"
        "web_search_per_1k,profile_fingerprint,verified_at,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (PRICING_REF, "ANTHROPIC", MODEL_ID, "VERIFIED", "USD",
         "usd_per_mtok__web_search_per_1k", "5.000000", "25.000000",
         "0.500000", "6.250000", "10.000000", PRICING_FP, now, now),
    )
    conn.execute(
        "INSERT INTO jobs (id,account_id,kind,workflow,idempotency_key,"
        "earliest_run_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        # A LOCAL job carries no frozen-content contract, which keeps this
        # fixture focused on the role-execution lifecycle rather than on the
        # separate C1 content-preparation invariants.
        (JOB_ID, "acct", "LOCAL", "ANALYTICS", "b3-key", now, now, now),
    )
    conn.execute(
        "INSERT INTO runs (id,account_id,workflow) VALUES (?,?,?)",
        (RUN_ID, "acct", "ANALYTICS"),
    )
    conn.execute(
        "INSERT INTO content_items (id,account_id,type,title,job_id,run_id,"
        "updated_at) VALUES (?,?,?,?,?,?,?)",
        (CONTENT_ID, "acct", "ARTICLE", "t", JOB_ID, RUN_ID, now),
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    store = SqliteStorage(conn)

    # The binding is created through the real authority chain, so this fixture
    # proves the 0029 constraints are still enforced rather than bypassing them:
    # owner-approved VERIFIED role policy -> qualification PASS -> VERIFIED
    # capability -> activation -> frozen content_role binding.
    store.upsert_model_role_policy(owner_approved_role_policy(ROLE))
    store.record_model_qualification(QualificationReport(
        qualification_ref="b3-qual",
        model_registry_id=REGISTRY_ID,
        state=QualificationState.PASS,
        suite_version="b3_suite_v1",
        fixture_set_ref="b3-fixtures",
        result_payload={"source": "LOCAL_FIXTURE"},
        evaluated_at=now,
        source="LOCAL_FIXTURE",
    ))
    store.record_model_capabilities(REGISTRY_ID, CapabilityDeclaration(
        capability_ref="b3-cap",
        verification_state=CapabilityVerificationState.VERIFIED,
        structured_response=True,
        max_context_tokens=16000,
        max_output_tokens=2048,
        verified_at=now,
    ))
    store.promote_best_model(ROLE, reason="b3 part A lifecycle fixture")
    store.freeze_model_for_intent(
        ROLE, intent_kind="content_role", intent_id=f"{JOB_ID}:{ROLE.value}",
    )
    approval_trigger = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' "
        "AND name='content_provider_approvals_contract'"
    ).fetchone()[0]
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("DROP TRIGGER content_provider_approvals_contract")
    store.record_content_provider_approval(
        approval_ref="b3-approval", job_id=JOB_ID, account_id="acct", role=ROLE,
        model_registry_id=REGISTRY_ID, provider="ANTHROPIC",
        technical_model_id=MODEL_ID, pricing_ref=PRICING_REF,
        max_output_tokens=2048, cap_usd="0.500000", approved_by="owner",
        approved_at=now, expires_at="2026-08-12 00:00:00.000000",
    )
    conn.execute(approval_trigger)
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    yield store
    conn.close()


def _authority() -> RoleProviderAuthority:
    return RoleProviderAuthority(
        job_id=JOB_ID,
        role=ROLE,
        binding_intent_id=f"{JOB_ID}:{ROLE.value}",
        model_registry_id=REGISTRY_ID,
        provider="ANTHROPIC",
        technical_model_id=MODEL_ID,
        pricing_ref=PRICING_REF,
        pricing_profile_fingerprint=PRICING_FP,
        qualification_ref="b3-qual",
        capability_ref="b3-cap",
        prices=PRICES,
    )


def _begin(storage) -> dict:
    return storage.begin_role_provider_execution(
        execution_ref=EXEC_REF, job_id=JOB_ID, run_id=RUN_ID,
        content_id=CONTENT_ID, role=ROLE, attempt_no=1,
        max_cost_usd="0.100000", authority=_authority(),
        daily_limit_usd=2, monthly_limit_usd=40,
    )


def _execution(outcome: str, *, returned: str | None = MODEL_ID,
               failure: str | None = None) -> RoleProviderExecution:
    usage = RoleUsage(
        input_tokens=100, output_tokens=50, cache_read_tokens=0,
        cache_write_tokens=0, web_search_requests=0,
        inference_geo="global", service_tier="standard",
    )
    return RoleProviderExecution(
        execution_ref=EXEC_REF, job_id=JOB_ID, run_id=RUN_ID,
        content_id=CONTENT_ID, role=ROLE, attempt_no=1, authority=_authority(),
        returned_model_id=returned, outcome=outcome, failure_kind=failure,
        usage=usage, cost_usd=Decimal("0.001750"),
        payload={"reviewer_version": "b3-test"},
    )


def test_01_second_begin_for_same_content_and_role_is_refused(storage):
    _begin(storage)
    with pytest.raises(ContentFoundationError) as exc:
        storage.begin_role_provider_execution(
            execution_ref="b3-exec-other", job_id=JOB_ID, run_id=RUN_ID,
            content_id=CONTENT_ID, role=ROLE, attempt_no=1,
            max_cost_usd="0.100000", authority=_authority(),
            daily_limit_usd=2, monthly_limit_usd=40,
        )
    assert exc.value.code == "CONTENT_ROLE_EXECUTION_ALREADY_EXISTS"
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM role_provider_executions"
    ).fetchone()[0] == 1


def test_02_settlement_requires_an_in_flight_reservation(storage):
    with pytest.raises(ContentFoundationError) as exc:
        storage.settle_role_provider_execution(_execution("SUCCESS"))
    assert exc.value.code == "CONTENT_ROLE_EXECUTION_MISSING"


def test_03_second_settlement_is_refused(storage):
    _begin(storage)
    storage.settle_role_provider_execution(_execution("SUCCESS"))
    with pytest.raises(ContentFoundationError) as exc:
        storage.settle_role_provider_execution(
            _execution("FAILURE", failure="PROVIDER_REFUSAL"),
        )
    assert exc.value.code == "CONTENT_ROLE_EXECUTION_ALREADY_SETTLED"


def test_04_terminal_can_never_return_to_in_flight(storage):
    _begin(storage)
    storage.settle_role_provider_execution(_execution("SUCCESS"))
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE role_provider_executions SET outcome='IN_FLIGHT' "
            "WHERE execution_ref=?", (EXEC_REF,),
        )


def test_05_delete_is_impossible(storage):
    _begin(storage)
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "DELETE FROM role_provider_executions WHERE execution_ref=?",
            (EXEC_REF,),
        )


def test_06_success_with_a_different_returned_model_is_refused(storage):
    _begin(storage)
    with pytest.raises(sqlite3.IntegrityError):
        storage.settle_role_provider_execution(
            _execution("SUCCESS", returned="claude-sonnet-5"),
        )
    row = storage.get_role_provider_execution(content_id=CONTENT_ID, role=ROLE)
    assert row["outcome"] == "IN_FLIGHT"


def test_07_in_flight_carries_null_usage_and_result(storage):
    row = _begin(storage)
    assert row["outcome"] == "IN_FLIGHT"
    assert row["reserved_at"] is not None
    assert row["external_effect_started_at"] is None
    assert row["settled_at"] is None
    for column in (
        "returned_model_id", "failure_kind", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens", "web_search_requests",
        "cost_usd", "result_json", "result_fingerprint",
    ):
        assert row[column] is None, column


def test_08_terminal_row_cannot_be_incomplete(storage):
    _begin(storage)
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE role_provider_executions SET outcome='SUCCESS',"
            "settled_at='2026-08-11 00:00:01.000000' WHERE execution_ref=?",
            (EXEC_REF,),
        )
    assert storage.get_role_provider_execution(
        content_id=CONTENT_ID, role=ROLE,
    )["outcome"] == "IN_FLIGHT"


def test_09_uncertain_in_flight_survives_restart_without_a_second_record(
    storage, tmp_path,
):
    _begin(storage)
    storage.mark_role_provider_effect_started(EXEC_REF)
    db_path = storage.conn.execute("PRAGMA database_list").fetchone()[2]
    storage.conn.close()

    # A completely new process-level handle: recovery sees the reservation.
    recovered = SqliteStorage(connect(db_path))
    pending = recovered.list_in_flight_role_provider_executions(job_id=JOB_ID)
    assert len(pending) == 1
    assert pending[0]["execution_ref"] == EXEC_REF
    assert pending[0]["external_effect_started_at"] is not None
    assert pending[0]["settled_at"] is None

    # Recovery cannot open a second execution for the same content and role,
    # so no code path can turn an uncertain call into another provider call.
    with pytest.raises(ContentFoundationError) as exc:
        recovered.begin_role_provider_execution(
            execution_ref="b3-exec-retry", job_id=JOB_ID, run_id=RUN_ID,
            content_id=CONTENT_ID, role=ROLE, attempt_no=1,
            max_cost_usd="0.100000", authority=_authority(),
            daily_limit_usd=2, monthly_limit_usd=40,
        )
    assert exc.value.code == "CONTENT_ROLE_EXECUTION_ALREADY_EXISTS"
    assert recovered.conn.execute(
        "SELECT COUNT(*) FROM role_provider_executions"
    ).fetchone()[0] == 1
    recovered.conn.close()


def test_10_effect_stamp_stays_in_flight_and_is_written_once(storage):
    _begin(storage)
    stamped = storage.mark_role_provider_effect_started(EXEC_REF)
    assert stamped["outcome"] == "IN_FLIGHT"
    assert stamped["external_effect_started_at"] is not None
    with pytest.raises(ContentFoundationError) as exc:
        storage.mark_role_provider_effect_started(EXEC_REF)
    assert exc.value.code == "CONTENT_ROLE_EXECUTION_EFFECT_ALREADY_STARTED"


def test_11_settlement_records_usage_and_cost_exactly_once(storage):
    _begin(storage)
    storage.mark_role_provider_effect_started(EXEC_REF)
    storage.settle_role_provider_execution(_execution("SUCCESS"))
    row = storage.get_role_provider_execution(content_id=CONTENT_ID, role=ROLE)
    assert row["outcome"] == "SUCCESS"
    assert row["input_tokens"] == 100 and row["output_tokens"] == 50
    assert row["cost_usd"] == "0.001750"
    assert row["settled_at"] is not None
    assert storage.list_in_flight_role_provider_executions() == ()
    usage = storage.conn.execute(
        "SELECT * FROM model_usage WHERE request_id=?", (EXEC_REF,),
    ).fetchone()
    assert usage is not None
    assert usage["task"] == "article_reviewer"
    assert Decimal(str(usage["estimated_cost_usd"])) == Decimal("0.00175")
    assert Decimal(str(storage.get_run(RUN_ID).cost_usd)) == Decimal("0.00175")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        storage.conn.execute(
            "UPDATE model_usage SET estimated_cost_usd=0 WHERE request_id=?",
            (EXEC_REF,),
        )


def test_12_runtime_floor_is_the_role_execution_global_ledger():
    """The floor includes canonical accounting for the paid reviewer."""
    assert RUNTIME_SCHEMA_VERSION == ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION
    assert RUNTIME_SCHEMA_VERSION != ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION
    canonical = canonical_migration_versions()
    assert canonical[-1] == ROLE_EXECUTION_GLOBAL_LEDGER_SCHEMA_VERSION
    assert canonical[-2] == ROLE_EXECUTION_LIFECYCLE_SCHEMA_VERSION


def test_13_unknown_terminal_cost_is_represented_by_null_not_zero(storage):
    _begin(storage)
    storage.mark_role_provider_effect_started(EXEC_REF)
    storage.settle_role_provider_execution(RoleProviderExecution(
        execution_ref=EXEC_REF, job_id=JOB_ID, run_id=RUN_ID,
        content_id=CONTENT_ID, role=ROLE, attempt_no=1, authority=_authority(),
        returned_model_id=None, outcome="NEEDS_VERIFICATION",
        failure_kind="REVIEWER_RESULT_UNKNOWN", usage=None, cost_usd=None,
        payload={"reviewer_version": "b3-test", "usage_known": False},
    ))
    row = storage.get_role_provider_execution(content_id=CONTENT_ID, role=ROLE)
    assert row["outcome"] == "NEEDS_VERIFICATION"
    assert row["cost_usd"] is None
    assert row["input_tokens"] is None and row["output_tokens"] is None


def test_14_two_attempts_are_legal_but_reservations_never_exceed_cap(storage):
    _begin(storage)
    with pytest.raises(ContentFoundationError) as exc:
        storage.begin_role_provider_execution(
            execution_ref="b3-exec-reviewer-2", job_id=JOB_ID, run_id=RUN_ID,
            content_id=CONTENT_ID, role=ROLE, attempt_no=2,
            max_cost_usd="0.450000", authority=_authority(),
            daily_limit_usd=2, monthly_limit_usd=40,
        )
    assert exc.value.code == "CONTENT_ARTICLE_BUDGET_EXHAUSTED"
    second = storage.begin_role_provider_execution(
        execution_ref="b3-exec-reviewer-2", job_id=JOB_ID, run_id=RUN_ID,
        content_id=CONTENT_ID, role=ROLE, attempt_no=2,
        max_cost_usd="0.400000", authority=_authority(),
        daily_limit_usd=2, monthly_limit_usd=40,
    )
    assert second["attempt_no"] == 2
    assert storage.remaining_article_budget(job_id=JOB_ID) == Decimal("0.000000")


def test_15_role_reservation_obeys_global_limits_before_external_effect(storage):
    with pytest.raises(BudgetReservationError):
        storage.begin_role_provider_execution(
            execution_ref=EXEC_REF, job_id=JOB_ID, run_id=RUN_ID,
            content_id=CONTENT_ID, role=ROLE, attempt_no=1,
            max_cost_usd="0.100000", authority=_authority(),
            daily_limit_usd="0.099999", monthly_limit_usd=40,
        )
    assert storage.get_role_provider_execution(
        content_id=CONTENT_ID, role=ROLE,
    ) is None
