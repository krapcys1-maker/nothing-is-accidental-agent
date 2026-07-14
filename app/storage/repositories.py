"""SqliteStorage — konkretna implementacja StoragePort na SQLite."""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from app.core.clock import Clock
from app.models import (
    Account,
    Job,
    JobExecutionContext,
    JobEnqueueContext,
    JobKind,
    JobLease,
    JobRecoveryResult,
    JobReservation,
    JobStatus,
    ModelUsage,
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
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    BudgetReservationError,
    JobConflictError,
    JobRunConflictError,
    JobRunReconciliationRequired,
    JobRunRelationError,
    LifecycleTransitionError,
    ResearchTopicIntegrityError,
    StaleJobExecutionError,
    SystemFlagError,
)
from app.storage.db import apply_migrations, connect


_RESEARCH_USAGE_TASKS = (
    "research",
    "research_gather",
    "research_synthesize",
    "research_discover",
    "research_extract",
    "research_synthesize_cards",
)
_RESEARCH_USAGE_PLACEHOLDERS = ", ".join("?" for _ in _RESEARCH_USAGE_TASKS)

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
_SECURITY_FLAG_DEFAULTS = {
    "kill_switch": True,
    "worker_enabled": False,
    "safe_mode": True,
    "paid_actions_enabled": False,
    "browser_actions_enabled": False,
}
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
        conn = connect(db_path)
        apply_migrations(conn)
        return cls(conn)

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
    def add_topic(self, account_id: str, topic: Topic) -> Topic:
        cur = self.conn.execute(
            "INSERT INTO topics (account_id, title, question, score, score_breakdown,"
            " status, source, duplicate_of, rejection_reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                account_id, topic.title, topic.question, topic.score,
                json.dumps(topic.score_breakdown), topic.status.value,
                topic.source, topic.duplicate_of, topic.rejection_reason,
                _ts(topic.created_at),
            ),
        )
        self.conn.commit()
        topic.id = int(cur.lastrowid)
        topic.account_id = account_id
        return topic

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
                and float(existing["cost_usd"]) == float(cost_usd)
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
                (target.value, cost_usd, error, _ts(), run_id, *allowed),
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
                    RunStatus.FAILED.value, cost_usd, error, _ts_precise(), run_id,
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
        self.conn.execute("BEGIN")
        try:
            cur = self.conn.execute(
                "INSERT INTO model_usage (run_id, provider, model, task, input_tokens,"
                " output_tokens, cache_read_tokens, cache_write_tokens, web_search_requests,"
                " estimated_cost_usd, dry_run, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    usage.run_id, usage.provider, usage.model, usage.task, usage.input_tokens,
                    usage.output_tokens, usage.cache_read_tokens, usage.cache_write_tokens,
                    usage.web_search_requests, usage.estimated_cost_usd, int(usage.dry_run),
                    _ts(usage.created_at),
                ),
            )
            if usage.task in _RESEARCH_USAGE_TASKS:
                self._set_run_cost_from_research_usage(usage.run_id)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        usage.id = int(cur.lastrowid)
        return usage

    def sum_real_cost_usd(self, since_prefix: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) AS total FROM model_usage"
            " WHERE dry_run=0 AND created_at LIKE ?",
            (f"{since_prefix}%",),
        ).fetchone()
        return float(row["total"])

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
            lease_expires_at=row["lease_expires_at"], attempts=int(row["attempts"]),
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
        if execution.kind is not JobKind.RESEARCH or execution.workflow is not WorkflowType.RESEARCH:
            raise StaleJobExecutionError(
                execution.job_id, "execution kind/workflow does not authorize research mutation.",
            )
        return _persisted_ts(self._job_now(execution.now()))

    def _require_job_execution_fence(
        self, execution: JobExecutionContext, current_ts: str,
    ) -> sqlite3.Row:
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
            "AND rr.flow='single' AND t.account_id=j.account_id",
            (
                execution.job_id, execution.run_id, execution.lease_owner,
                current_ts,
            ),
        ).fetchone()
        if row is None:
            raise StaleJobExecutionError(execution.job_id)
        return row

    @staticmethod
    def _canonical_payload(payload: dict) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise JobConflictError("Job payload must be JSON-serializable.") from exc

    @staticmethod
    def _job_context_matches(row: sqlite3.Row, job: Job, payload_json: str) -> bool:
        del payload_json
        return JobEnqueueContext.from_row(row) == JobEnqueueContext.from_job(job)

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
            job.max_attempts < 1 or job.reserved_cost_usd != 0.0
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
                    return result
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
            return self._job_from_row(row)
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
                "WHERE status='QUEUED' AND deadline_at IS NOT NULL AND deadline_at < ?",
                (current_ts, current_ts, current_ts),
            )
            self.conn.execute(
                "UPDATE jobs SET status='FAILED', last_error='Maximum attempts exhausted before claim.', "
                "finished_at=?, updated_at=?, reserved_cost_usd=0.0, budget_reserved_at=NULL "
                "WHERE status='QUEUED' AND attempts >= max_attempts",
                (current_ts, current_ts),
            )
            selected = self.conn.execute(
                "SELECT id FROM jobs WHERE status='QUEUED' AND earliest_run_at <= ? "
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
                "attempts=attempts+1, started_at=COALESCE(started_at, ?), updated_at=? "
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

    def _transition_leased_job(
        self, job_id: str, lease_owner: str, target: JobStatus, *, error: str | None,
        now: datetime | None, clock: Clock | None, release_budget: bool,
    ) -> None:
        allowed = (JobStatus.LEASED.value, JobStatus.RUNNING.value)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
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
            current_ts = _persisted_ts(self._job_now(now, clock=clock))
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
            if job.payload != {
                "account_id": job.account_id,
                "topic_id": int(job.topic_id),
                "dry_run": True,
            }:
                raise JobRunRelationError(
                    "RESEARCH_PAYLOAD_UNSUPPORTED", job_id,
                    "offline initialization accepts only the dry-run research payload.",
                )
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
                    run.status is RunStatus.DRY_RUN
                    and run_row["finished_at"] is None
                    and run_row["error"] is None
                    and float(run_row["cost_usd"]) == 0.0
                    and research_run.status is ResearchRunStatus.PENDING
                    and research_row["research_card_id"] is None
                    and research_row["error"] is None
                    and float(research_row["total_cost_usd"]) == 0.0
                )
                if not allowed_existing_state:
                    raise JobRunRelationError(
                        "ATTACHED_RESEARCH_RUN_STATE_INVALID", job_id,
                        "an existing worker initialization must remain exactly "
                        "DRY_RUN+single:PENDING without result, error, cost, or finished_at.",
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
                    RunStatus.DRY_RUN.value, "research", current_ts,
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

    def add_job_model_usage(
        self, execution: JobExecutionContext, usage: ModelUsage,
    ) -> ModelUsage:
        """Worker-only usage write; insert and run-cost refresh share the fence lock."""
        if usage.run_id != execution.run_id:
            raise StaleJobExecutionError(
                execution.job_id, "usage run_id does not match the fenced execution.",
            )
        if usage.task not in _RESEARCH_USAGE_TASKS:
            raise StaleJobExecutionError(
                execution.job_id, "usage task is not a research task.",
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(execution.now())
            current_ts = _persisted_ts(current)
            fence = self._require_job_execution_fence(execution, current_ts)
            expected_dry_run = fence["run_status"] == RunStatus.DRY_RUN.value
            if bool(usage.dry_run) != expected_dry_run:
                raise StaleJobExecutionError(
                    execution.job_id, "usage dry_run marker conflicts with the fenced run.",
                )
            cur = self.conn.execute(
                "INSERT INTO model_usage (run_id, provider, model, task, input_tokens,"
                " output_tokens, cache_read_tokens, cache_write_tokens, web_search_requests,"
                " estimated_cost_usd, dry_run, created_at) "
                "SELECT ?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=? AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    usage.run_id, usage.provider, usage.model, usage.task,
                    usage.input_tokens, usage.output_tokens, usage.cache_read_tokens,
                    usage.cache_write_tokens, usage.web_search_requests,
                    usage.estimated_cost_usd, int(usage.dry_run), current_ts,
                    execution.job_id, execution.run_id, execution.lease_owner, current_ts,
                ),
            )
            if cur.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self._set_run_cost_from_research_usage(execution.run_id)
            self.conn.commit()
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise
        usage.id = int(cur.lastrowid)
        usage.created_at = current
        return usage

    def fail_job_research_execution(
        self, execution: JobExecutionContext, cost_usd: float | None, error: str,
        *, terminalize_job: bool = False,
    ) -> None:
        """Worker-only failure boundary for the legacy single research flow.

        ``terminalize_job`` is reserved for an unexpected post-initialization
        pipeline exception. It makes jobs/runs/research_runs fail in the same
        fenced SQLite transaction instead of leaving an active execution behind.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current_ts = self._job_execution_timestamp(execution)
            fence = self._require_job_execution_fence(execution, current_ts)
            canonical = round(float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd),0.0) AS total FROM model_usage "
                "WHERE run_id=? AND task IN (" + _RESEARCH_USAGE_PLACEHOLDERS + ")",
                (execution.run_id, *_RESEARCH_USAGE_TASKS),
            ).fetchone()["total"]), 6)
            if cost_usd is not None and canonical != round(float(cost_usd), 6):
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
                    canonical, error, current_ts, execution.run_id, execution.job_id,
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
                    error, canonical, current_ts, execution.run_id, execution.job_id,
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
        except BaseException as primary:
            if self.conn.in_transaction:
                self._rollback_preserving_primary(primary, self.conn.rollback)
            raise

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
            canonical = round(float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd),0.0) AS total FROM model_usage "
                "WHERE run_id=? AND task IN (" + _RESEARCH_USAGE_PLACEHOLDERS + ")",
                (execution.run_id, *_RESEARCH_USAGE_TASKS),
            ).fetchone()["total"]), 6)
            if canonical != round(float(total_cost_usd), 6):
                raise ResearchTopicIntegrityError(
                    "Worker research finalization cost must equal canonical model usage."
                )
            topic = self.conn.execute(
                "SELECT status FROM topics WHERE id=? AND account_id=?",
                (card.topic_id, fence["research_account_id"]),
            ).fetchone()
            if topic is None or topic["status"] != TopicStatus.SELECTED.value:
                raise ResearchTopicIntegrityError(
                    "Worker research finalization requires its selected topic."
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
                    card.id, canonical, current_ts, execution.run_id, execution.job_id,
                    execution.lease_owner, current_ts,
                ),
            )
            run_cursor = self.conn.execute(
                "UPDATE runs SET status=?,cost_usd=?,error=NULL,finished_at=? "
                "WHERE id=? AND status=? AND finished_at IS NULL AND EXISTS ("
                "SELECT 1 FROM jobs WHERE id=? AND run_id=runs.id AND lease_owner=? "
                "AND lease_expires_at>=? AND status IN ('LEASED','RUNNING'))",
                (
                    terminal_run_status.value, canonical, current_ts, execution.run_id,
                    expected_run_status, execution.job_id, execution.lease_owner, current_ts,
                ),
            )
            topic_cursor = self.conn.execute(
                "UPDATE topics SET status='USED' WHERE id=? AND account_id=? "
                "AND status='SELECTED' AND EXISTS (SELECT 1 FROM jobs WHERE id=? "
                "AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING'))",
                (
                    card.topic_id, fence["research_account_id"], execution.job_id,
                    execution.run_id, execution.lease_owner, current_ts,
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
                "SELECT status,lease_owner,lease_expires_at,external_effect_started_at "
                "FROM jobs WHERE id=?", (job_id,),
            ).fetchone()
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
                "SELECT id,kind,run_id,attempts,max_attempts,external_effect_started_at FROM jobs "
                "WHERE status IN ('LEASED','RUNNING') AND lease_expires_at < ? ORDER BY id",
                (current_ts,),
            ).fetchall()
            for row in rows:
                if row["kind"] == JobKind.BROWSER.value or row["external_effect_started_at"] is not None:
                    target = JobStatus.NEEDS_VERIFICATION
                    release_budget = False
                    result.needs_verification_count += 1
                    error = "Lease expired; external effect requires verification."
                elif row["kind"] == JobKind.RESEARCH.value and row["run_id"] is not None:
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
            self.conn.commit()
            return result
        except Exception:
            if self.conn.in_transaction:
                self.conn.rollback()
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
        values = (amount_usd, daily_limit_usd, monthly_limit_usd)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise BudgetReservationError("Reservation amount and limits must be finite and non-negative.")
        placeholders = ", ".join("?" for _ in _ACTIVE_JOB_STATUSES)
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self._job_now(now, clock=clock)
            current_ts = _persisted_ts(current)
            day_prefix = current.strftime("%Y-%m-%d")
            month_prefix = current.strftime("%Y-%m")
            job = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None or job["status"] not in _ACTIVE_JOB_STATUSES:
                raise self._job_lifecycle_error(
                    job_id, "BUDGET_RESERVED", _ACTIVE_JOB_STATUSES,
                    detail="Only an active non-terminal job may hold a reservation.",
                )
            if job["budget_reserved_at"] is not None:
                if float(job["reserved_cost_usd"]) == float(amount_usd):
                    result = JobReservation(
                        job_id=job_id, amount_usd=float(job["reserved_cost_usd"]),
                        reserved_at=job["budget_reserved_at"],
                    )
                    self.conn.commit()
                    return result
                raise BudgetReservationError(
                    f"Job {job_id} already has a different active budget reservation."
                )
            day_real = float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) AS total FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{day_prefix}%",),
            ).fetchone()["total"])
            month_real = float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) AS total FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{month_prefix}%",),
            ).fetchone()["total"])
            active_reserved = float(self.conn.execute(
                "SELECT COALESCE(SUM(reserved_cost_usd), 0.0) AS total FROM jobs "
                f"WHERE status IN ({placeholders}) AND budget_reserved_at IS NOT NULL",
                _ACTIVE_JOB_STATUSES,
            ).fetchone()["total"])
            if any(not math.isfinite(value) or value < 0 for value in (
                day_real, month_real, active_reserved,
            )):
                raise BudgetReservationError("Persisted budget state is invalid.")
            if month_real + active_reserved + amount_usd > monthly_limit_usd:
                raise BudgetReservationError("Reservation would exceed the global monthly limit.")
            if day_real + active_reserved + amount_usd > daily_limit_usd:
                raise BudgetReservationError("Reservation would exceed the global daily limit.")
            cursor = self.conn.execute(
                "UPDATE jobs SET reserved_cost_usd=?, budget_reserved_at=?, updated_at=? "
                "WHERE id=? AND budget_reserved_at IS NULL AND status IN "
                f"({placeholders})",
                (amount_usd, current_ts, current_ts, job_id, *_ACTIVE_JOB_STATUSES),
            )
            if cursor.rowcount != 1:
                raise BudgetReservationError("Concurrent reservation compare-and-swap failed.")
            self.conn.commit()
            return JobReservation(job_id=job_id, amount_usd=amount_usd, reserved_at=current_ts)
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
        values = (amount_usd, daily_limit_usd, monthly_limit_usd)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise BudgetReservationError(
                "Reservation amount and limits must be finite and non-negative."
            )
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
                if float(job["reserved_cost_usd"]) == float(amount_usd):
                    result = JobReservation(
                        job_id=execution.job_id,
                        amount_usd=float(job["reserved_cost_usd"]),
                        reserved_at=job["budget_reserved_at"],
                    )
                    self.conn.commit()
                    return result
                raise BudgetReservationError(
                    "Job execution already has a different active budget reservation."
                )
            day_real = float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd),0.0) AS total FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{day_prefix}%",),
            ).fetchone()["total"])
            month_real = float(self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd),0.0) AS total FROM model_usage "
                "WHERE dry_run=0 AND created_at LIKE ?", (f"{month_prefix}%",),
            ).fetchone()["total"])
            active_reserved = float(self.conn.execute(
                "SELECT COALESCE(SUM(reserved_cost_usd),0.0) AS total FROM jobs "
                f"WHERE status IN ({placeholders}) AND budget_reserved_at IS NOT NULL",
                _ACTIVE_JOB_STATUSES,
            ).fetchone()["total"])
            if any(not math.isfinite(value) or value < 0 for value in (
                day_real, month_real, active_reserved,
            )):
                raise BudgetReservationError("Persisted budget state is invalid.")
            if month_real + active_reserved + amount_usd > monthly_limit_usd:
                raise BudgetReservationError("Reservation would exceed the global monthly limit.")
            if day_real + active_reserved + amount_usd > daily_limit_usd:
                raise BudgetReservationError("Reservation would exceed the global daily limit.")
            cursor = self.conn.execute(
                "UPDATE jobs SET reserved_cost_usd=?,budget_reserved_at=?,updated_at=? "
                "WHERE id=? AND run_id=? AND lease_owner=? AND lease_expires_at>=? "
                "AND status IN ('LEASED','RUNNING') AND budget_reserved_at IS NULL",
                (
                    amount_usd, current_ts, current_ts, execution.job_id,
                    execution.run_id, execution.lease_owner, current_ts,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleJobExecutionError(execution.job_id)
            self.conn.commit()
            return JobReservation(
                job_id=execution.job_id, amount_usd=amount_usd, reserved_at=current,
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

    def get_system_flag(self, key: str) -> SystemFlag | None:
        """Reads SQLite on every call; safety flags fail closed when absent or malformed."""
        row = self.conn.execute("SELECT * FROM system_flags WHERE key=?", (key,)).fetchone()
        if row is None:
            if key not in _SECURITY_FLAG_DEFAULTS:
                return None
            return SystemFlag(key=key, value=_SECURITY_FLAG_DEFAULTS[key], is_valid=False)
        try:
            value = json.loads(row["value_json"])
            if not isinstance(value, bool):
                raise ValueError("safety flag must contain a JSON boolean")
        except (TypeError, ValueError, json.JSONDecodeError):
            if key not in _SECURITY_FLAG_DEFAULTS:
                raise SystemFlagError(f"System flag {key!r} has malformed JSON.")
            return SystemFlag(
                key=key, value=_SECURITY_FLAG_DEFAULTS[key], updated_at=row["updated_at"],
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

            canonical_row = self.conn.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) AS total FROM model_usage"
                " WHERE run_id=? AND task IN (" + _RESEARCH_USAGE_PLACEHOLDERS + ")",
                (research_run_id, *_RESEARCH_USAGE_TASKS),
            ).fetchone()
            canonical_cost = round(float(canonical_row["total"]), 6)
            if canonical_cost != round(float(total_cost_usd), 6):
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
                    and float(row["research_cost"]) == canonical_cost
                    and row["run_status"] == terminal_run_status.value
                    and float(row["run_cost"]) == canonical_cost
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
                (ResearchRunStatus.COMPLETE.value, _ts(), card.id, canonical_cost, _ts(),
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
                (terminal_run_status.value, canonical_cost, _ts(), research_run_id,
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
        self.conn.execute(
            "INSERT INTO research_runs (id, account_id, topic_id, flow, status,"
            " is_force_reresearch, total_cost_usd, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                research_run.id, research_run.account_id, research_run.topic_id,
                research_run.flow.value, research_run.status.value,
                int(research_run.is_force_reresearch), research_run.total_cost_usd,
                _ts(research_run.created_at), _ts(research_run.updated_at),
            ),
        )
        self.conn.commit()
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
                    and float(row["research_cost"]) == float(total_cost_usd)
                    and row["run_status"] == terminal_run_status.value
                    and float(row["run_cost"]) == float(total_cost_usd)
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
                    (ResearchRunStatus.COMPLETE.value, _ts(), research_card_id, total_cost_usd,
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            else:
                cursor = self.conn.execute(
                    "UPDATE research_runs SET status=?, research_card_id=?, total_cost_usd=?,"
                    " updated_at=? WHERE id=? AND account_id=? AND topic_id=?"
                    " AND status IN (?) AND research_card_id IS NULL",
                    (ResearchRunStatus.COMPLETE.value, research_card_id, total_cost_usd,
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano research_run {research_run_id}.")

            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? "
                "WHERE id=? AND account_id=? AND status IN (?)",
                (terminal_run_status.value, total_cost_usd, None, _ts(), research_run_id,
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
            )
            for r in rows
        ]

    def _set_run_cost_from_research_usage(self, research_run_id: str) -> None:
        """Ustawia cache runs.cost_usd z kanonicznych wpisów model_usage tego runu.

        Celowo nie filtruje dry_run: cache runu zachowuje koszt zapisany w
        model_usage, a budżet odróżnia realne użycie przez sum_real_cost_usd.
        """
        cursor = self.conn.execute(
            "UPDATE runs SET cost_usd=COALESCE(("
            " SELECT SUM(estimated_cost_usd) FROM model_usage"
            f" WHERE run_id=? AND task IN ({_RESEARCH_USAGE_PLACEHOLDERS})"
            "), 0.0) WHERE id=?",
            (research_run_id, *_RESEARCH_USAGE_TASKS, research_run_id),
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
