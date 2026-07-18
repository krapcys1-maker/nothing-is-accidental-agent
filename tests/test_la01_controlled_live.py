"""LA-01-R1 controlled-live regression and counterexample suite (offline only)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import app.operations.controlled_live as controlled
from app.models import Job, JobKind, Topic, TopicStatus, WorkflowType
from app.operations.controlled_live import (
    ControlledLiveRequest,
    ControlledWorkerContract,
    DbFingerprint,
    DeterministicFakeControlledWorkerAdapter,
    FAIL_CLOSED_ORDER,
    FAIL_CLOSED_PROFILE,
    OPEN_PROFILE_ORDER,
    WorkerOnceResult,
    acquire_session_marker,
    clear_session_marker,
    confirm_flags,
    is_fail_closed,
    marker_path,
    read_session_marker,
    run_controlled_live_once,
    sanitize_report_payload,
    write_operator_report,
    write_session_marker,
)
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.research.durable_intent import controlled_session_contract
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from scripts import run_capped_research

from tests.conftest import write_approved_pricing_profile

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
MODEL = "dry-run-fake"
HEAD = "a" * 40
BRANCH = "dev/test"
DB_SHA = "B" * 64


class FixedClock:
    def now(self):
        return NOW


def _prepare(storage, account, tmp_path):
    storage.ensure_account(account)
    storage.apply_security_flag_profile(
        FAIL_CLOSED_ORDER,
        updated_by="test",
        reason="controlled-live fixture",
        now=NOW,
    )
    topic = storage.add_topic(
        account.id,
        Topic(
            account_id=account.id,
            title="Controlled topic",
            question="Private prompt: why?",
            score=90.0,
            status=TopicStatus.SELECTED,
        ),
    )
    _, pricing = write_approved_pricing_profile(
        tmp_path,
        model=MODEL,
        profile_id="p-approved",
    )
    return topic, pricing


def _request(topic, account, **changes):
    values = {
        "account_id": account.id,
        "topic_id": int(topic.id),
        "operation_key": "controlled-once",
        "model": MODEL,
        "pricing_profile_id": "p-approved",
        "max_tokens": 1000,
        "max_web_searches": 2,
        "max_cost_usd": "0.500000",
        "expected_db_sha256": DB_SHA,
        "expected_schema": "0014",
        "expected_branch": BRANCH,
        "expected_head": HEAD,
        "max_attempts": 1,
        "max_retries": 0,
    }
    values.update(changes)
    return ControlledLiveRequest(**values)


def _git(branch=BRANCH, head=HEAD):
    return lambda _root: (branch, head)


def _db():
    return lambda _path: DbFingerprint(DB_SHA, 1, "0014_provider")


def _clean_quiescence():
    return {
        "project_process_ids": (),
        "scheduled_tasks": (),
        "locked_paths": (),
    }


def _refresh_fixture_storage(storage, settings):
    try:
        storage.conn.execute("SELECT 1").fetchone()
    except sqlite3.ProgrammingError:
        replacement = SqliteStorage.open(settings.db_path)
        storage.conn = replacement.conn


def _run(
    storage,
    settings,
    account,
    tmp_path,
    topic,
    pricing,
    *,
    worker=None,
    request_changes=None,
    git=None,
    quiescence=None,
    report_writer=write_operator_report,
    marker_clearer=clear_session_marker,
    reopen_calls=None,
    allow_job_creation=True,
):
    effective = replace(settings, model_quality=MODEL, dry_run=False)
    clock = FixedClock()
    runner = worker or DeterministicFakeControlledWorkerAdapter(
        storage=storage,
        settings=effective,
        clock=clock,
    )

    def reopen():
        if reopen_calls is not None:
            reopen_calls.append(object())
        return SqliteStorage.open(effective.db_path)

    outcome = run_controlled_live_once(
        _request(topic, account, **(request_changes or {})),
        settings=effective,
        storage=storage,
        storage_reopener=reopen,
        project_root=tmp_path,
        runtime_dir=tmp_path / "runtime",
        worker_runner=runner,
        git_identity=git or _git(),
        db_fingerprint=_db(),
        frozen_quiescence=quiescence or _clean_quiescence(),
        pricing_profiles_path=pricing,
        clock=clock,
        now=NOW,
        allow_execution=True,
        allow_job_creation=allow_job_creation,
        report_writer=report_writer,
        marker_clearer=marker_clearer,
    )
    _refresh_fixture_storage(storage, effective)
    return outcome


def test_full_fake_success_has_owned_terminal_state_report_and_no_marker(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    effective = replace(settings, model_quality=MODEL, dry_run=False)
    profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing),
        profile_id="p-approved",
        model=MODEL,
    )
    enqueue_args = SimpleNamespace(
        mode="single",
        force_re_research=False,
        operation_key="controlled-once",
        pricing_profile="p-approved",
        max_web_searches=2,
    )
    assert run_capped_research._enqueue_durable_real_job(
        enqueue_args,
        storage,
        account,
        topic,
        effective,
        max_cost_usd=0.5,
        request_max_tokens=1000,
        approved_profile=profile,
        now=NOW,
    ) == 0
    persisted = storage.get_job(_request(topic, account).job_id())
    assert persisted.earliest_run_at == NOW.replace(tzinfo=None)
    assert persisted.payload["controlled_session"] == controlled_session_contract(
        "controlled-once",
        job_id=persisted.id,
    )
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        allow_job_creation=False,
    )
    assert outcome.status == "COMPLETED_FAIL_CLOSED"
    assert outcome.exit_code == 0
    assert outcome.worker_result.job_id == outcome.plan.job_id
    assert outcome.worker_result.request_id == outcome.plan.request_id
    assert outcome.worker_result.attempt_no == 1
    assert is_fail_closed(outcome.flags_after)
    assert outcome.report_path.is_file()
    assert not marker_path(tmp_path / "runtime").exists()
    job = storage.get_job(outcome.plan.job_id)
    assert job.status.value == "DONE"
    attempts = storage.conn.execute(
        "SELECT status,attempt_no,request_id,request_started_at,actual_cost_usd "
        "FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchall()
    assert [(row["status"], row["attempt_no"], row["request_id"]) for row in attempts] == [
        ("SETTLED", 1, outcome.plan.request_id)
    ]
    assert attempts[0]["request_started_at"] is not None
    assert attempts[0]["actual_cost_usd"] is not None
    assert job.attempts == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?",
        (outcome.plan.request_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE job_id=? AND attempt_no<>1",
        (job.id,),
    ).fetchone()[0] == 0


def test_open_and_close_profiles_are_atomic_and_ordered(
    storage, settings, account, tmp_path, monkeypatch,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    writes = []
    original = storage.apply_security_flag_profile

    def spy(profile, **kwargs):
        writes.append(list(profile))
        return original(profile, **kwargs)

    monkeypatch.setattr(storage, "apply_security_flag_profile", spy)
    outcome = _run(storage, settings, account, tmp_path, topic, pricing)
    assert outcome.exit_code == 0
    assert writes == [OPEN_PROFILE_ORDER, FAIL_CLOSED_ORDER]
    assert writes[0][-1] == ("kill_switch", False)
    assert writes[1][0] == ("kill_switch", True)


@pytest.mark.parametrize(
    ("request_changes", "expected"),
    [
        ({"expected_branch": "foreign"}, "PREFLIGHT_FAILED"),
        ({"expected_head": "0" * 40}, "PREFLIGHT_FAILED"),
        ({"max_attempts": 2}, "PREFLIGHT_FAILED"),
        ({"max_retries": 1}, "PREFLIGHT_FAILED"),
        ({"max_cost_usd": "0.000001"}, "PREFLIGHT_FAILED"),
    ],
)
def test_preflight_gates_stop_before_worker(
    storage, settings, account, tmp_path, request_changes, expected,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    calls = 0

    def worker(_contract):
        nonlocal calls
        calls += 1
        raise AssertionError("worker must not run")

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=worker,
        request_changes=request_changes,
    )
    assert outcome.status == expected
    assert outcome.exit_code != 0
    assert calls == 0
    assert is_fail_closed(confirm_flags(storage))


@pytest.mark.parametrize(
    "quiescence",
    [
        {"project_process_ids": (123,), "scheduled_tasks": (), "locked_paths": ()},
        {"project_process_ids": (), "scheduled_tasks": ("NIA Worker",), "locked_paths": ()},
        {"project_process_ids": (), "scheduled_tasks": (), "locked_paths": ("agent.db",)},
    ],
)
def test_real_quiescence_dimensions_block(
    storage, settings, account, tmp_path, quiescence,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        quiescence=quiescence,
    )
    assert outcome.status == "PREFLIGHT_FAILED"
    assert outcome.exit_code != 0


def test_process_preflight_report_preserves_inner_code_and_safe_diagnostics(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    secret = "sk-live-super-secret-value"
    private_prompt = "private unreleased prompt words"
    diagnostics = (
        {
            "pid": 902,
            "parent_pid": 90,
            "executable": r"C:\Python\python.exe",
            "command_line": (
                "python.exe -m app.main worker --once "
                f"--api-key {secret} --prompt \"{private_prompt}\" --max-tokens 5"
            ),
            "creation_time_utc": "2026-07-17T10:00:02.0000000Z",
            "classification": "BLOCKING_APPLICATION_PROCESS",
            "reason_codes": ("APP_ROLE_WORKER",),
            "blocking": True,
            "belongs_to_probe_ancestry": False,
        },
        {
            "pid": 321,
            "parent_pid": 123,
            "executable": r"C:\Windows\System32\cmd.exe",
            "command_line": "cmd /c python -m app.main controlled-live-once",
            "creation_time_utc": "2026-07-17T10:00:01.0000000Z",
            "classification": "BLOCKING_APPLICATION_PROCESS",
            "reason_codes": ("APP_ROLE_OPERATOR_CLI",),
            "blocking": True,
            "belongs_to_probe_ancestry": False,
        },
    )
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        quiescence={
            "project_process_ids": (902, 321),
            "scheduled_tasks": (),
            "locked_paths": (),
            "probe_current_pid": 100,
            "probe_parent_pid": 90,
            "probe_ancestry_process_ids": (90, 100),
            "probe_helper_process_ids": (101,),
            "process_diagnostics": diagnostics,
        },
    )

    report_text = outcome.report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    error = report["error"]
    assert report["reason_code"] == "PREFLIGHT_FAILED"
    assert report["final_status"] == "PREFLIGHT_FAILED"
    assert error["outer_reason_code"] == "PREFLIGHT_FAILED"
    assert error["reason_code"] == "PROCESSES_PRESENT"
    assert error["failing_invariant"] == "QUIESCENCE_PROJECT_PROCESSES"
    assert error["check_order"] == 6
    assert error["blocking_process_ids"] == [321, 902]
    assert [item["pid"] for item in error["process_diagnostics"]] == [321, 902]
    assert error["process_diagnostics"][0]["classification"]
    assert error["process_diagnostics"][0]["reason_codes"]
    assert error["process_diagnostics"][0]["belongs_to_probe_ancestry"] is False
    assert error["process_diagnostics"][0]["identity_fingerprint"]
    assert error["diagnostic_fingerprint"]
    assert secret not in report_text
    assert private_prompt not in report_text
    assert "[REDACTED]" in report_text
    assert report["provider_request_started"] is False


def test_fake_controlled_live_flow_does_not_block_on_verified_ancestry(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    quiescence = {
        "project_process_ids": (),
        "scheduled_tasks": (),
        "locked_paths": (),
        "probe_current_pid": 100,
        "probe_parent_pid": 90,
        "probe_ancestry_process_ids": (80, 90, 100),
        "probe_helper_process_ids": (101,),
        "process_diagnostics": (
            {
                "pid": 80,
                "parent_pid": 1,
                "executable": "cmd.exe",
                "command_line": "cmd /c python -m app.main controlled-live-once",
                "creation_time_utc": "2026-07-17T10:00:00.0000000Z",
                "classification": "PROBE_ANCESTRY_LAUNCHER",
                "reason_codes": ("VERIFIED_PROBE_ANCESTRY",),
                "blocking": False,
                "belongs_to_probe_ancestry": True,
            },
        ),
    }

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        quiescence=quiescence,
    )

    assert outcome.status == "COMPLETED_FAIL_CLOSED"
    assert outcome.exit_code == 0
    assert outcome.worker_result.attempt_no == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?",
        (outcome.plan.job_id,),
    ).fetchone()[0] == 1


def test_default_quiescence_probe_delegates_to_approved_probe(monkeypatch, tmp_path):
    seen = []

    class Report:
        project_process_ids = (7,)
        scheduled_tasks = ("task",)
        locked_paths = ("db",)

    import app.operations.stage1_migration as migration

    monkeypatch.setattr(
        migration,
        "_default_quiesce_probe",
        lambda root, db: seen.append((root, db)) or Report(),
    )
    result = controlled.default_quiescence_probe(tmp_path, tmp_path / "agent.db")
    assert seen == [(tmp_path, tmp_path / "agent.db")]
    assert result["project_process_ids"] == (7,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_id", "foreign-job"),
        ("request_id", "foreign-request"),
        ("attempt_no", 2),
        ("worker_execution_token", "foreign-fence"),
    ],
)
def test_foreign_worker_result_never_completes(
    storage, settings, account, tmp_path, field, value,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    base = DeterministicFakeControlledWorkerAdapter(
        storage=storage,
        settings=replace(settings, model_quality=MODEL, dry_run=False),
        clock=FixedClock(),
    )

    def forged(contract):
        return replace(base(contract), **{field: value})

    outcome = _run(
        storage, settings, account, tmp_path, topic, pricing, worker=forged
    )
    assert outcome.status == "VALIDATION_FAILED_FAIL_CLOSED"
    assert outcome.exit_code != 0
    assert is_fail_closed(outcome.flags_after)


def test_success_text_without_attempt_usage_or_settlement_is_rejected(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def text_only(contract):
        return WorkerOnceResult(
            status="SUCCEEDED",
            job_id=contract.expected_job_id,
            request_id=contract.expected_request_id,
            attempt_no=1,
            worker_execution_token=contract.worker_execution_token,
        )

    outcome = _run(
        storage, settings, account, tmp_path, topic, pricing, worker=text_only
    )
    assert outcome.status == "VALIDATION_FAILED_FAIL_CLOSED"
    assert outcome.exit_code != 0
    assert "COMPLETED" not in outcome.status


@pytest.mark.parametrize(
    "counterexample",
    [
        "missing_attempt",
        "attempt_two",
        "missing_usage",
        "missing_settlement",
        "nonterminal_job",
    ],
)
def test_durable_success_counterexamples_never_complete(
    monkeypatch,
    storage,
    settings,
    account,
    tmp_path,
    counterexample,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    original_evidence = controlled._execution_evidence

    def forged_evidence(*args, **kwargs):
        evidence = original_evidence(*args, **kwargs)
        evidence = {
            **evidence,
            "job": (
                None
                if evidence["job"] is None
                else dict(evidence["job"])
            ),
            "attempts": [
                dict(attempt) for attempt in evidence["attempts"]
            ],
            "usage": [dict(row) for row in evidence["usage"]],
        }
        if counterexample == "missing_attempt":
            evidence["attempts"] = []
        elif counterexample == "attempt_two":
            second = dict(evidence["attempts"][0])
            second["attempt_no"] = 2
            second["request_id"] = f"{second['job_id']}:research:2"
            evidence["attempts"].append(second)
        elif counterexample == "missing_usage":
            evidence["usage"] = []
        elif counterexample == "missing_settlement":
            evidence["attempts"][0]["status"] = "REQUEST_STARTED"
            evidence["attempts"][0]["settled_at"] = None
            evidence["attempts"][0]["actual_cost_usd"] = None
        elif counterexample == "nonterminal_job":
            evidence["job"]["status"] = "RUNNING"
        return evidence

    monkeypatch.setattr(controlled, "_execution_evidence", forged_evidence)
    outcome = _run(storage, settings, account, tmp_path, topic, pricing)
    assert outcome.status == "VALIDATION_FAILED_FAIL_CLOSED"
    assert outcome.exit_code != 0
    assert "COMPLETED" not in outcome.status


def test_repeated_worker_claim_still_creates_at_most_one_request(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    adapter = DeterministicFakeControlledWorkerAdapter(
        storage=storage,
        settings=replace(settings, model_quality=MODEL, dry_run=False),
        clock=FixedClock(),
    )

    def twice(contract):
        first = adapter(contract)
        second = adapter(contract)
        assert first.status == "SUCCEEDED"
        assert second.status == "IDLE"
        return first

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=twice,
    )
    assert outcome.exit_code == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?",
        (outcome.plan.job_id,),
    ).fetchone()[0] == 1


def test_bare_worker_winning_claim_is_fenced_and_recovered(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def bare(_contract):
        lease = storage.claim_next_job("bare-worker", 120, now=NOW)
        assert lease is not None
        return WorkerOnceResult(
            "SUCCEEDED",
            lease.job.id,
            f"{lease.job.id}:research:1",
            1,
            "bare-worker",
        )

    outcome = _run(
        storage, settings, account, tmp_path, topic, pricing, worker=bare
    )
    assert outcome.exit_code != 0
    assert outcome.status == "VALIDATION_FAILED_FAIL_CLOSED"
    job = storage.get_job(outcome.plan.job_id)
    assert job.status.value == "NEEDS_VERIFICATION"
    assert job.lease_owner is None
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (job.id,)
    ).fetchone()[0] == 0


def test_dispatcher_session_fence_rejects_bare_lease(
    storage, settings, account, tmp_path,
):
    from app.policies.policy_engine import PolicyEngine
    from app.scheduler.dispatcher import JobDispatcher, PayloadValidationError

    topic, pricing = _prepare(storage, account, tmp_path)
    contract = ControlledWorkerContract(
        "session",
        "operation",
        "job",
        "job:research:1",
        1,
        "expected-fence",
    )
    profile = controlled.resolve_real_pricing_profile(
        controlled.load_pricing_profiles(pricing),
        profile_id="p-approved",
        model=MODEL,
    )
    intent = controlled.DurableResearchExecutionIntent.from_settings(
        settings=replace(settings, model_quality=MODEL),
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd="0.5",
        max_web_searches=2,
        question="private",
        niche=account.niche,
        max_tokens=1000,
        pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )
    job = Job(
        id="job",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key="real-research:operation",
        topic_id=int(topic.id),
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
            "controlled_session": contract.as_dict(),
        },
    )
    dispatcher = JobDispatcher(
        settings=replace(settings, model_quality=MODEL),
        storage=storage,
        policy=PolicyEngine(settings, storage, FixedClock()),
        clock=FixedClock(),
    )
    with pytest.raises(PayloadValidationError, match="fence"):
        dispatcher._validate_research_payload(job, lease_owner="bare-worker")


def test_future_earliest_run_at_is_not_claimable(
    storage, settings, account, tmp_path,
):
    storage.ensure_account(account)
    job = Job(
        id="future",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="future",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW + timedelta(minutes=1),
    )
    storage.enqueue_job(job)
    assert controlled._claimable_job_ids(storage, NOW) == ()


@pytest.mark.parametrize(
    ("clock_offset", "claimable"),
    [
        (timedelta(microseconds=-1), False),
        (timedelta(0), True),
        (timedelta(microseconds=1), True),
    ],
    ids=("before-earliest", "exactly-earliest", "after-earliest"),
)
def test_claimability_uses_one_explicit_clock_at_earliest_boundary(
    storage, account, clock_offset, claimable,
):
    storage.ensure_account(account)
    storage.enqueue_job(Job(
        id="clock-boundary",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="clock-boundary",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
    ))
    observed = controlled._claimable_job_ids(storage, NOW + clock_offset)
    assert (observed == ("clock-boundary",)) is claimable


def test_report_write_failure_is_nonzero_and_retains_marker(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def fail_report(*_args, **_kwargs):
        raise OSError("private prompt and sk-secret-value")

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        report_writer=fail_report,
    )
    assert outcome.status == "REPORT_WRITE_FAILED_RECOVERY_REQUIRED"
    assert outcome.exit_code != 0
    assert marker_path(tmp_path / "runtime").exists()
    assert "COMPLETED" not in outcome.status


def test_report_is_durable_before_marker_removal(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    order = []

    def writer(directory, session_id, payload):
        path = write_operator_report(directory, session_id, payload)
        order.append(("report", path.exists()))
        return path

    def clearer(runtime):
        order.append(("clear", marker_path(runtime).exists()))
        clear_session_marker(runtime)

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        report_writer=writer,
        marker_clearer=clearer,
    )
    assert outcome.exit_code == 0
    first_clear = next(index for index, event in enumerate(order) if event[0] == "clear")
    assert any(event == ("report", True) for event in order[:first_clear])
    assert order[first_clear] == ("clear", True)


def test_same_operation_key_preserves_preflight_and_terminal_report_history(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    first = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        request_changes={"expected_head": "b" * 40},
    )
    second = _run(storage, settings, account, tmp_path, topic, pricing)

    assert first.status == "PREFLIGHT_FAILED"
    assert second.status == "COMPLETED_FAIL_CLOSED"
    assert first.session_id == second.session_id
    assert first.report_path != second.report_path
    reports = sorted((tmp_path / "runtime" / "controlled_live_reports").glob("*.json"))
    assert reports == sorted([first.report_path, second.report_path])
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
    assert {payload["final_status"] for payload in payloads} == {
        "PREFLIGHT_FAILED", "COMPLETED_FAIL_CLOSED",
    }
    assert len({payload["invocation_id"] for payload in payloads}) == 2
    assert all(path.stem.startswith(first.session_id + "--") for path in reports)


def test_marker_clear_failure_is_nonzero_and_explicit(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def fail_clear(_runtime):
        raise OSError("cannot unlink")

    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        marker_clearer=fail_clear,
    )
    assert outcome.status == "MARKER_CLEAR_FAILED_RECOVERY_REQUIRED"
    assert outcome.exit_code != 0
    assert marker_path(tmp_path / "runtime").exists()


def test_sanitizer_redacts_api_key_authorization_prompt_and_raw_exception(
    monkeypatch,
):
    monkeypatch.setenv("PRIVATE_TOKEN", "environment-private-token")
    private_prompt = "The private prompt says investigate a hidden person."
    raw = {
        "api_key": "sk-super-secret-123456",
        "Authorization": "Bearer token-abcdefghi",
        "prompt": private_prompt,
        "worker_detail": (
            "Authorization: Bearer abcdef secret=environment-private-token "
            "sk-provider-secret-999"
        ),
    }
    rendered = json.dumps(sanitize_report_payload(raw))
    for forbidden in (
        "sk-super-secret-123456",
        "token-abcdefghi",
        private_prompt,
        "environment-private-token",
        "sk-provider-secret-999",
    ):
        assert forbidden not in rendered


def test_persistent_report_never_contains_worker_exception_text(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    secret = "sk-private-exception-123456 private prompt literal"

    def explode(_contract):
        raise RuntimeError(secret)

    outcome = _run(
        storage, settings, account, tmp_path, topic, pricing, worker=explode
    )
    text = outcome.report_path.read_text(encoding="utf-8")
    assert secret not in text
    assert "RuntimeError" in text
    assert "diagnostic_fingerprint" in text


def test_true_reopen_uses_new_storage_object(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    calls = []
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        reopen_calls=calls,
    )
    assert outcome.exit_code == 0
    assert len(calls) == 1


def test_frozen_quiescence_is_required_and_none_rejects_without_hidden_probe(
    storage, settings, account, tmp_path, monkeypatch,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    parameter = inspect.signature(run_controlled_live_once).parameters[
        "frozen_quiescence"
    ]
    assert parameter.default is inspect.Parameter.empty
    default_probe_calls = 0
    worker_calls = 0

    def forbidden_default_probe(*_args):
        nonlocal default_probe_calls
        default_probe_calls += 1
        raise AssertionError("open storage must never trigger a hidden handle probe")

    def forbidden_worker(_contract):
        nonlocal worker_calls
        worker_calls += 1
        raise AssertionError("invalid construction must stop before worker/provider")

    monkeypatch.setattr(controlled, "default_quiescence_probe", forbidden_default_probe)
    with pytest.raises(TypeError, match="frozen_quiescence"):
        run_controlled_live_once(
            _request(topic, account),
            settings=replace(settings, model_quality=MODEL, dry_run=False),
            storage=storage,
            storage_reopener=lambda: SqliteStorage.open(settings.db_path),
            project_root=tmp_path,
            runtime_dir=tmp_path / "runtime",
            worker_runner=forbidden_worker,
            frozen_quiescence=None,
            git_identity=_git(),
            db_fingerprint=_db(),
            pricing_profiles_path=pricing,
            clock=FixedClock(),
            now=NOW,
            allow_execution=True,
            allow_job_creation=True,
        )
    assert default_probe_calls == 0
    assert worker_calls == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0] == 0


def test_open_storage_uses_only_explicit_frozen_quiescence(
    storage, settings, account, tmp_path, monkeypatch,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def forbidden_default_probe(*_args):
        raise AssertionError("default handle probe is forbidden after storage open")

    monkeypatch.setattr(controlled, "default_quiescence_probe", forbidden_default_probe)
    outcome = _run(storage, settings, account, tmp_path, topic, pricing)
    assert outcome.status == "COMPLETED_FAIL_CLOSED"


def test_reopen_returning_same_object_fails_and_retains_marker(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    effective = replace(settings, model_quality=MODEL, dry_run=False)
    adapter = DeterministicFakeControlledWorkerAdapter(
        storage=storage, settings=effective, clock=FixedClock()
    )
    outcome = run_controlled_live_once(
        _request(topic, account),
        settings=effective,
        storage=storage,
        storage_reopener=lambda: storage,
        project_root=tmp_path,
        runtime_dir=tmp_path / "runtime",
        worker_runner=adapter,
        git_identity=_git(),
        db_fingerprint=_db(),
        frozen_quiescence=_clean_quiescence(),
        pricing_profiles_path=pricing,
        clock=FixedClock(),
        now=NOW,
        allow_execution=True,
        allow_job_creation=True,
    )
    assert outcome.status == "REOPEN_FAILED_RECOVERY_REQUIRED"
    assert marker_path(tmp_path / "runtime").exists()
    _refresh_fixture_storage(storage, effective)


def test_restoration_failure_retains_marker_and_never_completes(
    storage, settings, account, tmp_path, monkeypatch,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    original = storage.apply_security_flag_profile
    calls = 0

    def fail_restore(profile, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("restore unavailable")
        return original(profile, **kwargs)

    monkeypatch.setattr(storage, "apply_security_flag_profile", fail_restore)
    outcome = _run(storage, settings, account, tmp_path, topic, pricing)
    assert outcome.status == "RESTORE_FAILED_RECOVERY_REQUIRED"
    assert outcome.exit_code != 0
    assert marker_path(tmp_path / "runtime").exists()


def _started_then_raise(storage, settings):
    def worker(contract):
        lease = storage.claim_next_job(
            contract.worker_execution_token, 120, now=NOW
        )
        storage.mark_job_running(
            lease.job.id, contract.worker_execution_token, now=NOW
        )
        initialized = storage.initialize_research_run_for_job(
            lease.job.id,
            contract.worker_execution_token,
            "recovery-run",
            now=NOW,
        )
        execution = controlled.JobExecutionContext(
            job_id=lease.job.id,
            lease_owner=contract.worker_execution_token,
            run_id=initialized.run.id,
            clock=FixedClock(),
        )
        attempt = storage.begin_provider_attempt(
            execution,
            stage="research",
            attempt_no=1,
            max_cost_usd=0.5,
            daily_limit_usd=2.0,
            monthly_limit_usd=40.0,
        )
        storage.mark_provider_attempt_request_started(
            execution, attempt.request_id
        )
        raise TimeoutError("unknown provider outcome")

    return worker


def test_request_started_failure_is_escalated_without_retry(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=_started_then_raise(storage, settings),
    )
    assert outcome.status == "WORKER_ERROR_FAIL_CLOSED"
    attempt = storage.conn.execute(
        "SELECT status,request_started_at FROM provider_attempts WHERE job_id=?",
        (outcome.plan.job_id,),
    ).fetchone()
    assert attempt["status"] == "NEEDS_RECONCILIATION"
    assert attempt["request_started_at"] is not None
    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert report["post_execution_recovery"]["provider_request_started"] is True
    assert report["post_execution_recovery"]["retry_performed"] is False
    assert report["post_execution_recovery"]["possible_unknown_provider_outcome"] is True


def test_startup_recovery_reads_persistent_provider_state_and_never_calls_worker(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)

    def fail_report(*_args):
        raise OSError("retain marker")

    first = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=_started_then_raise(storage, settings),
        report_writer=fail_report,
    )
    assert first.status == "REPORT_WRITE_FAILED_RECOVERY_REQUIRED"
    retained_marker = read_session_marker(tmp_path / "runtime")
    assert retained_marker is not None
    retained_report_key = retained_marker["report_key"]
    calls = 0

    def forbidden(_contract):
        nonlocal calls
        calls += 1
        raise AssertionError("recovery must not retry")

    second = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=forbidden,
    )
    assert second.status == "RECOVERY_FORCED_FAIL_CLOSED"
    assert second.exit_code != 0
    assert calls == 0
    assert second.recovery["provider_request_started"] is True
    assert second.recovery["possible_unknown_provider_outcome"] is True
    assert second.recovery["retry_performed"] is False
    assert second.recovery["recovered_report_key"] == retained_report_key
    assert second.report_path.stem != retained_report_key
    recovery_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert recovery_report["recovery"]["recovered_report_key"] == retained_report_key
    assert not marker_path(tmp_path / "runtime").exists()


def test_marker_and_report_paths_use_file_and_directory_durability(
    tmp_path, monkeypatch,
):
    file_fsync = []
    dir_fsync = []
    real_fsync = os.fsync
    real_dirsync = controlled._fsync_directory

    def fsync_spy(fd):
        file_fsync.append(fd)
        return real_fsync(fd)

    def dirsync_spy(directory):
        dir_fsync.append(Path(directory))
        return real_dirsync(Path(directory))

    monkeypatch.setattr(controlled.os, "fsync", fsync_spy)
    monkeypatch.setattr(controlled, "_fsync_directory", dirsync_spy)
    runtime = tmp_path / "runtime"
    assert acquire_session_marker(runtime, {"session_id": "s", "status": "A"})
    write_session_marker(runtime, {"session_id": "s", "status": "B"})
    write_operator_report(runtime / "reports", "s", {"status": "safe"})
    clear_session_marker(runtime)
    assert len(file_fsync) >= 3
    assert runtime in dir_fsync
    assert runtime / "reports" in dir_fsync
    assert len([path for path in dir_fsync if path == runtime]) >= 3


def test_apply_security_profile_rejects_partial_and_single_setter_cannot_open(
    storage,
):
    with pytest.raises(Exception, match="all five"):
        storage.apply_security_flag_profile(
            [("kill_switch", False), ("worker_enabled", True)]
        )
    with pytest.raises(Exception, match="single"):
        storage.set_system_flag("paid_actions_enabled", True)
    with pytest.raises(Exception, match="single"):
        storage.set_system_flag("kill_switch", False)
    storage.set_system_flag("paid_actions_enabled", False)
    storage.apply_security_flag_profile(OPEN_PROFILE_ORDER)
    assert confirm_flags(storage) == dict(controlled.OPEN_PROFILE)
    storage.apply_security_flag_profile(FAIL_CLOSED_ORDER)
    assert confirm_flags(storage) == dict(FAIL_CLOSED_PROFILE)


def test_operational_marker_read_is_read_only(tmp_path):
    runtime = tmp_path / "runtime"
    assert acquire_session_marker(
        runtime,
        {
            "session_id": "read-only",
            "status": "WORKER_RUNNING",
            "expected_request_id": "job:research:1",
        },
    )
    before = hashlib.sha256(marker_path(runtime).read_bytes()).hexdigest()
    first = read_session_marker(runtime)
    second = read_session_marker(runtime)
    after = hashlib.sha256(marker_path(runtime).read_bytes()).hexdigest()
    assert first == second
    assert before == after


def test_real_execution_gate_calls_wrapper_but_does_not_open_profile(
    storage, settings, account, tmp_path,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    calls = 0

    def worker(_contract):
        nonlocal calls
        calls += 1

    outcome = run_controlled_live_once(
        _request(topic, account),
        settings=replace(settings, model_quality=MODEL),
        storage=storage,
        storage_reopener=lambda: SqliteStorage.open(settings.db_path),
        project_root=tmp_path,
        runtime_dir=tmp_path / "runtime",
        worker_runner=worker,
        git_identity=_git(),
        db_fingerprint=_db(),
        frozen_quiescence=_clean_quiescence(),
        pricing_profiles_path=pricing,
        clock=FixedClock(),
        now=NOW,
        allow_execution=False,
        allow_job_creation=True,
    )
    assert outcome.status == "REAL_EXECUTION_DISABLED"
    assert outcome.exit_code != 0
    assert calls == 0
    assert is_fail_closed(confirm_flags(storage))
    assert not marker_path(tmp_path / "runtime").exists()


def test_canonical_fake_subprocess_runs_cli_wrapper_worker_restore_and_report(
    settings, account, tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current_branch
    db_path = tmp_path / "subprocess" / "agent.db"
    db_path.parent.mkdir(parents=True)
    initialize_database(db_path)
    seed = SqliteStorage.open(db_path)
    seed.ensure_account(account)
    seed.apply_security_flag_profile(
        FAIL_CLOSED_ORDER,
        updated_by="test",
        reason="subprocess fixture",
        now=NOW,
    )
    topic = seed.add_topic(
        account.id,
        Topic(
            account_id=account.id,
            title="Subprocess topic",
            question="Private subprocess prompt",
            score=90.0,
            status=TopicStatus.SELECTED,
        ),
    )
    seed.close()
    _, pricing = write_approved_pricing_profile(
        tmp_path, model=MODEL, profile_id="p-approved"
    )
    runtime = tmp_path / "subprocess-runtime"
    env = dict(os.environ)
    env.update(
        {
            "NIA_TEST_MODE": "1",
            "NIA_CONTROLLED_LIVE_FAKE": "1",
            "NIA_CONTROLLED_LIVE_TEST_DB_PATH": str(db_path),
            "NIA_CONTROLLED_LIVE_TEST_RUNTIME_DIR": str(runtime),
            "NIA_PRICING_PROFILES_PATH": str(pricing),
        }
    )
    command = [
        sys.executable,
        "-m",
        "app.main",
        "controlled-live-once",
        "--account",
        account.id,
        "--topic-id",
        str(topic.id),
        "--operation-key",
        "subprocess-once",
        "--model",
        MODEL,
        "--pricing-profile",
        "p-approved",
        "--max-tokens",
        "1000",
        "--max-web-searches",
        "2",
        "--max-cost-usd",
        "0.5",
        "--expected-db-sha",
        hashlib.sha256(db_path.read_bytes()).hexdigest().upper(),
        "--expected-schema",
        "0014",
        "--expected-branch",
        current_branch,
        "--expected-head",
        current_head,
    ]
    result = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLETED_FAIL_CLOSED" in result.stdout
    reports = list((runtime / "controlled_live_reports").glob("*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["final_status"] == (
        "COMPLETED_FAIL_CLOSED"
    )
    assert not marker_path(runtime).exists()


def _controlled_cli_args(*, topic_id: int, expected_sha: str) -> SimpleNamespace:
    return SimpleNamespace(
        account="nothing_is_accidental",
        topic_id=topic_id,
        operation_key="composition-once",
        model=MODEL,
        pricing_profile="p-approved",
        max_tokens=1000,
        max_web_searches=2,
        max_cost_usd="0.5",
        expected_db_sha=expected_sha,
        expected_schema="0014",
        expected_branch=BRANCH,
        expected_head=HEAD,
        max_attempts=1,
        max_retries=0,
    )


def test_cli_composition_runs_canonical_pre_storage_probe_before_main_open(
    settings, account, tmp_path, monkeypatch,
):
    import app.main as main_module
    import app.operations.stage1_migration as migration

    db_path = tmp_path / "composition" / "agent.db"
    runtime = tmp_path / "composition-runtime"
    initialize_database(db_path)
    seed = SqliteStorage.open(db_path)
    topic, pricing = _prepare(seed, account, tmp_path)
    seed.close()
    expected_sha = hashlib.sha256(db_path.read_bytes()).hexdigest().upper()
    effective = replace(settings, project_root=tmp_path, db_path=db_path)
    monkeypatch.setattr(main_module, "load_settings", lambda: effective)
    monkeypatch.setattr(migration, "_git_identity", lambda _root: (BRANCH, HEAD))
    monkeypatch.setenv("NIA_TEST_MODE", "1")
    monkeypatch.setenv("NIA_CONTROLLED_LIVE_FAKE", "1")
    monkeypatch.setenv("NIA_CONTROLLED_LIVE_TEST_DB_PATH", str(db_path))
    monkeypatch.setenv("NIA_CONTROLLED_LIVE_TEST_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("NIA_PRICING_PROFILES_PATH", str(pricing))

    events: list[str] = []
    real_check = controlled.run_controlled_live_quiescence_check
    real_open = SqliteStorage.open

    def check_spy(**kwargs):
        events.append("pre_storage_probe")
        assert "main_storage_open" not in events
        return real_check(**kwargs)

    def open_spy(cls, path):
        del cls
        events.append("main_storage_open")
        return real_open(path)

    monkeypatch.setattr(controlled, "run_controlled_live_quiescence_check", check_spy)
    monkeypatch.setattr(SqliteStorage, "open", classmethod(open_spy))

    exit_code = main_module._cmd_controlled_live_once(
        _controlled_cli_args(topic_id=int(topic.id), expected_sha=expected_sha)
    )

    assert exit_code == 0
    assert events[0] == "pre_storage_probe"
    assert events.count("pre_storage_probe") == 1
    assert events.index("pre_storage_probe") < events.index("main_storage_open")
    assert not marker_path(runtime).exists()


def test_database_change_between_pre_storage_pass_and_main_open_stops(
    settings, tmp_path, monkeypatch,
):
    import app.main as main_module
    import app.operations.stage1_migration as migration

    db_path = tmp_path / "drift" / "agent.db"
    initialize_database(db_path)
    seed = SqliteStorage.open(db_path)
    seed.close()
    expected_sha = hashlib.sha256(db_path.read_bytes()).hexdigest().upper()
    effective = replace(settings, project_root=tmp_path, db_path=db_path, dry_run=False)
    monkeypatch.setattr(main_module, "load_settings", lambda: effective)
    monkeypatch.setattr(migration, "_git_identity", lambda _root: (BRANCH, HEAD))
    monkeypatch.delenv("NIA_CONTROLLED_LIVE_FAKE", raising=False)
    monkeypatch.setattr(controlled, "REAL_CONTROLLED_LIVE_ENABLED", True)

    def clean_pre_storage(**_kwargs):
        record = {
            "sha256": expected_sha,
            "size": db_path.stat().st_size,
            "mtime_ns": db_path.stat().st_mtime_ns,
            "mtime_utc": "2026-07-17T00:00:00Z",
        }
        return 0, {
            "status": "PASS",
            "reason_code": "QUIESCENT",
            "project_process_ids": (),
            "scheduled_tasks": (),
            "locked_paths": (),
            "database_before": {"database": record, "wal": None, "shm": None},
            "database_after": {"database": record, "wal": None, "shm": None},
            "database_unchanged": True,
        }

    real_open = SqliteStorage.open
    opened = False

    def drifting_open(cls, path):
        nonlocal opened
        del cls
        if not opened:
            opened = True
            connection = sqlite3.connect(path)
            try:
                connection.execute("CREATE TABLE drift_after_pre_storage(id INTEGER)")
                connection.commit()
            finally:
                connection.close()
        return real_open(path)

    monkeypatch.setattr(
        controlled, "run_controlled_live_quiescence_check", clean_pre_storage
    )
    monkeypatch.setattr(SqliteStorage, "open", classmethod(drifting_open))

    exit_code = main_module._cmd_controlled_live_once(
        _controlled_cli_args(topic_id=1, expected_sha=expected_sha)
    )

    assert exit_code != 0
    assert opened is True
    assert not marker_path(tmp_path / "runtime").exists()
    check = sqlite3.connect(db_path)
    try:
        assert check.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0] == 0
        assert check.execute("SELECT COUNT(*) FROM model_usage").fetchone()[0] == 0
    finally:
        check.close()


def test_second_wrapper_loses_marker_fence_before_worker(
    storage, settings, account, tmp_path, monkeypatch,
):
    topic, pricing = _prepare(storage, account, tmp_path)
    worker_calls = 0

    def worker(_contract):
        nonlocal worker_calls
        worker_calls += 1
        raise AssertionError("contending wrapper must not run the worker")

    monkeypatch.setattr(controlled, "acquire_session_marker", lambda *_args: False)
    outcome = _run(
        storage,
        settings,
        account,
        tmp_path,
        topic,
        pricing,
        worker=worker,
    )

    assert outcome.status == "SESSION_CONTENTION"
    assert worker_calls == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0] == 0


def test_production_db_path_is_forbidden_in_tests():
    protected = Path(__file__).resolve().parents[1] / "data" / "agent.db"
    with pytest.raises(RuntimeError, match="must not open"):
        SqliteStorage.open(protected)
