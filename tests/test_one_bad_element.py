"""One bad element must not destroy work the provider was already paid for.

Nine separate validators held the same idea: find one unusable item in a
collection, reject the whole collection. Each was locally reasonable and each
was written in a different wave of the build, so nothing ever noticed they were
the same mistake. Every one of them was discovered by a live failure, and each
discovery cost between 0.60 and 0.97 USD.

  1. an unclassified source condemned the corpus
  2. duplicate sources condemned the corpus
  3. a seventh citable number was fatal to the whole card
  4. a claim that could not be bound to evidence destroyed the card
  5. one abbreviated fingerprint discarded a 22-entry paid review
  6. a repeated source identity threw away a settled discovery
  7. a prompt inviting 8 confirmed claims against a ceiling of 6
  8. the same for uncertain_claims, 4 against 3
  9. the same for contradictions, 4 against 3

Items 7-9 are now impossible by construction - see
test_prompt_contract_agreement.py. This file guards 1-6: the behaviour, not the
instance. Each case below feeds a validator a collection where exactly one item
is unusable and asserts the rest survives.

The line this file does NOT cross: authority, identity and money stay
fail-closed. A bad approval, a mismatched intent fingerprint, an exceeded cost
ceiling or a wrong schema version must still reject everything, because there
losing money is better than spending it wrongly. This is only about discarding
work already paid for.
"""
from __future__ import annotations

import pytest

from app.research import output_contract as oc
from app.research.base import ResearchDraft


def _draft_with(**overrides) -> ResearchDraft:
    """A minimal draft that satisfies the size contract before overrides."""
    base = dict(
        question="Why is the tag on a mattress there?",
        working_thesis="A federal flammability rule requires the label.",
        main_mechanism="The rule assigns responsibility to the manufacturer.",
        confirmed_claims=["a claim", "b claim", "c claim", "d claim"],
        uncertain_claims=["one caveat"],
        contradictions=[],
        strongest_counterargument="The label may predate the rule.",
        citable_numbers=["16 CFR 1632"],
        visual_idea="A close photograph of the tag.",
        confidence_score=0.6,
        source_quality_score=0.7,
        sources=[],
    )
    base.update(overrides)
    return ResearchDraft(**base)


def test_a_surplus_citable_number_is_trimmed_not_fatal():
    """The list carries no meaning by its length; the writer never cites it."""
    draft = _draft_with(
        citable_numbers=[f"figure {i}" for i in range(oc.MAX_CITABLE_NUMBERS + 3)]
    )
    oc.enforce_single_research_draft_budget(draft)
    assert len(draft.citable_numbers) == oc.MAX_CITABLE_NUMBERS


def test_caveat_lists_still_fail_closed_rather_than_being_truncated():
    """The deliberate exception, pinned so nobody 'fixes' it into a trim.

    uncertain_claims becomes the writer's forbidden list and contradictions are
    what stop a confident sentence outrunning a messy record. Silently deleting
    a caveat would make the article MORE assertive than the evidence supports,
    which is worse than losing the card. The prompt is kept in step with these
    ceilings by test_prompt_contract_agreement.py, so a well-behaved model never
    reaches this path.
    """
    with pytest.raises(Exception):
        oc.enforce_single_research_draft_budget(
            _draft_with(
                uncertain_claims=[f"c{i}" for i in range(oc.MAX_UNCERTAIN_CLAIMS + 1)]
            )
        )


def test_a_repeated_source_identity_drops_the_repeat_not_the_result():
    """Discovery naming one regulation twice is ordinary, not corruption.

    A question that names 16 CFR 1632 and 1633 invites exactly this. Condemning
    the answer for it discarded a settled 0.618865 USD call that had found what
    it was asked for.
    """
    import inspect

    from app.storage import repositories

    source = inspect.getsource(repositories.SqliteStorage.finalize_source_discovery_success)
    assert "A1 source identities must be unique within one result" not in source, (
        "the whole-result rejection is back: a repeated identity must drop the "
        "repeat, not the discovery"
    )
    assert "seen_identities" in source, (
        "the deduplication that replaced it is gone"
    )


def test_an_abbreviated_fingerprint_does_not_discard_the_review():
    """A prefix identifies the segment; segment_id already carries it."""
    import inspect

    from app.content import reviewer

    source = inspect.getsource(reviewer.parse_reviewer_response)
    assert "startswith" in source, (
        "the reviewer parser no longer accepts an abbreviated fingerprint echo; "
        "one abbreviation in a 22-entry review used to discard the whole paid "
        "review"
    )


def test_source_admission_records_findings_rather_than_condemning():
    """Unclassified and duplicate sources are findings, not verdicts."""
    import inspect

    from app.research import source_admission

    source = inspect.getsource(source_admission)
    # The corpus-level refusals that remain are about the corpus as a whole -
    # too few sources, no primary record - not about one member of it.
    assert "SYNDICATED_DUPLICATE_SOURCES" in source, (
        "duplicate sources are no longer collapsed with a recorded finding"
    )
    assert "is simply not admitted" in source, (
        "the comment recording why an unclassified source is dropped rather "
        "than condemning the corpus is gone; check the behaviour went with it"
    )
