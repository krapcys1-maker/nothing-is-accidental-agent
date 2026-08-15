"""Policy Engine — deterministyczne, jawne reguły. Model językowy nie może ich ominąć.

W walking skeleton pokrywa: kill-switch, aktywność konta, budżet (miesięczny nadrzędny
nad dziennym — ADR-012) oraz progi scoringu tematu.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import math
from typing import Any

from app.content.contracts import EVALUATOR_VERSION, EvaluationType
from app.content.decision import (
    ContentDecisionActor,
    ContentDecisionOutcome,
    ContentDecisionPlan,
)
from app.content.foundation import ContentStatus, ContentType
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.money import decimal_from, quantize_usd, usd_float
from app.models import Account, AccountMode, AutonomyLevel, JobKind, TopicStatus
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

    def decide_content(
        self,
        snapshot: dict[str, Any],
        *,
        expected_input_fingerprint: str | None = None,
    ) -> ContentDecisionPlan:
        """Decide one exact durable draft without provider or publication access.

        The method consumes only an already persisted snapshot.  Every relevant
        policy fact is copied into the canonical input preimage, so a later
        change to autonomy, account mode, draft, evaluations, policy version or
        threshold necessarily changes ``input_fingerprint``.
        """
        content = dict(snapshot.get("content") or {})
        account = dict(snapshot.get("account") or {})
        account_policy = dict(snapshot.get("account_policy") or {})
        draft = dict(snapshot.get("draft") or {})
        lineage = dict(snapshot.get("lineage") or {})
        evaluation_rows = [
            dict(row) for row in (snapshot.get("evaluations") or [])
            if isinstance(row, dict)
        ]

        observed_type = str(content.get("type", ""))
        try:
            content_type = ContentType(observed_type)
        except ValueError:
            # A database-level CHECK makes this unreachable in supported state.
            # Retaining a typed fallback lets PolicyEngine return a durable
            # fail-closed category for a corrupt/manual snapshot in tests.
            fallback = str(content.get("workflow", ""))
            content_type = (
                ContentType.NOTE if fallback == ContentType.NOTE.value
                else ContentType.ARTICLE
            )

        configuration_error: str | None = None
        try:
            threshold, policy_version = self._content_decision_threshold(content_type)
        except ValueError as exc:
            configuration_error = str(exc)
            threshold = 0.0
            policy_version = "content_decision_policy_invalid"
        normalized_evaluations: list[dict[str, Any]] = []
        for row in evaluation_rows:
            findings = row.get("findings")
            if findings is None:
                try:
                    findings = json.loads(str(row.get("findings_json", "[]")))
                except (TypeError, ValueError, json.JSONDecodeError):
                    findings = [{"code": "MALFORMED_FINDINGS"}]
            normalized_evaluations.append({
                "id": row.get("id"),
                "draft_id": row.get("draft_id"),
                "content_id": row.get("content_id"),
                "job_id": row.get("job_id"),
                "run_id": row.get("run_id"),
                "attempt_no": row.get("attempt_no"),
                "evaluation_type": row.get("evaluation_type"),
                "evaluator_version": row.get("evaluator_version"),
                "result": row.get("result"),
                "score": row.get("score"),
                "findings": findings,
                "draft_fingerprint": row.get("draft_fingerprint"),
                "decision": row.get("decision"),
            })
        normalized_evaluations.sort(
            key=lambda row: (str(row["evaluation_type"]), str(row["id"]))
        )
        decision_input: dict[str, Any] = {
            "content": {
                "id": content.get("id"),
                "account_id": content.get("account_id"),
                "type": observed_type,
                "status": content.get("status"),
                "job_id": content.get("job_id"),
                "run_id": content.get("run_id"),
                "input_sha256": content.get("input_sha256"),
            },
            "account": {
                "id": account.get("id"),
                "mode": account.get("mode"),
                "autonomy_level": account.get("autonomy_level"),
                "active": account.get("active"),
            },
            "account_policy": {
                "require_article_approval": account_policy.get(
                    "require_article_approval"
                ),
                "require_note_approval": account_policy.get(
                    "require_note_approval"
                ),
            },
            "draft": {
                "id": draft.get("id"),
                "content_id": draft.get("content_id"),
                "job_id": draft.get("job_id"),
                "run_id": draft.get("run_id"),
                "attempt_no": draft.get("attempt_no"),
                "draft_fingerprint": draft.get("draft_fingerprint"),
                "intent_id": draft.get("intent_id"),
                "request_id": draft.get("request_id"),
            },
            "lineage": lineage,
            "evaluations": normalized_evaluations,
            "thresholds": {
                "policy_version": policy_version,
                "evaluator_version": EVALUATOR_VERSION,
                "auto_approve_min_score": threshold,
                "configuration_error": configuration_error,
            },
        }

        def plan(
            *,
            actor: ContentDecisionActor,
            outcome: ContentDecisionOutcome,
            reason_code: str,
            lifecycle_status: ContentStatus,
            score: float | None,
        ) -> ContentDecisionPlan:
            return ContentDecisionPlan.build(
                content_id=int(content.get("id") or 0),
                account_id=str(content.get("account_id") or ""),
                job_id=str(content.get("job_id") or ""),
                run_id=str(content.get("run_id") or ""),
                draft_id=int(draft.get("id") or 0),
                draft_fingerprint=str(draft.get("draft_fingerprint") or "0" * 64),
                content_type=content_type,
                autonomy_level=str(account.get("autonomy_level") or ""),
                account_mode=str(account.get("mode") or ""),
                actor=actor,
                outcome=outcome,
                reason_code=reason_code,
                lifecycle_status=lifecycle_status,
                policy_version=policy_version,
                threshold=threshold,
                score=score,
                input=decision_input,
            )

        def stale(code: str, score: float | None = None) -> ContentDecisionPlan:
            return plan(
                actor=ContentDecisionActor.AUTONOMOUS,
                outcome=ContentDecisionOutcome.STALE_INPUT,
                reason_code=code,
                lifecycle_status=ContentStatus.NEEDS_VERIFICATION,
                score=score,
            )

        identity_invalid = (
            not isinstance(content.get("id"), int)
            or int(content.get("id") or 0) < 1
            or not str(content.get("account_id") or "")
            or not str(content.get("job_id") or "")
            or not str(content.get("run_id") or "")
            or not isinstance(draft.get("id"), int)
            or int(draft.get("id") or 0) < 1
            or len(str(draft.get("draft_fingerprint") or "")) != 64
        )
        if configuration_error is not None:
            result = plan(
                actor=ContentDecisionActor.AUTONOMOUS,
                outcome=ContentDecisionOutcome.TECHNICAL_ERROR,
                reason_code="CONTENT_DECISION_CONFIGURATION_ERROR",
                lifecycle_status=ContentStatus.FAILED,
                score=None,
            )
        elif identity_invalid:
            result = stale("CONTENT_DECISION_IDENTITY_INVALID")
        elif observed_type not in {item.value for item in ContentType}:
            result = stale("CONTENT_DECISION_TYPE_UNSUPPORTED")
        elif content.get("status") not in {
            ContentStatus.RUNNING.value,
            ContentStatus.REVISE.value,
        }:
            result = stale("CONTENT_DECISION_CONTENT_NOT_CURRENT")
        elif (
            content.get("account_id") != account.get("id")
            or content.get("id") != draft.get("content_id")
            or content.get("job_id") != draft.get("job_id")
            or content.get("run_id") != draft.get("run_id")
            or not lineage.get("draft_is_current")
            or lineage.get("writer_outcome") != "SUCCESS"
            or lineage.get("provider_attempt_status") != "SETTLED"
            or int(lineage.get("usage_count") or 0) != 1
        ):
            result = stale("CONTENT_DECISION_LINEAGE_INCONSISTENT")
        else:
            required_types = {item.value for item in EvaluationType}
            observed_types = [
                str(row.get("evaluation_type")) for row in normalized_evaluations
            ]
            evaluation_invalid = (
                len(normalized_evaluations) != len(required_types)
                or set(observed_types) != required_types
                or len(set(observed_types)) != len(observed_types)
            )
            scores: list[float] = []
            hard_failure = False
            any_failure = False
            for row in normalized_evaluations:
                raw_score = row.get("score")
                valid_score = (
                    not isinstance(raw_score, bool)
                    and isinstance(raw_score, (int, float))
                    and math.isfinite(float(raw_score))
                    and 0.0 <= float(raw_score) <= 1.0
                )
                if valid_score:
                    scores.append(float(raw_score))
                findings = row.get("findings")
                result_value = row.get("result")
                decision_value = row.get("decision")
                binding_invalid = (
                    row.get("draft_id") != draft.get("id")
                    or row.get("content_id") != content.get("id")
                    or row.get("job_id") != content.get("job_id")
                    or row.get("run_id") != content.get("run_id")
                    or row.get("attempt_no") != draft.get("attempt_no")
                    or row.get("draft_fingerprint") != draft.get("draft_fingerprint")
                    or row.get("evaluator_version") != EVALUATOR_VERSION
                )
                result_invalid = (
                    result_value not in {"PASS", "FAIL"}
                    or decision_value not in {"PASS", "REWRITE_ONCE", "BLOCK"}
                    or (result_value == "PASS" and decision_value != "PASS")
                    or (result_value == "FAIL" and decision_value == "PASS")
                    or not isinstance(findings, list)
                    or (
                        result_value == "FAIL"
                        and not any(
                            isinstance(item, dict)
                            and isinstance(item.get("code"), str)
                            and bool(item["code"].strip())
                            for item in findings
                        )
                    )
                )
                evaluation_invalid = (
                    evaluation_invalid or binding_invalid or result_invalid
                    or not valid_score
                )
                if result_value == "FAIL":
                    any_failure = True
                    if row.get("evaluation_type") in {
                        EvaluationType.UNSUPPORTED_CLAIMS.value,
                        EvaluationType.BRAND_TOPIC_POLICY.value,
                        EvaluationType.FAKE_PERSONAL_EXPERIENCE.value,
                    }:
                        hard_failure = True
            score = (
                None if len(scores) != len(required_types)
                else sum(scores) / len(scores)
            )
            if evaluation_invalid:
                result = stale("CONTENT_DECISION_EVALUATIONS_INCONSISTENT", score)
            elif hard_failure:
                result = plan(
                    actor=ContentDecisionActor.AUTONOMOUS,
                    outcome=ContentDecisionOutcome.REJECTED,
                    reason_code="CONTENT_HARD_POLICY_VIOLATION",
                    lifecycle_status=ContentStatus.REJECTED,
                    score=score,
                )
            elif any_failure:
                result = plan(
                    actor=ContentDecisionActor.AUTONOMOUS,
                    outcome=ContentDecisionOutcome.REJECTED,
                    reason_code="CONTENT_EVALUATION_REJECTED",
                    lifecycle_status=ContentStatus.REJECTED,
                    score=score,
                )
            elif account.get("active") not in {1, True}:
                result = plan(
                    actor=ContentDecisionActor.AUTONOMOUS,
                    outcome=ContentDecisionOutcome.REJECTED,
                    reason_code="CONTENT_ACCOUNT_INACTIVE",
                    lifecycle_status=ContentStatus.REJECTED,
                    score=score,
                )
            elif account.get("mode") in {
                AccountMode.COMMENT_ONLY.value,
                AccountMode.RESEARCH_ONLY.value,
            }:
                result = plan(
                    actor=ContentDecisionActor.AUTONOMOUS,
                    outcome=ContentDecisionOutcome.REJECTED,
                    reason_code="CONTENT_ACCOUNT_MODE_FORBIDS_TYPE",
                    lifecycle_status=ContentStatus.REJECTED,
                    score=score,
                )
            else:
                autonomy = str(account.get("autonomy_level") or "")
                autonomy_supported = autonomy in {
                    item.value for item in AutonomyLevel
                }
                requires_approval = bool(
                    account_policy.get(
                        "require_article_approval"
                        if content_type is ContentType.ARTICLE
                        else "require_note_approval",
                        True,
                    )
                )
                human_reason: str | None = None
                if account.get("mode") == AccountMode.DRAFT_ONLY.value:
                    human_reason = "CONTENT_DRAFT_ONLY_REQUIRES_HUMAN"
                elif autonomy == AutonomyLevel.LEVEL_0.value:
                    human_reason = "CONTENT_LEVEL_0_REQUIRES_HUMAN"
                elif autonomy == AutonomyLevel.LEVEL_1.value:
                    human_reason = "CONTENT_LEVEL_1_REQUIRES_HUMAN"
                elif (
                    autonomy == AutonomyLevel.LEVEL_2.value
                    and content_type is ContentType.ARTICLE
                ):
                    human_reason = "CONTENT_LEVEL_2_ARTICLE_REQUIRES_HUMAN"
                elif not autonomy_supported:
                    result = stale("CONTENT_AUTONOMY_LEVEL_UNSUPPORTED", score)
                    human_reason = None
                elif requires_approval:
                    human_reason = "CONTENT_ACCOUNT_POLICY_REQUIRES_HUMAN"

                if human_reason is not None:
                    result = plan(
                        actor=ContentDecisionActor.HUMAN_REQUIRED,
                        outcome=ContentDecisionOutcome.HUMAN_REQUIRED,
                        reason_code=human_reason,
                        lifecycle_status=ContentStatus.PENDING_APPROVAL,
                        score=score,
                    )
                elif autonomy_supported:
                    if score is None or score < threshold:
                        result = plan(
                            actor=ContentDecisionActor.AUTONOMOUS,
                            outcome=ContentDecisionOutcome.REJECTED,
                            reason_code="CONTENT_SCORE_BELOW_THRESHOLD",
                            lifecycle_status=ContentStatus.REJECTED,
                            score=score,
                        )
                    else:
                        result = plan(
                            actor=ContentDecisionActor.AUTONOMOUS,
                            outcome=ContentDecisionOutcome.APPROVED,
                            reason_code="CONTENT_AUTONOMOUSLY_APPROVED",
                            lifecycle_status=ContentStatus.APPROVED,
                            score=score,
                        )

        if (
            expected_input_fingerprint is not None
            and result.input_fingerprint != expected_input_fingerprint
        ):
            return result.as_stale(reason_code="CONTENT_DECISION_INPUT_DRIFT")
        return result

    def _content_decision_threshold(
        self, content_type: ContentType,
    ) -> tuple[float, str]:
        value = (
            self._settings.content_article_auto_approve_min_score
            if content_type is ContentType.ARTICLE
            else self._settings.content_note_auto_approve_min_score
        )
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError("CONTENT_DECISION_THRESHOLD_INVALID")
        version = self._settings.content_decision_policy_version
        if not isinstance(version, str) or not version.strip():
            raise ValueError("CONTENT_DECISION_POLICY_VERSION_INVALID")
        return float(value), version.strip()

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
