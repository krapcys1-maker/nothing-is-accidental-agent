"""Orchestration boundary for offline discovery, qualification and calls."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, TypeVar

from app.model_routing.contracts import (
    CatalogueCandidate,
    FrozenModelBinding,
    LogicalModelRole,
    PromotionOutcome,
    QualificationReport,
    RegisteredModel,
    RolePolicy,
    RoutingError,
    parse_role,
)


class ModelCatalogueSource(Protocol):
    """Future provider catalogue boundary; this wave supplies fake sources only."""

    def discover(self) -> Sequence[CatalogueCandidate]: ...


class ModelQualificationRunner(Protocol):
    """Controlled regression qualification boundary.

    Implementations receive local fixtures and return auditable evidence.  No
    real runner or provider adapter is shipped by this wave.
    """

    def qualify(
        self,
        model: RegisteredModel,
        fixtures: Mapping[str, Any],
    ) -> QualificationReport: ...


_T = TypeVar("_T")


class TechnicalModelCaller(Protocol[_T]):
    def __call__(self, binding: FrozenModelBinding) -> _T: ...


class ModelRoutingStorage(Protocol):
    def register_model_candidate(self, candidate: CatalogueCandidate) -> RegisteredModel: ...
    def get_registered_model(self, model_registry_id: str) -> RegisteredModel | None: ...
    def record_model_qualification(self, report: QualificationReport) -> RegisteredModel: ...
    def list_role_policies_for_family(self, family: object) -> tuple[RolePolicy, ...]: ...
    def promote_best_model(self, role: object, *, reason: str) -> PromotionOutcome: ...
    def freeze_model_for_intent(
        self, role: object, *, intent_kind: str, intent_id: str,
    ) -> FrozenModelBinding: ...
    def get_frozen_model_binding(
        self, *, intent_kind: str, intent_id: str,
    ) -> FrozenModelBinding | None: ...
    def deprecate_registered_model(self, model_registry_id: str, *, reason: str) -> tuple[object, ...]: ...


class ModelRoutingService:
    """Small composition service; all consistency lives in SQLite transactions."""

    def __init__(self, storage: ModelRoutingStorage) -> None:
        self._storage = storage

    def ingest_catalogue(self, source: ModelCatalogueSource) -> tuple[RegisteredModel, ...]:
        candidates = source.discover()
        return tuple(self._storage.register_model_candidate(item) for item in candidates)

    def qualify_candidate(
        self,
        model_registry_id: str,
        *,
        runner: ModelQualificationRunner,
        fixtures: Mapping[str, Any],
        auto_promote: bool = True,
    ) -> tuple[RegisteredModel, tuple[PromotionOutcome, ...]]:
        model = self._storage.get_registered_model(model_registry_id)
        if model is None:
            raise RoutingError("UNKNOWN_MODEL", f"Unknown model: {model_registry_id!r}.")
        report = runner.qualify(model, fixtures)
        if report.model_registry_id != model.registry_id:
            raise RoutingError(
                "QUALIFICATION_MODEL_MISMATCH",
                "Qualification report names a different registry entry.",
            )
        updated = self._storage.record_model_qualification(report)
        promotions: list[PromotionOutcome] = []
        if auto_promote and report.state.value == "PASS":
            for policy in self._storage.list_role_policies_for_family(model.family):
                promotions.append(
                    self._storage.promote_best_model(
                        policy.role,
                        reason=f"QUALIFICATION_PASS:{report.qualification_ref}",
                    )
                )
        return updated, tuple(promotions)

    def promote(self, role: object, *, reason: str = "POLICY_EVALUATION") -> PromotionOutcome:
        return self._storage.promote_best_model(parse_role(role), reason=reason)

    def freeze_new_intent(
        self, role: object, *, intent_kind: str, intent_id: str,
    ) -> FrozenModelBinding:
        return self._storage.freeze_model_for_intent(
            parse_role(role), intent_kind=intent_kind, intent_id=intent_id,
        )

    def execute_new_intent(
        self,
        role: object,
        *,
        intent_kind: str,
        intent_id: str,
        caller: TechnicalModelCaller[_T],
    ) -> _T:
        """Resolve once, freeze, then call exactly the selected technical ID."""
        binding = self.freeze_new_intent(
            role, intent_kind=intent_kind, intent_id=intent_id,
        )
        return caller(binding)

    def execute_frozen_intent(
        self, *, intent_kind: str, intent_id: str, caller: TechnicalModelCaller[_T],
    ) -> _T:
        """Retry/restart path: never re-resolve and never select a fallback."""
        binding = self._storage.get_frozen_model_binding(
            intent_kind=intent_kind, intent_id=intent_id,
        )
        if binding is None:
            raise RoutingError(
                "FROZEN_MODEL_BINDING_MISSING",
                "A retry/restart cannot resolve a replacement model.",
            )
        return caller(binding)

    def runtime_failure(self, binding: FrozenModelBinding, *, error_code: str) -> None:
        """Make the no-fallback rule executable rather than documentary."""
        raise RoutingError(
            "RUNTIME_FALLBACK_FORBIDDEN",
            f"{binding.intent_kind}/{binding.intent_id} remains frozen on "
            f"{binding.technical_model_id}; provider failure {error_code!r} cannot reroute it.",
        )

    def deprecate(self, model_registry_id: str, *, reason: str) -> tuple[object, ...]:
        return self._storage.deprecate_registered_model(
            model_registry_id, reason=reason,
        )
