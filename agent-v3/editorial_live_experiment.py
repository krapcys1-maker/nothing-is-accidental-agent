"""Kontrolowany eksperyment live całego systemu redakcyjnego V3.

Badanie rozdziela dwa pytania, których jeden liniowy przebieg nie potrafi
odróżnić:

1. naturalny łańcuch ``scout -> feasibility -> discovery -> fetch -> classify
   -> synthesis -> warto_pisac`` na wejściu wymyślonym przez bieżący model;
2. kontrolowane próby pisarza, profilu stylu, rewizji i Notes na tym samym
   materiale. Dzięki temu awaria discovery nie zasłania zachowania pisarza.

Moduł nie importuje browsera, nie zna sesji Substacka i dopuszcza wyłącznie
``MODEL_CALL`` oraz ``PUBLIC_WEB_READ``. Każdy prompt, wynik, koszt i błąd trafia
do odizolowanego artefaktu w katalogu eksperymentu.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import statistics
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Callable
from unittest import mock
from urllib.parse import urlsplit

import capabilities
import config
import db
import editorial
import gates
import llm
import provenance
import safe_fetch
import stages
import style


HISTORICAL_COST_USD = 0.07558670
USER_GLOBAL_LIMIT_USD = 10.00
LIVE_EXPERIMENT_MAX_USD = 4.50
MAX_FETCH_SOURCES = 4
SCOUT_REPLICATIONS = 2
NOTE_FORMS = ("PROSTA", "LICZBA", "SCENA", "ODWROCENIE", "ZACZEP_I_KONKRET")

EXPECTED_ROUTING = {
    "scout": config.DEEPSEEK_PRO,
    "feasibility": config.DEEPSEEK,
    "discovery": config.DEEPSEEK_PRO,
    "classify": config.DEEPSEEK,
    "synthesis": config.DEEPSEEK_PRO,
    "warto_pisac": config.DEEPSEEK_PRO,
    "write": config.FABLE,
    "review": config.DEEPSEEK_PRO,
    "forma": config.DEEPSEEK_PRO,
    "revise": config.FABLE,
    "note": config.CLAUDE,
    "factcheck": config.DEEPSEEK,
}

# Maksymalna liczba wywołań ``llm.call``. Weryfikacja Notes jest leniwa, więc
# realna liczba może być mniejsza. Discovery może wykonać drugi request wyboru
# URL wewnątrz jednej zarezerwowanej pozycji ledgeru.
MAX_LEDGERED_MODEL_CALLS = 32
MAX_CALLS_BY_MODEL = {
    config.DEEPSEEK_PRO: 14,
    config.DEEPSEEK: 10,
    config.FABLE: 3,
    config.CLAUDE: 5,
}

ALLOWED_CAPABILITIES = frozenset({
    capabilities.Capability.MODEL_CALL,
    capabilities.Capability.PUBLIC_WEB_READ,
})


class ExperimentStopped(RuntimeError):
    """Kontrolowany stop po nieznanym koszcie lub przekroczeniu kontraktu."""


@dataclass(frozen=True)
class ExperimentPaths:
    workspace: pathlib.Path
    data: pathlib.Path
    database: pathlib.Path
    articles: pathlib.Path
    partial: pathlib.Path
    result: pathlib.Path


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    """Kopia JSON bez obcinania surowych wyników modelu."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True,
                  default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_preflight(
    workspace: pathlib.Path, max_cost_usd: float = LIVE_EXPERIMENT_MAX_USD,
) -> None:
    """Odmowa przed utworzeniem katalogu i przed pierwszym dispatch."""
    agent_root = pathlib.Path(__file__).resolve().parent
    resolved = workspace.resolve()
    if not _inside(resolved, agent_root) or resolved == agent_root:
        raise RuntimeError("workspace eksperymentu musi być nowym podkatalogiem agent-v3")
    if workspace.exists():
        raise RuntimeError("workspace eksperymentu nie może istnieć przed dispatch")
    if capabilities.current_mode() is not capabilities.Mode.MODEL_TEST:
        raise RuntimeError("eksperyment live wymaga AGENT_V3_MODE=model_test")
    if capabilities.kill_switch_active():
        raise RuntimeError("eksperyment live wymaga AGENT_V3_KILL_SWITCH=0")
    if config.DRY_RUN:
        raise RuntimeError("eksperyment live wymaga AGENT_V3_DRY_RUN=false")
    if config.CHEAP_MODE:
        raise RuntimeError("eksperyment zabrania AGENT_V3_CHEAP")
    if not 0 < float(max_cost_usd) <= LIVE_EXPERIMENT_MAX_USD:
        raise RuntimeError(
            f"max-cost-usd musi być w (0, {LIVE_EXPERIMENT_MAX_USD:.2f}]"
        )
    if HISTORICAL_COST_USD + float(max_cost_usd) > USER_GLOBAL_LIMIT_USD:
        raise RuntimeError("plan przekracza globalny limit użytkownika 10 USD")
    # Pisarz jest najdroższym etapem. Integralność jego głosu musi być
    # rozstrzygnięta teraz, a nie po opłaceniu scouta i researchu.
    style.load_examples()
    style.load_profiles()
    actual = {purpose: config.MODEL_FOR.get(purpose) for purpose in EXPECTED_ROUTING}
    if actual != EXPECTED_ROUTING:
        raise RuntimeError(
            "routing odbiega od normalnego V3: "
            + json.dumps(actual, sort_keys=True)
        )
    missing: list[str] = []
    if not config.DEEPSEEK_API_KEY:
        missing.append("AGENT_V3_DEEPSEEK_API_KEY")
    if not config.ANTHROPIC_API_KEY:
        missing.append("AGENT_V3_ANTHROPIC_API_KEY")
    if missing:
        raise RuntimeError("brak lokalnych kluczy: " + ", ".join(missing))


def _paths(workspace: pathlib.Path) -> ExperimentPaths:
    root = workspace.resolve()
    data = root / "data"
    return ExperimentPaths(
        workspace=root,
        data=data,
        database=data / "experiment.db",
        articles=data / "articles",
        partial=root / "result.partial.json",
        result=root / "result.json",
    )


def _is_substack(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == "substack.com" or host.endswith(".substack.com")


def _controlled_fixture() -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Zamrożona karta do prób pisarza, gdy naturalny research padnie.

    Fikcyjność jest jawna i zapisana w artefakcie. Fixture bada zachowanie
    modelu wobec karty, a nie prawdziwość rozporządzenia.
    """
    question = "What did the Harbor Lighting Ordinance require and establish?"
    source_text = (
        "The Harbor Lighting Ordinance took effect on January 1, 2025. "
        "Section 4 requires municipal walkways to use fixtures rated at no more "
        "than 20 watts. The rule applies only to fixtures installed after the "
        "effective date. A city pilot covered 240 fixtures across six parks. "
        "The audit recorded an 18% reduction in electricity use during its first "
        "6 months. The audit did not measure pedestrian safety or maintenance "
        "costs. Existing fixtures may remain until replacement."
    )
    excerpts = [
        "The Harbor Lighting Ordinance took effect on January 1, 2025.",
        (
            "Section 4 requires municipal walkways to use fixtures rated at no "
            "more than 20 watts."
        ),
        "The rule applies only to fixtures installed after the effective date.",
        "A city pilot covered 240 fixtures across six parks.",
        (
            "The audit recorded an 18% reduction in electricity use during its "
            "first 6 months."
        ),
        "The audit did not measure pedestrian safety or maintenance costs.",
        "Existing fixtures may remain until replacement.",
    ]
    source = {
        "url": "https://fixture.invalid/harbor-lighting-ordinance",
        "title": "Harbor Lighting Ordinance and pilot audit",
        "publisher": "Fixture City Records",
        "host": "fixture.invalid",
        "text": source_text,
    }
    item = provenance.fragments_from_excerpts(source, excerpts)
    item.update({"class": "PRIMARY", "relevance": 1.0, "note": "fixture"})
    evidence = [item]
    fragments = item["fragments"]
    number_by_value = {number["value"]: number for number in item["numbers"]}
    raw_card = {
        "working_thesis": "The rule phases a narrow requirement through replacement.",
        "main_mechanism": "A prospective equipment rule changes the stock gradually.",
        "confirmed_claims": [
            {"claim": "The ordinance took effect on January 1, 2025.",
             "fragment_ids": [fragments[0]["fragment_id"]]},
            {"claim": "Section 4 caps new municipal walkway fixtures at 20 watts.",
             "fragment_ids": [fragments[1]["fragment_id"], fragments[2]["fragment_id"]]},
            {"claim": "The pilot covered 240 fixtures across six parks.",
             "fragment_ids": [fragments[3]["fragment_id"]]},
            {"claim": "The audit recorded an 18% electricity reduction over 6 months.",
             "fragment_ids": [fragments[4]["fragment_id"]]},
            {"claim": "The audit did not measure safety or maintenance costs.",
             "fragment_ids": [fragments[5]["fragment_id"]]},
            {"claim": "Existing fixtures may remain until replacement.",
             "fragment_ids": [fragments[6]["fragment_id"]]},
        ],
        "citable_numbers": [
            {"number_id": number_by_value["20"]["number_id"],
             "means": "maximum fixture wattage", "claim_index": 1},
            {"number_id": number_by_value["240"]["number_id"],
             "means": "fixtures in the pilot", "claim_index": 2},
            {"number_id": number_by_value["18%"]["number_id"],
             "means": "recorded electricity reduction", "claim_index": 3},
        ],
        "parallel_mechanisms": [],
        "uncertain_claims": [],
        "contradictions": [],
        "not_established": ["The fixture does not establish any safety effect."],
    }
    return question, evidence, provenance.bind_card(raw_card, evidence)


def _topic_tokens(topic: dict[str, Any]) -> set[str]:
    text = f"{topic.get('title', '')} {topic.get('question', '')}".lower()
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def assess_scout(replications: list[list[dict[str, Any]]]) -> dict[str, Any]:
    per_run = []
    for topics in replications:
        modes = {
            str(topic.get("mode") or topic.get("kind") or "").strip()
            for topic in topics
            if str(topic.get("mode") or topic.get("kind") or "").strip()
        }
        per_run.append({
            "count": len(topics),
            "unique_titles": len({str(t.get('title', '')).strip().lower() for t in topics}),
            "nosne": sum(bool(t.get("nosny")) for t in topics),
            "na_artykul": sum(bool(t.get("na_artykul")) for t in topics),
            "nasycone": sum(bool(t.get("nasycony")) for t in topics),
            "distinct_invention_modes": len(modes),
            "modes": sorted(modes),
            "mean_dimensions": round(statistics.fmean(
                int(t.get("ile_osi") or len(t.get("dimensions") or []))
                for t in topics
            ), 2) if topics else 0.0,
            "mean_article_routes": round(statistics.fmean(
                int(t.get("ile_watkow") or len(t.get("article_routes") or []))
                for t in topics
            ), 2) if topics else 0.0,
            "mean_distinct_engines": round(statistics.fmean(
                int(t.get("ile_mechanizmow") or 0) for t in topics
            ), 2) if topics else 0.0,
            "titles": [t.get("title") for t in topics],
        })
    stability: dict[str, Any] = {"available": len(replications) >= 2}
    if len(replications) >= 2:
        left, right = replications[0], replications[1]
        best = [
            max((_jaccard(_topic_tokens(topic), _topic_tokens(other)) for other in right),
                default=0.0)
            for topic in left
        ]
        stability.update({
            "exact_title_overlap": len(
                {str(t.get('title', '')).strip().lower() for t in left}
                & {str(t.get('title', '')).strip().lower() for t in right}
            ),
            "mean_best_token_jaccard": round(statistics.fmean(best), 4) if best else 0.0,
            "best_token_jaccard_per_topic": [round(value, 4) for value in best],
        })
    return {"runs": per_run, "stability": stability}


def _draft_features(
    draft: dict[str, Any], card: dict[str, Any], glebokosc: str | None = None,
) -> dict[str, Any]:
    body = str(draft.get("body") or "")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    sentence_units = provenance.sentence_units(body)
    sentence_lengths = [len(unit["text"].split()) for unit in sentence_units]
    findings = gates.deterministic_floors(
        body, card, poprzednie=[], glebokosc=glebokosc
    )
    return {
        "title": draft.get("title"),
        "subtitle": draft.get("subtitle"),
        "body_sha256": _sha256_text(body),
        "words": len(body.split()),
        "paragraphs": len(paragraphs),
        "sentences": len(sentence_units),
        "median_sentence_words": (
            round(statistics.median(sentence_lengths), 2) if sentence_lengths else 0
        ),
        "paragraph_word_counts": [len(part.split()) for part in paragraphs],
        "first_sentence": sentence_units[0]["text"] if sentence_units else "",
        "last_sentence": sentence_units[-1]["text"] if sentence_units else "",
        "deterministic_findings": findings,
    }


def _style_judge_prompt(first: dict[str, Any], second: dict[str, Any]) -> str:
    return (
        "Blindly compare ARTICLE A and ARTICLE B. You do not know which one got "
        "the editorial style profile. Score each 0-4 on: concrete opening, "
        "concrete-to-system movement, mechanism clarity, counterargument, "
        "paragraph rhythm, specificity, non-generic voice, and ending. For every "
        "score give one short exact quote as evidence. Then choose A, B or TIE. "
        "Do not judge factual support; both were written from the same card.\n\n"
        "Return only JSON: {\"A\": {\"scores\": {\"concrete_opening\": 0, "
        "\"concrete_to_system\": 0, \"mechanism\": 0, \"counterargument\": 0, "
        "\"paragraph_rhythm\": 0, \"specificity\": 0, \"non_generic_voice\": 0, "
        "\"ending\": 0}, \"evidence\": [\"...\"]}, \"B\": {\"scores\": {}, "
        "\"evidence\": [\"...\"]}, \"winner\": \"A|B|TIE\", "
        "\"reason\": \"...\"}.\n\n"
        f"ARTICLE A\n{json.dumps(first, ensure_ascii=False)}\n\n"
        f"ARTICLE B\n{json.dumps(second, ensure_ascii=False)}"
    )


def _parse_style_judgment(raw: str) -> dict[str, Any]:
    value = llm.parse_json(raw)
    if not isinstance(value, dict) or value.get("winner") not in {"A", "B", "TIE"}:
        raise ValueError("sędzia stylu nie zwrócił A/B/TIE")
    for label in ("A", "B"):
        side = value.get(label)
        if not isinstance(side, dict) or not isinstance(side.get("scores"), dict):
            raise ValueError(f"sędzia stylu nie zwrócił rubryki {label}")
        for score in side["scores"].values():
            if not isinstance(score, (int, float)) or not 0 <= score <= 4:
                raise ValueError(f"wynik stylu poza zakresem: {score!r}")
    return value


def _call_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        "SELECT id, run_id, at, provider, model, purpose, tokens_in, tokens_out, "
        "cache_hit, web_searches, cost_usd, cost_status, reserved_usd, "
        "price_verified, ok, note FROM calls ORDER BY id"
    )]


def _cost_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT provider, cost_status, COUNT(*) AS n, SUM(cost_usd) AS known, "
        "SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') THEN reserved_usd "
        "ELSE 0 END) AS unresolved FROM calls GROUP BY provider, cost_status "
        "ORDER BY provider, cost_status"
    ).fetchall()
    known = float(conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) FROM calls"
    ).fetchone()[0])
    unresolved = float(conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') "
        "THEN reserved_usd ELSE 0 END),0) FROM calls"
    ).fetchone()[0])
    return {
        "known_usd": known,
        "reserved_or_unknown_usd": unresolved,
        "new_exposure_usd": known + unresolved,
        "program_exposure_including_history_usd": HISTORICAL_COST_USD + known + unresolved,
        "by_provider_and_status": [dict(row) for row in rows],
    }


def run_experiment(
    workspace: pathlib.Path, *, max_cost_usd: float = LIVE_EXPERIMENT_MAX_USD,
) -> dict[str, Any]:
    validate_preflight(workspace, max_cost_usd)
    paths = _paths(workspace)
    paths.data.mkdir(parents=True, exist_ok=False)
    paths.articles.mkdir(parents=True, exist_ok=True)

    routing_before = dict(config.MODEL_FOR)
    browser_before = "browser" in sys.modules
    requested_capabilities: list[str] = []
    result: dict[str, Any] = {
        "experiment": "editorial-system-live@1",
        "status": "RUNNING",
        "started_at": db.now(),
        "constraints": {
            "historical_cost_usd": HISTORICAL_COST_USD,
            "new_max_cost_usd": float(max_cost_usd),
            "program_max_exposure_usd": HISTORICAL_COST_USD + float(max_cost_usd),
            "global_user_limit_usd": USER_GLOBAL_LIMIT_USD,
            "max_ledgered_model_calls": MAX_LEDGERED_MODEL_CALLS,
            "max_calls_by_model": MAX_CALLS_BY_MODEL,
            "max_public_fetches": MAX_FETCH_SOURCES,
            "substack": "FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION",
        },
        "routing": EXPECTED_ROUTING,
        "style_assets": {
            "corpus": str(config.STYLE_CORPUS),
            "corpus_sha256_expected": config.STYLE_CORPUS_SHA256,
            "corpus_sha256_canonical": style.corpus_sha256(),
            "corpus_sha256_raw_checkout": hashlib.sha256(
                config.STYLE_CORPUS.read_bytes()
            ).hexdigest(),
        },
        "calls_raw": [],
        "phases": {},
        "requested_capabilities": requested_capabilities,
    }

    conn: sqlite3.Connection | None = None

    def checkpoint() -> None:
        if conn is not None:
            result["cost"] = _cost_summary(conn)
            result["call_ledger"] = _call_rows(conn)
        _atomic_json(paths.partial, result)

    real_require = capabilities.require
    real_get = safe_fetch.get
    real_call = llm.call

    def controlled_require(capability: capabilities.Capability | str) -> None:
        requested = capabilities.Capability(capability)
        requested_capabilities.append(requested.value)
        if requested not in ALLOWED_CAPABILITIES:
            raise capabilities.CapabilityDenied(
                f"eksperyment zabrania capability {requested.value!r}"
            )
        real_require(requested)

    def controlled_get(url: str, **kwargs: Any) -> Any:
        normalized = safe_fetch.normalize_url(url)
        if _is_substack(normalized):
            raise safe_fetch.SafeFetchError("eksperyment bezwarunkowo blokuje Substack")
        return real_get(normalized, **kwargs)

    def captured_call(
        purpose: str, system: str, user: str, **kwargs: Any,
    ) -> str:
        if len(result["calls_raw"]) >= MAX_LEDGERED_MODEL_CALLS:
            raise ExperimentStopped("osiągnięto maksymalną liczbę dispatchy")
        started = time.monotonic()
        item: dict[str, Any] = {
            "ordinal": len(result["calls_raw"]) + 1,
            "purpose": purpose,
            "model": config.MODEL_FOR[purpose],
            "system": system,
            "system_sha256": _sha256_text(system),
            "user": user,
            "user_sha256": _sha256_text(user),
            "web_search": bool(kwargs.get("web_search")),
            "started_at": db.now(),
        }
        result["calls_raw"].append(item)
        checkpoint()
        try:
            text = real_call(purpose, system, user, **kwargs)
            item["response"] = text
            item["response_sha256"] = _sha256_text(text)
            item["error"] = None
            return text
        except BaseException as exc:
            item["response"] = None
            item["response_sha256"] = None
            item["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            item["finished_at"] = db.now()
            item["seconds"] = round(time.monotonic() - started, 3)
            checkpoint()

    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(config, "DATA_DIR", paths.data))
        stack.enter_context(mock.patch.object(config, "DB_PATH", paths.database))
        stack.enter_context(mock.patch.object(config, "ARTICLES_DIR", paths.articles))
        stack.enter_context(mock.patch.object(config, "DAILY_LIMIT_USD", float(max_cost_usd)))
        stack.enter_context(mock.patch.object(stages, "ZUZYTE_FAKTY", paths.data / "zuzyte_fakty.json"))
        stack.enter_context(mock.patch.object(stages, "PROMOCJA", paths.data / "promocja.json"))
        stack.enter_context(mock.patch.object(stages, "BANK_NOTEK", paths.data / "bank_notek.json"))
        stack.enter_context(mock.patch.object(stages, "PYTANIA_CZYTELNIKOW", paths.data / "pytania.json"))
        stack.enter_context(mock.patch.object(stages, "INDEKS_KANDYDATOW", paths.data / "indeks.json"))
        stack.enter_context(mock.patch.object(capabilities, "require", side_effect=controlled_require))
        stack.enter_context(mock.patch.object(safe_fetch, "get", side_effect=controlled_get))
        stack.enter_context(mock.patch.object(llm, "call", side_effect=captured_call))

        conn = db.connect(paths.database)
        current_run: int | None = None

        def ensure_cost_known() -> None:
            unknown = int(conn.execute(
                "SELECT COUNT(*) FROM calls WHERE cost_status IN ('RESERVED','UNKNOWN')"
            ).fetchone()[0])
            if unknown:
                raise ExperimentStopped(
                    f"{unknown} kosztów RESERVED/UNKNOWN — stop bez dalszych dispatchy"
                )
            exposure = db.financial_exposure(conn)
            if exposure > float(max_cost_usd) + 1e-9:
                raise ExperimentStopped(
                    f"ekspozycja ${exposure:.6f} przekroczyła cap ${max_cost_usd:.6f}"
                )

        def phase(name: str, function: Callable[[int], Any]) -> Any:
            nonlocal current_run
            current_run = db.start_run(conn, stage=name)
            started = time.monotonic()
            entry: dict[str, Any] = {
                "run_id": current_run,
                "started_at": db.now(),
                "status": "RUNNING",
            }
            result["phases"][name] = entry
            checkpoint()
            try:
                value = function(current_run)
                entry.update({
                    "status": "PASS",
                    "error": None,
                    "value": _jsonable(value),
                })
                db.finish_run(conn, current_run, "DONE", name, "")
                return value
            except ExperimentStopped:
                db.finish_run(conn, current_run, "FAILED", name, "controlled stop")
                entry["status"] = "STOP"
                raise
            except BaseException as exc:
                entry.update({
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                    "value": None,
                })
                db.finish_run(
                    conn, current_run, "FAILED", name,
                    f"{type(exc).__name__}: {exc}"[:500],
                )
                return None
            finally:
                entry["finished_at"] = db.now()
                entry["seconds"] = round(time.monotonic() - started, 3)
                checkpoint()
                ensure_cost_known()

        try:
            # A. Dwie identycznie zasilone próby skauta: jakość i stabilność.
            scout_runs: list[list[dict[str, Any]]] = []
            for index in range(SCOUT_REPLICATIONS):
                topics = phase(
                    f"scout_replication_{index + 1}",
                    lambda run_id: stages.scout(
                        conn, run_id, count=config.TOPIC_COUNT, editorial_memory={}
                    ),
                )
                if topics:
                    scout_runs.append(topics)
            result["scout_assessment"] = assess_scout(scout_runs)
            checkpoint()

            topics_a = scout_runs[0] if scout_runs else None
            assessments = phase(
                "feasibility",
                lambda run_id: stages.feasibility(conn, run_id, topics_a),
            ) if topics_a else None
            selected_topic: dict[str, Any] | None = None
            selected_assessment: dict[str, Any] | None = None
            if topics_a and assessments:
                selected_topic, selected_assessment = stages.pick_topic(topics_a, assessments)
                result["selected_topic"] = {
                    "topic": selected_topic,
                    "assessment": selected_assessment,
                }
                checkpoint()

            discovered = phase(
                "discovery",
                lambda run_id: stages.discovery(
                    conn, run_id, selected_topic["question"], []
                ),
            ) if selected_topic else None
            permitted_sources = [
                source for source in (discovered or [])
                if not _is_substack(str(source.get("url") or ""))
            ][:MAX_FETCH_SOURCES]
            result["source_filter"] = {
                "discovered": len(discovered or []),
                "substack_rejected": len(discovered or []) - len([
                    source for source in (discovered or [])
                    if not _is_substack(str(source.get("url") or ""))
                ]),
                "selected_for_fetch": len(permitted_sources),
                "urls": [source.get("url") for source in permitted_sources],
            }
            checkpoint()

            corpus = phase(
                "fetch_public_web",
                lambda run_id: stages.fetch(conn, run_id, permitted_sources),
            ) if permitted_sources else None
            evidence = phase(
                "classify",
                lambda run_id: stages.classify(
                    conn, run_id, selected_topic["question"], corpus
                ),
            ) if corpus and selected_topic else None
            natural_card = phase(
                "synthesis",
                lambda run_id: stages.synthesis(
                    conn, run_id, selected_topic["question"], evidence
                ),
            ) if evidence and selected_topic else None
            natural_interest = phase(
                "warto_pisac",
                lambda run_id: stages.warto_pisac(conn, run_id, natural_card),
            ) if natural_card else None
            result["natural_chain"] = {
                "topic_available": selected_topic is not None,
                "fetched_documents": len(corpus or []),
                "evidence_documents": len(evidence or []),
                "card_available": natural_card is not None,
                "interest": natural_interest,
            }
            checkpoint()

            fixture_question, fixture_evidence, fixture_card = _controlled_fixture()
            if natural_card and evidence:
                writing_question = selected_topic["question"]
                writing_evidence = evidence
                writing_card = natural_card
                writing_depth = str((selected_assessment or {}).get("depth") or "RICH")
                writing_source = "NATURAL_LIVE_CHAIN"
            else:
                writing_question = fixture_question
                writing_evidence = fixture_evidence
                writing_card = fixture_card
                writing_depth = "RICH"
                writing_source = "SYNTHETIC_CONTROL_AFTER_NATURAL_CHAIN_FAILURE"
            result["writing_input"] = {
                "source": writing_source,
                "question": writing_question,
                "evidence": writing_evidence,
                "card": writing_card,
                "depth": writing_depth,
            }
            checkpoint()

            # B. Jedyna interwencja A/B to obecność zatwierdzonego stylu.
            fixed_ending = config.losowy_ruch_koncowy()
            fixed_parallels = config.losowa_liczba_paraleli(writing_depth)
            result["style_intervention"] = {
                "held_constant": {
                    "card_sha256": _sha256_text(json.dumps(
                        writing_card, ensure_ascii=False, sort_keys=True
                    )),
                    "depth": writing_depth,
                    "ending": fixed_ending,
                    "parallels": fixed_parallels,
                    "model": config.MODEL_FOR["write"],
                },
                "variable": "approved style examples and positive/negative profiles",
                "limitation": "one stochastic pair; causal estimate is preliminary",
            }

            def write_styled(run_id: int) -> dict[str, Any]:
                with mock.patch.object(config, "losowy_ruch_koncowy", return_value=fixed_ending), \
                        mock.patch.object(
                            config, "losowa_liczba_paraleli", return_value=fixed_parallels
                        ):
                    return stages.write(conn, run_id, writing_card, writing_depth, {})

            styled = phase("write_with_style", write_styled)

            def write_ablated(run_id: int) -> dict[str, Any]:
                with mock.patch.object(config, "losowy_ruch_koncowy", return_value=fixed_ending), \
                        mock.patch.object(
                            config, "losowa_liczba_paraleli", return_value=fixed_parallels
                        ), \
                        mock.patch.object(style, "load_examples", return_value=[]), \
                        mock.patch.object(
                            style, "load_profiles",
                            return_value=(
                                "No editorial style profile supplied.",
                                "No editorial negative profile supplied.",
                            ),
                        ):
                    return stages.write(conn, run_id, writing_card, writing_depth, {})

            ablated = phase("write_without_style_ablation", write_ablated)

            def observe(label: str, draft: dict[str, Any] | None) -> dict[str, Any] | None:
                if not draft:
                    return None

                def run_observation(run_id: int) -> dict[str, Any]:
                    review = stages.review(conn, run_id, writing_card, draft)
                    form = stages.ocen_forme(conn, run_id, draft)
                    _, lineage = provenance.finalize_card(
                        writing_card, writing_evidence, review, draft["body"]
                    )
                    findings = gates.deterministic_floors(
                        draft["body"], writing_card, poprzednie=[]
                    )
                    findings.extend(lineage)
                    findings.extend(gates.uwagi_z_formy(form, draft["body"]))
                    findings.extend({
                        "gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")
                    } for item in review.get("unsupported_facts", []))
                    return {
                        "features": _draft_features(
                            draft, writing_card, writing_depth
                        ),
                        "review": review,
                        "form": form,
                        "findings": findings,
                        "decision": editorial.quality_decision(findings),
                    }

                return phase(f"observe_{label}", run_observation)

            styled_observation = observe("styled", styled)
            ablated_observation = observe("ablated", ablated)
            result["style_comparison"] = {
                "styled": styled_observation,
                "ablated": ablated_observation,
            }
            checkpoint()

            if styled and ablated:
                def judge_style(run_id: int) -> dict[str, Any]:
                    system = (
                        "You are a blind editorial-style evaluator. Use only the supplied "
                        "rubric and exact quotes. Return exactly one JSON object."
                    )
                    first = _parse_style_judgment(llm.call(
                        "review", system, _style_judge_prompt(styled, ablated),
                        conn=conn, run_id=run_id,
                    ))
                    second_raw = _parse_style_judgment(llm.call(
                        "review", system, _style_judge_prompt(ablated, styled),
                        conn=conn, run_id=run_id,
                    ))
                    # W drugim porządku B oznacza wersję ze stylem.
                    mapped_second = {
                        "raw": second_raw,
                        "winner_mapped": (
                            "STYLED" if second_raw["winner"] == "B" else
                            "ABLATED" if second_raw["winner"] == "A" else "TIE"
                        ),
                    }
                    return {
                        "order_styled_first": first,
                        "order_ablated_first": mapped_second,
                        "winner_first_mapped": (
                            "STYLED" if first["winner"] == "A" else
                            "ABLATED" if first["winner"] == "B" else "TIE"
                        ),
                    }

                result["style_blind_judges"] = phase("style_blind_judges", judge_style)
                checkpoint()

            # C. Kontrolowany błąd faktograficzny -> review -> revise -> review.
            if styled:
                def revision_challenge(run_id: int) -> dict[str, Any]:
                    injected = "The records prove that this system prevented exactly 12 accidents."
                    challenged = dict(styled)
                    challenged["body"] = styled["body"].rstrip() + "\n\n" + injected
                    before_review = stages.review(conn, run_id, writing_card, challenged)
                    _, before_lineage = provenance.finalize_card(
                        writing_card, writing_evidence, before_review, challenged["body"]
                    )
                    findings = list(before_lineage)
                    findings.extend({
                        "gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")
                    } for item in before_review.get("unsupported_facts", []))
                    if not findings:
                        findings.append({
                            "gate": "FAKT_BEZ_POKRYCIA",
                            "detail": injected,
                        })
                    revised = stages.revise(
                        conn, run_id, writing_card, challenged, findings
                    )
                    after_review = stages.review(conn, run_id, writing_card, revised)
                    after_form = stages.ocen_forme(conn, run_id, revised)
                    return {
                        "injected_sentence": injected,
                        "before": challenged,
                        "before_review": before_review,
                        "findings_sent_to_reviser": findings,
                        "revised": revised,
                        "after_review": after_review,
                        "after_form": after_form,
                        "injected_sentence_removed": injected.lower() not in revised["body"].lower(),
                        "unsupported_before": len(before_review.get("unsupported_facts", [])),
                        "unsupported_after": len(after_review.get("unsupported_facts", [])),
                    }

                result["revision_challenge"] = phase(
                    "controlled_revision_challenge", revision_challenge
                )
                checkpoint()

            # D. Ten sam zweryfikowalny fakt, pięć form Notes, zero publikacji.
            note_evidence = {
                "confirmed_claims": [{
                    "text": (
                        "Mains-powered clocks keep time by counting electricity-grid "
                        "cycles. In early 2018, a prolonged frequency deviation below "
                        "50 Hz in Continental Europe caused synchronous clocks to fall "
                        "about six minutes behind."
                    ),
                    "url": (
                        "https://www.entsoe.eu/news/2018/03/06/press-release-"
                        "continuing-frequency-deviation-in-the-continental-"
                        "european-power-system/"
                    ),
                    "publisher": "ENTSO-E",
                }],
                "citable_numbers": [
                    {"value": "50 Hz", "means": "nominal grid frequency"},
                    {"value": "six minutes", "means": "clock delay"},
                ],
            }

            def notes_trial(run_id: int) -> dict[str, Any]:
                outputs: list[dict[str, Any]] = []
                for form in NOTE_FORMS:
                    generated = stages.note(
                        conn, run_id, "CIEKAWOSTKA", note_evidence, note_form=form
                    )
                    candidates = generated.get("candidates") or []
                    chosen = next(
                        (candidate for candidate in candidates if candidate.get("safe_to_post")),
                        None,
                    )
                    representative = chosen or (candidates[0] if candidates else {})
                    text = str(representative.get("note") or "")
                    outputs.append({
                        "form": form,
                        "selected_safe": chosen is not None,
                        "text": text,
                        "words": representative.get("words_actual"),
                        "blocks": len([part for part in re.split(r"\n\s*\n", text) if part]),
                        "first_line": text.splitlines()[0] if text.splitlines() else "",
                        "last_line": text.splitlines()[-1] if text.splitlines() else "",
                        "all_candidates": candidates,
                    })
                return {"same_evidence": note_evidence, "outputs": outputs}

            result["notes_forms"] = phase("notes_five_forms", notes_trial)
            checkpoint()

            ensure_cost_known()
            failed_phases = [
                name for name, entry in result["phases"].items()
                if entry.get("status") == "FAIL"
            ]
            result["failed_phases"] = failed_phases
            result["status"] = (
                "COMPLETE_WITH_STAGE_FAILURES" if failed_phases else "COMPLETE"
            )
        except ExperimentStopped as exc:
            result["status"] = "STOPPED_FAIL_CLOSED"
            result["stop_reason"] = str(exc)
        except BaseException as exc:
            result["status"] = "FAILED_HARNESS"
            result["stop_reason"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            result["finished_at"] = db.now()
            result["routing_unchanged"] = dict(config.MODEL_FOR) == routing_before
            result["browser_imported"] = (not browser_before and "browser" in sys.modules)
            result["cost"] = _cost_summary(conn)
            result["call_ledger"] = _call_rows(conn)
            result["contract_checks"] = [dict(row) for row in conn.execute(
                "SELECT * FROM model_contract_checks ORDER BY id"
            )]
            result["provenance_checks"] = [dict(row) for row in conn.execute(
                "SELECT * FROM provenance_checks ORDER BY id"
            )]
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result["database_sha256_at_final_checkpoint"] = hashlib.sha256(
                paths.database.read_bytes()
            ).hexdigest()
            checkpoint()
            conn.close()
            conn = None

    if not result.get("routing_unchanged"):
        result["status"] = "FAILED_ROUTING_MUTATION"
    if result.get("browser_imported"):
        result["status"] = "FAILED_FORBIDDEN_BROWSER"
    if any(
        capability not in {item.value for item in ALLOWED_CAPABILITIES}
        for capability in requested_capabilities
    ):
        result["status"] = "FAILED_FORBIDDEN_CAPABILITY"
    if result["cost"]["new_exposure_usd"] > float(max_cost_usd) + 1e-9:
        result["status"] = "FAILED_BUDGET"

    _atomic_json(paths.result, result)
    if paths.partial.exists():
        paths.partial.unlink()
    return result


def exit_code(result: dict[str, Any]) -> int:
    if result.get("status") == "COMPLETE_WITH_STAGE_FAILURES":
        return 5
    if result.get("status") != "COMPLETE":
        return 2
    if result.get("browser_imported") or not result.get("routing_unchanged"):
        return 3
    if result.get("cost", {}).get("reserved_or_unknown_usd", 0):
        return 4
    return 0


__all__ = [
    "EXPECTED_ROUTING",
    "HISTORICAL_COST_USD",
    "LIVE_EXPERIMENT_MAX_USD",
    "MAX_CALLS_BY_MODEL",
    "MAX_LEDGERED_MODEL_CALLS",
    "NOTE_FORMS",
    "USER_GLOBAL_LIMIT_USD",
    "assess_scout",
    "exit_code",
    "run_experiment",
    "validate_preflight",
]
