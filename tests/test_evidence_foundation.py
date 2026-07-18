"""Etap 2 / fala E1: kanonizacja, ekstrakcja, FetchPort, recorder i weryfikator.

Warstwa evidence jest w tej fali izolowana — testy nie dotykają pipeline'u
researchu ani semantyki `verification_status`. Po naprawie fali E1 (ADR-100)
wszystkie operacje repozytorium działają w jawnym zakresie konta, publiczna
ścieżka zapisu nie przyjmuje gotowych hashy, a statycznie ukryty HTML nie jest
treścią cytowalną.
"""
from __future__ import annotations

import dataclasses
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
# To samo ID co conftest.make_account — testy budowy rekordów nie dotykają DB.
ACCOUNT_ID = "nothing_is_accidental"

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
    raw = "  Alpha\t beta\r\nga mma delta \n\n epsilon  "
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
    assert canonicalize_text(" \t\r\n ") == ""


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


# --- Statycznie ukryty HTML nie jest treścią cytowalną (E1-B04) ---

def test_extraction_skips_exact_review_hidden_example():
    html = (
        '<p>Visible before</p>'
        '<div hidden aria-hidden="true" style="display:none">HIDDEN EVIDENCE</div>'
        '<p>Visible after</p>'
    )
    text = extract_text_from_html(html)
    assert "HIDDEN EVIDENCE" not in text
    assert "Visible before" in text
    assert "Visible after" in text


@pytest.mark.parametrize("marker", [
    'hidden',
    'hidden=""',
    "hidden='hidden'",
    'HIDDEN',
    'aria-hidden="true"',
    "aria-hidden='TRUE'",
    'aria-hidden=" true "',
    'style="display:none"',
    'style="display: none"',
    'style="DISPLAY : NONE"',
    'style="color:red; display:none; margin:0"',
    'style="display:none !important"',
    'style="visibility:hidden"',
    'style=" Visibility : HIDDEN "',
    'style="content-visibility:hidden"',
])
def test_extraction_skips_each_static_hiding_marker_separately(marker):
    html = f'<p>przed</p><div {marker}>SEKRET</div><p>po</p>'
    text = extract_text_from_html(html)
    assert "SEKRET" not in text
    assert "przed" in text and "po" in text


def test_extraction_hidden_parent_skips_whole_nested_subtree():
    html = (
        '<p>widoczny wstep</p>'
        '<div hidden><p>SEKRET1</p><span>SEKRET2 <b>SEKRET3</b></span>'
        '<div><ul><li>SEKRET4</li></ul></div></div>'
        '<p>widoczne zakonczenie</p>'
    )
    text = extract_text_from_html(html)
    for secret in ("SEKRET1", "SEKRET2", "SEKRET3", "SEKRET4"):
        assert secret not in text
    assert "widoczny wstep" in text and "widoczne zakonczenie" in text


def test_extraction_keeps_visible_elements_without_hiding_markers():
    html = (
        '<div aria-hidden="false" style="display:block; color:red" '
        'data-hidden="true" class="hidden">tekst pozostaje widoczny</div>'
    )
    # Klasa CSS ".hidden" i data-atrybuty NIE są markerami statycznego ukrycia
    # (brak silnika CSS); aria-hidden="false" i display:block też nie ukrywają.
    assert "tekst pozostaje widoczny" in extract_text_from_html(html)


def test_extraction_hidden_element_between_texts_keeps_word_separation():
    text = extract_text_from_html('slowo-a<div hidden>SEKRET</div>slowo-b')
    assert "SEKRET" not in text
    assert "slowo-a" in text and "slowo-b" in text
    assert "slowo-aslowo-b" not in text


def test_extraction_skipped_elements_and_hidden_subtrees_compose():
    html = (
        '<div hidden><script>var a=1;</script><p>SEKRET</p></div>'
        '<noscript>ukryte-noscript</noscript>'
        '<template><div hidden>ukryte-template</div></template>'
        '<p>jawna tresc</p>'
    )
    text = extract_text_from_html(html)
    for gone in ("var a=1", "SEKRET", "ukryte-noscript", "ukryte-template"):
        assert gone not in text
    assert "jawna tresc" in text


def test_extraction_unclosed_hidden_element_stays_fail_closed():
    # Zniekształcony HTML z niedomkniętym ukrytym elementem: ekstraktor woli
    # pominąć za dużo, niż wypuścić jawnie ukrytą treść jako cytowalną.
    text = extract_text_from_html('<div><p hidden>SEKRET</div><p>reszta</p>')
    assert "SEKRET" not in text


def test_recorder_keeps_statically_hidden_html_out_of_canonical_text():
    body = (
        '<html><body><p>Fakt widoczny w artykule.</p>'
        '<div hidden aria-hidden="true" style="display:none">HIDDEN EVIDENCE</div>'
        '</body></html>'
    ).encode("utf-8")
    retrieval = build_evidence_retrieval(_document(body=body), account_id=ACCOUNT_ID)
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert "HIDDEN EVIDENCE" not in retrieval.canonical_text
    assert "Fakt widoczny w artykule." in retrieval.canonical_text


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


def test_fetched_document_carries_no_hash_or_derived_fields():
    """Publiczna ścieżka zapisu przyjmuje tylko surowy dokument — nie istnieje
    pole, którym wywołujący mógłby przekazać gotowy hash jako dowód."""
    names = {field.name for field in dataclasses.fields(FetchedDocument)}
    assert names == {
        "requested_url", "final_url", "fetched_at", "http_status",
        "content_type", "body", "error",
    }


# --- Recorder: build_evidence_retrieval ---

def test_build_retrieval_ok_persists_full_derivation_chain():
    retrieval = build_evidence_retrieval(_document(), account_id=ACCOUNT_ID)
    assert retrieval.account_id == ACCOUNT_ID
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
    first = build_evidence_retrieval(_document(), account_id=ACCOUNT_ID, now=FETCHED_AT)
    second = build_evidence_retrieval(_document(), account_id=ACCOUNT_ID, now=FETCHED_AT)
    assert first == second


def test_build_retrieval_decodes_declared_charset():
    body = "Zażółć gęślą".encode("iso-8859-2")
    doc = _document(content_type="text/plain; charset=iso-8859-2", body=body)
    retrieval = build_evidence_retrieval(doc, account_id=ACCOUNT_ID)
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert "Zażółć" in retrieval.canonical_text


def test_build_retrieval_unknown_charset_falls_back_to_utf8_replace():
    doc = _document(content_type="text/plain; charset=no-such-charset",
                    body=b"plain ascii content here")
    retrieval = build_evidence_retrieval(doc, account_id=ACCOUNT_ID)
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
    retrieval = build_evidence_retrieval(_document(**kwargs), account_id=ACCOUNT_ID)
    assert retrieval.status is EvidenceRetrievalStatus.FAILED
    assert retrieval.fetch_error == expected_error
    assert retrieval.canonical_text == ""
    assert retrieval.canonical_chars == 0
    assert retrieval.truncated is False


def test_build_retrieval_empty_content_fails_closed():
    doc = _document(content_type="text/plain", body=b"  \t\r\n  ")
    retrieval = build_evidence_retrieval(doc, account_id=ACCOUNT_ID)
    assert retrieval.status is EvidenceRetrievalStatus.FAILED
    assert retrieval.fetch_error == "EMPTY_CONTENT"


def test_build_retrieval_caps_raw_bytes_and_flags_truncation():
    body = b"slowo " * 100
    retrieval = build_evidence_retrieval(
        _document(content_type="text/plain", body=body),
        account_id=ACCOUNT_ID, max_raw_bytes=60,
    )
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert retrieval.truncated is True
    assert retrieval.raw_size_bytes == 60
    assert retrieval.raw_sha256 == sha256_hex(body[:60])


def test_build_retrieval_caps_canonical_chars_and_flags_truncation():
    body = ("slowo " * 100).encode("utf-8")
    retrieval = build_evidence_retrieval(
        _document(content_type="text/plain", body=body),
        account_id=ACCOUNT_ID, max_canonical_chars=50,
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
        ), account_id=ACCOUNT_ID)
    with pytest.raises(ValueError, match="positive"):
        build_evidence_retrieval(_document(), account_id=ACCOUNT_ID, max_raw_bytes=0)


def test_build_retrieval_requires_explicit_non_blank_account():
    with pytest.raises(ValueError, match="account_id"):
        build_evidence_retrieval(_document(), account_id="  ")
    with pytest.raises(TypeError):
        build_evidence_retrieval(_document())


# --- Deterministyczny weryfikator ---

def _ok_document(**kwargs) -> FetchedDocument:
    text = ("Sto lat temu nikt nie przypuszczal, ze przypadek stanie sie "
            "najlepiej udokumentowanym mechanizmem wspolczesnej ekonomii uwagi. " * 3)
    return _document(content_type="text/plain", body=text.encode("utf-8"), **kwargs)


def _ok_retrieval(**kwargs):
    return build_evidence_retrieval(_ok_document(), account_id=ACCOUNT_ID, **kwargs)


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
    failed = build_evidence_retrieval(_document(http_status=500), account_id=ACCOUNT_ID)
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


# --- Repozytorium: trwaly zapis w zakresie konta, przez weryfikator ---

@pytest.fixture
def evidence_account(storage, account):
    storage.ensure_account(account)
    return account


@pytest.fixture
def other_account(storage, account):
    other = account.model_copy(update={"id": "other-evidence-account"})
    storage.ensure_account(other)
    return other


def test_repository_round_trips_retrieval_exactly(storage, evidence_account):
    stored = storage.record_evidence_retrieval(
        _document(), account_id=evidence_account.id,
    )
    assert stored.id is not None
    expected = build_evidence_retrieval(_document(), account_id=evidence_account.id)
    read = storage.get_evidence_retrieval(stored.id, account_id=evidence_account.id)
    assert read is not None
    for field in (
        "account_id", "requested_url", "final_url", "status", "http_status",
        "content_type", "fetch_error", "raw_size_bytes", "raw_sha256",
        "extracted_chars", "extracted_sha256", "canonical_text",
        "canonical_chars", "canonical_sha256", "truncated",
    ):
        assert getattr(read, field) == getattr(expected, field), field
    listed = storage.list_evidence_retrievals(
        account_id=evidence_account.id, final_url=expected.final_url,
    )
    assert [item.id for item in listed] == [stored.id]


def test_repository_public_write_path_takes_document_not_declared_hashes(
    storage, evidence_account,
):
    """Wspierana ścieżka aplikacyjna nie przyjmuje żadnego gotowego hasha:
    jedynym wejściem jest surowy FetchedDocument, a hashe wychodzą z recordera."""
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    assert stored.raw_sha256 == sha256_hex(_ok_document().body)
    assert stored.canonical_sha256 == sha256_hex(stored.canonical_text)
    with pytest.raises(TypeError):
        storage.record_evidence_retrieval(
            _ok_document(), account_id=evidence_account.id,
            canonical_sha256="0" * 64,
        )


@pytest.mark.parametrize("field, value, match", [
    ("canonical_sha256", "0" * 64, "not accepted as proof"),
    ("canonical_chars", 7, "canonical_chars"),
])
def test_repository_internal_insert_recomputes_canon_and_refuses_lies(
    storage, evidence_account, field, value, match,
):
    forged = build_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    ).model_copy(update={field: value})
    with pytest.raises(ValueError, match=match):
        storage._insert_evidence_retrieval(forged)
    assert storage.list_evidence_retrievals(account_id=evidence_account.id) == []


def test_repository_internal_insert_refuses_nul_canonical_text(
    storage, evidence_account,
):
    base = build_evidence_retrieval(_ok_document(), account_id=evidence_account.id)
    nul_text = base.canonical_text[:20] + "\x00" + base.canonical_text[21:]
    forged = base.model_copy(update={
        "canonical_text": nul_text,
        "canonical_chars": len(nul_text),
        "canonical_sha256": sha256_hex(nul_text),
    })
    with pytest.raises(ValueError, match="NUL"):
        storage._insert_evidence_retrieval(forged)
    assert storage.list_evidence_retrievals(account_id=evidence_account.id) == []


def test_repository_records_verified_excerpt_with_claim_hash(storage, evidence_account):
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    excerpt = storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id,
        claim_text="Przypadek jest udokumentowany",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    assert excerpt.id is not None
    assert excerpt.account_id == evidence_account.id
    assert excerpt.claim_sha256 == sha256_hex("Przypadek jest udokumentowany")
    listed = storage.list_evidence_excerpts(stored.id, account_id=evidence_account.id)
    assert [item.id for item in listed] == [excerpt.id]
    assert listed[0].excerpt_text == text[start:end]


def test_repository_rejects_unverified_excerpt_without_persisting(storage, evidence_account):
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            stored.id, account_id=evidence_account.id, claim_text="claim",
            excerpt_text="sfabrykowany cytat, ktorego nie ma w kanonie",
            start_offset=0, end_offset=44,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.EXCERPT_TEXT_MISMATCH
    assert storage.list_evidence_excerpts(stored.id, account_id=evidence_account.id) == []


def test_repository_rejects_missing_retrieval(storage, evidence_account):
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            424242, account_id=evidence_account.id, claim_text="claim",
            excerpt_text="dowolny tekst dowodowy",
            start_offset=0, end_offset=22,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.RETRIEVAL_NOT_FOUND


def test_repository_rejects_duplicate_excerpt_range(storage, evidence_account):
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id, claim_text="claim",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            stored.id, account_id=evidence_account.id, claim_text="claim",
            excerpt_text=text[start:end], start_offset=start, end_offset=end,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.DUPLICATE_EXCERPT
    assert len(storage.list_evidence_excerpts(stored.id, account_id=evidence_account.id)) == 1


def test_repository_allows_distinct_claims_and_ranges(storage, evidence_account):
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    first = storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id, claim_text="claim A",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    # Inny claim dla tego samego zakresu — legalny.
    second = storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id, claim_text="claim B",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    # Ten sam claim dla innego legalnego zakresu — legalny.
    s2, e2 = _aligned_span(text, 60, start=end + 1)
    third = storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id, claim_text="claim A",
        excerpt_text=text[s2:e2], start_offset=s2, end_offset=e2,
    )
    ids = [item.id for item in storage.list_evidence_excerpts(
        stored.id, account_id=evidence_account.id,
    )]
    assert ids == [first.id, second.id, third.id]


def test_repository_verifies_against_persisted_state_not_caller_object(storage, evidence_account):
    """Zapis excerptu weryfikuje stan z bazy — obiekt wywolujacego jest bez znaczenia."""
    stored = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    text = stored.canonical_text
    start, end = _aligned_span(text, 60)
    # Wywolujacy moze twierdzic cokolwiek — liczy sie utrwalony kanon.
    excerpt = storage.record_verified_evidence_excerpt(
        stored.id, account_id=evidence_account.id, claim_text="claim",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    assert excerpt.excerpt_text == text[start:end]


# --- Account scope repozytorium (E1-B03) ---

def test_repository_reads_require_explicit_account_scope(storage):
    """Globalny odczyt bez zakresu konta nie istnieje w publicznym API."""
    with pytest.raises(TypeError):
        storage.list_evidence_retrievals()
    with pytest.raises(TypeError):
        storage.get_evidence_retrieval(1)
    with pytest.raises(TypeError):
        storage.list_evidence_excerpts(1)
    with pytest.raises(TypeError):
        storage.record_evidence_retrieval(_ok_document())


def test_repository_scopes_retrievals_to_their_account(
    storage, evidence_account, other_account,
):
    mine = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    assert storage.get_evidence_retrieval(mine.id, account_id=other_account.id) is None
    assert storage.list_evidence_retrievals(account_id=other_account.id) == []
    assert storage.get_evidence_retrieval(
        mine.id, account_id=evidence_account.id,
    ).id == mine.id


def test_repository_refuses_cross_account_excerpt_write_and_read(
    storage, evidence_account, other_account,
):
    mine = storage.record_evidence_retrieval(
        _ok_document(), account_id=evidence_account.id,
    )
    text = mine.canonical_text
    start, end = _aligned_span(text, 60)
    with pytest.raises(EvidenceVerificationError) as excinfo:
        storage.record_verified_evidence_excerpt(
            mine.id, account_id=other_account.id, claim_text="cudzy claim",
            excerpt_text=text[start:end], start_offset=start, end_offset=end,
        )
    assert excinfo.value.verdict.reason is EvidenceRejectionReason.RETRIEVAL_NOT_FOUND
    excerpt = storage.record_verified_evidence_excerpt(
        mine.id, account_id=evidence_account.id, claim_text="wlasny claim",
        excerpt_text=text[start:end], start_offset=start, end_offset=end,
    )
    assert storage.list_evidence_excerpts(mine.id, account_id=other_account.id) == []
    assert [item.id for item in storage.list_evidence_excerpts(
        mine.id, account_id=evidence_account.id,
    )] == [excerpt.id]
