"""Copy-only 0009 -> 0014 production migration rehearsal."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from app.operations.stage1_migration import (
    MIGRATIONS_0010_TO_0014,
    REQUIRED_STAGE1_TRIGGERS,
    Stage1MigrationPreflightError,
    Stage1MigrationRequest,
    fingerprint,
    run_stage1_copy_preflight,
)
from app.core.security_flags import SECURITY_FLAG_DEFAULTS
from app.storage.db import MIGRATIONS_DIR, apply_migrations


BRANCH = "dev/first-successful-research-card"
HEAD = "637d1f21fbac164d7f78b11590facc7098182559"
NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _production_shape_0009(path: Path, migration_dir: Path) -> None:
    migration_dir.mkdir()
    for source in sorted(MIGRATIONS_DIR.glob("*.sql"))[:9]:
        (migration_dir / source.name).write_bytes(source.read_bytes())
    conn = sqlite3.connect(path)
    try:
        assert len(apply_migrations(conn, migration_dir)) == 9
        conn.execute(
            "INSERT INTO accounts(id,name,mode,autonomy_level,active,browser_profile_path,"
            "writing_profile_path) VALUES (?,?,?,?,?,?,?)",
            ("acc", "Account", "RESEARCH_ONLY", "LEVEL_1", 1, "", ""),
        )
        costs = ["0.050000"] * 12 + ["0.084580"]
        for index, cost in enumerate(costs, start=1):
            run_id = f"legacy-run-{index:02d}"
            conn.execute(
                "INSERT INTO runs(id,account_id,workflow,status,cost_usd) "
                "VALUES (?,?,?,? ,?)",
                (run_id, "acc", "ANALYTICS", "SUCCESS", float(cost)),
            )
            conn.execute(
                "INSERT INTO model_usage(run_id,model,task,estimated_cost_usd,dry_run) "
                "VALUES (?,?,?,?,0)",
                (run_id, "legacy-model", "legacy", float(cost)),
            )
        conn.commit()
    finally:
        conn.close()


def _request(source: Path, workspace: Path, project_root: Path) -> Stage1MigrationRequest:
    baseline = fingerprint(source)
    return Stage1MigrationRequest(
        project_root=project_root,
        source_db=source,
        workspace=workspace,
        expected_branch=BRANCH,
        expected_head=HEAD,
        expected_source_sha256=baseline.sha256,
        expected_source_size=baseline.size,
        expected_source_mtime_utc=baseline.mtime_utc,
    )


def test_copy_preflight_preserves_source_and_backup_and_proves_candidate(tmp_path: Path):
    source_dir = tmp_path / "production"
    source_dir.mkdir()
    source = source_dir / "agent.db"
    _production_shape_0009(source, tmp_path / "migrations-0009")
    source_before = fingerprint(source)
    request = _request(source, tmp_path / "external-rehearsal", tmp_path)

    result = run_stage1_copy_preflight(
        request,
        git_identity_provider=lambda root: (BRANCH, HEAD),
        now=NOW,
    )

    assert result.applied_migrations == MIGRATIONS_0010_TO_0014
    assert result.legacy_proof_count == 13
    assert result.real_cost_usd == "0.684580"
    assert result.source == source_before == fingerprint(source)
    assert result.backup == source_before == fingerprint(result.backup_path)
    assert result.candidate_path != source
    assert not Path(f"{source}-wal").exists()
    assert not Path(f"{source}-shm").exists()

    backup = sqlite3.connect(result.backup_path)
    candidate = sqlite3.connect(result.candidate_path)
    try:
        assert backup.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 9
        assert candidate.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 14
        triggers = {
            row[0] for row in candidate.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        assert REQUIRED_STAGE1_TRIGGERS <= triggers
        flags = {
            row[0]: json.loads(row[1])
            for row in candidate.execute("SELECT key,value_json FROM system_flags")
        }
        assert flags == dict(SECURITY_FLAG_DEFAULTS)
        assert apply_migrations(
            candidate, through="0014_provider_attempt_reconciliation",
        ) == []
    finally:
        backup.close()
        candidate.close()

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "COPY_PREFLIGHT_PASSED_NOT_PRODUCTION_MIGRATION"
    assert report["source_unchanged"] is True
    assert report["rollback"]["method"] == "full_file_restore"
    rendered = json.dumps(report).upper()
    assert "UPDATE " not in rendered
    assert "DELETE " not in rendered


def test_copy_preflight_rejects_wrong_metadata_before_creating_workspace(tmp_path: Path):
    source_dir = tmp_path / "production"
    source_dir.mkdir()
    source = source_dir / "agent.db"
    _production_shape_0009(source, tmp_path / "migrations-0009")
    workspace = tmp_path / "external-rehearsal"
    request = _request(source, workspace, tmp_path)
    request = Stage1MigrationRequest(**{
        **request.__dict__, "expected_source_sha256": "00" * 32,
    })
    with pytest.raises(Stage1MigrationPreflightError, match="approved baseline"):
        run_stage1_copy_preflight(
            request, git_identity_provider=lambda root: (BRANCH, HEAD), now=NOW,
        )
    assert not workspace.exists()
    assert fingerprint(source).sha256 != "00" * 32


def test_copy_preflight_requires_workspace_outside_source_tree(tmp_path: Path):
    source_dir = tmp_path / "production"
    source_dir.mkdir()
    source = source_dir / "agent.db"
    _production_shape_0009(source, tmp_path / "migrations-0009")
    request = _request(source, source_dir / "nested", tmp_path)
    with pytest.raises(Stage1MigrationPreflightError, match="separate"):
        run_stage1_copy_preflight(
            request, git_identity_provider=lambda root: (BRANCH, HEAD), now=NOW,
        )
