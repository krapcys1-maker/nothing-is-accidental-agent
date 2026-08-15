"""Inherited, test-only boundary against network and production SQLite access."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import sqlite3
from typing import Any
from urllib.parse import unquote, urlparse


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROTECTED_DB = _PROJECT_ROOT / "data" / "agent.db"
_SCRUBBED_ENVIRONMENT = (
    "ANTHROPIC_API_KEY",
    "anthropic_api_key",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
_ORIGINAL_SQLITE_CONNECT = sqlite3.connect
_ACTIVATED = False


def _canonical_path(path: str) -> str | None:
    if path == ":memory:" or path.startswith(":memory:"):
        return None
    try:
        return os.path.normcase(str(Path(path).resolve(strict=False)))
    except (OSError, ValueError):
        return None


def canonical_sqlite_path(value: object) -> str | None:
    """Canonicalize SQLite filename and file-URI spellings without opening them."""
    if not isinstance(value, (str, bytes, os.PathLike)):
        return None
    raw = os.fsdecode(os.fspath(value))
    if raw == ":memory:":
        return None

    if raw.lower().startswith("file:"):
        parsed = urlparse(raw)
        # The test contract accepts only local SQLite file URIs.  A non-local
        # authority is never canonicalized into a safe temporary path and is
        # rejected by the connect guard before SQLite can interpret it.
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            raise RuntimeError("Tests reject non-local SQLite URI authorities.")
        # SQLite's ``file:relative.db`` is a URI even though it has no //.
        path = unquote(parsed.path)
        if not path and raw[5:].startswith(":memory:"):
            return None
        # ``file:///C:/...`` has one URI slash too many for Windows Path.
        if len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
            path = path[1:]
        return _canonical_path(path)
    return _canonical_path(raw)


def is_protected_sqlite_database(value: object) -> bool:
    """Whether ``value`` denotes the production database in the active test kernel."""
    if os.environ.get("NIA_TEST_MODE") != "1":
        return False
    protected = os.environ.get("NIA_TEST_PROTECTED_DB")
    if not protected:
        raise RuntimeError("NIA_TEST_MODE requires NIA_TEST_PROTECTED_DB.")
    return canonical_sqlite_path(value) == _canonical_path(protected)


def _blocked_network(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("Network access is blocked for the complete pytest process.")


def _guarded_sqlite_connect(database: object, *args: Any, **kwargs: Any):
    if is_protected_sqlite_database(database):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    return _ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


def _prepend_project_root_to_pythonpath() -> None:
    root = str(_PROJECT_ROOT)
    current = os.environ.get("PYTHONPATH", "")
    entries = [entry for entry in current.split(os.pathsep) if entry]
    if root not in entries:
        os.environ["PYTHONPATH"] = os.pathsep.join([root, *entries])


def _block_real_anthropic_construction() -> None:
    try:
        import anthropic
    except ImportError:
        return
    anthropic.Anthropic = _blocked_network
    if hasattr(anthropic, "AsyncAnthropic"):
        anthropic.AsyncAnthropic = _blocked_network


def activate() -> None:
    """Activate once, only for pytest or an explicitly inherited test process."""
    global _ACTIVATED
    if _ACTIVATED:
        return
    if os.environ.get("NIA_TEST_MODE") not in (None, "1"):
        raise RuntimeError("NIA test safety kernel refuses an invalid test-mode value.")
    os.environ["NIA_TEST_MODE"] = "1"
    os.environ.setdefault("NIA_TEST_PROTECTED_DB", _canonical_path(str(_DEFAULT_PROTECTED_DB)) or "")
    if not os.environ["NIA_TEST_PROTECTED_DB"]:
        raise RuntimeError("NIA test safety kernel cannot resolve the protected database.")
    for name in _SCRUBBED_ENVIRONMENT:
        os.environ.pop(name, None)
    _prepend_project_root_to_pythonpath()

    sqlite3.connect = _guarded_sqlite_connect
    sqlite3.dbapi2.connect = _guarded_sqlite_connect
    socket.socket.connect = _blocked_network
    socket.socket.connect_ex = _blocked_network
    socket.socket.sendto = _blocked_network
    socket.create_connection = _blocked_network
    socket.getaddrinfo = _blocked_network
    _block_real_anthropic_construction()
    _ACTIVATED = True
