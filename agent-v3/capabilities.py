"""Centralna polityka efektów zewnętrznych prototypu Agent V3.

Ten moduł nie wykonuje sieci ani I/O poza sprawdzeniem znacznika prototypu.
Każda granica transportowa pyta go o możliwość bezpośrednio przed działaniem.
Stan jest czytany dynamicznie ze środowiska, więc wyłącznik działa także po
uruchomieniu procesu.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path


class CapabilityDenied(RuntimeError):
    """Żądana możliwość jest zabroniona przez politykę prototypu."""


class Mode(str, Enum):
    FIXTURE = "fixture"
    MODEL_TEST = "model_test"
    LIVE_READ_ONLY = "live_read_only"
    LIVE_TEST = "live_test"


class Capability(str, Enum):
    MODEL_CALL = "model_call"
    PUBLIC_WEB_READ = "public_web_read"
    SUBSTACK_READ = "substack_read"
    SESSION_WRITE = "session_write"
    ALERT_SEND = "alert_send"
    LIKE = "like"
    FOLLOW = "follow"
    SUBSCRIBE = "subscribe"
    SETTINGS = "settings"
    REPLY = "reply"
    PUBLISH_ARTICLE = "publish_article"
    PUBLISH_NOTE = "publish_note"
    COMMENT = "comment"
    RESTACK = "restack"


PROTOTYPE_MARKER = Path(__file__).resolve().parent / "TO_JEST_KOPIA_TESTOWA"
PRODUCTION_HANDLE = "nothingisaccidental"
LIVE_TEST_CONFIRMATION = "V3_ISOLATED_TEST_ACCOUNT"

MUTATIONS = frozenset({
    Capability.LIKE,
    Capability.FOLLOW,
    Capability.SUBSCRIBE,
    Capability.SETTINGS,
    Capability.REPLY,
    Capability.PUBLISH_ARTICLE,
    Capability.PUBLISH_NOTE,
    Capability.COMMENT,
    Capability.RESTACK,
})

ALLOWED_BY_MODE = {
    Mode.FIXTURE: frozenset(),
    Mode.MODEL_TEST: frozenset({
        Capability.MODEL_CALL,
        Capability.PUBLIC_WEB_READ,
    }),
    Mode.LIVE_READ_ONLY: frozenset({
        Capability.MODEL_CALL,
        Capability.PUBLIC_WEB_READ,
        Capability.SUBSTACK_READ,
    }),
    Mode.LIVE_TEST: frozenset(Capability),
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def current_mode() -> Mode:
    raw = _env("AGENT_V3_MODE", Mode.FIXTURE.value)
    try:
        return Mode(raw)
    except ValueError as exc:
        known = ", ".join(mode.value for mode in Mode)
        raise CapabilityDenied(
            f"nieznany AGENT_V3_MODE={raw!r}; dozwolone: {known}"
        ) from exc


def kill_switch_active() -> bool:
    """Wyłącznik jest domyślnie aktywny i odczytywany przy każdym żądaniu."""
    return _truthy(_env("AGENT_V3_KILL_SWITCH", "1"))


def _test_target() -> tuple[str, str]:
    return (
        _env("AGENT_V3_TEST_ACCOUNT_HANDLE").lower(),
        _env("AGENT_V3_SUBSTACK_HANDLE").lower(),
    )


def _require_isolated_target(*, mutation: bool) -> None:
    expected, target = _test_target()
    if not expected or not target:
        raise CapabilityDenied(
            "brak AGENT_V3_TEST_ACCOUNT_HANDLE lub AGENT_V3_SUBSTACK_HANDLE"
        )
    if expected != target:
        raise CapabilityDenied(
            "cel Substacka nie jest zgodny z odseparowanym kontem testowym"
        )
    if target == PRODUCTION_HANDLE:
        raise CapabilityDenied(
            f"V3 ma bezwarunkowy zakaz celu produkcyjnego {PRODUCTION_HANDLE!r}"
        )
    if not PROTOTYPE_MARKER.is_file():
        raise CapabilityDenied("brak znacznika prototypu V3")
    if mutation and _env("AGENT_V3_LIVE_TEST_CONFIRM") != LIVE_TEST_CONFIRMATION:
        raise CapabilityDenied("brak dokładnego potwierdzenia trybu live_test")


def require(capability: Capability | str) -> None:
    """Odmawia przed transportem, jeśli proces nie ma danej możliwości."""
    try:
        requested = Capability(capability)
    except ValueError as exc:
        raise CapabilityDenied(f"nieznana możliwość: {capability!r}") from exc

    mode = current_mode()
    if kill_switch_active():
        raise CapabilityDenied("AGENT_V3_KILL_SWITCH jest aktywny")
    if requested not in ALLOWED_BY_MODE[mode]:
        raise CapabilityDenied(
            f"tryb {mode.value!r} nie zezwala na {requested.value!r}"
        )
    if requested == Capability.SUBSTACK_READ:
        _require_isolated_target(mutation=False)
    elif requested == Capability.SESSION_WRITE:
        _require_isolated_target(mutation=True)
    elif requested == Capability.ALERT_SEND:
        if _env("AGENT_V3_LIVE_TEST_CONFIRM") != LIVE_TEST_CONFIRMATION:
            raise CapabilityDenied("brak dokładnego potwierdzenia trybu live_test")
    elif requested in MUTATIONS:
        _require_isolated_target(mutation=True)


def assert_runtime_account(actual_handle: str) -> None:
    """Dowodzi, że zalogowana sesja należy do skonfigurowanego konta testowego."""
    require(Capability.PUBLISH_ARTICLE)
    expected, _ = _test_target()
    actual = (actual_handle or "").strip().lower()
    if actual != expected:
        raise CapabilityDenied(
            f"sesja należy do {actual!r}, oczekiwano konta testowego {expected!r}"
        )


def status() -> dict[str, object]:
    """Bezsekretowy opis polityki do logu i testów."""
    expected, target = _test_target()
    mode = current_mode()
    return {
        "mode": mode.value,
        "kill_switch": kill_switch_active(),
        "prototype_marker": PROTOTYPE_MARKER.is_file(),
        "test_target_configured": bool(expected and target and expected == target),
        "production_target": target == PRODUCTION_HANDLE,
    }
