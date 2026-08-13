"""Schema-aware durable execution intent for autonomous topic generation.

Ten kontrakt jest bliźniakiem `app.research.durable_intent`, ale opisuje jedyny
płatny request, który z definicji NIE MOŻE mieć `topic_id`: temat jeszcze nie
istnieje i powstanie dopiero z odpowiedzi modelu.  Wszystkie prymitywy walidacji
(pieniądze, liczby całkowite, tekst, profil cennika, fingerprint) są IMPORTOWANE
z kontraktu research — jeden kanon, zero drugiej implementacji.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from types import SimpleNamespace
from typing import Mapping

from app.core.config import Settings
from app.core.pricing import REQUIRED_CURRENCY, REQUIRED_UNIT
from app.llm.anthropic_provider_contract import (
    TOPIC_GENERATION_INFERENCE_CONFIG,
    AnthropicInferenceConfig,
    inference_config_from_payload,
)
from app.research.cost_estimator import estimate_no_search_call_usd
from app.research.durable_intent import (
    DurableExecutionIntentError,
    SENTINEL_PRICING_PROFILE_ID,
    SENTINEL_PRICING_PROFILE_VERSION,
    _bounded_max_tokens,
    _integer,
    _money,
    _pricing_fingerprint,
    _pricing_profile,
    _text,
    _text_list,
    canonical_execution_intent_json,
)
from app.research.output_contract import CONSERVATIVE_CHARS_PER_TOKEN

_SCHEMA = "durable_topic_generation_intent_v1"
_PIPELINE_VERSION = "topic_generation_pipeline_v1"
_PROMPT_CONTRACT_VERSION = "anthropic_topics_v1"

# Provider stage jest CZĘŚCIĄ tożsamości requestu (`<job_id>:topics:1`) i musi
# zgadzać się ze stage'em, który `AnthropicLLMClient` aktywuje na durable
# boundary.  Zmiana tej stałej zmienia tożsamość requestu — nowa decyzja.
PROVIDER_STAGE = "topics"
TOPIC_GENERATION_EXECUTION = "durable_topic_generation_v1"
TOPIC_GENERATION_WORKFLOW = "TOPIC_GENERATION"

# Zamknięty kontrakt liczności kandydatów: dolna granica trzyma sensowny batch,
# górna jest sufitem zgodnym z `TOPIC_MAX_OUTPUT_TOKENS` i kontraktem promptu.
MIN_CANDIDATE_COUNT = 1
MAX_CANDIDATE_COUNT = 10

# Pinowany budżet znaków promptu POZA niszą konta (system + instrukcje kontraktu
# + nagłówki).  Test kontraktowy dowodzi, że realny szablon promptu tematów z
# polami na granicach mieści się w tym budżecie.  Przeliczenie znaki->tokeny
# używa ISTNIEJĄCEJ konserwatywnej stałej output_contract (3.5 znaka/token).
TOPIC_PROMPT_OVERHEAD_CHARS = 2000
MAX_SCORE_DIMENSIONS = 32


def topic_generation_job_id(operation_key: object) -> str:
    """Deterministyczna tożsamość joba wspólna dla enqueue i zgody L1."""
    canonical_key = _text(operation_key, field="operation_key")
    idempotency_key = topic_generation_idempotency_key(canonical_key)
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return f"topic-generation-{digest}"


def topic_generation_idempotency_key(operation_key: object) -> str:
    """Jedyna postać klucza idempotencji publicznego enqueue tematów."""
    return f"topic-generation:{_text(operation_key, field='operation_key')}"


def _score_dimensions(value: object) -> list[str]:
    """Zamknięty, deterministycznie uporządkowany zbiór wymiarów scoringu."""
    names = _text_list(value, field="score_dimensions")
    if not names:
        raise DurableExecutionIntentError(
            "score_dimensions must contain at least one dimension.",
            code="SCORE_DIMENSIONS_INVALID",
        )
    if len(names) > MAX_SCORE_DIMENSIONS:
        raise DurableExecutionIntentError(
            f"score_dimensions exceeds the closed maximum of {MAX_SCORE_DIMENSIONS}.",
            code="SCORE_DIMENSIONS_INVALID",
        )
    if len(set(names)) != len(names):
        raise DurableExecutionIntentError(
            "score_dimensions must not repeat a dimension.",
            code="SCORE_DIMENSIONS_INVALID",
        )
    if names != sorted(names):
        raise DurableExecutionIntentError(
            "score_dimensions must be persisted in ascending order.",
            code="SCORE_DIMENSIONS_INVALID",
        )
    return names


def _candidate_count(value: object) -> int:
    # minimum=0 so that a zero count reports the specific range violation rather
    # than the generic integer-shape error.
    parsed = _integer(value, field="candidate_count", minimum=0)
    if parsed < MIN_CANDIDATE_COUNT or parsed > MAX_CANDIDATE_COUNT:
        raise DurableExecutionIntentError(
            f"candidate_count {parsed} is outside the approved bound "
            f"[{MIN_CANDIDATE_COUNT}, {MAX_CANDIDATE_COUNT}].",
            code="CANDIDATE_COUNT_OUT_OF_RANGE",
        )
    return parsed


def topic_forwarded_context_tokens(prompt_input: Mapping[str, object]) -> int:
    """Deterministyczny, konserwatywny kontrakt znaki->tokeny wejścia promptu."""
    niche = prompt_input["niche"]
    assert isinstance(niche, list)
    total_chars = TOPIC_PROMPT_OVERHEAD_CHARS + len(", ".join(str(item) for item in niche))
    return math.ceil(total_chars / CONSERVATIVE_CHARS_PER_TOKEN)


def _cost_projection(
    *, profile: Mapping[str, str], max_tokens: int,
    prompt_input: Mapping[str, object],
) -> tuple[str, str]:
    # Generowanie tematów jest z definicji bez web search, więc projekcja idzie
    # przez ISTNIEJĄCY kontrakt no-search (jawny człon input + margines >= 50%).
    estimate = estimate_no_search_call_usd(
        SimpleNamespace(pricing=dict(profile)),
        max_output_tokens=max_tokens,
        forwarded_context_tokens=topic_forwarded_context_tokens(prompt_input),
    )
    return (
        _money(estimate.subtotal_usd, field="projected_cost_usd", allow_zero=True),
        _money(estimate.total_usd, field="pessimistic_cost_usd", allow_zero=True),
    )


@dataclass(frozen=True)
class DurableTopicGenerationIntent:
    """Kompletny, zamrożony wsad jednego płatnego requestu generowania tematów.

    Celowo NIE zawiera `topic_id` — jego obecność jest błędem kontraktu, bo
    przed odpowiedzią modelu żaden temat nie istnieje.
    """

    account_id: str
    prompt_input: dict[str, object]
    candidate_count: int
    score_dimensions: list[str]
    stage: str
    cap_usd: str
    provider: str
    model: str
    max_tokens: int
    max_web_searches: int
    timeout_seconds: int
    pricing_profile: dict[str, str]
    pricing_fingerprint: str
    pricing_profile_id: str
    pricing_profile_version: str
    pricing_currency: str
    pricing_unit: str
    projected_cost_usd: str
    pessimistic_cost_usd: str
    pipeline_version: str
    prompt_contract_version: str
    max_retries: int
    inference_config: AnthropicInferenceConfig

    @classmethod
    def from_settings(
        cls, *, settings: Settings, account_id: str, cap_usd: object,
        candidate_count: object, niche: object, model: object,
        max_tokens: object, score_dimensions: object,
        pricing_prices: Mapping[str, object] | None = None,
        pricing_profile_id: object = SENTINEL_PRICING_PROFILE_ID,
        pricing_profile_version: object = SENTINEL_PRICING_PROFILE_VERSION,
        pricing_currency: object = REQUIRED_CURRENCY,
        pricing_unit: object = REQUIRED_UNIT,
    ) -> "DurableTopicGenerationIntent":
        source_prices = settings.pricing if pricing_prices is None else pricing_prices
        profile = _pricing_profile(source_prices)
        canonical_model = _text(model, field="model")
        profile_id = _text(pricing_profile_id, field="pricing_profile_id")
        profile_version = _text(
            pricing_profile_version, field="pricing_profile_version",
        )
        currency = _text(pricing_currency, field="pricing_currency")
        unit = _text(pricing_unit, field="pricing_unit")
        bounded_tokens = _bounded_max_tokens(max_tokens, field="max_tokens")
        prompt_input: dict[str, object] = {
            "niche": _text_list(niche, field="prompt_input.niche"),
        }
        if not prompt_input["niche"]:
            raise DurableExecutionIntentError(
                "prompt_input.niche must contain at least one entry.",
                code="TOPIC_PROMPT_INPUT_INVALID",
            )
        projected, pessimistic = _cost_projection(
            profile=profile, max_tokens=bounded_tokens, prompt_input=prompt_input,
        )
        return cls(
            account_id=_text(account_id, field="account_id"),
            prompt_input=prompt_input,
            candidate_count=_candidate_count(candidate_count),
            score_dimensions=_score_dimensions(score_dimensions),
            stage=PROVIDER_STAGE,
            cap_usd=_money(cap_usd, field="cap_usd"),
            provider="anthropic",
            model=canonical_model,
            max_tokens=bounded_tokens,
            max_web_searches=0,
            timeout_seconds=_integer(
                settings.research_timeout_seconds, field="timeout_seconds", minimum=1,
            ),
            pricing_profile=profile,
            pricing_fingerprint=_pricing_fingerprint(
                profile_id=profile_id, version=profile_version, model=canonical_model,
                currency=currency, unit=unit, profile=profile,
            ),
            pricing_profile_id=profile_id,
            pricing_profile_version=profile_version,
            pricing_currency=currency,
            pricing_unit=unit,
            projected_cost_usd=projected,
            pessimistic_cost_usd=pessimistic,
            pipeline_version=_PIPELINE_VERSION,
            prompt_contract_version=_PROMPT_CONTRACT_VERSION,
            max_retries=0,
            inference_config=TOPIC_GENERATION_INFERENCE_CONFIG,
        )

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, object],
    ) -> "DurableTopicGenerationIntent":
        expected = {
            "schema", "account_id", "workflow", "mode", "cap_usd", "provider",
            "model", "max_tokens", "max_web_searches", "timeout_seconds",
            "pricing_profile", "pricing_fingerprint", "pricing_profile_id",
            "pricing_profile_version", "pricing_currency", "pricing_unit",
            "projected_cost_usd", "pessimistic_cost_usd", "pipeline_version",
            "prompt_contract_version", "max_retries", "stage", "prompt_input",
            "candidate_count", "score_dimensions", "inference_config",
        }
        # Obecność topic_id jest jawnie nazwanym błędem kontraktu, a nie tylko
        # "nieznanym polem": temat nie istnieje przed odpowiedzią modelu.  Ta
        # kontrola musi wyprzedzać ogólne porównanie zbioru pól, żeby diagnoza
        # była jednoznaczna.
        if "topic_id" in payload:
            raise DurableExecutionIntentError(
                "topic generation intent must not carry a topic_id.",
                code="TOPIC_GENERATION_FORBIDS_TOPIC_ID",
            )
        if set(payload) != expected:
            raise DurableExecutionIntentError(
                "durable topic generation intent has unsupported or missing fields.",
                code="MALFORMED_TOPIC_GENERATION_INTENT",
            )
        if (
            payload["schema"] != _SCHEMA
            or payload["workflow"] != TOPIC_GENERATION_WORKFLOW
            or payload["mode"] != "single"
        ):
            raise DurableExecutionIntentError(
                "durable topic generation intent schema/workflow/mode is invalid.",
                code="MALFORMED_TOPIC_GENERATION_INTENT",
            )
        if payload["stage"] != PROVIDER_STAGE:
            raise DurableExecutionIntentError(
                "durable topic generation intent stage is invalid.",
                code="MALFORMED_TOPIC_GENERATION_INTENT",
            )
        prompt_raw = payload["prompt_input"]
        if not isinstance(prompt_raw, Mapping) or set(prompt_raw) != {"niche"}:
            raise DurableExecutionIntentError(
                "prompt_input must contain exactly niche.",
                code="TOPIC_PROMPT_INPUT_INVALID",
            )
        prompt_input: dict[str, object] = {
            "niche": _text_list(prompt_raw["niche"], field="prompt_input.niche"),
        }
        if not prompt_input["niche"]:
            raise DurableExecutionIntentError(
                "prompt_input.niche must contain at least one entry.",
                code="TOPIC_PROMPT_INPUT_INVALID",
            )
        profile_raw = payload["pricing_profile"]
        if not isinstance(profile_raw, Mapping):
            raise DurableExecutionIntentError("pricing_profile must be an object.")
        profile = _pricing_profile(profile_raw)
        pricing_profile_id = _text(
            payload["pricing_profile_id"], field="pricing_profile_id",
        )
        pricing_profile_version = _text(
            payload["pricing_profile_version"], field="pricing_profile_version",
        )
        pricing_currency = _text(payload["pricing_currency"], field="pricing_currency")
        pricing_unit = _text(payload["pricing_unit"], field="pricing_unit")
        model = _text(payload["model"], field="model")
        fingerprint = _text(
            payload["pricing_fingerprint"], field="pricing_fingerprint",
        )
        if fingerprint != _pricing_fingerprint(
            profile_id=pricing_profile_id, version=pricing_profile_version,
            model=model, currency=pricing_currency, unit=pricing_unit,
            profile=profile,
        ):
            raise DurableExecutionIntentError(
                "pricing fingerprint does not match the complete frozen contract."
            )
        max_tokens = _bounded_max_tokens(payload["max_tokens"], field="max_tokens")
        max_web_searches = _integer(
            payload["max_web_searches"], field="max_web_searches", minimum=0,
        )
        if max_web_searches != 0:
            raise DurableExecutionIntentError(
                "topic generation requires max_web_searches=0.",
                code="TOPIC_GENERATION_REQUIRES_ZERO_SEARCHES",
            )
        retries = _integer(payload["max_retries"], field="max_retries", minimum=0)
        if retries != 0:
            raise DurableExecutionIntentError(
                "topic generation requires max_retries=0.",
                code="TOPIC_GENERATION_REQUIRES_ZERO_RETRIES",
            )
        try:
            inference_config = inference_config_from_payload(
                payload["inference_config"], expected_role="TOPIC_GENERATION",
            )
        except ValueError as exc:
            raise DurableExecutionIntentError(
                "durable topic-generation inference config is invalid.",
                code="INFERENCE_CONFIG_MISMATCH",
            ) from exc
        expected_projected, expected_pessimistic = _cost_projection(
            profile=profile, max_tokens=max_tokens, prompt_input=prompt_input,
        )
        projected = _money(
            payload["projected_cost_usd"], field="projected_cost_usd", allow_zero=True,
        )
        pessimistic = _money(
            payload["pessimistic_cost_usd"], field="pessimistic_cost_usd",
            allow_zero=True,
        )
        if (projected, pessimistic) != (expected_projected, expected_pessimistic):
            raise DurableExecutionIntentError(
                "persisted cost projections do not match frozen pricing and limits."
            )
        return cls(
            account_id=_text(payload["account_id"], field="account_id"),
            prompt_input=prompt_input,
            candidate_count=_candidate_count(payload["candidate_count"]),
            score_dimensions=_score_dimensions(payload["score_dimensions"]),
            stage=PROVIDER_STAGE,
            cap_usd=_money(payload["cap_usd"], field="cap_usd"),
            provider=_text(payload["provider"], field="provider"),
            model=model,
            max_tokens=max_tokens,
            max_web_searches=max_web_searches,
            timeout_seconds=_integer(
                payload["timeout_seconds"], field="timeout_seconds", minimum=1,
            ),
            pricing_profile=profile,
            pricing_fingerprint=fingerprint,
            pricing_profile_id=pricing_profile_id,
            pricing_profile_version=pricing_profile_version,
            pricing_currency=pricing_currency,
            pricing_unit=pricing_unit,
            projected_cost_usd=projected,
            pessimistic_cost_usd=pessimistic,
            pipeline_version=_text(
                payload["pipeline_version"], field="pipeline_version",
            ),
            prompt_contract_version=_text(
                payload["prompt_contract_version"], field="prompt_contract_version",
            ),
            max_retries=retries,
            inference_config=inference_config,
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "schema": _SCHEMA,
            "account_id": self.account_id,
            "prompt_input": {"niche": list(self.prompt_input["niche"])},
            "candidate_count": self.candidate_count,
            "score_dimensions": list(self.score_dimensions),
            "stage": self.stage,
            "workflow": TOPIC_GENERATION_WORKFLOW,
            "mode": "single",
            "cap_usd": self.cap_usd,
            "provider": self.provider,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "max_web_searches": self.max_web_searches,
            "timeout_seconds": self.timeout_seconds,
            "pricing_profile": dict(self.pricing_profile),
            "pricing_fingerprint": self.pricing_fingerprint,
            "pricing_profile_id": self.pricing_profile_id,
            "pricing_profile_version": self.pricing_profile_version,
            "pricing_currency": self.pricing_currency,
            "pricing_unit": self.pricing_unit,
            "projected_cost_usd": self.projected_cost_usd,
            "pessimistic_cost_usd": self.pessimistic_cost_usd,
            "pipeline_version": self.pipeline_version,
            "prompt_contract_version": self.prompt_contract_version,
            "max_retries": self.max_retries,
            "inference_config": self.inference_config.payload(),
        }

    def prompt_account(self):
        """Zbuduj wsad promptu WYŁĄCZNIE z zamrożonego snapshotu, nie z bazy."""
        from app.models import Account, AccountMode

        return Account(
            id=self.account_id,
            display_name=self.account_id,
            mode=AccountMode.RESEARCH_ONLY,
            active=True,
            niche=list(self.prompt_input["niche"]),
        )

    def runtime_pricing(self) -> dict[str, float]:
        return {key: float(value) for key, value in self.pricing_profile.items()}

    def is_supported_by_current_worker(self) -> bool:
        """Czy snapshot jest wykonywalny przez ten single-provider worker."""
        return (
            self.provider == "anthropic"
            and self.pipeline_version == _PIPELINE_VERSION
            and self.prompt_contract_version == _PROMPT_CONTRACT_VERSION
            and self.max_retries == 0
            and self.max_web_searches == 0
            and self.stage == PROVIDER_STAGE
        )


def canonicalize_topic_generation_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Kanonizuje zewnętrzny payload joba; odrzuca każde dodatkowe pole."""
    required = {
        "account_id", "dry_run", "execution", "mode", "max_cost_usd",
        "execution_intent",
    }
    if "execution_intent" not in payload:
        raise DurableExecutionIntentError(
            "durable topic generation payload is missing execution_intent.",
            code="MISSING_EXECUTION_INTENT",
        )
    if set(payload) != required:
        raise DurableExecutionIntentError(
            "durable topic generation payload has unsupported or missing fields.",
            code="MALFORMED_TOPIC_GENERATION_PAYLOAD",
        )
    if payload["execution"] != TOPIC_GENERATION_EXECUTION:
        raise DurableExecutionIntentError(
            f"durable topic generation requires execution={TOPIC_GENERATION_EXECUTION}.",
            code="UNSUPPORTED_EXECUTION_CONTRACT",
        )
    if payload["dry_run"] is not False or payload["mode"] != "single":
        raise DurableExecutionIntentError(
            "durable topic generation execution contract is invalid.",
            code="MALFORMED_TOPIC_GENERATION_PAYLOAD",
        )
    raw_intent = payload["execution_intent"]
    if not isinstance(raw_intent, Mapping):
        raise DurableExecutionIntentError(
            "durable topic generation execution_intent must be an object.",
            code="MALFORMED_TOPIC_GENERATION_PAYLOAD",
        )
    intent = DurableTopicGenerationIntent.from_payload(raw_intent)
    account_id = _text(payload["account_id"], field="account_id")
    cap = _money(payload["max_cost_usd"], field="max_cost_usd")
    if (account_id, cap) != (intent.account_id, intent.cap_usd):
        raise DurableExecutionIntentError(
            "payload identity/cap must match execution_intent.",
            code="MALFORMED_TOPIC_GENERATION_PAYLOAD",
        )
    return {
        "account_id": account_id,
        "dry_run": False,
        "execution": TOPIC_GENERATION_EXECUTION,
        "mode": "single",
        "max_cost_usd": cap,
        "execution_intent": intent.as_payload(),
    }


def frozen_topic_generation_contract(
    payload: Mapping[str, object],
) -> tuple[DurableTopicGenerationIntent, str, str]:
    """Jedno przejście walidacji: (intent, kanoniczny JSON, fingerprint).

    Każdy wywołujący potrzebuje wszystkich trzech wartości naraz, a pełna
    walidacja intentu (fingerprint cennika + ponowna projekcja kosztu) nie jest
    tania — dlatego kanonizacja wykonuje się dokładnie raz.
    """
    canonical = canonicalize_topic_generation_payload(payload)
    raw_intent = canonical["execution_intent"]
    assert isinstance(raw_intent, dict)
    encoded = canonical_execution_intent_json(raw_intent)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return DurableTopicGenerationIntent.from_payload(raw_intent), encoded, fingerprint


def frozen_topic_generation_intent_json(
    payload: Mapping[str, object],
) -> tuple[str, str]:
    """Zwraca (kanoniczny JSON intentu, jego SHA-256) dla jednego payloadu.

    JSON jest dosłownym preimage'em fingerprintu; trwała zgoda L1 przechowuje go
    verbatim, a podłoga SQLite przelicza hash ze składowanego tekstu (0020).
    """
    _, encoded, fingerprint = frozen_topic_generation_contract(payload)
    return encoded, fingerprint


def durable_topic_generation_fingerprint(payload: Mapping[str, object]) -> str:
    """Stabilny fingerprint całego zamrożonego wsadu płatnego requestu."""
    return frozen_topic_generation_intent_json(payload)[1]
