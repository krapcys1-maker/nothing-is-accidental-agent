"""E3: liczba źródeł evidence research = odrębne ZATWIERDZONE retrievale.

Regresja dokładnie do rozbieżności ujawnionej w pierwszym realnym live evidence
research (job real-research-82e36c4b…, karta id=4): jeden retrieval zacytowany
trzykrotnie dał 3 rekordy `sources` VERIFIED, a stara bramka liczyła rekordy, nie
odrębne retrievale — przez co `TOO_FEW_SOURCES` nie zadziałało. Testy tu są
czysto jednostkowe (bez sieci, bez API, bez bazy): sprawdzają helper liczenia i
próg `validate_draft`.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models import SourceType, SourceVerification
from app.research.base import ResearchDraft, SourceDraft
from app.research.validation import (
    TOO_FEW_SOURCES,
    count_distinct_verified_evidence_sources,
    validate_draft,
)

_THRESHOLDS = dict(min_sources=3, min_confidence=0.60, min_source_quality=0.50)


def _src(url, verification=SourceVerification.VERIFIED, claim="c"):
    return SourceDraft(
        url=url, title="t", source_type=SourceType.SECONDARY,
        supports_claim=claim, verification=verification,
    )


def _ret(retrieval_id, requested_url, final_url=None):
    return SimpleNamespace(
        id=retrieval_id, requested_url=requested_url,
        final_url=final_url if final_url is not None else requested_url,
    )


# --- helper: count_distinct_verified_evidence_sources -----------------------

def test_three_verified_rows_one_retrieval_count_one():
    # Dokładny kształt live: 3 źródła VERIFIED, ten sam URL jednego retrievalu.
    corpus = [_ret(1, "https://e.example/doc")]
    sources = [_src("https://e.example/doc") for _ in range(3)]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 1


def test_three_distinct_retrievals_count_three():
    corpus = [
        _ret(1, "https://e.example/a"),
        _ret(2, "https://e.example/b"),
        _ret(3, "https://e.example/c"),
    ]
    sources = [
        _src("https://e.example/a"),
        _src("https://e.example/b"),
        _src("https://e.example/c"),
    ]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 3


def test_two_records_same_retrieval_id_do_not_increase_count():
    corpus = [_ret(7, "https://e.example/doc")]
    sources = [_src("https://e.example/doc"), _src("https://e.example/doc")]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 1


def test_different_urls_same_retrieval_do_not_increase_count():
    # requested_url != final_url tego samego retrievalu — oba mapują na id=1.
    corpus = [_ret(1, "https://e.example/requested", "https://e.example/final")]
    sources = [
        _src("https://e.example/requested"),
        _src("https://e.example/final"),
    ]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 1


def test_url_outside_approved_corpus_not_counted():
    # Źródło spoza zatwierdzonego korpusu (np. URL z innym, niezatwierdzonym
    # materiałem) NIE tworzy nowego źródła — liczy się tylko zatwierdzony korpus.
    corpus = [_ret(1, "https://e.example/approved")]
    sources = [
        _src("https://e.example/approved"),
        _src("https://e.example/unapproved-other"),
    ]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 1


def test_unverified_source_not_counted():
    corpus = [_ret(1, "https://e.example/doc")]
    sources = [
        _src("https://e.example/doc", SourceVerification.UNVERIFIED),
        _src("https://e.example/doc", SourceVerification.FAILED),
    ]
    assert count_distinct_verified_evidence_sources(sources, corpus) == 0


# --- validate_draft: evidence_source_count steruje TOO_FEW_SOURCES ----------

def _draft(*, sources, confirmed_claims):
    return ResearchDraft(
        question="Why?", working_thesis="w", main_mechanism="m",
        confirmed_claims=list(confirmed_claims), confidence_score=0.9,
        source_quality_score=0.9, sources=list(sources),
    )


def test_evidence_source_count_one_forces_too_few_sources():
    # Trzy excerpty/źródła z jednego retrievalu (count=1) NIE spełniają min=3.
    draft = _draft(
        sources=[_src("https://e.example/doc", claim=f"claim{i}") for i in range(3)],
        confirmed_claims=[f"claim{i}" for i in range(3)],
    )
    outcome = validate_draft(draft, **_THRESHOLDS, evidence_source_count=1)
    assert not outcome.passed
    assert TOO_FEW_SOURCES in outcome.reasons


def test_evidence_source_count_three_does_not_flag_too_few():
    # Trzy ODRĘBNE retrievale (count=3) spełniają cardinality min=3.
    draft = _draft(
        sources=[_src(f"https://e.example/{i}", claim=f"claim{i}") for i in range(3)],
        confirmed_claims=[f"claim{i}" for i in range(3)],
    )
    outcome = validate_draft(draft, **_THRESHOLDS, evidence_source_count=3)
    assert TOO_FEW_SOURCES not in outcome.reasons


def test_legacy_source_count_unchanged_without_evidence_arg():
    # Regresja legacy (web-search/offline): bez evidence_source_count liczba
    # źródeł = liczba sensownych rekordów — dokładnie jak dotąd. Trzy sensowne
    # rekordy przy min=3 NIE dają TOO_FEW_SOURCES.
    draft = _draft(
        sources=[_src(f"https://e.example/{i}", claim=f"claim{i}") for i in range(3)],
        confirmed_claims=[f"claim{i}" for i in range(3)],
    )
    outcome = validate_draft(draft, **_THRESHOLDS)
    assert TOO_FEW_SOURCES not in outcome.reasons
    # a dwa rekordy nadal dają TOO_FEW_SOURCES (niezmieniona semantyka wierszy).
    two = _draft(
        sources=[_src(f"https://e.example/{i}", claim=f"claim{i}") for i in range(2)],
        confirmed_claims=[f"claim{i}" for i in range(2)],
    )
    assert TOO_FEW_SOURCES in validate_draft(two, **_THRESHOLDS).reasons
