"""Hermetyczny replay całej orkiestracji artykułu V3.

Adapter zastępuje wyłącznie dwa efekty zewnętrzne: transport modelu i publiczny
fetch. Cała reszta biegnie przez normalne ``run.main`` oraz prawdziwe funkcje
``stages``: kontrakty, provenance, bramki, cache, SQLite i zapis artykułu.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Any
from unittest import mock

import trafilatura

import capabilities
import config
import db
import run
import safe_fetch
import stages


URLS = (
    "https://record-one.example/board-rule",
    "https://record-two.example/maintenance-sequence",
    "https://record-three.example/public-guide",
    "https://record-four.example/archive-procedure",
)

EXCERPTS = {
    URLS[0]: (
        "The Harbor Board assigns the first fixture decision to its recorded "
        "inspection panel."
    ),
    URLS[1]: (
        "The maintenance memorandum requires a written inspection before a "
        "replacement request can begin."
    ),
    URLS[2]: (
        "The public guide tells the reader that your fixture remains under the "
        "recorded rule until the board closes the case."
    ),
    URLS[3]: (
        "The archive procedure identifies the same board as the body that "
        "records the final disposition."
    ),
}

SOURCE_TEXTS = {
    url: (
        excerpt
        + "\n\n"
        + "The accompanying administrative record describes roles, forms, "
          "inspection order, custody, and the route by which a written decision "
          "moves through the office. " * 5
    )
    for url, excerpt in EXCERPTS.items()
}


@dataclass(frozen=True)
class ReplayResult:
    exit_code: int
    purposes: list[str]
    requested_capabilities: list[str]
    browser_imported: bool
    run_status: tuple[str, str] | None
    article_status: str | None
    call_rows: int
    contract_checks: int
    contract_failures: int
    source_rows: int
    fetched_rows: int
    document_rows: int
    fragment_rows: int
    claim_rows: int
    sentence_rows: int
    citation_rows: int
    revision_rows: int
    revision_statuses: list[str]
    article_files: list[str]
    remote_mutations: int
    known_cost_usd: float
    reserved_cost_usd: float
    unknown_calls: int
    routing_unchanged: bool
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _FixtureResponse:
    url: str
    text: str
    status_code: int = 200
    redirect_chain: tuple[str, ...] = ()
    resolved_ips: dict[str, list[str]] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {"content-type": "text/html; charset=utf-8"}

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


class _FixtureModels:
    def __init__(
        self, fail_purpose: str | None = None,
        revision_scenario: str | None = None,
    ) -> None:
        self.fail_purpose = fail_purpose
        self.revision_scenario = revision_scenario
        self.revision_calls = 0
        self.purposes: list[str] = []

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False)

    def __call__(
        self, purpose: str, _system: str, user: str, **kwargs: Any,
    ) -> str:
        self.purposes.append(purpose)
        if purpose == self.fail_purpose:
            raise RuntimeError(f"fixture failure at {purpose}")

        if purpose == "scout":
            payload = {
                "discarded_seeds": [{
                    "title": "A fixture lamp that blinks once",
                    "rejection": (
                        "One diagnostic code has one short documented answer, "
                        "so it cannot sustain independent articles."
                    ),
                }],
                "topics": [{
                    "title": "The Board Hidden Inside a Fixture Record",
                    "central_question": (
                        "Who gains authority when a shared technical object fails, "
                        "and how does that authority change after repeated failures?"
                    ),
                    "mode": "CONFLICT",
                    "why_fascinating": (
                        "A visible breakdown turns quiet divisions of expertise, "
                        "ownership and liability into decisions people can contest."
                    ),
                    "reader_entry_point": (
                        "A familiar object stops working while several people each "
                        "claim that somebody else must decide what happens next."
                    ),
                    "obvious_coverage": ["maintenance checklists"],
                    "underexplored_connections": [
                        "Repair records become informal constitutions by deciding whose diagnosis counts.",
                        "Insurance exclusions can move practical authority away from the nominal owner.",
                        "Repeated failures preserve organizational memory even after experienced staff leave.",
                    ],
                    "dimensions": [
                        {
                            "name": "authority",
                            "question_opened": "Who can stop use and order a remedy?",
                            "why_independent": "Legal power can differ from technical knowledge.",
                        },
                        {
                            "name": "liability",
                            "question_opened": "Who pays when every actor followed a narrow duty?",
                            "why_independent": "Payment rules can redirect behavior without changing diagnosis.",
                        },
                        {
                            "name": "memory",
                            "question_opened": "How do old failures remain legible after staff turnover?",
                            "why_independent": "Records outlive the people and contracts that created them.",
                        },
                    ],
                    "tensions": [
                        {
                            "force_a": "rapid restoration",
                            "force_b": "independent investigation",
                            "why_unresolved": "Evidence disappears when speed requires immediate replacement.",
                        },
                        {
                            "force_a": "central accountability",
                            "force_b": "distributed expertise",
                            "why_unresolved": "The actor answerable for harm may not understand the failure.",
                        },
                    ],
                    "open_branches": [
                        {
                            "possibility": "The owner consolidates control after each failure.",
                            "logic": "Liability rewards one auditable chain of command.",
                            "what_would_change_our_mind": "Records showing durable delegation after costly failures.",
                        },
                        {
                            "possibility": "Specialists gain authority without formal ownership.",
                            "logic": "Repeated exceptions make situated knowledge indispensable.",
                            "what_would_change_our_mind": "Cases where specialist advice is routinely overridden without cost.",
                        },
                        {
                            "possibility": "The record, not any actor, becomes the effective governor.",
                            "logic": "Audit and insurance make documented sequence more powerful than discretion.",
                            "what_would_change_our_mind": "Organizations that ignore the record yet retain coverage and trust.",
                        },
                    ],
                    "article_routes": [
                        {
                            "question": "When does a maintenance log become more powerful than the asset owner?",
                            "distinct_engine": "Auditability transfers practical authority to documented procedure.",
                            "evidence_needed": "Maintenance records, contracts, interviews and disputed repair decisions.",
                        },
                        {
                            "question": "How do insurers quietly decide who may authorize an emergency repair?",
                            "distinct_engine": "Coverage conditions redistribute control before a failure occurs.",
                            "evidence_needed": "Policy language, claims files, adjuster testimony and court records.",
                        },
                        {
                            "question": "What knowledge vanishes when the last experienced technician leaves?",
                            "distinct_engine": "Tacit exception knowledge resists formal transfer and standardization.",
                            "evidence_needed": "Retirement histories, incident timelines, manuals and worker interviews.",
                        },
                    ],
                    "note_test": {
                        "can_be_exhausted_in_three_sentences": False,
                        "why": "Authority, liability and memory require different records and can conflict.",
                    },
                    "fatal_weakness": (
                        "The territory could collapse into a generic accountability story "
                        "if the three mechanisms do not differ in real cases."
                    ),
                }],
                "ranking": {
                    "largest_article_universe": [0],
                    "most_compelling": [0],
                    "most_original_angle": [0],
                    "most_likely_to_collapse": [0],
                },
            }
            requested_match = re.search(
                r"Propose exactly\s+(\d+)\s+final topics", user,
            )
            requested = int(requested_match.group(1)) if requested_match else 1
            base_topic = payload["topics"][0]
            topics: list[dict[str, Any]] = []
            for index in range(requested):
                topic = json.loads(json.dumps(base_topic))
                topic["title"] = f"{base_topic['title']} {index + 1}"
                topic["central_question"] = (
                    f"{base_topic['central_question']} Case {index + 1} asks "
                    "which mechanism becomes decisive."
                )
                topic["mode"] = "CONFLICT" if index % 2 == 0 else "REVERSAL"
                topics.append(topic)
            ranking_size = min(3, requested)
            payload["topics"] = topics
            payload["ranking"] = {
                "largest_article_universe": list(range(ranking_size)),
                "most_compelling": list(range(ranking_size)),
                "most_original_angle": list(range(ranking_size)),
                "most_likely_to_collapse": list(
                    range(max(0, requested - ranking_size), requested)
                ),
            }
            return self._json(payload)

        if purpose == "feasibility":
            return self._json({"assessments": [{
                "index": 0, "feasible": True, "confidence": 0.95,
                "expected_primary_sources": 2, "depth": "RICH",
                "parallels": ["maintenance", "public administration"],
                "note": "The fixture corpus contains the governing records.",
                "route_assessments": [{
                    "route_index": 0, "feasible": True, "confidence": 0.95,
                    "expected_primary_sources": 2,
                    "depth": "RICH",
                    "second_act": (
                        "The record changes authority and liability after failure."
                    ),
                    "note": "The first route has two fixture records.",
                }],
                "selected_route_index": 0,
                "selected_route_reason": (
                    "The first route has the strongest fixture evidence."
                ),
            }]})

        if purpose == "discovery":
            collector = kwargs.get("collect_urls")
            if isinstance(collector, list):
                collector.extend(URLS)
            return self._json({"sources": [
                {
                    "url": url,
                    "title": f"Fixture record {index + 1}",
                    "publisher": f"Fixture authority {index + 1}",
                    "class": "PRIMARY" if index < 2 else "SUPPORTING",
                    "host_role": "ORIGINATING_AUTHORITY",
                    "access_claim": "FULL_TEXT_NO_LOGIN",
                    "published_at": "2026-08-21",
                    "evidence_status": "OBSERVED_CURRENT_RECORD",
                    "evidence_roles": [
                        "CURRENT_SCALE" if index == 0 else
                        "MECHANISM" if index == 1 else
                        "SECOND_ACT" if index == 2 else "BACKGROUND"
                    ],
                    "answers_why": index in {1, 2},
                    "has_numbers": False,
                    "note": "Frozen replay source.",
                }
                for index, url in enumerate(URLS)
            ]})

        if purpose == "classify":
            url = next((item for item in URLS if item in user), None)
            if url is None:
                raise AssertionError("classify prompt lacks a fixture URL")
            return self._json({
                "class": "PRIMARY" if URLS.index(url) < 2 else "SUPPORTING",
                "relevance": 0.95 - URLS.index(url) * 0.05,
                "excerpts": [EXCERPTS[url]],
                "note": "Exact frozen excerpt.",
            })

        if purpose == "synthesis":
            evidence = json.loads(user.split("## The evidence\n", 1)[1])
            claims = [
                {
                    "claim": source["fragments"][0]["text"],
                    "fragment_ids": [source["fragments"][0]["fragment_id"]],
                }
                for source in evidence
            ]
            return self._json({
                "working_thesis": (
                    "The visible failure is governed by an invisible written route."
                ),
                "main_mechanism": (
                    "The record separates inspection, request, and final decision "
                    "instead of leaving replacement to the first observer."
                ),
                "confirmed_claims": claims,
                "citable_numbers": [],
                "parallel_mechanisms": [
                    {"domain": "maintenance",
                     "how_it_matches": "A written gate assigns the next decision."},
                    {"domain": "public administration",
                     "how_it_matches": "Custody and authority move in separate steps."},
                ],
                "uncertain_claims": [], "contradictions": [],
                "not_established": [
                    "The records do not measure how quickly a case is completed."
                ],
            })

        if purpose == "warto_pisac":
            return self._json({
                "contradicted_belief": {
                    "present": True,
                    "the_belief": "The first observer simply orders the replacement",
                    "evidence": "The card assigns inspection and decision separately.",
                },
                "named_decider": {
                    "present": True, "evidence": "The Harbor Board is named."
                },
                "felt_number": {
                    "present": False, "evidence": "The fixture carries no figure."
                },
                "second_domain": {
                    "present": True,
                    "evidence": "The mechanism also appears in administration.",
                },
                "unsettled_outcome": {
                    "present": False, "the_question": "", "the_situation": "",
                    "governed_by": "The outcome in this replay is already recorded.",
                },
                "what_would_rescue_it": (
                    "A measured delay produced by the same split authority."
                ),
                "one_line_verdict": "The card breaks a belief and names a decider.",
            })

        if purpose == "write":
            card = json.loads(user.split("## The evidence card\n", 1)[1])
            claims = [claim["claim"] for claim in card["confirmed_claims"][:4]]
            paragraphs: list[str] = []
            while len(" ".join(paragraphs).split()) < 920:
                paragraphs.extend(claims)
            body = "\n\n".join(paragraphs)
            injected = {
                "resolve_fact": ["There were 12 accidents."],
                "no_improvement": ["There were 12 accidents."],
                "regression": ["There were 12 accidents."],
                "limit": [
                    "There were 12 accidents.",
                    "There were 13 injuries.",
                    "There were 14 closures.",
                ],
            }.get(self.revision_scenario, [])
            if injected:
                body += "\n\n" + " ".join(injected)
            return self._json({
                "title": "The Board Inside the Broken Fixture",
                "subtitle": "A visible failure follows an invisible written route.",
                "body": body, "numbers_used": [],
                "limits_paragraph_present": True,
            })

        if purpose == "review":
            card_text, sentence_text = user.split(
                "## The article sentence units\n", 1)
            card = json.loads(card_text.split("## The evidence card\n", 1)[1])
            sentences = json.loads(sentence_text)
            claims = card["confirmed_claims"]
            reviewed = []
            for index, sentence in enumerate(sentences):
                unsupported = any(
                    marker in sentence["text"]
                    for marker in (
                        "12 accidents", "13 injuries", "14 closures",
                    )
                )
                reviewed.append({
                    "sentence_id": sentence["sentence_id"],
                    "class": "FACT",
                    "support": "UNSUPPORTED" if unsupported else "SUPPORTED",
                    "claim_ids": (
                        [] if unsupported
                        else [claims[index % len(claims)]["claim_id"]]
                    ),
                    "why": "not present in the frozen card" if unsupported else "",
                })
            return self._json({
                "sentences": reviewed,
                "summary": "Every replay sentence maps to its frozen claim.",
            })

        if purpose == "forma":
            body = user.split("## The article\n", 1)[1]
            sentences = [item["text"] for item in stages.provenance.sentence_units(body)]
            return self._json({
                "beliefs": [
                    {"belief": f"Replay belief {index + 1}",
                     "first_stated": sentence}
                    for index, sentence in enumerate(sentences)
                ],
                "support_only": [],
                "hardest_fact": {"quote": sentences[-1], "why": "It names authority."},
                "procedural_nearby": {"quote": sentences[1]},
                "same_register": False,
                "reader_moment": {
                    "quote": sentences[2], "object": "the reader's fixture"
                },
                "opening_claim": {
                    "quote": sentences[0], "already_familiar": False
                },
                "summary": "The replay has distinct beats and a reader object.",
            })

        if purpose == "revise":
            self.revision_calls += 1
            draft_text = user.split("## Current draft\n", 1)[1]
            draft, _ = json.JSONDecoder().raw_decode(draft_text.lstrip())
            body = str(draft["body"])
            if self.revision_scenario == "resolve_fact":
                body = body.replace("\n\nThere were 12 accidents.", "")
            elif self.revision_scenario == "regression":
                body = body.replace("\n\nThere were 12 accidents.", "")
                body = "Turn over the fixture record. " + body
            elif self.revision_scenario == "limit":
                markers = (
                    "\n\nThere were 12 accidents.",
                    " There were 13 injuries.",
                    " There were 14 closures.",
                )
                marker = markers[min(self.revision_calls - 1, len(markers) - 1)]
                body = body.replace(marker, "", 1)
            return self._json({
                "title": draft["title"],
                "subtitle": draft.get("subtitle", ""),
                "body": body,
                "limits_paragraph_present": bool(
                    draft.get("limits_paragraph_present")),
                "changes": [f"fixture revision {self.revision_calls}"],
            })

        raise AssertionError(f"unexpected replay purpose {purpose!r}")


LIVE_CORE_PURPOSES = frozenset({
    "classify", "synthesis", "write", "review", "forma", "revise",
})
LIVE_REPLAY_MAX_USD = 1.50
EXPECTED_LIVE_ROUTING = {
    "classify": config.DEEPSEEK,
    "synthesis": config.DEEPSEEK_PRO,
    "write": config.FABLE,
    "review": config.DEEPSEEK_PRO,
    "forma": config.DEEPSEEK_PRO,
    "revise": config.FABLE,
}


class _LiveCoreModels(_FixtureModels):
    """Fixture dla wejścia potoku, prawdziwy transport dla rdzenia redakcyjnego."""

    def __init__(self) -> None:
        super().__init__()
        self._real_call = stages.llm.call

    def __call__(
        self, purpose: str, system: str, user: str, **kwargs: Any,
    ) -> str:
        if purpose in LIVE_CORE_PURPOSES:
            self.purposes.append(purpose)
            return self._real_call(purpose, system, user, **kwargs)
        return super().__call__(purpose, system, user, **kwargs)


def validate_live_preflight(max_cost_usd: float = LIVE_REPLAY_MAX_USD) -> None:
    """Odmawia przed plikiem, bazą i dispatch, jeśli live replay nie jest ścisły."""
    if capabilities.current_mode() is not capabilities.Mode.MODEL_TEST:
        raise RuntimeError("live replay requires AGENT_V3_MODE=model_test")
    if capabilities.kill_switch_active():
        raise RuntimeError("live replay requires AGENT_V3_KILL_SWITCH=0")
    if config.DRY_RUN:
        raise RuntimeError("live replay requires AGENT_V3_DRY_RUN=false")
    if config.CHEAP_MODE:
        raise RuntimeError("live replay forbids AGENT_V3_CHEAP override")
    if not 0 < float(max_cost_usd) <= LIVE_REPLAY_MAX_USD:
        raise RuntimeError(
            f"live replay max cost must be in (0, {LIVE_REPLAY_MAX_USD:.2f}] USD")
    actual = {purpose: config.MODEL_FOR[purpose] for purpose in EXPECTED_LIVE_ROUTING}
    if actual != EXPECTED_LIVE_ROUTING:
        raise RuntimeError(
            "live replay routing differs from normal V3: "
            + json.dumps(actual, sort_keys=True)
        )
    missing = []
    if not config.DEEPSEEK_API_KEY:
        missing.append("AGENT_V3_DEEPSEEK_API_KEY")
    if not config.ANTHROPIC_API_KEY:
        missing.append("AGENT_V3_ANTHROPIC_API_KEY")
    if missing:
        raise RuntimeError("missing credentials: " + ", ".join(missing))


def _scalar(conn: Any, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def _execute(
    workspace: pathlib.Path, *, model_driver: _FixtureModels,
    allowed_capabilities: frozenset[capabilities.Capability],
    enforce_runtime_policy: bool,
    run_limit_usd: float | None = None,
) -> ReplayResult:
    workspace = workspace.resolve()
    data_dir = workspace / "data"
    articles_dir = data_dir / "articles"
    db_path = data_dir / "replay.db"
    cache_dir = data_dir / "cache"
    data_dir.mkdir(parents=True, exist_ok=True)

    requested_capabilities: list[str] = []
    real_require = capabilities.require
    routing_before = dict(config.MODEL_FOR)

    def require_replay(capability: capabilities.Capability | str) -> None:
        requested = capabilities.Capability(capability)
        requested_capabilities.append(requested.value)
        if requested not in allowed_capabilities:
            raise capabilities.CapabilityDenied(
                f"replay forbids capability {requested.value!r}")
        if enforce_runtime_policy:
            real_require(requested)

    def fixture_get(url: str, **_kwargs: Any) -> _FixtureResponse:
        normalized = safe_fetch.normalize_url(url)
        if normalized not in SOURCE_TEXTS:
            raise safe_fetch.SafeFetchError(f"URL outside frozen replay: {url}")
        return _FixtureResponse(
            url=normalized, text=SOURCE_TEXTS[normalized],
            resolved_ips={normalized.split("/", 3)[2]: ["192.0.2.10"]},
        )

    stdout = io.StringIO()
    stderr = io.StringIO()
    browser_before = "browser" in sys.modules
    path_patches = (
        mock.patch.object(config, "DATA_DIR", data_dir),
        mock.patch.object(config, "DB_PATH", db_path),
        mock.patch.object(config, "ARTICLES_DIR", articles_dir),
        mock.patch.object(run, "CACHE_DIR", cache_dir),
        mock.patch.object(stages, "ZUZYTE_FAKTY", data_dir / "zuzyte_fakty.json"),
        mock.patch.object(stages, "PROMOCJA", data_dir / "promocja.json"),
        mock.patch.object(stages, "BANK_NOTEK", data_dir / "bank_notek.json"),
        mock.patch.object(
            stages, "PYTANIA_CZYTELNIKOW", data_dir / "pytania_czytelnikow.json"),
        mock.patch.object(
            stages, "INDEKS_KANDYDATOW", data_dir / "indeks_kandydatow.json"),
    )

    with path_patches[0], path_patches[1], path_patches[2], path_patches[3], \
            path_patches[4], path_patches[5], path_patches[6], path_patches[7], \
            path_patches[8], \
            mock.patch.object(
                config, "RUN_LIMIT_USD",
                float(run_limit_usd) if run_limit_usd is not None
                else config.RUN_LIMIT_USD), \
            mock.patch.object(stages.llm, "call", side_effect=model_driver), \
            mock.patch.object(stages.safe_fetch, "get", side_effect=fixture_get), \
            mock.patch.object(
                trafilatura, "extract", side_effect=lambda text, **_kwargs: text), \
            mock.patch.object(capabilities, "require", side_effect=require_replay), \
            mock.patch.object(sys, "argv", ["run.py", "--topics", "1"]), \
            redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = run.main()

    browser_imported = not browser_before and "browser" in sys.modules
    conn = db.connect(db_path)
    try:
        run_row = conn.execute(
            "SELECT status, stage FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        article_row = conn.execute(
            "SELECT status FROM articles ORDER BY id DESC LIMIT 1"
        ).fetchone()
        cost_row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), "
            "COALESCE(SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') "
            "THEN reserved_usd ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN cost_status='UNKNOWN' THEN 1 ELSE 0 END), 0) "
            "FROM calls"
        ).fetchone()
        result = ReplayResult(
            exit_code=exit_code,
            purposes=list(model_driver.purposes),
            requested_capabilities=requested_capabilities,
            browser_imported=browser_imported,
            run_status=((str(run_row["status"]), str(run_row["stage"]))
                        if run_row else None),
            article_status=str(article_row["status"]) if article_row else None,
            call_rows=_scalar(conn, "SELECT COUNT(*) FROM calls"),
            contract_checks=_scalar(
                conn, "SELECT COUNT(*) FROM model_contract_checks"),
            contract_failures=_scalar(
                conn, "SELECT COUNT(*) FROM model_contract_checks WHERE ok=0"),
            source_rows=_scalar(conn, "SELECT COUNT(*) FROM sources"),
            fetched_rows=_scalar(
                conn, "SELECT COUNT(*) FROM sources WHERE fetched_ok=1"),
            document_rows=_scalar(
                conn, "SELECT COUNT(*) FROM provenance_documents"),
            fragment_rows=_scalar(
                conn, "SELECT COUNT(*) FROM provenance_fragments"),
            claim_rows=_scalar(conn, "SELECT COUNT(*) FROM article_claims"),
            sentence_rows=_scalar(
                conn, "SELECT COUNT(*) FROM article_sentences"),
            citation_rows=_scalar(
                conn, "SELECT COUNT(*) FROM article_citations"),
            revision_rows=_scalar(
                conn, "SELECT COUNT(*) FROM article_revisions"),
            revision_statuses=[
                str(row["status"])
                for row in conn.execute(
                    "SELECT status FROM article_revisions ORDER BY iteration"
                ).fetchall()
            ],
            article_files=sorted(
                path.name for path in articles_dir.glob("*.md")
                if not path.name.endswith(".uwagi.md")
            ) if articles_dir.exists() else [],
            remote_mutations=0,
            known_cost_usd=float(cost_row[0]),
            reserved_cost_usd=float(cost_row[1]),
            unknown_calls=int(cost_row[2]),
            routing_unchanged=dict(config.MODEL_FOR) == routing_before,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )
    finally:
        conn.close()
    return result


def run_fixture(
    workspace: pathlib.Path, *, fail_purpose: str | None = None,
    revision_scenario: str | None = None,
) -> ReplayResult:
    """Wykonuje jeden pełny przebieg bez sieci, modeli i Substacka."""
    return _execute(
        workspace,
        model_driver=_FixtureModels(fail_purpose, revision_scenario),
        allowed_capabilities=frozenset({capabilities.Capability.PUBLIC_WEB_READ}),
        enforce_runtime_policy=False,
    )


def run_model_live(
    workspace: pathlib.Path, *, max_cost_usd: float = LIVE_REPLAY_MAX_USD,
) -> ReplayResult:
    """Prawdziwe modele rdzenia na zamrożonym korpusie, bez zewnętrznego fetchu."""
    validate_live_preflight(max_cost_usd)
    return _execute(
        workspace,
        model_driver=_LiveCoreModels(),
        allowed_capabilities=frozenset({
            capabilities.Capability.MODEL_CALL,
            capabilities.Capability.PUBLIC_WEB_READ,
        }),
        enforce_runtime_policy=True,
        run_limit_usd=max_cost_usd,
    )
