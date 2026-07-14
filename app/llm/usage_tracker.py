"""Tracking kosztów: liczy koszt z cennika, zapisuje do model_usage i dopisuje do docs/COSTS.csv."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import logging
from pathlib import Path

from app.core.config import Settings
from app.llm.base import Usage
from app.models import JobExecutionContext, ModelUsage
from app.ports.storage import StoragePort

_CSV_COLUMNS = [
    "date", "run_id", "task", "provider", "model", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "web_search_requests", "image_count",
    "estimated_cost_usd", "notes",
]
_LOGGER = logging.getLogger(__name__)


class UsageTracker:
    def __init__(self, settings: Settings, storage: StoragePort,
                 costs_csv_path: Path | None = None) -> None:
        self._settings = settings
        self._storage = storage
        self._csv_path = Path(costs_csv_path or settings.costs_csv_path)

    def estimate_cost(self, usage: Usage) -> float:
        p = self._settings.pricing
        cost = (
            usage.input_tokens / 1_000_000 * p.get("input_per_mtok", 0.0)
            + usage.output_tokens / 1_000_000 * p.get("output_per_mtok", 0.0)
            + usage.cache_read_tokens / 1_000_000 * p.get("cache_read_per_mtok", 0.0)
            + usage.cache_write_tokens / 1_000_000 * p.get("cache_write_per_mtok", 0.0)
            + usage.web_search_requests / 1_000 * p.get("web_search_per_1k", 0.0)
        )
        return round(cost, 6)

    def record(self, run_id: str, model: str, usage: Usage, task: str,
               dry_run: bool, provider: str = "anthropic") -> ModelUsage:
        cost = self.estimate_cost(usage)
        row = ModelUsage(
            run_id=run_id, provider=provider, model=model, task=task,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            web_search_requests=usage.web_search_requests,
            estimated_cost_usd=cost, dry_run=dry_run,
        )
        self._storage.add_model_usage(row)
        self._append_csv_safely(row)
        return row

    def record_job(
        self,
        execution: JobExecutionContext,
        model: str,
        usage: Usage,
        task: str,
        dry_run: bool,
        provider: str = "anthropic",
    ) -> ModelUsage:
        """Worker-only path: SQLite fence succeeds before any CSV side effect."""
        cost = self.estimate_cost(usage)
        row = ModelUsage(
            run_id=execution.run_id, provider=provider, model=model, task=task,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            web_search_requests=usage.web_search_requests,
            estimated_cost_usd=cost, dry_run=dry_run,
        )
        self._storage.add_job_model_usage(execution, row)
        self._append_csv_safely(row)
        return row

    def _append_csv_safely(self, row: ModelUsage) -> None:
        """Best-effort derived export; SQLite remains the cost authority."""
        try:
            self._append_csv(row)
        except Exception as exc:
            # COSTS.csv is intentionally a rebuildable operator convenience, not
            # a second durability boundary after the fenced SQLite commit.
            _LOGGER.warning(
                "COSTS_CSV_DERIVED_EXPORT_FAILED run_id=%s task=%s error_type=%s",
                row.run_id,
                row.task,
                type(exc).__name__,
            )

    def _append_csv(self, row: ModelUsage) -> None:
        notes = "dry_run estimate (no real charge)" if row.dry_run else "actual"
        self._csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self._csv_path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                row.run_id, row.task, row.provider, row.model,
                row.input_tokens, row.output_tokens, row.cache_read_tokens,
                row.cache_write_tokens, row.web_search_requests, 0,
                f"{row.estimated_cost_usd:.6f}", notes,
            ])
