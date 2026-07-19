"""Regresje Etapu 0 / Task 1: jawny research_runs.flow i bezpieczne resume."""
from __future__ import annotations

from argparse import Namespace
import inspect
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.llm.usage_tracker import UsageTracker
from app.models import (
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect
from app.workflows.research.pipeline import (
    _validate_resume_flow,
    resume_research_stage_b,
    resume_staged_research,
)


def _database_through_0005(path: Path) -> sqlite3.Connection:
    conn = connect(path)
    conn.execute(
        "CREATE TABLE schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration.stem >= "0006_research_run_flow":
            break
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (migration.stem,))
    conn.commit()
    return conn


def _seed_historical_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO accounts "
        "(id,name,mode,autonomy_level,active,browser_profile_path,writing_profile_path) "
        "VALUES ('nothing_is_accidental','Nothing Is Accidental','FULL_PUBLICATION',"
        "'LEVEL_1',1,'browser','writing')"
    )
    conn.executemany(
        "INSERT INTO topics (id,account_id,title,question,status) VALUES "
        "(?,'nothing_is_accidental',?,?,'SELECTED')",
        [(1, "Ticket prices", "Why prices?"), (2, "Checked baggage", "Where bags go?")],
    )
    runs = [
        ("bda661bc-59c9-4f4e-9313-86c659bde74d", "DRY_RUN", "research", "2026-07-11 14:41:04",
         "2026-07-11 14:41:04", 0.0492, None),
        ("1b649314-27cf-4b29-857e-287175664a3f", "FAILED", "research", "2026-07-11 19:04:45",
         "2026-07-11 19:27:43", 0.25, "single parse failure"),
        ("2a3b4bb9-two-stage", "FAILED", "gather_sources", "2026-07-12 03:30:37",
         "2026-07-12 03:30:59", 0.123823, "gather failure"),
        ("9bbeb020-staged", "FAILED", "discover_sources", "2026-07-12 08:47:50",
         "2026-07-12 09:12:36", 0.126793, "partial extraction"),
    ]
    conn.executemany(
        "INSERT INTO runs "
        "(id,account_id,workflow,status,current_state,started_at,finished_at,cost_usd,error) "
        "VALUES (?,'nothing_is_accidental','RESEARCH',?,?,?,?,?,?)",
        runs,
    )
    conn.execute(
        "INSERT INTO research_cards "
        "(id,topic_id,question,thesis,confidence,created_at) "
        "VALUES (1,1,'Why prices?','Revenue management',0.8,'2026-07-11 14:41:04')"
    )
    conn.executemany(
        "INSERT INTO model_usage (run_id,model,task,dry_run) VALUES (?, 'model', ?, ?)",
        [
            ("bda661bc-59c9-4f4e-9313-86c659bde74d", "research", 1),
            ("1b649314-27cf-4b29-857e-287175664a3f", "research", 0),
            ("2a3b4bb9-two-stage", "research_gather", 0),
            ("9bbeb020-staged", "research_discover", 0),
        ],
    )
    conn.executemany(
        "INSERT INTO research_runs "
        "(id,account_id,topic_id,status,total_cost_usd,error,created_at,updated_at) "
        "VALUES (?,'nothing_is_accidental',2,?,?,?,?,?)",
        [
            ("2a3b4bb9-two-stage", "FAILED", 0.0, "gather failure",
             "2026-07-12 03:30:37", "2026-07-12 03:30:59"),
            ("9bbeb020-staged", "PARTIAL", 0.0, "partial extraction",
             "2026-07-12 08:47:50", "2026-07-12 09:12:36"),
        ],
    )
    conn.executemany(
        "INSERT INTO research_stage_results (research_run_id,stage,status) VALUES (?,?,?)",
        [
            ("2a3b4bb9-two-stage", "A", "FAILED"),
            ("9bbeb020-staged", "A1", "SUCCESS"),
        ],
    )
    conn.execute(
        "INSERT INTO research_source_candidates "
        "(research_run_id,url,title,status) VALUES "
        "('9bbeb020-staged','https://example.org/source','Source','PENDING_EXTRACTION')"
    )
    conn.commit()


def test_migration_0006_backfills_all_historical_flows(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "legacy.db")
    _seed_historical_runs(conn)
    old_columns = {
        row["name"]: (row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in conn.execute("PRAGMA table_info(research_runs)")
    }
    old_column_order = list(old_columns)
    old_indexes = {
        row["name"]: row["sql"]
        for row in conn.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='research_runs' AND sql IS NOT NULL"
        )
    }
    old_triggers = {
        row["name"]: row["sql"]
        for row in conn.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='research_runs'"
        )
    }

    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]

    rows = {
        row["id"]: row
        for row in conn.execute(
            "SELECT id,topic_id,flow,status,research_card_id FROM research_runs"
        )
    }
    assert rows["1b649314-27cf-4b29-857e-287175664a3f"]["flow"] == "single"
    assert rows["1b649314-27cf-4b29-857e-287175664a3f"]["topic_id"] == 2
    assert rows["bda661bc-59c9-4f4e-9313-86c659bde74d"]["flow"] == "single"
    assert rows["bda661bc-59c9-4f4e-9313-86c659bde74d"]["topic_id"] == 1
    assert rows["bda661bc-59c9-4f4e-9313-86c659bde74d"]["research_card_id"] == 1
    assert rows["2a3b4bb9-two-stage"]["flow"] == "two_stage"
    assert rows["9bbeb020-staged"]["flow"] == "staged"
    assert conn.execute(
        "SELECT count(*) FROM research_source_candidates "
        "WHERE research_run_id='9bbeb020-staged'"
    ).fetchone()[0] == 1
    new_column_rows = list(conn.execute("PRAGMA table_info(research_runs)"))
    new_columns = {
        row["name"]: (row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in new_column_rows
    }
    assert [name for name in new_columns if name not in {"flow", "is_force_reresearch"}] == old_column_order
    assert {name: new_columns[name] for name in old_columns} == old_columns
    flow_column = next(row for row in new_column_rows if row["name"] == "flow")
    assert flow_column["notnull"] == 1
    assert flow_column["dflt_value"] is None
    force_column = next(row for row in new_column_rows if row["name"] == "is_force_reresearch")
    assert (force_column["type"], force_column["notnull"], force_column["dflt_value"]) == (
        "INTEGER", 1, "0",
    )
    assert conn.execute(
        "SELECT count(*) FROM research_runs WHERE is_force_reresearch != 0"
    ).fetchone()[0] == 0
    new_indexes = {
        row["name"]: row["sql"]
        for row in conn.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='research_runs' AND sql IS NOT NULL"
        )
    }
    assert {name: new_indexes[name] for name in old_indexes} == old_indexes
    assert "ix_research_runs_flow" in new_indexes
    new_triggers = {
        row["name"]: row["sql"]
        for row in conn.execute(
            "SELECT name,sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='research_runs'"
        )
    }
    # 0014 adds reconciliation guards; 0015 adds the SETTLED execution-only
    # authorization and freezes its terminal research lifecycle.
    added_reconciliation_triggers = {
        "research_runs_cost_cache_frozen_after_reconciliation",
        "research_runs_terminal_requires_provider_attempt_normalized",
        "research_runs_settled_recovery_requires_event",
        "research_runs_execution_recovery_terminal_is_immutable",
    }
    assert added_reconciliation_triggers <= new_triggers.keys()
    assert {
        name: sql for name, sql in new_triggers.items()
        if name not in added_reconciliation_triggers
    } == old_triggers
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_migration_0006_runs_on_clean_empty_database(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "clean.db")

    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    assert conn.execute("SELECT count(*) FROM research_runs").fetchone()[0] == 0
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def _delete_historical_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("DELETE FROM model_usage WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
    conn.commit()


def test_migration_0006_without_paid_single_uuid(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "without-paid-single.db")
    _seed_historical_runs(conn)
    _delete_historical_run(conn, "1b649314-27cf-4b29-857e-287175664a3f")

    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    flows = {row["id"]: row["flow"] for row in conn.execute(
        "SELECT id,flow FROM research_runs")}
    assert "1b649314-27cf-4b29-857e-287175664a3f" not in flows
    assert flows["bda661bc-59c9-4f4e-9313-86c659bde74d"] == "single"
    assert flows["2a3b4bb9-two-stage"] == "two_stage"
    assert flows["9bbeb020-staged"] == "staged"
    conn.close()


def test_migration_0006_without_either_local_single_uuid(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "without-local-singles.db")
    _seed_historical_runs(conn)
    _delete_historical_run(conn, "1b649314-27cf-4b29-857e-287175664a3f")
    _delete_historical_run(conn, "bda661bc-59c9-4f4e-9313-86c659bde74d")

    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    flows = {row["id"]: row["flow"] for row in conn.execute(
        "SELECT id,flow FROM research_runs")}
    assert flows == {
        "2a3b4bb9-two-stage": "two_stage",
        "9bbeb020-staged": "staged",
    }
    conn.close()


def test_migration_0006_rejects_unclassifiable_history(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "ambiguous.db")
    conn.execute(
        "INSERT INTO accounts "
        "(id,name,mode,autonomy_level,active,browser_profile_path,writing_profile_path) "
        "VALUES ('a','A','RESEARCH_ONLY','LEVEL_1',1,'browser','writing')"
    )
    conn.execute(
        "INSERT INTO topics (id,account_id,title,status) VALUES (1,'a','Topic','SELECTED')"
    )
    conn.execute(
        "INSERT INTO runs (id,account_id,workflow,status,current_state) "
        "VALUES ('unknown','a','RESEARCH','FAILED','unknown_state')"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="requires_exactly_one_flow"):
        apply_migrations(conn)
    conn.rollback()
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0006_research_run_flow'"
    ).fetchone()[0] == 0
    conn.close()


def test_migration_0006_rolls_back_on_conflicting_flow_signals(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "conflict.db")
    _seed_historical_runs(conn)
    conn.execute(
        "INSERT INTO model_usage (run_id,model,task,dry_run) "
        "VALUES ('2a3b4bb9-two-stage','model','research_extract',0)"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="requires_exactly_one_flow"):
        apply_migrations(conn)
    conn.rollback()
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0006_research_run_flow'"
    ).fetchone()[0] == 0
    assert "flow" not in {
        row["name"] for row in conn.execute("PRAGMA table_info(research_runs)")
    }
    conn.close()


def test_database_rejects_invalid_or_missing_flow(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "flow-constraints.db")
    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    conn.execute(
        "INSERT INTO accounts "
        "(id,name,mode,autonomy_level,active,browser_profile_path,writing_profile_path) "
        "VALUES ('a','A','RESEARCH_ONLY','LEVEL_1',1,'browser','writing')"
    )
    conn.execute(
        "INSERT INTO topics (id,account_id,title,status) VALUES (1,'a','Topic','SELECTED')"
    )
    conn.executemany(
        "INSERT INTO runs (id,account_id,workflow,status) VALUES (?,'a','RESEARCH','RUNNING')",
        [("invalid-flow",), ("missing-flow",)],
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute(
            "INSERT INTO research_runs (id,account_id,topic_id,flow,status) "
            "VALUES ('invalid-flow','a',1,'invalid','PENDING')"
        )
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed"):
        conn.execute(
            "INSERT INTO research_runs (id,account_id,topic_id,status) "
            "VALUES ('missing-flow','a',1,'PENDING')"
        )
    conn.rollback()
    conn.close()


def test_migration_0007_backfills_conservative_historical_attempt_lower_bound(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "candidate-attempts.db")
    _seed_historical_runs(conn)
    conn.executemany(
        "INSERT INTO research_source_candidates (research_run_id,url,title,status) VALUES (?,?,?,?)",
        [
            ("9bbeb020-staged", "https://example.org/extracted", "Extracted", "EXTRACTED"),
            ("9bbeb020-staged", "https://example.org/failed", "Failed", "EXTRACTION_FAILED"),
        ],
    )
    conn.commit()

    assert apply_migrations(conn) == [
        "0006_research_run_flow", "0007_candidate_attempts", "0008_staged_force_reresearch",
        "0009_jobs_system_flags", "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]

    attempts_column = next(
        row for row in conn.execute("PRAGMA table_info(research_source_candidates)")
        if row["name"] == "attempts"
    )
    assert (attempts_column["type"], attempts_column["notnull"], attempts_column["dflt_value"]) == (
        "INTEGER", 1, "0",
    )
    attempts = {
        row["status"]: row["attempts"]
        for row in conn.execute(
            "SELECT status,attempts FROM research_source_candidates "
            "WHERE research_run_id='9bbeb020-staged'"
        )
    }
    assert attempts == {
        "PENDING_EXTRACTION": 0,
        "EXTRACTED": 1,
        "EXTRACTION_FAILED": 1,
    }
    assert apply_migrations(conn) == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_migration_0007_rolls_back_schema_when_ledger_insert_fails(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "attempts-ledger-rollback.db")
    conn.execute(
        "CREATE TRIGGER reject_attempts_ledger BEFORE INSERT ON schema_migrations "
        "WHEN NEW.version='0007_candidate_attempts' "
        "BEGIN SELECT RAISE(ABORT, 'forced ledger failure'); END"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced ledger failure"):
        apply_migrations(conn)

    assert "attempts" not in {
        row["name"] for row in conn.execute("PRAGMA table_info(research_source_candidates)")
    }
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0007_candidate_attempts'"
    ).fetchone()[0] == 0

    conn.execute("DROP TRIGGER reject_attempts_ledger")
    conn.commit()
    assert apply_migrations(conn) == [
        "0007_candidate_attempts", "0008_staged_force_reresearch", "0009_jobs_system_flags",
        "0010_provider_attempts", "0011_provider_attempt_invariants",
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    assert "attempts" in {
        row["name"] for row in conn.execute("PRAGMA table_info(research_source_candidates)")
    }
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0007_candidate_attempts'"
    ).fetchone()[0] == 1
    conn.close()


def test_migration_0008_rolls_back_force_marker_when_ledger_insert_fails(tmp_path: Path):
    conn = _database_through_0005(tmp_path / "force-marker-ledger-rollback.db")
    _seed_historical_runs(conn)
    conn.execute(
        "CREATE TRIGGER reject_force_marker_ledger BEFORE INSERT ON schema_migrations "
        "WHEN NEW.version='0008_staged_force_reresearch' "
        "BEGIN SELECT RAISE(ABORT, 'forced force-marker ledger failure'); END"
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced force-marker ledger failure"):
        apply_migrations(conn)

    assert "is_force_reresearch" not in {
        row["name"] for row in conn.execute("PRAGMA table_info(research_runs)")
    }
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0008_staged_force_reresearch'"
    ).fetchone()[0] == 0

    conn.execute("DROP TRIGGER reject_force_marker_ledger")
    conn.commit()
    assert apply_migrations(conn) == [
        "0008_staged_force_reresearch", "0009_jobs_system_flags", "0010_provider_attempts",
        "0011_provider_attempt_invariants", "0012_provider_ledger_hardening",
            "0013_provider_attempt_usage_integrity", "0014_provider_attempt_reconciliation",
            "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle",
    ]
    force_column = next(
        row for row in conn.execute("PRAGMA table_info(research_runs)")
        if row["name"] == "is_force_reresearch"
    )
    assert (force_column["type"], force_column["notnull"], force_column["dflt_value"]) == (
        "INTEGER", 1, "0",
    )
    assert conn.execute(
        "SELECT count(*) FROM research_runs WHERE is_force_reresearch != 0"
    ).fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute(
            "UPDATE research_runs SET is_force_reresearch=2 "
            "WHERE id='9bbeb020-staged'"
        )
    conn.rollback()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def _topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Flow test", question="Which flow?",
        score=90, status=TopicStatus.SELECTED,
    ))


def _create_research_run(storage, account, topic, run_id: str,
                         flow: ResearchFlow, status: ResearchRunStatus) -> ResearchRun:
    storage.create_run(Run(
        id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    return storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=flow, status=status,
    ))


def test_repository_creates_and_reads_each_explicit_flow(storage, account):
    topic = _topic(storage, account)
    for flow in ResearchFlow:
        run_id = f"run-{flow.value}"
        _create_research_run(storage, account, topic, run_id, flow, ResearchRunStatus.PENDING)
        assert storage.get_research_run(run_id).flow == flow


def test_research_run_requires_explicit_flow(account):
    with pytest.raises(ValidationError, match="flow"):
        ResearchRun(id="missing-flow", account_id=account.id, topic_id=1)


def test_research_run_rejects_unknown_flow(account):
    with pytest.raises(ValidationError, match="flow"):
        ResearchRun(id="bad-flow", account_id=account.id, topic_id=1, flow="legacy")


@pytest.mark.parametrize("flow", list(ResearchFlow))
def test_resume_flow_validator_accepts_matching_flow(account, flow: ResearchFlow):
    research_run = ResearchRun(
        id=f"matching-{flow.value}", account_id=account.id, topic_id=1,
        flow=flow, status=ResearchRunStatus.PARTIAL,
    )
    _validate_resume_flow(research_run, flow)


def _resume_dependencies(settings, storage):
    return {
        "settings": settings,
        "storage": storage,
        "research_client": object(),
        "usage_tracker": UsageTracker(
            settings, storage, costs_csv_path=settings.costs_csv_path),
        "policy": PolicyEngine(settings, storage),
        "notifier": LogNotification(),
    }


@pytest.mark.parametrize("actual", [ResearchFlow.SINGLE, ResearchFlow.TWO_STAGE])
def test_staged_resume_rejects_other_flows_before_work(
        settings, storage, account, actual: ResearchFlow):
    topic = _topic(storage, account)
    run_id = f"staged-resume-on-{actual.value}"
    _create_research_run(
        storage, account, topic, run_id, actual, ResearchRunStatus.DISCOVERY_COMPLETE)

    with pytest.raises(ValueError) as exc:
        resume_staged_research(
            run_id, account, **_resume_dependencies(settings, storage))
    message = str(exc.value)
    assert run_id in message
    assert "expected flow 'staged'" in message
    assert f"stored flow '{actual.value}'" in message


@pytest.mark.parametrize("actual", [ResearchFlow.SINGLE, ResearchFlow.STAGED])
def test_two_stage_resume_rejects_other_flows_before_work(
        settings, storage, account, actual: ResearchFlow):
    topic = _topic(storage, account)
    run_id = f"two-stage-resume-on-{actual.value}"
    _create_research_run(
        storage, account, topic, run_id, actual, ResearchRunStatus.SOURCE_COLLECTED)

    with pytest.raises(ValueError) as exc:
        resume_research_stage_b(
            run_id, account, **_resume_dependencies(settings, storage))
    message = str(exc.value)
    assert run_id in message
    assert "expected flow 'two_stage'" in message
    assert f"stored flow '{actual.value}'" in message


def test_single_resume_validation_rejects_staged_run(account):
    research_run = ResearchRun(
        id="single-resume-on-staged", account_id=account.id, topic_id=1,
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.PARTIAL,
    )
    with pytest.raises(ValueError) as exc:
        _validate_resume_flow(research_run, ResearchFlow.SINGLE)
    message = str(exc.value)
    assert research_run.id in message
    assert "expected flow 'single'" in message
    assert "stored flow 'staged'" in message


class _CliResumeStorage:
    def __init__(self, research_run: ResearchRun, *, reject_post_lookup: bool = False,
                 uncertain_count: int = 0):
        self.research_run = research_run
        self.reject_post_lookup = reject_post_lookup
        self.uncertain_count = uncertain_count
        self.calls: list[str] = []

    def get_research_run(self, run_id: str) -> ResearchRun:
        self.calls.append("get_research_run")
        assert run_id == self.research_run.id
        return self.research_run

    def get_research_usage(self, run_id: str):
        self.calls.append("get_research_usage")
        if self.reject_post_lookup:
            raise AssertionError("invalid resume reached usage/estimation path")
        return []

    def list_source_candidates(self, run_id: str, status=None):
        self.calls.append("list_source_candidates")
        assert run_id == self.research_run.id
        return [object()] * self.uncertain_count

    def sum_real_cost_usd(self, prefix: str) -> float:
        self.calls.append("sum_real_cost_usd")
        if self.reject_post_lookup:
            raise AssertionError("invalid resume reached budget/preflight path")
        return 0.0


def _patch_cli_resume_environment(monkeypatch, storage: _CliResumeStorage):
    import scripts.run_capped_research as capped_script

    settings = SimpleNamespace(
        anthropic_api_key=None,
        model_quality="fake-model",
        kill_switch=False,
        max_monthly_cost_usd=40.0,
        max_daily_cost_usd=2.0,
        db_path=":memory:",
    )
    monkeypatch.setattr(capped_script, "load_settings", lambda: settings)
    monkeypatch.setattr(capped_script, "replace", lambda value, **changes: value)
    monkeypatch.setattr(capped_script.SqliteStorage, "open", lambda path: storage)
    return capped_script


@pytest.mark.parametrize(
    ("flow", "status", "estimate_only"),
    [
        (ResearchFlow.SINGLE, ResearchRunStatus.PENDING, False),
        (ResearchFlow.STAGED, ResearchRunStatus.FAILED, False),
        (ResearchFlow.STAGED, ResearchRunStatus.COMPLETE, True),
        (ResearchFlow.TWO_STAGE, ResearchRunStatus.FAILED, False),
    ],
)
def test_cli_resume_rejects_non_resumable_status_before_any_work(
        monkeypatch, capsys, account, flow, status, estimate_only):
    run = ResearchRun(
        id=f"cli-invalid-{flow.value}-{status.value}",
        account_id=account.id,
        topic_id=1,
        flow=flow,
        status=status,
    )
    storage = _CliResumeStorage(run, reject_post_lookup=True)
    capped_script = _patch_cli_resume_environment(monkeypatch, storage)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid resume created a client or called a pipeline path")

    monkeypatch.setattr(capped_script, "_run_resume_legacy", forbidden)
    monkeypatch.setattr(capped_script, "_run_resume_staged", forbidden)

    result = capped_script._run_resume(Namespace(
        resume=run.id,
        estimate_only=estimate_only,
    ))

    assert result == 1
    assert storage.calls == ["get_research_run"]
    output = capsys.readouterr().out
    assert run.id in output
    assert f"flow={flow.value}" in output
    assert f"status={status.value}" in output
    assert "dozwolone statusy" in output


@pytest.mark.parametrize(
    ("flow", "status", "expected_helper"),
    [
        (ResearchFlow.TWO_STAGE, ResearchRunStatus.SOURCE_COLLECTED, "legacy"),
        (ResearchFlow.STAGED, ResearchRunStatus.DISCOVERY_COMPLETE, "staged"),
    ],
)
def test_cli_resume_dispatches_valid_status_by_persisted_flow(
        monkeypatch, account, flow, status, expected_helper):
    run = ResearchRun(
        id=f"cli-valid-{flow.value}", account_id=account.id, topic_id=1,
        flow=flow, status=status,
    )
    storage = _CliResumeStorage(run)
    capped_script = _patch_cli_resume_environment(monkeypatch, storage)
    dispatched: list[str] = []

    def legacy(*args, **kwargs):
        dispatched.append("legacy")
        return 17

    def staged(*args, **kwargs):
        dispatched.append("staged")
        return 17

    monkeypatch.setattr(capped_script, "_run_resume_legacy", legacy)
    monkeypatch.setattr(capped_script, "_run_resume_staged", staged)

    assert capped_script._run_resume(Namespace(resume=run.id)) == 17
    assert dispatched == [expected_helper]
    assert storage.calls[0] == "get_research_run"
    assert "get_research_usage" in storage.calls


def test_cli_resume_refuses_uncertain_candidate_before_preflight_or_client(
        monkeypatch, capsys, account):
    run = ResearchRun(
        id="cli-uncertain-staged", account_id=account.id, topic_id=1,
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_COMPLETE,
    )
    storage = _CliResumeStorage(run, reject_post_lookup=True, uncertain_count=1)
    capped_script = _patch_cli_resume_environment(monkeypatch, storage)

    assert capped_script._run_resume(Namespace(resume=run.id)) == 1
    assert storage.calls == ["get_research_run", "list_source_candidates"]
    assert "EXTRACTION_IN_PROGRESS" in capsys.readouterr().out


def test_resume_dispatch_uses_only_persisted_flow():
    import scripts.run_capped_research as capped_script

    source = inspect.getsource(capped_script._run_resume)
    assert "research_run.flow" in source
    assert "_detect_flow" not in source
    # Candidate reads are allowed solely for the explicit uncertain-A2 safety guard;
    # flow dispatch itself remains based only on the persisted research_run.flow.
    assert "list_research_sources" not in source

    project_root = Path(__file__).resolve().parents[1]
    python_sources = list((project_root / "app").rglob("*.py"))
    python_sources.extend((project_root / "scripts").rglob("*.py"))
    assert all("_detect_flow" not in path.read_text(encoding="utf-8")
               for path in python_sources)
