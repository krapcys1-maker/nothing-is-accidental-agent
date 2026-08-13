"""E3: evidence research — frozen evidence input + jednorazowy approval L1.

Całość offline na nowych tymczasowych bazach: fake evidence caller, zero SDK,
zero sieci. Pokrycie: kontrakt intentu (fingerprint/limity/projekcja), trwały
jednorazowy approval EVIDENCE_RESEARCH (binding, expiry, exactly-once,
concurrency, restart, immutability, lineage po mutacji payloadu), fail-closed
walidacja evidence przed rezerwacją, atomowa konsumpcja + rezerwacja, pełny
worker E2E (REJECT/TOO_FEW_SOURCES przy jednym retrievalu), verifier excerptów,
over-reservation -> reconciliation, recovery i lease fencing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.llm.base import Usage
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    RunStatus,
    SourceVerification,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.fetch import FetchedDocument
from app.ports.storage import (
    EvidenceResearchAuthorizationError,
    ProviderAttemptReconciliationRequired,
    StaleJobExecutionError,
)
from app.research.evidence import EvidenceVerificationError
from app.research.durable_intent import (
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    EVIDENCE_PROMPT_CONTRACT_VERSION,
    EVIDENCE_PROMPT_OVERHEAD_CHARS,
    MAX_EVIDENCE_CHARS_PER_RETRIEVAL,
    MAX_EVIDENCE_RETRIEVALS,
    canonical_execution_intent_json,
    durable_execution_intent_fingerprint,
    evidence_input_payload,
    frozen_execution_intent_json,
)
from app.scheduler import dispatcher as dispatcher_module
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from tests.conftest import write_approved_pricing_profile

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
CANONICAL_BODY = (
    "Supermarkets place essential items at the back of the store so shoppers "
    "walk past tempting displays on every trip. Retail layout studies report "
    "measurably larger baskets across chains that use this arrangement."
)
EXCERPT = "essential items at the back of the store"
CLAIM = "Essentials at the back lengthen the shopper path."


def _topic(storage, account, suffix):
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title=f"Evidence topic {suffix}", question="Why?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _seed_retrieval(storage, account, *, url="https://evidence.example/doc",
                    body=CANONICAL_BODY):
    storage.ensure_account(account)
    return storage.record_evidence_retrieval(
        FetchedDocument(
            requested_url=url, final_url=url, fetched_at=NOW,
            http_status=200, content_type="text/plain; charset=utf-8",
            body=body.encode("utf-8"), error=None,
        ),
        account_id=account.id,
        now=NOW,
    )


def _real_settings(settings, model="evidence-test-model"):
    return replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-only-key",
        model_quality=model,
        research_timeout_seconds=31,
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def _pricing_profile(real_settings):
    profile_id, pricing_path = write_approved_pricing_profile(
        real_settings.project_root,
        model=real_settings.model_quality,
        prices=dict(real_settings.pricing),
    )
    return resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real_settings.model_quality,
    )


def _evidence_intent(real_settings, account, topic, retrievals, *, cap=1.0,
                     pricing_profile=None, max_web_searches=0):
    pricing_kwargs = {}
    if pricing_profile is not None:
        pricing_kwargs = {
            "pricing_prices": pricing_profile.prices,
            "pricing_profile_id": pricing_profile.profile_id,
            "pricing_profile_version": pricing_profile.version,
            "pricing_currency": pricing_profile.currency,
            "pricing_unit": pricing_profile.unit,
        }
    return DurableResearchExecutionIntent.from_settings(
        settings=real_settings, account_id=account.id, topic_id=int(topic.id),
        cap_usd=cap, max_web_searches=max_web_searches,
        question=topic.question or topic.title, niche=account.niche,
        max_tokens=3000,
        evidence_input=evidence_input_payload([
            (int(r.id), r.canonical_sha256, int(r.canonical_chars))
            for r in retrievals
        ]),
        **pricing_kwargs,
    )


def _evidence_payload(real_settings, account, topic, retrievals, *, cap=1.0,
                      pricing_profile=None):
    intent = _evidence_intent(
        real_settings, account, topic, retrievals, cap=cap,
        pricing_profile=pricing_profile,
    )
    return {
        "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": intent.cap_usd,
        "execution_intent": intent.as_payload(),
    }, intent


def _job(account, topic, key, payload):
    return Job(
        id=f"evidence-job-{key}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"evidence-{key}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1, payload=payload,
    )


def _open_flags(storage):
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="e3", now=NOW)


def _approve(storage, job_id, account, *, hours=2, approved_by="owner-l1"):
    return storage.record_evidence_research_approval(
        job_id=job_id, account_id=account.id, approved_by=approved_by,
        expires_at=NOW + timedelta(hours=hours), clock=FixedClock(NOW),
    )


def _evidence_response(url, *, claim=CLAIM, excerpt=EXCERPT):
    return json.dumps({
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
            "url": url,
            "title": "Supermarket layout",
            "author_or_org": None,
            "published_at": None,
            "source_type": "SECONDARY",
            "supports_claim": claim,
            "supporting_excerpt": excerpt,
        }],
    })


class _FakeEvidenceCaller:
    def __init__(self, response=None, usage=None):
        self.calls = []
        self.contracts = []
        self._response = response
        self._usage = usage or Usage(input_tokens=100, output_tokens=100)

    def __call__(self, plan, contract):
        self.calls.append(plan)
        self.contracts.append(contract)
        response = self._response
        if response is None:
            response = _evidence_response(contract.documents[0].url)
        return response, self._usage, "end_turn"


def _install_fake_client(monkeypatch, caller):
    from app.research.anthropic_client import AnthropicResearchClient

    def fake_client(*args, **kwargs):
        return AnthropicResearchClient(*args, evidence_caller=caller, **kwargs)

    monkeypatch.setattr(dispatcher_module, "AnthropicResearchClient", fake_client)


def _worker(real_settings, storage, *, lease_owner="e3-worker", clock=None):
    from app.model_routing import LogicalModelRole, ModelFamily
    from tests.controlled_provider_fixtures import seed_model, seed_role_policy

    if storage.get_active_model_for_role(LogicalModelRole.ARTICLE_RESEARCH) is None:
        seed_role_policy(storage, LogicalModelRole.ARTICLE_RESEARCH)
        seed_model(
            storage,
            version="0.0.1",
            family=ModelFamily.OPUS,
            provider="ANTHROPIC",
            technical_model_id_override=real_settings.model_quality,
        )
        storage.promote_best_model(
            LogicalModelRole.ARTICLE_RESEARCH,
            reason="offline research provider-contract fixture",
        )
    clock = clock or FixedClock(NOW)
    policy = PolicyEngine(real_settings, storage, clock)
    dispatcher = JobDispatcher(
        settings=real_settings, storage=storage, policy=policy, clock=clock,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner=lease_owner, lease_seconds=120,
        heartbeat_interval_seconds=1,
        heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real_settings.db_path),
        clock=clock,
    )


def _prepared_e2e(settings, storage, account, *, cap=1.0, key="e2e"):
    real_settings = _real_settings(settings)
    profile = _pricing_profile(real_settings)
    topic = _topic(storage, account, key)
    retrieval = _seed_retrieval(storage, account)
    payload, intent = _evidence_payload(
        real_settings, account, topic, [retrieval], cap=cap,
        pricing_profile=profile,
    )
    job = storage.enqueue_job(_job(account, topic, key, payload))
    _open_flags(storage)
    return real_settings, topic, retrieval, job, intent


# ---------------------------------------------------------------------------
# Kontrakt intentu: fingerprint, limity, projekcja
# ---------------------------------------------------------------------------

def test_frozen_intent_fingerprint_is_sha256_of_canonical_json(
        settings, storage, account):
    real = _real_settings(settings)
    topic = _topic(storage, account, "fp")
    retrieval = _seed_retrieval(storage, account)
    payload, _intent = _evidence_payload(real, account, topic, [retrieval])
    encoded, fingerprint = frozen_execution_intent_json(payload)
    assert fingerprint == hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert encoded == canonical_execution_intent_json(
        json.loads(encoded)
    )
    assert durable_execution_intent_fingerprint(payload) == fingerprint
    parsed = json.loads(encoded)
    assert parsed["evidence_input"]["retrievals"] == [{
        "retrieval_id": int(retrieval.id),
        "canonical_sha256": retrieval.canonical_sha256,
        "canonical_chars": int(retrieval.canonical_chars),
    }]


def test_fingerprint_changes_with_every_request_affecting_field(
        settings, storage, account):
    real = _real_settings(settings)
    topic = _topic(storage, account, "fp-fields")
    retrieval = _seed_retrieval(storage, account)
    payload, _ = _evidence_payload(real, account, topic, [retrieval])
    base = durable_execution_intent_fingerprint(payload)

    def variant(mutate):
        candidate = json.loads(json.dumps(payload))
        mutate(candidate)
        return durable_execution_intent_fingerprint(candidate)

    def set_intent(candidate, key, value):
        candidate["execution_intent"][key] = value

    entry = lambda c: c["execution_intent"]["evidence_input"]["retrievals"][0]
    clean_mutations = {
        "retrieval_id": lambda c: entry(c).update(retrieval_id=999),
        "canonical_sha256": lambda c: entry(c).update(canonical_sha256="f" * 64),
        "max_retries": lambda c: set_intent(c, "max_retries", 1),
    }
    # Te pola są dodatkowo związane z przeliczanymi projekcjami/kontraktem
    # cenowym: samodzielna mutacja łamie intent fail-closed ZANIM fingerprint
    # w ogóle powstanie — czyli również nie może przejść niezauważona.
    fail_closed_mutations = {
        "canonical_chars": lambda c: entry(c).update(canonical_chars=17),
        "model": lambda c: set_intent(c, "model", "another-model"),
        "max_tokens": lambda c: set_intent(c, "max_tokens", 2999),
    }
    seen = {base}
    for name, mutate in clean_mutations.items():
        fingerprint = variant(mutate)
        assert fingerprint != base, name
        assert fingerprint not in seen, name
        seen.add(fingerprint)
    for name, mutate in fail_closed_mutations.items():
        candidate = json.loads(json.dumps(payload))
        mutate(candidate)
        with pytest.raises(DurableExecutionIntentError):
            durable_execution_intent_fingerprint(candidate)
    # cap żyje w intencie i payloadzie jednocześnie.
    candidate = json.loads(json.dumps(payload))
    candidate["execution_intent"]["cap_usd"] = "0.900000"
    candidate["max_cost_usd"] = "0.900000"
    assert durable_execution_intent_fingerprint(candidate) != base


def test_evidence_input_limits_are_closed_and_enforced(settings, storage, account):
    # Liczba retrievali > MAX odrzucona.
    too_many = [(index + 1, "a" * 64, 10) for index in range(MAX_EVIDENCE_RETRIEVALS + 1)]
    with pytest.raises(DurableExecutionIntentError, match="EVIDENCE_INPUT_INVALID"):
        evidence_input_payload(too_many)
    # Rozmiar pojedynczego retrievalu > MAX odrzucony.
    with pytest.raises(DurableExecutionIntentError, match="EVIDENCE_INPUT_INVALID"):
        evidence_input_payload([(1, "a" * 64, MAX_EVIDENCE_CHARS_PER_RETRIEVAL + 1)])
    # Duplikat ID odrzucony.
    with pytest.raises(DurableExecutionIntentError, match="EVIDENCE_INPUT_INVALID"):
        evidence_input_payload([(1, "a" * 64, 10), (1, "b" * 64, 10)])
    # Blok limits musi być literalnie zgodny z zamkniętym kontraktem v1.
    tampered = evidence_input_payload([(1, "a" * 64, 10)])
    tampered["limits"]["max_total_chars"] = 10 ** 9
    real = _real_settings(settings)
    topic = _topic(storage, account, "limits")
    with pytest.raises(DurableExecutionIntentError, match="EVIDENCE_INPUT_INVALID"):
        DurableResearchExecutionIntent.from_settings(
            settings=real, account_id=account.id, topic_id=int(topic.id),
            cap_usd=1.0, max_web_searches=0, question="Why?",
            niche=account.niche, max_tokens=3000, evidence_input=tampered,
        )
    # Tryb evidence wymusza zero web searchy.
    with pytest.raises(DurableExecutionIntentError, match="EVIDENCE_REQUIRES_ZERO"):
        DurableResearchExecutionIntent.from_settings(
            settings=real, account_id=account.id, topic_id=int(topic.id),
            cap_usd=1.0, max_web_searches=1, question="Why?",
            niche=account.niche, max_tokens=3000,
            evidence_input=evidence_input_payload([(1, "a" * 64, 10)]),
        )


def test_evidence_projected_cost_grows_with_corpus_size(settings, storage, account):
    real = _real_settings(settings)
    topic = _topic(storage, account, "cost")
    small = _seed_retrieval(storage, account, url="https://evidence.example/a")
    large = _seed_retrieval(
        storage, account, url="https://evidence.example/b",
        body=CANONICAL_BODY * 40,
    )
    one = _evidence_intent(real, account, topic, [small])
    two = _evidence_intent(real, account, topic, [small, large])
    assert float(two.projected_cost_usd) > float(one.projected_cost_usd)
    assert float(two.pessimistic_cost_usd) > float(one.pessimistic_cost_usd)
    assert one.prompt_contract_version == EVIDENCE_PROMPT_CONTRACT_VERSION
    assert one.is_supported_by_current_worker()


def test_cli_estimation_domain_equals_frozen_intent_projection(
        settings, storage, account):
    # Jedna domena projekcji: CLI (estimate_no_search + evidence forwarded
    # tokens) == zamrożony intent == (w E2E) rezerwacja attemptu.
    from types import SimpleNamespace

    from app.research.cost_estimator import estimate_no_search_call_usd
    from app.research.durable_intent import evidence_forwarded_context_tokens

    real = _real_settings(settings)
    topic = _topic(storage, account, "cli-parity")
    retrieval = _seed_retrieval(storage, account)
    intent = _evidence_intent(real, account, topic, [retrieval])
    cli_estimate = estimate_no_search_call_usd(
        SimpleNamespace(pricing=dict(real.pricing)),
        max_output_tokens=intent.max_tokens,
        forwarded_context_tokens=evidence_forwarded_context_tokens(
            intent.evidence_input,
        ),
    )
    assert float(intent.projected_cost_usd) == pytest.approx(
        cli_estimate.subtotal_usd, abs=1e-6,
    )
    assert float(intent.pessimistic_cost_usd) == pytest.approx(
        cli_estimate.total_usd, abs=1e-6,
    )


def test_evidence_prompt_template_fits_the_pinned_overhead_budget():
    from app.research.anthropic_client import (
        EvidenceSynthesisContract,
        EvidenceSynthesisDocument,
        build_evidence_research_prompt,
    )
    from app.research.base import ResearchPlan

    document = EvidenceSynthesisDocument(
        retrieval_id=1, url="https://u.example/" + "u" * 180, canonical_text="",
    )
    plan = ResearchPlan(
        topic_id=1, account_id="nothing_is_accidental",
        question="Q" * 300, niche=["n" * 40] * 4, guidance="g" * 400,
    )
    prompt = build_evidence_research_prompt(
        plan,
        EvidenceSynthesisContract(
            documents=(document,) * 6, max_web_searches=0, max_output_tokens=3000,
        ),
    )
    # Budżet narzutu promptu (poza corpusem) jest przypięty i musi pokrywać
    # realny szablon z polami na granicach kontraktu.
    assert len(prompt) <= EVIDENCE_PROMPT_OVERHEAD_CHARS


# ---------------------------------------------------------------------------
# Approval: binding, expiry, exactly-once, restart, immutability
# ---------------------------------------------------------------------------

def test_approval_binds_exactly_the_frozen_evidence_job(settings, storage, account):
    real_settings, topic, retrieval, job, intent = _prepared_e2e(
        settings, storage, account, key="bind",
    )
    approval = _approve(storage, job.id, account)
    assert approval.job_id == job.id
    assert approval.account_id == account.id
    assert approval.topic_id == int(topic.id)
    assert approval.action_type == "EVIDENCE_RESEARCH"
    assert approval.consumed_at is None
    expected_fp = durable_execution_intent_fingerprint(
        storage.get_job(job.id).payload
    )
    assert approval.intent_fingerprint == expected_fp
    preimage = approval.execution_intent_json
    assert hashlib.sha256(preimage.encode("utf-8")).hexdigest() == expected_fp
    frozen = json.loads(preimage)
    assert frozen["evidence_input"]["retrievals"][0]["retrieval_id"] == int(retrieval.id)
    # Restart: zgoda przeżywa ponowne otwarcie bazy.
    reopened = SqliteStorage.open(real_settings.db_path)
    try:
        persisted = reopened.get_evidence_research_approval_for_job(job.id)
        assert persisted is not None
        assert persisted.execution_intent_json == preimage
    finally:
        reopened.close()


def test_approval_refuses_wrong_execution_type_and_missing_evidence(
        settings, storage, account, monkeypatch):
    real = _real_settings(settings)
    fetch_topic = _topic(storage, account, "wrong-type-fetch")
    plain_topic = _topic(storage, account, "wrong-type-plain")
    # Job controlled_fetch_v1 nie może dostać zgody EVIDENCE_RESEARCH.
    from app.research.controlled_fetch_intent import ControlledFetchIntent

    fetch_intent = ControlledFetchIntent.build(
        account_id=account.id, topic_id=int(fetch_topic.id), source_identity="doc",
        requested_url="https://fetch.example/doc", timeout_seconds=10,
        max_bytes=1000, max_redirects=1,
        allowed_content_types=["text/html", "text/plain"],
        requested_at=NOW, expires_at=NOW + timedelta(hours=1),
    )
    fetch_job = storage.enqueue_job(Job(
        id="fetch-job-wrong-type", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key="fetch-wrong-type",
        topic_id=int(fetch_topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={
            "account_id": account.id, "topic_id": int(fetch_topic.id), "dry_run": False,
            "execution": "controlled_fetch_v1",
            "execution_intent": fetch_intent.as_payload(),
        },
    ))
    with pytest.raises(EvidenceResearchAuthorizationError, match="INTENT_INVALID"):
        _approve(storage, fetch_job.id, account)
    # Durable job BEZ evidence_input też jest odrzucany.
    plain_intent = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=int(plain_topic.id),
        cap_usd=1.0, max_web_searches=3, question="Why?", niche=account.niche,
        max_tokens=3000,
    )
    plain_job = storage.enqueue_job(Job(
        id="plain-durable-job", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key="plain-durable",
        topic_id=int(plain_topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={
            "account_id": account.id, "topic_id": int(plain_topic.id), "dry_run": False,
            "execution": "durable_provider_v2", "mode": "single",
            "max_cost_usd": plain_intent.cap_usd,
            "execution_intent": plain_intent.as_payload(),
        },
    ))
    with pytest.raises(EvidenceResearchAuthorizationError, match="INTENT_NOT_EVIDENCE"):
        _approve(storage, plain_job.id, account)


def test_approval_refuses_missing_foreign_or_diverged_evidence(
        settings, storage, account):
    real = _real_settings(settings)
    retrieval = _seed_retrieval(storage, account)

    def enqueue(key, entries):
        topic = _topic(storage, account, f"evidence-checks-{key}")
        intent = DurableResearchExecutionIntent.from_settings(
            settings=real, account_id=account.id, topic_id=int(topic.id),
            cap_usd=1.0, max_web_searches=0, question="Why?",
            niche=account.niche, max_tokens=3000,
            evidence_input=evidence_input_payload(entries),
        )
        return storage.enqueue_job(Job(
            id=f"evidence-checks-{key}", account_id=account.id,
            kind=JobKind.RESEARCH, workflow=WorkflowType.RESEARCH,
            idempotency_key=f"evidence-checks-{key}", topic_id=int(topic.id),
            schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW,
            max_attempts=1,
            payload={
                "account_id": account.id, "topic_id": int(topic.id),
                "dry_run": False, "execution": "durable_provider_v2",
                "mode": "single", "max_cost_usd": intent.cap_usd,
                "execution_intent": intent.as_payload(),
            },
        ))

    missing = enqueue("missing", [(999, "a" * 64, 10)])
    with pytest.raises(
        EvidenceResearchAuthorizationError, match="EVIDENCE_RETRIEVAL_MISSING",
    ):
        _approve(storage, missing.id, account)
    wrong_hash = enqueue(
        "hash", [(int(retrieval.id), "e" * 64, int(retrieval.canonical_chars))],
    )
    with pytest.raises(
        EvidenceResearchAuthorizationError, match="EVIDENCE_HASH_MISMATCH",
    ):
        _approve(storage, wrong_hash.id, account)
    wrong_chars = enqueue(
        "chars", [(int(retrieval.id), retrieval.canonical_sha256, 17)],
    )
    with pytest.raises(
        EvidenceResearchAuthorizationError, match="EVIDENCE_CHARS_MISMATCH",
    ):
        _approve(storage, wrong_chars.id, account)
    # Odmowa nie utrwala niczego: zero wierszy zgody.
    assert storage.conn.execute(
        "SELECT count(*) FROM controlled_fetch_approvals"
    ).fetchone()[0] == 0


def test_expired_approval_is_refused_and_not_consumed(settings, storage, account):
    real_settings, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="expired",
    )
    with pytest.raises(
        EvidenceResearchAuthorizationError, match="APPROVAL_EXPIRY_INVALID",
    ):
        storage.record_evidence_research_approval(
            job_id=job.id, account_id=account.id, approved_by="owner",
            expires_at=NOW - timedelta(minutes=1), clock=FixedClock(NOW),
        )
    approval = _approve(storage, job.id, account, hours=1)
    caller = _FakeEvidenceCaller()
    # Konsumpcja PO expiry: worker startuje po czasie ważności zgody.
    later = FixedClock(NOW + timedelta(hours=3))
    worker_result = None
    import pytest as _pytest  # noqa: F401

    worker = _worker(real_settings, storage, clock=later)
    worker_result = worker.run_once()
    assert worker_result.status is WorkerIterationStatus.FAILED
    row = storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?",
        (approval.id,),
    ).fetchone()
    assert row["consumed_at"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts"
    ).fetchone()[0] == 0
    assert not caller.calls
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    assert "EVIDENCE_RESEARCH_REFUSED:APPROVAL_EXPIRED" in (job_row.last_error or "")


def test_approval_row_is_immutable_outside_single_consumption(
        settings, storage, account):
    _real, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="immutable",
    )
    approval = _approve(storage, job.id, account)
    for mutation, params in [
        ("UPDATE controlled_fetch_approvals SET execution_intent_json='{}' WHERE id=?",
         (approval.id,)),
        ("UPDATE controlled_fetch_approvals SET intent_fingerprint=? WHERE id=?",
         ("f" * 64, approval.id)),
        ("UPDATE controlled_fetch_approvals SET expires_at='2099-01-01 00:00:00' WHERE id=?",
         (approval.id,)),
        ("UPDATE controlled_fetch_approvals SET approved_by='intruder' WHERE id=?",
         (approval.id,)),
        ("UPDATE controlled_fetch_approvals SET topic_id=topic_id+1 WHERE id=?",
         (approval.id,)),
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            storage.conn.execute(mutation, params)
        storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "DELETE FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
        )
    storage.conn.rollback()
    # Legalna jest wyłącznie jedna konsumpcja NULL -> timestamp...
    storage.conn.execute(
        "UPDATE controlled_fetch_approvals SET consumed_at='2026-07-19 12:30:00' "
        "WHERE id=?", (approval.id,),
    )
    storage.conn.commit()
    # ...i nigdy z powrotem ani ponownie.
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE controlled_fetch_approvals SET consumed_at=NULL WHERE id=?",
            (approval.id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE controlled_fetch_approvals SET consumed_at='2026-07-19 12:31:00' "
            "WHERE id=?", (approval.id,),
        )
    storage.conn.rollback()


def test_concurrent_consumption_yields_exactly_one_success(
        settings, storage, account):
    real_settings, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="race",
    )
    approval = _approve(storage, job.id, account)
    barrier = threading.Barrier(2)
    outcomes: list[int] = []
    lock = threading.Lock()

    def consume(tag):
        connection = SqliteStorage.open(real_settings.db_path)
        try:
            barrier.wait(timeout=10)
            cursor = connection.conn.execute(
                "UPDATE controlled_fetch_approvals SET consumed_at=? "
                "WHERE id=? AND consumed_at IS NULL",
                (f"2026-07-19 12:0{tag}:00", approval.id),
            )
            connection.conn.commit()
            with lock:
                outcomes.append(cursor.rowcount)
        finally:
            connection.close()

    threads = [threading.Thread(target=consume, args=(i,)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == [0, 1]


# ---------------------------------------------------------------------------
# Pełny worker E2E i konsumpcja atomowa
# ---------------------------------------------------------------------------

def test_worker_e2e_single_retrieval_yields_reject_card_and_done(
        monkeypatch, settings, storage, account):
    real_settings, topic, retrieval, job, intent = _prepared_e2e(
        settings, storage, account, key="happy",
    )
    _approve(storage, job.id, account)
    caller = _FakeEvidenceCaller()
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert result.job_id == job.id
    # Dokładnie jeden request; caller dostał dokładnie zatwierdzony corpus
    # i kontrakt max_web_searches=0.
    assert len(caller.calls) == 1
    contract = caller.contracts[0]
    assert contract.max_web_searches == 0
    assert [
        (document.retrieval_id, document.url, document.canonical_text)
        for document in contract.documents
    ] == [(int(retrieval.id), retrieval.requested_url, retrieval.canonical_text)]

    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.DONE
    run_id = job_row.run_id
    assert storage.get_run(run_id).status is RunStatus.SUCCESS
    research_run = storage.get_research_run(run_id)
    assert research_run.status.value == "COMPLETE"
    assert research_run.research_card_id is not None

    # Dokładnie jedno usage i settlement; rezerwacja pokrywa pełną zatwierdzoną
    # kopertę ARTICLE_RESEARCH, niezależnie od mniejszego bieżącego corpusu.
    from app.research.durable_intent import evidence_full_envelope_cost_usd
    attempt = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == "SETTLED"
    assert attempt["attempt_no"] == 1
    assert attempt["execution_intent_fingerprint"] == (
        durable_execution_intent_fingerprint(job_row.payload)
    )
    assert attempt["reserved_amount_usd"] == pytest.approx(
        float(evidence_full_envelope_cost_usd(
            pricing_profile=intent.pricing_profile,
            max_output_tokens=intent.max_tokens,
        ))
    )
    assert attempt["actual_cost_usd"] <= attempt["reserved_amount_usd"]
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=? AND dry_run=0", (run_id,),
    ).fetchone()[0] == 1
    usage_row = storage.conn.execute(
        "SELECT web_search_requests FROM model_usage WHERE run_id=?", (run_id,),
    ).fetchone()
    assert usage_row["web_search_requests"] == 0

    # Konsumpcja zgody nastąpiła atomowo z rezerwacją: identyczny timestamp.
    approval_row = storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?",
        (job.id,),
    ).fetchone()
    assert approval_row["consumed_at"] == attempt["reserved_at"]

    # Weryfikator E1 zatwierdził excerpt i tylko on nadał VERIFIED.
    excerpts = storage.list_evidence_excerpts(
        int(retrieval.id), account_id=account.id,
    )
    assert len(excerpts) == 1
    excerpt = excerpts[0]
    start = retrieval.canonical_text.find(EXCERPT)
    assert (excerpt.start_offset, excerpt.end_offset) == (start, start + len(EXCERPT))
    assert excerpt.excerpt_text == EXCERPT
    assert excerpt.claim_text == CLAIM

    card_row = storage.conn.execute(
        "SELECT publication_recommendation, rejection_reason FROM research_cards "
        "WHERE id=?", (research_run.research_card_id,),
    ).fetchone()
    assert card_row["publication_recommendation"] == "REJECT"
    assert "TOO_FEW_SOURCES" in card_row["rejection_reason"]
    source_row = storage.conn.execute(
        "SELECT url, verification_status FROM sources WHERE research_card_id=?",
        (research_run.research_card_id,),
    ).fetchone()
    assert source_row["url"] == retrieval.requested_url
    assert source_row["verification_status"] == SourceVerification.VERIFIED.value

    # Zero nowego Fetchu i zero nowych retrievali.
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_retrievals"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM controlled_fetch_attempts"
    ).fetchone()[0] == 0

    # Restart nie przywraca zużytej zgody; ponowny worker jest IDLE.
    reopened = SqliteStorage.open(real_settings.db_path)
    try:
        persisted = reopened.get_evidence_research_approval_for_job(job.id)
        assert persisted.consumed_at is not None
    finally:
        reopened.close()
    assert _worker(real_settings, storage, lease_owner="e3-second").run_once().status \
        is WorkerIterationStatus.IDLE


def test_worker_without_approval_fails_closed_before_any_reservation(
        monkeypatch, settings, storage, account):
    real_settings, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="no-approval",
    )
    caller = _FakeEvidenceCaller()
    _install_fake_client(monkeypatch, caller)
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.FAILED
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    assert "EVIDENCE_RESEARCH_REFUSED:APPROVAL_MISSING" in (job_row.last_error or "")
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0
    assert not caller.calls


def test_cap_below_projection_blocks_before_consumption_and_provider(
        monkeypatch, settings, storage, account):
    real_settings, _topic_row, _retrieval, job, intent = _prepared_e2e(
        settings, storage, account, key="cap", cap=0.000005,
    )
    assert float(intent.pessimistic_cost_usd) > float(intent.cap_usd)
    approval = _approve(storage, job.id, account)
    caller = _FakeEvidenceCaller()
    _install_fake_client(monkeypatch, caller)
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.FAILED
    assert not caller.calls
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?",
        (approval.id,),
    ).fetchone()["consumed_at"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0


def test_payload_mutation_after_approval_keeps_lineage_and_refuses_execution(
        monkeypatch, settings, storage, account):
    real_settings, topic, retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="mutation",
    )
    approval = _approve(storage, job.id, account)
    original_preimage = approval.execution_intent_json
    # Mutacja trwałego payloadu po zatwierdzeniu (payload durable_provider_v2
    # nie jest SQL-frozen — autorytetem pozostaje wiersz zgody).
    mutated = json.loads(storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (job.id,),
    ).fetchone()[0])
    mutated["execution_intent"]["evidence_input"]["retrievals"][0][
        "canonical_sha256"
    ] = "d" * 64
    storage.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?",
        (json.dumps(mutated, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")), job.id),
    )
    storage.conn.commit()

    # Lineage jest nadal jednoznacznie odtwarzalny z niezmiennego preimage.
    persisted = storage.get_evidence_research_approval_for_job(job.id)
    assert persisted.execution_intent_json == original_preimage
    frozen = json.loads(persisted.execution_intent_json)
    assert frozen["evidence_input"]["retrievals"] == [{
        "retrieval_id": int(retrieval.id),
        "canonical_sha256": retrieval.canonical_sha256,
        "canonical_chars": int(retrieval.canonical_chars),
    }]
    assert hashlib.sha256(
        persisted.execution_intent_json.encode("utf-8")
    ).hexdigest() == persisted.intent_fingerprint

    # Wykonanie jest odrzucane fail-closed: zero konsumpcji, zero requestu.
    caller = _FakeEvidenceCaller()
    _install_fake_client(monkeypatch, caller)
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.FAILED
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    assert "EVIDENCE_RESEARCH_REFUSED" in (job_row.last_error or "")
    assert not caller.calls
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?",
        (approval.id,),
    ).fetchone()["consumed_at"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts"
    ).fetchone()[0] == 0


def test_rejected_excerpt_leaves_source_unverified_but_flow_succeeds(
        monkeypatch, settings, storage, account):
    real_settings, _topic_row, retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="paraphrase",
    )
    _approve(storage, job.id, account)
    caller = _FakeEvidenceCaller(
        response=_evidence_response(
            retrieval.requested_url,
            excerpt="A paraphrase that does not appear verbatim in the canon.",
        ),
    )
    _install_fake_client(monkeypatch, caller)
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.DONE
    run_id = storage.get_job(job.id).run_id
    research_run = storage.get_research_run(run_id)
    assert storage.list_evidence_excerpts(
        int(retrieval.id), account_id=account.id,
    ) == []
    source_row = storage.conn.execute(
        "SELECT verification_status FROM sources WHERE research_card_id=?",
        (research_run.research_card_id,),
    ).fetchone()
    assert source_row["verification_status"] == SourceVerification.UNVERIFIED.value


def test_over_reservation_uses_existing_reconciliation_contract(
        monkeypatch, settings, storage, account):
    real_settings, _topic_row, retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="over",
    )
    _approve(storage, job.id, account)
    caller = _FakeEvidenceCaller(
        usage=Usage(input_tokens=10_000_000, output_tokens=1_000_000),
    )
    _install_fake_client(monkeypatch, caller)
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    attempt = storage.conn.execute(
        "SELECT status, error_code FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchone()
    assert attempt["status"] == "NEEDS_RECONCILIATION"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 1
    assert len(caller.calls) == 1
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION


# ---------------------------------------------------------------------------
# Podłogi SQL: provider attempt bez zgody jest niereprezentowalny
# ---------------------------------------------------------------------------

def test_sql_floor_blocks_attempt_without_consumed_matching_approval(
        settings, storage, account):
    _real, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="floor",
    )
    fingerprint = durable_execution_intent_fingerprint(
        storage.get_job(job.id).payload
    )
    insert = (
        "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,"
        "status,execution_intent_fingerprint,reserved_amount_usd,reserved_at) "
        "VALUES (?,?,?,?,?,?,?,?)"
    )
    # Bez approvalu w ogóle.
    with pytest.raises(sqlite3.IntegrityError, match="consumed matching L1 approval"):
        storage.conn.execute(insert, (
            job.id, "research", 1, f"{job.id}:research:1", "RESERVED",
            fingerprint, 0.5, "2026-07-19 12:00:00",
        ))
    storage.conn.rollback()
    approval = _approve(storage, job.id, account)
    # Approval istnieje, ale NIE jest skonsumowany.
    with pytest.raises(sqlite3.IntegrityError, match="consumed matching L1 approval"):
        storage.conn.execute(insert, (
            job.id, "research", 1, f"{job.id}:research:1", "RESERVED",
            fingerprint, 0.5, "2026-07-19 12:00:00",
        ))
    storage.conn.rollback()
    storage.conn.execute(
        "UPDATE controlled_fetch_approvals SET consumed_at='2026-07-19 12:00:00' "
        "WHERE id=?", (approval.id,),
    )
    # Skonsumowany, ale fingerprint attemptu inny niż zatwierdzony.
    with pytest.raises(sqlite3.IntegrityError, match="consumed matching L1 approval"):
        storage.conn.execute(insert, (
            job.id, "research", 1, f"{job.id}:research:1", "RESERVED",
            "f" * 64, 0.5, "2026-07-19 12:00:01",
        ))
    storage.conn.rollback()
    # Drugi attempt (attempt_no=2) jest niereprezentowalny.
    with pytest.raises(sqlite3.IntegrityError, match="exactly one attempt"):
        storage.conn.execute(insert, (
            job.id, "research", 2, f"{job.id}:research:2", "RESERVED",
            fingerprint, 0.5, "2026-07-19 12:00:01",
        ))
    storage.conn.rollback()


# ---------------------------------------------------------------------------
# Granica providera, recovery i fencing (manualny durable walk)
# ---------------------------------------------------------------------------

def _manual_walk(settings, storage, account, *, key, request_started):
    """Claim + init + (konsumpcja i rezerwacja) [+ REQUEST_STARTED] pod FixedClock."""
    real_settings, topic, retrieval, job, intent = _prepared_e2e(
        settings, storage, account, key=key,
    )
    _approve(storage, job.id, account)
    clock = FixedClock(NOW)
    lease = storage.claim_next_job("walk-owner", 60, clock=clock)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_running(job.id, "walk-owner", clock=clock)
    initialized = storage.initialize_research_run_for_job(
        job.id, "walk-owner", f"run-{key}", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="walk-owner", run_id=initialized.run.id,
        clock=clock,
    )
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1,
        max_cost_usd=float(intent.pessimistic_cost_usd),
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    if request_started:
        storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    return real_settings, retrieval, job, execution, attempt


def test_boundary_snapshot_recheck_maps_divergence_to_reconciliation(
        settings, storage, account):
    real_settings, retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="boundary", request_started=True,
    )
    fingerprint = attempt.execution_intent_fingerprint
    # Snapshot przechodzi przy zgodnym stanie.
    storage.assert_evidence_research_snapshot(
        execution, expected_intent_fingerprint=fingerprint,
    )
    # Rozjazd payloadu PO REQUEST_STARTED...
    mutated = json.loads(storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (job.id,),
    ).fetchone()[0])
    mutated["execution_intent"]["evidence_input"]["retrievals"][0][
        "canonical_sha256"
    ] = "c" * 64
    storage.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?",
        (json.dumps(mutated), job.id),
    )
    storage.conn.commit()
    with pytest.raises(EvidenceResearchAuthorizationError):
        storage.assert_evidence_research_snapshot(
            execution, expected_intent_fingerprint=fingerprint,
        )
    # ...trafia w ISTNIEJĄCY kontrakt reconciliation — nigdy w drugi request.
    storage.mark_provider_attempt_needs_reconciliation(
        execution, attempt.request_id, error_code="EVIDENCE_SNAPSHOT_DIVERGED",
    )
    row = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert row["status"] == "NEEDS_RECONCILIATION"
    with pytest.raises(ProviderAttemptReconciliationRequired):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=1,
            max_cost_usd=0.5, daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )


@pytest.mark.parametrize("request_started", [False, True])
def test_recovery_after_crash_never_replays_the_consumed_approval(
        settings, storage, account, request_started):
    real_settings, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account,
        key=f"recovery-{int(request_started)}", request_started=request_started,
    )
    consumed_before = storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?",
        (job.id,),
    ).fetchone()["consumed_at"]
    assert consumed_before is not None
    # Crash: proces znika, lease wygasa; recovery działa później.
    later = FixedClock(NOW + timedelta(minutes=10))
    recovery = storage.release_or_requeue_expired_leases(clock=later)
    assert recovery.escalated_reconciliation_count == 1
    attempt_row = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert attempt_row["status"] == "NEEDS_RECONCILIATION"
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.NEEDS_VERIFICATION
    # Zużyta zgoda nie odradza się po restarcie/recovery.
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?",
        (job.id,),
    ).fetchone()["consumed_at"] == consumed_before
    # Żaden nowy attempt nie jest możliwy bez resolvera (fence odrzuca nowego
    # ownera bez lease, a przy ważnym lease resolver jest wymagany).
    with pytest.raises(
        (ProviderAttemptReconciliationRequired, StaleJobExecutionError),
    ):
        storage.begin_provider_attempt(
            JobExecutionContext(
                job_id=job.id, lease_owner="new-owner",
                run_id=execution.run_id, clock=later,
            ),
            stage="research", attempt_no=1, max_cost_usd=0.5,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )


def test_worker_exception_after_settlement_terminalizes_without_second_request(
        monkeypatch, settings, storage, account):
    # Wyjątek PO settlemencie w ŻYWYM workerze: karta+terminalizacja są jedną
    # transakcją (nie powstała), koszt pozostaje w kanonie, attempt SETTLED,
    # zero drugiego requestu i zero drugiego settlementu.
    real_settings, _topic_row, _retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="settled-exc",
    )
    _approve(storage, job.id, account)
    caller = _FakeEvidenceCaller()
    _install_fake_client(monkeypatch, caller)

    def crashing_finalize(self, *args, **kwargs):
        raise RuntimeError("simulated failure between settlement and card")

    monkeypatch.setattr(
        SqliteStorage, "finalize_job_research_execution", crashing_finalize,
    )
    result = _worker(real_settings, storage).run_once()
    assert result.status is WorkerIterationStatus.FAILED
    attempt = storage.conn.execute(
        "SELECT status, actual_cost_usd FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchone()
    assert attempt["status"] == "SETTLED"
    assert attempt["actual_cost_usd"] is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 1
    run_id = storage.get_job(job.id).run_id
    research_run = storage.get_research_run(run_id)
    assert research_run.research_card_id is None
    assert research_run.status.value == "FAILED"
    assert float(research_run.total_cost_usd) == pytest.approx(
        float(attempt["actual_cost_usd"])
    )
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert len(caller.calls) == 1


def test_process_death_after_settlement_recovers_via_settled_execution_recovery(
        settings, storage, account):
    # Śmierć procesu PO settlemencie a PRZED kartą: lease wygasa, recovery
    # 0015 rozstrzyga EXECUTION_FAILED — bez drugiego requestu, z jednym
    # settlementem i zachowanym kanonem kosztu.
    from app.models import ModelUsage

    real_settings, _retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="settled-death", request_started=True,
    )
    usage = storage.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, provider="anthropic", model="evidence-test-model",
        task="research", input_tokens=100, output_tokens=100,
        estimated_cost_usd=0.000123, dry_run=False, request_id=attempt.request_id,
        created_at=NOW,
    ))
    assert usage.id is not None
    settled = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert settled["status"] == "SETTLED"
    # Proces znika; recovery działa po wygaśnięciu lease.
    later = FixedClock(NOW + timedelta(minutes=10))
    recovery = storage.release_or_requeue_expired_leases(clock=later)
    assert recovery.settled_execution_recovery_count == 1
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    research_run = storage.get_research_run(execution.run_id)
    assert research_run.status.value == "FAILED"
    assert research_run.research_card_id is None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()["status"] == "SETTLED"
    # Zużyta zgoda pozostaje zużyta.
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?",
        (job.id,),
    ).fetchone()["consumed_at"] is not None


def test_stale_or_old_owner_cannot_write_usage_excerpts_card_or_terminal(
        settings, storage, account):
    from app.models import ModelUsage

    real_settings, retrieval, job, execution, attempt = _manual_walk(
        settings, storage, account, key="fencing", request_started=True,
    )
    later = FixedClock(NOW + timedelta(minutes=10))
    stale = JobExecutionContext(
        job_id=job.id, lease_owner="walk-owner", run_id=execution.run_id,
        clock=later,
    )
    wrong_owner = JobExecutionContext(
        job_id=job.id, lease_owner="intruder", run_id=execution.run_id,
        clock=FixedClock(NOW),
    )
    for context in (stale, wrong_owner):
        with pytest.raises(StaleJobExecutionError):
            storage.add_job_model_usage(context, ModelUsage(
                run_id=execution.run_id, provider="anthropic", model="m",
                task="research", input_tokens=1, output_tokens=1,
                estimated_cost_usd=0.01, dry_run=False,
                request_id=attempt.request_id,
            ))
        with pytest.raises(StaleJobExecutionError):
            storage.record_job_verified_evidence_excerpt(
                context, int(retrieval.id), claim_text=CLAIM,
                excerpt_text=EXCERPT,
                start_offset=retrieval.canonical_text.find(EXCERPT),
                end_offset=retrieval.canonical_text.find(EXCERPT) + len(EXCERPT),
            )
        with pytest.raises(StaleJobExecutionError):
            storage.assert_evidence_research_snapshot(
                context,
                expected_intent_fingerprint=attempt.execution_intent_fingerprint,
            )
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 0
    assert storage.list_evidence_excerpts(
        int(retrieval.id), account_id=account.id,
    ) == []


def test_fenced_excerpt_writer_rejects_non_canonical_ranges(
        settings, storage, account):
    real_settings, retrieval, job, execution, _attempt = _manual_walk(
        settings, storage, account, key="verifier", request_started=False,
    )
    with pytest.raises(EvidenceVerificationError):
        storage.record_job_verified_evidence_excerpt(
            execution, int(retrieval.id), claim_text=CLAIM,
            excerpt_text="not a canonical range of the persisted text",
            start_offset=0, end_offset=46,
        )
    assert storage.list_evidence_excerpts(
        int(retrieval.id), account_id=account.id,
    ) == []
    start = retrieval.canonical_text.find(EXCERPT)
    stored = storage.record_job_verified_evidence_excerpt(
        execution, int(retrieval.id), claim_text=CLAIM, excerpt_text=EXCERPT,
        start_offset=start, end_offset=start + len(EXCERPT),
    )
    assert stored.id is not None
    assert stored.retrieval_id == int(retrieval.id)


# ---------------------------------------------------------------------------
# Regresja cardinality źródeł: jeden retrieval = jedno źródło (live shape)
# ---------------------------------------------------------------------------

def _evidence_response_multi(url, entries):
    """Odpowiedź evidence z wieloma źródłami wskazującymi TEN SAM URL/retrieval."""
    return json.dumps({
        "question": "Why?",
        "working_thesis": "Layout drives basket size.",
        "main_mechanism": "Forced path exposure.",
        "confirmed_claims": [claim for claim, _ in entries],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "Convenience placement exists too.",
        "citable_numbers": [],
        "visual_idea": "A floor plan.",
        "confidence_score": 0.9,
        "source_quality_score": 0.9,
        "sources": [
            {
                "url": url, "title": f"Supermarket layout {index}",
                "author_or_org": None, "published_at": None,
                "source_type": "SECONDARY",
                "supports_claim": claim, "supporting_excerpt": excerpt,
            }
            for index, (claim, excerpt) in enumerate(entries)
        ],
    })


def test_three_excerpts_one_retrieval_reject_too_few_sources(
        monkeypatch, settings, storage, account):
    # Dokładny kształt pierwszego realnego live (job real-research-82e36c4b…,
    # karta id=4): jeden retrieval zacytowany trzykrotnie. Wszystkie 3 excerpty
    # E1-VERIFIED, ale to JEDNO odrębne źródło → REJECT / TOO_FEW_SOURCES.
    real_settings, _topic_row, retrieval, job, _intent = _prepared_e2e(
        settings, storage, account, key="cardinality",
    )
    _approve(storage, job.id, account)
    entries = [
        ("Essentials sit at the back of the store.",
         "essential items at the back of the store"),
        ("Shoppers pass tempting displays.",
         "walk past tempting displays on every trip"),
        ("Baskets grow measurably larger.",
         "measurably larger baskets across chains"),
    ]
    # każdy excerpt to dosłowny fragment tego samego canonical text
    for _claim, excerpt in entries:
        assert excerpt in retrieval.canonical_text
    caller = _FakeEvidenceCaller(
        response=_evidence_response_multi(retrieval.requested_url, entries),
    )
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    # Techniczny sukces bez zmian: jeden request, DONE, jedno usage, settlement.
    assert result.status is WorkerIterationStatus.DONE
    assert len(caller.calls) == 1
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.DONE
    run_id = job_row.run_id
    assert storage.get_run(run_id).status is RunStatus.SUCCESS
    research_run = storage.get_research_run(run_id)
    assert research_run.status.value == "COMPLETE"
    assert research_run.research_card_id is not None
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == "SETTLED"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=? AND dry_run=0", (run_id,),
    ).fetchone()[0] == 1

    # Trzy rekordy source, wszystkie VERIFIED, wszystkie wskazują ten sam URL/
    # retrieval — a więc JEDNO odrębne, zatwierdzone źródło.
    srcs = storage.conn.execute(
        "SELECT url, verification_status FROM sources WHERE research_card_id=?",
        (research_run.research_card_id,),
    ).fetchall()
    assert len(srcs) == 3
    assert {s["url"] for s in srcs} == {retrieval.requested_url}
    assert all(
        s["verification_status"] == SourceVerification.VERIFIED.value for s in srcs
    )
    assert storage.list_evidence_excerpts(
        int(retrieval.id), account_id=account.id,
    )  # E1 zweryfikował excerpt(y) z tego jednego retrievalu

    # Bramka jakości: jeden odrębny retrieval < min_sources=3 → TOO_FEW_SOURCES.
    card_row = storage.conn.execute(
        "SELECT publication_recommendation, rejection_reason FROM research_cards "
        "WHERE id=?", (research_run.research_card_id,),
    ).fetchone()
    assert card_row["publication_recommendation"] == "REJECT"
    assert "TOO_FEW_SOURCES" in (card_row["rejection_reason"] or "")

    # Zero nowego retrievalu i zero nowego Fetchu (jak w live).
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_retrievals"
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM controlled_fetch_attempts"
    ).fetchone()[0] == 0
