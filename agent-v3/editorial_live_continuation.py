"""Provider-isolated continuation of the E-012 live editorial experiment.

T118 ended after the first DeepSeek dispatch with an incomplete response body
and an UNKNOWN $1.60 reservation.  This module does not retry that request.
Instead it runs two bounded arms in fresh ledgers:

* Anthropic: controlled writing, style ablation, revision and five Note forms;
* DeepSeek: a materially distinct scout replication, natural research and
  independent evaluation of the Anthropic outputs.

The unresolved T118 reservation is charged at its full value in every budget
calculation.  The exception allowing a *different* DeepSeek request after T118
is therefore explicit, user-authorized and bounded by the global $10 cap.
Neither arm imports a browser or permits any Substack access or mutation.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import ExitStack
from typing import Any, Callable
from unittest import mock

import capabilities
import config
import db
import editorial
import editorial_live_experiment as base
import gates
import llm
import provenance
import safe_fetch
import stages
import style


ARM_ANTHROPIC = "anthropic"
ARM_DEEPSEEK = "deepseek"
ARMS = (ARM_ANTHROPIC, ARM_DEEPSEEK)

HISTORICAL_COST_USD = base.HISTORICAL_COST_USD
T118_UNKNOWN_EXPOSURE_USD = 1.60
E014_LONG_SCOUT_UNKNOWN_EXPOSURE_USD = 1.60
E015_CONCISE_SCOUT_UNKNOWN_EXPOSURE_USD = 1.60
PRIOR_UNKNOWN_EXPOSURE_USD = (
    T118_UNKNOWN_EXPOSURE_USD
    + E014_LONG_SCOUT_UNKNOWN_EXPOSURE_USD
    + E015_CONCISE_SCOUT_UNKNOWN_EXPOSURE_USD
)
BASELINE_EXPOSURE_USD = HISTORICAL_COST_USD + PRIOR_UNKNOWN_EXPOSURE_USD
GLOBAL_LIMIT_USD = base.USER_GLOBAL_LIMIT_USD

ANTHROPIC_MAX_USD = 3.50
DEEPSEEK_MAX_USD = 1.60
PROGRAM_MAX_EXPOSURE_USD = (
    BASELINE_EXPOSURE_USD + ANTHROPIC_MAX_USD + DEEPSEEK_MAX_USD
)

MAX_CALLS_BY_ARM = {
    ARM_ANTHROPIC: {config.FABLE: 3, config.CLAUDE: 5},
    ARM_DEEPSEEK: {config.DEEPSEEK_PRO: 13, config.DEEPSEEK: 10},
}
MAX_CALLS = {arm: sum(models.values()) for arm, models in MAX_CALLS_BY_ARM.items()}
MAX_COST = {ARM_ANTHROPIC: ANTHROPIC_MAX_USD, ARM_DEEPSEEK: DEEPSEEK_MAX_USD}

ALLOWED_CAPABILITIES = frozenset({
    capabilities.Capability.MODEL_CALL,
    capabilities.Capability.PUBLIC_WEB_READ,
})

SCOUT_REPLICATION_ID = "E-015-DEEPSEEK-SCOUT-R3-CONCISE-PROMPT"
MAX_FETCH_SOURCES = 4
DEEPSEEK_LIVE_BLOCKED_AFTER_THREE_UNKNOWN = True


class ControlledStop(RuntimeError):
    """Fail-closed stop after unknown cost or a breached experiment contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False,
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
    ) as handle:
        temp = pathlib.Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True,
                  default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        # Windows może na moment zablokować świeżo zamknięty plik (indekser,
        # AV). Stała nazwa .tmp dodatkowo kolidowała z szybkim checkpointem.
        # Zachowujemy atomowe replace, ale dajemy krótkie, ograniczone okno na
        # zwolnienie uchwytu; po pięciu próbach błąd pozostaje fail-closed.
        for attempt in range(5):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01 * (2 ** attempt))
    finally:
        temp.unlink(missing_ok=True)


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_substack(url: str) -> bool:
    return base._is_substack(url)


def _provider_for_model(model: str) -> str:
    return "deepseek" if model.startswith("deepseek") else "anthropic"


def _paths(workspace: pathlib.Path) -> dict[str, pathlib.Path]:
    root = workspace.resolve()
    data = root / "data"
    return {
        "root": root,
        "data": data,
        "database": data / "experiment.db",
        "articles": data / "articles",
        "partial": root / "result.partial.json",
        "result": root / "result.json",
    }


def validate_preflight(
    workspace: pathlib.Path,
    *,
    arm: str,
    max_cost_usd: float,
    anthropic_artifact: pathlib.Path | None = None,
) -> None:
    """Validate all invariants before creating a workspace or dispatching."""
    if arm not in ARMS:
        raise RuntimeError(f"unknown continuation arm: {arm!r}")
    if arm == ARM_DEEPSEEK and DEEPSEEK_LIVE_BLOCKED_AFTER_THREE_UNKNOWN:
        raise RuntimeError(
            "DeepSeek live is blocked after three consecutive UNKNOWN scout "
            "reservations; reconcile provider billing/transport before any new call"
        )
    root = pathlib.Path(__file__).resolve().parent
    if not _inside(workspace, root) or workspace.resolve() == root:
        raise RuntimeError("workspace must be a new subdirectory of agent-v3")
    if workspace.exists():
        raise RuntimeError("workspace must not exist before dispatch")
    if capabilities.current_mode() is not capabilities.Mode.MODEL_TEST:
        raise RuntimeError("live continuation requires AGENT_V3_MODE=model_test")
    if capabilities.kill_switch_active():
        raise RuntimeError("live continuation requires AGENT_V3_KILL_SWITCH=0")
    if config.DRY_RUN:
        raise RuntimeError("live continuation requires AGENT_V3_DRY_RUN=false")
    if config.CHEAP_MODE:
        raise RuntimeError("live continuation forbids AGENT_V3_CHEAP")
    if not 0 < float(max_cost_usd) <= MAX_COST[arm]:
        raise RuntimeError(f"{arm} max cost must be in (0, {MAX_COST[arm]:.2f}]")
    if PROGRAM_MAX_EXPOSURE_USD > GLOBAL_LIMIT_USD:
        raise RuntimeError("the complete continuation plan exceeds the global $10 cap")
    if BASELINE_EXPOSURE_USD + float(max_cost_usd) > GLOBAL_LIMIT_USD:
        raise RuntimeError("this arm exceeds the global $10 cap after T118")

    actual = {purpose: config.MODEL_FOR.get(purpose) for purpose in base.EXPECTED_ROUTING}
    if actual != base.EXPECTED_ROUTING:
        raise RuntimeError("normal V3 routing has changed: " + json.dumps(actual))

    if arm == ARM_ANTHROPIC:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("missing AGENT_V3_ANTHROPIC_API_KEY")
        style.load_examples()
        style.load_profiles()
    else:
        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError("missing AGENT_V3_DEEPSEEK_API_KEY")
        if anthropic_artifact is None or not anthropic_artifact.is_file():
            raise RuntimeError("DeepSeek arm requires the completed Anthropic artifact")
        artifact = json.loads(anthropic_artifact.read_text(encoding="utf-8"))
        if artifact.get("experiment") != "editorial-live-continuation@1" or \
                artifact.get("arm") != ARM_ANTHROPIC:
            raise RuntimeError("the supplied input is not an Anthropic continuation artifact")
        prior_exposure = float((artifact.get("cost") or {}).get("new_exposure_usd", 0))
        if BASELINE_EXPOSURE_USD + prior_exposure + float(max_cost_usd) > GLOBAL_LIMIT_USD:
            raise RuntimeError("DeepSeek arm would exceed the global cap with prior exposure")


def _cost_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    summary = base._cost_summary(conn)
    summary["baseline_before_continuation_usd"] = BASELINE_EXPOSURE_USD
    summary["program_exposure_including_t118_usd"] = (
        BASELINE_EXPOSURE_USD + summary["new_exposure_usd"]
    )
    return summary


def _result_base(arm: str, max_cost_usd: float) -> dict[str, Any]:
    return {
        "experiment": "editorial-live-continuation@1",
        "arm": arm,
        "status": "RUNNING",
        "started_at": db.now(),
        "budget": {
            "historical_cost_usd": HISTORICAL_COST_USD,
            "t118_unknown_charged_usd": T118_UNKNOWN_EXPOSURE_USD,
            "e014_long_scout_unknown_charged_usd": (
                E014_LONG_SCOUT_UNKNOWN_EXPOSURE_USD
            ),
            "e015_concise_scout_unknown_charged_usd": (
                E015_CONCISE_SCOUT_UNKNOWN_EXPOSURE_USD
            ),
            "baseline_exposure_usd": BASELINE_EXPOSURE_USD,
            "arm_max_usd": float(max_cost_usd),
            "both_arms_program_max_usd": PROGRAM_MAX_EXPOSURE_USD,
            "global_limit_usd": GLOBAL_LIMIT_USD,
        },
        "dispatch_contract": {
            "max_calls": MAX_CALLS[arm],
            "max_calls_by_model": MAX_CALLS_BY_ARM[arm],
            "automatic_transport_retries": 0,
            "normal_routing_unchanged": True,
        },
        "t118_policy": {
            "same_prompt_retry": False,
            "unknown_cost_reconciled": False,
            "unknown_cost_treated_as_full_reservation": True,
            "new_deepseek_call_allowed_because": (
                "user explicitly required continued live testing; the next scout prompt "
                "is materially distinct and all prior reservations remain fully charged"
            ),
        },
        "substack": "FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION",
        "routing": base.EXPECTED_ROUTING,
        "calls_raw": [],
        "phases": {},
        "requested_capabilities": [],
    }


def run_arm(
    workspace: pathlib.Path,
    *,
    arm: str,
    max_cost_usd: float,
    anthropic_artifact: pathlib.Path | None = None,
) -> dict[str, Any]:
    validate_preflight(
        workspace, arm=arm, max_cost_usd=max_cost_usd,
        anthropic_artifact=anthropic_artifact,
    )
    paths = _paths(workspace)
    paths["data"].mkdir(parents=True, exist_ok=False)
    paths["articles"].mkdir(parents=True, exist_ok=True)

    result = _result_base(arm, max_cost_usd)
    routing_before = dict(config.MODEL_FOR)
    browser_before = "browser" in sys.modules
    conn: sqlite3.Connection | None = None

    def checkpoint() -> None:
        if conn is not None:
            result["cost"] = _cost_summary(conn)
            result["call_ledger"] = base._call_rows(conn)
        _atomic_json(paths["partial"], result)

    real_require = capabilities.require
    real_get = safe_fetch.get
    real_call = llm.call
    allowed_models = frozenset(MAX_CALLS_BY_ARM[arm])

    def controlled_require(capability: capabilities.Capability | str) -> None:
        requested = capabilities.Capability(capability)
        result["requested_capabilities"].append(requested.value)
        if requested not in ALLOWED_CAPABILITIES:
            raise capabilities.CapabilityDenied(
                f"continuation forbids capability {requested.value!r}"
            )
        real_require(requested)

    def controlled_get(url: str, **kwargs: Any) -> Any:
        normalized = safe_fetch.normalize_url(url)
        if _is_substack(normalized):
            raise safe_fetch.SafeFetchError("continuation blocks all Substack access")
        return real_get(normalized, **kwargs)

    def captured_call(purpose: str, system: str, user: str, **kwargs: Any) -> str:
        model = config.MODEL_FOR[purpose]
        if model not in allowed_models or _provider_for_model(model) != arm:
            raise ControlledStop(
                f"{arm} arm refused cross-provider purpose={purpose!r} model={model!r}"
            )
        if len(result["calls_raw"]) >= MAX_CALLS[arm]:
            raise ControlledStop(f"{arm} arm reached its dispatch ceiling")
        model_count = sum(item["model"] == model for item in result["calls_raw"])
        if model_count >= MAX_CALLS_BY_ARM[arm][model]:
            raise ControlledStop(f"{arm} arm reached the {model!r} ceiling")
        started = time.monotonic()
        item: dict[str, Any] = {
            "ordinal": len(result["calls_raw"]) + 1,
            "purpose": purpose,
            "model": model,
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
            response = real_call(purpose, system, user, **kwargs)
            item.update({
                "response": response,
                "response_sha256": _sha256_text(response),
                "error": None,
            })
            return response
        except BaseException as exc:
            item.update({
                "response": None,
                "response_sha256": None,
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise
        finally:
            item["finished_at"] = db.now()
            item["seconds"] = round(time.monotonic() - started, 3)
            checkpoint()

    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(config, "DATA_DIR", paths["data"]))
        stack.enter_context(mock.patch.object(config, "DB_PATH", paths["database"]))
        stack.enter_context(mock.patch.object(config, "ARTICLES_DIR", paths["articles"]))
        stack.enter_context(mock.patch.object(config, "DAILY_LIMIT_USD", float(max_cost_usd)))
        stack.enter_context(mock.patch.object(config, "PONOWIENIA", 0))
        stack.enter_context(mock.patch.object(stages, "ZUZYTE_FAKTY", paths["data"] / "zuzyte_fakty.json"))
        stack.enter_context(mock.patch.object(stages, "PROMOCJA", paths["data"] / "promocja.json"))
        stack.enter_context(mock.patch.object(stages, "BANK_NOTEK", paths["data"] / "bank_notek.json"))
        stack.enter_context(mock.patch.object(stages, "PYTANIA_CZYTELNIKOW", paths["data"] / "pytania.json"))
        stack.enter_context(mock.patch.object(stages, "INDEKS_KANDYDATOW", paths["data"] / "indeks.json"))
        stack.enter_context(mock.patch.object(capabilities, "require", side_effect=controlled_require))
        stack.enter_context(mock.patch.object(safe_fetch, "get", side_effect=controlled_get))
        stack.enter_context(mock.patch.object(llm, "call", side_effect=captured_call))

        conn = db.connect(paths["database"])

        def ensure_budget_resolved() -> None:
            unresolved = int(conn.execute(
                "SELECT COUNT(*) FROM calls WHERE cost_status IN ('RESERVED','UNKNOWN')"
            ).fetchone()[0])
            if unresolved:
                raise ControlledStop(
                    f"{unresolved} RESERVED/UNKNOWN cost rows; no further {arm} dispatch"
                )
            exposure = db.financial_exposure(conn)
            if exposure > float(max_cost_usd) + 1e-9:
                raise ControlledStop(
                    f"arm exposure ${exposure:.6f} exceeded ${max_cost_usd:.6f}"
                )

        def phase(name: str, function: Callable[[int], Any]) -> Any:
            run_id = db.start_run(conn, stage=name)
            started = time.monotonic()
            entry: dict[str, Any] = {
                "run_id": run_id,
                "started_at": db.now(),
                "status": "RUNNING",
            }
            result["phases"][name] = entry
            checkpoint()
            try:
                value = function(run_id)
                entry.update({"status": "PASS", "error": None, "value": value})
                db.finish_run(conn, run_id, "DONE", name, "")
                return value
            except ControlledStop:
                db.finish_run(conn, run_id, "FAILED", name, "controlled stop")
                entry["status"] = "STOP"
                raise
            except BaseException as exc:
                entry.update({
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                    "value": None,
                })
                db.finish_run(
                    conn, run_id, "FAILED", name,
                    f"{type(exc).__name__}: {exc}"[:500],
                )
                return None
            finally:
                entry["finished_at"] = db.now()
                entry["seconds"] = round(time.monotonic() - started, 3)
                checkpoint()
                ensure_budget_resolved()

        try:
            if arm == ARM_ANTHROPIC:
                _run_anthropic(result, phase, checkpoint)
            else:
                assert anthropic_artifact is not None
                _run_deepseek(result, phase, checkpoint, anthropic_artifact)
            failures = [
                name for name, item in result["phases"].items()
                if item.get("status") == "FAIL"
            ]
            result["failed_phases"] = failures
            result["status"] = "COMPLETE_WITH_STAGE_FAILURES" if failures else "COMPLETE"
        except ControlledStop as exc:
            result["status"] = "STOPPED_FAIL_CLOSED"
            result["stop_reason"] = str(exc)
        except BaseException as exc:
            result["status"] = "FAILED_HARNESS"
            result["stop_reason"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            result["finished_at"] = db.now()
            result["routing_unchanged"] = dict(config.MODEL_FOR) == routing_before
            result["browser_imported"] = not browser_before and "browser" in sys.modules
            result["cost"] = _cost_summary(conn)
            result["call_ledger"] = base._call_rows(conn)
            result["contract_checks"] = [dict(row) for row in conn.execute(
                "SELECT * FROM model_contract_checks ORDER BY id"
            )]
            result["provenance_checks"] = [dict(row) for row in conn.execute(
                "SELECT * FROM provenance_checks ORDER BY id"
            )]
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result["database_sha256_at_final_checkpoint"] = _sha256_file(paths["database"])
            checkpoint()
            conn.close()
            conn = None

    if not result.get("routing_unchanged"):
        result["status"] = "FAILED_ROUTING_MUTATION"
    if result.get("browser_imported"):
        result["status"] = "FAILED_FORBIDDEN_BROWSER"
    if any(value not in {item.value for item in ALLOWED_CAPABILITIES}
           for value in result["requested_capabilities"]):
        result["status"] = "FAILED_FORBIDDEN_CAPABILITY"
    if result["cost"]["new_exposure_usd"] > float(max_cost_usd) + 1e-9:
        result["status"] = "FAILED_BUDGET"

    _atomic_json(paths["result"], result)
    if paths["partial"].exists():
        paths["partial"].unlink()
    return result


def _run_anthropic(
    result: dict[str, Any],
    phase: Callable[[str, Callable[[int], Any]], Any],
    checkpoint: Callable[[], None],
) -> None:
    question, evidence, card = base._controlled_fixture()
    fixed_ending = config.losowy_ruch_koncowy()
    fixed_parallels = config.losowa_liczba_paraleli("RICH")
    result["controlled_input"] = {
        "fixture_is_fictional": True,
        "purpose": "hold evidence constant while testing writing behavior",
        "question": question,
        "evidence": evidence,
        "card": card,
        "depth": "RICH",
        "fixed_ending": fixed_ending,
        "fixed_parallels": fixed_parallels,
    }
    result["style_assets"] = {
        "corpus": str(config.STYLE_CORPUS),
        "canonical_sha256": style.corpus_sha256(),
        "expected_sha256": config.STYLE_CORPUS_SHA256,
        "examples": style.load_examples(),
        "profiles": style.load_profiles(),
    }
    checkpoint()

    def write_styled(run_id: int) -> dict[str, Any]:
        with mock.patch.object(config, "losowy_ruch_koncowy", return_value=fixed_ending), \
                mock.patch.object(config, "losowa_liczba_paraleli", return_value=fixed_parallels):
            return stages.write(conn=_phase_conn(phase), run_id=run_id, card=card,
                                glebokosc="RICH", editorial_memory={})

    styled = phase("anthropic_write_with_style", write_styled)
    result["styled_draft"] = styled
    if styled:
        result["styled_features"] = base._draft_features(styled, card, "RICH")
    checkpoint()

    def write_ablated(run_id: int) -> dict[str, Any]:
        with mock.patch.object(config, "losowy_ruch_koncowy", return_value=fixed_ending), \
                mock.patch.object(config, "losowa_liczba_paraleli", return_value=fixed_parallels), \
                mock.patch.object(style, "load_examples", return_value=[]), \
                mock.patch.object(
                    style, "load_profiles",
                    return_value=("No style profile supplied.", "No negative profile supplied."),
                ):
            return stages.write(conn=_phase_conn(phase), run_id=run_id, card=card,
                                glebokosc="RICH", editorial_memory={})

    ablated = phase("anthropic_write_without_style", write_ablated)
    result["ablated_draft"] = ablated
    if ablated:
        result["ablated_features"] = base._draft_features(ablated, card, "RICH")
    checkpoint()

    if styled:
        injected = "The records prove that this system prevented exactly 12 accidents."
        challenged = dict(styled)
        challenged["body"] = str(styled["body"]).rstrip() + "\n\n" + injected
        findings = [{"gate": "FAKT_BEZ_POKRYCIA", "detail": injected}]

        def revise(run_id: int) -> dict[str, Any]:
            return stages.revise(
                _phase_conn(phase), run_id, card, challenged, findings
            )

        revised = phase("anthropic_controlled_revision", revise)
        result["revision"] = {
            "injected_sentence": injected,
            "challenged": challenged,
            "findings": findings,
            "revised": revised,
            "injected_sentence_removed": bool(
                revised and injected.lower() not in str(revised.get("body", "")).lower()
            ),
        }
        checkpoint()

    note_evidence = {
        "confirmed_claims": [{
            "text": (
                "Mains-powered clocks keep time by counting electricity-grid cycles. "
                "In early 2018, a prolonged frequency deviation below 50 Hz in "
                "Continental Europe caused synchronous clocks to fall about six "
                "minutes behind."
            ),
            "url": (
                "https://www.entsoe.eu/news/2018/03/06/press-release-continuing-"
                "frequency-deviation-in-the-continental-european-power-system/"
            ),
            "publisher": "ENTSO-E",
        }],
        "citable_numbers": [
            {"value": "50 Hz", "means": "nominal grid frequency"},
            {"value": "six minutes", "means": "clock delay"},
        ],
    }
    result["notes_verification_policy"] = (
        "generation only in Anthropic arm; every candidate remains unsafe until the "
        "provider-isolated DeepSeek fact-check arm"
    )

    def deferred_verification(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "claims": [],
            "safe_to_post": False,
            "verification_available": False,
            "verdict": "DEFERRED_TO_DEEPSEEK_ARM_NO_CROSS_PROVIDER_CALL",
        }

    note_outputs: list[dict[str, Any]] = []
    with mock.patch.object(stages, "zweryfikuj", side_effect=deferred_verification):
        for form in base.NOTE_FORMS:
            generated = phase(
                f"anthropic_note_{form.lower()}",
                lambda run_id, form=form: stages.note(
                    _phase_conn(phase), run_id, "CIEKAWOSTKA", note_evidence,
                    note_form=form,
                ),
            )
            candidates = (generated or {}).get("candidates") or []
            representative = candidates[0] if candidates else {}
            text = str(representative.get("note") or "")
            note_outputs.append({
                "form": form,
                "text": text,
                "words": representative.get("words_actual"),
                "blocks": len([part for part in re.split(r"\n\s*\n", text) if part]),
                "first_line": text.splitlines()[0] if text.splitlines() else "",
                "last_line": text.splitlines()[-1] if text.splitlines() else "",
                "safe_to_post": False,
                "raw_generation": representative,
            })
    result["notes"] = {"same_evidence": note_evidence, "outputs": note_outputs}
    checkpoint()


def _phase_conn(phase: Callable[..., Any]) -> sqlite3.Connection:
    """Retrieve the live connection captured by the local ``phase`` closure.

    Keeping the connection in the closure prevents it from leaking into public
    function arguments or being serialized into the experiment artifact.
    """
    closure = getattr(phase, "__closure__", None) or ()
    for cell in closure:
        value = cell.cell_contents
        if isinstance(value, sqlite3.Connection):
            return value
    raise RuntimeError("experiment phase closure does not contain a database connection")


def _run_deepseek(
    result: dict[str, Any],
    phase: Callable[[str, Callable[[int], Any]], Any],
    checkpoint: Callable[[], None],
    anthropic_artifact: pathlib.Path,
) -> None:
    prior = json.loads(anthropic_artifact.read_text(encoding="utf-8"))
    result["anthropic_input"] = {
        "path": str(anthropic_artifact.resolve()),
        "sha256": _sha256_file(anthropic_artifact),
        "status": prior.get("status"),
        "cost": prior.get("cost"),
    }
    question, fixture_evidence, fixture_card = base._controlled_fixture()
    result["evaluation_input"] = {
        "fixture_question": question,
        "fixture_card_sha256": _sha256_text(json.dumps(
            fixture_card, ensure_ascii=False, sort_keys=True
        )),
        "anthropic_artifact_sha256": _sha256_file(anthropic_artifact),
    }
    checkpoint()

    replication_memory = {
        "live_experiment": {
            "replication_id": SCOUT_REPLICATION_ID,
            "purpose": "independent live replication after T118 transport failure",
            "difference_from_t118": (
                "non-empty frozen editorial memory and an explicit replication marker; "
                "this is not a retry of the prior request"
            ),
            "constraints_not_evidence": [
                "prefer a named governing record",
                "prefer a mechanism with at least one dated precedent",
            ],
        }
    }
    result["scout_replication"] = {
        "id": SCOUT_REPLICATION_ID,
        "materially_distinct_from_t118": True,
        "changed_input": replication_memory,
    }
    checkpoint()

    topics = phase(
        "deepseek_scout_distinct_replication",
        lambda run_id: stages.scout(
            _phase_conn(phase), run_id, count=config.TOPIC_COUNT,
            editorial_memory=replication_memory,
        ),
    )
    result["scout_assessment"] = base.assess_scout([topics] if topics else [])
    checkpoint()

    assessments = phase(
        "deepseek_feasibility",
        lambda run_id: stages.feasibility(_phase_conn(phase), run_id, topics),
    ) if topics else None
    selected_topic = selected_assessment = None
    if topics and assessments:
        selected_topic, selected_assessment = stages.pick_topic(topics, assessments)
        result["selected_topic"] = {
            "topic": selected_topic,
            "assessment": selected_assessment,
        }
        checkpoint()

    discovered = phase(
        "deepseek_discovery",
        lambda run_id: stages.discovery(
            _phase_conn(phase), run_id, selected_topic["question"], []
        ),
    ) if selected_topic else None
    non_substack = [
        source for source in (discovered or [])
        if not _is_substack(str(source.get("url") or ""))
    ]
    permitted = non_substack[:MAX_FETCH_SOURCES]
    result["source_filter"] = {
        "discovered": len(discovered or []),
        "substack_rejected": len(discovered or []) - len(non_substack),
        "selected_for_fetch": len(permitted),
        "urls": [source.get("url") for source in permitted],
    }
    checkpoint()

    corpus = phase(
        "deepseek_fetch_public_web",
        lambda run_id: stages.fetch(_phase_conn(phase), run_id, permitted),
    ) if permitted else None
    evidence = phase(
        "deepseek_classify_up_to_four",
        lambda run_id: stages.classify(
            _phase_conn(phase), run_id, selected_topic["question"], corpus
        ),
    ) if corpus and selected_topic else None
    card = phase(
        "deepseek_synthesis",
        lambda run_id: stages.synthesis(
            _phase_conn(phase), run_id, selected_topic["question"], evidence
        ),
    ) if evidence and selected_topic else None
    interest = phase(
        "deepseek_worth",
        lambda run_id: stages.warto_pisac(_phase_conn(phase), run_id, card),
    ) if card else None
    result["natural_chain"] = {
        "topics": topics,
        "assessments": assessments,
        "selected_topic": selected_topic,
        "selected_assessment": selected_assessment,
        "discovered_sources": discovered,
        "fetched_documents": corpus,
        "classified_evidence": evidence,
        "synthesis_card": card,
        "worth": interest,
    }
    checkpoint()

    styled = prior.get("styled_draft")
    ablated = prior.get("ablated_draft")
    revision = prior.get("revision") or {}

    def observe(label: str, draft: dict[str, Any] | None) -> dict[str, Any] | None:
        if not draft:
            return None
        review = phase(
            f"deepseek_review_{label}",
            lambda run_id: stages.review(
                _phase_conn(phase), run_id, fixture_card, draft
            ),
        )
        form = phase(
            f"deepseek_form_{label}",
            lambda run_id: stages.ocen_forme(_phase_conn(phase), run_id, draft),
        )
        lineage: list[dict[str, Any]] = []
        if review:
            _, lineage = provenance.finalize_card(
                fixture_card, fixture_evidence, review, draft["body"]
            )
        findings = gates.deterministic_floors(draft["body"], fixture_card, poprzednie=[])
        findings.extend(lineage)
        if form:
            findings.extend(gates.uwagi_z_formy(form, draft["body"]))
        if review:
            findings.extend({
                "gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")
            } for item in review.get("unsupported_facts", []))
        return {
            "features": base._draft_features(draft, fixture_card, "RICH"),
            "review": review,
            "form": form,
            "findings": findings,
            "decision": editorial.quality_decision(findings),
        }

    styled_observation = observe("styled", styled)
    ablated_observation = observe("ablated", ablated)
    result["style_observations"] = {
        "styled": styled_observation,
        "ablated": ablated_observation,
    }
    checkpoint()

    if styled and ablated:
        system = (
            "You are a blind editorial-style evaluator. Use only the supplied "
            "rubric and exact quotes. Return exactly one JSON object."
        )
        first = phase(
            "deepseek_style_judge_styled_first",
            lambda run_id: base._parse_style_judgment(llm.call(
                "review", system, base._style_judge_prompt(styled, ablated),
                conn=_phase_conn(phase), run_id=run_id,
            )),
        )
        second = phase(
            "deepseek_style_judge_ablated_first",
            lambda run_id: base._parse_style_judgment(llm.call(
                "review", system, base._style_judge_prompt(ablated, styled),
                conn=_phase_conn(phase), run_id=run_id,
            )),
        )
        result["blind_style_judges"] = {
            "styled_first": first,
            "ablated_first": second,
            "mapped_winners": [
                ("STYLED" if first and first.get("winner") == "A" else
                 "ABLATED" if first and first.get("winner") == "B" else "TIE"),
                ("STYLED" if second and second.get("winner") == "B" else
                 "ABLATED" if second and second.get("winner") == "A" else "TIE"),
            ],
        }
        checkpoint()

    challenged = revision.get("challenged")
    revised = revision.get("revised")
    if challenged and revised:
        before_review = phase(
            "deepseek_revision_review_before",
            lambda run_id: stages.review(
                _phase_conn(phase), run_id, fixture_card, challenged
            ),
        )
        after_review = phase(
            "deepseek_revision_review_after",
            lambda run_id: stages.review(
                _phase_conn(phase), run_id, fixture_card, revised
            ),
        )
        after_form = phase(
            "deepseek_revision_form_after",
            lambda run_id: stages.ocen_forme(_phase_conn(phase), run_id, revised),
        )
        result["revision_evaluation"] = {
            "before_review": before_review,
            "after_review": after_review,
            "after_form": after_form,
            "injected_sentence_removed": revision.get("injected_sentence_removed"),
            "unsupported_before": len((before_review or {}).get("unsupported_facts", [])),
            "unsupported_after": len((after_review or {}).get("unsupported_facts", [])),
        }
        checkpoint()

    factchecks: list[dict[str, Any]] = []
    for note in ((prior.get("notes") or {}).get("outputs") or []):
        form = str(note.get("form") or "UNKNOWN")
        text = str(note.get("text") or "")
        audit = phase(
            f"deepseek_factcheck_note_{form.lower()}",
            lambda run_id, text=text, form=form: stages.zweryfikuj(
                _phase_conn(phase), run_id, text,
                f"controlled live Note candidate, form {form}",
            ),
        ) if text else None
        factchecks.append({"form": form, "text": text, "audit": audit})
    result["note_factchecks"] = factchecks
    checkpoint()


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
    "ANTHROPIC_MAX_USD",
    "ARM_ANTHROPIC",
    "ARM_DEEPSEEK",
    "BASELINE_EXPOSURE_USD",
    "DEEPSEEK_MAX_USD",
    "MAX_CALLS",
    "MAX_CALLS_BY_ARM",
    "PROGRAM_MAX_EXPOSURE_USD",
    "SCOUT_REPLICATION_ID",
    "exit_code",
    "run_arm",
    "validate_preflight",
]
