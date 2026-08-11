"""E3: subprocess testy CLI approve-evidence-research i pełnego workera.

Dwa realne procesy potomne:
1. `python -m app.main approve-evidence-research` na oczyszczonym środowisku —
   fail-closed odmowa bez dotknięcia chronionej produkcyjnej bazy.
2. Driver uruchamiający PRAWDZIWĄ kompozycję CLI (app.main._build_worker,
   realny JobDispatcher) na tymczasowej bazie, z fake evidence callerem
   wstrzykniętym w fabrykę klienta dispatchera (sankcjonowany wzorzec fake
   SDK/callerów; safety kernel celowo blokuje każdy moduł `anthropic`).
   Wewnątrz driver wykonuje też właściwe CLI approve przez app.main.main([...]).
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

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


def test_approve_cli_subprocess_refuses_protected_db_with_scrubbed_env():
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "approve-evidence-research",
         "--job-id", "missing-job", "--account-id", "nothing_is_accidental",
         "--approved-by", "op", "--expires-at", "2099-01-01T00:00:00+00:00"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env=_base_env(), check=False,
    )
    # Fail-closed (config/storage/authorization refusal) bez mutacji
    # chronionej bazy; nigdy traceback ani sukces.
    assert result.returncode == 2, result.stderr
    assert "failed closed" in result.stderr
    assert "Traceback" not in result.stderr


_DRIVER = '''
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path

tmp_root = Path(sys.argv[1])

from app.core.config import Settings
from app.models import Job, JobKind, JobStatus, Topic, TopicStatus, WorkflowType
from app.ports.fetch import FetchedDocument
from app.research.durable_intent import (
    DurableResearchExecutionIntent, evidence_input_payload,
)
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from tests.conftest import (
    STANDARD_WEIGHTS, make_account, write_approved_pricing_profile,
)
from tests.controlled_provider_fixtures import seed_active_provider_role
from app.model_routing import LogicalModelRole
import app.main as main_module

NOW = datetime.now(timezone.utc)
CANONICAL_BODY = (
    "Supermarkets place essential items at the back of the store so shoppers "
    "walk past tempting displays on every trip. Retail layout studies report "
    "measurably larger baskets across chains that use this arrangement."
)
EXCERPT = "essential items at the back of the store"

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
    model_quality="evidence-subprocess-model",
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
profile_id, pricing_path = write_approved_pricing_profile(
    tmp_root, model=settings.model_quality, prices=dict(settings.pricing),
)
profile = resolve_real_pricing_profile(
    load_pricing_profiles(pricing_path), profile_id=profile_id,
    model=settings.model_quality,
)

storage = SqliteStorage.open(settings.db_path)
storage.ensure_account(account)
topic = storage.add_topic(account.id, Topic(
    account_id=account.id, title="Subprocess evidence topic", question="Why?",
    score=90.0, status=TopicStatus.SELECTED,
))
retrieval = storage.record_evidence_retrieval(
    FetchedDocument(
        requested_url="https://evidence.example/doc",
        final_url="https://evidence.example/doc",
        fetched_at=NOW, http_status=200,
        content_type="text/plain; charset=utf-8",
        body=CANONICAL_BODY.encode("utf-8"), error=None,
    ),
    account_id=account.id, now=NOW,
)

# Fake evidence caller wstrzyknięty w fabrykę klienta dispatchera — dokładnie
# jeden request, zero SDK, zero sieci (kernel i tak blokuje moduł anthropic).
from app.llm.base import Usage
from app.research.anthropic_client import AnthropicResearchClient
from app.scheduler import dispatcher as dispatcher_module

caller_log = []


def fake_evidence_caller(plan, contract):
    caller_log.append(contract)
    assert contract.max_web_searches == 0
    claim = "Essentials at the back lengthen the shopper path."
    response = json.dumps({
        "question": "Why?",
        "working_thesis": "Layout drives basket size.",
        "main_mechanism": "Forced path exposure.",
        "confirmed_claims": [claim],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "Convenience placement exists too.",
        "citable_numbers": [],
        "visual_idea": "A floor plan.",
        "confidence_score": 0.9,
        "source_quality_score": 0.9,
        "sources": [{
            "url": contract.documents[0].url,
            "title": "Supermarket layout",
            "author_or_org": None,
            "published_at": None,
            "source_type": "SECONDARY",
            "supports_claim": claim,
            "supporting_excerpt": EXCERPT,
        }],
    })
    return response, Usage(input_tokens=120, output_tokens=90), "end_turn"


def fake_client_factory(*args, **kwargs):
    return AnthropicResearchClient(
        *args, evidence_caller=fake_evidence_caller, **kwargs,
    )


dispatcher_module.AnthropicResearchClient = fake_client_factory
intent = DurableResearchExecutionIntent.from_settings(
    settings=settings, account_id=account.id, topic_id=int(topic.id),
    cap_usd=1.0, max_web_searches=0, question=topic.question,
    niche=account.niche, max_tokens=3000,
    pricing_prices=profile.prices,
    pricing_profile_id=profile.profile_id,
    pricing_profile_version=profile.version,
    pricing_currency=profile.currency,
    pricing_unit=profile.unit,
    evidence_input=evidence_input_payload([
        (int(retrieval.id), retrieval.canonical_sha256,
         int(retrieval.canonical_chars)),
    ]),
)
job = storage.enqueue_job(Job(
    id="subprocess-evidence-job", account_id=account.id, kind=JobKind.RESEARCH,
    workflow=WorkflowType.RESEARCH, idempotency_key="subprocess-evidence",
    topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
    earliest_run_at=NOW - timedelta(minutes=1), max_attempts=1,
    payload={
        "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single",
        "max_cost_usd": intent.cap_usd,
        "execution_intent": intent.as_payload(),
    },
))
seed_active_provider_role(
    storage,
    role=LogicalModelRole.ARTICLE_RESEARCH,
    technical_model_id=intent.model,
)
storage.apply_security_flag_profile([
    ("worker_enabled", True),
    ("safe_mode", False),
    ("paid_actions_enabled", True),
    ("browser_actions_enabled", False),
    ("kill_switch", False),
], updated_by="driver", reason="e3-subprocess", now=NOW)

# Właściwe CLI approve przez prawdziwy parser app.main.
main_module.load_settings = lambda: settings
expiry = (NOW + timedelta(hours=1)).isoformat()
code = main_module.main([
    "approve-evidence-research", "--job-id", job.id,
    "--account-id", account.id, "--approved-by", "owner-subprocess",
    "--expires-at", expiry,
])
assert code == 0, f"approve CLI exit={code}"
print("E3-SUBPROCESS-APPROVE-OK")
duplicate = main_module.main([
    "approve-evidence-research", "--job-id", job.id,
    "--account-id", account.id, "--approved-by", "owner-subprocess",
    "--expires-at", expiry,
])
assert duplicate == 2, f"duplicate approve exit={duplicate}"

# Pełny worker entrypoint CLI (ta sama kompozycja co `app.main worker`).
worker, worker_storage = main_module._build_worker(settings)
try:
    result = worker.run_once()
finally:
    worker_storage.close()
assert result.status.value == "DONE", result
job_row = storage.get_job(job.id)
assert job_row.status is JobStatus.DONE, job_row.status
run_id = job_row.run_id
research_run = storage.get_research_run(run_id)
assert research_run.status.value == "COMPLETE"
assert research_run.research_card_id is not None
card = storage.conn.execute(
    "SELECT publication_recommendation, rejection_reason FROM research_cards "
    "WHERE id=?", (research_run.research_card_id,),
).fetchone()
assert card["publication_recommendation"] == "REJECT"
assert "TOO_FEW_SOURCES" in card["rejection_reason"]
attempt = storage.conn.execute(
    "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
).fetchone()
assert attempt["status"] == "SETTLED"
assert storage.conn.execute(
    "SELECT count(*) FROM model_usage WHERE dry_run=0"
).fetchone()[0] == 1
assert storage.conn.execute(
    "SELECT count(*) FROM evidence_retrievals"
).fetchone()[0] == 1
excerpts = storage.list_evidence_excerpts(int(retrieval.id), account_id=account.id)
assert len(excerpts) == 1
approval_row = storage.conn.execute(
    "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?",
    (job.id,),
).fetchone()
assert approval_row["consumed_at"] is not None
assert len(caller_log) == 1
assert [
    (d.retrieval_id, d.url, d.canonical_text) for d in caller_log[0].documents
] == [(int(retrieval.id), retrieval.requested_url, retrieval.canonical_text)]
storage.close()
print("E3-SUBPROCESS-WORKER-OK")
'''


def test_full_worker_entrypoint_subprocess_with_fake_caller(tmp_path):
    driver = tmp_path / "driver.py"
    driver.write_text(textwrap.dedent(_DRIVER), encoding="utf-8")
    work_root = tmp_path / "work"
    work_root.mkdir()
    result = subprocess.run(
        [sys.executable, str(driver), str(work_root)],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        env=_base_env(), check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "E3-SUBPROCESS-APPROVE-OK" in result.stdout
    assert "E3-SUBPROCESS-WORKER-OK" in result.stdout
