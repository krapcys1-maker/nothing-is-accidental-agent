"""Regression for the reviewer quality gate exposed by the first REVIEW-ONLY live.

The live run (job ``online-e2e-article-card-7-v5``, content 5, draft
``b6654bc2…``, provider request ``msg_011CdzjaaVLrFXzgNXijd79K``) returned
APPROVE on 29 body segments: 18 ARGUMENT_OR_INFERENCE, 4 EVIDENCE_GROUNDED_FACT,
7 NON_FACTUAL_PROSE, every one PASS.  The title was never a segment, one
inference carried an evidence id, and the whole-article question was never
asked.  These tests pin the exact problem classes so that shape can never pass
again, and one positive test keeps legitimate evidence-bound reasoning allowed.

Everything here is offline: no provider, no SDK, no network, no database.
"""
from __future__ import annotations

import json

import pytest

from app.content.contracts import FakeDraft
from app.content.quality_gate import (
    DocumentCheck,
    DocumentReview,
    SegmentKind,
    build_claim_segments,
)
from app.content.reviewer import (
    REVIEWER_VERSION,
    ProductionReviewerError,
    parse_reviewer_response,
)

# The live title promised bunching arithmetic; the body argued about metrics.
LIVE_TITLE = "Why the Bus Bunches: The Arithmetic That Makes Two Arrive Together"
LIVE_BODY = (
    "On a route that comes every few minutes, almost nobody consults the timetable. "
    "The metric cannot detect bunching, and cannot penalize it. "
    "Scoring rewards hurrying between timepoints and idling at them. "
    "Legal mandates, union rules and institutional inertia keep the measure in place. "
    "A late bus makes riders miss a transfer and then an appointment. "
    "Headway control can hold a punctual operator behind a slower one."
)

EVIDENCE_ID = "research-card:7:confirmed-claim:0"


def _draft(*, title: str = LIVE_TITLE, body: str = LIVE_BODY) -> FakeDraft:
    return FakeDraft(
        attempt_no=1,
        route_key="article:opus",
        title=title,
        body=body,
        evidence_ids_used=(EVIDENCE_ID,),
        unsupported_claims=(),
        personal_experience=False,
        style_ok=True,
        brief_compliant=True,
    )


def _checks(**overrides: bool) -> dict[str, bool]:
    checks = {check.value: True for check in DocumentCheck}
    checks.update(overrides)
    return checks


def _entry(segment, *, classification="ARGUMENT_OR_INFERENCE", evidence_ids=(),
           outcome="PASS", external=False, reason="reasoning over frozen material"):
    return {
        "segment_id": segment.segment_id,
        "segment_fingerprint": segment.fingerprint,
        "classification": classification,
        "evidence_ids": list(evidence_ids),
        "reason": reason,
        "outcome": outcome,
        "contains_external_fact": external,
    }


def _response(segments, *, entries=None, checks=None, findings=None):
    document_checks = _checks() if checks is None else checks
    if findings is None:
        findings = [] if all(document_checks.values()) else ["fix the article"]
    return json.dumps({
        "reviewer_version": REVIEWER_VERSION,
        "entries": entries if entries is not None else [_entry(s) for s in segments],
        "document_review": {"checks": document_checks, "findings": findings},
    })


# --- coverage: the title is now reviewed -----------------------------------

def test_title_is_a_reviewable_segment_alongside_every_body_sentence():
    segments = build_claim_segments(_draft())
    kinds = [segment.kind for segment in segments]
    assert kinds[0] is SegmentKind.TITLE
    assert segments[0].text == LIVE_TITLE
    assert kinds.count(SegmentKind.TITLE) == 1
    assert all(kind is SegmentKind.BODY for kind in kinds[1:])
    # The live surface covered body sentences only; it is now strictly larger.
    assert len(segments) == len(kinds) and len(segments) > 1
    assert segments[0].segment_id.startswith("title:0:")


def test_segment_kind_is_part_of_identity_so_a_title_cannot_pose_as_a_sentence():
    segments = build_claim_segments(_draft())
    title = segments[0]
    same_text_body = build_claim_segments(_draft(title="x", body=LIVE_TITLE))[1]
    assert title.text == same_text_body.text
    assert title.fingerprint != same_text_body.fingerprint


# --- the exact live shape can no longer pass -------------------------------

def test_live_all_pass_response_without_document_review_is_now_refused():
    """The exact v2 payload shape from the live run is now a contract error."""
    segments = build_claim_segments(_draft())
    legacy = json.dumps({
        "reviewer_version": REVIEWER_VERSION,
        "entries": [_entry(segment) for segment in segments],
    })
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(legacy, segments=segments)
    assert exc.value.code == "REVIEWER_RESPONSE_CONTRACT_INVALID"


def test_live_cited_inference_is_refused_by_the_parser():
    """Live returned one ARGUMENT_OR_INFERENCE carrying an evidence id."""
    segments = build_claim_segments(_draft())
    entries = [_entry(segment) for segment in segments]
    entries[1] = _entry(
        segments[1], classification="ARGUMENT_OR_INFERENCE",
        evidence_ids=[EVIDENCE_ID],
    )
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(
            _response(segments, entries=entries),
            segments=segments, allowed_evidence_ids=frozenset({EVIDENCE_ID}),
        )
    assert exc.value.code == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"


def test_non_factual_prose_and_grounded_fact_cardinality_are_both_enforced():
    segments = build_claim_segments(_draft())
    cited_prose = [_entry(s) for s in segments]
    cited_prose[2] = _entry(
        segments[2], classification="NON_FACTUAL_PROSE", evidence_ids=[EVIDENCE_ID],
    )
    with pytest.raises(ProductionReviewerError) as prose:
        parse_reviewer_response(
            _response(segments, entries=cited_prose), segments=segments,
            allowed_evidence_ids=frozenset({EVIDENCE_ID}),
        )
    assert prose.value.code == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"

    uncited_fact = [_entry(s) for s in segments]
    uncited_fact[2] = _entry(
        segments[2], classification="EVIDENCE_GROUNDED_FACT", evidence_ids=[],
    )
    with pytest.raises(ProductionReviewerError) as fact:
        parse_reviewer_response(
            _response(segments, entries=uncited_fact), segments=segments,
        )
    assert fact.value.code == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"


# --- the whole-article gate -------------------------------------------------

@pytest.mark.parametrize("failed", [check for check in DocumentCheck])
def test_any_failed_document_check_blocks_approval(failed):
    segments = build_claim_segments(_draft())
    _, review = parse_reviewer_response(
        _response(segments, checks=_checks(**{failed.value: False}),
                  findings=["explain the bunching arithmetic the title promises"]),
        segments=segments,
    )
    assert review.approved is False
    assert failed in review.failed_checks


def test_live_title_body_mismatch_is_expressible_and_fails_the_gate():
    """The live failure mode: vivid title, different unexplained mechanism."""
    segments = build_claim_segments(_draft())
    _, review = parse_reviewer_response(
        _response(
            segments,
            checks=_checks(
                TITLE_PROMISE_FULFILLED=False, TITLE_MECHANISM_EXPLAINED=False,
            ),
            findings=[
                "Title promises bunching arithmetic; body only argues metric flaws.",
                "Either explain how two buses converge or retitle to the metric claim.",
            ],
        ),
        segments=segments,
    )
    assert review.approved is False
    assert set(review.failed_checks) == {
        DocumentCheck.TITLE_PROMISE_FULFILLED,
        DocumentCheck.TITLE_MECHANISM_EXPLAINED,
    }
    assert len(review.findings) == 2


def test_failed_check_without_instruction_and_clean_check_with_findings_are_errors():
    segments = build_claim_segments(_draft())
    with pytest.raises(ProductionReviewerError) as silent:
        parse_reviewer_response(
            _response(segments, checks=_checks(THESIS_CONSISTENT=False), findings=[]),
            segments=segments,
        )
    assert silent.value.code == "REVIEWER_DOCUMENT_REVIEW_MALFORMED"
    with pytest.raises(ProductionReviewerError) as noisy:
        parse_reviewer_response(
            _response(segments, checks=_checks(), findings=["nothing is wrong"]),
            segments=segments,
        )
    assert noisy.value.code == "REVIEWER_DOCUMENT_REVIEW_MALFORMED"


@pytest.mark.parametrize("document_review", [
    {"checks": {}, "findings": []},
    {"checks": {check.value: True for check in DocumentCheck}},
    {"checks": {check.value: "yes" for check in DocumentCheck}, "findings": []},
    {"checks": {check.value: True for check in DocumentCheck},
     "findings": [""], "extra": 1},
])
def test_malformed_document_review_is_never_a_quiet_pass(document_review):
    segments = build_claim_segments(_draft())
    payload = json.dumps({
        "reviewer_version": REVIEWER_VERSION,
        "entries": [_entry(segment) for segment in segments],
        "document_review": document_review,
    })
    with pytest.raises(ProductionReviewerError):
        parse_reviewer_response(payload, segments=segments)


# --- the reviewer must still allow a correct article ------------------------

def test_legitimate_evidence_bound_reasoning_is_not_blocked():
    """A clean article: grounded facts cite, inferences reason, title matches."""
    draft = _draft(
        title="What On-Time Performance Misses at Unscheduled Stops",
        body=(
            "The agency reports on-time performance above 93 percent. "
            "That figure is measured only at designated timepoints. "
            "So a stop outside the timepoint set can be missed by the report entirely. "
            "Now consider what that means for the rider."
        ),
    )
    segments = build_claim_segments(draft)
    entries = [
        _entry(segments[0], classification="ARGUMENT_OR_INFERENCE",
               reason="title states the article's actual subject"),
        _entry(segments[1], classification="EVIDENCE_GROUNDED_FACT",
               evidence_ids=[EVIDENCE_ID], external=True,
               reason="reported figure is in evidence"),
        _entry(segments[2], classification="EVIDENCE_GROUNDED_FACT",
               evidence_ids=[EVIDENCE_ID], external=True,
               reason="measurement basis is in evidence"),
        _entry(segments[3], classification="ARGUMENT_OR_INFERENCE",
               reason="conclusion follows from the two grounded facts"),
        _entry(segments[4], classification="NON_FACTUAL_PROSE",
               reason="transition asserting nothing factual"),
    ]
    parsed, review = parse_reviewer_response(
        _response(segments, entries=entries), segments=segments,
        allowed_evidence_ids=frozenset({EVIDENCE_ID}),
    )
    assert len(parsed) == len(segments)
    assert review.approved is True
    assert review.findings == ()
    assert all(entry.outcome.value == "PASS" for entry in parsed)


# --- decision semantics -----------------------------------------------------

def test_document_review_payload_reports_failures_for_the_rewrite():
    review = DocumentReview(
        checks={check: check is not DocumentCheck.BRIEF_QUESTION_ANSWERED
                for check in DocumentCheck},
        findings=("answer the brief's question directly",),
    )
    payload = review.payload()
    assert payload["approved"] is False
    assert payload["failed_checks"] == [DocumentCheck.BRIEF_QUESTION_ANSWERED.value]
    assert payload["findings"] == ["answer the brief's question directly"]


def test_document_gate_failure_drives_exactly_one_rewrite_then_post_review(
    storage, settings, account,
):
    """All segments PASS but the article fails: exactly one canonical rewrite.

    This is the live shape — every sentence individually defensible — and it
    must no longer reach APPROVE.
    """
    import json as _json

    from app.content.review_only import run_controlled_article_review_only
    from app.core.clock import FixedClock
    from tests.test_pr46_review_only_resume import (
        NOW, ROOT, WriterTransport, _authority, _failed_article, _sdk_factory,
    )
    from dataclasses import replace
    from app.llm.anthropic_controlled_adapter import ControlledProviderRawResponse

    class _TitleMismatchReviewer:
        """Every segment passes; the whole article does not."""

        def __init__(self) -> None:
            self.calls = 0
            self.seen_prompts: list[dict] = []

        def __call__(self, _client, request):
            self.calls += 1
            payload = _json.loads(request.user_prompt)
            self.seen_prompts.append(payload)
            entries = [
                {
                    "segment_id": segment["segment_id"],
                    "segment_fingerprint": segment["fingerprint"],
                    "classification": "ARGUMENT_OR_INFERENCE",
                    "evidence_ids": [],
                    "reason": "reasoning over frozen material",
                    "outcome": "PASS",
                    "contains_external_fact": False,
                }
                for segment in payload["draft_segments"]
            ]
            # Only the first review fails the document gate; the rewrite fixes it.
            failing = self.calls == 1
            checks = _checks(
                TITLE_PROMISE_FULFILLED=not failing,
                TITLE_MECHANISM_EXPLAINED=not failing,
            )
            findings = (
                ["Title promises an arithmetic the body never explains."]
                if failing else []
            )
            return ControlledProviderRawResponse(
                returned_model_id="claude-opus-5",
                text=_json.dumps({
                    "reviewer_version": REVIEWER_VERSION,
                    "entries": entries,
                    "document_review": {"checks": checks, "findings": findings},
                }),
                input_tokens=900, output_tokens=400, cache_read_tokens=0,
                cache_write_tokens=0, web_search_requests=0,
                stop_reason="end_turn",
                provider_request_id=f"fake-doc-gate-{self.calls}",
            )

    state = _failed_article(storage, settings, account, job="doc-gate-rewrite")
    authority = _authority(state, suffix="doc-gate")
    initial = _TitleMismatchReviewer()
    writer = WriterTransport()
    post = _TitleMismatchReviewer()
    post.calls = 1  # the post-rewrite verdict is clean

    result = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority, api_key_provider=lambda: "fake",
        initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )

    # Exactly one rewrite: reviewer 1, writer 2, reviewer 2 — and no third round.
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 2)
    assert result.writer_attempt_no == 2
    assert result.review_no == 2
    assert result.writer_attempts == 2

    first = storage.conn.execute(
        "SELECT result_json FROM content_review_resume_executions WHERE review_no=1",
    ).fetchone()
    decision = _json.loads(str(first["result_json"]))
    assert decision["decision"] == "REWRITE_ONCE"
    assert decision["document_review"]["approved"] is False
    assert all(
        entry["outcome"] == "PASS" for entry in decision["entries"]
    ), "the live shape: every segment passes, the article still does not"

    # The writer received the whole-article instruction, not only segment notes.
    intent = _json.loads(str(storage.get_content_pipeline_state(
        authority.job_id,
    )["intents"][1]["intent_json"]))
    document_feedback = [
        item for item in intent["rewrite_feedback"] if item.get("scope") == "DOCUMENT"
    ]
    assert len(document_feedback) == 1
    assert document_feedback[0]["failed_checks"] == [
        DocumentCheck.TITLE_PROMISE_FULFILLED.value,
        DocumentCheck.TITLE_MECHANISM_EXPLAINED.value,
    ]
    assert document_feedback[0]["instructions"]


def test_output_budget_has_headroom_for_the_expanded_contract():
    """The live response used 4358 of 8192 output tokens on 29 body segments.

    The v3 surface adds one title segment and one document_review object.  A
    conservative 3.5-characters-per-token estimate over a deliberately verbose
    response must still leave clear headroom.
    """
    segments = build_claim_segments(_draft())
    verbose = [
        _entry(segment, reason="a deliberately long reviewer justification " * 3)
        for segment in segments
    ]
    response = _response(
        segments, entries=verbose,
        checks=_checks(TITLE_MECHANISM_EXPLAINED=False),
        findings=["explain the bunching arithmetic the title promises " * 3],
    )
    per_segment = len(response) / max(len(segments), 1)
    projected_chars = per_segment * 30 + 1200  # 29 live segments + title + verdict
    assert projected_chars / 3.5 < 8192 * 0.75
