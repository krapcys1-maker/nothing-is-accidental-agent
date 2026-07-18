"""Independent offline disproof for PR1-MAJ-005 using one throwaway SQLite file."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.testing.safety_kernel import activate as _activate_safety_kernel  # noqa: E402

_activate_safety_kernel()

from app.storage.db import (  # noqa: E402
    RUNTIME_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    SchemaVersionTooOld,
    database_schema_versions,
    initialize_database,
    migrate_0014_to_0015,
)
from app.storage.repositories import SqliteStorage  # noqa: E402


def _fingerprint(path: Path):
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        stat.st_size,
        stat.st_mtime_ns,
        tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")),
        database_schema_versions(path),
    )


def main() -> int:
    checks: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="nia-runtime-schema-gate-") as tmp:
        path = Path(tmp) / "schema-gate.db"
        initialize_database(path, through=STAGE1_SCHEMA_VERSION)
        before = _fingerprint(path)
        checks.append(before[3] == (False, False, False))
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        checks.append(_fingerprint(path) == before)
        checks.append(len(before[4]) == 14 and before[4][-1] == STAGE1_SCHEMA_VERSION)

        migrated = migrate_0014_to_0015(path)
        checks.append(migrated.applied_migrations == (RUNTIME_SCHEMA_VERSION,))
        checks.append(len(database_schema_versions(path)) == 15)
        runtime = SqliteStorage.open(path)
        runtime.close()
        checks.append(True)
        repeated = migrate_0014_to_0015(path)
        checks.append(repeated.idempotent and repeated.applied_migrations == ())

    passed = sum(checks)
    print(f"[BLOCKED] runtime schema-gate disproof: {passed}/{len(checks)}")
    return 0 if passed == len(checks) == 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
