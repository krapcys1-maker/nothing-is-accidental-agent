"""Etap 2 / fala E1: kanonizacja, ekstrakcja, FetchPort, recorder i weryfikator.

Warstwa evidence jest w tej fali izolowana — testy nie dotykają pipeline'u
researchu ani semantyki `verification_status`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import EvidenceRetrievalStatus
from app.ports.fetch import DisabledFetch, FakeFetch, FetchedDocument
from app.research.evidence import (
    EvidenceRejectionReason,
    EvidenceVerificationError,
    MAX_EXCERPT_CHARS,
    MIN_EXCERPT_CHARS,
    TRUNCATION_TAIL_GUARD_CHARS,
    build_evidence_retrieval,
    canonicalize_text,
    sha256_hex,
    verify_evidence_excerpt,
)
from app.research.html_text import extract_text_from_html

FETCHED_AT = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)

HTML_BODY = (
    b"<html><head><title>Widoczny tytul</title>"
    b"<script>var hidden = 'nigdy';</script>"
    b"<style>body { color: red; }</style></head>"
    b"<body><p>Pierwszy   akapit &amp; encja.</p>"
    b"<p>Drugi akapit z <b>pogrubieniem</b> w srodku.</p>"
    b"<noscript>ukryte</noscript><template>ukryte</template></body></html>"
)


def _document(
    *,
    url: str = "https://example.org/article",
    http_status: int | None = 200,
    content_type: str | None = "text/html; charset=utf-8",
    body: bytes = HTML_BODY,
    error: str | None = None,
) -> FetchedDocument:
    return FetchedDocument(
        requested_url=url, final_url=url, fetched_at=FETCHED_AT,
        http_status=http_status, content_type=content_type, body=body, error=error,
    )


# --- Dokładnie jedna kanonizacja tekstu ---

def test_canonicalize_collapses_every_whitespace_kind_to_single_spaces():
    raw = "  Alpha\t beta\r\nga mma delta \n\n epsilon  "
    assert canonicalize_text(raw) == "Alpha beta ga mma delta epsilon"


def test_canonicalize_applies_nfc_composition():
    decomposed = 'cafe' + chr(0x0301)  # e + combining acute
    composed = 'caf' + chr(0x00E9)     # precomposed single code point
    assert canonicalize_text(decomposed) == composed
    assert len(canonicalize_text(decomposed)) == 4


def test_canonicalize_removes_format_characters_and_controls():
    raw = ('A' + chr(0x200B) + 'B' + chr(0xFEFF)
           + 'C' + chr(0) + 'D' + chr(7) + 'E')
    # Cf (ZWSP/BOM) znika bez sladu; Cc (NUL/BEL) staje sie spacja.
    assert canonicalize_text(raw) == 'ABC D E'

def test_canonicalize_is_idempotent_and_deterministic():
    raw = '  Ala  ma ' + chr(9) + ' kota' + chr(0x200B) + ' i psa' + chr(13) + chr(10)
    once = canonicalize_text(raw)
    assert once == 'Ala ma kota i psa'
    assert canonicalize_text(once) == once
    assert canonicalize_text(raw) == once

def test_canonicalize_empty_and_whitespace_only_yield_empty():
    assert canonicalize_text("") == ""
    assert canonicalize_text(" \t\r\n ") == ""


def test_sha256_hex_treats_text_as_utf8():
    assert sha256_hex("zażółć") == sha256_hex(
        "zażółć".encode("utf-8")
    )
    assert len(sha256_hex("")) == 64


# --- Deterministyczna ekstrakcja HTML -> tekst ---

def test_extraction_drops_script_style_noscript_template_content():
    text = extract_text_from_html(HTML_BODY.decode("utf-8"))
    for hidden in ("hidden", "nigdy", "color: red", "ukryte"):
        assert hidden not in text
    assert "Widoczny tytul" in text
    assert "Pierwszy   akapit & encja." in text


def test_extraction_separates_blocks_but_not_inline_elements():
    text = extract_text_from_html("<p>jeden</p><p>dwa</p><span>trzy</span>")
    assert "jeden" in text and "dwa" in text
    assert "jedendwa" not in text
    inline = extract_text_from_html("po<b>gru</b>bienie")
    assert "pogrubienie" in inline


def test_extraction_decodes_entities_and_survives_malformed_html():
    assert "A & B" in extract_text_from_html("A &amp; B")
    # Niedomkniete tagi i smieci nie moga podniesc wyjatku.
    messy = "<div><p>tekst <b>bez konca <script>x=1;"
    assert "tekst bez konca" in extract_text_from_html(messy).replace("\n", " ")


def test_extraction_is_deterministic():
    html = HTML_BODY.decode("utf-8")
    assert extract_text_from_html(html) == extract_text_from_html(html)


# --- FetchPort: fake i disabled ---

def test_fake_fetch_returns_registered_document_and_records_calls():
    doc = _document()
    fake = FakeFetch({doc.requested_url: doc})
    assert fake.fetch(doc.requested_url) is doc
    assert fake.calls == [doc.requested_url]


def test_fake_fetch_refuses_unregistered_url():
    with pytest.raises(KeyError, match="no registered document"):
        FakeFetch().fetch("https://example.org/missing")


def test_disabled_fetch_fails_closed():
    with pytest.raises(NotImplementedError, match="wyłączona"):
        DisabledFetch().fetch("https://example.org/anything")


# --- Recorder: build_evidence_retrieval ---

def test_build_retrieval_ok_persists_full_derivation_chain():
    retrieval = build_evidence_retrieval(_document())
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert retrieval.fetch_error is None
    assert retrieval.http_status == 200
    assert retrieval.raw_size_bytes == len(HTML_BODY)
    assert retrieval.raw_sha256 == sha256_hex(HTML_BODY)
    extracted = extract_text_from_html(HTML_BODY.decode("utf-8"))
    assert retrieval.extracted_chars == len(extracted)
    assert retrieval.extracted_sha256 == sha256_hex(extracted)
    assert retrieval.canonical_text == canonicalize_text(extracted)
    assert retrieval.canonical_chars == len(retrieval.canonical_text)
    assert retrieval.canonical_sha256 == sha256_hex(retrieval.canonical_text)
    assert retrieval.truncated is False
    assert "Pierwszy akapit & encja." in retrieval.canonical_text


def test_build_retrieval_is_deterministic():
    first = build_evidence_retrieval(_document(), now=FETCHED_AT)
    second = build_evidence_retrieval(_document(), now=FETCHED_AT)
    assert first == second


def test_build_retrieval_decodes_declared_charset():
    body = "Zażółć gęślą".encode("iso-8859-2")
    doc = _document(content_type="text/plain; charset=iso-8859-2", body=body)
    retrieval = build_evidence_retrieval(doc)
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert "Zażółć" in retrieval.canonical_text


def test_build_retrieval_unknown_charset_falls_back_to_utf8_replace():
    doc = _document(content_type="text/plain; charset=no-such-charset",
                    body=b"plain ascii content here")
    retrieval = build_evidence_retrieval(doc)
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert retrieval.canonical_text == "plain ascii content here"


@pytest.mark.parametrize("kwargs, expected_error", [
    ({"error": "connection reset"}, "TRANSPORT_ERROR:connection reset"),
    ({"http_status": None}, "MISSING_HTTP_STATUS"),
    ({"http_status": 404}, "HTTP_STATUS_404"),
    ({"http_status": 301}, "HTTP_STATUS_301"),
    ({"content_type": None}, "MISSING_CONTENT_TYPE"),
    ({"content_type": "application/pdf"}, "CONTENT_TYPE_REJECTED:application/pdf"),
    ({"content_type": "image/png; charset=utf-8"}, "CONTENT_TYPE_REJECTED:image/png"),
])
def test_build_retrieval_classifies_failures_deterministically(kwargs, expected_error):
    retrieval = build_evidence_retrieval(_document(**kwargs))
    assert retrieval.status is EvidenceRetrievalStatus.FAILED
    assert retrieval.fetch_error == expected_error
    assert retrieval.canonical_text == ""
    assert retrieval.canonical_chars == 0
    assert retrieval.truncated is False


def test_build_retrieval_empty_content_fails_closed():
    doc = _document(content_type="text/plain", body=b"  \t\r\n  ")
    retrieval = build_evidence_retrieval(doc)
    assert retrieval.status is EvidenceRetrievalStatus.FAILED
    assert retrieval.fetch_error == "EMPTY_CONTENT"


def test_build_retrieval_caps_raw_bytes_and_flags_truncation():
    body = b"slowo " * 100
    retrieval = build_evidence_retrieval(
        _document(content_type="text/plain", body=body), max_raw_bytes=60,
    )
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert retrieval.truncated is True
    assert retrieval.raw_size_bytes == 60
    assert retrieval.raw_sha256 == sha256_hex(body[:60])


def test_build_retrieval_caps_canonical_chars_and_flags_truncation():
    body = ("slowo " * 100).encode("utf-8")
    retrieval = build_evidence_retrieval(
        _document(content_type="text/plain", body=body), max_canonical_chars=50,
    )
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert retrieval.truncated is True
    assert retrieval.canonical_chars <= 50
    assert not retrieval.canonical_text.endswith(" ")


def test_build_retrieval_rejects_blank_urls_and_bad_limits():
    with pytest.raises(ValueError, match="non-empty"):
        build_evidence_retrieval(FetchedDocument(
            requested_url=" ", final_url="https://x", fetched_at=FETCHED_AT,
            http_status=200, content_type="text/plain", body=b"x",
        ))
    with pytest.raises(ValueError, match="positive"):
        build_evidence_retrieval(_document(), max_raw_bytes=0)


# --- Deterministyczny weryfikator ---

def _ok_retrieval(**kwargs):
    text = ("Sto lat temu nikt nie przypuszczal, ze przypadek stanie sie "
            "najlepiej udokumentowanym mechanizmem wspolczesnej ekonomii uwagi. " * 3)
    return build_evidence_retrieval(
        _document(content_type="text/plain", body=text.encode("utf-8")), **kwargs,
    )


def _aligned_span(text: str, length: int, *, start: int = 0) -> tuple[int, int]:
    while text[start] == " ":
        start += 1
    end = start + length
    while text[end - 1] == " ":
        end -= 1
    return start, end


def test_verifier_approves_exact_canonical_range():
    retrieval = _ok_retrieval()
    start, end = _aligned_span(retrieval.canonical_text, 80)
    verdict = verify_evidence_excerpt(
        retrieval, claim_text="claim", start_offset=start, end_offset=end,
        excerpt_text=retrieval.canonical_text[start:end],
    )
    assert verdict.approved and verdict.reason is None


def test_verifier_rejects_empty_claim():
    retrieval = _ok_retrieval()
    verdict = verify_evidence_excerpt(
        retrieval, claim_text="  ", excerpt_text=retrieval.canonical_text[:20],
        start_offset=0, end_offset=20,
    )
    assert verdict.reason is EvidenceRejectionReason.CLAIM_EMPTY


def test_verifier_rejects_failed_retrieval():
    failed = build_evidence_retrieval(_document(http_status=500))
    verdict = verify_evidence_excerpt(
        failed, claim_text="claim", excerpt_text="cokolwiek dluzszego niz limit",
        start_offset=0, end_offset=29,
    )
    assert verdict.reason is EvidenceRejectionReason.RETRIEVAL_NOT_OK


def test_verifier_recomputes_canonical_length():
    tampered = _ok_retrieval().model_copy(update={"canonical_chars": 7})
    verdict = verify_evidence_excerpt(
        tampered, claim_text="claim", excerpt_text=tampered.canonical_text[:20],
        start_offset=0, end_offset=20,
    )
    assert verdict.reason is EvidenceRejectionReason.CANONICAL_LENGTH_MISMATCH


def test_verifier_recomputes_canonical_hash():
    tampered = _ok_retrieval().model_copy(update={"canonical_sha256": "0" * 64})
    verdict = verify_evidence_excerpt(
        tampered, claim_text="claim", excerpt_text=tampered.canonical_text[:20],
        start_offset=0, end_offset=20,
    )
    assert verdict.reason is EvidenceRejectionReason.CANONICAL_HASH_MISMATCH


@pytest.mark.parametrize("start,end", [
    (-1, 20), (5, 5), (30, 20), (0, 10**9), (True, 40),
])
def test_verifier_rejects_invalid_offsets(start, end):
    retrieval = _ok_retrieval()
    verdict = verify_evidence_excerpt(
        retrieval, claim_text="claim",
        excerpt_text=retrieval.canonical_text[:20], start_offset=start, end_offset=end,
    )
    assert verdict.reason is EvidenceRejectionReason.OFFSETS_INVALID


def test_verifier_enforces_span_bounds():
    retrieval = _ok_retrieval()
    text = retrieval.canonical_text
    short = verify_evidence_excerpt(
        retrieval, claim_text="claim",
        excerpt_text=text[:MIN_EXCERPT_CHARS - 1],
        start_offset=0, end_offset=MIN_EXCERPT_CHARS - 1,
    )
    assert short.reason is EvidenceRejectionReason.EXCERPT_LENGTH_OUT_OF_BOUNDS
    if len(text) > MAX_EXCERPT_CHARS + 1:
        long = verify_evidence_excerpt(
            retrieval, claim_text="claim",
            excerpt_text=text[:MAX_EXCERPT_CHARS + 1],
            start_offset=0, end_offset=MAX_EXCERPT_CHARS + 1,
        )
        assert long.reason is EvidenceRejectionReason.EXCERPT_LENGTH_OUT_OF_BOUNDS


def test_verifier_enforces_truncation_tail_guard():
    truncated = _ok_retrieval(max_canonical_chars=200)
    assert truncated.truncated is True
    text = truncated.canonical_text
    end = len(text)
    start = end - 40
    verdict = verify_evidence_excerpt(
        truncated, claim_text="claim", excerpt_text=text[start:end],
        start_offset=start, end_offset=end,
    )
    assert verdict.reason is EvidenceRejectionReason.TRUNCATION_TAIL_GUARD
    safe_end = len(text) - TRUNCATION_TAIL_GUARD_CHARS
    s2, e2 = _aligned_span(text, 40, start=safe_end - 60)
    assert e2 <= safe_end
    ok = verify_evidence_excerpt(
        truncated, claim_text="claim", excerpt_text=text[s2:e2],
        start_offset=s2, end_offset=e2,
    )
    assert ok.approved


def test_verifier_rejects_text_mismatch_and_whitespace_edges():
    retrieval = _ok_retrieval()
    text = retrieval.canonical_text
    start, end = _aligned_span(text, 60)
    forged = verify_evidence_excerpt(
        retrieval, claim_text="claim",
        excerpt_text="x" * (end - start), start_offset=start, end_offset=end,
    )
    assert forged.reason is EvidenceRejectionReason.EXCERPT_TEXT_MISMATCH
    space_at = text.index(" ")
    edged = verify_evidence_excerpt(
        retrieval, claim_text="claim",
        excerpt_text=text[space_at:space_at + 40],
        start_offset=space_at, end_offset=space_at + 40,
    )
    assert edged.reason is EvidenceRejectionReason.EXCERPT_WHITESPACE_EDGE


# --- Repozytorium: trwaly zapis przez weryfikator ---

def test_repository_round_trips_retrieval_exactly(storage):
    retrieval = build_evidence_retrieval(_document())
    stored = storage.add_evidence_retrieval(retrieval)
    assert stored.id is not None
    read = storage.get_evidence_retrieval(stored.id)
    assert read is not None
    for field in (
        "requested_url", "final_url", "status", "http_status", "content_type",
        "fetch_error", "raw_size_bytes", "raw_sha256", "extracted_chars",
        "extracted_sha256", "canonical_text", "canonical_chars",
        "canonical_sha256", "truncated",
    ):
        assert getattr(read, field) == getattr(retrieval, field), field
    assert storage.list_evidence_retrievals(final_url=retrieval.final_url)[0].id == stored.id


def test_repository_records_verified_excerpt_with_claim_hash(storage):
    stored = storage.add_evidence_retrieval(_ok_retrieval())
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    excerpt = storage.record_verified_evidence_excerpt(
        stored.id, claim_text="Przypadek jest udokumentowany",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    assert excerpt.id is not None
    assert excerpt.claim_sha256 == sha256_hex("Przypadek jest udokumentowany")
    listed = storage.list_evidence_excerpts(stored.id)
    assert [item.id for item in listed] == [excerpt.id]
    assert listed[0].excerpt_text == text[start:end]


def test_repository_rejects_unverified_excerpt_without_persisting(storage):
    stored = storage.add_evidence_retrieval(_ok_retrieval())
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            stored.id, claim_text="claim",
            excerpt_text="sfabrykowany cytat, ktorego nie ma w kanonie",
            start_offset=0, end_offset=44,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.EXCERPT_TEXT_MISMATCH
    assert storage.list_evidence_excerpts(stored.id) == []


def test_repository_rejects_missing_retrieval(storage):
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            424242, claim_text="claim", excerpt_text="dowolny tekst dowodowy",
            start_offset=0, end_offset=22,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.RETRIEVAL_NOT_FOUND


def test_repository_rejects_duplicate_excerpt_range(storage):
    stored = storage.add_evidence_retrieval(_ok_retrieval())
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    storage.record_verified_evidence_excerpt(
        stored.id, claim_text="claim", excerpt_text=text[start:end],
        start_offset=start, end_offset=end,
    )
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            stored.id, claim_text="claim", excerpt_text=text[start:end],
            start_offset=start, end_offset=end,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.DUPLICATE_EXCERPT
    assert len(storage.list_evidence_excerpts(stored.id)) == 1


def test_repository_verifies_against_persisted_state_not_caller_object(storage):
    """Zapis excerptu weryfikuje stan z bazy — obiekt wywolujacego jest bez znaczenia."""
    stored = storage.add_evidence_retrieval(_ok_retrieval())
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    # Wywolujacy moze twierdzic cokolwiek — liczy sie utrwalony kanon.
    excerpt = storage.record_verified_evidence_excerpt(
        stored.id, claim_text="claim", excerpt_text=text[start:end],
        start_offset=start, end_offset=end,
    )
    assert excerpt.excerpt_text == text[start:end]
