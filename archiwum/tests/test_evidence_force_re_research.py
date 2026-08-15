"""Wąskie regresje: durable evidence RE-RESEARCH przez jawne --force-re-research.

Naprawiona sprzeczność bramek: temat z kompletną Research Card był blokowany
bez --force-re-research, a durable enqueue odrzucał --force-re-research. Ten fix
dopuszcza jawny re-research WYŁĄCZNIE jako re-syntezę zamrożonego evidence
(single, zero web search), zapisuje flagę w frozen intencie (odrębny fingerprint),
i przewleka ją przez dispatcher do bramki wykonania — bez nadpisywania starej karty.

BLOCKER-1 (finalizacja durable single flow wymagała tematu `SELECTED`, więc temat
`USED` płacił za request i kończył `FAILED` bez karty) ma tu pełne pokrycie
production-like: job -> approval L1 -> worker -> dispatcher -> pipeline -> fake
provider -> finalizacja -> storage, na replice produkcyjnego stanu tematu 9.
Zero sieci, zero SDK, zero kosztu — wyłącznie fake caller i bazy tymczasowe.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.llm.usage_tracker import UsageTracker
from app.models import (
    Job,
    JobKind,
    JobStatus,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.fetch import FetchedDocument
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.ports.storage import EvidenceResearchAuthorizationError
from app.research.durable_intent import (
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    durable_execution_intent_fingerprint,
    evidence_input_payload,
)
from app.research.fake_client import FakeResearchClient
from app.scheduler.worker import WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from app.workflows.research.pipeline import (
    CompletedResearchExistsError,
    ensure_topic_can_start_research,
    run_research_pipeline,
)

from tests.conftest import write_approved_pricing_profile
# Ten sam, już zaufany harness durable evidence co E3 — jeden worker, jeden
# dispatcher, jeden fake caller; nic tu nie duplikuje produkcyjnej ścieżki.
from tests.test_e3_evidence_research import (
    NOW as WORKER_NOW,
    _FakeEvidenceCaller,
    _approve,
    _install_fake_client,
    _open_flags,
    _pricing_profile,
    _real_settings as _worker_real_settings,
    _seed_retrieval as _seed_worker_retrieval,
    _worker,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
MODEL = "dry-run-fake"


def _real_settings(settings):
    return replace(
        settings, dry_run=False, model_quality=MODEL, anthropic_api_key="test-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def _selected_topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Why supermarkets put milk at the back",
        question="What incentive puts milk far from the entrance?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _complete_card(settings, storage, account, topic) -> None:
    """Create exactly one completed Research Card for the topic (offline fake)."""
    run_research_pipeline(
        account, topic, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def _seed_retrieval(storage, account, url, *, status=200, error=None,
                    body="Milk sits at the back to build the basket. " * 40):
    storage.ensure_account(account)
    return storage.record_evidence_retrieval(
        FetchedDocument(
            requested_url=url, final_url=url, fetched_at=NOW, http_status=status,
            content_type="text/html; charset=utf-8", body=body.encode("utf-8"),
            error=error,
        ),
        account_id=account.id, now=NOW,
    )


def _enqueue(monkeypatch, real_settings, topic_id, extra):
    from scripts import run_capped_research
    profile_id, _ = write_approved_pricing_profile(real_settings.project_root, model=MODEL)
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: real_settings)
    argv = [
        "--topic-id", str(topic_id), "--real", "--mode", "single",
        "--max-web-searches", "0", "--operation-key", "evidence-reresearch",
        "--pricing-profile", profile_id, "--max-tokens", "3000",
        "--max-cost-usd", "1.0", "--max-retries", "0", *extra,
    ]
    return run_capped_research.main(argv)


def _persisted_intent(storage):
    row = storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id LIKE 'real-research-%'"
    ).fetchone()
    return json.loads(row["payload_json"])["execution_intent"]


# --------------------------------------------------------------------------- #
# CLI enqueue — the fixed conflict                                            #
# --------------------------------------------------------------------------- #

def test_completed_card_without_force_still_refuses_evidence_enqueue(
        monkeypatch, capsys, settings, storage, account):
    """Invariant 1: the old completed-card block still fires without --force."""
    real = _real_settings(settings)
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)
    r = _seed_retrieval(storage, account, "https://a.example/doc")

    code = _enqueue(monkeypatch, real, topic.id, ["--evidence-retrieval-id", str(r.id)])

    assert code == 1
    assert "--force-re-research" in capsys.readouterr().out
    # nothing durable was persisted
    assert storage.conn.execute(
        "SELECT count(*) FROM jobs WHERE id LIKE 'real-research-%'"
    ).fetchone()[0] == 0


def test_completed_card_with_force_enqueues_evidence_reresearch(
        monkeypatch, settings, storage, account):
    """Invariants 2/7/8/11/13: force durable evidence re-research, frozen + auditable."""
    real = _real_settings(settings)
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)
    cards_before = storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0]
    r1 = _seed_retrieval(storage, account, "https://a.example/doc")
    r2 = _seed_retrieval(storage, account, "https://b.example/doc")

    code = _enqueue(monkeypatch, real, topic.id, [
        "--force-re-research",
        "--evidence-retrieval-id", str(r1.id),
        "--evidence-retrieval-id", str(r2.id),
    ])

    assert code == 0
    intent = _persisted_intent(storage)
    # frozen intent records that this is a re-research
    assert intent["flags"] == {"force_re_research": True}
    # exact retrieval IDs, cardinality from unique evidence_retrieval_id
    ids = [entry["retrieval_id"] for entry in intent["evidence_input"]["retrievals"]]
    assert ids == [int(r1.id), int(r2.id)]
    assert len(set(ids)) == 2
    # enqueue performs NO provider request and NO attempt
    assert storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE dry_run=0").fetchone()[0] == 0
    # the existing Research Card is untouched (enqueue never creates/edits cards)
    assert storage.conn.execute(
        "SELECT count(*) FROM research_cards"
    ).fetchone()[0] == cards_before
    # zero web search stays frozen in the intent
    assert intent["max_web_searches"] == 0


def test_force_without_evidence_is_refused_by_durable_path(
        monkeypatch, capsys, settings, storage, account):
    """Scope: --force-re-research is honoured ONLY as evidence re-research."""
    real = _real_settings(settings)
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)

    # search-based (no --evidence-retrieval-id) force re-research must be refused
    code = _enqueue(monkeypatch, real, topic.id, ["--force-re-research"])

    assert code == 2
    assert "INVALID_CONFIGURATION" in capsys.readouterr().out
    assert storage.conn.execute(
        "SELECT count(*) FROM jobs WHERE id LIKE 'real-research-%'"
    ).fetchone()[0] == 0


def test_failed_retrieval_is_rejected_as_evidence(
        monkeypatch, capsys, settings, storage, account):
    """Invariants 5/6: only OK retrievals; a FAILED (e.g. HTTP 403) is refused."""
    real = _real_settings(settings)
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)
    failed = _seed_retrieval(
        storage, account, "https://rd.example/403",
        status=403, error="HTTP_STATUS_403", body="forbidden",
    )

    code = _enqueue(monkeypatch, real, topic.id, [
        "--force-re-research", "--evidence-retrieval-id", str(failed.id),
    ])

    assert code == 1
    out = capsys.readouterr().out
    assert "OK" in out  # STOP: ... ma status ...; wymagany OK.
    assert storage.conn.execute(
        "SELECT count(*) FROM jobs WHERE id LIKE 'real-research-%'"
    ).fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# Frozen intent contract                                                      #
# --------------------------------------------------------------------------- #

def _evidence_intent(real, account, *, force_re_research, evidence=True):
    ev = evidence_input_payload([(1, "a" * 64, 100)]) if evidence else None
    return DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=9, cap_usd="0.30",
        max_web_searches=0, question="q", niche=list(account.niche), max_tokens=3000,
        evidence_input=ev, force_re_research=force_re_research,
    )


def _full_payload(intent):
    return {
        "account_id": intent.account_id, "topic_id": intent.topic_id, "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single",
        "max_cost_usd": intent.cap_usd, "execution_intent": intent.as_payload(),
    }


def test_frozen_intent_records_reresearch_and_changes_fingerprint(settings, account):
    real = _real_settings(settings)
    it_re = _evidence_intent(real, account, force_re_research=True)
    it_no = _evidence_intent(real, account, force_re_research=False)

    assert it_re.force_re_research is True
    assert it_re.as_payload()["flags"] == {"force_re_research": True}
    assert it_no.as_payload()["flags"] == {"force_re_research": False}
    # re-research is a distinct request-affecting flag → distinct fingerprint
    assert durable_execution_intent_fingerprint(_full_payload(it_re)) != \
        durable_execution_intent_fingerprint(_full_payload(it_no))
    # round-trip preserves the flag
    assert DurableResearchExecutionIntent.from_payload(
        it_re.as_payload()
    ).force_re_research is True


def test_force_re_research_requires_evidence_both_directions(settings, account):
    real = _real_settings(settings)
    # from_settings: force without evidence is refused
    with pytest.raises(DurableExecutionIntentError) as exc_settings:
        _evidence_intent(real, account, force_re_research=True, evidence=False)
    assert exc_settings.value.code == "FORCE_RE_RESEARCH_REQUIRES_EVIDENCE"

    # from_payload: a non-evidence payload whose flags claim re-research is malformed
    plain = _evidence_intent(real, account, force_re_research=False, evidence=False)
    payload = plain.as_payload()
    assert "evidence_input" not in payload
    payload["flags"] = {"force_re_research": True}
    with pytest.raises(DurableExecutionIntentError) as exc_payload:
        DurableResearchExecutionIntent.from_payload(payload)
    assert exc_payload.value.code == "FORCE_RE_RESEARCH_REQUIRES_EVIDENCE"


def test_default_durable_intent_stays_non_reresearch(settings, account):
    """Invariant 3: unrelated durable/dry paths keep flags force_re_research=False."""
    real = _real_settings(settings)
    it = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=9, cap_usd="0.30",
        max_web_searches=3, question="q", niche=list(account.niche), max_tokens=3000,
    )
    assert it.force_re_research is False
    assert it.as_payload()["flags"] == {"force_re_research": False}


# --------------------------------------------------------------------------- #
# Execution gate + dispatcher threading                                       #
# --------------------------------------------------------------------------- #

def test_pipeline_gate_bypassed_only_with_force_and_preserves_old_card(
        settings, storage, account):
    """Invariants 2/11/12: the completed-card gate bypasses ONLY with force; the
    prior card is preserved and a new run adds a distinct card."""
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)
    cards_after_first = storage.conn.execute(
        "SELECT id FROM research_cards WHERE topic_id=?", (int(topic.id),)
    ).fetchall()
    assert len(cards_after_first) == 1
    first_card_id = cards_after_first[0][0]

    # Without force the gate refuses (unchanged behaviour).
    with pytest.raises(CompletedResearchExistsError):
        ensure_topic_can_start_research(storage, account, topic, False)

    # With force a fresh pipeline run proceeds and adds a SECOND, distinct card.
    _complete_card_force(settings, storage, account, topic)
    cards_after_second = storage.conn.execute(
        "SELECT id FROM research_cards WHERE topic_id=? ORDER BY id", (int(topic.id),)
    ).fetchall()
    assert len(cards_after_second) == 2
    # the original card is still present and untouched (never deleted/rewritten)
    assert first_card_id in [row[0] for row in cards_after_second]


def _complete_card_force(settings, storage, account, topic) -> None:
    run_research_pipeline(
        account, topic, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        force_re_research=True,
    )


# --------------------------------------------------------------------------- #
# Production-like durable flow na replice produkcyjnego stanu tematu 9         #
# job -> approval L1 -> worker -> dispatcher -> pipeline -> fake provider ->   #
# finalizacja -> storage.  Bez dry-runu pipeline'u jako dowodu finalizacji.    #
# --------------------------------------------------------------------------- #

# Trzy dosłowne fragmenty kanonu retrievalu (ten sam korpus co harness E3).
EVIDENCE_ENTRIES = (
    ("Essentials sit at the back of the store.",
     "essential items at the back of the store"),
    ("Shoppers pass tempting displays.",
     "walk past tempting displays on every trip"),
    ("Baskets grow measurably larger.",
     "measurably larger baskets across chains"),
)


def _evidence_response_for(sources):
    """Odpowiedź fake providera cytująca podane (url, claim, excerpt)."""
    return json.dumps({
        "question": "Why?",
        "working_thesis": "Layout drives basket size.",
        "main_mechanism": "Forced path exposure.",
        "confirmed_claims": [claim for _url, claim, _excerpt in sources],
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
            for index, (url, claim, excerpt) in enumerate(sources)
        ],
    })


def _durable_evidence_job(storage, real_settings, account, topic, retrievals, *,
                          force_re_research, key, cap=1.0):
    """Trwały job durable_provider_v2 z zamrożonym evidence i flagą trybu."""
    profile = _pricing_profile(real_settings)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real_settings, account_id=account.id, topic_id=int(topic.id),
        cap_usd=cap, max_web_searches=0,
        question=topic.question or topic.title, niche=account.niche,
        max_tokens=3000,
        evidence_input=evidence_input_payload([
            (int(r.id), r.canonical_sha256, int(r.canonical_chars))
            for r in retrievals
        ]),
        force_re_research=force_re_research,
        pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )
    payload = {
        "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single",
        "max_cost_usd": intent.cap_usd, "execution_intent": intent.as_payload(),
    }
    job = storage.enqueue_job(Job(
        id=f"reresearch-job-{key}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"reresearch-{key}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=WORKER_NOW, max_attempts=1, payload=payload,
    ))
    _open_flags(storage)
    return job, intent


def _topic_status(storage, topic_id):
    return storage.conn.execute(
        "SELECT status FROM topics WHERE id=?", (int(topic_id),),
    ).fetchone()["status"]


def _card_ids(storage, topic_id):
    return [row[0] for row in storage.conn.execute(
        "SELECT id FROM research_cards WHERE topic_id=? ORDER BY id", (int(topic_id),),
    ).fetchall()]


def _card_snapshot(storage, card_id):
    card = dict(storage.conn.execute(
        "SELECT * FROM research_cards WHERE id=?", (int(card_id),),
    ).fetchone())
    sources = [dict(row) for row in storage.conn.execute(
        "SELECT * FROM sources WHERE research_card_id=? ORDER BY id", (int(card_id),),
    ).fetchall()]
    return card, sources


def _counters(storage):
    return {
        "attempts": storage.conn.execute(
            "SELECT count(*) FROM provider_attempts"
        ).fetchone()[0],
        "real_usage": storage.conn.execute(
            "SELECT count(*) FROM model_usage WHERE dry_run=0"
        ).fetchone()[0],
    }


def _used_topic_with_card(settings, storage, account, *, retrieval_count=3):
    """Replika produkcyjnego stanu tematu 9: USED + jedna kompletna karta.

    Kartę tworzy prawdziwy pipeline (fake client, dry-run), więc relacja
    run/research_run/karta/temat jest dokładnie taka jak w produkcji.
    """
    topic = _selected_topic(storage, account)
    _complete_card(settings, storage, account, topic)
    assert _topic_status(storage, topic.id) == TopicStatus.USED.value
    old_cards = _card_ids(storage, topic.id)
    assert len(old_cards) == 1
    retrievals = [
        _seed_worker_retrieval(storage, account, url=f"https://evidence.example/doc{index}")
        for index in range(retrieval_count)
    ]
    return topic, old_cards[0], retrievals


def _caller_for(retrievals, entries=EVIDENCE_ENTRIES):
    sources = [
        (retrieval.requested_url, claim, excerpt)
        for retrieval, (claim, excerpt) in zip(retrievals, entries)
    ]
    for retrieval, (_claim, excerpt) in zip(retrievals, entries):
        assert excerpt in retrieval.canonical_text
    return _FakeEvidenceCaller(response=_evidence_response_for(sources))


def test_used_topic_without_force_is_refused_before_any_provider_request(
        monkeypatch, settings, storage, account):
    """Przypadek 1: temat USED + istniejąca karta + BEZ force -> odmowa przed providerem."""
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=False, key="used-no-force",
    )
    approval = _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.FAILED
    assert not caller.calls
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert _counters(storage) == {"attempts": 0, "real_usage": 0}
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"] is None
    # Stara karta i temat nietknięte.
    assert _card_ids(storage, topic.id) == [old_card_id]
    assert _topic_status(storage, topic.id) == TopicStatus.USED.value


def test_used_topic_force_re_research_adds_a_second_card_via_one_provider_request(
        monkeypatch, settings, storage, account):
    """Przypadek 2 (kontrpróba na replice tematu 9): dokładnie jeden fake request,
    job DONE, attempt terminalny, zgoda zużyta raz, stara karta zachowana,
    nowa karta odrębna, temat pozostaje USED."""
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    old_card_before = _card_snapshot(storage, old_card_id)
    job, intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="used-force",
    )
    assert intent.force_re_research is True
    approval = _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    # Exactly-one provider request — dowód z zachowania fake callera.
    assert len(caller.calls) == 1
    assert caller.contracts[0].max_web_searches == 0
    assert [document.retrieval_id for document in caller.contracts[0].documents] == [
        int(r.id) for r in retrievals
    ]

    assert result.status is WorkerIterationStatus.DONE
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.DONE
    assert storage.get_run(job_row.run_id).status is RunStatus.SUCCESS
    research_run = storage.get_research_run(job_row.run_id)
    assert research_run.status.value == "COMPLETE"
    assert research_run.is_force_reresearch is True

    # Nowa karta jest ODRĘBNYM rekordem; stara pozostała bajt-w-bajt taka sama.
    cards = _card_ids(storage, topic.id)
    assert len(cards) == 2 and old_card_id in cards
    new_card_id = next(card_id for card_id in cards if card_id != old_card_id)
    assert research_run.research_card_id == new_card_id
    assert _card_snapshot(storage, old_card_id) == old_card_before

    # Temat zostaje w spójnym stanie końcowym lifecycle'u.
    assert _topic_status(storage, topic.id) == TopicStatus.USED.value

    # Attempt terminalny, jedno usage, zgoda zużyta dokładnie raz.
    attempts = [dict(row) for row in storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchall()]
    assert len(attempts) == 1
    assert attempts[0]["status"] == "SETTLED"
    assert attempts[0]["attempt_no"] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=? AND dry_run=0",
        (job_row.run_id,),
    ).fetchone()[0] == 1
    approval_row = storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()
    assert approval_row["consumed_at"] == attempts[0]["reserved_at"]

    # Zero nowego Fetchu — re-research to wyłącznie re-synteza zamrożonego evidence.
    assert storage.conn.execute(
        "SELECT count(*) FROM controlled_fetch_attempts"
    ).fetchone()[0] == 0


def test_same_frozen_evidence_can_be_reused_by_a_second_reresearch_run(
        monkeypatch, settings, storage, account):
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    _install_fake_client(monkeypatch, _caller_for(retrievals))

    first, _ = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="same-corpus-first",
    )
    _approve(storage, first.id, account)
    assert _worker(real_settings, storage).run_once().status is WorkerIterationStatus.DONE

    second, _ = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="same-corpus-second",
    )
    _approve(storage, second.id, account)
    assert _worker(real_settings, storage).run_once().status is WorkerIterationStatus.DONE

    assert len(_card_ids(storage, topic.id)) == 3
    assert old_card_id in _card_ids(storage, topic.id)
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_candidate_retrievals "
        "WHERE retrieval_id=?",
        (int(retrievals[0].id),),
    ).fetchone()[0] == 2


def test_public_cli_force_re_research_reaches_a_new_card_through_the_worker(
        monkeypatch, settings, storage, account):
    """Pełny production-like łańcuch: publiczny CLI -> job -> approval L1 ->
    worker -> dispatcher -> pipeline -> fake provider -> finalizacja -> storage."""
    from datetime import timedelta

    from app.core.clock import FixedClock
    from app.research.durable_intent import (
        controlled_research_job_id,
        controlled_session_contract,
    )

    real = _real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    old_card_before = _card_snapshot(storage, old_card_id)

    evidence_args = []
    for retrieval in retrievals:
        evidence_args += ["--evidence-retrieval-id", str(retrieval.id)]
    assert _enqueue(monkeypatch, real, topic.id, ["--force-re-research", *evidence_args]) == 0

    operation_key = "evidence-reresearch"
    job_id = controlled_research_job_id(operation_key)
    session = controlled_session_contract(operation_key)
    enqueued = storage.get_job(job_id)
    assert enqueued.status is JobStatus.QUEUED
    assert json.loads(storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (job_id,),
    ).fetchone()[0])["execution_intent"]["flags"] == {"force_re_research": True}

    clock = FixedClock(datetime.now(timezone.utc) + timedelta(minutes=1))
    storage.apply_security_flag_profile([
        ("worker_enabled", True), ("safe_mode", False), ("paid_actions_enabled", True),
        ("browser_actions_enabled", False), ("kill_switch", False),
    ], updated_by="test", reason="cli-reresearch", now=clock.now())
    approval = storage.record_evidence_research_approval(
        job_id=job_id, account_id=account.id, approved_by="owner-l1",
        expires_at=clock.now() + timedelta(hours=2), clock=clock,
    )
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(
        real, storage, lease_owner=session["worker_execution_token"], clock=clock,
    ).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert len(caller.calls) == 1
    job_row = storage.get_job(job_id)
    assert job_row.status is JobStatus.DONE
    research_run = storage.get_research_run(job_row.run_id)
    assert research_run.status.value == "COMPLETE"
    cards = _card_ids(storage, topic.id)
    assert len(cards) == 2 and old_card_id in cards
    assert research_run.research_card_id == next(c for c in cards if c != old_card_id)
    assert _card_snapshot(storage, old_card_id) == old_card_before
    assert _topic_status(storage, topic.id) == TopicStatus.USED.value
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"] is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=? AND status='SETTLED'",
        (job_id,),
    ).fetchone()[0] == 1


def test_selected_topic_force_re_research_completes_and_marks_topic_used(
        monkeypatch, settings, storage, account):
    """Przypadek 3: temat SELECTED + force kończy się zgodnie z kontraktem."""
    real_settings = _worker_real_settings(settings)
    topic = _selected_topic(storage, account)
    retrievals = [_seed_worker_retrieval(
        storage, account, url="https://evidence.example/selected",
    )]
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="selected-force",
    )
    _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.DONE
    assert len(caller.calls) == 1
    assert len(_card_ids(storage, topic.id)) == 1
    assert _topic_status(storage, topic.id) == TopicStatus.USED.value


def test_unsupported_topic_status_is_refused_before_any_provider_request(
        monkeypatch, settings, storage, account):
    """Przypadek 4: temat w nieobsługiwanym stanie -> odmowa przed granicą płatności."""
    real_settings = _worker_real_settings(settings)
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Not selected yet", question="Why?",
        score=40.0, status=TopicStatus.DISCOVERED,
    ))
    retrievals = [_seed_worker_retrieval(
        storage, account, url="https://evidence.example/discovered",
    )]
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="bad-status",
    )
    approval = _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.FAILED
    assert not caller.calls
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    assert "EVIDENCE_RESEARCH_REFUSED:TOPIC_NOT_RE_RESEARCHABLE" in (job_row.last_error or "")
    assert _counters(storage) == {"attempts": 0, "real_usage": 0}
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"] is None
    assert _card_ids(storage, topic.id) == []
    assert _topic_status(storage, topic.id) == TopicStatus.DISCOVERED.value


def test_topic_status_change_after_preflight_terminalizes_without_a_second_request(
        monkeypatch, settings, storage, account):
    """Przypadek 5: stan tematu zmieniony po kontroli sprzed płatności jest
    wykrywany transakcyjnie w finalizacji — bez drugiego requestu i bez
    częściowej nowej karty."""
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="state-change",
    )
    _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    original_finalize = SqliteStorage.finalize_job_research_execution

    def finalize_after_topic_moved(self, *args, **kwargs):
        # Zmiana statusu tematu dokładnie w oknie: po kontroli przed płatnością
        # i po jedynym requeście, tuż przed transakcją finalizacji.
        self.conn.execute(
            "UPDATE topics SET status=? WHERE id=?",
            (TopicStatus.REJECTED.value, int(topic.id)),
        )
        self.conn.commit()
        return original_finalize(self, *args, **kwargs)

    monkeypatch.setattr(
        SqliteStorage, "finalize_job_research_execution", finalize_after_topic_moved,
    )

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.FAILED
    assert len(caller.calls) == 1  # żadnego drugiego requestu
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    research_run = storage.get_research_run(job_row.run_id)
    assert research_run.status.value == "FAILED"
    assert research_run.research_card_id is None
    # Zero częściowej karty i zero osieroconych źródeł nowego runu.
    assert _card_ids(storage, topic.id) == [old_card_id]
    attempt = storage.conn.execute(
        "SELECT status, actual_cost_usd FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == "SETTLED"
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE dry_run=0"
    ).fetchone()[0] == 1


def test_consumed_approval_cannot_be_replayed_by_a_second_execution(
        monkeypatch, settings, storage, account):
    """Przypadek 6: zgoda jest single-use — replay tej samej zgody jest odrzucony."""
    real_settings = _worker_real_settings(settings)
    topic, _old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="replay",
    )
    approval = _approve(storage, job.id, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    assert _worker(real_settings, storage).run_once().status is WorkerIterationStatus.DONE
    consumed_at = storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"]
    assert consumed_at is not None

    # Kolejna iteracja workera nie ma czego przejąć, a zużyta zgoda nie wraca.
    assert _worker(real_settings, storage, lease_owner="second").run_once().status \
        is WorkerIterationStatus.IDLE
    assert len(caller.calls) == 1

    # Bezpośrednia próba ponownego użycia tej samej zgody (kontrakt storage).
    with pytest.raises(EvidenceResearchAuthorizationError) as exc:
        storage.record_evidence_research_approval(
            job_id=job.id, account_id=account.id, approved_by="owner-l1",
            expires_at=WORKER_NOW.replace(hour=23), clock=_fixed_worker_clock(),
        )
    assert exc.value.code in {"APPROVAL_ALREADY_EXISTS", "JOB_NOT_APPROVABLE"}
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"] == consumed_at
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts"
    ).fetchone()[0] == 1


def test_force_flag_tampered_after_approval_is_refused_before_provider(
        monkeypatch, settings, storage, account):
    """Przypadek 7: podniesienie flagi re-researchu po zgodzie nie kupuje
    re-researchu — rozjazd fingerprintu odmawia przed granicą płatności."""
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=False, key="tampered",
    )
    approval = _approve(storage, job.id, account)
    mutated = json.loads(storage.conn.execute(
        "SELECT payload_json FROM jobs WHERE id=?", (job.id,),
    ).fetchone()[0])
    mutated["execution_intent"]["flags"]["force_re_research"] = True
    storage.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?",
        (json.dumps(mutated, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")), job.id),
    )
    storage.conn.commit()
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    result = _worker(real_settings, storage).run_once()

    assert result.status is WorkerIterationStatus.FAILED
    assert not caller.calls
    job_row = storage.get_job(job.id)
    assert job_row.status is JobStatus.FAILED
    assert "EVIDENCE_RESEARCH_REFUSED:INTENT_MISMATCH" in (job_row.last_error or "")
    assert _counters(storage) == {"attempts": 0, "real_usage": 0}
    assert storage.conn.execute(
        "SELECT consumed_at FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
    ).fetchone()["consumed_at"] is None
    assert _card_ids(storage, topic.id) == [old_card_id]


def test_enqueue_alone_never_reaches_a_provider(
        monkeypatch, settings, storage, account):
    """Przypadek 8: samo utrwalenie joba (bez zgody i bez workera) nie wykonuje
    żadnego requestu ani attemptu."""
    real_settings = _worker_real_settings(settings)
    topic, old_card_id, retrievals = _used_topic_with_card(settings, storage, account)
    caller = _caller_for(retrievals)
    _install_fake_client(monkeypatch, caller)

    job, _intent = _durable_evidence_job(
        storage, real_settings, account, topic, retrievals,
        force_re_research=True, key="enqueue-only",
    )

    assert storage.get_job(job.id).status is JobStatus.QUEUED
    assert not caller.calls
    assert _counters(storage) == {"attempts": 0, "real_usage": 0}
    assert storage.get_evidence_research_approval_for_job(job.id) is None
    assert _card_ids(storage, topic.id) == [old_card_id]


def _fixed_worker_clock():
    from app.core.clock import FixedClock

    return FixedClock(WORKER_NOW)
