"""Offline acceptance contract for the ARTICLE_WRITER Fable-to-Opus switch.

No test in this module uses a provider SDK, network, or the production DB.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.content.foundation import ContentType
from app.model_routing import LogicalModelRole, ModelFamily, RoutingError
from app.model_routing.catalogue import OPUS_5
from app.model_routing.contracts import ROLE_FAMILY
from app.model_routing.production_qualification import (
    OPUS_PRODUCTION_QUALIFICATION_CONTRACT,
    OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON,
    execute_opus_production_qualification,
)
from app.model_routing.qualification import (
    QualificationProbeResponse,
    QualificationProbeUsage,
)
from app.storage.db import (
    ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION,
    ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION,
    ExplicitMigrationError,
    connect_existing_writable,
    database_schema_versions,
    initialize_database,
    migrate_0030_to_0031,
    migrate_0031_to_0032,
    migrate_0032_to_0033,
    migrate_0033_to_0034,
    migrate_0034_to_0035,
    migrate_0035_to_0036,
    migrate_0036_to_0037,
    migrate_0037_to_0038,
    migrate_0038_to_0039,
)
from app.storage.repositories import SqliteStorage
from tests.test_prec5_verified_catalogue_live_root import _approval, _entry_for
from tests.test_fable_production_qualification_caller import NOW as QUALIFICATION_NOW


WRITER = LogicalModelRole.ARTICLE_WRITER
FABLE_REQUEST_ID = "fable5-qualification-request-20260810-001"


def _open_0030(path):
    initialize_database(path, through=ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION)
    return SqliteStorage(connect_existing_writable(path))


def _seed_fable_history_and_binding(path):
    """Build a legal pre-switch binding and restore the fail-closed policy."""
    storage = _open_0030(path)
    storage.register_owner_verified_catalogue(verified_by="owner-test")
    original_policy = dict(storage.conn.execute(
        "SELECT * FROM model_role_policies WHERE role='ARTICLE_WRITER'"
    ).fetchone())

    refusal = _approval(
        storage,
        role=WRITER,
        family=ModelFamily.FABLE,
        request_id=FABLE_REQUEST_ID,
        cap="0.01",
    )
    storage.record_model_qualification_approval(refusal)
    refused = storage.execute_controlled_qualification(
        refusal,
        caller=lambda approval: QualificationProbeResponse(
            returned_model_id=approval.technical_model_id,
            structured_response_ok=False,
            stop_reason="refusal",
            usage=QualificationProbeUsage(input_tokens=151, output_tokens=3),
        ),
    )
    assert (refused.outcome, refused.failure_kind, refused.cost_usd) == (
        "FAIL", "PROVIDER_REFUSAL", Decimal("0.001660"),
    )

    passing = _approval(
        storage,
        role=WRITER,
        family=ModelFamily.FABLE,
        request_id="historical-fable-binding-pass",
        cap="1",
    )
    storage.record_model_qualification_approval(passing)
    passed = storage.execute_controlled_qualification(
        passing,
        caller=lambda approval: QualificationProbeResponse(
            returned_model_id=approval.technical_model_id,
            structured_response_ok=True,
            usage=QualificationProbeUsage(input_tokens=100, output_tokens=10),
        ),
    )
    fable = _entry_for(storage, ModelFamily.FABLE)
    storage.conn.execute(
        "UPDATE model_role_policies SET policy_version='historical-test',"
        "capability_verification_state='VERIFIED',require_structured_response=1,"
        "min_context_tokens=16000,min_output_tokens=2048,"
        "pricing_verification_state='VERIFIED',max_input_per_mtok='10.000000',"
        "max_output_per_mtok='50.000000',max_cache_read_per_mtok='1.000000',"
        "max_cache_write_per_mtok='12.500000',max_web_search_per_1k='10.000000',"
        "policy_fingerprint=? WHERE role='ARTICLE_WRITER'",
        ("a" * 64,),
    )
    storage.conn.execute(
        "UPDATE model_registry SET lifecycle_state='ACTIVE' WHERE registry_id=?",
        (fable["registry_id"],),
    )
    storage.conn.execute(
        "INSERT INTO model_role_activations VALUES (?,?,?,?)",
        (WRITER.value, fable["registry_id"], "2026-08-10T12:00:00+00:00", "b" * 64),
    )
    storage.conn.execute(
        "INSERT INTO model_intent_bindings (intent_kind,intent_id,role,"
        "model_registry_id,provider,family,logical_version,technical_model_id,"
        "pricing_ref,qualification_ref,capability_ref,"
        "activation_decision_fingerprint,fallback_policy,bound_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "content_writer", "historical-job:content_writer", WRITER.value,
            fable["registry_id"], "ANTHROPIC", "FABLE", "5", "claude-fable-5",
            fable["pricing_ref"], passed.qualification_ref,
            fable["current_capability_ref"], "b" * 64, "FORBIDDEN",
            "2026-08-10T12:00:01+00:00",
        ),
    )
    storage.conn.execute(
        "DELETE FROM model_role_activations WHERE role='ARTICLE_WRITER'"
    )
    storage.conn.execute(
        "UPDATE model_registry SET lifecycle_state='CANDIDATE' WHERE registry_id=?",
        (fable["registry_id"],),
    )
    columns = tuple(original_policy)
    storage.conn.execute(
        "UPDATE model_role_policies SET "
        + ",".join(f"{name}=?" for name in columns if name != "role")
        + " WHERE role=?",
        tuple(original_policy[name] for name in columns if name != "role")
        + (WRITER.value,),
    )
    storage.conn.commit()
    storage.close()


def test_canonical_and_default_writer_family_is_opus():
    assert ROLE_FAMILY[WRITER] is ModelFamily.OPUS
    assert OPUS_PRODUCTION_QUALIFICATION_CONTRACT.catalogue_entry is OPUS_5
    assert OPUS_5.technical_model_id == "claude-opus-5"
    assert OPUS_5.default_pricing_ref == "anthropic-opus-5-standard-2026-08"
    prices = OPUS_5.pricing[0].prices
    assert prices is not None
    assert prices.as_decimal_mapping() == {
        "input_per_mtok": Decimal("5.000000"),
        "output_per_mtok": Decimal("25.000000"),
        "cache_read_per_mtok": Decimal("0.500000"),
        "cache_write_per_mtok": Decimal("6.250000"),
        "web_search_per_1k": Decimal("10.000000"),
    }


def test_0031_preserves_fable_history_and_existing_frozen_binding(tmp_path):
    path = tmp_path / "history.db"
    _seed_fable_history_and_binding(path)
    before = connect_existing_writable(path)
    history_before = tuple(before.execute(
        "SELECT outcome,failure_kind,input_tokens,output_tokens,cost_usd "
        "FROM model_qualification_runs WHERE request_id=?",
        (FABLE_REQUEST_ID,),
    ).fetchone())
    result_before = tuple(before.execute(
        "SELECT state,source,result_fingerprint FROM model_qualification_results "
        "WHERE qualification_ref=?",
        (f"controlled-qual-{FABLE_REQUEST_ID}",),
    ).fetchone())
    before.close()

    assert migrate_0030_to_0031(path).applied_migrations == (
        ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION,
    )
    # Reach the current runtime floor before opening the strict runtime handle.
    migrate_0031_to_0032(path)
    migrate_0032_to_0033(path)
    migrate_0033_to_0034(path)
    migrate_0034_to_0035(path)
    migrate_0035_to_0036(path)
    migrate_0036_to_0037(path)
    migrate_0037_to_0038(path)
    migrate_0038_to_0039(path)
    from app.storage.db import migrate_0039_to_0040
    migrate_0039_to_0040(path)
    storage = SqliteStorage.open(path)
    try:
        assert tuple(storage.conn.execute(
            "SELECT outcome,failure_kind,input_tokens,output_tokens,cost_usd "
            "FROM model_qualification_runs WHERE request_id=?",
            (FABLE_REQUEST_ID,),
        ).fetchone()) == history_before == (
            "FAIL", "PROVIDER_REFUSAL", 151, 3, "0.001660",
        )
        assert tuple(storage.conn.execute(
            "SELECT state,source,result_fingerprint FROM model_qualification_results "
            "WHERE qualification_ref=?",
            (f"controlled-qual-{FABLE_REQUEST_ID}",),
        ).fetchone()) == result_before
        frozen = storage.freeze_content_writer_model_binding(
            job_id="historical-job", content_type=ContentType.ARTICLE,
        )
        assert frozen.family is ModelFamily.FABLE
        assert frozen.technical_model_id == "claude-fable-5"
        policy = storage.conn.execute(
            "SELECT * FROM model_role_policies WHERE role='ARTICLE_WRITER'"
        ).fetchone()
        assert (policy["allowed_family"], policy["qualification_required"],
                policy["fallback_policy"]) == ("OPUS", 1, "FORBIDDEN")
        assert policy["capability_verification_state"] == "UNVERIFIED"
        assert storage.conn.execute(
            "SELECT count(*) FROM model_role_activations WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_0031_is_explicit_idempotent_and_rejects_wrong_source(tmp_path):
    path = tmp_path / "explicit.db"
    initialize_database(path, through=ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION)
    first = migrate_0030_to_0031(path)
    second = migrate_0030_to_0031(path)
    assert first.idempotent is False and second.idempotent is True
    assert database_schema_versions(path)[-1] == ARTICLE_WRITER_OPUS_POLICY_SCHEMA_VERSION
    with pytest.raises(ExplicitMigrationError, match="requires exact"):
        old = tmp_path / "old.db"
        initialize_database(old, through="0029_verified_catalogue_and_controlled_roles")
        migrate_0030_to_0031(old)


def test_0031_rejects_policy_drift_without_partial_schema_or_ledger(tmp_path):
    path = tmp_path / "drift.db"
    initialize_database(path, through=ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION)
    conn = connect_existing_writable(path)
    conn.execute(
        "UPDATE model_role_policies SET policy_version='unexpected-drift' "
        "WHERE role='ARTICLE_WRITER'"
    )
    conn.commit()
    conn.close()

    with pytest.raises(ExplicitMigrationError, match="CHECK constraint failed"):
        migrate_0030_to_0031(path)
        migrate_0031_to_0032(path)
    assert database_schema_versions(path)[-1] == ANTHROPIC_PROVIDER_CONTRACT_SCHEMA_VERSION
    verify = connect_existing_writable(path)
    try:
        assert verify.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert verify.execute("PRAGMA foreign_key_check").fetchall() == []
        assert verify.execute(
            "SELECT policy_version FROM model_role_policies "
            "WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == "unexpected-drift"
    finally:
        verify.close()


def test_no_opus_activation_or_binding_before_separate_qualification(tmp_path):
    path = tmp_path / "closed.db"
    initialize_database(path)
    storage = SqliteStorage.open(path)
    try:
        storage.register_owner_verified_catalogue(verified_by="owner-test")
        with pytest.raises(RoutingError, match="ACTIVE_MODEL_MISSING"):
            storage.freeze_content_writer_model_binding(
                job_id="new-job", content_type=ContentType.ARTICLE,
            )
        assert storage.conn.execute(
            "SELECT count(*) FROM model_role_activations WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == 0
        assert storage.conn.execute(
            "SELECT count(*) FROM model_intent_bindings WHERE role='ARTICLE_WRITER'"
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_fake_opus_production_root_records_returned_identity_and_frozen_price(tmp_path):
    from tests.test_fable_production_qualification_caller import (
        FakeMessages,
        FakeSdkFactory,
        _seed_exact_authority,
    )

    path = tmp_path / "opus-root.db"
    initialize_database(path)
    storage = SqliteStorage.open(path)
    try:
        approval = _seed_exact_authority(storage)
        messages = FakeMessages(
            text=OPUS_QUALIFICATION_EXPECTED_RESPONSE_JSON,
            returned_model_id="claude-opus-5",
            input_tokens=151,
            output_tokens=3,
        )
        factory = FakeSdkFactory(messages)
        outcome = execute_opus_production_qualification(
            storage,
            approval,
            api_key_provider=lambda: "fake-secret",
            sdk_factory=factory,
            now=QUALIFICATION_NOW,
        )
        assert outcome.outcome == "PASS"
        assert outcome.returned_model_id == "claude-opus-5"
        assert outcome.pricing_ref == "anthropic-opus-5-standard-2026-08"
        assert outcome.cost_usd == Decimal("0.000830")
        assert len(factory.calls) == len(messages.calls) == 1
    finally:
        storage.close()
