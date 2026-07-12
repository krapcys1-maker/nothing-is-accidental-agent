"""SqliteStorage — konkretna implementacja StoragePort na SQLite."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from app.models import (
    Account,
    ModelUsage,
    ResearchCard,
    ResearchRecommendation,
    ResearchRun,
    ResearchFlow,
    ResearchRunStatus,
    ResearchSourceRecord,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    RunStatus,
    Source,
    SourceCandidateRecord,
    SourceCandidateRetryResult,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import ResearchTopicIntegrityError
from app.storage.db import apply_migrations, connect


_RESEARCH_USAGE_TASKS = (
    "research_gather",
    "research_synthesize",
    "research_discover",
    "research_extract",
    "research_synthesize_cards",
)
_RESEARCH_USAGE_PLACEHOLDERS = ", ".join("?" for _ in _RESEARCH_USAGE_TASKS)


def _ts(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class SqliteStorage:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

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
        self.conn.execute(
            "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? WHERE id=?",
            (status, cost_usd, error, _ts(), run_id),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> Run | None:
        r = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if r is None:
            return None
        return Run(
            id=r["id"], account_id=r["account_id"],
            workflow=WorkflowType(r["workflow"]), status=RunStatus(r["status"]),
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
            "INSERT INTO research_runs (id, account_id, topic_id, flow, status, total_cost_usd,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                research_run.id, research_run.account_id, research_run.topic_id,
                research_run.flow.value, research_run.status.value, research_run.total_cost_usd,
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
        return ResearchRun(
            id=r["id"], account_id=r["account_id"], topic_id=r["topic_id"],
            flow=ResearchFlow(r["flow"]),
            status=ResearchRunStatus(r["status"]),
            stage_a_completed_at=r["stage_a_completed_at"],
            stage_b_completed_at=r["stage_b_completed_at"],
            research_card_id=r["research_card_id"],
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
        """Atomowo finalizuje kartę już zapisaną przez pipeline.

        Karta może powstać przed finalizacją, ale żaden status sukcesu nie jest wtedy
        jeszcze zatwierdzany. W tej jednej transakcji są walidacja relacji, COMPLETE,
        terminalny status `runs` i `topics.USED`. Identyczne powtórzenie jest no-op;
        każde sprzeczne powtórzenie kończy się błędem integralności bez mutacji.
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
                ResearchFlow.STAGED.value: {ResearchRunStatus.SYNTHESIS_PENDING.value},
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
                # Jawne wznowienie etapu B zaczyna z FAILED po wcześniejszej
                # nieudanej syntezie lub blokadzie budżetowej, ale nie powtarza A.
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
                    " AND status=? AND research_card_id IS NULL",
                    (ResearchRunStatus.COMPLETE.value, _ts(), research_card_id, total_cost_usd,
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            else:
                cursor = self.conn.execute(
                    "UPDATE research_runs SET status=?, research_card_id=?, total_cost_usd=?,"
                    " updated_at=? WHERE id=? AND account_id=? AND topic_id=?"
                    " AND status=? AND research_card_id IS NULL",
                    (ResearchRunStatus.COMPLETE.value, research_card_id, total_cost_usd,
                     _ts(), research_run_id, row["research_account_id"], row["topic_id"],
                     row["research_status"]),
                )
            if cursor.rowcount != 1:
                raise ResearchTopicIntegrityError(f"Nie zaktualizowano research_run {research_run_id}.")

            cursor = self.conn.execute(
                "UPDATE runs SET status=?, cost_usd=?, error=?, finished_at=? "
                "WHERE id=? AND account_id=? AND status=?",
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
        for src in sources:
            self._insert_research_source(research_run_id, src)
        self.conn.execute(
            "UPDATE research_runs SET status=?, stage_a_completed_at=?, updated_at=?"
            " WHERE id=?",
            (ResearchRunStatus.SOURCE_COLLECTED.value, _ts(), _ts(), research_run_id),
        )
        self.conn.commit()
        return sources

    def mark_research_run_failed(self, research_run_id: str, error: str) -> None:
        """Etap A się nie powiódł — nie ma czego wznawiać (brak trwałych źródeł)."""
        self.conn.execute(
            "UPDATE research_runs SET status=?, error=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.FAILED.value, error, _ts(), research_run_id),
        )
        self.conn.commit()

    def mark_research_run_partial(self, research_run_id: str, error: str) -> None:
        """Etap A udany, etap B nieudany — źródła w research_sources zostają
        nietknięte; można ponowić WYŁĄCZNIE etap B, bez ponownego web search."""
        self.conn.execute(
            "UPDATE research_runs SET status=?, error=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.PARTIAL.value, error, _ts(), research_run_id),
        )
        self.conn.commit()

    def mark_research_run_complete(self, research_run_id: str, research_card_id: int,
                                   total_cost_usd: float) -> None:
        """Kompatybilny alias kanonicznej atomowej finalizacji etapów z syntezą B."""
        self.finalize_research_success(
            research_run_id, research_card_id, total_cost_usd, stage_b_completed=True,
            terminal_run_status=self._terminal_status_for_finalization(research_run_id),
        )

    def add_research_stage_result(self, research_run_id: str, stage: ResearchStageName,
                                  status: ResearchStageStatus, error: str | None = None) -> None:
        """Log KAŻDEJ próby etapu (audytowalność) — niezależny od research_runs.status,
        który trzyma tylko stan BIEŻĄCY."""
        self.conn.execute(
            "INSERT INTO research_stage_results (research_run_id, stage, status,"
            " finished_at, error) VALUES (?,?,?,?,?)",
            (research_run_id, stage.value, status.value, _ts(), error),
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
        cur = self.conn.cursor()
        for c in candidates:
            row = cur.execute(
                "INSERT INTO research_source_candidates (research_run_id, url, title,"
                " status) VALUES (?,?,?,?)",
                (research_run_id, c.url, c.title, SourceCandidateStatus.PENDING_EXTRACTION.value),
            )
            c.id = int(row.lastrowid)
            c.research_run_id = research_run_id
        self.conn.execute(
            "UPDATE research_runs SET status=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.DISCOVERY_COMPLETE.value, _ts(), research_run_id),
        )
        self.conn.commit()
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
        self.conn.execute(
            "UPDATE research_runs SET status=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.EXTRACTION_IN_PROGRESS.value, _ts(), research_run_id),
        )
        self.conn.commit()

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
            " extracted_at=? WHERE id=? AND status=?",
            (
                title, author_or_org, published_at, source_type.value,
                json.dumps(supported_claims), json.dumps(numeric_facts),
                verification_status.value, source_quality_score,
                SourceCandidateStatus.EXTRACTED.value, _ts(), candidate_id,
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError(
                f"Source candidate #{candidate_id} is not EXTRACTION_IN_PROGRESS; "
                "cannot persist extraction success."
            )
        self.conn.commit()

    def mark_source_candidate_failed(self, candidate_id: int, error: str) -> None:
        """Ekstrakcja nieudana dla JEDNEGO źródła — commit NATYCHMIAST. Inne kandydaci
        (przetworzeni wcześniej lub później) są nietknięci."""
        cursor = self.conn.execute(
            "UPDATE research_source_candidates SET status=?, extraction_error=?,"
            " extracted_at=? WHERE id=? AND status=?",
            (
                SourceCandidateStatus.EXTRACTION_FAILED.value, error, _ts(), candidate_id,
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError(
                f"Source candidate #{candidate_id} is not EXTRACTION_IN_PROGRESS; "
                "cannot persist extraction failure."
            )
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
            "WHERE id=? AND status=? AND attempts < ?",
            (
                SourceCandidateStatus.EXTRACTION_IN_PROGRESS.value,
                candidate_id, SourceCandidateStatus.PENDING_EXTRACTION.value, max_attempts,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError(
                f"Source candidate #{candidate_id} is not claimable "
                "(requires PENDING_EXTRACTION below attempts cap)."
            )
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
                "SELECT status FROM research_runs WHERE id=?", (research_run_id,)
            ).fetchone()
            if run_row is None:
                raise ValueError(f"Research run #{research_run_id} does not exist.")
            if run_row["status"] not in (
                ResearchRunStatus.PARTIAL.value,
                ResearchRunStatus.PARTIAL_EXHAUSTED.value,
            ):
                raise ValueError(
                    f"Research run #{research_run_id} cannot retry failed candidates "
                    f"from status {run_row['status']}."
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
                            "WHERE id=? AND status=? AND attempts < ?",
                            (
                                SourceCandidateStatus.PENDING_EXTRACTION.value, row["id"],
                                SourceCandidateStatus.EXTRACTION_FAILED.value, max_attempts,
                            ),
                        )
                        reset_count += cursor.rowcount
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
                    "WHERE id=? AND status=?",
                    (
                        ResearchRunStatus.PARTIAL.value, _ts(), research_run_id,
                        ResearchRunStatus.PARTIAL_EXHAUSTED.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"Research run #{research_run_id} could not be reopened from "
                        "PARTIAL_EXHAUSTED."
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
        self.conn.execute(
            "UPDATE research_runs SET status=?, stage_a_completed_at=?, updated_at=?"
            " WHERE id=?",
            (ResearchRunStatus.SOURCES_COMPLETE.value, _ts(), _ts(), research_run_id),
        )
        self.conn.commit()

    def mark_research_run_partial_exhausted(self, research_run_id: str, error: str) -> None:
        """Terminalny brak legalnej drogi A2: nie ma pending ani failed poniżej capu."""
        cursor = self.conn.execute(
            "UPDATE research_runs SET status=?, error=?, updated_at=? "
            "WHERE id=? AND status IN (?,?,?)",
            (
                ResearchRunStatus.PARTIAL_EXHAUSTED.value, error, _ts(), research_run_id,
                ResearchRunStatus.DISCOVERY_COMPLETE.value,
                ResearchRunStatus.EXTRACTION_IN_PROGRESS.value,
                ResearchRunStatus.PARTIAL.value,
            ),
        )
        if cursor.rowcount != 1:
            self.conn.rollback()
            raise ValueError(
                f"Research run #{research_run_id} cannot transition to PARTIAL_EXHAUSTED "
                "from its current status."
            )
        self.conn.commit()

    def mark_synthesis_pending(self, research_run_id: str) -> None:
        """Wołane TUŻ PRZED próbą etapu B — czysto obserwacyjne (jak `runs.current_state`),
        nie mechanizm odzyskiwania w locie (nie-streamowane wywołanie API i tak nie da
        się 'odzyskać' w połowie — awaria w trakcie po prostu traci TĘ próbę, tak jak
        zawsze; źródła i tak zostają nietknięte, więc kolejna próba jest tania)."""
        self.conn.execute(
            "UPDATE research_runs SET status=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.SYNTHESIS_PENDING.value, _ts(), research_run_id),
        )
        self.conn.commit()

    def revert_to_sources_complete(self, research_run_id: str, error: str) -> None:
        """Etap B nieudany — źródła (research_source_candidates) zostają nietknięte;
        status wraca do SOURCES_COMPLETE, żeby etap B można było ponowić bez powtarzania
        A1/A2. `error` zapisany dla widoczności/audytu, nie kasuje wcześniejszego sukcesu."""
        self.conn.execute(
            "UPDATE research_runs SET status=?, error=?, updated_at=? WHERE id=?",
            (ResearchRunStatus.SOURCES_COMPLETE.value, error, _ts(), research_run_id),
        )
        self.conn.commit()
