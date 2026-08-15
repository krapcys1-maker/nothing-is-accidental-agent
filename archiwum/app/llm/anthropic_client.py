"""Realny klient Anthropic. Używany tylko poza dry_run (DRY_RUN=false).

W walking skeleton NIE jest wywoływany. Pakiet `anthropic` importowany leniwie,
żeby dry_run i testy nie wymagały tej zależności.
"""
from __future__ import annotations

import json
import math
from typing import Callable

from app.llm.anthropic_controlled_adapter import (
    ControlledAdapterError,
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
    assert_returned_model_identity,
)
from app.llm.anthropic_provider_contract import (
    TOPIC_GENERATION_INFERENCE_CONFIG,
    returned_provenance_mismatch,
)
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
from app.content.cost_estimate import (
    TOPIC_GENERATION_MAX_INPUT_TOKENS,
    TOPIC_GENERATION_MAX_OUTPUT_TOKENS,
)
from app.research.base import (
    DurableAttemptActivationCallback,
    DurableAttemptAssertionCallback,
    DurableAttemptContextCallback,
    DurableProviderBoundary,
)

TopicCaller = Callable[[Account, int], tuple[str, Usage]]

TOPIC_MAX_OUTPUT_TOKENS = 4096
# Measured against the durable ledger rather than guessed: the four topic
# generations that succeeded took 26, 42, 44 and 53 seconds. A 60 second
# timeout left seven seconds of margin on the worst of them, and a slightly
# longer prompt then crossed it - the client gave up at 61 seconds on a request
# the provider may well have completed and charged for, which is the worst
# possible outcome. It reserves, it pays, and it keeps nothing.
#
# A timeout is a guard against hanging forever, not a performance budget, so it
# belongs far above the observed distribution instead of inside it.
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 420.0
SDK_MAX_RETRIES = 0

_SYSTEM = (
    "You are a topic scout for the English-language Substack 'Nothing Is Accidental', "
    "which explains the hidden systems, incentives and decisions behind ordinary things. "
    "Return only valid JSON."
)


def _build_prompt(
    account: Account,
    count: int,
    editorial_history: tuple[dict[str, str], ...] = (),
) -> str:
    niche = ", ".join(account.niche) or "hidden everyday systems"
    history_json = json.dumps(
        list(editorial_history), ensure_ascii=False, separators=(",", ":"),
    )
    return (
        f"Propose {count} article topic ideas in the niche: {niche}. "
        "For each, return an object with keys: title, question, and score_breakdown. "
        # The question is not the article's thesis.  It is the string a web
        # search actually runs, so it decides which sources exist to be found.
        # This was measured, twice, on our own failed topics: asking "why did
        # cities switch to cold white LEDs within a few years" returned lighting
        # vendors and local news, while asking about the Department of Energy's
        # street lighting consortium reports on the same subject returned four
        # energy.gov documents plus osti.gov - enough to clear our own floors.
        # Asking "why is the supermarket car park empty six days a week"
        # returned Quora, Goodreads and a fiction newsletter; asking about the
        # ITE Parking Generation manual returned the manual itself and the
        # academic critique of it.  Neither topic was bad.  Both were phrased so
        # that no institution could answer them, and the research stage was then
        # rejected as NO_PRIMARY_SOURCE or WEAK_SOURCES at a cost of about
        # 0.89 USD per attempt.
        "Write each question so that it points at a body that had to write its "
        "reasoning down. Name that body, or name the document family, inside the "
        "question itself: an agency manual, a standard, a rulemaking preamble, a "
        "regulator's filing, an official statistic, a first-party technical "
        "guide. A question no institution has answered in public cannot be "
        "researched, however good it sounds. "
        "Do NOT assert the answer. No naming of the motive, no 'not because X "
        "but because Y', and no quantity, percentage, timeframe or proportion - "
        "you have read no sources yet, so any number you write is invented, and "
        "the research stage will spend real money failing to confirm it. "
        "This does not make topics dull. The documented figures are routinely "
        "stranger than invented ones, and the article's hook is harvested later, "
        "by the writer, out of the record. Your job is to predict WHERE a "
        "surprising number lives, not to guess what it says. "
        "The phenomenon itself must still be concrete, ordinary and immediately "
        "recognisable - something a reader has stood in front of. "
        "The title is an internal handle, not the published headline, so let it "
        "describe the phenomenon rather than announce a conclusion. "
        "Do not repeat or paraphrase an editorial angle in this bounded history: "
        f"{history_json}. "
        "score_breakdown must contain these keys, each 0.0-1.0: curiosity, source_quality, "
        "non_obvious, universality, discussion_potential, visual_potential, originality. "
        # source_quality is the one score with a downstream consequence: a topic
        # the research stage cannot source costs about 0.89 USD to discover that.
        # Left undefined the model scores it as a vibe, so it is pinned to the
        # only question that predicts the cost.
        "Score source_quality as your honest confidence that a specific, named "
        "institutional document answering this question exists AND can be read "
        "for free as HTML by a plain HTTP client. Both halves matter: the "
        "fetcher cannot read PDFs, cannot log in and cannot pay. A paywalled "
        "standard - BSI, ISO, IEC, ASTM, DIN and the like - scores 0.3 however "
        "authoritative it is, because we will never see inside it. A record "
        "published only as a PDF scores no higher than 0.5 unless the issuing "
        "body also publishes the substance on an HTML page. Statute and "
        "regulations published in full HTML by a national legislation service, "
        "and agency guidance published as web pages, are the 0.9 cases. Do not "
        "inflate it; a topic scored honestly low costs us nothing, while a topic "
        "scored dishonestly high costs a paid research run. "
        # A live run proved this half was missing: a question that named the
        # Department for Transport guidance and the British Standards exactly
        # scored 0.9, and returned zero primary sources - the guidance is a PDF
        # and the standards are behind a paywall. Naming the document is not the
        # same as being able to read it.
        "Prefer questions whose answer lives in a document that is free and in "
        "HTML. If the only authority is paywalled, ask a question that a freely "
        "published body has also answered. "
        # Free and in HTML turned out not to be enough. A run aimed squarely at
        # eCFR fetched ten pages and five of them were the same block notice:
        # "Due to aggressive automated scraping of FederalRegister.gov and
        # eCFR.gov, programmatic access to these sites is limited to access to
        # our extensive developer APIs." The corpus reported ten successes and
        # held one usable source. The block is respected, not worked around, so
        # the scout has to steer around it instead.
        "There is a third requirement and it is not obvious: the site must "
        "permit ordinary automated reading. eCFR.gov and FederalRegister.gov "
        "serve a CAPTCHA to programmatic requests and offer an API instead, so "
        "a question whose only answer is a CFR part will come back empty however "
        "authoritative it is - score those 0.3 and prefer the agency that WROTE "
        "the rule, which usually explains it in plain web pages: the "
        "commission, department or administration's own guidance, FAQ, "
        "enforcement policy or press material. Legislation and guidance "
        "published directly by a government or regulator on its own site are "
        "the reliable 0.9 cases. "
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
        topic_max_tokens: int = TOPIC_MAX_OUTPUT_TOKENS,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds musi być skończoną liczbą dodatnią.")
        if (
            isinstance(topic_max_tokens, bool)
            or not isinstance(topic_max_tokens, int)
            or topic_max_tokens < 1
        ):
            raise ValueError("topic_max_tokens musi być dodatnią liczbą całkowitą.")
        self.model = model
        self._api_key = api_key
        self._caller = caller or self._default_caller
        self._uses_default_caller = caller is None
        self._timeout_seconds = timeout_seconds
        self._topic_max_tokens = topic_max_tokens
        self._estimated_attempt_cost = 0.0
        self._durable_control_configured = False
        self._durable_boundary = DurableProviderBoundary(provider_label="Real Anthropic topic")
        self._editorial_history: tuple[dict[str, str], ...] = ()

    def set_editorial_history(
        self, history: tuple[dict[str, str], ...],
    ) -> None:
        """Install the bounded durable snapshot used by the next topic call."""
        if not isinstance(history, tuple) or len(history) > 40:
            raise ValueError("Editorial history must be a bounded tuple.")
        allowed = {"title", "question", "central_thesis", "status"}
        if any(not isinstance(row, dict) or set(row) != allowed for row in history):
            raise ValueError("Editorial history has an unsupported prompt shape.")
        self._editorial_history = tuple(dict(row) for row in history)

    def configure_durable_attempt_control(
        self,
        *,
        context_callback: DurableAttemptContextCallback | None,
        activation_callback: DurableAttemptActivationCallback | None,
        assertion_callback: DurableAttemptAssertionCallback | None,
        estimated_attempt_cost: float = 0.0,
    ) -> None:
        """Installs the non-optional paid-request contract for the SDK path.

        Once configured, the boundary governs an INJECTED caller too: a fake
        transport in tests then exercises the identical durable lifecycle
        (reservation, REQUEST_STARTED, final assertion) as the real SDK.
        """
        self._durable_boundary.configure(
            context_callback=context_callback,
            activation_callback=activation_callback,
            assertion_callback=assertion_callback,
        )
        self._estimated_attempt_cost = float(estimated_attempt_cost)
        self._durable_control_configured = (
            context_callback is not None and activation_callback is not None
        )

    def _requires_durable_provider_context(self) -> bool:
        return self._uses_default_caller or self._durable_control_configured

    def _activate_durable_attempt(self) -> None:
        self._durable_boundary.activate(
            stage="topics", attempt_no=1,
            estimated_attempt_cost=self._estimated_attempt_cost,
        )

    def _assert_active_durable_provider_attempt(self) -> str:
        return self._durable_boundary.assert_immediately_before_provider_call()

    def generate_and_score_topics(self, account: Account, count: int) -> TopicGenerationResult:
        prompt = _build_prompt(account, count, self._editorial_history)
        # No project tokenizer is available at this boundary.  3.5 chars/token
        # is the repository's established conservative estimator; include both
        # system and user prompt before any durable provider attempt exists.
        estimated_input_tokens = math.ceil((len(_SYSTEM) + len(prompt)) / 3.5)
        if (
            estimated_input_tokens > TOPIC_GENERATION_MAX_INPUT_TOKENS
            or self._topic_max_tokens > TOPIC_GENERATION_MAX_OUTPUT_TOKENS
        ):
            raise LLMProviderError(
                "TOPIC_GENERATION_ENVELOPE_EXCEEDED before provider attempt.",
                model=self.model,
            )
        durable = self._requires_durable_provider_context()
        if durable:
            self._activate_durable_attempt()
        try:
            if durable and not self._uses_default_caller:
                # The production caller makes this assertion inside itself after
                # constructing the SDK.  An injected caller IS the request
                # boundary stand-in, so it is asserted directly before invocation.
                self._assert_active_durable_provider_attempt()
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

        adapter = ControlledAnthropicAdapter(
            api_key_provider=lambda: self._api_key,
            sdk_factory=lambda **kwargs: anthropic.Anthropic(**kwargs),
        )
        try:
            request_id = self._assert_active_durable_provider_attempt()
            raw = adapter.execute(ControlledProviderRequest(
                technical_model_id=self.model,
                system_prompt=_SYSTEM,
                user_prompt=_build_prompt(account, count, self._editorial_history),
                max_output_tokens=self._topic_max_tokens,
                timeout_seconds=self._timeout_seconds,
                inference_config=TOPIC_GENERATION_INFERENCE_CONFIG,
                extra_headers={"Idempotency-Key": request_id},
            ))
        except anthropic.APIError as exc:
            raise LLMProviderError(
                f"Błąd providera Anthropic przed otrzymaniem odpowiedzi: {exc}",
                model=self.model,
            ) from exc
        except ControlledAdapterError as exc:
            raise LLMProviderError(
                f"Kontrolowany kontrakt Anthropic odrzucił request: {exc}",
                model=self.model,
            ) from exc

        # Usage is constructed immediately after the provider response and
        # before inspecting/parsing its text, so a billed malformed response
        # cannot disappear from the workflow's ledger.
        usage = Usage(
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            cache_read_tokens=raw.cache_read_tokens,
            cache_write_tokens=raw.cache_write_tokens,
            web_search_requests=raw.web_search_requests,
            thinking_tokens=raw.thinking_tokens,
        )
        try:
            assert_returned_model_identity(
                requested_model_id=self.model,
                returned_model_id=raw.returned_model_id,
            )
            provenance_error = returned_provenance_mismatch(
                inference_geo=raw.inference_geo,
                service_tier=raw.service_tier,
            )
            if provenance_error:
                raise ControlledAdapterError(
                    provenance_error,
                    "Provider-returned execution provenance violates the frozen contract.",
                )
        except ControlledAdapterError as exc:
            raise LLMProviderError(
                f"Kontrolowany kontrakt Anthropic odrzucił odpowiedź: {exc}",
                usage=usage,
                model=self.model,
            ) from exc
        return raw.text, usage
