"""Fundament lokalnego evidence (Etap 2, fala E1).

Trzy odpowiedzialności — i tylko one:

1. **Jedna kanonizacja tekstu.** `canonicalize_text` jest jedyną funkcją
   normalizującą tekst cytowalny. Offsety excerptów ZAWSZE adresują utrwalony
   `canonical_text`; pierwotna ekstrakcja jest wyłącznie fingerprintowana
   (hash + długość), nigdy adresowana.
2. **Deterministyczna budowa retrievalu.** `build_evidence_retrieval` zamienia
   surowy `FetchedDocument` w kompletny, klasyfikowany rekord evidence dla
   jawnie wskazanego konta (status OK/FAILED, hashe łańcucha raw → extracted
   → canonical, truncation). Hashe wylicza wyłącznie builder — publiczna
   ścieżka zapisu nie przyjmuje gotowych hashy od wywołujących.
3. **Deterministyczny weryfikator.** `verify_evidence_excerpt` zatwierdza
   excerpt wyłącznie przeciwko utrwalonemu stanowi retrievalu — przelicza
   długość i hash, nie ufa żadnemu polu deklarowanemu.

Warstwa NIE jest zintegrowana z pipeline'em researchu w tej fali i nie zmienia
semantyki istniejącego `verification_status`.
"""
from __future__ import annotations

import codecs
import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from app.models import EvidenceRetrieval, EvidenceRetrievalStatus
from app.ports.fetch import FetchedDocument

# --- Zamknięte limity fali E1 (stałe pinowane testami; zmiana = nowa decyzja).
MAX_RAW_FETCH_BYTES = 2_000_000
MAX_CANONICAL_CHARS = 100_000
MIN_EXCERPT_CHARS = 10
MAX_EXCERPT_CHARS = 600
# Ucięty dokument mógł stracić koniec zdania — końcówka nie jest cytowalna.
# Ta sama stała jest wkompilowana w trigger SQL migracji 0016 (test pinuje obie).
TRUNCATION_TAIL_GUARD_CHARS = 100

_TEXT_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
_HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})


def sha256_hex(payload: bytes | str) -> str:
    """SHA-256 jako 64 małe znaki hex; tekst zawsze jako UTF-8."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def canonicalize_text(text: str) -> str:
    """Jedyna kanonizacja tekstu cytowalnego — deterministyczna i idempotentna.

    Kroki (dokładnie w tej kolejności):
    1. Unicode NFC,
    2. usunięcie znaków formatujących (kategoria ``Cf`` — ZWSP/BOM/ZWJ itd.),
    3. zamiana każdego znaku kontrolnego (``Cc``, w tym NUL) i każdego białego
       znaku na pojedynczą spację ASCII,
    4. zwinięcie ciągów spacji do jednej + obcięcie brzegów,
    5. końcowe NFC (usunięcie ``Cf`` mogło zetknąć znaki składalne).

    Wynik nie zawiera NUL ani żadnego białego znaku poza pojedynczą spacją —
    dzięki temu ``length()``/``substr()`` SQLite i slicing Pythona adresują
    dokładnie te same code pointy.
    """
    normalized = unicodedata.normalize("NFC", text)
    mapped: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        if category == "Cc" or char.isspace():
            mapped.append(" ")
        else:
            mapped.append(char)
    collapsed = " ".join("".join(mapped).split())
    return unicodedata.normalize("NFC", collapsed)


def _media_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    media = content_type.split(";", 1)[0].strip().lower()
    return media or None


def _charset(content_type: str) -> str:
    for parameter in content_type.split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset":
            candidate = value.strip().strip('"').strip("'")
            if candidate:
                return candidate
    return "utf-8"


def _decode_body(body: bytes, content_type: str) -> str:
    charset = _charset(content_type)
    try:
        codec = codecs.lookup(charset).name
    except LookupError:
        codec = "utf-8"
    return body.decode(codec, errors="replace")


def build_evidence_retrieval(
    document: FetchedDocument,
    *,
    account_id: str,
    now: datetime | None = None,
    max_raw_bytes: int = MAX_RAW_FETCH_BYTES,
    max_canonical_chars: int = MAX_CANONICAL_CHARS,
) -> EvidenceRetrieval:
    """Deterministycznie klasyfikuje jedno pobranie i buduje rekord retrievalu.

    Rekord należy zawsze do jawnie wskazanego konta (``account_id``).
    Łańcuch pochodzenia: surowe bajty (przycięte do ``max_raw_bytes``)
    → dekodowanie wg charsetu → ekstrakcja (HTML) albo passthrough (plain)
    → kanonizacja → przycięcie do ``max_canonical_chars``. Wszystkie hashe
    wylicza wyłącznie ten builder z rzeczywistych danych każdego ogniwa;
    ``raw_sha256`` i ``extracted_sha256`` są metadanymi audytowymi (ich
    źródła nie są utrwalane w bazie), ``canonical_sha256`` jest dodatkowo
    egzekwowany przez trigger SQLite przy zapisie.
    """
    if not account_id or not account_id.strip():
        raise ValueError("Evidence retrieval requires a non-empty account_id.")
    if not document.requested_url.strip() or not document.final_url.strip():
        raise ValueError("FetchedDocument requires non-empty requested/final URL.")
    if max_raw_bytes < 1 or max_canonical_chars < 1:
        raise ValueError("Evidence limits must be positive.")
    created_at = now or datetime.now(timezone.utc)

    body = document.body or b""
    truncated = len(body) > max_raw_bytes
    derivation = body[:max_raw_bytes]

    media = _media_type(document.content_type)
    failure: str | None = None
    if document.error is not None:
        failure = f"TRANSPORT_ERROR:{document.error}"
    elif document.http_status is None:
        failure = "MISSING_HTTP_STATUS"
    elif not 200 <= document.http_status <= 299:
        failure = f"HTTP_STATUS_{document.http_status}"
    elif media is None:
        failure = "MISSING_CONTENT_TYPE"
    elif media not in _TEXT_MEDIA_TYPES:
        failure = f"CONTENT_TYPE_REJECTED:{media}"

    extracted = ""
    canonical = ""
    if failure is None:
        decoded = _decode_body(derivation, document.content_type or "")
        if media in _HTML_MEDIA_TYPES:
            from app.research.html_text import extract_text_from_html

            extracted = extract_text_from_html(decoded)
        else:
            extracted = decoded
        canonical = canonicalize_text(extracted)
        if len(canonical) > max_canonical_chars:
            canonical = canonical[:max_canonical_chars].rstrip()
            truncated = True
        if not canonical:
            failure = "EMPTY_CONTENT"

    if failure is not None:
        return EvidenceRetrieval(
            account_id=account_id,
            requested_url=document.requested_url,
            final_url=document.final_url,
            fetched_at=document.fetched_at,
            status=EvidenceRetrievalStatus.FAILED,
            http_status=document.http_status,
            content_type=document.content_type,
            fetch_error=failure,
            raw_size_bytes=len(derivation),
            raw_sha256=sha256_hex(derivation),
            extracted_chars=0,
            extracted_sha256=sha256_hex(""),
            canonical_text="",
            canonical_chars=0,
            canonical_sha256=sha256_hex(""),
            truncated=False,
            created_at=created_at,
        )

    return EvidenceRetrieval(
        account_id=account_id,
        requested_url=document.requested_url,
        final_url=document.final_url,
        fetched_at=document.fetched_at,
        status=EvidenceRetrievalStatus.OK,
        http_status=document.http_status,
        content_type=document.content_type,
        fetch_error=None,
        raw_size_bytes=len(derivation),
        raw_sha256=sha256_hex(derivation),
        extracted_chars=len(extracted),
        extracted_sha256=sha256_hex(extracted),
        canonical_text=canonical,
        canonical_chars=len(canonical),
        canonical_sha256=sha256_hex(canonical),
        truncated=truncated,
        created_at=created_at,
    )


class EvidenceRejectionReason(str, Enum):
    CLAIM_EMPTY = "CLAIM_EMPTY"
    RETRIEVAL_NOT_FOUND = "RETRIEVAL_NOT_FOUND"
    RETRIEVAL_NOT_OK = "RETRIEVAL_NOT_OK"
    CANONICAL_LENGTH_MISMATCH = "CANONICAL_LENGTH_MISMATCH"
    CANONICAL_HASH_MISMATCH = "CANONICAL_HASH_MISMATCH"
    OFFSETS_INVALID = "OFFSETS_INVALID"
    EXCERPT_LENGTH_OUT_OF_BOUNDS = "EXCERPT_LENGTH_OUT_OF_BOUNDS"
    TRUNCATION_TAIL_GUARD = "TRUNCATION_TAIL_GUARD"
    EXCERPT_TEXT_MISMATCH = "EXCERPT_TEXT_MISMATCH"
    EXCERPT_WHITESPACE_EDGE = "EXCERPT_WHITESPACE_EDGE"
    DUPLICATE_EXCERPT = "DUPLICATE_EXCERPT"


@dataclass(frozen=True)
class EvidenceVerdict:
    approved: bool
    reason: EvidenceRejectionReason | None = None
    detail: str = ""

    @staticmethod
    def ok() -> "EvidenceVerdict":
        return EvidenceVerdict(approved=True)

    @staticmethod
    def rejected(reason: EvidenceRejectionReason, detail: str) -> "EvidenceVerdict":
        return EvidenceVerdict(approved=False, reason=reason, detail=detail)


class EvidenceVerificationError(RuntimeError):
    """Kontrolowana odmowa zapisania excerptu — nic nie zostało utrwalone."""

    def __init__(self, verdict: EvidenceVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"Evidence rejected: {verdict.reason.value if verdict.reason else 'UNKNOWN'}"
            f" ({verdict.detail})"
        )


def verify_evidence_excerpt(
    retrieval: EvidenceRetrieval,
    *,
    claim_text: str,
    excerpt_text: str,
    start_offset: int,
    end_offset: int,
) -> EvidenceVerdict:
    """Deterministyczny weryfikator: excerpt = dokładny fragment kanonu.

    Weryfikator przelicza długość i hash utrwalonego `canonical_text` — nie
    ufa zdeklarowanym polom. Kolejność sprawdzeń jest częścią kontraktu
    (pierwsza złamana reguła wyznacza powód odmowy).
    """
    if not claim_text.strip():
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.CLAIM_EMPTY, "claim text is empty",
        )
    if (
        retrieval.status is not EvidenceRetrievalStatus.OK
        or retrieval.fetch_error is not None
        or retrieval.http_status is None
        or not 200 <= retrieval.http_status <= 299
    ):
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.RETRIEVAL_NOT_OK,
            f"retrieval status={retrieval.status.value}",
        )
    canonical = retrieval.canonical_text
    if retrieval.canonical_chars != len(canonical) or not canonical:
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.CANONICAL_LENGTH_MISMATCH,
            f"declared={retrieval.canonical_chars} actual={len(canonical)}",
        )
    if sha256_hex(canonical) != retrieval.canonical_sha256:
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.CANONICAL_HASH_MISMATCH,
            "stored canonical_sha256 does not match recomputed hash",
        )
    if not (
        isinstance(start_offset, int)
        and isinstance(end_offset, int)
        and not isinstance(start_offset, bool)
        and not isinstance(end_offset, bool)
        and 0 <= start_offset < end_offset <= len(canonical)
    ):
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.OFFSETS_INVALID,
            f"start={start_offset!r} end={end_offset!r} canonical={len(canonical)}",
        )
    span = end_offset - start_offset
    if not MIN_EXCERPT_CHARS <= span <= MAX_EXCERPT_CHARS:
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.EXCERPT_LENGTH_OUT_OF_BOUNDS,
            f"span={span} allowed=[{MIN_EXCERPT_CHARS},{MAX_EXCERPT_CHARS}]",
        )
    if retrieval.truncated and end_offset > len(canonical) - TRUNCATION_TAIL_GUARD_CHARS:
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.TRUNCATION_TAIL_GUARD,
            f"end={end_offset} guard={TRUNCATION_TAIL_GUARD_CHARS}",
        )
    if excerpt_text != canonical[start_offset:end_offset]:
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.EXCERPT_TEXT_MISMATCH,
            "excerpt text is not the exact canonical range",
        )
    if excerpt_text[0] == " " or excerpt_text[-1] == " ":
        return EvidenceVerdict.rejected(
            EvidenceRejectionReason.EXCERPT_WHITESPACE_EDGE,
            "excerpt starts or ends with whitespace",
        )
    return EvidenceVerdict.ok()
