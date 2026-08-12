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

from decimal import Decimal
import json
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
    DraftClaimSegment,
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
from app.llm.anthropic_provider_contract import OPUS_5_MODEL_ID
from app.model_routing.contracts import LogicalModelRole, ModelFamily

REVIEWER_VERSION = "production_article_reviewer_opus_v2"
REVIEWER_TIMEOUT_SECONDS = 300.0
REVIEWER_MAX_OUTPUT_TOKENS = 8_192
REVIEWER_MAX_INPUT_TOKENS = 23_808

_SYSTEM = """You are the independent claim reviewer for the anonymous editorial
brand Nothing Is Accidental. You did not write this draft and you never rewrite
it. You only account for what it claims.

For every supplied draft segment decide exactly one classification:

EVIDENCE_GROUNDED_FACT - the segment asserts a fact about the world whose full
scope is supported by the supplied frozen evidence. List every confirmed_claim_id
that supports it. Only these ids exist; never invent one.
ARGUMENT_OR_INFERENCE - reasoning, interpretation or a conclusion drawn from the
allowed material. It must contain no external fact of its own.
NON_FACTUAL_PROSE - framing, transition or rhetoric that asserts nothing factual
and needs no evidence.

Judge meaning, not word overlap. A sentence that reuses the evidence wording but
widens its scope is not grounded. A sentence that shares no words with the
evidence may still be grounded by it.

Set outcome to PASS when the segment is acceptable as classified, and BLOCK when
it is not. Set contains_external_fact to false for ARGUMENT_OR_INFERENCE and
NON_FACTUAL_PROSE, and to true only when a segment smuggles in an outside fact.

Return exactly one JSON object and nothing else. No Markdown, no code fence, no
prose before or after it. Return exactly one entry per supplied segment_id,
copying each segment_id and segment_fingerprint verbatim. Keep each reason to
at most 12 words."""


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
                "with: segment_id, segment_fingerprint, classification "
                "(EVIDENCE_GROUNDED_FACT | ARGUMENT_OR_INFERENCE | "
                "NON_FACTUAL_PROSE), evidence_ids (array of allowed "
                "confirmed_claim_id values; empty unless grounded), reason "
                "(non-empty string of at most 12 words), outcome (PASS | BLOCK), "
                "contains_external_fact (boolean)"
            ),
        },
    }
    return canonical_json(payload)


def parse_reviewer_response(
    text: object, *, segments: tuple[DraftClaimSegment, ...],
) -> tuple[ClaimAccountingEntry, ...]:
    """Map the transport response onto the existing claim-accounting contract.

    This validates structure only.  Coverage, identity and evidence-scope
    invariants stay where they already live, in the quality gate.
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
    if type(payload) is not dict or set(payload) != {"reviewer_version", "entries"}:
        raise ProductionReviewerError(
            "REVIEWER_RESPONSE_CONTRACT_INVALID",
            "The reviewer response must contain exactly reviewer_version and entries.",
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
    known = {segment.segment_id for segment in segments}
    required_fields = {
        "segment_id", "segment_fingerprint", "classification", "evidence_ids",
        "reason", "outcome", "contains_external_fact",
    }
    entries: list[ClaimAccountingEntry] = []
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
                or len(raw["reason"].split()) > 12
            ):
                raise TypeError(
                    "reason must be a non-empty canonical string of at most 12 words"
                )
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
        entries.append(entry)
    return tuple(entries)


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
        self._clock = clock or SystemClock()
        self.provider_calls = 0

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
        execution_ref = (
            f"{self._job_id}:{LogicalModelRole.ARTICLE_REVIEWER.value}:"
            f"{attempt_no}"
        )

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

        # 3. Durable IN_FLIGHT, then the durable external-effect stamp, both
        #    committed before the transport can be reached at all.
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

        prompt = assemble_reviewer_prompt(
            draft_fingerprint=draft.fingerprint(),
            brief=brief,
            evidence=evidence,
            segments=segments,
            lineage={"job_id": self._job_id, "run_id": run_id,
                     "content_id": content_id},
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
            ))
        except BaseException as exc:
            self._settle(
                execution_ref, authority, run_id, content_id, attempt_no,
                outcome="NEEDS_VERIFICATION",
                failure_kind="REVIEWER_RESULT_UNKNOWN",
                usage=None, returned_model_id=None,
                detail=f"{type(exc).__name__}",
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
            entries = parse_reviewer_response(raw.text, segments=segments)
        except (ControlledAdapterError, ProductionReviewerError) as exc:
            self._settle(
                execution_ref, authority, run_id, content_id, attempt_no,
                outcome="FAILURE", failure_kind=getattr(exc, "code", "REVIEWER_FAILED"),
                usage=usage, returned_model_id=raw.returned_model_id,
                detail=str(exc)[:200],
            )
            raise

        self._settle(
            execution_ref, authority, run_id, content_id, attempt_no,
            outcome="SUCCESS", failure_kind=None, usage=usage,
            returned_model_id=raw.returned_model_id,
            detail=None, entry_count=len(entries),
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
    ) -> None:
        """Settle the reserved row once, pricing usage from the frozen profile."""
        cost = authority.settle(usage) if usage is not None else None
        payload: dict[str, Any] = {"reviewer_version": REVIEWER_VERSION}
        if detail is not None:
            payload["detail"] = detail
        if entry_count is not None:
            payload["entry_count"] = entry_count
        if usage is None:
            payload["usage_known"] = False
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
    "ProductionArticleReviewer",
    "ProductionReviewerError",
    "REVIEWER_MAX_INPUT_TOKENS",
    "REVIEWER_MAX_OUTPUT_TOKENS",
    "REVIEWER_VERSION",
    "assemble_reviewer_prompt",
    "parse_reviewer_response",
]
