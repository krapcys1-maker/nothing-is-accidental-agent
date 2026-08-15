"""Process-wide regression tests for the pytest safety kernel."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from urllib.parse import quote

import pytest

from app.storage.db import connect


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_DB = _PROJECT_ROOT / "data" / "agent.db"


def test_network_and_sensitive_environment_are_blocked_before_test_execution():
    for name in (
        "ANTHROPIC_API_KEY", "anthropic_api_key", "HTTP_PROXY", "http_proxy",
        "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy",
        "NO_PROXY", "no_proxy",
    ):
        assert name not in os.environ
    with pytest.raises(RuntimeError, match="Network access is blocked"):
        socket.create_connection(("example.com", 443))
    with pytest.raises(RuntimeError, match="Network access is blocked"):
        socket.getaddrinfo("example.com", 443)


@pytest.mark.parametrize("path", [
    _PROJECT_DB,
    Path("data") / "agent.db",
    Path("data") / "subdir" / ".." / "agent.db",
    "file:data/agent.db",
    "file:data/agent.db?mode=ro",
    "file:data/agent.db?mode=rw",
    "file:data/agent.db?mode=rwc",
    _PROJECT_DB.as_uri(),
    f"{_PROJECT_DB.as_uri()}?mode=ro",
    "file:" + quote(str(_PROJECT_DB).replace("\\", "/")),
])
def test_raw_sqlite_and_project_wrapper_reject_all_production_path_spellings(path):
    with pytest.raises(RuntimeError, match="must not open"):
        sqlite3.connect(path)
    with pytest.raises(RuntimeError, match="must not open"):
        connect(path)


def test_sqlite_dbapi2_connect_is_guarded_too():
    with pytest.raises(RuntimeError, match="must not open"):
        sqlite3.dbapi2.connect("file:data/agent.db?mode=ro", uri=True)


def test_real_anthropic_sdk_construction_is_blocked_but_injected_fake_remains_usable():
    import anthropic

    with pytest.raises(RuntimeError, match="Network access is blocked"):
        anthropic.Anthropic(api_key="test-only")

    class FakeSdk:
        def __init__(self, marker):
            self.marker = marker

    assert FakeSdk("fake").marker == "fake"


def test_available_async_anthropic_sdk_construction_is_blocked_too():
    import anthropic

    async_client = getattr(anthropic, "AsyncAnthropic", None)
    if async_client is None:
        pytest.skip("Installed SDK does not expose AsyncAnthropic.")
    with pytest.raises(RuntimeError, match="Network access is blocked"):
        async_client(api_key="test-only")


@pytest.mark.parametrize("database", [
    str(_PROJECT_DB)[:1].lower() + str(_PROJECT_DB)[1:],
    "file:" + str(_PROJECT_DB).replace("/", "\\\\") + "?mode=ro",
    "file://localhost/" + _PROJECT_DB.as_posix().lstrip("/") + "?mode=ro",
])
def test_protected_database_backslashes_windows_drive_case_and_local_uri_are_blocked(database):
    # ``normcase`` makes the comparison drive-case-insensitive on Windows.  The
    # path spellings are deliberately passed to raw sqlite, not pre-normalized.
    with pytest.raises(RuntimeError, match="must not open"):
        sqlite3.connect(database, uri=database.lower().startswith("file:"))


def test_nonlocal_sqlite_uri_authority_is_rejected_fail_closed():
    with pytest.raises(RuntimeError, match="non-local SQLite URI authorities"):
        sqlite3.connect("file://example.test/tmp/agent.db?mode=ro", uri=True)


def test_subprocess_inherits_production_db_protection():
    code = (
        "from pathlib import Path; "
        "from app.storage.repositories import SqliteStorage; "
        "\ntry:\n SqliteStorage.open(Path('data') / 'agent.db')\n"
        "except RuntimeError as exc:\n print(type(exc).__name__)\n"
        "else:\n raise SystemExit('unsafe production database open')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RuntimeError" in result.stdout


@pytest.mark.parametrize("database", [
    "data/agent.db",
    "file:data/agent.db?mode=ro",
    _PROJECT_DB.as_uri(),
])
def test_subprocess_blocks_sqlite_spellings_without_opening_the_database(database):
    code = (
        "import sqlite3\n"
        f"database = {database!r}\n"
        "try:\n sqlite3.connect(database, uri=database.startswith('file:'))\n"
        "except RuntimeError as exc:\n print(type(exc).__name__)\n"
        "else:\n raise SystemExit('unsafe production database open')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RuntimeError" in result.stdout


def test_subprocess_blocks_network_dns_and_real_sdk_and_scrubs_environment():
    code = (
        "import os, socket, anthropic\n"
        "names=('ANTHROPIC_API_KEY','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY',"
        "'http_proxy','https_proxy','all_proxy','no_proxy')\n"
        "assert not any(name in os.environ for name in names)\n"
        "for operation in (lambda: socket.create_connection(('example.com',443)), "
        "lambda: socket.getaddrinfo('example.com',443), "
        "lambda: anthropic.Anthropic(api_key='test-only')):\n"
        " try:\n  operation()\n except RuntimeError:\n  pass\n else:\n  raise SystemExit('unsafe subprocess operation')\n"
        "print('blocked')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "blocked"


def test_subprocess_scrubs_lowercase_anthropic_key_before_configuration_import():
    code = (
        "import os\n"
        "assert 'anthropic_api_key' not in os.environ\n"
        "from app.core.config import load_settings\n"
        "assert 'anthropic_api_key' not in os.environ\n"
        "print('scrubbed')\n"
    )
    environment = dict(os.environ)
    environment["anthropic_api_key"] = "test-only-lowercase-secret"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT, env=environment,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "scrubbed"


def test_subprocess_still_allows_a_temporary_sqlite_database(tmp_path):
    temporary_db = tmp_path / "allowed.db"
    code = (
        "import sqlite3\n"
        f"connection = sqlite3.connect({str(temporary_db)!r})\n"
        "connection.execute('CREATE TABLE allowed(value INTEGER)')\n"
        "connection.close()\n"
        "print('allowed')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_PROJECT_ROOT,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "allowed"
