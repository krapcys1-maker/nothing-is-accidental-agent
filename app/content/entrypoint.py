"""Explicit local C2 entrypoint for one targeted fake-only content job."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentType,
)
from app.content.writer import FakeContentWriter, WriterPort
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationResult
from app.storage.repositories import SqliteStorage


@dataclass(frozen=True)
class OfflineContentEntrypointResult:
    content_id: int
    job_id: str
    worker: WorkerIterationResult


def run_content_offline(
    *,
    settings: Settings,
    account_id: str,
    research_card_id: int,
    content_type: ContentType,
    idempotency_key: str,
    job_id: str | None = None,
    lease_owner: str | None = None,
    writer: WriterPort | None = None,
    clock: Clock | None = None,
) -> OfflineContentEntrypointResult:
    """Prepare and execute one named C2 job; never scans the CONTENT queue."""
    clock = clock or SystemClock()
    storage = SqliteStorage.open(settings.db_path)
    try:
        resolved_job_id = job_id or f"content-c2-{uuid4()}"
        prepared = storage.prepare_content_job(
            ContentPreparationRequest(
                job_id=resolved_job_id,
                idempotency_key=idempotency_key,
                account_id=account_id,
                research_card_id=research_card_id,
                content_type=content_type,
                execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
                prompt_version="offline_content_prompt_v1",
                style_guide_version=(
                    "ARTICLE_STYLE_PROFILE_V1"
                    if content_type is ContentType.ARTICLE
                    else "NOTES_STYLE_PROFILE_V1_PROVISIONAL"
                ),
            ),
            clock=clock,
        )
        policy = PolicyEngine(settings, storage, clock)
        dispatcher = JobDispatcher(
            settings=settings,
            storage=storage,
            policy=policy,
            clock=clock,
            allow_real_research=False,
            allow_real_topic_generation=False,
            content_writer=writer or FakeContentWriter(),
        )
        worker = Worker(
            storage=storage,
            policy=policy,
            dispatcher=dispatcher,
            lease_owner=lease_owner or f"content-c2-worker-{uuid4()}",
            target_job_id=resolved_job_id,
            lease_seconds=60,
            heartbeat_interval_seconds=20.0,
            heartbeat_startup_timeout_seconds=5.0,
            heartbeat_shutdown_timeout_seconds=5.0,
            heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
            clock=clock,
        )
        result = worker.run_once()
        return OfflineContentEntrypointResult(
            content_id=prepared.content.id,
            job_id=resolved_job_id,
            worker=result,
        )
    finally:
        storage.close()
