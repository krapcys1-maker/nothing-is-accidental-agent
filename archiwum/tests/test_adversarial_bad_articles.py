"""Counter-evidence set: articles that MUST be blocked.

Every other gate test in this repo asks whether a sound draft survives. Twenty
false positives were fixed on 2026-08-14, each of them a case where the gate
stopped an article that was fine, and each fix moved the gate in the same
direction: let more through. Three separate checks were loosened in one day.

Nothing in the suite asked the opposite question. That is the dangerous half:
a gate that has only ever been tuned to stop blocking good work has no measured
evidence that it still blocks bad work, and the whole quality argument for
autonomy rests on exactly that.

So these drafts are deliberately defective, each in one specific way a real
article could go wrong, and each must fail. The reviewer here is honest - it
classifies what it is given faithfully - because the point is to test OUR
deterministic floors, not the model's judgement. A reviewer that lies is a
different test, and the entries below where the reviewer mislabels something
cover that separately.
"""
from __future__ import annotations

import pytest

from app.content.quality_gate import (
    FABRICATED_PERSONAL_EXPERIENCE,
    FACTUAL_CLAIM_EVIDENCE_MISSING,
    FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE,
    NON_FACTUAL_CLASSIFICATION_INCONSISTENT,
    UNATTRIBUTED_SOURCE_APPEAL,
    UNSUPPORTED_FACTUAL_CLAIM,
    ClaimClassification,
    ClaimReviewOutcome,
    QualityCheck,
    assess_draft,
)
from tests.claim_accounting_fakes import FakeClaimAccountingReviewer, grounded_fact
from tests.test_prec5_claim_accounting_cost_cap import EVIDENCE_ID, _entry
from tests.test_prec5_repair_regression import _brief, _draft, _evidence


def _codes(verdict) -> set[str]:
    return {item.get("code") for item in verdict.findings}


def _claim_gate_passed(verdict) -> bool:
    return all(
        item.get("check") != QualityCheck.NO_OUT_OF_CORPUS_CLAIMS.value
        and item.get("check") != QualityCheck.FACTUAL_CLAIM_SUPPORT.value
        and item.get("check") != QualityCheck.NO_FABRICATED_EXPERIENCE.value
        for item in verdict.findings
    )


def _assess_honest(body: str):
    """Assess a draft with a reviewer that classifies faithfully."""
    return assess_draft(
        _draft(body),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(default=grounded_fact(EVIDENCE_ID)),
    )


# --- 1. Fabricated quantities ------------------------------------------------
# The most common way an explainer goes wrong: a number that sounds plausible,
# that no source in the frozen package contains.

FABRICATED_NUMBERS = (
    "Gate assignment follows contractual priority in 87 percent of cases.",
    "The contract was signed in 1997 and has not been revised since.",
    "Airlines pay $4.2 million a year for preferential gate access.",
    "Roughly 12,500 passengers a day pass through the affected gates.",
    "The delay rose by 3.7 percentage points after the change.",
)


@pytest.mark.parametrize("sentence", FABRICATED_NUMBERS)
def test_fabricated_quantity_is_blocked(sentence):
    verdict = _assess_honest(f"Gate assignment follows contractual priority. {sentence}")
    assert UNSUPPORTED_FACTUAL_CLAIM in _codes(verdict), (
        f"a number absent from the corpus was released: {sentence!r}"
    )
    assert not _claim_gate_passed(verdict)


# --- 2. Appeals to authority the package does not contain --------------------

UNBACKED_APPEALS = (
    "According to a recent study, boarding queues shorten when gates rotate.",
    "Analysts estimate the practice costs travellers a full working day a year.",
    "Data from the regulator confirms the pattern across every major hub.",
)


@pytest.mark.parametrize("sentence", UNBACKED_APPEALS)
def test_unbacked_source_appeal_is_blocked(sentence):
    verdict = _assess_honest(f"{sentence} The ordinary result is not accidental.")
    assert UNATTRIBUTED_SOURCE_APPEAL in _codes(verdict), (
        f"an appeal to an absent authority was released: {sentence!r}"
    )


# The deterministic floor is defeated by corpus vocabulary, and this records
# exactly where. It fires only when the sentence shares fewer than
# min_evidence_overlap content words with the corpus, so borrowing two of them
# launders any invented attribution around a claim the corpus never makes.
#
# This is NOT a bug to paper over and NOT a case the floors can decide: whether
# "raises average taxi time" exceeds a corpus about contractual gate priority is
# a judgement about meaning. It belongs to the reviewer, which reads the whole
# evidence package and reports an unsupported claim as EVIDENCE_GROUNDED_FACT
# with no evidence - the path test_fact_asserted_with_no_evidence_is_blocked
# covers.
#
# The consequence is worth stating plainly before anyone runs this unattended:
# the deterministic floors catch fabricated NUMBERS and bare appeals. They do
# not catch semantic overreach dressed in the corpus's own words. That class of
# defect has exactly one guard, and it is a paid model call.
LAUNDERED_BY_CORPUS_VOCABULARY = (
    "Research shows that contractual priority raises average taxi time.",
)


@pytest.mark.parametrize("sentence", LAUNDERED_BY_CORPUS_VOCABULARY)
def test_semantic_overreach_is_the_reviewers_job_not_the_floors(sentence):
    """Documents the boundary so nobody mistakes the floors for a fact checker."""
    verdict = _assess_honest(f"{sentence} The ordinary result is not accidental.")
    assert UNATTRIBUTED_SOURCE_APPEAL not in _codes(verdict)


# --- 3. Invented lived experience --------------------------------------------
# The account must never claim to have been somewhere or spoken to someone.

FABRICATED_EXPERIENCE = (
    "I stood at the gate last week and watched the board change twice.",
    "When I worked at the airport, the rule was never written down.",
    "A friend of mine told me the contracts are renegotiated every spring.",
    "My family waited three hours at a gate that had already been reassigned.",
)


@pytest.mark.parametrize("sentence", FABRICATED_EXPERIENCE)
def test_fabricated_personal_experience_is_blocked(sentence):
    verdict = _assess_honest(f"Gate assignment follows contractual priority. {sentence}")
    assert FABRICATED_PERSONAL_EXPERIENCE in _codes(verdict), (
        f"invented lived experience was released: {sentence!r}"
    )


# --- 4. A reviewer that lies about the class ---------------------------------
# The gate must not simply believe the reviewer. These entries are internally
# dishonest in the specific ways a degraded or confused reviewer produces.


def test_fact_asserted_with_no_evidence_is_blocked():
    """The core protection: a grounded fact that cites nothing."""
    verdict = assess_draft(
        _draft("Gate assignment follows contractual priority."),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=lambda segment, ids: _entry(
                segment, ids,
                classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
                evidence_ids=(),
                external_fact=True,
            ),
        ),
    )
    assert FACTUAL_CLAIM_EVIDENCE_MISSING in _codes(verdict)
    assert not _claim_gate_passed(verdict)


def test_citation_outside_the_frozen_package_is_blocked():
    """An invented evidence id must never be accepted as support."""
    verdict = assess_draft(
        _draft("Gate assignment follows contractual priority."),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=lambda segment, ids: _entry(
                segment, ids,
                classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
                evidence_ids=("research-card:99:confirmed-claim:7",),
                external_fact=True,
            ),
        ),
    )
    assert FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE in _codes(verdict)
    assert not _claim_gate_passed(verdict)


def test_named_body_absent_from_the_corpus_cannot_be_filed_as_prose():
    """Laundering an attribution by calling it prose must fail.

    This is the check that was narrowed on 2026-08-14 to compare against the
    corpus instead of against the alphabet. The narrowing must not have removed
    it: a body the evidence never mentions is still a checkable assertion.
    """
    verdict = assess_draft(
        _draft("The Federal Railroad Administration requires a backup battery."),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=lambda segment, ids: _entry(
                segment, ids,
                classification=ClaimClassification.NON_FACTUAL_PROSE,
                outcome=ClaimReviewOutcome.PASS,
                external_fact=False,
            ),
        ),
    )
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)
    assert not _claim_gate_passed(verdict)


def test_factual_question_cannot_be_filed_as_prose():
    """A proposition smuggled in as a rhetorical question still counts."""
    verdict = assess_draft(
        _draft("Did the regulator approve the contract in 2019?"),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=lambda segment, ids: _entry(
                segment, ids,
                classification=ClaimClassification.NON_FACTUAL_PROSE,
                outcome=ClaimReviewOutcome.PASS,
                external_fact=False,
            ),
        ),
    )
    assert not _claim_gate_passed(verdict)


def test_inference_carrying_an_outside_fact_is_blocked():
    """Reasoning may reason over the package; it may not import new facts."""
    verdict = assess_draft(
        _draft("Gate assignment follows contractual priority."),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=lambda segment, ids: _entry(
                segment, ids,
                classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
                external_fact=True,
            ),
        ),
    )
    assert not _claim_gate_passed(verdict)


# --- 5. The whole set, as one number -----------------------------------------


def test_every_defective_draft_in_this_file_is_blocked():
    """One assertion that summarises the file, so a regression is one line.

    If this ever fails, the gates have stopped catching a class of defect and
    no amount of green elsewhere makes the pipeline safe to run unattended.
    """
    released: list[str] = []
    for sentence in FABRICATED_NUMBERS + UNBACKED_APPEALS + FABRICATED_EXPERIENCE:
        verdict = _assess_honest(
            f"Gate assignment follows contractual priority. {sentence}"
        )
        if _claim_gate_passed(verdict):
            released.append(sentence)
    assert not released, f"defective drafts released by the gates: {released}"
