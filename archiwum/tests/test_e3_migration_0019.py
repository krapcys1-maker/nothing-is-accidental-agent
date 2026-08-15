"""Migracja 0019: generalizacja controlled_fetch_approvals (E3).

Pokrycie: świeża drabina 0001->0019, jawny upgrade 0018->0019 z zachowanym
bajt-w-bajt istniejącym approvalem CONTROLLED_FETCH, rollback schema+ledger
przy awarii w trakcie migracji, podłoga preimage-hash i bind trigger gałęzi
EVIDENCE_RESEARCH oraz nienaruszona referencja FK controlled_fetch_attempts.
Wszystko na nowych tymczasowych bazach.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.research.controlled_fetch_intent import ControlledFetchIntent
from app.storage.db import (
    CONTROLLED_FETCH_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_SCHEMA_VERSION,
    ExplicitMigrationError,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0018_to_0019,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def _seed_fetch_approval_at_0018(conn: sqlite3.Connection) -> dict:
    """Buduje na 0018 konto/temat/job controlled_fetch_v1 + skonsumowany approval."""
    conn.execute(
        "INSERT INTO accounts (id,name,mode,autonomy_level,active,"
        "browser_profile_path,writing_profile_path) VALUES "
        "('nothing_is_accidental','NIA','FULL_PUBLICATION','LEVEL_1',1,'','')"
    )
    cursor = conn.execute(
        "INSERT INTO topics (account_id,title,status,created_at) VALUES "
        "('nothing_is_accidental','Fetch topic','SELECTED','2026-07-19 10:00:00')"
    )
    topic_id = int(cursor.lastrowid)
    intent = ControlledFetchIntent.build(
        account_id="nothing_is_accidental", topic_id=topic_id,
        source_identity="doc", requested_url="https://fetch.example/doc",
        timeout_seconds=10, max_bytes=1000, max_redirects=1,
        allowed_content_types=["text/html", "text/plain"],
        requested_at=NOW, expires_at=NOW + timedelta(hours=2),
    )
    payload = {
        "account_id": "nothing_is_accidental", "topic_id": topic_id,
        "dry_run": False, "execution": "controlled_fetch_v1",
        "execution_intent": intent.as_payload(),
    }
    conn.execute(
        "INSERT INTO jobs (id,account_id,kind,workflow,status,priority,"
        "idempotency_key,topic_id,run_id,payload_json,schedule_reason,"
        "earliest_run_at,deadline_at,lease_owner,lease_expires_at,attempts,"
        "max_attempts,reserved_cost_usd,budget_reserved_at,"
        "external_effect_started_at,last_error,created_at,started_at,"
        "finished_at,updated_at) VALUES "
        "('fetch-legacy-job','nothing_is_accidental','RESEARCH','RESEARCH',"
        "'QUEUED',0,'fetch-legacy',?,NULL,?,'WITHIN_EDITORIAL_WINDOW',"
        "'2026-07-19 10:00:00',NULL,NULL,NULL,0,1,0.0,NULL,NULL,NULL,"
        "'2026-07-19 10:00:00',NULL,NULL,'2026-07-19 10:00:00')",
        (topic_id, json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))),
    )
    conn.execute(
        "INSERT INTO controlled_fetch_approvals (job_id,account_id,action_type,"
        "requested_url,intent_fingerprint,timeout_seconds,max_bytes,"
        "max_redirects,approved_by,approved_at,expires_at,consumed_at) VALUES "
        "('fetch-legacy-job','nothing_is_accidental','CONTROLLED_FETCH',?,?,"
        "10,1000,1,'human-l1','2026-07-19 10:05:00','2026-07-19 14:00:00',NULL)",
        (intent.requested_url, intent.fingerprint),
    )
    conn.execute(
        "UPDATE controlled_fetch_approvals SET consumed_at='2026-07-19 10:10:00' "
        "WHERE job_id='fetch-legacy-job'"
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM controlled_fetch_approvals WHERE job_id='fetch-legacy-job'"
    ).fetchone()
    return dict(zip([c[0] for c in conn.execute(
        "SELECT * FROM controlled_fetch_approvals LIMIT 0"
    ).description], row))


def test_upgrade_0018_to_0019_preserves_the_fetch_approval_byte_for_byte(tmp_path):
    path = tmp_path / "upgrade.db"
    initialize_database(path, through=CONTROLLED_FETCH_SCHEMA_VERSION)
    conn = connect(path)
    try:
        before = _seed_fetch_approval_at_0018(conn)
    finally:
        conn.close()

    result = migrate_0018_to_0019(path)
    assert result.applied_migrations == (EVIDENCE_RESEARCH_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == EVIDENCE_RESEARCH_SCHEMA_VERSION

    conn = connect(path)
    try:
        conn.row_factory = sqlite3.Row
        after = dict(conn.execute(
            "SELECT * FROM controlled_fetch_approvals WHERE job_id='fetch-legacy-job'"
        ).fetchone())
        for key, value in before.items():
            assert after[key] == value, key
        assert after["topic_id"] is None
        assert after["execution_intent_json"] is None
        # FK controlled_fetch_attempts nadal wskazuje odbudowaną tabelę.
        attempts_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='controlled_fetch_attempts'"
        ).fetchone()[0]
        assert "_0018_old" not in attempts_sql
        assert "controlled_fetch_approvals" in attempts_sql
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # Kontrakt consume-exactly-once nie zregresował: zużytej zgody nie
        # można ani odświeżyć, ani cofnąć, ani usunąć.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE controlled_fetch_approvals SET consumed_at=NULL "
                "WHERE job_id='fetch-legacy-job'"
            )
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM controlled_fetch_approvals "
                "WHERE job_id='fetch-legacy-job'"
            )
        conn.rollback()
        # Idempotentne ponowienie kroku.
        rerun = migrate_0018_to_0019(path)
        assert rerun.idempotent is True
    finally:
        conn.close()


def test_migration_fault_rolls_back_schema_and_ledger(tmp_path):
    path = tmp_path / "fault.db"
    initialize_database(path, through=CONTROLLED_FETCH_SCHEMA_VERSION)
    conn = connect(path)
    try:
        _seed_fetch_approval_at_0018(conn)
        # Wymuszona awaria W ŚRODKU transakcji migracji: docelowa nazwa
        # tymczasowa już istnieje, więc ALTER ... RENAME pada po DROP TRIGGER.
        conn.execute("CREATE TABLE controlled_fetch_approvals_0018_old (id INTEGER)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ExplicitMigrationError):
        migrate_0018_to_0019(path)

    assert database_schema_versions(path)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    conn = connect(path)
    try:
        columns = [row[1] for row in conn.execute(
            "PRAGMA table_info(controlled_fetch_approvals)"
        )]
        # Schemat pozostał na kontrakcie 0018 (bez kolumn gałęzi evidence).
        assert "execution_intent_json" not in columns
        triggers = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
        # Zdropowane na początku skryptu triggery wróciły wraz z rollbackiem.
        assert "controlled_fetch_approvals_consume_exactly_once" in triggers
        assert "controlled_fetch_attempts_bind_consumed_approval" in triggers
        row = conn.execute(
            "SELECT consumed_at FROM controlled_fetch_approvals "
            "WHERE job_id='fetch-legacy-job'"
        ).fetchone()
        assert row[0] == "2026-07-19 10:10:00"
    finally:
        conn.close()


def test_closed_production_orchestrator_is_permanently_retired_by_0019():
    """W repo z 0019 zamknięty orchestrator 0014->0018 odmawia fail-closed.

    Jego kontrakt preflight zamroził dokładną drabinę 0001..0018 — dodanie
    0019 czyni wykonane narzędzie trwale nieuruchamialnym (celowo; realna
    migracja 0014->0018 została już wykonana i nie może się powtórzyć).
    """
    from app.operations.production_schema_migration import (
        ProductionMigrationError,
        _validate_migration_contract,
    )

    with pytest.raises(ProductionMigrationError) as caught:
        _validate_migration_contract()
    assert caught.value.code == "MIGRATION_CONTRACT_INVALID"


def test_evidence_branch_floors_hash_bind_and_matrix(tmp_path):
    path = tmp_path / "floors.db"
    initialize_database(path)
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO accounts (id,name,mode,autonomy_level,active,"
            "browser_profile_path,writing_profile_path) VALUES "
            "('nothing_is_accidental','NIA','FULL_PUBLICATION','LEVEL_1',1,'','')"
        )
        cursor = conn.execute(
            "INSERT INTO topics (account_id,title,status,created_at) VALUES "
            "('nothing_is_accidental','T','SELECTED','2026-07-19 10:00:00')"
        )
        topic_id = int(cursor.lastrowid)
        conn.commit()
        insert = (
            "INSERT INTO controlled_fetch_approvals (job_id,account_id,"
            "action_type,requested_url,intent_fingerprint,timeout_seconds,"
            "max_bytes,max_redirects,topic_id,execution_intent_json,"
            "approved_by,approved_at,expires_at,consumed_at) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)"
        )
        preimage = '{"k":"v"}'
        import hashlib

        good_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
        # Bez pasującego joba durable evidence bind trigger odmawia nawet przy
        # poprawnym hashu preimage.
        with pytest.raises(sqlite3.IntegrityError, match="must bind one durable"):
            conn.execute(insert, (
                "no-such-job", "nothing_is_accidental", "EVIDENCE_RESEARCH",
                None, good_hash, None, None, None, topic_id, preimage,
                "owner", "2026-07-19 10:00:00", "2026-07-19 12:00:00",
            ))
        conn.rollback()
        # Macierz gałęzi: EVIDENCE_RESEARCH bez preimage jest niereprezentowalny.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (
                "no-such-job", "nothing_is_accidental", "EVIDENCE_RESEARCH",
                None, good_hash, None, None, None, topic_id, None,
                "owner", "2026-07-19 10:00:00", "2026-07-19 12:00:00",
            ))
        conn.rollback()
        # CONTROLLED_FETCH nie może przemycić kolumn evidence.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, (
                "no-such-job", "nothing_is_accidental", "CONTROLLED_FETCH",
                "https://fetch.example/doc", good_hash, 10, 1000, 1,
                topic_id, preimage,
                "owner", "2026-07-19 10:00:00", "2026-07-19 12:00:00",
            ))
        conn.rollback()
        # Fałszywy fingerprint preimage odpada na podłodze evidence_sha256_hex,
        # niezależnie od aplikacji.
        from app.research.durable_intent import (
            DurableResearchExecutionIntent,
            evidence_input_payload,
        )
        from types import SimpleNamespace

        # Prawdziwy job evidence, żeby dojść aż do podłogi hasha.
        conn.execute(
            "INSERT INTO evidence_retrievals (account_id,requested_url,final_url,"
            "fetched_at,status,http_status,content_type,fetch_error,raw_size_bytes,"
            "raw_sha256,extracted_chars,extracted_sha256,canonical_text,"
            "canonical_chars,canonical_sha256,truncated,created_at) VALUES "
            "('nothing_is_accidental','https://e.example','https://e.example',"
            "'2026-07-19 10:00:00','OK',200,'text/plain',NULL,20,?,20,?,"
            "'twenty chars of text',20,?,0,'2026-07-19 10:00:00')",
            (
                hashlib.sha256(b"twenty chars of text").hexdigest(),
                hashlib.sha256("twenty chars of text".encode()).hexdigest(),
                hashlib.sha256("twenty chars of text".encode()).hexdigest(),
            ),
        )
        retrieval_id = int(conn.execute(
            "SELECT id FROM evidence_retrievals"
        ).fetchone()[0])
        intent = DurableResearchExecutionIntent.from_settings(
            settings=SimpleNamespace(
                pricing={
                    "input_per_mtok": 1.0, "output_per_mtok": 1.0,
                    "cache_read_per_mtok": 1.0, "cache_write_per_mtok": 1.0,
                    "web_search_per_1k": 1.0,
                },
                model_quality="m", research_timeout_seconds=60,
            ),
            account_id="nothing_is_accidental", topic_id=topic_id,
            cap_usd=1.0, max_web_searches=0, question="Why?", niche=["n"],
            max_tokens=3000,
            evidence_input=evidence_input_payload([(
                retrieval_id,
                hashlib.sha256("twenty chars of text".encode()).hexdigest(),
                20,
            )]),
        )
        payload = {
            "account_id": "nothing_is_accidental", "topic_id": topic_id,
            "dry_run": False, "execution": "durable_provider_v2",
            "mode": "single", "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        }
        conn.execute(
            "INSERT INTO jobs (id,account_id,kind,workflow,status,priority,"
            "idempotency_key,topic_id,run_id,payload_json,schedule_reason,"
            "earliest_run_at,deadline_at,lease_owner,lease_expires_at,attempts,"
            "max_attempts,reserved_cost_usd,budget_reserved_at,"
            "external_effect_started_at,last_error,created_at,started_at,"
            "finished_at,updated_at) VALUES "
            "('evidence-floor-job','nothing_is_accidental','RESEARCH',"
            "'RESEARCH','QUEUED',0,'evidence-floor',?,NULL,?,"
            "'WITHIN_EDITORIAL_WINDOW','2026-07-19 10:00:00',NULL,NULL,NULL,"
            "0,1,0.0,NULL,NULL,NULL,'2026-07-19 10:00:00',NULL,NULL,"
            "'2026-07-19 10:00:00')",
            (topic_id, json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"))),
        )
        conn.commit()
        from app.research.durable_intent import frozen_execution_intent_json

        intent_json, fingerprint = frozen_execution_intent_json(payload)
        with pytest.raises(sqlite3.IntegrityError, match="SHA-256"):
            conn.execute(insert, (
                "evidence-floor-job", "nothing_is_accidental",
                "EVIDENCE_RESEARCH", None, "a" * 64, None, None, None,
                topic_id, intent_json,
                "owner", "2026-07-19 10:00:00", "2026-07-19 12:00:00",
            ))
        conn.rollback()
        # Prawdziwy preimage + prawdziwy fingerprint przechodzą.
        conn.execute(insert, (
            "evidence-floor-job", "nothing_is_accidental", "EVIDENCE_RESEARCH",
            None, fingerprint, None, None, None, topic_id, intent_json,
            "owner", "2026-07-19 10:00:00", "2026-07-19 12:00:00",
        ))
        conn.commit()
    finally:
        conn.close()
