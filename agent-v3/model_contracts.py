"""Wersjonowane, zamknięte kontrakty odpowiedzi modeli Agent V3.

To nie jest naprawianie odpowiedzi ani łagodne coercion. Model zwrócił obiekt
zgodny z konkretną wersją albo wynik nie może sterować kolejnym etapem.
"""

from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class ContractError(ValueError):
    """Odpowiedź modelu nie spełnia wskazanego kontraktu."""


Schema = dict[str, Any]


def string(*, nullable: bool = False) -> Schema:
    return {"kind": "string", "nullable": nullable}


def boolean() -> Schema:
    return {"kind": "boolean"}


def integer(*, minimum: int | None = None) -> Schema:
    return {"kind": "integer", "minimum": minimum}


def number(*, minimum: float | None = None,
           maximum: float | None = None) -> Schema:
    return {"kind": "number", "minimum": minimum, "maximum": maximum}


def enum(*values: str) -> Schema:
    return {"kind": "enum", "values": frozenset(values)}


def array(items: Schema) -> Schema:
    return {"kind": "array", "items": items}


def nullable(schema: Schema) -> Schema:
    return {"kind": "nullable", "schema": schema}


def obj(required: Mapping[str, Schema], optional: Mapping[str, Schema] | None = None,
        *, allow_extra: bool = False) -> Schema:
    fields = dict(required)
    fields.update(optional or {})
    return {
        "kind": "object",
        "fields": fields,
        "required": frozenset(required),
        "allow_extra": allow_extra,
    }


S = string()
B = boolean()
I = integer()
NONNEG_I = integer(minimum=0)
STRINGS = array(S)
INTS = array(I)

CLAIM = obj({"claim": S, "fragment_ids": STRINGS})
NUMBER = obj({"number_id": S, "means": S, "claim_index": NONNEG_I})
PARALLEL = obj(
    {"domain": S, "how_it_matches": S},
    {"origin": enum("synthesis", "evidence_bank")},
)


SCHEMAS: dict[str, Schema] = {
    "review": obj({
        "sentences": array(obj(
            {"sentence_id": S,
             "class": enum("FACT", "MIXED", "INFERENCE", "PROSE"),
             "support": enum("SUPPORTED", "UNSUPPORTED", "NOT_APPLICABLE"),
             "claim_ids": STRINGS, "why": S})),
        "summary": S,
    }),
    "forma": obj({
        "beliefs": array(obj({"belief": S, "first_stated": S})),
        "support_only": array(obj({"quote": S, "supports": NONNEG_I})),
        "hardest_fact": obj({"quote": S, "why": S}),
        "procedural_nearby": obj({"quote": S}),
        "same_register": B,
        "reader_moment": nullable(obj({"quote": S, "object": S})),
        "opening_claim": obj({"quote": S, "already_familiar": B}),
        "summary": S,
    }),
    "write": obj({
        "title": S, "subtitle": S, "body": S, "numbers_used": STRINGS,
        "limits_paragraph_present": B,
    }),
    "revise": obj({
        "title": S, "subtitle": S, "body": S,
        "limits_paragraph_present": B, "changes": STRINGS,
    }),
    "wybor": obj({
        "choices": array(obj({
            "index": NONNEG_I, "rank": integer(minimum=1), "why": S,
            "kind": enum("disagreement", "question", "correction", "addition",
                         "agreement"),
        })),
        "skipped_because": S,
    }),
    "reply": obj({
        "reply": nullable(S), "reason_if_silent": S,
        "kind": enum("answer", "correction_accepted", "disagreement", "built_on"),
    }),
    "grafika": obj({"subject": S, "why_this_object": S, "prompt": S}),
    "cele": obj({
        "targets": array(obj({
            "index": NONNEG_I, "worth_it": B, "what_i_would_add": S,
            "why_not": S,
        })),
    }),
    "curiosity": obj({
        "facts": array(obj({
            "fact": S, "wrong_belief": S, "actually": S, "decision": S,
            "consequence": S, "url": S, "domain": S,
        })),
    }),
    "note": obj({"note": S, "words": NONNEG_I, "fact_used": S, "source_url": S}),
    "restack": obj({
        "restack": B, "reason": S, "sentence": S, "mechanism_named": S,
    }),
    "fact_search": obj({
        "facts": array(obj({"fact": S, "url": S})),
    }),
    "verification": obj({
        "claims": array(obj({
            "claim": S, "status": enum("confirmed", "refuted", "unverified"),
            "url": S, "what_the_source_says": S,
        })),
        "safe_to_post": B, "verdict": S,
    }),
    "comment": obj({
        "comment": nullable(S), "reason_if_silent": S, "what_it_adds": S,
    }),
    "synthesis": obj({
        "working_thesis": S, "main_mechanism": S,
        "confirmed_claims": array(CLAIM), "citable_numbers": array(NUMBER),
        "parallel_mechanisms": array(PARALLEL), "uncertain_claims": STRINGS,
        "contradictions": STRINGS, "not_established": STRINGS,
    }),
    "classify": obj({
        "class": enum("PRIMARY", "SUPPORTING", "ODPAD"),
        "relevance": number(minimum=0.0, maximum=1.0),
        "excerpts": STRINGS, "note": S,
    }),
    "discovery": obj({
        "sources": array(obj({
            "url": S, "title": S, "publisher": S,
            "class": enum("PRIMARY", "SUPPORTING"),
            "host_role": enum(
                "ORIGINATING_AUTHORITY", "OFFICIAL_ARCHIVE", "MIRROR", "OTHER"
            ),
            "access_claim": enum(
                "FULL_TEXT_NO_LOGIN", "LANDING_ONLY_OR_LOGIN", "UNKNOWN"
            ),
            "published_at": S,
            "evidence_status": enum(
                "OBSERVED_CURRENT_RECORD", "ENACTED_OR_IN_FORCE",
                "PROPOSED_OR_PENDING", "HISTORICAL_ANALYSIS", "UNKNOWN"
            ),
            "evidence_roles": array(enum(
                "MECHANISM", "CURRENT_SCALE", "SECOND_ACT",
                "COUNTEREVIDENCE_OR_LIMIT", "BACKGROUND"
            )),
            "answers_why": B, "has_numbers": B, "note": S,
        })),
    }),
    "feasibility": obj({
        "assessments": array(obj({
            "index": NONNEG_I, "feasible": B,
            "confidence": number(minimum=0.0, maximum=1.0),
            "expected_primary_sources": NONNEG_I,
            "depth": enum("RICH", "SINGLE", "THIN"),
            "parallels": STRINGS, "note": S,
            "route_assessments": array(obj({
                "route_index": NONNEG_I, "feasible": B,
                "confidence": number(minimum=0.0, maximum=1.0),
                "expected_primary_sources": NONNEG_I,
                "depth": enum("RICH", "SINGLE", "THIN"),
                "second_act": S, "note": S,
            })),
            "selected_route_index": NONNEG_I,
            "selected_route_reason": S,
        })),
    }),
    "scout": obj({
        "discarded_seeds": array(obj({"title": S, "rejection": S})),
        "topics": array(obj({
            "title": S, "central_question": S, "mode": S,
            "why_fascinating": S, "reader_entry_point": S,
            "obvious_coverage": STRINGS,
            "underexplored_connections": STRINGS,
            "dimensions": array(obj({
                "name": S, "question_opened": S, "why_independent": S,
            })),
            "tensions": array(obj({
                "force_a": S, "force_b": S, "why_unresolved": S,
            })),
            "open_branches": array(obj({
                "possibility": S, "logic": S,
                "what_would_change_our_mind": S,
            })),
            "article_routes": array(obj({
                "question": S, "distinct_engine": S, "evidence_needed": S,
            })),
            "note_test": obj({
                "can_be_exhausted_in_three_sentences": B, "why": S,
            }),
            "fatal_weakness": S,
        })),
        "ranking": obj({
            "largest_article_universe": INTS, "most_compelling": INTS,
            "most_original_angle": INTS, "most_likely_to_collapse": INTS,
        }),
    }),
    "bibliotekarz": obj({
        "groups": array(obj({
            "mechanism": S, "why_it_travels": S,
            "members": array(obj({"id": NONNEG_I, "domain": S, "role": S})),
            "missing": S,
        })),
        "loners": INTS, "note": S,
    }),
    "warto_pisac": obj({
        "contradicted_belief": obj({"present": B, "the_belief": S, "evidence": S}),
        "named_decider": obj({"present": B, "evidence": S}),
        "felt_number": obj({"present": B, "evidence": S}),
        "second_domain": obj({"present": B, "evidence": S}),
        "unsettled_outcome": obj({
            "present": B, "the_question": S, "the_situation": S, "governed_by": S,
        }),
        "what_would_rescue_it": S, "one_line_verdict": S,
    }),
    "fedreg": obj({
        "candidates": array(obj({
            "fact": S, "wrong_belief": S, "actually": S, "decision": S,
            "consequence": S, "domain": S,
        })),
    }),
}


@dataclass(frozen=True)
class Contract:
    name: str
    version: int
    schema: Schema
    custom: Callable[[Any], None] | None = None

    @property
    def schema_hash(self) -> str:
        def plain(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: plain(value[key]) for key in sorted(value)}
            if isinstance(value, (set, frozenset)):
                return sorted(plain(item) for item in value)
            if isinstance(value, (list, tuple)):
                return [plain(item) for item in value]
            return value

        payload = json.dumps(
            plain(self.schema), ensure_ascii=True, sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}:{self.schema_hash}"


def _fail(path: str, message: str) -> None:
    raise ContractError(f"{path}: {message}")


def _validate(schema: Schema, value: Any, path: str) -> None:
    kind = schema["kind"]
    if kind == "nullable":
        if value is None:
            return
        _validate(schema["schema"], value, path)
        return
    if kind == "string":
        if value is None and schema.get("nullable"):
            return
        if not isinstance(value, str):
            _fail(path, f"oczekiwano string, jest {type(value).__name__}")
        return
    if kind == "boolean":
        if type(value) is not bool:
            _fail(path, f"oczekiwano boolean, jest {type(value).__name__}")
        return
    if kind == "integer":
        if type(value) is not int:
            _fail(path, f"oczekiwano integer, jest {type(value).__name__}")
        if schema.get("minimum") is not None and value < schema["minimum"]:
            _fail(path, f"wartość {value} < {schema['minimum']}")
        return
    if kind == "number":
        if type(value) not in {int, float} or not math.isfinite(float(value)):
            _fail(path, f"oczekiwano skończonej liczby, jest {value!r}")
        if schema.get("minimum") is not None and value < schema["minimum"]:
            _fail(path, f"wartość {value} < {schema['minimum']}")
        if schema.get("maximum") is not None and value > schema["maximum"]:
            _fail(path, f"wartość {value} > {schema['maximum']}")
        return
    if kind == "enum":
        if not isinstance(value, str) or value not in schema["values"]:
            _fail(path, f"wartość {value!r} poza enum {sorted(schema['values'])}")
        return
    if kind == "array":
        if not isinstance(value, list):
            _fail(path, f"oczekiwano array, jest {type(value).__name__}")
        for index, item in enumerate(value):
            _validate(schema["items"], item, f"{path}[{index}]")
        return
    if kind == "object":
        if not isinstance(value, dict):
            _fail(path, f"oczekiwano object, jest {type(value).__name__}")
        missing = sorted(schema["required"] - value.keys())
        if missing:
            _fail(path, f"brak pól {missing}")
        unknown = sorted(value.keys() - schema["fields"].keys())
        if unknown and not schema["allow_extra"]:
            _fail(path, f"nadmiarowe pola {unknown}")
        for key, item in value.items():
            if key in schema["fields"]:
                _validate(schema["fields"][key], item, f"{path}.{key}")
        return
    raise RuntimeError(f"nieznany rodzaj schematu {kind!r}")


def _custom_review(data: dict[str, Any]) -> None:
    seen: set[str] = set()
    for index, sentence in enumerate(data["sentences"]):
        path = f"$.sentences[{index}]"
        sentence_id = sentence["sentence_id"]
        if sentence_id in seen:
            _fail(f"{path}.sentence_id", "duplikat")
        seen.add(sentence_id)
        factual = sentence["class"] in {"FACT", "MIXED"}
        if factual and sentence["support"] == "NOT_APPLICABLE":
            _fail(f"{path}.support", "FACT/MIXED wymaga oceny pokrycia")
        if (factual and sentence["support"] == "SUPPORTED"
                and not sentence["claim_ids"]):
            _fail(f"{path}.claim_ids", "SUPPORTED wymaga claim_id")
        if (factual and sentence["support"] == "UNSUPPORTED"
                and not sentence["why"].strip()):
            _fail(f"{path}.why", "UNSUPPORTED wymaga uzasadnienia")
        if not factual and sentence["support"] != "NOT_APPLICABLE":
            _fail(f"{path}.support", "INFERENCE/PROSE wymaga NOT_APPLICABLE")
        if not factual and sentence["claim_ids"]:
            _fail(f"{path}.claim_ids", "INFERENCE/PROSE nie wiąże twierdzeń")


def _custom_synthesis(data: dict[str, Any]) -> None:
    for index, claim in enumerate(data["confirmed_claims"]):
        if not claim["claim"].strip():
            _fail(f"$.confirmed_claims[{index}].claim", "puste twierdzenie")
        if not claim["fragment_ids"]:
            _fail(f"$.confirmed_claims[{index}].fragment_ids", "brak dowodu")
        if len(claim["fragment_ids"]) != len(set(claim["fragment_ids"])):
            _fail(f"$.confirmed_claims[{index}].fragment_ids", "duplikat")


def _custom_forma(data: dict[str, Any]) -> None:
    size = len(data["beliefs"])
    for index, support in enumerate(data["support_only"]):
        if support["supports"] >= size:
            _fail(f"$.support_only[{index}].supports", "indeks poza beliefs")


def _custom_scout(data: dict[str, Any]) -> None:
    total = len(data["topics"])
    for index, topic in enumerate(data["topics"]):
        if topic["note_test"]["can_be_exhausted_in_three_sentences"]:
            _fail(
                f"$.topics[{index}].note_test",
                "finalista sam przyznaje, że jest notką",
            )
        dimension_names = [
            item["name"].strip().casefold() for item in topic["dimensions"]
        ]
        if len(dimension_names) != len(set(dimension_names)):
            _fail(f"$.topics[{index}].dimensions", "powtórzone osie")
        route_questions = [
            item["question"].strip().casefold() for item in topic["article_routes"]
        ]
        if len(route_questions) != len(set(route_questions)):
            _fail(f"$.topics[{index}].article_routes", "powtórzone pytania")
    if total == 0 and all(not values for values in data["ranking"].values()):
        return
    ranking_size = min(3, total)
    for name, indices in data["ranking"].items():
        if len(indices) != ranking_size or len(indices) != len(set(indices)):
            _fail(
                f"$.ranking.{name}",
                f"wymagane {ranking_size} różne indeksy dla {total} tematów",
            )
        for index in indices:
            if index < 0 or index >= total:
                _fail(f"$.ranking.{name}", f"indeks {index} poza topics")
    if total >= 2 * ranking_size and set(
            data["ranking"]["largest_article_universe"]) & set(
            data["ranking"]["most_likely_to_collapse"]):
        _fail("$.ranking", "największe uniwersum nie może jednocześnie upadać")


def _custom_feasibility(data: dict[str, Any]) -> None:
    seen_topics: set[int] = set()
    for index, assessment in enumerate(data["assessments"]):
        topic_index = assessment["index"]
        if topic_index in seen_topics:
            _fail(f"$.assessments[{index}].index", "duplikat tematu")
        seen_topics.add(topic_index)
        routes = assessment["route_assessments"]
        if not routes:
            _fail(f"$.assessments[{index}].route_assessments", "pusta ocena dróg")
        route_indices = [item["route_index"] for item in routes]
        if len(route_indices) != len(set(route_indices)):
            _fail(f"$.assessments[{index}].route_assessments", "duplikat drogi")
        selected = assessment["selected_route_index"]
        candidates = [
            item for item in routes
            if item["route_index"] == selected and item["feasible"]
            and item["depth"] != "THIN"
        ]
        if not candidates:
            _fail(
                f"$.assessments[{index}].selected_route_index",
                "wybrana droga nie istnieje, jest niewykonalna albo THIN",
            )
        for route_index, route in enumerate(routes):
            if route["depth"] == "RICH" and len(route["second_act"].split()) < 4:
                _fail(
                    f"$.assessments[{index}].route_assessments[{route_index}]"
                    ".second_act",
                    "RICH wymaga opisanego drugiego aktu",
                )


def _custom_silence(data: dict[str, Any], field: str) -> None:
    if data[field] is None and not data["reason_if_silent"].strip():
        _fail("$.reason_if_silent", f"wymagane, gdy {field} jest null")


def _custom_verification(data: dict[str, Any]) -> None:
    for index, claim in enumerate(data["claims"]):
        if claim["status"] == "refuted" and not claim["what_the_source_says"].strip():
            _fail(f"$.claims[{index}].what_the_source_says", "wymagane dla refuted")


def _custom_discovery(data: dict[str, Any]) -> None:
    for index, source in enumerate(data["sources"]):
        if not source["published_at"].strip():
            _fail(f"$.sources[{index}].published_at", "data lub rok są wymagane")
        roles = source["evidence_roles"]
        if not roles:
            _fail(f"$.sources[{index}].evidence_roles", "co najmniej jedna rola")
        if len(roles) != len(set(roles)):
            _fail(f"$.sources[{index}].evidence_roles", "role muszą być unikalne")


CUSTOM: dict[str, Callable[[Any], None]] = {
    "review": _custom_review,
    "forma": _custom_forma,
    "scout": _custom_scout,
    "feasibility": _custom_feasibility,
    "reply": lambda data: _custom_silence(data, "reply"),
    "comment": lambda data: _custom_silence(data, "comment"),
    "verification": _custom_verification,
    "synthesis": _custom_synthesis,
    "discovery": _custom_discovery,
}

VERSIONS = {
    "review": 2, "synthesis": 2, "classify": 2, "scout": 3,
    "feasibility": 3, "discovery": 3,
}

CONTRACTS: dict[str, Contract] = {
    name: Contract(name, VERSIONS.get(name, 1), schema, CUSTOM.get(name))
    for name, schema in SCHEMAS.items()
}


def contract_id(name: str) -> str:
    try:
        return CONTRACTS[name].id
    except KeyError as exc:
        raise ContractError(f"nieznany kontrakt {name!r}") from exc


def validate(name: str, value: Any) -> dict[str, Any]:
    """Waliduje bez naprawiania i zwraca ten sam słownik."""
    try:
        contract = CONTRACTS[name]
    except KeyError as exc:
        raise ContractError(f"nieznany kontrakt {name!r}") from exc
    try:
        _validate(contract.schema, value, "$")
        if contract.custom is not None:
            contract.custom(value)
    except ContractError as exc:
        raise ContractError(f"{contract.id}: {exc}") from exc
    return value
