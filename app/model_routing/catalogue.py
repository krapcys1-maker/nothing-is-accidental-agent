"""Owner-verified Anthropic catalogue snapshot.

Every value here was checked by the owner/coordinator in official Anthropic
material on 2026-08-09 and handed to this repository as data.  Nothing in this
module performs discovery, reads the network, or infers a model ID from a name.

Two things this module deliberately does NOT do:

* It does not qualify anything.  Knowing a model's ID and price says nothing
  about whether it passes this project's regression suite, so every entry
  registered from here starts ``UNQUALIFIED`` and can only reach ``PASS``
  through a separately approved controlled qualification run.
* It does not decide which role uses which model.  Roles map to *families*
  (``app.model_routing.contracts.ROLE_FAMILY``); this module supplies the
  concrete version inside a family, so a later model can replace it without
  touching a single role.

C5 runtime shape asserted by the persisted catalogue evidence: explicit global
inference and Standard Tier, no fast mode, no prompt caching, no server-side web
tools, no Batch API, no provider Fallback API.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.llm.anthropic_provider_contract import (
    CONTROLLED_INFERENCE_GEO,
    CONTROLLED_SERVICE_TIER,
    EXPECTED_RETURNED_INFERENCE_GEO,
    EXPECTED_RETURNED_SERVICE_TIER,
)

from app.model_routing.contracts import (
    AvailabilityState,
    CatalogueCandidate,
    ModelFamily,
    ModelPricingProfile,
    PriceDimensions,
    PricingVerificationState,
    fingerprint,
)

PROVIDER = "ANTHROPIC"
CATALOGUE_REF = "anthropic-owner-verified-2026-08-09"
CATALOGUE_SOURCE = "OWNER_VERIFIED_PROVIDER_DOCUMENTATION"
VERIFIED_AT = "2026-08-09T00:00:00.000000+00:00"
PROVIDER_PREFLIGHT_AT = "2026-08-10T00:00:00.000000+00:00"
PRICING_UNIT = "usd_per_mtok__web_search_per_1k"
PRICING_CURRENCY = "USD"

# The exact runtime configuration the owner verified these prices against.
# C5 runs with every optional provider feature off, so any of them appearing in
# a real response contradicts this evidence instead of being priced silently.
VERIFIED_RUNTIME_SHAPE: Mapping[str, object] = MappingProxyType({
    "inference_geography": CONTROLLED_INFERENCE_GEO,
    "service_tier_request": CONTROLLED_SERVICE_TIER,
    "expected_response_inference_geo": EXPECTED_RETURNED_INFERENCE_GEO,
    "expected_response_service_tier": EXPECTED_RETURNED_SERVICE_TIER,
    "fast_mode": False,
    "prompt_caching": False,
    "server_web_tools": False,
    "batch_api": False,
    "provider_fallback_api": False,
})

# Sonnet 5 uses the two published calendar-date price regimes. The profiles can
# change at the local normalized boundary without leaving the role unpriced.
# The exact UTC timestamp is deterministic LOCAL POLICY normalization. Anthropic
# publishes only the dates: promo through 2026-08-31, standard from 2026-09-01.
SONNET_PROMO_UNTIL = "2026-08-31T23:59:59.999999+00:00"
SONNET_STANDARD_FROM = "2026-09-01T00:00:00.000000+00:00"


@dataclass(frozen=True)
class CatalogueEntry:
    """One owner-verified model plus every price list approved for it."""

    family: ModelFamily
    logical_version: str
    technical_model_id: str
    pricing: tuple[ModelPricingProfile, ...]
    notes: str

    @property
    def default_pricing_ref(self) -> str:
        return self.pricing[0].pricing_ref

    def candidate(self) -> CatalogueCandidate:
        return CatalogueCandidate(
            provider=PROVIDER,
            family=self.family,
            logical_version=self.logical_version,
            technical_model_id=self.technical_model_id,
            # Owner-verified availability of the published model; still not a
            # statement about qualification.
            availability_state=AvailabilityState.AVAILABLE,
            pricing_ref=self.default_pricing_ref,
            discovered_at=VERIFIED_AT,
            catalogue_ref=CATALOGUE_REF,
        )

    def evidence_payload(self, registry_id: str) -> dict[str, object]:
        return {
            "evidence_ref": f"catalogue-{registry_id}",
            "model_registry_id": registry_id,
            "provider": PROVIDER,
            "technical_model_id": self.technical_model_id,
            "source": CATALOGUE_SOURCE,
            "verified_at": VERIFIED_AT,
            "family": self.family.value,
            "logical_version": self.logical_version,
            "pricing_refs": [item.pricing_ref for item in self.pricing],
            "runtime_shape": dict(VERIFIED_RUNTIME_SHAPE),
            "notes": self.notes,
        }

    def evidence_fingerprint(self, registry_id: str) -> str:
        return fingerprint(self.evidence_payload(registry_id))


def _profile(
    pricing_ref: str,
    technical_model_id: str,
    *,
    input_per_mtok: str,
    output_per_mtok: str,
    cache_read_per_mtok: str,
    cache_write_per_mtok: str,
    effective_from: str | None = None,
    effective_until: str | None = None,
) -> ModelPricingProfile:
    return ModelPricingProfile(
        pricing_ref=pricing_ref,
        provider=PROVIDER,
        technical_model_id=technical_model_id,
        verification_state=PricingVerificationState.VERIFIED,
        currency=PRICING_CURRENCY,
        unit=PRICING_UNIT,
        prices=PriceDimensions.from_mapping({
            "input_per_mtok": input_per_mtok,
            "output_per_mtok": output_per_mtok,
            "cache_read_per_mtok": cache_read_per_mtok,
            "cache_write_per_mtok": cache_write_per_mtok,
            # C5 never enables provider web search. The dimension still has to
            # carry a real rate so a non-zero count can never be priced as free.
            "web_search_per_1k": "10",
        }),
        verified_at=VERIFIED_AT,
        effective_from=effective_from,
        effective_until=effective_until,
    )


FABLE_5 = CatalogueEntry(
    family=ModelFamily.FABLE,
    logical_version="5",
    technical_model_id="claude-fable-5",
    pricing=(
        _profile(
            "anthropic-fable-5-standard-2026-08",
            "claude-fable-5",
            input_per_mtok="10",
            output_per_mtok="50",
            # Published cache rates are recorded for completeness; C5 disables
            # prompt caching, so a non-zero cache count is a contradiction to be
            # verified, never a free ride.
            cache_read_per_mtok="1",
            cache_write_per_mtok="12.5",
        ),
    ),
    notes=(
        "Explicit global inference and standard_only request tier; expected "
        "returned tier standard; caching disabled for C5. Fable requires a "
        "separate, approval-scoped 30-day-retention acceptance before a real call."
    ),
)

OPUS_5 = CatalogueEntry(
    family=ModelFamily.OPUS,
    logical_version="5",
    technical_model_id="claude-opus-5",
    pricing=(
        _profile(
            "anthropic-opus-5-standard-2026-08",
            "claude-opus-5",
            input_per_mtok="5",
            output_per_mtok="25",
            cache_read_per_mtok="0.5",
            cache_write_per_mtok="6.25",
        ),
    ),
    notes=(
        "Explicit global inference and standard_only request tier; expected "
        "returned tier standard; fast mode and caching disabled."
    ),
)

SONNET_5 = CatalogueEntry(
    family=ModelFamily.SONNET,
    logical_version="5",
    technical_model_id="claude-sonnet-5",
    pricing=(
        _profile(
            "anthropic-sonnet-5-promotional-until-2026-08-31",
            "claude-sonnet-5",
            input_per_mtok="2",
            output_per_mtok="10",
            cache_read_per_mtok="0.2",
            cache_write_per_mtok="2.5",
            effective_until=SONNET_PROMO_UNTIL,
        ),
        _profile(
            "anthropic-sonnet-5-standard-from-2026-09-01",
            "claude-sonnet-5",
            input_per_mtok="3",
            output_per_mtok="15",
            cache_read_per_mtok="0.3",
            cache_write_per_mtok="3.75",
            effective_from=SONNET_STANDARD_FROM,
        ),
    ),
    notes=(
        "Provider confirms promotional pricing through 2026-08-31 and standard "
        "pricing from 2026-09-01. The exact UTC boundary is local deterministic "
        "policy normalization, not a provider-published timestamp."
    ),
)

OWNER_VERIFIED_CATALOGUE: tuple[CatalogueEntry, ...] = (FABLE_5, OPUS_5, SONNET_5)

CATALOGUE_BY_FAMILY: Mapping[ModelFamily, CatalogueEntry] = MappingProxyType({
    entry.family: entry for entry in OWNER_VERIFIED_CATALOGUE
})
