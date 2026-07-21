"""Durable owner-proposed topic intake + jednorazowa zgoda L1 -> SELECTED.

Brakującym ogniwem pełnego live Etapów 0-2 było utworzenie NOWEGO tematu:
`run-topics` jest offline-only i zwraca stałe fixture'y, które dedup oznacza
jako DUPLICATE, a żadna publiczna komenda nie promowała kandydata do SELECTED.
Ta fala dokłada lokalny, bezkosztowy composition root: propozycja właściciela ->
walidacja -> istniejący scoring i dedup -> trwały kandydat -> zgoda L1 ->
atomowe SELECTED. Zero sieci, providera, usage i attemptów.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.models import TopicStatus
from app.storage.repositories import SqliteStorage
from app.workflows.topics.discover import compute_weighted_score
from app.workflows.topics.proposal import (
    OWNER_TOPIC_PROPOSAL_OBJECT_TYPE,
    OwnerTopicProposalError,
    canonical_proposal_payload,
    proposal_fingerprint,
    validate_score_breakdown,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
TITLE = "Why bakeries move fresh bread to the entrance in the afternoon"
QUESTION = "What incentive puts fresh bread near the door late in the day?"

STRONG = {
    "curiosity": 0.90, "source_quality": 0.85, "non_obvious": 0.85,
    "universality": 0.80, "discussion_potential": 0.80, "visual_potential": 0.75,
    "originality": 0.85,
}
WEAK = {key: 0.30 for key in STRONG}


def _breakdown(settings, values):
    return validate_score_breakdown(values, settings.topic_scoring_weights)


def _score(settings, values):
    return compute_weighted_score(_breakdown(settings, values), settings.topic_scoring_weights)


def _propose(storage, settings, account, *, title=TITLE, question=QUESTION,
             values=None, key="topic-intake-1", hours=6, now=NOW, rationale=None):
    values = STRONG if values is None else values
    breakdown = _breakdown(settings, values)
    score = compute_weighted_score(breakdown, settings.topic_scoring_weights)
    status = (
        TopicStatus.SCORED if score >= settings.note_min_score else TopicStatus.REJECTED
    )
    return storage.record_owner_topic_proposal(
        account_id=account.id, title=title, question=question, rationale=rationale,
        score_breakdown=breakdown, score=score, candidate_status=status,
        operation_key=key, proposed_by="owner:krapcys1-maker",
        expires_at=now + timedelta(hours=hours),
        duplicate_threshold=settings.topic_duplicate_threshold,
        clock=FixedClock(now),
    )


def _approve(storage, settings, account, topic_id, *, now=NOW, fingerprint=None,
             approved_by="owner-l1"):
    return storage.approve_owner_topic_proposal(
        account_id=account.id, topic_id=topic_id, approved_by=approved_by,
        article_min_score=settings.article_min_score,
        duplicate_threshold=settings.topic_duplicate_threshold,
        clock=FixedClock(now), expected_fingerprint=fingerprint,
    )


def _counters(storage):
    return {
        "usage": storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0],
        "attempts": storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0],
        "runs": storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0],
        "jobs": storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0],
    }


def _topic_status(storage, topic_id):
    return storage.conn.execute(
        "SELECT status FROM topics WHERE id=?", (int(topic_id),)).fetchone()[0]


# --------------------------------------------------------------------------- #
# 1. Proposal                                                                  #
# --------------------------------------------------------------------------- #

def test_owner_proposal_persists_candidate_without_provider(settings, storage, account):
    storage.ensure_account(account)
    before = _counters(storage)

    proposal = _propose(storage, settings, account)

    assert proposal.topic_id > 0
    assert proposal.topic_status is TopicStatus.SCORED       # kandydat, NIE SELECTED
    assert _topic_status(storage, proposal.topic_id) == "SCORED"
    assert proposal.decision == "PENDING" and proposal.consumed_at is None
    assert proposal.score == _score(settings, STRONG) >= settings.article_min_score
    assert proposal.fingerprint == proposal_fingerprint(json.loads(proposal.proposal_json))
    # zero providera, usage, attemptów, runów i jobów
    assert _counters(storage) == before
    row = storage.conn.execute(
        "SELECT object_type, decision FROM approvals WHERE object_id=?",
        (proposal.topic_id,)).fetchone()
    assert row["object_type"] == OWNER_TOPIC_PROPOSAL_OBJECT_TYPE
    assert row["decision"] == "PENDING"
    stored = storage.conn.execute(
        "SELECT source, score FROM topics WHERE id=?", (proposal.topic_id,)).fetchone()
    assert stored["source"] == "owner_proposal"
    assert stored["score"] == pytest.approx(proposal.score)


def test_owner_proposal_requires_the_exact_score_dimensions(settings, storage, account):
    storage.ensure_account(account)
    with pytest.raises(OwnerTopicProposalError) as exc:
        _propose(storage, settings, account, values={"curiosity": 0.9})
    assert exc.value.code == "SCORE_BREAKDOWN_INVALID"
    with pytest.raises(OwnerTopicProposalError) as out_of_range:
        _propose(storage, settings, account, values={**STRONG, "curiosity": 1.4})
    assert out_of_range.value.code == "SCORE_BREAKDOWN_INVALID"


# --------------------------------------------------------------------------- #
# 2-3. Approval + replay                                                       #
# --------------------------------------------------------------------------- #

def test_l1_approval_selects_the_topic_exactly_once(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    before = _counters(storage)

    approved = _approve(storage, settings, account, proposal.topic_id,
                        fingerprint=proposal.fingerprint)

    assert approved.topic_status is TopicStatus.SELECTED
    assert _topic_status(storage, proposal.topic_id) == "SELECTED"
    assert approved.decision == "APPROVED"
    assert approved.consumed_at is not None
    assert approved.approved_by == "owner-l1"
    assert _counters(storage) == before          # nadal zero providera i kosztu

    # replay tej samej zgody
    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, proposal.topic_id)
    assert exc.value.code == "PROPOSAL_ALREADY_DECIDED"
    assert _topic_status(storage, proposal.topic_id) == "SELECTED"


def test_without_approval_topic_never_becomes_selected(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.conn.execute(
            "SELECT status FROM topics WHERE id=?", (proposal.topic_id,)
        ).fetchone()[0] == "SCORED"
    finally:
        reopened.close()


# --------------------------------------------------------------------------- #
# 4-6. Dedup i próg                                                            #
# --------------------------------------------------------------------------- #

def test_exact_duplicate_is_refused_before_any_write(settings, storage, account):
    storage.ensure_account(account)
    first = _propose(storage, settings, account)
    topics_before = storage.conn.execute("SELECT count(*) FROM topics").fetchone()[0]

    with pytest.raises(OwnerTopicProposalError) as exc:
        _propose(storage, settings, account, key="topic-intake-2")

    assert exc.value.code == "DUPLICATE_TOPIC"
    assert storage.conn.execute("SELECT count(*) FROM topics").fetchone()[0] == topics_before
    assert _topic_status(storage, first.topic_id) == "SCORED"


def test_near_duplicate_respects_the_configured_threshold(settings, storage, account):
    storage.ensure_account(account)
    _propose(storage, settings, account)
    near = TITLE.replace("bakeries", "bakery shops")

    with pytest.raises(OwnerTopicProposalError) as exc:
        _propose(storage, settings, account, title=near, key="topic-intake-near")
    assert exc.value.code == "DUPLICATE_TOPIC"
    assert "SEMANTIC_SIMILARITY" in str(exc.value) or "EXACT" in str(exc.value)

    distinct = "How night trains decide which carriages stay coupled"
    other = _propose(storage, settings, account, title=distinct, key="topic-intake-distinct")
    assert other.topic_status is TopicStatus.SCORED


def test_below_threshold_topic_cannot_be_approved(settings, storage, account):
    storage.ensure_account(account)
    weak = _propose(storage, settings, account, values=WEAK, key="topic-intake-weak")
    assert weak.score < settings.article_min_score

    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, weak.topic_id)

    assert exc.value.code in {"BELOW_SELECTION_THRESHOLD", "TOPIC_STATUS_NOT_APPROVABLE"}
    assert _topic_status(storage, weak.topic_id) != "SELECTED"
    assert storage.conn.execute(
        "SELECT decision FROM approvals WHERE object_id=?", (weak.topic_id,)
    ).fetchone()[0] == "PENDING"


# --------------------------------------------------------------------------- #
# 7-9. Tamper, account, expiry                                                 #
# --------------------------------------------------------------------------- #

def test_title_tamper_after_proposal_is_refused_and_keeps_approval_unused(
        settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    storage.conn.execute(
        "UPDATE topics SET title=? WHERE id=?", ("Rewritten title", proposal.topic_id))
    storage.conn.commit()

    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, proposal.topic_id)

    assert exc.value.code == "FINGERPRINT_MISMATCH"
    assert _topic_status(storage, proposal.topic_id) == "SCORED"
    assert storage.conn.execute(
        "SELECT decision, decided_at FROM approvals WHERE object_id=?", (proposal.topic_id,)
    ).fetchone()["decision"] == "PENDING"


def test_question_tamper_and_expected_fingerprint_mismatch_are_refused(
        settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    with pytest.raises(OwnerTopicProposalError) as wrong_expected:
        _approve(storage, settings, account, proposal.topic_id, fingerprint="d" * 64)
    assert wrong_expected.value.code == "FINGERPRINT_MISMATCH"

    storage.conn.execute(
        "UPDATE topics SET question=? WHERE id=?", ("different question", proposal.topic_id))
    storage.conn.commit()
    with pytest.raises(OwnerTopicProposalError) as tampered:
        _approve(storage, settings, account, proposal.topic_id)
    assert tampered.value.code == "FINGERPRINT_MISMATCH"
    assert _topic_status(storage, proposal.topic_id) == "SCORED"


def test_account_mismatch_is_refused(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)

    with pytest.raises(OwnerTopicProposalError) as exc:
        storage.approve_owner_topic_proposal(
            account_id="someone_else", topic_id=proposal.topic_id, approved_by="owner-l1",
            article_min_score=settings.article_min_score,
            duplicate_threshold=settings.topic_duplicate_threshold,
            clock=FixedClock(NOW),
        )

    assert exc.value.code == "ACCOUNT_MISMATCH"
    assert _topic_status(storage, proposal.topic_id) == "SCORED"


def test_expired_proposal_cannot_be_approved(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account, hours=1)

    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, proposal.topic_id,
                 now=NOW + timedelta(hours=2))

    assert exc.value.code == "PROPOSAL_EXPIRED"
    assert _topic_status(storage, proposal.topic_id) == "SCORED"
    assert storage.conn.execute(
        "SELECT decision FROM approvals WHERE object_id=?", (proposal.topic_id,)
    ).fetchone()[0] == "PENDING"


# --------------------------------------------------------------------------- #
# 10-12. Idempotencja, współbieżność, restart                                  #
# --------------------------------------------------------------------------- #

def test_repeated_operation_key_is_idempotent(settings, storage, account):
    storage.ensure_account(account)
    first = _propose(storage, settings, account)
    again = _propose(storage, settings, account)

    assert again.topic_id == first.topic_id and again.id == first.id
    assert storage.conn.execute("SELECT count(*) FROM topics").fetchone()[0] == 1
    assert storage.conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1

    with pytest.raises(OwnerTopicProposalError) as exc:
        _propose(storage, settings, account, title="Completely different topic entirely")
    assert exc.value.code == "OPERATION_KEY_CONFLICT"
    assert storage.conn.execute("SELECT count(*) FROM topics").fetchone()[0] == 1


def test_concurrent_approvals_yield_exactly_one_selection(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    results: list[str] = []
    barrier = threading.Barrier(2)

    def approve(tag: str) -> None:
        worker = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            worker.approve_owner_topic_proposal(
                account_id=account.id, topic_id=proposal.topic_id, approved_by=tag,
                article_min_score=settings.article_min_score,
                duplicate_threshold=settings.topic_duplicate_threshold,
                clock=FixedClock(NOW),
            )
            results.append("OK")
        except Exception as exc:  # noqa: BLE001 - kontrolowany wynik wyścigu
            results.append(getattr(exc, "code", type(exc).__name__))
        finally:
            worker.close()

    threads = [threading.Thread(target=approve, args=(f"owner-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert results.count("OK") == 1
    assert _topic_status(storage, proposal.topic_id) == "SELECTED"
    assert storage.conn.execute(
        "SELECT count(*) FROM approvals WHERE decision='APPROVED'").fetchone()[0] == 1


def test_proposal_and_approval_survive_restart_without_auto_selection(
        settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_owner_topic_proposal(proposal.topic_id)
        assert persisted is not None
        assert persisted.operation_key == proposal.operation_key
        assert persisted.fingerprint == proposal.fingerprint
        assert persisted.proposed_by == "owner:krapcys1-maker"
        assert persisted.decision == "PENDING" and persisted.consumed_at is None
        assert persisted.topic_status is TopicStatus.SCORED     # brak auto-selekcji
        approved = reopened.approve_owner_topic_proposal(
            account_id=account.id, topic_id=proposal.topic_id, approved_by="owner-l1",
            article_min_score=settings.article_min_score,
            duplicate_threshold=settings.topic_duplicate_threshold,
            clock=FixedClock(NOW),
        )
        assert approved.topic_status is TopicStatus.SELECTED
    finally:
        reopened.close()

    final = SqliteStorage.open(settings.db_path)
    try:
        after = final.get_owner_topic_proposal(proposal.topic_id)
        assert after.decision == "APPROVED" and after.consumed_at is not None
        assert after.topic_status is TopicStatus.SELECTED
    finally:
        final.close()


def test_duplicate_created_between_proposal_and_approval_blocks_selection(
        settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    # Konkurencyjny temat o tym samym tytule pojawia się PO zgłoszeniu.
    from app.models import Topic

    storage.add_topic(account.id, Topic(
        account_id=account.id, title=TITLE, question=QUESTION, score=90.0,
        status=TopicStatus.SELECTED))

    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, proposal.topic_id)

    assert exc.value.code == "DUPLICATE_TOPIC"
    assert _topic_status(storage, proposal.topic_id) == "SCORED"


def test_used_topic_cannot_be_reselected_through_a_proposal(settings, storage, account):
    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    storage.conn.execute(
        "UPDATE topics SET status='USED' WHERE id=?", (proposal.topic_id,))
    storage.conn.commit()

    with pytest.raises(OwnerTopicProposalError) as exc:
        _approve(storage, settings, account, proposal.topic_id)

    assert exc.value.code == "TOPIC_STATUS_NOT_APPROVABLE"
    assert _topic_status(storage, proposal.topic_id) == "USED"


# --------------------------------------------------------------------------- #
# 13. Publiczny CLI (subprocess, bez prywatnych helperów)                      #
# --------------------------------------------------------------------------- #

_DRIVER = '''
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

tmp_root = Path(sys.argv[1])

from app.core.config import Settings
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage
from tests.conftest import STANDARD_WEIGHTS, make_account
import app.main as main_module

NOW = datetime.now(timezone.utc)
account = make_account(active=True)
data_dir = tmp_root / "data"
initialize_database(data_dir / "agent.db")
settings = Settings(
    project_root=tmp_root, data_dir=data_dir, db_path=data_dir / "agent.db",
    costs_csv_path=tmp_root / "COSTS.csv", dry_run=True, kill_switch=False,
    max_daily_cost_usd=2.00, max_monthly_cost_usd=40.00,
    monthly_limit_has_priority=True, model_fast="dry-run-fake",
    model_quality="dry-run-fake",
    pricing={"input_per_mtok": 1.0, "output_per_mtok": 1.0,
             "cache_read_per_mtok": 1.0, "cache_write_per_mtok": 1.0,
             "web_search_per_1k": 1.0},
    article_min_score=75.0, note_min_score=65.0,
    topic_scoring_weights=dict(STANDARD_WEIGHTS), anthropic_api_key=None,
    accounts={account.id: account},
    editorial_schedule={
        "timezone": "Europe/Bucharest",
        "windows": [{"weekdays": [0, 1, 2, 3, 4, 5, 6],
                     "start": "00:00", "end": "23:59"}],
    },
)
main_module.load_settings = lambda: settings
storage = SqliteStorage.open(settings.db_path)
storage.ensure_account(account)
storage.close()

expiry = (NOW + timedelta(hours=6)).isoformat()
propose = main_module.main([
    "propose-topic", "--account-id", account.id,
    "--title", "Why bakeries move fresh bread to the entrance in the afternoon",
    "--question", "What incentive puts fresh bread near the door late in the day?",
    "--rationale", "Owner editorial judgement for the acceptance run.",
    "--score", "curiosity=0.90", "--score", "source_quality=0.85",
    "--score", "non_obvious=0.85", "--score", "universality=0.80",
    "--score", "discussion_potential=0.80", "--score", "visual_potential=0.75",
    "--score", "originality=0.85",
    "--operation-key", "20260721-stage0-2-live-acceptance",
    "--expires-at", expiry, "--proposed-by", "owner:krapcys1-maker",
    "--owner-authored",
])
print("PROPOSE_EXIT", propose)

check = SqliteStorage.open(settings.db_path)
topic_id = check.conn.execute("SELECT id FROM topics").fetchone()[0]
print("TOPIC_ID", topic_id)
print("STATUS_BEFORE", check.conn.execute(
    "SELECT status FROM topics WHERE id=?", (topic_id,)).fetchone()[0])
check.close()

approve = main_module.main([
    "approve-topic-proposal", "--account-id", account.id,
    "--topic-id", str(topic_id), "--approved-by", "owner-l1-subprocess",
])
print("APPROVE_EXIT", approve)

# Granica z istniejącym publicznym flow: enqueue Controlled Fetch dla nowego
# tematu (zero sieci, zero pobrania — enqueue tylko zamraża intent).
fetch = main_module.main([
    "enqueue-controlled-fetch", "--account-id", account.id,
    "--topic-id", str(topic_id), "--url", "https://example.org/document",
    "--source-identity", "owner-proposal-source", "--timeout-seconds", "20",
    "--max-bytes", "1000000", "--max-redirects", "3",
    "--expires-at", (NOW + timedelta(hours=6)).isoformat(),
])
print("FETCH_ENQUEUE_EXIT", fetch)

final = SqliteStorage.open(settings.db_path)
print("STATUS_AFTER", final.conn.execute(
    "SELECT status FROM topics WHERE id=?", (topic_id,)).fetchone()[0])
print("DECISION", final.conn.execute(
    "SELECT decision FROM approvals WHERE object_id=?", (topic_id,)).fetchone()[0])
print("USAGE", final.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0])
print("ATTEMPTS", final.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0])
print("FETCH_JOBS", final.conn.execute(
    "SELECT count(*) FROM jobs WHERE topic_id=? AND status='QUEUED'", (topic_id,)).fetchone()[0])
final.close()
'''


def _base_env():
    import os
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    return {
        "NIA_TEST_MODE": "1",
        "NIA_TEST_PROTECTED_DB": str(root / "data" / "agent.db"),
        "PATH": os.environ.get("PATH", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", os.environ.get("SystemRoot", "")),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(root),
    }


def test_public_cli_subprocess_runs_proposal_then_approval(tmp_path):
    """Pełny publiczny flow w OSOBNYM procesie, bez prywatnych helperów."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    driver = tmp_path / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(driver), str(tmp_path)],
        cwd=root, capture_output=True, text=True, env=_base_env(), check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    out = dict(
        line.split(" ", 1) for line in result.stdout.splitlines()
        if line.split(" ", 1)[0] in {
            "PROPOSE_EXIT", "TOPIC_ID", "STATUS_BEFORE", "APPROVE_EXIT",
            "FETCH_ENQUEUE_EXIT", "STATUS_AFTER", "DECISION", "USAGE",
            "ATTEMPTS", "FETCH_JOBS",
        }
    )
    assert out["PROPOSE_EXIT"] == "0" and out["APPROVE_EXIT"] == "0"
    assert out["STATUS_BEFORE"] == "SCORED"      # brak automatycznej selekcji
    assert out["STATUS_AFTER"] == "SELECTED"     # dopiero po zgodzie L1
    assert out["DECISION"] == "APPROVED"
    assert out["USAGE"] == "0" and out["ATTEMPTS"] == "0"
    # istniejący publiczny enqueue Controlled Fetch przyjmuje nowy temat
    assert out["FETCH_ENQUEUE_EXIT"] == "0" and out["FETCH_JOBS"] == "1"
    assert "Traceback" not in result.stderr


# --------------------------------------------------------------------------- #
# 14. Regresja: run-topics pozostaje offline-only                              #
# --------------------------------------------------------------------------- #

def test_run_topics_stays_offline_only(settings, storage, account):
    from app.orchestrator.runner import run_topics
    from app.main import _cmd_run_topics
    import argparse

    assert _cmd_run_topics(argparse.Namespace(real=True, count=6, account=account.id)) == 2
    with pytest.raises(RuntimeError):
        run_topics(count=1, account_id=account.id, force_real=True, settings=settings)


def test_owner_proposal_does_not_change_fake_fixture_behaviour(settings, storage, account):
    from app.llm.fake_client import FakeLLMClient

    result = FakeLLMClient().generate_and_score_topics(account, 6)
    assert [idea.title for idea in result.ideas][0] == \
        "Why airline ticket prices change every few hours"
    assert len(result.ideas) == 6


# --------------------------------------------------------------------------- #
# Kompatybilność granicy z późniejszym Fetch/evidence research (offline)       #
# --------------------------------------------------------------------------- #

def test_selected_owner_topic_is_accepted_by_existing_research_and_fetch_gates(
        settings, storage, account):
    """Po zgodzie temat jest legalnym wejściem istniejących publicznych flow.

    Nie wykonujemy Fetchu ani researchu — potwierdzamy wyłącznie, że granice
    tych flow przyjmują nowy temat (bramka researchu i enqueue controlled fetch).
    """
    from app.research.controlled_fetch_intent import (
        SUPPORTED_FETCH_CONTENT_TYPES,
        ControlledFetchIntent,
    )
    from app.workflows.research.pipeline import ensure_topic_can_start_research

    storage.ensure_account(account)
    proposal = _propose(storage, settings, account)
    _approve(storage, settings, account, proposal.topic_id)

    topic = next(t for t in storage.list_topics(account.id) if t.id == proposal.topic_id)
    assert topic.status is TopicStatus.SELECTED
    # bramka świeżego researchu przyjmuje temat bez --force-re-research
    ensure_topic_can_start_research(storage, account, topic, False)
    # zamrożony intent controlled fetch da się zbudować dla tego tematu
    intent = ControlledFetchIntent.build(
        account_id=account.id, topic_id=int(topic.id),
        source_identity="owner-proposal-source",
        requested_url="https://example.org/document",
        timeout_seconds=20, max_bytes=1000000, max_redirects=3,
        allowed_content_types=list(SUPPORTED_FETCH_CONTENT_TYPES),
        requested_at=NOW, expires_at=NOW + timedelta(hours=6),
    )
    assert intent.topic_id == int(topic.id)
    assert storage.list_topics_by_status(account.id, TopicStatus.SELECTED)[0].id == topic.id
