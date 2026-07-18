"""Canonical fail-closed security flag profile shared by storage and operations."""
from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping


SECURITY_FLAG_DEFAULTS: Final[Mapping[str, bool]] = MappingProxyType({
    "kill_switch": True,
    "safe_mode": True,
    "worker_enabled": False,
    "paid_actions_enabled": False,
    "browser_actions_enabled": False,
})
