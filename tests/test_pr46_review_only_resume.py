"""Offline acceptance probes for the PR #46 reviewer-resume boundary.

Every transport is an in-memory fake of the installed Anthropic SDK surface.
No provider SDK request, network access, production database or publication
path is used by this module.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import inspect
import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.content.contracts import PipelineDecision
from app.content.cost_estimate import (
    ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS,
    ARTICLE_REVIEWER_MAX_OUTPUT_TOKENS,
    ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
    TOPIC_GENERATION_MAX_OUTPUT_TOKENS,
)
from app.content.quality_gate import DocumentCheck, DraftClaimSegment
from app.content.review_only import (
    ReviewOnlyAuthority,
    ReviewOnlyError,
    run_controlled_article_review_only,
)
from app.content.reviewer import (
    REVIEWER_VERSION,
    parse_reviewer_response,
    safe_reviewer_response_artifact,
)
from app.core.clock import FixedClock
from app.llm.anthropic_controlled_adapter import (
    ControlledAnthropicAdapter,
    ControlledProviderRequest,
    ControlledProviderRawResponse,
)
from app.llm.anthropic_provider_contract import ARTICLE_REVIEWER_INFERENCE_CONFIG
from app.llm.anthropic_provider_contract import (
    AnthropicInferenceConfig,
    COMMENT_WRITER_INFERENCE_CONFIG,
    ARTICLE_RESEARCH_INFERENCE_CONFIG,
    ARTICLE_WRITER_INFERENCE_CONFIG,
    NOTE_WRITER_INFERENCE_CONFIG,
    TOPIC_GENERATION_INFERENCE_CONFIG,
)
from app.research.source_discovery_intent import (
    SourceDiscoveryIntent,
    SourceDiscoveryIntentError,
    _fingerprint as source_discovery_fingerprint,
)
from app.research.base import DEFAULT_SYNTHESIS_MAX_TOKENS
from app.research.durable_intent import DEFAULT_REQUEST_MAX_TOKENS
from tests.test_b3_production_reviewer import (
    ROOT,
    NOW,
    ReviewerTransport,
    WriterTransport,
    _sdk_factory,
    _run,
)


def _clean_document_review() -> dict:
    """A passing whole-article verdict for fakes that exercise other invariants."""
    return {
        "checks": {check.value: True for check in DocumentCheck},
        "findings": [],
    }


def _response_for_prompt(prompt: str):
    supplied = json.loads(prompt)["draft_segments"]
    reason = (
        "This deliberately longer reason remains valid because semantic "
        "classification and identity are complete and correct"
    )
    body = json.dumps({
        "reviewer_version": REVIEWER_VERSION,
        "entries": [
            {
                "segment_id": segment["segment_id"],
                "segment_fingerprint": segment["fingerprint"],
                "classification": "ARGUMENT_OR_INFERENCE",
                "evidence_ids": [],
                "reason": reason,
                "outcome": "PASS",
                "contains_external_fact": False,
            }
            for segment in supplied
        ],
        "document_review": _clean_document_review(),
    })
    usage = SimpleNamespace(
        input_tokens=900,
        output_tokens=400,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=0),
        inference_geo="global",
        service_tier="standard",
        output_tokens_details=SimpleNamespace(thinking_tokens=120),
    )
    return SimpleNamespace(
        id="fake-stream-request-1",
        model="claude-opus-5",
        stop_reason="end_turn",
        usage=usage,
        content=(SimpleNamespace(type="text", text=body),),
    )


class _StreamManager:
    def __init__(self, *, prompt: str, failure: BaseException | None = None):
        self.prompt = prompt
        self.failure = failure
        self.final_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get_final_message(self):
        self.final_calls += 1
        if self.failure is not None:
            raise self.failure
        return _response_for_prompt(self.prompt)


class _Messages:
    def __init__(self, *, failure: BaseException | None = None):
        self.failure = failure
        self.stream_calls: list[dict[str, object]] = []
        self.managers: list[_StreamManager] = []

    def create(self, **_kwargs):
        raise AssertionError("streaming reviewer must never use messages.create")

    def stream(self, **kwargs):
        self.stream_calls.append(dict(kwargs))
        prompt = str(kwargs["messages"][0]["content"])
        manager = _StreamManager(prompt=prompt, failure=self.failure)
        self.managers.append(manager)
        return manager


class _SdkFactory:
    def __init__(self, *, failure: BaseException | None = None):
        self.calls: list[dict[str, object]] = []
        self.messages = _Messages(failure=failure)
        self.client = SimpleNamespace(messages=self.messages)

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.client


def _request() -> ControlledProviderRequest:
    return ControlledProviderRequest(
        technical_model_id="claude-opus-5",
        system_prompt="system",
        user_prompt=json.dumps({"draft_segments": []}),
        max_output_tokens=8192,
        timeout_seconds=300.0,
        inference_config=ARTICLE_REVIEWER_INFERENCE_CONFIG,
        stream_response=True,
    )


def test_official_fake_stream_returns_only_the_complete_final_message():
    factory = _SdkFactory()
    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "fake-never-sent",
        sdk_factory=factory,
    )
    raw = adapter.execute(_request())

    assert adapter.caller_calls == 1
    assert factory.calls == [{
        "api_key": "fake-never-sent", "max_retries": 0, "timeout": 300.0,
    }]
    assert len(factory.messages.stream_calls) == 1
    sent = factory.messages.stream_calls[0]
    assert sent["model"] == raw.returned_model_id == "claude-opus-5"
    assert sent["max_tokens"] == 8192 and sent["timeout"] == 300.0
    assert sent["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in sent["thinking"]
    assert sent["output_config"] == {"effort": "low"}
    assert factory.messages.managers[0].final_calls == 1
    assert raw.provider_request_id == "fake-stream-request-1"
    assert (raw.input_tokens, raw.output_tokens, raw.thinking_tokens) == (900, 400, 120)
    assert raw.stop_reason == "end_turn"


def test_role_thinking_effort_is_explicit_fingerprinted_and_fail_closed():
    assert ARTICLE_REVIEWER_INFERENCE_CONFIG.payload() == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
    }
    assert ARTICLE_WRITER_INFERENCE_CONFIG.payload()["output_config"] == {
        "effort": "high",
    }
    assert ARTICLE_RESEARCH_INFERENCE_CONFIG.payload()["thinking"] == {
        "type": "adaptive",
    }
    assert TOPIC_GENERATION_INFERENCE_CONFIG.payload()["output_config"] == {
        "effort": "medium",
    }
    role_configs = {
        "ARTICLE_REVIEWER": (ARTICLE_REVIEWER_INFERENCE_CONFIG, "low"),
        "ARTICLE_WRITER": (ARTICLE_WRITER_INFERENCE_CONFIG, "high"),
        "ARTICLE_RESEARCH": (ARTICLE_RESEARCH_INFERENCE_CONFIG, "high"),
        "TOPIC_GENERATION": (TOPIC_GENERATION_INFERENCE_CONFIG, "medium"),
        "NOTE_WRITER": (NOTE_WRITER_INFERENCE_CONFIG, "medium"),
        "COMMENT_WRITER": (COMMENT_WRITER_INFERENCE_CONFIG, "medium"),
    }
    for config, effort in role_configs.values():
        assert config.payload() == {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        assert "budget_tokens" not in json.dumps(config.payload())
    intent = SourceDiscoveryIntent.build(account_id="account", topic_id=7)
    original = intent.as_payload()
    assert original["inference_config"] == ARTICLE_RESEARCH_INFERENCE_CONFIG.payload()
    mutated = json.loads(json.dumps(original))
    mutated["inference_config"]["output_config"]["effort"] = "low"
    mutated["fingerprint"] = source_discovery_fingerprint(mutated)
    assert mutated["fingerprint"] != original["fingerprint"]
    with pytest.raises(SourceDiscoveryIntentError, match="inference config mismatch"):
        SourceDiscoveryIntent.from_payload(mutated)
    legacy = json.loads(json.dumps(original))
    legacy["inference_config"]["thinking"] = {
        "type": "enabled", "budget_tokens": 4096,
    }
    legacy["fingerprint"] = source_discovery_fingerprint(legacy)
    with pytest.raises(SourceDiscoveryIntentError, match="inference config mismatch"):
        SourceDiscoveryIntent.from_payload(legacy)


class _AdaptiveOnlyMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        if kwargs["model"] in {"claude-opus-5", "claude-sonnet-5"} and kwargs.get(
            "thinking"
        ) != {"type": "adaptive"}:
            raise ValueError("fake SDK rejects legacy thinking for Claude 5")
        if "budget_tokens" in kwargs.get("thinking", {}):
            raise ValueError("fake SDK rejects budget_tokens for Claude 5")
        self.calls.append(dict(kwargs))
        response = _response_for_prompt(json.dumps({"draft_segments": []}))
        response.model = kwargs["model"]
        return response


@pytest.mark.parametrize(
    ("model_id", "config", "effort"),
    [
        ("claude-opus-5", ARTICLE_WRITER_INFERENCE_CONFIG, "high"),
        ("claude-sonnet-5", NOTE_WRITER_INFERENCE_CONFIG, "medium"),
    ],
)
def test_fake_sdk_accepts_only_adaptive_without_budget_for_assigned_models(
    model_id, config, effort,
):
    messages = _AdaptiveOnlyMessages()
    client = SimpleNamespace(messages=messages)
    adapter = ControlledAnthropicAdapter(
        api_key_provider=lambda: "fake-never-sent",
        sdk_factory=lambda **_kwargs: client,
    )
    adapter.execute(ControlledProviderRequest(
        technical_model_id=model_id,
        system_prompt="system",
        user_prompt="prompt",
        max_output_tokens=128,
        timeout_seconds=300.0,
        inference_config=config,
    ))
    sent = messages.calls[0]
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["output_config"] == {"effort": effort}
    with pytest.raises(ValueError, match="legacy thinking"):
        messages.create(
            model=model_id,
            thinking={"type": "enabled", "budget_tokens": 1024},
        )


def test_production_evidence_limits_and_topic_identity_are_not_narrowed():
    assert ARTICLE_REVIEWER_MAX_OUTPUT_TOKENS == 8192
    assert ARTICLE_WRITER_MAX_OUTPUT_TOKENS == 8192
    assert ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS == 8192
    assert DEFAULT_SYNTHESIS_MAX_TOKENS == DEFAULT_REQUEST_MAX_TOKENS == 8192
    assert TOPIC_GENERATION_MAX_OUTPUT_TOKENS == 4096
    discovery = SourceDiscoveryIntent.build(account_id="account", topic_id=17)
    assert (discovery.max_results, discovery.max_output_tokens) == (6, 8192)

    import scripts.run_article_research_e2e_live as live_root

    with pytest.raises(SystemExit) as missing_topic:
        live_root.main(["--approved-by", "owner", "--confirm-live"])
    assert missing_topic.value.code == 2
    source = inspect.getsource(live_root)
    assert "storage.add_topic" not in source
    assert "successes >= discovery_contract.max_results" in source
    assert "if successes < 3" in source


def test_0039_accepts_adaptive_approval_and_rejects_legacy_thinking(
    storage, settings, account, tmp_path,
):
    first_state = _failed_article(storage, settings, account, job="pr46-sql-adaptive")
    first = _authority(first_state, suffix="sql-adaptive")
    storage.record_content_review_resume_approval(
        approval_ref=first.approval_ref,
        job_id=first.job_id,
        run_id=str(first_state["content"]["run_id"]),
        content_id=first.content_id,
        source_draft_fingerprint=first.draft_fingerprint,
        initial_review_execution_ref=first.initial_review_execution_ref,
        writer_execution_ref=first.writer_execution_ref,
        post_review_execution_ref=first.post_review_execution_ref,
        reviewer_provider="ANTHROPIC",
        reviewer_model_id="claude-opus-5",
        writer_provider="ANTHROPIC",
        writer_model_id="claude-opus-5",
        reviewer_max_output_tokens=8192,
        writer_max_output_tokens=8192,
        reviewer_max_cost_usd="0.300000",
        writer_max_cost_usd="0.300000",
        chain_cap_usd="1.000000",
        daily_limit_usd="2.000000",
        monthly_limit_usd="40.000000",
        approved_by=first.approved_by,
        approved_at=first.approved_at,
        expires_at=first.expires_at,
    )
    adaptive_row = storage.get_content_review_resume_approval(
        approval_ref=first.approval_ref,
    )
    assert adaptive_row is not None
    assert json.loads(str(adaptive_row["approval_json"]))["reviewer"][
        "inference_config"
    ]["thinking"] == {"type": "adaptive"}

    from app.storage.db import initialize_database
    from app.storage.repositories import SqliteStorage

    second_settings = replace(settings, db_path=tmp_path / "legacy-thinking.db")
    initialize_database(second_settings.db_path)
    second_storage = SqliteStorage.open(second_settings.db_path)
    second_storage.ensure_account(account)
    second_state = _failed_article(
        second_storage, second_settings, account, job="pr46-sql-legacy",
    )
    second = _authority(second_state, suffix="sql-legacy")
    legacy = json.loads(str(adaptive_row["approval_json"]))
    legacy.update({
        "approval_ref": second.approval_ref,
        "job_id": second.job_id,
        "run_id": str(second_state["content"]["run_id"]),
        "content_id": second.content_id,
        "source_draft_fingerprint": second.draft_fingerprint,
        "initial_review_execution_ref": second.initial_review_execution_ref,
        "writer_execution_ref": second.writer_execution_ref,
        "post_review_execution_ref": second.post_review_execution_ref,
    })
    legacy["reviewer"]["inference_config"]["thinking"] = {
        "type": "enabled", "budget_tokens": 2048,
    }
    legacy["writer"]["inference_config"]["thinking"] = {
        "type": "enabled", "budget_tokens": 4096,
    }
    legacy_json = json.dumps(
        legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    with pytest.raises(sqlite3.IntegrityError, match="exact terminal chain"):
        second_storage.conn.execute(
            "INSERT INTO content_review_resume_approvals (approval_ref,job_id,"
            "run_id,content_id,source_draft_fingerprint,"
            "initial_review_execution_ref,writer_execution_ref,"
            "post_review_execution_ref,reviewer_provider,reviewer_model_id,"
            "writer_provider,writer_model_id,reviewer_max_output_tokens,"
            "writer_max_output_tokens,reviewer_max_cost_usd,writer_max_cost_usd,"
            "chain_cap_usd,daily_limit_usd,monthly_limit_usd,approved_by,"
            "approved_at,expires_at,consumed_at,approval_json,"
            "approval_fingerprint,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?)",
            (
                second.approval_ref, second.job_id,
                str(second_state["content"]["run_id"]), second.content_id,
                second.draft_fingerprint, second.initial_review_execution_ref,
                second.writer_execution_ref, second.post_review_execution_ref,
                "ANTHROPIC", "claude-opus-5", "ANTHROPIC", "claude-opus-5",
                8192, 8192, "0.300000", "0.300000", "1.000000",
                "2.000000", "40.000000", second.approved_by,
                second.approved_at, second.expires_at, legacy_json,
                hashlib.sha256(legacy_json.encode("utf-8")).hexdigest(),
                second.approved_at,
            ),
        )
    second_storage.conn.rollback()
    second_storage.close()


def test_27_segment_maximal_contract_and_long_reason_are_accepted():
    segments = tuple(
        DraftClaimSegment(
            ordinal=index,
            segment_id=f"segment-{index:02d}",
            fingerprint=hashlib.sha256(f"segment-{index}".encode()).hexdigest(),
            text=("A deliberately substantial draft segment. " * 20).strip(),
        )
        for index in range(1, 28)
    )
    payload = {
        "reviewer_version": REVIEWER_VERSION,
        "entries": [
            {
                "segment_id": segment.segment_id,
                "segment_fingerprint": segment.fingerprint,
                "classification": "ARGUMENT_OR_INFERENCE",
                "evidence_ids": [],
                "reason": (
                    "This reason intentionally contains considerably more than "
                    "twelve words yet preserves every required classification field"
                ),
                "outcome": "PASS",
                "contains_external_fact": False,
            }
            for segment in segments
        ],
        "document_review": _clean_document_review(),
    }
    parsed, document_review = parse_reviewer_response(json.dumps(payload), segments=segments)
    assert len(parsed) == 27
    assert all(len(entry.reason.split()) > 12 for entry in parsed)
    assert document_review.approved is True


def test_safe_diagnostic_artifact_redacts_credentials_and_is_bounded():
    secret = "sk-ant-this_must_never_survive_123456"
    artifact = safe_reviewer_response_artifact(
        f'{{"api_key":"{secret}","authorization":"Bearer abcdefghijklmnop"}}'
    )
    assert secret not in artifact["redacted_text"]
    assert "abcdefghijklmnop" not in artifact["redacted_text"]
    assert artifact["response_bytes"] > 0
    assert len(str(artifact["response_sha256"])) == 64


def _failed_article(storage, settings, account, *, job: str):
    _, outcome = _run(
        storage,
        settings,
        account,
        job=job,
        writer=WriterTransport(),
        reviewer=ReviewerTransport(text="not-json"),
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    assert state["content"]["status"] in {"FAILED", "NEEDS_VERIFICATION"}
    assert len(state["drafts"]) == 1
    return state


def _authority(state, *, suffix: str) -> ReviewOnlyAuthority:
    job_id = str(state["job"]["id"])
    return ReviewOnlyAuthority(
        job_id=job_id,
        content_id=int(state["content"]["id"]),
        draft_fingerprint=str(state["drafts"][0]["draft_fingerprint"]),
        approval_ref=f"review-only-approval-{suffix}",
        initial_review_execution_ref=f"review-only-initial-{suffix}",
        writer_execution_ref=f"{job_id}:content_draft:2",
        post_review_execution_ref=f"review-only-post-{suffix}",
        approved_by="test-owner",
        approved_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(minutes=30)).isoformat(),
        cost_ceiling_usd="2.000000",
    )


def _cli_args(authority: ReviewOnlyAuthority) -> list[str]:
    return [
        "--job-id", authority.job_id,
        "--content-id", str(authority.content_id),
        "--draft-fingerprint", authority.draft_fingerprint,
        "--initial-review-execution-ref", authority.initial_review_execution_ref,
        "--writer-execution-ref", authority.writer_execution_ref,
        "--post-review-execution-ref", authority.post_review_execution_ref,
        "--approval-ref", authority.approval_ref,
        "--approved-by", authority.approved_by,
        "--cost-ceiling-usd", str(authority.cost_ceiling_usd),
        "--confirm-review-only",
    ]


class _BlockingReviewerTransport:
    def __init__(self, *, raise_error: BaseException | None = None) -> None:
        self.calls = 0
        self.raise_error = raise_error

    def __call__(self, _client, request):
        self.calls += 1
        if self.raise_error is not None:
            raise self.raise_error
        payload = json.loads(request.user_prompt)
        entries = []
        for index, segment in enumerate(payload["draft_segments"]):
            entries.append({
                "segment_id": segment["segment_id"],
                "segment_fingerprint": segment["fingerprint"],
                # An unsupported factual claim is reported honestly: the class
                # says it asserts a fact, the empty citation says nothing
                # supports it, and the outcome blocks it.
                "classification": (
                    "EVIDENCE_GROUNDED_FACT" if index == 0
                    else "ARGUMENT_OR_INFERENCE"
                ),
                "evidence_ids": [],
                "reason": "rewrite this exact segment before approval",
                "outcome": "BLOCK" if index == 0 else "PASS",
                "contains_external_fact": index == 0,
            })
        return ControlledProviderRawResponse(
            returned_model_id="claude-opus-5",
            text=json.dumps({
                "reviewer_version": REVIEWER_VERSION,
                "entries": entries,
                "document_review": _clean_document_review(),
            }),
            input_tokens=900,
            output_tokens=400,
            cache_read_tokens=0,
            cache_write_tokens=0,
            web_search_requests=0,
            stop_reason="end_turn",
            provider_request_id=f"fake-blocking-reviewer-{self.calls}",
        )


class APIConnectionError(Exception):
    """SDK-shaped uncertain failure used only by in-memory test callers."""


class _UncertainWriterTransport:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, _client, _request):
        self.calls += 1
        raise APIConnectionError("writer connection outcome is unknown")


def _today_real_cost(storage) -> Decimal:
    value = storage.conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM model_usage "
        "WHERE dry_run=0 AND created_at LIKE ?",
        (f"{NOW.isoformat()[:10]}%",),
    ).fetchone()[0]
    return Decimal(str(value))


def test_review_only_resumes_exact_draft_without_research_or_writer_attempt_one(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-resume")
    before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "topics", "research_runs", "research_source_candidates",
            "evidence_retrievals", "content_writer_intents", "content_drafts",
        )
    }
    factory = _SdkFactory()
    result = run_controlled_article_review_only(
        settings=replace(settings, db_path=settings.db_path),
        authority=_authority(state, suffix="success"),
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=factory,
        clock=FixedClock(NOW),
    )
    after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in before
    }
    assert before == after
    assert result.decision is PipelineDecision.PASS
    assert result.final_status.value == "PENDING_APPROVAL"
    assert result.writer_attempt_no == result.review_no == 1
    assert result.draft_fingerprint == str(state["drafts"][0]["draft_fingerprint"])
    assert result.writer_attempts == 1 and result.reviews == 1
    assert len(factory.messages.stream_calls) == 1
    row = storage.conn.execute(
        "SELECT * FROM content_review_resume_executions WHERE execution_ref=?",
        (result.initial_review_execution_ref,),
    ).fetchone()
    assert row["outcome"] == "SUCCESS"
    assert row["cost_usd"] == "0.014500"
    assert row["returned_model_id"] == "claude-opus-5"
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_approvals "
        "WHERE approval_ref=? AND consumed_at IS NOT NULL",
        (result.approval_ref,),
    ).fetchone()[0] == 1
    approval = storage.conn.execute(
        "SELECT approval_json FROM content_review_resume_approvals WHERE approval_ref=?",
        (result.approval_ref,),
    ).fetchone()
    approval_payload = json.loads(approval["approval_json"])
    assert approval_payload["reviewer"]["inference_config"] == (
        ARTICLE_REVIEWER_INFERENCE_CONFIG.payload()
    )
    assert approval_payload["writer"]["inference_config"] == (
        ARTICLE_WRITER_INFERENCE_CONFIG.payload()
    )


def test_interrupted_review_only_stream_is_unknown_once_and_never_retried(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-broken")
    factory = _SdkFactory(failure=ConnectionError("stream disconnected"))
    authority = _authority(state, suffix="broken")
    with pytest.raises(ConnectionError, match="stream disconnected"):
        run_controlled_article_review_only(
            settings=settings,
            authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=factory,
            clock=FixedClock(NOW),
        )
    assert len(factory.messages.stream_calls) == 1
    row = storage.conn.execute(
        "SELECT * FROM content_review_resume_executions WHERE execution_ref=?",
        (authority.initial_review_execution_ref,),
    ).fetchone()
    assert row["outcome"] == "NEEDS_VERIFICATION"
    assert row["cost_usd"] is None
    assert row["input_tokens"] is None and row["output_tokens"] is None
    with pytest.raises(Exception):
        run_controlled_article_review_only(
            settings=settings,
            authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=factory,
            clock=FixedClock(NOW),
        )
    assert len(factory.messages.stream_calls) == 1


def test_changed_inference_config_after_approval_conflicts_before_sdk(
    storage, settings, account, monkeypatch,
):
    import app.content.review_only as review_module
    import app.llm.anthropic_provider_contract as provider_contract

    state = _failed_article(storage, settings, account, job="pr46-inference-conflict")
    authority = _authority(state, suffix="inference-conflict")
    original_review = review_module._review_once_or_resume

    def crash_before_sdk(**_kwargs):
        raise RuntimeError("stop after immutable approval")

    monkeypatch.setattr(review_module, "_review_once_or_resume", crash_before_sdk)
    with pytest.raises(RuntimeError, match="immutable approval"):
        run_controlled_article_review_only(
            settings=settings, authority=authority, clock=FixedClock(NOW),
        )
    monkeypatch.setattr(review_module, "_review_once_or_resume", original_review)
    monkeypatch.setattr(
        provider_contract,
        "ARTICLE_REVIEWER_INFERENCE_CONFIG",
        AnthropicInferenceConfig(thinking_type="adaptive", effort="medium"),
    )
    caller = ReviewerTransport()
    with pytest.raises(Exception, match="CONTENT_REVIEW_APPROVAL_CONFLICT"):
        run_controlled_article_review_only(
            settings=settings,
            authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=caller,
            clock=FixedClock(NOW),
        )
    assert caller.calls == 0


def test_review_only_honours_unresolved_full_reservation_before_sdk(
    storage, settings, account,
):
    _, outcome = _run(
        storage,
        settings,
        account,
        job="pr46-unresolved-block",
        writer=WriterTransport(),
        reviewer=ReviewerTransport(raise_error=ConnectionError("unknown result")),
    )
    state = storage.get_content_pipeline_state(outcome.job_id)
    exposure = storage.unresolved_provider_exposure()
    assert exposure > 0
    factory = _SdkFactory()
    with pytest.raises(ReviewOnlyError) as blocked:
        run_controlled_article_review_only(
            settings=settings,
            authority=_authority(state, suffix="exposure-block"),
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=factory,
            clock=FixedClock(NOW),
        )
    assert blocked.value.code == "REVIEW_ONLY_RECONCILIATION_REQUIRED"
    assert f"{exposure:.6f}" in blocked.value.detail
    assert factory.calls == [] and factory.messages.stream_calls == []


def test_review_only_composition_has_no_earlier_stage_or_publication_imports():
    import app.content.review_only as module

    source = inspect.getsource(module)
    for forbidden in (
        "topic_generation", "source_discovery", "controlled_fetch",
        "research.pipeline",
        "publication.service", "substack",
    ):
        assert forbidden not in source
    assert "resume_writer_attempt_two_only=True" in source
    assert "content_draft:2" in source


def test_rewrite_once_runs_exactly_canonical_writer_two_then_post_review(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-rewrite-pass")
    authority = _authority(state, suffix="rewrite-pass")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    protected = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "topics", "research_runs", "research_source_candidates",
            "evidence_retrievals", "controlled_fetch_attempts",
        )
    }

    result = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT),
        authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory,
        writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory,
        post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )

    assert result.final_status.value == "PENDING_APPROVAL"
    assert result.writer_attempts == result.reviews == 2
    assert result.writer_attempt_no == result.review_no == 2
    assert result.draft_fingerprint != authority.draft_fingerprint
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)
    state_after = storage.get_content_pipeline_state(authority.job_id)
    assert [int(row["attempt_no"]) for row in state_after["attempts"]] == [1, 2]
    assert [int(row["attempt_no"]) for row in state_after["drafts"]] == [1, 2]
    assert state_after["attempts"][1]["request_id"] == authority.writer_execution_ref
    intent2 = json.loads(str(state_after["intents"][1]["intent_json"]))
    frozen = storage.assert_content_snapshot(
        str(state_after["content"]["account_id"]), authority.content_id,
    )
    assert intent2["attempt_no"] == 2
    assert intent2["rewrite_of_draft_fingerprint"] == authority.draft_fingerprint
    assert any(item["outcome"] == "BLOCK" for item in intent2["rewrite_feedback"])
    assert intent2["frozen_input_sha256"] == frozen.input_sha256
    assert intent2["evidence_manifest_sha256"] == frozen.evidence_manifest_sha256
    assert {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in protected
    } == protected
    assert storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE content_id=? AND attempt_no=1",
        (authority.content_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE content_id=? AND attempt_no=2",
        (authority.content_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_executions WHERE content_id=?",
        (authority.content_id,),
    ).fetchone()[0] == 2


@pytest.mark.parametrize("rewrite", [False, True])
def test_operator_cli_main_reports_approve_and_rewrite_success_without_traceback(
    storage, settings, account, monkeypatch, capsys, rewrite,
):
    import scripts.run_article_review_only_live as cli
    import app.content.review_only as review_module

    state = _failed_article(
        storage, settings, account, job=f"pr46-cli-{'rewrite' if rewrite else 'approve'}",
    )
    authority = _authority(state, suffix=f"cli-{'rewrite' if rewrite else 'approve'}")
    initial = _BlockingReviewerTransport() if rewrite else ReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings, project_root=ROOT))
    monkeypatch.setattr(cli, "SystemClock", lambda: FixedClock(NOW))

    def controlled_runner(**kwargs):
        return review_module.run_controlled_article_review_only(
            **kwargs,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
            writer_sdk_factory=_sdk_factory,
            writer_caller=writer,
            post_reviewer_sdk_factory=_sdk_factory,
            post_reviewer_caller=post,
        )

    monkeypatch.setattr(cli, "run_controlled_article_review_only", controlled_runner)
    assert cli.main(_cli_args(authority)) == 0
    report = json.loads(capsys.readouterr().out)
    expected_stage = 2 if rewrite else 1
    assert report["status"] == "REVIEW_ONLY_COMPLETE"
    assert report["writer_attempt_no"] == expected_stage
    assert report["review_no"] == expected_stage
    assert len(report["draft_fingerprint"]) == 64
    assert report["final_status"] == "PENDING_APPROVAL"
    assert report["publication_reachable"] is False
    assert initial.calls == 1
    assert writer.calls == (1 if rewrite else 0)
    assert post.calls == (1 if rewrite else 0)


def test_operator_cli_resume_reuses_immutable_approval_after_clock_shift(
    storage, settings, account, monkeypatch, capsys,
):
    import scripts.run_article_review_only_live as cli
    import app.content.review_only as review_module

    state = _failed_article(storage, settings, account, job="pr46-cli-resume")
    authority = _authority(state, suffix="cli-resume")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    clocks = [FixedClock(NOW)]
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings, project_root=ROOT))
    monkeypatch.setattr(cli, "SystemClock", lambda: clocks[0])

    def controlled_runner(**kwargs):
        return review_module.run_controlled_article_review_only(
            **kwargs,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
            writer_sdk_factory=_sdk_factory,
            writer_caller=writer,
            post_reviewer_sdk_factory=_sdk_factory,
            post_reviewer_caller=post,
        )

    monkeypatch.setattr(cli, "run_controlled_article_review_only", controlled_runner)
    original_begin = review_module.SqliteStorage.begin_content_review_resume_session
    crashed = {"done": False}

    def crash_once(*args, **kwargs):
        if not crashed["done"]:
            crashed["done"] = True
            raise RuntimeError("simulated CLI crash after initial review")
        return original_begin(*args, **kwargs)

    monkeypatch.setattr(
        review_module.SqliteStorage, "begin_content_review_resume_session", crash_once,
    )
    with pytest.raises(RuntimeError, match="simulated CLI crash"):
        cli.main(_cli_args(authority))
    approval_before = storage.conn.execute(
        "SELECT approval_json,approval_fingerprint,approved_at,expires_at "
        "FROM content_review_resume_approvals WHERE approval_ref=?",
        (authority.approval_ref,),
    ).fetchone()
    assert approval_before is not None
    capsys.readouterr()

    clocks[0] = FixedClock(NOW + timedelta(minutes=5))
    assert cli.main(_cli_args(authority)) == 0
    report = json.loads(capsys.readouterr().out)
    approval_after = storage.conn.execute(
        "SELECT approval_json,approval_fingerprint,approved_at,expires_at "
        "FROM content_review_resume_approvals WHERE approval_ref=?",
        (authority.approval_ref,),
    ).fetchone()
    assert tuple(approval_after) == tuple(approval_before)
    assert report["writer_attempt_no"] == report["review_no"] == 2
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)


def test_operator_cli_changed_or_expired_resume_stops_before_sdk(
    storage, settings, account, monkeypatch, capsys,
):
    import scripts.run_article_review_only_live as cli
    import app.content.review_only as review_module

    state = _failed_article(storage, settings, account, job="pr46-cli-expiry")
    authority = _authority(state, suffix="cli-expiry")
    initial = _BlockingReviewerTransport()
    clocks = [FixedClock(NOW)]
    original_begin = review_module.SqliteStorage.begin_content_review_resume_session
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings, project_root=ROOT))
    monkeypatch.setattr(cli, "SystemClock", lambda: clocks[0])

    def controlled_runner(**kwargs):
        return review_module.run_controlled_article_review_only(
            **kwargs,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
        )

    monkeypatch.setattr(cli, "run_controlled_article_review_only", controlled_runner)
    monkeypatch.setattr(
        review_module.SqliteStorage,
        "begin_content_review_resume_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated CLI crash after initial review")
        ),
    )
    with pytest.raises(RuntimeError):
        cli.main(_cli_args(authority))
    capsys.readouterr()

    changed = _cli_args(authority)
    changed[changed.index("--draft-fingerprint") + 1] = "0" * 64
    assert cli.main(changed) == 2
    changed_report = json.loads(capsys.readouterr().out)
    assert changed_report["code"] == "REVIEW_ONLY_APPROVAL_CONTRACT_MISMATCH"
    assert initial.calls == 1

    monkeypatch.setattr(
        review_module.SqliteStorage,
        "begin_content_review_resume_session",
        original_begin,
    )
    clocks[0] = FixedClock(NOW + timedelta(minutes=31))
    assert cli.main(_cli_args(authority)) == 2
    expired_report = json.loads(capsys.readouterr().out)
    assert expired_report["code"] == "CONTENT_REVIEW_APPROVAL_EXPIRED"
    assert initial.calls == 1


def test_post_rewrite_second_rewrite_is_terminal_and_never_creates_attempt_three(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-rewrite-stop")
    authority = _authority(state, suffix="rewrite-stop")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = _BlockingReviewerTransport()

    result = run_controlled_article_review_only(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory,
        writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory,
        post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )

    assert result.final_status.value == "FAILED"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)
    assert storage.conn.execute(
        "SELECT count(*) FROM content_writer_attempts WHERE content_id=?",
        (authority.content_id,),
    ).fetchone()[0] == 2
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_executions WHERE content_id=?",
        (authority.content_id,),
    ).fetchone()[0] == 2
    with pytest.raises(Exception):
        storage.conn.execute(
            "INSERT INTO content_writer_attempts (request_id,intent_id,job_id,run_id,"
            "content_id,account_id,stage,attempt_no,call_mode,provider,model,created_at) "
            "SELECT 'illegal-third',intent_id,job_id,run_id,content_id,account_id,"
            "stage,3,call_mode,provider,model,created_at FROM content_writer_attempts "
            "WHERE content_id=? LIMIT 1",
            (authority.content_id,),
        )
    storage.conn.rollback()


def test_resume_after_complete_chain_performs_no_provider_call(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-idempotent")
    authority = _authority(state, suffix="idempotent")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory,
        writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory,
        post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )
    first = run_controlled_article_review_only(**kwargs)
    second = run_controlled_article_review_only(**kwargs)
    assert first.final_status == second.final_status
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)


def test_chain_cap_blocks_before_initial_sdk(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-review-cap")
    authority = replace(_authority(state, suffix="cap"), cost_ceiling_usd="0.900000")
    initial = ReviewerTransport()
    with pytest.raises(ReviewOnlyError) as blocked:
        run_controlled_article_review_only(
            settings=replace(settings, project_root=ROOT), authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
            clock=FixedClock(NOW),
        )
    assert blocked.value.code == "REVIEW_ONLY_CHAIN_CAP_TOO_LOW"
    assert initial.calls == 0


def test_uncertain_writer_two_is_terminal_without_post_review_or_retry(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-writer-unknown")
    authority = _authority(state, suffix="writer-unknown")
    initial = _BlockingReviewerTransport()
    writer = _UncertainWriterTransport()
    post = ReviewerTransport()
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )

    first = run_controlled_article_review_only(**kwargs)
    second = run_controlled_article_review_only(**kwargs)

    assert first.final_status.value == second.final_status.value == "NEEDS_VERIFICATION"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 0)
    attempt = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE request_id=?",
        (authority.writer_execution_ref,),
    ).fetchone()
    assert attempt["status"] == "NEEDS_RECONCILIATION"
    assert attempt["actual_cost_usd"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM content_review_resume_executions "
        "WHERE content_id=? AND review_no=2", (authority.content_id,),
    ).fetchone()[0] == 0


def test_uncertain_post_review_is_terminal_without_any_replay(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-post-unknown")
    authority = _authority(state, suffix="post-unknown")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport(
        raise_error=APIConnectionError("post-review connection outcome is unknown"),
    )
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )

    with pytest.raises(APIConnectionError):
        run_controlled_article_review_only(**kwargs)
    rerun = run_controlled_article_review_only(**kwargs)

    assert rerun.final_status.value == "NEEDS_VERIFICATION"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)
    review = storage.conn.execute(
        "SELECT * FROM content_review_resume_executions "
        "WHERE execution_ref=?", (authority.post_review_execution_ref,),
    ).fetchone()
    assert review["outcome"] == "NEEDS_VERIFICATION"
    assert review["cost_usd"] is None


def test_resume_after_durable_initial_review_does_not_repeat_it(
    storage, settings, account, monkeypatch,
):
    import app.content.review_only as module

    state = _failed_article(storage, settings, account, job="pr46-resume-initial")
    authority = _authority(state, suffix="resume-initial")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    original = module.SqliteStorage.begin_content_review_resume_session

    def crash_after_initial(*_args, **_kwargs):
        raise RuntimeError("simulated process stop after durable initial review")

    monkeypatch.setattr(
        module.SqliteStorage, "begin_content_review_resume_session", crash_after_initial,
    )
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )
    with pytest.raises(RuntimeError, match="after durable initial"):
        run_controlled_article_review_only(**kwargs)
    monkeypatch.setattr(
        module.SqliteStorage, "begin_content_review_resume_session", original,
    )

    result = run_controlled_article_review_only(**kwargs)
    assert result.final_status.value == "PENDING_APPROVAL"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)


def test_resume_after_durable_writer_two_does_not_repeat_writer(
    storage, settings, account, monkeypatch,
):
    import app.content.review_only as module

    state = _failed_article(storage, settings, account, job="pr46-resume-writer")
    authority = _authority(state, suffix="resume-writer")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    original = module.run_offline_content_pipeline

    def crash_after_draft(*args, **kwargs):
        def fault(point):
            if point == "DRAFT_PERSISTED":
                raise RuntimeError("simulated process stop after durable writer two")
        return original(*args, **dict(kwargs, fault_point=fault))

    monkeypatch.setattr(module, "run_offline_content_pipeline", crash_after_draft)
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )
    with pytest.raises(RuntimeError, match="after durable writer two"):
        run_controlled_article_review_only(**kwargs)
    monkeypatch.setattr(module, "run_offline_content_pipeline", original)

    result = run_controlled_article_review_only(**kwargs)
    assert result.final_status.value == "PENDING_APPROVAL"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)


def test_resume_after_durable_post_review_does_not_repeat_any_stage(
    storage, settings, account, monkeypatch,
):
    import app.content.review_only as module

    state = _failed_article(storage, settings, account, job="pr46-resume-post")
    authority = _authority(state, suffix="resume-post")
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    original = module._PostRewriteReview.review

    def crash_after_review(self, **kwargs):
        original(self, **kwargs)
        raise RuntimeError("simulated process stop after durable post review")

    monkeypatch.setattr(module._PostRewriteReview, "review", crash_after_review)
    kwargs = dict(
        settings=replace(settings, project_root=ROOT), authority=authority,
        api_key_provider=lambda: "fake-never-sent",
        initial_reviewer_sdk_factory=_sdk_factory,
        initial_reviewer_caller=initial,
        writer_sdk_factory=_sdk_factory, writer_caller=writer,
        post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
        clock=FixedClock(NOW),
    )
    with pytest.raises(RuntimeError, match="after durable post review"):
        run_controlled_article_review_only(**kwargs)
    monkeypatch.setattr(module._PostRewriteReview, "review", original)

    result = run_controlled_article_review_only(**kwargs)
    assert result.final_status.value == "PENDING_APPROVAL"
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 1)


def test_global_budget_blocks_before_writer_two(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-budget-writer")
    authority = _authority(state, suffix="budget-writer")
    existing = _today_real_cost(storage)
    limited = replace(
        settings, project_root=ROOT,
        max_daily_cost_usd=float(existing + Decimal("0.330000")),
    )
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    with pytest.raises(Exception):
        run_controlled_article_review_only(
            settings=limited, authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
            writer_sdk_factory=_sdk_factory, writer_caller=writer,
            post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
            clock=FixedClock(NOW),
        )
    assert (initial.calls, writer.calls, post.calls) == (1, 0, 0)



def test_global_budget_blocks_before_post_review(
    storage, settings, account,
):
    state = _failed_article(storage, settings, account, job="pr46-budget-post")
    authority = _authority(state, suffix="budget-post")
    existing = _today_real_cost(storage)
    limited = replace(
        settings, project_root=ROOT,
        max_daily_cost_usd=float(existing + Decimal("0.350000")),
    )
    initial = _BlockingReviewerTransport()
    writer = WriterTransport()
    post = ReviewerTransport()
    with pytest.raises(Exception):
        run_controlled_article_review_only(
            settings=limited, authority=authority,
            api_key_provider=lambda: "fake-never-sent",
            initial_reviewer_sdk_factory=_sdk_factory,
            initial_reviewer_caller=initial,
            writer_sdk_factory=_sdk_factory, writer_caller=writer,
            post_reviewer_sdk_factory=_sdk_factory, post_reviewer_caller=post,
            clock=FixedClock(NOW),
        )
    assert (initial.calls, writer.calls, post.calls) == (1, 1, 0)
