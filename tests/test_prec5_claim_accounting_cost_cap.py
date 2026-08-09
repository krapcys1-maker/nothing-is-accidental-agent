"""PRE-C5 claim-accounting counterprobes and paid over-cap closure."""
from __future__ import annotations

from datetime import timedelta
import json

import pytest

from app.content.evaluations import evaluate_draft
from app.content.quality_gate import (
    CLAIM_ACCOUNTING_COVERAGE_DUPLICATE,
    CLAIM_ACCOUNTING_COVERAGE_MISSING,
    CLAIM_ACCOUNTING_ENTRY_MALFORMED,
    CLAIM_ACCOUNTING_REVIEW_MISSING,
    CLAIM_CLASSIFICATION_UNKNOWN,
    FACTUAL_CLAIM_EVIDENCE_MISSING,
    FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE,
    FACTUAL_CLAIM_SCOPE_NOT_CONFIRMED,
    NON_FACTUAL_CLASSIFICATION_INCONSISTENT,
    INFERENCE_CONTAINS_EXTERNAL_FACT,
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    QualityCheck,
    assess_draft,
)
from app.core.clock import FixedClock
from app.models import JobStatus, ProviderAttemptStatus, RunStatus
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    grounded_fact,
)
from tests.test_prec5_repair_regression import (
    NOW,
    PaidFakeWriter,
    _brief,
    _draft,
    _evidence,
    _run_paid,
)


EVIDENCE_ID = "research-card:1:confirmed-claim:0"


def _entry(
    segment,
    _evidence_ids,
    *,
    classification,
    evidence_ids=(),
    outcome=ClaimReviewOutcome.PASS,
    external_fact=None,
    reason="fake independent reviewer completed semantic review",
):
    return ClaimAccountingEntry(
        segment_id=segment.segment_id,
        segment_fingerprint=segment.fingerprint,
        classification=classification,
        evidence_ids=tuple(evidence_ids),
        reason=reason,
        outcome=outcome,
        contains_external_fact=external_fact,
    )


def _assess(sentence, decide, *, evidence=None):
    frozen = (_evidence(),) if evidence is None else tuple(evidence)
    return assess_draft(
        _draft(sentence),
        _brief(),
        evidence=frozen,
        claim_reviewer=FakeClaimAccountingReviewer(decide=decide),
    )


def _unsupported_fact(sentence):
    return _assess(
        sentence,
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
            evidence_ids=(),
            outcome=ClaimReviewOutcome.PASS,
            external_fact=True,
        ),
    )


def _claim_gate_passed(verdict):
    return (
        verdict.claim_coverage_complete
        and verdict.passed(QualityCheck.FACTUAL_CLAIM_SUPPORT)
        and verdict.passed(QualityCheck.NO_OUT_OF_CORPUS_CLAIMS)
    )


def test_rv1_a_single_depot_without_evidence_blocks():
    verdict = _unsupported_fact(
        "The system routes all freight through a single depot."
    )
    assert not _claim_gate_passed(verdict)
    assert FACTUAL_CLAIM_EVIDENCE_MISSING in {f["code"] for f in verdict.findings}


def test_rv1_b_plain_causal_fact_without_markers_blocks():
    assert not _claim_gate_passed(
        _unsupported_fact("Cheap bearings make the conveyor fail early.")
    )


def test_rv1_c_historical_fact_without_markers_blocks():
    assert not _claim_gate_passed(
        _unsupported_fact("Merchants crossed this pass before the railway arrived.")
    )


def test_rv1_d_lexical_overlap_with_meaning_expansion_blocks():
    verdict = _assess(
        "Gate priority eliminates every boarding delay.",
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
            evidence_ids=(EVIDENCE_ID,),
            outcome=ClaimReviewOutcome.BLOCK,
            external_fact=True,
            reason="evidence describes priority, not elimination of all delays",
        ),
    )
    assert not _claim_gate_passed(verdict)
    assert FACTUAL_CLAIM_SCOPE_NOT_CONFIRMED in {f["code"] for f in verdict.findings}


def test_rv1_e_short_bridge_fact_without_evidence_blocks():
    assert not _claim_gate_passed(
        _unsupported_fact("The bridge closes at night.")
    )


def test_rv1_f_physical_property_without_evidence_blocks():
    assert not _claim_gate_passed(
        _unsupported_fact("The machine uses a single backup battery.")
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "I think this is a bad trade-off.",
        "This suggests the incentive is poorly aligned.",
    ],
)
def test_rv1_g_h_explicit_opinion_and_inference_can_pass(sentence):
    verdict = _assess(
        sentence,
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
            outcome=ClaimReviewOutcome.PASS,
            external_fact=False,
        ),
    )
    assert _claim_gate_passed(verdict)
    assert verdict.claim_accounting[0]["classification"] == (
        ClaimClassification.ARGUMENT_OR_INFERENCE.value
    )


def test_rv1_i_fact_exactly_covered_by_frozen_evidence_passes():
    verdict = _assess(
        "Gate assignment follows contractual priority, not passenger convenience.",
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
            evidence_ids=(EVIDENCE_ID,),
            outcome=ClaimReviewOutcome.PASS,
            external_fact=True,
            reason="frozen claim and excerpt cover the sentence without expansion",
        ),
    )
    assert _claim_gate_passed(verdict)


def test_rv1_j_reviewer_omits_one_substantive_sentence_blocks():
    omitted = "The bridge closes at night."
    body = "Gate assignment follows contractual priority. " + omitted
    verdict = assess_draft(
        _draft(body),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            default=grounded_fact(EVIDENCE_ID),
            omit_texts=(omitted,),
        ),
    )
    assert not _claim_gate_passed(verdict)
    assert CLAIM_ACCOUNTING_COVERAGE_MISSING in {f["code"] for f in verdict.findings}


def test_rv1_k_factual_declaration_misclassified_non_factual_blocks():
    verdict = _assess(
        "The machine uses a single backup battery.",
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.NON_FACTUAL_PROSE,
            outcome=ClaimReviewOutcome.PASS,
            external_fact=False,
        ),
    )
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in {
        f["code"] for f in verdict.findings
    }


def test_rv1_l_evidence_id_outside_frozen_package_blocks():
    verdict = _assess(
        "Gate assignment follows contractual priority.",
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
            evidence_ids=("research-card:999:confirmed-claim:0",),
            external_fact=True,
        ),
    )
    assert not _claim_gate_passed(verdict)
    assert FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE in {
        f["code"] for f in verdict.findings
    }


def test_rv1_m_article_without_reviewer_blocks():
    verdict = assess_draft(_draft("A question of incentives."), _brief(), evidence=(_evidence(),))
    assert not _claim_gate_passed(verdict)
    assert CLAIM_ACCOUNTING_REVIEW_MISSING in {f["code"] for f in verdict.findings}


def test_claim_accounting_is_carried_by_the_existing_evaluation_audit_shape():
    sentence = "Gate assignment follows contractual priority, not passenger convenience."
    reviewer = FakeClaimAccountingReviewer(decide=lambda segment, ids: _entry(
        segment,
        ids,
        classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
        evidence_ids=(EVIDENCE_ID,),
        external_fact=True,
    ))
    evaluations = evaluate_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
        claim_reviewer=reviewer,
    )
    unsupported = next(
        item for item in evaluations if item.evaluation_type.value == "UNSUPPORTED_CLAIMS"
    )
    audit = next(
        item for item in unsupported.findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    assert audit["coverage_complete"] is True
    assert audit["claims"][0]["segment_id"].startswith("sentence:0:")
    assert audit["claims"][0]["reviewer_outcome"] == "PASS"


def test_claim_accounting_audit_is_persisted_with_the_draft_evaluation(
    storage, settings, account,
):
    request, _, _, summary = _run_paid(
        storage, settings, account,
        suffix="claim-audit-durable",
        writer=PaidFakeWriter(),
    )
    assert summary.status.value == "PENDING_APPROVAL"
    row = storage.conn.execute(
        "SELECT findings_json FROM content_draft_evaluations WHERE content_id=("
        "SELECT id FROM content_items WHERE job_id=?) "
        "AND evaluation_type='UNSUPPORTED_CLAIMS'",
        (request.job_id,),
    ).fetchone()
    assert row is not None
    findings = json.loads(row["findings_json"])
    audit = next(
        item for item in findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    assert audit["coverage_complete"] is True
    assert len(audit["claims"]) >= 1


def test_unknown_and_ambiguous_reviewer_outputs_fail_closed():
    class UnknownReviewer:
        reviewer_version = "fake-unknown-reviewer-v1"

        def review(self, *, draft, brief, evidence, segments):
            del draft, brief, evidence
            return tuple({
                "segment_id": segment.segment_id,
                "segment_fingerprint": segment.fingerprint,
                "classification": "UNKNOWN",
                "evidence_ids": (),
                "reason": "reviewer could not classify this segment",
                "outcome": "PASS",
                "contains_external_fact": None,
            } for segment in segments)

    unknown = assess_draft(
        _draft("The bridge closes at night."), _brief(),
        evidence=(_evidence(),), claim_reviewer=UnknownReviewer(),
    )
    assert CLAIM_CLASSIFICATION_UNKNOWN in {f["code"] for f in unknown.findings}

    class AmbiguousReviewer(UnknownReviewer):
        reviewer_version = "fake-ambiguous-reviewer-v1"

        def review(self, *, draft, brief, evidence, segments):
            rows = list(super().review(
                draft=draft, brief=brief, evidence=evidence, segments=segments,
            ))
            rows[0]["classification"] = "EVIDENCE_GROUNDED_FACT"
            rows[0]["outcome"] = "MAYBE"
            return tuple(rows)

    ambiguous = assess_draft(
        _draft("The bridge closes at night."), _brief(),
        evidence=(_evidence(),), claim_reviewer=AmbiguousReviewer(),
    )
    assert CLAIM_ACCOUNTING_ENTRY_MALFORMED in {
        f["code"] for f in ambiguous.findings
    }


def test_duplicate_accounting_and_inference_hiding_a_fact_fail_closed():
    class DuplicateReviewer:
        reviewer_version = "fake-duplicate-reviewer-v1"

        def review(self, *, draft, brief, evidence, segments):
            row = _entry(
                segments[0], (),
                classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
                external_fact=False,
            )
            return (row, row)

    duplicate = assess_draft(
        _draft("I think this is a bad trade-off."), _brief(),
        evidence=(_evidence(),), claim_reviewer=DuplicateReviewer(),
    )
    assert CLAIM_ACCOUNTING_COVERAGE_DUPLICATE in {
        f["code"] for f in duplicate.findings
    }

    hidden = _assess(
        "I think the bridge closes at night.",
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
            external_fact=True,
            reason="opinion wrapper contains a new external fact",
        ),
    )
    assert INFERENCE_CONTAINS_EXTERNAL_FACT in {f["code"] for f in hidden.findings}


SELF_CHALLENGE_FACTS = (
    ("logistics", "The depot dispatches every truck through the eastern gate."),
    ("infrastructure", "The tunnel carries the district's only water main."),
    ("economics", "Lower fees shifted demand toward the smaller exchange."),
    ("institutional_behavior", "The agency delays applications until quarter end."),
    ("historical_fact", "Workers built the viaduct before the port expanded."),
    ("physical_property", "The valve contains a ceramic inner seal."),
    ("operational_rule", "The terminal locks its doors after the final train."),
    ("causal_statement", "Thin insulation makes the battery lose heat faster."),
    ("named_entity", "Northbridge Transit owns the maintenance depot."),
    ("unnamed_entity", "The operator keeps a second ledger off site."),
    ("supply_chain", "Each shipment passes through one private warehouse."),
    ("market_structure", "One wholesaler controls the local spare-parts market."),
    ("software_operation", "The service deletes inactive accounts each Friday."),
    ("energy_system", "The building draws backup power from a diesel generator."),
)


@pytest.mark.parametrize("factual_class,sentence", SELF_CHALLENGE_FACTS)
def test_self_challenge_unsupported_external_fact_classes_all_block(
    factual_class, sentence,
):
    verdict = _unsupported_fact(sentence)
    assert not _claim_gate_passed(verdict), factual_class


@pytest.mark.parametrize(
    "label,sentence,classification",
    [
        ("opinion", "I think this trade-off is unacceptable.", ClaimClassification.ARGUMENT_OR_INFERENCE),
        ("rhetorical_question", "What would a fair incentive look like?", ClaimClassification.ARGUMENT_OR_INFERENCE),
        ("metaphor", "The policy is a maze with no centre.", ClaimClassification.ARGUMENT_OR_INFERENCE),
        ("style_transition", "Now, a step back.", ClaimClassification.NON_FACTUAL_PROSE),
        ("explicit_inference", "This suggests the incentive is misaligned.", ClaimClassification.ARGUMENT_OR_INFERENCE),
    ],
)
def test_self_challenge_non_factual_false_positive_controls_pass(
    label, sentence, classification,
):
    verdict = _assess(
        sentence,
        lambda segment, ids: _entry(
            segment,
            ids,
            classification=classification,
            external_fact=False,
            reason=f"fake reviewer confirmed {label} without a new external fact",
        ),
    )
    assert _claim_gate_passed(verdict), label


def test_paid_content_over_cap_terminalizes_atomically_without_reaper(
    storage, settings, account,
):
    writer = PaidFakeWriter(cost_usd=0.075)
    request, _, _, summary = _run_paid(
        storage, settings, account, suffix="paid-over-cap", writer=writer,
    )
    assert writer.calls == 1
    assert summary.status.value == "NEEDS_VERIFICATION"
    assert storage.get_job(request.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.get_run(summary.run_id).status is RunStatus.STOPPED
    usage = storage.conn.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(estimated_cost_usd),0) AS cost "
        "FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()
    assert usage["n"] == 1
    assert usage["cost"] == pytest.approx(0.075)
    attempt = storage.conn.execute(
        "SELECT status,actual_cost_usd,settled_at FROM provider_attempts WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value
    assert attempt["actual_cost_usd"] is None
    assert attempt["settled_at"] is None
    counts = storage.conn.execute(
        "SELECT SUM(status='SETTLED') AS settled,"
        "SUM(status='NEEDS_RECONCILIATION') AS reconciliation "
        "FROM provider_attempts WHERE job_id=?", (request.job_id,),
    ).fetchone()
    assert (counts["settled"], counts["reconciliation"]) == (0, 1)


def test_later_reaper_cannot_change_over_cap_cost_or_make_second_call(
    storage, settings, account,
):
    writer = PaidFakeWriter(cost_usd=0.075)
    request, _, _, summary = _run_paid(
        storage, settings, account, suffix="paid-over-cap-reaper", writer=writer,
    )
    before = storage.conn.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(estimated_cost_usd),0) AS cost "
        "FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()
    storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(hours=4))
    )
    after = storage.conn.execute(
        "SELECT COUNT(*) AS n,COALESCE(SUM(estimated_cost_usd),0) AS cost "
        "FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()
    assert (after["n"], after["cost"]) == (before["n"], before["cost"])
    assert writer.calls == 1
    assert storage.claim_specific_job(
        request.job_id, "second-owner", 60,
        clock=FixedClock(NOW + timedelta(hours=5)),
    ) is None
    assert storage.get_job(request.job_id).status is JobStatus.NEEDS_VERIFICATION
