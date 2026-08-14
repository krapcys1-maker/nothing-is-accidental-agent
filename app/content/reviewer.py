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

Return exactly one JSON object and nothing else. No Markdown, no code fence, no
prose before or after it. Return exactly one entry per supplied segment_id,
copying each segment_id verbatim. For segment_fingerprint copy only its FIRST
16 CHARACTERS, not the whole value: the segment_id already carries that prefix
and the full 64-character hash wastes the output budget an article-length
review needs. Keep each reason to at most 12 words and each finding to at most
30 words. Budget discipline matters here: a review that runs out of output
tokens is discarded whole, so be terse everywhere rather than thorough in the
first entries and truncated in the last."""


class ProductionReviewerError(RuntimeError):
    """A typed fail-closed refusal on the production reviewer boundary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def assemble_reviewer_prompt(
    *,
    draft_fingerprint: str,
    brief: ContentBrief,
    evidence: tuple[FrozenEvidenceItem, ...],
    segments: tuple[DraftClaimSegment, ...],
    lineage: dict[str, Any],
) -> str:
    """Build the exact reviewer user prompt; no secret and no raw style corpus."""
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
                "array with exactly one object per supplied segment_id, each "
                "with: segment_id, segment_fingerprint (FIRST 16 CHARACTERS "
                "ONLY), classification "
                "(EVIDENCE_GROUNDED_FACT | ARGUMENT_OR_INFERENCE | "
                "NON_FACTUAL_PROSE), evidence_ids (array of allowed "
                "confirmed_claim_id values; non-empty for a PASSing "
                "EVIDENCE_GROUNDED_FACT, [] for a BLOCKed unsupported one, and "
                "always exactly [] for ARGUMENT_OR_INFERENCE and "
                "NON_FACTUAL_PROSE), reason (non-empty string of at most 12 "
                "words), outcome (PASS | BLOCK), contains_external_fact "
                "(boolean; false for ARGUMENT_OR_INFERENCE and NON_FACTUAL_PROSE)"
            ),
            "document_review": (
                "object with: checks (object whose keys are exactly "
                + " | ".join(check.value for check in DocumentCheck)
                + ", each a boolean) and findings (array of specific rewrite "
                "instructions, one per false check, each at most 30 words; "
                "exactly [] when every check is true)"
            ),
        },
    }
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
) -> tuple[tuple[ClaimAccountingEntry, ...], DocumentReview]:
    """Map the transport response onto the claim-accounting and document contract.

    Structure, per-class evidence cardinality and the document verdict are
    validated here.  Coverage, identity and evidence-scope invariants stay
    where they already live, in the quality gate.
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
    if type(payload) is not dict or set(payload) != {
        "reviewer_version", "entries", "document_review",
    }:
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_CONTRACT_INVALID",
            "The reviewer response must contain exactly reviewer_version, "
            "entries and document_review.",
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
    required_fields = {
        "segment_id", "segment_fingerprint", "classification", "evidence_ids",
        "reason", "outcome", "contains_external_fact",
    }
    entries: list[ClaimAccountingEntry] = []
    seen: set[str] = set()
    for raw in payload["entries"]:
        if type(raw) is not dict or set(raw) != required_fields:
            raise ProductionReviewerError(
                "REVIEWER_ENTRY_MALFORMED",
                "A reviewer entry must be an exact canonical object.",
            )
        try:
            if type(raw["segment_id"]) is not str or not raw["segment_id"]:
                raise TypeError("segment_id must be a non-empty string")
            if (
                type(raw["segment_fingerprint"]) is not str
                or not raw["segment_fingerprint"]
            ):
                raise TypeError("segment_fingerprint must be a non-empty string")
            if type(raw["classification"]) is not str:
                raise TypeError("classification must be a string enum literal")
            classification = ClaimClassification(raw["classification"])
            if type(raw["outcome"]) is not str:
                raise TypeError("outcome must be a string enum literal")
            outcome = ClaimReviewOutcome(raw["outcome"])
            if type(raw["evidence_ids"]) is not list or not all(
                type(value) is str and bool(value) for value in raw["evidence_ids"]
            ):
                raise TypeError("evidence_ids must be an array of non-empty strings")
            evidence_ids = tuple(raw["evidence_ids"])
            if (
                type(raw["reason"]) is not str
                or not raw["reason"].strip()
                or raw["reason"] != raw["reason"].strip()
            ):
                raise TypeError("reason must be a non-empty canonical string")
            if type(raw["contains_external_fact"]) is not bool:
                raise TypeError("contains_external_fact must be a JSON boolean")
            entry = ClaimAccountingEntry(
                segment_id=raw["segment_id"],
                segment_fingerprint=raw["segment_fingerprint"],
                classification=classification,
                evidence_ids=evidence_ids,
                reason=raw["reason"],
                outcome=outcome,
                contains_external_fact=raw["contains_external_fact"],
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
        prompt = assemble_reviewer_prompt(
            draft_fingerprint=draft.fingerprint(),
            brief=brief,
            evidence=evidence,
            segments=segments,
            lineage={"job_id": self._job_id, "run_id": run_id,
                     "content_id": content_id},
        )
        prompt_fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        resume = self._resume_intent
        execution_ref = (
            resume.execution_ref if resume is not None else
            f"{self._job_id}:{LogicalModelRole.ARTICLE_REVIEWER.value}:{attempt_no}"
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

            # 1. Uncertain reservations are reconciliation items, never retries.
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

            # 2. One ARTICLE budget, shared with the writer.
            ceiling = self.max_legal_cost(authority)

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

        # 4. Exactly one provider call.
        try:
            self.provider_calls += 1
            raw = self._adapter.execute(ControlledProviderRequest(
                technical_model_id=authority.technical_model_id,
                system_prompt=_SYSTEM,
                user_prompt=prompt,
                max_output_tokens=REVIEWER_MAX_OUTPUT_TOKENS,
                timeout_seconds=self._timeout_seconds,
                inference_config=ARTICLE_REVIEWER_INFERENCE_CONFIG,
                stream_response=True,
            ))
        except BaseException as exc:
            self._settle(
                execution_ref, authority, run_id, content_id, attempt_no,
                outcome="NEEDS_VERIFICATION",
                failure_kind="REVIEWER_RESULT_UNKNOWN",
                usage=None, returned_model_id=None,
                detail=f"{type(exc).__name__}", stop_reason=None,
                provider_request_id=None,
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

        # 5. Identity and disabled-feature gates, then the structured contract.
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
            entries, document_review = parse_reviewer_response(
                raw.text,
                segments=segments,
                allowed_evidence_ids=frozenset(
                    item.confirmed_claim_id for item in evidence
                ),
            )
            self.last_document_review = document_review
        except (ControlledAdapterError, ProductionReviewerError) as exc:
            self._settle(
                execution_ref, authority, run_id, content_id, attempt_no,
                outcome="FAILURE", failure_kind=getattr(exc, "code", "REVIEWER_FAILED"),
                usage=usage, returned_model_id=raw.returned_model_id,
                detail=str(exc)[:200],
                stop_reason=raw.stop_reason,
                provider_request_id=raw.provider_request_id,
                diagnostic_artifact=safe_reviewer_response_artifact(raw.text),
            )
            raise

        self._settle(
            execution_ref, authority, run_id, content_id, attempt_no,
            outcome="SUCCESS", failure_kind=None, usage=usage,
            returned_model_id=raw.returned_model_id,
            detail=None, entry_count=len(entries),
            entries=entries, document_review=document_review,
            stop_reason=raw.stop_reason,
            provider_request_id=raw.provider_request_id,
        )
        return entries

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
    "REVIEWER_MAX_INPUT_TOKENS",
    "REVIEWER_MAX_OUTPUT_TOKENS",
    "REVIEWER_VERSION",
    "ReviewerRequestIntent",
    "assemble_reviewer_prompt",
    "parse_reviewer_response",
    "safe_reviewer_response_artifact",
]
