"""Policy Engine — deterministyczne, jawne reguły. Model językowy nie może ich ominąć.

W walking skeleton pokrywa: kill-switch, aktywność konta, budżet (miesięczny nadrzędny
nad dziennym — ADR-012) oraz progi scoringu tematu.
"""
from __future__ import annotations

from dataclasses import dataclass

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
        now = self._clock.now()
        month_prefix = now.strftime("%Y-%m")
        day_prefix = now.strftime("%Y-%m-%d")
        month_spent = self._storage.sum_real_cost_usd(month_prefix)
        day_spent = self._storage.sum_real_cost_usd(day_prefix)
        monthly = self._settings.max_monthly_cost_usd
        daily = self._settings.max_daily_cost_usd

        # Limit miesięczny ma bezwzględny priorytet (ADR-012).
        if self._settings.monthly_limit_has_priority and month_spent >= monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_REACHED",
                f"Osiągnięto limit miesięczny {monthly:.2f} USD (wydano {month_spent:.4f}). "
                "Wszystkie płatne działania zatrzymane.",
            )
        if month_spent + estimated_cost_usd > monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_EXCEEDED",
                f"Koszt przekroczyłby limit miesięczny {monthly:.2f} USD "
                f"(wydano {month_spent:.4f}, szac. +{estimated_cost_usd:.4f}).",
            )
        if day_spent + estimated_cost_usd > daily:
            return PolicyDecision.block(
                "BUDGET_DAILY_EXCEEDED",
                f"Koszt przekroczyłby limit dzienny {daily:.2f} USD "
                f"(wydano dziś {day_spent:.4f}, szac. +{estimated_cost_usd:.4f}).",
            )
        return PolicyDecision.ok()

    def decide_topic_status(self, score: float) -> TopicStatus:
        if score >= self._settings.article_min_score:
            return TopicStatus.SELECTED
        if score >= self._settings.note_min_score:
            return TopicStatus.SCORED
        return TopicStatus.REJECTED
