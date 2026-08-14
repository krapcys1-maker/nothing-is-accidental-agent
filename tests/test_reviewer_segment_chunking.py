"""A long article's claim accounting is split across several paid reviewer calls.

The reviewer's output ceiling is 8192 tokens and cannot be raised without a new
paid qualification.  Its answer scales with the number of SEGMENTS, so a long
draft truncates mid-JSON, the whole paid review is discarded, and because
``content_frozen_inputs.input_sha256`` is globally unique the research card
behind it can never be retried.  These tests pin the split that removes that
failure mode, and pin that it changes nothing at all below the threshold.

Every provider effect stops at a fake FINAL transport.  The entrypoint, the
pipeline, the writer, the reviewer, the storage floor and the cost accounting
are the production ones.
"""
from __future__ import annotations

from decimal import Decimal
import json

import pytest

from app.content.quality_gate import DocumentCheck, DraftClaimSegment
from app.content.reviewer import (
    ProductionArticleReviewer,
    ProductionReviewerError,
    REVIEWER_MAX_CHUNKS,
    REVIEWER_MAX_SEGMENTS_PER_CALL,
    REVIEWER_VERSION,
    ReviewerRequestIntent,
    accounted_segments_fingerprint,
    parse_reviewer_response,
    plan_review_chunks,
)
from app.llm.anthropic_controlled_adapter import ControlledProviderRawResponse
from app.model_routing.contracts import LogicalModelRole
from app.storage.repositories import ContentFoundationError
from tests.test_b3_production_reviewer import (
    OPUS,
    WriterTransport,
    _run,
    _sdk_factory,
)

# One chunk short of the threshold and one chunk over it, so the split is the
# only thing that differs between the two production runs below.
SHORT_BODY_SENTENCES = 30
LONG_BODY_SENTENCES = 55


def _segment(ordinal: int) -> DraftClaimSegment:
    return DraftClaimSegment(
        ordinal=ordinal,
        segment_id=f"sentence:{ordinal}:{ordinal:016d}",
        fingerprint=f"{ordinal:064d}",
        text=f"Sentence {ordinal}.",
    )


def _segments(count: int) -> tuple[DraftClaimSegment, ...]:
    return tuple(_segment(index) for index in range(count))


# ------------------------------------------------------------ the plan ------

def test_a_draft_at_the_threshold_is_still_one_call():
    assert REVIEWER_MAX_SEGMENTS_PER_CALL == 48
    for count in (0, 1, 12, 47, 48):
        chunks = plan_review_chunks(_segments(count))
        assert len(chunks) == 1
        assert chunks[0] == _segments(count)


def test_crossing_the_threshold_splits_into_balanced_chunks():
    for count, expected in (
        (49, [25, 24]),
        (64, [32, 32]),
        (96, [48, 48]),
        (97, [33, 32, 32]),
        (192, [48, 48, 48, 48]),
    ):
        chunks = plan_review_chunks(_segments(count))
        assert [len(chunk) for chunk in chunks] == expected
        # A partition: reading order preserved, every segment exactly once.
        flattened = tuple(
            segment for chunk in chunks for segment in chunk
        )
        assert flattened == _segments(count)
        assert max(len(chunk) for chunk in chunks) <= REVIEWER_MAX_SEGMENTS_PER_CALL


def test_a_draft_needing_more_than_four_calls_is_refused_before_any_spend():
    with pytest.raises(ProductionReviewerError) as exc:
        plan_review_chunks(_segments(REVIEWER_MAX_SEGMENTS_PER_CALL * REVIEWER_MAX_CHUNKS + 1))
    assert exc.value.code == "REVIEWER_SEGMENT_COUNT_UNSUPPORTED"
    assert "No provider call was made." in exc.value.detail


# ------------------------------------------------------- the contract ------

def _entry(segment: DraftClaimSegment) -> dict:
    return {
        "segment_id": segment.segment_id,
        "segment_fingerprint": segment.fingerprint[:16],
        "classification": "ARGUMENT_OR_INFERENCE",
        "reason": "reasoning drawn from the supplied package",
        "outcome": "PASS",
    }


def test_a_continuation_chunk_must_not_restate_the_whole_article_verdict():
    segments = _segments(3)
    clean = {
        "reviewer_version": REVIEWER_VERSION,
        "entries": [_entry(segment) for segment in segments],
    }
    entries, document = parse_reviewer_response(
        json.dumps(clean), segments=segments, expect_document_review=False,
    )
    assert len(entries) == 3
    assert document is None, "only the first chunk owns the whole-article verdict"

    restated = {
        **clean,
        "document_review": {
            "checks": {check.value: True for check in DocumentCheck},
            "findings": [],
        },
    }
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(
            json.dumps(restated), segments=segments, expect_document_review=False,
        )
    assert exc.value.code == "REVIEWER_RESPONSE_CONTRACT_INVALID"


def test_the_first_chunk_must_carry_the_whole_article_verdict():
    segments = _segments(3)
    without = {
        "reviewer_version": REVIEWER_VERSION,
        "entries": [_entry(segment) for segment in segments],
    }
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(json.dumps(without), segments=segments)
    assert exc.value.code == "REVIEWER_RESPONSE_CONTRACT_INVALID"


def test_a_chunk_answering_about_a_segment_it_was_not_given_is_refused():
    segments = _segments(4)
    chunk = segments[:2]
    payload = {
        "reviewer_version": REVIEWER_VERSION,
        "entries": [_entry(segment) for segment in segments[:3]],
    }
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(
            json.dumps(payload), segments=chunk, expect_document_review=False,
        )
    assert exc.value.code == "REVIEWER_ENTRY_UNKNOWN_SEGMENT"


# ------------------------------------------------------ the transports ------

_FILLER = (
    "and the same decision path keeps shaping the ordinary result for the "
    "people who rarely notice it happening at all"
).split()


def _pad_to_words(sentences: list[str], target_words: int) -> list[str]:
    """Hold the article length fixed while the sentence count varies.

    That is the whole experiment: the reviewer's answer is bounded by how many
    segments it must account for, not by how many words it read.
    """
    padded = [sentence.rstrip(".").split() for sentence in sentences]
    index = 0
    while sum(len(words) for words in padded) < target_words:
        padded[index % len(padded)].append(_FILLER[index % len(_FILLER)])
        index += 1
    return [" ".join(words) + "." for words in padded]


class LongWriterTransport(WriterTransport):
    """A production-shaped draft whose SENTENCE count is the variable.

    The word count stays inside the ARTICLE window (900-1200) in both shapes,
    which is the whole point: what overruns the reviewer's output ceiling is how
    many segments it must account for, not how long the article is.
    """

    def __init__(self, *, sentences: int, model_id: str = OPUS) -> None:
        super().__init__(model_id=model_id)
        self.sentences = sentences

    def __call__(self, _client, request):
        self.calls += 1
        prompt = json.loads(request.user_prompt)
        brief = prompt["brief"]
        evidence = prompt["confirmed_claims_and_allowed_evidence"]
        lines = [
            f"A small visible outcome raises a larger question: "
            f"{brief['answer_question'].rstrip('?')}",
            f"The durable research card points to this thesis: "
            f"{brief['central_thesis']}",
        ]
        while len(lines) < self.sentences - 2:
            fact = evidence[len(lines) % len(evidence)]["claim_text"].replace(".", "")
            lines.append(
                f"Frozen evidence supports a bounded part of the mechanism: {fact}"
            )
        lines.append(
            f"A serious limit remains: {brief['counterargument_or_limitation']}"
        )
        lines.append(
            "Seen this way, the ordinary result is not accidental, but the "
            "visible edge of a system of incentives, constraints and prior choices"
        )
        assert len(lines) == self.sentences
        draft = {
            "title": brief["working_title"],
            "body": "\n\n".join(_pad_to_words(lines, 1000)),
            "evidence_ids_used": [
                row["confirmed_claim_id"] for row in evidence
            ],
            "unsupported_claims": [],
            "personal_experience": False,
            "style_ok": True,
            "brief_compliant": True,
        }
        return ControlledProviderRawResponse(
            returned_model_id=self.model_id,
            text=json.dumps(draft),
            input_tokens=1200,
            output_tokens=800,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            stop_reason="end_turn",
            provider_request_id=f"fake-writer-{self.calls}",
        )


class ChunkAwareReviewerTransport:
    """Answers exactly what each request asks for, and nothing more.

    It refuses to invent entries for segments it was not asked to account for,
    which is what makes the coverage assertions below meaningful.
    """

    def __init__(
        self,
        *,
        model_id: str = OPUS,
        fail_on_call: int | None = None,
        raise_on_call: int | None = None,
        failure_text: str = "truncated {\"entries\": [",
    ) -> None:
        self.calls = 0
        self.model_id = model_id
        self.fail_on_call = fail_on_call
        self.raise_on_call = raise_on_call
        self.failure_text = failure_text
        self.prompts: list[dict] = []

    def __call__(self, _client, request):
        self.calls += 1
        payload = json.loads(request.user_prompt)
        self.prompts.append(payload)
        if self.raise_on_call == self.calls:
            raise TimeoutError("chunk result unknown")
        by_id = {
            segment["segment_id"]: segment
            for segment in payload["draft_segments"]
        }
        requested = payload.get("account_for_segment_ids")
        targets = (
            [by_id[segment_id] for segment_id in requested]
            if requested is not None else payload["draft_segments"]
        )
        body = {
            "reviewer_version": REVIEWER_VERSION,
            "entries": [
                {
                    "segment_id": segment["segment_id"],
                    "segment_fingerprint": segment["fingerprint"][:16],
                    "classification": "ARGUMENT_OR_INFERENCE",
                    "reason": "reasoning drawn from the supplied package",
                    "outcome": "PASS",
                }
                for segment in targets
            ],
        }
        chunk_no = int(
            payload["contract"].get("review_chunk", {}).get("chunk_no", 1)
        )
        if chunk_no == 1:
            body["document_review"] = {
                "checks": {check.value: True for check in DocumentCheck},
                "findings": [],
            }
        text = self.failure_text if self.fail_on_call == self.calls else json.dumps(body)
        return ControlledProviderRawResponse(
            returned_model_id=self.model_id,
            text=text,
            input_tokens=900,
            output_tokens=400,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            stop_reason="end_turn",
            provider_request_id=f"fake-reviewer-{self.calls}",
        )


def _umbrella(storage, job_id: str) -> dict:
    row = storage.conn.execute(
        "SELECT * FROM role_provider_executions WHERE job_id=? "
        "AND logical_role='ARTICLE_REVIEWER'", (job_id,),
    ).fetchone()
    return None if row is None else dict(row)


def _chunks(storage, job_id: str) -> list[dict]:
    return [dict(row) for row in storage.conn.execute(
        "SELECT * FROM content_review_chunk_executions WHERE job_id=? "
        "ORDER BY chunk_no", (job_id,),
    ).fetchall()]


def _words(storage, job_id: str) -> int:
    body = storage.conn.execute(
        "SELECT body FROM content_items WHERE job_id=?", (job_id,),
    ).fetchone()["body"]
    return len(str(body).split())


# --------------------------------------------------- below the threshold ----

def test_a_short_draft_makes_one_call_and_writes_no_chunk_rows(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-short",
        writer=LongWriterTransport(sentences=SHORT_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    payload = json.loads(umbrella["result_json"])["payload"]
    assert reviewer.calls == 1
    assert _chunks(storage, outcome.job_id) == []
    assert umbrella["outcome"] == "SUCCESS"
    # 900 in @5/MTok + 400 out @25/MTok, exactly as an unsplit review always was.
    assert umbrella["cost_usd"] == "0.014500"
    assert "chunked_review" not in payload
    assert "account_for_segment_ids" not in reviewer.prompts[0]
    assert 900 <= _words(storage, outcome.job_id) <= 1200


# --------------------------------------------------- above the threshold ----

def test_a_long_draft_splits_into_two_separately_reserved_paid_calls(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-long",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    chunks = _chunks(storage, outcome.job_id)
    content_id = int(storage.get_content_row_for_job(
        job_id=outcome.job_id,
    )["id"])

    # The article is no longer than the short one; it merely has more sentences.
    assert 900 <= _words(storage, outcome.job_id) <= 1200
    assert reviewer.calls == 2
    assert len(chunks) == 2

    for index, chunk in enumerate(chunks, start=1):
        assert chunk["chunk_execution_ref"] == (
            f"{umbrella['execution_ref']}:chunk:{index}/2"
        )
        assert chunk["parent_execution_ref"] == umbrella["execution_ref"]
        assert chunk["chunk_no"] == index and chunk["chunk_count"] == 2
        assert chunk["content_id"] == content_id
        assert chunk["attempt_no"] == umbrella["attempt_no"]
        # Its own reservation, its own external-effect stamp, its own
        # settlement -- reserved before the call, settled after it.
        assert chunk["reserved_cost_usd"] == "0.323840"
        assert chunk["reserved_at"] <= chunk["external_effect_started_at"]
        assert chunk["external_effect_started_at"] <= chunk["settled_at"]
        assert chunk["outcome"] == "SUCCESS"
        assert chunk["cost_usd"] == "0.014500"
        assert chunk["returned_model_id"] == OPUS
        assert chunk["requests_document_review"] == (1 if index == 1 else 0)

    assert [chunk["prompt_fingerprint"] for chunk in chunks][0] != (
        chunks[1]["prompt_fingerprint"]
    )
    assert storage.list_content_review_chunk_executions(
        content_id=content_id, attempt_no=int(umbrella["attempt_no"]),
    ) == tuple(chunks)


def test_the_whole_article_and_evidence_go_in_every_chunk(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _run(
        storage, settings, account, job="chunk-context",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    first, second = reviewer.prompts
    assert first["draft_segments"] == second["draft_segments"]
    assert first["allowed_evidence"] == second["allowed_evidence"]
    assert first["brief"] == second["brief"]
    assert first["allowed_evidence"], "the evidence package is not empty"

    # Only the accounting list narrows, and it partitions the whole surface.
    accounted = first["account_for_segment_ids"] + second["account_for_segment_ids"]
    assert accounted == [
        segment["segment_id"] for segment in first["draft_segments"]
    ]
    assert len(set(accounted)) == len(accounted)


def test_the_whole_article_verdict_is_asked_for_in_the_first_chunk_only(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-document",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    first, second = reviewer.prompts
    assert first["contract"]["review_chunk"]["chunk_no"] == 1
    assert second["contract"]["review_chunk"]["chunk_no"] == 2
    assert first["required_output"]["document_review"].startswith("object with")
    assert second["required_output"]["document_review"].startswith("OMIT")

    payload = json.loads(_umbrella(storage, outcome.job_id)["result_json"])["payload"]
    document = payload["document_review"]
    assert document["approved"] is True
    assert document["failed_checks"] == [] and document["findings"] == []
    assert payload["decision"] == "APPROVE"


def test_coverage_is_complete_across_the_chunks_combined(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-coverage",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    payload = json.loads(_umbrella(storage, outcome.job_id)["result_json"])["payload"]
    supplied = [
        segment["segment_id"] for segment in reviewer.prompts[0]["draft_segments"]
    ]
    accounted = [entry["segment_id"] for entry in payload["entries"]]

    assert len(supplied) > REVIEWER_MAX_SEGMENTS_PER_CALL
    assert accounted == supplied, "one entry per segment, in reading order"
    assert payload["entry_count"] == len(supplied)
    assert payload["chunked_review"]["chunk_count"] == 2
    assert payload["chunked_review"]["completed_chunks"] == 2
    assert payload["chunked_review"]["failed_chunk_no"] is None
    assert [chunk["entry_count"] for chunk in payload["chunked_review"]["chunks"]] == [
        len(reviewer.prompts[0]["account_for_segment_ids"]),
        len(reviewer.prompts[1]["account_for_segment_ids"]),
    ]
    # The quality gate is what consumes this, and it demands one accounting
    # entry per segment across the whole draft.
    assessment = state["evaluations"]
    assert assessment, "the split review still reached the quality gate"
    assert state["content"]["status"] == "PENDING_APPROVAL"


def test_the_summed_usage_is_settled_once_and_never_double_counted(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-usage",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    state = storage.get_content_pipeline_state(outcome.job_id)
    ledger = [dict(row) for row in storage.conn.execute(
        "SELECT task,estimated_cost_usd,request_id FROM model_usage "
        "WHERE run_id=? ORDER BY id", (state["content"]["run_id"],),
    ).fetchall()]

    assert umbrella["input_tokens"] == 1800 and umbrella["output_tokens"] == 800
    assert umbrella["cost_usd"] == "0.029000"
    # Exactly one reviewer row in the shared usage ledger, carrying the sum.
    assert [row["task"] for row in ledger] == ["content_draft", "article_reviewer"]
    assert [row["request_id"] for row in ledger][-1] == umbrella["execution_ref"]
    assert Decimal(str(ledger[-1]["estimated_cost_usd"])) == Decimal("0.029000")
    assert Decimal(str(storage.get_run(state["content"]["run_id"]).cost_usd)) == sum(
        Decimal(str(row["estimated_cost_usd"])) for row in ledger
    )


# ------------------------------------------------------------- the cost -----

def test_the_whole_plan_is_reserved_before_the_first_chunk_is_paid_for(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-ceiling",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    chunks = _chunks(storage, outcome.job_id)
    # 23808 in @5/MTok + 8192 out @25/MTok = 0.323840 per call, twice.
    assert umbrella["reserved_cost_usd"] == "0.647680"
    assert sum(Decimal(chunk["cost_usd"]) for chunk in chunks) <= Decimal(
        umbrella["reserved_cost_usd"]
    )
    assert Decimal(umbrella["cost_usd"]) == sum(
        Decimal(chunk["cost_usd"]) for chunk in chunks
    )
    cap = Decimal(storage.conn.execute(
        "SELECT cap_usd FROM content_provider_approvals WHERE job_id=?",
        (outcome.job_id,),
    ).fetchone()["cap_usd"])
    settled = sum(
        (Decimal(row["cost_usd"]) for row in storage.conn.execute(
            "SELECT cost_usd FROM content_provider_cost_settlements WHERE job_id=?",
            (outcome.job_id,),
        ).fetchall()),
        Decimal("0"),
    )
    assert settled + Decimal(umbrella["cost_usd"]) <= cap
    assert storage.remaining_article_budget(job_id=outcome.job_id) == (
        cap - settled - Decimal(umbrella["cost_usd"])
    )


def test_a_job_that_cannot_afford_every_chunk_makes_zero_calls(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    # One reviewer call fits inside this cap; two do not.  The refusal must
    # land before the first chunk is paid for, not between the chunks.
    _, outcome = _run(
        storage, settings, account, job="chunk-unaffordable",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="0.400000",
    )
    assert reviewer.calls == 0, "PROVIDER CALL COUNT MUST BE 0"
    assert _umbrella(storage, outcome.job_id) is None
    assert _chunks(storage, outcome.job_id) == []


def test_the_chunk_ledger_refuses_to_spend_past_the_umbrella_envelope(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="chunk-envelope",
        writer=LongWriterTransport(sentences=SHORT_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    # The umbrella of that run is settled, so a chunk cannot attach to it at
    # all -- the durable floor refuses a chunk without a live reservation.
    with pytest.raises(ContentFoundationError) as exc:
        storage.begin_content_review_chunk_execution(
            chunk_execution_ref="forged:chunk:1/2",
            parent_execution_ref=umbrella["execution_ref"],
            job_id=outcome.job_id,
            run_id=str(umbrella["run_id"]),
            content_id=int(umbrella["content_id"]),
            attempt_no=int(umbrella["attempt_no"]),
            chunk_no=1,
            chunk_count=2,
            segment_count=4,
            accounted_segments_fingerprint="a" * 64,
            prompt_fingerprint="b" * 64,
            requests_document_review=True,
            reserved_cost_usd="0.323840",
            provider="ANTHROPIC",
            technical_model_id=OPUS,
        )
    assert exc.value.code == "CONTENT_REVIEW_CHUNK_PARENT_NOT_IN_FLIGHT"


# ---------------------------------------------------------- one chunk fails --

def test_a_failing_second_chunk_fails_the_whole_review(
    storage, settings, account,
):
    """No partial review is ever passed on: the whole review fails, once."""
    reviewer = ChunkAwareReviewerTransport(fail_on_call=2)
    _, outcome = _run(
        storage, settings, account, job="chunk-failure",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    chunks = _chunks(storage, outcome.job_id)
    state = storage.get_content_pipeline_state(outcome.job_id)
    payload = json.loads(umbrella["result_json"])["payload"]

    assert reviewer.calls == 2, "the failure is terminal; there is no retry"
    assert [chunk["outcome"] for chunk in chunks] == ["SUCCESS", "FAILURE"]
    assert chunks[1]["failure_kind"] == "REVIEWER_RESPONSE_NOT_JSON"
    assert chunks[0]["cost_usd"] == "0.014500", "the paid first chunk is recorded"

    assert umbrella["outcome"] == "FAILURE"
    assert umbrella["failure_kind"] == "REVIEWER_RESPONSE_NOT_JSON"
    # Both calls were paid for, so both are priced into the one settlement.
    assert umbrella["cost_usd"] == "0.029000"
    assert "entries" not in payload, "no partial accounting is ever stored"
    assert "decision" not in payload, "a failed review decides nothing"
    assert payload["chunked_review"]["failed_chunk_no"] == 2
    assert payload["chunked_review"]["completed_chunks"] == 1

    # The gate saw a failed review, not a passing one.
    assert state["content"]["status"] != "PENDING_APPROVAL"
    findings = {
        finding["code"]
        for evaluation in state["evaluations"]
        for finding in json.loads(str(evaluation["findings_json"]))
        if isinstance(finding, dict) and "code" in finding
    }
    assert "CLAIM_ACCOUNTING_REVIEW_FAILED" in findings


def test_an_unknown_second_chunk_leaves_the_review_cost_unknown(
    storage, settings, account,
):
    reviewer = ChunkAwareReviewerTransport(raise_on_call=2)
    _, outcome = _run(
        storage, settings, account, job="chunk-unknown",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    chunks = _chunks(storage, outcome.job_id)
    payload = json.loads(umbrella["result_json"])["payload"]

    assert [chunk["outcome"] for chunk in chunks] == ["SUCCESS", "NEEDS_VERIFICATION"]
    assert chunks[1]["failure_kind"] == "REVIEWER_RESULT_UNKNOWN"
    assert chunks[1]["cost_usd"] is None
    assert chunks[1]["external_effect_started_at"] is not None

    # One chunk's cost is unknown, so the review's cost is unknown.  What IS
    # known stays visible for the operator without being asserted as the total.
    assert umbrella["outcome"] == "NEEDS_VERIFICATION"
    assert umbrella["failure_kind"] == "REVIEWER_RESULT_UNKNOWN"
    assert umbrella["cost_usd"] is None
    assert umbrella["input_tokens"] is None
    assert payload["usage_known"] is False
    assert payload["chunked_review"]["known_chunk_cost_usd"] == "0.014500"
    assert payload["chunked_review"]["failed_chunk_no"] == 2

    with pytest.raises(ContentFoundationError) as exc:
        storage.remaining_article_budget(job_id=outcome.job_id)
    assert exc.value.code == "CONTENT_ARTICLE_COST_UNKNOWN"


def test_a_chunk_that_cannot_be_reserved_still_closes_the_umbrella(
    storage, settings, account, monkeypatch,
):
    """An open reservation whose effect started blocks the job until a human acts.

    So the failure that happens BETWEEN two paid calls must still settle the
    umbrella, with the cost the earlier calls really had.
    """
    reviewer = ChunkAwareReviewerTransport()
    original = type(storage).begin_content_review_chunk_execution

    def refuse_second(self, **kwargs):
        if int(kwargs["chunk_no"]) == 2:
            raise ContentFoundationError(
                "CONTENT_REVIEW_CHUNK_ENVELOPE_EXCEEDED", "probe",
            )
        return original(self, **kwargs)

    monkeypatch.setattr(
        type(storage), "begin_content_review_chunk_execution", refuse_second,
    )
    _, outcome = _run(
        storage, settings, account, job="chunk-unreserved",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=reviewer, cap="1.000000",
    )
    umbrella = _umbrella(storage, outcome.job_id)
    chunks = _chunks(storage, outcome.job_id)

    assert reviewer.calls == 1, "the second chunk never reached the transport"
    assert [chunk["outcome"] for chunk in chunks] == ["SUCCESS"]
    assert umbrella["outcome"] == "FAILURE"
    assert umbrella["failure_kind"] == "CONTENT_REVIEW_CHUNK_ENVELOPE_EXCEEDED"
    # Exactly what the one call that happened cost -- not unknown, not double.
    assert umbrella["cost_usd"] == "0.014500"
    # The budget is readable again: nothing is left reserved or unknown.
    assert storage.remaining_article_budget(job_id=outcome.job_id) > Decimal("0")


# ------------------------------------------------------------- resume -------

def test_review_only_resume_refuses_to_chunk_before_any_call(
    storage, settings, account,
):
    """A chain approval authorises one reviewer call per stage, not three."""
    _run(
        storage, settings, account, job="chunk-resume",
        writer=WriterTransport(), reviewer=ChunkAwareReviewerTransport(),
        cap="0.120000",
    )
    content = storage.get_content_row_for_job(job_id="chunk-resume")
    transport = ChunkAwareReviewerTransport()
    intent = ReviewerRequestIntent(
        execution_ref="chunk-resume:review:1",
        job_id="chunk-resume",
        run_id=str(content["run_id"]),
        content_id=int(content["id"]),
        draft_fingerprint="c" * 64,
        writer_attempt_no=1,
        review_no=1,
        prompt_fingerprint="d" * 64,
    )
    reviewer = ProductionArticleReviewer(
        storage=storage, job_id="chunk-resume", api_key_provider=lambda: "k",
        sdk_factory=_sdk_factory, caller=transport,
        daily_limit_usd=2, monthly_limit_usd=40,
        resume_approval_ref="approval-chunk-resume", resume_intent=intent,
    )

    class _Draft:
        attempt_no = 1

        def fingerprint(self) -> str:
            return "c" * 64

    from tests.test_b3_production_reviewer import _brief

    with pytest.raises(ProductionReviewerError) as exc:
        reviewer.review(
            draft=_Draft(), brief=_brief(storage, content), evidence=(),
            segments=_segments(60),
        )
    assert exc.value.code == "REVIEW_RESUME_CHUNKING_UNAPPROVED"
    assert transport.calls == 0, "PROVIDER CALL COUNT MUST BE 0"
    assert reviewer.provider_calls == 0
    assert _chunks(storage, "chunk-resume") == []


# ------------------------------------------------------------- identity -----

def test_the_accounted_slice_has_a_stable_visible_identity():
    segments = _segments(60)
    chunks = plan_review_chunks(segments)
    fingerprints = [accounted_segments_fingerprint(chunk) for chunk in chunks]
    assert len(set(fingerprints)) == len(chunks)
    assert all(len(value) == 64 for value in fingerprints)
    assert accounted_segments_fingerprint(chunks[0]) == fingerprints[0]
    assert accounted_segments_fingerprint(chunks[0][::-1]) != fingerprints[0]


def test_the_reviewer_role_is_the_only_one_that_chunks(storage, settings, account):
    _run(
        storage, settings, account, job="chunk-role",
        writer=LongWriterTransport(sentences=LONG_BODY_SENTENCES),
        reviewer=ChunkAwareReviewerTransport(), cap="1.000000",
    )
    roles = {
        str(row["logical_role"]) for row in storage.conn.execute(
            "SELECT DISTINCT logical_role FROM role_provider_executions "
            "WHERE job_id='chunk-role'",
        ).fetchall()
    }
    assert roles == {LogicalModelRole.ARTICLE_REVIEWER.value}
    assert all(
        chunk["parent_execution_ref"].endswith(":ARTICLE_REVIEWER:1")
        for chunk in _chunks(storage, "chunk-role")
    )
