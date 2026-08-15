"""Adversarial probe: try to break the canonical contract via public APIs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from app.content.review_only import run_controlled_article_review_only
from app.core.clock import FixedClock
from tests.test_pr46_review_only_resume import (
    NOW, ROOT, _authority, _failed_article, _sdk_factory,
)

CANON = ("TITLE_REFLECTS_BODY", "TITLE_PROMISE_FULFILLED", "TITLE_MECHANISM_EXPLAINED",
         "BRIEF_QUESTION_ANSWERED", "THESIS_CONSISTENT", "CONCLUSIONS_WITHIN_EVIDENCE")
V3 = "production_article_reviewer_opus_v3"
DOC = {"approved": True, "checks": {n: True for n in CANON},
       "failed_checks": [], "findings": []}


def _usage():
    return SimpleNamespace(input_tokens=900, output_tokens=400, cache_read_tokens=0,
                           cache_write_tokens=0, web_search_requests=0)


def _attack(storage, settings, account, job, payload_builder, outcome="SUCCESS"):
    state = _failed_article(storage, settings, account, job=job)
    authority = _authority(state, suffix=job)
    out = {}

    def hijack(_client, request):
        supplied = json.loads(request.user_prompt)["draft_segments"]
        reserved = storage.get_content_review_resume_execution(
            execution_ref=authority.initial_review_execution_ref,
        )
        assert reserved is not None
        payload = payload_builder(supplied, authority)
        payload.setdefault(
            "request_intent_fingerprint",
            reserved["request_intent_fingerprint"],
        )
        try:
            storage.settle_content_review_resume_execution(
                execution_ref=authority.initial_review_execution_ref,
                outcome=outcome, failure_kind=None if outcome == "SUCCESS" else "X",
                returned_model_id="claude-opus-5", usage=_usage(),
                cost_usd=Decimal("0.010000"),
                result_payload=payload, now=NOW)
            out["r"] = "ACCEPTED"
        except Exception as exc:
            out["r"] = f"refused ({type(exc).__name__})"
        raise RuntimeError("stop")

    with pytest.raises(Exception):
        run_controlled_article_review_only(
            settings=replace(settings, project_root=ROOT), authority=authority,
            api_key_provider=lambda: "f", initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=hijack, writer_sdk_factory=_sdk_factory,
            writer_caller=hijack, post_reviewer_sdk_factory=_sdk_factory,
            post_reviewer_caller=hijack, clock=FixedClock(NOW))
    row = storage.conn.execute(
        "SELECT outcome,result_json FROM content_review_resume_executions "
        "WHERE execution_ref=?", (authority.initial_review_execution_ref,)).fetchone()
    approved = (row is not None and row["outcome"] == "SUCCESS"
                and json.loads(str(row["result_json"] or "{}")).get("decision") == "APPROVE")
    pend = storage.conn.execute(
        "SELECT count(*) FROM content_items WHERE status='PENDING_APPROVAL'").fetchone()[0]
    return out.get("r"), approved, pend


def _base(supplied, authority, **over):
    p = {"reviewer_version": V3, "decision": "APPROVE",
         "draft_fingerprint": authority.draft_fingerprint, "review_no": 1,
         "entries": [{"segment_id": s["segment_id"],
                      "segment_fingerprint": s["fingerprint"],
                      "classification": "ARGUMENT_OR_INFERENCE", "evidence_ids": [],
                      "reason": "r", "outcome": "PASS",
                      "contains_external_fact": False} for s in supplied],
         "document_review": DOC}
    p.update(over)
    return p


ATTACKS = {
    "A1 entries as string": lambda s, a: _base(s, a, entries="not-an-array"),
    "A2 entries as object": lambda s, a: _base(s, a, entries={"0": "x"}),
    "A3 entries empty array": lambda s, a: _base(s, a, entries=[]),
    "A4 entry is a number": lambda s, a: _base(s, a, entries=[1, 2]),
    "A5 entry is null": lambda s, a: _base(s, a, entries=[None]),
    "A6 entry is a string": lambda s, a: _base(s, a, entries=["x"]),
    "A7 nested entries": lambda s, a: _base(s, a, entries=[[{"classification": "x"}]]),
    "A8 no decision key": lambda s, a: {
        k: v for k, v in _base(s, a).items() if k != "decision"},
    "A9 no document_review": lambda s, a: {
        k: v for k, v in _base(s, a).items() if k != "document_review"},
    "A10 no reviewer_version": lambda s, a: {
        k: v for k, v in _base(s, a).items() if k != "reviewer_version"},
    "A11 contradiction hidden behind REWRITE_ONCE": lambda s, a: _base(
        s, a, decision="REWRITE_ONCE",
        entries=[{"segment_id": x["segment_id"], "segment_fingerprint": x["fingerprint"],
                  "classification": "NON_FACTUAL_PROSE", "evidence_ids": [],
                  "reason": "r", "outcome": "PASS",
                  "contains_external_fact": True} for x in s]),
    "A12 classification as number": lambda s, a: _base(
        s, a, entries=[{"segment_id": x["segment_id"],
                        "segment_fingerprint": x["fingerprint"],
                        "classification": 1, "evidence_ids": [], "reason": "r",
                        "outcome": "PASS", "contains_external_fact": False} for x in s]),
    "A13 outcome as number": lambda s, a: _base(
        s, a, entries=[{"segment_id": x["segment_id"],
                        "segment_fingerprint": x["fingerprint"],
                        "classification": "ARGUMENT_OR_INFERENCE", "evidence_ids": [],
                        "reason": "r", "outcome": 1,
                        "contains_external_fact": False} for x in s]),
    "A14 lowercase class": lambda s, a: _base(
        s, a, entries=[{"segment_id": x["segment_id"],
                        "segment_fingerprint": x["fingerprint"],
                        "classification": "argument_or_inference", "evidence_ids": [],
                        "reason": "r", "outcome": "PASS",
                        "contains_external_fact": False} for x in s]),
    "A15 evidence on inference with BLOCK": lambda s, a: _base(
        s, a, entries=[{"segment_id": x["segment_id"],
                        "segment_fingerprint": x["fingerprint"],
                        "classification": "ARGUMENT_OR_INFERENCE",
                        "evidence_ids": ["e1"], "reason": "r", "outcome": "BLOCK",
                        "contains_external_fact": False} for x in s]),
    "A16 null segment id": lambda s, a: _base(
        s, a, entries=[_e(x, segment_id=None) for x in s]),
    "A17 null segment fingerprint": lambda s, a: _base(
        s, a, entries=[_e(x, segment_fingerprint=None) for x in s]),
    "A18 blank reason": lambda s, a: _base(
        s, a, entries=[_e(x, reason=" ") for x in s]),
    "A19 non-string evidence member": lambda s, a: _base(
        s, a, entries=[_e(
            x,
            classification="EVIDENCE_GROUNDED_FACT",
            evidence_ids=[None],
            contains_external_fact=True,
        ) for x in s]),
    "A20 duplicate segment coverage": lambda s, a: _base(
        s, a, entries=[_e(s[0]) for _ in s]),
    "A21 unknown segment identity": lambda s, a: _base(
        s, a, entries=[
            _e(x, segment_id="unknown:segment") if i == 0 else _e(x)
            for i, x in enumerate(s)
        ]),
}


@pytest.mark.parametrize("name", list(ATTACKS))
def test_adversarial(name, storage, settings, account):
    r, approved, pend = _attack(storage, settings, account, "adv", ATTACKS[name])
    print(f"  {'HOLE' if (approved or pend) else 'ok  '}  {name:46s} "
          f"settle={r} stored_APPROVE={approved} pending={pend}")
    assert not approved, f"{name}: a contradictory APPROVE was stored"
    assert not pend, f"{name}: PENDING_APPROVAL was reached"
    assert str(r).startswith("refused"), f"{name}: invalid SUCCESS was stored: {r}"

def test_second_update_cannot_swap_a_settled_payload(storage, settings, account):
    """A settled SUCCESS row must not be re-settled with a different payload."""
    from tests.test_b3_production_reviewer import ReviewerTransport
    state = _failed_article(storage, settings, account, job="adv-reupdate")
    authority = _authority(state, suffix="adv-reupdate")
    run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "f", initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=ReviewerTransport(), clock=FixedClock(NOW))
    print("\n=== RE-SETTLEMENT OF A SETTLED ROW ===")
    try:
        storage.settle_content_review_resume_execution(
            execution_ref=authority.initial_review_execution_ref,
            outcome="SUCCESS", failure_kind=None, returned_model_id="claude-opus-5",
            usage=_usage(), cost_usd=Decimal("0.010000"),
            result_payload=_base([], authority, entries=[
                {"segment_id": "x", "segment_fingerprint": "y",
                 "classification": "NON_FACTUAL_PROSE", "evidence_ids": [],
                 "reason": "r", "outcome": "PASS", "contains_external_fact": True}]),
            now=NOW)
        print("   ACCEPTED  ** HOLE **")
        raise AssertionError("a settled row was re-settled")
    except AssertionError:
        raise
    except Exception as exc:
        print(f"   refused: {type(exc).__name__}: {str(exc)[:90]}")
def _e(x, **over):
    item = {"segment_id": x["segment_id"], "segment_fingerprint": x["fingerprint"],
            "classification": "ARGUMENT_OR_INFERENCE", "evidence_ids": [],
            "reason": "r", "outcome": "PASS", "contains_external_fact": False}
    item.update(over)
    return item


ROUND2 = {
    "B1 doc approved=false, findings empty": lambda s, a: _base(
        s, a, document_review={"approved": False, "checks": {n: True for n in CANON},
                               "failed_checks": [], "findings": []}),
    "B2 one doc check false, failed_checks empty": lambda s, a: _base(
        s, a, document_review={"approved": True,
                               "checks": {**{n: True for n in CANON},
                                          CANON[0]: False},
                               "failed_checks": [], "findings": []}),
    "B3 entry with extra unknown field": lambda s, a: _base(
        s, a, entries=[_e(x, injected="whatever") for x in s]),
    "B4 grounded fact external=false with evidence": lambda s, a: _base(
        s, a, entries=[_e(x, classification="EVIDENCE_GROUNDED_FACT",
                          evidence_ids=["e1"], contains_external_fact=False)
                       for x in s]),
    "B5 APPROVE with one BLOCK entry": lambda s, a: _base(
        s, a, entries=[_e(x, outcome="BLOCK" if i == 0 else "PASS")
                       for i, x in enumerate(s)]),
    "B6 doc failed_checks non-empty but approved true": lambda s, a: _base(
        s, a, document_review={"approved": True, "checks": {n: True for n in CANON},
                               "failed_checks": ["TITLE_REFLECTS_BODY"],
                               "findings": []}),
    "B7 doc checks duplicated key names": lambda s, a: _base(
        s, a, document_review={"approved": True,
                               "checks": {n: True for n in CANON[:5]},
                               "failed_checks": [], "findings": []}),
    "B8 document review has an extra field": lambda s, a: _base(
        s, a, document_review={**DOC, "unexpected": "field"}),
}

# Storing a contradictory payload under a NON-success outcome stays legal as a
# diagnostic, but must never be consumable as an approval.
NONSUCCESS = {
    "C1 FAILURE carrying APPROVE payload": ("FAILURE", lambda s, a: _base(
        s, a, entries=[_e(x, contains_external_fact=True) for x in s])),
    "C2 NEEDS_VERIFICATION carrying APPROVE": ("NEEDS_VERIFICATION", lambda s, a: _base(
        s, a, entries=[_e(x, contains_external_fact=True) for x in s])),
}


@pytest.mark.parametrize("name", list(ROUND2))
def test_adversarial_round2(name, storage, settings, account):
    r, approved, pend = _attack(storage, settings, account, "adv2", ROUND2[name])
    print(f"  {'HOLE' if (approved or pend) else 'ok  '}  {name:46s} "
          f"settle={r} stored_APPROVE={approved} pending={pend}")
    assert not approved, f"{name}: a contradictory APPROVE was stored"
    assert not pend, f"{name}: PENDING_APPROVAL was reached"
    assert str(r).startswith("refused"), f"{name}: invalid SUCCESS was stored: {r}"


@pytest.mark.parametrize("name", list(NONSUCCESS))
def test_adversarial_non_success_outcomes(name, storage, settings, account):
    outcome, builder = NONSUCCESS[name]
    r, approved, pend = _attack(
        storage, settings, account, "adv3", builder, outcome=outcome)
    print(f"  {'HOLE' if (approved or pend) else 'ok  '}  {name:46s} "
          f"settle={r} stored_APPROVE={approved} pending={pend}")
    assert not approved and not pend
