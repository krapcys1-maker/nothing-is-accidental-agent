"""Owner-proposed topic intake — kanoniczny, deterministyczny kontrakt propozycji.

Ta warstwa jest CZYSTA: waliduje i normalizuje wejście operatora, liczy score
tym samym deterministycznym scorerem co tematy z modelu i wylicza fingerprint
kanonicznego payloadu. Nie dotyka sieci, providera, kosztu, ledgeru ani storage.

Propozycja właściciela NIE jest wygenerowana przez model — dlatego nie ma
breakdownu od providera. Zamknięty kontrakt jest taki: operator podaje pełny,
jawny breakdown redakcyjny (dokładnie te same wymiary co wagi konta, każdy
w zakresie 0..1), a wynik liczy istniejący `compute_weighted_score`. Dzięki temu
nie ma sztucznego „100 bez polityki": ta sama skala, te same wagi i ten sam próg
`article_min_score` decydują o tym, czy temat w ogóle może zostać `SELECTED`.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping

from app.core.sanitization import sanitize_persistent_text

OWNER_TOPIC_PROPOSAL_OBJECT_TYPE = "OWNER_TOPIC_PROPOSAL"
OWNER_TOPIC_PROPOSAL_SOURCE = "owner_proposal"
PROPOSAL_SCHEMA = "owner_topic_proposal_v1"

MAX_TITLE_CHARS = 200
MAX_QUESTION_CHARS = 400
MAX_RATIONALE_CHARS = 1000
MAX_OPERATION_KEY_CHARS = 96
MAX_PROPOSER_CHARS = 120

_OPERATION_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_WS_RE = re.compile(r"\s+")


class OwnerTopicProposalError(RuntimeError):
    """Typowana odmowa intake'u propozycji właściciela (zawsze przed zapisem)."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def normalize_proposal_text(
    value: object, *, field: str, max_chars: int, code: str, required: bool = True,
) -> str | None:
    """Jedna deterministyczna normalizacja tekstu operatora.

    Sekrety są redagowane tym samym sanitizerem co inne trwałe teksty, białe
    znaki są składane, a długość jest zamknięta — kanoniczny payload i jego
    fingerprint nie mogą zależeć od formatowania wejścia.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise OwnerTopicProposalError(code, f"{field} must be a non-empty string.")
        return None
    if not isinstance(value, str):
        raise OwnerTopicProposalError(code, f"{field} must be a string.")
    text = _WS_RE.sub(" ", sanitize_persistent_text(value).strip())
    if not text:
        raise OwnerTopicProposalError(code, f"{field} must be a non-empty string.")
    if len(text) > max_chars:
        raise OwnerTopicProposalError(
            code, f"{field} exceeds the {max_chars} character limit.",
        )
    return text


def validate_operation_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OwnerTopicProposalError(
            "OPERATION_KEY_INVALID", "operation_key must be a non-empty string.",
        )
    key = value.strip()
    if len(key) > MAX_OPERATION_KEY_CHARS or not _OPERATION_KEY_RE.match(key):
        raise OwnerTopicProposalError(
            "OPERATION_KEY_INVALID",
            "operation_key accepts only letters, digits, '-' and '_' (max "
            f"{MAX_OPERATION_KEY_CHARS}).",
        )
    return key


def validate_score_breakdown(
    breakdown: Mapping[str, object], weights: Mapping[str, float],
) -> dict[str, float]:
    """Zamknięty kontrakt oceny: dokładnie wymiary wag konta, każdy 0..1."""
    if not isinstance(breakdown, Mapping) or set(breakdown) != set(weights):
        expected = ", ".join(sorted(weights))
        raise OwnerTopicProposalError(
            "SCORE_BREAKDOWN_INVALID",
            f"score breakdown must contain exactly these dimensions: {expected}.",
        )
    normalized: dict[str, float] = {}
    for key in sorted(breakdown):
        raw = breakdown[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise OwnerTopicProposalError(
                "SCORE_BREAKDOWN_INVALID", f"score '{key}' must be a number in 0..1.",
            )
        value = float(raw)
        if not 0.0 <= value <= 1.0:
            raise OwnerTopicProposalError(
                "SCORE_BREAKDOWN_INVALID", f"score '{key}' must be within 0..1.",
            )
        normalized[key] = round(value, 6)
    return normalized


def canonical_proposal_payload(
    *,
    account_id: str,
    title: str,
    question: str,
    rationale: str | None,
    score_breakdown: Mapping[str, float],
    score: float,
    operation_key: str,
    proposed_by: str,
    owner_authored: bool,
    expires_at: str,
) -> dict[str, object]:
    """Deterministyczny preimage fingerprintu — bez topic_id i bez czasu zapisu."""
    if owner_authored is not True:
        raise OwnerTopicProposalError(
            "OWNER_AUTHORSHIP_NOT_CONFIRMED",
            "the proposal must be explicitly confirmed as owner-authored, not model-generated.",
        )
    return {
        "schema": PROPOSAL_SCHEMA,
        "account_id": account_id,
        "title": title,
        "question": question,
        "rationale": rationale,
        "score_breakdown": {key: float(value) for key, value in sorted(score_breakdown.items())},
        "score": float(score),
        "operation_key": operation_key,
        "proposed_by": proposed_by,
        "owner_authored": True,
        "expires_at": expires_at,
    }


def canonical_proposal_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def proposal_fingerprint(payload: Mapping[str, object]) -> str:
    """SHA-256 kanonicznego JSON-a propozycji (bez pola fingerprint)."""
    material = {key: value for key, value in payload.items() if key != "fingerprint"}
    return hashlib.sha256(canonical_proposal_json(material).encode("utf-8")).hexdigest()


def frozen_proposal_json(payload: Mapping[str, object]) -> tuple[str, str]:
    """Zwraca (kanoniczny JSON preimage, fingerprint) dla trwałego zapisu."""
    fingerprint = proposal_fingerprint(payload)
    return canonical_proposal_json(payload), fingerprint
