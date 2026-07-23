"""SqliteStorage — konkretna implementacja StoragePort na SQLite."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from app.content.foundation import (
    CONTENT_EXECUTION,
    CONTENT_PROVIDER_STAGE,
    ContentCallIntent,
    ContentContractError,
    ContentEvaluation,
    ContentInitialization,
    ContentInitializationFaultPoint,
    ContentItem,
    ContentPreparationRequest,
    ContentRun,
    ContentStatus,
    ContentTransitionResult,
    ContentType,
    FrozenContentInput,
    FrozenEvidenceItem,
    canonical_json,
    canonicalize_content_job_payload,
    content_job_payload,
    sha256_text,
)
from app.content.contracts import (
    ContentPlan,
    DraftEvaluation,
    FakeDraft,
    WriterIntent,
)
from app.core.clock import Clock
from app.core.money import decimal_from, quantize_usd, sum_usd
from app.core.security_flags import SECURITY_FLAG_DEFAULTS
from app.models import (
    Account,
    CONTROLLED_FETCH_ACTION_TYPE,
    ControlledFetchApproval,
    ControlledFetchAttempt,
    ControlledFetchAttemptStatus,
    ControlledFetchFailureOutcome,
    ControlledFetchInitialization,
    ControlledFetchTransportAuthorization,
    _issue_controlled_fetch_transport_authorization,
    DurableProviderAttemptContext,
    EVIDENCE_RESEARCH_ACTION_TYPE,
    EvidenceExcerpt,
    EvidenceResearchApproval,
    EvidenceRetrieval,
    EvidenceRetrievalStatus,
    ExecutionResolution,
    FinancialResolution,
    Job,
    JobEnqueueResult,
    JobExecutionContext,
    JobEnqueueContext,
    JobKind,
    JobLease,
    JobRecoveryResult,
    JobReservation,
    JobStatus,
    ModelUsage,
    OperationalFieldStatus,
    OperationalFlagState,
    OperationalReport,
    OperationalScalar,
    ProviderAttempt,
    ProviderAttemptReconciliationResult,
    ProviderAttemptStatus,
    ReconciliationEvent,
    ReconciliationEventType,
    ReconciliationFaultPoint,
    ReconciliationPreview,
    ResearchExecutionFailureOutcome,
    ResearchCard,
    ResearchRecommendation,
    ResearchRun,
    ResearchRunInitialization,
    ResearchFlow,
    ResearchRunStatus,
    ResearchSourceRecord,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    RunReaperResult,
    RunStatus,
    Source,
    SourceCandidateRecord,
    SourceCandidateRetryResult,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    StagedFinalizationContext,
    StagedFinalizationFaultPoint,
    StagedFinalizationMode,
    SystemFlag,
    GeneratedTopicLineage,
    Topic,
    TopicGenerationApproval,
    TopicGenerationCandidate,
    TopicGenerationInitialization,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    AmountBelowMinimumPrecisionError,
    BudgetReservationError,
    ContentFoundationError,
    ContentSnapshotError,
    ControlledFetchAuthorizationError,
    ControlledFetchRetrievalNotOk,
    EvidenceResearchAuthorizationError,
    JobConflictError,
    JobPayloadValidationError,
    JobRunConflictError,
    JobRunReconciliationRequired,
    JobRunRelationError,
    LifecycleTransitionError,
    ModelUsageRequestIdError,
    ProviderAttemptOverReservationError,
    ProviderAttemptReconciliationError,
    ProviderAttemptReconciliationRequired,
    ReconciliationPreviewStaleError,
    ResearchTopicIntegrityError,
    StaleJobExecutionError,
    SystemFlagError,
    TopicGenerationAuthorizationError,
    TopicGenerationResultError,
)
from app.research.durable_intent import (
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    MAX_EVIDENCE_CHARS_PER_RETRIEVAL,
    MAX_EVIDENCE_TOTAL_CHARS,
    canonicalize_durable_research_payload,
    durable_execution_intent_fingerprint,
    frozen_execution_intent_json,
)
from app.research.offline_evidence_intent import (
    OfflineEvidenceIntentError,
    canonicalize_offline_evidence_payload,
)
from app.topics.durable_intent import (
    PROVIDER_STAGE as TOPIC_GENERATION_PROVIDER_STAGE,
    TOPIC_GENERATION_EXECUTION,
    DurableTopicGenerationIntent,
    canonicalize_topic_generation_payload,
    frozen_topic_generation_contract,
)
from app.research.controlled_fetch_intent import (
    CONTROLLED_FETCH_EXECUTION,
    ControlledFetchIntent,
    ControlledFetchIntentError,
    canonicalize_controlled_fetch_payload,
    controlled_fetch_intent_fingerprint,
)
from app.ports.fetch import FetchedDocument
from app.research.evidence import (
    EvidenceRejectionReason,
    EvidenceVerdict,
    EvidenceVerificationError,
    MAX_CANONICAL_CHARS,
    MAX_RAW_FETCH_BYTES,
    build_evidence_retrieval,
    sha256_hex,
    verify_evidence_excerpt,
)
from app.storage.db import (
    RUNTIME_SCHEMA_VERSION,
    canonical_migration_versions,
    connect,
    connect_existing_writable,
    connect_read_only,
    prepare_writable_connection,
    require_connection_schema,
    require_database_schema,
)


@dataclass(frozen=True)
class EvidenceResearchCorpus:
    """Approved evidence corpus of one durable evidence-research execution.

    Retrievale są w dokładnej kolejności zamrożonego intentu; JSON i
    fingerprint to autorytatywny snapshot z payloadu, zweryfikowany bajt-w-bajt
    z wierszem approvalu w tej samej transakcji, w której powstał ten obiekt.
    ``force_re_research`` pochodzi WYŁĄCZNIE z tego zamrożonego, zatwierdzonego
    intentu — nigdy z pamięci wywołującego.
    """

    retrievals: tuple[EvidenceRetrieval, ...]
    execution_intent_json: str
    intent_fingerprint: str
    force_re_research: bool = False


_RESEARCH_USAGE_TASKS = (
    "research",
    "research_gather",
    "research_synthesize",
    "research_discover",
    "research_extract",
    "research_synthesize_cards",
    "research_reconciliation",
)
_RESEARCH_USAGE_PLACEHOLDERS = ", ".join("?" for _ in _RESEARCH_USAGE_TASKS)
# The canonical `model_usage.task` of one paid topic-generation request.  It is
# deliberately NOT a member of _RESEARCH_USAGE_TASKS: research cost caches and
# topic-generation cost caches must never contribute to one another.  Both live
# in the one shared `model_usage` ledger; reconciliation selects the exact task
# set from the durable job kind.
TOPIC_GENERATION_USAGE_TASK = "topics"
# Formal, closed contract for the task of a canonical usage the resolver may bind
# to a reconciled attempt.  Never widened by a ``startswith('research')`` prefix.
_RECONCILIATION_RESEARCH_USAGE_TASKS = frozenset(_RESEARCH_USAGE_TASKS)
# WAVE 1A lifecycle contract: a terminal financial outcome (CHARGED_KNOWN or
# NOT_CHARGED) must be paired with a terminal execution outcome, never with
# MANUAL_REVIEW_REMAINS_REQUIRED (which would strand a terminal attempt on a job
# that stays NEEDS_VERIFICATION).  MANUAL lives only on the append-only
# CHARGE_UNKNOWN observation path, which never terminalizes attempt or job.
_ALLOWED_RECONCILIATION_EXECUTION_RESOLUTIONS = {
    FinancialResolution.CHARGED_KNOWN: frozenset({
        ExecutionResolution.EXECUTION_FAILED,
        ExecutionResolution.RESULT_ALREADY_FINALIZED,
    }),
    FinancialResolution.NOT_CHARGED: frozenset({
        ExecutionResolution.EXECUTION_FAILED,
        ExecutionResolution.RESULT_ALREADY_FINALIZED,
    }),
    FinancialResolution.CHARGE_UNKNOWN: frozenset({
        ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
    }),
}
# WAVE 1A (W1A-VERIFY-01): the maintenance reaper terminalizes an orphaned stale
# run to STOPPED while its job stays NEEDS_VERIFICATION.  An EXECUTION_FAILED
# reconciliation must therefore accept STOPPED as an already-terminal non-success
# run — alongside RUNNING (the resolver won the race) and FAILED (idempotent-
# compatible) — and drive it to FAILED.  SUCCESS and every other status stay
# fail-closed; RESULT_ALREADY_FINALIZED owns the finalized-run path.  This single
# tuple feeds BOTH the Python precondition and the compare-and-swap UPDATE so the
# two can never drift (the drift between them was the original defect).
_EXECUTION_FAILED_RUN_STATUSES = (
    RunStatus.RUNNING.value,
    RunStatus.STOPPED.value,
    RunStatus.FAILED.value,
)
# W1A-AUD-04: the only two enumerated crash-window escalation reasons.  A
# RESERVED attempt provably never crossed the request boundary; a
# REQUEST_STARTED attempt may carry a real, unrecorded provider charge.
_LEASE_EXPIRED_BEFORE_REQUEST_STARTED = "LEASE_EXPIRED_BEFORE_REQUEST_STARTED"
_LEASE_EXPIRED_AFTER_REQUEST_STARTED = "LEASE_EXPIRED_AFTER_REQUEST_STARTED"
_UNEXPECTED_FAILURE_BEFORE_REQUEST_STARTED = (
    "UNEXPECTED_EXECUTION_FAILURE_BEFORE_REQUEST_STARTED"
)
_UNEXPECTED_FAILURE_AFTER_REQUEST_STARTED = (
    "UNEXPECTED_EXECUTION_FAILURE_AFTER_REQUEST_STARTED"
)
_ESCALATION_OPERATOR = "maintenance-recovery"
_WORKER_FAILURE_ESCALATION_OPERATOR = "worker-failure-boundary"
_SETTLED_EXECUTION_RECOVERY_OPERATOR = "maintenance-settled-execution-recovery"
_SETTLED_EXECUTION_RECOVERY_NOTE = (
    "Automatic execution-only recovery after a known SETTLED provider outcome."
)
_TOPIC_SETTLED_EXECUTION_RECOVERY_NOTE = (
    "Settled provider execution recovered before topic result finalization."
)
_SETTLED_EXECUTION_RECOVERY_BLOCKED = "SETTLED_EXECUTION_RECOVERY_BLOCKED"

_ACTIVE_JOB_STATUSES = (
    JobStatus.QUEUED.value,
    JobStatus.LEASED.value,
    JobStatus.RUNNING.value,
    JobStatus.NEEDS_VERIFICATION.value,
)
_TERMINAL_JOB_STATUSES = (
    JobStatus.DONE.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
)
_RELEASABLE_RESERVATION_STATUSES = (
    JobStatus.QUEUED.value,
    JobStatus.LEASED.value,
    JobStatus.RUNNING.value,
)
_EXECUTABLE_JOB_STATUSES = (
    JobStatus.LEASED.value,
    JobStatus.RUNNING.value,
)
_STALE_RUN_REAPER_REASON = "STALE_RUN_REAPER: stale RUNNING run has no executable job lease."
_LOGGER = logging.getLogger(__name__)


def _ts(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _ts_precise(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _persisted_ts(dt: datetime) -> str:
    return _ts_precise(dt) if dt.microsecond else _ts(dt)


def _money(value: object, *, positive: bool, label: str) -> Decimal:
    """Canonical six-decimal money value without binary-float boundary errors."""
    try:
        amount = decimal_from(value, label=label)
    except ValueError as exc:
        raise BudgetReservationError(f"{label} must be a finite numeric amount.") from exc
    if not amount.is_finite() or (amount <= 0 if positive else amount < 0):
        relation = "positive" if positive else "non-negative"
        raise BudgetReservationError(f"{label} must be finite and {relation}.")
    canonical = quantize_usd(amount, label=label)
    if positive and canonical == Decimal("0.000000"):
        raise AmountBelowMinimumPrecisionError(
            f"{label} is below the minimum USD precision of 0.000001 (ROUND_HALF_UP)."
        )
    return canonical


def _money_sum(values: Sequence[object], *, label: str) -> Decimal:
    """Sum decimal-string inputs first and apply the USD contract once."""
    try:
        return sum_usd(values, label=label)
    except ValueError as exc:
        raise BudgetReservationError(f"{label} must be a finite numeric amount.") from exc


def _money_equal(left: object, right: object, *, label: str) -> bool:
    """Compare persisted USD values only after the common Decimal boundary."""
    try:
        return (
            _money(left, positive=False, label=label)
            == _money(right, positive=False, label=label)
        )
    except BudgetReservationError:
        return False


def _is_positive_money(value: object, *, label: str) -> bool:
    try:
        _money(value, positive=True, label=label)
    except BudgetReservationError:
        return False
    return True


def _sum_money_rows(
    rows: Iterable[sqlite3.Row],
    column: str,
    *,
    label: str,
) -> Decimal:
    """Aggregate persisted REAL values as Decimal strings, never SQLite floats."""
    return _money_sum(tuple(row[column] for row in rows), label=label)


class SqliteStorage:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _current_status(self, table: str, identifier: str | int) -> str | None:
        row = self.conn.execute(
            f"SELECT status FROM {table} WHERE id=?", (identifier,),
        ).fetchone()
        return None if row is None else str(row["status"])

    def _lifecycle_error(
        self,
        *,
        table: str,
        entity: str,
        identifier: str | int,
        target_status: str,
        allowed_source_statuses: Sequence[str],
        include_flow: bool = False,
        detail: str | None = None,
    ) -> LifecycleTransitionError:
        columns = "status, flow" if include_flow else "status"
        row = self.conn.execute(
            f"SELECT {columns} FROM {table} WHERE id=?", (identifier,),
        ).fetchone()
        current = None if row is None else str(row["status"])
        if row is not None and include_flow:
            current = f"{row['flow']}:{current}"
        return LifecycleTransitionError(
            entity,
            identifier,
            target_status,
            allowed_source_statuses,
            current,
            detail=detail,
        )

    def _require_one_transition(
        self,
        cursor: sqlite3.Cursor,
        *,
        table: str,
        entity: str,
        identifier: str | int,
        target_status: str,
        allowed_source_statuses: Sequence[str],
        include_flow: bool = False,
        detail: str | None = None,
    ) -> None:
        if cursor.rowcount == 1:
            return
        if cursor.rowcount > 1:
            detail = (
                f"Integrity failure: lifecycle UPDATE changed {cursor.rowcount} rows."
            )
        raise self._lifecycle_error(
            table=table,
            entity=entity,
            identifier=identifier,
            target_status=target_status,
            allowed_source_statuses=allowed_source_statuses,
            include_flow=include_flow,
            detail=detail,
        )

    # --- fabryka ---
    @classmethod
    def open(cls, db_path: Path | str) -> "SqliteStorage":
        """Open runtime storage only after an immutable exact-schema preflight.

        This method never creates a database and never applies migrations.
        """
        # A test must never silently point a writable SQLite adapter at the
        # project's forensic/runtime database, even through a relative path or
        # a Windows junction/symlink.  Production processes do not set this
        # pytest marker and retain their explicit operational contract.
        if os.environ.get("PYTEST_CURRENT_TEST") and str(db_path) != ":memory:":
            target = (Path(__file__).resolve().parents[2] / "data" / "agent.db").resolve()
            if Path(db_path).resolve() == target:
                raise RuntimeError("Tests must not open the project data/agent.db for writing.")
        require_database_schema(db_path, required_version=RUNTIME_SCHEMA_VERSION)
        conn = connect_existing_writable(db_path)
        try:
            # Recheck on the mode=rw handle before any mutating connection setup.
            require_connection_schema(conn, required_version=RUNTIME_SCHEMA_VERSION)
            prepare_writable_connection(conn, db_path)
            return cls(conn)
        except Exception:
            conn.close()
            raise

    @classmethod
    def open_read_only(cls, db_path: Path | str) -> "SqliteStorage":
        """Open an existing database with query_only and without migrations."""
        return cls(connect_read_only(db_path))

    def close(self) -> None:
        self.conn.close()

    # --- konta ---
    def ensure_account(self, account: Account) -> None:
        self.conn.execute(
            "INSERT INTO accounts (id, name, mode, autonomy_level, active,"
            " browser_profile_path, writing_profile_path) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name, mode=excluded.mode,"
            " autonomy_level=excluded.autonomy_level, active=excluded.active,"
            " browser_profile_path=excluded.browser_profile_path,"
            " writing_profile_path=excluded.writing_profile_path",
            (
                account.id, account.display_name, account.mode.value,
                account.autonomy_level.value, int(account.active),
                account.browser_profile_path, account.writing_profile_path,
            ),
        )
        p = account.policies
        self.conn.execute(
            "INSERT INTO account_policies (account_id, daily_comment_limit, daily_note_limit,"
            " weekly_article_limit, max_per_author_per_day, require_comment_approval,"
            " require_note_approval, require_article_approval, require_restack_approval,"
            " allow_links, link_ratio_limit) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(account_id) DO UPDATE SET"
            " daily_comment_limit=excluded.daily_comment_limit,"
            " daily_note_limit=excluded.daily_note_limit,"
            " weekly_article_limit=excluded.weekly_article_limit,"
            " max_per_author_per_day=excluded.max_per_author_per_day,"
            " require_comment_approval=excluded.require_comment_approval,"
            " require_note_approval=excluded.require_note_approval,"
            " require_article_approval=excluded.require_article_approval,"
            " require_restack_approval=excluded.require_restack_approval,"
            " allow_links=excluded.allow_links, link_ratio_limit=excluded.link_ratio_limit",
            (
                account.id, p.daily_comment_limit, p.daily_note_limit, p.weekly_article_limit,
                p.max_per_author_per_day, int(p.require_comment_approval),
                int(p.require_note_approval), int(p.require_article_approval),
                int(p.require_restack_approval), int(p.allow_links), p.link_ratio_limit,
            ),
        )
        self.conn.commit()

    # --- tematy ---
    def _insert_topic(self, topic: Topic, account_id: str | None = None) -> Topic:
        """Insert one topic WITHOUT committing, so a caller can own the transaction."""
        owner = topic.account_id if account_id is None else account_id
        cur = self.conn.execute(
            "INSERT INTO topics (account_id, title, question, score, score_breakdown,"
            " status, source, duplicate_of, rejection_reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                owner, topic.title, topic.question, topic.score,
                json.dumps(topic.score_breakdown), topic.status.value,
                topic.source, topic.duplicate_of, topic.rejection_reason,
                _ts(topic.created_at),
            ),
        )
        topic.id = int(cur.lastrowid)
        topic.account_id = owner
        return topic

    def add_topic(self, account_id: str, topic: Topic) -> Topic:
        stored = self._insert_topic(topic, account_id)
        self.conn.commit()
        return stored

    def list_topics(self, account_id: str) -> Sequence[Topic]:
        rows = self.conn.execute(
            "SELECT * FROM topics WHERE account_id=? ORDER BY score DESC, id ASC",
            (account_id,),
        ).fetchall()
        result: list[Topic] = []
        for r in rows:
            result.append(Topic(
                id=r["id"], account_id=r["account_id"], title=r["title"],
                question=r["question"], score=r["score"],
                score_breakdown=json.loads(r["score_breakdown"] or "{}"),
                status=TopicStatus(r["status"]), source=r["source"],
                duplicate_of=r["duplicate_of"], rejection_reason=r["rejection_reason"],
            ))
        return result

    def list_topic_titles_for_dedup(self, account_id: str) -> list[tuple[int, str]]:
        """(id, title) aktywnych tematów konta (bez DUPLICATE) — cel deduplikacji."""
        rows = self.conn.execute(
            "SELECT id, title FROM topics WHERE account_id=? AND status != 'DUPLICATE'"
            " ORDER BY id ASC",
            (account_id,),
        ).fetchall()
        return [(r["id"], r["title"]) for r in rows]

    def list_topics_by_status(self, account_id: str, status: TopicStatus) -> Sequence[Topic]:
        return [t for t in self.list_topics(account_id) if t.status == status]

    # --- Etap 3 / WAVE C1: durable content foundation -----------------------

    @staticmethod
    def _content_item_from_row(row: sqlite3.Row) -> ContentItem:
        final_result = (
            None if row["final_result_json"] is None
            else json.loads(row["final_result_json"])
        )
        return ContentItem(
            id=int(row["id"]),
            account_id=row["account_id"],
            research_card_id=int(row["research_card_id"]),
            content_type=ContentType(row["type"]),
            status=ContentStatus(row["status"]),
            job_id=row["job_id"],
            run_id=row["run_id"],
            input_sha256=row["input_sha256"],
            intent_key=row["intent_key"],
            reason_code=row["reason_code"],
            final_result=final_result,
            score=row["score"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _content_run_from_row(row: sqlite3.Row) -> ContentRun:
        final_result = (
            None if row["final_result_json"] is None
            else json.loads(row["final_result_json"])
        )
        return ContentRun(
            run_id=row["run_id"],
            content_id=int(row["content_id"]),
            job_id=row["job_id"],
            account_id=row["account_id"],
            research_card_id=int(row["research_card_id"]),
            workflow=ContentType(row["workflow"]),
            input_sha256=row["input_sha256"],
            status=ContentStatus(row["status"]),
            reason_code=row["reason_code"],
            final_result=final_result,
            score=row["score"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
        )

    @staticmethod
    def _content_fault(
        point: ContentInitializationFaultPoint,
        callback: Callable[[ContentInitializationFaultPoint], None] | None,
    ) -> None:
        if callback is not None:
            callback(point)

    def _build_content_snapshot(
        self,
        *,
        account_id: str,
        research_card_id: int,
        content_type: ContentType,
        input_schema_version: str,
        output_schema_version: str,
        prompt_version: str,
        style_guide_version: str,
        article_brief_placeholder: dict[str, object],
    ) -> dict[str, object]:
        """Read and canonicalize one complete account-scoped evidence snapshot."""
        card = self.conn.execute(
            "SELECT rc.*,t.account_id AS topic_account_id,t.title AS topic_title,"
            "t.question AS topic_question FROM research_cards rc "
            "JOIN topics t ON t.id=rc.topic_id WHERE rc.id=?",
            (research_card_id,),
        ).fetchone()
        if card is None:
            raise ContentSnapshotError(
                "CONTENT_CARD_MISSING", "Research Card does not exist.",
            )
        if card["topic_account_id"] != account_id:
            raise ContentSnapshotError(
                "CONTENT_ACCOUNT_CARD_MISMATCH",
                "Research Card topic belongs to a different account.",
            )
        account = self.conn.execute(
            "SELECT active FROM accounts WHERE id=?", (account_id,),
        ).fetchone()
        if account is None or int(account["active"]) != 1:
            raise ContentSnapshotError(
                "CONTENT_ACCOUNT_INACTIVE", "Content requires an active account.",
            )
        if card["publication_recommendation"] != ResearchRecommendation.PROCEED.value:
            raise ContentSnapshotError(
                "CONTENT_CARD_NOT_PROCEED",
                "Only a Research Card with publication_recommendation=PROCEED is eligible.",
            )
        try:
            confirmed = json.loads(card["confirmed_claims"] or "[]")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ContentSnapshotError(
                "CONTENT_CONFIRMED_CLAIMS_INVALID",
                "Research Card confirmed_claims is not valid JSON.",
            ) from exc
        if (
            not isinstance(confirmed, list)
            or not confirmed
            or any(
                not isinstance(claim, str)
                or not claim.strip()
                or claim != claim.strip()
                for claim in confirmed
            )
        ):
            raise ContentSnapshotError(
                "CONTENT_CONFIRMED_CLAIMS_INVALID",
                "Confirmed claims must be a non-empty list of trimmed strings.",
            )

        evidence_rows = self.conn.execute(
            "SELECT sl.source_id,sl.research_card_id,sl.candidate_id,"
            "sl.research_run_id,sl.research_job_id,sl.account_id,sl.topic_id,"
            "sl.retrieval_id,sl.excerpt_id,sl.confirmed_claim_id,"
            "sl.confirmed_claim_ordinal,sl.confirmed_claim_sha256,"
            "sl.lineage_fingerprint,s.url AS source_url,s.supports_claim,"
            "ee.id AS excerpt_id,ee.claim_text,ee.claim_sha256,ee.excerpt_text,"
            "er.id AS retrieval_id,er.requested_url,er.final_url,er.canonical_sha256 "
            "FROM evidence_source_lineage sl "
            "JOIN sources s ON s.id=sl.source_id "
            "JOIN research_source_candidates c ON c.id=sl.candidate_id "
            "JOIN research_runs rr ON rr.id=sl.research_run_id "
            "JOIN jobs rj ON rj.id=sl.research_job_id "
            "JOIN evidence_excerpts ee ON ee.id=sl.excerpt_id "
            "JOIN evidence_retrievals er ON er.id=sl.retrieval_id "
            "WHERE sl.research_card_id=? AND sl.account_id=? "
            "AND sl.topic_id=? AND s.verification_status='VERIFIED' "
            "AND sl.confirmed_claim_id IS NOT NULL "
            "AND sl.confirmed_claim_ordinal IS NOT NULL "
            "AND sl.confirmed_claim_sha256 IS NOT NULL "
            "AND sl.research_job_id IS NOT NULL "
            "AND sl.lineage_fingerprint IS NOT NULL "
            "AND c.status='EXTRACTED' AND c.verification_status='VERIFIED' "
            "AND rr.account_id=? AND rr.topic_id=? "
            "AND rj.run_id=rr.id AND rj.account_id=? AND rj.topic_id=? "
            "AND rj.kind='RESEARCH' AND rj.workflow='RESEARCH' "
            "AND ee.account_id=? AND er.account_id=? AND er.status='OK' "
            "ORDER BY sl.confirmed_claim_ordinal,sl.source_id",
            (
                research_card_id, account_id, int(card["topic_id"]),
                account_id, int(card["topic_id"]), account_id,
                int(card["topic_id"]), account_id, account_id,
            ),
        ).fetchall()
        by_claim_id: dict[str, list[sqlite3.Row]] = {
            f"research-card:{research_card_id}:confirmed-claim:{ordinal}": []
            for ordinal in range(len(confirmed))
        }
        for row in evidence_rows:
            claim_ordinal = int(row["confirmed_claim_ordinal"])
            if claim_ordinal < 0 or claim_ordinal >= len(confirmed):
                raise ContentSnapshotError(
                    "CONTENT_LINEAGE_CLAIM_ID_INVALID",
                    "Evidence lineage points outside the Research Card claim list.",
                )
            claim = confirmed[claim_ordinal]
            claim_id = (
                f"research-card:{research_card_id}:"
                f"confirmed-claim:{claim_ordinal}"
            )
            lineage_preimage = {
                "account_id": account_id,
                "candidate_id": int(row["candidate_id"]),
                "confirmed_claim_id": claim_id,
                "confirmed_claim_ordinal": claim_ordinal,
                "excerpt_id": int(row["excerpt_id"]),
                "research_card_id": research_card_id,
                "research_job_id": row["research_job_id"],
                "research_run_id": row["research_run_id"],
                "retrieval_id": int(row["retrieval_id"]),
                "source_id": int(row["source_id"]),
                "topic_id": int(card["topic_id"]),
            }
            if (
                row["confirmed_claim_id"] != claim_id
                or row["confirmed_claim_sha256"] != sha256_text(claim)
                or row["claim_sha256"] != sha256_text(claim)
                or row["supports_claim"] != claim
                or row["claim_text"] != claim
                or row["lineage_fingerprint"]
                    != sha256_text(canonical_json(lineage_preimage))
            ):
                raise ContentSnapshotError(
                    "CONTENT_LINEAGE_FINGERPRINT_INVALID",
                    "Authoritative evidence lineage or one of its fingerprints drifted.",
                )
            by_claim_id[claim_id].append(row)
        missing = [
            claim_id for claim_id, rows in by_claim_id.items() if not rows
        ]
        if missing:
            raise ContentSnapshotError(
                "CONTENT_EVIDENCE_INCOMPLETE",
                f"{len(missing)} confirmed claim(s) lack authoritative evidence_source_lineage.",
            )

        items: list[FrozenEvidenceItem] = []
        ordinal = 0
        for claim_ordinal, claim in enumerate(confirmed):
            claim_id = (
                f"research-card:{research_card_id}:"
                f"confirmed-claim:{claim_ordinal}"
            )
            for row in by_claim_id[claim_id]:
                item = FrozenEvidenceItem(
                    ordinal=ordinal,
                    account_id=account_id,
                    topic_id=int(card["topic_id"]),
                    research_run_id=row["research_run_id"],
                    research_job_id=row["research_job_id"],
                    research_card_id=research_card_id,
                    confirmed_claim_id=claim_id,
                    confirmed_claim_ordinal=claim_ordinal,
                    claim_text=claim,
                    claim_sha256=sha256_text(claim),
                    candidate_id=int(row["candidate_id"]),
                    source_id=int(row["source_id"]),
                    source_url=row["source_url"],
                    source_url_sha256=sha256_text(row["source_url"]),
                    source_claim_text=row["supports_claim"],
                    source_claim_sha256=sha256_text(row["supports_claim"]),
                    excerpt_id=int(row["excerpt_id"]),
                    excerpt_text=row["excerpt_text"],
                    excerpt_sha256=sha256_text(row["excerpt_text"]),
                    retrieval_id=int(row["retrieval_id"]),
                    requested_url_sha256=sha256_text(row["requested_url"]),
                    final_url_sha256=sha256_text(row["final_url"]),
                    canonical_sha256=row["canonical_sha256"],
                    lineage_fingerprint=row["lineage_fingerprint"],
                )
                items.append(item)
                ordinal += 1

        card_columns = (
            "id", "topic_id", "question", "thesis", "mechanism", "facts_json",
            "counterargument", "citable_numbers", "visual_idea", "confidence",
            "created_at", "working_thesis", "confirmed_claims", "uncertain_claims",
            "contradictions", "source_quality_score", "publication_recommendation",
            "rejection_reason",
        )
        card_snapshot = {column: card[column] for column in card_columns}
        card_snapshot["topic_title"] = card["topic_title"]
        card_snapshot["topic_question"] = card["topic_question"]
        card_json = canonical_json(card_snapshot)
        manifest_data = [item.model_dump(mode="json") for item in items]
        manifest_json = canonical_json(manifest_data)
        brief_json = canonical_json(article_brief_placeholder)
        input_data = {
            "account_id": account_id,
            "research_card": card_snapshot,
            "content_type": content_type.value,
            "input_schema_version": input_schema_version,
            "output_schema_version": output_schema_version,
            "prompt_version": prompt_version,
            "style_guide_version": style_guide_version,
            "article_brief_placeholder": article_brief_placeholder,
            "evidence_manifest": manifest_data,
        }
        input_json = canonical_json(input_data)
        return {
            "card": card,
            "card_json": card_json,
            "manifest_json": manifest_json,
            "manifest_sha256": sha256_text(manifest_json),
            "brief_json": brief_json,
            "brief_sha256": sha256_text(brief_json),
            "input_json": input_json,
            "input_sha256": sha256_text(input_json),
            "items": tuple(items),
        }

    def _frozen_content_input_from_rows(
        self,
        row: sqlite3.Row,
        evidence_rows: Sequence[sqlite3.Row],
    ) -> FrozenContentInput:
        items = tuple(FrozenEvidenceItem(
            ordinal=int(item["ordinal"]),
            account_id=item["account_id"],
            topic_id=int(item["topic_id"]),
            research_run_id=item["research_run_id"],
            research_job_id=item["research_job_id"],
            research_card_id=int(item["research_card_id"]),
            confirmed_claim_id=item["confirmed_claim_id"],
            confirmed_claim_ordinal=int(item["confirmed_claim_ordinal"]),
            claim_text=item["claim_text"],
            claim_sha256=item["claim_sha256"],
            candidate_id=int(item["candidate_id"]),
            source_id=int(item["source_id"]),
            source_url=item["source_url"],
            source_url_sha256=item["source_url_sha256"],
            source_claim_text=item["source_claim_text"],
            source_claim_sha256=item["source_claim_sha256"],
            excerpt_id=int(item["excerpt_id"]),
            excerpt_text=item["excerpt_text"],
            excerpt_sha256=item["excerpt_sha256"],
            retrieval_id=int(item["retrieval_id"]),
            requested_url_sha256=item["requested_url_sha256"],
            final_url_sha256=item["final_url_sha256"],
            canonical_sha256=item["canonical_sha256"],
            lineage_fingerprint=item["lineage_fingerprint"],
        ) for item in evidence_rows)
        if int(row["evidence_item_count"]) != len(items):
            raise ContentSnapshotError(
                "CONTENT_EVIDENCE_COUNT_DRIFT",
                "Frozen evidence row count does not match its sealed manifest.",
            )
        return FrozenContentInput(
            content_id=int(row["content_id"]),
            account_id=row["account_id"],
            research_card_id=int(row["research_card_id"]),
            content_type=ContentType(row["content_type"]),
            input_schema_version=row["input_schema_version"],
            output_schema_version=row["output_schema_version"],
            prompt_version=row["prompt_version"],
            style_guide_version=row["style_guide_version"],
            article_brief_placeholder_json=row["article_brief_placeholder_json"],
            article_brief_placeholder_sha256=row["article_brief_placeholder_sha256"],
            research_card_snapshot_json=row["research_card_snapshot_json"],
            evidence_manifest_json=row["evidence_manifest_json"],
            evidence_manifest_sha256=row["evidence_manifest_sha256"],
            input_snapshot_json=row["input_snapshot_json"],
            input_sha256=row["input_sha256"],
            evidence_items=items,
            created_at=row["created_at"],
        )

    def get_content_item(
        self, account_id: str, content_id: int,
    ) -> ContentItem | None:
        row = self.conn.execute(
            "SELECT * FROM content_items WHERE id=? AND account_id=?",
            (content_id, account_id),
        ).fetchone()
        return None if row is None else self._content_item_from_row(row)

    def get_frozen_content_input(
        self, account_id: str, content_id: int,
    ) -> FrozenContentInput | None:
        row = self.conn.execute(
            "SELECT * FROM content_frozen_inputs WHERE content_id=? AND account_id=?",
            (content_id, account_id),
        ).fetchone()
        if row is None:
            return None
        evidence = self.conn.execute(
            "SELECT * FROM content_evidence_items WHERE content_id=? ORDER BY ordinal",
            (content_id,),
        ).fetchall()
        return self._frozen_content_input_from_rows(row, evidence)

    def _assert_content_snapshot_in_transaction(
        self, account_id: str, content_id: int,
    ) -> FrozenContentInput:
        frozen = self.get_frozen_content_input(account_id, content_id)
        if frozen is None:
            raise ContentSnapshotError(
                "CONTENT_FROZEN_INPUT_MISSING", "Frozen content input is missing.",
            )
        current = self._build_content_snapshot(
            account_id=account_id,
            research_card_id=frozen.research_card_id,
            content_type=frozen.content_type,
            input_schema_version=frozen.input_schema_version,
            output_schema_version=frozen.output_schema_version,
            prompt_version=frozen.prompt_version,
            style_guide_version=frozen.style_guide_version,
            article_brief_placeholder=json.loads(
                frozen.article_brief_placeholder_json
            ),
        )
        comparisons = (
            ("research card", current["card_json"], frozen.research_card_snapshot_json),
            ("evidence manifest", current["manifest_json"], frozen.evidence_manifest_json),
            ("input", current["input_json"], frozen.input_snapshot_json),
            ("input hash", current["input_sha256"], frozen.input_sha256),
        )
        for label, observed, expected in comparisons:
            if observed != expected:
                raise ContentSnapshotError(
                    "CONTENT_FROZEN_INPUT_DRIFT",
                    f"Current {label} no longer equals the frozen snapshot.",
                )
        return frozen

    def assert_content_snapshot(
        self, account_id: str, content_id: int,
    ) -> FrozenContentInput:
        owns_transaction = not self.conn.in_transaction
        if owns_transaction:
            self.conn.execute("BEGIN")
        try:
            frozen = self._assert_content_snapshot_in_transaction(
                account_id, content_id,
            )
            if owns_transaction:
                self.conn.commit()
            return frozen
        except Exception:
            if owns_transaction and self.conn.in_transaction:
                self.conn.rollback()
            raise

    def _existing_content_initialization(
        self,
        request: ContentPreparationRequest,
        row: sqlite3.Row,
    ) -> ContentInitialization:
        try:
            payload = canonicalize_content_job_payload(json.loads(row["payload_json"]))
        except (json.JSONDecodeError, ContentContractError) as exc:
            raise ContentFoundationError(
                "CONTENT_IDEMPOTENCY_CONFLICT",
                "Existing idempotency key has a malformed content payload.",
            ) from exc
        if (
            row["id"] != request.job_id
            or row["account_id"] != request.account_id
            or row["kind"] != JobKind.CONTENT.value
            or row["workflow"] != request.content_type.value
            or int(row["max_attempts"]) != request.max_attempts
            or payload["research_card_id"] != request.research_card_id
            or payload["content_type"] != request.content_type.value
        ):
            raise ContentFoundationError(
                "CONTENT_IDEMPOTENCY_CONFLICT",
                "Existing idempotency key belongs to a different content intent.",
            )
        content = self.get_content_item(
            request.account_id, int(payload["content_id"]),
        )
        if content is None or content.job_id != request.job_id:
            raise ContentFoundationError(
                "CONTENT_IDEMPOTENCY_CONFLICT",
                "Existing content job has no matching content record.",
            )
        frozen = self._assert_content_snapshot_in_transaction(
            request.account_id, content.id,
        )
        if (
            frozen.input_schema_version != request.input_schema_version
            or frozen.output_schema_version != request.output_schema_version
            or frozen.prompt_version != request.prompt_version
            or frozen.style_guide_version != request.style_guide_version
            or frozen.article_brief_placeholder_json
                != canonical_json(request.article_brief_placeholder)
        ):
            raise ContentFoundationError(
                "CONTENT_IDEMPOTENCY_CONFLICT",
                "Repeated preparation changed a frozen contract version.",
            )
        run = None
        if content.run_id is not None:
            run_row = self.conn.execute(
                "SELECT * FROM content_runs WHERE run_id=?", (content.run_id,),
            ).fetchone()
            if run_row is None:
                raise ContentFoundationError(
                    "CONTENT_RUN_RELATION_INVALID",
                    "Content references a missing content run.",
                )
            run = self._content_run_from_row(run_row)
        return ContentInitialization(
            content=content, frozen_input=frozen, job_created=False, run=run,
        )

    def prepare_content_job(
        self,
        request: ContentPreparationRequest,
        *,
        now: datetime | None = None,
        clock: Clock | None = None,
        fault_point: Callable[[ContentInitializationFaultPoint], None] | None = None,
    ) -> ContentInitialization:
        """Atomically freeze evidence and enqueue one held CONTENT job.

        The ordinary worker never claims CONTENT in C1.  The job can be leased
        only through ``claim_specific_job`` for local lifecycle/recovery tests.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            existing = self.conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                result = self._existing_content_initialization(request, existing)
                self.conn.commit()
                return result

            snapshot = self._build_content_snapshot(
                account_id=request.account_id,
                research_card_id=request.research_card_id,
                content_type=request.content_type,
                input_schema_version=request.input_schema_version,
                output_schema_version=request.output_schema_version,
                prompt_version=request.prompt_version,
                style_guide_version=request.style_guide_version,
                article_brief_placeholder=request.article_brief_placeholder,
            )
            intent_key = sha256_text(canonical_json({
                "account_id": request.account_id,
                "research_card_id": request.research_card_id,
                "content_type": request.content_type.value,
                "input_sha256": snapshot["input_sha256"],
                "input_schema_version": request.input_schema_version,
            }))
            cursor = self.conn.execute(
                "INSERT INTO content_items (account_id,type,status,research_card_id,"
                "created_at,updated_at) VALUES (?,?, 'DRAFT', ?,?,?)",
                (
                    request.account_id, request.content_type.value,
                    request.research_card_id, current_ts, current_ts,
                ),
            )
            if cursor.rowcount != 1 or cursor.lastrowid is None:
                raise ContentFoundationError(
                    "CONTENT_INSERT_FAILED",
                    "Content preparation did not create exactly one record.",
                )
            content_id = int(cursor.lastrowid)
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_CONTENT_INSERT, fault_point,
            )
            self.conn.execute(
                "INSERT INTO content_frozen_inputs (content_id,account_id,research_card_id,"
                "content_type,input_schema_version,output_schema_version,prompt_version,"
                "style_guide_version,article_brief_placeholder_json,"
                "article_brief_placeholder_sha256,research_card_snapshot_json,"
                "evidence_manifest_json,evidence_manifest_sha256,evidence_item_count,"
                "input_snapshot_json,input_sha256,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    content_id, request.account_id, request.research_card_id,
                    request.content_type.value, request.input_schema_version,
                    request.output_schema_version, request.prompt_version,
                    request.style_guide_version, snapshot["brief_json"],
                    snapshot["brief_sha256"], snapshot["card_json"],
                    snapshot["manifest_json"], snapshot["manifest_sha256"],
                    len(snapshot["items"]), snapshot["input_json"],
                    snapshot["input_sha256"], current_ts,
                ),
            )
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_FROZEN_INPUT_INSERT,
                fault_point,
            )
            for item in snapshot["items"]:
                assert isinstance(item, FrozenEvidenceItem)
                self.conn.execute(
                    "INSERT INTO content_evidence_items (content_id,account_id,"
                    "research_card_id,ordinal,topic_id,research_run_id,"
                    "research_job_id,confirmed_claim_id,confirmed_claim_ordinal,"
                    "claim_text,claim_sha256,candidate_id,source_id,"
                    "source_url,source_url_sha256,source_claim_text,"
                    "source_claim_sha256,excerpt_id,excerpt_text,excerpt_sha256,"
                    "retrieval_id,requested_url_sha256,final_url_sha256,"
                    "canonical_sha256,lineage_fingerprint,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        content_id, request.account_id, request.research_card_id,
                        item.ordinal, item.topic_id, item.research_run_id,
                        item.research_job_id, item.confirmed_claim_id,
                        item.confirmed_claim_ordinal, item.claim_text,
                        item.claim_sha256, item.candidate_id, item.source_id,
                        item.source_url, item.source_url_sha256,
                        item.source_claim_text, item.source_claim_sha256,
                        item.excerpt_id, item.excerpt_text, item.excerpt_sha256,
                        item.retrieval_id, item.requested_url_sha256,
                        item.final_url_sha256, item.canonical_sha256,
                        item.lineage_fingerprint, current_ts,
                    ),
                )
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_EVIDENCE_INSERTS, fault_point,
            )
            payload = content_job_payload(
                account_id=request.account_id,
                research_card_id=request.research_card_id,
                content_id=content_id,
                content_type=request.content_type,
                frozen_input_sha256=str(snapshot["input_sha256"]),
                evidence_manifest_sha256=str(snapshot["manifest_sha256"]),
                intent_key=intent_key,
                execution_mode=request.execution_mode,
            )
            card = snapshot["card"]
            assert isinstance(card, sqlite3.Row)
            job = Job(
                id=request.job_id,
                account_id=request.account_id,
                kind=JobKind.CONTENT,
                workflow=WorkflowType(request.content_type.value),
                idempotency_key=request.idempotency_key,
                topic_id=int(card["topic_id"]),
                payload=payload,
                schedule_reason="WITHIN_EDITORIAL_WINDOW",
                earliest_run_at=current,
                max_attempts=request.max_attempts,
                created_at=current,
                updated_at=current,
            )
            self._validate_job_enqueue_relation(job)
            payload_json = self._canonical_payload(payload)
            self.conn.execute(
                "INSERT INTO jobs (id,account_id,kind,workflow,status,priority,"
                "idempotency_key,topic_id,run_id,payload_json,schedule_reason,"
                "earliest_run_at,deadline_at,lease_owner,lease_expires_at,attempts,"
                "max_attempts,reserved_cost_usd,budget_reserved_at,"
                "external_effect_started_at,last_error,created_at,started_at,"
                "finished_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job.id, job.account_id, job.kind.value, job.workflow.value,
                    JobStatus.QUEUED.value, job.priority, job.idempotency_key,
                    job.topic_id, None, payload_json, job.schedule_reason,
                    current_ts, None, None, None, 0, job.max_attempts, 0.0,
                    None, None, None, current_ts, None, None, current_ts,
                ),
            )
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_JOB_INSERT, fault_point,
            )
            prepared = self.conn.execute(
                "UPDATE content_items SET status='PREPARED',job_id=?,input_sha256=?,"
                "intent_key=?,updated_at=? WHERE id=? AND account_id=? AND status='DRAFT'",
                (
                    request.job_id, snapshot["input_sha256"], intent_key,
                    current_ts, content_id, request.account_id,
                ),
            )
            if prepared.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_PREPARATION_FAILED",
                    "Frozen content preparation did not update exactly one record.",
                )
            self._content_fault(
                ContentInitializationFaultPoint.BEFORE_PREPARATION_COMMIT,
                fault_point,
            )
            self.conn.commit()
            content = self.get_content_item(request.account_id, content_id)
            frozen = self.get_frozen_content_input(request.account_id, content_id)
            assert content is not None and frozen is not None
            return ContentInitialization(
                content=content, frozen_input=frozen, job_created=True,
            )
        except sqlite3.IntegrityError as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise ContentFoundationError(
                "CONTENT_DURABLE_CONFLICT",
                "Content intent conflicts with an existing durable relation.",
            ) from exc
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def initialize_content_run_for_job(
        self,
        job_id: str,
        lease_owner: str,
        fence_token: int,
        run_id: str,
        *,
        now: datetime | None = None,
        clock: Clock | None = None,
        fault_point: Callable[[ContentInitializationFaultPoint], None] | None = None,
    ) -> ContentInitialization:
        """Atomically attach runs/content_runs under the current lease fence."""
        if (
            not job_id.strip() or not lease_owner.strip() or not run_id.strip()
            or fence_token <= 0
        ):
            raise ValueError(
                "job_id, lease_owner and run_id must be non-empty and "
                "fence_token must be positive."
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            row = self.conn.execute(
                "SELECT j.*,c.id AS content_id,c.status AS content_status,"
                "c.run_id AS content_run_id,c.input_sha256,c.intent_key,"
                "c.research_card_id,c.type AS content_type "
                "FROM jobs j JOIN content_items c ON c.job_id=j.id WHERE j.id=?",
                (job_id,),
            ).fetchone()
            if (
                row is None
                or row["kind"] != JobKind.CONTENT.value
                or row["workflow"] not in (
                    WorkflowType.ARTICLE.value, WorkflowType.NOTE.value,
                )
                or row["account_id"] is None
                or row["lease_owner"] != lease_owner
                or int(row["execution_generation"]) != fence_token
                or row["lease_expires_at"] is None
                or row["lease_expires_at"] < current_ts
                or row["status"] not in _EXECUTABLE_JOB_STATUSES
            ):
                raise StaleJobExecutionError(
                    job_id, "content run initialization lacks an active lease fence.",
                )
            payload = canonicalize_content_job_payload(
                json.loads(row["payload_json"])
            )
            if (
                payload["content_id"] != int(row["content_id"])
                or payload["account_id"] != row["account_id"]
                or payload["research_card_id"] != int(row["research_card_id"])
                or payload["content_type"] != row["content_type"]
                or payload["frozen_input_sha256"] != row["input_sha256"]
            ):
                raise ContentFoundationError(
                    "CONTENT_JOB_RELATION_INVALID",
                    "Content job payload does not match the persisted content record.",
                )
            frozen = self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["content_id"]),
            )
            if row["run_id"] is not None:
                if row["run_id"] != run_id or row["content_run_id"] != run_id:
                    raise JobRunConflictError(job_id, row["run_id"], run_id)
                run_row = self.conn.execute(
                    "SELECT cr.*,r.status AS general_status,r.account_id AS general_account,"
                    "r.workflow AS general_workflow,r.finished_at AS general_finished "
                    "FROM content_runs cr JOIN runs r ON r.id=cr.run_id "
                    "WHERE cr.run_id=?",
                    (run_id,),
                ).fetchone()
                if (
                    run_row is None
                    or run_row["content_id"] != row["content_id"]
                    or run_row["job_id"] != job_id
                    or run_row["account_id"] != row["account_id"]
                    or run_row["input_sha256"] != row["input_sha256"]
                    or run_row["general_status"] != RunStatus.RUNNING.value
                    or run_row["general_finished"] is not None
                    or run_row["general_account"] != row["account_id"]
                    or run_row["general_workflow"] != row["workflow"]
                    or run_row["status"] not in (
                        ContentStatus.PREPARED.value,
                        ContentStatus.RUNNING.value,
                    )
                ):
                    raise ContentFoundationError(
                        "CONTENT_RUN_RELATION_INVALID",
                        "Existing content run cannot be resumed safely.",
                    )
                if run_row["status"] == ContentStatus.PREPARED.value:
                    self._apply_content_transition_command(
                        mode="EXECUTION",
                        job_id=job_id,
                        run_id=run_id,
                        content_id=int(row["content_id"]),
                        account_id=row["account_id"],
                        workflow=row["workflow"],
                        source_status=ContentStatus.PREPARED.value,
                        target_status=ContentStatus.RUNNING.value,
                        target_run_status=RunStatus.RUNNING.value,
                        target_job_status=JobStatus.RUNNING.value,
                        lease_owner=lease_owner,
                        execution_generation=fence_token,
                        lease_expires_at=row["lease_expires_at"],
                        reason_code=None,
                        result_json=None,
                        score=None,
                        current_ts=current_ts,
                    )
                if row["status"] == JobStatus.LEASED.value:
                    job_started = self.conn.execute(
                        "UPDATE jobs SET status='RUNNING',updated_at=? WHERE id=? "
                        "AND status='LEASED' AND lease_owner=? AND lease_expires_at>=? "
                        "AND execution_generation=?",
                        (current_ts, job_id, lease_owner, current_ts, fence_token),
                    )
                    self._require_one_transition(
                        job_started,
                        table="jobs",
                        entity="job",
                        identifier=job_id,
                        target_status=JobStatus.RUNNING.value,
                        allowed_source_statuses=(JobStatus.LEASED.value,),
                        detail="Content takeover could not resume the leased job.",
                    )
                self.conn.commit()
                content = self.get_content_item(
                    row["account_id"], int(row["content_id"]),
                )
                persisted_run = self.conn.execute(
                    "SELECT * FROM content_runs WHERE run_id=?", (run_id,),
                ).fetchone()
                assert content is not None and persisted_run is not None
                return ContentInitialization(
                    content=content, frozen_input=frozen, job_created=False,
                    run=self._content_run_from_row(persisted_run),
                )

            if row["content_status"] != ContentStatus.PREPARED.value:
                raise ContentFoundationError(
                    "CONTENT_NOT_PREPARED",
                    "A new content run requires PREPARED content.",
                )
            self.conn.execute(
                "INSERT INTO runs (id,account_id,workflow,status,current_state,"
                "started_at,cost_usd,human_intervention_count) "
                "VALUES (?,?,?,'RUNNING','RUNNING',?,0.0,0)",
                (run_id, row["account_id"], row["workflow"], current_ts),
            )
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_RUN_INSERT, fault_point,
            )
            self.conn.execute(
                "INSERT INTO content_runs (run_id,content_id,job_id,account_id,"
                "research_card_id,workflow,input_sha256,status,started_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,'RUNNING',?,?)",
                (
                    run_id, row["content_id"], job_id, row["account_id"],
                    row["research_card_id"], row["workflow"], row["input_sha256"],
                    current_ts, current_ts,
                ),
            )
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_CONTENT_RUN_INSERT,
                fault_point,
            )
            attached = self.conn.execute(
                "UPDATE jobs SET run_id=?,status='RUNNING',updated_at=? "
                "WHERE id=? AND run_id IS NULL AND status IN ('LEASED','RUNNING') "
                "AND lease_owner=? AND lease_expires_at>=? "
                "AND execution_generation=?",
                (
                    run_id, current_ts, job_id, lease_owner, current_ts,
                    fence_token,
                ),
            )
            if attached.rowcount != 1:
                raise StaleJobExecutionError(job_id)
            self._content_fault(
                ContentInitializationFaultPoint.AFTER_JOB_RUN_ATTACH, fault_point,
            )
            self._content_fault(
                ContentInitializationFaultPoint.BEFORE_EXECUTION_SNAPSHOT_RECHECK,
                fault_point,
            )
            # Re-read the authoritative lineage in this same write transaction
            # immediately before content becomes executable.
            self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["content_id"]),
            )
            content_attached = self.conn.execute(
                "UPDATE content_items SET run_id=?,status='RUNNING',updated_at=? "
                "WHERE id=? AND job_id=? AND run_id IS NULL AND status='PREPARED'",
                (run_id, current_ts, row["content_id"], job_id),
            )
            if content_attached.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_RUN_ATTACH_FAILED",
                    "Content run attach did not update exactly one content record.",
                )
            self._content_fault(
                ContentInitializationFaultPoint.BEFORE_RUN_INITIALIZATION_COMMIT,
                fault_point,
            )
            self.conn.commit()
            content = self.get_content_item(
                row["account_id"], int(row["content_id"]),
            )
            run_row = self.conn.execute(
                "SELECT * FROM content_runs WHERE run_id=?", (run_id,),
            ).fetchone()
            assert content is not None and run_row is not None
            return ContentInitialization(
                content=content, frozen_input=frozen, job_created=False,
                run=self._content_run_from_row(run_row),
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    @staticmethod
    def _validate_content_transition_payload(
        target: ContentStatus,
        reason_code: str | None,
        final_result: dict[str, object] | None,
        score: float | None,
    ) -> tuple[str | None, str | None, float | None]:
        reason_required = {
            ContentStatus.REVISE,
            ContentStatus.SKIPPED,
            ContentStatus.FAILED,
            ContentStatus.NEEDS_VERIFICATION,
        }
        if target in reason_required:
            if (
                not isinstance(reason_code, str)
                or not reason_code
                or reason_code != reason_code.strip()
                or len(reason_code) > 100
                or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in reason_code)
            ):
                raise ValueError(
                    "Negative/revision content states require a controlled reason_code."
                )
        elif reason_code is not None:
            raise ValueError(f"{target.value} does not accept a reason_code.")
        result_json = None if final_result is None else canonical_json(final_result)
        if score is not None:
            if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                raise ValueError("Content score must be finite.")
            if not 0 <= float(score) <= 1:
                raise ValueError("Content score must be between 0 and 1.")
            score = float(score)
        return reason_code, result_json, score

    def _apply_content_transition_command(
        self,
        *,
        mode: str,
        job_id: str,
        run_id: str,
        content_id: int,
        account_id: str,
        workflow: str,
        source_status: str,
        target_status: str,
        target_run_status: str,
        target_job_status: str,
        lease_owner: str,
        execution_generation: int,
        lease_expires_at: str,
        reason_code: str | None,
        result_json: str | None,
        score: float | None,
        current_ts: str,
    ) -> None:
        """Insert the one SQL command which owns a content transition."""
        sequence = int(self.conn.execute(
            "SELECT COALESCE(MAX(id),0)+1 FROM content_transition_commands"
        ).fetchone()[0])
        command_id = sha256_text(canonical_json({
            "account_id": account_id,
            "content_id": content_id,
            "created_at": current_ts,
            "execution_generation": execution_generation,
            "job_id": job_id,
            "mode": mode,
            "run_id": run_id,
            "sequence": sequence,
            "source_status": source_status,
            "target_job_status": target_job_status,
            "target_run_status": target_run_status,
            "target_status": target_status,
            "workflow": workflow,
        }))
        inserted = self.conn.execute(
            "INSERT INTO content_transition_commands (command_id,mode,job_id,"
            "run_id,content_id,account_id,workflow,source_content_status,"
            "target_content_status,target_run_status,target_job_status,"
            "lease_owner,execution_generation,lease_expires_at,reason_code,"
            "final_result_json,score,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                command_id, mode, job_id, run_id, content_id, account_id,
                workflow, source_status, target_status, target_run_status,
                target_job_status, lease_owner, execution_generation,
                lease_expires_at, reason_code, result_json, score, current_ts,
            ),
        )
        if inserted.rowcount != 1:
            raise ContentFoundationError(
                "CONTENT_TRANSITION_COMMAND_FAILED",
                "Content transition command did not affect exactly one row.",
            )

    def transition_content_execution(
        self,
        execution: JobExecutionContext,
        target: ContentStatus,
        *,
        reason_code: str | None = None,
        final_result: dict[str, object] | None = None,
        score: float | None = None,
    ) -> ContentTransitionResult:
        """One fenced transaction owns content/run/job terminalization."""
        if target is ContentStatus.DRAFT:
            raise ValueError("Content cannot transition back to DRAFT.")
        if (
            execution.kind is not JobKind.CONTENT
            or execution.workflow not in (
                WorkflowType.ARTICLE, WorkflowType.NOTE,
            )
            or execution.fence_token <= 0
        ):
            raise StaleJobExecutionError(
                execution.job_id,
                "Content transition requires a typed context with a positive fence.",
            )
        reason_code, result_json, score = self._validate_content_transition_payload(
            target, reason_code, final_result, score,
        )
        allowed = {
            ContentStatus.PREPARED: (
                ContentStatus.RUNNING.value, ContentStatus.REVISE.value,
            ),
            ContentStatus.RUNNING: (
                ContentStatus.PREPARED.value, ContentStatus.REVISE.value,
            ),
            ContentStatus.REVISE: (ContentStatus.RUNNING.value,),
            ContentStatus.SKIPPED: (
                ContentStatus.PREPARED.value, ContentStatus.RUNNING.value,
                ContentStatus.REVISE.value,
            ),
            ContentStatus.PENDING_APPROVAL: (ContentStatus.RUNNING.value,),
            ContentStatus.FAILED: (
                ContentStatus.PREPARED.value, ContentStatus.RUNNING.value,
                ContentStatus.REVISE.value,
            ),
            ContentStatus.NEEDS_VERIFICATION: (
                ContentStatus.PREPARED.value, ContentStatus.RUNNING.value,
                ContentStatus.REVISE.value,
            ),
        }.get(target, ())
        if not allowed:
            raise ValueError(f"Unsupported content transition target {target.value}.")
        terminal_map = {
            ContentStatus.SKIPPED: (RunStatus.SUCCESS, JobStatus.DONE),
            ContentStatus.PENDING_APPROVAL: (RunStatus.SUCCESS, JobStatus.DONE),
            ContentStatus.FAILED: (RunStatus.FAILED, JobStatus.FAILED),
            ContentStatus.NEEDS_VERIFICATION: (
                RunStatus.STOPPED, JobStatus.NEEDS_VERIFICATION,
            ),
        }
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self.conn.execute(
                "SELECT cr.*,c.type AS content_type,c.status AS item_status,"
                "c.id AS item_id,c.job_id AS item_job_id,c.run_id AS item_run_id,"
                "c.account_id AS item_account,"
                "c.reason_code AS item_reason,c.final_result_json AS item_result,"
                "c.score AS item_score,j.status AS job_status,j.account_id AS job_account,"
                "j.kind AS job_kind,j.workflow AS job_workflow,j.run_id AS job_run_id,"
                "j.lease_owner,j.lease_expires_at,j.execution_generation,"
                "r.status AS general_status,"
                "r.account_id AS general_account,r.workflow AS general_workflow,"
                "r.finished_at AS general_finished "
                "FROM content_runs cr JOIN content_items c ON c.id=cr.content_id "
                "JOIN jobs j ON j.id=cr.job_id JOIN runs r ON r.id=cr.run_id "
                "WHERE cr.job_id=? AND cr.run_id=?",
                (execution.job_id, execution.run_id),
            ).fetchone()
            if (
                row is None
                or row["job_kind"] != JobKind.CONTENT.value
                or row["content_type"] != execution.workflow.value
                or row["workflow"] != execution.workflow.value
                or row["job_workflow"] != row["content_type"]
                or row["job_run_id"] != execution.run_id
                or row["item_job_id"] != execution.job_id
                or row["item_run_id"] != execution.run_id
                or row["item_account"] != row["account_id"]
                or row["job_account"] != row["account_id"]
                or row["general_account"] != row["account_id"]
                or row["general_workflow"] != row["content_type"]
                or row["item_status"] != row["status"]
            ):
                raise ContentFoundationError(
                    "CONTENT_EXECUTION_RELATION_INVALID",
                    "Content/job/run relation is inconsistent.",
                )
            if int(row["execution_generation"]) != execution.fence_token:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "Content execution fence no longer matches the durable generation.",
                )
            literal_noop = (
                row["status"] == target.value
                and row["reason_code"] == reason_code
                and row["final_result_json"] == result_json
                and (
                    (row["score"] is None and score is None)
                    or (
                        row["score"] is not None and score is not None
                        and float(row["score"]) == score
                    )
                )
                and row["item_reason"] == reason_code
                and row["item_result"] == result_json
            )
            if literal_noop:
                if target in terminal_map:
                    run_target, job_target = terminal_map[target]
                    command = self.conn.execute(
                        "SELECT * FROM content_transition_commands "
                        "WHERE job_id=? AND run_id=? AND content_id=? "
                        "AND target_content_status=? AND target_run_status=? "
                        "AND target_job_status=? AND lease_owner=? "
                        "AND execution_generation=? AND reason_code IS ? "
                        "AND final_result_json IS ? AND score IS ? AND applied=1",
                        (
                            execution.job_id, execution.run_id,
                            int(row["content_id"]), target.value,
                            run_target.value, job_target.value,
                            execution.lease_owner, execution.fence_token,
                            reason_code, result_json, score,
                        ),
                    ).fetchone()
                    if (
                        command is None
                        or command["workflow"] != execution.workflow.value
                        or command["lease_expires_at"] < current_ts
                        or row["job_status"] != job_target.value
                        or row["general_status"] != run_target.value
                        or row["general_finished"] is None
                    ):
                        raise StaleJobExecutionError(
                            execution.job_id,
                            "Terminal replay no longer owns the recorded lease fence.",
                        )
                elif (
                    row["job_status"] not in _EXECUTABLE_JOB_STATUSES
                    or row["lease_owner"] != execution.lease_owner
                    or row["lease_expires_at"] is None
                    or row["lease_expires_at"] < current_ts
                    or row["general_status"] != RunStatus.RUNNING.value
                ):
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "Non-terminal replay lacks the current lease fence.",
                    )
                content_row = self.conn.execute(
                    "SELECT * FROM content_items WHERE id=?", (row["content_id"],),
                ).fetchone()
                assert content_row is not None
                self.conn.commit()
                return ContentTransitionResult(
                    content=self._content_item_from_row(content_row),
                    run=self._content_run_from_row(row),
                    idempotent=True,
                )
            if (
                row["status"] not in allowed
                or row["job_status"] not in _EXECUTABLE_JOB_STATUSES
                or row["lease_owner"] != execution.lease_owner
                or row["lease_expires_at"] is None
                or row["lease_expires_at"] < current_ts
                or int(row["execution_generation"]) != execution.fence_token
                or row["general_status"] != RunStatus.RUNNING.value
                or row["general_finished"] is not None
            ):
                raise LifecycleTransitionError(
                    "content_run", execution.run_id, target.value, allowed,
                    row["status"],
                    detail="Content transition lacks a matching active lease or source state.",
                )
            self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["content_id"]),
            )
            if target in terminal_map:
                run_target, job_target = terminal_map[target]
            else:
                run_target, job_target = RunStatus.RUNNING, JobStatus.RUNNING
            self._apply_content_transition_command(
                mode="EXECUTION",
                job_id=execution.job_id,
                run_id=execution.run_id,
                content_id=int(row["content_id"]),
                account_id=row["account_id"],
                workflow=execution.workflow.value,
                source_status=row["status"],
                target_status=target.value,
                target_run_status=run_target.value,
                target_job_status=job_target.value,
                lease_owner=execution.lease_owner,
                execution_generation=execution.fence_token,
                lease_expires_at=row["lease_expires_at"],
                reason_code=reason_code,
                result_json=result_json,
                score=score,
                current_ts=current_ts,
            )
            self.conn.commit()
            content_row = self.conn.execute(
                "SELECT * FROM content_items WHERE id=?", (row["content_id"],),
            ).fetchone()
            run_row = self.conn.execute(
                "SELECT * FROM content_runs WHERE run_id=?", (execution.run_id,),
            ).fetchone()
            assert content_row is not None and run_row is not None
            return ContentTransitionResult(
                content=self._content_item_from_row(content_row),
                run=self._content_run_from_row(run_row),
                idempotent=False,
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _require_content_execution_fence(
        self,
        execution: JobExecutionContext,
        current_ts: str,
        *,
        allowed_content_statuses: Sequence[str] = (
            ContentStatus.RUNNING.value,
            ContentStatus.REVISE.value,
        ),
    ) -> sqlite3.Row:
        if (
            execution.kind is not JobKind.CONTENT
            or execution.workflow not in (
                WorkflowType.ARTICLE, WorkflowType.NOTE,
            )
            or execution.fence_token <= 0
        ):
            raise StaleJobExecutionError(
                execution.job_id,
                "content storage requires a typed CONTENT execution context.",
            )
        placeholders = ",".join("?" for _ in allowed_content_statuses)
        row = self.conn.execute(
            "SELECT c.*,cr.status AS content_run_status,j.status AS job_status,"
            "j.lease_owner,j.lease_expires_at,j.kind AS job_kind,j.kind AS kind,"
            "j.workflow AS job_workflow,j.run_id AS job_run_id,"
            "j.execution_generation,cr.workflow AS content_run_workflow,"
            "r.workflow AS general_workflow,r.account_id AS general_account,"
            "r.status AS general_status,r.status AS run_status,"
            "r.finished_at AS general_finished "
            "FROM content_items c JOIN content_runs cr ON cr.content_id=c.id "
            "JOIN jobs j ON j.id=c.job_id "
            "JOIN runs r ON r.id=cr.run_id "
            "WHERE j.id=? AND j.run_id=? AND c.run_id=? "
            "AND j.account_id=c.account_id AND cr.job_id=j.id AND cr.run_id=j.run_id "
            "AND j.kind='CONTENT' AND j.workflow=c.type AND cr.workflow=c.type "
            "AND r.workflow=c.type AND r.account_id=c.account_id "
            "AND r.status='RUNNING' AND r.finished_at IS NULL "
            "AND j.status IN ('LEASED','RUNNING') "
            "AND j.lease_owner=? AND j.lease_expires_at>=? "
            "AND j.execution_generation=? "
            f"AND c.status IN ({placeholders}) AND cr.status=c.status",
            (
                execution.job_id, execution.run_id, execution.run_id,
                execution.lease_owner, current_ts, execution.fence_token,
                *allowed_content_statuses,
            ),
        ).fetchone()
        if (
            row is None
            or row["type"] != execution.workflow.value
            or row["job_workflow"] != execution.workflow.value
            or row["content_run_workflow"] != execution.workflow.value
            or row["general_workflow"] != execution.workflow.value
        ):
            raise StaleJobExecutionError(execution.job_id)
        return row

    def record_content_article_brief(
        self,
        execution: JobExecutionContext,
        *,
        brief_schema_version: str,
        brief: dict[str, object],
    ) -> str:
        """Persist a caller-supplied brief contract; C1 generates no brief."""
        if (
            not brief_schema_version
            or brief_schema_version != brief_schema_version.strip()
            or len(brief_schema_version) > 100
        ):
            raise ValueError("brief_schema_version must be a controlled string.")
        brief_json = canonical_json(brief)
        brief_sha256 = sha256_text(brief_json)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["id"]),
            )
            existing = self.conn.execute(
                "SELECT * FROM content_article_briefs WHERE content_id=?",
                (row["id"],),
            ).fetchone()
            if existing is not None:
                if (
                    existing["job_id"] == execution.job_id
                    and existing["run_id"] == execution.run_id
                    and existing["brief_schema_version"] == brief_schema_version
                    and existing["brief_json"] == brief_json
                    and existing["brief_sha256"] == brief_sha256
                ):
                    self.conn.commit()
                    return brief_sha256
                raise ContentFoundationError(
                    "CONTENT_BRIEF_CONFLICT",
                    "An immutable Article Brief already exists for this content.",
                )
            inserted = self.conn.execute(
                "INSERT INTO content_article_briefs (content_id,job_id,run_id,"
                "account_id,brief_schema_version,brief_json,brief_sha256,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    row["id"], execution.job_id, execution.run_id,
                    row["account_id"], brief_schema_version, brief_json,
                    brief_sha256, current_ts,
                ),
            )
            if inserted.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_BRIEF_INSERT_FAILED",
                    "Article Brief insert did not affect exactly one row.",
                )
            self.conn.commit()
            return brief_sha256
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_content_call_intent(
        self,
        execution: JobExecutionContext,
        intent: ContentCallIntent,
    ) -> ContentCallIntent:
        """Persist a future paid-call preimage without authorizing an attempt."""
        preimage = intent.canonical_preimage()
        fingerprint = intent.fingerprint()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            frozen = self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["id"]),
            )
            if (
                intent.job_id != execution.job_id
                or intent.run_id != execution.run_id
                or intent.content_id != int(row["id"])
                or intent.account_id != row["account_id"]
                or intent.research_card_id != int(row["research_card_id"])
                or intent.content_type.value != row["type"]
                or intent.frozen_input_sha256 != frozen.input_sha256
                or intent.evidence_manifest_sha256
                    != frozen.evidence_manifest_sha256
                or intent.prompt_version != frozen.prompt_version
                or intent.style_guide_version != frozen.style_guide_version
                or intent.output_schema_version != frozen.output_schema_version
                or _persisted_ts(intent.expires_at) <= current_ts
            ):
                raise ContentFoundationError(
                    "CONTENT_CALL_INTENT_MISMATCH",
                    "Future paid-call intent does not match the active frozen content execution.",
                )
            brief = self.conn.execute(
                "SELECT brief_sha256 FROM content_article_briefs "
                "WHERE content_id=? AND job_id=? AND run_id=?",
                (row["id"], execution.job_id, execution.run_id),
            ).fetchone()
            if brief is None or brief["brief_sha256"] != intent.article_brief_sha256:
                raise ContentFoundationError(
                    "CONTENT_CALL_BRIEF_MISMATCH",
                    "Future paid-call intent requires the exact immutable Article Brief.",
                )
            existing = self.conn.execute(
                "SELECT * FROM content_call_intents WHERE intent_id=? OR job_id=?",
                (intent.intent_id, execution.job_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["intent_id"] == intent.intent_id
                    and existing["job_id"] == intent.job_id
                    and existing["intent_json"] == preimage
                    and existing["intent_fingerprint"] == fingerprint
                ):
                    self.conn.commit()
                    return intent
                raise ContentFoundationError(
                    "CONTENT_CALL_INTENT_CONFLICT",
                    "A different immutable call intent already exists.",
                )
            inserted = self.conn.execute(
                "INSERT INTO content_call_intents (intent_id,job_id,run_id,"
                "content_id,account_id,research_card_id,content_type,stage,"
                "frozen_input_sha256,article_brief_sha256,evidence_manifest_sha256,"
                "provider,model,pricing_profile_id,pricing_profile_version,"
                "pricing_fingerprint,max_input_tokens,max_context_tokens,"
                "max_output_tokens,web_searches,max_retries,attempt_no,"
                "prompt_version,style_guide_version,output_schema_version,"
                "max_cost_usd,expires_at,intent_json,intent_fingerprint,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    intent.intent_id, intent.job_id, intent.run_id,
                    intent.content_id, intent.account_id, intent.research_card_id,
                    intent.content_type.value, intent.stage,
                    intent.frozen_input_sha256,
                    intent.article_brief_sha256,
                    intent.evidence_manifest_sha256, intent.provider, intent.model,
                    intent.pricing_profile_id, intent.pricing_profile_version,
                    intent.pricing_fingerprint, intent.max_input_tokens,
                    intent.max_context_tokens, intent.max_output_tokens,
                    intent.web_searches, intent.max_retries, intent.attempt_no,
                    intent.prompt_version, intent.style_guide_version,
                    intent.output_schema_version, intent.max_cost_usd,
                    _persisted_ts(intent.expires_at), preimage, fingerprint,
                    _persisted_ts(intent.created_at),
                ),
            )
            if inserted.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_CALL_INTENT_INSERT_FAILED",
                    "Future call intent insert did not affect exactly one row.",
                )
            self.conn.commit()
            return intent
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_content_evaluation(
        self,
        execution: JobExecutionContext,
        evaluation: ContentEvaluation,
    ) -> ContentEvaluation:
        """Persist an audit result supplied by C2; C1 runs no audit logic."""
        findings_json = canonical_json(evaluation.findings)
        reason_codes_json = canonical_json(evaluation.reason_codes)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(
                execution,
                current_ts,
                allowed_content_statuses=(
                    ContentStatus.RUNNING.value,
                    ContentStatus.REVISE.value,
                ),
            )
            if (
                evaluation.content_id != int(row["id"])
                or evaluation.account_id != row["account_id"]
                or evaluation.job_id != execution.job_id
                or evaluation.run_id != execution.run_id
            ):
                raise ContentFoundationError(
                    "CONTENT_EVALUATION_MISMATCH",
                    "Evaluation does not match the active content execution.",
                )
            existing = self.conn.execute(
                "SELECT * FROM evaluations WHERE content_id=? AND kind=? "
                "AND audit_version=?",
                (
                    evaluation.content_id, evaluation.kind.value,
                    evaluation.audit_version,
                ),
            ).fetchone()
            if existing is not None:
                same = (
                    existing["account_id"] == evaluation.account_id
                    and existing["job_id"] == evaluation.job_id
                    and existing["run_id"] == evaluation.run_id
                    and existing["status"] == evaluation.status.value
                    and existing["score"] == evaluation.score
                    and existing["findings_json"] == findings_json
                    and existing["reason_codes_json"] == reason_codes_json
                )
                if same:
                    self.conn.commit()
                    values = evaluation.model_dump()
                    values.update({
                        "id": int(existing["id"]),
                        "created_at": existing["created_at"],
                        "updated_at": existing["updated_at"],
                    })
                    return ContentEvaluation(**values)
                raise ContentFoundationError(
                    "CONTENT_EVALUATION_CONFLICT",
                    "A different evaluation already exists for this audit version.",
                )
            cursor = self.conn.execute(
                "INSERT INTO evaluations (content_id,account_id,job_id,run_id,"
                "kind,audit_version,status,score,findings_json,reason_codes_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    evaluation.content_id, evaluation.account_id,
                    evaluation.job_id, evaluation.run_id, evaluation.kind.value,
                    evaluation.audit_version, evaluation.status.value,
                    evaluation.score, findings_json, reason_codes_json,
                    current_ts, current_ts,
                ),
            )
            if cursor.rowcount != 1 or cursor.lastrowid is None:
                raise ContentFoundationError(
                    "CONTENT_EVALUATION_INSERT_FAILED",
                    "Evaluation insert did not affect exactly one row.",
                )
            self.conn.commit()
            values = evaluation.model_dump()
            values.update({
                "id": int(cursor.lastrowid),
                "created_at": current_ts,
                "updated_at": current_ts,
            })
            return ContentEvaluation(**values)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def get_content_pipeline_state(self, job_id: str) -> dict[str, object]:
        """Read the complete durable C2 checkpoint set for one content job."""
        job = self.conn.execute(
            "SELECT * FROM jobs WHERE id=? AND kind='CONTENT'", (job_id,),
        ).fetchone()
        if job is None:
            raise ContentFoundationError(
                "CONTENT_JOB_MISSING", "C2 pipeline job does not exist.",
            )
        content = self.conn.execute(
            "SELECT * FROM content_items WHERE job_id=?", (job_id,),
        ).fetchone()
        if content is None:
            raise ContentFoundationError(
                "CONTENT_RELATION_MISSING", "C2 pipeline content item is missing.",
            )
        plan = self.conn.execute(
            "SELECT * FROM content_plans WHERE content_id=?", (content["id"],),
        ).fetchone()
        brief = self.conn.execute(
            "SELECT * FROM content_article_briefs WHERE content_id=?", (content["id"],),
        ).fetchone()
        intents = self.conn.execute(
            "SELECT * FROM content_writer_intents WHERE content_id=? ORDER BY attempt_no",
            (content["id"],),
        ).fetchall()
        attempts = self.conn.execute(
            "SELECT wa.*,pa.status,pa.actual_cost_usd,pa.request_started_at,"
            "pa.settled_at FROM content_writer_attempts wa "
            "JOIN provider_attempts pa ON pa.request_id=wa.request_id "
            "WHERE wa.content_id=? ORDER BY wa.attempt_no",
            (content["id"],),
        ).fetchall()
        drafts = self.conn.execute(
            "SELECT * FROM content_drafts WHERE content_id=? ORDER BY attempt_no",
            (content["id"],),
        ).fetchall()
        evaluations = self.conn.execute(
            "SELECT * FROM content_draft_evaluations WHERE content_id=? "
            "ORDER BY attempt_no,evaluation_type",
            (content["id"],),
        ).fetchall()

        def mapping(row: sqlite3.Row | None) -> dict[str, object] | None:
            return None if row is None else {key: row[key] for key in row.keys()}

        return {
            "job": mapping(job),
            "content": mapping(content),
            "plan": mapping(plan),
            "brief": mapping(brief),
            "intents": [mapping(row) for row in intents],
            "attempts": [mapping(row) for row in attempts],
            "drafts": [mapping(row) for row in drafts],
            "evaluations": [mapping(row) for row in evaluations],
        }

    def record_content_plan(
        self, execution: JobExecutionContext, plan: ContentPlan,
    ) -> str:
        """Persist the immutable planner output under the active content fence."""
        plan_json = plan.canonical_preimage()
        fingerprint = plan.fingerprint()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            frozen = self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["id"]),
            )
            if (
                plan.content_id != int(row["id"])
                or plan.account_id != row["account_id"]
                or plan.research_card_id != int(row["research_card_id"])
                or plan.content_type.value != row["type"]
                or plan.frozen_input_sha256 != frozen.input_sha256
                or plan.evidence_manifest_sha256 != frozen.evidence_manifest_sha256
            ):
                raise ContentFoundationError(
                    "CONTENT_PLAN_MISMATCH",
                    "Content plan does not match the active frozen execution.",
                )
            existing = self.conn.execute(
                "SELECT * FROM content_plans WHERE content_id=?", (row["id"],),
            ).fetchone()
            if existing is not None:
                if (
                    existing["plan_json"] == plan_json
                    and existing["plan_fingerprint"] == fingerprint
                ):
                    self.conn.commit()
                    return fingerprint
                raise ContentFoundationError(
                    "CONTENT_PLAN_CONFLICT", "A different immutable plan already exists.",
                )
            cursor = self.conn.execute(
                "INSERT INTO content_plans (content_id,job_id,run_id,account_id,"
                "research_card_id,content_type,plan_schema_version,"
                "route_config_version,route_config_fingerprint,"
                "frozen_input_sha256,evidence_manifest_sha256,plan_json,"
                "plan_fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"], execution.job_id, execution.run_id,
                    row["account_id"], row["research_card_id"], row["type"],
                    plan.schema_version, plan.route.config_version,
                    plan.route.config_fingerprint, frozen.input_sha256,
                    frozen.evidence_manifest_sha256, plan_json, fingerprint,
                    current_ts,
                ),
            )
            if cursor.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_PLAN_INSERT_FAILED", "Content plan insert failed.",
                )
            self.conn.commit()
            return fingerprint
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_content_writer_intent(
        self, execution: JobExecutionContext, intent: WriterIntent,
    ) -> str:
        """Persist one of the at most two immutable fake writer intents."""
        intent_json = intent.canonical_preimage()
        fingerprint = intent.fingerprint()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            frozen = self._assert_content_snapshot_in_transaction(
                row["account_id"], int(row["id"]),
            )
            if (
                intent.job_id != execution.job_id
                or intent.run_id != execution.run_id
                or intent.content_id != int(row["id"])
                or intent.account_id != row["account_id"]
                or intent.content_type.value != row["type"]
                or intent.frozen_input_sha256 != frozen.input_sha256
                or intent.evidence_manifest_sha256 != frozen.evidence_manifest_sha256
            ):
                raise ContentFoundationError(
                    "CONTENT_WRITER_INTENT_MISMATCH",
                    "Writer intent does not match the active frozen execution.",
                )
            existing = self.conn.execute(
                "SELECT * FROM content_writer_intents "
                "WHERE intent_id=? OR (content_id=? AND attempt_no=?)",
                (intent.intent_id, row["id"], intent.attempt_no),
            ).fetchone()
            if existing is not None:
                if (
                    existing["intent_id"] == intent.intent_id
                    and existing["intent_json"] == intent_json
                    and existing["intent_fingerprint"] == fingerprint
                ):
                    self.conn.commit()
                    return fingerprint
                raise ContentFoundationError(
                    "CONTENT_WRITER_INTENT_CONFLICT",
                    "A different writer intent already exists for this attempt.",
                )
            inserted = self.conn.execute(
                "INSERT INTO content_writer_intents (intent_id,job_id,run_id,"
                "content_id,account_id,content_type,attempt_no,call_mode,"
                "route_key,route_config_version,route_config_fingerprint,"
                "provider_status,api_model_id_status,availability_status,"
                "pricing_status,plan_fingerprint,brief_sha256,"
                "frozen_input_sha256,evidence_manifest_sha256,style_profile_id,"
                "negative_style_profile_id,rewrite_of_draft_fingerprint,"
                "rewrite_feedback_json,max_cost_usd,intent_json,"
                "intent_fingerprint,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    intent.intent_id, intent.job_id, intent.run_id,
                    intent.content_id, intent.account_id,
                    intent.content_type.value, intent.attempt_no,
                    intent.call_mode, intent.route.route_key,
                    intent.route.config_version,
                    intent.route.config_fingerprint, intent.route.provider,
                    intent.route.api_model_id, intent.route.availability,
                    intent.route.pricing_profile, intent.plan_fingerprint,
                    intent.brief_sha256, intent.frozen_input_sha256,
                    intent.evidence_manifest_sha256, intent.style_profile_id,
                    intent.negative_style_profile_id,
                    intent.rewrite_of_draft_fingerprint,
                    canonical_json(intent.rewrite_feedback),
                    intent.max_cost_usd, intent_json, fingerprint, current_ts,
                ),
            )
            if inserted.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_WRITER_INTENT_INSERT_FAILED",
                    "Writer intent insert failed.",
                )
            self.conn.commit()
            return fingerprint
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def begin_fake_content_writer_attempt(
        self, execution: JobExecutionContext, attempt_no: int,
    ) -> ProviderAttempt:
        """Create the canonical fake attempt without authorizing any transport."""
        if attempt_no not in (1, 2):
            raise ValueError("C2 permits only writer attempt 1 or 2.")
        request_id = self._provider_request_id(
            execution.job_id, CONTENT_PROVIDER_STAGE, attempt_no,
        )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_content_execution_fence(execution, current_ts)
            intent = self.conn.execute(
                "SELECT * FROM content_writer_intents "
                "WHERE job_id=? AND run_id=? AND attempt_no=?",
                (execution.job_id, execution.run_id, attempt_no),
            ).fetchone()
            if (
                intent is None
                or intent["call_mode"] != "FAKE"
                or float(intent["max_cost_usd"]) != 0.0
                or any(
                    intent[field] != "UNVERIFIED"
                    for field in (
                        "provider_status", "api_model_id_status",
                        "availability_status", "pricing_status",
                    )
                )
            ):
                raise ContentFoundationError(
                    "CONTENT_FAKE_INTENT_REQUIRED",
                    "Canonical fake attempt requires a zero-cost C2 writer intent.",
                )
            existing = self.conn.execute(
                "SELECT p.* FROM provider_attempts p "
                "JOIN content_writer_attempts wa ON wa.request_id=p.request_id "
                "WHERE p.request_id=? AND wa.intent_id=?",
                (request_id, intent["intent_id"]),
            ).fetchone()
            if existing is not None:
                if existing["status"] not in (
                    ProviderAttemptStatus.RESERVED.value,
                    ProviderAttemptStatus.REQUEST_STARTED.value,
                    ProviderAttemptStatus.SETTLED.value,
                ):
                    raise ContentFoundationError(
                        "CONTENT_FAKE_ATTEMPT_UNSAFE",
                        "Existing fake attempt is not safely resumable.",
                    )
                self.conn.commit()
                return self._provider_attempt_from_row(existing)
            extension = self.conn.execute(
                "INSERT INTO content_writer_attempts (request_id,intent_id,"
                "job_id,run_id,content_id,account_id,stage,attempt_no,call_mode,"
                "provider,model,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request_id, intent["intent_id"], execution.job_id,
                    execution.run_id, intent["content_id"], intent["account_id"],
                    CONTENT_PROVIDER_STAGE, attempt_no, "FAKE",
                    "fake-content-writer", intent["route_key"], current_ts,
                ),
            )
            if extension.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_FAKE_EXTENSION_FAILED",
                    "Fake writer attempt extension insert failed.",
                )
            # The historical canonical ledger has a positive reservation floor.
            # 0.000001 is a structural placeholder, never a cost or budget hold;
            # the zero-cost usage settles it to actual_cost_usd=0.0.
            self.conn.execute(
                "INSERT INTO provider_attempts (job_id,stage,attempt_no,"
                "request_id,status,reserved_amount_usd,reserved_at,"
                "execution_intent_fingerprint) VALUES (?,?,?,?,?,?,?,?)",
                (
                    execution.job_id, CONTENT_PROVIDER_STAGE, attempt_no,
                    request_id, ProviderAttemptStatus.RESERVED.value,
                    0.000001, current_ts, intent["intent_fingerprint"],
                ),
            )
            row = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=?",
                (request_id,),
            ).fetchone()
            assert row is not None
            self.conn.commit()
            return self._provider_attempt_from_row(row)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def mark_fake_content_writer_started(
        self, execution: JobExecutionContext, request_id: str,
    ) -> ProviderAttempt:
        """Mark only the local fake boundary; never set external-effect state."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_content_execution_fence(execution, current_ts)
            row = self.conn.execute(
                "SELECT p.* FROM provider_attempts p "
                "JOIN content_writer_attempts wa ON wa.request_id=p.request_id "
                "WHERE p.request_id=? AND p.job_id=? AND wa.call_mode='FAKE'",
                (request_id, execution.job_id),
            ).fetchone()
            if row is None:
                raise StaleJobExecutionError(execution.job_id)
            if row["status"] == ProviderAttemptStatus.RESERVED.value:
                cursor = self.conn.execute(
                    "UPDATE provider_attempts SET status='REQUEST_STARTED',"
                    "request_started_at=? WHERE request_id=? AND status='RESERVED'",
                    (current_ts, request_id),
                )
                if cursor.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
            elif row["status"] not in (
                ProviderAttemptStatus.REQUEST_STARTED.value,
                ProviderAttemptStatus.SETTLED.value,
            ):
                raise ContentFoundationError(
                    "CONTENT_FAKE_ATTEMPT_UNSAFE",
                    "Fake writer attempt cannot cross the local boundary.",
                )
            persisted = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=?", (request_id,),
            ).fetchone()
            assert persisted is not None
            self.conn.commit()
            return self._provider_attempt_from_row(persisted)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_content_draft(
        self, execution: JobExecutionContext, intent: WriterIntent, draft: FakeDraft,
    ) -> int:
        """Persist one immutable draft after its canonical fake usage settled."""
        draft_json = draft.canonical_preimage()
        draft_fingerprint = draft.fingerprint()
        request_id = self._provider_request_id(
            execution.job_id, CONTENT_PROVIDER_STAGE, draft.attempt_no,
        )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            if (
                draft.attempt_no != intent.attempt_no
                or draft.route_key != intent.route.route_key
                or intent.content_id != int(row["id"])
            ):
                raise ContentFoundationError(
                    "CONTENT_DRAFT_MISMATCH", "Draft does not match its writer intent.",
                )
            existing = self.conn.execute(
                "SELECT * FROM content_drafts WHERE content_id=? AND attempt_no=?",
                (row["id"], draft.attempt_no),
            ).fetchone()
            if existing is not None:
                if (
                    existing["draft_json"] == draft_json
                    and existing["draft_fingerprint"] == draft_fingerprint
                ):
                    self.conn.commit()
                    return int(existing["id"])
                raise ContentFoundationError(
                    "CONTENT_DRAFT_CONFLICT",
                    "A different immutable draft already exists for this attempt.",
                )
            cursor = self.conn.execute(
                "INSERT INTO content_drafts (content_id,job_id,run_id,account_id,"
                "attempt_no,request_id,intent_id,route_key,title,body,"
                "evidence_ids_json,unsupported_claims_json,personal_experience,"
                "style_ok,brief_compliant,rewrite_of_draft_fingerprint,"
                "draft_json,draft_fingerprint,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["id"], execution.job_id, execution.run_id,
                    row["account_id"], draft.attempt_no, request_id,
                    intent.intent_id, draft.route_key, draft.title, draft.body,
                    canonical_json(draft.evidence_ids_used),
                    canonical_json(draft.unsupported_claims),
                    int(draft.personal_experience), int(draft.style_ok),
                    int(draft.brief_compliant),
                    draft.rewrite_of_draft_fingerprint, draft_json,
                    draft_fingerprint, current_ts,
                ),
            )
            if cursor.rowcount != 1 or cursor.lastrowid is None:
                raise ContentFoundationError(
                    "CONTENT_DRAFT_INSERT_FAILED", "Draft insert failed.",
                )
            self.conn.commit()
            return int(cursor.lastrowid)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_content_draft_evaluation(
        self,
        execution: JobExecutionContext,
        *,
        draft_id: int,
        attempt_no: int,
        evaluation: DraftEvaluation,
    ) -> int:
        """Persist one of the exact nine append-only C2 evaluation results."""
        findings_json = canonical_json(evaluation.findings)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            existing = self.conn.execute(
                "SELECT * FROM content_draft_evaluations WHERE draft_id=? "
                "AND evaluation_type=? AND evaluator_version=?",
                (
                    draft_id, evaluation.evaluation_type.value,
                    evaluation.evaluator_version,
                ),
            ).fetchone()
            if existing is not None:
                same = (
                    existing["content_id"] == row["id"]
                    and int(existing["attempt_no"]) == attempt_no
                    and existing["result"] == evaluation.result
                    and existing["score"] == evaluation.score
                    and existing["findings_json"] == findings_json
                    and existing["draft_fingerprint"] == evaluation.draft_fingerprint
                    and existing["decision"] == evaluation.decision.value
                )
                if same:
                    self.conn.commit()
                    return int(existing["id"])
                raise ContentFoundationError(
                    "CONTENT_DRAFT_EVALUATION_CONFLICT",
                    "A different evaluation already exists.",
                )
            cursor = self.conn.execute(
                "INSERT INTO content_draft_evaluations (draft_id,content_id,"
                "job_id,run_id,attempt_no,evaluation_type,evaluator_version,"
                "result,score,findings_json,draft_fingerprint,decision,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    draft_id, row["id"], execution.job_id, execution.run_id,
                    attempt_no, evaluation.evaluation_type.value,
                    evaluation.evaluator_version, evaluation.result,
                    evaluation.score, findings_json,
                    evaluation.draft_fingerprint, evaluation.decision.value,
                    current_ts,
                ),
            )
            if cursor.rowcount != 1 or cursor.lastrowid is None:
                raise ContentFoundationError(
                    "CONTENT_DRAFT_EVALUATION_INSERT_FAILED",
                    "Draft evaluation insert failed.",
                )
            self.conn.commit()
            return int(cursor.lastrowid)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def finalize_content_draft(
        self,
        execution: JobExecutionContext,
        *,
        draft_fingerprint: str,
    ) -> ContentTransitionResult:
        """Set title/body and use the C1 command for atomic PENDING_APPROVAL."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            row = self._require_content_execution_fence(execution, current_ts)
            draft = self.conn.execute(
                "SELECT d.*,(SELECT count(*) FROM content_draft_evaluations e "
                "WHERE e.draft_id=d.id) AS evaluation_count,"
                "(SELECT count(*) FROM content_draft_evaluations e "
                "WHERE e.draft_id=d.id AND e.result='PASS' AND e.decision='PASS') "
                "AS pass_count FROM content_drafts d "
                "WHERE d.content_id=? AND d.draft_fingerprint=?",
                (row["id"], draft_fingerprint),
            ).fetchone()
            if (
                draft is None
                or int(draft["evaluation_count"]) != 9
                or int(draft["pass_count"]) != 9
            ):
                raise ContentFoundationError(
                    "CONTENT_DRAFT_NOT_APPROVABLE",
                    "Final draft must have exactly nine passing evaluations.",
                )
            updated = self.conn.execute(
                "UPDATE content_items SET title=?,body=?,updated_at=? "
                "WHERE id=? AND job_id=? AND run_id=? AND status IN ('RUNNING','REVISE')",
                (
                    draft["title"], draft["body"], current_ts, row["id"],
                    execution.job_id, execution.run_id,
                ),
            )
            if updated.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            score = float(self.conn.execute(
                "SELECT avg(score) FROM content_draft_evaluations WHERE draft_id=?",
                (draft["id"],),
            ).fetchone()[0])
            result_json = canonical_json({
                "attempt_no": int(draft["attempt_no"]),
                "draft_fingerprint": draft_fingerprint,
                "evaluation_count": 9,
                "mode": "FAKE_OFFLINE_C2",
            })
            self._apply_content_transition_command(
                mode="EXECUTION",
                job_id=execution.job_id,
                run_id=execution.run_id,
                content_id=int(row["id"]),
                account_id=row["account_id"],
                workflow=execution.workflow.value,
                source_status=row["status"],
                target_status=ContentStatus.PENDING_APPROVAL.value,
                target_run_status=RunStatus.SUCCESS.value,
                target_job_status=JobStatus.DONE.value,
                lease_owner=execution.lease_owner,
                execution_generation=execution.fence_token,
                lease_expires_at=row["lease_expires_at"],
                reason_code=None,
                result_json=result_json,
                score=score,
                current_ts=current_ts,
            )
            self.conn.commit()
            content_row = self.conn.execute(
                "SELECT * FROM content_items WHERE id=?", (row["id"],),
            ).fetchone()
            run_row = self.conn.execute(
                "SELECT * FROM content_runs WHERE run_id=?", (execution.run_id,),
            ).fetchone()
            assert content_row is not None and run_row is not None
            return ContentTransitionResult(
                content=self._content_item_from_row(content_row),
                run=self._content_run_from_row(run_row),
                idempotent=False,
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    # --- runy ---
    def create_run(self, run: Run) -> Run:
        self.conn.execute(
            "INSERT INTO runs (id, account_id, workflow, status, current_state, started_at)"
            " VALUES (?,?,?,?,?,?)",
            (run.id, run.account_id, run.workflow.value, run.status.value,
             run.current_state, _ts(run.started_at)),
        )
        self.conn.commit()
        return run

    def finish_run(self, run_id: str, status: str, cost_usd: float,
                   error: str | None = None) -> None:
        if self.conn.execute(
            "SELECT 1 FROM content_runs WHERE run_id=?", (run_id,),
        ).fetchone() is not None:
            raise ContentFoundationError(
                "CONTENT_GENERIC_RUN_TERMINALIZATION_FORBIDDEN",
                "CONTENT runs terminalize only through transition_content_execution.",
            )
        canonical_cost = _money(
            cost_usd, positive=False, label="Finished run cost",
        )
        try:
            target = RunStatus(status)
        except ValueError as exc:
            raise LifecycleTransitionError(
                "run", run_id, str(status), (),
                self._current_status("runs", run_id),
                detail="Unknown terminal run status.",
            ) from exc
        allowed_by_target = {
            RunStatus.SUCCESS: (RunStatus.RUNNING.value,),
            RunStatus.FAILED: (RunStatus.RUNNING.value, RunStatus.DRY_RUN.value),
            RunStatus.STOPPED: (RunStatus.RUNNING.value,),
            RunStatus.DRY_RUN: (RunStatus.DRY_RUN.value,),
        }
        allowed = allowed_by_target.get(target, ())
        if not allowed:
            raise LifecycleTransitionError(
                "run", run_id, target.value, allowed,
                self._current_status("runs", run_id),
                detail="finish_run accepts terminal targets only.",
            )
        if target in (RunStatus.SUCCESS, RunStatus.DRY_RUN):
            flow_row = self.conn.execute(
                "SELECT flow FROM research_runs WHERE id=?", (run_id,),
            ).fetchone()
            if flow_row is not None and flow_row["flow"] == ResearchFlow.STAGED.value:
                raise ResearchTopicIntegrityError(
                    "STAGED research must be finalized through "
                    "finalize_staged_research_with_card"
                )

        existing = self.conn.execute(
            "SELECT status, cost_usd, error, finished_at FROM runs WHERE id=?", (run_id,),
        ).fetchone()
        if existing is not None and existing["finished_at"] is not None:
            if (
                existing["status"] == target.value
                and _money_equal(
                    existing["cost_usd"],
                    canonical_cost,
                    label="Repeated run finalization cost",
                )
                and existing["error"] == error
            ):
                return
            raise LifecycleTransitionError(
                "run", run_id, target.value, allowed, str(existing["status"]),
                detail="Conflicting repeated run finalization.",
            )

        placeholders = ", ".join("?" for _ in allowed)
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? "
                f"WHERE id=? AND status IN ({placeholders}) "
                "AND finished_at IS NULL",
                (target.value, float(canonical_cost), error, _ts(), run_id, *allowed),
            )
            self._require_one_transition(
                cursor, table="runs", entity="run", identifier=run_id,
                target_status=target.value, allowed_source_statuses=allowed,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def finish_resumed_research_run(
        self, run_id: str, account_id: str, expected_flow: ResearchFlow,
        expected_finished_at: datetime, cost_usd: float, error: str,
    ) -> None:
        """Atomically records a later FAILED result for an explicit research resume.

        The caller must retain the terminal timestamp observed before the resumed
        attempt. It is the compare-and-swap token: two resumptions of the same
        snapshot cannot both rewrite the audit event.
        """
        canonical_cost = _money(
            cost_usd, positive=False, label="Resumed research failure cost",
        )
        allowed_research_statuses = {
            ResearchFlow.TWO_STAGE: (ResearchRunStatus.PARTIAL.value,),
            ResearchFlow.STAGED: (
                ResearchRunStatus.PARTIAL.value,
                ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                ResearchRunStatus.SOURCES_COMPLETE.value,
            ),
        }.get(expected_flow, ())
        allowed = tuple(
            f"{RunStatus.FAILED.value}+{expected_flow.value}:{status}"
            for status in allowed_research_statuses
        )
        expected_finished = _persisted_ts(expected_finished_at)
        try:
            row = self.conn.execute(
                "SELECT r.account_id AS run_account_id, r.workflow, r.status AS run_status, "
                "r.finished_at, rr.account_id AS research_account_id, rr.flow, "
                "rr.status AS research_status, rr.topic_id, t.account_id AS topic_account_id "
                "FROM runs r LEFT JOIN research_runs rr ON rr.id=r.id "
                "LEFT JOIN topics t ON t.id=rr.topic_id WHERE r.id=?",
                (run_id,),
            ).fetchone()
            current = None if row is None else (
                f"{row['run_status']}+{row['flow']}:{row['research_status']}"
            )
            invalid = (
                row is None
                or not allowed_research_statuses
                or row["research_account_id"] is None
                or row["topic_account_id"] is None
                or row["workflow"] != WorkflowType.RESEARCH.value
                or row["run_account_id"] != account_id
                or row["research_account_id"] != account_id
                or row["topic_account_id"] != account_id
                or row["flow"] != expected_flow.value
                or row["research_status"] not in allowed_research_statuses
                or row["run_status"] != RunStatus.FAILED.value
                or row["finished_at"] != expected_finished
            )
            if invalid:
                raise LifecycleTransitionError(
                    "resumed_research_run", run_id, RunStatus.FAILED.value,
                    allowed, current,
                    detail="Explicit research resume validation failed.",
                )
            placeholders = ", ".join("?" for _ in allowed_research_statuses)
            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? "
                "WHERE id=? AND account_id=? AND status IN (?) AND finished_at=? "
                "AND EXISTS (SELECT 1 FROM research_runs rr JOIN topics t ON t.id=rr.topic_id "
                "WHERE rr.id=runs.id AND rr.account_id=? AND t.account_id=? AND rr.flow=? "
                f"AND rr.status IN ({placeholders}))",
                (
                    RunStatus.FAILED.value, float(canonical_cost), error, _ts_precise(), run_id,
                    account_id, RunStatus.FAILED.value, expected_finished,
                    account_id, account_id, expected_flow.value,
                    *allowed_research_statuses,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleTransitionError(
                    "resumed_research_run", run_id, RunStatus.FAILED.value,
                    allowed, current,
                    detail="Conflicting concurrent resume finalization.",
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_run(self, run_id: str) -> Run | None:
        r = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if r is None:
            return None
        return self._run_from_row(r)

    @staticmethod
    def _run_from_row(r: sqlite3.Row) -> Run:
        return Run(
            id=r["id"], account_id=r["account_id"],
            workflow=WorkflowType(r["workflow"]), status=RunStatus(r["status"]),
            started_at=r["started_at"], finished_at=r["finished_at"],
            cost_usd=r["cost_usd"], error=r["error"],
        )

    # --- zużycie modelu / koszty ---
    def add_model_usage(self, usage: ModelUsage) -> ModelUsage:
        """Persist usage; research usage atomically refreshes the run cost cache."""
        if not usage.dry_run and not usage.request_id:
            raise ModelUsageRequestIdError(
                "New real model usage requires a durable provider request_id."
            )
        canonical_cost = _money(
            usage.estimated_cost_usd, positive=False, label="Model usage cost",
        )
        self.conn.execute("BEGIN")
        try:
            cur = self.conn.execute(
                "INSERT INTO model_usage (run_id, provider, model, task, input_tokens,"
                " output_tokens, cache_read_tokens, cache_write_tokens, web_search_requests,"
                " estimated_cost_usd, dry_run, request_id, is_legacy_usage, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    usage.run_id, usage.provider, usage.model, usage.task, usage.input_tokens,
                    usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens,
                    usage.web_search_requests, float(canonical_cost), int(usage.dry_run), usage.request_id,
                    0, _ts(usage.created_at),
                ),
            )
            if usage.task in _RESEARCH_USAGE_TASKS:
                self._set_run_cost_from_research_usage(usage.run_id)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        usage.id = int(cur.lastrowid)
        usage.estimated_cost_usd = float(canonical_cost)
        return usage

    def sum_real_cost_usd(self, since_prefix: str) -> float:
        rows = self.conn.execute(
            "SELECT estimated_cost_usd FROM model_usage"
            " WHERE dry_run=0 AND created_at LIKE ?",
            (f"{since_prefix}%",),
        ).fetchall()
        return float(_sum_money_rows(
            rows, "estimated_cost_usd", label="Persisted real usage total",
        ))

    def _research_usage_total(self, research_run_id: str) -> Decimal:
        rows = self.conn.execute(
            "SELECT estimated_cost_usd FROM model_usage "
            "WHERE run_id=? AND task IN (" + _RESEARCH_USAGE_PLACEHOLDERS + ")",
            (research_run_id, *_RESEARCH_USAGE_TASKS),
        ).fetchall()
        return _sum_money_rows(
            rows, "estimated_cost_usd", label="Canonical research usage total",
        )

    # --- Etap 1: trwała kolejka, lease i runtime system flags ---

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> Job:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise JobConflictError(f"Job {row['id']} has malformed payload_json.") from exc
        if not isinstance(payload, dict):
            raise JobConflictError(f"Job {row['id']} payload_json must be an object.")
        return Job(
            id=row["id"], account_id=row["account_id"], kind=JobKind(row["kind"]),
            workflow=WorkflowType(row["workflow"]), status=JobStatus(row["status"]),
            priority=int(row["priority"]), idempotency_key=row["idempotency_key"],
            topic_id=row["topic_id"], run_id=row["run_id"], payload=payload,
            schedule_reason=row["schedule_reason"], earliest_run_at=row["earliest_run_at"],
            deadline_at=row["deadline_at"], lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            execution_generation=(
                int(row["execution_generation"])
                if "execution_generation" in row.keys() else 0
            ),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            reserved_cost_usd=float(row["reserved_cost_usd"]),
            budget_reserved_at=row["budget_reserved_at"], last_error=row["last_error"],
            external_effect_started_at=row["external_effect_started_at"],
            created_at=row["created_at"], started_at=row["started_at"],
            finished_at=row["finished_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _job_now(now: datetime | None = None, *, clock: Clock | None = None) -> datetime:
        """Read lifecycle time only after the caller owns the SQLite write lock.

        ``now`` remains a narrow deterministic-test compatibility argument. Runtime
        callers must pass ``clock`` so waiting on ``BEGIN IMMEDIATE`` can never
        preserve a pre-lock timestamp as a fresh lease authorization.
        """
        if now is not None and clock is not None:
            raise ValueError("Pass either now or clock, not both.")
        current = clock.now() if clock is not None else (now or datetime.now(timezone.utc))
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Job lifecycle timestamps must be timezone-aware UTC instants.")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _rollback_preserving_primary(primary: BaseException, rollback) -> None:
        """Best-effort rollback that never replaces the operation's primary error."""
        try:
            rollback()
        except BaseException as rollback_error:
            primary.add_note(
                "Secondary SQLite rollback failure: "
                f"{type(rollback_error).__name__}. Primary error was preserved."
            )
            _LOGGER.error(
                "SQLite rollback failed while preserving primary %s",
                type(primary).__name__,
                exc_info=rollback_error,
            )

    def _job_execution_timestamp(self, execution: JobExecutionContext) -> str:
        if not execution.job_id.strip() or not execution.lease_owner.strip() or not execution.run_id.strip():
            raise ValueError("Job execution identifiers must be non-empty.")
        valid_execution = (
            (
                execution.kind is JobKind.RESEARCH
                and execution.workflow is WorkflowType.RESEARCH
            )
            or (
                execution.kind is JobKind.CONTENT
                and execution.workflow in (WorkflowType.ARTICLE, WorkflowType.NOTE)
            )
        )
        if not valid_execution:
            raise StaleJobExecutionError(
                execution.job_id, "execution kind/workflow does not authorize this mutation.",
            )
        return _persisted_ts(self._job_now(execution.now()))

    def _require_topic_generation_fence(
        self, execution: JobExecutionContext, current_ts: str,
    ) -> sqlite3.Row:
        """Closed job -> run -> account -> lease fence for TOPIC_GENERATION.

        There is deliberately no ``research_runs`` and no ``topics`` join: a
        topic-generation job carries no topic (0020 CHECK), because the topic
        only comes into existence from the provider response.  The returned row
        keeps the same column names as the research fence wherever they overlap
        and pins the research-only columns to NULL, so any research-only caller
        that is reached by mistake fails its own precondition rather than
        silently accepting a foreign lifecycle.
        """
        row = self.conn.execute(
            "SELECT j.status AS job_status,j.kind,j.workflow,j.run_id,j.lease_owner,"
            "j.lease_expires_at,j.account_id AS job_account_id,"
            "r.status AS run_status,r.account_id AS run_account_id,"
            "NULL AS research_status,NULL AS research_account_id,"
            "NULL AS topic_id,NULL AS flow,NULL AS topic_account_id "
            "FROM jobs j JOIN runs r ON r.id=j.run_id "
            "WHERE j.id=? AND j.run_id=? AND j.lease_owner=? "
            "AND j.lease_expires_at>=? AND j.status IN ('LEASED','RUNNING') "
            "AND j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION' "
            "AND j.topic_id IS NULL "
            "AND r.workflow='TOPIC_GENERATION' AND r.account_id=j.account_id",
            (
                execution.job_id, execution.run_id, execution.lease_owner,
                current_ts,
            ),
        ).fetchone()
        if row is None:
            raise StaleJobExecutionError(execution.job_id)
        return row

    def _require_job_execution_fence(
        self, execution: JobExecutionContext, current_ts: str,
        *, flow: ResearchFlow = ResearchFlow.SINGLE,
    ) -> sqlite3.Row:
        # One shared entry point keeps every existing caller (usage write,
        # attempt reservation, request-start, release, escalation, settlement)
        # on exactly one fence implementation per workflow.  RESEARCH keeps its
        # original query byte-for-byte below.
        kind_row = self.conn.execute(
            "SELECT kind FROM jobs WHERE id=?", (execution.job_id,),
        ).fetchone()
        if kind_row is not None and kind_row["kind"] == JobKind.TOPIC_GENERATION.value:
            return self._require_topic_generation_fence(execution, current_ts)
        if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
            return self._require_content_execution_fence(execution, current_ts)
        row = self.conn.execute(
            "SELECT j.status AS job_status,j.kind,j.workflow,j.run_id,j.lease_owner,"
            "j.lease_expires_at,r.status AS run_status,r.account_id AS run_account_id,"
            "rr.status AS research_status,rr.account_id AS research_account_id,"
            "rr.topic_id,rr.flow,t.account_id AS topic_account_id "
            "FROM jobs j JOIN runs r ON r.id=j.run_id "
            "JOIN research_runs rr ON rr.id=r.id "
            "JOIN topics t ON t.id=rr.topic_id "
            "WHERE j.id=? AND j.run_id=? AND j.lease_owner=? "
            "AND j.lease_expires_at>=? AND j.status IN ('LEASED','RUNNING') "
            "AND j.kind='RESEARCH' AND j.workflow='RESEARCH' "
            "AND r.workflow='RESEARCH' AND r.account_id=j.account_id "
            "AND rr.account_id=j.account_id AND rr.topic_id=j.topic_id "
            "AND rr.flow=? AND t.account_id=j.account_id",
            (
                execution.job_id, execution.run_id, execution.lease_owner,
                current_ts, flow.value,
            ),
        ).fetchone()
        if row is None:
            raise StaleJobExecutionError(execution.job_id)
        return row

    @staticmethod
    def _provider_attempt_from_row(row: sqlite3.Row) -> ProviderAttempt:
        return ProviderAttempt(
            job_id=row["job_id"], stage=row["stage"], attempt_no=int(row["attempt_no"]),
            request_id=row["request_id"], status=ProviderAttemptStatus(row["status"]),
            execution_intent_fingerprint=row["execution_intent_fingerprint"],
            reserved_amount_usd=float(row["reserved_amount_usd"]),
            reserved_at=row["reserved_at"], request_started_at=row["request_started_at"],
            settled_at=row["settled_at"], released_at=row["released_at"],
            actual_cost_usd=row["actual_cost_usd"], error_code=row["error_code"],
            reconciled_at=row["reconciled_at"] if "reconciled_at" in row.keys() else None,
            reconciled_by=row["reconciled_by"] if "reconciled_by" in row.keys() else None,
            reconciliation_note=row["reconciliation_note"] if "reconciliation_note" in row.keys() else None,
            reconciliation_resolution=(
                row["reconciliation_resolution"] if "reconciliation_resolution" in row.keys() else None
            ),
        )

    @staticmethod
    def _provider_request_id(job_id: str, stage: str, attempt_no: int) -> str:
        """Stable, deterministic provider identity; never time/random based."""
        return f"{job_id}:{stage}:{attempt_no}"

    @staticmethod
    def _validate_provider_attempt_identity(stage: str, attempt_no: int) -> None:
        if not stage or len(stage) > 64 or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in stage):
            raise ValueError("Provider attempt stage must be a controlled lowercase identifier.")
        if attempt_no < 1:
            raise ValueError("Provider attempt number must be positive.")

    @staticmethod
    def _canonical_payload(payload: dict) -> str:
        try:
            normalized: dict = payload
            if payload.get("execution") == "durable_provider_v1":
                raise DurableExecutionIntentError(
                    "durable_provider_v1 is retired; use durable_provider_v2.",
                    code="UNSUPPORTED_EXECUTION_CONTRACT",
                )
            if payload.get("execution") == "durable_provider_v2":
                normalized = canonicalize_durable_research_payload(payload)
            elif payload.get("execution") == "offline_evidence_v1":
                normalized = canonicalize_offline_evidence_payload(payload)
            elif payload.get("execution") == TOPIC_GENERATION_EXECUTION:
                normalized = canonicalize_topic_generation_payload(payload)
            elif payload.get("execution") == CONTENT_EXECUTION:
                normalized = canonicalize_content_job_payload(payload)
            return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (
            ContentContractError,
            DurableExecutionIntentError,
            OfflineEvidenceIntentError,
        ) as exc:
            code = getattr(exc, "code", "OFFLINE_EVIDENCE_INTENT_INVALID")
            raise JobPayloadValidationError(code, str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise JobPayloadValidationError(
                "MALFORMED_JOB_PAYLOAD", "Job payload must be JSON-serializable."
            ) from exc

    @staticmethod
    def _job_context_matches(row: sqlite3.Row, job: Job, payload_json: str) -> bool:
        return JobEnqueueContext.from_row(row) == replace(
            JobEnqueueContext.from_job(job), payload_json=payload_json,
        )

    def _validate_job_enqueue_relation(self, job: Job) -> None:
        # Local import avoids loading the scheduler composition package while the
        # SQLite adapter itself is still being imported.
        from app.scheduler.scheduling import SchedulingValidationError, validate_schedule_reason

        if not job.idempotency_key.strip():
            raise JobConflictError("Job idempotency_key cannot be blank.")
        try:
            validate_schedule_reason(job.schedule_reason)
        except SchedulingValidationError as exc:
            raise JobConflictError(
                "Job schedule_reason must be a controlled, bounded scheduling code."
            ) from exc
        if job.status != JobStatus.QUEUED or job.lease_owner is not None or job.lease_expires_at is not None:
            raise JobConflictError("enqueue_job accepts only a fresh QUEUED job without a lease.")
        if job.attempts != 0 or job.started_at is not None or job.finished_at is not None:
            raise JobConflictError("enqueue_job accepts only a job without prior attempts or lifecycle timestamps.")
        if (
            job.max_attempts < 1
            or not _money_equal(
                job.reserved_cost_usd, Decimal("0"), label="Fresh job reservation",
            )
            or job.budget_reserved_at is not None or job.external_effect_started_at is not None
        ):
            raise JobConflictError("enqueue_job requires max_attempts >= 1 and no pre-existing budget reservation.")
        if job.deadline_at is not None and job.deadline_at < job.earliest_run_at:
            raise JobConflictError("Job deadline_at cannot precede earliest_run_at.")
        if job.topic_id is not None:
            topic = self.conn.execute(
                "SELECT account_id FROM topics WHERE id=?", (job.topic_id,),
            ).fetchone()
            if topic is None or topic["account_id"] != job.account_id:
                raise JobConflictError("Job topic must belong to the same account.")
        if job.run_id is not None:
            run = self.conn.execute(
                "SELECT account_id FROM runs WHERE id=?", (job.run_id,),
            ).fetchone()
            if run is None or run["account_id"] != job.account_id:
                raise JobConflictError("Job run must belong to the same account.")

    def enqueue_job(self, job: Job) -> Job:
        return self.enqueue_job_result(job).job

    def enqueue_job_result(self, job: Job) -> JobEnqueueResult:
        """Atomowo tworzy QUEUED job lub zwraca identyczny job idempotentny."""
        payload_json = self._canonical_payload(job.payload)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            existing = self.conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (job.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if self._job_context_matches(existing, job, payload_json):
                    result = self._job_from_row(existing)
                    self.conn.commit()
                    return JobEnqueueResult(job=result, created=False)
                raise JobConflictError(
                    f"idempotency_key {job.idempotency_key!r} already belongs to a different job context."
                )

            self._validate_job_enqueue_relation(job)
            now = self._job_now(None)
            created_at = _persisted_ts(job.created_at)
            self.conn.execute(
                "INSERT INTO jobs (id,account_id,kind,workflow,status,priority,idempotency_key,"
                "topic_id,run_id,payload_json,schedule_reason,earliest_run_at,deadline_at,"
                "lease_owner,lease_expires_at,attempts,max_attempts,reserved_cost_usd,"
                "budget_reserved_at,external_effect_started_at,last_error,created_at,started_at,finished_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job.id, job.account_id, job.kind.value, job.workflow.value,
                    JobStatus.QUEUED.value, job.priority, job.idempotency_key,
                    job.topic_id, job.run_id, payload_json, job.schedule_reason,
                    _persisted_ts(job.earliest_run_at),
                    None if job.deadline_at is None else _persisted_ts(job.deadline_at),
                    None, None, 0, job.max_attempts, 0.0, None, None, None,
                    created_at, None, None, _persisted_ts(now),
                ),
            )
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job.id,)).fetchone()
            self.conn.commit()
            assert row is not None
            return JobEnqueueResult(job=self._job_from_row(row), created=True)
        except sqlite3.IntegrityError as exc:
            if self.conn.in_transaction:
                self.conn.rollback()
            active = self.conn.execute(
                "SELECT id FROM jobs WHERE account_id=? AND topic_id=? AND kind='RESEARCH' "
                "AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION')",
                (job.account_id, job.topic_id),
            ).fetchone()
            if job.kind == JobKind.RESEARCH and job.topic_id is not None and active is not None:
                raise JobConflictError(
                    f"Active research job {active['id']} already exists for topic {job.topic_id}."
                ) from exc
            raise JobConflictError("Job violates a durable queue constraint.") from exc
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return None if row is None else self._job_from_row(row)

    def get_job_by_idempotency_key(self, idempotency_key: str) -> Job | None:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,),
        ).fetchone()
        return None if row is None else self._job_from_row(row)

    def _job_lifecycle_error(
        self, job_id: str, target: JobStatus | str, allowed: Sequence[str], *, detail: str,
    ) -> LifecycleTransitionError:
        current = self._current_status("jobs", job_id)
        return LifecycleTransitionError("job", job_id, str(target), allowed, current, detail=detail)

    def claim_next_job(
        self, lease_owner: str, lease_seconds: int, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> JobLease | None:
        """Claims exactly one queued job in a BEGIN IMMEDIATE transaction.

        ``attempts`` counts successful lease acquisitions, including a later claim
        after a safe recovery. Expired deadlines and exhausted queued jobs become
        explicit FAILED records before selection; they are never silently run.
        """
        if not lease_owner.strip() or lease_seconds <= 0:
            raise ValueError("lease_owner must be non-empty and lease_seconds must be positive.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            lease_until = _persisted_ts(current + timedelta(seconds=lease_seconds))
            self.conn.execute(
                "UPDATE jobs SET status='FAILED', last_error='Deadline elapsed before claim.', "
                "finished_at=?, updated_at=?, reserved_cost_usd=0.0, budget_reserved_at=NULL "
                "WHERE status='QUEUED' AND kind<>'CONTENT' "
                "AND deadline_at IS NOT NULL AND deadline_at < ?",
                (current_ts, current_ts, current_ts),
            )
            self.conn.execute(
                "UPDATE jobs SET status='FAILED', last_error='Maximum attempts exhausted before claim.', "
                "finished_at=?, updated_at=?, reserved_cost_usd=0.0, budget_reserved_at=NULL "
                "WHERE status='QUEUED' AND kind<>'CONTENT' AND attempts >= max_attempts",
                (current_ts, current_ts),
            )
            selected = self.conn.execute(
                "SELECT id FROM jobs WHERE status='QUEUED' AND kind<>'CONTENT' "
                "AND earliest_run_at <= ? "
                "AND (deadline_at IS NULL OR deadline_at >= ?) AND attempts < max_attempts "
                "ORDER BY priority DESC, deadline_at IS NULL ASC, deadline_at ASC, created_at ASC, id ASC "
                "LIMIT 1",
                (current_ts, current_ts),
            ).fetchone()
            if selected is None:
                self.conn.commit()
                return None
            cursor = self.conn.execute(
                "UPDATE jobs SET status='LEASED', lease_owner=?, lease_expires_at=?, "
                "attempts=attempts+1,"
                "execution_generation=execution_generation+CASE "
                "WHEN kind='CONTENT' THEN 1 ELSE 0 END,"
                "started_at=COALESCE(started_at, ?), updated_at=? "
                "WHERE id=? AND status='QUEUED' AND earliest_run_at <= ? "
                "AND (deadline_at IS NULL OR deadline_at >= ?) AND attempts < max_attempts",
                (lease_owner, lease_until, current_ts, current_ts, selected["id"], current_ts, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=selected["id"],
                target_status=JobStatus.LEASED.value,
                allowed_source_statuses=(JobStatus.QUEUED.value,),
                detail="Atomic claim compare-and-swap failed.",
            )
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (selected["id"],)).fetchone()
            self.conn.commit()
            assert row is not None
            claimed = self._job_from_row(row)
            assert claimed.lease_expires_at is not None
            return JobLease(
                job=claimed, lease_owner=lease_owner, lease_expires_at=claimed.lease_expires_at,
            )
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def claim_specific_job(
        self, job_id: str, lease_owner: str, lease_seconds: int, *,
        now: datetime | None = None, clock: Clock | None = None,
    ) -> JobLease | None:
        """Atomically leases EXACTLY the named QUEUED job, never any other.

        Unlike :meth:`claim_next_job` this performs no queue-wide deadline/attempt
        sweep and no priority selection: it only compare-and-swaps the one
        ``job_id`` from QUEUED to LEASED. Other queued jobs are never selected,
        failed, or mutated by this call. If the named job is not currently an
        eligible QUEUED row (wrong id, already leased/terminal, deadline elapsed,
        or attempts exhausted) it returns ``None`` and touches nothing.
        """
        if not lease_owner.strip() or lease_seconds <= 0:
            raise ValueError("lease_owner must be non-empty and lease_seconds must be positive.")
        if not job_id.strip():
            raise ValueError("job_id must be non-empty.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            lease_until = _persisted_ts(current + timedelta(seconds=lease_seconds))
            cursor = self.conn.execute(
                "UPDATE jobs SET status='LEASED', lease_owner=?, lease_expires_at=?, "
                "attempts=attempts+1,"
                "execution_generation=execution_generation+CASE "
                "WHEN kind='CONTENT' THEN 1 ELSE 0 END,"
                "started_at=COALESCE(started_at, ?), updated_at=? "
                "WHERE id=? AND status='QUEUED' AND earliest_run_at <= ? "
                "AND (deadline_at IS NULL OR deadline_at >= ?) AND attempts < max_attempts",
                (lease_owner, lease_until, current_ts, current_ts, job_id, current_ts, current_ts),
            )
            if cursor.rowcount != 1:
                self.conn.commit()
                return None
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            self.conn.commit()
            assert row is not None
            claimed = self._job_from_row(row)
            assert claimed.lease_expires_at is not None
            return JobLease(
                job=claimed, lease_owner=lease_owner, lease_expires_at=claimed.lease_expires_at,
            )
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def _transition_leased_job(
        self, job_id: str, lease_owner: str, target: JobStatus, *, error: str | None,
        now: datetime | None, clock: Clock | None, release_budget: bool,
    ) -> None:
        allowed = (JobStatus.LEASED.value, JobStatus.RUNNING.value)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
                    "CONTENT jobs terminalize only through the dedicated atomic boundary.",
                )
            terminal_fields = (
                ", finished_at=?, reserved_cost_usd=0.0, budget_reserved_at=NULL"
                if release_budget else ""
            )
            params: list[object] = [target.value, error, current_ts]
            if release_budget:
                params.append(current_ts)
            params.extend([job_id, lease_owner, current_ts])
            cursor = self.conn.execute(
                "UPDATE jobs SET status=?, last_error=?, lease_owner=NULL, lease_expires_at=NULL, "
                "updated_at=?" + terminal_fields + " WHERE id=? "
                "AND status IN ('LEASED','RUNNING') AND lease_owner=? AND lease_expires_at >= ?",
                tuple(params),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status=target.value, allowed_source_statuses=allowed,
                detail="Lease owner, lease freshness, or lifecycle state did not match.",
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def mark_job_running(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(
                self._job_now(now, clock=None if now is not None else clock)
            )
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_RUNTIME_MUTATION_FORBIDDEN",
                    "CONTENT execution starts only through initialize_content_run_for_job.",
                )
            cursor = self.conn.execute(
                "UPDATE jobs SET status='RUNNING', updated_at=? WHERE id=? AND status='LEASED' "
                "AND lease_owner=? AND lease_expires_at >= ?",
                (current_ts, job_id, lease_owner, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status=JobStatus.RUNNING.value,
                allowed_source_statuses=(JobStatus.LEASED.value,),
                detail="Lease owner or expiry did not match.",
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def initialize_research_run_for_job(
        self, job_id: str, lease_owner: str, run_id: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> ResearchRunInitialization:
        """Atomically initializes the offline single-flow execution for one job lease.

        This is deliberately the only Stage 1 worker path that may create a
        research ``Run``.  The new run, its one-to-one ``research_runs`` row,
        and the job's CAS binding either commit together or do not exist at all.
        A retry while the same fresh lease already sees an attached run returns
        that durable relation instead of creating a second execution.
        """
        if not run_id.strip():
            raise ValueError("run_id must be non-empty.")
        if not lease_owner.strip():
            raise ValueError("lease_owner must be non-empty.")

        allowed = (JobStatus.LEASED.value, JobStatus.RUNNING.value)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            job_row = self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if job_row is None:
                raise self._job_lifecycle_error(
                    job_id, "RESEARCH_EXECUTION_INITIALIZED", allowed,
                    detail="Job must exist before research execution can be initialized.",
                )
            job = self._job_from_row(job_row)
            if job.kind is not JobKind.RESEARCH:
                raise JobRunRelationError(
                    "JOB_KIND_MISMATCH", job_id,
                    "only kind=RESEARCH may initialize a research run.",
                )
            if job.workflow is not WorkflowType.RESEARCH:
                raise JobRunRelationError(
                    "JOB_WORKFLOW_MISMATCH", job_id,
                    "only workflow=RESEARCH may initialize a research run.",
                )
            if job.topic_id is None:
                raise JobRunRelationError(
                    "JOB_TOPIC_MISSING", job_id,
                    "research job must have a topic_id before initialization.",
                )
            if job.status.value not in allowed:
                raise self._job_lifecycle_error(
                    job_id, "RESEARCH_EXECUTION_INITIALIZED", allowed,
                    detail="Initialization requires an active job lifecycle state.",
                )
            if job.lease_owner != lease_owner or job.lease_expires_at is None or (
                _persisted_ts(job.lease_expires_at) < current_ts
            ):
                raise self._job_lifecycle_error(
                    job_id, "RESEARCH_EXECUTION_INITIALIZED", allowed,
                    detail="Initialization requires the caller's fresh lease.",
                )
            dry_payload = {
                "account_id": job.account_id,
                "topic_id": int(job.topic_id),
                "dry_run": True,
            }
            if job.payload == dry_payload:
                expected_run_status = RunStatus.DRY_RUN
            else:
                if job.payload.get("execution") == "durable_provider_v1":
                    raise JobRunRelationError(
                        "DURABLE_PROVIDER_V1_UNSUPPORTED",
                        job_id,
                        "durable_provider_v1 is retired; enqueue a durable_provider_v2 intent.",
                    )
                try:
                    normalized = canonicalize_durable_research_payload(job.payload)
                except DurableExecutionIntentError as exc:
                    raise JobRunRelationError(
                        exc.code,
                        job_id,
                        "initialization requires a valid durable_provider_v2 payload.",
                    ) from exc
                if (
                    normalized["account_id"] != job.account_id
                    or normalized["topic_id"] != int(job.topic_id)
                ):
                    raise JobRunRelationError(
                        "RESEARCH_PAYLOAD_IDENTITY_MISMATCH",
                        job_id,
                        "durable_provider_v2 payload identity must match the job.",
                    )
                expected_run_status = RunStatus.RUNNING
            topic = self.conn.execute(
                "SELECT 1 FROM topics WHERE id=? AND account_id=?",
                (job.topic_id, job.account_id),
            ).fetchone()
            if topic is None:
                raise JobRunRelationError(
                    "JOB_TOPIC_ACCOUNT_MISMATCH", job_id,
                    "research job topic must belong to its account.",
                )

            if job.run_id is not None:
                run_row = self.conn.execute(
                    "SELECT * FROM runs WHERE id=?", (job.run_id,),
                ).fetchone()
                research_row = self.conn.execute(
                    "SELECT * FROM research_runs WHERE id=?", (job.run_id,),
                ).fetchone()
                if run_row is None or research_row is None:
                    raise JobRunRelationError(
                        "ATTACHED_RESEARCH_RUN_MISSING", job_id,
                        "attached job run must have both run and research-run records.",
                    )
                run = self._run_from_row(run_row)
                research_run = self._research_run_from_row(research_row)
                if (
                    run.account_id != job.account_id
                    or run.workflow is not WorkflowType.RESEARCH
                    or research_run.account_id != job.account_id
                    or research_run.topic_id != job.topic_id
                    or research_run.flow is not ResearchFlow.SINGLE
                ):
                    raise JobRunRelationError(
                        "ATTACHED_RESEARCH_RUN_INVALID", job_id,
                        "attached run relation is incompatible with the research job.",
                    )
                allowed_existing_state = (
                    run.status is expected_run_status
                    and run_row["finished_at"] is None
                    and run_row["error"] is None
                    and _money_equal(
                        run_row["cost_usd"], Decimal("0"), label="Attached run cost",
                    )
                    and research_run.status is ResearchRunStatus.PENDING
                    and research_row["research_card_id"] is None
                    and research_row["error"] is None
                    and _money_equal(
                        research_row["total_cost_usd"],
                        Decimal("0"),
                        label="Attached research run cost",
                    )
                )
                if not allowed_existing_state:
                    raise JobRunRelationError(
                        "ATTACHED_RESEARCH_RUN_STATE_INVALID", job_id,
                        "an existing worker initialization must remain exactly "
                        "the expected run status plus single:PENDING without result, error, cost, or finished_at.",
                    )
                self.conn.commit()
                return ResearchRunInitialization(
                    job=job, run=run, research_run=research_run, created=False,
                )

            self.conn.execute(
                "INSERT INTO runs (id, account_id, workflow, status, current_state, started_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    run_id, job.account_id, WorkflowType.RESEARCH.value,
                    expected_run_status.value, "research", current_ts,
                ),
            )
            self.conn.execute(
                "INSERT INTO research_runs (id, account_id, topic_id, flow, status, "
                "is_force_reresearch, total_cost_usd, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run_id, job.account_id, job.topic_id, ResearchFlow.SINGLE.value,
                    ResearchRunStatus.PENDING.value, 0, 0.0, current_ts, current_ts,
                ),
            )
            cursor = self.conn.execute(
                "UPDATE jobs SET run_id=?, updated_at=? WHERE id=? AND run_id IS NULL "
                "AND status IN ('LEASED','RUNNING') AND lease_owner=? AND lease_expires_at >= ?",
                (run_id, current_ts, job_id, lease_owner, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status="RESEARCH_EXECUTION_INITIALIZED", allowed_source_statuses=allowed,
                detail="Initialization requires a fresh lease and an empty run_id.",
            )
            initialized_job_row = self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            run_row = self.conn.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,),
            ).fetchone()
            research_row = self.conn.execute(
                "SELECT * FROM research_runs WHERE id=?", (run_id,),
            ).fetchone()
            if initialized_job_row is None or run_row is None or research_row is None:
                raise JobRunRelationError(
                    "RESEARCH_EXECUTION_INITIALIZATION_INCOMPLETE", job_id,
                    "transaction did not expose every required execution record.",
                )
            initialized = ResearchRunInitialization(
                job=self._job_from_row(initialized_job_row),
                run=self._run_from_row(run_row),
                research_run=self._research_run_from_row(research_row),
                created=True,
            )
            self.conn.commit()
            return initialized
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def assert_job_execution_active(self, execution: JobExecutionContext) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def initialize_offline_evidence_run_for_job(
        self, job_id: str, lease_owner: str, run_id: str, *,
        clock: Clock,
    ) -> ResearchRunInitialization:
        """Create or resume the exact E2-A STAGED run under a fresh job lease."""
        if not run_id.strip() or not lease_owner.strip():
            raise ValueError("offline evidence execution identifiers must be non-empty.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = _persisted_ts(self._job_now(clock=clock))
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobRunRelationError("JOB_MISSING", job_id, "offline evidence job is missing.")
            job = self._job_from_row(row)
            try:
                payload = canonicalize_offline_evidence_payload(job.payload)
            except OfflineEvidenceIntentError as exc:
                raise JobRunRelationError(
                    "OFFLINE_EVIDENCE_INTENT_INVALID", job_id, str(exc),
                ) from exc
            if (
                job.kind is not JobKind.RESEARCH
                or job.workflow is not WorkflowType.RESEARCH
                or job.topic_id is None
                or payload["account_id"] != job.account_id
                or payload["topic_id"] != job.topic_id
            ):
                raise JobRunRelationError(
                    "OFFLINE_EVIDENCE_IDENTITY_MISMATCH", job_id,
                    "job, payload, account and topic identity must match.",
                )
            if (
                job.status not in (JobStatus.LEASED, JobStatus.RUNNING)
                or job.lease_owner != lease_owner
                or job.lease_expires_at is None
                or _persisted_ts(job.lease_expires_at) < now
            ):
                raise StaleJobExecutionError(job_id)
            if self.conn.execute(
                "SELECT 1 FROM topics WHERE id=? AND account_id=?",
                (job.topic_id, job.account_id),
            ).fetchone() is None:
                raise JobRunRelationError(
                    "JOB_TOPIC_ACCOUNT_MISMATCH", job_id,
                    "offline evidence topic must belong to the job account.",
                )

            if job.run_id is None:
                self.conn.execute(
                    "INSERT INTO runs (id,account_id,workflow,status,current_state,started_at,"
                    "cost_usd) VALUES (?,?,?,?,?,?,0)",
                    (run_id, job.account_id, WorkflowType.RESEARCH.value,
                     RunStatus.DRY_RUN.value, "offline_evidence", now),
                )
                self.conn.execute(
                    "INSERT INTO research_runs (id,account_id,topic_id,flow,status,"
                    "is_force_reresearch,total_cost_usd,created_at,updated_at)"
                    " VALUES (?,?,?,?,?,0,0,?,?)",
                    (run_id, job.account_id, job.topic_id, ResearchFlow.STAGED.value,
                     ResearchRunStatus.DISCOVERY_PENDING.value, now, now),
                )
                cursor = self.conn.execute(
                    "UPDATE jobs SET run_id=?,updated_at=? WHERE id=? AND run_id IS NULL "
                    "AND lease_owner=? AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                    (run_id, now, job_id, lease_owner, now),
                )
                if cursor.rowcount != 1:
                    raise StaleJobExecutionError(job_id)
                created = True
                attached_run_id = run_id
            else:
                created = False
                attached_run_id = job.run_id

            run_row = self.conn.execute(
                "SELECT * FROM runs WHERE id=?", (attached_run_id,),
            ).fetchone()
            research_row = self.conn.execute(
                "SELECT * FROM research_runs WHERE id=?", (attached_run_id,),
            ).fetchone()
            if run_row is None or research_row is None:
                raise JobRunRelationError(
                    "ATTACHED_RESEARCH_RUN_MISSING", job_id,
                    "offline evidence run relation is incomplete.",
                )
            run = self._run_from_row(run_row)
            research_run = self._research_run_from_row(research_row)
            resumable = {
                ResearchRunStatus.DISCOVERY_PENDING,
                ResearchRunStatus.DISCOVERY_COMPLETE,
                ResearchRunStatus.EXTRACTION_IN_PROGRESS,
                ResearchRunStatus.SOURCES_COMPLETE,
                ResearchRunStatus.SYNTHESIS_PENDING,
            }
            if (
                run.account_id != job.account_id
                or run.workflow is not WorkflowType.RESEARCH
                or run.status is not RunStatus.DRY_RUN
                or run_row["finished_at"] is not None
                or float(run_row["cost_usd"]) != 0
                or research_run.account_id != job.account_id
                or research_run.topic_id != job.topic_id
                or research_run.flow is not ResearchFlow.STAGED
                or research_run.status not in resumable
                or research_run.research_card_id is not None
                or float(research_run.total_cost_usd) != 0
            ):
                raise JobRunRelationError(
                    "ATTACHED_OFFLINE_EVIDENCE_RUN_INVALID", job_id,
                    "attached run is not a zero-cost resumable E2-A checkpoint.",
                )
            job = self._job_from_row(self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone())
            result = ResearchRunInitialization(
                job=job, run=run, research_run=research_run, created=created,
            )
            self.conn.commit()
            return result
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def assert_offline_evidence_execution_active(
        self, execution: JobExecutionContext,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, now, flow=ResearchFlow.STAGED)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def assert_durable_provider_attempt_active(
        self, context: DurableProviderAttemptContext, *, clock: Clock,
    ) -> ProviderAttempt:
        """Atomically prove the complete single-research lifecycle before SDK.

        This is intentionally stricter than a lease check.  The request can
        cross the provider boundary only while one current job, run,
        research_run, attempt and durable snapshot still describe the same
        pre-request single-flow lifecycle.
        """
        expected_fence = f"{context.job_id}:{context.run_id}:{context.lease_owner}"
        if context.fence_token != expected_fence:
            raise StaleJobExecutionError(
                context.job_id, "durable provider context fence token is invalid.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            # checked_at is diagnostic evidence only. Lease authorization uses
            # the execution clock freshly inside this SQLite transaction.
            current_ts = _persisted_ts(self._job_now(clock=clock))
            # WAVE 0B's paid durable contract supports exactly the persisted
            # ``research`` stage.  Existing non-provider boundary regression
            # tests use other controlled labels; preserve their older lease-only
            # guard rather than silently pretending they are durable single
            # research requests.
            # Routing keys on the durable JOB KIND, never on the stage label
            # alone: existing RESEARCH jobs may legitimately carry other stage
            # names (including 'topics') and must keep their original guard.
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (context.job_id,),
            ).fetchone()
            is_topic_generation = (
                kind_row is not None
                and kind_row["kind"] == JobKind.TOPIC_GENERATION.value
            )
            if is_topic_generation and context.stage == TOPIC_GENERATION_PROVIDER_STAGE:
                # The paid topic-generation boundary: exactly the same proof as
                # research minus the research_run/topic relation, which cannot
                # exist before the model has answered.
                topic_row = self.conn.execute(
                    "SELECT p.* FROM provider_attempts p "
                    "JOIN jobs j ON j.id=p.job_id "
                    "JOIN runs r ON r.id=j.run_id "
                    "WHERE p.request_id=? AND p.job_id=? AND p.stage=? "
                    "AND p.attempt_no=? AND p.status='REQUEST_STARTED' "
                    "AND j.run_id=? AND j.lease_owner=? AND j.lease_expires_at>=? "
                    "AND j.status IN ('LEASED','RUNNING') "
                    "AND j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION' "
                    "AND j.topic_id IS NULL "
                    "AND r.id=? AND r.account_id=j.account_id "
                    "AND r.workflow='TOPIC_GENERATION' AND r.status='RUNNING' "
                    "AND p.execution_intent_fingerprint IS NOT NULL "
                    "AND EXISTS (SELECT 1 FROM topic_generation_approvals a "
                    "  WHERE a.job_id=j.id AND a.consumed_at IS NOT NULL "
                    "    AND a.expires_at > ? "
                    "    AND a.intent_fingerprint = p.execution_intent_fingerprint)",
                    (
                        context.request_id, context.job_id, context.stage,
                        context.attempt_no, context.run_id, context.lease_owner,
                        current_ts, context.run_id, current_ts,
                    ),
                ).fetchone()
                if topic_row is None:
                    raise StaleJobExecutionError(
                        context.job_id,
                        "topic generation provider boundary is not active for the "
                        "current job/run/lease/approval.",
                    )
                self.conn.commit()
                return self._provider_attempt_from_row(topic_row)
            if context.stage != "research":
                legacy = self.conn.execute(
                    "SELECT p.* FROM provider_attempts p "
                    "JOIN jobs j ON j.id=p.job_id "
                    "JOIN runs r ON r.id=j.run_id "
                    "WHERE p.request_id=? AND p.job_id=? AND p.stage=? AND p.attempt_no=? "
                    "AND p.status='REQUEST_STARTED' AND j.run_id=? AND j.lease_owner=? "
                    "AND j.lease_expires_at>=? AND j.status IN ('LEASED','RUNNING') "
                    "AND j.kind='RESEARCH' AND j.workflow='RESEARCH' "
                    "AND r.id=? AND r.account_id=j.account_id",
                    (
                        context.request_id, context.job_id, context.stage, context.attempt_no,
                        context.run_id, context.lease_owner, current_ts, context.run_id,
                    ),
                ).fetchone()
                if legacy is None:
                    raise StaleJobExecutionError(
                        context.job_id,
                        "non-durable provider boundary is not active for the current job/run/lease.",
                    )
                self.conn.commit()
                return self._provider_attempt_from_row(legacy)
            row = self.conn.execute(
                "SELECT "
                "p.job_id AS p_job_id,p.stage AS p_stage,p.attempt_no AS p_attempt_no,"
                "p.request_id AS p_request_id,p.status AS p_status,"
                "p.execution_intent_fingerprint AS p_fingerprint,"
                "p.reserved_amount_usd AS p_reserved_amount,p.reserved_at AS p_reserved_at,"
                "p.request_started_at AS p_request_started_at,"
                "p.settled_at AS p_settled_at,p.actual_cost_usd AS p_actual_cost,"
                "p.error_code AS p_error_code,"
                "j.id AS j_id,j.account_id AS j_account_id,j.kind AS j_kind,"
                "j.workflow AS j_workflow,j.topic_id AS j_topic_id,j.run_id AS j_run_id,"
                "j.status AS j_status,j.lease_owner AS j_lease_owner,"
                "j.lease_expires_at AS j_lease_expires_at,j.finished_at AS j_finished_at,"
                "j.payload_json AS j_payload_json,"
                "r.id AS r_id,r.account_id AS r_account_id,r.workflow AS r_workflow,"
                "r.status AS r_status,r.finished_at AS r_finished_at,r.error AS r_error,"
                "rr.id AS rr_id,rr.account_id AS rr_account_id,rr.topic_id AS rr_topic_id,"
                "rr.flow AS rr_flow,rr.status AS rr_status,"
                "rr.stage_a_completed_at AS rr_stage_a_completed_at,"
                "rr.stage_b_completed_at AS rr_stage_b_completed_at,"
                "rr.research_card_id AS rr_research_card_id,rr.total_cost_usd AS rr_total_cost,"
                "rr.error AS rr_error,rr.is_force_reresearch AS rr_is_force_reresearch "
                "FROM provider_attempts p "
                "LEFT JOIN jobs j ON j.id=p.job_id "
                "LEFT JOIN runs r ON r.id=j.run_id "
                "LEFT JOIN research_runs rr ON rr.id=r.id "
                "WHERE p.request_id=?",
                (context.request_id,),
            ).fetchone()

            def reject(code: str, detail: str, *, stale: bool = False) -> None:
                """Retain a started request for explicit reconciliation, then refuse."""
                if (
                    row is not None
                    and row["p_job_id"] == context.job_id
                    and row["p_status"] == ProviderAttemptStatus.REQUEST_STARTED.value
                ):
                    cursor = self.conn.execute(
                        "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',error_code=? "
                        "WHERE request_id=? AND job_id=? AND status='REQUEST_STARTED'",
                        (code, context.request_id, context.job_id),
                    )
                    if cursor.rowcount != 1:
                        raise StaleJobExecutionError(
                            context.job_id,
                            "durable provider attempt could not be retained for reconciliation.",
                        )
                self.conn.commit()
                if stale:
                    raise StaleJobExecutionError(context.job_id, detail)
                raise JobRunRelationError(code, context.job_id, detail)

            if row is None:
                reject(
                    "FINAL_LIFECYCLE_ATTEMPT_MISSING",
                    "provider attempt disappeared before the provider boundary.",
                )
            assert row is not None
            if (
                row["p_job_id"] != context.job_id
                or row["p_stage"] != context.stage
                or row["p_attempt_no"] != context.attempt_no
                or row["p_request_id"] != context.request_id
            ):
                reject(
                    "FINAL_LIFECYCLE_ATTEMPT_IDENTITY_MISMATCH",
                    "provider attempt identity no longer matches the durable context.",
                )
            if (
                row["p_status"] != ProviderAttemptStatus.REQUEST_STARTED.value
                or not _is_positive_money(
                    row["p_reserved_amount"], label="Persisted provider reservation",
                )
                or not isinstance(row["p_reserved_at"], str)
                or not row["p_reserved_at"].strip()
                or not isinstance(row["p_request_started_at"], str)
                or not row["p_request_started_at"].strip()
                or row["p_settled_at"] is not None
                or row["p_actual_cost"] is not None
                or row["p_error_code"] is not None
            ):
                reject(
                    "FINAL_LIFECYCLE_ATTEMPT_STATE_INVALID",
                    "provider attempt is not an un-settled request-started attempt.",
                )
            if row["j_id"] is None:
                reject(
                    "FINAL_LIFECYCLE_JOB_MISSING",
                    "provider attempt no longer has its research job.",
                )
            if (
                row["j_id"] != context.job_id
                or row["j_run_id"] != context.run_id
                or row["j_kind"] != JobKind.RESEARCH.value
                or row["j_workflow"] != WorkflowType.RESEARCH.value
                or row["j_status"] not in _EXECUTABLE_JOB_STATUSES
                or row["j_finished_at"] is not None
                or row["j_lease_owner"] != context.lease_owner
                or row["j_lease_expires_at"] is None
                or row["j_lease_expires_at"] < current_ts
            ):
                reject(
                    "STALE_JOB_EXECUTION",
                    "job/run/workflow/lease state is not executable at the provider boundary.",
                    stale=True,
                )
            if row["r_id"] is None:
                reject(
                    "FINAL_LIFECYCLE_RUN_MISSING",
                    "research job no longer has its attached run.",
                )
            if (
                row["r_id"] != context.run_id
                or row["r_account_id"] != row["j_account_id"]
                or row["r_workflow"] != WorkflowType.RESEARCH.value
                or row["r_status"] != RunStatus.RUNNING.value
                or row["r_finished_at"] is not None
                or row["r_error"] is not None
            ):
                reject(
                    "FINAL_LIFECYCLE_RUN_INVALID",
                    "run is not an unfinished error-free RUNNING research lifecycle.",
                )
            if row["rr_id"] is None:
                reject(
                    "FINAL_LIFECYCLE_RESEARCH_RUN_MISSING",
                    "research run extension is missing at the provider boundary.",
                )
            try:
                payload = json.loads(row["j_payload_json"])
                if not isinstance(payload, dict):
                    raise DurableExecutionIntentError(
                        "persisted durable payload must be a JSON object."
                    )
                canonical_payload = canonicalize_durable_research_payload(payload)
                intent_raw = canonical_payload["execution_intent"]
                assert isinstance(intent_raw, dict)
                intent = DurableResearchExecutionIntent.from_payload(intent_raw)
                current_fingerprint = durable_execution_intent_fingerprint(payload)
            except (TypeError, json.JSONDecodeError) as exc:
                intent_error = DurableExecutionIntentError(
                    "persisted durable payload is not valid JSON."
                )
                intent_error.__cause__ = exc
            except DurableExecutionIntentError as exc:
                intent_error = exc
            else:
                intent_error = None

            if intent_error is not None:
                code = (
                    intent_error.code
                )
                reject(code, "persisted execution_intent is malformed.")
            assert intent_error is None
            if (
                row["j_account_id"] != intent.account_id
                or row["j_topic_id"] != intent.topic_id
                or row["rr_account_id"] != intent.account_id
                or row["rr_topic_id"] != intent.topic_id
                or row["rr_flow"] != ResearchFlow.SINGLE.value
                or row["rr_status"] != ResearchRunStatus.PENDING.value
                or row["rr_stage_a_completed_at"] is not None
                or row["rr_stage_b_completed_at"] is not None
                or row["rr_research_card_id"] is not None
                or not _money_equal(
                    row["rr_total_cost"],
                    Decimal("0"),
                    label="Fresh durable research run cost",
                )
                or row["rr_error"] is not None
                or bool(row["rr_is_force_reresearch"])
            ):
                reject(
                    "FINAL_LIFECYCLE_RESEARCH_RUN_INVALID",
                    "research_run is not the fresh single:PENDING lifecycle for this intent.",
                )
            if intent.stage != context.stage:
                reject(
                    "FINAL_LIFECYCLE_STAGE_MISMATCH",
                    "persisted provider stage does not match the provider attempt context.",
                )
            if row["p_fingerprint"] != current_fingerprint:
                reject(
                    "INVALID_EXECUTION_INTENT_FINGERPRINT",
                    "persisted execution_intent fingerprint no longer matches the attempt.",
                )
            self.conn.commit()
            attempt_row = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=?", (context.request_id,),
            ).fetchone()
            assert attempt_row is not None
            return self._provider_attempt_from_row(attempt_row)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _set_run_cost_from_content_usage(self, run_id: str) -> None:
        rows = self.conn.execute(
            "SELECT estimated_cost_usd FROM model_usage "
            "WHERE run_id=? AND task=?",
            (run_id, CONTENT_PROVIDER_STAGE),
        ).fetchall()
        total = _sum_money_rows(
            rows, "estimated_cost_usd", label="Canonical content usage total",
        )
        cursor = self.conn.execute(
            "UPDATE runs SET cost_usd=? WHERE id=?", (float(total), run_id),
        )
        if cursor.rowcount != 1:
            raise StaleJobExecutionError(
                run_id, "Content run cost cache could not be refreshed.",
            )

    def add_job_model_usage(
        self, execution: JobExecutionContext, usage: ModelUsage,
    ) -> ModelUsage:
        """Worker-only usage write; insert and run-cost refresh share the fence lock."""
        if usage.run_id != execution.run_id:
            raise StaleJobExecutionError(
                execution.job_id, "usage run_id does not match the fenced execution.",
            )
        if usage.task not in _RESEARCH_USAGE_TASKS + (
            TOPIC_GENERATION_USAGE_TASK, CONTENT_PROVIDER_STAGE,
        ):
            raise StaleJobExecutionError(
                execution.job_id, "usage task is not a research task.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(execution.now())
            current_ts = _persisted_ts(current)
            fence = self._require_job_execution_fence(execution, current_ts)
            # The usage task and the fenced workflow must agree: a research job
            # can never book topic-generation usage and vice versa, so neither
            # cost cache can ever be fed from the other workflow's ledger rows.
            is_topic_generation = fence["kind"] == JobKind.TOPIC_GENERATION.value
            is_content = fence["kind"] == JobKind.CONTENT.value
            if (
                is_topic_generation != (usage.task == TOPIC_GENERATION_USAGE_TASK)
                or is_content != (usage.task == CONTENT_PROVIDER_STAGE)
                or (
                    not is_topic_generation and not is_content
                    and usage.task not in _RESEARCH_USAGE_TASKS
                )
            ):
                raise StaleJobExecutionError(
                    execution.job_id, "usage task does not match the fenced workflow.",
                )
            fake_content_attempt = False
            if is_content and usage.request_id:
                fake_content_attempt = self.conn.execute(
                    "SELECT 1 FROM content_writer_attempts "
                    "WHERE request_id=? AND job_id=? AND run_id=? "
                    "AND call_mode='FAKE'",
                    (usage.request_id, execution.job_id, execution.run_id),
                ).fetchone() is not None
            expected_dry_run = (
                fence["run_status"] == RunStatus.DRY_RUN.value
                or fake_content_attempt
            )
            if bool(usage.dry_run) != expected_dry_run:
                raise StaleJobExecutionError(
                    execution.job_id, "usage dry_run marker conflicts with the fenced run.",
                )
            if not expected_dry_run and not usage.request_id:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "real worker usage requires a durable provider request_id.",
                )
            actual_amount = _money(
                usage.estimated_cost_usd, positive=False,
                label="Provider actual usage cost",
            )
            if fake_content_attempt and actual_amount != Decimal("0.000000"):
                raise StaleJobExecutionError(
                    execution.job_id, "fake content usage cost must be exactly zero.",
                )
            if usage.request_id:
                attempt = self.conn.execute(
                    "SELECT p.* FROM provider_attempts p JOIN jobs j ON j.id=p.job_id "
                    "WHERE p.request_id=? AND p.job_id=? AND j.run_id=?",
                    (usage.request_id, execution.job_id, execution.run_id),
                ).fetchone()
                if attempt is None or attempt["job_id"] != execution.job_id or \
                        attempt["status"] != ProviderAttemptStatus.REQUEST_STARTED.value:
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "usage request_id is not an active provider attempt for this execution.",
                    )
                reserved_amount = _money(
                    attempt["reserved_amount_usd"], positive=True,
                    label="Persisted provider reservation",
                )
                over_reservation = actual_amount > reserved_amount
            else:
                reserved_amount = None
                over_reservation = False
            cur = self.conn.execute(
                "INSERT INTO model_usage (run_id, provider, model, task, input_tokens,"
                " output_tokens, cache_read_tokens, cache_write_tokens, web_search_requests,"
                " estimated_cost_usd, dry_run, request_id, created_at) "
                "SELECT ?,?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=? AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    usage.run_id, usage.provider, usage.model, usage.task,
                    usage.input_tokens, usage.output_tokens, usage.cache_read_tokens,
                    usage.cache_write_tokens, usage.web_search_requests,
                    float(actual_amount),
                    int(usage.dry_run), usage.request_id, current_ts,
                    execution.job_id, execution.run_id, execution.lease_owner, current_ts,
                ),
            )
            if cur.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            if usage.request_id:
                assert reserved_amount is not None and actual_amount is not None
                if over_reservation:
                    settled = self.conn.execute(
                        "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',"
                        "actual_cost_usd=NULL,settled_at=NULL,error_code=? WHERE request_id=? "
                        "AND job_id=? AND status='REQUEST_STARTED'",
                        (
                            ProviderAttemptOverReservationError.code, usage.request_id,
                            execution.job_id,
                        ),
                    )
                else:
                    settled = self.conn.execute(
                        "UPDATE provider_attempts SET status='SETTLED',actual_cost_usd=?,"
                        "settled_at=?,error_code=NULL WHERE request_id=? "
                        "AND job_id=? AND status='REQUEST_STARTED'",
                        (
                            float(actual_amount), current_ts, usage.request_id,
                            execution.job_id,
                        ),
                    )
                if settled.rowcount != 1:
                    raise StaleJobExecutionError(
                        execution.job_id, "provider attempt could not be settled with usage.",
                    )
            if is_topic_generation:
                self._set_run_cost_from_topic_generation_usage(execution.run_id)
            elif is_content:
                self._set_run_cost_from_content_usage(execution.run_id)
            else:
                self._set_run_cost_from_research_usage(execution.run_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise
        usage.id = int(cur.lastrowid)
        usage.created_at = current
        usage.estimated_cost_usd = float(actual_amount)
        if over_reservation:
            assert reserved_amount is not None and actual_amount is not None
            raise ProviderAttemptOverReservationError(
                reserved_amount_usd=float(reserved_amount),
                actual_cost_usd=float(actual_amount),
            )
        return usage

    def begin_provider_attempt(
        self, execution: JobExecutionContext, *, stage: str, attempt_no: int,
        max_cost_usd: float, daily_limit_usd: float, monthly_limit_usd: float,
    ) -> ProviderAttempt:
        """Creates or returns the one durable pre-network provider attempt.

        SQLite's write lock covers the fence, real spend, every still-active
        reservation and this insertion.  Therefore two workers/jobs cannot
        both pass a shared daily/monthly budget check for the same funds.
        """
        self._validate_provider_attempt_identity(stage, attempt_no)
        max_cost = _money(max_cost_usd, positive=True, label="Provider reservation")
        daily_limit = _money(daily_limit_usd, positive=False, label="Daily provider limit")
        monthly_limit = _money(monthly_limit_usd, positive=False, label="Monthly provider limit")
        request_id = self._provider_request_id(execution.job_id, stage, attempt_no)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(execution.now())
            current_ts = _persisted_ts(current)
            self._require_job_execution_fence(execution, current_ts)
            payload_row = self.conn.execute(
                "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
            ).fetchone()
            if payload_row is None:
                raise StaleJobExecutionError(execution.job_id)
            try:
                payload = json.loads(payload_row["payload_json"])
                if not isinstance(payload, dict):
                    raise DurableExecutionIntentError(
                        "persisted durable payload must be a JSON object."
                    )
                content_attempt = payload.get("execution") == CONTENT_EXECUTION
                content_intent = None
                if content_attempt:
                    canonicalize_content_job_payload(payload)
                    content_intent = self.conn.execute(
                        "SELECT * FROM content_call_intents "
                        "WHERE job_id=? AND run_id=?",
                        (execution.job_id, execution.run_id),
                    ).fetchone()
                    if (
                        content_intent is None
                        or stage != content_intent["stage"]
                        or stage != CONTENT_PROVIDER_STAGE
                        or attempt_no != int(content_intent["attempt_no"])
                        or content_intent["expires_at"] <= current_ts
                        or not _money_equal(
                            content_intent["max_cost_usd"],
                            max_cost,
                            label="Content provider reservation",
                        )
                    ):
                        raise ContentFoundationError(
                            "CONTENT_PROVIDER_INTENT_MISMATCH",
                            "Provider reservation does not match the immutable content call intent.",
                        )
                    intent_json = content_intent["intent_json"]
                    intent_fingerprint = content_intent["intent_fingerprint"]
                    topic_generation = False
                    topic_intent = None
                    intent = None
                else:
                    topic_generation = (
                    payload.get("execution") == TOPIC_GENERATION_EXECUTION
                    )
                if not content_attempt and topic_generation:
                    topic_intent, intent_json, intent_fingerprint = (
                        frozen_topic_generation_contract(payload)
                    )
                    intent = None
                elif not content_attempt:
                    canonical_payload = canonicalize_durable_research_payload(payload)
                    intent_raw = canonical_payload["execution_intent"]
                    assert isinstance(intent_raw, dict)
                    intent = DurableResearchExecutionIntent.from_payload(intent_raw)
                    topic_intent = None
                    intent_json, intent_fingerprint = frozen_execution_intent_json(payload)
            except (TypeError, json.JSONDecodeError) as exc:
                raise JobRunRelationError(
                    "MALFORMED_DURABLE_V2_PAYLOAD",
                    execution.job_id,
                    "provider attempt requires a valid persisted durable payload.",
                ) from exc
            except DurableExecutionIntentError as exc:
                raise JobRunRelationError(exc.code, execution.job_id, str(exc)) from exc
            stage_attempts = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE job_id=? AND stage=? ORDER BY attempt_no",
                (execution.job_id, stage),
            ).fetchall()
            existing = next(
                (row for row in stage_attempts if int(row["attempt_no"]) == attempt_no),
                None,
            )
            if existing is not None:
                attempt = self._provider_attempt_from_row(existing)
                if attempt.status is ProviderAttemptStatus.RESERVED:
                    self.conn.commit()
                    return attempt
                if attempt.status is ProviderAttemptStatus.NEEDS_RECONCILIATION:
                    raise ProviderAttemptReconciliationRequired(
                        "Provider attempt is NEEDS_RECONCILIATION; WAVE 1 resolver is required."
                    )
                raise StaleJobExecutionError(
                    execution.job_id,
                    "provider attempt already crossed the request boundary and requires reconciliation.",
                )
            if attempt_no > 1 and stage_attempts:
                raise ProviderAttemptReconciliationRequired(
                    "A prior provider attempt exists; WAVE 0B.2 does not authorize a new attempt number."
                )
            day_prefix = current.strftime("%Y-%m-%d")
            month_prefix = current.strftime("%Y-%m")
            day_real_rows = self.conn.execute(
                "SELECT estimated_cost_usd FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{day_prefix}%",),
            ).fetchall()
            month_real_rows = self.conn.execute(
                "SELECT estimated_cost_usd FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{month_prefix}%",),
            ).fetchall()
            active_attempt_rows = self.conn.execute(
                "SELECT reserved_amount_usd FROM provider_attempts "
                "WHERE status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')",
            ).fetchall()
            active_job_rows = self.conn.execute(
                "SELECT reserved_cost_usd FROM jobs "
                "WHERE status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION') "
                "AND budget_reserved_at IS NOT NULL",
            ).fetchall()
            day_real_amount = _sum_money_rows(
                day_real_rows, "estimated_cost_usd", label="Persisted daily provider cost",
            )
            month_real_amount = _sum_money_rows(
                month_real_rows, "estimated_cost_usd", label="Persisted monthly provider cost",
            )
            attempt_reserved_amount = _sum_money_rows(
                active_attempt_rows,
                "reserved_amount_usd",
                label="Persisted provider reservation",
            )
            job_reserved_amount = _sum_money_rows(
                active_job_rows, "reserved_cost_usd", label="Persisted job reservation",
            )
            total_reserved = _money_sum(
                (attempt_reserved_amount, job_reserved_amount, max_cost),
                label="Total provider reservation",
            )
            if month_real_amount + total_reserved > monthly_limit:
                raise BudgetReservationError("Provider reservation would exceed the global monthly limit.")
            if day_real_amount + total_reserved > daily_limit:
                raise BudgetReservationError("Provider reservation would exceed the global daily limit.")
            if topic_generation:
                # Konsumpcja jednorazowej zgody L1 i rezerwacja attemptu są
                # JEDNĄ transakcją. Każda odmowa poniżej wycofuje całość: zero
                # konsumpcji, zero attemptu, zero requestu, zero kosztu.
                assert topic_intent is not None
                self._consume_topic_generation_approval(
                    execution,
                    topic_intent,
                    canonical_intent_json=intent_json,
                    intent_fingerprint=intent_fingerprint,
                    current_ts=current_ts,
                )
            elif intent is not None and intent.evidence_input is not None:
                # E3: konsumpcja jednorazowej zgody L1 i rezerwacja attemptu są
                # JEDNĄ transakcją. Każda odmowa poniżej wycofuje całość: zero
                # konsumpcji, zero attemptu, zero requestu, zero kosztu.
                self._consume_evidence_research_approval(
                    execution,
                    intent,
                    canonical_intent_json=intent_json,
                    intent_fingerprint=intent_fingerprint,
                    current_ts=current_ts,
                )
            if content_attempt:
                assert content_intent is not None
                extension = self.conn.execute(
                    "INSERT INTO content_provider_attempts (request_id,intent_id,"
                    "job_id,run_id,content_id,account_id,stage,attempt_no,"
                    "provider,model,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        request_id, content_intent["intent_id"],
                        execution.job_id, execution.run_id,
                        int(content_intent["content_id"]),
                        content_intent["account_id"], stage, attempt_no,
                        content_intent["provider"], content_intent["model"],
                        current_ts,
                    ),
                )
                if extension.rowcount != 1:
                    raise ContentFoundationError(
                        "CONTENT_PROVIDER_EXTENSION_FAILED",
                        "Content attempt extension did not affect exactly one row.",
                    )
            self.conn.execute(
                "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
                "execution_intent_fingerprint,reserved_amount_usd,reserved_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    execution.job_id, stage, attempt_no, request_id,
                    ProviderAttemptStatus.RESERVED.value, intent_fingerprint,
                    float(max_cost), current_ts,
                ),
            )
            row = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=?", (request_id,),
            ).fetchone()
            assert row is not None
            self.conn.commit()
            return self._provider_attempt_from_row(row)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def mark_provider_attempt_request_started(
        self, execution: JobExecutionContext, request_id: str,
    ) -> ProviderAttempt:
        """Durably records the last point before the SDK can submit a request."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            cursor = self.conn.execute(
                "UPDATE provider_attempts SET status='REQUEST_STARTED',request_started_at=? "
                "WHERE request_id=? AND job_id=? AND status='RESERVED'",
                (current_ts, request_id, execution.job_id),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(
                    execution.job_id, "provider attempt is not reserved for request start.",
                )
            # This protects recovery even if the process dies immediately after
            # commit but before/inside the SDK call.
            effect = self.conn.execute(
                "UPDATE jobs SET external_effect_started_at=COALESCE(external_effect_started_at,?),"
                "updated_at=? WHERE id=? AND run_id=? AND lease_owner=? AND "
                "lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                (
                    current_ts, current_ts, execution.job_id, execution.run_id,
                    execution.lease_owner, current_ts,
                ),
            )
            if effect.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            row = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=?", (request_id,),
            ).fetchone()
            assert row is not None
            self.conn.commit()
            return self._provider_attempt_from_row(row)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def release_provider_attempt_before_request(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        """Releases only a reservation which demonstrably did not reach the SDK."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            cursor = self.conn.execute(
                "UPDATE provider_attempts SET status='RELEASED',released_at=?,error_code=? "
                "WHERE request_id=? AND job_id=? AND status='RESERVED'",
                (current_ts, error_code, request_id, execution.job_id),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def mark_provider_attempt_needs_reconciliation(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            cursor = self.conn.execute(
                "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',error_code=? "
                "WHERE request_id=? AND job_id=? AND status='REQUEST_STARTED'",
                (error_code, request_id, execution.job_id),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def settle_provider_attempt_without_usage(
        self, execution: JobExecutionContext, request_id: str, *, error_code: str,
    ) -> None:
        """Settles a provider-confirmed no-usage error once, never retries it."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            cursor = self.conn.execute(
                "UPDATE provider_attempts SET status='SETTLED',actual_cost_usd=0.0,"
                "settled_at=?,error_code=? WHERE request_id=? AND job_id=? "
                "AND status='REQUEST_STARTED'",
                (current_ts, error_code, request_id, execution.job_id),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def list_provider_attempts_needing_reconciliation(
        self, *, account_id: str | None = None,
    ) -> list[ProviderAttempt]:
        """Read-only L1 queue.  No worker, SDK or provider boundary is involved."""
        sql = (
            "SELECT p.* FROM provider_attempts p JOIN jobs j ON j.id=p.job_id "
            "WHERE p.status='NEEDS_RECONCILIATION'"
        )
        params: list[object] = []
        if account_id is not None:
            sql += " AND j.account_id=?"
            params.append(account_id)
        sql += " ORDER BY p.reserved_at,p.request_id"
        return [self._provider_attempt_from_row(row) for row in self.conn.execute(sql, params)]

    def _reconciliation_fault_point(self, point: ReconciliationFaultPoint) -> None:
        """Dedicated test seam; production implementation is deliberately a no-op."""
        del point

    def _recovery_fault_point(self, point: str) -> None:
        """Dedicated recovery/escalation test seam; production no-op."""
        del point

    def _escalate_crash_window_attempts(self, current_ts: str, result: JobRecoveryResult) -> None:
        """W1A-AUD-04: escalate dead-fence RESERVED/REQUEST_STARTED attempts.

        A RESERVED or REQUEST_STARTED attempt whose job already reached
        NEEDS_VERIFICATION has provably lost its execution fence (every path
        into NEEDS_VERIFICATION nulls the lease; the expired-lease belt keeps
        this true even for a hypothetical future path).  Each such attempt
        atomically moves to NEEDS_RECONCILIATION with one enumerated reason and
        an append-only AUTO_ESCALATION event, so the operator queue lists it,
        preview/confirm can resolve it, and the reservation stops being
        invisible.  Idempotent: an escalated attempt no longer matches the
        selection.  Never touches an attempt whose job still holds a live
        lease, never touches a terminal attempt, performs no provider call, no
        retry and no attempt #2.  Runs inside the caller's BEGIN IMMEDIATE
        transaction, so two concurrent maintenance runners serialize and
        exactly one escalates.
        """
        rows = self.conn.execute(
            "SELECT p.request_id, p.status FROM provider_attempts p "
            "JOIN jobs j ON j.id=p.job_id "
            "WHERE p.status IN ('RESERVED','REQUEST_STARTED') "
            "AND j.status='NEEDS_VERIFICATION' "
            "AND (j.lease_owner IS NULL OR j.lease_expires_at < ?) "
            "ORDER BY p.request_id",
            (current_ts,),
        ).fetchall()
        for attempt_row in rows:
            started = attempt_row["status"] == ProviderAttemptStatus.REQUEST_STARTED.value
            reason = (
                _LEASE_EXPIRED_AFTER_REQUEST_STARTED if started
                else _LEASE_EXPIRED_BEFORE_REQUEST_STARTED
            )
            cursor = self.conn.execute(
                "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',error_code=? "
                "WHERE request_id=? AND status=?",
                (reason, attempt_row["request_id"], attempt_row["status"]),
            )
            if cursor.rowcount != 1:
                raise ProviderAttemptReconciliationError(
                    "Crash-window escalation lost its compare-and-swap."
                )
            self._recovery_fault_point("AFTER_ESCALATION_UPDATE")
            note = (
                "Automatic escalation: job lease expired after the provider request "
                "boundary was crossed; the financial outcome is unknown."
                if started else
                "Automatic escalation: job lease expired before the provider request "
                "boundary; no provider call was made."
            )
            self._append_reconciliation_event(
                request_id=attempt_row["request_id"],
                event_type=ReconciliationEventType.AUTO_ESCALATION,
                financial_resolution=(
                    FinancialResolution.CHARGE_UNKNOWN
                    if started else FinancialResolution.NOT_CHARGED
                ),
                execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                operator=_ESCALATION_OPERATOR, note=note,
                previous_status=attempt_row["status"],
                resulting_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                idempotency_key=self._reconciliation_idempotency_key(
                    attempt_row["request_id"], (
                        FinancialResolution.CHARGE_UNKNOWN
                        if started else FinancialResolution.NOT_CHARGED
                    ),
                    ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                    _ESCALATION_OPERATOR, note, "ESCALATION",
                ),
                created_at=current_ts,
            )
            self._recovery_fault_point("AFTER_ESCALATION_EVENT")
            result.escalated_reconciliation_count += 1

    def _recover_settled_execution_attempts(
        self, current_ts: str, result: JobRecoveryResult,
    ) -> None:
        """Close financially-known SETTLED crash windows without provider work.

        Expired leases have already been fenced into NEEDS_VERIFICATION by the
        caller.  Each attempt is isolated by a savepoint: ordinary valid states
        become one audited terminal result, while tampered or incomplete lineage
        remains explicitly reviewable and cannot roll back unrelated lease
        recovery.  No attempt, usage, cost or reservation is created or changed.
        """
        rows = self.conn.execute(
            "SELECT p.request_id,j.kind AS job_kind FROM provider_attempts p "
            "JOIN jobs j ON j.id=p.job_id "
            "WHERE p.status='SETTLED' AND j.status='NEEDS_VERIFICATION' "
            "AND j.kind IN ('RESEARCH','TOPIC_GENERATION') "
            "AND NOT EXISTS (SELECT 1 FROM reconciliation_events e "
            "WHERE e.request_id=p.request_id AND e.event_type='EXECUTION_RECOVERY') "
            "ORDER BY p.request_id"
        ).fetchall()
        for candidate in rows:
            self.conn.execute("SAVEPOINT settled_execution_recovery")
            try:
                row = self._reconciliation_state_row(candidate["request_id"])
                if row is None:
                    raise ProviderAttemptReconciliationError(
                        "SETTLED execution disappeared during recovery."
                    )
                is_topic_generation = (
                    row["job_kind"] == JobKind.TOPIC_GENERATION.value
                )
                resolution = (
                    ExecutionResolution.EXECUTION_FAILED
                    if is_topic_generation
                    else (
                        ExecutionResolution.RESULT_ALREADY_FINALIZED
                        if row["research_card_id"] is not None
                        else ExecutionResolution.EXECUTION_FAILED
                    )
                )
                actual = _money(
                    row["actual_cost_usd"], positive=True,
                    label="SETTLED execution actual cost",
                )
                self._resolve_settled_execution_in_transaction(
                    row=row, account_id=row["job_account_id"],
                    execution_resolution=resolution, actual_amount=actual,
                    operator=_SETTLED_EXECUTION_RECOVERY_OPERATOR,
                    note_text=(
                        _TOPIC_SETTLED_EXECUTION_RECOVERY_NOTE
                        if is_topic_generation
                        else _SETTLED_EXECUTION_RECOVERY_NOTE
                    ),
                    current_ts=current_ts,
                )
                self._recovery_fault_point("AFTER_SETTLED_EXECUTION_RECOVERY")
            except (ProviderAttemptReconciliationError, BudgetReservationError):
                self.conn.execute("ROLLBACK TO settled_execution_recovery")
                self.conn.execute("RELEASE settled_execution_recovery")
                # Topic-generation invariants are a closed acceptance contract:
                # an invalid candidate is observed fail-closed, without even a
                # diagnostic row mutation.  The historical RESEARCH behavior is
                # deliberately retained byte-for-byte.
                if candidate["job_kind"] != JobKind.TOPIC_GENERATION.value:
                    self.conn.execute(
                        "UPDATE jobs SET last_error=?,updated_at=? WHERE id=("
                        "SELECT job_id FROM provider_attempts WHERE request_id=?"
                        ") AND status='NEEDS_VERIFICATION'",
                        (
                            _SETTLED_EXECUTION_RECOVERY_BLOCKED, current_ts,
                            candidate["request_id"],
                        ),
                    )
                result.settled_execution_blocked_count += 1
            else:
                self.conn.execute("RELEASE settled_execution_recovery")
                result.settled_execution_recovery_count += 1

    @staticmethod
    def _reconciliation_text(value: object, *, label: str, limit: int) -> str:
        if not isinstance(value, str):
            raise ProviderAttemptReconciliationError(f"{label} must be a non-empty controlled string.")
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > limit:
            raise ProviderAttemptReconciliationError(f"{label} must be 1..{limit} characters.")
        return normalized

    def _reconciliation_state_row(self, request_id: str) -> sqlite3.Row | None:
        """Single durable snapshot of the attempt and its whole lineage."""
        return self.conn.execute(
            "SELECT p.*,j.account_id AS job_account_id,j.status AS job_status,j.kind AS job_kind,"
            "j.workflow AS job_workflow,j.run_id,j.topic_id,j.payload_json,"
            "j.lease_owner,j.lease_expires_at,j.reserved_cost_usd,j.budget_reserved_at,"
            "j.external_effect_started_at,"
            "r.status AS run_status,r.account_id AS run_account_id,r.workflow AS run_workflow,"
            "r.cost_usd AS run_cost_usd,"
            "rr.status AS research_status,rr.research_card_id,rr.topic_id AS research_topic_id,"
            "rr.account_id AS research_account_id,rr.flow AS research_flow,"
            "rr.total_cost_usd AS research_cost_usd,t.status AS topic_status,"
            "ta.account_id AS topic_approval_account_id,"
            "ta.intent_fingerprint AS topic_approval_fingerprint,"
            "ta.execution_intent_json AS topic_approval_intent_json,"
            "ta.consumed_at AS topic_approval_consumed_at "
            "FROM provider_attempts p JOIN jobs j ON j.id=p.job_id "
            "LEFT JOIN runs r ON r.id=j.run_id LEFT JOIN research_runs rr ON rr.id=j.run_id "
            "LEFT JOIN topics t ON t.id=j.topic_id "
            "LEFT JOIN topic_generation_approvals ta ON ta.job_id=j.id "
            "WHERE p.request_id=?",
            (request_id,),
        ).fetchone()

    @staticmethod
    def _reconciliation_event_from_row(row: sqlite3.Row) -> ReconciliationEvent:
        return ReconciliationEvent(
            id=int(row["id"]), request_id=row["request_id"], sequence_number=int(row["sequence_number"]),
            event_type=ReconciliationEventType(row["event_type"]),
            financial_resolution=FinancialResolution(row["financial_resolution"]),
            execution_resolution=ExecutionResolution(row["execution_resolution"]),
            operator=row["operator"], note=row["note"],
            previous_attempt_status=ProviderAttemptStatus(row["previous_attempt_status"]),
            resulting_attempt_status=ProviderAttemptStatus(row["resulting_attempt_status"]),
            created_at=row["created_at"], idempotency_key=row["idempotency_key"],
        )

    def _reconciliation_version_token(self, row: sqlite3.Row) -> str:
        """Fingerprint the exact durable state a preview observed.

        Any change to the attempt status, lifecycle statuses, canonical usage
        count/cost, or event history invalidates the token, so a stale preview
        can never confirm a mutation.
        """
        request_id = row["request_id"]
        run_id = row["run_id"]
        usage_count = self.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE request_id=? AND dry_run=0 AND is_legacy_usage=0",
            (request_id,),
        ).fetchone()[0]
        canonical_cost = (
            self._reconciliation_usage_total(row)
            if run_id is not None else Decimal("0.000000")
        )
        max_seq = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_number),0) FROM reconciliation_events WHERE request_id=?",
            (request_id,),
        ).fetchone()[0]
        material = json.dumps(
            [
                "reconciliation-token-v3", str(request_id), str(row["status"]),
                str(row["job_status"]), str(row["run_status"]), str(row["research_status"]),
                None if row["research_card_id"] is None else int(row["research_card_id"]),
                int(usage_count), format(canonical_cost, "f"), int(max_seq),
                # Full lineage: any change to account/workflow/kind/topic/flow/run_id or the
                # bound durable-intent fingerprint between preview and confirm is stale.
                str(row["job_account_id"]), str(row["job_kind"]), str(row["job_workflow"]),
                str(row["run_id"]), None if row["topic_id"] is None else int(row["topic_id"]),
                str(row["run_account_id"]), str(row["run_workflow"]),
                str(row["research_account_id"]),
                None if row["research_topic_id"] is None else int(row["research_topic_id"]),
                str(row["research_flow"]), str(row["execution_intent_fingerprint"]),
                str(row["lease_owner"]), str(row["lease_expires_at"]),
                str(row["reserved_cost_usd"]), str(row["budget_reserved_at"]),
                str(row["external_effect_started_at"]),
                str(row["actual_cost_usd"]), str(row["run_cost_usd"]),
                str(row["research_cost_usd"]), str(row["topic_status"]),
                str(row["topic_approval_account_id"]),
                str(row["topic_approval_fingerprint"]),
                str(row["topic_approval_intent_json"]),
                str(row["topic_approval_consumed_at"]),
            ],
            ensure_ascii=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _reconciliation_idempotency_key(
        request_id: str, financial: FinancialResolution, execution: ExecutionResolution,
        operator: str, note: str, kind: str,
    ) -> str:
        material = json.dumps(
            ["reconciliation-idem-v1", kind, request_id, financial.value, execution.value, operator, note],
            ensure_ascii=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _reconciliation_require_consistent_lineage(
        self, row: sqlite3.Row, account_id: str,
    ) -> DurableResearchExecutionIntent | DurableTopicGenerationIntent:
        """Fail-closed unless the whole durable lineage is present and consistent.

        Verifies attempt -> job -> run -> research_run -> account -> workflow ->
        topic -> durable execution intent as one relation.  The worker/reaper only
        ever build a run whose account and workflow equal the job's, so any
        divergence — foreign ``runs.account_id``, non-research ``runs.workflow``,
        cross-account/topic research_run, wrong flow, wrong job kind/workflow, or a
        tampered durable intent — means the attempt is unsafe to reconcile.  Returns
        the fingerprint-verified durable intent for reuse.  Performs no mutation.
        """
        if row["job_kind"] == JobKind.TOPIC_GENERATION.value:
            return self._reconciliation_require_topic_generation_lineage(
                row, account_id,
            )
        if row["run_id"] is None or row["run_status"] is None or row["research_status"] is None:
            raise ProviderAttemptReconciliationError(
                "Attempt lacks the required durable job->run->research_run relation."
            )
        intent = self._reconciliation_intent(row)
        job_account = row["job_account_id"]
        job_topic = None if row["topic_id"] is None else int(row["topic_id"])
        problems: list[str] = []
        # Operator owns the job; job is a single real-research job.
        if job_account != account_id:
            problems.append("job.account_id!=operator")
        if row["job_kind"] != JobKind.RESEARCH.value:
            problems.append("job.kind")
        if row["job_workflow"] != WorkflowType.RESEARCH.value:
            problems.append("job.workflow")
        # The run must belong to the same account and be a research run (the fail-open).
        if row["run_account_id"] != job_account:
            problems.append("run.account_id!=job.account_id")
        if row["run_workflow"] != WorkflowType.RESEARCH.value:
            problems.append("run.workflow")
        # research_run shares the run id (JOIN) and must share account/topic and be single.
        if row["research_account_id"] != job_account:
            problems.append("research_run.account_id!=job.account_id")
        if job_topic is None or int(row["research_topic_id"]) != job_topic:
            problems.append("research_run.topic_id!=job.topic_id")
        if row["research_flow"] != ResearchFlow.SINGLE.value:
            problems.append("research_run.flow")
        # Durable intent identity (already fingerprint-verified) must match the lineage.
        if intent.account_id != job_account:
            problems.append("intent.account_id")
        if job_topic is None or int(intent.topic_id) != job_topic:
            problems.append("intent.topic_id")
        if problems:
            raise ProviderAttemptReconciliationError(
                "Attempt lineage is inconsistent: " + ",".join(problems)
            )
        return intent

    def _reconciliation_require_topic_generation_lineage(
        self, row: sqlite3.Row, account_id: str,
    ) -> DurableTopicGenerationIntent:
        """Validate the distinct job -> run -> attempt topic-generation lineage."""
        if row["run_id"] is None or row["run_status"] is None:
            raise ProviderAttemptReconciliationError(
                "Topic-generation attempt lacks the required durable job->run relation."
            )
        intent, expected_json, expected_fingerprint = (
            self._reconciliation_topic_contract(row)
        )
        job_account = row["job_account_id"]
        problems: list[str] = []
        if job_account != account_id:
            problems.append("job.account_id!=operator")
        if row["job_workflow"] != WorkflowType.TOPIC_GENERATION.value:
            problems.append("job.workflow")
        if row["topic_id"] is not None:
            problems.append("job.topic_id")
        if row["run_account_id"] != job_account:
            problems.append("run.account_id!=job.account_id")
        if row["run_workflow"] != WorkflowType.TOPIC_GENERATION.value:
            problems.append("run.workflow")
        if row["research_status"] is not None:
            problems.append("unexpected research_run")
        if row["stage"] != TOPIC_GENERATION_PROVIDER_STAGE:
            problems.append("attempt.stage")
        if int(row["attempt_no"]) != 1:
            problems.append("attempt.attempt_no")
        if row["request_id"] != (
            f"{row['job_id']}:{TOPIC_GENERATION_PROVIDER_STAGE}:1"
        ):
            problems.append("attempt.request_id")
        attempt_count = self.conn.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?",
            (row["job_id"],),
        ).fetchone()[0]
        if int(attempt_count) != 1:
            problems.append("attempt.count")
        if intent.account_id != job_account:
            problems.append("intent.account_id")
        if row["topic_approval_account_id"] != job_account:
            problems.append("approval.account_id")
        if row["topic_approval_consumed_at"] is None:
            problems.append("approval.consumed_at")
        if row["topic_approval_fingerprint"] != row["execution_intent_fingerprint"]:
            problems.append("approval.fingerprint")
        if expected_fingerprint != row["execution_intent_fingerprint"]:
            problems.append("intent.fingerprint")
        if row["topic_approval_intent_json"] != expected_json:
            problems.append("approval.execution_intent_json")
        self._reconciliation_validate_topic_generated_lineage(row)
        if problems:
            raise ProviderAttemptReconciliationError(
                "Attempt lineage is inconsistent: " + ",".join(problems)
            )
        return intent

    def _reconciliation_topic_intent(
        self, row: sqlite3.Row,
    ) -> DurableTopicGenerationIntent:
        return self._reconciliation_topic_contract(row)[0]

    def _reconciliation_topic_contract(
        self, row: sqlite3.Row,
    ) -> tuple[DurableTopicGenerationIntent, str, str]:
        try:
            payload = json.loads(row["payload_json"])
            intent, intent_json, fingerprint = frozen_topic_generation_contract(payload)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, DurableExecutionIntentError) as exc:
            raise ProviderAttemptReconciliationError(
                "Durable topic-generation identity cannot be reconstructed."
            ) from exc
        if fingerprint != row["execution_intent_fingerprint"]:
            raise ProviderAttemptReconciliationError(
                "Stored durable execution intent fingerprint does not match the attempt."
            )
        return intent, intent_json, fingerprint

    def _reconciliation_validate_topic_generated_lineage(
        self, row: sqlite3.Row,
    ) -> int:
        generated = self.conn.execute(
            "SELECT g.*,t.account_id AS topic_account_id FROM generated_topics g "
            "LEFT JOIN topics t ON t.id=g.topic_id "
            "WHERE g.job_id=? OR g.run_id=? OR g.request_id=? ORDER BY g.candidate_index",
            (row["job_id"], row["run_id"], row["request_id"]),
        ).fetchall()
        for item in generated:
            if (
                item["job_id"] != row["job_id"]
                or item["run_id"] != row["run_id"]
                or item["request_id"] != row["request_id"]
                or item["account_id"] != row["job_account_id"]
                or item["topic_account_id"] != row["job_account_id"]
            ):
                raise ProviderAttemptReconciliationError(
                    "Generated topic lineage is inconsistent with the reconciled attempt."
                )
        return len(generated)

    def _reconciliation_usage_total(self, row: sqlite3.Row) -> Decimal:
        if row["job_kind"] == JobKind.TOPIC_GENERATION.value:
            return self._topic_generation_usage_total(row["run_id"])
        return self._research_usage_total(row["run_id"])

    def _reconciliation_intent(
        self, row: sqlite3.Row,
    ) -> DurableResearchExecutionIntent | DurableTopicGenerationIntent:
        """Reconstruct and fingerprint-verify the durable provider/model identity."""
        if row["job_kind"] == JobKind.TOPIC_GENERATION.value:
            return self._reconciliation_topic_intent(row)
        try:
            payload = json.loads(row["payload_json"])
            canonical_payload = canonicalize_durable_research_payload(payload)
            intent = DurableResearchExecutionIntent.from_payload(canonical_payload["execution_intent"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, DurableExecutionIntentError) as exc:
            raise ProviderAttemptReconciliationError(
                "Durable provider/model identity cannot be reconstructed."
            ) from exc
        if durable_execution_intent_fingerprint(payload) != row["execution_intent_fingerprint"]:
            raise ProviderAttemptReconciliationError(
                "Stored durable execution intent fingerprint does not match the attempt."
            )
        return intent

    def _reconciliation_verify_usage_identity(
        self, row: sqlite3.Row, usage: sqlite3.Row, actual_amount: Decimal | None,
        *, intent: DurableResearchExecutionIntent | DurableTopicGenerationIntent | None = None,
    ) -> None:
        """Accept an existing usage only on a full identity match, never on cost alone."""
        if intent is None:
            intent = self._reconciliation_intent(row)
        problems: list[str] = []
        if usage["run_id"] != row["run_id"]:
            problems.append("run_id")
        if int(usage["dry_run"]) != 0:
            problems.append("dry_run")
        if int(usage["is_legacy_usage"]) != 0:
            problems.append("is_legacy_usage")
        if usage["request_id"] != row["request_id"]:
            problems.append("request_id")
        if usage["provider"] != intent.provider:
            problems.append("provider")
        if usage["model"] != intent.model:
            problems.append("model")
        acceptable_tasks = (
            frozenset((TOPIC_GENERATION_USAGE_TASK,))
            if row["job_kind"] == JobKind.TOPIC_GENERATION.value
            else _RECONCILIATION_RESEARCH_USAGE_TASKS
        )
        if usage["task"] not in acceptable_tasks:
            problems.append("task")
        if actual_amount is not None and not _money_equal(
                usage["estimated_cost_usd"], actual_amount, label="Existing reconciled usage"):
            problems.append("cost")
        if problems:
            raise ProviderAttemptReconciliationError(
                "Existing usage identity mismatch: " + ",".join(problems)
            )

    def _reconciliation_require_exclusive_card(self, row: sqlite3.Row) -> None:
        """RESULT_ALREADY_FINALIZED needs an exclusive durable Research Card proof."""
        card_id = row["research_card_id"]
        if card_id is None:
            raise ProviderAttemptReconciliationError(
                "RESULT_ALREADY_FINALIZED requires a finalized Research Card."
            )
        if row["run_status"] != "SUCCESS" or row["research_status"] != "COMPLETE":
            raise ProviderAttemptReconciliationError(
                "RESULT_ALREADY_FINALIZED requires a SUCCESS run and a COMPLETE research_run."
            )
        card = self.conn.execute(
            "SELECT c.id FROM research_cards c WHERE c.id=? AND c.topic_id=?",
            (card_id, row["topic_id"]),
        ).fetchone()
        if card is None:
            raise ProviderAttemptReconciliationError(
                "Finalized Research Card not found for the attempt topic."
            )
        owners = self.conn.execute(
            "SELECT id FROM research_runs WHERE research_card_id=?", (card_id,),
        ).fetchall()
        if len(owners) != 1 or owners[0]["id"] != row["run_id"]:
            raise ProviderAttemptReconciliationError(
                "Research Card is not exclusively owned by this research_run."
            )

    def _reconciliation_assert_ledger_cache_consistent(
        self, row: sqlite3.Row, expected_total: Decimal,
    ) -> None:
        """Canonical usage equals every lifecycle-specific cost cache."""
        run_id = row["run_id"]
        canonical = self._reconciliation_usage_total(row)
        if canonical != expected_total:
            raise ProviderAttemptReconciliationError(
                "Canonical ledger total changed during reconciliation."
            )
        run_row = self.conn.execute("SELECT cost_usd FROM runs WHERE id=?", (run_id,)).fetchone()
        if run_row is None:
            raise ProviderAttemptReconciliationError("Cost cache rows missing during reconciliation.")
        if not _money_equal(run_row["cost_usd"], canonical, label="run cost cache"):
            raise ProviderAttemptReconciliationError(
                "Ledger and cost cache diverged after reconciliation."
            )
        if row["job_kind"] != JobKind.TOPIC_GENERATION.value:
            rr_row = self.conn.execute(
                "SELECT total_cost_usd FROM research_runs WHERE id=?", (run_id,),
            ).fetchone()
            if rr_row is None or not _money_equal(
                rr_row["total_cost_usd"], canonical,
                label="research_run cost cache",
            ):
                raise ProviderAttemptReconciliationError(
                    "Ledger and cost cache diverged after reconciliation."
                )

    def _reconciliation_assert_settled_execution_cache_prestate(
        self, row: sqlite3.Row, expected_total: Decimal,
    ) -> None:
        """Validate the real post-usage/pre-finalization cache contract.

        ``add_job_model_usage`` immediately refreshes ``runs.cost_usd``.  The
        single-flow ``research_runs.total_cost_usd`` cache is intentionally
        finalized later with the lifecycle, so PENDING legitimately remains
        zero in the crash window.  Already-terminal compatible prestates must
        already carry the canonical total.
        """
        canonical = self._reconciliation_usage_total(row)
        if canonical != expected_total or not _money_equal(
            row["run_cost_usd"], canonical, label="run cost cache",
        ):
            raise ProviderAttemptReconciliationError(
                "Canonical ledger and run cost cache diverged before execution recovery."
            )
        if row["job_kind"] == JobKind.TOPIC_GENERATION.value:
            if row["research_status"] is not None or row["research_cost_usd"] is not None:
                raise ProviderAttemptReconciliationError(
                    "Topic-generation execution recovery forbids a research_run cache."
                )
            return
        research_amount = _money(
            row["research_cost_usd"], positive=False,
            label="research_run pre-finalization cost cache",
        )
        expected_research = (
            Decimal("0")
            if row["research_status"] == ResearchRunStatus.PENDING.value
            else canonical
        )
        if research_amount != expected_research:
            raise ProviderAttemptReconciliationError(
                "research_run cost cache is not a legal pre-finalization value."
            )

    def _append_reconciliation_event(
        self, *, request_id: str, event_type: ReconciliationEventType,
        financial_resolution: FinancialResolution, execution_resolution: ExecutionResolution,
        operator: str, note: str, previous_status: str, resulting_status: str,
        idempotency_key: str, created_at: str,
    ) -> ReconciliationEvent:
        sequence_number = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_number),0)+1 FROM reconciliation_events WHERE request_id=?",
            (request_id,),
        ).fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO reconciliation_events (request_id,sequence_number,event_type,financial_resolution,"
            "execution_resolution,operator,note,previous_attempt_status,resulting_attempt_status,created_at,"
            "idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, int(sequence_number), event_type.value, financial_resolution.value,
             execution_resolution.value, operator, note, previous_status, resulting_status,
             created_at, idempotency_key),
        )
        if cursor.rowcount != 1:
            raise ProviderAttemptReconciliationError("Reconciliation event insert failed.")
        inserted = self.conn.execute(
            "SELECT * FROM reconciliation_events WHERE id=?", (cursor.lastrowid,),
        ).fetchone()
        assert inserted is not None
        return self._reconciliation_event_from_row(inserted)

    def list_reconciliation_events(
        self, *, request_id: str, account_id: str,
    ) -> list[ReconciliationEvent]:
        """Read-only, ordered append-only history for one attempt (account scoped)."""
        row = self._reconciliation_state_row(request_id)
        if row is None or row["job_account_id"] != account_id:
            raise ProviderAttemptReconciliationError("Attempt does not belong to the requested account.")
        return [
            self._reconciliation_event_from_row(event)
            for event in self.conn.execute(
                "SELECT * FROM reconciliation_events WHERE request_id=? ORDER BY sequence_number",
                (request_id,),
            )
        ]

    def _require_settled_execution_card(self, row: sqlite3.Row) -> None:
        """Validate a card persisted before lifecycle terminalization.

        Unlike the financial reconciliation helper, this proof deliberately
        accepts RUNNING/STOPPED + PENDING: those are the exact crash states this
        recovery closes.  The card must already be exclusively linked to this
        single research_run and to its account-owned topic.
        """
        card_id = row["research_card_id"]
        if card_id is None:
            raise ProviderAttemptReconciliationError(
                "RESULT_ALREADY_FINALIZED requires a durable Research Card."
            )
        if row["run_status"] not in (
            RunStatus.RUNNING.value, RunStatus.STOPPED.value, RunStatus.SUCCESS.value,
        ) or row["research_status"] not in (
            ResearchRunStatus.PENDING.value, ResearchRunStatus.COMPLETE.value,
        ):
            raise ProviderAttemptReconciliationError(
                "Recovered Research Card has an incompatible pre-terminal lifecycle."
            )
        card = self.conn.execute(
            "SELECT c.id FROM research_cards c JOIN topics t ON t.id=c.topic_id "
            "WHERE c.id=? AND c.topic_id=? AND t.account_id=?",
            (card_id, row["topic_id"], row["job_account_id"]),
        ).fetchone()
        owners = self.conn.execute(
            "SELECT id FROM research_runs WHERE research_card_id=?", (card_id,),
        ).fetchall()
        if card is None or len(owners) != 1 or owners[0]["id"] != row["run_id"]:
            raise ProviderAttemptReconciliationError(
                "Recovered Research Card lineage or exclusive ownership is inconsistent."
            )

    def _resolve_settled_execution_in_transaction(
        self,
        *,
        row: sqlite3.Row,
        account_id: str,
        execution_resolution: ExecutionResolution,
        actual_amount: Decimal,
        operator: str,
        note_text: str,
        current_ts: str,
    ) -> ProviderAttemptReconciliationResult:
        """Resolve only execution state for an already-known SETTLED charge.

        ``EXECUTION_RECOVERY`` is inserted once and the 0015 AFTER trigger
        terminalizes the lifecycle.  The provider attempt, actual cost and sole
        canonical usage are never changed or recreated.
        """
        request_id = str(row["request_id"])
        if row["status"] != ProviderAttemptStatus.SETTLED.value:
            raise ProviderAttemptReconciliationError(
                "Execution-only recovery requires a SETTLED provider attempt."
            )
        if execution_resolution not in (
            ExecutionResolution.EXECUTION_FAILED,
            ExecutionResolution.RESULT_ALREADY_FINALIZED,
        ):
            raise ProviderAttemptReconciliationError(
                "SETTLED execution recovery requires a terminal execution resolution."
            )
        if not _money_equal(
            row["actual_cost_usd"], actual_amount, label="Settled provider actual cost",
        ):
            raise ProviderAttemptReconciliationError(
                "SETTLED execution recovery cannot change the provider actual cost."
            )

        usage_rows = self.conn.execute(
            (
                "SELECT * FROM model_usage WHERE run_id=? ORDER BY id"
                if row["job_kind"] == JobKind.TOPIC_GENERATION.value
                else "SELECT * FROM model_usage WHERE request_id=? AND dry_run=0 "
                     "AND is_legacy_usage=0 ORDER BY id"
            ),
            (
                (row["run_id"],)
                if row["job_kind"] == JobKind.TOPIC_GENERATION.value
                else (request_id,)
            ),
        ).fetchall()
        if len(usage_rows) != 1:
            raise ProviderAttemptReconciliationError(
                "SETTLED execution recovery requires exactly one canonical usage."
            )
        intent = self._reconciliation_require_consistent_lineage(row, account_id)
        self._reconciliation_verify_usage_identity(
            row, usage_rows[0], actual_amount, intent=intent,
        )
        self._reconciliation_assert_settled_execution_cache_prestate(row, actual_amount)
        is_topic_generation = row["job_kind"] == JobKind.TOPIC_GENERATION.value
        if is_topic_generation and execution_resolution is not (
            ExecutionResolution.EXECUTION_FAILED
        ):
            raise ProviderAttemptReconciliationError(
                "TOPIC_GENERATION SETTLED recovery supports EXECUTION_FAILED only."
            )

        if row["lease_owner"] is not None or row["lease_expires_at"] is not None:
            raise ProviderAttemptReconciliationError(
                "SETTLED execution recovery requires a dead execution fence."
            )
        if row["job_status"] != JobStatus.NEEDS_VERIFICATION.value:
            existing = self.conn.execute(
                "SELECT * FROM reconciliation_events WHERE request_id=? "
                "AND event_type='EXECUTION_RECOVERY'",
                (request_id,),
            ).fetchone()
            if existing is None:
                raise ProviderAttemptReconciliationError(
                    "SETTLED execution resolver requires NEEDS_VERIFICATION."
                )
        if not _money_equal(
            row["reserved_cost_usd"], Decimal("0"), label="Recovered job reservation",
        ) or row["budget_reserved_at"] is not None:
            raise ProviderAttemptReconciliationError(
                "SETTLED execution recovery requires a fully settled reservation."
            )

        if execution_resolution is ExecutionResolution.EXECUTION_FAILED:
            if row["research_card_id"] is not None:
                raise ProviderAttemptReconciliationError(
                    "EXECUTION_FAILED cannot coexist with a Research Card."
                )
            research_lifecycle_valid = (
                row["research_status"] is None
                if is_topic_generation
                else row["research_status"] in (
                    ResearchRunStatus.PENDING.value,
                    ResearchRunStatus.FAILED.value,
                )
            )
            if row["run_status"] not in _EXECUTION_FAILED_RUN_STATUSES or not (
                research_lifecycle_valid
            ):
                raise ProviderAttemptReconciliationError(
                    "SETTLED execution failure has an incompatible lifecycle."
                )
            if is_topic_generation and self._reconciliation_validate_topic_generated_lineage(row):
                raise ProviderAttemptReconciliationError(
                    "SETTLED topic execution failure cannot coexist with generated topics."
                )
        else:
            self._require_settled_execution_card(row)

        idempotency_key = self._reconciliation_idempotency_key(
            request_id, FinancialResolution.CHARGED_KNOWN, execution_resolution,
            operator, note_text, "EXECUTION_RECOVERY",
        )
        existing = self.conn.execute(
            "SELECT * FROM reconciliation_events WHERE request_id=? "
            "AND event_type='EXECUTION_RECOVERY'",
            (request_id,),
        ).fetchone()
        if existing is not None:
            event = self._reconciliation_event_from_row(existing)
            if event.financial_resolution is not FinancialResolution.CHARGED_KNOWN or \
                    event.execution_resolution is not execution_resolution:
                raise ProviderAttemptReconciliationError(
                    "SETTLED execution was already recovered with different parameters."
                )
            return ProviderAttemptReconciliationResult(
                attempt=self._provider_attempt_from_row(row),
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=execution_resolution,
                usage_id=int(usage_rows[0]["id"]), idempotent=True, event=event,
            )

        event = self._append_reconciliation_event(
            request_id=request_id,
            event_type=ReconciliationEventType.EXECUTION_RECOVERY,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=execution_resolution,
            operator=operator, note=note_text,
            previous_status=ProviderAttemptStatus.SETTLED.value,
            resulting_status=ProviderAttemptStatus.SETTLED.value,
            idempotency_key=idempotency_key, created_at=current_ts,
        )
        self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_EVENT_INSERT)
        resolved = self._reconciliation_state_row(request_id)
        assert resolved is not None
        expected = (
            (JobStatus.FAILED.value, RunStatus.FAILED.value, None)
            if is_topic_generation
            else (
                (
                    JobStatus.FAILED.value,
                    RunStatus.FAILED.value,
                    ResearchRunStatus.FAILED.value,
                )
                if execution_resolution is ExecutionResolution.EXECUTION_FAILED
                else (
                    JobStatus.DONE.value,
                    RunStatus.SUCCESS.value,
                    ResearchRunStatus.COMPLETE.value,
                )
            )
        )
        if (
            resolved["job_status"], resolved["run_status"], resolved["research_status"]
        ) != expected or resolved["status"] != ProviderAttemptStatus.SETTLED.value:
            raise ProviderAttemptReconciliationError(
                "EXECUTION_RECOVERY did not create the expected terminal lifecycle."
            )
        self._reconciliation_assert_ledger_cache_consistent(row, actual_amount)
        return ProviderAttemptReconciliationResult(
            attempt=self._provider_attempt_from_row(resolved),
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=execution_resolution,
            usage_id=int(usage_rows[0]["id"]), event=event,
        )

    def preview_provider_attempt_reconciliation(
        self, *, request_id: str, account_id: str,
    ) -> ReconciliationPreview:
        """Read-only durable snapshot + version token; performs no mutation."""
        if not isinstance(request_id, str) or not request_id.strip() or not isinstance(account_id, str) or not account_id.strip():
            raise ProviderAttemptReconciliationError("request_id and account_id are required.")
        try:
            self.conn.execute("BEGIN")
            row = self._reconciliation_state_row(request_id)
            if row is None or row["job_account_id"] != account_id:
                raise ProviderAttemptReconciliationError("Attempt does not belong to the requested account.")
            usage_rows = self.conn.execute(
                "SELECT estimated_cost_usd FROM model_usage WHERE request_id=? AND dry_run=0 AND is_legacy_usage=0",
                (request_id,),
            ).fetchall()
            run_id = row["run_id"]
            canonical = (
                self._reconciliation_usage_total(row)
                if run_id is not None else Decimal("0.000000")
            )
            events = self.conn.execute(
                "SELECT * FROM reconciliation_events WHERE request_id=? ORDER BY sequence_number",
                (request_id,),
            ).fetchall()
            token = self._reconciliation_version_token(row)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise
        active = row["status"] in (
            ProviderAttemptStatus.RESERVED.value,
            ProviderAttemptStatus.REQUEST_STARTED.value,
            ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
        )
        return ReconciliationPreview(
            request_id=request_id, account_id=account_id,
            attempt_status=ProviderAttemptStatus(row["status"]),
            job_status=row["job_status"], run_status=row["run_status"],
            research_run_status=row["research_status"],
            usage_count=len(usage_rows), canonical_cost_usd=format(canonical, "f"),
            reserved_amount_usd=float(row["reserved_amount_usd"]), reservation_active=active,
            research_card_id=row["research_card_id"], event_count=len(events),
            latest_event=self._reconciliation_event_from_row(events[-1]) if events else None,
            version_token=token,
        )

    def resolve_provider_attempt_reconciliation(
        self,
        *,
        request_id: str,
        account_id: str,
        financial_resolution: FinancialResolution,
        execution_resolution: ExecutionResolution,
        actual_cost_usd: float | str | None,
        reconciled_by: str,
        note: str,
        expected_version_token: str | None = None,
        now: datetime | None = None,
    ) -> ProviderAttemptReconciliationResult:
        """Resolve financial uncertainty or a SETTLED execution crash atomically.

        The method is intentionally outside worker fences: a human resolves an
        already stopped job.  It never calls a provider.  ``CHARGE_UNKNOWN`` only
        appends an audit observation; ``CHARGED_KNOWN``/``NOT_CHARGED`` terminalize
        the attempt, the append-only history, the canonical ``model_usage`` ledger,
        the cost cache, and the job lifecycle together, or roll everything back.
        A pre-existing SETTLED outcome takes a separate execution-only branch: its
        attempt, usage and cost remain unchanged while EXECUTION_RECOVERY closes
        the lifecycle through the additive 0015 SQLite contract.
        """
        if not isinstance(financial_resolution, FinancialResolution):
            financial_resolution = FinancialResolution(financial_resolution)
        if not isinstance(execution_resolution, ExecutionResolution):
            execution_resolution = ExecutionResolution(execution_resolution)
        if not isinstance(request_id, str) or not request_id.strip() or not isinstance(account_id, str) or not account_id.strip():
            raise ProviderAttemptReconciliationError("request_id and account_id are required.")
        if expected_version_token is not None and (
                not isinstance(expected_version_token, str) or not expected_version_token.strip()):
            raise ProviderAttemptReconciliationError("A provided version token must be a non-empty string.")
        operator = self._reconciliation_text(reconciled_by, label="reconciled_by", limit=128)
        note_text = self._reconciliation_text(note, label="reconciliation note", limit=1000)
        if execution_resolution not in _ALLOWED_RECONCILIATION_EXECUTION_RESOLUTIONS[financial_resolution]:
            raise ProviderAttemptReconciliationError(
                f"{financial_resolution.value} may not use {execution_resolution.value}."
            )
        if financial_resolution is FinancialResolution.CHARGED_KNOWN:
            if actual_cost_usd is None:
                raise ProviderAttemptReconciliationError("CHARGED_KNOWN requires actual_cost_usd.")
            try:
                actual_amount: Decimal | None = _money(
                    actual_cost_usd, positive=True, label="Reconciled provider cost")
            except BudgetReservationError as exc:
                raise ProviderAttemptReconciliationError(
                    "CHARGED_KNOWN requires a positive actual_cost_usd; use NOT_CHARGED for a zero charge."
                ) from exc
        else:
            if actual_cost_usd is not None:
                raise ProviderAttemptReconciliationError("Only CHARGED_KNOWN accepts actual_cost_usd.")
            actual_amount = None

        combined = f"{financial_resolution.value}:{execution_resolution.value}"
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self._reconciliation_state_row(request_id)
            if row is None or row["job_account_id"] != account_id:
                raise ProviderAttemptReconciliationError("Attempt does not belong to the requested account.")
            if expected_version_token is not None and self._reconciliation_version_token(row) != expected_version_token:
                raise ReconciliationPreviewStaleError(
                    "Preview is stale: durable state changed since the preview token was issued."
                )
            resolution_ts = _persisted_ts(self._job_now(now))
            usage_rows = self.conn.execute(
                "SELECT * FROM model_usage WHERE request_id=? AND dry_run=0 AND is_legacy_usage=0 ORDER BY id",
                (request_id,),
            ).fetchall()
            if len(usage_rows) > 1:
                raise ProviderAttemptReconciliationError("Attempt has duplicate non-legacy usage rows.")
            status = row["status"]

            # ---- known financial outcome, missing execution terminalization ----
            if status == ProviderAttemptStatus.SETTLED.value:
                if financial_resolution is not FinancialResolution.CHARGED_KNOWN or actual_amount is None:
                    raise ProviderAttemptReconciliationError(
                        "SETTLED execution recovery requires CHARGED_KNOWN with the unchanged actual cost."
                    )
                if row["job_status"] in (
                    JobStatus.LEASED.value, JobStatus.RUNNING.value,
                ):
                    cursor = self.conn.execute(
                        "UPDATE jobs SET status='NEEDS_VERIFICATION',last_error=?,"
                        "lease_owner=NULL,lease_expires_at=NULL,updated_at=?,finished_at=NULL "
                        "WHERE id=? AND status IN ('LEASED','RUNNING') "
                        "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                        (
                            "SETTLED_EXECUTION_RECOVERY_REQUIRED", resolution_ts,
                            row["job_id"], resolution_ts,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ProviderAttemptReconciliationError(
                            "A live execution fence cannot be resolved as a SETTLED crash."
                        )
                    row = self._reconciliation_state_row(request_id)
                    assert row is not None
                result = self._resolve_settled_execution_in_transaction(
                    row=row, account_id=account_id,
                    execution_resolution=execution_resolution,
                    actual_amount=actual_amount, operator=operator,
                    note_text=note_text, current_ts=resolution_ts,
                )
                self._reconciliation_fault_point(ReconciliationFaultPoint.BEFORE_COMMIT)
                self.conn.commit()
                return result

            # ---- CHARGE_UNKNOWN: append-only observation, never terminal ----
            if financial_resolution is FinancialResolution.CHARGE_UNKNOWN:
                if status != ProviderAttemptStatus.NEEDS_RECONCILIATION.value:
                    raise ProviderAttemptReconciliationError(
                        "Only NEEDS_RECONCILIATION may receive an unresolved observation."
                    )
                self._reconciliation_require_consistent_lineage(row, account_id)
                # W1A-AUD-04: a never-started attempt has a known financial outcome
                # (no request left the process), so its charge is never "unknown".
                if row["request_started_at"] is None:
                    raise ProviderAttemptReconciliationError(
                        "An attempt that never reached REQUEST_STARTED can only be resolved NOT_CHARGED."
                    )
                idempotency_key = self._reconciliation_idempotency_key(
                    request_id, financial_resolution, execution_resolution, operator, note_text, "OBSERVATION")
                existing = self.conn.execute(
                    "SELECT * FROM reconciliation_events WHERE idempotency_key=?", (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    event = self._reconciliation_event_from_row(existing)
                    self.conn.commit()
                    return ProviderAttemptReconciliationResult(
                        attempt=self._provider_attempt_from_row(row),
                        financial_resolution=financial_resolution,
                        execution_resolution=execution_resolution, usage_id=None,
                        idempotent=True, observed=True, event=event,
                    )
                prior = self.conn.execute(
                    "SELECT COUNT(*) FROM reconciliation_events WHERE request_id=? "
                    "AND event_type IN ('UNRESOLVED_OBSERVATION','FOLLOW_UP')",
                    (request_id,),
                ).fetchone()[0]
                event_type = (
                    ReconciliationEventType.UNRESOLVED_OBSERVATION if prior == 0
                    else ReconciliationEventType.FOLLOW_UP
                )
                now = _persisted_ts(datetime.now(timezone.utc))
                event = self._append_reconciliation_event(
                    request_id=request_id, event_type=event_type,
                    financial_resolution=financial_resolution, execution_resolution=execution_resolution,
                    operator=operator, note=note_text,
                    previous_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                    resulting_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                    idempotency_key=idempotency_key, created_at=now,
                )
                self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_EVENT_INSERT)
                self._reconciliation_fault_point(ReconciliationFaultPoint.BEFORE_COMMIT)
                current = self._reconciliation_state_row(request_id)
                assert current is not None
                self.conn.commit()
                return ProviderAttemptReconciliationResult(
                    attempt=self._provider_attempt_from_row(current),
                    financial_resolution=financial_resolution,
                    execution_resolution=execution_resolution, usage_id=None, observed=True, event=event,
                )

            # ---- terminal financial outcomes: CHARGED_KNOWN / NOT_CHARGED ----
            terminal_status = (
                ProviderAttemptStatus.RECONCILED_SETTLED.value
                if financial_resolution is FinancialResolution.CHARGED_KNOWN
                else ProviderAttemptStatus.RECONCILED_RELEASED.value
            )
            if status in (
                ProviderAttemptStatus.RECONCILED_SETTLED.value,
                ProviderAttemptStatus.RECONCILED_RELEASED.value,
            ):
                if row["job_kind"] == JobKind.TOPIC_GENERATION.value:
                    self._reconciliation_require_consistent_lineage(row, account_id)
                existing_resolution = str(row["reconciliation_resolution"] or "")
                if status != terminal_status or existing_resolution != combined or \
                        row["reconciled_by"] != operator or row["reconciliation_note"] != note_text:
                    raise ProviderAttemptReconciliationError(
                        "Attempt was already reconciled with different parameters."
                    )
                if financial_resolution is FinancialResolution.CHARGED_KNOWN:
                    if len(usage_rows) != 1:
                        raise ProviderAttemptReconciliationError(
                            "Reconciled settled attempt must have exactly one canonical usage."
                        )
                    self._reconciliation_verify_usage_identity(row, usage_rows[0], actual_amount)
                    usage_id: int | None = int(usage_rows[0]["id"])
                else:
                    if usage_rows:
                        raise ProviderAttemptReconciliationError(
                            "NOT_CHARGED conflicts with existing non-legacy usage."
                        )
                    usage_id = None
                final_event_row = self.conn.execute(
                    "SELECT * FROM reconciliation_events WHERE request_id=? AND event_type='FINAL_RESOLUTION' "
                    "ORDER BY sequence_number DESC LIMIT 1",
                    (request_id,),
                ).fetchone()
                event = self._reconciliation_event_from_row(final_event_row) if final_event_row else None
                self.conn.commit()
                return ProviderAttemptReconciliationResult(
                    attempt=self._provider_attempt_from_row(row), financial_resolution=financial_resolution,
                    execution_resolution=execution_resolution, usage_id=usage_id, idempotent=True, event=event,
                )
            if status != ProviderAttemptStatus.NEEDS_RECONCILIATION.value:
                raise ProviderAttemptReconciliationError("Only NEEDS_RECONCILIATION may be resolved.")
            intent = self._reconciliation_require_consistent_lineage(row, account_id)
            is_topic_generation = row["job_kind"] == JobKind.TOPIC_GENERATION.value
            if is_topic_generation and execution_resolution is not ExecutionResolution.EXECUTION_FAILED:
                raise ProviderAttemptReconciliationError(
                    "TOPIC_GENERATION reconciliation supports EXECUTION_FAILED only."
                )
            # W1A-AUD-04: an escalated RESERVED attempt provably never crossed the
            # request boundary, so the only truthful financial outcome is NOT_CHARGED.
            if row["request_started_at"] is None and financial_resolution is not FinancialResolution.NOT_CHARGED:
                raise ProviderAttemptReconciliationError(
                    "An attempt that never reached REQUEST_STARTED can only be resolved NOT_CHARGED."
                )
            if financial_resolution is FinancialResolution.NOT_CHARGED and usage_rows:
                raise ProviderAttemptReconciliationError(
                    "NOT_CHARGED is forbidden when non-legacy usage exists."
                )
            if financial_resolution is FinancialResolution.CHARGED_KNOWN and usage_rows:
                assert actual_amount is not None
                self._reconciliation_verify_usage_identity(
                    row, usage_rows[0], actual_amount, intent=intent)

            now = _persisted_ts(datetime.now(timezone.utc))
            # W1A-SQLITE-01 write order: the attempt flips LAST, so the SQLite
            # terminal triggers can require the complete consistent end state
            # (terminal lifecycle, released reservation, canonical usage, equal
            # cost caches, matching FINAL_RESOLUTION event) inside one transaction.
            # ---- Step 1: lifecycle terminalization (job/run/research_run). ----
            if execution_resolution is ExecutionResolution.EXECUTION_FAILED:
                if row["research_card_id"] is not None:
                    raise ProviderAttemptReconciliationError(
                        "EXECUTION_FAILED cannot coexist with a Research Card."
                    )
                research_lifecycle_valid = (
                    row["research_status"] is None
                    if is_topic_generation
                    else row["research_status"] in ("PENDING", "FAILED")
                )
                if row["run_status"] not in _EXECUTION_FAILED_RUN_STATUSES \
                        or not research_lifecycle_valid:
                    raise ProviderAttemptReconciliationError(
                        "Execution failure requires a non-success single lifecycle."
                    )
                if is_topic_generation and self._reconciliation_validate_topic_generated_lineage(row):
                    raise ProviderAttemptReconciliationError(
                        "EXECUTION_FAILED cannot coexist with generated topic lineage."
                    )
                # Same status set as the precondition (never a divergent literal), so a
                # reaper-STOPPED run is driven to FAILED under one compare-and-swap.
                # error/finished_at use COALESCE to preserve any reaper/maintenance
                # history; both cost caches are refreshed in Step 2.
                run_status_placeholders = ",".join("?" for _ in _EXECUTION_FAILED_RUN_STATUSES)
                run_cursor = self.conn.execute(
                    "UPDATE runs SET status='FAILED',error=COALESCE(error,?),"
                    "finished_at=COALESCE(finished_at,?) "
                    f"WHERE id=? AND status IN ({run_status_placeholders})",
                    ("OPERATOR_RECONCILIATION_EXECUTION_FAILED", now, row["run_id"],
                     *_EXECUTION_FAILED_RUN_STATUSES),
                )
                if is_topic_generation:
                    research_rowcount = 1
                else:
                    research_cursor = self.conn.execute(
                        "UPDATE research_runs SET status='FAILED',error=?,updated_at=? "
                        "WHERE id=? AND flow='single' AND status IN ('PENDING','FAILED') AND research_card_id IS NULL",
                        ("OPERATOR_RECONCILIATION_EXECUTION_FAILED", now, row["run_id"]),
                    )
                    research_rowcount = research_cursor.rowcount
                if run_cursor.rowcount != 1 or research_rowcount != 1:
                    raise ProviderAttemptReconciliationError("Execution failure lifecycle update is inconsistent.")
                job_target = "FAILED"
                cache_run_status = "FAILED"
            else:  # RESULT_ALREADY_FINALIZED
                self._reconciliation_require_exclusive_card(row)
                job_target = "DONE"
                cache_run_status = "SUCCESS"
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_RUN_UPDATE)
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_RESEARCH_RUN_UPDATE)

            if row["job_status"] != JobStatus.NEEDS_VERIFICATION.value:
                raise ProviderAttemptReconciliationError("Resolver requires a job already in NEEDS_VERIFICATION.")
            external_effect_clear = (
                "external_effect_started_at=NULL," if is_topic_generation else ""
            )
            job_cursor = self.conn.execute(
                "UPDATE jobs SET status=?,last_error=?,lease_owner=NULL,lease_expires_at=NULL,"
                "reserved_cost_usd=0.0,budget_reserved_at=NULL," + external_effect_clear +
                "updated_at=?,finished_at=COALESCE(finished_at,?) "
                "WHERE id=? AND status='NEEDS_VERIFICATION'",
                (job_target, "OPERATOR_RECONCILIATION:" + combined, now, now, row["job_id"]),
            )
            if job_cursor.rowcount != 1:
                raise ProviderAttemptReconciliationError("Job resolution lost its compare-and-swap.")
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_JOB_UPDATE)

            # ---- Step 2: canonical usage and both cost caches. ----
            usage_id = None
            if financial_resolution is FinancialResolution.CHARGED_KNOWN:
                assert actual_amount is not None
                if usage_rows:
                    usage_id = int(usage_rows[0]["id"])
                else:
                    usage_task = (
                        TOPIC_GENERATION_USAGE_TASK
                        if is_topic_generation else "research_reconciliation"
                    )
                    usage = self.conn.execute(
                        "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,output_tokens,"
                        "cache_read_tokens,cache_write_tokens,web_search_requests,estimated_cost_usd,dry_run,request_id,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (row["run_id"], intent.provider, intent.model, usage_task, 0, 0, 0, 0, 0,
                         float(actual_amount), 0, request_id, now),
                    )
                    if usage.rowcount != 1:
                        raise ProviderAttemptReconciliationError("Canonical usage insert failed.")
                    usage_id = int(usage.lastrowid)
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_USAGE_WRITE)
            total = self._reconciliation_usage_total(row)
            run_cache_cursor = self.conn.execute(
                "UPDATE runs SET cost_usd=? WHERE id=? AND status=?",
                (float(total), row["run_id"], cache_run_status),
            )
            if is_topic_generation:
                research_cache_rowcount = 1
            elif execution_resolution is ExecutionResolution.EXECUTION_FAILED:
                research_cache_cursor = self.conn.execute(
                    "UPDATE research_runs SET total_cost_usd=?,updated_at=? "
                    "WHERE id=? AND flow='single' AND status='FAILED' AND research_card_id IS NULL",
                    (float(total), now, row["run_id"]),
                )
                research_cache_rowcount = research_cache_cursor.rowcount
            else:
                research_cache_cursor = self.conn.execute(
                    "UPDATE research_runs SET total_cost_usd=?,updated_at=? "
                    "WHERE id=? AND flow='single' AND status='COMPLETE' AND research_card_id=?",
                    (float(total), now, row["run_id"], row["research_card_id"]),
                )
                research_cache_rowcount = research_cache_cursor.rowcount
            if run_cache_cursor.rowcount != 1 or research_cache_rowcount != 1:
                raise ProviderAttemptReconciliationError("Cost cache refresh is inconsistent.")
            self._reconciliation_assert_ledger_cache_consistent(row, total)
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_CACHE_REFRESH)

            # ---- Step 3: FINAL_RESOLUTION event precedes the terminal flip; the
            # attempt-side trigger then requires this exact matching event. ----
            idempotency_key = self._reconciliation_idempotency_key(
                request_id, financial_resolution, execution_resolution, operator, note_text, "FINAL")
            event = self._append_reconciliation_event(
                request_id=request_id, event_type=ReconciliationEventType.FINAL_RESOLUTION,
                financial_resolution=financial_resolution, execution_resolution=execution_resolution,
                operator=operator, note=note_text,
                previous_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                resulting_status=terminal_status, idempotency_key=idempotency_key, created_at=now,
            )
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_EVENT_INSERT)

            # ---- Step 4: the attempt flip is the LAST durable mutation. ----
            if financial_resolution is FinancialResolution.CHARGED_KNOWN:
                attempt_cursor = self.conn.execute(
                    "UPDATE provider_attempts SET status='RECONCILED_SETTLED',settled_at=?,reconciled_at=?,"
                    "reconciled_by=?,reconciliation_note=?,reconciliation_resolution=? "
                    "WHERE request_id=? AND status='NEEDS_RECONCILIATION'",
                    (now, now, operator, note_text, combined, request_id),
                )
            else:  # NOT_CHARGED
                attempt_cursor = self.conn.execute(
                    "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at=?,reconciled_at=?,"
                    "reconciled_by=?,reconciliation_note=?,reconciliation_resolution=? "
                    "WHERE request_id=? AND status='NEEDS_RECONCILIATION'",
                    (now, now, operator, note_text, combined, request_id),
                )
            if attempt_cursor.rowcount != 1:
                raise ProviderAttemptReconciliationError("Attempt resolution lost its compare-and-swap.")
            self._reconciliation_fault_point(ReconciliationFaultPoint.AFTER_ATTEMPT_UPDATE)
            self._reconciliation_fault_point(ReconciliationFaultPoint.BEFORE_COMMIT)
            resolved = self._reconciliation_state_row(request_id)
            assert resolved is not None
            self.conn.commit()
            return ProviderAttemptReconciliationResult(
                attempt=self._provider_attempt_from_row(resolved), financial_resolution=financial_resolution,
                execution_resolution=execution_resolution, usage_id=usage_id, event=event,
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def fail_or_escalate_job_research_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False, preserve_for_verification: bool = False,
    ) -> ResearchExecutionFailureOutcome:
        """Atomically fail a safe execution or expose its active attempt for review.

        RESERVED, REQUEST_STARTED, and NEEDS_RECONCILIATION are never hidden
        behind a terminal job/run state.  The first two are escalated, with the
        reservation retained, before the job moves to NEEDS_VERIFICATION.  An
        already-escalated attempt is idempotent and never gains a second event.

        StoragePort owns the semantic operation and executes it in one SQLite
        transaction.  SQLite triggers provide a durable-state floor; they do not
        prove provenance against an arbitrary privileged multi-table writer.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            lifecycle = self.conn.execute(
                "SELECT j.status AS job_status,j.run_id,j.lease_owner,j.lease_expires_at,"
                "r.status AS run_status,rr.status AS research_status,rr.research_card_id "
                "FROM jobs j JOIN runs r ON r.id=j.run_id "
                "JOIN research_runs rr ON rr.id=j.run_id "
                "WHERE j.id=? AND j.run_id=?",
                (execution.job_id, execution.run_id),
            ).fetchone()
            if lifecycle is None:
                raise StaleJobExecutionError(
                    execution.job_id, "research lifecycle relation no longer exists.",
                )

            active_attempts = self.conn.execute(
                "SELECT request_id,status FROM provider_attempts WHERE job_id=? "
                "AND status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION') "
                "ORDER BY stage,attempt_no",
                (execution.job_id,),
            ).fetchall()
            if len(active_attempts) > 1:
                raise ProviderAttemptReconciliationError(
                    "Research execution has multiple active provider attempts."
                )

            if active_attempts:
                active = active_attempts[0]
                state = self._reconciliation_state_row(active["request_id"])
                if state is None:
                    raise ProviderAttemptReconciliationError(
                        "Active provider attempt disappeared during failure normalization."
                    )
                # Failure normalization needs the durable structural relation,
                # but it must not rewrite or bless a mismatched execution-intent
                # fingerprint.  Moving the attempt into the operator queue keeps
                # that P2-1 case visible and reserved; the resolver still performs
                # the full fingerprint recomputation and fails closed.
                structural_problems: list[str] = []
                if state["run_id"] is None or state["run_status"] is None \
                        or state["research_status"] is None:
                    structural_problems.append("job->run->research_run")
                if state["job_kind"] != JobKind.RESEARCH.value:
                    structural_problems.append("job.kind")
                if state["job_workflow"] != WorkflowType.RESEARCH.value:
                    structural_problems.append("job.workflow")
                if state["run_account_id"] != state["job_account_id"]:
                    structural_problems.append("run.account_id")
                if state["run_workflow"] != WorkflowType.RESEARCH.value:
                    structural_problems.append("run.workflow")
                if state["research_account_id"] != state["job_account_id"]:
                    structural_problems.append("research_run.account_id")
                if state["topic_id"] is None or state["research_topic_id"] != state["topic_id"]:
                    structural_problems.append("research_run.topic_id")
                if state["research_flow"] != ResearchFlow.SINGLE.value:
                    structural_problems.append("research_run.flow")
                if structural_problems:
                    raise ProviderAttemptReconciliationError(
                        "Attempt lineage is inconsistent: " + ",".join(structural_problems)
                    )
                attempt_status = ProviderAttemptStatus(active["status"])

                if attempt_status is ProviderAttemptStatus.NEEDS_RECONCILIATION:
                    if state["job_status"] == JobStatus.NEEDS_VERIFICATION.value:
                        if state["run_status"] not in (
                            RunStatus.RUNNING.value, RunStatus.STOPPED.value,
                        ) or state["research_status"] != ResearchRunStatus.PENDING.value:
                            raise ProviderAttemptReconciliationError(
                                "Escalated provider attempt has an inconsistent lifecycle."
                            )
                        self.conn.commit()
                        return ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION
                    if state["job_status"] not in _EXECUTABLE_JOB_STATUSES:
                        raise ProviderAttemptReconciliationError(
                            "Active reconciliation is hidden behind a non-reviewable job state."
                        )
                    self._require_job_execution_fence(execution, current_ts)
                    job_cursor = self.conn.execute(
                        "UPDATE jobs SET status='NEEDS_VERIFICATION',last_error=?,"
                        "lease_owner=NULL,lease_expires_at=NULL,updated_at=?,finished_at=NULL "
                        "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                        "AND status IN ('LEASED','RUNNING')",
                        (
                            error, current_ts, execution.job_id, execution.run_id,
                            execution.lease_owner, current_ts,
                        ),
                    )
                    if job_cursor.rowcount != 1:
                        raise StaleJobExecutionError(execution.job_id)
                    self.conn.commit()
                    return ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION

                already_preserved = state["job_status"] == JobStatus.NEEDS_VERIFICATION.value
                if already_preserved:
                    if state["lease_owner"] is not None or state["lease_expires_at"] is not None:
                        raise ProviderAttemptReconciliationError(
                            "A reviewable job must not retain an execution lease."
                        )
                    run_status = state["run_status"]
                    research_status = state["research_status"]
                else:
                    fence = self._require_job_execution_fence(execution, current_ts)
                    run_status = fence["run_status"]
                    research_status = fence["research_status"]
                if run_status not in (
                    RunStatus.RUNNING.value, RunStatus.DRY_RUN.value,
                ) or research_status != ResearchRunStatus.PENDING.value:
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "research lifecycle is no longer mutable by this execution.",
                    )
                reason = (
                    _UNEXPECTED_FAILURE_BEFORE_REQUEST_STARTED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else _UNEXPECTED_FAILURE_AFTER_REQUEST_STARTED
                )
                financial = (
                    FinancialResolution.NOT_CHARGED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else FinancialResolution.CHARGE_UNKNOWN
                )
                attempt_cursor = self.conn.execute(
                    "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',error_code=? "
                    "WHERE request_id=? AND status=?",
                    (reason, active["request_id"], attempt_status.value),
                )
                if attempt_cursor.rowcount != 1:
                    raise ProviderAttemptReconciliationError(
                        "Provider attempt changed during failure normalization."
                    )
                self._append_reconciliation_event(
                    request_id=active["request_id"],
                    event_type=ReconciliationEventType.AUTO_ESCALATION,
                    financial_resolution=financial,
                    execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                    operator=_WORKER_FAILURE_ESCALATION_OPERATOR,
                    note=reason,
                    previous_status=attempt_status.value,
                    resulting_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                    idempotency_key=self._reconciliation_idempotency_key(
                        active["request_id"], financial,
                        ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                        _WORKER_FAILURE_ESCALATION_OPERATOR, reason, "ESCALATION",
                    ),
                    created_at=current_ts,
                )
                if not already_preserved:
                    job_cursor = self.conn.execute(
                        "UPDATE jobs SET status='NEEDS_VERIFICATION',last_error=?,"
                        "lease_owner=NULL,lease_expires_at=NULL,updated_at=?,finished_at=NULL "
                        "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                        "AND status IN ('LEASED','RUNNING')",
                        (
                            error, current_ts, execution.job_id, execution.run_id,
                            execution.lease_owner, current_ts,
                        ),
                    )
                    if job_cursor.rowcount != 1:
                        raise StaleJobExecutionError(execution.job_id)
                self.conn.commit()
                return (
                    ResearchExecutionFailureOutcome.ESCALATED_RESERVED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED
                )

            if lifecycle["job_status"] in _TERMINAL_JOB_STATUSES:
                self.conn.commit()
                return ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED
            if preserve_for_verification and lifecycle["job_status"] == JobStatus.NEEDS_VERIFICATION.value:
                self.conn.commit()
                return ResearchExecutionFailureOutcome.PRESERVED_NEEDS_VERIFICATION
            if (
                lifecycle["run_status"] == RunStatus.FAILED.value
                and lifecycle["research_status"] == ResearchRunStatus.FAILED.value
                and (not terminalize_job or lifecycle["job_status"] == JobStatus.FAILED.value)
            ):
                self.conn.commit()
                return ResearchExecutionFailureOutcome.TERMINALIZED_FAILED

            fence = self._require_job_execution_fence(execution, current_ts)
            if preserve_for_verification:
                if fence["run_status"] not in (
                    RunStatus.RUNNING.value, RunStatus.DRY_RUN.value,
                ) or fence["research_status"] != ResearchRunStatus.PENDING.value:
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "research lifecycle cannot be preserved for verification.",
                    )
                job_cursor = self.conn.execute(
                    "UPDATE jobs SET status='NEEDS_VERIFICATION',last_error=?,"
                    "lease_owner=NULL,lease_expires_at=NULL,updated_at=?,finished_at=NULL "
                    "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                    "AND status IN ('LEASED','RUNNING')",
                    (
                        error, current_ts, execution.job_id, execution.run_id,
                        execution.lease_owner, current_ts,
                    ),
                )
                if job_cursor.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
                self.conn.commit()
                return ResearchExecutionFailureOutcome.PRESERVED_NEEDS_VERIFICATION
            canonical = self._research_usage_total(execution.run_id)
            if cost_usd is not None and canonical != _money(
                    cost_usd, positive=False, label="Worker research failure cost"):
                raise ResearchTopicIntegrityError(
                    "Worker research failure cost must equal canonical model usage."
                )
            if fence["run_status"] not in (RunStatus.RUNNING.value, RunStatus.DRY_RUN.value) or \
                    fence["research_status"] != ResearchRunStatus.PENDING.value:
                raise StaleJobExecutionError(
                    execution.job_id, "research lifecycle is no longer mutable by this execution.",
                )
            run_cursor = self.conn.execute(
                "UPDATE runs SET status='FAILED',cost_usd=?,error=?,finished_at=? "
                "WHERE id=? AND status IN ('RUNNING','DRY_RUN') AND finished_at IS NULL "
                "AND EXISTS (SELECT 1 FROM jobs WHERE id=? AND run_id=runs.id "
                "AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING'))",
                (
                    float(canonical), error, current_ts, execution.run_id, execution.job_id,
                    execution.lease_owner, current_ts,
                ),
            )
            research_cursor = self.conn.execute(
                "UPDATE research_runs SET status='FAILED',error=?,total_cost_usd=?,updated_at=? "
                "WHERE id=? AND flow='single' AND status='PENDING' "
                "AND research_card_id IS NULL AND EXISTS (SELECT 1 FROM jobs "
                "WHERE id=? AND run_id=research_runs.id AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    error, float(canonical), current_ts, execution.run_id, execution.job_id,
                    execution.lease_owner, current_ts,
                ),
            )
            if run_cursor.rowcount != 1 or research_cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            if terminalize_job:
                job_cursor = self.conn.execute(
                    "UPDATE jobs SET status='FAILED',last_error=?,lease_owner=NULL,"
                    "lease_expires_at=NULL,updated_at=?,finished_at=?,"
                    "reserved_cost_usd=0.0,budget_reserved_at=NULL WHERE id=? "
                    "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                    "AND status IN ('LEASED','RUNNING')",
                    (
                        error, current_ts, current_ts, execution.job_id,
                        execution.run_id, execution.lease_owner, current_ts,
                    ),
                )
                if job_cursor.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return ResearchExecutionFailureOutcome.TERMINALIZED_FAILED
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def fail_job_research_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False,
    ) -> ResearchExecutionFailureOutcome:
        """Compatibility alias for the centralized fail-or-escalate operation."""
        return self.fail_or_escalate_job_research_execution(
            execution, cost_usd, error, terminalize_job=terminalize_job,
        )

    @staticmethod
    def _allowed_finalization_topic_statuses(force_re_research: bool) -> tuple[str, ...]:
        """Jedyna definicja statusów tematu, z których finalizacja jest legalna.

        Zwykły research kończy się wyłącznie z `SELECTED`. Jawny evidence
        RE-RESEARCH dopuszcza dodatkowo `USED` — dokładnie ta sama para, którą
        od dawna finalizują flow staged i legacy, więc temat po sukcesie zostaje
        `USED`, a stara karta pozostaje nietkniętym rekordem historycznym.
        """
        if force_re_research:
            return (TopicStatus.SELECTED.value, TopicStatus.USED.value)
        return (TopicStatus.SELECTED.value,)

    def _durable_re_research_authorized(self, job_id: str, current_ts: str) -> bool:
        """True tylko dla zamrożonego, zatwierdzonego kontraktu re-researchu.

        Autorytetem trybu jest payload joba skonfrontowany bajt-w-bajt ze
        zużytym wierszem zgody L1 (fingerprint + pełny preimage intentu). Każdy
        brak, rozjazd albo wyłączona flaga daje False, więc każdy inny przepływ
        zachowuje ścisłą finalizację tylko ze stanu `SELECTED`.
        """
        row = self.conn.execute(
            "SELECT payload_json FROM jobs WHERE id=?", (job_id,),
        ).fetchone()
        if row is None:
            return False
        try:
            intent, intent_json, fingerprint = self._frozen_evidence_contract_from_payload(
                row["payload_json"], job_id,
            )
            if not intent.force_re_research:
                return False
            self._require_usable_evidence_research_approval(
                job_id,
                account_id=intent.account_id,
                topic_id=intent.topic_id,
                canonical_intent_json=intent_json,
                intent_fingerprint=fingerprint,
                current_ts=current_ts,
                require_consumed=True,
            )
        except EvidenceResearchAuthorizationError:
            return False
        return True

    def finalize_job_research_execution(
        self, execution: JobExecutionContext, card: ResearchCard, total_cost_usd: float,
        *, terminal_run_status: RunStatus,
    ) -> ResearchCard:
        """Worker-only atomic card/source/lifecycle finalization for single flow."""
        if terminal_run_status not in (RunStatus.SUCCESS, RunStatus.DRY_RUN):
            raise ValueError("Worker research success requires SUCCESS or DRY_RUN.")
        if card.id is not None:
            raise ResearchTopicIntegrityError("A worker finalization card must not be pre-persisted.")
        original_card_id = card.id
        original_sources = [(source.id, source.research_card_id) for source in card.sources]
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(execution, current_ts)
            expected_run_status = (
                RunStatus.DRY_RUN.value
                if terminal_run_status is RunStatus.DRY_RUN
                else RunStatus.RUNNING.value
            )
            if fence["run_status"] != expected_run_status or \
                    fence["research_status"] != ResearchRunStatus.PENDING.value or \
                    int(fence["topic_id"]) != int(card.topic_id):
                raise StaleJobExecutionError(
                    execution.job_id, "research lifecycle no longer matches finalization preconditions.",
                )
            canonical = self._research_usage_total(execution.run_id)
            if canonical != _money(
                    total_cost_usd, positive=False, label="Worker research finalization cost"):
                raise ResearchTopicIntegrityError(
                    "Worker research finalization cost must equal canonical model usage."
                )
            # Ta sama transakcja BEGIN IMMEDIATE rozstrzyga tryb i stan tematu
            # PONOWNIE: zmiana statusu między kontrolą sprzed granicy płatności
            # a finalizacją kończy wykonanie tutaj — bez karty i bez drugiego
            # requestu (żaden request nie wychodzi z tej ścieżki).
            re_research = self._durable_re_research_authorized(execution.job_id, current_ts)
            allowed_topic_statuses = self._allowed_finalization_topic_statuses(re_research)
            topic = self.conn.execute(
                "SELECT status FROM topics WHERE id=? AND account_id=?",
                (card.topic_id, fence["research_account_id"]),
            ).fetchone()
            if topic is None or topic["status"] not in allowed_topic_statuses:
                raise ResearchTopicIntegrityError(
                    "Worker research finalization requires an eligible topic status."
                )

            self._insert_finalization_card(card)
            for source in card.sources:
                source.research_card_id = card.id
                self._insert_finalization_source(source)

            research_cursor = self.conn.execute(
                "UPDATE research_runs SET status='COMPLETE',research_card_id=?,"
                "total_cost_usd=?,error=NULL,updated_at=? WHERE id=? AND flow='single' "
                "AND status='PENDING' AND research_card_id IS NULL AND EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=research_runs.id "
                "AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING'))",
                (
                    card.id, float(canonical), current_ts, execution.run_id, execution.job_id,
                    execution.lease_owner, current_ts,
                ),
            )
            run_cursor = self.conn.execute(
                "UPDATE runs SET status=?,cost_usd=?,error=NULL,finished_at=? "
                "WHERE id=? AND status=? AND finished_at IS NULL AND EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=runs.id AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    terminal_run_status.value, float(canonical), current_ts, execution.run_id,
                    expected_run_status, execution.job_id, execution.lease_owner, current_ts,
                ),
            )
            topic_cursor = self.conn.execute(
                "UPDATE topics SET status='USED' WHERE id=? AND account_id=? "
                f"AND status IN ({','.join('?' for _ in allowed_topic_statuses)}) "
                "AND EXISTS (SELECT 1 FROM jobs WHERE id=? "
                "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING'))",
                (
                    card.topic_id, fence["research_account_id"], *allowed_topic_statuses,
                    execution.job_id, execution.run_id, execution.lease_owner, current_ts,
                ),
            )
            job_cursor = self.conn.execute(
                "UPDATE jobs SET status='DONE',last_error=NULL,lease_owner=NULL,"
                "lease_expires_at=NULL,updated_at=?,finished_at=?,"
                "reserved_cost_usd=0.0,budget_reserved_at=NULL WHERE id=? "
                "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING')",
                (
                    current_ts, current_ts, execution.job_id, execution.run_id,
                    execution.lease_owner, current_ts,
                ),
            )
            if research_cursor.rowcount != 1 or run_cursor.rowcount != 1 or \
                    topic_cursor.rowcount != 1 or job_cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return card
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            card.id = original_card_id
            for source, (source_id, research_card_id) in zip(card.sources, original_sources):
                source.id = source_id
                source.research_card_id = research_card_id
            raise

    def attach_job_run(
        self, job_id: str, lease_owner: str, run_id: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Durably binds a just-created run to the current job lease.

        The relation is written only while the caller still owns a fresh lease.
        Both sides must be the exact single-flow relation created by the offline
        worker: RESEARCH job/workflow, same account/topic, RESEARCH run and its
        matching ``research_runs`` row. Repeating that exact relation is harmless;
        replacing a different run is rejected so a restarted worker cannot rewrite
        execution history.
        """
        if not run_id.strip():
            raise ValueError("run_id must be non-empty.")
        allowed = (JobStatus.LEASED.value, JobStatus.RUNNING.value)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            job = self.conn.execute(
                "SELECT account_id,kind,workflow,topic_id,run_id,status,lease_owner,lease_expires_at "
                "FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise self._job_lifecycle_error(
                    job_id, "RUN_ATTACHED", allowed,
                    detail="Job must exist before a run can be attached.",
                )
            if job["kind"] != JobKind.RESEARCH.value:
                raise JobRunRelationError(
                    "JOB_KIND_MISMATCH", job_id,
                    "only kind=RESEARCH may attach a research run.",
                )
            if job["workflow"] != WorkflowType.RESEARCH.value:
                raise JobRunRelationError(
                    "JOB_WORKFLOW_MISMATCH", job_id,
                    "only workflow=RESEARCH may attach a research run.",
                )
            if job["topic_id"] is None:
                raise JobRunRelationError(
                    "JOB_TOPIC_MISSING", job_id,
                    "research job must have a topic_id before a run can be attached.",
                )
            if job["status"] not in allowed:
                raise self._job_lifecycle_error(
                    job_id, "RUN_ATTACHED", allowed,
                    detail="Run binding requires an active job lifecycle state.",
                )
            if job["run_id"] is not None and job["run_id"] != run_id:
                raise JobRunConflictError(job_id, job["run_id"], run_id)

            run = self.conn.execute(
                "SELECT account_id,workflow,status FROM runs WHERE id=?", (run_id,),
            ).fetchone()
            if run is None:
                raise JobRunRelationError(
                    "RUN_MISSING", job_id, "requested run does not exist.",
                )
            if run["workflow"] != WorkflowType.RESEARCH.value:
                raise JobRunRelationError(
                    "RUN_WORKFLOW_MISMATCH", job_id,
                    "requested run must have workflow=RESEARCH.",
                )
            if run["account_id"] != job["account_id"]:
                raise JobRunRelationError(
                    "JOB_RUN_ACCOUNT_MISMATCH", job_id,
                    "job and run must belong to the same account.",
                )
            research_run = self.conn.execute(
                "SELECT account_id,topic_id,flow,status FROM research_runs WHERE id=?", (run_id,),
            ).fetchone()
            if research_run is None:
                raise JobRunRelationError(
                    "RESEARCH_RUN_MISSING", job_id,
                    "requested research run extension does not exist.",
                )
            if research_run["account_id"] != job["account_id"]:
                raise JobRunRelationError(
                    "JOB_RESEARCH_RUN_ACCOUNT_MISMATCH", job_id,
                    "job and research run must belong to the same account.",
                )
            if research_run["topic_id"] != job["topic_id"]:
                raise JobRunRelationError(
                    "JOB_RUN_TOPIC_MISMATCH", job_id,
                    "job and research run must refer to the same topic.",
                )
            if research_run["flow"] != ResearchFlow.SINGLE.value:
                raise JobRunRelationError(
                    "RESEARCH_RUN_FLOW_UNSUPPORTED", job_id,
                    "offline worker accepts only the single research flow.",
                )

            existing_binding = job["run_id"] == run_id
            if not existing_binding and run["status"] not in (
                RunStatus.RUNNING.value, RunStatus.DRY_RUN.value,
            ):
                raise JobRunRelationError(
                    "RUN_STATUS_NOT_ATTACHABLE", job_id,
                    "new binding requires a running or dry-run research run.",
                )
            if not existing_binding and research_run["status"] != ResearchRunStatus.PENDING.value:
                raise JobRunRelationError(
                    "RESEARCH_RUN_STATUS_NOT_ATTACHABLE", job_id,
                    "new binding requires a pending single-flow research run.",
                )
            if (
                existing_binding
                and job["status"] in allowed
                and job["lease_owner"] == lease_owner
                and job["lease_expires_at"] >= current_ts
            ):
                self.conn.commit()
                return
            cursor = self.conn.execute(
                "UPDATE jobs SET run_id=?, updated_at=? WHERE id=? AND run_id IS NULL "
                "AND status IN ('LEASED','RUNNING') AND lease_owner=? AND lease_expires_at >= ?",
                (run_id, current_ts, job_id, lease_owner, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status="RUN_ATTACHED", allowed_source_statuses=allowed,
                detail="Run binding requires a fresh lease and an empty run_id.",
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def mark_job_external_effect_started(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Records the durable boundary after which automatic retry is unsafe."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            row = self.conn.execute(
                "SELECT kind,status,lease_owner,lease_expires_at,external_effect_started_at "
                "FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if row is not None and row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_RUNTIME_MUTATION_FORBIDDEN",
                    "CONTENT external markers require its typed execution boundary.",
                )
            if (
                row is not None
                and row["external_effect_started_at"] is not None
                and row["status"] in (JobStatus.LEASED.value, JobStatus.RUNNING.value)
                and row["lease_owner"] == lease_owner
                and row["lease_expires_at"] >= current_ts
            ):
                self.conn.commit()
                return
            cursor = self.conn.execute(
                "UPDATE jobs SET external_effect_started_at=?, updated_at=? WHERE id=? "
                "AND status IN ('LEASED','RUNNING') AND lease_owner=? AND lease_expires_at >= ? "
                "AND external_effect_started_at IS NULL",
                (current_ts, current_ts, job_id, lease_owner, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status="EXTERNAL_EFFECT_STARTED", allowed_source_statuses=(
                    JobStatus.LEASED.value, JobStatus.RUNNING.value,
                ), detail="Lease owner, expiry, or lifecycle state did not match.",
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def complete_job(
        self, job_id: str, lease_owner: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._transition_leased_job(
            job_id, lease_owner, JobStatus.DONE, error=None, now=now, clock=clock,
            release_budget=True,
        )

    def fail_job(
        self, job_id: str, lease_owner: str, error: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._transition_leased_job(
            job_id, lease_owner, JobStatus.FAILED, error=error, now=now, clock=clock,
            release_budget=True,
        )

    def mark_job_needs_verification(
        self, job_id: str, lease_owner: str, error: str, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._transition_leased_job(
            job_id, lease_owner, JobStatus.NEEDS_VERIFICATION, error=error,
            now=now, clock=clock, release_budget=False,
        )

    def heartbeat_job_lease(
        self, job_id: str, lease_owner: str, lease_seconds: int,
        *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None:
        if not lease_owner.strip() or lease_seconds <= 0:
            raise ValueError("lease_owner must be non-empty and lease_seconds must be positive.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_RUNTIME_MUTATION_FORBIDDEN",
                    "CONTENT lease heartbeats require a typed generation fence.",
                )
            lease_until = _persisted_ts(current + timedelta(seconds=lease_seconds))
            cursor = self.conn.execute(
                "UPDATE jobs SET lease_expires_at=CASE WHEN lease_expires_at >= ? "
                "THEN lease_expires_at ELSE ? END, updated_at=? WHERE id=? "
                "AND status IN ('LEASED','RUNNING') AND lease_owner=? AND lease_expires_at >= ?",
                (lease_until, lease_until, current_ts, job_id, lease_owner, current_ts),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status="HEARTBEAT", allowed_source_statuses=(
                    JobStatus.LEASED.value, JobStatus.RUNNING.value,
                ), detail="Lease owner, expiry, or lifecycle state did not match.",
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def _recover_content_expired_lease(
        self, row: sqlite3.Row, current_ts: str,
    ) -> tuple[JobStatus, bool, str, bool] | None:
        """Recover C1 or coherent zero-cost C2 checkpoints without transport."""
        if row["kind"] != JobKind.CONTENT.value:
            return None
        content = self.conn.execute(
            "SELECT * FROM content_items WHERE job_id=?", (row["id"],),
        ).fetchone()
        if content is None:
            raise ContentFoundationError(
                "CONTENT_RECOVERY_RELATION_MISSING",
                "CONTENT recovery cannot terminalize without all four durable records.",
            )
        attempts = int(row["attempts"])
        max_attempts = int(row["max_attempts"])
        if row["run_id"] is None:
            if attempts < max_attempts and row["external_effect_started_at"] is None:
                return (
                    JobStatus.QUEUED,
                    False,
                    "Content lease expired before run initialization; safely requeued.",
                    False,
                )
            reason = "CONTENT_LEASE_EXPIRED_MAX_ATTEMPTS"
            recovery_run_id = (
                f"content-recovery:{row['id']}:"
                f"{int(row['execution_generation'])}"
            )
            self.conn.execute(
                "INSERT INTO runs (id,account_id,workflow,status,current_state,"
                "started_at,cost_usd,human_intervention_count) "
                "VALUES (?,?,?,'RUNNING','RUNNING',?,0.0,0)",
                (
                    recovery_run_id, row["account_id"], row["workflow"],
                    current_ts,
                ),
            )
            self.conn.execute(
                "INSERT INTO content_runs (run_id,content_id,job_id,account_id,"
                "research_card_id,workflow,input_sha256,status,started_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,'RUNNING',?,?)",
                (
                    recovery_run_id, content["id"], row["id"], row["account_id"],
                    content["research_card_id"], row["workflow"],
                    content["input_sha256"], current_ts, current_ts,
                ),
            )
            attached = self.conn.execute(
                "UPDATE jobs SET run_id=?,updated_at=? WHERE id=? "
                "AND run_id IS NULL AND status IN ('LEASED','RUNNING') "
                "AND lease_owner=? AND lease_expires_at=? "
                "AND execution_generation=?",
                (
                    recovery_run_id, current_ts, row["id"], row["lease_owner"],
                    row["lease_expires_at"], row["execution_generation"],
                ),
            )
            if attached.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_RECOVERY_ATTACH_FAILED",
                    "Recovery run did not attach to exactly one CONTENT job.",
                )
            content_attached = self.conn.execute(
                "UPDATE content_items SET run_id=?,status='RUNNING',updated_at=? "
                "WHERE id=? AND job_id=? AND run_id IS NULL AND status='PREPARED'",
                (recovery_run_id, current_ts, content["id"], row["id"]),
            )
            if content_attached.rowcount != 1:
                raise ContentFoundationError(
                    "CONTENT_RECOVERY_ATTACH_FAILED",
                    "Recovery run did not attach to exactly one content item.",
                )
            self._apply_content_transition_command(
                mode="RECOVERY",
                job_id=row["id"],
                run_id=recovery_run_id,
                content_id=int(content["id"]),
                account_id=row["account_id"],
                workflow=row["workflow"],
                source_status=ContentStatus.RUNNING.value,
                target_status=ContentStatus.FAILED.value,
                target_run_status=RunStatus.FAILED.value,
                target_job_status=JobStatus.FAILED.value,
                lease_owner=row["lease_owner"],
                execution_generation=int(row["execution_generation"]),
                lease_expires_at=row["lease_expires_at"],
                reason_code=reason,
                result_json=None,
                score=None,
                current_ts=current_ts,
            )
            return (
                JobStatus.FAILED,
                True,
                "Content lease expired after maximum attempts before run initialization.",
                True,
            )

        state = self.conn.execute(
            "SELECT cr.*,r.status AS general_status,r.finished_at AS general_finished,"
            "r.cost_usd AS general_cost,"
            "(SELECT count(*) FROM provider_attempts p WHERE p.job_id=cr.job_id) "
            "AS provider_attempt_count,"
            "(SELECT count(*) FROM provider_attempts p "
            "JOIN content_writer_attempts wa ON wa.request_id=p.request_id "
            "WHERE p.job_id=cr.job_id AND wa.call_mode='FAKE' "
            "AND p.status IN ('RESERVED','REQUEST_STARTED','SETTLED') "
            "AND (p.status!='SETTLED' OR p.actual_cost_usd=0.0)) "
            "AS safe_fake_attempt_count,"
            "(SELECT count(*) FROM model_usage mu WHERE mu.run_id=cr.run_id) "
            "AS usage_count,"
            "(SELECT count(*) FROM model_usage mu "
            "JOIN content_writer_attempts wa ON wa.request_id=mu.request_id "
            "WHERE mu.run_id=cr.run_id AND wa.call_mode='FAKE' "
            "AND mu.dry_run=1 AND mu.estimated_cost_usd=0.0) "
            "AS safe_fake_usage_count "
            "FROM content_runs cr JOIN runs r ON r.id=cr.run_id "
            "WHERE cr.job_id=? AND cr.run_id=? AND cr.content_id=? "
            "AND cr.account_id=? AND cr.input_sha256=?",
            (
                row["id"], row["run_id"], content["id"], content["account_id"],
                content["input_sha256"],
            ),
        ).fetchone()
        if state is None:
            raise ContentFoundationError(
                "CONTENT_RECOVERY_RELATION_INVALID",
                "Attached CONTENT recovery relation is inconsistent.",
            )
        safe_zero_cost = (
            row["external_effect_started_at"] is None
            and float(row["reserved_cost_usd"]) == 0
            and row["budget_reserved_at"] is None
            and int(state["provider_attempt_count"]) == int(
                state["safe_fake_attempt_count"]
            )
            and int(state["usage_count"]) == int(state["safe_fake_usage_count"])
            and state["general_status"] == RunStatus.RUNNING.value
            and state["general_finished"] is None
            and float(state["general_cost"]) == 0
            and state["status"] in {
                ContentStatus.PREPARED.value,
                ContentStatus.RUNNING.value,
                ContentStatus.REVISE.value,
            }
        )
        if safe_zero_cost and attempts < max_attempts:
            self._apply_content_transition_command(
                mode="RECOVERY",
                job_id=row["id"],
                run_id=row["run_id"],
                content_id=int(content["id"]),
                account_id=row["account_id"],
                workflow=row["workflow"],
                source_status=state["status"],
                target_status=ContentStatus.PREPARED.value,
                target_run_status=RunStatus.RUNNING.value,
                target_job_status=JobStatus.QUEUED.value,
                lease_owner=row["lease_owner"],
                execution_generation=int(row["execution_generation"]),
                lease_expires_at=row["lease_expires_at"],
                reason_code=None,
                result_json=None,
                score=None,
                current_ts=current_ts,
            )
            return (
                JobStatus.QUEUED,
                False,
                "Lease expired at a durable zero-cost content checkpoint; safely requeued.",
                True,
            )
        if safe_zero_cost:
            reason = "CONTENT_LEASE_EXPIRED_MAX_ATTEMPTS"
            self._apply_content_transition_command(
                mode="RECOVERY",
                job_id=row["id"],
                run_id=row["run_id"],
                content_id=int(content["id"]),
                account_id=row["account_id"],
                workflow=row["workflow"],
                source_status=state["status"],
                target_status=ContentStatus.FAILED.value,
                target_run_status=RunStatus.FAILED.value,
                target_job_status=JobStatus.FAILED.value,
                lease_owner=row["lease_owner"],
                execution_generation=int(row["execution_generation"]),
                lease_expires_at=row["lease_expires_at"],
                reason_code=reason,
                result_json=None,
                score=None,
                current_ts=current_ts,
            )
            return (
                JobStatus.FAILED,
                True,
                "Content lease expired after maximum safe offline attempts.",
                True,
            )

        reason = "CONTENT_LEASE_EXPIRED_AMBIGUOUS"
        if state["status"] not in {
            ContentStatus.PREPARED.value,
            ContentStatus.RUNNING.value,
            ContentStatus.REVISE.value,
        }:
            raise ContentFoundationError(
                "CONTENT_RECOVERY_RELATION_INVALID",
                "Ambiguous recovery found an already terminal content_run.",
            )
        self._apply_content_transition_command(
            mode="RECOVERY",
            job_id=row["id"],
            run_id=row["run_id"],
            content_id=int(content["id"]),
            account_id=row["account_id"],
            workflow=row["workflow"],
            source_status=state["status"],
            target_status=ContentStatus.NEEDS_VERIFICATION.value,
            target_run_status=RunStatus.STOPPED.value,
            target_job_status=JobStatus.NEEDS_VERIFICATION.value,
            lease_owner=row["lease_owner"],
            execution_generation=int(row["execution_generation"]),
            lease_expires_at=row["lease_expires_at"],
            reason_code=reason,
            result_json=None,
            score=None,
            current_ts=current_ts,
        )
        return (
            JobStatus.NEEDS_VERIFICATION,
            False,
            "Content lease expired after a possible paid/external boundary; no retry.",
            True,
        )

    def _recover_controlled_fetch_expired_lease(
        self, row: sqlite3.Row, current_ts: str,
    ) -> tuple[JobStatus, bool, str] | None:
        """Decide and normalize one expired controlled fetch lease (E2-B).

        Zwraca (target, release_budget, error) albo ``None`` gdy job nie jest
        kontrolowanym pobraniem. Attempt i run są normalizowane w TEJ samej
        transakcji recovery, zanim generyczny UPDATE dotknie joba — podłogi
        0018 wymuszają tę kolejność. RESERVED = jednoznacznie żaden request nie
        wyszedł, ale jednorazowa zgoda została zużyta → terminalny FAILED (bez
        wskrzeszania zgody). REQUEST_STARTED = wynik niejednoznaczny →
        NEEDS_VERIFICATION bez automatycznego ponowienia.
        """
        if row["kind"] != JobKind.RESEARCH.value:
            return None
        try:
            canonicalize_controlled_fetch_payload(json.loads(row["payload_json"]))
        except (json.JSONDecodeError, ControlledFetchIntentError):
            return None

        def _fail_run(error: str) -> None:
            if row["run_id"] is not None:
                self.conn.execute(
                    "UPDATE runs SET status='FAILED',error=?,cost_usd=0,finished_at=? "
                    "WHERE id=? AND status='RUNNING' AND finished_at IS NULL",
                    (error, current_ts, row["run_id"]),
                )

        attempt = self.conn.execute(
            "SELECT id,status FROM controlled_fetch_attempts WHERE job_id=?",
            (row["id"],),
        ).fetchone()
        if attempt is None:
            run_state = None
            if row["run_id"] is not None:
                run_state = self.conn.execute(
                    "SELECT status,finished_at,cost_usd FROM runs WHERE id=?",
                    (row["run_id"],),
                ).fetchone()
            clean_run = row["run_id"] is None or (
                run_state is not None
                and run_state["status"] == RunStatus.RUNNING.value
                and run_state["finished_at"] is None
                and float(run_state["cost_usd"]) == 0
            )
            if (
                row["external_effect_started_at"] is None
                and clean_run
                and int(row["attempts"]) < int(row["max_attempts"])
            ):
                return (
                    JobStatus.QUEUED, False,
                    "Lease expired before any controlled fetch approval was consumed; safely requeued.",
                )
            error = "Controlled fetch lease expired without a safely repeatable state."
            _fail_run(error)
            return (JobStatus.FAILED, True, error)
        if attempt["status"] == ControlledFetchAttemptStatus.RESERVED.value:
            error = (
                "CONTROLLED_FETCH_"
                + _LEASE_EXPIRED_BEFORE_REQUEST_STARTED
                + ": one-shot approval was consumed and cannot be replayed."
            )
            cursor = self.conn.execute(
                "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                "outcome_reason=? WHERE id=? AND status=?",
                (
                    ControlledFetchAttemptStatus.FAILED.value, current_ts,
                    _LEASE_EXPIRED_BEFORE_REQUEST_STARTED, attempt["id"],
                    ControlledFetchAttemptStatus.RESERVED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleTransitionError(
                    "controlled_fetch_attempt", attempt["id"],
                    ControlledFetchAttemptStatus.FAILED.value,
                    (ControlledFetchAttemptStatus.RESERVED.value,),
                    str(attempt["status"]),
                    detail="Recovery attempt normalization compare-and-swap failed.",
                )
            _fail_run(error)
            return (JobStatus.FAILED, True, error)
        if attempt["status"] == ControlledFetchAttemptStatus.REQUEST_STARTED.value:
            error = (
                "CONTROLLED_FETCH_"
                + _LEASE_EXPIRED_AFTER_REQUEST_STARTED
                + ": request outcome requires verification."
            )
            cursor = self.conn.execute(
                "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                "outcome_reason=? WHERE id=? AND status=?",
                (
                    ControlledFetchAttemptStatus.NEEDS_VERIFICATION.value, current_ts,
                    _LEASE_EXPIRED_AFTER_REQUEST_STARTED, attempt["id"],
                    ControlledFetchAttemptStatus.REQUEST_STARTED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LifecycleTransitionError(
                    "controlled_fetch_attempt", attempt["id"],
                    ControlledFetchAttemptStatus.NEEDS_VERIFICATION.value,
                    (ControlledFetchAttemptStatus.REQUEST_STARTED.value,),
                    str(attempt["status"]),
                    detail="Recovery attempt normalization compare-and-swap failed.",
                )
            _fail_run(error)
            return (JobStatus.NEEDS_VERIFICATION, False, error)
        # Terminalny attempt przy niedomkniętym jobie nie powstaje w żadnej
        # naszej transakcji; fail-closed do kolejki operatora bez mutacji attemptu.
        _fail_run("Controlled fetch attempt is terminal but the job lease expired unresolved.")
        return (
            JobStatus.NEEDS_VERIFICATION, False,
            "Controlled fetch attempt is terminal but the job lease expired unresolved.",
        )

    def release_or_requeue_expired_leases(
        self, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> JobRecoveryResult:
        """Recovers each expired lease exactly once under a write transaction.

        Browser jobs and any job after an external effect move to
        NEEDS_VERIFICATION. LOCAL and RESEARCH jobs without a durable ``run_id``
        are requeued only before max_attempts; an attached RESEARCH run requires
        explicit future reconciliation instead of an automatic restart.
        """
        result = JobRecoveryResult()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            rows = self.conn.execute(
                "SELECT id,account_id,kind,workflow,run_id,attempts,max_attempts,"
                "external_effect_started_at,payload_json,reserved_cost_usd,"
                "budget_reserved_at,lease_owner,lease_expires_at,"
                "execution_generation FROM jobs "
                "WHERE status IN ('LEASED','RUNNING') AND lease_expires_at < ? ORDER BY id",
                (current_ts,),
            ).fetchall()
            for row in rows:
                safe_offline_resume = False
                if (
                    row["kind"] == JobKind.RESEARCH.value
                    and row["run_id"] is not None
                    and row["external_effect_started_at"] is None
                    and float(row["reserved_cost_usd"]) == 0
                    and row["budget_reserved_at"] is None
                ):
                    try:
                        payload = canonicalize_offline_evidence_payload(
                            json.loads(row["payload_json"])
                        )
                    except (json.JSONDecodeError, OfflineEvidenceIntentError):
                        payload = None
                    if payload is not None:
                        state = self.conn.execute(
                            "SELECT r.status AS run_status,r.finished_at,r.cost_usd,"
                            "rr.flow,rr.status AS research_status,rr.research_card_id,"
                            "rr.total_cost_usd,"
                            "(SELECT count(*) FROM model_usage mu WHERE mu.run_id=r.id) AS usage_count,"
                            "(SELECT count(*) FROM provider_attempts pa WHERE pa.job_id=?) AS attempt_count "
                            "FROM runs r JOIN research_runs rr ON rr.id=r.id WHERE r.id=?",
                            (row["id"], row["run_id"]),
                        ).fetchone()
                        safe_offline_resume = bool(
                            state is not None
                            and state["run_status"] == RunStatus.DRY_RUN.value
                            and state["finished_at"] is None
                            and float(state["cost_usd"]) == 0
                            and state["flow"] == ResearchFlow.STAGED.value
                            and state["research_status"] in {
                                ResearchRunStatus.DISCOVERY_PENDING.value,
                                ResearchRunStatus.DISCOVERY_COMPLETE.value,
                                ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                                ResearchRunStatus.SOURCES_COMPLETE.value,
                                ResearchRunStatus.SYNTHESIS_PENDING.value,
                            }
                            and state["research_card_id"] is None
                            and float(state["total_cost_usd"]) == 0
                            and int(state["usage_count"]) == 0
                            and int(state["attempt_count"]) == 0
                        )
                content_recovery = self._recover_content_expired_lease(
                    row, current_ts,
                )
                controlled_fetch_recovery = (
                    None if content_recovery is not None
                    else self._recover_controlled_fetch_expired_lease(row, current_ts)
                )
                specialized_recovery = content_recovery or controlled_fetch_recovery
                content_job_already_updated = False
                if specialized_recovery is not None:
                    if content_recovery is not None:
                        (
                            target, release_budget, error,
                            content_job_already_updated,
                        ) = content_recovery
                    else:
                        target, release_budget, error = specialized_recovery
                    if target is JobStatus.QUEUED:
                        result.requeued_count += 1
                    elif target is JobStatus.NEEDS_VERIFICATION:
                        result.needs_verification_count += 1
                    else:
                        result.failed_count += 1
                elif row["kind"] == JobKind.BROWSER.value or row["external_effect_started_at"] is not None:
                    target = JobStatus.NEEDS_VERIFICATION
                    release_budget = False
                    result.needs_verification_count += 1
                    error = "Lease expired; external effect requires verification."
                elif safe_offline_resume and int(row["attempts"]) < int(row["max_attempts"]):
                    target = JobStatus.QUEUED
                    release_budget = False
                    result.requeued_count += 1
                    error = "Lease expired at a durable zero-cost E2-A checkpoint; safely requeued."
                elif safe_offline_resume:
                    target = JobStatus.FAILED
                    release_budget = True
                    result.failed_count += 1
                    error = "Offline E2-A lease expired after maximum attempts."
                elif row["kind"] == JobKind.RESEARCH.value and row["run_id"] is not None:
                    target = JobStatus.NEEDS_VERIFICATION
                    release_budget = False
                    result.needs_verification_count += 1
                    error = str(JobRunReconciliationRequired(row["id"]))
                elif (
                    row["kind"] == JobKind.TOPIC_GENERATION.value
                    and row["run_id"] is not None
                ):
                    # An attached topic-generation run has already consumed its
                    # one-shot L1 approval, so a requeue could never legally
                    # reserve again.  Explicit review, never an automatic restart.
                    target = JobStatus.NEEDS_VERIFICATION
                    release_budget = False
                    result.needs_verification_count += 1
                    error = str(JobRunReconciliationRequired(row["id"]))
                elif int(row["attempts"]) >= int(row["max_attempts"]):
                    target = JobStatus.FAILED
                    release_budget = True
                    result.failed_count += 1
                    error = "Lease expired after maximum attempts."
                else:
                    target = JobStatus.QUEUED
                    release_budget = False
                    result.requeued_count += 1
                    error = "Lease expired before an external effect; safely requeued."
                if content_job_already_updated:
                    continue
                fields = (
                    ", finished_at=?, reserved_cost_usd=0.0, budget_reserved_at=NULL"
                    if release_budget else ""
                )
                params: list[object] = [target.value, error, current_ts]
                if release_budget:
                    params.append(current_ts)
                params.extend([row["id"], current_ts])
                cursor = self.conn.execute(
                    "UPDATE jobs SET status=?, last_error=?, lease_owner=NULL, lease_expires_at=NULL, "
                    "updated_at=?" + fields + " WHERE id=? "
                    "AND status IN ('LEASED','RUNNING') AND lease_expires_at < ?",
                    tuple(params),
                )
                self._require_one_transition(
                    cursor, table="jobs", entity="job", identifier=row["id"],
                    target_status=target.value,
                    allowed_source_statuses=(JobStatus.LEASED.value, JobStatus.RUNNING.value),
                    detail="Expired-lease recovery compare-and-swap failed.",
                )
            # W1A-AUD-04: the same durable transaction escalates every
            # dead-fence RESERVED/REQUEST_STARTED attempt into the operator
            # queue, so no reservation can stay invisible and unresolvable.
            self._escalate_crash_window_attempts(current_ts, result)
            # PR1-MAJ-001: a known SETTLED charge is not financial uncertainty.
            # Resolve only its missing execution outcome through the 0015 audit.
            self._recover_settled_execution_attempts(current_ts, result)
            self._recovery_fault_point("BEFORE_COMMIT")
            self.conn.commit()
            return result
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def recover_controlled_live_session(
        self,
        *,
        expected_job_id: str,
        expected_request_id: str,
        now: datetime | None = None,
        clock: Clock | None = None,
    ) -> dict[str, object]:
        """Durably fence one interrupted controlled-live execution.

        The marker is the authorization for this narrowly scoped recovery.  A
        live/queued job becomes NEEDS_VERIFICATION, its lease is cleared, and a
        RESERVED/REQUEST_STARTED attempt becomes NEEDS_RECONCILIATION with an
        append-only AUTO_ESCALATION event.  No provider or retry path exists here.
        """
        if not expected_job_id.strip() or not expected_request_id.strip():
            raise ValueError("Controlled-live recovery requires expected job/request ids.")
        result: dict[str, object] = {
            "job_found": False,
            "job_status": None,
            "attempt_found": False,
            "attempt_status": None,
            "provider_request_started": False,
            "possible_unknown_provider_outcome": False,
            "reconciliation_required": False,
            "retry_performed": False,
        }
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(
                self._job_now(now, clock=None if now is not None else clock)
            )
            job = self.conn.execute(
                "SELECT id,status FROM jobs WHERE id=?",
                (expected_job_id,),
            ).fetchone()
            if job is not None:
                result["job_found"] = True
                if job["status"] in (
                    JobStatus.QUEUED.value,
                    JobStatus.LEASED.value,
                    JobStatus.RUNNING.value,
                ):
                    cursor = self.conn.execute(
                        "UPDATE jobs SET status='NEEDS_VERIFICATION',"
                        "lease_owner=NULL,lease_expires_at=NULL,last_error=?,updated_at=? "
                        "WHERE id=? AND status IN ('QUEUED','LEASED','RUNNING')",
                        (
                            "CONTROLLED_LIVE_SESSION_INTERRUPTED",
                            current_ts,
                            expected_job_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise JobRunRelationError(
                            "CONTROLLED_LIVE_RECOVERY_FENCE_LOST",
                            expected_job_id,
                            "controlled-live recovery lost its job compare-and-swap.",
                        )

            attempts = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE job_id=? ORDER BY attempt_no",
                (expected_job_id,),
            ).fetchall()
            if len(attempts) > 1:
                raise JobRunRelationError(
                    "CONTROLLED_LIVE_MULTIPLE_ATTEMPTS",
                    expected_job_id,
                    "controlled-live recovery found more than one provider attempt.",
                )
            attempt = attempts[0] if attempts else None
            if attempt is not None:
                if attempt["request_id"] != expected_request_id or int(attempt["attempt_no"]) != 1:
                    raise JobRunRelationError(
                        "CONTROLLED_LIVE_REQUEST_OWNERSHIP_MISMATCH",
                        expected_job_id,
                        "controlled-live recovery found a foreign request identity.",
                    )
                result["attempt_found"] = True
                original_status = str(attempt["status"])
                provider_started = attempt["request_started_at"] is not None
                result["provider_request_started"] = provider_started
                result["possible_unknown_provider_outcome"] = (
                    original_status
                    in (
                        ProviderAttemptStatus.REQUEST_STARTED.value,
                        ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                    )
                    and provider_started
                )
                if original_status in (
                    ProviderAttemptStatus.RESERVED.value,
                    ProviderAttemptStatus.REQUEST_STARTED.value,
                ):
                    reason = (
                        _LEASE_EXPIRED_AFTER_REQUEST_STARTED
                        if provider_started
                        else _LEASE_EXPIRED_BEFORE_REQUEST_STARTED
                    )
                    cursor = self.conn.execute(
                        "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',"
                        "error_code=? WHERE request_id=? AND status=?",
                        (reason, expected_request_id, original_status),
                    )
                    if cursor.rowcount != 1:
                        raise ProviderAttemptReconciliationError(
                            "Controlled-live recovery lost its attempt compare-and-swap."
                        )
                    operator = "controlled-live-recovery"
                    note = (
                        "Controlled-live recovery: provider request boundary was crossed; "
                        "the financial outcome may be unknown."
                        if provider_started
                        else
                        "Controlled-live recovery: the reserved attempt did not cross the "
                        "provider request boundary."
                    )
                    financial = (
                        FinancialResolution.CHARGE_UNKNOWN
                        if provider_started
                        else FinancialResolution.NOT_CHARGED
                    )
                    self._append_reconciliation_event(
                        request_id=expected_request_id,
                        event_type=ReconciliationEventType.AUTO_ESCALATION,
                        financial_resolution=financial,
                        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                        operator=operator,
                        note=note,
                        previous_status=original_status,
                        resulting_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                        idempotency_key=self._reconciliation_idempotency_key(
                            expected_request_id,
                            financial,
                            ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                            operator,
                            note,
                            "CONTROLLED_LIVE_RECOVERY",
                        ),
                        created_at=current_ts,
                    )
                    result["attempt_status"] = ProviderAttemptStatus.NEEDS_RECONCILIATION.value
                    result["reconciliation_required"] = True
                else:
                    result["attempt_status"] = original_status
                    result["reconciliation_required"] = (
                        original_status
                        == ProviderAttemptStatus.NEEDS_RECONCILIATION.value
                    )
            refreshed = self.conn.execute(
                "SELECT status FROM jobs WHERE id=?",
                (expected_job_id,),
            ).fetchone()
            result["job_status"] = None if refreshed is None else str(refreshed["status"])
            self.conn.commit()
            return result
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def reap_orphaned_stale_runs(
        self, stale_before: datetime, *, now: datetime | None = None,
        clock: Clock | None = None,
    ) -> RunReaperResult:
        """Stops only stale RUNNING runs that cannot be legally executed.

        Callers must first recover expired job leases. The reaper deliberately
        blocks on every QUEUED/LEASED/RUNNING job referencing the run, including an
        expired lease, so it cannot create ``job=QUEUED`` plus ``run=STOPPED``.
        Reconciled RESEARCH jobs are ``NEEDS_VERIFICATION`` and therefore remain
        durable audit records without authorizing a resume.
        """
        stale_ts = _persisted_ts(stale_before)
        result = RunReaperResult()
        blocking_statuses = (
            JobStatus.QUEUED.value,
            JobStatus.LEASED.value,
            JobStatus.RUNNING.value,
        )
        placeholders = ", ".join("?" for _ in blocking_statuses)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            if stale_ts >= current_ts:
                raise ValueError("stale_before must be earlier than now.")
            candidates = self.conn.execute(
                "SELECT id FROM runs WHERE status='RUNNING' AND finished_at IS NULL "
                "AND started_at < ? ORDER BY id",
                (stale_ts,),
            ).fetchall()
            result.checked_count = len(candidates)
            for candidate in candidates:
                cursor = self.conn.execute(
                    "UPDATE runs SET status='STOPPED', error=?, finished_at=? "
                    "WHERE id=? AND status='RUNNING' AND finished_at IS NULL "
                    "AND started_at < ? AND NOT EXISTS ("
                    "SELECT 1 FROM jobs WHERE jobs.run_id=runs.id "
                    f"AND jobs.status IN ({placeholders})"
                    ")",
                    (
                        _STALE_RUN_REAPER_REASON,
                        current_ts,
                        candidate["id"],
                        stale_ts,
                        *blocking_statuses,
                    ),
                )
                if cursor.rowcount == 1:
                    result.stopped_count += 1
            self.conn.commit()
            return result
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def cancel_job(
        self, job_id: str, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
                    "CONTENT jobs cannot be cancelled outside the dedicated content boundary.",
                )
            cursor = self.conn.execute(
                "UPDATE jobs SET status='CANCELLED', finished_at=?, updated_at=?, "
                "reserved_cost_usd=0.0, budget_reserved_at=NULL WHERE id=? AND status='QUEUED'",
                (current_ts, current_ts, job_id),
            )
            self._require_one_transition(
                cursor, table="jobs", entity="job", identifier=job_id,
                target_status=JobStatus.CANCELLED.value,
                allowed_source_statuses=(JobStatus.QUEUED.value,),
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def reserve_job_budget(
        self, job_id: str, amount_usd: float, *, daily_limit_usd: float,
        monthly_limit_usd: float, now: datetime | None = None, clock: Clock | None = None,
    ) -> JobReservation:
        """Atomically reserves one conservative budget amount for an active job."""
        amount = _money(amount_usd, positive=False, label="Job reservation")
        daily_limit = _money(daily_limit_usd, positive=False, label="Daily job limit")
        monthly_limit = _money(monthly_limit_usd, positive=False, label="Monthly job limit")
        placeholders = ", ".join("?" for _ in _ACTIVE_JOB_STATUSES)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            day_prefix = current.strftime("%Y-%m-%d")
            month_prefix = current.strftime("%Y-%m")
            job = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is not None and job["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_RUNTIME_MUTATION_FORBIDDEN",
                    "CONTENT budget mutations require a typed generation fence.",
                )
            if job is None or job["status"] not in _ACTIVE_JOB_STATUSES:
                raise self._job_lifecycle_error(
                    job_id, "BUDGET_RESERVED", _ACTIVE_JOB_STATUSES,
                    detail="Only an active non-terminal job may hold a reservation.",
            )
            if job["budget_reserved_at"] is not None:
                persisted_amount = _money(
                    job["reserved_cost_usd"], positive=False, label="Persisted job reservation",
                )
                if persisted_amount == amount:
                    result = JobReservation(
                        job_id=job_id, amount_usd=float(persisted_amount),
                        reserved_at=job["budget_reserved_at"],
                    )
                    self.conn.commit()
                    return result
                raise BudgetReservationError(
                    f"Job {job_id} already has a different active budget reservation."
                )
            day_real = _sum_money_rows(
                self.conn.execute(
                    "SELECT estimated_cost_usd FROM model_usage "
                    "WHERE dry_run=0 AND created_at LIKE ?", (f"{day_prefix}%",),
                ).fetchall(),
                "estimated_cost_usd",
                label="Persisted daily job cost",
            )
            month_real = _sum_money_rows(
                self.conn.execute(
                    "SELECT estimated_cost_usd FROM model_usage "
                    "WHERE dry_run=0 AND created_at LIKE ?", (f"{month_prefix}%",),
                ).fetchall(),
                "estimated_cost_usd",
                label="Persisted monthly job cost",
            )
            active_reserved = _sum_money_rows(
                self.conn.execute(
                    "SELECT reserved_cost_usd FROM jobs "
                    f"WHERE status IN ({placeholders}) AND budget_reserved_at IS NOT NULL",
                    _ACTIVE_JOB_STATUSES,
                ).fetchall(),
                "reserved_cost_usd",
                label="Persisted active job reservation",
            )
            total_reserved = _money_sum(
                (active_reserved, amount), label="Total job reservation",
            )
            if month_real + total_reserved > monthly_limit:
                raise BudgetReservationError("Reservation would exceed the global monthly limit.")
            if day_real + total_reserved > daily_limit:
                raise BudgetReservationError("Reservation would exceed the global daily limit.")
            cursor = self.conn.execute(
                "UPDATE jobs SET reserved_cost_usd=?, budget_reserved_at=?, updated_at=? "
                "WHERE id=? AND budget_reserved_at IS NULL AND status IN "
                f"({placeholders})",
                (float(amount), current_ts, current_ts, job_id, *_ACTIVE_JOB_STATUSES),
            )
            if cursor.rowcount != 1:
                raise BudgetReservationError("Concurrent reservation compare-and-swap failed.")
            self.conn.commit()
            return JobReservation(job_id=job_id, amount_usd=float(amount), reserved_at=current_ts)
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def release_job_budget(
        self, job_id: str, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None:
        placeholders = ", ".join("?" for _ in _RELEASABLE_RESERVATION_STATUSES)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
            kind_row = self.conn.execute(
                "SELECT kind FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if kind_row is not None and kind_row["kind"] == JobKind.CONTENT.value:
                raise ContentFoundationError(
                    "CONTENT_GENERIC_RUNTIME_MUTATION_FORBIDDEN",
                    "CONTENT budget mutations require a typed generation fence.",
                )
            cursor = self.conn.execute(
                "UPDATE jobs SET reserved_cost_usd=0.0, budget_reserved_at=NULL, updated_at=? "
                f"WHERE id=? AND status IN ({placeholders}) AND budget_reserved_at IS NOT NULL "
                "AND external_effect_started_at IS NULL",
                (current_ts, job_id, *_RELEASABLE_RESERVATION_STATUSES),
            )
            if cursor.rowcount == 0:
                job = self.conn.execute(
                    "SELECT status, external_effect_started_at FROM jobs WHERE id=?", (job_id,),
                ).fetchone()
                if job is None or job["status"] not in _RELEASABLE_RESERVATION_STATUSES:
                    raise self._job_lifecycle_error(
                        job_id, "BUDGET_RELEASED", _RELEASABLE_RESERVATION_STATUSES,
                        detail=(
                            "Only a queued or leased/running job without an uncertain external "
                            "effect can release a reservation."
                        ),
                    )
                if job["external_effect_started_at"] is not None:
                    raise LifecycleTransitionError(
                        "job", job_id, "BUDGET_RELEASED", _RELEASABLE_RESERVATION_STATUSES,
                        str(job["status"]),
                        detail="A job whose external effect has started must retain its reservation.",
                    )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def reserve_job_budget_for_execution(
        self, execution: JobExecutionContext, amount_usd: float, *,
        daily_limit_usd: float, monthly_limit_usd: float,
    ) -> JobReservation:
        """Owner-aware reservation path; queue-level reservations remain separate."""
        amount = _money(amount_usd, positive=False, label="Job execution reservation")
        daily_limit = _money(daily_limit_usd, positive=False, label="Daily job limit")
        monthly_limit = _money(monthly_limit_usd, positive=False, label="Monthly job limit")
        placeholders = ", ".join("?" for _ in _ACTIVE_JOB_STATUSES)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(execution.now())
            current_ts = _persisted_ts(current)
            day_prefix = current.strftime("%Y-%m-%d")
            month_prefix = current.strftime("%Y-%m")
            self._require_job_execution_fence(execution, current_ts)
            job = self.conn.execute(
                "SELECT reserved_cost_usd,budget_reserved_at FROM jobs WHERE id=?",
                (execution.job_id,),
            ).fetchone()
            assert job is not None
            if job["budget_reserved_at"] is not None:
                persisted_amount = _money(
                    job["reserved_cost_usd"], positive=False, label="Persisted job reservation",
                )
                if persisted_amount == amount:
                    result = JobReservation(
                        job_id=execution.job_id,
                        amount_usd=float(persisted_amount),
                        reserved_at=job["budget_reserved_at"],
                    )
                    self.conn.commit()
                    return result
                raise BudgetReservationError(
                    "Job execution already has a different active budget reservation."
                )
            day_real = _sum_money_rows(
                self.conn.execute(
                    "SELECT estimated_cost_usd FROM model_usage "
                    "WHERE dry_run=0 AND created_at LIKE ?", (f"{day_prefix}%",),
                ).fetchall(),
                "estimated_cost_usd",
                label="Persisted daily job cost",
            )
            month_real = _sum_money_rows(
                self.conn.execute(
                    "SELECT estimated_cost_usd FROM model_usage "
                    "WHERE dry_run=0 AND created_at LIKE ?", (f"{month_prefix}%",),
                ).fetchall(),
                "estimated_cost_usd",
                label="Persisted monthly job cost",
            )
            active_reserved = _sum_money_rows(
                self.conn.execute(
                    "SELECT reserved_cost_usd FROM jobs "
                    f"WHERE status IN ({placeholders}) AND budget_reserved_at IS NOT NULL",
                    _ACTIVE_JOB_STATUSES,
                ).fetchall(),
                "reserved_cost_usd",
                label="Persisted active job reservation",
            )
            total_reserved = _money_sum(
                (active_reserved, amount), label="Total job execution reservation",
            )
            if month_real + total_reserved > monthly_limit:
                raise BudgetReservationError("Reservation would exceed the global monthly limit.")
            if day_real + total_reserved > daily_limit:
                raise BudgetReservationError("Reservation would exceed the global daily limit.")
            cursor = self.conn.execute(
                "UPDATE jobs SET reserved_cost_usd=?,budget_reserved_at=?,updated_at=? "
                "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING') AND budget_reserved_at IS NULL",
                (
                    float(amount), current_ts, current_ts, execution.job_id,
                    execution.run_id, execution.lease_owner, current_ts,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return JobReservation(
                job_id=execution.job_id, amount_usd=float(amount), reserved_at=current,
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def release_job_budget_for_execution(self, execution: JobExecutionContext) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, current_ts)
            job = self.conn.execute(
                "SELECT budget_reserved_at,external_effect_started_at FROM jobs WHERE id=?",
                (execution.job_id,),
            ).fetchone()
            assert job is not None
            if job["external_effect_started_at"] is not None:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "an execution with a started external effect must retain its reservation.",
                )
            if job["budget_reserved_at"] is not None:
                cursor = self.conn.execute(
                    "UPDATE jobs SET reserved_cost_usd=0.0,budget_reserved_at=NULL,updated_at=? "
                    "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                    "AND status IN ('LEASED','RUNNING') AND external_effect_started_at IS NULL",
                    (
                        current_ts, execution.job_id, execution.run_id,
                        execution.lease_owner, current_ts,
                    ),
                )
                if cursor.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def read_operational_report(
        self, *, now: datetime | None = None, clock: Clock | None = None,
    ) -> OperationalReport:
        """Collect a query-only Stage 1 snapshot without inferring missing data as zero."""
        current = self._job_now(now, clock=clock)
        current_ts = _persisted_ts(current)
        tables = {
            str(row["name"])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        unknown_reasons: list[str] = []

        if "schema_migrations" not in tables:
            schema_migrations = OperationalScalar(
                status=OperationalFieldStatus.UNKNOWN,
                detail="schema_migrations table is missing.",
            )
            unknown_reasons.append("schema_migrations is unavailable")
        else:
            versions = [
                str(row["version"])
                for row in self.conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            schema_migrations = OperationalScalar(
                status=OperationalFieldStatus.OK,
                value=len(versions),
                detail=",".join(versions),
            )
            required_count = len(canonical_migration_versions())
            if (
                len(versions) != required_count
                or not versions
                or versions[-1] != RUNTIME_SCHEMA_VERSION
            ):
                unknown_reasons.append(
                    f"schema has {len(versions)} migrations; current code requires "
                    f"{required_count} ending at {RUNTIME_SCHEMA_VERSION}"
                )

        job_counts: dict[str, int] | None = None
        job_counts_status = OperationalFieldStatus.UNKNOWN
        active_leases = OperationalScalar(
            status=OperationalFieldStatus.UNKNOWN,
            detail="jobs table is missing.",
        )
        needs_verification = OperationalScalar(
            status=OperationalFieldStatus.UNKNOWN,
            detail="jobs table is missing.",
        )
        active_reservations = OperationalScalar(
            status=OperationalFieldStatus.UNKNOWN,
            detail="jobs table is missing.",
        )
        active_reserved_cost = OperationalScalar(
            status=OperationalFieldStatus.UNKNOWN,
            detail="jobs table is missing.",
        )
        if "jobs" not in tables:
            unknown_reasons.append("jobs data is unavailable")
        else:
            status_rows = self.conn.execute(
                "SELECT status,COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
            raw_counts = {str(row["status"]): int(row["count"]) for row in status_rows}
            expected_statuses = {status.value for status in JobStatus}
            unexpected = sorted(set(raw_counts) - expected_statuses)
            if unexpected:
                unknown_reasons.append(
                    "jobs contains unknown statuses: " + ",".join(unexpected)
                )
            else:
                job_counts = {
                    status.value: raw_counts.get(status.value, 0)
                    for status in JobStatus
                }
                job_counts_status = OperationalFieldStatus.OK

            invalid_active_lease = self.conn.execute(
                "SELECT COUNT(*) AS count FROM jobs "
                "WHERE status IN ('LEASED','RUNNING') "
                "AND (lease_owner IS NULL OR trim(lease_owner)='' OR lease_expires_at IS NULL)"
            ).fetchone()["count"]
            if int(invalid_active_lease):
                unknown_reasons.append("active job lease data is malformed")
                active_leases = OperationalScalar(
                    status=OperationalFieldStatus.UNKNOWN,
                    detail="LEASED/RUNNING job has incomplete lease fields.",
                )
            else:
                count = self.conn.execute(
                    "SELECT COUNT(*) AS count FROM jobs "
                    "WHERE status IN ('LEASED','RUNNING') AND lease_owner IS NOT NULL "
                    "AND lease_expires_at>=?",
                    (current_ts,),
                ).fetchone()["count"]
                active_leases = OperationalScalar(
                    status=OperationalFieldStatus.OK, value=int(count),
                )

            needs_count = self.conn.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE status='NEEDS_VERIFICATION'"
            ).fetchone()["count"]
            needs_verification = OperationalScalar(
                status=OperationalFieldStatus.OK, value=int(needs_count),
            )

            reservation_rows = self.conn.execute(
                "SELECT status,reserved_cost_usd,budget_reserved_at FROM jobs "
                "WHERE reserved_cost_usd!=0.0 OR budget_reserved_at IS NOT NULL"
            ).fetchall()
            allowed_reservation_statuses = {
                JobStatus.QUEUED.value,
                JobStatus.LEASED.value,
                JobStatus.RUNNING.value,
                JobStatus.NEEDS_VERIFICATION.value,
            }
            reservation_values: list[object] = []
            reservation_invalid = False
            for row in reservation_rows:
                try:
                    amount = decimal_from(
                        row["reserved_cost_usd"], label="Operational reservation",
                    )
                except ValueError:
                    reservation_invalid = True
                    break
                if (
                    not amount.is_finite()
                    or amount <= 0
                    or row["budget_reserved_at"] is None
                    or str(row["status"]) not in allowed_reservation_statuses
                ):
                    reservation_invalid = True
                    break
                reservation_values.append(amount)
            if reservation_invalid:
                unknown_reasons.append("active cost reservation data is malformed")
                active_reservations = OperationalScalar(
                    status=OperationalFieldStatus.UNKNOWN,
                    detail="Reservation amount, timestamp, or lifecycle is inconsistent.",
                )
                active_reserved_cost = OperationalScalar(
                    status=OperationalFieldStatus.UNKNOWN,
                    detail="Reservation total is not trustworthy.",
                )
            else:
                total = sum_usd(
                    reservation_values, label="Operational active reservations",
                )
                active_reservations = OperationalScalar(
                    status=OperationalFieldStatus.OK,
                    value=len(reservation_values),
                )
                active_reserved_cost = OperationalScalar(
                    status=OperationalFieldStatus.OK,
                    value=f"{total:.6f}",
                )

        if "provider_attempts" not in tables:
            needs_reconciliation = OperationalScalar(
                status=OperationalFieldStatus.UNKNOWN,
                detail="provider_attempts table is unavailable before migration 0010.",
            )
            unknown_reasons.append("provider reconciliation data is unavailable")
        else:
            count = self.conn.execute(
                "SELECT COUNT(*) AS count FROM provider_attempts "
                "WHERE status='NEEDS_RECONCILIATION'"
            ).fetchone()["count"]
            needs_reconciliation = OperationalScalar(
                status=OperationalFieldStatus.OK, value=int(count),
            )

        flag_states: dict[str, OperationalFlagState] = {}
        for key, fail_closed_value in SECURITY_FLAG_DEFAULTS.items():
            if "system_flags" not in tables:
                flag_states[key] = OperationalFlagState(
                    key=key,
                    status=OperationalFieldStatus.UNKNOWN,
                    effective_fail_closed_value=fail_closed_value,
                    detail="system_flags table is missing; effective value is fail-closed.",
                )
                unknown_reasons.append(f"system flag {key} is unavailable")
                continue
            flag = self.get_system_flag(key)
            if flag is None or not flag.is_valid:
                flag_states[key] = OperationalFlagState(
                    key=key,
                    status=OperationalFieldStatus.UNKNOWN,
                    effective_fail_closed_value=fail_closed_value,
                    detail="missing or malformed; effective value is fail-closed.",
                )
                unknown_reasons.append(f"system flag {key} is missing or malformed")
            else:
                flag_states[key] = OperationalFlagState(
                    key=key,
                    status=OperationalFieldStatus.OK,
                    value=flag.value,
                    effective_fail_closed_value=fail_closed_value,
                )

        # MaintenanceRunner currently persists effects, not a cycle timestamp.
        # The report must not invent one from job.updated_at or return zero.
        last_maintenance = OperationalScalar(
            status=OperationalFieldStatus.UNKNOWN,
            detail="No durable maintenance-cycle timestamp exists in schema 0014.",
        )
        unknown_reasons.append("last maintenance-cycle timestamp is not persisted")

        return OperationalReport(
            schema_migrations=schema_migrations,
            job_counts=job_counts,
            job_counts_status=job_counts_status,
            active_leases=active_leases,
            needs_verification_jobs=needs_verification,
            needs_reconciliation_attempts=needs_reconciliation,
            active_reservations=active_reservations,
            active_reserved_cost_usd=active_reserved_cost,
            system_flags=flag_states,
            last_maintenance_at=last_maintenance,
            unknown_reasons=unknown_reasons,
        )

    def get_system_flag(self, key: str) -> SystemFlag | None:
        """Reads SQLite on every call; safety flags fail closed when absent or malformed."""
        row = self.conn.execute("SELECT * FROM system_flags WHERE key=?", (key,)).fetchone()
        if row is None:
            if key not in SECURITY_FLAG_DEFAULTS:
                return None
            return SystemFlag(key=key, value=SECURITY_FLAG_DEFAULTS[key], is_valid=False)
        try:
            value = json.loads(row["value_json"])
            if not isinstance(value, bool):
                raise ValueError("safety flag must contain a JSON boolean")
        except (TypeError, ValueError, json.JSONDecodeError):
            if key not in SECURITY_FLAG_DEFAULTS:
                raise SystemFlagError(f"System flag {key!r} has malformed JSON.")
            return SystemFlag(
                key=key, value=SECURITY_FLAG_DEFAULTS[key], updated_at=row["updated_at"],
                updated_by=row["updated_by"], reason=row["reason"], is_valid=False,
            )
        return SystemFlag(
            key=key, value=value, updated_at=row["updated_at"], updated_by=row["updated_by"],
            reason=row["reason"], is_valid=True,
        )

    def set_system_flag(
        self, key: str, value: bool, *, updated_by: str | None = None,
        reason: str | None = None, now: datetime | None = None,
    ) -> SystemFlag:
        if not key.strip() or not isinstance(value, bool):
            raise SystemFlagError("System flag key must be non-empty and value must be boolean.")
        if key in SECURITY_FLAG_DEFAULTS and value != SECURITY_FLAG_DEFAULTS[key]:
            raise SystemFlagError(
                "A single system-flag setter may only move a security flag fail-closed; "
                "opening requires apply_security_flag_profile with all five flags."
            )
        current_ts = _persisted_ts(self._job_now(now))
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "INSERT INTO system_flags(key,value_json,updated_at,updated_by,reason) VALUES (?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_at=excluded.updated_at, updated_by=excluded.updated_by, reason=excluded.reason",
                (key, json.dumps(value), current_ts, updated_by, reason),
            )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        flag = self.get_system_flag(key)
        assert flag is not None
        return flag

    def apply_security_flag_profile(
        self, ordered_updates: list[tuple[str, bool]], *,
        updated_by: str | None = None, reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, bool]:
        """Set a full security-flag profile atomically, in the caller's order.

        One ``BEGIN IMMEDIATE`` covers every write, so a crash cannot leave the
        profile half-applied within this call.  The order is honoured only for the
        durable write sequence; on success every listed flag is committed together.
        """
        if len(ordered_updates) != len(SECURITY_FLAG_DEFAULTS):
            raise SystemFlagError("Security flag profile requires all five flags.")
        seen: set[str] = set()
        for key, value in ordered_updates:
            if not isinstance(key, str) or not key.strip():
                raise SystemFlagError("Security flag key must be a non-empty string.")
            if key not in SECURITY_FLAG_DEFAULTS:
                raise SystemFlagError(f"Unknown security flag {key!r}; refusing to write.")
            if not isinstance(value, bool):
                raise SystemFlagError(f"Security flag {key!r} value must be boolean.")
            if key in seen:
                raise SystemFlagError(f"Security flag {key!r} appears twice in the profile.")
            seen.add(key)
        if seen != set(SECURITY_FLAG_DEFAULTS):
            raise SystemFlagError(
                "Security flag profile must contain exactly the canonical five flags."
            )
        profile = dict(ordered_updates)
        kill_index = next(
            index for index, (key, _value) in enumerate(ordered_updates)
            if key == "kill_switch"
        )
        if profile["kill_switch"] is True and kill_index != 0:
            raise SystemFlagError(
                "Closing profile must write kill_switch first."
            )
        if profile["kill_switch"] is False and kill_index != len(ordered_updates) - 1:
            raise SystemFlagError(
                "Opening profile must write kill_switch last."
            )
        current_ts = _persisted_ts(self._job_now(now))
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            for key, value in ordered_updates:
                self.conn.execute(
                    "INSERT INTO system_flags(key,value_json,updated_at,updated_by,reason) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                    "value_json=excluded.value_json, updated_at=excluded.updated_at, "
                    "updated_by=excluded.updated_by, reason=excluded.reason",
                    (key, json.dumps(value), current_ts, updated_by, reason),
                )
            self.conn.commit()
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        return {key: value for key, value in ordered_updates}

    # --- research cards + źródła ---
    def add_research_card(self, card: ResearchCard) -> ResearchCard:
        cur = self.conn.execute(
            "INSERT INTO research_cards (topic_id, question, thesis, working_thesis,"
            " mechanism, facts_json, confirmed_claims, uncertain_claims, contradictions,"
            " counterargument, citable_numbers, visual_idea, confidence, source_quality_score,"
            " publication_recommendation, rejection_reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                card.topic_id, card.question, card.working_thesis, card.working_thesis,
                card.main_mechanism,
                json.dumps({"confirmed": card.confirmed_claims,
                            "uncertain": card.uncertain_claims}),
                json.dumps(card.confirmed_claims), json.dumps(card.uncertain_claims),
                json.dumps(card.contradictions), card.strongest_counterargument,
                json.dumps(card.citable_numbers), card.visual_idea, card.confidence_score,
                card.source_quality_score, card.publication_recommendation.value,
                card.rejection_reason, _ts(card.created_at),
            ),
        )
        self.conn.commit()
        card.id = int(cur.lastrowid)
        for src in card.sources:
            src.research_card_id = card.id
            self.add_source(src)
        return card

    def add_source(self, source: Source) -> Source:
        cur = self.conn.execute(
            "INSERT INTO sources (research_card_id, url, title, author_or_org, published_at,"
            " source_type, supports_claim, verified, verification_status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                source.research_card_id, source.url, source.title, source.author_or_org,
                source.published_at, source.source_type.value, source.supports_claim,
                int(source.verification_status == SourceVerification.VERIFIED),
                source.verification_status.value,
            ),
        )
        self.conn.commit()
        source.id = int(cur.lastrowid)
        return source

    @staticmethod
    def _same_card_payload(left: ResearchCard, right: ResearchCard) -> bool:
        """Compare card payloads; final-source order is not domain identity."""
        def source_payload(source: Source) -> tuple[object, ...]:
            return (
                source.url, source.title, source.author_or_org, source.published_at,
                source.source_type.value, source.supports_claim,
                source.verification_status.value,
            )

        return (
            left.topic_id == right.topic_id
            and left.question == right.question
            and left.working_thesis == right.working_thesis
            and left.main_mechanism == right.main_mechanism
            and left.confirmed_claims == right.confirmed_claims
            and left.uncertain_claims == right.uncertain_claims
            and left.contradictions == right.contradictions
            and left.strongest_counterargument == right.strongest_counterargument
            and left.citable_numbers == right.citable_numbers
            and left.visual_idea == right.visual_idea
            and left.confidence_score == right.confidence_score
            and left.source_quality_score == right.source_quality_score
            and left.publication_recommendation == right.publication_recommendation
            and left.rejection_reason == right.rejection_reason
            # The source collection is a multiset for idempotency. `repr` keeps
            # mixed optional SQLite values comparable while preserving every
            # field, so reordering is a no-op but a changed source is not.
            and sorted((source_payload(source) for source in left.sources), key=repr)
            == sorted((source_payload(source) for source in right.sources), key=repr)
        )

    @staticmethod
    def _is_force_finalization_mode(mode: StagedFinalizationMode) -> bool:
        return mode in {
            StagedFinalizationMode.FORCE_RERESEARCH,
            StagedFinalizationMode.FORCE_RERESEARCH_RESUME_B,
        }

    @staticmethod
    def _is_resume_finalization_mode(mode: StagedFinalizationMode) -> bool:
        return mode in {
            StagedFinalizationMode.RESUME_B,
            StagedFinalizationMode.FORCE_RERESEARCH_RESUME_B,
        }

    def _staged_finalization_row(self, research_run_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT rr.account_id AS research_account_id, rr.topic_id, rr.flow,"
            " rr.status AS research_status, rr.research_card_id AS stored_card_id,"
            " rr.total_cost_usd AS research_cost, rr.stage_b_completed_at,"
            " rr.error AS research_error, rr.is_force_reresearch,"
            " r.account_id AS run_account_id, r.workflow, r.status AS run_status,"
            " r.cost_usd AS run_cost, r.error AS run_error, r.finished_at,"
            " t.account_id AS topic_account_id, t.status AS topic_status "
            "FROM research_runs rr JOIN runs r ON r.id=rr.id "
            "JOIN topics t ON t.id=rr.topic_id WHERE rr.id=?",
            (research_run_id,),
        ).fetchone()

    def _require_staged_finalization_relation(
        self, row: sqlite3.Row | None, research_run_id: str,
    ) -> sqlite3.Row:
        if row is None or row["workflow"] != WorkflowType.RESEARCH.value or \
                row["research_account_id"] != row["run_account_id"] or \
                row["research_account_id"] != row["topic_account_id"] or \
                row["flow"] != ResearchFlow.STAGED.value:
            raise ResearchTopicIntegrityError(
                f"Invalid run/research_run/topic relation for {research_run_id}."
            )
        return row

    def _validate_staged_finalization_context(
        self,
        row: sqlite3.Row,
        research_run_id: str,
        terminal_run_status: RunStatus,
        context: StagedFinalizationContext,
        *,
        expected_persisted_research_status: ResearchRunStatus,
        terminal_repeat: bool = False,
    ) -> bool:
        """Validate a typed mode against durable lifecycle state without mutation.

        COMPLETE is not a bypass for the typed execution contract. A terminal
        repeat validates the same mode marker and, for resume, the durable
        FAILED/CAS audit trail before payload idempotency can return a no-op.
        """
        if context.expected_research_status != ResearchRunStatus.SOURCES_COMPLETE:
            raise ResearchTopicIntegrityError(
                f"Finalization context {research_run_id} lacks SOURCES_COMPLETE snapshot."
            )
        if row["research_status"] != expected_persisted_research_status.value:
            raise ResearchTopicIntegrityError(
                f"research_run {research_run_id} is not in "
                f"{expected_persisted_research_status.value}."
            )

        is_force = self._is_force_finalization_mode(context.mode)
        is_resume = self._is_resume_finalization_mode(context.mode)
        if bool(row["is_force_reresearch"]) != is_force:
            raise ResearchTopicIntegrityError(
                f"Finalization mode {context.mode.value} conflicts with durable force marker "
                f"for {research_run_id}."
            )
        if terminal_repeat:
            allowed_topics = {TopicStatus.USED.value}
        else:
            allowed_topics = (
                {TopicStatus.SELECTED.value, TopicStatus.USED.value}
                if is_force else {TopicStatus.SELECTED.value}
            )
        if row["topic_status"] not in allowed_topics:
            raise ResearchTopicIntegrityError(
                f"Topic for {research_run_id} violates {context.mode.value} preconditions."
            )

        if is_resume:
            if context.expected_run_status != RunStatus.FAILED or \
                    context.expected_finished_at is None or not context.expected_failure_marker:
                raise ResearchTopicIntegrityError(
                    f"Resume B {research_run_id} requires a complete FAILED/CAS snapshot."
                )
            expected_finished = _persisted_ts(context.expected_finished_at)
            if row["research_error"] != context.expected_failure_marker:
                raise ResearchTopicIntegrityError(
                    f"FAILED/CAS snapshot for resume B {research_run_id} no longer matches SQLite."
                )
            failed_b = self.conn.execute(
                "SELECT 1 FROM research_stage_results WHERE research_run_id=? AND stage=? "
                "AND status=? AND error=? AND finished_at=? LIMIT 1",
                (
                    research_run_id, ResearchStageName.B.value,
                    ResearchStageStatus.FAILED.value, context.expected_failure_marker,
                    expected_finished,
                ),
            ).fetchone()
            if failed_b is None:
                raise ResearchTopicIntegrityError(
                    f"FAILED/CAS snapshot for resume B {research_run_id} lacks a matching "
                    "durable earlier B FAILED entry."
                )
            if not terminal_repeat and (
                row["run_status"] != RunStatus.FAILED.value or
                row["finished_at"] != expected_finished or
                row["run_error"] != context.expected_failure_marker
            ):
                raise ResearchTopicIntegrityError(
                    f"FAILED/CAS snapshot for resume B {research_run_id} no longer matches SQLite."
                )
        else:
            if context.expected_run_status not in (RunStatus.RUNNING, RunStatus.DRY_RUN) or \
                    context.expected_finished_at is not None or \
                    context.expected_failure_marker is not None:
                raise ResearchTopicIntegrityError(
                    f"Fresh staged B context {research_run_id} does not match run status."
                )
            if terminal_repeat:
                has_failed_b = self.conn.execute(
                    "SELECT 1 FROM research_stage_results WHERE research_run_id=? AND stage=? "
                    "AND status=? LIMIT 1",
                    (research_run_id, ResearchStageName.B.value, ResearchStageStatus.FAILED.value),
                ).fetchone() is not None
                if row["research_error"] is not None or has_failed_b:
                    raise ResearchTopicIntegrityError(
                        f"Fresh finalization mode for {research_run_id} conflicts with resume history."
                    )
            elif row["run_status"] != context.expected_run_status.value or \
                    row["finished_at"] is not None or row["run_error"] is not None:
                raise ResearchTopicIntegrityError(
                    f"Fresh staged B context {research_run_id} does not match run status."
                )
        return is_force

    def preflight_staged_finalization(
        self,
        research_run_id: str,
        *,
        terminal_run_status: RunStatus,
        context: StagedFinalizationContext,
    ) -> None:
        """Fail closed before a paid B call; this method makes no mutation."""
        if terminal_run_status not in (RunStatus.SUCCESS, RunStatus.DRY_RUN):
            raise ValueError("Staged B finalization requires SUCCESS or DRY_RUN.")
        row = self._require_staged_finalization_relation(
            self._staged_finalization_row(research_run_id), research_run_id,
        )
        is_force = self._validate_staged_finalization_context(
            row, research_run_id, terminal_run_status, context,
            expected_persisted_research_status=ResearchRunStatus.SOURCES_COMPLETE,
        )
        if row["stored_card_id"] is not None:
            raise ResearchTopicIntegrityError(
                f"research_run {research_run_id} already has a research_card_id before B."
            )
        if self.conn.execute(
            "SELECT 1 FROM research_stage_results WHERE research_run_id=? AND stage=? AND status=?",
            (research_run_id, ResearchStageName.B.value, ResearchStageStatus.SUCCESS.value),
        ).fetchone() is not None:
            raise ResearchTopicIntegrityError(
                f"research_run {research_run_id} already has B SUCCESS without COMPLETE."
            )
        existing_complete = self.conn.execute(
            "SELECT 1 FROM research_runs WHERE topic_id=? AND status=? LIMIT 1",
            (row["topic_id"], ResearchRunStatus.COMPLETE.value),
        ).fetchone()
        if existing_complete is not None and not is_force:
            raise ResearchTopicIntegrityError(
                f"Topic #{row['topic_id']} already has a complete research_run."
            )

    def _finalization_fault_point(
        self, point: StagedFinalizationFaultPoint, source_index: int | None = None,
    ) -> None:
        """No-op production hook; tests inject one deterministic transaction failure."""

    def _insert_finalization_card(self, card: ResearchCard) -> None:
        """Wstawia kartę bez commita; używane wyłącznie przez atomową finalizację B."""
        cur = self.conn.execute(
            "INSERT INTO research_cards (topic_id, question, thesis, working_thesis,"
            " mechanism, facts_json, confirmed_claims, uncertain_claims, contradictions,"
            " counterargument, citable_numbers, visual_idea, confidence, source_quality_score,"
            " publication_recommendation, rejection_reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                card.topic_id, card.question, card.working_thesis, card.working_thesis,
                card.main_mechanism,
                json.dumps({"confirmed": card.confirmed_claims,
                            "uncertain": card.uncertain_claims}),
                json.dumps(card.confirmed_claims), json.dumps(card.uncertain_claims),
                json.dumps(card.contradictions), card.strongest_counterargument,
                json.dumps(card.citable_numbers), card.visual_idea, card.confidence_score,
                card.source_quality_score, card.publication_recommendation.value,
                card.rejection_reason, _ts(card.created_at),
            ),
        )
        if cur.rowcount != 1:
            raise ResearchTopicIntegrityError(
                "Worker finalization must insert exactly one research card."
            )
        if cur.lastrowid is None:
            raise ResearchTopicIntegrityError(
                "Worker finalization card insert did not return its row id."
            )
        card.id = int(cur.lastrowid)

    def _insert_finalization_source(self, source: Source) -> None:
        """Wstawia źródło bez commita; osobny hook ułatwia test rollbacku."""
        cur = self.conn.execute(
            "INSERT INTO sources (research_card_id, url, title, author_or_org, published_at,"
            " source_type, supports_claim, verified, verification_status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                source.research_card_id, source.url, source.title, source.author_or_org,
                source.published_at, source.source_type.value, source.supports_claim,
                int(source.verification_status == SourceVerification.VERIFIED),
                source.verification_status.value,
            ),
        )
        if cur.rowcount != 1:
            raise ResearchTopicIntegrityError(
                "Worker finalization must insert exactly one source per source record."
            )
        if cur.lastrowid is None:
            raise ResearchTopicIntegrityError(
                "Worker finalization source insert did not return its row id."
            )
        source.id = int(cur.lastrowid)

    def _insert_finalization_stage_b_success(self, research_run_id: str) -> None:
        self.conn.execute(
            "INSERT INTO research_stage_results (research_run_id, stage, status,"
            " finished_at, error) VALUES (?,?,?,?,NULL)",
            (research_run_id, ResearchStageName.B.value, ResearchStageStatus.SUCCESS.value, _ts()),
        )

    def finalize_staged_research_with_card(
        self, research_run_id: str, card: ResearchCard, total_cost_usd: float,
        *, terminal_run_status: RunStatus, min_sources: int, min_verified_sources: int,
        context: StagedFinalizationContext,
    ) -> ResearchCard:
        """Atomowo utrwala sukces B staged, kartę, źródła i cały lifecycle.

        To jest jedyna ścieżka sukcesu staged B. Karta nie może istnieć przed
        wywołaniem helpera: rollback po każdym błędzie usuwa także częściowo
        wstawioną kartę, jej źródła i wpis SUCCESS etapu B.
        """
        if terminal_run_status not in (RunStatus.SUCCESS, RunStatus.DRY_RUN):
            raise ValueError("Finalizacja staged B wymaga statusu SUCCESS albo DRY_RUN.")
        if min_sources < 1 or min_verified_sources < 0:
            raise ValueError("Minimalna liczba źródeł musi być dodatnia, a VERIFIED nieujemna.")

        original_card_id = card.id
        original_sources = [(source.id, source.research_card_id) for source in card.sources]
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._require_staged_finalization_relation(
                self._staged_finalization_row(research_run_id), research_run_id,
            )
            terminal_repeat = row["research_status"] == ResearchRunStatus.COMPLETE.value
            if terminal_repeat:
                self._validate_staged_finalization_context(
                    row, research_run_id, terminal_run_status, context,
                    expected_persisted_research_status=ResearchRunStatus.COMPLETE,
                    terminal_repeat=True,
                )

            canonical_cost = self._research_usage_total(research_run_id)
            if canonical_cost != _money(
                    total_cost_usd, positive=False, label="Staged research finalization cost"):
                raise ResearchTopicIntegrityError(
                    f"Koszt finalizacji {total_cost_usd} nie jest kanoniczną sumą usage "
                    f"{canonical_cost} dla {research_run_id}."
                )

            stage_successes = int(self.conn.execute(
                "SELECT COUNT(*) FROM research_stage_results "
                "WHERE research_run_id=? AND stage=? AND status=?",
                (research_run_id, ResearchStageName.B.value, ResearchStageStatus.SUCCESS.value),
            ).fetchone()[0])

            if terminal_repeat:
                persisted = self.get_research_card(int(row["stored_card_id"])) \
                    if row["stored_card_id"] is not None else None
                identical = (
                    persisted is not None
                    and self._same_card_payload(persisted, card)
                    and _money_equal(
                        row["research_cost"], canonical_cost,
                        label="Repeated staged research cost",
                    )
                    and row["run_status"] == terminal_run_status.value
                    and _money_equal(
                        row["run_cost"], canonical_cost,
                        label="Repeated staged run cost",
                    )
                    and row["run_error"] is None
                    and row["finished_at"] is not None
                    and row["stage_b_completed_at"] is not None
                    and row["topic_status"] == TopicStatus.USED.value
                    and stage_successes == 1
                )
                if not identical:
                    raise ResearchTopicIntegrityError(
                        f"Sprzeczna ponowna finalizacja staged B {research_run_id}."
                    )
                self.conn.rollback()
                return persisted

            is_force_mode = self._validate_staged_finalization_context(
                row, research_run_id, terminal_run_status, context,
                expected_persisted_research_status=ResearchRunStatus.SYNTHESIS_PENDING,
            )
            is_resume_mode = self._is_resume_finalization_mode(context.mode)
            allowed_topic_statuses = (
                {TopicStatus.SELECTED.value, TopicStatus.USED.value}
                if is_force_mode else {TopicStatus.SELECTED.value}
            )
            if row["research_status"] != ResearchRunStatus.SYNTHESIS_PENDING.value or \
                    row["stored_card_id"] is not None or \
                    row["topic_status"] not in allowed_topic_statuses:
                raise ResearchTopicIntegrityError(
                    f"research_run {research_run_id} nie spełnia preconditions finalizacji staged B."
                )
            allowed_run_statuses = (
                {RunStatus.FAILED.value}
                if is_resume_mode else {context.expected_run_status.value}
            )
            if row["run_status"] not in allowed_run_statuses:
                raise ResearchTopicIntegrityError(
                    f"run {research_run_id} nie może przejść z {row['run_status']} "
                    f"do {terminal_run_status.value}."
                )
            if card.id is not None or card.topic_id != row["topic_id"]:
                raise ResearchTopicIntegrityError(
                    f"Karta staged B dla {research_run_id} musi być nowa i należeć do jego tematu."
                )
            existing_complete = self.conn.execute(
                "SELECT 1 FROM research_runs WHERE topic_id=? AND status=? LIMIT 1",
                (row["topic_id"], ResearchRunStatus.COMPLETE.value),
            ).fetchone()
            if existing_complete is not None and not is_force_mode:
                raise ResearchTopicIntegrityError(
                    f"Temat #{row['topic_id']} ma już kompletny research_run."
                )
            if stage_successes:
                raise ResearchTopicIntegrityError(
                    f"research_run {research_run_id} ma już sukces etapu B bez COMPLETE."
                )

            candidates = self.conn.execute(
                "SELECT url, verification_status FROM research_source_candidates "
                "WHERE research_run_id=? AND status=?",
                (research_run_id, SourceCandidateStatus.EXTRACTED.value),
            ).fetchall()
            candidate_verification = {candidate["url"]: candidate["verification_status"]
                                      for candidate in candidates}
            verified_sources = 0
            for source in card.sources:
                stored_verification = candidate_verification.get(source.url)
                if stored_verification is None or stored_verification != source.verification_status.value:
                    raise ResearchTopicIntegrityError(
                        f"Źródło {source.url} nie jest zgodną kartą A2 runu {research_run_id}."
                    )
                verified_sources += int(source.verification_status == SourceVerification.VERIFIED)
            if len(card.sources) < min_sources or len(card.sources) > len(candidates) or \
                    len({source.url for source in card.sources}) != len(card.sources) or \
                    verified_sources < min_verified_sources:
                raise ResearchTopicIntegrityError(
                    f"Karta staged B {research_run_id} nie spełnia wymaganego minimum źródeł VERIFIED."
                )

            self._finalization_fault_point(StagedFinalizationFaultPoint.BEFORE_CARD_INSERT)
            self._insert_finalization_card(card)
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_CARD_INSERT)
            for source_index, source in enumerate(card.sources):
                self._finalization_fault_point(
                    StagedFinalizationFaultPoint.BEFORE_SOURCE_INSERT, source_index,
                )
                source.research_card_id = card.id
                self._insert_finalization_source(source)
                if source_index == 0:
                    self._finalization_fault_point(
                        StagedFinalizationFaultPoint.AFTER_FIRST_SOURCE_INSERT,
                    )
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_ALL_SOURCE_INSERTS)
            self._finalization_fault_point(StagedFinalizationFaultPoint.BEFORE_STAGE_B_SUCCESS_INSERT)
            self._insert_finalization_stage_b_success(research_run_id)
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_STAGE_B_SUCCESS_INSERT)

            self._finalization_fault_point(StagedFinalizationFaultPoint.BEFORE_RESEARCH_RUN_UPDATE)
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, stage_b_completed_at=?, research_card_id=?,"
                " total_cost_usd=?, updated_at=? WHERE id=? AND account_id=? AND topic_id=?"
                " AND flow=? AND status=? AND research_card_id IS NULL",
                (ResearchRunStatus.COMPLETE.value, _ts(), card.id, float(canonical_cost), _ts(),
                 research_run_id, row["research_account_id"], row["topic_id"],
                 ResearchFlow.STAGED.value, ResearchRunStatus.SYNTHESIS_PENDING.value),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano research_run {research_run_id}.")
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_RESEARCH_RUN_UPDATE)
            self._finalization_fault_point(StagedFinalizationFaultPoint.BEFORE_RUN_UPDATE)
            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=NULL, finished_at=? "
                "WHERE id=? AND account_id=? AND workflow=? AND status=?",
                (terminal_run_status.value, float(canonical_cost), _ts(), research_run_id,
                 row["research_account_id"], WorkflowType.RESEARCH.value, row["run_status"]),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano run {research_run_id}.")
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_RUN_UPDATE)
            self._finalization_fault_point(StagedFinalizationFaultPoint.BEFORE_TOPIC_USED_UPDATE)
            cursor = self.conn.execute(
                "UPDATE topics SET status=? WHERE id=? AND account_id=? AND status IN (?,?)",
                (TopicStatus.USED.value, row["topic_id"], row["research_account_id"],
                 TopicStatus.SELECTED.value, TopicStatus.USED.value),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano topic #{row['topic_id']}.")
            self._finalization_fault_point(StagedFinalizationFaultPoint.AFTER_TOPIC_USED_UPDATE)
            self.conn.commit()
            return card
        except Exception:
            self.conn.rollback()
            card.id = original_card_id
            for source, (source_id, research_card_id) in zip(card.sources, original_sources):
                source.id = source_id
                source.research_card_id = research_card_id
            raise

    def get_research_card(self, card_id: int) -> ResearchCard | None:
        r = self.conn.execute(
            "SELECT * FROM research_cards WHERE id=?", (card_id,)
        ).fetchone()
        if r is None:
            return None
        sources = self._sources_for_card(card_id)
        return ResearchCard(
            id=r["id"], topic_id=r["topic_id"], question=r["question"],
            working_thesis=r["working_thesis"] or r["thesis"],
            main_mechanism=r["mechanism"],
            confirmed_claims=json.loads(r["confirmed_claims"] or "[]"),
            uncertain_claims=json.loads(r["uncertain_claims"] or "[]"),
            contradictions=json.loads(r["contradictions"] or "[]"),
            strongest_counterargument=r["counterargument"],
            citable_numbers=json.loads(r["citable_numbers"] or "[]"),
            visual_idea=r["visual_idea"], confidence_score=r["confidence"],
            source_quality_score=r["source_quality_score"],
            publication_recommendation=ResearchRecommendation(
                r["publication_recommendation"] or "REJECT"),
            rejection_reason=r["rejection_reason"], sources=sources,
        )

    def _sources_for_card(self, card_id: int) -> list[Source]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE research_card_id=? ORDER BY id ASC", (card_id,)
        ).fetchall()
        return [
            Source(
                id=r["id"], research_card_id=r["research_card_id"], url=r["url"],
                title=r["title"], author_or_org=r["author_or_org"],
                published_at=r["published_at"], source_type=SourceType(r["source_type"]),
                supports_claim=r["supports_claim"],
                verification_status=SourceVerification(
                    r["verification_status"] or "UNVERIFIED"),
            )
            for r in rows
        ]

    def list_research_cards(self, account_id: str) -> list[ResearchCard]:
        """Research cards konta (przez join topics) — izolacja po account_id."""
        rows = self.conn.execute(
            "SELECT rc.id FROM research_cards rc JOIN topics t ON t.id = rc.topic_id"
            " WHERE t.account_id=? ORDER BY rc.id ASC",
            (account_id,),
        ).fetchall()
        return [self.get_research_card(r["id"]) for r in rows]

    # --- wznawialny dwuetapowy research (research_runs / research_sources / stage log) ---

    def create_research_run(self, research_run: ResearchRun) -> ResearchRun:
        """`research_run.id` musi być TYM SAMYM id co odpowiadający `Run` (rozszerzenie 1:1) —
       wołający tworzy najpierw `create_run(...)`, potem to, z tym samym id."""
        canonical_cost = _money(
            research_run.total_cost_usd,
            positive=False,
            label="Initial research run cost",
        )
        self.conn.execute(
            "INSERT INTO research_runs (id, account_id, topic_id, flow, status,"
            " is_force_reresearch, total_cost_usd, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                research_run.id, research_run.account_id, research_run.topic_id,
                research_run.flow.value, research_run.status.value,
                int(research_run.is_force_reresearch), float(canonical_cost),
                _ts(research_run.created_at), _ts(research_run.updated_at),
            ),
        )
        self.conn.commit()
        research_run.total_cost_usd = float(canonical_cost)
        return research_run

    def get_research_run(self, research_run_id: str) -> ResearchRun | None:
        r = self.conn.execute(
            "SELECT * FROM research_runs WHERE id=?", (research_run_id,)
        ).fetchone()
        if r is None:
            return None
        return self._research_run_from_row(r)

    @staticmethod
    def _research_run_from_row(r: sqlite3.Row) -> ResearchRun:
        return ResearchRun(
            id=r["id"], account_id=r["account_id"], topic_id=r["topic_id"],
            flow=ResearchFlow(r["flow"]),
            status=ResearchRunStatus(r["status"]),
            stage_a_completed_at=r["stage_a_completed_at"],
            stage_b_completed_at=r["stage_b_completed_at"],
            research_card_id=r["research_card_id"],
            is_force_reresearch=bool(r["is_force_reresearch"]),
            total_cost_usd=r["total_cost_usd"], error=r["error"],
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def has_valid_completed_research_card_for_topic(self, account_id: str, topic_id: int) -> bool:
        """Sprawdza poprawną relację COMPLETE runu, karty i tematu.

        `USED` bez takiej relacji oraz COMPLETE z błędną kartą są stanem uszkodzonym.
        Zatrzymujemy świeży research fail-closed, również gdy wywołujący poda force.
        """
        topic = self.conn.execute(
            "SELECT status FROM topics WHERE id=? AND account_id=?", (topic_id, account_id),
        ).fetchone()
        if topic is None:
            raise ResearchTopicIntegrityError(
                f"Temat #{topic_id} nie należy do konta {account_id} lub nie istnieje."
            )

        invalid_complete = self.conn.execute(
            "SELECT rr.id FROM research_runs rr "
            "LEFT JOIN runs r ON r.id=rr.id "
            "LEFT JOIN research_cards rc ON rc.id=rr.research_card_id "
            "LEFT JOIN topics card_topic ON card_topic.id=rc.topic_id "
            "WHERE rr.account_id=? AND rr.topic_id=? AND rr.status=? AND ("
            "rr.research_card_id IS NULL OR rc.id IS NULL OR rc.topic_id!=rr.topic_id "
            "OR card_topic.account_id!=rr.account_id OR r.id IS NULL "
            "OR r.account_id!=rr.account_id OR r.status NOT IN (?,?)) LIMIT 1",
            (account_id, topic_id, ResearchRunStatus.COMPLETE.value,
             RunStatus.SUCCESS.value, RunStatus.DRY_RUN.value),
        ).fetchone()
        if invalid_complete is not None:
            raise ResearchTopicIntegrityError(
                f"research_run {invalid_complete['id']} ma niepoprawną relację COMPLETE/karta/temat."
            )

        valid_complete = self.conn.execute(
            "SELECT 1 FROM research_runs rr "
            "JOIN runs r ON r.id=rr.id AND r.account_id=rr.account_id "
            "JOIN research_cards rc ON rc.id=rr.research_card_id AND rc.topic_id=rr.topic_id "
            "JOIN topics card_topic ON card_topic.id=rc.topic_id AND card_topic.account_id=rr.account_id "
            "WHERE rr.account_id=? AND rr.topic_id=? AND rr.status=? AND r.status IN (?,?) LIMIT 1",
            (account_id, topic_id, ResearchRunStatus.COMPLETE.value,
             RunStatus.SUCCESS.value, RunStatus.DRY_RUN.value),
        ).fetchone()
        if TopicStatus(topic["status"]) == TopicStatus.USED and valid_complete is None:
            raise ResearchTopicIntegrityError(
                f"Temat #{topic_id} ma status USED bez poprawnej kompletnej karty researchu."
            )
        return valid_complete is not None

    def finalize_research_success(
        self, research_run_id: str, research_card_id: int, total_cost_usd: float,
        *, stage_b_completed: bool, terminal_run_status: RunStatus,
    ) -> None:
        """Atomowo finalizuje legacy `single` albo `two_stage` z kartą zapisaną wcześniej.

        Karta może powstać przed finalizacją, ale żaden status sukcesu nie jest wtedy
        jeszcze zatwierdzany. W tej jednej transakcji są walidacja relacji, COMPLETE,
        terminalny status `runs` i `topics.USED`. Identyczne powtórzenie jest no-op;
        każde sprzeczne powtórzenie kończy się błędem integralności bez mutacji.
        Flow `staged` ma wyłączną granicę sukcesu w
        `finalize_staged_research_with_card`, aby karta, źródła, B SUCCESS, koszt i
        lifecycle nie mogły zostać rozdzielone przez publiczny legacy helper.
        """
        if terminal_run_status not in (RunStatus.SUCCESS, RunStatus.DRY_RUN):
            raise ValueError("Finalizacja sukcesu wymaga statusu SUCCESS albo DRY_RUN.")
        canonical_cost = _money(
            total_cost_usd,
            positive=False,
            label="Legacy research finalization cost",
        )
        self.conn.execute("BEGIN")
        try:
            row = self.conn.execute(
                "SELECT rr.account_id AS research_account_id, rr.topic_id, rr.flow, "
                "rr.status AS research_status, rr.research_card_id AS stored_card_id, "
                "rr.total_cost_usd AS research_cost, rr.error AS research_error, "
                "rr.stage_b_completed_at, rr.updated_at AS research_updated_at, "
                "r.account_id AS run_account_id, r.status AS run_status, "
                "r.cost_usd AS run_cost, r.error AS run_error, r.finished_at, "
                "t.account_id AS topic_account_id, rc.id AS card_id, "
                "t.status AS topic_status, rc.topic_id AS card_topic_id, "
                "card_topic.account_id AS card_account_id "
                "FROM research_runs rr "
                "JOIN runs r ON r.id=rr.id "
                "JOIN topics t ON t.id=rr.topic_id "
                "LEFT JOIN research_cards rc ON rc.id=? "
                "LEFT JOIN topics card_topic ON card_topic.id=rc.topic_id "
                "WHERE rr.id=?",
                (research_card_id, research_run_id),
            ).fetchone()
            if row is None:
                raise ResearchTopicIntegrityError(
                    f"Nie znaleziono pełnej relacji run/research_run/temat dla {research_run_id}."
                )
            if row["flow"] == ResearchFlow.STAGED.value:
                raise ResearchTopicIntegrityError(
                    "STAGED research must be finalized through "
                    "finalize_staged_research_with_card"
                )
            if row["card_id"] is None or row["card_topic_id"] != row["topic_id"] or \
                    row["research_account_id"] != row["run_account_id"] or \
                    row["research_account_id"] != row["topic_account_id"] or \
                    row["research_account_id"] != row["card_account_id"]:
                raise ResearchTopicIntegrityError(
                    f"Karta {research_card_id} nie należy do tematu i konta research_run {research_run_id}."
                )
            expected_stage_b = row["flow"] != ResearchFlow.SINGLE.value
            if stage_b_completed != expected_stage_b:
                raise ResearchTopicIntegrityError(
                    f"Niezgodna semantyka etapu B dla flow {row['flow']} w {research_run_id}."
                )

            if row["research_status"] == ResearchRunStatus.COMPLETE.value:
                identical = (
                    row["stored_card_id"] == research_card_id
                    and _money_equal(
                        row["research_cost"], canonical_cost,
                        label="Repeated legacy research cost",
                    )
                    and row["run_status"] == terminal_run_status.value
                    and _money_equal(
                        row["run_cost"], canonical_cost,
                        label="Repeated legacy run cost",
                    )
                    and row["run_error"] is None
                    and row["finished_at"] is not None
                    and row["topic_status"] == TopicStatus.USED.value
                    and ((row["stage_b_completed_at"] is not None) == stage_b_completed)
                )
                if not identical:
                    raise ResearchTopicIntegrityError(
                        f"Sprzeczna ponowna finalizacja research_run {research_run_id}."
                    )
                self.conn.rollback()
                return

            allowed_research_statuses = {
                ResearchFlow.SINGLE.value: {ResearchRunStatus.PENDING.value},
                ResearchFlow.TWO_STAGE.value: {
                    ResearchRunStatus.SOURCE_COLLECTED.value,
                    ResearchRunStatus.PARTIAL.value,
                },
            }
            if row["research_status"] not in allowed_research_statuses.get(row["flow"], set()):
                raise ResearchTopicIntegrityError(
                    f"research_run {research_run_id} nie może zostać sfinalizowany ze stanu "
                    f"{row['research_status']}."
                )
            if row["stored_card_id"] is not None:
                raise ResearchTopicIntegrityError(
                    f"research_run {research_run_id} ma kartę przed stanem COMPLETE."
                )
            allowed_source_statuses = (
                {RunStatus.DRY_RUN.value, RunStatus.RUNNING.value}
                if terminal_run_status == RunStatus.DRY_RUN
                else {RunStatus.RUNNING.value}
            )
            if row["flow"] == ResearchFlow.TWO_STAGE.value:
                # Jawne wznowienie etapu B może zaczynać z FAILED po wcześniejszej
                # próbie, ale nie powtarza zachowanych etapów A/A1/A2.
                allowed_source_statuses.add(RunStatus.FAILED.value)
            if row["run_status"] not in allowed_source_statuses:
                raise ResearchTopicIntegrityError(
                    f"run {research_run_id} nie może przejść z {row['run_status']} "
                    f"do {terminal_run_status.value}."
                )
            if row["topic_status"] not in (TopicStatus.SELECTED.value, TopicStatus.USED.value):
                raise ResearchTopicIntegrityError(
                    f"Temat #{row['topic_id']} nie może przejść do USED ze stanu "
                    f"{row['topic_status']}."
                )

            if stage_b_completed:
                cursor = self.conn.execute(
                    "UPDATE research_runs SET status=?, stage_b_completed_at=?, research_card_id=?,"
                    " total_cost_usd=?, updated_at=? WHERE id=? AND account_id=? AND topic_id=?"
                    " AND status IN (?) AND research_card_id IS NULL",
                    (ResearchRunStatus.COMPLETE.value, _ts(), research_card_id, float(canonical_cost),
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            else:
                cursor = self.conn.execute(
                    "UPDATE research_runs SET status=?, research_card_id=?, total_cost_usd=?,"
                    " updated_at=? WHERE id=? AND account_id=? AND topic_id=?"
                    " AND status IN (?) AND research_card_id IS NULL",
                    (ResearchRunStatus.COMPLETE.value, research_card_id, float(canonical_cost),
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano research_run {research_run_id}.")

            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? "
                "WHERE id=? AND account_id=? AND status IN (?)",
                (terminal_run_status.value, float(canonical_cost), None, _ts(), research_run_id,
                 row["research_account_id"], row["run_status"]),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano run {research_run_id}.")

            cursor = self.conn.execute(
                "UPDATE topics SET status=? WHERE id=? AND account_id=? AND status IN (?,?)",
                (TopicStatus.USED.value, row["topic_id"], row["research_account_id"],
                 TopicStatus.SELECTED.value, TopicStatus.USED.value),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(
                    f"Nie znaleziono tematu #{row['topic_id']} dla research_run {research_run_id}."
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_single_research_run_complete(
        self, research_run_id: str, research_card_id: int, total_cost_usd: float,
    ) -> None:
        """Kompatybilny alias kanonicznej atomowej finalizacji single flow."""
        self.finalize_research_success(
            research_run_id, research_card_id, total_cost_usd, stage_b_completed=False,
            terminal_run_status=self._terminal_status_for_finalization(research_run_id),
        )

    def _terminal_status_for_finalization(self, research_run_id: str) -> RunStatus:
        run = self.get_run(research_run_id)
        if run is None:
            raise ResearchTopicIntegrityError(f"Nie znaleziono run {research_run_id}.")
        return RunStatus.DRY_RUN if run.status == RunStatus.DRY_RUN else RunStatus.SUCCESS

    def add_research_sources(self, research_run_id: str,
                             sources: list[ResearchSourceRecord]) -> list[ResearchSourceRecord]:
        """Zapis samodzielny (commit na końcu) — do zasilania fixture'ów w testach.
        Realny pipeline używa `mark_research_stage_a_success` (atomowe ze zmianą statusu)."""
        for src in sources:
            self._insert_research_source(research_run_id, src)
        self.conn.commit()
        return sources

    def _insert_research_source(self, research_run_id: str, src: ResearchSourceRecord) -> None:
        cur = self.conn.execute(
            "INSERT INTO research_sources (research_run_id, url, title, author_or_org,"
            " published_at, source_type, key_facts_json, verification_status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                research_run_id, src.url, src.title, src.author_or_org, src.published_at,
                src.source_type.value, json.dumps(src.key_facts), src.verification_status.value,
            ),
        )
        src.id = int(cur.lastrowid)
        src.research_run_id = research_run_id

    def list_research_sources(self, research_run_id: str) -> list[ResearchSourceRecord]:
        rows = self.conn.execute(
            "SELECT * FROM research_sources WHERE research_run_id=? ORDER BY id ASC",
            (research_run_id,),
        ).fetchall()
        return [
            ResearchSourceRecord(
                id=r["id"], research_run_id=r["research_run_id"], url=r["url"],
                title=r["title"], author_or_org=r["author_or_org"],
                published_at=r["published_at"], source_type=SourceType(r["source_type"]),
                key_facts=json.loads(r["key_facts_json"] or "[]"),
                verification_status=SourceVerification(
                    r["verification_status"] or "UNVERIFIED"),
            )
            for r in rows
        ]

    def mark_research_stage_a_success(
        self, research_run_id: str, sources: list[ResearchSourceRecord],
    ) -> list[ResearchSourceRecord]:
        """Zapisuje źródła etapu A I zmienia status na SOURCE_COLLECTED w JEDNEJ
        transakcji (jeden commit) — unika stanu pośredniego (źródła zapisane, status
        wciąż PENDING), gdyby proces padł w trakcie. To jest sedno odporności:
        po tym wywołaniu wyniki wyszukiwania są trwałe, niezależnie od losu etapu B."""
        allowed = (f"{ResearchFlow.TWO_STAGE.value}:{ResearchRunStatus.PENDING.value}",)
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, stage_a_completed_at=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?)",
                (
                    ResearchRunStatus.SOURCE_COLLECTED.value, _ts(), _ts(), research_run_id,
                    ResearchFlow.TWO_STAGE.value, ResearchRunStatus.PENDING.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.SOURCE_COLLECTED.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            for src in sources:
                self._insert_research_source(research_run_id, src)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return sources

    def mark_research_run_failed(self, research_run_id: str, error: str) -> None:
        """Etap A się nie powiódł — nie ma czego wznawiać (brak trwałych źródeł)."""
        allowed = (
            f"{ResearchFlow.SINGLE.value}:{ResearchRunStatus.PENDING.value}",
            f"{ResearchFlow.TWO_STAGE.value}:{ResearchRunStatus.PENDING.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.DISCOVERY_PENDING.value}",
        )
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, error=?, updated_at=? WHERE id=? AND "
                "((flow IN (?, ?) AND status IN (?)) OR (flow=? AND status IN (?)))",
                (
                    ResearchRunStatus.FAILED.value, error, _ts(), research_run_id,
                    ResearchFlow.SINGLE.value, ResearchFlow.TWO_STAGE.value,
                    ResearchRunStatus.PENDING.value, ResearchFlow.STAGED.value,
                    ResearchRunStatus.DISCOVERY_PENDING.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id, target_status=ResearchRunStatus.FAILED.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_research_run_partial(self, research_run_id: str, error: str) -> None:
        """Etap A udany, etap B nieudany — źródła w research_sources zostają
        nietknięte; można ponowić WYŁĄCZNIE etap B, bez ponownego web search."""
        allowed = (
            f"{ResearchFlow.TWO_STAGE.value}:{ResearchRunStatus.SOURCE_COLLECTED.value}",
            f"{ResearchFlow.TWO_STAGE.value}:{ResearchRunStatus.PARTIAL.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.EXTRACTION_IN_PROGRESS.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.DISCOVERY_COMPLETE.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.PARTIAL.value}",
        )
        existing = self.conn.execute(
            "SELECT flow, status, error FROM research_runs WHERE id=?", (research_run_id,),
        ).fetchone()
        if (
            existing is not None
            and existing["status"] == ResearchRunStatus.PARTIAL.value
            and existing["error"] == error
            and f"{existing['flow']}:{existing['status']}" in allowed
        ):
            return
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, error=?, updated_at=? WHERE id=? AND "
                "((flow=? AND status IN (?, ?)) OR (flow=? AND status IN (?, ?, ?)))",
                (
                    ResearchRunStatus.PARTIAL.value, error, _ts(), research_run_id,
                    ResearchFlow.TWO_STAGE.value, ResearchRunStatus.SOURCE_COLLECTED.value,
                    ResearchRunStatus.PARTIAL.value, ResearchFlow.STAGED.value,
                    ResearchRunStatus.DISCOVERY_COMPLETE.value,
                    ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                    ResearchRunStatus.PARTIAL.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id, target_status=ResearchRunStatus.PARTIAL.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_research_run_complete(self, research_run_id: str, research_card_id: int,
                                   total_cost_usd: float) -> None:
        """Alias legacy `two_stage`; flow `staged` odrzuca delegowany finalizer."""
        self.finalize_research_success(
            research_run_id, research_card_id, total_cost_usd, stage_b_completed=True,
            terminal_run_status=self._terminal_status_for_finalization(research_run_id),
        )

    def add_research_stage_result(
        self, research_run_id: str, stage: ResearchStageName,
        status: ResearchStageStatus, error: str | None = None,
        *, finished_at: datetime | None = None,
    ) -> None:
        """Log KAŻDEJ próby etapu (audytowalność) — niezależny od research_runs.status,
        który trzyma tylko stan BIEŻĄCY."""
        if stage == ResearchStageName.B and status == ResearchStageStatus.SUCCESS:
            flow_row = self.conn.execute(
                "SELECT flow FROM research_runs WHERE id=?", (research_run_id,),
            ).fetchone()
            if flow_row is not None and flow_row["flow"] == ResearchFlow.STAGED.value:
                raise ResearchTopicIntegrityError(
                    "Staged B SUCCESS may only be written by the atomic finalization helper."
                )
        self.conn.execute(
            "INSERT INTO research_stage_results (research_run_id, stage, status,"
            " finished_at, error) VALUES (?,?,?,?,?)",
            (research_run_id, stage.value, status.value, _ts(finished_at), error),
        )
        self.conn.commit()

    def get_research_usage(self, research_run_id: str) -> list[ModelUsage]:
        """Zużycie/koszt WSZYSTKICH etapów researchu (stary dwuetapowy przepływ ORAZ
        nowy etapowy A1/A2/B). Celowo BRAK osobnej tabeli 'research_usage' — to wpisy
        model_usage dla tego run_id, dla dowolnego zadania researchowego."""
        rows = self.conn.execute(
            "SELECT * FROM model_usage WHERE run_id=? AND task IN"
            f" ({_RESEARCH_USAGE_PLACEHOLDERS}) ORDER BY id ASC",
            (research_run_id, *_RESEARCH_USAGE_TASKS),
        ).fetchall()
        return [
            ModelUsage(
                id=r["id"], run_id=r["run_id"], provider=r["provider"], model=r["model"],
                task=r["task"], input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"], cache_read_tokens=r["cache_read_tokens"],
                cache_write_tokens=r["cache_write_tokens"],
                web_search_requests=r["web_search_requests"],
                estimated_cost_usd=r["estimated_cost_usd"], dry_run=bool(r["dry_run"]),
                request_id=r["request_id"],
            )
            for r in rows
        ]

    def _set_run_cost_from_research_usage(self, research_run_id: str) -> None:
        """Ustawia cache runs.cost_usd z kanonicznych wpisów model_usage tego runu.

        Celowo nie filtruje dry_run: cache runu zachowuje koszt zapisany w
        model_usage, a budżet odróżnia realne użycie przez sum_real_cost_usd.
        """
        total = self._research_usage_total(research_run_id)
        cursor = self.conn.execute(
            "UPDATE runs SET cost_usd=? WHERE id=?",
            (float(total), research_run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Nie znaleziono run #{research_run_id} do synchronizacji kosztu.")

    def sync_run_cost_from_research_usage(self, research_run_id: str) -> float:
        """Idempotently repairs the cache from canonical research usage."""
        self.conn.execute("BEGIN")
        try:
            self._set_run_cost_from_research_usage(research_run_id)
            row = self.conn.execute(
                "SELECT cost_usd FROM runs WHERE id=?", (research_run_id,)
            ).fetchone()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return float(row["cost_usd"])

    # --- etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis) ---

    def create_source_candidates(
        self, research_run_id: str, candidates: list[SourceCandidateRecord],
    ) -> list[SourceCandidateRecord]:
        """Zapisuje kandydatów z etapu A1 I zmienia status na DISCOVERY_COMPLETE w
        JEDNEJ transakcji (jeden commit) — analogicznie do `mark_research_stage_a_success`
        dla starego przepływu. Unika stanu pośredniego (kandydaci zapisani, status
        wciąż DISCOVERY_PENDING), gdyby proces padł w trakcie."""
        allowed = (f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.DISCOVERY_PENDING.value}",)
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?)",
                (
                    ResearchRunStatus.DISCOVERY_COMPLETE.value, _ts(), research_run_id,
                    ResearchFlow.STAGED.value, ResearchRunStatus.DISCOVERY_PENDING.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.DISCOVERY_COMPLETE.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            cur = self.conn.cursor()
            for c in candidates:
                row = cur.execute(
                    "INSERT INTO research_source_candidates (research_run_id, url, title,"
                    " status) VALUES (?,?,?,?)",
                    (
                        research_run_id, c.url, c.title,
                        SourceCandidateStatus.PENDING_EXTRACTION.value,
                    ),
                )
                c.id = int(row.lastrowid)
                c.research_run_id = research_run_id
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return candidates

    def list_source_candidates(
        self, research_run_id: str, status: SourceCandidateStatus | None = None,
    ) -> list[SourceCandidateRecord]:
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM research_source_candidates WHERE research_run_id=?"
                " ORDER BY id ASC", (research_run_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM research_source_candidates WHERE research_run_id=?"
                " AND status=? ORDER BY id ASC", (research_run_id, status.value),
            ).fetchall()
        return [self._candidate_from_row(r) for r in rows]

    @staticmethod
    def _candidate_from_row(r: sqlite3.Row) -> SourceCandidateRecord:
        return SourceCandidateRecord(
            id=r["id"], research_run_id=r["research_run_id"], url=r["url"], title=r["title"],
            author_or_org=r["author_or_org"], published_at=r["published_at"],
            source_type=SourceType(r["source_type"]),
            supported_claims=json.loads(r["supported_claims_json"] or "[]"),
            numeric_facts=json.loads(r["numeric_facts_json"] or "[]"),
            verification_status=SourceVerification(r["verification_status"] or "UNVERIFIED"),
            source_quality_score=r["source_quality_score"],
            status=SourceCandidateStatus(r["status"]),
            extraction_error=r["extraction_error"],
            attempts=r["attempts"],
            discovered_at=r["discovered_at"], extracted_at=r["extracted_at"],
        )

    def mark_extraction_in_progress(self, research_run_id: str) -> None:
        """Idempotentne — wołane na START pętli ekstrakcji (etap A2), niezależnie od
        tego, czy to pierwsze uruchomienie czy wznowienie po restarcie."""
        allowed = (
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.DISCOVERY_COMPLETE.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.PARTIAL.value}",
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.EXTRACTION_IN_PROGRESS.value}",
        )
        existing = self.conn.execute(
            "SELECT flow, status FROM research_runs WHERE id=?", (research_run_id,),
        ).fetchone()
        if (
            existing is not None
            and existing["flow"] == ResearchFlow.STAGED.value
            and existing["status"] == ResearchRunStatus.EXTRACTION_IN_PROGRESS.value
        ):
            return
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?, ?)",
                (
                    ResearchRunStatus.EXTRACTION_IN_PROGRESS.value, _ts(), research_run_id,
                    ResearchFlow.STAGED.value, ResearchRunStatus.DISCOVERY_COMPLETE.value,
                    ResearchRunStatus.PARTIAL.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def update_source_candidate_extracted(
        self, candidate_id: int, *, title: str | None, author_or_org: str | None,
        published_at: str | None, source_type: SourceType, supported_claims: list[str],
        numeric_facts: list[str], verification_status: SourceVerification,
        source_quality_score: float,
    ) -> None:
        """Zapisuje pełną Source Card dla JEDNEGO kandydata — commit NATYCHMIAST, nie
        czeka na pozostałych. To jest sedno odporności etapu A2: awaria źródła N+1 nie
        wpływa na już zapisane źródło N."""
        cursor = self.conn.execute(
            "UPDATE research_source_candidates SET title=?, author_or_org=?,"
            " published_at=?, source_type=?, supported_claims_json=?, numeric_facts_json=?,"
            " verification_status=?, source_quality_score=?, status=?, extraction_error=NULL,"
            " extracted_at=? WHERE id=? AND status IN (?)",
            (
                title, author_or_org, published_at, source_type.value,
                json.dumps(supported_claims), json.dumps(numeric_facts),
                verification_status.value, source_quality_score,
                SourceCandidateStatus.EXTRACTED.value, _ts(), candidate_id,
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
            ),
        )
        try:
            self._require_one_transition(
                cursor, table="research_source_candidates", entity="source_candidate",
                identifier=candidate_id,
                target_status=SourceCandidateStatus.EXTRACTED.value,
                allowed_source_statuses=(
                    SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
                ),
                detail=(
                    f"Source candidate #{candidate_id} is not EXTRACTION_IN_PROGRESS; "
                    "cannot persist extraction success."
                ),
            )
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

    def mark_source_candidate_failed(self, candidate_id: int, error: str) -> None:
        """Ekstrakcja nieudana dla JEDNEGO źródła — commit NATYCHMIAST. Inne kandydaci
        (przetworzeni wcześniej lub później) są nietknięci."""
        cursor = self.conn.execute(
            "UPDATE research_source_candidates SET status=?, extraction_error=?,"
            " extracted_at=? WHERE id=? AND status IN (?)",
            (
                SourceCandidateStatus.EXTRACTION_FAILED.value, error, _ts(), candidate_id,
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
            ),
        )
        try:
            self._require_one_transition(
                cursor, table="research_source_candidates", entity="source_candidate",
                identifier=candidate_id,
                target_status=SourceCandidateStatus.EXTRACTION_FAILED.value,
                allowed_source_statuses=(
                    SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
                ),
                detail=(
                    f"Source candidate #{candidate_id} is not EXTRACTION_IN_PROGRESS; "
                    "cannot persist extraction failure."
                ),
            )
        except Exception:
            self.conn.rollback()
            raise
        self.conn.commit()

    def claim_source_candidate_attempt(self, candidate_id: int, *, max_attempts: int) -> int:
        """Atomically reserves one legal A2 attempt before the external call.

        The conditional UPDATE makes the candidate unavailable to another process
        and enforces the cap at the only point where a model call may begin.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive.")
        cursor = self.conn.execute(
            "UPDATE research_source_candidates "
            "SET attempts=attempts+1, status=? "
            "WHERE id=? AND status IN (?) AND attempts < ?",
            (
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
                candidate_id, SourceCandidateStatus.PENDING_EXTRACTION.value, max_attempts,
            ),
        )
        try:
            self._require_one_transition(
                cursor, table="research_source_candidates", entity="source_candidate",
                identifier=candidate_id,
                target_status=SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
                allowed_source_statuses=(
                    f"{SourceCandidateStatus.PENDING_EXTRACTION.value} below attempts cap",
                ),
                detail=(
                    f"Source candidate #{candidate_id} is not claimable "
                    "(requires PENDING_EXTRACTION below attempts cap)."
                ),
            )
        except Exception:
            self.conn.rollback()
            raise
        row = self.conn.execute(
            "SELECT attempts FROM research_source_candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        self.conn.commit()
        return int(row["attempts"])

    def retry_failed_source_candidates(
        self, research_run_id: str, *, max_attempts: int,
    ) -> SourceCandidateRetryResult:
        """Idempotentnie przygotowuje tylko eligible EXTRACTION_FAILED do jawnego A2.

        Reset nie zmienia attempts, kosztu ani usage. Dla PARTIAL_EXHAUSTED z co
        najmniej jednym resetem atomowo otwiera run z powrotem jako PARTIAL. Historia
        zakończonych prób pozostaje w research_stage_results i diagnostyce.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts musi być dodatnie.")
        self.conn.execute("BEGIN")
        try:
            run_row = self.conn.execute(
                "SELECT status, flow FROM research_runs WHERE id=?", (research_run_id,)
            ).fetchone()
            if run_row is None:
                raise LifecycleTransitionError(
                    "research_run", research_run_id, "retry_failed_candidates",
                    (
                        f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.PARTIAL.value}",
                        f"{ResearchFlow.STAGED.value}:"
                        f"{ResearchRunStatus.PARTIAL_EXHAUSTED.value}",
                    ),
                    None,
                )
            if (
                run_row["flow"] != ResearchFlow.STAGED.value
                or run_row["status"] not in (
                    ResearchRunStatus.PARTIAL.value,
                    ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                )
            ):
                raise LifecycleTransitionError(
                    "research_run", research_run_id, "retry_failed_candidates",
                    (
                        f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.PARTIAL.value}",
                        f"{ResearchFlow.STAGED.value}:"
                        f"{ResearchRunStatus.PARTIAL_EXHAUSTED.value}",
                    ),
                    f"{run_row['flow']}:{run_row['status']}",
                    detail=(
                        f"Research run #{research_run_id} cannot retry failed candidates "
                        f"from status {run_row['status']}."
                    ),
                )
            rows = self.conn.execute(
                "SELECT id, status, attempts FROM research_source_candidates "
                "WHERE research_run_id=? ORDER BY id ASC",
                (research_run_id,),
            ).fetchall()
            reset_count = 0
            skipped_cap_count = 0
            already_pending_count = 0
            in_progress_count = 0
            for row in rows:
                status = SourceCandidateStatus(row["status"])
                if status == SourceCandidateStatus.PENDING_EXTRACTION:
                    already_pending_count += 1
                elif status == SourceCandidateStatus.EXTRACTION_IN_PROGRESS:
                    in_progress_count += 1
                elif status == SourceCandidateStatus.EXTRACTION_FAILED:
                    if row["attempts"] < max_attempts:
                        cursor = self.conn.execute(
                            "UPDATE research_source_candidates SET status=? "
                            "WHERE id=? AND status IN (?) AND attempts < ?",
                            (
                                SourceCandidateStatus.PENDING_EXTRACTION.value, row["id"],
                                SourceCandidateStatus.EXTRACTION_FAILED.value, max_attempts,
                            ),
                        )
                        self._require_one_transition(
                            cursor, table="research_source_candidates",
                            entity="source_candidate", identifier=row["id"],
                            target_status=SourceCandidateStatus.PENDING_EXTRACTION.value,
                            allowed_source_statuses=(
                                f"{SourceCandidateStatus.EXTRACTION_FAILED.value} "
                                "below attempts cap",
                            ),
                        )
                        reset_count += 1
                    else:
                        skipped_cap_count += 1
            remaining_failed_count = int(self.conn.execute(
                "SELECT count(*) FROM research_source_candidates "
                "WHERE research_run_id=? AND status=?",
                (research_run_id, SourceCandidateStatus.EXTRACTION_FAILED.value),
            ).fetchone()[0])
            reopened_run = False
            if (
                run_row["status"] == ResearchRunStatus.PARTIAL_EXHAUSTED.value
                and reset_count > 0
            ):
                cursor = self.conn.execute(
                    "UPDATE research_runs SET status=?, error=NULL, updated_at=? "
                    "WHERE id=? AND status IN (?)",
                    (
                        ResearchRunStatus.PARTIAL.value, _ts(), research_run_id,
                        ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                    ),
                )
                self._require_one_transition(
                    cursor, table="research_runs", entity="research_run",
                    identifier=research_run_id,
                    target_status=ResearchRunStatus.PARTIAL.value,
                    allowed_source_statuses=(
                        ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                    ),
                    detail=(
                        f"Research run #{research_run_id} could not be reopened from "
                        "PARTIAL_EXHAUSTED."
                    ),
                )
                reopened_run = True
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return SourceCandidateRetryResult(
            reset_count=reset_count,
            skipped_cap_count=skipped_cap_count,
            already_pending_count=already_pending_count,
            in_progress_count=in_progress_count,
            remaining_failed_count=remaining_failed_count,
            reopened_run=reopened_run,
        )

    def mark_sources_complete(self, research_run_id: str) -> None:
        """Etap A2 dał >= research_min_sources wyekstrahowanych kart — gotowe do etapu B."""
        allowed = (
            f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.EXTRACTION_IN_PROGRESS.value}",
        )
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, stage_a_completed_at=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?)",
                (
                    ResearchRunStatus.SOURCES_COMPLETE.value, _ts(), _ts(), research_run_id,
                    ResearchFlow.STAGED.value,
                    ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.SOURCES_COMPLETE.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_research_run_partial_exhausted(self, research_run_id: str, error: str) -> None:
        """Terminalny brak legalnej drogi A2: nie ma pending ani failed poniżej capu."""
        allowed = tuple(
            f"{ResearchFlow.STAGED.value}:{status}"
            for status in (
                ResearchRunStatus.DISCOVERY_COMPLETE.value,
                ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                ResearchRunStatus.PARTIAL.value,
            )
        )
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, error=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?,?,?)",
                (
                    ResearchRunStatus.PARTIAL_EXHAUSTED.value, error, _ts(), research_run_id,
                    ResearchFlow.STAGED.value, ResearchRunStatus.DISCOVERY_COMPLETE.value,
                    ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                    ResearchRunStatus.PARTIAL.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def mark_synthesis_pending(self, research_run_id: str) -> None:
        """Wołane TUŻ PRZED próbą etapu B — czysto obserwacyjne (jak `runs.current_state`),
        nie mechanizm odzyskiwania w locie (nie-streamowane wywołanie API i tak nie da
        się 'odzyskać' w połowie — awaria w trakcie po prostu traci TĘ próbę, tak jak
        zawsze; źródła i tak zostają nietknięte, więc kolejna próba jest tania)."""
        allowed = (f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.SOURCES_COMPLETE.value}",)
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?)",
                (
                    ResearchRunStatus.SYNTHESIS_PENDING.value, _ts(), research_run_id,
                    ResearchFlow.STAGED.value, ResearchRunStatus.SOURCES_COMPLETE.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.SYNTHESIS_PENDING.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def revert_to_sources_complete(self, research_run_id: str, error: str) -> None:
        """Etap B nieudany — źródła (research_source_candidates) zostają nietknięte;
        status wraca do SOURCES_COMPLETE, żeby etap B można było ponowić bez powtarzania
        A1/A2. `error` zapisany dla widoczności/audytu, nie kasuje wcześniejszego sukcesu."""
        allowed = (f"{ResearchFlow.STAGED.value}:{ResearchRunStatus.SYNTHESIS_PENDING.value}",)
        self.conn.execute("BEGIN")
        try:
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?, error=?, updated_at=? "
                "WHERE id=? AND flow=? AND status IN (?)",
                (
                    ResearchRunStatus.SOURCES_COMPLETE.value, error, _ts(), research_run_id,
                    ResearchFlow.STAGED.value, ResearchRunStatus.SYNTHESIS_PENDING.value,
                ),
            )
            self._require_one_transition(
                cursor, table="research_runs", entity="research_run",
                identifier=research_run_id,
                target_status=ResearchRunStatus.SOURCES_COMPLETE.value,
                allowed_source_statuses=allowed, include_flow=True,
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- E2-A: lease-fenced offline staged evidence integration ---

    def persist_offline_evidence_discovery(
        self,
        execution: JobExecutionContext,
        candidates: list[SourceCandidateRecord],
    ) -> list[SourceCandidateRecord]:
        """Persist A1 and its STAGED checkpoint in one fenced transaction."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.STAGED,
            )
            if fence["research_status"] != ResearchRunStatus.DISCOVERY_PENDING.value:
                raise StaleJobExecutionError(
                    execution.job_id, "offline A1 checkpoint is no longer pending.",
                )
            if not candidates or len({item.url for item in candidates}) != len(candidates):
                raise ResearchTopicIntegrityError("offline A1 candidates must be non-empty and unique.")
            for candidate in candidates:
                cursor = self.conn.execute(
                    "INSERT INTO research_source_candidates "
                    "(research_run_id,url,title,status,discovered_at) VALUES (?,?,?,?,?)",
                    (execution.run_id, candidate.url, candidate.title,
                     SourceCandidateStatus.PENDING_EXTRACTION.value, now),
                )
                candidate.id = int(cursor.lastrowid)
                candidate.research_run_id = execution.run_id
            cursor = self.conn.execute(
                "UPDATE research_runs SET status=?,updated_at=? WHERE id=? AND flow=? AND status=?",
                (ResearchRunStatus.DISCOVERY_COMPLETE.value, now, execution.run_id,
                 ResearchFlow.STAGED.value, ResearchRunStatus.DISCOVERY_PENDING.value),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.execute(
                "INSERT INTO research_stage_results "
                "(research_run_id,stage,status,finished_at,error) VALUES (?,?,?,?,NULL)",
                (execution.run_id, ResearchStageName.A1.value,
                 ResearchStageStatus.SUCCESS.value, now),
            )
            self.conn.commit()
            return candidates
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def get_offline_evidence_lineage(
        self, research_run_id: str,
    ) -> list[sqlite3.Row]:
        """Read the complete candidate→evidence→card relation for resume/audit."""
        return self.conn.execute(
            "SELECT c.*,cr.retrieval_id,ce.excerpt_id,sl.source_id,sl.research_card_id "
            "FROM research_source_candidates c "
            "LEFT JOIN evidence_candidate_retrievals cr ON cr.candidate_id=c.id "
            "LEFT JOIN evidence_candidate_excerpts ce ON ce.candidate_id=c.id "
            "LEFT JOIN evidence_source_lineage sl ON sl.candidate_id=c.id "
            "WHERE c.research_run_id=? ORDER BY c.id",
            (research_run_id,),
        ).fetchall()

    def persist_offline_evidence_retrieval(
        self,
        execution: JobExecutionContext,
        candidate_id: int,
        document: FetchedDocument,
    ) -> EvidenceRetrieval:
        """Record the E1 retrieval and candidate lineage under the same lease."""
        retrieval: EvidenceRetrieval | None = None
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.STAGED,
            )
            candidate = self.conn.execute(
                "SELECT * FROM research_source_candidates WHERE id=? AND research_run_id=?",
                (candidate_id, execution.run_id),
            ).fetchone()
            if candidate is None or candidate["url"] != document.requested_url:
                raise ResearchTopicIntegrityError("retrieval candidate/run/url identity mismatch.")
            existing = self.conn.execute(
                "SELECT er.* FROM evidence_candidate_retrievals cr "
                "JOIN evidence_retrievals er ON er.id=cr.retrieval_id "
                "WHERE cr.candidate_id=? AND cr.research_run_id=? AND cr.account_id=?",
                (candidate_id, execution.run_id, fence["research_account_id"]),
            ).fetchone()
            if existing is not None:
                self.conn.commit()
                return self._row_to_evidence_retrieval(existing)
            retrieval = build_evidence_retrieval(
                document, account_id=fence["research_account_id"],
                now=execution.now(),
            )
            canonical = retrieval.canonical_text
            cursor = self.conn.execute(
                "INSERT INTO evidence_retrievals (account_id,requested_url,final_url,"
                "fetched_at,status,http_status,content_type,fetch_error,raw_size_bytes,"
                "raw_sha256,extracted_chars,extracted_sha256,canonical_text,canonical_chars,"
                "canonical_sha256,truncated,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    retrieval.account_id, retrieval.requested_url, retrieval.final_url,
                    _ts_precise(retrieval.fetched_at), retrieval.status.value,
                    retrieval.http_status, retrieval.content_type, retrieval.fetch_error,
                    retrieval.raw_size_bytes, retrieval.raw_sha256,
                    retrieval.extracted_chars, retrieval.extracted_sha256,
                    canonical, len(canonical), sha256_hex(canonical),
                    int(retrieval.truncated), _ts_precise(retrieval.created_at),
                ),
            )
            retrieval.id = int(cursor.lastrowid)
            self.conn.execute(
                "INSERT INTO evidence_candidate_retrievals "
                "(candidate_id,research_run_id,account_id,retrieval_id,created_at)"
                " VALUES (?,?,?,?,?)",
                (candidate_id, execution.run_id, fence["research_account_id"],
                 retrieval.id, now),
            )
            self.conn.commit()
            return retrieval
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def persist_offline_verified_excerpt(
        self,
        execution: JobExecutionContext,
        candidate_id: int,
        *,
        claim_text: str,
        excerpt_text: str,
        start_offset: int,
        end_offset: int,
        title: str | None,
        author_or_org: str | None,
        published_at: str | None,
        source_type: SourceType,
        source_quality_score: float,
    ) -> EvidenceExcerpt:
        """Run the E1 verifier and only then set the candidate to VERIFIED."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.STAGED,
            )
            row = self.conn.execute(
                "SELECT er.* "
                "FROM research_source_candidates c "
                "JOIN evidence_candidate_retrievals cr ON cr.candidate_id=c.id "
                "JOIN evidence_retrievals er ON er.id=cr.retrieval_id "
                "WHERE c.id=? AND c.research_run_id=? AND cr.research_run_id=? "
                "AND cr.account_id=? AND er.account_id=?",
                (candidate_id, execution.run_id, execution.run_id,
                 fence["research_account_id"], fence["research_account_id"]),
            ).fetchone()
            if row is None:
                raise EvidenceVerificationError(EvidenceVerdict.rejected(
                    EvidenceRejectionReason.RETRIEVAL_NOT_FOUND,
                    "candidate has no retrieval in this run/account",
                ))
            existing = self.conn.execute(
                "SELECT ee.* FROM evidence_candidate_excerpts ce "
                "JOIN evidence_excerpts ee ON ee.id=ce.excerpt_id "
                "WHERE ce.candidate_id=? AND ce.research_run_id=? AND ce.account_id=?",
                (candidate_id, execution.run_id, fence["research_account_id"]),
            ).fetchone()
            if existing is not None:
                self.conn.commit()
                return EvidenceExcerpt(
                    id=existing["id"], account_id=existing["account_id"],
                    retrieval_id=existing["retrieval_id"], claim_text=existing["claim_text"],
                    claim_sha256=existing["claim_sha256"], excerpt_text=existing["excerpt_text"],
                    start_offset=existing["start_offset"], end_offset=existing["end_offset"],
                    created_at=existing["created_at"],
                )
            retrieval = self._row_to_evidence_retrieval(row)
            verdict = verify_evidence_excerpt(
                retrieval, claim_text=claim_text, excerpt_text=excerpt_text,
                start_offset=start_offset, end_offset=end_offset,
            )
            if not verdict.approved:
                raise EvidenceVerificationError(verdict)
            cursor = self.conn.execute(
                "INSERT INTO evidence_excerpts "
                "(account_id,retrieval_id,claim_text,claim_sha256,excerpt_text,"
                "start_offset,end_offset,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (fence["research_account_id"], retrieval.id, claim_text,
                 sha256_hex(claim_text), excerpt_text, start_offset, end_offset, now),
            )
            excerpt_id = int(cursor.lastrowid)
            self.conn.execute(
                "INSERT INTO evidence_candidate_excerpts "
                "(candidate_id,research_run_id,account_id,retrieval_id,excerpt_id,created_at)"
                " VALUES (?,?,?,?,?,?)",
                (candidate_id, execution.run_id, fence["research_account_id"],
                 retrieval.id, excerpt_id, now),
            )
            cursor = self.conn.execute(
                "UPDATE research_source_candidates SET title=?,author_or_org=?,published_at=?,"
                "source_type=?,supported_claims_json=?,numeric_facts_json='[]',"
                "verification_status='VERIFIED',source_quality_score=?,status='EXTRACTED',"
                "attempts=attempts+1,extraction_error=NULL,extracted_at=? "
                "WHERE id=? AND research_run_id=? AND status='PENDING_EXTRACTION'",
                (title, author_or_org, published_at, source_type.value,
                 json.dumps([claim_text]), source_quality_score, now,
                 candidate_id, execution.run_id),
            )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError("candidate is not pending local verification.")
            self.conn.execute(
                "UPDATE research_runs SET status=?,updated_at=? WHERE id=? AND status IN (?,?)",
                (ResearchRunStatus.EXTRACTION_IN_PROGRESS.value, now, execution.run_id,
                 ResearchRunStatus.DISCOVERY_COMPLETE.value,
                 ResearchRunStatus.EXTRACTION_IN_PROGRESS.value),
            )
            self.conn.execute(
                "INSERT INTO research_stage_results "
                "(research_run_id,stage,status,finished_at,error) VALUES (?,?,?,?,NULL)",
                (execution.run_id, ResearchStageName.A2.value,
                 ResearchStageStatus.SUCCESS.value, now),
            )
            self.conn.commit()
            return EvidenceExcerpt(
                id=excerpt_id, account_id=fence["research_account_id"],
                retrieval_id=int(retrieval.id), claim_text=claim_text,
                claim_sha256=sha256_hex(claim_text), excerpt_text=excerpt_text,
                start_offset=start_offset, end_offset=end_offset,
                created_at=execution.now(),
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def prepare_offline_evidence_synthesis(
        self, execution: JobExecutionContext, *, min_verified_sources: int,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, now, flow=ResearchFlow.STAGED)
            count = int(self.conn.execute(
                "SELECT count(*) FROM research_source_candidates c "
                "JOIN evidence_candidate_excerpts ce ON ce.candidate_id=c.id "
                "WHERE c.research_run_id=? AND c.status='EXTRACTED' "
                "AND c.verification_status='VERIFIED'",
                (execution.run_id,),
            ).fetchone()[0])
            if count < min_verified_sources:
                raise ResearchTopicIntegrityError("insufficient locally verified evidence.")
            cursor = self.conn.execute(
                "UPDATE research_runs SET status='SYNTHESIS_PENDING',stage_a_completed_at=?,"
                "updated_at=? WHERE id=? AND flow='staged' "
                "AND status IN ('EXTRACTION_IN_PROGRESS','SOURCES_COMPLETE')",
                (now, now, execution.run_id),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(
                    execution.job_id, "offline synthesis checkpoint is unavailable.",
                )
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def finalize_offline_evidence_execution(
        self,
        execution: JobExecutionContext,
        card: ResearchCard,
        *,
        min_verified_sources: int,
    ) -> ResearchCard:
        """Atomically commit card, evidence lineage, run/topic and job DONE."""
        original_card_id = card.id
        original_sources = [(item.id, item.research_card_id) for item in card.sources]
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.STAGED,
            )
            if (
                fence["research_status"] != ResearchRunStatus.SYNTHESIS_PENDING.value
                or fence["run_status"] != RunStatus.DRY_RUN.value
                or card.id is not None
                or card.topic_id != fence["topic_id"]
                or len(card.sources) < min_verified_sources
            ):
                raise ResearchTopicIntegrityError("offline finalization preconditions failed.")
            lineage = {
                row["url"]: row for row in self.conn.execute(
                    "SELECT c.id AS candidate_id,c.url,cr.retrieval_id,ce.excerpt_id "
                    "FROM research_source_candidates c "
                    "JOIN evidence_candidate_retrievals cr ON cr.candidate_id=c.id "
                    "JOIN evidence_candidate_excerpts ce ON ce.candidate_id=c.id "
                    "WHERE c.research_run_id=? AND c.status='EXTRACTED' "
                    "AND c.verification_status='VERIFIED'",
                    (execution.run_id,),
                ).fetchall()
            }
            if (
                len({source.url for source in card.sources}) != len(card.sources)
                or any(
                    source.verification_status is not SourceVerification.VERIFIED
                    or source.url not in lineage
                    for source in card.sources
                )
            ):
                raise ResearchTopicIntegrityError(
                    "card sources must be backed by locally VERIFIED excerpts.",
                )
            self._insert_finalization_card(card)
            for source in card.sources:
                source.research_card_id = card.id
                self._insert_finalization_source(source)
                item = lineage[source.url]
                claim_positions = [
                    index for index, claim in enumerate(card.confirmed_claims)
                    if claim == source.supports_claim
                ]
                if len(claim_positions) != 1:
                    raise ResearchTopicIntegrityError(
                        "source claim must identify exactly one confirmed-claim position."
                    )
                claim_ordinal = claim_positions[0]
                claim_id = (
                    f"research-card:{card.id}:"
                    f"confirmed-claim:{claim_ordinal}"
                )
                lineage_preimage = {
                    "account_id": fence["research_account_id"],
                    "candidate_id": int(item["candidate_id"]),
                    "confirmed_claim_id": claim_id,
                    "confirmed_claim_ordinal": claim_ordinal,
                    "excerpt_id": int(item["excerpt_id"]),
                    "research_card_id": int(card.id),
                    "research_job_id": execution.job_id,
                    "research_run_id": execution.run_id,
                    "retrieval_id": int(item["retrieval_id"]),
                    "source_id": int(source.id),
                    "topic_id": int(card.topic_id),
                }
                self.conn.execute(
                    "INSERT INTO evidence_source_lineage "
                    "(source_id,research_card_id,candidate_id,research_run_id,account_id,"
                    "retrieval_id,excerpt_id,created_at,confirmed_claim_ordinal,"
                    "confirmed_claim_id,confirmed_claim_sha256,research_job_id,"
                    "topic_id,lineage_fingerprint) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (source.id, card.id, item["candidate_id"], execution.run_id,
                     fence["research_account_id"], item["retrieval_id"],
                     item["excerpt_id"], now, claim_ordinal, claim_id,
                     sha256_text(card.confirmed_claims[claim_ordinal]),
                     execution.job_id, card.topic_id,
                     sha256_text(canonical_json(lineage_preimage))),
                )
            self.conn.execute(
                "INSERT INTO research_stage_results "
                "(research_run_id,stage,status,finished_at,error) VALUES (?,?,?,?,NULL)",
                (execution.run_id, ResearchStageName.B.value,
                 ResearchStageStatus.SUCCESS.value, now),
            )
            research = self.conn.execute(
                "UPDATE research_runs SET status='COMPLETE',stage_b_completed_at=?,"
                "research_card_id=?,total_cost_usd=0,error=NULL,updated_at=? "
                "WHERE id=? AND flow='staged' AND status='SYNTHESIS_PENDING'",
                (now, card.id, now, execution.run_id),
            )
            run = self.conn.execute(
                "UPDATE runs SET status='DRY_RUN',cost_usd=0,error=NULL,finished_at=? "
                "WHERE id=? AND status='DRY_RUN' AND finished_at IS NULL",
                (now, execution.run_id),
            )
            topic = self.conn.execute(
                "UPDATE topics SET status='USED' WHERE id=? AND account_id=? AND status='SELECTED'",
                (fence["topic_id"], fence["research_account_id"]),
            )
            job = self.conn.execute(
                "UPDATE jobs SET status='DONE',last_error=NULL,lease_owner=NULL,"
                "lease_expires_at=NULL,updated_at=?,finished_at=?,reserved_cost_usd=0,"
                "budget_reserved_at=NULL WHERE id=? AND run_id=? AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                (now, now, execution.job_id, execution.run_id,
                 execution.lease_owner, now),
            )
            if any(cursor.rowcount != 1 for cursor in (research, run, topic, job)):
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return card
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            card.id = original_card_id
            for source, state in zip(card.sources, original_sources):
                source.id, source.research_card_id = state
            raise

    def fail_offline_evidence_execution(
        self, execution: JobExecutionContext, error: str,
    ) -> None:
        """Atomically terminalize a confirmed zero-external-effect E2-A failure."""
        safe_error = " ".join(error.split())[:240] or "OFFLINE_EVIDENCE_FAILED"
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.STAGED,
            )
            research = self.conn.execute(
                "UPDATE research_runs SET status='FAILED',error=?,total_cost_usd=0,"
                "updated_at=? WHERE id=? AND flow='staged' AND status NOT IN ('COMPLETE','FAILED')",
                (safe_error, now, execution.run_id),
            )
            run = self.conn.execute(
                "UPDATE runs SET status='FAILED',error=?,cost_usd=0,finished_at=? "
                "WHERE id=? AND status='DRY_RUN' AND finished_at IS NULL",
                (safe_error, now, execution.run_id),
            )
            job = self.conn.execute(
                "UPDATE jobs SET status='FAILED',last_error=?,lease_owner=NULL,"
                "lease_expires_at=NULL,updated_at=?,finished_at=?,reserved_cost_usd=0,"
                "budget_reserved_at=NULL WHERE id=? AND run_id=? AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                (safe_error, now, now, execution.job_id, execution.run_id,
                 execution.lease_owner, now),
            )
            if research.rowcount != 1 or run.rowcount != 1 or job.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    # --- Controlled Fetch foundation (Etap 2, fala E2-B) ---
    # Trwały lifecycle jednego zatwierdzonego pobrania: approval L1 → RESERVED
    # → REQUEST_STARTED → SUCCEEDED | FAILED | NEEDS_VERIFICATION. Każda
    # mutacja działa pod tym samym rodzajem fence co research (job→run→topic,
    # świeży lease), a podłogi SQLite migracji 0018 wiążą approval, attempt,
    # payload i retrieval w jeden niepodrabialny łańcuch.

    @staticmethod
    def _controlled_fetch_approval_from_row(row: sqlite3.Row) -> ControlledFetchApproval:
        return ControlledFetchApproval(
            id=int(row["id"]), job_id=row["job_id"], account_id=row["account_id"],
            action_type=row["action_type"], requested_url=row["requested_url"],
            intent_fingerprint=row["intent_fingerprint"],
            timeout_seconds=int(row["timeout_seconds"]),
            max_bytes=int(row["max_bytes"]),
            max_redirects=int(row["max_redirects"]),
            approved_by=row["approved_by"], approved_at=row["approved_at"],
            expires_at=row["expires_at"], consumed_at=row["consumed_at"],
        )

    @staticmethod
    def _controlled_fetch_attempt_from_row(row: sqlite3.Row) -> ControlledFetchAttempt:
        return ControlledFetchAttempt(
            id=int(row["id"]), job_id=row["job_id"], run_id=row["run_id"],
            account_id=row["account_id"], topic_id=int(row["topic_id"]),
            approval_id=int(row["approval_id"]), attempt_no=int(row["attempt_no"]),
            source_identity=row["source_identity"],
            requested_url=row["requested_url"],
            intent_fingerprint=row["intent_fingerprint"],
            status=ControlledFetchAttemptStatus(row["status"]),
            lease_owner=row["lease_owner"], reserved_at=row["reserved_at"],
            request_started_at=row["request_started_at"],
            terminalized_at=row["terminalized_at"],
            retrieval_id=row["retrieval_id"], outcome_reason=row["outcome_reason"],
        )

    def get_controlled_fetch_approval_for_job(
        self, job_id: str,
    ) -> ControlledFetchApproval | None:
        row = self.conn.execute(
            "SELECT * FROM controlled_fetch_approvals WHERE job_id=?", (job_id,),
        ).fetchone()
        return None if row is None else self._controlled_fetch_approval_from_row(row)

    def get_controlled_fetch_attempt_for_job(
        self, job_id: str,
    ) -> ControlledFetchAttempt | None:
        row = self.conn.execute(
            "SELECT * FROM controlled_fetch_attempts WHERE job_id=?", (job_id,),
        ).fetchone()
        return None if row is None else self._controlled_fetch_attempt_from_row(row)

    def record_controlled_fetch_approval(
        self, *, job_id: str, account_id: str, approved_by: str,
        expires_at: datetime, clock: Clock,
    ) -> ControlledFetchApproval:
        """L1: derive the approval entirely from the frozen job contract.

        URL, fingerprint i limity NIE są przyjmowane od wywołującego — pochodzą
        wyłącznie z kanonizowanego, zamrożonego payloadu joba, więc zgoda nigdy
        nie może opisywać czegoś innego niż wykonywany kontrakt.
        """
        if not approved_by.strip():
            raise ControlledFetchAuthorizationError(
                "APPROVER_MISSING", "approved_by must identify the human L1 operator.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now_dt = self._job_now(clock=clock)
            now = _persisted_ts(now_dt)
            expiry_dt = self._job_now(expires_at)
            if expiry_dt <= now_dt:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_EXPIRY_INVALID", "expires_at must be in the future.",
                )
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise ControlledFetchAuthorizationError(
                    "JOB_MISSING", f"job {job_id!r} does not exist.",
                )
            job = self._job_from_row(row)
            try:
                payload = canonicalize_controlled_fetch_payload(job.payload)
            except ControlledFetchIntentError as exc:
                raise ControlledFetchAuthorizationError(
                    "INTENT_INVALID", str(exc),
                ) from exc
            intent = ControlledFetchIntent.from_payload(payload["execution_intent"])
            if job.account_id != account_id or intent.account_id != account_id:
                raise ControlledFetchAuthorizationError(
                    "ACCOUNT_MISMATCH", "approval account must own the frozen job contract.",
                )
            if job.status is not JobStatus.QUEUED:
                raise ControlledFetchAuthorizationError(
                    "JOB_NOT_APPROVABLE",
                    f"approval must precede execution; job status is {job.status.value}.",
                )
            if now_dt >= intent.expires_at_datetime():
                raise ControlledFetchAuthorizationError(
                    "INTENT_EXPIRED", "the frozen intent has already expired.",
                )
            if self.conn.execute(
                "SELECT 1 FROM controlled_fetch_approvals WHERE job_id=?", (job_id,),
            ).fetchone() is not None:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_ALREADY_EXISTS", "the job already carries its one approval.",
                )
            cursor = self.conn.execute(
                "INSERT INTO controlled_fetch_approvals (job_id,account_id,action_type,"
                "requested_url,intent_fingerprint,timeout_seconds,max_bytes,max_redirects,"
                "approved_by,approved_at,expires_at,consumed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    job_id, account_id, CONTROLLED_FETCH_ACTION_TYPE,
                    intent.requested_url, intent.fingerprint,
                    intent.timeout_seconds, intent.max_bytes, intent.max_redirects,
                    approved_by.strip(), now, _persisted_ts(expiry_dt),
                ),
            )
            approval_id = int(cursor.lastrowid)
            stored = self.conn.execute(
                "SELECT * FROM controlled_fetch_approvals WHERE id=?", (approval_id,),
            ).fetchone()
            self.conn.commit()
            assert stored is not None
            return self._controlled_fetch_approval_from_row(stored)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def initialize_controlled_fetch_run_for_job(
        self, job_id: str, lease_owner: str, run_id: str, *, clock: Clock,
    ) -> ControlledFetchInitialization:
        """Create or resume the single controlled fetch run under a fresh lease."""
        if not run_id.strip() or not lease_owner.strip():
            raise ValueError("controlled fetch execution identifiers must be non-empty.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = _persisted_ts(self._job_now(clock=clock))
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise JobRunRelationError("JOB_MISSING", job_id, "controlled fetch job is missing.")
            job = self._job_from_row(row)
            try:
                payload = canonicalize_controlled_fetch_payload(job.payload)
            except ControlledFetchIntentError as exc:
                raise JobRunRelationError(
                    "CONTROLLED_FETCH_INTENT_INVALID", job_id, str(exc),
                ) from exc
            if (
                job.kind is not JobKind.RESEARCH
                or job.workflow is not WorkflowType.RESEARCH
                or job.topic_id is None
                or payload["account_id"] != job.account_id
                or payload["topic_id"] != job.topic_id
            ):
                raise JobRunRelationError(
                    "CONTROLLED_FETCH_IDENTITY_MISMATCH", job_id,
                    "job, payload, account and topic identity must match.",
                )
            if (
                job.status not in (JobStatus.LEASED, JobStatus.RUNNING)
                or job.lease_owner != lease_owner
                or job.lease_expires_at is None
                or _persisted_ts(job.lease_expires_at) < now
            ):
                raise StaleJobExecutionError(job_id)
            if self.conn.execute(
                "SELECT 1 FROM topics WHERE id=? AND account_id=?",
                (job.topic_id, job.account_id),
            ).fetchone() is None:
                raise JobRunRelationError(
                    "JOB_TOPIC_ACCOUNT_MISMATCH", job_id,
                    "controlled fetch topic must belong to the job account.",
                )

            if job.run_id is None:
                self.conn.execute(
                    "INSERT INTO runs (id,account_id,workflow,status,current_state,"
                    "started_at,cost_usd) VALUES (?,?,?,?,?,?,0)",
                    (run_id, job.account_id, WorkflowType.RESEARCH.value,
                     RunStatus.RUNNING.value, "controlled_fetch", now),
                )
                cursor = self.conn.execute(
                    "UPDATE jobs SET run_id=?,updated_at=? WHERE id=? AND run_id IS NULL "
                    "AND lease_owner=? AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                    (run_id, now, job_id, lease_owner, now),
                )
                if cursor.rowcount != 1:
                    raise StaleJobExecutionError(job_id)
                created = True
                attached_run_id = run_id
            else:
                created = False
                attached_run_id = job.run_id

            run_row = self.conn.execute(
                "SELECT * FROM runs WHERE id=?", (attached_run_id,),
            ).fetchone()
            if run_row is None:
                raise JobRunRelationError(
                    "ATTACHED_RUN_MISSING", job_id,
                    "controlled fetch run relation is incomplete.",
                )
            run = self._run_from_row(run_row)
            if (
                run.account_id != job.account_id
                or run.workflow is not WorkflowType.RESEARCH
                or run.status is not RunStatus.RUNNING
                or run_row["finished_at"] is not None
                or float(run_row["cost_usd"]) != 0
                or run_row["current_state"] != "controlled_fetch"
            ):
                raise JobRunRelationError(
                    "ATTACHED_CONTROLLED_FETCH_RUN_INVALID", job_id,
                    "attached run is not a zero-cost active controlled fetch run.",
                )
            attempt = self.get_controlled_fetch_attempt_for_job(job_id)
            job = self._job_from_row(self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone())
            result = ControlledFetchInitialization(
                job=job, run=run, attempt=attempt, created=created,
            )
            self.conn.commit()
            return result
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _require_controlled_fetch_fence(
        self, execution: JobExecutionContext, current_ts: str,
    ) -> sqlite3.Row:
        """Jedna transakcyjna kontrola aktualności job→run→topic→payload."""
        row = self.conn.execute(
            "SELECT j.status AS job_status,j.account_id AS job_account_id,"
            "j.topic_id AS job_topic_id,j.payload_json,j.external_effect_started_at,"
            "r.status AS run_status "
            "FROM jobs j JOIN runs r ON r.id=j.run_id "
            "JOIN topics t ON t.id=j.topic_id "
            "WHERE j.id=? AND j.run_id=? AND j.lease_owner=? "
            "AND j.lease_expires_at>=? AND j.status IN ('LEASED','RUNNING') "
            "AND j.kind='RESEARCH' AND j.workflow='RESEARCH' "
            "AND r.workflow='RESEARCH' AND r.account_id=j.account_id "
            "AND r.status='RUNNING' AND r.finished_at IS NULL "
            "AND t.account_id=j.account_id "
            "AND json_extract(j.payload_json,'$.execution')=?",
            (
                execution.job_id, execution.run_id, execution.lease_owner,
                current_ts, CONTROLLED_FETCH_EXECUTION,
            ),
        ).fetchone()
        if row is None:
            raise StaleJobExecutionError(execution.job_id)
        return row

    def _controlled_fetch_intent_from_fence(
        self, fence: sqlite3.Row, job_id: str,
    ) -> ControlledFetchIntent:
        """Re-read the executed contract from the durable payload, never memory."""
        try:
            payload = canonicalize_controlled_fetch_payload(
                json.loads(fence["payload_json"])
            )
        except (json.JSONDecodeError, ControlledFetchIntentError) as exc:
            raise ControlledFetchAuthorizationError(
                "INTENT_INVALID", f"job {job_id!r} payload is not a valid frozen intent.",
            ) from exc
        return ControlledFetchIntent.from_payload(payload["execution_intent"])

    def begin_controlled_fetch_attempt(
        self, execution: JobExecutionContext,
    ) -> ControlledFetchAttempt:
        """Atomically consume the one-shot approval and reserve the attempt.

        W jednej transakcji przed granicą transportu: fence (job/run/topic/
        lease/fencing), świeży odczyt zamrożonego intentu z payloadu, ważność
        intentu i approval, zgodność approval↔intent, brak wcześniejszego
        startu — potem konsumpcja approval i INSERT attemptu RESERVED.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_controlled_fetch_fence(execution, now)
            intent = self._controlled_fetch_intent_from_fence(fence, execution.job_id)
            now_dt = self._job_now(execution.now())
            if now_dt >= intent.expires_at_datetime():
                raise ControlledFetchAuthorizationError(
                    "INTENT_EXPIRED", "the frozen intent expired before execution.",
                )
            if self.conn.execute(
                "SELECT 1 FROM controlled_fetch_attempts WHERE job_id=?",
                (execution.job_id,),
            ).fetchone() is not None:
                raise ControlledFetchAuthorizationError(
                    "ATTEMPT_ALREADY_EXISTS",
                    "the single controlled fetch attempt was already reserved.",
                )
            approval_row = self.conn.execute(
                "SELECT * FROM controlled_fetch_approvals WHERE job_id=?",
                (execution.job_id,),
            ).fetchone()
            if approval_row is None:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_MISSING", "no L1 approval exists for this job.",
                )
            if approval_row["account_id"] != fence["job_account_id"]:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_ACCOUNT_MISMATCH", "approval account does not own the job.",
                )
            if approval_row["action_type"] != CONTROLLED_FETCH_ACTION_TYPE:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_ACTION_MISMATCH", "approval action type is not CONTROLLED_FETCH.",
                )
            if approval_row["requested_url"] != intent.requested_url:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_URL_MISMATCH", "approval URL differs from the frozen intent.",
                )
            if approval_row["intent_fingerprint"] != intent.fingerprint:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_FINGERPRINT_MISMATCH",
                    "approval fingerprint differs from the frozen intent.",
                )
            if (
                int(approval_row["timeout_seconds"]) != intent.timeout_seconds
                or int(approval_row["max_bytes"]) != intent.max_bytes
                or int(approval_row["max_redirects"]) != intent.max_redirects
            ):
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_LIMITS_MISMATCH", "approval limits differ from the frozen intent.",
                )
            if approval_row["consumed_at"] is not None:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_ALREADY_CONSUMED", "the one-shot approval was already consumed.",
                )
            if str(approval_row["expires_at"]) <= now:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_EXPIRED", "the approval expired before execution.",
                )
            consumed = self.conn.execute(
                "UPDATE controlled_fetch_approvals SET consumed_at=? "
                "WHERE id=? AND consumed_at IS NULL",
                (now, approval_row["id"]),
            )
            if consumed.rowcount != 1:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_CONSUME_RACE", "approval consumption compare-and-swap failed.",
                )
            cursor = self.conn.execute(
                "INSERT INTO controlled_fetch_attempts (job_id,run_id,account_id,"
                "topic_id,approval_id,attempt_no,source_identity,requested_url,"
                "intent_fingerprint,status,lease_owner,reserved_at) "
                "VALUES (?,?,?,?,?,1,?,?,?,?,?,?)",
                (
                    execution.job_id, execution.run_id, fence["job_account_id"],
                    fence["job_topic_id"], approval_row["id"],
                    intent.source_identity, intent.requested_url,
                    intent.fingerprint,
                    ControlledFetchAttemptStatus.RESERVED.value,
                    execution.lease_owner, now,
                ),
            )
            attempt_id = int(cursor.lastrowid)
            stored = self.conn.execute(
                "SELECT * FROM controlled_fetch_attempts WHERE id=?", (attempt_id,),
            ).fetchone()
            self.conn.commit()
            assert stored is not None
            return self._controlled_fetch_attempt_from_row(stored)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def authorize_controlled_fetch_transport(
        self, execution: JobExecutionContext, attempt_id: int,
    ) -> ControlledFetchTransportAuthorization:
        """Issue an ephemeral transport capability from durable state only.

        The transaction re-reads the active fence, frozen intent, consumed L1
        approval and the single RESERVED attempt. No in-memory intent or ENV
        value can mint this capability.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            now_dt = self._job_now(execution.now())
            fence = self._require_controlled_fetch_fence(execution, now)
            intent = self._controlled_fetch_intent_from_fence(
                fence, execution.job_id,
            )
            attempt_row = self.conn.execute(
                "SELECT * FROM controlled_fetch_attempts "
                "WHERE id=? AND job_id=?",
                (attempt_id, execution.job_id),
            ).fetchone()
            if (
                attempt_row is None
                or attempt_row["run_id"] != execution.run_id
                or attempt_row["lease_owner"] != execution.lease_owner
                or int(attempt_row["attempt_no"]) != 1
                or attempt_row["status"]
                != ControlledFetchAttemptStatus.RESERVED.value
                or attempt_row["request_started_at"] is not None
                or attempt_row["terminalized_at"] is not None
                or attempt_row["retrieval_id"] is not None
            ):
                raise ControlledFetchAuthorizationError(
                    "ATTEMPT_NOT_TRANSPORT_AUTHORIZABLE",
                    "transport requires the single active RESERVED attempt.",
                )
            approval_row = self.conn.execute(
                "SELECT * FROM controlled_fetch_approvals WHERE id=? AND job_id=?",
                (attempt_row["approval_id"], execution.job_id),
            ).fetchone()
            if approval_row is None:
                raise ControlledFetchAuthorizationError(
                    "APPROVAL_MISSING", "the attempt has no durable L1 approval.",
                )
            approval = self._controlled_fetch_approval_from_row(approval_row)
            if (
                approval.action_type != CONTROLLED_FETCH_ACTION_TYPE
                or approval.account_id != fence["job_account_id"]
                or approval.requested_url != intent.requested_url
                or approval.intent_fingerprint != intent.fingerprint
                or approval.timeout_seconds != intent.timeout_seconds
                or approval.max_bytes != intent.max_bytes
                or approval.max_redirects != intent.max_redirects
                or approval.consumed_at is None
                or approval_row["consumed_at"] != attempt_row["reserved_at"]
                or str(approval_row["expires_at"]) <= now
                or now_dt >= intent.expires_at_datetime()
                or fence["external_effect_started_at"] is not None
                or attempt_row["account_id"] != fence["job_account_id"]
                or int(attempt_row["topic_id"]) != int(fence["job_topic_id"])
                or attempt_row["requested_url"] != intent.requested_url
                or attempt_row["intent_fingerprint"] != intent.fingerprint
                or attempt_row["source_identity"] != intent.source_identity
            ):
                raise ControlledFetchAuthorizationError(
                    "TRANSPORT_AUTHORIZATION_MISMATCH",
                    "durable approval, attempt and frozen intent do not match.",
                )
            authorization = _issue_controlled_fetch_transport_authorization(
                job_id=execution.job_id,
                run_id=execution.run_id,
                account_id=fence["job_account_id"],
                topic_id=int(fence["job_topic_id"]),
                approval_id=int(approval.id),
                attempt_id=int(attempt_row["id"]),
                requested_url=intent.requested_url,
                source_identity=intent.source_identity,
                intent_fingerprint=intent.fingerprint,
                timeout_seconds=intent.timeout_seconds,
                max_bytes=intent.max_bytes,
                max_redirects=intent.max_redirects,
                allowed_content_types=tuple(intent.allowed_content_types),
                approval_expires_at=(
                    approval.expires_at.replace(tzinfo=timezone.utc)
                    if approval.expires_at.tzinfo is None
                    else approval.expires_at.astimezone(timezone.utc)
                ),
            )
            self.conn.commit()
            return authorization
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def mark_controlled_fetch_request_started(
        self, execution: JobExecutionContext, attempt_id: int,
    ) -> None:
        """Durable boundary right before the transport; retry stops being safe."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            self._require_controlled_fetch_fence(execution, now)
            attempt = self.conn.execute(
                "UPDATE controlled_fetch_attempts SET status=?,request_started_at=? "
                "WHERE id=? AND job_id=? AND status=? AND lease_owner=?",
                (
                    ControlledFetchAttemptStatus.REQUEST_STARTED.value, now,
                    attempt_id, execution.job_id,
                    ControlledFetchAttemptStatus.RESERVED.value,
                    execution.lease_owner,
                ),
            )
            if attempt.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            job = self.conn.execute(
                "UPDATE jobs SET external_effect_started_at=?,updated_at=? "
                "WHERE id=? AND status IN ('LEASED','RUNNING') AND lease_owner=? "
                "AND lease_expires_at>=? AND external_effect_started_at IS NULL",
                (now, now, execution.job_id, execution.lease_owner, now),
            )
            if job.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _insert_controlled_fetch_retrieval(
        self, retrieval: EvidenceRetrieval,
    ) -> EvidenceRetrieval:
        canonical = retrieval.canonical_text
        cursor = self.conn.execute(
            "INSERT INTO evidence_retrievals (account_id,requested_url,final_url,"
            "fetched_at,status,http_status,content_type,fetch_error,raw_size_bytes,"
            "raw_sha256,extracted_chars,extracted_sha256,canonical_text,canonical_chars,"
            "canonical_sha256,truncated,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                retrieval.account_id, retrieval.requested_url, retrieval.final_url,
                _ts_precise(retrieval.fetched_at), retrieval.status.value,
                retrieval.http_status, retrieval.content_type, retrieval.fetch_error,
                retrieval.raw_size_bytes, retrieval.raw_sha256,
                retrieval.extracted_chars, retrieval.extracted_sha256,
                canonical, len(canonical), sha256_hex(canonical),
                int(retrieval.truncated), _ts_precise(retrieval.created_at),
            ),
        )
        retrieval.id = int(cursor.lastrowid)
        return retrieval

    def finalize_controlled_fetch_success(
        self, execution: JobExecutionContext, attempt_id: int,
        document: FetchedDocument,
    ) -> EvidenceRetrieval:
        """Atomically persist retrieval OK + SUCCEEDED attempt + terminal job/run."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_controlled_fetch_fence(execution, now)
            attempt_row = self.conn.execute(
                "SELECT * FROM controlled_fetch_attempts WHERE id=? AND job_id=?",
                (attempt_id, execution.job_id),
            ).fetchone()
            if (
                attempt_row is None
                or attempt_row["status"] != ControlledFetchAttemptStatus.REQUEST_STARTED.value
                or attempt_row["lease_owner"] != execution.lease_owner
                or attempt_row["requested_url"] != document.requested_url
            ):
                raise StaleJobExecutionError(
                    execution.job_id, "controlled fetch attempt is not finalizable.",
                )
            retrieval = build_evidence_retrieval(
                document, account_id=fence["job_account_id"], now=execution.now(),
            )
            if retrieval.status is not EvidenceRetrievalStatus.OK:
                raise ControlledFetchRetrievalNotOk(
                    retrieval.fetch_error or "RETRIEVAL_NOT_OK"
                )
            retrieval = self._insert_controlled_fetch_retrieval(retrieval)
            attempt = self.conn.execute(
                "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                "retrieval_id=? WHERE id=? AND status=?",
                (
                    ControlledFetchAttemptStatus.SUCCEEDED.value, now,
                    retrieval.id, attempt_id,
                    ControlledFetchAttemptStatus.REQUEST_STARTED.value,
                ),
            )
            run = self.conn.execute(
                "UPDATE runs SET status='SUCCESS',cost_usd=0,error=NULL,finished_at=? "
                "WHERE id=? AND status='RUNNING' AND finished_at IS NULL",
                (now, execution.run_id),
            )
            job = self.conn.execute(
                "UPDATE jobs SET status='DONE',last_error=NULL,lease_owner=NULL,"
                "lease_expires_at=NULL,updated_at=?,finished_at=?,reserved_cost_usd=0,"
                "budget_reserved_at=NULL WHERE id=? AND run_id=? AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                (now, now, execution.job_id, execution.run_id,
                 execution.lease_owner, now),
            )
            if any(cursor.rowcount != 1 for cursor in (attempt, run, job)):
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return retrieval
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def fail_controlled_fetch_execution(
        self, execution: JobExecutionContext, error: str, *,
        document: FetchedDocument | None = None,
    ) -> ControlledFetchFailureOutcome:
        """Deterministic failure boundary of one controlled fetch execution.

        Bez attemptu i przy RESERVED wynik jest jednoznaczny (żaden request nie
        wyszedł) → terminalny FAILED. Po REQUEST_STARTED typowany dokument
        błędu również terminalizuje FAILED (request odbył się i zawiódł);
        brak typowanego wyniku = niejednoznaczność → NEEDS_VERIFICATION bez
        automatycznego ponowienia.
        """
        safe_error = " ".join(error.split())[:240] or "CONTROLLED_FETCH_FAILED"
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_controlled_fetch_fence(execution, now)
            attempt_row = self.conn.execute(
                "SELECT * FROM controlled_fetch_attempts WHERE job_id=?",
                (execution.job_id,),
            ).fetchone()

            def _terminal_run() -> None:
                run = self.conn.execute(
                    "UPDATE runs SET status='FAILED',error=?,cost_usd=0,finished_at=? "
                    "WHERE id=? AND status='RUNNING' AND finished_at IS NULL",
                    (safe_error, now, execution.run_id),
                )
                if run.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)

            def _terminal_job(status: JobStatus, *, release_budget: bool) -> None:
                fields = (
                    ",finished_at=?,reserved_cost_usd=0,budget_reserved_at=NULL"
                    if release_budget else ""
                )
                params: list[object] = [status.value, safe_error, now]
                if release_budget:
                    params.append(now)
                params.extend([
                    execution.job_id, execution.run_id, execution.lease_owner, now,
                ])
                job = self.conn.execute(
                    "UPDATE jobs SET status=?,last_error=?,lease_owner=NULL,"
                    "lease_expires_at=NULL,updated_at=?" + fields +
                    " WHERE id=? AND run_id=? AND lease_owner=? "
                    "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING')",
                    tuple(params),
                )
                if job.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)

            if attempt_row is None:
                _terminal_run()
                _terminal_job(JobStatus.FAILED, release_budget=True)
                self.conn.commit()
                return ControlledFetchFailureOutcome.FAILED_NO_ATTEMPT

            status = ControlledFetchAttemptStatus(attempt_row["status"])
            if status is ControlledFetchAttemptStatus.RESERVED:
                attempt = self.conn.execute(
                    "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                    "outcome_reason=? WHERE id=? AND status=?",
                    (
                        ControlledFetchAttemptStatus.FAILED.value, now, safe_error,
                        attempt_row["id"], ControlledFetchAttemptStatus.RESERVED.value,
                    ),
                )
                if attempt.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
                _terminal_run()
                _terminal_job(JobStatus.FAILED, release_budget=True)
                self.conn.commit()
                return ControlledFetchFailureOutcome.FAILED_BEFORE_REQUEST

            if status is ControlledFetchAttemptStatus.REQUEST_STARTED:
                retrieval_id: int | None = None
                if document is not None:
                    retrieval = build_evidence_retrieval(
                        document, account_id=fence["job_account_id"],
                        now=execution.now(),
                    )
                    if retrieval.status is EvidenceRetrievalStatus.FAILED:
                        retrieval_id = self._insert_controlled_fetch_retrieval(
                            retrieval,
                        ).id
                    else:
                        # Dokument klasyfikuje się jako OK — to nie jest typowany
                        # błąd; wynik pozostaje niejednoznaczny dla tej granicy.
                        document = None
                if document is not None:
                    attempt = self.conn.execute(
                        "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                        "retrieval_id=?,outcome_reason=? WHERE id=? AND status=?",
                        (
                            ControlledFetchAttemptStatus.FAILED.value, now,
                            retrieval_id, safe_error, attempt_row["id"],
                            ControlledFetchAttemptStatus.REQUEST_STARTED.value,
                        ),
                    )
                    if attempt.rowcount != 1:
                        raise StaleJobExecutionError(execution.job_id)
                    _terminal_run()
                    _terminal_job(JobStatus.FAILED, release_budget=True)
                    self.conn.commit()
                    return ControlledFetchFailureOutcome.FAILED_AFTER_REQUEST
                attempt = self.conn.execute(
                    "UPDATE controlled_fetch_attempts SET status=?,terminalized_at=?,"
                    "outcome_reason=? WHERE id=? AND status=?",
                    (
                        ControlledFetchAttemptStatus.NEEDS_VERIFICATION.value, now,
                        safe_error, attempt_row["id"],
                        ControlledFetchAttemptStatus.REQUEST_STARTED.value,
                    ),
                )
                if attempt.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
                _terminal_run()
                _terminal_job(JobStatus.NEEDS_VERIFICATION, release_budget=False)
                self.conn.commit()
                return ControlledFetchFailureOutcome.ESCALATED_NEEDS_VERIFICATION

            # Attempt terminalny przy żywym fence nie powstaje w żadnej naszej
            # transakcji; pozostawiamy stan operatorowi bez dalszych mutacji.
            self.conn.commit()
            return ControlledFetchFailureOutcome.ALREADY_TERMINALIZED
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    # --- Lokalny fundament evidence (Etap 2, fala E1; ADR-099 + ADR-100) ---
    # Warstwa NIE jest zintegrowana z pipeline'em researchu w tej fali.
    # Publiczna ścieżka zapisu retrievalu przyjmuje wyłącznie surowy
    # FetchedDocument — wszystkie hashe wylicza recorder; excerpt przechodzi
    # przez deterministyczny weryfikator. Podłogi SQLite migracji 0016 bronią
    # tych samych relacji przed raw writerem. Wszystkie operacje działają w
    # jawnym zakresie jednego konta.

    # --- Evidence research approval (Etap 2, fala E3) ---
    # Jednorazowa zgoda L1 EVIDENCE_RESEARCH żyje w TEJ SAMEJ tabeli co zgody
    # controlled fetch (0019 generalizuje 0018 — brak nowej rodziny tabel).
    # Wiersz zgody trwale przechowuje pełny kanoniczny execution_intent JSON
    # (preimage fingerprintu), więc autorytatywny evidence input przeżywa
    # restart i każdą późniejszą mutację jobs.payload_json. Konsumpcja odbywa
    # się atomowo w transakcji `begin_provider_attempt`.

    @staticmethod
    def _evidence_research_approval_from_row(row: sqlite3.Row) -> EvidenceResearchApproval:
        return EvidenceResearchApproval(
            id=int(row["id"]), job_id=row["job_id"], account_id=row["account_id"],
            topic_id=int(row["topic_id"]), action_type=row["action_type"],
            intent_fingerprint=row["intent_fingerprint"],
            execution_intent_json=row["execution_intent_json"],
            approved_by=row["approved_by"], approved_at=row["approved_at"],
            expires_at=row["expires_at"], consumed_at=row["consumed_at"],
        )

    def get_evidence_research_approval_for_job(
        self, job_id: str,
    ) -> EvidenceResearchApproval | None:
        row = self.conn.execute(
            "SELECT * FROM controlled_fetch_approvals WHERE job_id=? AND action_type=?",
            (job_id, EVIDENCE_RESEARCH_ACTION_TYPE),
        ).fetchone()
        return None if row is None else self._evidence_research_approval_from_row(row)

    def _frozen_evidence_contract_from_payload(
        self, payload_text: str, job_id: str,
    ) -> tuple[DurableResearchExecutionIntent, str, str]:
        """Re-derive (intent, canonical JSON, fingerprint) from one payload text."""
        try:
            payload = json.loads(payload_text)
            if not isinstance(payload, dict):
                raise EvidenceResearchAuthorizationError(
                    "INTENT_INVALID", f"job {job_id!r} payload is not a JSON object.",
                )
            canonical = canonicalize_durable_research_payload(payload)
            intent_raw = canonical["execution_intent"]
            assert isinstance(intent_raw, dict)
            intent = DurableResearchExecutionIntent.from_payload(intent_raw)
            intent_json, fingerprint = frozen_execution_intent_json(payload)
        except (json.JSONDecodeError, TypeError, DurableExecutionIntentError) as exc:
            raise EvidenceResearchAuthorizationError(
                "INTENT_INVALID", f"job {job_id!r} payload is not a valid durable intent.",
            ) from exc
        if intent.evidence_input is None:
            raise EvidenceResearchAuthorizationError(
                "INTENT_NOT_EVIDENCE",
                f"job {job_id!r} durable intent carries no evidence_input.",
            )
        return intent, intent_json, fingerprint

    def _validate_evidence_rows(
        self, account_id: str, evidence_input: dict[str, object],
    ) -> list[sqlite3.Row]:
        """Fail-closed comparison of the frozen evidence entries with the rows.

        Każdy wpis intentu musi wskazywać ISTNIEJĄCY retrieval tego samego
        konta w statusie OK, którego kanon zgadza się literalnie (hash zapisany
        i hash PRZELICZONY z utrwalonego tekstu) i długościowo z zamrożonym
        kontraktem; limity corpusu są rewalidowane w całości.
        """
        retrievals = evidence_input["retrievals"]
        assert isinstance(retrievals, list)
        rows: list[sqlite3.Row] = []
        total_chars = 0
        for entry in retrievals:
            retrieval_id = int(entry["retrieval_id"])
            expected_sha = str(entry["canonical_sha256"])
            expected_chars = int(entry["canonical_chars"])
            row = self.conn.execute(
                "SELECT * FROM evidence_retrievals WHERE id=? AND account_id=?",
                (retrieval_id, account_id),
            ).fetchone()
            if row is None:
                raise EvidenceResearchAuthorizationError(
                    "EVIDENCE_RETRIEVAL_MISSING",
                    f"retrieval id={retrieval_id} does not exist for this account.",
                )
            if row["status"] != EvidenceRetrievalStatus.OK.value:
                raise EvidenceResearchAuthorizationError(
                    "EVIDENCE_RETRIEVAL_NOT_OK",
                    f"retrieval id={retrieval_id} status={row['status']} is not usable.",
                )
            canonical_text = row["canonical_text"]
            if (
                row["canonical_sha256"] != expected_sha
                or sha256_hex(canonical_text) != expected_sha
            ):
                raise EvidenceResearchAuthorizationError(
                    "EVIDENCE_HASH_MISMATCH",
                    f"retrieval id={retrieval_id} canonical hash diverged from the frozen intent.",
                )
            if (
                int(row["canonical_chars"]) != expected_chars
                or len(canonical_text) != expected_chars
            ):
                raise EvidenceResearchAuthorizationError(
                    "EVIDENCE_CHARS_MISMATCH",
                    f"retrieval id={retrieval_id} canonical size diverged from the frozen intent.",
                )
            if expected_chars > MAX_EVIDENCE_CHARS_PER_RETRIEVAL:
                raise EvidenceResearchAuthorizationError(
                    "EVIDENCE_CORPUS_LIMIT_EXCEEDED",
                    f"retrieval id={retrieval_id} exceeds the per-retrieval character limit.",
                )
            total_chars += expected_chars
            rows.append(row)
        if total_chars > MAX_EVIDENCE_TOTAL_CHARS:
            raise EvidenceResearchAuthorizationError(
                "EVIDENCE_CORPUS_LIMIT_EXCEEDED",
                f"evidence corpus of {total_chars} characters exceeds the total limit.",
            )
        return rows

    def _require_usable_evidence_research_approval(
        self, job_id: str, *, account_id: str, topic_id: int,
        canonical_intent_json: str, intent_fingerprint: str, current_ts: str,
        require_consumed: bool = False,
    ) -> sqlite3.Row:
        """One closed matrix of approval refusals, shared by every caller."""
        row = self.conn.execute(
            "SELECT * FROM controlled_fetch_approvals WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_MISSING", "no L1 evidence research approval exists for this job.",
            )
        if row["action_type"] != EVIDENCE_RESEARCH_ACTION_TYPE:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_ACTION_MISMATCH",
                "the job approval is not an EVIDENCE_RESEARCH approval.",
            )
        if row["account_id"] != account_id:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_ACCOUNT_MISMATCH", "approval account does not own the job.",
            )
        if int(row["topic_id"]) != int(topic_id):
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_TOPIC_MISMATCH", "approval topic does not match the job.",
            )
        if require_consumed:
            if row["consumed_at"] is None:
                raise EvidenceResearchAuthorizationError(
                    "APPROVAL_NOT_CONSUMED",
                    "the approval was not consumed by this execution.",
                )
        elif row["consumed_at"] is not None:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_ALREADY_CONSUMED", "the one-shot approval was already consumed.",
            )
        if str(row["expires_at"]) <= current_ts and not require_consumed:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_EXPIRED", "the approval expired before execution.",
            )
        if (
            row["intent_fingerprint"] != intent_fingerprint
            or row["execution_intent_json"] != canonical_intent_json
        ):
            raise EvidenceResearchAuthorizationError(
                "INTENT_MISMATCH",
                "the current job payload diverged from the approved frozen intent.",
            )
        return row

    def record_evidence_research_approval(
        self, *, job_id: str, account_id: str, approved_by: str,
        expires_at: datetime, clock: Clock,
    ) -> EvidenceResearchApproval:
        """L1: derive the approval entirely from the frozen durable job contract.

        Fingerprint i pełny kanoniczny execution_intent JSON NIE są przyjmowane
        od wywołującego — pochodzą wyłącznie z kanonizowanego payloadu joba,
        więc zgoda nigdy nie może opisywać czegoś innego niż wykonywany
        kontrakt; retrievale są walidowane względem bazy już przy zgodzie.
        """
        if not approved_by.strip():
            raise EvidenceResearchAuthorizationError(
                "APPROVER_MISSING", "approved_by must identify the human L1 operator.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now_dt = self._job_now(clock=clock)
            now = _persisted_ts(now_dt)
            expiry_dt = self._job_now(expires_at)
            if expiry_dt <= now_dt:
                raise EvidenceResearchAuthorizationError(
                    "APPROVAL_EXPIRY_INVALID", "expires_at must be in the future.",
                )
            row = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise EvidenceResearchAuthorizationError(
                    "JOB_MISSING", f"job {job_id!r} does not exist.",
                )
            job = self._job_from_row(row)
            intent, intent_json, fingerprint = self._frozen_evidence_contract_from_payload(
                row["payload_json"], job_id,
            )
            if job.account_id != account_id or intent.account_id != account_id:
                raise EvidenceResearchAuthorizationError(
                    "ACCOUNT_MISMATCH", "approval account must own the frozen job contract.",
                )
            if job.topic_id is None or int(job.topic_id) != intent.topic_id:
                raise EvidenceResearchAuthorizationError(
                    "TOPIC_MISMATCH", "job topic must match the frozen intent.",
                )
            if job.status is not JobStatus.QUEUED:
                raise EvidenceResearchAuthorizationError(
                    "JOB_NOT_APPROVABLE",
                    f"approval must precede execution; job status is {job.status.value}.",
                )
            if self.conn.execute(
                "SELECT 1 FROM controlled_fetch_approvals WHERE job_id=?", (job_id,),
            ).fetchone() is not None:
                raise EvidenceResearchAuthorizationError(
                    "APPROVAL_ALREADY_EXISTS", "the job already carries its one approval.",
                )
            assert intent.evidence_input is not None
            self._validate_evidence_rows(account_id, intent.evidence_input)
            cursor = self.conn.execute(
                "INSERT INTO controlled_fetch_approvals (job_id,account_id,action_type,"
                "requested_url,intent_fingerprint,timeout_seconds,max_bytes,max_redirects,"
                "topic_id,execution_intent_json,approved_by,approved_at,expires_at,"
                "consumed_at) VALUES (?,?,?,NULL,?,NULL,NULL,NULL,?,?,?,?,?,NULL)",
                (
                    job_id, account_id, EVIDENCE_RESEARCH_ACTION_TYPE,
                    fingerprint, intent.topic_id, intent_json,
                    approved_by.strip(), now, _persisted_ts(expiry_dt),
                ),
            )
            approval_id = int(cursor.lastrowid)
            stored = self.conn.execute(
                "SELECT * FROM controlled_fetch_approvals WHERE id=?", (approval_id,),
            ).fetchone()
            self.conn.commit()
            assert stored is not None
            return self._evidence_research_approval_from_row(stored)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _consume_evidence_research_approval(
        self, execution: JobExecutionContext, intent: DurableResearchExecutionIntent,
        *, canonical_intent_json: str, intent_fingerprint: str, current_ts: str,
    ) -> None:
        """Atomic one-shot consumption inside the reservation transaction.

        Wywoływane WYŁĄCZNIE z `begin_provider_attempt` (ta sama transakcja co
        INSERT RESERVED). Każda odmowa wycofuje całą transakcję — zero
        konsumpcji, zero attemptu.
        """
        assert intent.evidence_input is not None
        approval_row = self._require_usable_evidence_research_approval(
            execution.job_id,
            account_id=intent.account_id,
            topic_id=intent.topic_id,
            canonical_intent_json=canonical_intent_json,
            intent_fingerprint=intent_fingerprint,
            current_ts=current_ts,
        )
        self._validate_evidence_rows(intent.account_id, intent.evidence_input)
        consumed = self.conn.execute(
            "UPDATE controlled_fetch_approvals SET consumed_at=? "
            "WHERE id=? AND consumed_at IS NULL",
            (current_ts, approval_row["id"]),
        )
        if consumed.rowcount != 1:
            raise EvidenceResearchAuthorizationError(
                "APPROVAL_CONSUME_RACE", "approval consumption compare-and-swap failed.",
            )

    # --- TOPIC_GENERATION: zgoda L1, run, lineage, finalizacja i granica błędu ---

    def _topic_generation_usage_total(self, run_id: str) -> Decimal:
        rows = self.conn.execute(
            "SELECT estimated_cost_usd FROM model_usage WHERE run_id=? AND task=?",
            (run_id, TOPIC_GENERATION_USAGE_TASK),
        ).fetchall()
        return _sum_money_rows(
            rows, "estimated_cost_usd",
            label="Canonical topic generation usage total",
        )

    def _set_run_cost_from_topic_generation_usage(self, run_id: str) -> None:
        total = self._topic_generation_usage_total(run_id)
        cursor = self.conn.execute(
            "UPDATE runs SET cost_usd=? WHERE id=?", (float(total), run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                f"Nie znaleziono run #{run_id} do synchronizacji kosztu tematów."
            )

    @staticmethod
    def _topic_generation_approval_from_row(
        row: sqlite3.Row,
    ) -> TopicGenerationApproval:
        return TopicGenerationApproval(
            id=int(row["id"]), job_id=row["job_id"], account_id=row["account_id"],
            intent_fingerprint=row["intent_fingerprint"],
            execution_intent_json=row["execution_intent_json"],
            model=row["model"], cap_usd=row["cap_usd"],
            max_tokens=int(row["max_tokens"]),
            approved_by=row["approved_by"], approved_at=row["approved_at"],
            expires_at=row["expires_at"], consumed_at=row["consumed_at"],
        )

    @staticmethod
    def _generated_topic_from_row(row: sqlite3.Row) -> GeneratedTopicLineage:
        return GeneratedTopicLineage(
            id=int(row["id"]), topic_id=int(row["topic_id"]),
            account_id=row["account_id"], job_id=row["job_id"],
            run_id=row["run_id"], request_id=row["request_id"],
            candidate_index=int(row["candidate_index"]),
            is_selected=bool(row["is_selected"]), created_at=row["created_at"],
        )

    def _frozen_topic_generation_contract_from_payload(
        self, payload_text: str, job_id: str,
    ) -> tuple[DurableTopicGenerationIntent, str, str]:
        """Re-derive (intent, canonical JSON, fingerprint) from one payload text."""
        try:
            payload = json.loads(payload_text)
            if not isinstance(payload, dict):
                raise DurableExecutionIntentError(
                    "persisted topic generation payload must be a JSON object."
                )
            intent, intent_json, fingerprint = frozen_topic_generation_contract(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise TopicGenerationAuthorizationError(
                "MALFORMED_TOPIC_GENERATION_PAYLOAD",
                f"job {job_id!r} does not carry a valid frozen topic generation payload.",
            ) from exc
        except DurableExecutionIntentError as exc:
            raise TopicGenerationAuthorizationError(exc.code, str(exc)) from exc
        return intent, intent_json, fingerprint

    def record_topic_generation_approval(
        self, *, job_id: str, account_id: str, approved_by: str,
        expires_at: datetime, clock: Clock,
    ) -> TopicGenerationApproval:
        """L1: derive the approval entirely from the frozen durable job contract.

        Model, cap, max_tokens, fingerprint i pełny kanoniczny execution_intent
        JSON NIE są przyjmowane od wywołującego — pochodzą wyłącznie z
        kanonizowanego payloadu joba, więc zgoda nigdy nie może opisywać czegoś
        innego niż kontrakt, który zostanie wykonany.
        """
        if not approved_by.strip():
            raise TopicGenerationAuthorizationError(
                "APPROVER_MISSING", "approved_by must identify the human L1 operator.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now_dt = self._job_now(clock=clock)
            now = _persisted_ts(now_dt)
            expiry_dt = self._job_now(expires_at)
            if expiry_dt <= now_dt:
                raise TopicGenerationAuthorizationError(
                    "APPROVAL_EXPIRY_INVALID", "expires_at must be in the future.",
                )
            row = self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if row is None:
                raise TopicGenerationAuthorizationError(
                    "JOB_MISSING", f"job {job_id!r} does not exist.",
                )
            job = self._job_from_row(row)
            intent, intent_json, fingerprint = (
                self._frozen_topic_generation_contract_from_payload(
                    row["payload_json"], job_id,
                )
            )
            if job.account_id != account_id or intent.account_id != account_id:
                raise TopicGenerationAuthorizationError(
                    "ACCOUNT_MISMATCH", "approval account must own the frozen job contract.",
                )
            if (
                job.kind is not JobKind.TOPIC_GENERATION
                or job.workflow is not WorkflowType.TOPIC_GENERATION
            ):
                raise TopicGenerationAuthorizationError(
                    "JOB_KIND_MISMATCH",
                    "approval requires a TOPIC_GENERATION job and workflow.",
                )
            if job.topic_id is not None:
                raise TopicGenerationAuthorizationError(
                    "TOPIC_ID_FORBIDDEN",
                    "a topic generation job must not reference a topic.",
                )
            if job.status is not JobStatus.QUEUED:
                raise TopicGenerationAuthorizationError(
                    "JOB_NOT_APPROVABLE",
                    f"approval must precede execution; job status is {job.status.value}.",
                )
            if self.conn.execute(
                "SELECT 1 FROM topic_generation_approvals WHERE job_id=?", (job_id,),
            ).fetchone() is not None:
                raise TopicGenerationAuthorizationError(
                    "APPROVAL_ALREADY_EXISTS", "the job already carries its one approval.",
                )
            cursor = self.conn.execute(
                "INSERT INTO topic_generation_approvals (job_id,account_id,"
                "intent_fingerprint,execution_intent_json,model,cap_usd,max_tokens,"
                "approved_by,approved_at,expires_at,consumed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    job_id, account_id, fingerprint, intent_json, intent.model,
                    intent.cap_usd, intent.max_tokens, approved_by.strip(), now,
                    _persisted_ts(expiry_dt),
                ),
            )
            stored = self.conn.execute(
                "SELECT * FROM topic_generation_approvals WHERE id=?",
                (int(cursor.lastrowid),),
            ).fetchone()
            self.conn.commit()
            assert stored is not None
            return self._topic_generation_approval_from_row(stored)
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def get_topic_generation_approval_for_job(
        self, job_id: str,
    ) -> TopicGenerationApproval | None:
        row = self.conn.execute(
            "SELECT * FROM topic_generation_approvals WHERE job_id=?", (job_id,),
        ).fetchone()
        return None if row is None else self._topic_generation_approval_from_row(row)

    def _require_usable_topic_generation_approval(
        self, job_id: str, *, account_id: str, model: str, cap_usd: str,
        max_tokens: int, canonical_intent_json: str, intent_fingerprint: str,
        current_ts: str, require_consumed: bool = False,
    ) -> sqlite3.Row:
        """One closed matrix of approval refusals, shared by every caller."""
        row = self.conn.execute(
            "SELECT * FROM topic_generation_approvals WHERE job_id=?", (job_id,),
        ).fetchone()
        if row is None:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_MISSING",
                "no L1 topic generation approval exists for this job.",
            )
        if row["account_id"] != account_id:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_ACCOUNT_MISMATCH", "approval account does not own the job.",
            )
        if row["model"] != model:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_MODEL_MISMATCH",
                "the approved model differs from the frozen intent model.",
            )
        # A cap may only ever shrink relative to what a human approved; a higher
        # cap is a different, unapproved financial exposure.
        if _money(row["cap_usd"], positive=True, label="Approved cap") < _money(
            cap_usd, positive=True, label="Frozen intent cap",
        ):
            raise TopicGenerationAuthorizationError(
                "APPROVAL_CAP_EXCEEDED",
                "the frozen intent cap exceeds the approved cap.",
            )
        if int(row["max_tokens"]) != int(max_tokens):
            raise TopicGenerationAuthorizationError(
                "APPROVAL_MAX_TOKENS_MISMATCH",
                "the approved max_tokens differs from the frozen intent.",
            )
        if require_consumed:
            if row["consumed_at"] is None:
                raise TopicGenerationAuthorizationError(
                    "APPROVAL_NOT_CONSUMED",
                    "the approval was not consumed by this execution.",
                )
        elif row["consumed_at"] is not None:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_ALREADY_CONSUMED",
                "the one-shot approval was already consumed.",
            )
        if str(row["expires_at"]) <= current_ts and not require_consumed:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_EXPIRED", "the approval expired before execution.",
            )
        if (
            row["intent_fingerprint"] != intent_fingerprint
            or row["execution_intent_json"] != canonical_intent_json
        ):
            raise TopicGenerationAuthorizationError(
                "INTENT_MISMATCH",
                "the current job payload diverged from the approved frozen intent.",
            )
        return row

    def _consume_topic_generation_approval(
        self, execution: JobExecutionContext,
        intent: DurableTopicGenerationIntent, *, canonical_intent_json: str,
        intent_fingerprint: str, current_ts: str,
    ) -> None:
        """Atomic one-shot consumption inside the reservation transaction.

        Wywoływane WYŁĄCZNIE z `begin_provider_attempt` (ta sama transakcja co
        INSERT RESERVED). Każda odmowa wycofuje całą transakcję — zero
        konsumpcji, zero attemptu, zero requestu, zero kosztu.
        """
        approval_row = self._require_usable_topic_generation_approval(
            execution.job_id,
            account_id=intent.account_id,
            model=intent.model,
            cap_usd=intent.cap_usd,
            max_tokens=intent.max_tokens,
            canonical_intent_json=canonical_intent_json,
            intent_fingerprint=intent_fingerprint,
            current_ts=current_ts,
        )
        consumed = self.conn.execute(
            "UPDATE topic_generation_approvals SET consumed_at=? "
            "WHERE id=? AND consumed_at IS NULL",
            (current_ts, approval_row["id"]),
        )
        if consumed.rowcount != 1:
            raise TopicGenerationAuthorizationError(
                "APPROVAL_CONSUME_RACE", "approval consumption compare-and-swap failed.",
            )

    def initialize_topic_generation_run_for_job(
        self, job_id: str, lease_owner: str, run_id: str, *, clock: Clock,
    ) -> TopicGenerationInitialization:
        """Create or resume the one TOPIC_GENERATION run under a fresh lease."""
        if not run_id.strip() or not lease_owner.strip():
            raise ValueError("topic generation identifiers must be non-empty.")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = _persisted_ts(self._job_now(clock=clock))
            row = self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            if row is None:
                raise JobRunRelationError(
                    "JOB_MISSING", job_id, "topic generation job is missing.",
                )
            job = self._job_from_row(row)
            try:
                payload = canonicalize_topic_generation_payload(job.payload)
            except DurableExecutionIntentError as exc:
                raise JobRunRelationError(
                    "TOPIC_GENERATION_INTENT_INVALID", job_id, str(exc),
                ) from exc
            if (
                job.kind is not JobKind.TOPIC_GENERATION
                or job.workflow is not WorkflowType.TOPIC_GENERATION
                or job.topic_id is not None
                or payload["account_id"] != job.account_id
            ):
                raise JobRunRelationError(
                    "TOPIC_GENERATION_IDENTITY_MISMATCH", job_id,
                    "job, payload and account identity must match, without a topic.",
                )
            if (
                job.status not in (JobStatus.LEASED, JobStatus.RUNNING)
                or job.lease_owner != lease_owner
                or job.lease_expires_at is None
                or _persisted_ts(job.lease_expires_at) < now
            ):
                raise StaleJobExecutionError(job_id)

            if job.run_id is None:
                self.conn.execute(
                    "INSERT INTO runs (id,account_id,workflow,status,current_state,"
                    "started_at,cost_usd) VALUES (?,?,?,?,?,?,0)",
                    (
                        run_id, job.account_id, WorkflowType.TOPIC_GENERATION.value,
                        RunStatus.RUNNING.value, "generate", now,
                    ),
                )
                cursor = self.conn.execute(
                    "UPDATE jobs SET run_id=?,updated_at=? WHERE id=? AND run_id IS NULL "
                    "AND lease_owner=? AND lease_expires_at>=? "
                    "AND status IN ('LEASED','RUNNING')",
                    (run_id, now, job_id, lease_owner, now),
                )
                if cursor.rowcount != 1:
                    raise StaleJobExecutionError(job_id)
                created = True
                attached_run_id = run_id
            else:
                created = False
                attached_run_id = job.run_id

            run_row = self.conn.execute(
                "SELECT * FROM runs WHERE id=?", (attached_run_id,),
            ).fetchone()
            if run_row is None:
                raise JobRunRelationError(
                    "ATTACHED_TOPIC_GENERATION_RUN_MISSING", job_id,
                    "topic generation run relation is incomplete.",
                )
            run = self._run_from_row(run_row)
            if (
                run.account_id != job.account_id
                or run.workflow is not WorkflowType.TOPIC_GENERATION
                or run.status is not RunStatus.RUNNING
                or run_row["finished_at"] is not None
            ):
                raise JobRunRelationError(
                    "ATTACHED_TOPIC_GENERATION_RUN_INVALID", job_id,
                    "attached topic generation run is not resumable.",
                )
            refreshed = self.conn.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
            assert refreshed is not None
            self.conn.commit()
            return TopicGenerationInitialization(
                job=self._job_from_row(refreshed), run=run, created=created,
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def assert_topic_generation_execution_active(
        self, execution: JobExecutionContext, *,
        expected_intent_fingerprint: str | None = None,
    ) -> None:
        """Fresh fence check; optionally re-proves the frozen intent identity."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            self._require_topic_generation_fence(execution, current_ts)
            if expected_intent_fingerprint is not None:
                row = self.conn.execute(
                    "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
                ).fetchone()
                if row is None:
                    raise StaleJobExecutionError(execution.job_id)
                intent, intent_json, fingerprint = (
                    self._frozen_topic_generation_contract_from_payload(
                        row["payload_json"], execution.job_id,
                    )
                )
                if fingerprint != expected_intent_fingerprint:
                    raise TopicGenerationAuthorizationError(
                        "INTENT_MISMATCH",
                        "the durable intent changed after the reservation.",
                    )
                # The consumed approval must still be the one that authorized
                # exactly this frozen contract.
                self._require_usable_topic_generation_approval(
                    execution.job_id,
                    account_id=intent.account_id,
                    model=intent.model,
                    cap_usd=intent.cap_usd,
                    max_tokens=intent.max_tokens,
                    canonical_intent_json=intent_json,
                    intent_fingerprint=fingerprint,
                    current_ts=current_ts,
                    require_consumed=True,
                )
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def list_generated_topics_for_run(
        self, run_id: str,
    ) -> list[GeneratedTopicLineage]:
        rows = self.conn.execute(
            "SELECT * FROM generated_topics WHERE run_id=? ORDER BY candidate_index",
            (run_id,),
        ).fetchall()
        return [self._generated_topic_from_row(row) for row in rows]

    def finalize_topic_generation_success(
        self, execution: JobExecutionContext, *, request_id: str,
        candidates: Sequence[TopicGenerationCandidate], total_cost_usd: float,
    ) -> list[GeneratedTopicLineage]:
        """One transaction: topics, lineage, settlement, run cost, terminal job.

        Repeating the exact same finalization is refused rather than partially
        applied: the fence requires a live lease and an unfinished run, both of
        which the first successful call has already cleared.
        """
        if not candidates:
            raise ValueError("topic generation finalization requires candidates.")
        selected = [c for c in candidates if c.is_selected]
        if len(selected) > 1:
            raise TopicGenerationResultError(
                "MULTIPLE_SELECTED",
                "one topic generation execution may select at most one topic.",
            )
        indexes = [c.candidate_index for c in candidates]
        if sorted(indexes) != list(range(len(candidates))):
            raise TopicGenerationResultError(
                "CANDIDATE_INDEX_INVALID",
                "candidate indexes must be a dense zero-based ranking.",
            )
        if any(c.topic.id is not None for c in candidates):
            raise TopicGenerationResultError(
                "CANDIDATE_PREPERSISTED",
                "a finalization candidate must not be pre-persisted.",
            )
        original_ids = [c.topic.id for c in candidates]
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(execution.now())
            current_ts = _persisted_ts(current)
            fence = self._require_topic_generation_fence(execution, current_ts)
            if fence["run_status"] != RunStatus.RUNNING.value:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "topic generation run is no longer finalizable.",
                )
            account_id = fence["run_account_id"]
            attempt = self.conn.execute(
                "SELECT * FROM provider_attempts WHERE request_id=? AND job_id=?",
                (request_id, execution.job_id),
            ).fetchone()
            if attempt is None or attempt["status"] != (
                ProviderAttemptStatus.SETTLED.value
            ):
                raise StaleJobExecutionError(
                    execution.job_id,
                    "topic generation finalization requires its settled attempt.",
                )
            canonical = self._topic_generation_usage_total(execution.run_id)
            if canonical != _money(
                total_cost_usd, positive=False,
                label="Topic generation finalization cost",
            ):
                raise TopicGenerationResultError(
                    "COST_MISMATCH",
                    "finalization cost must equal canonical model usage.",
                )
            lineage: list[GeneratedTopicLineage] = []
            for candidate in sorted(candidates, key=lambda c: c.candidate_index):
                topic = candidate.topic
                if topic.account_id != account_id:
                    raise TopicGenerationResultError(
                        "CANDIDATE_ACCOUNT_MISMATCH",
                        "a generated topic must belong to the executing account.",
                    )
                stored = self._insert_topic(topic)
                cursor = self.conn.execute(
                    "INSERT INTO generated_topics (topic_id,account_id,job_id,run_id,"
                    "request_id,candidate_index,is_selected,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        int(stored.id), account_id, execution.job_id,
                        execution.run_id, request_id, candidate.candidate_index,
                        int(bool(candidate.is_selected)), current_ts,
                    ),
                )
                row = self.conn.execute(
                    "SELECT * FROM generated_topics WHERE id=?",
                    (int(cursor.lastrowid),),
                ).fetchone()
                assert row is not None
                lineage.append(self._generated_topic_from_row(row))

            run_cursor = self.conn.execute(
                "UPDATE runs SET status='SUCCESS',cost_usd=?,error=NULL,finished_at=? "
                "WHERE id=? AND status='RUNNING' AND finished_at IS NULL AND EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=runs.id AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    float(canonical), current_ts, execution.run_id,
                    execution.job_id, execution.lease_owner, current_ts,
                ),
            )
            job_cursor = self.conn.execute(
                "UPDATE jobs SET status='DONE',last_error=NULL,lease_owner=NULL,"
                "lease_expires_at=NULL,updated_at=?,finished_at=?,"
                "reserved_cost_usd=0.0,budget_reserved_at=NULL WHERE id=? "
                "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING')",
                (
                    current_ts, current_ts, execution.job_id, execution.run_id,
                    execution.lease_owner, current_ts,
                ),
            )
            if run_cursor.rowcount != 1 or job_cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return lineage
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            for candidate, original in zip(candidates, original_ids):
                candidate.topic.id = original
            raise

    def fail_or_escalate_topic_generation_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False, preserve_for_verification: bool = False,
    ) -> ResearchExecutionFailureOutcome:
        """Atomically fail a safe execution or expose its active attempt.

        Mirrors the research boundary contract exactly: RESERVED,
        REQUEST_STARTED and NEEDS_RECONCILIATION are never hidden behind a
        terminal job state, the reservation is retained on escalation, and no
        second provider attempt can ever follow.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            lifecycle = self.conn.execute(
                "SELECT j.status AS job_status,j.run_id,j.lease_owner,"
                "j.lease_expires_at,r.status AS run_status "
                "FROM jobs j JOIN runs r ON r.id=j.run_id "
                "WHERE j.id=? AND j.run_id=? AND j.kind='TOPIC_GENERATION'",
                (execution.job_id, execution.run_id),
            ).fetchone()
            if lifecycle is None:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "topic generation lifecycle relation no longer exists.",
                )
            active_attempts = self.conn.execute(
                "SELECT request_id,status FROM provider_attempts WHERE job_id=? "
                "AND status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION') "
                "ORDER BY stage,attempt_no",
                (execution.job_id,),
            ).fetchall()
            if len(active_attempts) > 1:
                raise ProviderAttemptReconciliationError(
                    "Topic generation has multiple active provider attempts."
                )

            if active_attempts:
                active = active_attempts[0]
                attempt_status = ProviderAttemptStatus(active["status"])
                already_preserved = (
                    lifecycle["job_status"] == JobStatus.NEEDS_VERIFICATION.value
                )
                if attempt_status is ProviderAttemptStatus.NEEDS_RECONCILIATION:
                    if already_preserved:
                        self.conn.commit()
                        return (
                            ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION
                        )
                    if lifecycle["job_status"] not in _EXECUTABLE_JOB_STATUSES:
                        raise ProviderAttemptReconciliationError(
                            "Active reconciliation is hidden behind a non-reviewable job state."
                        )
                    self._require_topic_generation_fence(execution, current_ts)
                    self._preserve_topic_generation_job(execution, error, current_ts)
                    self.conn.commit()
                    return ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION

                if already_preserved:
                    if lifecycle["lease_owner"] is not None or \
                            lifecycle["lease_expires_at"] is not None:
                        raise ProviderAttemptReconciliationError(
                            "A reviewable job must not retain an execution lease."
                        )
                    run_status = lifecycle["run_status"]
                else:
                    fence = self._require_topic_generation_fence(execution, current_ts)
                    run_status = fence["run_status"]
                if run_status != RunStatus.RUNNING.value:
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "topic generation lifecycle is no longer mutable by this execution.",
                    )
                reason = (
                    _UNEXPECTED_FAILURE_BEFORE_REQUEST_STARTED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else _UNEXPECTED_FAILURE_AFTER_REQUEST_STARTED
                )
                financial = (
                    FinancialResolution.NOT_CHARGED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else FinancialResolution.CHARGE_UNKNOWN
                )
                attempt_cursor = self.conn.execute(
                    "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',"
                    "error_code=? WHERE request_id=? AND status=?",
                    (reason, active["request_id"], attempt_status.value),
                )
                if attempt_cursor.rowcount != 1:
                    raise ProviderAttemptReconciliationError(
                        "Provider attempt changed during failure normalization."
                    )
                self._append_reconciliation_event(
                    request_id=active["request_id"],
                    event_type=ReconciliationEventType.AUTO_ESCALATION,
                    financial_resolution=financial,
                    execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                    operator=_WORKER_FAILURE_ESCALATION_OPERATOR,
                    note=reason,
                    previous_status=attempt_status.value,
                    resulting_status=ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
                    idempotency_key=self._reconciliation_idempotency_key(
                        active["request_id"], financial,
                        ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
                        _WORKER_FAILURE_ESCALATION_OPERATOR, reason, "ESCALATION",
                    ),
                    created_at=current_ts,
                )
                if not already_preserved:
                    self._preserve_topic_generation_job(execution, error, current_ts)
                self.conn.commit()
                return (
                    ResearchExecutionFailureOutcome.ESCALATED_RESERVED
                    if attempt_status is ProviderAttemptStatus.RESERVED
                    else ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED
                )

            if lifecycle["job_status"] in _TERMINAL_JOB_STATUSES:
                self.conn.commit()
                return ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED
            if preserve_for_verification and lifecycle["job_status"] == (
                JobStatus.NEEDS_VERIFICATION.value
            ):
                self.conn.commit()
                return ResearchExecutionFailureOutcome.PRESERVED_NEEDS_VERIFICATION
            if lifecycle["run_status"] == RunStatus.FAILED.value and (
                not terminalize_job
                or lifecycle["job_status"] == JobStatus.FAILED.value
            ):
                self.conn.commit()
                return ResearchExecutionFailureOutcome.TERMINALIZED_FAILED

            fence = self._require_topic_generation_fence(execution, current_ts)
            if preserve_for_verification:
                if fence["run_status"] != RunStatus.RUNNING.value:
                    raise StaleJobExecutionError(
                        execution.job_id,
                        "topic generation lifecycle cannot be preserved for verification.",
                    )
                self._preserve_topic_generation_job(execution, error, current_ts)
                self.conn.commit()
                return ResearchExecutionFailureOutcome.PRESERVED_NEEDS_VERIFICATION
            canonical = self._topic_generation_usage_total(execution.run_id)
            if cost_usd is not None and canonical != _money(
                cost_usd, positive=False, label="Topic generation failure cost",
            ):
                raise TopicGenerationResultError(
                    "COST_MISMATCH",
                    "failure cost must equal canonical model usage.",
                )
            if fence["run_status"] != RunStatus.RUNNING.value:
                raise StaleJobExecutionError(
                    execution.job_id,
                    "topic generation lifecycle is no longer mutable by this execution.",
                )
            run_cursor = self.conn.execute(
                "UPDATE runs SET status='FAILED',cost_usd=?,error=?,finished_at=? "
                "WHERE id=? AND status='RUNNING' AND finished_at IS NULL "
                "AND EXISTS (SELECT 1 FROM jobs WHERE id=? AND run_id=runs.id "
                "AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING'))",
                (
                    float(canonical), error, current_ts, execution.run_id,
                    execution.job_id, execution.lease_owner, current_ts,
                ),
            )
            if run_cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            if terminalize_job:
                job_cursor = self.conn.execute(
                    "UPDATE jobs SET status='FAILED',last_error=?,lease_owner=NULL,"
                    "lease_expires_at=NULL,updated_at=?,finished_at=?,"
                    "reserved_cost_usd=0.0,budget_reserved_at=NULL WHERE id=? "
                    "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                    "AND status IN ('LEASED','RUNNING')",
                    (
                        error, current_ts, current_ts, execution.job_id,
                        execution.run_id, execution.lease_owner, current_ts,
                    ),
                )
                if job_cursor.rowcount != 1:
                    raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return ResearchExecutionFailureOutcome.TERMINALIZED_FAILED
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def _preserve_topic_generation_job(
        self, execution: JobExecutionContext, error: str, current_ts: str,
    ) -> None:
        """Move the leased job to NEEDS_VERIFICATION and clear its lease."""
        job_cursor = self.conn.execute(
            "UPDATE jobs SET status='NEEDS_VERIFICATION',last_error=?,"
            "lease_owner=NULL,lease_expires_at=NULL,updated_at=?,finished_at=NULL "
            "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
            "AND status IN ('LEASED','RUNNING')",
            (
                error, current_ts, execution.job_id, execution.run_id,
                execution.lease_owner, current_ts,
            ),
        )
        if job_cursor.rowcount != 1:
            raise StaleJobExecutionError(execution.job_id)

    def _assert_evidence_finalization_path(
        self, *, account_id: str, topic_id: int, fence_topic_id: int,
        research_card_id: int | None, force_re_research: bool,
    ) -> None:
        """Dowód sprzed granicy płatności, że finalizacja TEGO tematu jest legalna.

        Wołane w transakcji walidacji przed rezerwacją: temat musi istnieć,
        mieć status dopuszczony dla trybu z zamrożonego intentu, a jego
        dotychczasowa kompletna karta musi mieć nienaruszoną relację
        run/karta/temat, żeby mogła pozostać rekordem historycznym. Nowa karta
        powstaje zawsze jako ODRĘBNY wiersz `research_cards` — ten run nie może
        mieć jeszcze żadnej karty. Każda odmowa jest typowana i pada PRZED
        rezerwacją: zero konsumpcji zgody, zero attemptu, zero requestu, zero
        kosztu.
        """
        if int(fence_topic_id) != int(topic_id):
            raise EvidenceResearchAuthorizationError(
                "INTENT_TOPIC_MISMATCH",
                "the leased research run does not belong to the frozen intent topic.",
            )
        if research_card_id is not None:
            raise EvidenceResearchAuthorizationError(
                "RESEARCH_RUN_ALREADY_HAS_CARD",
                "this execution already carries a research card.",
            )
        topic = self.conn.execute(
            "SELECT status FROM topics WHERE id=? AND account_id=?",
            (int(topic_id), account_id),
        ).fetchone()
        if topic is None:
            raise EvidenceResearchAuthorizationError(
                "TOPIC_MISSING", f"topic #{topic_id} does not exist for this account.",
            )
        allowed = self._allowed_finalization_topic_statuses(force_re_research)
        if topic["status"] not in allowed:
            raise EvidenceResearchAuthorizationError(
                "TOPIC_NOT_RE_RESEARCHABLE" if force_re_research else "TOPIC_NOT_SELECTED",
                f"topic #{topic_id} status {topic['status']} has no legal finalization "
                "path for this execution.",
            )
        try:
            has_completed_card = self.has_valid_completed_research_card_for_topic(
                account_id, int(topic_id),
            )
        except ResearchTopicIntegrityError as exc:
            raise EvidenceResearchAuthorizationError(
                "TOPIC_RESEARCH_HISTORY_INVALID", str(exc),
            ) from exc
        if has_completed_card and not force_re_research:
            raise EvidenceResearchAuthorizationError(
                "COMPLETED_CARD_REQUIRES_FORCE",
                f"topic #{topic_id} already has a complete research card; only an "
                "explicit re-research may add another one.",
            )

    def load_evidence_research_corpus(
        self, execution: JobExecutionContext,
    ) -> "EvidenceResearchCorpus":
        """Fail-closed pre-reservation validation of approval and evidence.

        Zwraca zatwierdzony corpus (retrievale w kolejności zamrożonego
        intentu). Rozjazd przed rezerwacją = typowana odmowa: zero konsumpcji
        zgody, zero attemptu, zero requestu, zero usage, zero kosztu.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.SINGLE,
            )
            payload_row = self.conn.execute(
                "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
            ).fetchone()
            if payload_row is None:
                raise StaleJobExecutionError(execution.job_id)
            intent, intent_json, fingerprint = self._frozen_evidence_contract_from_payload(
                payload_row["payload_json"], execution.job_id,
            )
            self._require_usable_evidence_research_approval(
                execution.job_id,
                account_id=intent.account_id,
                topic_id=intent.topic_id,
                canonical_intent_json=intent_json,
                intent_fingerprint=fingerprint,
                current_ts=now,
            )
            rows = self._validate_evidence_rows(
                intent.account_id, intent.evidence_input,
            )
            run_row = self.conn.execute(
                "SELECT research_card_id FROM research_runs WHERE id=?",
                (execution.run_id,),
            ).fetchone()
            if run_row is None:
                raise StaleJobExecutionError(execution.job_id)
            self._assert_evidence_finalization_path(
                account_id=intent.account_id,
                topic_id=intent.topic_id,
                fence_topic_id=int(fence["topic_id"]),
                research_card_id=run_row["research_card_id"],
                force_re_research=intent.force_re_research,
            )
            corpus = EvidenceResearchCorpus(
                retrievals=tuple(self._row_to_evidence_retrieval(row) for row in rows),
                execution_intent_json=intent_json,
                intent_fingerprint=fingerprint,
                force_re_research=intent.force_re_research,
            )
            self.conn.commit()
            return corpus
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def assert_evidence_research_snapshot(
        self, execution: JobExecutionContext, *, expected_intent_fingerprint: str,
    ) -> None:
        """Provider-boundary recheck of the frozen intent, approval and evidence.

        Zgodnie z aktualnym wzorcem kontroli aktualności trwałego stanu:
        wołane po REQUEST_STARTED i tuż przed granicą SDK. Rozjazd podnosi
        typowaną odmowę, którą pipeline mapuje na istniejący kontrakt
        NEEDS_RECONCILIATION — nigdy na drugi request.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            self._require_job_execution_fence(execution, now, flow=ResearchFlow.SINGLE)
            payload_row = self.conn.execute(
                "SELECT payload_json FROM jobs WHERE id=?", (execution.job_id,),
            ).fetchone()
            if payload_row is None:
                raise StaleJobExecutionError(execution.job_id)
            intent, intent_json, fingerprint = self._frozen_evidence_contract_from_payload(
                payload_row["payload_json"], execution.job_id,
            )
            if fingerprint != expected_intent_fingerprint:
                raise EvidenceResearchAuthorizationError(
                    "INTENT_MISMATCH",
                    "the persisted payload diverged from the frozen evidence snapshot.",
                )
            self._require_usable_evidence_research_approval(
                execution.job_id,
                account_id=intent.account_id,
                topic_id=intent.topic_id,
                canonical_intent_json=intent_json,
                intent_fingerprint=fingerprint,
                current_ts=now,
                require_consumed=True,
            )
            self._validate_evidence_rows(intent.account_id, intent.evidence_input)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    def record_job_verified_evidence_excerpt(
        self, execution: JobExecutionContext, retrieval_id: int, *,
        claim_text: str, excerpt_text: str, start_offset: int, end_offset: int,
    ) -> EvidenceExcerpt:
        """E1 verifier plus persistence, fenced by the active job execution.

        Ten sam deterministyczny weryfikator co spine offline; zapis jest
        możliwy wyłącznie pod świeżym lease (old-owner/expired lease nie może
        utrwalić excerptu). Odmowa weryfikatora nie utrwala niczego.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            now = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(
                execution, now, flow=ResearchFlow.SINGLE,
            )
            account_id = fence["research_account_id"]
            row = self.conn.execute(
                "SELECT * FROM evidence_retrievals WHERE id=? AND account_id=?",
                (retrieval_id, account_id),
            ).fetchone()
            if row is None:
                raise EvidenceVerificationError(EvidenceVerdict.rejected(
                    EvidenceRejectionReason.RETRIEVAL_NOT_FOUND,
                    f"retrieval id={retrieval_id} does not exist for this account",
                ))
            retrieval = self._row_to_evidence_retrieval(row)
            verdict = verify_evidence_excerpt(
                retrieval,
                claim_text=claim_text,
                excerpt_text=excerpt_text,
                start_offset=start_offset,
                end_offset=end_offset,
            )
            if not verdict.approved:
                raise EvidenceVerificationError(verdict)
            try:
                cursor = self.conn.execute(
                    "INSERT INTO evidence_excerpts (account_id, retrieval_id,"
                    " claim_text, claim_sha256, excerpt_text, start_offset,"
                    " end_offset, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        account_id, retrieval_id, claim_text,
                        sha256_hex(claim_text), excerpt_text,
                        start_offset, end_offset, now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "UNIQUE" in str(exc).upper():
                    raise EvidenceVerificationError(EvidenceVerdict.rejected(
                        EvidenceRejectionReason.DUPLICATE_EXCERPT,
                        "identical excerpt already recorded for this claim and range",
                    )) from exc
                raise
            excerpt_id = int(cursor.lastrowid)
            self.conn.commit()
            return EvidenceExcerpt(
                id=excerpt_id, account_id=account_id, retrieval_id=retrieval_id,
                claim_text=claim_text, claim_sha256=sha256_hex(claim_text),
                excerpt_text=excerpt_text, start_offset=start_offset,
                end_offset=end_offset, created_at=execution.now(),
            )
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

    # --- Evidence foundation (Etap 2, fala E1) ---

    def record_evidence_retrieval(
        self,
        document: FetchedDocument,
        *,
        account_id: str,
        now: datetime | None = None,
        max_raw_bytes: int = MAX_RAW_FETCH_BYTES,
        max_canonical_chars: int = MAX_CANONICAL_CHARS,
    ) -> EvidenceRetrieval:
        """Jedyna publiczna droga zapisu retrievalu — od surowego dokumentu.

        Wywołujący nie może przekazać żadnego gotowego hasha: ``raw_sha256``,
        ``extracted_sha256`` i ``canonical_sha256`` wylicza wyłącznie recorder
        z rzeczywistych bajtów/tekstów ogniw łańcucha.
        """
        retrieval = build_evidence_retrieval(
            document,
            account_id=account_id,
            now=now,
            max_raw_bytes=max_raw_bytes,
            max_canonical_chars=max_canonical_chars,
        )
        return self._insert_evidence_retrieval(retrieval)

    def _insert_evidence_retrieval(self, retrieval: EvidenceRetrieval) -> EvidenceRetrieval:
        """Wewnętrzny insert recordera — nie jest publicznym API zapisu.

        Nie ufa zdeklarowanym polom kanonu: przelicza długość i hash z
        rzeczywiście utrwalanego ``canonical_text`` i odmawia przy każdej
        rozbieżności (ten sam warunek egzekwuje trigger SQLite 0016).
        """
        canonical = retrieval.canonical_text
        if "\x00" in canonical:
            raise ValueError(
                "Evidence canonical_text must not contain NUL characters."
            )
        if retrieval.canonical_chars != len(canonical):
            raise ValueError(
                "Evidence canonical_chars must equal len(canonical_text); "
                f"declared={retrieval.canonical_chars} actual={len(canonical)}",
            )
        if retrieval.canonical_sha256 != sha256_hex(canonical):
            raise ValueError(
                "Evidence canonical_sha256 must be recomputed from the persisted "
                "canonical_text; a caller-declared hash is not accepted as proof.",
            )
        cur = self.conn.execute(
            "INSERT INTO evidence_retrievals (account_id, requested_url, final_url,"
            " fetched_at, status, http_status, content_type, fetch_error,"
            " raw_size_bytes, raw_sha256, extracted_chars, extracted_sha256,"
            " canonical_text, canonical_chars, canonical_sha256, truncated,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                retrieval.account_id, retrieval.requested_url, retrieval.final_url,
                _ts_precise(retrieval.fetched_at), retrieval.status.value,
                retrieval.http_status, retrieval.content_type, retrieval.fetch_error,
                retrieval.raw_size_bytes, retrieval.raw_sha256,
                retrieval.extracted_chars, retrieval.extracted_sha256,
                canonical, len(canonical), sha256_hex(canonical),
                int(retrieval.truncated), _ts_precise(retrieval.created_at),
            ),
        )
        self.conn.commit()
        stored = retrieval.model_copy()
        stored.id = int(cur.lastrowid)
        return stored

    @staticmethod
    def _row_to_evidence_retrieval(row) -> EvidenceRetrieval:
        return EvidenceRetrieval(
            id=row["id"], account_id=row["account_id"],
            requested_url=row["requested_url"],
            final_url=row["final_url"], fetched_at=row["fetched_at"],
            status=EvidenceRetrievalStatus(row["status"]),
            http_status=row["http_status"], content_type=row["content_type"],
            fetch_error=row["fetch_error"], raw_size_bytes=row["raw_size_bytes"],
            raw_sha256=row["raw_sha256"], extracted_chars=row["extracted_chars"],
            extracted_sha256=row["extracted_sha256"],
            canonical_text=row["canonical_text"],
            canonical_chars=row["canonical_chars"],
            canonical_sha256=row["canonical_sha256"],
            truncated=bool(row["truncated"]), created_at=row["created_at"],
        )

    def get_evidence_retrieval(
        self, retrieval_id: int, *, account_id: str,
    ) -> EvidenceRetrieval | None:
        row = self.conn.execute(
            "SELECT * FROM evidence_retrievals WHERE id=? AND account_id=?",
            (retrieval_id, account_id),
        ).fetchone()
        return self._row_to_evidence_retrieval(row) if row is not None else None

    def list_evidence_retrievals(
        self, *, account_id: str, final_url: str | None = None,
    ) -> list[EvidenceRetrieval]:
        if final_url is None:
            rows = self.conn.execute(
                "SELECT * FROM evidence_retrievals WHERE account_id=? ORDER BY id",
                (account_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM evidence_retrievals"
                " WHERE account_id=? AND final_url=? ORDER BY id",
                (account_id, final_url),
            ).fetchall()
        return [self._row_to_evidence_retrieval(row) for row in rows]

    def record_verified_evidence_excerpt(
        self,
        retrieval_id: int,
        *,
        account_id: str,
        claim_text: str,
        excerpt_text: str,
        start_offset: int,
        end_offset: int,
        now: datetime | None = None,
    ) -> EvidenceExcerpt:
        """Jedyna aplikacyjna droga zapisu excerptu — najpierw weryfikator.

        Weryfikacja przebiega przeciwko stanowi retrievalu odczytanemu z bazy
        w zakresie tego samego konta (nie przeciwko obiektowi wywołującego);
        retrieval innego konta jest nieodróżnialny od nieistniejącego.
        ``claim_sha256`` wylicza wyłącznie ta metoda — wywołujący nie może
        przekazać gotowego hasha. Odmowa nie utrwala niczego.
        """
        retrieval = self.get_evidence_retrieval(retrieval_id, account_id=account_id)
        if retrieval is None:
            raise EvidenceVerificationError(EvidenceVerdict.rejected(
                EvidenceRejectionReason.RETRIEVAL_NOT_FOUND,
                f"retrieval id={retrieval_id} does not exist for this account",
            ))
        verdict = verify_evidence_excerpt(
            retrieval,
            claim_text=claim_text,
            excerpt_text=excerpt_text,
            start_offset=start_offset,
            end_offset=end_offset,
        )
        if not verdict.approved:
            raise EvidenceVerificationError(verdict)
        excerpt = EvidenceExcerpt(
            account_id=account_id,
            retrieval_id=retrieval_id,
            claim_text=claim_text,
            claim_sha256=sha256_hex(claim_text),
            excerpt_text=excerpt_text,
            start_offset=start_offset,
            end_offset=end_offset,
            created_at=now or datetime.now(timezone.utc),
        )
        try:
            cur = self.conn.execute(
                "INSERT INTO evidence_excerpts (account_id, retrieval_id,"
                " claim_text, claim_sha256, excerpt_text, start_offset,"
                " end_offset, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    excerpt.account_id, excerpt.retrieval_id, excerpt.claim_text,
                    excerpt.claim_sha256, excerpt.excerpt_text,
                    excerpt.start_offset, excerpt.end_offset,
                    _ts_precise(excerpt.created_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            if "UNIQUE" in str(exc).upper():
                raise EvidenceVerificationError(EvidenceVerdict.rejected(
                    EvidenceRejectionReason.DUPLICATE_EXCERPT,
                    "identical excerpt already recorded for this claim and range",
                )) from exc
            raise
        self.conn.commit()
        excerpt.id = int(cur.lastrowid)
        return excerpt

    def list_evidence_excerpts(
        self, retrieval_id: int, *, account_id: str,
    ) -> list[EvidenceExcerpt]:
        rows = self.conn.execute(
            "SELECT * FROM evidence_excerpts WHERE retrieval_id=? AND account_id=?"
            " ORDER BY id",
            (retrieval_id, account_id),
        ).fetchall()
        return [
            EvidenceExcerpt(
                id=row["id"], account_id=row["account_id"],
                retrieval_id=row["retrieval_id"],
                claim_text=row["claim_text"], claim_sha256=row["claim_sha256"],
                excerpt_text=row["excerpt_text"], start_offset=row["start_offset"],
                end_offset=row["end_offset"], created_at=row["created_at"],
            )
            for row in rows
        ]
