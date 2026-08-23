"""Segmentowy live-test normalnego V3 bez dostępu do Substacka.

Uprząż nie zastępuje orkiestracji artykułu. Uruchamia prawdziwe ``run.main``
z bezpiecznym cache'em wyników poprzednich segmentów. Jedynymi adapterami są:

* izolowane ścieżki danych w katalogu eksperymentu;
* bezwarunkowa blokada Substacka na granicy publicznego fetchu;
* rejestr pełnych promptów i odpowiedzi modeli;
* limit liczby wywołań oraz kosztu konkretnego segmentu.

Późniejszy świeży przebieg może użyć tej samej funkcji bez zasianego cache'u.
Nie ma tu fixture'u treści, syntetycznej karty ani zmiany routingu modeli.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import re
import sqlite3
import sys
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from typing import Any
from unittest import mock
from urllib.parse import urlparse

import capabilities
import config
import db
import editorial
import llm
import model_contracts
import run
import safe_fetch
import stages


ROOT = pathlib.Path(__file__).resolve().parent
EXPERIMENT_VERSION = "normal-v3-live-segments@2"
SCOUT_LIVE_MAX_COST_USD = 0.04
ALLOWED_CAPABILITIES = frozenset({
    capabilities.Capability.MODEL_CALL,
    capabilities.Capability.PUBLIC_WEB_READ,
})
EXPECTED_ROUTING = {
    purpose: config.MODEL_FOR[purpose]
    for purpose in (
        "scout", "feasibility", "discovery", "classify", "synthesis",
        "warto_pisac", "write", "review", "forma", "revise",
        "curiosity", "note", "factcheck", "bibliotekarz",
    )
}

# Limity logicznych wywołań jednego uruchomienia run.main. Transport może
# ponowić wyłącznie błąd rozpoznany jako sprzed dispatch; testy segmentowe
# ustawiają retry=0. Świeży replay końcowy zachowuje normalne retry V3.
SEGMENT_CALL_LIMITS: dict[str, dict[str, int]] = {
    "feasibility": {"feasibility": 1},
    "discovery": {"discovery": 1},
    # Normalny run może wejść w drugą rundę discovery, jeśli fetch zwróci
    # mniej niż cztery dokumenty.
    "fetch": {"discovery": 1},
    "classify": {"discovery": 1, "classify": 20},
    "synthesis": {"discovery": 1, "classify": 20, "synthesis": 1},
    "warto_pisac": {
        "discovery": 1, "classify": 20, "synthesis": 1,
        "warto_pisac": 1,
    },
    "write": {
        "discovery": 1, "classify": 20, "synthesis": 1,
        "warto_pisac": 1, "bibliotekarz": 1, "write": 1,
    },
    "quality_save": {
        "discovery": 1, "classify": 20, "synthesis": 1,
        "warto_pisac": 1, "bibliotekarz": 1, "write": 1,
        "review": 3, "forma": 3, "revise": 2,
    },
    "full": {
        "scout": 1, "feasibility": 1, "discovery": 2, "classify": 20,
        "synthesis": 1, "warto_pisac": 1, "bibliotekarz": 1,
        "write": 1, "review": 3, "forma": 3, "revise": 2,
    },
}
NOTES_CALL_LIMITS = {"curiosity": 2, "note": 5, "factcheck": 5}


class LiveRunnerError(RuntimeError):
    """Błąd uprzęży lub naruszenie jej granic bezpieczeństwa."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _inside_root(path: pathlib.Path) -> bool:
    resolved = path.resolve()
    return resolved == ROOT or ROOT in resolved.parents


def _is_substack(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host == "substack.com" or host.endswith(".substack.com")


def _paths(workspace: pathlib.Path) -> dict[str, pathlib.Path]:
    workspace = workspace.resolve()
    data = workspace / "data"
    return {
        "workspace": workspace,
        "data": data,
        "database": data / "experiment.db",
        "articles": data / "articles",
        "cache": data / "cache",
        "captures": workspace / "model-captures.json",
        "manifest": workspace / "manifest.json",
    }


def validate_preflight(
    workspace: pathlib.Path, *, stage_cap_usd: float, require_existing: bool,
    require_anthropic: bool = True,
) -> None:
    if not _inside_root(workspace):
        raise LiveRunnerError("workspace musi być podkatalogiem agent-v3")
    if require_existing and not workspace.is_dir():
        raise LiveRunnerError("workspace segmentów nie istnieje")
    if not require_existing and workspace.exists():
        raise LiveRunnerError("nowy workspace nie może już istnieć")
    if capabilities.current_mode() is not capabilities.Mode.MODEL_TEST:
        raise LiveRunnerError("live runner wymaga AGENT_V3_MODE=model_test")
    if capabilities.kill_switch_active():
        raise LiveRunnerError("live runner wymaga AGENT_V3_KILL_SWITCH=0")
    if config.DRY_RUN:
        raise LiveRunnerError("live runner wymaga AGENT_V3_DRY_RUN=false")
    if config.CHEAP_MODE:
        raise LiveRunnerError("live runner zabrania AGENT_V3_CHEAP")
    if not 0 < float(stage_cap_usd) <= 3.50:
        raise LiveRunnerError("cap segmentu musi należeć do (0, 3.50] USD")
    actual = {purpose: config.MODEL_FOR[purpose] for purpose in EXPECTED_ROUTING}
    if actual != EXPECTED_ROUTING:
        raise LiveRunnerError("routing modeli różni się od normalnego V3")
    missing = []
    if not config.DEEPSEEK_API_KEY:
        missing.append("AGENT_V3_DEEPSEEK_API_KEY")
    if require_anthropic and not config.ANTHROPIC_API_KEY:
        missing.append("AGENT_V3_ANTHROPIC_API_KEY")
    if missing:
        raise LiveRunnerError("brak kluczy: " + ", ".join(missing))


def _path_patches(paths: dict[str, pathlib.Path]) -> tuple[Any, ...]:
    data = paths["data"]
    return (
        mock.patch.object(config, "DATA_DIR", data),
        mock.patch.object(config, "DB_PATH", paths["database"]),
        mock.patch.object(config, "ARTICLES_DIR", paths["articles"]),
        mock.patch.object(run, "CACHE_DIR", paths["cache"]),
        mock.patch.object(stages, "ZUZYTE_FAKTY", data / "zuzyte_fakty.json"),
        mock.patch.object(stages, "PROMOCJA", data / "promocja.json"),
        mock.patch.object(stages, "BANK_NOTEK", data / "bank_notek.json"),
        mock.patch.object(stages, "PYTANIA_CZYTELNIKOW", data / "pytania.json"),
        mock.patch.object(stages, "INDEKS_KANDYDATOW", data / "indeks.json"),
    )


def _load_captures(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise LiveRunnerError("model-captures.json nie jest listą")
    return value


def _cost(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT provider, cost_status, COUNT(*) AS n, "
        "COALESCE(SUM(cost_usd), 0) AS known, "
        "COALESCE(SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') "
        "THEN reserved_usd ELSE 0 END), 0) AS unresolved "
        "FROM calls GROUP BY provider, cost_status ORDER BY provider, cost_status"
    ).fetchall()
    known = float(conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM calls"
    ).fetchone()[0])
    unresolved = float(conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') "
        "THEN reserved_usd ELSE 0 END), 0) FROM calls"
    ).fetchone()[0])
    return {
        "known_usd": known,
        "reserved_or_unknown_usd": unresolved,
        "exposure_usd": known + unresolved,
        "rows": [dict(row) for row in rows],
    }


def _deepseek_worst_case_usd(
    purpose: str, system: str, user: str, *, web_search: bool = False,
) -> float:
    """Konserwatywna cena przed dispatch: bajt wejścia <= jeden token.

    To celowo zawyża angielski prompt, ale twardy cap nie może zależeć od
    nadziei, że tokenizer albo model zużyje mniej niż dopuszczony sufit.
    """
    model = config.MODEL_FOR[purpose]
    if not model.startswith("deepseek"):
        raise LiveRunnerError("wycena predispatch obsługuje wyłącznie DeepSeek")
    price = config.stawka_deepseek(model)
    first_input_upper = len((system + user).encode("utf-8"))
    one_output_upper = int(config.MAX_TOKENS[purpose])
    input_upper = first_input_upper
    output_upper = one_output_upper
    if web_search:
        # Po wyszukiwaniu zawsze działa beznarzędziowy exact-URL selector.
        # Konserwatywnie liczymy dwa pełne wyjścia oraz drugi input jako
        # powtórzony prompt + maksymalne pierwsze wyjście + twardo ograniczoną
        # listę adresów. To dwa requesty, ale jedno rozliczone logiczne zadanie.
        input_upper += first_input_upper + one_output_upper
        input_upper += int(config.DISCOVERY_SELECTOR_MAX_URL_CHARS_TOTAL)
        output_upper += one_output_upper
    return (
        input_upper * float(price["in"])
        + output_upper * float(price["out"])
    ) / 1_000_000


def _cache_values(cache_dir: pathlib.Path) -> dict[str, list[pathlib.Path]]:
    result: dict[str, list[pathlib.Path]] = {}
    if not cache_dir.is_dir():
        return result
    for stage_dir in sorted(path for path in cache_dir.iterdir() if path.is_dir()):
        result[stage_dir.name] = sorted(stage_dir.glob("*.json"))
    return result


def seed_scout(
    workspace: pathlib.Path, scout_artifact: pathlib.Path,
) -> dict[str, Any]:
    """Zasiewa cache Scouta z zaliczonego wyniku albo dokładnego raw capture.

    Raw capture jest ponownie przepuszczany przez BIEZACY kontrakt i bramke
    Scouta. Dzięki temu dalszy segment nie dziedziczy historycznego werdyktu
    harnessu ani nie wymaga ręcznego przepisywania tematów.
    """
    validate_preflight(workspace, stage_cap_usd=0.000001, require_existing=False)
    artifact = json.loads(scout_artifact.read_text(encoding="utf-8"))
    source_kind = "phase_result"
    if isinstance(artifact, list):
        captures = [
            item for item in artifact
            if isinstance(item, dict) and item.get("purpose") == "scout"
            and isinstance(item.get("response"), str) and item["response"].strip()
        ]
        if not captures:
            raise LiveRunnerError("capture nie zawiera kompletnej odpowiedzi Scouta")
        data = model_contracts.validate(
            "scout", llm.parse_json(captures[-1]["response"])
        )
        raw_topics = data.get("topics")
        if not isinstance(raw_topics, list):
            raise LiveRunnerError("capture Scouta nie zawiera listy tematów")
        topics = stages._scout_universe_quality(
            data, raw_topics, config.TOPIC_COUNT,
        )
        source_kind = "exact_raw_capture_replay"
    else:
        try:
            phase = artifact["phases"]["scout_replication_1"]
            topics = phase["value"]
        except (KeyError, TypeError) as exc:
            raise LiveRunnerError("artefakt nie zawiera zaliczonego Scouta") from exc
        if phase.get("status") != "PASS":
            raise LiveRunnerError("Scout źródłowy nie ma statusu PASS")
    if not isinstance(topics, list) or len(topics) != config.TOPIC_COUNT:
        raise LiveRunnerError("Scout źródłowy nie zawiera dokładnie sześciu tematów")
    article_universes = [
        item for item in topics
        if item.get("na_artykul") and item.get("nosny")
        and item.get("pole_redakcyjne")
    ]
    if len(article_universes) != len(topics):
        raise LiveRunnerError(
            "artefakt Scouta nie spełnia bramki jakości portfela: "
            f"pełne pola redakcyjne={len(article_universes)}/{len(topics)}"
        )

    paths = _paths(workspace)
    paths["articles"].mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for patch in _path_patches(paths):
            stack.enter_context(patch)
        conn = db.connect(paths["database"])
        try:
            memory = editorial.memory_brief(conn)
        finally:
            conn.close()
        cached_topics = run.cached(
            "scout", lambda: topics, False,
            {"count": config.TOPIC_COUNT, "editorial_memory": memory},
        )

    manifest = {
        "experiment": EXPERIMENT_VERSION,
        "created_at": db.now(),
        "routing": EXPECTED_ROUTING,
        "substack": "FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION",
        "scout_artifact": str(scout_artifact.resolve()),
        "scout_artifact_sha256": _sha256(scout_artifact.read_bytes()),
        "scout_source_kind": source_kind,
        "topic_count": len(cached_topics),
        "topic_titles": [item.get("title") for item in cached_topics],
        "segments": [],
    }
    _atomic_json(paths["manifest"], manifest)
    return manifest


def _run_with_guards(
    workspace: pathlib.Path, *, label: str, stage_cap_usd: float,
    allowed_calls: dict[str, int], argv: list[str] | None,
    notes: bool, zero_retry: bool, scout_only: bool = False,
) -> dict[str, Any]:
    paths = _paths(workspace)
    validate_preflight(
        workspace, stage_cap_usd=stage_cap_usd, require_existing=True,
        require_anthropic=not scout_only,
    )
    paths["articles"].mkdir(parents=True, exist_ok=True)
    routing_before = dict(config.MODEL_FOR)
    browser_before = "browser" in sys.modules
    captures = _load_captures(paths["captures"])
    capture_start = len(captures)
    requested_capabilities: list[str] = []
    fetched_urls: list[str] = []
    call_counts: dict[str, int] = {}
    real_require = capabilities.require
    real_get = safe_fetch.get
    real_call = llm.call

    conn_before = db.connect(paths["database"])
    try:
        cost_before = _cost(conn_before)
        last_call_id = int(conn_before.execute(
            "SELECT COALESCE(MAX(id), 0) FROM calls"
        ).fetchone()[0])
    finally:
        conn_before.close()

    def guarded_require(capability: capabilities.Capability | str) -> None:
        requested = capabilities.Capability(capability)
        requested_capabilities.append(requested.value)
        if requested not in ALLOWED_CAPABILITIES:
            raise capabilities.CapabilityDenied(
                f"normal live runner zabrania {requested.value!r}"
            )
        real_require(requested)

    def guarded_get(url: str, **kwargs: Any) -> Any:
        normalized = safe_fetch.normalize_url(url)
        if _is_substack(normalized):
            raise safe_fetch.SafeFetchError("Substack zablokowany przez live runner")
        if len(fetched_urls) >= 20:
            raise safe_fetch.SafeFetchError("przekroczono 20 publicznych fetchy segmentu")
        fetched_urls.append(normalized)
        return real_get(normalized, **kwargs)

    def captured_call(
        purpose: str, system: str, user: str, **kwargs: Any,
    ) -> str:
        limit = int(allowed_calls.get(purpose, 0))
        call_counts[purpose] = call_counts.get(purpose, 0) + 1
        if call_counts[purpose] > limit:
            raise LiveRunnerError(
                f"segment {label!r} odmówił nadmiarowego wywołania {purpose!r}"
            )
        item: dict[str, Any] = {
            "ordinal": len(captures) + 1,
            "segment": label,
            "purpose": purpose,
            "model": config.MODEL_FOR[purpose],
            "system": system,
            "system_sha256": _sha256(system.encode("utf-8")),
            "user": user,
            "user_sha256": _sha256(user.encode("utf-8")),
            "web_search": bool(kwargs.get("web_search")),
            "started_at": db.now(),
        }
        if config.MODEL_FOR[purpose].startswith("deepseek"):
            item["worst_case_usd_before_dispatch"] = _deepseek_worst_case_usd(
                purpose, system, user,
                web_search=bool(kwargs.get("web_search")),
            )
        captures.append(item)
        _atomic_json(paths["captures"], captures)
        started = time.monotonic()
        try:
            if (item.get("worst_case_usd_before_dispatch") is not None
                    and item["worst_case_usd_before_dispatch"]
                    > float(stage_cap_usd) + 1e-12):
                raise LiveRunnerError(
                    "odmowa przed dispatch: sufit etapu może kosztować "
                    f"${item['worst_case_usd_before_dispatch']:.6f}, "
                    f"cap wynosi ${float(stage_cap_usd):.6f}"
                )
            response = real_call(purpose, system, user, **kwargs)
            item["response"] = response
            item["response_sha256"] = _sha256(response.encode("utf-8"))
            item["error"] = None
            return response
        except BaseException as exc:
            item["response"] = None
            item["response_sha256"] = None
            item["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            collected_urls = kwargs.get("collect_urls")
            if isinstance(collected_urls, list):
                # Sam finalny JSON nie wystarcza do odtworzenia exact-URL gate.
                # Utrwalamy pełną, uporządkowaną listę wyników zwróconych przez
                # narzędzie, również gdy późniejsza bramka etapu odrzuci JSON.
                item["search_result_urls"] = list(dict.fromkeys(
                    url for url in collected_urls if isinstance(url, str)
                ))
                item["search_result_url_count"] = len(
                    item["search_result_urls"]
                )
            else:
                item["search_result_urls"] = []
                item["search_result_url_count"] = 0
            raw_trace = kwargs.get("collect_trace")
            trace_items: list[dict[str, Any]] = []
            if isinstance(raw_trace, list):
                for raw_entry in raw_trace:
                    if not isinstance(raw_entry, dict):
                        continue
                    entry = dict(raw_entry)
                    for field in ("system", "user", "response"):
                        value = entry.get(field)
                        if isinstance(value, str):
                            entry[f"{field}_sha256"] = _sha256(
                                value.encode("utf-8")
                            )
                    trace_items.append(entry)
            item["provider_trace"] = trace_items
            item["provider_request_count"] = len(trace_items)
            item["seconds"] = round(time.monotonic() - started, 3)
            item["finished_at"] = db.now()
            _atomic_json(paths["captures"], captures)

    stdout = io.StringIO()
    stderr = io.StringIO()
    outcome: Any = None
    exit_code = 0
    execution_error: str | None = None
    with ExitStack() as stack:
        for patch in _path_patches(paths):
            stack.enter_context(patch)
        cumulative_limit = float(cost_before["exposure_usd"]) + float(stage_cap_usd)
        stack.enter_context(mock.patch.object(config, "RUN_LIMIT_USD", float(stage_cap_usd)))
        stack.enter_context(mock.patch.object(config, "DAILY_LIMIT_USD", cumulative_limit))
        stack.enter_context(mock.patch.object(config, "MONTHLY_LIMIT_USD", cumulative_limit))
        if zero_retry:
            stack.enter_context(mock.patch.object(config, "PONOWIENIA", 0))
        stack.enter_context(mock.patch.object(capabilities, "require", side_effect=guarded_require))
        stack.enter_context(mock.patch.object(safe_fetch, "get", side_effect=guarded_get))
        stack.enter_context(mock.patch.object(llm, "call", side_effect=captured_call))
        stack.enter_context(redirect_stdout(stdout))
        stack.enter_context(redirect_stderr(stderr))
        if scout_only:
            conn = db.connect(paths["database"])
            run_id = db.start_run(conn, stage="scout_live_only")
            try:
                outcome = stages.scout(
                    conn, run_id, count=config.TOPIC_COUNT, editorial_memory={}
                )
                db.finish_run(conn, run_id, "DONE", "scout_live_only", "")
            except BaseException as exc:
                execution_error = f"{type(exc).__name__}: {exc}"
                exit_code = 1
                db.finish_run(
                    conn, run_id, "FAILED", "scout_live_only",
                    execution_error[:500],
                )
            finally:
                conn.close()
        elif notes:
            conn = db.connect(paths["database"])
            run_id = db.start_run(conn, stage="notes_local_live")
            try:
                outcome = stages.notki_dnia(conn, run_id, ile=5)
                db.finish_run(conn, run_id, "DONE", "notes_local_live", "")
            except BaseException as exc:
                db.finish_run(
                    conn, run_id, "FAILED", "notes_local_live",
                    f"{type(exc).__name__}: {exc}"[:500],
                )
                raise
            finally:
                conn.close()
        else:
            with mock.patch.object(sys, "argv", argv or ["run.py"]):
                exit_code = int(run.main())

    conn_after = db.connect(paths["database"])
    try:
        cost_after = _cost(conn_after)
        new_call_rows = [dict(row) for row in conn_after.execute(
            "SELECT * FROM calls WHERE id>? ORDER BY id", (last_call_id,)
        ).fetchall()]
        contract_failures = int(conn_after.execute(
            "SELECT COUNT(*) FROM model_contract_checks WHERE ok=0"
        ).fetchone()[0])
        latest_run = conn_after.execute(
            "SELECT status, stage, note FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest_article = conn_after.execute(
            "SELECT id, title, status, file_path FROM articles ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn_after.close()

    delta = float(cost_after["exposure_usd"]) - float(cost_before["exposure_usd"])
    notes_validation: dict[str, Any] | None = None
    if notes:
        facts = [str(item.get("fakt") or "").strip() for item in (outcome or [])]
        selected = []
        for item in outcome or []:
            candidates = item.get("candidates") or []
            selected.append(next(
                (candidate for candidate in candidates if candidate.get("safe_to_post")),
                None,
            ))
        normalized = {
            re.sub(r"\W+", " ", fact.lower()).strip() for fact in facts if fact
        }
        notes_validation = {
            "requested": 5,
            "returned": len(outcome or []),
            "different_materials": len(normalized),
            "safe_candidates": sum(item is not None for item in selected),
            "pass": (
                len(outcome or []) == 5
                and len(normalized) == 5
                and all(item is not None for item in selected)
            ),
        }

    result = {
        "experiment": EXPERIMENT_VERSION,
        "segment": label,
        "finished_at": db.now(),
        "argv": argv,
        "zero_retry": zero_retry,
        "allowed_logical_calls": allowed_calls,
        "actual_logical_calls": call_counts,
        "stage_cap_usd": float(stage_cap_usd),
        "cost_before": cost_before,
        "cost_after": cost_after,
        "new_exposure_usd": delta,
        "new_call_rows": new_call_rows,
        "capture_ordinals": list(range(capture_start + 1, len(captures) + 1)),
        "provider_request_count": sum(
            int(item.get("provider_request_count", 0) or 0)
            for item in captures[capture_start:]
        ),
        "requested_capabilities": requested_capabilities,
        "public_fetches": fetched_urls,
        "substack_requested": any(_is_substack(url) for url in fetched_urls),
        "browser_imported": not browser_before and "browser" in sys.modules,
        "routing_unchanged": dict(config.MODEL_FOR) == routing_before,
        "contract_failures_total": contract_failures,
        "exit_code": exit_code,
        "latest_run": dict(latest_run) if latest_run else None,
        "latest_article": dict(latest_article) if latest_article else None,
        "notes": outcome if notes else None,
        "topics": outcome if scout_only else None,
        "notes_validation": notes_validation,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "execution_error": execution_error,
    }
    result["pass"] = bool(
        exit_code == 0
        and cost_after["reserved_or_unknown_usd"] == 0
        and delta <= float(stage_cap_usd) + 1e-9
        and not result["substack_requested"]
        and not result["browser_imported"]
        and result["routing_unchanged"]
        and (notes_validation is None or notes_validation["pass"])
    )
    result_path = paths["workspace"] / f"segment-{label}-result.json"
    _atomic_json(result_path, result)

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest.setdefault("segments", []).append({
        "label": label,
        "result": result_path.name,
        "result_sha256": _sha256(result_path.read_bytes()),
        "pass": result["pass"],
        "new_exposure_usd": delta,
        "actual_logical_calls": call_counts,
    })
    _atomic_json(paths["manifest"], manifest)
    return result


def run_article_segment(
    workspace: pathlib.Path, segment: str, *, stage_cap_usd: float,
    zero_retry: bool = True,
) -> dict[str, Any]:
    if segment not in SEGMENT_CALL_LIMITS:
        raise LiveRunnerError(f"nieznany segment: {segment}")
    if segment == "full":
        argv = ["run.py", "--topics", str(config.TOPIC_COUNT)]
    elif segment == "quality_save":
        argv = ["run.py", "--topics", str(config.TOPIC_COUNT), "--use-cache"]
    else:
        argv = [
            "run.py", "--topics", str(config.TOPIC_COUNT), "--use-cache",
            "--stop-after", segment,
        ]
    return _run_with_guards(
        workspace, label=segment, stage_cap_usd=stage_cap_usd,
        allowed_calls=SEGMENT_CALL_LIMITS[segment], argv=argv,
        notes=False, zero_retry=zero_retry,
    )


def run_notes(
    workspace: pathlib.Path, *, stage_cap_usd: float, zero_retry: bool = True,
) -> dict[str, Any]:
    return _run_with_guards(
        workspace, label="notes", stage_cap_usd=stage_cap_usd,
        allowed_calls=NOTES_CALL_LIMITS, argv=None, notes=True,
        zero_retry=zero_retry,
    )


def run_scout_live(
    workspace: pathlib.Path, *, stage_cap_usd: float,
) -> dict[str, Any]:
    """Jeden naturalny Scout, bez dalszych etapów i bez automatycznego retry."""
    if float(stage_cap_usd) > SCOUT_LIVE_MAX_COST_USD:
        raise LiveRunnerError(
            f"Scout live ma twardy cap ${SCOUT_LIVE_MAX_COST_USD:.2f}"
        )
    create_fresh_workspace(workspace, require_anthropic=False)
    result = _run_with_guards(
        workspace, label="scout-live-only", stage_cap_usd=stage_cap_usd,
        allowed_calls={"scout": 1}, argv=None, notes=False,
        zero_retry=True, scout_only=True,
    )
    result["pass"] = bool(
        result["pass"]
        and result["actual_logical_calls"] == {"scout": 1}
        and isinstance(result.get("topics"), list)
        and len(result["topics"]) == config.TOPIC_COUNT
        and all(item.get("pole_redakcyjne") for item in result["topics"])
    )
    result_path = workspace.resolve() / "segment-scout-live-only-result.json"
    _atomic_json(result_path, result)
    manifest_path = workspace.resolve() / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("segments"):
        manifest["segments"][-1].update({
            "pass": result["pass"],
            "result_sha256": _sha256(result_path.read_bytes()),
        })
        _atomic_json(manifest_path, manifest)
    return result


def create_fresh_workspace(
    workspace: pathlib.Path, *, require_anthropic: bool = True,
) -> dict[str, Any]:
    """Tworzy pustą izolację dla końcowego przebiegu bez cache'u."""
    validate_preflight(
        workspace, stage_cap_usd=0.000001, require_existing=False,
        require_anthropic=require_anthropic,
    )
    paths = _paths(workspace)
    paths["articles"].mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for patch in _path_patches(paths):
            stack.enter_context(patch)
        conn = db.connect(paths["database"])
        conn.close()
    manifest = {
        "experiment": EXPERIMENT_VERSION,
        "created_at": db.now(),
        "routing": EXPECTED_ROUTING,
        "substack": "FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION",
        "fresh_without_seed_or_cache": True,
        "segments": [],
    }
    _atomic_json(paths["manifest"], manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-scout")
    seed.add_argument("--workspace", type=pathlib.Path, required=True)
    seed.add_argument("--artifact", type=pathlib.Path, required=True)
    fresh = sub.add_parser("create-fresh")
    fresh.add_argument("--workspace", type=pathlib.Path, required=True)
    segment = sub.add_parser("segment")
    segment.add_argument("--workspace", type=pathlib.Path, required=True)
    segment.add_argument("--name", choices=tuple(SEGMENT_CALL_LIMITS), required=True)
    segment.add_argument("--max-cost-usd", type=float, required=True)
    segment.add_argument("--normal-retry", action="store_true")
    notes = sub.add_parser("notes")
    notes.add_argument("--workspace", type=pathlib.Path, required=True)
    notes.add_argument("--max-cost-usd", type=float, required=True)
    notes.add_argument("--normal-retry", action="store_true")
    scout_live = sub.add_parser("scout-live")
    scout_live.add_argument("--workspace", type=pathlib.Path, required=True)
    scout_live.add_argument("--max-cost-usd", type=float, required=True)
    args = parser.parse_args()

    if args.command == "seed-scout":
        result = seed_scout(args.workspace, args.artifact)
    elif args.command == "create-fresh":
        result = create_fresh_workspace(args.workspace)
    elif args.command == "segment":
        result = run_article_segment(
            args.workspace, args.name, stage_cap_usd=args.max_cost_usd,
            zero_retry=not args.normal_retry,
        )
    elif args.command == "notes":
        result = run_notes(
            args.workspace, stage_cap_usd=args.max_cost_usd,
            zero_retry=not args.normal_retry,
        )
    else:
        result = run_scout_live(
            args.workspace, stage_cap_usd=args.max_cost_usd,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
