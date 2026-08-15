"""Counter-tests for the two P1 findings from the independent review.

P1-1  The REVIEW-ONLY initial path read entry outcomes directly, so a PASS
      entry classified ARGUMENT_OR_INFERENCE or NON_FACTUAL_PROSE while also
      declaring contains_external_fact=true reached APPROVE and PENDING_APPROVAL,
      even though the shared quality gate rejects exactly that contradiction.

P1-2  The 0041 trigger counted six checks and tested value!=1, so six arbitrary
      names satisfied it and a literal integer 1 passed as if it were JSON true.

These tests drive the real flow — parser, REVIEW-ONLY initial review, review
after rewrite, the shared content quality gate, durable storage, v3 resume and
the PENDING_APPROVAL predicate.  Offline only: no provider, no network, and
every write goes to a fresh temporary database.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.content.contracts import FakeDraft
from app.content.quality_gate import (
    CLASSIFICATION_CONTRACT_VIOLATION,
    ClaimClassification,
    ClaimReviewOutcome,
    DocumentCheck,
    build_claim_segments,
    classification_contract_error,
)
from app.content.reviewer import (
    REVIEWER_VERSION,
    ProductionReviewerError,
    parse_reviewer_response,
)

CANONICAL_CHECKS = tuple(check.value for check in DocumentCheck)
CONTRADICTORY = ("ARGUMENT_OR_INFERENCE", "NON_FACTUAL_PROSE")


def _draft(*, title="What the on-time metric misses", body="A sentence.") -> FakeDraft:
    return FakeDraft(
        attempt_no=1, route_key="article:opus", title=title, body=body,
        evidence_ids_used=(), unsupported_claims=(), personal_experience=False,
        style_ok=True, brief_compliant=True,
    )


def _payload(segments, *, classification, external, evidence_ids=(), outcome="PASS"):
    return json.dumps({
        "reviewer_version": REVIEWER_VERSION,
        "entries": [
            {
                "segment_id": segment.segment_id,
                "segment_fingerprint": segment.fingerprint,
                "classification": classification,
                "evidence_ids": list(evidence_ids),
                "reason": "reviewer justification",
                "outcome": outcome,
                "contains_external_fact": external,
            }
            for segment in segments
        ],
        "document_review": {
            "checks": {name: True for name in CANONICAL_CHECKS},
            "findings": [],
        },
    })


# --- P1-1: counter-tests 1 and 2 -------------------------------------------

@pytest.mark.parametrize("classification", CONTRADICTORY)
def test_p1_1_contradictory_entry_is_refused_at_the_parser(classification):
    """The exact accepted shape: PASS, evidence_ids=[], contains_external_fact=true."""
    segments = build_claim_segments(_draft())
    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(
            _payload(segments, classification=classification, external=True),
            segments=segments,
        )
    assert exc.value.code == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"
    assert "contains_external_fact=false" in exc.value.detail


@pytest.mark.parametrize("classification", CONTRADICTORY)
def test_p1_1_canonical_invariant_is_one_definition(classification):
    """Parser and quality gate consult the same predicate, not two copies."""
    error = classification_contract_error(
        classification=ClaimClassification(classification),
        evidence_ids=(),
        contains_external_fact=True,
    )
    assert error is not None
    assert classification_contract_error(
        classification=ClaimClassification(classification),
        evidence_ids=(),
        contains_external_fact=False,
    ) is None
    # A grounded fact keeps its external fact and its citation.
    assert classification_contract_error(
        classification=ClaimClassification.EVIDENCE_GROUNDED_FACT,
        evidence_ids=("e1",),
        contains_external_fact=True,
    ) is None


@pytest.mark.parametrize("classification", CONTRADICTORY)
def test_p1_1_review_only_initial_cannot_approve_the_contradiction(
    classification, storage, settings, account,
):
    """The full REVIEW-ONLY flow: no APPROVE, no PENDING_APPROVAL, one rewrite."""
    from dataclasses import replace

    from app.content.review_only import run_controlled_article_review_only
    from app.core.clock import FixedClock
    from app.llm.anthropic_controlled_adapter import (
        ControlledAdapterError,
        ControlledProviderRawResponse,
    )
    from tests.test_pr46_review_only_resume import (
        NOW, ROOT, _authority, _failed_article, _sdk_factory,
    )

    class _ContradictoryReviewer:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, _client, request):
            self.calls += 1
            supplied = json.loads(request.user_prompt)["draft_segments"]
            segments = [
                type("S", (), {"segment_id": s["segment_id"],
                               "fingerprint": s["fingerprint"]})()
                for s in supplied
            ]
            return ControlledProviderRawResponse(
                returned_model_id="claude-opus-5",
                text=_payload(segments, classification=classification, external=True),
                input_tokens=900, output_tokens=400, cache_read_tokens=0,
                cache_write_tokens=0, web_search_requests=0, stop_reason="end_turn",
                provider_request_id=f"fake-contradictory-{self.calls}",
            )

    state = _failed_article(
        storage, settings, account, job=f"p1-1-{classification.lower()}",
    )
    authority = _authority(state, suffix=f"p1-1-{classification.lower()}")
    reviewer = _ContradictoryReviewer()

    with pytest.raises((ProductionReviewerError, ControlledAdapterError)) as exc:
        run_controlled_article_review_only(
            settings=replace(settings, project_root=ROOT), authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=reviewer,
            writer_sdk_factory=_sdk_factory, writer_caller=reviewer,
            post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=reviewer,
            clock=FixedClock(NOW),
        )
    assert getattr(exc.value, "code", "") == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"

    # Nothing became an approval, and the content never reached the queue.
    row = storage.conn.execute(
        "SELECT outcome,failure_kind,result_json FROM content_review_resume_executions "
        "WHERE content_id=?", (authority.content_id,),
    ).fetchone()
    assert row is not None and row["outcome"] == "FAILURE"
    assert row["failure_kind"] == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"
    assert json.loads(str(row["result_json"])).get("decision") is None
    status = storage.conn.execute(
        "SELECT status FROM content_items WHERE id=?", (authority.content_id,),
    ).fetchone()[0]
    assert status != "PENDING_APPROVAL"


@pytest.mark.parametrize("classification", CONTRADICTORY)
def test_p1_1_shared_quality_gate_also_blocks_the_contradiction(classification):
    """Review after rewrite and the ordinary content flow use this gate."""
    from app.content.quality_gate import ClaimAccountingEntry, assess_draft
    from tests.test_prec5_question_semantic_boundary import _brief, _evidence

    draft = _draft()
    segments = build_claim_segments(draft)

    class _ContradictoryPort:
        reviewer_version = "fake_contradictory_v1"

        def review(self, *, draft, brief, evidence, segments):
            del draft, brief, evidence
            return tuple(
                ClaimAccountingEntry(
                    segment_id=segment.segment_id,
                    segment_fingerprint=segment.fingerprint,
                    classification=ClaimClassification(classification),
                    evidence_ids=(),
                    reason="contradictory entry",
                    outcome=ClaimReviewOutcome.PASS,
                    contains_external_fact=True,
                )
                for segment in segments
            )

    verdict = assess_draft(
        draft, _brief(), evidence=(_evidence(),), claim_reviewer=_ContradictoryPort(),
    )
    codes = {item.get("code") for item in verdict.findings}
    assert codes & {
        "INFERENCE_CONTAINS_EXTERNAL_FACT",
        "NON_FACTUAL_CLASSIFICATION_INCONSISTENT",
        CLASSIFICATION_CONTRACT_VIOLATION,
    }
    assert all(
        item["reviewer_outcome"] == "BLOCK" for item in verdict.claim_accounting
    )


# --- counter-test 3: a correct response still passes ------------------------

def test_correct_response_still_passes_every_layer():
    segments = build_claim_segments(
        _draft(body="The report covers timepoints only. So the gap is invisible."),
    )
    entries = [
        {
            "segment_id": segments[0].segment_id,
            "segment_fingerprint": segments[0].fingerprint,
            "classification": "ARGUMENT_OR_INFERENCE", "evidence_ids": [],
            "reason": "title names the article's subject",
            "outcome": "PASS", "contains_external_fact": False,
        },
        {
            "segment_id": segments[1].segment_id,
            "segment_fingerprint": segments[1].fingerprint,
            "classification": "EVIDENCE_GROUNDED_FACT", "evidence_ids": ["e1"],
            "reason": "measurement basis is in evidence",
            "outcome": "PASS", "contains_external_fact": True,
        },
        {
            "segment_id": segments[2].segment_id,
            "segment_fingerprint": segments[2].fingerprint,
            "classification": "ARGUMENT_OR_INFERENCE", "evidence_ids": [],
            "reason": "conclusion follows from the grounded fact",
            "outcome": "PASS", "contains_external_fact": False,
        },
    ]
    parsed, review = parse_reviewer_response(
        json.dumps({
            "reviewer_version": REVIEWER_VERSION, "entries": entries,
            "document_review": {
                "checks": {name: True for name in CANONICAL_CHECKS}, "findings": [],
            },
        }),
        segments=segments, allowed_evidence_ids=frozenset({"e1"}),
    )
    assert len(parsed) == 3
    assert review.approved is True
    assert all(
        classification_contract_error(
            classification=entry.classification,
            evidence_ids=entry.evidence_ids,
            contains_external_fact=entry.contains_external_fact,
        ) is None
        for entry in parsed
    )


def test_unsupported_factual_claim_stays_expressible_as_a_block():
    """Closing P1-1 must not remove the reviewer's way to report a bad fact.

    An uncited EVIDENCE_GROUNDED_FACT is the encoding for "this asserts a fact
    nothing supports".  It is legal as a BLOCK and illegal as a PASS, so the
    reviewer can still flag it without resorting to a contradictory class.
    """
    segments = build_claim_segments(_draft())
    blocked = _payload(
        segments, classification="EVIDENCE_GROUNDED_FACT", external=True,
        outcome="BLOCK",
    )
    entries, _ = parse_reviewer_response(blocked, segments=segments)
    assert all(entry.outcome is ClaimReviewOutcome.BLOCK for entry in entries)
    assert all(entry.evidence_ids == () for entry in entries)

    with pytest.raises(ProductionReviewerError) as exc:
        parse_reviewer_response(
            _payload(
                segments, classification="EVIDENCE_GROUNDED_FACT", external=True,
                outcome="PASS",
            ),
            segments=segments,
        )
    assert exc.value.code == "REVIEWER_ENTRY_EVIDENCE_CONTRACT"
    assert "cannot PASS" in exc.value.detail


# --- P1-2: counter-tests 4, 5, 6 against the real applied trigger -----------

def _database_at_0041(tmp_path):
    from app.storage.db import (
        CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION,
        initialize_database,
        migrate_0040_to_0041,
    )

    path = tmp_path / "gate.db"
    initialize_database(path, through=CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION)
    migrate_0040_to_0041(path)
    return path


def _gate_predicate(path):
    """The document-review clause exactly as the applied trigger carries it."""
    conn = sqlite3.connect(path)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' "
        "AND name='content_c2_pending_approval_contract'"
    ).fetchone()[0]
    conn.close()
    clause = [
        line.strip() for line in sql.splitlines()
        if "document_review" in line or "c.type='true'" in line
        or "'TITLE_REFLECTS_BODY'" in line or "'THESIS_CONSISTENT'" in line
    ]
    return sql, "\n".join(clause)


def _evaluate(document_review) -> bool:
    condition = (
        "json_type(?1,'$.document_review')='object' "
        " AND json_type(?1,'$.document_review.approved')='true' "
        " AND json_type(?1,'$.document_review.checks')='object' "
        " AND (SELECT count(*) FROM json_each("
        "      json_extract(?1,'$.document_review.checks')))=6 "
        " AND (SELECT count(*) FROM json_each("
        "      json_extract(?1,'$.document_review.checks')) c "
        "      WHERE c.type='true' AND c.key IN ("
        "        'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',"
        "        'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',"
        "        'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE'))=6 "
        " AND json_type(?1,'$.document_review.failed_checks')='array' "
        " AND json_type(?1,'$.document_review.findings')='array' "
        " AND json_array_length(json_extract(?1,'$.document_review.failed_checks'))=0 "
        " AND json_array_length(json_extract(?1,'$.document_review.findings'))=0"
    )
    conn = sqlite3.connect(":memory:")
    try:
        return bool(conn.execute(
            f"SELECT ({condition})",
            (json.dumps({"document_review": document_review}),),
        ).fetchone()[0])
    finally:
        conn.close()


def _document(checks=None, *, approved=True, failed=None, findings=None):
    return {
        "approved": approved,
        "checks": {name: True for name in CANONICAL_CHECKS} if checks is None else checks,
        "failed_checks": [] if failed is None else failed,
        "findings": [] if findings is None else findings,
    }


def test_p1_2_trigger_pins_the_exact_canonical_check_names(tmp_path):
    path = _database_at_0041(tmp_path)
    sql, clause = _gate_predicate(path)
    for name in CANONICAL_CHECKS:
        assert f"'{name}'" in sql, name
    assert "c.type='true'" in sql

    assert _evaluate(_document()) is True
    assert _evaluate(_document({f"BOGUS_{i}": True for i in range(6)})) is False
    assert _evaluate(_document({
        **{name: True for name in CANONICAL_CHECKS[:5]}, "NOT_A_CHECK": True,
    })) is False
    assert _evaluate(_document({name: True for name in CANONICAL_CHECKS[:5]})) is False


@pytest.mark.parametrize("value", [1, 1.0, "true", "1", [True], {"v": True}])
def test_p1_2_trigger_requires_json_true_not_a_truthy_value(value):
    assert _evaluate(_document({name: value for name in CANONICAL_CHECKS})) is False


@pytest.mark.parametrize("approved", [1, "true", 1.0])
def test_p1_2_trigger_requires_json_true_for_approved(approved):
    assert _evaluate(_document(approved=approved)) is False


def test_p1_2_trigger_accepts_only_the_canonical_v3_document():
    assert _evaluate(_document()) is True
    assert _evaluate(_document(failed=["TITLE_REFLECTS_BODY"])) is False
    assert _evaluate(_document(findings=["rewrite the title"])) is False
    assert _evaluate(_document(approved=False)) is False
    assert _evaluate(_document({
        **{name: True for name in CANONICAL_CHECKS},
        CANONICAL_CHECKS[0]: False,
    })) is False


# --- counter-test 7: rollback leaves 0040 and the previous trigger ----------

def test_p1_2_failed_0041_rolls_back_to_untouched_0040(tmp_path):
    """A forced failure inside the 0041 transaction leaves 0040 exactly as it was.

    0041 is a runner-transactional migration, so the runner owns BEGIN and the
    failpoint fires after the schema SQL but before the ledger row and COMMIT.
    """
    import app.storage.db as db

    target = tmp_path / "rollback.db"
    db.initialize_database(
        target, through=db.CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION,
    )
    before = sqlite3.connect(target)
    old_trigger = before.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' "
        "AND name='content_c2_pending_approval_contract'"
    ).fetchone()[0]
    before_versions = [
        row[0] for row in before.execute(
            "SELECT version FROM schema_migrations ORDER BY version")
    ]
    before_objects = before.execute(
        "SELECT count(*) FROM sqlite_master").fetchone()[0]
    before.close()
    assert "document_review" not in old_trigger
    assert before_versions[-1] == db.CONTENT_ROLE_RECONCILIATION_SCHEMA_VERSION

    def boom(step: str) -> None:
        if step == db.REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION:
            raise RuntimeError("forced failure inside the 0041 transaction")

    conn = db.connect(target)
    try:
        # The failpoint is a SQLite user-defined function, so the raise surfaces
        # wrapped; what matters is that the whole step is rolled back.
        with pytest.raises(sqlite3.Error):
            db.apply_migrations(conn, transaction_failpoint=boom)
        assert not conn.in_transaction
    finally:
        conn.close()

    after = sqlite3.connect(target)
    try:
        assert [
            row[0] for row in after.execute(
                "SELECT version FROM schema_migrations ORDER BY version")
        ] == before_versions
        assert after.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='content_c2_pending_approval_contract'"
        ).fetchone()[0] == old_trigger
        assert after.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == (
            before_objects
        )
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        after.close()

    # The same database still migrates cleanly once the failure is removed.
    result = db.migrate_0040_to_0041(target)
    assert result.applied_migrations == (db.REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION,)
    assert db.database_schema_versions(target)[-1] == (
        db.REVIEWER_DOCUMENT_GATE_SCHEMA_VERSION
    )
