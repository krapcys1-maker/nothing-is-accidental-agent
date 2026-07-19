"""E2-C controlled fetch runner — jedno zatwierdzone pobranie, zero modelu.

Przepływ: trwały run → atomowa konsumpcja approval L1 + RESERVED → storage
capability → composition root → przypięcie adresu → REQUEST_STARTED →
wstrzyknięty transport → trwała terminalizacja (SUCCEEDED z retrievalem OK |
FAILED z typowanym błędem | NEEDS_VERIFICATION przy niejednoznaczności).
Żadna gałąź nie tworzy kosztu, provider attemptu, syntezy Research Card ani
akcji browser/publikacji.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.clock import Clock
from app.core.config import Settings
from app.core.ids import new_run_id
from app.models import (
    Account,
    ControlledFetchAttemptStatus,
    ControlledFetchFailureOutcome,
    ControlledFetchTransportAuthorization,
    JobExecutionContext,
    ResearchJobExecution,
    Topic,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.controlled_fetch import (
    ControlledFetchRequestContract,
    ControlledHttpFetch,
    FakeControlledHttpTransport,
    build_real_controlled_fetch_port,
    fake_resolver_from_fixture,
)
from app.ports.fetch import FetchPort
from app.ports.storage import (
    ControlledFetchAuthorizationError,
    ControlledFetchRetrievalNotOk,
    StaleJobExecutionError,
    StoragePort,
)
from app.research.controlled_fetch_intent import ControlledFetchIntent
from app.workflows.research.pipeline import ResearchRunSummary

CONTROLLED_FETCH_MODEL_LABEL = "controlled-fetch-no-model"


class ControlledFetchUnavailableError(RuntimeError):
    """Composition gate odmówił zbudowania transportu — nic nie wykonano."""


class ControlledFetchNeedsVerification(RuntimeError):
    """Trwała eskalacja już zapisana; worker musi zgłosić NEEDS_VERIFICATION."""


def resolve_controlled_fetch_port(
    authorization: ControlledFetchTransportAuthorization,
    *,
    settings: Settings,
    clock: Clock,
) -> FetchPort:
    """Composition root for an already consumed, exactly bound L1 approval.

    ENV może wybrać wyłącznie fake w test mode. Realna zdolność jest globalnie
    włączana jawnym booleanem YAML, ale samo ustawienie nigdy nie zastępuje
    capability ze storage.
    """
    authorization.assert_usable_at(clock.now())
    contract = ControlledFetchRequestContract(
        requested_url=authorization.requested_url,
        timeout_seconds=authorization.timeout_seconds,
        max_bytes=authorization.max_bytes,
        max_redirects=authorization.max_redirects,
        allowed_content_types=authorization.allowed_content_types,
    )
    fake_requested = os.environ.get("NIA_CONTROLLED_FETCH_FAKE") == "1"
    if fake_requested:
        if os.environ.get("NIA_TEST_MODE") != "1":
            raise ControlledFetchUnavailableError(
                "fake controlled fetch transport requires NIA_TEST_MODE."
            )
        fixture_path = os.environ.get("NIA_CONTROLLED_FETCH_FIXTURE")
        if not fixture_path:
            raise ControlledFetchUnavailableError(
                "fake controlled fetch transport requires an explicit fixture path."
            )
        try:
            data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ControlledFetchUnavailableError(
                f"controlled fetch fixture cannot be loaded: {type(exc).__name__}."
            ) from exc
        return ControlledHttpFetch(
            contract=contract,
            transport=FakeControlledHttpTransport.from_fixture(data),
            resolver=fake_resolver_from_fixture(data),
            clock=clock,
        )
    if settings.controlled_fetch_real_enabled:
        return build_real_controlled_fetch_port(
            authorization,
            clock=clock,
        )
    raise ControlledFetchUnavailableError(
        "real controlled fetch transport is globally disabled by YAML policy."
    )


def run_controlled_fetch(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    policy: PolicyEngine,
    clock: Clock,
    job_execution: ResearchJobExecution,
    intent: ControlledFetchIntent,
    fetch_port_factory=resolve_controlled_fetch_port,
) -> ResearchRunSummary:
    """Execute exactly one approved controlled fetch; every write is fenced."""
    del policy  # zamknięty kontrakt runnera; bramki sprawdza dispatcher
    initialized = storage.initialize_controlled_fetch_run_for_job(
        job_execution.job_id, job_execution.lease_owner, new_run_id(), clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_execution.job_id, lease_owner=job_execution.lease_owner,
        run_id=initialized.run.id, clock=clock,
    )
    summary = ResearchRunSummary(
        run_id=execution.run_id, account_id=account.id, topic_id=int(topic.id),
        dry_run=False, model=CONTROLLED_FETCH_MODEL_LABEL,
    )

    def _fail(error: str, *, document=None) -> ResearchRunSummary:
        outcome = storage.fail_controlled_fetch_execution(
            execution, error, document=document,
        )
        if outcome is ControlledFetchFailureOutcome.ESCALATED_NEEDS_VERIFICATION:
            raise ControlledFetchNeedsVerification(error)
        summary.error = error[:240]
        return summary

    try:
        attempt = initialized.attempt
        if attempt is not None:
            # Jedyna próba już istnieje. Jednorazowa zgoda nie odradza się po
            # restarcie, więc żaden stan attemptu nie jest tu wznawialny.
            if attempt.status is ControlledFetchAttemptStatus.REQUEST_STARTED:
                return _fail("CONTROLLED_FETCH_RESUMED_AFTER_REQUEST_STARTED")
            return _fail(
                f"CONTROLLED_FETCH_NOT_RESUMABLE:{attempt.status.value}"
            )
        try:
            attempt = storage.begin_controlled_fetch_attempt(execution)
            authorization = storage.authorize_controlled_fetch_transport(
                execution,
                attempt.id,
            )
        except ControlledFetchAuthorizationError as exc:
            return _fail(f"CONTROLLED_FETCH_REFUSED:{exc.code}")
        try:
            fetch = fetch_port_factory(
                authorization,
                settings=settings,
                clock=clock,
            )
        except (ControlledFetchUnavailableError, TypeError) as exc:
            return _fail(f"CONTROLLED_FETCH_UNAVAILABLE: {exc}")
        boundary = fetch.preflight_boundary()
        if not boundary.allowed:
            return _fail(f"URL_POLICY_REJECTED:{boundary.code}")
        storage.mark_controlled_fetch_request_started(execution, attempt.id)
        try:
            document = fetch.fetch(intent.requested_url)
        except Exception as exc:
            # Granica transportu przekroczona bez typowanego wyniku.
            return _fail(
                f"CONTROLLED_FETCH_OUTCOME_UNKNOWN:{type(exc).__name__}",
            )
        if document.error is not None:
            return _fail(f"FETCH_FAILED:{document.error}", document=document)
        try:
            storage.finalize_controlled_fetch_success(execution, attempt.id, document)
        except ControlledFetchRetrievalNotOk as exc:
            return _fail(f"FETCH_FAILED:{exc}", document=document)
        summary.passed = True
        summary.recommendation = "PROCEED"
        summary.sources_count = 1
        summary.candidates_discovered = 1
        return summary
    except (ControlledFetchNeedsVerification, StaleJobExecutionError):
        raise
    except Exception as exc:
        safe = f"{type(exc).__name__}: {str(exc)}"[:240]
        return _fail(safe)
