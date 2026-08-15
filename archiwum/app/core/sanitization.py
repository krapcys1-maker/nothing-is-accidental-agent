"""Canonical redaction for durable operator and diagnostic artifacts."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Mapping


_SENSITIVE_KEY = re.compile(
    r"(authorization|api[_-]?key|secret|password|token|prompt|question|guidance|"
    r"payload|(?:request|response)?[_-]?headers?|sdk[_-]?object|exception|cause)",
    re.IGNORECASE,
)
_SAFE_SENSITIVE_KEYS = frozenset({
    "worker_execution_token_hash",
    "pricing_fingerprint",
    "execution_intent_fingerprint",
    "preflight_fingerprint",
    "diagnostic_fingerprint",
    "max_tokens",
})
_AUTH_VALUE = re.compile(
    r"(?i)\b(?P<label>authorization)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;}\]]+"
)
_NAMED_SECRET_VALUE = re.compile(
    r"(?i)\b(?P<label>x-api-key|api[_ -]?key|secret|password|"
    r"access[_ -]?token|token)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;}\]]+"
)
_BEARER_VALUE = re.compile(r"(?i)\b(?P<label>bearer)\s+[^\s,;}\]]+")
_PROVIDER_KEY = re.compile(r"\b(?:sk|ant|key)-[A-Za-z0-9_-]{8,}\b")
_HEADER_OR_EXCEPTION_VALUE = re.compile(
    r"(?im)\b(?:request[_ -]?headers?|response[_ -]?headers?|headers?|"
    r"nested[_ -]?exception|exception[_ -]?cause|sdk[_ -]?object|cause)"
    r"\s*[:=]\s*[^\r\n]*"
)
_CLI_SENSITIVE_VALUE = re.compile(
    r"(?is)(?P<prefix>(?:^|\s)--(?:authorization|api[-_]?key|secret|password|"
    r"token|prompt|question|guidance|payload)(?:\s*=\s*|\s+))"
    r"(?P<value>.*?)(?=(?:\s+--[a-z0-9_-]+(?:\s|=))|$)"
)


def sanitize_persistent_text(
    value: object,
    *,
    preserve_safe_labels: bool = False,
) -> str:
    """Redact credentials and provider internals from durable free-form text."""
    redacted = str(value)
    redacted = _HEADER_OR_EXCEPTION_VALUE.sub("[REDACTED]", redacted)
    if preserve_safe_labels:
        redacted = _AUTH_VALUE.sub(
            lambda match: f"{match.group('label')}=[REDACTED]", redacted
        )
        redacted = _NAMED_SECRET_VALUE.sub(
            lambda match: f"{match.group('label')}=[REDACTED]", redacted
        )
        redacted = _BEARER_VALUE.sub("Bearer [REDACTED]", redacted)
    else:
        redacted = _AUTH_VALUE.sub("[REDACTED]", redacted)
        redacted = _NAMED_SECRET_VALUE.sub("[REDACTED]", redacted)
        redacted = _BEARER_VALUE.sub("[REDACTED]", redacted)
    redacted = _PROVIDER_KEY.sub("[REDACTED]", redacted)
    redacted = _CLI_SENSITIVE_VALUE.sub(
        lambda match: f"{match.group('prefix')}[REDACTED]", redacted
    )
    for env_key, env_value in os.environ.items():
        if env_value and len(env_value) >= 8 and _SENSITIVE_KEY.search(env_key):
            redacted = redacted.replace(env_value, "[REDACTED]")
    return redacted


def sanitize_persistent_payload(value: object, *, key: str = "") -> object:
    """Recursively sanitize values before any durable serialization."""
    if _SENSITIVE_KEY.search(key) and key not in _SAFE_SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_persistent_payload(
                item_value, key=str(item_key)
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_persistent_payload(item, key=key) for item in value]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str):
        return sanitize_persistent_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_persistent_text(value)
