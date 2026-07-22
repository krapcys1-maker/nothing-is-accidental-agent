"""Offline E2E autonomicznego generowania tematów przez PUBLICZNE entrypointy.

Dwa realne procesy potomne:
1. `python -m app.main enqueue-topic-generation` na oczyszczonym środowisku —
   fail-closed odmowa bez dotknięcia chronionej produkcyjnej bazy.
2. Driver uruchamiający PRAWDZIWĄ kompozycję CLI (app.main.main dla enqueue i
   approve, app.main._build_worker + realny JobDispatcher dla workera) na
   tymczasowej bazie, z fake callerem tematów wstrzykniętym WYŁĄCZNIE w fabrykę
   klienta dispatchera (sankcjonowany wzorzec fake SDK/callerów; safety kernel
   blokuje każdy moduł `anthropic`).

Łańcuch dowodzony przez driver:
    enqueue CLI -> reopen SQLite -> approve CLI -> worker entrypoint
    -> provider attempt -> parser -> scoring -> dedup -> lineage
    -> dokładnie jeden SELECTED tego runu -> model_usage -> settlement
    -> job DONE / run SUCCESS -> reopen bazy
    -> istniejący publiczny enqueue Controlled Fetch przyjmuje powstały temat.

Downstream NIE wykonuje realnego Fetchu ani researchu.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _base_env(extra_pythonpath: str = "") -> dict[str, str]:
    env = {
        "NIA_TEST_MODE": "1",
        "NIA_TEST_PROTECTED_DB": str(PROJECT_ROOT / "data" / "agent.db"),
        "PATH": os.environ.get("PATH", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", os.environ.get("SystemRoot", "")),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(PROJECT_ROOT) + (
            os.pathsep + extra_pythonpath if extra_pythonpath else ""
        ),
    }
    return env


def test_enqueue_cli_subprocess_refuses_protected_db_with_scrubbed_env():
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "enqueue-topic-generation",
         "--account-id", "nothing_is_accidental", "--operation-key", "probe",
         "--model", "some-model", "--pricing-profile", "some-profile",
         "--max-tokens", "1500", "--max-cost-usd", "0.5", "--count", "3"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env=_base_env(), check=False,
    )
    assert result.returncode == 2, result.stderr
    assert "failed closed" in result.stderr
    assert "Traceback" not in result.stderr


_DRIVER = '''
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp_root = Path(sys.argv[1])

from app.core.config import Settings
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.models import JobStatus, RunStatus, TopicStatus, WorkflowType
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from tests.conftest import (
    STANDARD_WEIGHTS, make_account, write_approved_pricing_profile,
)
import app.main as main_module

NOW = datetime.now(timezone.utc)
MODEL = "topics-subprocess-model"

account = make_account(active=True)
data_dir = tmp_root / "data"
initialize_database(data_dir / "agent.db")
settings = Settings(
    project_root=tmp_root,
    data_dir=data_dir,
    db_path=data_dir / "agent.db",
    costs_csv_path=tmp_root / "COSTS.csv",
    dry_run=False,
    kill_switch=False,
    max_daily_cost_usd=2.00,
    max_monthly_cost_usd=40.00,
    monthly_limit_has_priority=True,
    model_fast="dry-run-fake",
    model_quality=MODEL,
    pricing={
        "input_per_mtok": 1.0,
        "output_per_mtok": 1.0,
        "cache_read_per_mtok": 1.0,
        "cache_write_per_mtok": 1.0,
        "web_search_per_1k": 1.0,
    },
    article_min_score=75.0,
    note_min_score=65.0,
    topic_scoring_weights=dict(STANDARD_WEIGHTS),
    anthropic_api_key="subprocess-test-key",
    accounts={account.id: account},
)
settings.editorial_schedule = {
    "timezone": "UTC",
    "windows": [{
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "start": "00:00", "end": "23:59",
    }],
}
profile_id, pricing_path = write_approved_pricing_profile(
    tmp_root, model=MODEL, prices=dict(settings.pricing),
)

# The public CLI resolves settings through this one seam.
main_module.load_settings = lambda: settings

# --- 1. PUBLICZNY enqueue: zero requestu, zero tematu ------------------------
code = main_module.main([
    "enqueue-topic-generation",
    "--account-id", account.id,
    "--operation-key", "subprocess-wave-1",
    "--model", MODEL,
    "--pricing-profile", profile_id,
    "--max-tokens", "1500",
    "--max-cost-usd", "1.0",
    "--count", "3",
])
assert code == 0, f"enqueue CLI exit={code}"
print("TOPICGEN-SUBPROCESS-ENQUEUE-OK")

# --- 2. reopen SQLite: job istnieje, ZERO tematow ---------------------------
storage = SqliteStorage.open(settings.db_path)
job_row = storage.conn.execute(
    "SELECT * FROM jobs WHERE kind='TOPIC_GENERATION'"
).fetchone()
assert job_row is not None, "enqueue did not persist a job"
job_id = job_row["id"]
assert job_row["topic_id"] is None, "enqueue must not bind a topic"
assert job_row["status"] == "QUEUED"
assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
assert storage.conn.execute(
    "SELECT COUNT(*) c FROM provider_attempts"
).fetchone()["c"] == 0
assert storage.conn.execute("SELECT COUNT(*) c FROM model_usage").fetchone()["c"] == 0

# Idempotencja publicznego enqueue: ten sam operation_key = ten sam job.
again = main_module.main([
    "enqueue-topic-generation",
    "--account-id", account.id,
    "--operation-key", "subprocess-wave-1",
    "--model", MODEL,
    "--pricing-profile", profile_id,
    "--max-tokens", "1500",
    "--max-cost-usd", "1.0",
    "--count", "3",
])
assert again == 0, f"idempotent enqueue exit={again}"
assert storage.conn.execute(
    "SELECT COUNT(*) c FROM jobs WHERE kind='TOPIC_GENERATION'"
).fetchone()["c"] == 1

storage.apply_security_flag_profile([
    ("worker_enabled", True),
    ("safe_mode", False),
    ("paid_actions_enabled", True),
    ("browser_actions_enabled", False),
    ("kill_switch", False),
], updated_by="driver", reason="topicgen-subprocess", now=NOW)

# --- 3. PUBLICZNY approve L1 ------------------------------------------------
expiry = (NOW + timedelta(hours=1)).isoformat()
approve = main_module.main([
    "approve-topic-generation", "--job-id", job_id,
    "--account-id", account.id, "--approved-by", "owner-subprocess",
    "--expires-at", expiry,
])
assert approve == 0, f"approve CLI exit={approve}"
print("TOPICGEN-SUBPROCESS-APPROVE-OK")
duplicate = main_module.main([
    "approve-topic-generation", "--job-id", job_id,
    "--account-id", account.id, "--approved-by", "owner-subprocess",
    "--expires-at", expiry,
])
assert duplicate == 2, f"duplicate approve exit={duplicate}"

# --- 4. fake caller TYLKO jako transport dispatchera -------------------------
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.base import Usage
from app.scheduler import dispatcher as dispatcher_module

DIMENSIONS = sorted(STANDARD_WEIGHTS)
TITLES = [
    "Why supermarket queues form",
    "How postal codes shape insurance premiums",
    "The hidden economics of stadium parking",
]
SCORES = [0.95, 0.70, 0.20]
caller_log = []


def fake_topic_caller(prompt_account, count):
    caller_log.append((prompt_account.id, count))
    assert count == 3, count
    return json.dumps({"topics": [
        {
            "title": TITLES[i],
            "question": "Why does it work that way?",
            "score_breakdown": {name: SCORES[i] for name in DIMENSIONS},
        }
        for i in range(3)
    ]}), Usage(input_tokens=120, output_tokens=90)


def fake_client_factory(client_settings, intent):
    return AnthropicLLMClient(
        client_settings.anthropic_api_key, intent.model,
        caller=fake_topic_caller,
        timeout_seconds=float(intent.timeout_seconds),
        topic_max_tokens=intent.max_tokens,
    )


_real_dispatcher = dispatcher_module.JobDispatcher


def patched_dispatcher(**kwargs):
    kwargs.setdefault("topic_generation_client_factory", fake_client_factory)
    return _real_dispatcher(**kwargs)


dispatcher_module.JobDispatcher = patched_dispatcher
storage.close()

# --- 5. PUBLICZNY worker entrypoint (ta sama kompozycja co `app.main worker`) -
worker, worker_storage = main_module._build_worker(settings)
try:
    result = worker.run_once()
finally:
    worker_storage.close()
assert result.status.value == "DONE", f"worker status={result.status} {result.detail}"
assert len(caller_log) == 1, caller_log
print("TOPICGEN-SUBPROCESS-WORKER-OK")

# --- 6. reopen bazy: pelny lineage ------------------------------------------
verify = SqliteStorage.open(settings.db_path)
job = verify.get_job(job_id)
assert job.status is JobStatus.DONE, job.status
run = verify.get_run(job.run_id)
assert run.status is RunStatus.SUCCESS, run.status
assert run.workflow is WorkflowType.TOPIC_GENERATION

attempts = verify.conn.execute(
    "SELECT * FROM provider_attempts WHERE job_id=?", (job_id,)
).fetchall()
assert len(attempts) == 1, len(attempts)
assert attempts[0]["stage"] == "topics"
assert attempts[0]["attempt_no"] == 1
assert attempts[0]["request_id"] == job_id + ":topics:1"
assert attempts[0]["status"] == "SETTLED"

usage = verify.conn.execute(
    "SELECT * FROM model_usage WHERE request_id=?", (attempts[0]["request_id"],)
).fetchall()
assert len(usage) == 1, len(usage)
assert usage[0]["task"] == "topics" and usage[0]["dry_run"] == 0
assert abs(float(run.cost_usd) - float(usage[0]["estimated_cost_usd"])) < 1e-9
assert abs(float(attempts[0]["actual_cost_usd"])
           - float(usage[0]["estimated_cost_usd"])) < 1e-9

lineage = verify.list_generated_topics_for_run(job.run_id)
assert [r.candidate_index for r in lineage] == [0, 1, 2], lineage
assert sum(1 for r in lineage if r.is_selected) == 1
selected_rows = [r for r in lineage if r.is_selected]
selected_topic_id = selected_rows[0].topic_id
statuses = sorted(
    verify.conn.execute(
        "SELECT status FROM topics WHERE id=?", (r.topic_id,)
    ).fetchone()["status"] for r in lineage
)
assert statuses == ["REJECTED", "SCORED", "SELECTED"], statuses
approval = verify.get_topic_generation_approval_for_job(job_id)
assert approval.consumed_at is not None
print("TOPICGEN-SUBPROCESS-LINEAGE-OK")

# --- 7. istniejacy publiczny downstream przyjmuje wygenerowany temat ---------
# Sam Fetch NIE jest wykonywany: to jest tylko durable enqueue kontraktu E2-B.
verify.close()
fetch_expiry = (NOW + timedelta(hours=2)).isoformat()
downstream = main_module.main([
    "enqueue-controlled-fetch",
    "--account-id", account.id,
    "--topic-id", str(selected_topic_id),
    "--source-identity", "example-source",
    "--url", "https://example.org/article",
    "--timeout-seconds", "30",
    "--max-bytes", "500000",
    "--max-redirects", "2",
    "--expires-at", fetch_expiry,
])
assert downstream == 0, f"downstream enqueue exit={downstream}"
final = SqliteStorage.open(settings.db_path)
fetch_job = final.conn.execute(
    "SELECT * FROM jobs WHERE json_extract(payload_json,'$.execution')"
    "='controlled_fetch_v1'"
).fetchone()
assert fetch_job is not None, "downstream did not accept the generated topic"
assert fetch_job["topic_id"] == selected_topic_id
assert fetch_job["status"] == "QUEUED"
# Downstream nie wykonal zadnego pobrania ani requestu.
assert final.conn.execute(
    "SELECT COUNT(*) c FROM controlled_fetch_attempts"
).fetchone()["c"] == 0
assert final.conn.execute(
    "SELECT COUNT(*) c FROM provider_attempts"
).fetchone()["c"] == 1
final.close()
print("TOPICGEN-SUBPROCESS-DOWNSTREAM-OK")
'''


def test_public_cli_end_to_end_topic_generation(tmp_path):
    driver = tmp_path / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(driver), str(tmp_path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env=_base_env(), check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    for marker in (
        "TOPICGEN-SUBPROCESS-ENQUEUE-OK",
        "TOPICGEN-SUBPROCESS-APPROVE-OK",
        "TOPICGEN-SUBPROCESS-WORKER-OK",
        "TOPICGEN-SUBPROCESS-LINEAGE-OK",
        "TOPICGEN-SUBPROCESS-DOWNSTREAM-OK",
    ):
        assert marker in result.stdout, f"{marker} missing:\n{result.stdout}"
    # Nic nie dotknelo sieci ani prawdziwego SDK.
    assert "anthropic" not in result.stderr.lower()
