"""E2-C adversarial harness: capability gate, YAML activation and host binding.

PASS means the attempted counterexample was rejected. The harness is fully
offline: safety kernel blocks network and all durable probes use a fresh
temporary database.
"""
from __future__ import annotations

import inspect
import os
import sqlite3
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["NIA_TEST_MODE"] = "1"
os.environ["NIA_TEST_PROTECTED_DB"] = str(Path("data/agent.db").resolve())
from app.testing.safety_kernel import activate

activate()

from app.core.clock import FixedClock
from app.models import (
    ControlledFetchTransportAuthorization,
    JobExecutionContext,
    _issue_controlled_fetch_transport_authorization,
)
from app.ports import controlled_fetch as module
from app.ports.controlled_fetch import (
    ControlledFetchRequestContract,
    ControlledFetchTransportError,
    ControlledHttpFetch,
    FakeControlledHttpTransport,
    TransportResponse,
    bind_url_target,
)
from app.ports.storage import ControlledFetchAuthorizationError
from app.storage.repositories import SqliteStorage
from app.workflows.research.controlled_fetch import (
    ControlledFetchUnavailableError,
    resolve_controlled_fetch_port,
)
from e2b_refutation_harness import (
    account,
    approve,
    make_settings,
    seed,
)

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
URL = "https://example.com/report"
PUBLIC_IP = "93.184.216.34"
OTHER_IP = "142.250.72.14"
REDIRECT_URL = "https://www.example.org/final"
REDIRECT_IP = "151.101.1.69"

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, defended: bool, detail: str = "") -> None:
    RESULTS.append((name, defended, detail))


def authorization(*, seal_valid: bool = True):
    issuer = _issue_controlled_fetch_transport_authorization
    valid = issuer(
        job_id="job-e2c-h",
        run_id="run-e2c-h",
        account_id="nothing_is_accidental",
        topic_id=1,
        approval_id=1,
        attempt_id=1,
        requested_url=URL,
        source_identity="source",
        intent_fingerprint="a" * 64,
        timeout_seconds=10,
        max_bytes=1000,
        max_redirects=2,
        allowed_content_types=("text/html", "text/plain"),
        approval_expires_at=NOW + timedelta(hours=1),
    )
    if seal_valid:
        return valid
    return ControlledFetchTransportAuthorization(
        **{**valid.__dict__, "_seal": object()},
    )


def contract() -> ControlledFetchRequestContract:
    return ControlledFetchRequestContract(
        requested_url=URL,
        timeout_seconds=10,
        max_bytes=1000,
        max_redirects=2,
        allowed_content_types=("text/html", "text/plain"),
    )


def h1_public_real_constructor_absent() -> None:
    record(
        "H1 public real transport constructor is absent",
        not hasattr(module, "RealControlledHttpTransport"),
    )


def h2_private_constructor_requires_factory_seal() -> None:
    blocked = False
    try:
        module._RealControlledHttpTransport(_seal=object())
    except TypeError:
        blocked = True
    record("H2 direct private transport construction is rejected", blocked)


def h3_forged_capability_cannot_build_real_port() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        settings.controlled_fetch_real_enabled = True
        blocked = False
        try:
            resolve_controlled_fetch_port(
                authorization(seal_valid=False),
                settings=settings,
                clock=FixedClock(NOW),
            )
        except TypeError:
            blocked = True
        record("H3 forged capability cannot build real port", blocked)


def h4_env_cannot_enable_real_transport() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        settings.controlled_fetch_real_enabled = False
        os.environ["REAL_CONTROLLED_FETCH_ENABLED"] = "1"
        for variable in (
            "NIA_CONTROLLED_FETCH_FAKE",
            "NIA_CONTROLLED_FETCH_FIXTURE",
        ):
            os.environ.pop(variable, None)
        blocked = False
        try:
            resolve_controlled_fetch_port(
                authorization(),
                settings=settings,
                clock=FixedClock(NOW),
            )
        except ControlledFetchUnavailableError:
            blocked = True
        record("H4 ENV cannot replace the YAML global activation gate", blocked)


def h5_initial_dns_result_is_reused_by_transport() -> None:
    calls: list[str] = []

    def resolver(hostname: str) -> tuple[str, ...]:
        calls.append(hostname)
        if len(calls) > 1:
            return ("127.0.0.1",)
        return (PUBLIC_IP,)

    transport = FakeControlledHttpTransport({
        URL: TransportResponse(200, "text/html", None, b"ok", True),
    })
    adapter = ControlledHttpFetch(
        contract=contract(),
        transport=transport,
        resolver=resolver,
        clock=FixedClock(NOW),
    )
    adapter.preflight_boundary()
    document = adapter.fetch(URL)
    defended = (
        document.error is None
        and calls == ["example.com"]
        and transport.calls[0]["selected_address"] == PUBLIC_IP
    )
    record("H5 transport consumes the single approved DNS binding", defended)


def h6_mixed_safe_and_private_dns_result_is_rejected() -> None:
    binding = bind_url_target(
        URL,
        resolver=lambda _hostname: (PUBLIC_IP, "10.0.0.7"),
    )
    record(
        "H6 every resolved address must pass policy",
        not binding.decision.allowed
        and binding.decision.code == "ADDRESS_PRIVATE",
    )


def h7_empty_dns_result_is_rejected() -> None:
    binding = bind_url_target(URL, resolver=lambda _hostname: ())
    record(
        "H7 empty resolution fails closed",
        not binding.decision.allowed
        and binding.decision.code == "DNS_RESOLUTION_FAILED",
    )


def h8_redirect_gets_new_independent_binding() -> None:
    calls: list[str] = []
    addresses = {
        "example.com": (PUBLIC_IP,),
        "www.example.org": (REDIRECT_IP,),
    }

    def resolver(hostname: str) -> tuple[str, ...]:
        calls.append(hostname)
        return addresses[hostname]

    transport = FakeControlledHttpTransport({
        URL: TransportResponse(302, None, REDIRECT_URL, b"", True),
        REDIRECT_URL: TransportResponse(200, "text/plain", None, b"ok", True),
    })
    adapter = ControlledHttpFetch(
        contract=contract(),
        transport=transport,
        resolver=resolver,
        clock=FixedClock(NOW),
    )
    document = adapter.fetch(URL)
    record(
        "H8 redirect is rebound once and preserves its own Host/SNI",
        document.error is None
        and calls == ["example.com", "www.example.org"]
        and transport.calls[1]["selected_address"] == REDIRECT_IP
        and transport.calls[1]["host_header"] == "www.example.org"
        and transport.calls[1]["tls_server_name"] == "www.example.org",
    )


def h9_forged_selected_address_is_rejected() -> None:
    binding = bind_url_target(
        URL,
        resolver=lambda _hostname: (PUBLIC_IP, OTHER_IP),
    )
    assert binding.target is not None
    forged = replace(binding.target, selected_address=OTHER_IP)
    blocked = False
    try:
        FakeControlledHttpTransport().request(
            forged,
            timeout_seconds=10,
            max_read_bytes=100,
        )
    except ControlledFetchTransportError as exc:
        blocked = exc.code == "BOUND_TARGET_INVALID"
    record("H9 transport rejects a changed selected address", blocked)


def h10_real_transport_has_no_reresolution_path() -> None:
    source = inspect.getsource(module._RealControlledHttpTransport.request)
    record(
        "H10 real transport has no DNS, urllib or proxy path",
        "selected_address" in source
        and "getaddrinfo" not in source
        and "urllib" not in source
        and "Proxy" not in source,
    )


def h11_storage_capability_lives_only_in_reserved_window() -> None:
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        acc = account()
        settings = make_settings(tmp)
        topic, job_id, intent = seed(
            settings,
            acc,
            requested_at=NOW,
            expires_at=NOW + timedelta(hours=6),
        )
        approve(settings, acc, job_id, expires=timedelta(days=2))
        clock = FixedClock(NOW + timedelta(seconds=1))
        storage = SqliteStorage.open(settings.db_path)
        try:
            lease = storage.claim_next_job("e2c-h", 60, clock=clock)
            assert lease is not None
            initialized = storage.initialize_controlled_fetch_run_for_job(
                job_id,
                "e2c-h",
                "run-e2c-h",
                clock=clock,
            )
            execution = JobExecutionContext(
                job_id=job_id,
                lease_owner="e2c-h",
                run_id=initialized.run.id,
                clock=clock,
            )
            attempt = storage.begin_controlled_fetch_attempt(execution)
            issued = storage.authorize_controlled_fetch_transport(
                execution,
                attempt.id,
            )
            issued.assert_storage_issued()
            storage.mark_controlled_fetch_request_started(execution, attempt.id)
            blocked_after_start = False
            try:
                storage.authorize_controlled_fetch_transport(
                    execution,
                    attempt.id,
                )
            except ControlledFetchAuthorizationError:
                blocked_after_start = True
            approval = storage.get_controlled_fetch_approval_for_job(job_id)
            record(
                "H11 storage capability requires consumed L1 and RESERVED",
                approval.consumed_at is not None
                and issued.job_id == job_id
                and issued.account_id == acc.id
                and issued.topic_id == topic.id
                and issued.intent_fingerprint == intent.fingerprint
                and blocked_after_start,
            )
        finally:
            storage.close()


def h12_raw_sqlite_fk_off_cannot_tamper_contract() -> None:
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        acc = account()
        settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        raw = sqlite3.connect(settings.db_path)
        try:
            raw.execute("PRAGMA foreign_keys=OFF")
            payload = raw.execute(
                "SELECT payload_json FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()[0]
            blocked_payload = False
            try:
                raw.execute(
                    "UPDATE jobs SET payload_json=? WHERE id=?",
                    (
                        payload.replace(
                            "https://example.com/report",
                            "https://evil.invalid/steal",
                        ),
                        job_id,
                    ),
                )
            except sqlite3.IntegrityError:
                blocked_payload = True
            raw.rollback()

            blocked_approval = False
            try:
                raw.execute(
                    "INSERT INTO controlled_fetch_approvals "
                    "(job_id,account_id,action_type,requested_url,"
                    "intent_fingerprint,timeout_seconds,max_bytes,max_redirects,"
                    "approved_by,approved_at,expires_at,consumed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                    (
                        job_id,
                        acc.id,
                        "CONTROLLED_FETCH",
                        "https://evil.invalid/steal",
                        "0" * 64,
                        intent.timeout_seconds,
                        intent.max_bytes,
                        intent.max_redirects,
                        "attacker",
                        "2026-07-19 12:00:00",
                        "2026-07-19 13:00:00",
                    ),
                )
            except sqlite3.IntegrityError:
                blocked_approval = True
            raw.rollback()
            record(
                "H12 raw SQLite FK OFF cannot change payload or forge approval",
                raw.execute("PRAGMA foreign_keys").fetchone()[0] == 0
                and blocked_payload
                and blocked_approval
                and raw.execute(
                    "SELECT count(*) FROM controlled_fetch_approvals",
                ).fetchone()[0] == 0,
            )
        finally:
            raw.close()


def h13_two_workers_cannot_claim_the_same_approved_job() -> None:
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        acc = account()
        settings = make_settings(tmp)
        topic, job_id, intent = seed(
            settings,
            acc,
            requested_at=NOW,
            expires_at=NOW + timedelta(hours=6),
        )
        approve(settings, acc, job_id, expires=timedelta(days=2))
        barrier = threading.Barrier(2)

        def claim(owner: str):
            storage = SqliteStorage.open(settings.db_path)
            try:
                barrier.wait()
                lease = storage.claim_next_job(
                    owner,
                    60,
                    clock=FixedClock(NOW + timedelta(seconds=1)),
                )
                return lease.job.id if lease is not None else None
            finally:
                storage.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("e2c-race-a", "e2c-race-b")))
        storage = SqliteStorage.open(settings.db_path)
        try:
            approval = storage.get_controlled_fetch_approval_for_job(job_id)
            record(
                "H13 two workers yield one lease and zero transport attempts",
                results.count(job_id) == 1
                and results.count(None) == 1
                and approval.consumed_at is None
                and storage.conn.execute(
                    "SELECT count(*) FROM controlled_fetch_attempts",
                ).fetchone()[0] == 0,
            )
        finally:
            storage.close()


HYPOTHESES = [
    h1_public_real_constructor_absent,
    h2_private_constructor_requires_factory_seal,
    h3_forged_capability_cannot_build_real_port,
    h4_env_cannot_enable_real_transport,
    h5_initial_dns_result_is_reused_by_transport,
    h6_mixed_safe_and_private_dns_result_is_rejected,
    h7_empty_dns_result_is_rejected,
    h8_redirect_gets_new_independent_binding,
    h9_forged_selected_address_is_rejected,
    h10_real_transport_has_no_reresolution_path,
    h11_storage_capability_lives_only_in_reserved_window,
    h12_raw_sqlite_fk_off_cannot_tamper_contract,
    h13_two_workers_cannot_claim_the_same_approved_job,
]


def main() -> int:
    for hypothesis in HYPOTHESES:
        try:
            hypothesis()
        except Exception:
            record(
                hypothesis.__name__,
                False,
                "HARNESS EXCEPTION:\n" + traceback.format_exc(),
            )
    print("=" * 78)
    print("E2-C LIVE-READINESS HARNESS — PASS = counterexample rejected")
    print("=" * 78)
    passed = 0
    for name, defended, detail in RESULTS:
        status = "PASS" if defended else "FAIL"
        passed += int(defended)
        print(f"[{status}] {name}")
        if detail:
            print("    " + detail.replace("\n", "\n    "))
    print("-" * 78)
    print(f"RESULT: {passed}/{len(RESULTS)} invariants defended")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
