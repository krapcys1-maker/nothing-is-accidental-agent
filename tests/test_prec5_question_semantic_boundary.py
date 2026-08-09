"""PRE-C5 question semantic boundary contract.

Question meaning belongs to the independent reviewer.  The deterministic
layer enforces identity, complete accounting and the closed result contract;
it never releases an ARTICLE question through NON_FACTUAL_PROSE.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.content.contracts import EvaluationType, PipelineDecision
from app.content.evaluations import aggregate_decision, evaluate_draft
from app.content.foundation import ContentType
from app.content.quality_gate import (
    CLAIM_ACCOUNTING_COVERAGE_DUPLICATE,
    CLAIM_ACCOUNTING_COVERAGE_EXTRA,
    CLAIM_ACCOUNTING_COVERAGE_MISSING,
    CLAIM_ACCOUNTING_IDENTITY_MISMATCH,
    CLAIM_ACCOUNTING_REVIEW_MISSING,
    CLAIM_CLASSIFICATION_UNKNOWN,
    FACTUAL_CLAIM_EVIDENCE_MISSING,
    FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE,
    INFERENCE_CONTAINS_EXTERNAL_FACT,
    NON_FACTUAL_CLASSIFICATION_INCONSISTENT,
    UNSUPPORTED_FACTUAL_CLAIM,
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    QualityCheck,
    assess_draft,
)
from app.content.writer import FakeContentWriter
from app.core.clock import FixedClock
from tests.c2_fixtures import seed_c2_research
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    external_fact_as_inference,
    external_fact_without_evidence,
    grounded_fact,
    honest_inference,
    real_prose,
)
from tests.test_content_pipeline_c2 import (
    NOW,
    prepare_and_claim,
    run_offline_content_pipeline,
)
from tests.test_prec5_repair_regression import (
    GROUNDED_BODY,
    _brief,
    _draft,
    _evidence,
)


EVIDENCE_ID = "research-card:1:confirmed-claim:0"

MAJOR_QUESTION_MARKER_CASES = (
    "Now, didn't the inspector flag the corrosion?!",
    "Instead, hasn't the agency withheld the raw data?!",
    "Meanwhile, couldn't the seawall withstand the surge?!",
    "For now, what about the exclusion zone?!",
    "A step back, the capital of Australia?!",
)

QUESTION_MARKER_SHAPES = (
    ("exact", "Now, the exclusion zone?"),
    ("question-bang", "Now, the exclusion zone?!"),
    ("double-question", "Now, the exclusion zone??"),
    ("question-period", "Now, the exclusion zone?."),
    ("question-semicolon", "Now, the exclusion zone?;"),
    ("question-ellipsis", "Now, the exclusion zone?..."),
    ("before-closing-quote", 'Now, "the exclusion zone?"'),
    ("before-closing-parenthesis", "Now, (the exclusion zone?)"),
    ("before-closing-bracket", "Now, [the exclusion zone?]"),
    ("trailing-whitespace", "Now, the exclusion zone?   "),
    ("transition-contracted-negative", MAJOR_QUESTION_MARKER_CASES[0]),
    ("transition-noun-phrase", "Instead, the exclusion zone?!"),
    (
        "transition-rhetorical-tail",
        "For now, the depot closes at six, doesn't it?!",
    ),
    ("fullwidth-question", "Now, the exclusion zone？！"),
)


def _assess(sentence: str, decision):
    normalized = " ".join(sentence.split())
    return assess_draft(
        _draft(sentence),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            profile={normalized: decision},
        ),
    )


def _claim_gate_passed(verdict) -> bool:
    return (
        verdict.claim_coverage_complete
        and verdict.passed(QualityCheck.FACTUAL_CLAIM_SUPPORT)
        and verdict.passed(QualityCheck.NO_OUT_OF_CORPUS_CLAIMS)
    )


def _codes(verdict) -> set[str]:
    return {item["code"] for item in verdict.findings}


FACTUAL_QUESTIONS = (
    "Who did it?",
    "What did they do?",
    "Where is it?",
    "When was it done?",
    "Why do hospitals ration beds?",
    "Which company owns the depot?",
    "How does the valve regulate pressure?",
    "How many beds are available?",
    "How much water does the reservoir hold?",
    "Did they do it?",
    "Does the city own the bridge?",
    "Is the bridge closed?",
    "Are ferries running today?",
    "Has it been done?",
    "Have inspectors approved the tunnel?",
    "Will the factory reopen tomorrow?",
    "Can the backup battery power the lift?",
    "Could the old valve withstand the pressure?",
    "Should the alarm have sounded under the rule?",
    "Didn't the council approve the contract?",
    "Isn't the northern gate locked?",
    "The depot closes at six, doesn't it?",
    "The operator owns the line, doesn't it?",
    "Do you know who did it?",
    "Can you explain where the cargo went?",
    "Where did Acme Rail move the depot?",
    "Why did Northbridge Transit cancel the route?",
    "Whose company owns the warehouse?",
    "Is the eastern tower taller than the western tower?",
    "Are there spare generators in the basement?",
    "Who is the terminal operator?",
    "Is the emergency valve open?",
    "Where is the maintenance depot?",
    "When does the final train leave?",
    "Are there exactly enough seats for the crew?",
    "It is done, so what?",
    "What, then, did the council approve?",
    "Granted, why did the airline cancel the flight?",
    "Who was appointed to run the authority?",
    "Where was the cargo stored?",
    "Had the port expanded before the railway arrived?",
    "Would the old system have rejected the request?",
    "When will the replacement bridge open?",
    "What belongs to the transit authority?",
    "How far does the service extend?",
    "How often does the ferry run?",
    "What did the operator not disclose?",
    "Which of the two depots handles freight?",
    "Wasn't the backup generator working?",
    "The bridge is closed, but why?",
)


@pytest.mark.parametrize("sentence", FACTUAL_QUESTIONS)
def test_each_factual_question_has_all_four_required_routes(sentence):
    wrong_prose = _assess(sentence, real_prose())
    assert not _claim_gate_passed(wrong_prose)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(wrong_prose)

    external_inference = _assess(sentence, external_fact_as_inference())
    assert not _claim_gate_passed(external_inference)
    assert INFERENCE_CONTAINS_EXTERNAL_FACT in _codes(external_inference)

    ungrounded = _assess(sentence, external_fact_without_evidence())
    assert not _claim_gate_passed(ungrounded)
    assert FACTUAL_CLAIM_EVIDENCE_MISSING in _codes(ungrounded)

    grounded = _assess(sentence, grounded_fact(EVIDENCE_ID))
    assert _claim_gate_passed(grounded)
    assert len(grounded.claim_accounting) == 1
    assert grounded.claim_accounting[0]["reviewer_outcome"] == "PASS"


NON_FACTUAL_QUESTIONS = (
    "Why bother?",
    "What would fairness look like?",
    "Should we value convenience over resilience?",
    "Who would want a world without surprises?",
    "What if the opposite were true?",
    "Suppose the rule vanished; what then?",
    "Would that be a better trade-off?",
    "Is efficiency always worth the price?",
    "Why not choose a gentler metaphor?",
    "Could we imagine another ending?",
    "What ought a fair process to feel like?",
    "Which principle should guide us?",
    "How should we think about responsibility?",
    "When should patience give way to action?",
    "Where should the moral line be drawn?",
    "Does that seem reasonable?",
    "Isn't that the deeper point?",
    "Would anyone call that elegant?",
    "What if every assumption were reversed?",
    "How might the story end differently?",
    "Why cling to a tired frame?",
    "Can a metaphor carry too much weight?",
    "What deserves our attention?",
    "Who are we trying to persuade?",
    "Wouldn't a quieter ending work better?",
)


@pytest.mark.parametrize("sentence", NON_FACTUAL_QUESTIONS)
def test_non_factual_questions_keep_the_honest_inference_route(sentence):
    verdict = _assess(sentence, honest_inference())
    assert _claim_gate_passed(verdict)
    assert verdict.claim_accounting[0]["classification"] == (
        ClaimClassification.ARGUMENT_OR_INFERENCE.value
    )
    assert verdict.claim_accounting[0]["contains_external_fact"] is False


@pytest.mark.parametrize(
    "sentence",
    (
        "Who did it?",
        "Why bother?",
        "What if the opposite were true?",
    ),
)
def test_wrong_non_factual_prose_output_blocks_every_question(sentence):
    verdict = _assess(sentence, real_prose())
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)
    assert verdict.claim_accounting[0]["reviewer_outcome"] == "BLOCK"


@pytest.mark.parametrize(
    ("_shape", "sentence"),
    QUESTION_MARKER_SHAPES,
    ids=[shape for shape, _ in QUESTION_MARKER_SHAPES],
)
def test_question_marker_anywhere_disables_non_factual_prose(_shape, sentence):
    verdict = _assess(sentence, real_prose())
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)
    assert verdict.claim_accounting[0]["reviewer_outcome"] == "BLOCK"


@pytest.mark.parametrize("sentence", MAJOR_QUESTION_MARKER_CASES)
def test_each_confirmed_major_example_blocks_wrong_non_factual_prose(sentence):
    verdict = _assess(sentence, real_prose())
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)
    claim = verdict.claim_accounting[0]
    assert claim["text"] == sentence
    assert claim["classification"] == "NON_FACTUAL_PROSE"
    assert claim["reviewer_outcome"] == "BLOCK"


def test_question_marker_boundary_holds_in_a_multiline_article_draft():
    question = "Now, the exclusion zone?!"
    body = f"{question}\n{GROUNDED_BODY}"
    verdict = assess_draft(
        _draft(body),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            profile={question: real_prose()},
            default=grounded_fact(EVIDENCE_ID),
        ),
    )
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)
    claim = next(item for item in verdict.claim_accounting if item["text"] == question)
    assert claim["reviewer_outcome"] == "BLOCK"


def test_semantic_reviewer_trust_boundary_is_explicit_and_not_patched_with_regex():
    """A lying reviewer remains the documented SEMANTIC REVIEWER TRUST BOUNDARY."""
    verdict = _assess("Who owns the depot?", honest_inference())
    assert _claim_gate_passed(verdict)
    assert verdict.claim_accounting[0]["classification"] == (
        ClaimClassification.ARGUMENT_OR_INFERENCE.value
    )
    assert verdict.claim_accounting[0]["contains_external_fact"] is False


def test_real_non_question_prose_retains_its_narrow_structural_route():
    verdict = _assess("Now, a step back.", real_prose())
    assert _claim_gate_passed(verdict)


def test_default_fake_is_unknown_and_fail_closed_without_a_semantic_profile():
    verdict = assess_draft(
        _draft("Who did it?"),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(),
    )
    assert not _claim_gate_passed(verdict)
    assert CLAIM_CLASSIFICATION_UNKNOWN in _codes(verdict)
    assert verdict.claim_accounting[0]["classification"] == "UNKNOWN"
    assert verdict.claim_accounting[0]["evidence_ids"] == []
    assert verdict.claim_accounting[0]["reviewer_outcome"] == "BLOCK"


SUPPORTED_FLOW_QUESTIONS = (
    "Who did it?",
    "Where is it?",
    "Why do hospitals ration beds?",
    "The depot closes at six, doesn't it?",
    "Do you know who approved the contract?",
)


def _supported_evaluations(question: str, question_decision):
    body = f"{GROUNDED_BODY} {question}"
    reviewer = FakeClaimAccountingReviewer(
        profile={question: question_decision},
        default=grounded_fact(EVIDENCE_ID),
    )
    return evaluate_draft(
        _draft(body),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=reviewer,
    )


@pytest.mark.parametrize("question", SUPPORTED_FLOW_QUESTIONS)
def test_supported_article_flow_blocks_ungrounded_factual_question(question):
    evaluations = _supported_evaluations(
        question, external_fact_without_evidence()
    )
    unsupported = next(
        item
        for item in evaluations
        if item.evaluation_type is EvaluationType.UNSUPPORTED_CLAIMS
    )
    assert unsupported.result == "FAIL"
    assert len([item for item in evaluations if item.result == "PASS"]) != 9
    assert aggregate_decision(evaluations) is not PipelineDecision.PASS
    audit = next(
        item
        for item in unsupported.findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    claim = next(item for item in audit["claims"] if item["text"] == question)
    assert claim["classification"] == "EVIDENCE_GROUNDED_FACT"
    assert claim["contains_external_fact"] is True
    assert claim["evidence_ids"] == []
    assert claim["reviewer_outcome"] == "BLOCK"


@pytest.mark.parametrize("question", MAJOR_QUESTION_MARKER_CASES)
def test_supported_article_flow_blocks_major_question_as_non_factual_prose(
    question,
):
    evaluations = _supported_evaluations(question, real_prose())
    unsupported = next(
        item
        for item in evaluations
        if item.evaluation_type is EvaluationType.UNSUPPORTED_CLAIMS
    )
    assert unsupported.result == "FAIL"
    assert len([item for item in evaluations if item.result == "PASS"]) != 9
    assert aggregate_decision(evaluations) is not PipelineDecision.PASS
    audit = next(
        item
        for item in unsupported.findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    claim = next(item for item in audit["claims"] if item["text"] == question)
    assert claim["classification"] == "NON_FACTUAL_PROSE"
    assert claim["contains_external_fact"] is False
    assert claim["evidence_ids"] == []
    assert claim["reviewer_outcome"] == "BLOCK"
    finding = next(
        item
        for item in unsupported.findings
        if item.get("code") == NON_FACTUAL_CLASSIFICATION_INCONSISTENT
        and item.get("sentence") == question
    )
    assert finding["segment_id"] == claim["segment_id"]
    assert finding["segment_fingerprint"] == claim["fingerprint"]


@pytest.mark.parametrize("question", SUPPORTED_FLOW_QUESTIONS)
def test_same_factual_question_with_in_package_evidence_can_reach_nine_passes(
    question,
):
    evaluations = _supported_evaluations(question, grounded_fact(EVIDENCE_ID))
    assert [item.result for item in evaluations] == ["PASS"] * 9
    assert aggregate_decision(evaluations) is PipelineDecision.PASS


@pytest.mark.parametrize("question", MAJOR_QUESTION_MARKER_CASES)
def test_same_major_question_with_in_package_evidence_can_reach_nine_passes(
    question,
):
    evaluations = _supported_evaluations(question, grounded_fact(EVIDENCE_ID))
    assert [item.result for item in evaluations] == ["PASS"] * 9
    assert aggregate_decision(evaluations) is PipelineDecision.PASS


def test_supported_article_with_rhetorical_question_can_reach_nine_passes():
    evaluations = _supported_evaluations("Why bother?", honest_inference())
    assert [item.result for item in evaluations] == ["PASS"] * 9
    assert aggregate_decision(evaluations) is PipelineDecision.PASS


def test_supported_article_with_punctuated_rhetorical_question_can_reach_nine_passes():
    evaluations = _supported_evaluations(
        "For now, what if the opposite were true?!",
        honest_inference(),
    )
    assert [item.result for item in evaluations] == ["PASS"] * 9
    assert aggregate_decision(evaluations) is PipelineDecision.PASS


class _QuestionWriter(FakeContentWriter):
    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def write(self, request):
        result = super().write(request)
        draft = result.draft.model_copy(
            update={"body": f"{result.draft.body.rstrip()} {self.question}"}
        )
        return result.model_copy(update={"draft": draft})


@pytest.mark.parametrize(
    ("case_no", "question"),
    tuple(enumerate(SUPPORTED_FLOW_QUESTIONS, start=1)),
)
def test_supported_article_persists_exact_ungrounded_question_audit(
    storage, account, case_no, question,
):
    seed = seed_c2_research(
        storage, account, topic_title=f"Question boundary {case_no}"
    )
    request, _, lease = prepare_and_claim(
        storage,
        seed,
        ContentType.ARTICLE,
        suffix=f"question-boundary-{case_no}",
    )
    reviewer = FakeClaimAccountingReviewer(
        profile={question: external_fact_without_evidence()},
        default=grounded_fact(str(seed["claim_id"])),
    )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=f"owner-question-boundary-{case_no}",
        project_root=Path(__file__).resolve().parents[1],
        writer=_QuestionWriter(question),
        claim_reviewer=reviewer,
    )
    assert summary.evaluation_count == 9
    row = storage.conn.execute(
        "SELECT result,findings_json FROM content_draft_evaluations "
        "WHERE content_id=(SELECT id FROM content_items WHERE job_id=?) "
        "AND evaluation_type='UNSUPPORTED_CLAIMS' ORDER BY id DESC LIMIT 1",
        (request.job_id,),
    ).fetchone()
    assert row is not None
    assert row["result"] == "FAIL"
    findings = json.loads(row["findings_json"])
    audit = next(
        item
        for item in findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    claim = next(item for item in audit["claims"] if item["text"] == question)
    assert claim == {
        **{key: claim[key] for key in ("ordinal", "segment_id", "fingerprint", "text")},
        "classification": "EVIDENCE_GROUNDED_FACT",
        "evidence_ids": [],
        "reviewer_reason": (
            "reviewer found an external fact without supporting evidence"
        ),
        "reviewer_outcome": "BLOCK",
        "contains_external_fact": True,
        "reviewer_version": "fake_claim_accounting_reviewer_v2",
    }


@pytest.mark.parametrize(
    ("case_no", "question"),
    tuple(enumerate(MAJOR_QUESTION_MARKER_CASES, start=1)),
)
def test_full_offline_article_persists_exact_major_marker_block(
    storage, account, case_no, question,
):
    seed = seed_c2_research(
        storage, account, topic_title=f"Question marker repair {case_no}"
    )
    request, _, lease = prepare_and_claim(
        storage,
        seed,
        ContentType.ARTICLE,
        suffix=f"question-marker-repair-{case_no}",
    )
    reviewer = FakeClaimAccountingReviewer(
        profile={question: real_prose()},
        default=grounded_fact(str(seed["claim_id"])),
    )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=f"owner-question-marker-repair-{case_no}",
        project_root=Path(__file__).resolve().parents[1],
        writer=_QuestionWriter(question),
        claim_reviewer=reviewer,
    )
    assert summary.evaluation_count == 9
    row = storage.conn.execute(
        "SELECT result,findings_json FROM content_draft_evaluations "
        "WHERE content_id=(SELECT id FROM content_items WHERE job_id=?) "
        "AND evaluation_type='UNSUPPORTED_CLAIMS' ORDER BY id DESC LIMIT 1",
        (request.job_id,),
    ).fetchone()
    assert row is not None
    assert row["result"] == "FAIL"
    findings = json.loads(row["findings_json"])
    audit = next(
        item
        for item in findings
        if item.get("code") == "ARTICLE_CLAIM_ACCOUNTING_AUDIT"
    )
    claim = next(item for item in audit["claims"] if item["text"] == question)
    assert claim["classification"] == "NON_FACTUAL_PROSE"
    assert claim["contains_external_fact"] is False
    assert claim["evidence_ids"] == []
    assert claim["reviewer_outcome"] == "BLOCK"
    finding = next(
        item
        for item in findings
        if item.get("code") == NON_FACTUAL_CLASSIFICATION_INCONSISTENT
        and item.get("sentence") == question
    )
    assert finding["segment_id"] == claim["segment_id"]
    assert finding["segment_fingerprint"] == claim["fingerprint"]


def test_exactly_one_accounting_entry_exists_per_substantive_segment():
    body = "Gate assignment follows contractual priority. Why bother?"
    verdict = assess_draft(
        _draft(body),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(
            profile={"Why bother?": honest_inference()},
            default=grounded_fact(EVIDENCE_ID),
        ),
    )
    assert _claim_gate_passed(verdict)
    assert len(verdict.claim_accounting) == 2
    assert len({item["segment_id"] for item in verdict.claim_accounting}) == 2


def test_missing_extra_duplicate_and_identity_mismatch_all_block():
    sentence = "Who did it?"

    missing = assess_draft(
        _draft(sentence),
        _brief(),
        evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(omit_texts=(sentence,)),
    )
    assert CLAIM_ACCOUNTING_COVERAGE_MISSING in _codes(missing)

    class ExtraReviewer:
        reviewer_version = "fake-extra-v1"

        def review(self, *, draft, brief, evidence, segments):
            del draft, brief, evidence
            valid = grounded_fact(EVIDENCE_ID).bind(segments[0])
            extra = replace(valid, segment_id="sentence:extra")
            return (valid, extra)

    extra = assess_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
        claim_reviewer=ExtraReviewer(),
    )
    assert CLAIM_ACCOUNTING_COVERAGE_EXTRA in _codes(extra)

    class DuplicateReviewer(ExtraReviewer):
        reviewer_version = "fake-duplicate-v1"

        def review(self, *, draft, brief, evidence, segments):
            row = grounded_fact(EVIDENCE_ID).bind(segments[0])
            return (row, row)

    duplicate = assess_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
        claim_reviewer=DuplicateReviewer(),
    )
    assert CLAIM_ACCOUNTING_COVERAGE_DUPLICATE in _codes(duplicate)

    def mismatched(segment, _evidence_ids):
        return replace(
            grounded_fact(EVIDENCE_ID).bind(segment),
            segment_fingerprint="wrong-fingerprint",
        )

    mismatch = assess_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(decide=mismatched),
    )
    assert CLAIM_ACCOUNTING_IDENTITY_MISMATCH in _codes(mismatch)


def test_unknown_outside_evidence_and_absent_reviewer_all_block():
    sentence = "Where is it?"
    unknown = assess_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
        claim_reviewer=FakeClaimAccountingReviewer(),
    )
    assert CLAIM_CLASSIFICATION_UNKNOWN in _codes(unknown)

    outside = _assess(
        sentence,
        grounded_fact("research-card:999:confirmed-claim:0"),
    )
    assert FACTUAL_CLAIM_EVIDENCE_OUTSIDE_PACKAGE in _codes(outside)

    absent = assess_draft(
        _draft(sentence), _brief(), evidence=(_evidence(),),
    )
    assert CLAIM_ACCOUNTING_REVIEW_MISSING in _codes(absent)


def test_reviewer_cannot_clear_the_numeric_and_year_deterministic_floor():
    sentence = "How many beds were available in 2024?"
    verdict = _assess(sentence, grounded_fact(EVIDENCE_ID))
    assert not verdict.passed(QualityCheck.FACTUAL_CLAIM_SUPPORT)
    assert UNSUPPORTED_FACTUAL_CLAIM in _codes(verdict)
    assert verdict.claim_accounting[0]["reviewer_outcome"] == "PASS"


COUNTERPROBE_FACTUAL = (
    "Who signed the harbour lease?",
    "What caused the eastern pump to fail?",
    "Where are the reserve keys stored?",
    "When did the regulator issue the licence?",
    "Why does the clinic close on Fridays?",
    "Which contractor built the retaining wall?",
    "How did the operator allocate the slots?",
    "How many pumps feed the upper reservoir?",
    "How much fuel can the standby tank store?",
    "Did the inspector visit the site?",
    "Does the tariff include the service charge?",
    "Was the southern platform rebuilt?",
    "Were the records transferred off site?",
    "Has the authority published the schedule?",
    "Had the crew tested the alarm beforehand?",
    "May licensed trucks use the private road?",
    "Must the operator retain every receipt?",
    "Won't the old fuse trip under that load?",
    "The permit expired yesterday, didn't it?",
    "Could you tell me where the deed is kept?",
    "Who owns Meridian Water?",
    "Do freight trains use this siding?",
    "Whose signature appears on the order?",
    "Is the upper reservoir larger than the lower one?",
    "Is there a relief valve behind the panel?",
    "What is the unit's serial identity?",
    "Is the control room staffed?",
    "Where does the night shift assemble?",
    "When are the gates unlocked?",
    "How frequently are the filters replaced?",
)


COUNTERPROBE_NON_FACTUAL = (
    "Why settle for a hollow conclusion?",
    "What if the frame itself is wrong?",
    "Should dignity matter more than speed?",
    "Would a kinder rule be preferable?",
    "Who could object to a clearer ending?",
    "How ought we balance freedom and duty?",
    "Which value deserves priority?",
    "Where should empathy enter the argument?",
    "When is caution no longer a virtue?",
    "Could the image be less severe?",
    "Might another analogy serve us better?",
    "Does the conclusion feel earned?",
    "Is that really the lesson we want?",
    "Why not leave the tension unresolved?",
    "What would courage ask of us?",
    "Suppose nobody agreed; then what?",
    "Wouldn't restraint make the point sharper?",
    "Can an ending be both open and decisive?",
    "Who should get the final word?",
    "How might we phrase the dilemma more honestly?",
    "What deserves to remain uncertain?",
    "Is neatness always a virtue?",
    "Why demand a villain at all?",
    "Could ambiguity be the honest answer?",
    "Would the argument breathe better without that claim?",
)


COUNTERPROBE_QUESTIONS = COUNTERPROBE_FACTUAL + COUNTERPROBE_NON_FACTUAL

MARKER_SWEEP_PREFIXES = (
    "",
    "Now, ",
    "First, ",
    "Next, ",
    "Instead, ",
    "Meanwhile, ",
    "For now, ",
    "A step back, ",
)
MARKER_SWEEP_BODIES = (
    "what about the exclusion zone",
    "the capital of Australia",
    "the eastern inspection record",
)
MARKER_SWEEP_TERMINATORS = (
    "?",
    "?!",
    "??",
    "?.",
    "?;",
    "?...",
    '?"',
    "?)",
    "?]",
)


@pytest.mark.parametrize("sentence", COUNTERPROBE_QUESTIONS)
def test_counterprobe_finds_zero_questions_released_as_non_factual_prose(sentence):
    verdict = _assess(sentence, real_prose())
    assert not _claim_gate_passed(verdict)
    assert NON_FACTUAL_CLASSIFICATION_INCONSISTENT in _codes(verdict)


@pytest.mark.parametrize("sentence", COUNTERPROBE_NON_FACTUAL)
def test_counterprobe_non_factual_questions_retain_honest_inference(sentence):
    assert _claim_gate_passed(_assess(sentence, honest_inference()))


def test_counterprobe_cardinality_and_independence_from_main_matrices():
    assert len(COUNTERPROBE_QUESTIONS) >= 50
    assert len(set(COUNTERPROBE_QUESTIONS)) == len(COUNTERPROBE_QUESTIONS)
    assert not set(COUNTERPROBE_QUESTIONS) & set(FACTUAL_QUESTIONS)
    assert not set(COUNTERPROBE_QUESTIONS) & set(NON_FACTUAL_QUESTIONS)


def test_local_marker_combination_sweep_has_zero_non_factual_prose_leaks():
    cases = tuple(
        f"{prefix}{body}{terminator}"
        for prefix in MARKER_SWEEP_PREFIXES
        for body in MARKER_SWEEP_BODIES
        for terminator in MARKER_SWEEP_TERMINATORS
    )
    assert len(cases) == 216
    leaks = []
    for sentence in cases:
        verdict = _assess(sentence, real_prose())
        if (
            _claim_gate_passed(verdict)
            or NON_FACTUAL_CLASSIFICATION_INCONSISTENT not in _codes(verdict)
        ):
            leaks.append(sentence)
    assert leaks == []


def test_quality_gate_contains_no_question_semantic_heuristic_registry():
    source = Path(__file__).resolve().parents[1].joinpath(
        "app", "content", "quality_gate.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "_CONTENTLESS_QUESTION",
        "_is_contentless_question",
        "_QUESTION_BLACKLIST",
        "_QUESTION_WHITELIST",
        "_QUESTION_VOCABULARY",
        "_QUESTION_CONCRETE_REFERENT",
        "_QUESTION_PREDICATE",
    )
    assert not [name for name in forbidden if name in source]
    assert 'text.endswith("?")' not in source
