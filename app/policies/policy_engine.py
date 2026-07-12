"""Policy Engine — deterministyczne, jawne reguły. Model językowy nie może ich ominąć.

W walking skeleton pokrywa: kill-switch, aktywność konta, budżet (miesięczny nadrzędny
nad dziennym — ADR-012) oraz progi scoringu tematu.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.models import Account, TopicStatus
from app.ports.storage import StoragePort


@dataclass
class PolicyDecision:
    allowed: bool
    code: str
    reason: str

    @classmethod
    def ok(cls, code: str = "OK", reason: str = "") -> "PolicyDecision":
        return cls(True, code, reason)

    @classmethod
    def block(cls, code: str, reason: str) -> "PolicyDecision":
        return cls(False, code, reason)


class PolicyEngine:
    def __init__(self, settings: Settings, storage: StoragePort,
                 clock: Clock | None = None) -> None:
        self._settings = settings
        self._storage = storage
        self._clock = clock or SystemClock()

    def check_can_run(self, account: Account) -> PolicyDecision:
        if self._settings.kill_switch:
            return PolicyDecision.block("KILL_SWITCH", "Globalny wyłącznik bezpieczeństwa jest włączony.")
        if not account.active:
            return PolicyDecision.block("ACCOUNT_INACTIVE", f"Konto {account.id} jest nieaktywne.")
        return PolicyDecision.ok()

    def check_budget(self, estimated_cost_usd: float) -> PolicyDecision:
        """Backward-compatible global budget check for non-research workflows."""
        return self.check_run_budget(
            estimated_total=estimated_cost_usd,
            cap=None,
            current_run_cost=0.0,
        )

    def check_run_budget(
        self,
        estimated_total: float,
        cap: float | None,
        *,
        current_run_cost: float = 0.0,
        account: Account | None = None,
    ) -> PolicyDecision:
        """Central budget gate for a research run.

        ``estimated_total`` is the projected total cost of the run after the
        operation being considered. ``current_run_cost`` is the real usage
        already persisted for that run in ``model_usage``.  Global daily and
        monthly sums already contain that persisted usage, so only the
        incremental projection is added to them. ``cap=None`` is retained for
        legacy non-research callers; every paid research entry point supplies a
        concrete cap.
        """
        values = (estimated_total, current_run_cost)
        if any(not math.isfinite(value) or value < 0 for value in values):
            return PolicyDecision.block(
                "BUDGET_INVALID_INPUT",
                "Estymowany i aktualny koszt runu muszą być skończone i nieujemne.",
            )
        if estimated_total < current_run_cost:
            return PolicyDecision.block(
                "BUDGET_INVALID_INPUT",
                "Estymowany koszt całkowity nie może być niższy od już zapisanego kosztu runu.",
            )
        if cap is not None and (not math.isfinite(cap) or cap < 0):
            return PolicyDecision.block(
                "RUN_CAP_INVALID",
                "Cap runu musi być skończony i nieujemny.",
            )

        if account is not None:
            can_run = self.check_can_run(account)
            if not can_run.allowed:
                return can_run
        elif self._settings.kill_switch:
            return PolicyDecision.block(
                "KILL_SWITCH", "Globalny wyłącznik bezpieczeństwa jest włączony."
            )

        now = self._clock.now()
        month_prefix = now.strftime("%Y-%m")
        day_prefix = now.strftime("%Y-%m-%d")
        month_spent = self._storage.sum_real_cost_usd(month_prefix)
        day_spent = self._storage.sum_real_cost_usd(day_prefix)
        monthly = self._settings.max_monthly_cost_usd
        daily = self._settings.max_daily_cost_usd

        budget_state = (month_spent, day_spent, monthly, daily)
        if any(not math.isfinite(value) or value < 0 for value in budget_state):
            return PolicyDecision.block(
                "BUDGET_INVALID_STATE",
                "Limity oraz zapisane wykorzystanie budżetu muszą być skończone "
                "i nieujemne.",
            )

        # Limit miesięczny ma bezwzględny priorytet (ADR-012).
        if self._settings.monthly_limit_has_priority and month_spent >= monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_REACHED",
                f"Osiągnięto limit miesięczny {monthly:.2f} USD (wydano {month_spent:.4f}). "
                "Wszystkie płatne działania zatrzymane.",
            )
        incremental_estimate = estimated_total - current_run_cost
        if month_spent + incremental_estimate > monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_EXCEEDED",
                f"Koszt przekroczyłby limit miesięczny {monthly:.2f} USD "
                f"(wydano {month_spent:.4f}, szac. +{incremental_estimate:.4f}).",
            )
        if cap is not None and estimated_total > cap:
            return PolicyDecision.block(
                "RUN_CAP_EXCEEDED",
                f"Koszt runu przekroczyłby cap {cap:.4f} USD "
                f"(projekcja {estimated_total:.4f}, zapisano {current_run_cost:.4f}).",
            )
        if day_spent + incremental_estimate > daily:
            return PolicyDecision.block(
                "BUDGET_DAILY_EXCEEDED",
                f"Koszt przekroczyłby limit dzienny {daily:.2f} USD "
                f"(wydano dziś {day_spent:.4f}, szac. +{incremental_estimate:.4f}).",
            )
        return PolicyDecision.ok()

    def decide_topic_status(self, score: float) -> TopicStatus:
        if score >= self._settings.article_min_score:
            return TopicStatus.SELECTED
        if score >= self._settings.note_min_score:
            return TopicStatus.SCORED
        return TopicStatus.REJECTED
