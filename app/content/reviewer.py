"""Production semantic ARTICLE_REVIEWER bound to the frozen Opus 5 authority.

The reviewer owns no lifecycle of its own.  It reserves the durable
``role_provider_executions`` row added by 0032 BEFORE the transport is touched,
stamps the external effect, makes exactly one canonical adapter call, and then
settles that same row once.  A reservation whose effect already started is never
replayed: it is a reconciliation item, not a retry.

Its judgement is semantic and belongs to the model.  Nothing here classifies a
draft segment with lexical overlap, regexes or heuristics; this module only
validates that the returned structure is exactly the claim-accounting contract
the quality gate already consumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Callable

from app.content.contracts import ContentBrief, FrozenEvidenceItem
from app.content.foundation import canonical_json
from app.content.provider_roles import (
    RoleProviderAuthority,
    RoleProviderExecution,
    RoleUsage,
)
from app.content.quality_gate import (
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    DocumentCheck,
    DocumentReview,
    DraftClaimSegment,
    classification_contract_error,
)
from app.core.clock import Clock, SystemClock
from app.llm.anthropic_controlled_adapter import (
    ControlledAdapterError,
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
    ControlledSdkFactory,
    ControlledTechnicalCaller,
    assert_no_disabled_feature_usage,
    assert_returned_model_identity,
)
from app.llm.anthropic_provider_contract import (
    ARTICLE_REVIEWER_INFERENCE_CONFIG,
    OPUS_5_MODEL_ID,
)
from app.model_routing.contracts import LogicalModelRole, ModelFamily

# v3 adds the whole-article gate and the strict inference boundary.  The bump is
# load-bearing: a v2 accounting was produced against a body-only segment surface
# and a decision rule that read "every segment PASS", so it must never satisfy
# the v3 contract by replay.
REVIEWER_VERSION = "production_article_reviewer_opus_v3"
REVIEWER_TIMEOUT_SECONDS = 300.0
REVIEWER_MAX_OUTPUT_TOKENS = 8_192
REVIEWER_MAX_INPUT_TOKENS = 23_808

# How many segments one reviewer call may be asked to account for.
#
# The ceiling above is not raisable: the qualified capability declaration is
# 32000/8192, so a wider output ceiling costs a new paid qualification.  What
# scales the answer is the number of segments, not the length of the article --
# one entry per segment, plus adaptive thinking proportional to how many
# judgements are being made.  Two live observations bound the real capacity:
#
#   * 48 segments came back as one complete JSON object;
#   * 64 segments of an article the same length ran out of output tokens
#     mid-object and the whole paid review was discarded.
#
# So the true limit lies somewhere in (48, 64], and 48 is the largest count
# actually observed to complete.  It is also the safer of the two ends for a
# second reason: those observations were made while every entry still carried
# seven fields, and the entry contract has since been trimmed to four required
# fields, which bought roughly 35 percent of headroom.  A 48-segment chunk
# therefore runs today with about a third of its budget spare against the only
# configuration ever seen to succeed.
#
# Below the line one call is made, exactly as before -- picking a smaller number
# would double the cost of ordinary articles that are known to fit, and a review
# that cannot be afforded destroys the research card just as thoroughly as one
# that truncates.  Above the line the segments are split into equal chunks, so
# crossing the line by one segment yields two chunks of 25 rather than one of 48
# plus one of 1.
REVIEWER_MAX_SEGMENTS_PER_CALL = 48

# Each chunk re-sends the whole article and the whole evidence package, so the
# job pays a full input pass per chunk.  Beyond four chunks the draft is long
# enough that a human should look at it before roughly 1.30 USD of review is
# authorised, and the refusal below happens before any call is made, so it costs
# nothing.
REVIEWER_MAX_CHUNKS = 4


@dataclass(frozen=True)
class ReviewerRequestIntent:
    """Exact immutable identity of one review-only provider request."""

    execution_ref: str
    job_id: str
    run_id: str
    content_id: int
    draft_fingerprint: str
    writer_attempt_no: int
    review_no: int
    prompt_fingerprint: str
    provider: str = "ANTHROPIC"
    technical_model_id: str = OPUS_5_MODEL_ID
    reviewer_version: str = REVIEWER_VERSION
    max_input_tokens: int = REVIEWER_MAX_INPUT_TOKENS
    max_output_tokens: int = REVIEWER_MAX_OUTPUT_TOKENS
    timeout_seconds: float = REVIEWER_TIMEOUT_SECONDS
    streaming: bool = True
    max_retries: int = 0
    fallback_policy: str = "FORBIDDEN"

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                self.execution_ref, self.job_id, self.run_id,
                self.draft_fingerprint, self.prompt_fingerprint,
            )
        ):
            raise ValueError("Reviewer request intent requires complete identity.")
        if len(self.draft_fingerprint) != 64 or len(self.prompt_fingerprint) != 64:
            raise ValueError("Reviewer request fingerprints must be SHA-256 values.")
        if self.writer_attempt_no not in (1, 2) or self.review_no not in (1, 2):
            raise ValueError("Review-only permits at most two writer/reviewer rounds.")
        if (
            self.provider != "ANTHROPIC"
            or self.technical_model_id != OPUS_5_MODEL_ID
            or self.reviewer_version != REVIEWER_VERSION
            or self.max_input_tokens != REVIEWER_MAX_INPUT_TOKENS
            or self.max_output_tokens != REVIEWER_MAX_OUTPUT_TOKENS
            or self.timeout_seconds != REVIEWER_TIMEOUT_SECONDS
            or self.streaming is not True
            or self.max_retries != 0
            or self.fallback_policy != "FORBIDDEN"
        ):
            raise ValueError("Reviewer request intent changed a frozen runtime field.")

    def payload(self) -> dict[str, object]:
        return {
            "schema": "article_review_request_intent_v1",
            "execution_ref": self.execution_ref,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "content_id": self.content_id,
            "draft_fingerprint": self.draft_fingerprint,
            "writer_attempt_no": self.writer_attempt_no,
            "review_no": self.review_no,
            "prompt_fingerprint": self.prompt_fingerprint,
            "provider": self.provider,
            "technical_model_id": self.technical_model_id,
            "reviewer_version": self.reviewer_version,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "streaming": self.streaming,
            "max_retries": self.max_retries,
            "fallback_policy": self.fallback_policy,
            "inference_config": ARTICLE_REVIEWER_INFERENCE_CONFIG.payload(),
            "inference_config_fingerprint": (
                ARTICLE_REVIEWER_INFERENCE_CONFIG.evidence_fingerprint()
            ),
        }

    def canonical_preimage(self) -> str:
        return canonical_json(self.payload())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_preimage().encode("utf-8")).hexdigest()

_SYSTEM = """You are the independent claim reviewer for the anonymous editorial
brand Nothing Is Accidental. You did not write this draft and you never rewrite
it. You only account for what it claims.

Segments include the title and every other visible element, not only body
sentences. Each carries a "kind". A title is judged as a claim about what the
article delivers.

For every supplied draft segment decide exactly one classification:

EVIDENCE_GROUNDED_FACT - the segment asserts a fact about the world. List every
confirmed_claim_id that supports its full scope. Only these ids exist; never
invent one. To PASS it must cite at least one. If the segment asserts a fact
that nothing in the evidence supports, still classify it EVIDENCE_GROUNDED_FACT,
leave evidence_ids [] and set outcome to BLOCK - that is how an unsupported
factual claim is reported.
ARGUMENT_OR_INFERENCE - reasoning, interpretation or a conclusion that follows
from the frozen material already supplied. It may only connect, weigh or draw
out what the evidence and brief already establish. evidence_ids must be exactly
[].
NON_FACTUAL_PROSE - framing, transition or rhetoric that asserts nothing factual
and needs no evidence. evidence_ids must be exactly [].

ARGUMENT_OR_INFERENCE is NOT a place to put new claims. A segment that
introduces a NEW EXTERNAL FACT the frozen evidence does not support is not an
inference: a figure, a rate, a date, a rule, a named body's action, a practice
in the world, or any statement a reader could check against reality and find
false. If such a claim has exact evidence, classify it EVIDENCE_GROUNDED_FACT
and cite it. If it does not, set outcome to BLOCK.

That test is about NEW EXTERNAL FACTS, not about tone. This publication is
opinion journalism, not a datasheet, and the following are legitimate and must
PASS rather than BLOCK:

- reasoning that connects, weighs, reframes or draws a conclusion from the
  supplied evidence, even when phrased as a general observation - classify
  ARGUMENT_OR_INFERENCE;
- the writer's reading of what a mechanism means, what it rewards, or what it
  makes hard, provided the mechanism itself is in evidence -
  ARGUMENT_OR_INFERENCE;
- rhetoric, scene-setting, transitions, addresses to the reader, and titles that
  frame rather than assert - NON_FACTUAL_PROSE;
- a sentence that is plainly rhetorical rather than checkable, such as observing
  that there is nobody at the kerb to argue with - NON_FACTUAL_PROSE.

Ask one question of each segment: could a reader check this against the world
and find it FALSE? If yes, it is a fact and needs evidence. If it is the
writer's interpretation of supplied material, or rhetoric carrying no checkable
assertion, it is not a fact and must not be blocked for lacking evidence.
Blocking interpretation as if it were an unsupported fact is itself an error:
it produces a draft that says nothing rather than one that says too much.

Worked examples, assuming the evidence establishes that signal timing shares
green time between movements and that 9 percent of one city's buttons work:

"Only about 9 percent of the city's crosswalk buttons work."
  -> EVIDENCE_GROUNDED_FACT, cite the id, PASS.
"Only about 4 percent of the city's crosswalk buttons work."
  -> EVIDENCE_GROUNDED_FACT, evidence_ids [], BLOCK. The figure is wrong.
"Most councils quietly removed the wiring years ago."
  -> EVIDENCE_GROUNDED_FACT, evidence_ids [], BLOCK. A new practice in the
     world that nothing here supports.
"An inert button is not a device that stopped listening; it is attached to a
 machine that was never asking."
  -> NON_FACTUAL_PROSE, PASS. A metaphor restating the established mechanism.
"Distribution requires units."
  -> ARGUMENT_OR_INFERENCE, PASS. Drawn from the supplied guidance.
"Read as a budget rather than as a place, the crossing becomes arithmetic."
  -> ARGUMENT_OR_INFERENCE, PASS. The writer's reading, not a new fact.
"There is nobody standing there to argue with."
  -> NON_FACTUAL_PROSE, PASS. Rhetoric addressed to the reader.
"Nine Percent: The Button Is Not Where the Decision Gets Made"
  -> NON_FACTUAL_PROSE, PASS. A framing title; the figure inside it is carried
     by the body segment that states it.

Short aphoristic sentences and fragments are style, not evidence claims. Judge
what the sentence asserts, not how confident it sounds.

OUTCOME IS NOT A CLASSIFICATION. BLOCK means one thing only: this segment
asserts a fact the evidence does not support. ARGUMENT_OR_INFERENCE and
NON_FACTUAL_PROSE are ALWAYS outcome PASS - never BLOCK a transition, a
framing title, authorial signposting or a rhetorical setup on the grounds
that it carries no evidence, because carrying no evidence is what those
classes mean. If a segment really does smuggle an unsupported claim, it is
not prose or inference at all: classify it EVIDENCE_GROUNDED_FACT with
evidence_ids [] and BLOCK that.

Judge meaning, not word overlap. A sentence that reuses the evidence wording but
widens its scope is not grounded. A sentence that shares no words with the
evidence may still be grounded by it.

Set outcome to PASS when the segment is acceptable as classified, and BLOCK when
it is not. contains_external_fact must be false for ARGUMENT_OR_INFERENCE and
NON_FACTUAL_PROSE, and true for EVIDENCE_GROUNDED_FACT. The flag and the class
say the same thing: a segment that asserts an outside fact is a grounded fact,
and one that does not is not. Never combine ARGUMENT_OR_INFERENCE or
NON_FACTUAL_PROSE with contains_external_fact true, and never mark an
EVIDENCE_GROUNDED_FACT false; both are rejected contradictions, not ways to
flag a problem.

Then judge the article as a whole in document_review. Answer each check true only
if it clearly holds:
TITLE_REFLECTS_BODY - the title describes what the article actually discusses.
TITLE_PROMISE_FULFILLED - what the title promises the reader is delivered.
TITLE_MECHANISM_EXPLAINED - any mechanism, cause or arithmetic named in the title
is actually explained in the body. A vivid title for a different, unexplained
mechanism is false.
BRIEF_QUESTION_ANSWERED - the article answers the brief's question.
THESIS_CONSISTENT - one main thesis, held consistently.
CONCLUSIONS_WITHIN_EVIDENCE - conclusions do not reach past the evidence.
For every false check add a specific, actionable rewrite instruction to findings.
If every check is true, findings must be [].

A long article's accounting does not fit one answer, so it may be split across
several requests. Every request carries the WHOLE article and the WHOLE evidence
package; only the list of segments you must account for changes. If the request
carries account_for_segment_ids, return exactly one entry for each id in that
list and no entry for any other segment - the other segments are context you
read but do not account for here. If it carries no such list, account for every
supplied segment. Judge each segment in the context of the whole article either
way; the split changes what you report, never what you read.

Return document_review only when required_output asks for it. When it does not,
the whole-article verdict was already given in another request and repeating it
would contradict it.

Return exactly one JSON object and nothing else. No Markdown, no code fence, no
prose before or after it. Return exactly one entry per segment_id you were asked
to account for, copying each segment_id verbatim.

Each entry carries FOUR fields and no others: segment_id, classification,
reason, outcome. Add evidence_ids ONLY for EVIDENCE_GROUNDED_FACT, where it is
required. Do NOT emit segment_fingerprint - the segment_id already ends in it.
Do NOT emit contains_external_fact - the classification already states it. Do
NOT emit an empty evidence_ids for inference or prose. Those three fields
repeat what you were given, and repeating them has run reviews out of output
tokens before.

Keep each reason to at most 12 words and each finding to at most 30 words.
Budget discipline matters here: a review that runs out of output tokens is
discarded whole, so be terse everywhere rather than thorough in the first
entries and truncated in the last."""


class ProductionReviewerError(RuntimeError):
    """A typed fail-closed refusal on the production reviewer boundary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def plan_review_chunks(
    segments: tuple[DraftClaimSegment, ...],
) -> tuple[tuple[DraftClaimSegment, ...], ...]:
    """Split the coverage surface into calls that fit the output ceiling.

    The chunks partition ``segments`` in reading order: every segment appears in
    exactly one chunk, and their concatenation is the original tuple.  Sizes are
    balanced rather than greedy, so a draft that crosses the line by one segment
    produces two comfortable calls instead of one at the edge plus a stub.
    """
    ordered = tuple(segments)
    total = len(ordered)
    if total <= REVIEWER_MAX_SEGMENTS_PER_CALL:
        return (ordered,)
    chunk_count = -(-total // REVIEWER_MAX_SEGMENTS_PER_CALL)
    if chunk_count > REVIEWER_MAX_CHUNKS:
        raise ProductionReviewerError(
            "REVIEWER_SEGMENT_COUNT_UNSUPPORTED",
            f"A draft of {total} segments would need {chunk_count} paid reviewer "
            f"calls; at most {REVIEWER_MAX_CHUNKS} are permitted without a human "
            "decision. No provider call was made.",
        )
    base, extra = divmod(total, chunk_count)
    chunks: list[tuple[DraftClaimSegment, ...]] = []
    start = 0
    for index in range(chunk_count):
        size = base + (1 if index < extra else 0)
        chunks.append(ordered[start:start + size])
        start += size
    return tuple(chunks)


def accounted_segments_fingerprint(
    segments: tuple[DraftClaimSegment, ...],
) -> str:
    """Identity of the exact slice one chunk was asked to account for."""
    return hashlib.sha256(
        canonical_json([segment.segment_id for segment in segments]).encode("utf-8")
    ).hexdigest()


def assemble_reviewer_prompt(
    *,
    draft_fingerprint: str,
    brief: ContentBrief,
    evidence: tuple[FrozenEvidenceItem, ...],
    segments: tuple[DraftClaimSegment, ...],
    lineage: dict[str, Any],
    account_for: tuple[DraftClaimSegment, ...] | None = None,
    chunk_no: int = 1,
    chunk_count: int = 1,
) -> str:
    """Build the exact reviewer user prompt; no secret and no raw style corpus.

    ``account_for`` is the slice of ``segments`` this call must account for. It
    is omitted for an unsplit review, and the payload is then byte-identical to
    the one this function has always produced -- which matters, because a stored
    REVIEW-ONLY approval is bound to that prompt's fingerprint.
    """
    chunked = account_for is not None
    if chunked and chunk_count < 2:
        raise ProductionReviewerError(
            "REVIEWER_CHUNK_PLAN_INVALID",
            "A per-chunk accounting list requires at least two chunks.",
        )
    if not chunked and chunk_count != 1:
        raise ProductionReviewerError(
            "REVIEWER_CHUNK_PLAN_INVALID",
            "A multi-chunk review must name the segments each call accounts for.",
        )
    payload = {
        "contract": {
            "logical_model_role": LogicalModelRole.ARTICLE_REVIEWER.value,
            "model_family": ModelFamily.OPUS.value,
            "reviewer_version": REVIEWER_VERSION,
            "draft_fingerprint": draft_fingerprint,
            "fallback": "FORBIDDEN",
            "lineage": lineage,
        },
        "brief": brief.model_dump(mode="json"),
        "allowed_evidence": [
            {
                "confirmed_claim_id": item.confirmed_claim_id,
                "claim_text": item.claim_text,
                "source_url": item.source_url,
                "source_claim_text": item.source_claim_text,
                "evidence_excerpt": item.excerpt_text,
            }
            for item in evidence
        ],
        "draft_segments": [segment.payload() for segment in segments],
        "required_output": {
            "reviewer_version": "string equal to the contract reviewer_version",
            "entries": (
                "array with exactly one object per "
                + (
                    "segment_id listed in account_for_segment_ids"
                    if chunked else "supplied segment_id"
                )
                + ", each with: segment_id, segment_fingerprint (FIRST 16 "
                "CHARACTERS ONLY), classification "
                "(EVIDENCE_GROUNDED_FACT | ARGUMENT_OR_INFERENCE | "
                "NON_FACTUAL_PROSE), evidence_ids (array of allowed "
                "confirmed_claim_id values; non-empty for a PASSing "
                "EVIDENCE_GROUNDED_FACT, [] for a BLOCKed unsupported one, and "
                "always exactly [] for ARGUMENT_OR_INFERENCE and "
                "NON_FACTUAL_PROSE), reason (non-empty string of at most 12 "
                "words), outcome (PASS | BLOCK), contains_external_fact "
                "(boolean; false for ARGUMENT_OR_INFERENCE and NON_FACTUAL_PROSE)"
            ),
        },
    }
    if chunked:
        # The whole article and the whole evidence package stay above; only the
        # accounting list narrows.  The verdict on the article as a whole is
        # asked for once, in the first chunk, so it can be neither duplicated
        # nor contradicted.
        payload["contract"]["review_chunk"] = {
            "chunk_no": chunk_no,
            "chunk_count": chunk_count,
            "reason": (
                "The per-segment accounting for this draft does not fit one "
                "answer within the reviewer output ceiling."
            ),
        }
        payload["account_for_segment_ids"] = [
            segment.segment_id for segment in account_for
        ]
    if chunk_no == 1:
        payload["required_output"]["document_review"] = (
            "object with: checks (object whose keys are exactly "
            + " | ".join(check.value for check in DocumentCheck)
            + ", each a boolean) and findings (array of specific rewrite "
            "instructions, one per false check, each at most 30 words; "
            "exactly [] when every check is true)"
        )
    else:
        payload["required_output"]["document_review"] = (
            "OMIT this key entirely; the whole-article verdict belongs to "
            "chunk 1 of this review"
        )
    return canonical_json(payload)


def _parse_document_review(raw: object) -> DocumentReview:
    """Parse the whole-article verdict; an unusable verdict is never a PASS."""
    if type(raw) is not dict or set(raw) != {"checks", "findings"}:
        raise ProductionReviewerError(
            "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
            "document_review must contain exactly checks and findings.",
        )
    checks_raw = raw["checks"]
    if type(checks_raw) is not dict or set(checks_raw) != {
        check.value for check in DocumentCheck
    }:
        raise ProductionReviewerError(
            "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
            "document_review.checks must name exactly the required checks.",
        )
    checks: dict[DocumentCheck, bool] = {}
    for check in DocumentCheck:
        value = checks_raw[check.value]
        if type(value) is not bool:
            raise ProductionReviewerError(
                "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
                "Every document_review check must be a JSON boolean.",
            )
        checks[check] = value
    findings_raw = raw["findings"]
    if type(findings_raw) is not list or not all(
        type(item) is str and item.strip() and item == item.strip()
        for item in findings_raw
    ):
        raise ProductionReviewerError(
            "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
            "document_review.findings must be canonical non-empty strings.",
        )
    review = DocumentReview(checks=checks, findings=tuple(findings_raw))
    # A failed check without an instruction cannot drive a rewrite, and a clean
    # verdict carrying instructions contradicts itself.  Both are contract errors
    # rather than a quiet APPROVE.
    if review.failed_checks and not review.findings:
        raise ProductionReviewerError(
            "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
            "A failed document check requires at least one rewrite instruction.",
        )
    if not review.failed_checks and review.findings:
        raise ProductionReviewerError(
            "REVIEWER_DOCUMENT_REVIEW_MALFORMED",
            "A fully passing document review must carry no findings.",
        )
    return review


def parse_reviewer_response(
    text: object,
    *,
    segments: tuple[DraftClaimSegment, ...],
    allowed_evidence_ids: frozenset[str] | None = None,
    expect_document_review: bool = True,
) -> tuple[tuple[ClaimAccountingEntry, ...], DocumentReview | None]:
    """Map the transport response onto the claim-accounting and document contract.

    Structure, per-class evidence cardinality and the document verdict are
    validated here.  Coverage, identity and evidence-scope invariants stay
    where they already live, in the quality gate.

    ``segments`` is what THIS response must account for: the whole draft for an
    unsplit review, one chunk of it otherwise.  ``expect_document_review`` is
    false for every chunk after the first, where the whole-article verdict was
    already given and must not be restated; the response must then omit the key
    entirely rather than repeat, contradict or invent a second verdict.
    """
    if not isinstance(text, str) or not text.strip():
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_EMPTY", "The reviewer returned no text.",
        )
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_NOT_JSON",
            "The reviewer response is not one JSON object.",
        ) from exc
    required_keys = (
        {"reviewer_version", "entries", "document_review"}
        if expect_document_review else {"reviewer_version", "entries"}
    )
    if type(payload) is not dict or set(payload) != required_keys:
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_CONTRACT_INVALID",
            "The reviewer response must contain exactly reviewer_version, "
            "entries and document_review."
            if expect_document_review else
            "A continuation chunk must contain exactly reviewer_version and "
            "entries; the whole-article verdict belongs to the first chunk.",
        )
    if type(payload["reviewer_version"]) is not str or (
        payload["reviewer_version"] != REVIEWER_VERSION
    ):
        raise ProductionReviewerError(
            "REVIEWER_VERSION_MISMATCH",
            "The reviewer response does not name the exact canonical version.",
        )
    if type(payload["entries"]) is not list:
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_CONTRACT_INVALID",
            "The reviewer response does not carry a literal entries array.",
        )
    known = {segment.segment_id: segment.fingerprint for segment in segments}
    # Three of the seven fields carry no information the reviewer was not
    # already given, and the output budget is the binding constraint on an
    # article-length review: segment_id already ends in the first 16 hex
    # characters of the fingerprint, contains_external_fact is forced by the
    # classification, and evidence_ids must be empty for the two non-factual
    # classes.  A review that overruns max_tokens is discarded whole, so what
    # is redundant is made optional rather than mandatory.  Both shapes parse.
    required_fields = {"segment_id", "classification", "reason", "outcome"}
    optional_fields = {"segment_fingerprint", "contains_external_fact", "evidence_ids"}
    entries: list[ClaimAccountingEntry] = []
    seen: set[str] = set()
    for raw in payload["entries"]:
        if (
            type(raw) is not dict
            or not required_fields <= set(raw)
            or not set(raw) <= required_fields | optional_fields
        ):
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_MALFORMED",
                "A reviewer entry must be an exact canonical object.",
            )
        try:
            if type(raw["segment_id"]) is not str or not raw["segment_id"]:
                raise TypeError("segment_id must be a non-empty string")
            # Omitted means "the one segment_id already names"; the identity
            # check below is unchanged, because it compares against exactly the
            # value derived here.  A supplied value is still checked as before.
            fingerprint = raw.get(
                "segment_fingerprint", known.get(raw["segment_id"], ""),
            )
            if type(fingerprint) is not str or not fingerprint:
                raise TypeError("segment_fingerprint must be a non-empty string")
            if type(raw["classification"]) is not str:
                raise TypeError("classification must be a string enum literal")
            classification = ClaimClassification(raw["classification"])
            if type(raw["outcome"]) is not str:
                raise TypeError("outcome must be a string enum literal")
            outcome = ClaimReviewOutcome(raw["outcome"])
            # BLOCK on a non-factual class is a contradiction, not a verdict:
            # prose and inference assert nothing checkable, so there is nothing
            # for the evidence to fail to support. The reviewer nonetheless
            # keeps using BLOCK to mean "this is not a fact", with reasons like
            # "Transition" and "Framing title" - twelve such segments on one
            # sound draft - and no amount of instruction has stopped it. The
            # contradiction is normalised to PASS here, once, so both the
            # quality gate and the decision see a coherent entry. A segment
            # that genuinely smuggles an unsupported claim is not this class:
            # the reviewer reports that as EVIDENCE_GROUNDED_FACT with no
            # evidence, and that path is untouched.
            if (
                outcome is ClaimReviewOutcome.BLOCK
                and classification in (
                    ClaimClassification.ARGUMENT_OR_INFERENCE,
                    ClaimClassification.NON_FACTUAL_PROSE,
                )
            ):
                outcome = ClaimReviewOutcome.PASS
            # Omitted means the empty list, which is the only value the
            # contract permits for the two non-factual classes anyway.  A
            # grounded fact that omits it still fails as evidence missing.
            raw_evidence = raw.get("evidence_ids", [])
            if type(raw_evidence) is not list or not all(
                type(value) is str and bool(value) for value in raw_evidence
            ):
                raise TypeError("evidence_ids must be an array of non-empty strings")
            evidence_ids = tuple(raw_evidence)
            if (
                type(raw["reason"]) is not str
                or not raw["reason"].strip()
                or raw["reason"] != raw["reason"].strip()
            ):
                raise TypeError("reason must be a non-empty canonical string")
            # Omitted means what the classification already forces: an outside
            # fact for a grounded fact, none for inference or prose.  The gate
            # still rejects a supplied value that contradicts the class.
            external = raw.get(
                "contains_external_fact",
                classification is ClaimClassification.EVIDENCE_GROUNDED_FACT,
            )
            if type(external) is not bool:
                raise TypeError("contains_external_fact must be a JSON boolean")
            entry = ClaimAccountingEntry(
                segment_id=raw["segment_id"],
                segment_fingerprint=fingerprint,
                classification=classification,
                evidence_ids=evidence_ids,
                reason=raw["reason"],
                outcome=outcome,
                contains_external_fact=external,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_MALFORMED",
                f"A reviewer entry is not the claim-accounting contract: {exc}",
            ) from exc
        if entry.segment_id not in known:
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_UNKNOWN_SEGMENT",
                "The reviewer accounted for a segment that was not supplied.",
            )
        if entry.segment_id in seen:
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_DUPLICATE_SEGMENT",
                "The reviewer accounted for one segment more than once.",
            )
        # The reviewer echoes a value we supplied, so the risk here is that it
        # answers about a segment other than the one it names - not that it
        # forges a hash.  segment_id already pins the first 16 hex characters of
        # this fingerprint, so a wrong segment cannot survive the checks above.
        # Demanding a verbatim 64-character echo for every entry added nothing
        # and was brittle: on a live 22-entry review the model abbreviated
        # exactly one fingerprint to "a5e0caf75d91f563b..." and the whole paid
        # review was discarded. An abbreviation of the true value is accepted; a
        # different value, or one too short to identify the segment, is not.
        canonical = known[entry.segment_id]
        echoed = entry.segment_fingerprint.strip().rstrip(".…").strip()
        if not echoed or len(echoed) < 16 or not canonical.startswith(echoed):
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_FINGERPRINT_MISMATCH",
                "The reviewer changed the supplied segment fingerprint.",
            )
        if allowed_evidence_ids is not None and any(
            evidence_id not in allowed_evidence_ids
            for evidence_id in entry.evidence_ids
        ):
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_UNKNOWN_EVIDENCE",
                "The reviewer cited evidence outside the frozen package.",
            )
        # The single canonical entry contract: evidence cardinality *and*
        # external-fact consistency.  Refusing it here means no consumer of a
        # reviewer result can ever observe a self-contradictory PASS entry.
        violation = classification_contract_error(
            classification=entry.classification,
            evidence_ids=entry.evidence_ids,
            contains_external_fact=entry.contains_external_fact,
            outcome=entry.outcome,
        )
        if violation is not None:
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_EVIDENCE_CONTRACT", violation,
            )
        seen.add(entry.segment_id)
        entries.append(entry)
    if seen != set(known):
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_INCOMPLETE",
            "The reviewer did not account for every supplied segment exactly once.",
        )
    if not expect_document_review:
        return tuple(entries), None
    return tuple(entries), _parse_document_review(payload["document_review"])


_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r'(?i)("?(?:api[_-]?key|authorization|password|secret)"?\s*[:=]\s*)'
        r'("[^"\r\n]*"|[^,\s}\r\n]+)'
    ),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{8,}"),
)


def safe_reviewer_response_artifact(text: object) -> dict[str, object]:
    """Preserve a bounded diagnostic response without retaining credentials."""
    raw = text if isinstance(text, str) else repr(text)
    redacted = _SECRET_PATTERNS[0].sub("[REDACTED_ANTHROPIC_KEY]", raw)
    redacted = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub("Bearer [REDACTED]", redacted)
    encoded = raw.encode("utf-8", errors="replace")
    return {
        "response_sha256": hashlib.sha256(encoded).hexdigest(),
        "response_bytes": len(encoded),
        "redacted_text": redacted[:262_144],
        "truncated": len(redacted) > 262_144,
    }


def _sum_usage(usages: list[RoleUsage], raw: Any) -> RoleUsage:
    """Total token usage of every chunk that actually returned.

    The umbrella settles this once, so a chunked review is priced from the same
    frozen profile and lands in ``model_usage`` exactly once.  For a single call
    the result is that call's own usage, unchanged.  ``inference_geo`` and
    ``service_tier`` describe the last response, which is what an unsplit review
    reported too.  An empty list is a known zero -- no call was made at all --
    and never an unknown; unknown is expressed by passing ``usage=None`` to the
    settlement instead.
    """
    return RoleUsage(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        cache_read_tokens=sum(usage.cache_read_tokens for usage in usages),
        cache_write_tokens=sum(usage.cache_write_tokens for usage in usages),
        web_search_requests=sum(usage.web_search_requests for usage in usages),
        inference_geo=None if raw is None else raw.inference_geo,
        service_tier=None if raw is None else raw.service_tier,
    )


class ProductionArticleReviewer:
    """The production ``ClaimAccountingReviewPort`` for frozen Opus 5."""

    def __init__(
        self,
        *,
        storage: Any,
        job_id: str,
        api_key_provider: Callable[[], str | None],
        sdk_factory: ControlledSdkFactory | None = None,
        caller: ControlledTechnicalCaller | None = None,
        timeout_seconds: float = REVIEWER_TIMEOUT_SECONDS,
        daily_limit_usd: Decimal | float | str,
        monthly_limit_usd: Decimal | float | str,
        resume_approval_ref: str | None = None,
        resume_intent: ReviewerRequestIntent | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._storage = storage
        self._job_id = job_id
        self._adapter = ControlledAnthropicAdapter(
            api_key_provider=api_key_provider,
            sdk_factory=sdk_factory,
            caller=caller,
        )
        self._timeout_seconds = timeout_seconds
        self._daily_limit_usd = daily_limit_usd
        self._monthly_limit_usd = monthly_limit_usd
        if (resume_approval_ref is None) != (resume_intent is None):
            raise ValueError("Review resume approval and intent must appear together.")
        self._resume_approval_ref = resume_approval_ref
        self._resume_intent = resume_intent
        self._clock = clock or SystemClock()
        self.provider_calls = 0
        # The port returns segment entries; the whole-article verdict is read
        # from here by the caller that owns the APPROVE/REWRITE_ONCE decision.
        self.last_document_review: DocumentReview | None = None

    @property
    def reviewer_version(self) -> str:
        return REVIEWER_VERSION

    # -- authority -----------------------------------------------------------

    def _authority(self) -> tuple[RoleProviderAuthority, dict[str, Any]]:
        binding = self._storage.freeze_content_role_model_binding(
            job_id=self._job_id, role=LogicalModelRole.ARTICLE_REVIEWER,
        )
        if (
            binding.role is not LogicalModelRole.ARTICLE_REVIEWER
            or binding.family is not ModelFamily.OPUS
            or binding.technical_model_id != OPUS_5_MODEL_ID
            or binding.fallback_policy != "FORBIDDEN"
        ):
            raise ProductionReviewerError(
                "REVIEWER_BINDING_UNSUPPORTED",
                "The reviewer requires frozen OPUS / claude-opus-5 with "
                "fallback FORBIDDEN.",
            )
        provenance = self._storage.load_content_role_provenance(
            job_id=self._job_id, role=LogicalModelRole.ARTICLE_REVIEWER,
        )
        pricing = provenance["pricing"]
        if pricing is None or pricing.prices is None:
            raise ProductionReviewerError(
                "REVIEWER_PRICING_UNVERIFIED",
                "The frozen reviewer binding has no verified price list.",
            )
        authority = RoleProviderAuthority(
            job_id=self._job_id,
            role=LogicalModelRole.ARTICLE_REVIEWER,
            binding_intent_id=f"{self._job_id}:{LogicalModelRole.ARTICLE_REVIEWER.value}",
            model_registry_id=binding.model_registry_id,
            provider=binding.provider,
            technical_model_id=binding.technical_model_id,
            pricing_ref=binding.pricing_ref,
            pricing_profile_fingerprint=pricing.contract_fingerprint(),
            qualification_ref=binding.qualification_ref,
            capability_ref=binding.capability_ref,
            prices=pricing.prices,
        )
        return authority, provenance

    def max_legal_cost(self, authority: RoleProviderAuthority) -> Decimal:
        """The most this reviewer call may ever cost at its declared ceiling."""
        return authority.settle(RoleUsage(
            input_tokens=REVIEWER_MAX_INPUT_TOKENS,
            output_tokens=REVIEWER_MAX_OUTPUT_TOKENS,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            inference_geo=None,
            service_tier=None,
        ))

    # -- the port ------------------------------------------------------------

    def review(
        self,
        *,
        draft: Any,
        brief: ContentBrief,
        evidence: tuple[FrozenEvidenceItem, ...],
        segments: tuple[DraftClaimSegment, ...],
    ) -> tuple[ClaimAccountingEntry, ...]:
        content = self._storage.get_content_row_for_job(job_id=self._job_id)
        content_id = int(content["id"])
        run_id = str(content["run_id"])
        attempt_no = int(draft.attempt_no)
        authority, _ = self._authority()
        lineage = {"job_id": self._job_id, "run_id": run_id,
                   "content_id": content_id}
        resume = self._resume_intent

        # 1. Uncertain reservations are reconciliation items, never retries.
        #    This is asked first so a restart after a crash is told what its
        #    open reservation is, rather than something about this draft.
        if resume is None:
            existing = self._storage.get_role_provider_execution(
                content_id=content_id, role=LogicalModelRole.ARTICLE_REVIEWER,
                attempt_no=attempt_no,
            )
            if existing is not None:
                if str(existing["outcome"]) == "IN_FLIGHT":
                    started = existing["external_effect_started_at"] is not None
                    raise ProductionReviewerError(
                        "CONTENT_REVIEWER_RESULT_UNCERTAIN" if started
                        else "CONTENT_REVIEWER_RESERVATION_OPEN",
                        "A reviewer execution is already reserved for this content; "
                        "its provider outcome is unknown and is never replayed.",
                    )
                raise ProductionReviewerError(
                    "CONTENT_REVIEWER_ALREADY_SETTLED",
                    "This content already has a terminal reviewer execution.",
                )

        # The plan is made before anything is reserved and before any transport
        # is touched, so an unsupported draft costs nothing at all.
        chunks = plan_review_chunks(segments)
        chunk_count = len(chunks)
        prompt = assemble_reviewer_prompt(
            draft_fingerprint=draft.fingerprint(),
            brief=brief,
            evidence=evidence,
            segments=segments,
            lineage=lineage,
        )
        prompt_fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        execution_ref = (
            resume.execution_ref if resume is not None else
            f"{self._job_id}:{LogicalModelRole.ARTICLE_REVIEWER.value}:{attempt_no}"
        )
        if resume is not None and chunk_count > 1:
            # A REVIEW-ONLY approval is one immutable row that authorises one
            # reviewer call per stage at one declared cost.  Splitting the stage
            # would spend the chain cap on calls the owner never approved, so the
            # stage refuses before it reserves or spends anything.
            raise ProductionReviewerError(
                "REVIEW_RESUME_CHUNKING_UNAPPROVED",
                f"This draft needs {chunk_count} reviewer calls; the REVIEW-ONLY "
                "approval authorises one per stage. No provider call was made.",
            )

        if resume is not None:
            if (
                resume.job_id != self._job_id
                or resume.run_id != run_id
                or resume.content_id != content_id
                or resume.writer_attempt_no != attempt_no
                or resume.draft_fingerprint != draft.fingerprint()
                or resume.prompt_fingerprint != prompt_fingerprint
                or resume.provider != authority.provider
                or resume.technical_model_id != authority.technical_model_id
            ):
                raise ProductionReviewerError(
                    "REVIEW_RESUME_INTENT_MISMATCH",
                    "The approved REVIEW-ONLY request differs from the exact draft prompt.",
                )
            assert self._resume_approval_ref is not None
            ceiling = self.max_legal_cost(authority)
            self._storage.begin_content_review_resume_execution(
                approval_ref=self._resume_approval_ref,
                intent=resume,
                reserved_cost_usd=ceiling,
                daily_limit_usd=self._daily_limit_usd,
                monthly_limit_usd=self._monthly_limit_usd,
                now=self._clock.now(),
            )
            self._storage.mark_content_review_resume_effect_started(
                execution_ref, now=self._clock.now(),
            )
        else:
            # 2. One ARTICLE budget, shared with the writer.  A split review
            #    reserves the full legal cost of EVERY planned call up front, so
            #    a job that cannot afford the whole plan is refused before the
            #    first chunk is paid for rather than halfway through it.
            ceiling = self.max_legal_cost(authority) * chunk_count

            # 3. Durable IN_FLIGHT, then the durable external-effect stamp.
            self._storage.begin_role_provider_execution(
                execution_ref=execution_ref, job_id=self._job_id, run_id=run_id,
                content_id=content_id, role=LogicalModelRole.ARTICLE_REVIEWER,
                attempt_no=attempt_no, max_cost_usd=ceiling, authority=authority,
                daily_limit_usd=self._daily_limit_usd,
                monthly_limit_usd=self._monthly_limit_usd,
                now=self._clock.now(),
            )
            self._storage.mark_role_provider_effect_started(
                execution_ref, now=self._clock.now(),
            )

        # 4. One provider call per chunk.  A single-chunk review makes exactly
        #    the one call it always made, against the byte-identical prompt.
        allowed_evidence_ids = frozenset(
            item.confirmed_claim_id for item in evidence
        )
        per_call_ceiling = self.max_legal_cost(authority)
        collected: list[ClaimAccountingEntry] = []
        settled_usage: list[RoleUsage] = []
        chunk_records: list[dict[str, Any]] = []
        document_review: DocumentReview | None = None
        raw = None

        for chunk_no, chunk in enumerate(chunks, start=1):
            chunk_prompt = prompt if chunk_count == 1 else assemble_reviewer_prompt(
                draft_fingerprint=draft.fingerprint(),
                brief=brief,
                evidence=evidence,
                segments=segments,
                lineage=lineage,
                account_for=chunk,
                chunk_no=chunk_no,
                chunk_count=chunk_count,
            )
            chunk_ref: str | None = None
            if chunk_count > 1:
                # Every chunk is its own paid external effect: its own durable
                # reference, its own reservation carved out of the umbrella, and
                # its own effect stamp, all before the transport is touched.
                chunk_ref = f"{execution_ref}:chunk:{chunk_no}/{chunk_count}"
                try:
                    self._storage.begin_content_review_chunk_execution(
                        chunk_execution_ref=chunk_ref,
                        parent_execution_ref=execution_ref,
                        job_id=self._job_id,
                        run_id=run_id,
                        content_id=content_id,
                        attempt_no=attempt_no,
                        chunk_no=chunk_no,
                        chunk_count=chunk_count,
                        segment_count=len(chunk),
                        accounted_segments_fingerprint=(
                            accounted_segments_fingerprint(chunk)
                        ),
                        prompt_fingerprint=hashlib.sha256(
                            chunk_prompt.encode("utf-8"),
                        ).hexdigest(),
                        requests_document_review=chunk_no == 1,
                        reserved_cost_usd=per_call_ceiling,
                        provider=authority.provider,
                        technical_model_id=authority.technical_model_id,
                        now=self._clock.now(),
                    )
                    self._storage.mark_content_review_chunk_effect_started(
                        chunk_ref, now=self._clock.now(),
                    )
                except BaseException as exc:
                    # This chunk never reached the transport, so the review is
                    # over and it cost exactly what the earlier chunks cost --
                    # zero if this was the first.  The umbrella is settled with
                    # that known amount rather than left reserved, because an
                    # open reservation whose effect has started blocks every
                    # further paid action on the job until a human reconciles it.
                    self._settle(
                        execution_ref, authority, run_id, content_id, attempt_no,
                        outcome="FAILURE",
                        failure_kind=getattr(
                            exc, "code", "REVIEWER_CHUNK_NOT_RESERVED",
                        ),
                        usage=_sum_usage(settled_usage, raw),
                        returned_model_id=(
                            None if raw is None else raw.returned_model_id
                        ),
                        detail=str(exc)[:200], stop_reason=None,
                        provider_request_id=None,
                        chunk_summary=self._chunk_summary(
                            chunk_count, chunk_records, failed_chunk_no=chunk_no,
                            settled_usage=settled_usage, authority=authority,
                        ),
                    )
                    raise

            try:
                self.provider_calls += 1
                raw = self._adapter.execute(ControlledProviderRequest(
                    technical_model_id=authority.technical_model_id,
                    system_prompt=_SYSTEM,
                    user_prompt=chunk_prompt,
                    max_output_tokens=REVIEWER_MAX_OUTPUT_TOKENS,
                    timeout_seconds=self._timeout_seconds,
                    inference_config=ARTICLE_REVIEWER_INFERENCE_CONFIG,
                    stream_response=True,
                ))
            except BaseException as exc:
                # This call's outcome is unknown, so the review's total cost is
                # unknown even though earlier chunks settled a known cost.  The
                # umbrella therefore settles literally unknown and the operator
                # reconciliation path owns it; the per-chunk ledger still shows
                # exactly which calls did return and what they cost.
                self._settle_chunk(
                    chunk_ref, chunk_no, chunk_count, chunk,
                    outcome="NEEDS_VERIFICATION",
                    failure_kind="REVIEWER_RESULT_UNKNOWN",
                    usage=None, cost_usd=None, returned_model_id=None,
                    detail=f"{type(exc).__name__}", stop_reason=None,
                    provider_request_id=None, authority=authority,
                )
                self._settle(
                    execution_ref, authority, run_id, content_id, attempt_no,
                    outcome="NEEDS_VERIFICATION",
                    failure_kind="REVIEWER_RESULT_UNKNOWN",
                    usage=None, returned_model_id=None,
                    detail=f"{type(exc).__name__}", stop_reason=None,
                    provider_request_id=None,
                    chunk_summary=self._chunk_summary(
                        chunk_count, chunk_records, failed_chunk_no=chunk_no,
                        settled_usage=settled_usage, authority=authority,
                    ),
                )
                raise

            usage = RoleUsage(
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cache_read_tokens=raw.cache_read_tokens,
                cache_write_tokens=raw.cache_write_tokens,
                web_search_requests=raw.web_search_requests,
                inference_geo=raw.inference_geo,
                service_tier=raw.service_tier,
            )

            # 5. Identity and disabled-feature gates, then the structured
            #    contract for exactly the segments this call was asked about.
            try:
                assert_returned_model_identity(
                    requested_model_id=authority.technical_model_id,
                    returned_model_id=raw.returned_model_id,
                )
                assert_no_disabled_feature_usage(
                    cache_read_tokens=raw.cache_read_tokens,
                    cache_write_tokens=raw.cache_write_tokens,
                    web_search_requests=raw.web_search_requests,
                )
                entries, chunk_document = parse_reviewer_response(
                    raw.text,
                    segments=chunk,
                    allowed_evidence_ids=allowed_evidence_ids,
                    expect_document_review=chunk_no == 1,
                )
            except (ControlledAdapterError, ProductionReviewerError) as exc:
                # One bad chunk fails the whole review.  Nothing partial is ever
                # returned to the quality gate: the entries already paid for are
                # preserved in the durable per-chunk record for the operator,
                # and the caller sees the same terminal failure it would have
                # seen from an unsplit review.
                self._settle_chunk(
                    chunk_ref, chunk_no, chunk_count, chunk,
                    outcome="FAILURE",
                    failure_kind=getattr(exc, "code", "REVIEWER_FAILED"),
                    usage=usage, cost_usd=authority.settle(usage),
                    returned_model_id=raw.returned_model_id,
                    detail=str(exc)[:200], stop_reason=raw.stop_reason,
                    provider_request_id=raw.provider_request_id,
                    authority=authority,
                    diagnostic_artifact=safe_reviewer_response_artifact(raw.text),
                )
                settled_usage.append(usage)
                self._settle(
                    execution_ref, authority, run_id, content_id, attempt_no,
                    outcome="FAILURE",
                    failure_kind=getattr(exc, "code", "REVIEWER_FAILED"),
                    usage=_sum_usage(settled_usage, raw),
                    returned_model_id=raw.returned_model_id,
                    detail=str(exc)[:200],
                    stop_reason=raw.stop_reason,
                    provider_request_id=raw.provider_request_id,
                    diagnostic_artifact=safe_reviewer_response_artifact(raw.text),
                    chunk_summary=self._chunk_summary(
                        chunk_count, chunk_records, failed_chunk_no=chunk_no,
                        settled_usage=settled_usage, authority=authority,
                    ),
                )
                raise

            self._settle_chunk(
                chunk_ref, chunk_no, chunk_count, chunk,
                outcome="SUCCESS", failure_kind=None, usage=usage,
                cost_usd=authority.settle(usage),
                returned_model_id=raw.returned_model_id,
                detail=None, stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                authority=authority, entry_count=len(entries),
            )
            settled_usage.append(usage)
            collected.extend(entries)
            chunk_records.append({
                "chunk_no": chunk_no,
                "chunk_execution_ref": chunk_ref,
                "segment_count": len(chunk),
                "entry_count": len(entries),
                "accounted_segments_fingerprint": (
                    accounted_segments_fingerprint(chunk)
                ),
                "stop_reason": raw.stop_reason,
                "provider_request_id": raw.provider_request_id,
                "cost_usd": format(authority.settle(usage), ".6f"),
            })
            if chunk_no == 1:
                document_review = chunk_document

        assert raw is not None
        entries = tuple(collected)
        total_usage = _sum_usage(settled_usage, raw)

        # 6. Coverage of the whole draft, across every chunk combined.  The
        #    parser already enforced it per call, and the settlement validator
        #    rebuilds the segment surface from the durable draft and enforces it
        #    again; this is the cheap check that names the defect precisely
        #    before a paid SUCCESS is attempted.
        aggregate_failure = self._aggregate_contract_error(
            segments=segments, entries=entries, document_review=document_review,
        )
        if aggregate_failure is not None:
            code, detail = aggregate_failure
            self._settle(
                execution_ref, authority, run_id, content_id, attempt_no,
                outcome="FAILURE", failure_kind=code, usage=total_usage,
                returned_model_id=raw.returned_model_id, detail=detail,
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                chunk_summary=self._chunk_summary(
                    chunk_count, chunk_records, failed_chunk_no=None,
                    settled_usage=settled_usage, authority=authority,
                ),
            )
            raise ProductionReviewerError(code, detail)

        self.last_document_review = document_review
        self._settle(
            execution_ref, authority, run_id, content_id, attempt_no,
            outcome="SUCCESS", failure_kind=None, usage=total_usage,
            returned_model_id=raw.returned_model_id,
            detail=None, entry_count=len(entries),
            entries=entries, document_review=document_review,
            stop_reason=raw.stop_reason,
            provider_request_id=raw.provider_request_id,
            chunk_summary=self._chunk_summary(
                chunk_count, chunk_records, failed_chunk_no=None,
                settled_usage=settled_usage, authority=authority,
            ),
        )
        return entries

    @staticmethod
    def _aggregate_contract_error(
        *,
        segments: tuple[DraftClaimSegment, ...],
        entries: tuple[ClaimAccountingEntry, ...],
        document_review: DocumentReview | None,
    ) -> tuple[str, str] | None:
        """Refuse anything the chunks together do not add up to."""
        if document_review is None:
            return (
                "REVIEWER_DOCUMENT_REVIEW_MISSING",
                "The first chunk returned no whole-article verdict.",
            )
        accounted = [entry.segment_id for entry in entries]
        if len(set(accounted)) != len(accounted):
            return (
                "REVIEWER_CHUNK_COVERAGE_DUPLICATE",
                "Two chunks accounted for the same segment.",
            )
        if set(accounted) != {segment.segment_id for segment in segments}:
            return (
                "REVIEWER_CHUNK_COVERAGE_INCOMPLETE",
                "The chunks together did not account for every draft segment "
                "exactly once.",
            )
        return None

    @staticmethod
    def _chunk_summary(
        chunk_count: int,
        chunk_records: list[dict[str, Any]],
        *,
        failed_chunk_no: int | None,
        settled_usage: list[RoleUsage],
        authority: RoleProviderAuthority,
    ) -> dict[str, Any] | None:
        """The durable account of a split review; ``None`` when it was not split."""
        if chunk_count == 1:
            return None
        known = sum(
            (authority.settle(usage) for usage in settled_usage), Decimal("0"),
        )
        return {
            "chunk_count": chunk_count,
            "completed_chunks": len(chunk_records),
            "failed_chunk_no": failed_chunk_no,
            "known_chunk_cost_usd": format(known, ".6f"),
            "chunks": [dict(record) for record in chunk_records],
        }

    def _settle_chunk(
        self,
        chunk_ref: str | None,
        chunk_no: int,
        chunk_count: int,
        chunk: tuple[DraftClaimSegment, ...],
        *,
        outcome: str,
        failure_kind: str | None,
        usage: RoleUsage | None,
        cost_usd: Decimal | None,
        returned_model_id: str | None,
        detail: str | None,
        stop_reason: str | None,
        provider_request_id: str | None,
        authority: RoleProviderAuthority,
        entry_count: int | None = None,
        diagnostic_artifact: dict[str, object] | None = None,
    ) -> None:
        """Settle one chunk's own durable row; a no-op for an unsplit review."""
        if chunk_ref is None:
            return
        payload: dict[str, Any] = {
            "schema": "article_review_chunk_result_v1",
            "reviewer_version": REVIEWER_VERSION,
            "chunk_no": chunk_no,
            "chunk_count": chunk_count,
            "segment_count": len(chunk),
            "accounted_segments_fingerprint": accounted_segments_fingerprint(chunk),
            "inference_config_fingerprint": (
                ARTICLE_REVIEWER_INFERENCE_CONFIG.evidence_fingerprint()
            ),
            "stop_reason": stop_reason,
            "provider_request_id": provider_request_id,
        }
        if detail is not None:
            payload["detail"] = detail
        if entry_count is not None:
            payload["entry_count"] = entry_count
        if usage is None:
            payload["usage_known"] = False
        if diagnostic_artifact is not None:
            payload["response_artifact"] = diagnostic_artifact
        self._storage.settle_content_review_chunk_execution(
            chunk_execution_ref=chunk_ref,
            outcome=outcome,
            failure_kind=failure_kind,
            returned_model_id=returned_model_id,
            usage=usage,
            cost_usd=cost_usd,
            result_payload=payload,
            now=self._clock.now(),
        )

    def _settle(
        self,
        execution_ref: str,
        authority: RoleProviderAuthority,
        run_id: str,
        content_id: int,
        attempt_no: int,
        *,
        outcome: str,
        failure_kind: str | None,
        usage: RoleUsage | None,
        returned_model_id: str | None,
        detail: str | None,
        entry_count: int | None = None,
        entries: tuple[ClaimAccountingEntry, ...] | None = None,
        document_review: DocumentReview | None = None,
        stop_reason: str | None = None,
        provider_request_id: str | None = None,
        diagnostic_artifact: dict[str, object] | None = None,
        chunk_summary: dict[str, Any] | None = None,
    ) -> None:
        """Settle the reserved row once, pricing usage from the frozen profile."""
        cost = authority.settle(usage) if usage is not None else None
        payload: dict[str, Any] = {
            "reviewer_version": REVIEWER_VERSION,
            "inference_config": ARTICLE_REVIEWER_INFERENCE_CONFIG.payload(),
            "inference_config_fingerprint": (
                ARTICLE_REVIEWER_INFERENCE_CONFIG.evidence_fingerprint()
            ),
            "streaming": True,
            "stop_reason": stop_reason,
            "provider_request_id": provider_request_id,
        }
        if detail is not None:
            payload["detail"] = detail
        if entry_count is not None:
            payload["entry_count"] = entry_count
        if entries is not None:
            payload["entries"] = [
                {
                    "segment_id": entry.segment_id,
                    "segment_fingerprint": entry.segment_fingerprint,
                    "classification": entry.classification.value,
                    "evidence_ids": list(entry.evidence_ids),
                    "reason": entry.reason,
                    "outcome": entry.outcome.value,
                    "contains_external_fact": entry.contains_external_fact,
                }
                for entry in entries
            ]
            # APPROVE now means the whole article passed, not only that every
            # segment was individually accounted for.  A missing document
            # verdict is treated as a failed one; it is never an implicit pass.
            payload["document_review"] = (
                document_review.payload() if document_review is not None
                else {"approved": False, "checks": {}, "failed_checks": [],
                      "findings": ["document review is missing"]}
            )
            claims_clean = all(
                entry.outcome is ClaimReviewOutcome.PASS
                and classification_contract_error(
                    classification=entry.classification,
                    evidence_ids=entry.evidence_ids,
                    contains_external_fact=entry.contains_external_fact,
                    outcome=entry.outcome,
                ) is None
                for entry in entries
            )
            document_clean = document_review is not None and document_review.approved
            payload["decision"] = (
                "APPROVE"
                if claims_clean and document_clean
                else "REWRITE_ONCE"
                if attempt_no == 1
                else "HUMAN_REQUIRED"
            )
        if usage is None:
            payload["usage_known"] = False
        if diagnostic_artifact is not None:
            payload["response_artifact"] = diagnostic_artifact
        if chunk_summary is not None:
            # Present only when the review was actually split, so an unsplit
            # review settles the exact payload shape it always did.
            payload["chunked_review"] = chunk_summary
        if self._resume_intent is not None:
            payload["request_intent_fingerprint"] = self._resume_intent.fingerprint()
            payload["draft_fingerprint"] = self._resume_intent.draft_fingerprint
            payload["review_no"] = self._resume_intent.review_no
            self._storage.settle_content_review_resume_execution(
                execution_ref=execution_ref,
                outcome=outcome,
                failure_kind=failure_kind,
                returned_model_id=returned_model_id,
                usage=usage,
                cost_usd=cost,
                result_payload=payload,
                now=self._clock.now(),
            )
            return
        self._storage.settle_role_provider_execution(RoleProviderExecution(
            execution_ref=execution_ref,
            job_id=self._job_id,
            run_id=run_id,
            content_id=content_id,
            role=LogicalModelRole.ARTICLE_REVIEWER,
            attempt_no=attempt_no,
            authority=authority,
            returned_model_id=returned_model_id,
            outcome=outcome,
            failure_kind=failure_kind,
            usage=usage,
            cost_usd=cost,
            payload=payload,
        ), now=self._clock.now())


__all__ = [
    "DocumentCheck",
    "DocumentReview",
    "ProductionArticleReviewer",
    "ProductionReviewerError",
    "REVIEWER_MAX_CHUNKS",
    "REVIEWER_MAX_INPUT_TOKENS",
    "REVIEWER_MAX_OUTPUT_TOKENS",
    "REVIEWER_MAX_SEGMENTS_PER_CALL",
    "REVIEWER_VERSION",
    "ReviewerRequestIntent",
    "accounted_segments_fingerprint",
    "assemble_reviewer_prompt",
    "parse_reviewer_response",
    "plan_review_chunks",
    "safe_reviewer_response_artifact",
]
