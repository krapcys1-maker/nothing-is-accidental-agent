"""Realny klient Anthropic. Używany tylko poza dry_run (DRY_RUN=false).

W walking skeleton NIE jest wywoływany. Pakiet `anthropic` importowany leniwie,
żeby dry_run i testy nie wymagały tej zależności.
"""
from __future__ import annotations

import json
import math
from typing import Callable

from app.llm.base import (
    LLMClient,
    LLMParseError,
    LLMProviderError,
    LLMResponseError,
    LLMSchemaValidationError,
    TopicGenerationResult,
    TopicIdea,
    Usage,
)
from app.models import Account
from app.research.base import (
    DurableAttemptActivationCallback,
    DurableAttemptAssertionCallback,
    DurableAttemptContextCallback,
    DurableProviderBoundary,
)

TopicCaller = Callable[[Account, int], tuple[str, Usage]]

TOPIC_MAX_OUTPUT_TOKENS = 1500
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 60.0
SDK_MAX_RETRIES = 0

_SYSTEM = (
    "You are a topic scout for the English-language Substack 'Nothing Is Accidental', "
    "which explains the hidden systems, incentives and decisions behind ordinary things. "
    "Return only valid JSON."
)


def _build_prompt(account: Account, count: int) -> str:
    niche = ", ".join(account.niche) or "hidden everyday systems"
    return (
        f"Propose {count} article topic ideas in the niche: {niche}. "
        "For each, return an object with keys: title, question, and score_breakdown. "
        "score_breakdown must contain these keys, each 0.0-1.0: curiosity, source_quality, "
        "non_obvious, universality, discussion_potential, visual_potential, originality. "
        'Respond as JSON: {"topics": [ ... ]}.'
    )


def _strip_outer_code_fence(text: str) -> str:
    """Remove exactly one complete outer Markdown fence, if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    newline = stripped.find("\n")
    if newline == -1:
        raise LLMParseError("Niekompletny Markdown code fence w odpowiedzi tematów.")

    opening = stripped[:newline].rstrip("\r").strip().lower()
    if opening not in {"```", "```json"}:
        raise LLMParseError("Nieobsługiwany Markdown code fence w odpowiedzi tematów.")
    if not stripped.endswith("```"):
        raise LLMParseError("Brak zamykającego Markdown code fence w odpowiedzi tematów.")

    inner = stripped[newline + 1:-3].strip()
    if not inner:
        raise LLMParseError("Pusty Markdown code fence w odpowiedzi tematów.")
    return inner


def _parse_topic_response(text: str) -> list[TopicIdea]:
    """Parse and validate one complete topic-generation JSON response."""
    candidate = _strip_outer_code_fence(text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMParseError(
            f"Niepoprawny JSON odpowiedzi tematów: {exc.msg} "
            f"(linia {exc.lineno}, kolumna {exc.colno})."
        ) from exc

    if not isinstance(payload, dict):
        raise LLMSchemaValidationError("Odpowiedź tematów musi być obiektem JSON.")
    if "topics" not in payload:
        raise LLMSchemaValidationError("Odpowiedź tematów nie zawiera pola 'topics'.")
    items = payload["topics"]
    if not isinstance(items, list):
        raise LLMSchemaValidationError("Pole 'topics' musi być listą.")

    ideas: list[TopicIdea] = []
    for index, item in enumerate(items):
        label = f"topics[{index}]"
        if not isinstance(item, dict):
            raise LLMSchemaValidationError(f"{label} musi być obiektem JSON.")
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            raise LLMSchemaValidationError(f"{label}.title musi być niepustym tekstem.")
        question = item.get("question", "")
        if not isinstance(question, str):
            raise LLMSchemaValidationError(f"{label}.question musi być tekstem.")
        raw_breakdown = item.get("score_breakdown", {})
        if not isinstance(raw_breakdown, dict):
            raise LLMSchemaValidationError(f"{label}.score_breakdown musi być obiektem.")

        breakdown: dict[str, float] = {}
        for key, value in raw_breakdown.items():
            if not isinstance(key, str) or isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise LLMSchemaValidationError(
                    f"{label}.score_breakdown musi zawierać liczbowe oceny."
                )
            score = float(value)
            if not 0.0 <= score <= 1.0:
                raise LLMSchemaValidationError(
                    f"{label}.score_breakdown['{key}'] musi mieścić się w zakresie 0..1."
                )
            breakdown[key] = score

        ideas.append(TopicIdea(
            title=title,
            question=question,
            score_breakdown=breakdown,
        ))
    return ideas


class AnthropicLLMClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        caller: TopicCaller | None = None,
        timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds musi byÄ‡ skoÅ„czonÄ… liczbÄ… dodatniÄ….")
        self.model = model
        self._api_key = api_key
        self._caller = caller or self._default_caller
        self._uses_default_caller = caller is None
        self._timeout_seconds = timeout_seconds
        self._durable_boundary = DurableProviderBoundary(provider_label="Real Anthropic topic")

    def configure_durable_attempt_control(
        self,
        *,
        context_callback: DurableAttemptContextCallback | None,
        activation_callback: DurableAttemptActivationCallback | None,
        assertion_callback: DurableAttemptAssertionCallback | None,
    ) -> None:
        """Installs the non-optional paid-request contract for the SDK path."""
        self._durable_boundary.configure(
            context_callback=context_callback,
            activation_callback=activation_callback,
            assertion_callback=assertion_callback,
        )

    def _activate_durable_attempt(self) -> None:
        self._durable_boundary.activate(
            stage="topics", attempt_no=1, estimated_attempt_cost=0.0,
        )

    def _assert_active_durable_provider_attempt(self) -> str:
        return self._durable_boundary.assert_immediately_before_provider_call()

    def generate_and_score_topics(self, account: Account, count: int) -> TopicGenerationResult:
        if self._uses_default_caller:
            self._activate_durable_attempt()
        try:
            text, usage = self._caller(account, count)
        finally:
            self._durable_boundary.clear()
        try:
            ideas = _parse_topic_response(text)
        except LLMResponseError as exc:
            raise type(exc)(str(exc), usage=usage, model=self.model) from exc
        return TopicGenerationResult(ideas=ideas, usage=usage, model=self.model)

    def _default_caller(self, account: Account, count: int) -> tuple[str, Usage]:
        try:
            import anthropic  # leniwy import — tylko gdy realnie wołamy API
        except ImportError as exc:  # pragma: no cover - zależność opcjonalna
            raise RuntimeError(
                "Pakiet 'anthropic' nie jest zainstalowany. Zainstaluj extras: "
                "pip install -e .[llm] (potrzebne tylko poza dry_run)."
            ) from exc

        # The SDK retries by default. A logical attempt in this application is
        # exactly one provider request, therefore retries are explicitly off.
        client = anthropic.Anthropic(
            api_key=self._api_key,
            max_retries=SDK_MAX_RETRIES,
            timeout=self._timeout_seconds,
        )
        try:
            # The durable assertion deliberately happens after SDK construction
            # and immediately before the externally effective method call.
            request_id = self._assert_active_durable_provider_attempt()
            message = client.messages.create(
                model=self.model,
                max_tokens=TOPIC_MAX_OUTPUT_TOKENS,
                system=_SYSTEM,
                messages=[{"role": "user", "content": _build_prompt(account, count)}],
                timeout=self._timeout_seconds,
                extra_headers={"Idempotency-Key": request_id},
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(
                f"Błąd providera Anthropic przed otrzymaniem odpowiedzi: {exc}",
                model=self.model,
            ) from exc

        # Usage is constructed immediately after the provider response and
        # before inspecting/parsing its text, so a billed malformed response
        # cannot disappear from the workflow's ledger.
        usage = Usage(
            input_tokens=getattr(message.usage, "input_tokens", 0),
            output_tokens=getattr(message.usage, "output_tokens", 0),
            cache_read_tokens=getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return text, usage
