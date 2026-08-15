"""The canonical v3 entry contract at its two PERSISTENT boundaries.

The earlier fix lived only in application layers.  The public
``settle_content_review_resume_execution`` wrote its ``result_payload``
verbatim and the PENDING_APPROVAL trigger inspected only ``outcome='PASS'``,
so a caller that skipped the parser could store ``decision=APPROVE`` over
entries classified ARGUMENT_OR_INFERENCE with ``contains_external_fact=true``.

Every test here drives the REAL public settlement API against the REAL applied
0041 triggers.  Nothing copies the SQL predicate and nothing calls the helper
directly.  Offline: no provider, no network, temporary databases only.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from app.content.foundation import ContentStatus, canonical_json, sha256_text
from app.content.provider_roles import (
    RoleProviderExecution,
    RoleUsage,
)
from app.content.reviewer import ProductionArticleReviewer
from app.content.review_only import run_controlled_article_review_only
from app.core.clock import FixedClock
from app.models import JobExecutionContext, JobKind, WorkflowType
from app.model_routing.contracts import LogicalModelRole
from app.ports.storage import ContentFoundationError
from tests.test_pr46_review_only_resume import (
    NOW, ROOT, _BlockingReviewerTransport, _authority, _failed_article,
    _sdk_factory,
)
from tests.test_b3_production_reviewer import ReviewerTransport, WriterTransport, _run

CANON = (
    "TITLE_REFLECTS_BODY", "TITLE_PROMISE_FULFILLED", "TITLE_MECHANISM_EXPLAINED",
    "BRIEF_QUESTION_ANSWERED", "THESIS_CONSISTENT", "CONCLUSIONS_WITHIN_EVIDENCE",
)
V3 = "production_article_reviewer_opus_v3"


def _document(approved=True):
    return {
        "approved": approved,
        "checks": {name: True for name in CANON},
        "failed_checks": [], "findings": [],
    }


def _usage():
    return SimpleNamespace(
        input_tokens=900, output_tokens=400, cache_read_tokens=0,
        cache_write_tokens=0, web_search_requests=0,
    )


def _settle_directly(storage, settings, account, *, job, entry_factory,
                     reviewer_version=V3, decision="APPROVE", document=None,
                     direct_sql=False):
    """Run the real chain to IN_FLIGHT, then hit the PUBLIC settlement API.

    Returns ``(refusal, stored_row, content_status)``.  ``refusal`` is None when
    the persistent boundary accepted the payload.
    """
    state = _failed_article(storage, settings, account, job=job)
    authority = _authority(state, suffix=job)
    captured: dict[str, object] = {"refusal": None}

    def hijack(_client, request):
        supplied = json.loads(request.user_prompt)["draft_segments"]
        reserved = storage.get_content_review_resume_execution(
            execution_ref=authority.initial_review_execution_ref,
        )
        assert reserved is not None
        payload = {
            "reviewer_version": reviewer_version,
            "decision": decision,
            "request_intent_fingerprint": reserved["request_intent_fingerprint"],
            "draft_fingerprint": authority.draft_fingerprint,
            "review_no": 1,
            "entries": [entry_factory(index, seg)
                        for index, seg in enumerate(supplied)],
            "document_review": _document() if document is None else document,
        }
        try:
            if direct_sql:
                result_json = canonical_json(payload)
                storage.conn.execute(
                    "UPDATE content_review_resume_executions SET outcome='SUCCESS',"
                    "returned_model_id='claude-opus-5',result_json=?,"
                    "result_fingerprint=?,settled_at=? WHERE execution_ref=?",
                    (result_json, sha256_text(result_json), NOW.isoformat(),
                     authority.initial_review_execution_ref),
                )
                storage.conn.commit()
            else:
                storage.settle_content_review_resume_execution(
                    execution_ref=authority.initial_review_execution_ref,
                    outcome="SUCCESS", failure_kind=None,
                    returned_model_id="claude-opus-5",
                    usage=_usage(), cost_usd=Decimal("0.010000"),
                    result_payload=payload, now=NOW,
                )
        except Exception as exc:  # noqa: BLE001 - the boundary's own refusal
            if direct_sql and storage.conn.in_transaction:
                storage.conn.rollback()
            captured["refusal"] = f"{type(exc).__name__}: {exc}"
        raise RuntimeError("probe stops the chain after settlement")

    with pytest.raises(Exception):
        run_controlled_article_review_only(
            settings=replace(settings, project_root=ROOT), authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=hijack,
            writer_sdk_factory=_sdk_factory, writer_caller=hijack,
            post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=hijack,
            clock=FixedClock(NOW),
        )
    row = storage.conn.execute(
        "SELECT outcome,result_json FROM content_review_resume_executions "
        "WHERE execution_ref=?", (authority.initial_review_execution_ref,),
    ).fetchone()
    status = storage.conn.execute(
        "SELECT status FROM content_items WHERE id=?", (authority.content_id,),
    ).fetchone()[0]
    return captured["refusal"], row, status


def _entry(seg, *, classification="ARGUMENT_OR_INFERENCE", evidence_ids=(),
           outcome="PASS", external=False, drop=None, reason="r"):
    item = {
        "segment_id": seg["segment_id"],
        "segment_fingerprint": seg["fingerprint"],
        "classification": classification,
        "evidence_ids": list(evidence_ids) if isinstance(evidence_ids, (list, tuple))
        else evidence_ids,
        "reason": reason,
        "outcome": outcome,
        "contains_external_fact": external,
    }
    if drop is not None:
        item.pop(drop, None)
    return item


def _assert_refused(refusal, row, status):
    """No stored APPROVE, no PENDING_APPROVAL, no partial write."""
    assert refusal is not None, "the persistent boundary accepted the payload"
    assert (
        "review execution admits one effect stamp and settlement" in refusal
        or "CONTENT_REVIEW_RESULT_CONTRACT_INVALID" in refusal
        or "CONTENT_REVIEW_RESULT_IDENTITY_MISMATCH" in refusal
    )
    if row is not None and row["result_json"]:
        assert json.loads(str(row["result_json"])).get("decision") != "APPROVE"
    assert row is None or row["outcome"] != "SUCCESS"
    assert status != "PENDING_APPROVAL"


# --- counter-tests 1, 2, 3: the contradictions ------------------------------

def test_1_inference_with_external_true_is_refused_by_the_settlement_boundary(
    storage, settings, account,
):
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-inference-external",
        entry_factory=lambda i, s: _entry(
            s, classification="ARGUMENT_OR_INFERENCE", external=True),
    )
    _assert_refused(refusal, row, status)


def test_2_prose_with_external_true_is_refused_by_the_settlement_boundary(
    storage, settings, account,
):
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-prose-external",
        entry_factory=lambda i, s: _entry(
            s, classification="NON_FACTUAL_PROSE", external=True),
    )
    _assert_refused(refusal, row, status)


def test_3_grounded_fact_passing_without_evidence_is_refused(
    storage, settings, account,
):
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-grounded-nocite",
        entry_factory=lambda i, s: _entry(
            s, classification="EVIDENCE_GROUNDED_FACT", evidence_ids=(),
            outcome="PASS", external=True),
    )
    _assert_refused(refusal, row, status)


# --- counter-test 4: a legal BLOCK, but never an approval -------------------

def test_4_grounded_fact_blocked_without_evidence_is_storable_but_not_approved(
    storage, settings, account,
):
    """The reviewer must keep its way to report an unsupported factual claim.

    A BLOCK entry means the article needs a rewrite, so the honest decision is
    REWRITE_ONCE.  The result is storable; it simply never becomes an approval.
    """
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-grounded-block",
        decision="REWRITE_ONCE",
        entry_factory=lambda i, s: _entry(
            s, classification="EVIDENCE_GROUNDED_FACT", evidence_ids=(),
            outcome="BLOCK", external=True),
    )
    assert refusal is None, f"a BLOCKed unsupported fact must remain storable: {refusal}"
    assert row["outcome"] == "SUCCESS"
    assert json.loads(str(row["result_json"]))["decision"] == "REWRITE_ONCE"
    assert status != "PENDING_APPROVAL"


def test_4b_a_block_entry_can_never_be_stored_as_an_approval(
    storage, settings, account,
):
    """decision=APPROVE over a BLOCK entry is itself a contradiction."""
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-block-as-approve",
        decision="APPROVE",
        entry_factory=lambda i, s: _entry(
            s, classification="EVIDENCE_GROUNDED_FACT", evidence_ids=(),
            outcome="BLOCK", external=True),
    )
    _assert_refused(refusal, row, status)


# --- counter-tests 5, 6: correct payloads still pass ------------------------

def test_5_and_6_correct_entries_are_accepted_by_the_settlement_boundary(
    storage, settings, account,
):
    def mixed(index, seg):
        if index == 0:
            return _entry(seg, classification="EVIDENCE_GROUNDED_FACT",
                          evidence_ids=["research-card:1:confirmed-claim:0"],
                          outcome="PASS", external=True)
        if index % 2:
            return _entry(seg, classification="ARGUMENT_OR_INFERENCE", external=False)
        return _entry(seg, classification="NON_FACTUAL_PROSE", external=False)

    refusal, row, _ = _settle_directly(
        storage, settings, account, job="dc-correct", entry_factory=mixed,
    )
    assert refusal is None, f"a correct v3 payload must not be blocked: {refusal}"
    assert row["outcome"] == "SUCCESS"
    stored = json.loads(str(row["result_json"]))
    assert stored["decision"] == "APPROVE"


# --- counter-test 7: contains_external_fact typing --------------------------

@pytest.mark.parametrize("bad", [0, 1, "false", "true", None, [False], {"v": False}])
def test_7_contains_external_fact_must_be_a_json_boolean(
    bad, storage, settings, account,
):
    refusal, row, status = _settle_directly(
        storage, settings, account, job=f"dc-ext-{abs(hash(repr(bad))) % 10000}",
        entry_factory=lambda i, s: _entry(
            s, classification="ARGUMENT_OR_INFERENCE", external=bad),
    )
    _assert_refused(refusal, row, status)


# --- counter-test 8: evidence_ids typing and class agreement ----------------

@pytest.mark.parametrize(("classification", "evidence_ids"), [
    ("ARGUMENT_OR_INFERENCE", None),
    ("ARGUMENT_OR_INFERENCE", "e1"),
    ("ARGUMENT_OR_INFERENCE", {"id": "e1"}),
    ("ARGUMENT_OR_INFERENCE", ["e1"]),
    ("NON_FACTUAL_PROSE", ["e1"]),
    ("EVIDENCE_GROUNDED_FACT", None),
    ("EVIDENCE_GROUNDED_FACT", "e1"),
])
def test_8_evidence_ids_must_be_an_array_matching_the_class(
    classification, evidence_ids, storage, settings, account,
):
    tag = abs(hash((classification, repr(evidence_ids)))) % 100000
    refusal, row, status = _settle_directly(
        storage, settings, account, job=f"dc-ev-{tag}",
        entry_factory=lambda i, s: _entry(
            s, classification=classification, evidence_ids=evidence_ids,
            external=classification == "EVIDENCE_GROUNDED_FACT"),
    )
    _assert_refused(refusal, row, status)


# --- counter-test 9: unknown class, missing field, bad outcome, bad version --

def test_9a_unknown_classification_is_refused(storage, settings, account):
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-unknown-class",
        entry_factory=lambda i, s: _entry(s, classification="TOTALLY_NEW_CLASS"),
    )
    _assert_refused(refusal, row, status)


@pytest.mark.parametrize("missing", [
    "classification", "outcome", "evidence_ids", "contains_external_fact",
])
def test_9b_missing_field_fails_closed(missing, storage, settings, account):
    refusal, row, status = _settle_directly(
        storage, settings, account, job=f"dc-missing-{missing}",
        entry_factory=lambda i, s: _entry(s, drop=missing),
    )
    _assert_refused(refusal, row, status)


def test_9c_unknown_outcome_is_refused(storage, settings, account):
    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-unknown-outcome",
        entry_factory=lambda i, s: _entry(s, outcome="MAYBE"),
    )
    _assert_refused(refusal, row, status)


@pytest.mark.parametrize("version", [
    "production_article_reviewer_opus_v2", "v3", "", "PRODUCTION_ARTICLE_REVIEWER_OPUS_V3",
])
def test_9d_reviewer_version_must_be_exactly_v3(version, storage, settings, account):
    refusal, row, status = _settle_directly(
        storage, settings, account,
        job=f"dc-ver-{abs(hash(version)) % 10000}",
        entry_factory=lambda i, s: _entry(s), reviewer_version=version,
    )
    _assert_refused(refusal, row, status)


# --- counter-tests 10 and 11: mixed payload, atomic refusal -----------------

def test_10_and_11_one_bad_entry_rejects_the_whole_settlement_atomically(
    storage, settings, account,
):
    def mostly_good(index, seg):
        if index == 2:
            return _entry(seg, classification="NON_FACTUAL_PROSE", external=True)
        return _entry(seg, classification="ARGUMENT_OR_INFERENCE", external=False)

    refusal, row, status = _settle_directly(
        storage, settings, account, job="dc-mixed", entry_factory=mostly_good,
    )
    _assert_refused(refusal, row, status)
    # Nothing partial survived: no settled row, no usage, no cost, no payload.
    assert row is None or (
        row["outcome"] != "SUCCESS"
        and json.loads(str(row["result_json"] or "{}")).get("decision") != "APPROVE"
    )
    settled = storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_executions "
        "WHERE outcome='SUCCESS' AND json_extract(result_json,'$.decision')='APPROVE'",
    ).fetchone()[0]
    assert settled == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM content_items WHERE status='PENDING_APPROVAL'",
    ).fetchone()[0] == 0


@pytest.mark.parametrize("document", [None, {**_document(), "extra": "no"}])
def test_11b_raw_sql_cannot_bypass_the_resume_settlement_trigger(
    document, storage, settings, account,
):
    """The SQLite floor is effective even when the public Python API is skipped."""
    refusal, row, status = _settle_directly(
        storage, settings, account,
        job=f"dc-raw-resume-{'entry' if document is None else 'document'}",
        entry_factory=lambda i, s: _entry(
            s, classification="ARGUMENT_OR_INFERENCE", external=True,
        ),
        document=document,
        direct_sql=True,
    )
    _assert_refused(refusal, row, status)


# --- counter-test 12: the complete correct chain reaches PENDING_APPROVAL ---

def test_12_valid_v3_chain_reaches_pending_approval(storage, settings, account):
    """End to end through the parser, real settlement and real triggers."""
    from tests.test_b3_production_reviewer import ReviewerTransport

    state = _failed_article(storage, settings, account, job="dc-happy")
    authority = _authority(state, suffix="dc-happy")
    reviewer = ReviewerTransport()
    result = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=reviewer,
        clock=FixedClock(NOW),
    )
    assert result.final_status.value == "PENDING_APPROVAL"
    row = storage.conn.execute(
        "SELECT outcome,result_json FROM content_review_resume_executions "
        "WHERE execution_ref=?", (authority.initial_review_execution_ref,),
    ).fetchone()
    assert row["outcome"] == "SUCCESS"
    stored = json.loads(str(row["result_json"]))
    assert stored["decision"] == "APPROVE"
    assert stored["reviewer_version"] == V3
    assert stored["document_review"]["approved"] is True


# --- counter-test 14: resume and the ordinary flow keep the semantics -------

def test_14_resume_of_a_stored_valid_result_is_unchanged(storage, settings, account):
    from tests.test_b3_production_reviewer import ReviewerTransport

    state = _failed_article(storage, settings, account, job="dc-resume")
    authority = _authority(state, suffix="dc-resume")
    first = ReviewerTransport()
    run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=first,
        clock=FixedClock(NOW),
    )
    assert first.calls == 1
    second = ReviewerTransport()
    again = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory, initial_reviewer_caller=second,
        clock=FixedClock(NOW),
    )
    assert second.calls == 0, "resume must not re-run a settled review"
    assert again.final_status.value == "PENDING_APPROVAL"


@pytest.mark.parametrize(("direct_sql", "disguised_role"), [
    (False, False),
    (True, False),
    (False, True),
])
def test_15_ordinary_role_settlement_rejects_a_contradictory_reviewer_success(
    direct_sql, disguised_role, storage, settings, account,
):
    """The non-REVIEW-ONLY public settlement carries the same durable floor."""
    mode = "raw" if direct_sql else "disguised" if disguised_role else "public"
    job = f"b3-{mode}-role-settlement"
    captured: dict[str, object] = {"refusal": None}

    def hijack(_client, request):
        try:
            supplied = json.loads(request.user_prompt)["draft_segments"]
            reviewer = ProductionArticleReviewer(
                storage=storage,
                job_id=job,
                api_key_provider=lambda: "fake-never-sent",
                sdk_factory=_sdk_factory,
                caller=None,
                daily_limit_usd=settings.max_daily_cost_usd,
                monthly_limit_usd=settings.max_monthly_cost_usd,
                clock=FixedClock(NOW),
            )
            authority, _ = reviewer._authority()
            content = storage.get_content_row_for_job(job_id=job)
            usage = RoleUsage(input_tokens=900, output_tokens=400)
            payload = {
                "reviewer_version": V3,
                "decision": "APPROVE",
                "entries": [
                    {
                        "segment_id": segment["segment_id"],
                        "segment_fingerprint": segment["fingerprint"],
                        "classification": "ARGUMENT_OR_INFERENCE",
                        "evidence_ids": [],
                        "reason": "r",
                        "outcome": "PASS",
                        "contains_external_fact": True,
                    }
                    for segment in supplied
                ],
                "document_review": _document(),
            }
            execution = RoleProviderExecution(
                    execution_ref=f"{job}:ARTICLE_REVIEWER:1",
                    job_id=job,
                    run_id=str(content["run_id"]),
                    content_id=int(content["id"]),
                    role=(
                        LogicalModelRole.ARTICLE_PLAN
                        if disguised_role else authority.role
                    ),
                    attempt_no=1,
                    authority=authority,
                    returned_model_id=authority.technical_model_id,
                    outcome="SUCCESS",
                    failure_kind=None,
                    usage=usage,
                    cost_usd=authority.settle(usage),
                    payload=payload,
            )
            if direct_sql:
                result_json = canonical_json(execution.result_payload())
                storage.conn.execute(
                    "UPDATE role_provider_executions SET outcome='SUCCESS',"
                    "returned_model_id=?,result_json=?,result_fingerprint=?,"
                    "settled_at=? WHERE execution_ref=?",
                    (authority.technical_model_id, result_json,
                     sha256_text(result_json), NOW.isoformat(),
                     execution.execution_ref),
                )
                storage.conn.commit()
            else:
                storage.settle_role_provider_execution(execution, now=NOW)
        except Exception as exc:  # noqa: BLE001 - this is the tested boundary
            if direct_sql and storage.conn.in_transaction:
                storage.conn.rollback()
            captured["refusal"] = f"{type(exc).__name__}: {exc}"
        raise RuntimeError("stop after direct ordinary-role settlement probe")

    try:
        captured["run_result"] = _run(
            storage,
            settings,
            account,
            job=job,
            writer=WriterTransport(),
            reviewer=hijack,
        )
    except Exception as exc:
        captured["run_error"] = f"{type(exc).__name__}: {exc}"

    row = storage.get_role_provider_execution(
        content_id=int(storage.get_content_row_for_job(job_id=job)["id"]),
        role="ARTICLE_REVIEWER",
    )
    assert captured["refusal"] is not None, repr(captured)
    assert (
        "role provider execution admits one effect stamp and one settlement"
        in str(captured["refusal"])
        or "CONTENT_REVIEW_RESULT_CONTRACT_INVALID" in str(captured["refusal"])
        or "CONTENT_REVIEW_RESULT_IDENTITY_MISMATCH" in str(captured["refusal"])
    )
    assert row is not None
    stored = json.loads(str(row["result_json"])) if row["result_json"] else {}
    assert row["outcome"] != "SUCCESS" or (
        stored.get("payload", {}).get("decision") != "APPROVE"
    )
    assert storage.get_content_row_for_job(job_id=job)["status"] != "PENDING_APPROVAL"


def test_16_direct_pending_transition_is_refused_atomically_without_either_gate(
    storage, settings, account,
):
    """The public transition API cannot bypass C2 or the review-only result."""
    job = "dc-direct-pending-transition"
    state = _failed_article(storage, settings, account, job=job)
    authority = _authority(state, suffix=job)
    observed: dict[str, object] = {}
    delegate = WriterTransport()

    def probing_writer(client, request):
        session = storage.get_content_review_resume_session(
            approval_ref=authority.approval_ref,
        )
        assert session is not None and session["status"] == "ACTIVE"
        execution = JobExecutionContext(
            job_id=authority.job_id,
            lease_owner=str(session["lease_owner"]),
            run_id=str(session["run_id"]),
            clock=FixedClock(NOW),
            fence_token=int(session["execution_generation"]),
            kind=JobKind.CONTENT,
            workflow=WorkflowType.ARTICLE,
        )
        storage.transition_content_execution(execution, ContentStatus.RUNNING)
        before_commands = storage.conn.execute(
            "SELECT count(*) FROM content_transition_commands",
        ).fetchone()[0]
        try:
            storage.transition_content_execution(
                execution,
                ContentStatus.PENDING_APPROVAL,
                final_result={"draft_fingerprint": authority.draft_fingerprint},
                score=1.0,
            )
        except Exception as exc:  # noqa: BLE001 - this is the tested boundary
            observed["refusal"] = f"{type(exc).__name__}: {exc}"
        observed["status"] = storage.get_content_row_for_job(job_id=job)["status"]
        observed["commands_before"] = before_commands
        observed["commands_after"] = storage.conn.execute(
            "SELECT count(*) FROM content_transition_commands",
        ).fetchone()[0]
        return delegate(client, request)

    result = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT),
        authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=_BlockingReviewerTransport(),
        writer_sdk_factory=_sdk_factory,
        writer_caller=probing_writer,
        post_reviewer_sdk_factory=_sdk_factory,
        post_reviewer_caller=ReviewerTransport(),
        clock=FixedClock(NOW),
    )

    assert observed["refusal"] is not None
    assert "PENDING_APPROVAL requires evaluated C2 or exact review-only approval" in str(
        observed["refusal"]
    )
    assert observed["status"] == "RUNNING"
    assert observed["commands_after"] == observed["commands_before"]
    assert result.final_status.value == "PENDING_APPROVAL"
