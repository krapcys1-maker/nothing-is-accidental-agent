"""Wersjonowany, trwały kontrakt jednego kontrolowanego pobrania (E2-B).

`controlled_fetch_intent_v1` opisuje DOKŁADNIE jedno przyszłe pobranie jednego
jawnie wskazanego dokumentu http/https. Kontrakt jest zamknięty (exact keys),
deterministycznie kanonizowany i samopodpisany fingerprintem SHA-256, dzięki
czemu approval L1 i transakcja startu mogą go rewalidować bajt-w-bajt.

Intent NIE MOŻE wybierać modelu, providera LLM, kosztu modelu, przeglądarki,
publikacji ani żadnego modułu wykonawczego — zawiera wyłącznie dane jednego
pobrania. `offline_evidence_v1` pozostaje osobnym kontraktem offline i nigdy
nie autoryzuje wykonania zewnętrznego.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

CONTROLLED_FETCH_EXECUTION = "controlled_fetch_v1"
CONTROLLED_FETCH_INTENT_VERSION = "controlled_fetch_intent_v1"

# Zamknięte limity kontraktu v1 (pinowane testami; zmiana = nowa decyzja).
MIN_FETCH_TIMEOUT_SECONDS = 1
MAX_FETCH_TIMEOUT_SECONDS = 120
MIN_FETCH_MAX_BYTES = 1
MAX_FETCH_MAX_BYTES = 2_000_000  # == app.research.evidence.MAX_RAW_FETCH_BYTES
MIN_FETCH_MAX_REDIRECTS = 0
MAX_FETCH_MAX_REDIRECTS = 5
# Jedyne typy treści obsługiwane przez kontrakt v1 (media type bez parametrów).
SUPPORTED_FETCH_CONTENT_TYPES = ("text/html", "text/plain")

_INTENT_KEYS = {
    "version", "account_id", "topic_id", "source_identity", "requested_url",
    "timeout_seconds", "max_bytes", "max_redirects", "allowed_content_types",
    "requested_at", "expires_at", "fingerprint",
}
_PAYLOAD_KEYS = {"account_id", "topic_id", "dry_run", "execution", "execution_intent"}
_CANONICAL_TS = "%Y-%m-%dT%H:%M:%SZ"


class ControlledFetchIntentError(ValueError):
    """Kontrolowana odmowa: intent nie spełnia zamkniętego kontraktu v1."""


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlledFetchIntentError(f"{field} must be non-empty text.")
    return value


def _require_int(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlledFetchIntentError(f"{field} must be a plain integer.")
    if not minimum <= value <= maximum:
        raise ControlledFetchIntentError(
            f"{field} {value} is outside the closed bound [{minimum}, {maximum}]."
        )
    return value


def canonical_utc_timestamp(moment: datetime) -> str:
    """Serialize one aware datetime as the canonical fingerprintable UTC form."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ControlledFetchIntentError("intent timestamps require an explicit timezone.")
    return moment.astimezone(timezone.utc).replace(microsecond=0).strftime(_CANONICAL_TS)


def parse_canonical_utc_timestamp(value: Any, *, field: str) -> datetime:
    """Accept only the exact canonical UTC serialization (fail-closed exactness)."""
    text = _require_text(value, field=field)
    try:
        parsed = datetime.strptime(text, _CANONICAL_TS).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ControlledFetchIntentError(
            f"{field} must use the canonical UTC form YYYY-MM-DDTHH:MM:SSZ."
        ) from exc
    if canonical_utc_timestamp(parsed) != text:
        raise ControlledFetchIntentError(f"{field} is not canonical.")
    return parsed


def controlled_fetch_intent_fingerprint(fields: dict[str, Any]) -> str:
    """SHA-256 kanonicznego JSON wszystkich pól intentu poza fingerprintem."""
    domain = {key: fields[key] for key in sorted(_INTENT_KEYS - {"fingerprint"})}
    encoded = json.dumps(domain, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ControlledFetchIntent:
    version: str
    account_id: str
    topic_id: int
    source_identity: str
    requested_url: str
    timeout_seconds: int
    max_bytes: int
    max_redirects: int
    allowed_content_types: tuple[str, ...]
    requested_at: str
    expires_at: str
    fingerprint: str

    @classmethod
    def build(
        cls, *, account_id: str, topic_id: int, source_identity: str,
        requested_url: str, timeout_seconds: int, max_bytes: int,
        max_redirects: int, allowed_content_types: tuple[str, ...] | list[str],
        requested_at: datetime, expires_at: datetime,
    ) -> "ControlledFetchIntent":
        """Construct one canonical intent; the fingerprint is derived, never given."""
        fields: dict[str, Any] = {
            "version": CONTROLLED_FETCH_INTENT_VERSION,
            "account_id": account_id,
            "topic_id": topic_id,
            "source_identity": source_identity,
            "requested_url": requested_url,
            "timeout_seconds": timeout_seconds,
            "max_bytes": max_bytes,
            "max_redirects": max_redirects,
            "allowed_content_types": list(allowed_content_types),
            "requested_at": canonical_utc_timestamp(requested_at),
            "expires_at": canonical_utc_timestamp(expires_at),
        }
        fields["fingerprint"] = controlled_fetch_intent_fingerprint(fields)
        return cls.from_payload(fields)

    @classmethod
    def from_payload(cls, raw: Any) -> "ControlledFetchIntent":
        if not isinstance(raw, dict) or set(raw) != _INTENT_KEYS:
            raise ControlledFetchIntentError(
                "controlled fetch intent must contain exactly: "
                + ", ".join(sorted(_INTENT_KEYS)) + "."
            )
        if raw["version"] != CONTROLLED_FETCH_INTENT_VERSION:
            raise ControlledFetchIntentError("unsupported controlled fetch intent version.")
        account_id = _require_text(raw["account_id"], field="account_id")
        topic_id = _require_int(raw["topic_id"], field="topic_id", minimum=1, maximum=2**31)
        source_identity = _require_text(raw["source_identity"], field="source_identity")
        requested_url = _require_text(raw["requested_url"], field="requested_url")
        if requested_url != requested_url.strip():
            raise ControlledFetchIntentError("requested_url cannot carry edge whitespace.")
        timeout_seconds = _require_int(
            raw["timeout_seconds"], field="timeout_seconds",
            minimum=MIN_FETCH_TIMEOUT_SECONDS, maximum=MAX_FETCH_TIMEOUT_SECONDS,
        )
        max_bytes = _require_int(
            raw["max_bytes"], field="max_bytes",
            minimum=MIN_FETCH_MAX_BYTES, maximum=MAX_FETCH_MAX_BYTES,
        )
        max_redirects = _require_int(
            raw["max_redirects"], field="max_redirects",
            minimum=MIN_FETCH_MAX_REDIRECTS, maximum=MAX_FETCH_MAX_REDIRECTS,
        )
        allowed_raw = raw["allowed_content_types"]
        if (
            not isinstance(allowed_raw, list) or not allowed_raw
            or len(set(allowed_raw)) != len(allowed_raw)
            or any(item not in SUPPORTED_FETCH_CONTENT_TYPES for item in allowed_raw)
        ):
            raise ControlledFetchIntentError(
                "allowed_content_types must be a non-empty unique subset of: "
                + ", ".join(SUPPORTED_FETCH_CONTENT_TYPES) + "."
            )
        requested_at = parse_canonical_utc_timestamp(raw["requested_at"], field="requested_at")
        expires_at = parse_canonical_utc_timestamp(raw["expires_at"], field="expires_at")
        if expires_at <= requested_at:
            raise ControlledFetchIntentError("expires_at must be after requested_at.")
        fingerprint = _require_text(raw["fingerprint"], field="fingerprint")
        expected = controlled_fetch_intent_fingerprint(raw)
        if fingerprint != expected:
            raise ControlledFetchIntentError(
                "fingerprint does not match the canonical intent content."
            )
        return cls(
            version=CONTROLLED_FETCH_INTENT_VERSION,
            account_id=account_id, topic_id=topic_id,
            source_identity=source_identity, requested_url=requested_url,
            timeout_seconds=timeout_seconds, max_bytes=max_bytes,
            max_redirects=max_redirects,
            allowed_content_types=tuple(allowed_raw),
            requested_at=raw["requested_at"], expires_at=raw["expires_at"],
            fingerprint=fingerprint,
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "account_id": self.account_id,
            "topic_id": self.topic_id,
            "source_identity": self.source_identity,
            "requested_url": self.requested_url,
            "timeout_seconds": self.timeout_seconds,
            "max_bytes": self.max_bytes,
            "max_redirects": self.max_redirects,
            "allowed_content_types": list(self.allowed_content_types),
            "requested_at": self.requested_at,
            "expires_at": self.expires_at,
            "fingerprint": self.fingerprint,
        }

    def expires_at_datetime(self) -> datetime:
        return parse_canonical_utc_timestamp(self.expires_at, field="expires_at")


def canonicalize_controlled_fetch_payload(payload: Any) -> dict[str, Any]:
    """Validate the complete durable job payload of one controlled fetch job."""
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise ControlledFetchIntentError(
            "controlled fetch payload must contain exactly: "
            + ", ".join(sorted(_PAYLOAD_KEYS)) + "."
        )
    if payload["execution"] != CONTROLLED_FETCH_EXECUTION:
        raise ControlledFetchIntentError("controlled fetch payload execution is invalid.")
    if payload["dry_run"] is not False:
        # Kontrolowane pobranie jest efektem zewnętrznym; nigdy nie udaje dry-run.
        raise ControlledFetchIntentError("controlled fetch payload requires dry_run=false.")
    intent = ControlledFetchIntent.from_payload(payload["execution_intent"])
    account_id = _require_text(payload["account_id"], field="account_id")
    if isinstance(payload["topic_id"], bool) or not isinstance(payload["topic_id"], int):
        raise ControlledFetchIntentError("controlled fetch payload topic_id is invalid.")
    if account_id != intent.account_id or payload["topic_id"] != intent.topic_id:
        raise ControlledFetchIntentError(
            "controlled fetch payload identity must match its execution_intent."
        )
    return {
        "account_id": account_id,
        "topic_id": payload["topic_id"],
        "dry_run": False,
        "execution": CONTROLLED_FETCH_EXECUTION,
        "execution_intent": intent.as_payload(),
    }
