"""Kontrolowany live-test N-009 na syntetycznym, zamrożonym korpusie.

Uruchamiany wyłącznie na modelach z aktualnego `config.MODEL_FOR`. Nie czyta Substacka, nie
otwiera przeglądarki, nie wyszukuje sieci i nie wykonuje żadnej mutacji poza
płatnym wywołaniem modelu. Baza telemetrii powstaje w katalogu tymczasowym.

Historyczny E-007 miał także ramię Sonnet, które nadpisywało routing w pamięci
procesu. Ta możliwość została usunięta: budżet dostawcy nie jest zgodą na zmianę
modelu. Inny routing wymaga osobnej, jawnej zmiany poza tym harnesssem.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402
import provenance  # noqa: E402
import stages  # noqa: E402


QUESTION = (
    "What did the Harbor Lighting Ordinance require and what did its pilot "
    "establish?"
)

SOURCE_TEXT = (
    "The Harbor Lighting Ordinance took effect on January 1, 2025. "
    "Section 4 requires municipal walkways to use fixtures rated at no more "
    "than 20 watts. "
    "The rule applies only to fixtures installed after the effective date. "
    "A city pilot covered 240 fixtures across six parks. "
    "The audit recorded an 18% reduction in electricity use during its first "
    "6 months. "
    "The audit did not measure pedestrian safety or maintenance costs. "
    "Existing fixtures may remain until replacement. "
    "The city council adopted the rule after a public hearing."
)

EXCERPTS = [
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
    "The city council adopted the rule after a public hearing.",
]


def _source() -> dict[str, Any]:
    return {
        "url": "https://fixture.invalid/harbor-lighting-ordinance",
        "title": "Harbor Lighting Ordinance and pilot audit",
        "publisher": "Fixture City Records",
        "host": "fixture.invalid",
        "text": SOURCE_TEXT,
    }


def _evidence() -> list[dict[str, Any]]:
    item = provenance.fragments_from_excerpts(_source(), EXCERPTS)
    item.update({"class": "PRIMARY", "relevance": 1.0, "note": "fixture"})
    return [item]


def _review_card(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    fragments = evidence[0]["fragments"]
    number_by_value = {
        number["value"]: number for number in evidence[0]["numbers"]
    }
    raw = {
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
            {"claim": "The audit did not measure pedestrian safety or maintenance costs.",
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
    return provenance.bind_card(raw, evidence)


REVIEW_BODY = (
    "The ordinance limits new municipal walkway fixtures to 20 watts. "
    "Because the pilot covered 240 fixtures, my reading is that the city "
    "favored breadth over depth. "
    "Because the pilot prevented 12 accidents, my reading is that safety "
    "drove the rule. "
    "My reading is that replacement cycles were used as political cushioning."
)

ANALOGY_REVIEW_BODY = (
    "Vehicle emissions rules usually spare older cars, so my reading is that "
    "the same turnover mechanism is at work."
)


def _semantic_review(report: dict[str, Any]) -> dict[str, Any]:
    expected = [
        ("FACT", "SUPPORTED"),
        ("MIXED", "SUPPORTED"),
        ("MIXED", "UNSUPPORTED"),
        ("INFERENCE", "NOT_APPLICABLE"),
    ]
    actual = [
        (row["class"], row["support"])
        for row in report.get("sentences", [])
    ]
    unsupported = report.get("unsupported_facts", [])
    return {
        "expected": expected,
        "actual": actual,
        "pass": actual == expected and len(unsupported) == 1
        and "12 accidents" in unsupported[0].get("text", ""),
    }


def _semantic_analogy_review(report: dict[str, Any]) -> dict[str, Any]:
    rows = report.get("sentences", [])
    actual = [
        (row["class"], row["support"])
        for row in rows
    ]
    unsupported = report.get("unsupported_facts", [])
    expected = [("MIXED", "UNSUPPORTED")]
    return {
        "expected": expected,
        "actual": actual,
        "pass": actual == expected and len(unsupported) == 1
        and "Vehicle emissions" in unsupported[0].get("text", ""),
    }


def _run_stage(name: str, function: Any) -> dict[str, Any]:
    before = len(CAPTURED)
    try:
        value = function()
        error = None
    except Exception as exc:  # wynik badania, nie ukrycie błędu
        value = None
        error = f"{type(exc).__name__}: {exc}"
    raw = CAPTURED[before:]
    return {"stage": name, "error": error, "value": value, "raw": raw}


def _assess_classify(result: dict[str, Any]) -> dict[str, Any]:
    values = result.get("value") or []
    exact = bool(values) and all(
        fragment["text"] in SOURCE_TEXT
        for fragment in values[0].get("fragments", [])
    )
    joined = " ".join(
        fragment["text"] for item in values for fragment in item.get("fragments", [])
    )
    return {
        "transport_and_contract": result.get("error") is None,
        "kept_documents": len(values),
        "all_fragments_exact": exact,
        "core_facts_present": all(token in joined for token in ("20 watts", "240", "18%")),
        "pass": result.get("error") is None and len(values) == 1 and exact
        and all(token in joined for token in ("20 watts", "240", "18%")),
    }


def _assess_synthesis(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("value") or {}
    return {
        "transport_and_contract": result.get("error") is None,
        "confirmed_claims": len(value.get("confirmed_claims", [])),
        "citable_numbers": len(value.get("citable_numbers", [])),
        "provenance_version": value.get("provenance_version"),
        "pass": result.get("error") is None
        and len(value.get("confirmed_claims", [])) >= 5
        and len(value.get("citable_numbers", [])) >= 3
        and value.get("provenance_version") == 1,
    }


CAPTURED: list[dict[str, Any]] = []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "routing", choices=("configured",),
        help="używa dokładnie domyślnego routingu normalnego V3",
    )
    parser.add_argument(
        "--stage", choices=("all", "review-analogy"), default="all",
        help="Jawnie ogranicza płatny przebieg do jednego kontrprzykładu.",
    )
    args = parser.parse_args()

    models = {
        name: config.MODEL_FOR[name]
        for name in ("classify", "synthesis", "review")
    }
    normal_v3 = {
        "classify": config.DEEPSEEK,
        "synthesis": config.DEEPSEEK_PRO,
        "review": config.DEEPSEEK_PRO,
    }
    if models != normal_v3:
        raise SystemExit(
            "configured routing differs from normal V3; model override is forbidden"
        )
    if config.DRY_RUN:
        raise SystemExit("AGENT_V3_DRY_RUN must be false")

    config.MAX_TOKENS.update({"classify": 3000, "synthesis": 6000, "review": 6000})
    config.EFFORT.update({"classify": "low", "synthesis": "low", "review": "low"})
    config.PONOWIENIA = 0

    real_call = llm.call

    def capturing_call(purpose: str, system: str, user: str, **kwargs: Any) -> str:
        text = real_call(purpose, system, user, **kwargs)
        CAPTURED.append({
            "purpose": purpose,
            "model": config.MODEL_FOR[purpose],
            "response": text,
        })
        return text

    stages.llm.call = capturing_call

    evidence = _evidence()
    review_card = _review_card(evidence)
    with tempfile.TemporaryDirectory(prefix="agent-v3-live-") as temp:
        conn = db.connect(Path(temp) / "live.db")
        run_id = db.start_run(conn, stage="provenance-live-configured-routing")
        if args.stage == "review-analogy":
            classify_result = {"stage": "classify", "skipped": True}
            synthesis_result = {"stage": "synthesis", "skipped": True}
            review_result = _run_stage(
                "review-analogy",
                lambda: stages.review(
                    conn, run_id, review_card,
                    {"title": "Fixture", "subtitle": "Fixture",
                     "body": ANALOGY_REVIEW_BODY},
                ),
            )
            assessments = {
                "review_analogy": (
                    _semantic_analogy_review(review_result["value"])
                    if review_result.get("value") else {"pass": False}
                ),
            }
        else:
            classify_result = _run_stage(
                "classify",
                lambda: stages.classify(conn, run_id, QUESTION, [_source()]),
            )
            synthesis_result = _run_stage(
                "synthesis",
                lambda: stages.synthesis(conn, run_id, QUESTION, evidence),
            )
            review_result = _run_stage(
                "review",
                lambda: stages.review(
                    conn, run_id, review_card,
                    {"title": "Fixture", "subtitle": "Fixture", "body": REVIEW_BODY},
                ),
            )
            assessments = {
                "classify": _assess_classify(classify_result),
                "synthesis": _assess_synthesis(synthesis_result),
                "review": (
                    _semantic_review(review_result["value"])
                    if review_result.get("value") else {"pass": False}
                ),
            }
        calls = [dict(row) for row in conn.execute(
            "SELECT provider, model, purpose, tokens_in, tokens_out, cache_hit, "
            "cost_usd, cost_status, reserved_usd, provider_request_id, "
            "reconciled_at, price_verified, ok, note FROM calls ORDER BY id"
        )]
        contract_checks = [dict(row) for row in conn.execute(
            "SELECT purpose, contract_id, ok, error FROM model_contract_checks ORDER BY id"
        )]
        provenance_checks = [dict(row) for row in conn.execute(
            "SELECT stage, subject_id, ok, error FROM provenance_checks ORDER BY id"
        )]
        passed = all(item.get("pass") for item in assessments.values())
        db.finish_run(
            conn, run_id, "DONE" if passed else "FAILED",
            "provenance-live-configured-routing",
            json.dumps(assessments, ensure_ascii=False),
        )
        output = {
            "experiment": "E-007",
            "routing": "configured",
            "selected_stage": args.stage,
            "models": models,
            "fixture_sha256": provenance._sha256(SOURCE_TEXT),
            "question": QUESTION,
            "assessments": assessments,
            "stages": [classify_result, synthesis_result, review_result],
            "calls": calls,
            "contract_checks": contract_checks,
            "provenance_checks": provenance_checks,
            "known_cost_usd": round(
                sum(float(row["cost_usd"]) for row in calls), 8
            ),
            "unresolved_cost_calls": sum(
                row["cost_status"] in {"RESERVED", "UNKNOWN"} for row in calls
            ),
            "financial_exposure_usd": round(
                sum(
                    float(row["cost_usd"])
                    + (
                        float(row["reserved_usd"])
                        if row["cost_status"] in {"RESERVED", "UNKNOWN"}
                        else 0.0
                    )
                    for row in calls
                ),
                8,
            ),
            "pass": passed,
        }
        conn.close()
        print("E007_RESULT_BEGIN")
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        print("E007_RESULT_END")
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
