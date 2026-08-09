"""Etap 2 / fala E1: jawna drabina 0015 -> 0016, dokładny runtime gate i podłogi SQL.

Wszystkie próby zapisowe działają wyłącznie na tymczasowych bazach; podłogi są
atakowane surowym ``sqlite3`` z celowo WYŁĄCZONYM ``PRAGMA foreign_keys``.
Surowy writer w tych testach rejestruje PRAWDZIWĄ funkcję
``evidence_sha256_hex`` (uczciwy writer poza aplikacją); osobny test dowodzi,
że writer bez tej funkcji w ogóle nie może INSERT-ować (fail-closed). Podłogi
nie bronią przed autorem zmieniającym schemat, usuwającym triggery albo
rejestrującym celowo fałszywą funkcję — to jawna granica kontraktu E1.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from shutil import copy2
import sqlite3

import pytest

import scripts.migrate_schema_0016 as migration_cli_0016
import scripts.migrate_schema_0017 as migration_cli_0017
from app.research.evidence import (
    MAX_EXCERPT_CHARS,
    MIN_EXCERPT_CHARS,
    TRUNCATION_TAIL_GUARD_CHARS,
    canonicalize_text,
    sha256_hex,
)
from app.storage.db import (
    CONTENT_FOUNDATION_SCHEMA_VERSION,
    CONTENT_PIPELINE_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    CONTENT_DECISION_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    ExplicitMigrationError,
    MIGRATIONS_DIR,
    RUNTIME_SCHEMA_VERSION,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    SchemaVersionInvalid,
    SchemaVersionTooNew,
    SchemaVersionTooOld,
    canonical_migration_versions,
    database_schema_versions,
    initialize_database,
    migrate_0014_to_0015,
    migrate_0015_to_0016,
    migrate_0016_to_0017,
    register_evidence_hash_function,
    require_database_schema,
)
from app.storage.repositories import SqliteStorage

NOW = "2026-07-18 12:00:00.000000"
ACCOUNT_A = "qa-account-a"
ACCOUNT_B = "qa-account-b"
PROBE_TEXT = canonicalize_text(
    "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu "
    "xi omicron pi rho sigma tau upsilon phi chi psi omega. " * 8
)

_RETRIEVAL_SQL = (
    "INSERT INTO evidence_retrievals (account_id, requested_url, final_url,"
    " fetched_at, status, http_status, content_type, fetch_error,"
    " raw_size_bytes, raw_sha256, extracted_chars, extracted_sha256,"
    " canonical_text, canonical_chars, canonical_sha256, truncated, created_at)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

_EXCERPT_SQL = (
    "INSERT INTO evidence_excerpts (account_id, retrieval_id, claim_text,"
    " claim_sha256, excerpt_text, start_offset, end_offset, created_at)"
    " VALUES (?,?,?,?,?,?,?,?)"
)


def _fingerprint(path: Path):
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest(),
        stat.st_size,
        tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")),
        database_schema_versions(path),
    )


def _settled_database(path: Path) -> None:
    initialize_database(path, through=SETTLED_RECOVERY_SCHEMA_VERSION)
    assert database_schema_versions(path)[-1] == SETTLED_RECOVERY_SCHEMA_VERSION


def _raw_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Celowo bez PRAGMA foreign_keys: podłogi muszą bronić także bez FK.
    # Uczciwy writer rejestruje prawdziwą funkcję hash; bez niej INSERT-y do
    # tabel evidence w ogóle nie przechodzą (osobny test poniżej).
    register_evidence_hash_function(conn)
    return conn


def _seed_accounts(conn: sqlite3.Connection) -> None:
    for account_id in (ACCOUNT_A, ACCOUNT_B):
        conn.execute(
            "INSERT OR IGNORE INTO accounts (id, name, mode, autonomy_level,"
            " active, browser_profile_path, writing_profile_path)"
            " VALUES (?,?,?,?,?,?,?)",
            (account_id, account_id, "full_publication", "L1", 0, "./x", "./y"),
        )
    conn.commit()


def _insert_retrieval(
    conn: sqlite3.Connection,
    *,
    account_id: str = ACCOUNT_A,
    status: str = "OK",
    canonical_text: str = PROBE_TEXT,
    truncated: int = 0,
    http_status: int | None = 200,
    fetch_error: str | None = None,
) -> int:
    text = canonical_text if status == "OK" else ""
    cur = conn.execute(
        _RETRIEVAL_SQL,
        (
            account_id, "https://example.org/floor", "https://example.org/floor",
            NOW, status, http_status, "text/html", fetch_error,
            len(text.encode("utf-8")), sha256_hex(text.encode("utf-8")),
            len(text), sha256_hex(text), text, len(text), sha256_hex(text),
            truncated, NOW,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _aligned(text: str, length: int, *, start: int = 0) -> tuple[int, int]:
    while text[start] == " ":
        start += 1
    end = start + length
    while text[end - 1] == " ":
        end -= 1
    return start, end


@pytest.fixture
def evidence_db(tmp_path: Path) -> Path:
    path = tmp_path / "evidence-floor.db"
    initialize_database(path)
    conn = _raw_connection(path)
    try:
        _seed_accounts(conn)
    finally:
        conn.close()
    return path


# --- Drabina jawnych migracji i dokładny runtime gate ---

def test_runtime_schema_version_is_the_content_decision_migration():
    # Runtime gate wymaga dokładnie 0025; wcześniejsze kroki pozostają w drabinie.
    from app.storage.db import (
        CONTROLLED_FETCH_SCHEMA_VERSION,
        CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
        MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
        EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
        EVIDENCE_RESEARCH_SCHEMA_VERSION,
        TOPIC_GENERATION_SCHEMA_VERSION,
    )

    assert RUNTIME_SCHEMA_VERSION == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
    assert MODEL_FAMILY_ROUTING_SCHEMA_VERSION == "0027_model_family_routing"
    assert CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION == (
        "0026_controlled_provider_content"
    )
    assert EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION == (
        "0025_evidence_research_content_lineage"
    )
    assert CONTENT_DECISION_SCHEMA_VERSION == "0024_autonomous_content_decision"
    assert CONTENT_FOUNDATION_SCHEMA_VERSION == "0021_durable_content_foundation"
    assert TOPIC_GENERATION_SCHEMA_VERSION == "0020_topic_generation_lifecycle"
    assert EVIDENCE_RESEARCH_SCHEMA_VERSION == "0019_evidence_research_approvals"
    assert CONTROLLED_FETCH_SCHEMA_VERSION == "0018_controlled_fetch_lifecycle"
    assert EVIDENCE_SCHEMA_VERSION == "0016_evidence_foundation"
    canonical = canonical_migration_versions()
    assert canonical[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
    assert canonical[-2] == CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION
    assert canonical[-3] == EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION
    assert canonical[-4] == CONTENT_DECISION_SCHEMA_VERSION
    assert canonical[-5] == CONTENT_WRITER_SCHEMA_VERSION
    assert canonical[-6] == CONTENT_PIPELINE_SCHEMA_VERSION
    assert canonical[-7] == CONTENT_FOUNDATION_SCHEMA_VERSION
    assert canonical[-8] == TOPIC_GENERATION_SCHEMA_VERSION
    assert canonical[-9] == EVIDENCE_RESEARCH_SCHEMA_VERSION
    assert canonical[-10] == CONTROLLED_FETCH_SCHEMA_VERSION
    assert canonical[-11] == EVIDENCE_PIPELINE_SCHEMA_VERSION
    assert canonical[-12] == EVIDENCE_SCHEMA_VERSION
    assert len(canonical) == 27


def test_fresh_initialization_reaches_runtime_and_creates_evidence_tables(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert len(applied) == 27
    assert applied[-1] == RUNTIME_SCHEMA_VERSION
    storage = SqliteStorage.open(path)
    try:
        names = {
            row["name"] for row in storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"evidence_retrievals", "evidence_excerpts"} <= names
        columns = {
            row["name"] for row in storage.conn.execute(
                "PRAGMA table_info(evidence_retrievals)"
            )
        }
        assert "account_id" in columns
        excerpt_columns = {
            row["name"] for row in storage.conn.execute(
                "PRAGMA table_info(evidence_excerpts)"
            )
        }
        assert "account_id" in excerpt_columns
    finally:
        storage.close()


def test_runtime_open_refuses_0015_database_without_mutation(tmp_path):
    path = tmp_path / "settled.db"
    _settled_database(path)
    before = _fingerprint(path)
    with pytest.raises(SchemaVersionTooOld, match="SCHEMA_VERSION_TOO_OLD"):
        SqliteStorage.open(path)
    assert _fingerprint(path) == before


def test_explicit_0015_to_0016_is_exact_and_second_pass_is_idempotent(tmp_path):
    path = tmp_path / "ladder.db"
    _settled_database(path)
    first = migrate_0015_to_0016(path)
    assert first.source_version == SETTLED_RECOVERY_SCHEMA_VERSION
    assert first.target_version == EVIDENCE_SCHEMA_VERSION
    assert first.applied_migrations == (EVIDENCE_SCHEMA_VERSION,)
    assert first.idempotent is False
    assert len(database_schema_versions(path)) == 16
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)

    before = _fingerprint(path)
    second = migrate_0015_to_0016(path)
    assert second.idempotent is True
    assert second.applied_migrations == ()
    assert _fingerprint(path) == before


def test_explicit_0016_to_0017_is_exact_and_idempotent(tmp_path):
    path = tmp_path / "lineage-ladder.db"
    initialize_database(path, through=EVIDENCE_SCHEMA_VERSION)
    first = migrate_0016_to_0017(path)
    assert first.source_version == EVIDENCE_SCHEMA_VERSION
    assert first.target_version == EVIDENCE_PIPELINE_SCHEMA_VERSION
    assert first.applied_migrations == (EVIDENCE_PIPELINE_SCHEMA_VERSION,)
    assert len(database_schema_versions(path)) == 17
    # E2-B: runtime wymaga 0018, więc baza 0017 pozostaje odrzucona bez mutacji.
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    before = _fingerprint(path)
    second = migrate_0016_to_0017(path)
    assert second.idempotent is True
    assert second.applied_migrations == ()
    assert _fingerprint(path) == before


def test_0017_cli_requires_confirmation_and_applies_one_step(tmp_path, capsys):
    path = tmp_path / "lineage-cli.db"
    initialize_database(path, through=EVIDENCE_SCHEMA_VERSION)
    before = _fingerprint(path)
    assert migration_cli_0017.main(["--db-path", str(path)]) == 2
    assert _fingerprint(path) == before
    assert migration_cli_0017.main([
        "--db-path", str(path), "--confirm-0016-to-0017",
    ]) == 0
    assert database_schema_versions(path)[-1] == EVIDENCE_PIPELINE_SCHEMA_VERSION
    assert "source=0016_evidence_foundation" in capsys.readouterr().out


def test_runtime_refuses_0016_without_mutation(tmp_path):
    path = tmp_path / "e1-only.db"
    initialize_database(path, through=EVIDENCE_SCHEMA_VERSION)
    before = _fingerprint(path)
    with pytest.raises(SchemaVersionTooOld, match="SCHEMA_VERSION_TOO_OLD"):
        SqliteStorage.open(path)
    assert _fingerprint(path) == before


def test_explicit_0017_rolls_back_ledger_and_lineage_schema_on_fault(tmp_path):
    path = tmp_path / "lineage-rollback.db"
    initialize_database(path, through=EVIDENCE_SCHEMA_VERSION)
    migration_dir = tmp_path / "faulty-lineage"
    migration_dir.mkdir()
    source = MIGRATIONS_DIR / f"{EVIDENCE_PIPELINE_SCHEMA_VERSION}.sql"
    target = migration_dir / source.name
    target.write_text(
        source.read_text(encoding="utf-8")
        + "\nTHIS IS A CONTROLLED INVALID STATEMENT;\n",
        encoding="utf-8",
    )
    before = _fingerprint(path)
    with pytest.raises(Exception, match="syntax|near"):
        migrate_0016_to_0017(path, migrations_dir=migration_dir)
    assert _fingerprint(path) == before
    assert database_schema_versions(path)[-1] == EVIDENCE_SCHEMA_VERSION
    check = SqliteStorage.open_read_only(path)
    try:
        assert check.conn.execute(
            "SELECT count(*) FROM sqlite_master "
            "WHERE name IN ('evidence_candidate_retrievals',"
            "'evidence_candidate_excerpts','evidence_source_lineage')"
        ).fetchone()[0] == 0
    finally:
        check.close()


def test_explicit_0015_to_0016_fails_closed_for_0014_source(tmp_path):
    path = tmp_path / "too-old.db"
    initialize_database(path, through=STAGE1_SCHEMA_VERSION)
    before = _fingerprint(path)
    with pytest.raises(ExplicitMigrationError, match="requires exact"):
        migrate_0015_to_0016(path)
    assert _fingerprint(path) == before


def test_superseded_0014_step_fails_closed_on_0016_database(tmp_path):
    path = tmp_path / "already-new.db"
    initialize_database(path)
    with pytest.raises(ExplicitMigrationError, match="requires exact"):
        migrate_0014_to_0015(path)


def test_explicit_0016_rolls_back_ledger_and_partial_schema_on_fault(tmp_path):
    path = tmp_path / "rollback.db"
    _settled_database(path)
    migration_dir = tmp_path / "faulty-migrations"
    migration_dir.mkdir()
    source = MIGRATIONS_DIR / f"{EVIDENCE_SCHEMA_VERSION}.sql"
    target = migration_dir / source.name
    copy2(source, target)
    target.write_text(
        source.read_text(encoding="utf-8") + "\nTHIS IS A CONTROLLED INVALID STATEMENT;\n",
        encoding="utf-8",
    )
    before = database_schema_versions(path)

    with pytest.raises(Exception, match="syntax|near"):
        migrate_0015_to_0016(path, migrations_dir=migration_dir)

    assert database_schema_versions(path) == before
    check = SqliteStorage.open_read_only(path)
    try:
        assert check.conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=?",
            (EVIDENCE_SCHEMA_VERSION,),
        ).fetchone()[0] == 0
        assert check.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='evidence_retrievals'"
        ).fetchone()[0] == 0
        assert check.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master"
            " WHERE type IN ('trigger','index') AND name LIKE '%evidence%'"
        ).fetchone()[0] == 0
    finally:
        check.close()


def test_schema_gate_reports_too_new_for_intermediate_requirement(tmp_path):
    path = tmp_path / "newer.db"
    initialize_database(path)
    with pytest.raises(SchemaVersionTooNew, match="SCHEMA_VERSION_TOO_NEW"):
        require_database_schema(path, required_version=SETTLED_RECOVERY_SCHEMA_VERSION)


def test_unknown_future_ledger_row_is_invalid_not_silently_accepted(tmp_path):
    path = tmp_path / "future.db"
    initialize_database(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO schema_migrations(version) VALUES ('0017_not_yet_written')"
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaVersionInvalid, match="SCHEMA_VERSION_INVALID"):
        SqliteStorage.open(path)


def test_migration_cli_0016_requires_confirmation_and_is_idempotent(tmp_path, capsys):
    path = tmp_path / "cli-ladder.db"
    _settled_database(path)
    assert migration_cli_0016.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == SETTLED_RECOVERY_SCHEMA_VERSION
    assert migration_cli_0016.main([
        "--db-path", str(path), "--confirm-0015-to-0016",
    ]) == 0
    assert migration_cli_0016.main([
        "--db-path", str(path), "--confirm-0015-to-0016",
    ]) == 0
    output = capsys.readouterr()
    assert "idempotent=true" in output.out
    assert database_schema_versions(path)[-1] == EVIDENCE_SCHEMA_VERSION


def test_migration_cli_0016_fails_closed_on_0014(tmp_path, capsys):
    path = tmp_path / "cli-too-old.db"
    initialize_database(path, through=STAGE1_SCHEMA_VERSION)
    assert migration_cli_0016.main([
        "--db-path", str(path), "--confirm-0015-to-0016",
    ]) == 2
    assert "failed closed" in capsys.readouterr().err
    assert database_schema_versions(path)[-1] == STAGE1_SCHEMA_VERSION


# --- Podłogi SQLite migracji 0016 (surowy writer, bez FK) ---

def test_floor_accepts_exact_consistent_excerpt(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        conn.execute(_EXCERPT_SQL, (
            ACCOUNT_A, rid, "claim", sha256_hex("claim"),
            PROBE_TEXT[start:end], start, end, NOW,
        ))
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM evidence_excerpts"
        ).fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.parametrize("case", [
    "text_mismatch", "offsets_beyond_canonical", "failed_retrieval",
    "missing_retrieval", "truncation_tail", "span_below_min", "span_above_max",
    "whitespace_edge", "length_span_disagreement", "malformed_claim_hash",
])
def test_floor_rejects_inconsistent_excerpts(evidence_db, case):
    conn = _raw_connection(evidence_db)
    try:
        ok_id = _insert_retrieval(conn)
        failed_id = _insert_retrieval(
            conn, status="FAILED", http_status=404, fetch_error="HTTP_STATUS_404",
        )
        truncated_id = _insert_retrieval(conn, truncated=1)
        start, end = _aligned(PROBE_TEXT, 60)
        good = PROBE_TEXT[start:end]
        cases = {
                "text_mismatch": (ok_id, "x" * (end - start), start, end),
                "offsets_beyond_canonical": (
                    ok_id, PROBE_TEXT[-60:], len(PROBE_TEXT) - 55, len(PROBE_TEXT) + 5,
                ),
                "failed_retrieval": (failed_id, good, start, end),
                "missing_retrieval": (987654, good, start, end),
                "truncation_tail": (
                    truncated_id,
                    PROBE_TEXT[len(PROBE_TEXT) - 40:],
                    len(PROBE_TEXT) - 40,
                    len(PROBE_TEXT),
                ),
                "span_below_min": (
                    ok_id, PROBE_TEXT[start:start + MIN_EXCERPT_CHARS - 1],
                    start, start + MIN_EXCERPT_CHARS - 1,
                ),
                "span_above_max": (
                    ok_id, PROBE_TEXT[0:MAX_EXCERPT_CHARS + 7],
                    0, MAX_EXCERPT_CHARS + 7,
                ),
                "whitespace_edge": (
                    ok_id, PROBE_TEXT[PROBE_TEXT.index(" "):PROBE_TEXT.index(" ") + 40],
                    PROBE_TEXT.index(" "), PROBE_TEXT.index(" ") + 40,
                ),
                "length_span_disagreement": (ok_id, good, start, end + 1),
                "malformed_claim_hash": (ok_id, good, start, end),
        }
        rid, excerpt_text, s, e = cases[case]
        claim_hash = "XYZ-not-hex" if case == "malformed_claim_hash" else sha256_hex("claim")
        with pytest.raises(sqlite3.Error):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, "claim", claim_hash, excerpt_text, s, e, NOW,
            ))
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_tables_are_append_only(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        conn.execute(_EXCERPT_SQL, (
            ACCOUNT_A, rid, "claim", sha256_hex("claim"),
            PROBE_TEXT[start:end], start, end, NOW,
        ))
        conn.commit()
        for statement, params in (
            ("UPDATE evidence_retrievals SET canonical_text='tampered' WHERE id=?", (rid,)),
            ("DELETE FROM evidence_retrievals WHERE id=?", (rid,)),
            ("UPDATE evidence_excerpts SET excerpt_text='tampered' WHERE retrieval_id=?", (rid,)),
            ("DELETE FROM evidence_excerpts WHERE retrieval_id=?", (rid,)),
        ):
            with pytest.raises(sqlite3.Error, match="append-only"):
                conn.execute(statement, params)
            conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0] == 1
    finally:
        conn.close()


@pytest.mark.parametrize("mutation", [
    {"status": "OK", "fetch_error": "CONTRADICTION"},
    {"status": "OK", "http_status": 404},
    {"status": "OK", "http_status": None},
    {"status": "FAILED", "fetch_error": None},
    {"status": "UNKNOWN_STATUS"},
])
def test_floor_rejects_inconsistent_retrieval_rows(evidence_db, mutation):
    conn = _raw_connection(evidence_db)
    try:
        base = {
            "status": "OK", "http_status": 200, "fetch_error": None,
            "canonical_text": PROBE_TEXT, "truncated": 0,
        }
        base.update(mutation)
        text = base["canonical_text"] if base["status"] == "OK" else ""
        with pytest.raises(sqlite3.Error):
            conn.execute(
                _RETRIEVAL_SQL,
                (
                    ACCOUNT_A, "https://x", "https://x", NOW, base["status"],
                    base["http_status"], "text/html", base["fetch_error"],
                    len(text.encode("utf-8")), sha256_hex(text.encode("utf-8")),
                    len(text), sha256_hex(text),
                    # FAILED udający treść to osobny wariant tej samej podłogi:
                    text if base["status"] != "FAILED" else "fake content",
                    len(text) if base["status"] != "FAILED" else 12,
                    sha256_hex(text), base["truncated"], NOW,
                ),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_rejects_declared_length_and_hash_format_lies(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        common = (
            ACCOUNT_A, "https://x", "https://x", NOW, "OK", 200, "text/html", None,
            4, sha256_hex(b"wxyz"), 4, sha256_hex("wxyz"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_RETRIEVAL_SQL, (*common, "wxyz", 40, sha256_hex("wxyz"), 0, NOW))
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_RETRIEVAL_SQL, (*common, "wxyz", 4, "UPPER-NOT-HEX", 0, NOW))
        conn.rollback()
    finally:
        conn.close()


# --- E1-B01: NUL i zgodność interpretacji zakresów (repair po review) ---

def _nul_retrieval_params(text: str, *, declared_chars: int | None = None):
    return (
        ACCOUNT_A, "https://example.org/nul", "https://example.org/nul", NOW,
        "OK", 200, "text/html", None,
        len(text.encode("utf-8")), sha256_hex(text.encode("utf-8")),
        len(text), sha256_hex(text), text,
        declared_chars if declared_chars is not None else len(text),
        sha256_hex(text), 0, NOW,
    )


@pytest.mark.parametrize("position", ["before_range", "inside_range", "after_range"])
def test_floor_rejects_nul_anywhere_in_canonical_text(evidence_db, position):
    """NUL przed, w środku i po legalnym zakresie — zawsze odrzucony."""
    conn = _raw_connection(evidence_db)
    try:
        offsets = {"before_range": 2, "inside_range": 30, "after_range": len(PROBE_TEXT) - 3}
        at = offsets[position]
        text = PROBE_TEXT[:at] + "\x00" + PROBE_TEXT[at + 1:]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_RETRIEVAL_SQL, _nul_retrieval_params(text))
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_blocks_historical_length_stops_at_nul_exploit(evidence_db):
    """Dokładny exploit z review: length() SQLite zatrzymuje się na NUL, więc
    ``canonical_chars = length(canonical_text)`` dało się spełnić deklaracją
    liczby znaków sprzed NUL, desynchronizując substr() od Python slicing.
    Podłoga NUL musi zablokować taki wiersz w całości."""
    conn = _raw_connection(evidence_db)
    try:
        visible = PROBE_TEXT[:50]
        smuggled = visible + "\x00" + "HIDDEN TAIL NEVER ADDRESSABLE BY SQL"
        sqlite_length = conn.execute("SELECT length(?)", (smuggled,)).fetchone()[0]
        assert sqlite_length == 50  # potwierdzenie zachowania będącego exploitem
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                _RETRIEVAL_SQL,
                _nul_retrieval_params(smuggled, declared_chars=sqlite_length),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_rejects_nul_in_excerpt_text(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        smuggled = PROBE_TEXT[start:end - 1] + "\x00"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, "claim", sha256_hex("claim"), smuggled, start, end, NOW,
            ))
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_rejects_nul_in_claim_text(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        claim = "claim\x00with smuggled tail"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, claim, sha256_hex(claim),
                PROBE_TEXT[start:end], start, end, NOW,
            ))
        conn.rollback()
    finally:
        conn.close()


def test_floor_rejects_blob_canonical_text(evidence_db):
    """Kolumny tekstowe muszą być TEXT: BLOB miałby bajtową, nie znakową
    semantykę length()/substr() i rozjechałby offsety z Pythonem."""
    conn = _raw_connection(evidence_db)
    try:
        payload = PROBE_TEXT.encode("utf-8")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                _RETRIEVAL_SQL,
                (
                    ACCOUNT_A, "https://x", "https://x", NOW, "OK", 200,
                    "text/html", None, len(payload), sha256_hex(payload),
                    len(PROBE_TEXT), sha256_hex(PROBE_TEXT), payload,
                    len(payload), sha256_hex(payload), 0, NOW,
                ),
            )
        conn.rollback()
    finally:
        conn.close()


# --- E1-B02: authoritative canonical/claim hash (repair po review) ---

def test_floor_fails_closed_for_writer_without_hash_function(evidence_db):
    """Writer bez zarejestrowanej ``evidence_sha256_hex`` nie może INSERT-ować
    do tabel evidence w ogóle — kontrakt jest fail-closed, nie fail-open."""
    conn = sqlite3.connect(evidence_db)  # celowo BEZ rejestracji funkcji
    try:
        with pytest.raises(sqlite3.OperationalError, match="no such function"):
            conn.execute(
                _RETRIEVAL_SQL,
                (
                    ACCOUNT_A, "https://x", "https://x", NOW, "OK", 200,
                    "text/html", None, 4, sha256_hex(b"wxyz"), 4,
                    sha256_hex("wxyz"), "wxyz", 4, sha256_hex("wxyz"), 0, NOW,
                ),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_rejects_plausible_but_false_canonical_hash(evidence_db):
    """Poprawnie wyglądający (64 hex), ale fałszywy canonical_sha256 nie może
    utworzyć rekordu uznawanego przez kontrakt E1 za poprawny."""
    conn = _raw_connection(evidence_db)
    try:
        false_hash = sha256_hex("completely different text")
        assert false_hash != sha256_hex(PROBE_TEXT)
        with pytest.raises(sqlite3.IntegrityError, match="canonical_sha256"):
            conn.execute(
                _RETRIEVAL_SQL,
                (
                    ACCOUNT_A, "https://x", "https://x", NOW, "OK", 200,
                    "text/html", None,
                    len(PROBE_TEXT.encode("utf-8")), sha256_hex(PROBE_TEXT.encode("utf-8")),
                    len(PROBE_TEXT), sha256_hex(PROBE_TEXT), PROBE_TEXT,
                    len(PROBE_TEXT), false_hash, 0, NOW,
                ),
            )
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_rejects_plausible_but_false_claim_hash(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        false_hash = sha256_hex("not this claim")
        with pytest.raises(sqlite3.IntegrityError, match="claim_sha256"):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, "claim", false_hash,
                PROBE_TEXT[start:end], start, end, NOW,
            ))
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0] == 0
    finally:
        conn.close()


def test_floor_blocks_logical_duplicate_alt_claim_hash(evidence_db):
    """Dokładna kontrpróba reviewera (`logical_duplicate_alt_claim_hash`):
    ten sam account, retrieval, claim text i zakres NIE może zostać zapisany
    ponownie przez podmianę ``claim_sha256`` na inny, poprawnie wyglądający
    hash. Blokują go dwie niezależne podłogi: trigger authoritative claim hash
    oraz unikalność logicznej tożsamości (retrieval, claim_text, zakres)."""
    conn = _raw_connection(evidence_db)
    try:
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        good = PROBE_TEXT[start:end]
        conn.execute(_EXCERPT_SQL, (
            ACCOUNT_A, rid, "claim", sha256_hex("claim"), good, start, end, NOW,
        ))
        conn.commit()
        # Wariant 1: alternatywny, poprawnie wyglądający hash -> trigger.
        alt_hash = sha256_hex("claim-alternative-fingerprint")
        assert alt_hash != sha256_hex("claim") and len(alt_hash) == 64
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, "claim", alt_hash, good, start, end, NOW,
            ))
        conn.rollback()
        # Wariant 2: nawet z PRAWDZIWYM hashem duplikat logicznej tożsamości
        # zatrzymuje unikalność (retrieval_id, claim_text, start, end).
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_A, rid, "claim", sha256_hex("claim"), good, start, end, NOW,
            ))
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0] == 1
    finally:
        conn.close()


# --- E1-B03: trwały account scope (repair po review) ---

def test_floor_requires_non_blank_account_on_both_tables(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        for bad_account in (None, "", "   "):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    _RETRIEVAL_SQL,
                    (
                        bad_account, "https://x", "https://x", NOW, "OK", 200,
                        "text/html", None,
                        len(PROBE_TEXT.encode("utf-8")),
                        sha256_hex(PROBE_TEXT.encode("utf-8")),
                        len(PROBE_TEXT), sha256_hex(PROBE_TEXT), PROBE_TEXT,
                        len(PROBE_TEXT), sha256_hex(PROBE_TEXT), 0, NOW,
                    ),
                )
            conn.rollback()
        rid = _insert_retrieval(conn)
        start, end = _aligned(PROBE_TEXT, 60)
        for bad_account in (None, "", "   "):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(_EXCERPT_SQL, (
                    bad_account, rid, "claim", sha256_hex("claim"),
                    PROBE_TEXT[start:end], start, end, NOW,
                ))
            conn.rollback()
    finally:
        conn.close()


def test_floor_rejects_cross_account_excerpt_even_without_fk(evidence_db):
    """Excerpt konta B nie może cytować retrievalu konta A — lineage trigger
    działa także przy wyłączonym PRAGMA foreign_keys."""
    conn = _raw_connection(evidence_db)
    try:
        rid_a = _insert_retrieval(conn, account_id=ACCOUNT_A)
        start, end = _aligned(PROBE_TEXT, 60)
        with pytest.raises(sqlite3.IntegrityError, match="same account"):
            conn.execute(_EXCERPT_SQL, (
                ACCOUNT_B, rid_a, "claim", sha256_hex("claim"),
                PROBE_TEXT[start:end], start, end, NOW,
            ))
        conn.rollback()
        # Ta sama treść w zakresie własnego konta pozostaje legalna.
        rid_b = _insert_retrieval(conn, account_id=ACCOUNT_B)
        conn.execute(_EXCERPT_SQL, (
            ACCOUNT_B, rid_b, "claim", sha256_hex("claim"),
            PROBE_TEXT[start:end], start, end, NOW,
        ))
        conn.commit()
        rows = conn.execute(
            "SELECT account_id, retrieval_id FROM evidence_excerpts"
        ).fetchall()
        assert [(row["account_id"], row["retrieval_id"]) for row in rows] == [
            (ACCOUNT_B, rid_b),
        ]
    finally:
        conn.close()


def test_floor_enforces_account_reference_when_fk_is_on(evidence_db):
    conn = _raw_connection(evidence_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                _RETRIEVAL_SQL,
                (
                    "no-such-account", "https://x", "https://x", NOW, "OK", 200,
                    "text/html", None,
                    len(PROBE_TEXT.encode("utf-8")),
                    sha256_hex(PROBE_TEXT.encode("utf-8")),
                    len(PROBE_TEXT), sha256_hex(PROBE_TEXT), PROBE_TEXT,
                    len(PROBE_TEXT), sha256_hex(PROBE_TEXT), 0, NOW,
                ),
            )
        conn.rollback()
    finally:
        conn.close()


def test_sql_floor_constants_match_python_contract():
    """Stałe wkompilowane w SQL 0016 muszą równać się stałym weryfikatora."""
    sql = (MIGRATIONS_DIR / f"{EVIDENCE_SCHEMA_VERSION}.sql").read_text(encoding="utf-8")
    assert f"NEW.end_offset <= r.canonical_chars - {TRUNCATION_TAIL_GUARD_CHARS}" in sql
    assert (
        f"CHECK (end_offset - start_offset BETWEEN {MIN_EXCERPT_CHARS} AND {MAX_EXCERPT_CHARS})"
        in sql
    )
