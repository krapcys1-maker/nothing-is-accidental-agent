"""B3 part B: the production semantic reviewer on the real controlled root.

Every provider effect here stops at a fake FINAL transport. Nothing else is
faked: the entrypoint, dispatcher, pipeline, writer, reviewer, storage, prompt
builders and cost accounting are the production ones.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import inspect
import json
from pathlib import Path

import pytest

from app.content.controlled_entrypoint import (
    ControlledArticleAuthority,
    run_controlled_article,
)
from app.content.foundation import ContentType
from app.content.reviewer import (
    ProductionArticleReviewer,
    ProductionReviewerError,
    REVIEWER_VERSION,
    parse_reviewer_response,
)
from app.content.contracts import FakeDraft
from app.content.quality_gate import (
    CLAIM_ACCOUNTING_IDENTITY_MISMATCH,
    ClaimAccountingEntry,
    ClaimClassification,
    ClaimReviewOutcome,
    DocumentCheck,
    DraftClaimSegment,
    assess_draft,
)
from app.content.writer import ProductionArticleWriter
from app.core.clock import FixedClock
from app.llm.anthropic_controlled_adapter import ControlledProviderRawResponse
from app.model_routing.contracts import LogicalModelRole, ModelFamily
from app.storage.repositories import SqliteStorage
from tests.c2_fixtures import seed_c2_research
from tests.test_prec5_verified_catalogue_live_root import _activate_article_roles

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)
OPUS = "claude-opus-5"

BODY = " ".join([
    "Airport gate assignments look arbitrary from the departure lounge.",
    "The board changes and nobody explains why it changed.",
    "A reassignment is usually a scheduling decision rather than an accident.",
    "Ground handling capacity is finite and it is allocated continuously.",
    "That allocation is what the traveller experiences as a sudden change.",
    "The cost of the change lands on passengers rather than on the schedule.",
    "Seeing the mechanism does not remove the inconvenience.",
    "It does change what the change means.",
] * 5)


def _open_paid_flags(storage) -> None:
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test-owner", reason="b3 part B", now=NOW)


class WriterTransport:
    """Fake FINAL writer transport only; the writer itself is production."""

    def __init__(self, *, model_id: str = OPUS, rewrite_first: bool = False) -> None:
        self.calls = 0
        self.model_id = model_id
        self.rewrite_first = rewrite_first

    def __call__(self, _client, request):
        self.calls += 1
        prompt = json.loads(request.user_prompt)
        attempt_no = int(prompt["contract"]["attempt_no"])
        brief = prompt["brief"]
        evidence = prompt["confirmed_claims_and_allowed_evidence"]
        paragraphs = [
            f"A small visible outcome raises a larger question: {brief['answer_question']}",
            f"The durable research card points to this thesis: {brief['central_thesis']}",
        ]
        # Enough paragraphs to sit inside the ARTICLE word window, which now
        # matches a real Substack essay; a short draft would trip the length
        # gate and buy an unwanted second reviewer call.
        for index in range(18):
            fact = evidence[index % len(evidence)]["claim_text"].rstrip(".")
            paragraphs.append(
                f"Frozen evidence {index + 1} supports a bounded part of the "
                f"mechanism: {fact}. The point is not that one fact explains "
                "everything, but that the same decision path keeps shaping the "
                "ordinary result, and that the people who benefit from it are "
                "rarely the people who ever notice it happening at all."
            )
        paragraphs.extend([
            f"A serious limit remains: {brief['counterargument_or_limitation']}",
            "Seen this way, the ordinary result is not accidental. It is the "
            "visible edge of a system of incentives, constraints, and prior choices.",
        ])
        draft = {
            "title": brief["working_title"],
            "body": "\n\n".join(paragraphs),
            "evidence_ids_used": [
                row["confirmed_claim_id"]
                for row in prompt["confirmed_claims_and_allowed_evidence"]
            ],
            "unsupported_claims": [],
            "personal_experience": False,
            "style_ok": True,
            "brief_compliant": True,
        }
        if self.rewrite_first and attempt_no == 1:
            draft.update({
                "body": "A vague system did something important. More detail is needed.",
                "evidence_ids_used": [],
                "style_ok": False,
                "brief_compliant": False,
            })
        return ControlledProviderRawResponse(
            returned_model_id=self.model_id,
            text=json.dumps(draft),
            input_tokens=1200,
            output_tokens=800,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            stop_reason="end_turn",
            provider_request_id=f"fake-writer-{self.calls}",
        )


class ReviewerTransport:
    """Fake FINAL reviewer transport; classification is echoed, not computed."""

    def __init__(
        self,
        *,
        model_id: str = OPUS,
        raise_error: BaseException | None = None,
        text: str | None = None,
        document_checks: dict[str, bool] | None = None,
        document_findings: tuple[str, ...] | None = None,
    ) -> None:
        self.calls = 0
        self.model_id = model_id
        self.raise_error = raise_error
        self.text = text
        self.document_checks = document_checks
        self.document_findings = document_findings

    def document_review(self) -> dict[str, object]:
        """A clean whole-article verdict unless a test asks for a failing one."""
        checks = {check.value: True for check in DocumentCheck}
        if self.document_checks:
            checks.update(self.document_checks)
        findings = (
            list(self.document_findings) if self.document_findings is not None
            else ([] if all(checks.values()) else ["rewrite the article"])
        )
        return {"checks": checks, "findings": findings}

    def __call__(self, _client, request):
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        payload = json.loads(request.user_prompt)
        entries = [
            {
                "segment_id": segment["segment_id"],
                "segment_fingerprint": segment["fingerprint"],
                "classification": "ARGUMENT_OR_INFERENCE",
                "evidence_ids": [],
                "reason": "reasoning drawn from the supplied package",
                "outcome": "PASS",
                "contains_external_fact": False,
            }
            for segment in payload["draft_segments"]
        ]
        body = self.text or json.dumps({
            "reviewer_version": REVIEWER_VERSION,
            "entries": entries,
            "document_review": self.document_review(),
        })
        return ControlledProviderRawResponse(
            returned_model_id=self.model_id,
            text=body,
            input_tokens=900,
            output_tokens=400,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            stop_reason="end_turn",
            provider_request_id=f"fake-reviewer-{self.calls}",
        )


def _sdk_factory(**_kwargs):
    return object()


def _run(storage, settings, account, *, job, writer, reviewer, cap="0.500000"):
    seeded = seed_c2_research(storage, account)
    _activate_article_roles(storage)
    _open_paid_flags(storage)
    return seeded, run_controlled_article(
        settings=replace(settings, project_root=ROOT),
        account_id=account.id,
        research_card_id=int(seeded["card_id"]),
        idempotency_key=job,
        authority=ControlledArticleAuthority(
            job_id=job,
            approval_ref=f"approval-{job}",
            approved_by="owner",
            approved_at="2026-08-11T09:00:00.000000+00:00",
            expires_at="2026-08-12T09:00:00.000000+00:00",
            cost_ceiling_usd=cap,
        ),
        api_key_provider=lambda: "fake-key-at-final-boundary",
        sdk_factory=_sdk_factory,
        caller=writer,
        reviewer_sdk_factory=_sdk_factory,
        reviewer_caller=reviewer,
        clock=FixedClock(NOW),
    )


def _execution(storage, job_id):
    row = storage.conn.execute(
        "SELECT * FROM role_provider_executions WHERE job_id=? "
        "AND logical_role='ARTICLE_REVIEWER'", (job_id,),
    ).fetchone()
    return None if row is None else dict(row)


# --------------------------------------------------------------- smoke ------

def test_smoke_production_root_reaches_writer_then_reviewer(
    storage, settings, account, capsys,
):
    writer, reviewer = WriterTransport(), ReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="b3-smoke",
        writer=writer, reviewer=reviewer,
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    execution = _execution(storage, outcome.job_id)
    frozen = storage.get_frozen_content_input(
        account.id, int(state["content"]["id"]),
    )
    assert writer.calls == 1, "writer final transport reached exactly once"
    assert frozen is not None
    assert frozen.prompt_version == "controlled_article_prompt_v4"
    assert reviewer.calls == 1, "reviewer final transport reached exactly once"
    assert execution is not None and execution["outcome"] == "SUCCESS"
    assert execution["returned_model_id"] == OPUS
    assert execution["settled_at"] is not None
    assert execution["external_effect_started_at"] is not None

    writer_cost = sum(
        Decimal(str(row["estimated_cost_usd"])) for row in state["usages"]
    )
    reviewer_cost = Decimal(execution["cost_usd"])
    total = writer_cost + reviewer_cost
    remaining = storage.remaining_article_budget(job_id=outcome.job_id)
    print(
        f"\nSMOKE writer_calls={writer.calls} reviewer_calls={reviewer.calls} "
        f"writer_model={OPUS} reviewer_model={execution['returned_model_id']} "
        f"writer_cost={writer_cost} reviewer_cost={reviewer_cost} "
        f"total={total} ceiling=0.500000 remaining={remaining} "
        f"final={state['content']['status']}"
    )
    assert total <= Decimal("0.500000")
    ledger = storage.conn.execute(
        "SELECT task,estimated_cost_usd FROM model_usage WHERE run_id=? "
        "ORDER BY id", (state["content"]["run_id"],),
    ).fetchall()
    assert [row["task"] for row in ledger] == [
        "content_draft", "article_reviewer",
    ]
    assert Decimal(str(storage.get_run(state["content"]["run_id"]).cost_usd)) \
        == total
    # Whatever the gate decides, it decided it AFTER a real semantic review.
    assert state["content"]["status"] in {
        "PENDING_APPROVAL", "APPROVED", "REJECTED", "REVISE",
    }


# ----------------------------------------------------------- A..I probes ----

def test_A_in_flight_exists_before_the_reviewer_transport(
    storage, settings, account,
):
    observed: dict[str, object] = {}

    class Observing(ReviewerTransport):
        def __call__(self, client, request):
            # A brand-new connection proves the row is already COMMITTED.
            fresh = SqliteStorage.open(settings.db_path)
            observed["row"] = fresh.get_role_provider_execution(
                content_id=int(
                    fresh.get_content_row_for_job(job_id="b3-A")["id"]
                ),
                role=LogicalModelRole.ARTICLE_REVIEWER,
            )
            fresh.close()
            return super().__call__(client, request)

    _run(storage, settings, account, job="b3-A",
         writer=WriterTransport(), reviewer=Observing())
    row = observed["row"]
    assert row is not None
    assert row["outcome"] == "IN_FLIGHT"
    assert row["external_effect_started_at"] is not None
    assert row["settled_at"] is None


def test_B_success_settles_usage_and_cost_exactly_once(
    storage, settings, account,
):
    reviewer = ReviewerTransport()
    _, outcome = _run(storage, settings, account, job="b3-B",
                      writer=WriterTransport(), reviewer=reviewer)
    rows = storage.conn.execute(
        "SELECT * FROM role_provider_executions WHERE job_id=?",
        (outcome.job_id,),
    ).fetchall()
    assert reviewer.calls == 1
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["outcome"] == "SUCCESS"
    assert row["input_tokens"] == 900 and row["output_tokens"] == 400
    # 900 in @5/MTok + 400 out @25/MTok = 0.004500 + 0.010000
    assert row["cost_usd"] == "0.014500"
    state = storage.get_content_pipeline_state(outcome.job_id)
    assessment = state["evaluations"]
    assert assessment, "the semantic review reached the quality gate"


def test_C_provider_failure_is_terminal_without_retry(
    storage, settings, account,
):
    reviewer = ReviewerTransport(text="not json at all")
    _, outcome = _run(storage, settings, account, job="b3-C",
                      writer=WriterTransport(), reviewer=reviewer)
    row = _execution(storage, outcome.job_id)
    assert reviewer.calls == 1, "no retry after a refused/invalid answer"
    assert row["outcome"] == "FAILURE"
    assert row["failure_kind"] == "REVIEWER_RESPONSE_NOT_JSON"
    assert row["settled_at"] is not None


def test_D_uncertain_in_flight_is_never_replayed_by_a_new_runtime(
    storage, settings, account,
):
    # A run whose budget stops the reviewer leaves the content, the frozen
    # binding and the approval in place with no role execution yet.
    _run(storage, settings, account, job="b3-D",
         writer=WriterTransport(), reviewer=ReviewerTransport(),
         cap="0.120000")

    # Now reproduce exactly the state a process death leaves behind: reserved,
    # external effect started, never settled.  The trigger contract makes it
    # impossible to fabricate this by rewriting a terminal row, which is the
    # point: this is the only way the state can legitimately exist.
    first = ProductionArticleReviewer(
        storage=storage, job_id="b3-D", api_key_provider=lambda: "k",
        sdk_factory=_sdk_factory, caller=ReviewerTransport(),
        daily_limit_usd=2, monthly_limit_usd=40,
    )
    authority, _ = first._authority()
    content_row = storage.get_content_row_for_job(job_id="b3-D")
    storage.begin_role_provider_execution(
        execution_ref="b3-D:ARTICLE_REVIEWER", job_id="b3-D",
        run_id=str(content_row["run_id"]), content_id=int(content_row["id"]),
        role=LogicalModelRole.ARTICLE_REVIEWER, attempt_no=1,
        # This probe fabricates only the crash marker; the production review()
        # path separately proves its full legal reservation envelope.
        max_cost_usd="0.010000", authority=authority,
        daily_limit_usd=2, monthly_limit_usd=40,
    )
    storage.mark_role_provider_effect_started("b3-D:ARTICLE_REVIEWER")

    # A brand-new runtime object, exactly as a restarted process would build.
    fresh = SqliteStorage.open(settings.db_path)
    replay = ReviewerTransport()
    reviewer2 = ProductionArticleReviewer(
        storage=fresh, job_id="b3-D",
        api_key_provider=lambda: "fake-key",
        sdk_factory=_sdk_factory, caller=replay,
        daily_limit_usd=2, monthly_limit_usd=40,
    )
    content = fresh.get_content_row_for_job(job_id="b3-D")
    with pytest.raises(ProductionReviewerError) as exc:
        reviewer2.review(
            draft=_Draft(), brief=_brief(storage, content), evidence=(),
            segments=(),
        )
    assert exc.value.code == "CONTENT_REVIEWER_RESULT_UNCERTAIN"
    assert replay.calls == 0, "PROVIDER CALL COUNT MUST BE 0"
    assert reviewer2.provider_calls == 0
    assert fresh.conn.execute(
        "SELECT COUNT(*) FROM role_provider_executions WHERE job_id='b3-D'"
    ).fetchone()[0] == 1
    fresh.close()


def test_E_returned_model_mismatch_is_fail_closed(storage, settings, account):
    reviewer = ReviewerTransport(model_id="claude-sonnet-5")
    _, outcome = _run(storage, settings, account, job="b3-E",
                      writer=WriterTransport(), reviewer=reviewer)
    row = _execution(storage, outcome.job_id)
    assert reviewer.calls == 1
    assert row["outcome"] == "FAILURE"
    assert row["failure_kind"] == "RETURNED_MODEL_MISMATCH"
    state = storage.get_content_pipeline_state(outcome.job_id)
    assert state["content"]["status"] != "APPROVED"


def test_F_exhausted_article_budget_makes_zero_reviewer_calls(
    storage, settings, account,
):
    reviewer = ReviewerTransport()
    # The writer alone consumes almost the whole ceiling, so the reviewer
    # ceiling can no longer fit inside what is left.
    _, outcome = _run(storage, settings, account, job="b3-F",
                      writer=WriterTransport(), reviewer=reviewer,
                      cap="0.020000")
    assert reviewer.calls == 0, "PROVIDER CALL COUNT MUST BE 0"
    row = _execution(storage, outcome.job_id)
    assert row is None or row["outcome"] != "SUCCESS"


def test_G_writer_and_reviewer_share_one_article_ceiling(
    storage, settings, account,
):
    _, outcome = _run(storage, settings, account, job="b3-G",
                      writer=WriterTransport(), reviewer=ReviewerTransport())
    cap = Decimal(storage.conn.execute(
        "SELECT cap_usd FROM content_provider_approvals WHERE job_id=?",
        (outcome.job_id,),
    ).fetchone()["cap_usd"])
    settled = sum(
        (Decimal(row["cost_usd"]) for row in storage.conn.execute(
            "SELECT cost_usd FROM content_provider_cost_settlements WHERE job_id=?",
            (outcome.job_id,),
        ).fetchall()),
        Decimal("0"),
    )
    roles = sum(
        (Decimal(row["cost_usd"]) for row in storage.conn.execute(
            "SELECT cost_usd FROM role_provider_executions "
            "WHERE job_id=? AND cost_usd IS NOT NULL", (outcome.job_id,),
        ).fetchall()),
        Decimal("0"),
    )
    assert settled + roles <= cap
    assert storage.remaining_article_budget(job_id=outcome.job_id) == (
        cap - settled - roles
    )


def test_H_ordinary_worker_stays_paid_disabled():
    from app.scheduler.dispatcher import JobDispatcher
    signature = inspect.signature(JobDispatcher.__init__)
    assert signature.parameters["allow_paid_content"].default is False


def test_I_frozen_reviewer_binding_is_the_qualified_opus(
    storage, settings, account,
):
    _, outcome = _run(storage, settings, account, job="b3-I",
                      writer=WriterTransport(), reviewer=ReviewerTransport())
    binding = storage.get_frozen_model_binding(
        intent_kind="content_role",
        intent_id=f"{outcome.job_id}:ARTICLE_REVIEWER",
    )
    assert binding is not None
    assert binding.role is LogicalModelRole.ARTICLE_REVIEWER
    assert binding.family is ModelFamily.OPUS
    assert binding.technical_model_id == OPUS
    assert binding.fallback_policy == "FORBIDDEN"
    provenance = storage.load_content_role_provenance(
        job_id=outcome.job_id, role=LogicalModelRole.ARTICLE_REVIEWER,
    )
    assert provenance["qualification"] is not None
    assert provenance["capability"] is not None


def test_production_root_carries_no_test_component():
    source = inspect.getsource(run_controlled_article)
    assert "FakeContentWriter" not in source
    assert "Fake" not in source.replace("FakeContentWriter", "")


def test_production_writer_uses_only_the_canonical_adapter_boundary():
    source = inspect.getsource(ProductionArticleWriter)
    assert "ControlledAnthropicAdapter" in source
    assert "Anthropic(" not in source
    assert "messages.create" not in source


def test_rewrite_production_path_reaches_terminal_with_one_shared_cap(
    storage, settings, account,
):
    writer = WriterTransport(rewrite_first=True)
    reviewer = ReviewerTransport()
    seeded, outcome = _run(
        storage, settings, account, job="repair-rewrite-terminal",
        writer=writer, reviewer=reviewer, cap="0.500000",
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    role_rows = [dict(row) for row in storage.conn.execute(
        "SELECT * FROM role_provider_executions WHERE job_id=? ORDER BY attempt_no",
        (outcome.job_id,),
    ).fetchall()]
    writer_costs = [
        Decimal(str(row["estimated_cost_usd"])) for row in state["usages"]
    ]
    reviewer_costs = [Decimal(row["cost_usd"]) for row in role_rows]
    assert writer.calls == 2
    assert reviewer.calls == 2
    assert [row["attempt_no"] for row in role_rows] == [1, 2]
    assert state["content"]["status"] == "PENDING_APPROVAL"
    assert outcome.worker.status.value == "DONE"
    assert sum(writer_costs + reviewer_costs) == Decimal("0.081000")
    ledger = storage.conn.execute(
        "SELECT task,estimated_cost_usd FROM model_usage WHERE run_id=? "
        "ORDER BY id", (state["content"]["run_id"],),
    ).fetchall()
    assert [row["task"] for row in ledger] == [
        "content_draft", "article_reviewer",
        "content_draft", "article_reviewer",
    ]
    assert sum(Decimal(str(row["estimated_cost_usd"])) for row in ledger) \
        == Decimal("0.081000")
    assert Decimal(str(storage.get_run(state["content"]["run_id"]).cost_usd)) \
        == Decimal("0.081000")
    assert Decimal(str(storage.sum_real_cost_usd("2026-08-11"))) \
        == Decimal("0.081")
    cumulative = Decimal("0")
    remaining_after_each = []
    for cost in (
        writer_costs[0], reviewer_costs[0], writer_costs[1], reviewer_costs[1],
    ):
        cumulative += cost
        remaining_after_each.append(Decimal("0.500000") - cumulative)
    assert remaining_after_each == [
        Decimal("0.474000"), Decimal("0.459500"),
        Decimal("0.433500"), Decimal("0.419000"),
    ]
    assert storage.remaining_article_budget(job_id=outcome.job_id) == Decimal(
        "0.419000"
    )
    assert state["drafts"][-1]["draft_fingerprint"] == state["decisions"][-1][
        "draft_fingerprint"
    ]
    assert int(state["content"]["research_card_id"]) == int(seeded["card_id"])


def test_rewrite_budget_denial_stops_before_second_writer_call(
    storage, settings, account,
):
    writer = WriterTransport(rewrite_first=True)
    reviewer = ReviewerTransport()
    _, outcome = _run(
        storage, settings, account, job="repair-rewrite-denied",
        writer=writer, reviewer=reviewer, cap="0.400000",
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    assert writer.calls == 1
    assert reviewer.calls == 1
    assert state["content"]["status"] == "FAILED"
    assert state["content"]["reason_code"] == "CONTENT_APPROVAL_CAP_EXCEEDED"
    # The cap sits deliberately between one writer attempt and two: the first
    # draft and its review are affordable, the rewrite is not, and the denial
    # lands before the second paid call. The figures moved with the writer
    # envelope, which now reserves against the context ceiling because a rewrite
    # carries the prior draft and the reviewer's findings.
    assert storage.remaining_article_budget(job_id=outcome.job_id) == Decimal(
        "0.359500"
    )
    reopened = SqliteStorage.open(settings.db_path)
    assert reopened.remaining_article_budget(job_id=outcome.job_id) == Decimal(
        "0.359500"
    )
    reopened.close()


def test_unknown_reviewer_cost_is_null_and_blocks_next_paid_role_after_reopen(
    storage, settings, account,
):
    reviewer = ReviewerTransport(raise_error=TimeoutError("unknown result"))
    _, outcome = _run(
        storage, settings, account, job="repair-unknown-cost",
        writer=WriterTransport(), reviewer=reviewer,
    )
    row = _execution(storage, outcome.job_id)
    assert reviewer.calls == 1
    assert row["outcome"] == "NEEDS_VERIFICATION"
    assert row["failure_kind"] == "REVIEWER_RESULT_UNKNOWN"
    assert row["cost_usd"] is None
    assert row["input_tokens"] is None and row["output_tokens"] is None

    fresh = SqliteStorage.open(settings.db_path)
    next_transport = ReviewerTransport()
    restarted = ProductionArticleReviewer(
        storage=fresh, job_id=outcome.job_id,
        api_key_provider=lambda: "fake-key", sdk_factory=_sdk_factory,
        caller=next_transport,
        daily_limit_usd=2, monthly_limit_usd=40,
    )
    draft = _Draft()
    draft.attempt_no = 2
    with pytest.raises(Exception) as exc:
        restarted.review(
            draft=draft, brief=_brief(fresh, fresh.get_content_row_for_job(
                job_id=outcome.job_id,
            )), evidence=(), segments=(),
        )
    assert getattr(exc.value, "code", None) == "CONTENT_ARTICLE_COST_UNKNOWN"
    assert next_transport.calls == 0
    assert restarted.provider_calls == 0
    fresh.close()


def test_strict_reviewer_parser_matrix():
    segment = DraftClaimSegment(
        ordinal=1, segment_id="segment-1", fingerprint="a" * 64, text="A claim.",
    )
    entry = {
        "segment_id": segment.segment_id,
        "segment_fingerprint": segment.fingerprint,
        "classification": "ARGUMENT_OR_INFERENCE",
        "evidence_ids": [],
        "reason": "canonical reason",
        "outcome": "PASS",
        "contains_external_fact": False,
    }

    def encoded(**changes):
        payload = {
            "reviewer_version": REVIEWER_VERSION,
            "entries": [dict(entry)],
            "document_review": {
                "checks": {check.value: True for check in DocumentCheck},
                "findings": [],
            },
        }
        for key, value in changes.items():
            if key in {"reviewer_version", "document_review"}:
                payload[key] = value
            else:
                payload["entries"][0][key] = value
        return json.dumps(payload)

    parsed, document_review = parse_reviewer_response(encoded(), segments=(segment,))
    assert len(parsed) == 1 and parsed[0].contains_external_fact is False
    assert document_review.approved is True
    for malformed in (
        encoded(reviewer_version="wrong"),
        encoded(reason=None),
        encoded(contains_external_fact="false"),
        encoded(classification="UNKNOWN_CLASS"),
    ):
        with pytest.raises(ProductionReviewerError):
            parse_reviewer_response(malformed, segments=(segment,))
    with pytest.raises(ProductionReviewerError) as mismatch:
        parse_reviewer_response(
            encoded(segment_fingerprint="b" * 64), segments=(segment,),
        )
    assert mismatch.value.code == "REVIEWER_ENTRY_FINGERPRINT_MISMATCH"

    # An abbreviated echo of the true fingerprint is the model being lazy about
    # a value we supplied, not tampering: on a live 22-entry review exactly one
    # entry came back as "a5e0caf75d91f563b..." and the whole paid review was
    # discarded. segment_id already pins the first 16 hex characters, so the
    # segment is identified either way.
    for abbreviated in ("a" * 17 + "...", "a" * 20, "a" * 16, "a" * 40 + "…"):
        parsed_short, _ = parse_reviewer_response(
            encoded(segment_fingerprint=abbreviated), segments=(segment,),
        )
        assert len(parsed_short) == 1
    # Too short to identify, or a different value, still fails.
    for rejected in ("a" * 15, "b" * 20, "", "   ", "..."):
        with pytest.raises(ProductionReviewerError) as short:
            parse_reviewer_response(
                encoded(segment_fingerprint=rejected), segments=(segment,),
            )
        assert short.value.code in {
            "REVIEWER_ENTRY_FINGERPRINT_MISMATCH", "REVIEWER_ENTRY_MALFORMED",
        }

    class WrongFingerprintReviewer:
        reviewer_version = REVIEWER_VERSION

        def review(self, *, segments, **_kwargs):
            return tuple(ClaimAccountingEntry(
                segment_id=item.segment_id,
                segment_fingerprint="b" * 64,
                classification=ClaimClassification.ARGUMENT_OR_INFERENCE,
                evidence_ids=(), reason="canonical reason",
                outcome=ClaimReviewOutcome.PASS, contains_external_fact=False,
            ) for item in segments)

    assessment = assess_draft(
        FakeDraft(
            attempt_no=1, route_key="FABLE_5_ARTICLE", title="A title",
            body="A claim.", evidence_ids_used=(), unsupported_claims=(),
            personal_experience=False, style_ok=True, brief_compliant=True,
        ),
        _brief(None, None), evidence=(),
        claim_reviewer=WrongFingerprintReviewer(),
    )
    assert CLAIM_ACCOUNTING_IDENTITY_MISMATCH in {
        finding["code"] for finding in assessment.findings
    }


# --- helpers used only by the restart probe ---------------------------------

class _Draft:
    attempt_no = 1

    def fingerprint(self) -> str:
        return "0" * 64


def _brief(storage, content):
    from app.content.contracts import ArticleBrief

    return ArticleBrief(
        working_title="t", central_thesis="t", answer_question="q?",
        narrative_angle="a", target_reader="r", concrete_opening="o",
        argument_structure=("a",), required_facts=("f",), evidence_ids=("e",),
        counterargument_or_limitation="c", ending="e",
        min_words=240, max_words=420, forbidden_claims=(),
    )
