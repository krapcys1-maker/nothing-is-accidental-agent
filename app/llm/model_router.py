"""Wybór modelu na podstawie zadania. Nazwy modeli pochodzą z konfiguracji (.env), nie z kodu."""
from __future__ import annotations

from app.core.config import ConfigError, Settings

_FAST_TASKS = {"topics", "scoring", "note", "comment", "classify"}
_QUALITY_TASKS = {"article", "audit", "research", "strategy"}


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def model_for(self, task: str) -> str:
        if task in _QUALITY_TASKS:
            model = self._settings.model_quality
            env_key = "ANTHROPIC_MODEL_QUALITY"
        else:
            model = self._settings.model_fast
            env_key = "ANTHROPIC_MODEL_FAST"
        if not model:
            raise ConfigError(
                f"Brak nazwy modelu dla zadania {task!r}. Ustaw {env_key} w .env "
                "(nazwy modeli nie są zaszyte w kodzie)."
            )
        return model
