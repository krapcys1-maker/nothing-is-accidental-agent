"""Realny klient Anthropic. Używany tylko poza dry_run (DRY_RUN=false).

W walking skeleton NIE jest wywoływany. Pakiet `anthropic` importowany leniwie,
żeby dry_run i testy nie wymagały tej zależności.
"""
from __future__ import annotations

import json

from app.llm.base import LLMClient, TopicGenerationResult, TopicIdea, Usage
from app.models import Account

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


class AnthropicLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self._api_key = api_key

    def generate_and_score_topics(self, account: Account, count: int) -> TopicGenerationResult:
        try:
            import anthropic  # leniwy import — tylko gdy realnie wołamy API
        except ImportError as exc:  # pragma: no cover - zależność opcjonalna
            raise RuntimeError(
                "Pakiet 'anthropic' nie jest zainstalowany. Zainstaluj extras: "
                "pip install -e .[llm] (potrzebne tylko poza dry_run)."
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_prompt(account, count)}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        payload = json.loads(text)
        ideas = [
            TopicIdea(
                title=item["title"],
                question=item.get("question", ""),
                score_breakdown={k: float(v) for k, v in item.get("score_breakdown", {}).items()},
            )
            for item in payload.get("topics", [])
        ]
        usage = Usage(
            input_tokens=getattr(message.usage, "input_tokens", 0),
            output_tokens=getattr(message.usage, "output_tokens", 0),
            cache_read_tokens=getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
        )
        return TopicGenerationResult(ideas=ideas, usage=usage, model=self.model)
