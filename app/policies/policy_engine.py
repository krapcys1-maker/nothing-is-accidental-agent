"""Policy Engine — deterministyczne, jawne reguły. Model językowy nie może ich ominąć.

W walking skeleton pokrywa: kill-switch, aktywność konta, budżet (miesięczny nadrzędny
nad dziennym — ADR-012) oraz progi scoringu tematu.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.money import decimal_from, quantize_usd, usd_float
from app.models import Account, JobKind, TopicStatus
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

    @property
    def daily_limit_usd(self) -> float:
        """Configured limit exposed for the storage-backed reservation boundary."""
        return usd_float(self._settings.max_daily_cost_usd, label="daily budget limit")

    @property
    def monthly_limit_usd(self) -> float:
        """Configured limit exposed for the storage-backed reservation boundary."""
        return usd_float(self._settings.max_monthly_cost_usd, label="monthly budget limit")

    def check_can_run(self, account: Account) -> PolicyDecision:
        if self._settings.kill_switch:
            return PolicyDecision.block("KILL_SWITCH", "Globalny wyłącznik bezpieczeństwa jest włączony.")
        if not account.active:
            return PolicyDecision.block("ACCOUNT_INACTIVE", f"Konto {account.id} jest nieaktywne.")
        return PolicyDecision.ok()

    def check_worker_runtime(
        self,
        account: Account | None = None,
        *,
        job_kind: JobKind | None = None,
        dry_run: bool = True,
        controlled_fetch: bool = False,
    ) -> PolicyDecision:
        """Checks uncached SQLite safety flags for one worker iteration.

        Runtime flags are intentionally separate from the legacy configuration
        kill-switch: the latter remains an additional fail-closed boundary for
        existing manual workflows.  Every required flag must be present and a
        JSON boolean before even a local dry-run may proceed.
        """
        flag_keys = (
            "kill_switch",
            "worker_enabled",
            "safe_mode",
            "paid_actions_enabled",
            "browser_actions_enabled",
        )
        flags: dict[str, bool] = {}
        for key in flag_keys:
            try:
                flag = self._storage.get_system_flag(key)
            except Exception:
                return PolicyDecision.block(
                    "RUNTIME_FLAG_READ_FAILED",
                    "Nie można bezpiecznie odczytać runtime flagi workera.",
                )
            if flag is None or not flag.is_valid:
                return PolicyDecision.block(
                    "RUNTIME_FLAG_INVALID",
                    f"Runtime flaga bezpieczeństwa {key!r} jest nieobecna lub nieprawidłowa.",
                )
            flags[key] = flag.value

        if self._settings.kill_switch or flags["kill_switch"]:
            return PolicyDecision.block(
                "KILL_SWITCH", "Globalny wyłącznik bezpieczeństwa jest włączony."
            )
        if not flags["worker_enabled"]:
            return PolicyDecision.block(
                "WORKER_DISABLED", "Worker jest wyłączony przez runtime flagę bezpieczeństwa."
            )
        if flags["safe_mode"]:
            return PolicyDecision.block(
                "SAFE_MODE", "Tryb bezpieczny blokuje wykonanie workera."
            )

        if account is None:
            return PolicyDecision.ok("WORKER_RUNTIME_OK")
        if not account.active:
            return PolicyDecision.block("ACCOUNT_INACTIVE", f"Konto {account.id} jest nieaktywne.")
        if job_kind is JobKind.BROWSER:
            return PolicyDecision.block(
                "BROWSER_ACTIONS_BLOCKED",
                "Akcje browser/public pozostają zablokowane w tym etapie.",
            )
        if controlled_fetch:
            # Controlled fetch (E2-B) nie jest akcją płatną ani browserową:
            # zero modelu, zero providera. Jego właściwą bramką jest trwała,
            # jednorazowa zgoda L1 sprawdzana w transakcji startu — flaga
            # paid_actions_enabled celowo NIE otwiera i NIE zamyka tej ścieżki.
            if job_kind is not JobKind.RESEARCH:
                return PolicyDecision.block(
                    "CONTROLLED_FETCH_KIND_INVALID",
                    "Controlled fetch może wykonywać wyłącznie job RESEARCH.",
                )
            return PolicyDecision.ok("WORKER_JOB_ALLOWED")
        if not dry_run and not flags["paid_actions_enabled"]:
            return PolicyDecision.block(
                "PAID_ACTIONS_BLOCKED",
                "Płatne i niedry-runowe akcje pozostają zablokowane w tym etapie.",
            )
        return PolicyDecision.ok("WORKER_JOB_ALLOWED")

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
        try:
            estimated_raw = decimal_from(estimated_total, label="estimated total cost")
            current_raw = decimal_from(current_run_cost, label="current run cost")
            cap_raw = None if cap is None else decimal_from(cap, label="run cap")
            if (
                estimated_raw < Decimal("0")
                or current_raw < Decimal("0")
                or (cap_raw is not None and cap_raw < Decimal("0"))
            ):
                raise ValueError("negative monetary amount")
            estimated_amount = quantize_usd(
                estimated_raw, label="estimated total cost",
            )
            current_amount = quantize_usd(
                current_raw, label="current run cost",
            )
            cap_amount = (
                None
                if cap is None
                else quantize_usd(cap_raw, label="run cap")
            )
        except ValueError:
            return PolicyDecision.block(
                "BUDGET_INVALID_INPUT",
                "Estymowany i aktualny koszt runu muszą być skończone i nieujemne.",
            )
        if estimated_amount < current_amount:
            return PolicyDecision.block(
                "BUDGET_INVALID_INPUT",
                "Estymowany koszt całkowity nie może być niższy od już zapisanego kosztu runu.",
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
        try:
            month_raw = decimal_from(month_spent, label="monthly spend")
            day_raw = decimal_from(day_spent, label="daily spend")
            monthly_raw = decimal_from(
                self._settings.max_monthly_cost_usd, label="monthly budget limit",
            )
            daily_raw = decimal_from(
                self._settings.max_daily_cost_usd, label="daily budget limit",
            )
            if any(amount < Decimal("0") for amount in (
                month_raw, day_raw, monthly_raw, daily_raw,
            )):
                raise ValueError("negative budget state")
            month_amount = quantize_usd(month_raw, label="monthly spend")
            day_amount = quantize_usd(day_raw, label="daily spend")
            monthly = quantize_usd(monthly_raw, label="monthly budget limit")
            daily = quantize_usd(daily_raw, label="daily budget limit")
        except ValueError:
            return PolicyDecision.block(
                "BUDGET_INVALID_STATE",
                "Limity oraz zapisane wykorzystanie budżetu muszą być skończone "
                "i nieujemne.",
            )
        # Limit miesięczny ma bezwzględny priorytet (ADR-012).
        if self._settings.monthly_limit_has_priority and month_amount >= monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_REACHED",
                f"Osiągnięto limit miesięczny {monthly:.2f} USD (wydano {month_amount:.4f}). "
                "Wszystkie płatne działania zatrzymane.",
            )
        incremental_estimate = estimated_amount - current_amount
        if month_amount + incremental_estimate > monthly:
            return PolicyDecision.block(
                "BUDGET_MONTHLY_EXCEEDED",
                f"Koszt przekroczyłby limit miesięczny {monthly:.2f} USD "
                f"(wydano {month_amount:.4f}, szac. +{incremental_estimate:.4f}).",
            )
        if cap_amount is not None and estimated_amount > cap_amount:
            return PolicyDecision.block(
                "RUN_CAP_EXCEEDED",
                f"Koszt runu przekroczyłby cap {cap_amount:.4f} USD "
                f"(projekcja {estimated_amount:.4f}, zapisano {current_amount:.4f}).",
            )
        if day_amount + incremental_estimate > daily:
            return PolicyDecision.block(
                "BUDGET_DAILY_EXCEEDED",
                f"Koszt przekroczyłby limit dzienny {daily:.2f} USD "
                f"(wydano dziś {day_amount:.4f}, szac. +{incremental_estimate:.4f}).",
            )
        return PolicyDecision.ok()

    def decide_topic_status(self, score: float) -> TopicStatus:
        if score >= self._settings.article_min_score:
            return TopicStatus.SELECTED
        if score >= self._settings.note_min_score:
            return TopicStatus.SCORED
        return TopicStatus.REJECTED
