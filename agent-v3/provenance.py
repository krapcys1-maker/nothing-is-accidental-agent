"""Wykonywalny łańcuch pochodzenia treści Agent V3.

Identyfikatory nadaje kod, nie model. Model może wybrać wyłącznie istniejący
fragment, liczbę albo twierdzenie, a każda relacja jest sprawdzana przed użyciem.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sqlite3
from collections import defaultdict
from typing import Any, Iterable


class ProvenanceError(ValueError):
    """Dane nie tworzą pełnego, wewnętrznie spójnego łańcucha dowodu."""


LINEAGE_VERSION = 1
NUMBER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])\d(?:[\d,]*\d)?(?:\.\d+)?%?(?![A-Za-z0-9_])"
)
_CLOSERS = '\"”’)]}'
_ABBREVIATIONS = frozenset({
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "st.", "vs.",
    "e.g.", "i.e.", "u.s.", "u.k.", "no.", "fig.", "inc.", "ltd.",
})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_v{LINEAGE_VERSION}_{_sha256(payload)[:24]}"


def numeric_tokens(text: str) -> list[str]:
    """Zwraca liczby dokładnie w zapisie widocznym w tekście."""
    return [match.group(0) for match in NUMBER_TOKEN.finditer(text)]


def documentize(source: dict[str, Any]) -> dict[str, Any]:
    """Nadaje wersjonowane ID dokładnie tej treści pod dokładnym finalnym URL-em."""
    text = str(source.get("text") or "")
    url = str(source.get("url") or source.get("final_url") or "").strip()
    if not url:
        raise ProvenanceError("dokument nie ma finalnego URL-u")
    if not text:
        raise ProvenanceError(f"dokument {url!r} nie ma tekstu")
    content_sha256 = _sha256(text)
    document_id = _stable_id("doc", url, content_sha256)
    result = dict(source)
    result["document_id"] = document_id
    result["content_sha256"] = content_sha256
    return result


def fragments_from_excerpts(
    source: dict[str, Any], excerpts: Iterable[str],
) -> dict[str, Any]:
    """Wiąże dosłowne cytaty z offsetami dokumentu i wylicza liczby z cytatów."""
    result = documentize(source)
    text = result["text"]
    fragments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in excerpts:
        excerpt = str(raw)
        if not excerpt.strip():
            raise ProvenanceError("pusty fragment dowodowy")
        start = text.find(excerpt)
        if start < 0:
            raise ProvenanceError(
                f"fragment nie jest dosłownym podciągiem {result['document_id']}: "
                f"{excerpt[:120]!r}"
            )
        end = start + len(excerpt)
        fragment_id = _stable_id(
            "frag", result["document_id"], start, end, _sha256(excerpt)
        )
        if fragment_id in seen:
            continue
        seen.add(fragment_id)
        fragments.append({
            "fragment_id": fragment_id,
            "document_id": result["document_id"],
            "text": excerpt,
            "start_offset": start,
            "end_offset": end,
            "text_sha256": _sha256(excerpt),
        })

    numbers: list[dict[str, Any]] = []
    for fragment in fragments:
        for ordinal, match in enumerate(NUMBER_TOKEN.finditer(fragment["text"])):
            value = match.group(0)
            numbers.append({
                "number_id": _stable_id(
                    "num", fragment["fragment_id"], ordinal, match.start(), value
                ),
                "value": value,
                "fragment_id": fragment["fragment_id"],
                "document_id": result["document_id"],
                "url": result["url"],
            })
    result["fragments"] = fragments
    # Pole tekstowe pozostaje kompatybilnym widokiem, nie źródłem tożsamości.
    result["excerpts"] = [fragment["text"] for fragment in fragments]
    result["numbers"] = numbers
    result["provenance_version"] = LINEAGE_VERSION
    return result


def _evidence_index(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    documents: dict[str, dict[str, Any]] = {}
    fragments: dict[str, dict[str, Any]] = {}
    numbers: dict[str, dict[str, Any]] = {}
    for raw_source in evidence:
        source = raw_source
        document_id = str(source.get("document_id") or "")
        if not document_id:
            raise ProvenanceError("źródło evidence nie ma document_id")
        if document_id in documents:
            raise ProvenanceError(f"powtórzony document_id {document_id}")
        documents[document_id] = {
            "document_id": document_id,
            "url": str(source.get("url") or ""),
            "content_sha256": str(source.get("content_sha256") or ""),
            "publisher": str(source.get("publisher") or ""),
            "title": str(source.get("title") or ""),
            "source_class": str(source.get("class") or ""),
            "published_at": str(source.get("published_at") or ""),
            "retrieved_at": str(source.get("retrieved_at") or ""),
            "evidence_status": str(source.get("evidence_status") or ""),
            "evidence_roles": [
                str(role) for role in source.get("evidence_roles") or []
            ],
        }
        if not documents[document_id]["url"] or not documents[document_id]["content_sha256"]:
            raise ProvenanceError(f"niepełny dokument {document_id}")
        source_text = str(source.get("text") or "")
        if not source_text or _sha256(source_text) != documents[document_id]["content_sha256"]:
            raise ProvenanceError(f"tekst dokumentu {document_id} nie zgadza się z SHA-256")
        expected_document_id = _stable_id(
            "doc", documents[document_id]["url"], documents[document_id]["content_sha256"]
        )
        if document_id != expected_document_id:
            raise ProvenanceError(f"document_id {document_id} nie zgadza się z treścią")
        for fragment in source.get("fragments") or []:
            fragment_id = str(fragment.get("fragment_id") or "")
            if not fragment_id or fragment_id in fragments:
                raise ProvenanceError(f"brak lub duplikat fragment_id {fragment_id!r}")
            if fragment.get("document_id") != document_id:
                raise ProvenanceError(f"fragment {fragment_id} wskazuje inny dokument")
            start = fragment.get("start_offset")
            end = fragment.get("end_offset")
            fragment_text = str(fragment.get("text") or "")
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                raise ProvenanceError(f"fragment {fragment_id} ma błędne offsety")
            if source_text[start:end] != fragment_text:
                raise ProvenanceError(f"fragment {fragment_id} nie zgadza się z dokumentem")
            text_sha256 = _sha256(fragment_text)
            expected_fragment_id = _stable_id(
                "frag", document_id, start, end, text_sha256
            )
            if (fragment.get("text_sha256") != text_sha256
                    or fragment_id != expected_fragment_id):
                raise ProvenanceError(f"fragment {fragment_id} nie zgadza się z hashem")
            fragments[fragment_id] = dict(fragment)
        expected_numbers: dict[str, str] = {}
        for fragment in source.get("fragments") or []:
            for ordinal, match in enumerate(NUMBER_TOKEN.finditer(fragment["text"])):
                value = match.group(0)
                expected_numbers[_stable_id(
                    "num", fragment["fragment_id"], ordinal, match.start(), value
                )] = value
        for number in source.get("numbers") or []:
            number_id = str(number.get("number_id") or "")
            if not number_id or number_id in numbers:
                raise ProvenanceError(f"brak lub duplikat number_id {number_id!r}")
            fragment_id = str(number.get("fragment_id") or "")
            if fragment_id not in fragments:
                raise ProvenanceError(f"liczba {number_id} wskazuje obcy fragment")
            if number.get("value") not in numeric_tokens(fragments[fragment_id]["text"]):
                raise ProvenanceError(f"liczba {number_id} nie występuje we fragmencie")
            if expected_numbers.get(number_id) != number.get("value"):
                raise ProvenanceError(f"number_id {number_id} nie zgadza się z pozycją")
            numbers[number_id] = dict(number)
        if set(expected_numbers) != {
                str(number.get("number_id") or "") for number in source.get("numbers") or []}:
            raise ProvenanceError(f"inwentarz liczb dokumentu {document_id} jest niepełny")
    return {"documents": documents, "fragments": fragments, "numbers": numbers}


def bind_card(card: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Zastępuje indeksy modelu zweryfikowanymi relacjami i ID nadanymi przez kod."""
    index = _evidence_index(evidence)
    result = copy.deepcopy(card)
    bound_claims: list[dict[str, Any]] = []
    for ordinal, claim in enumerate(result.get("confirmed_claims") or []):
        fragment_ids = list(claim.get("fragment_ids") or [])
        if not fragment_ids or len(fragment_ids) != len(set(fragment_ids)):
            raise ProvenanceError(f"twierdzenie {ordinal} nie ma unikalnych fragment_ids")
        missing = [item for item in fragment_ids if item not in index["fragments"]]
        if missing:
            raise ProvenanceError(f"twierdzenie {ordinal} wskazuje obce fragmenty {missing}")
        claim_text = str(claim.get("claim") or "").strip()
        claim_id = _stable_id("claim", claim_text, *sorted(fragment_ids))
        document_ids = list(dict.fromkeys(
            index["fragments"][item]["document_id"] for item in fragment_ids
        ))
        urls = [index["documents"][item]["url"] for item in document_ids]
        bound = dict(claim)
        bound.update({
            "claim_id": claim_id,
            "fragment_ids": fragment_ids,
            "evidence": [index["fragments"][item]["text"] for item in fragment_ids],
            "document_ids": document_ids,
            "urls": urls,
            "url": urls[0],
        })
        bound_claims.append(bound)

    bound_numbers: list[dict[str, Any]] = []
    for ordinal, selected in enumerate(result.get("citable_numbers") or []):
        number_id = str(selected.get("number_id") or "")
        if number_id not in index["numbers"]:
            raise ProvenanceError(f"liczba {ordinal} wskazuje obcy number_id {number_id!r}")
        claim_index = selected.get("claim_index")
        if type(claim_index) is not int or not 0 <= claim_index < len(bound_claims):
            raise ProvenanceError(f"liczba {ordinal} ma claim_index poza zakresem")
        number = index["numbers"][number_id]
        claim = bound_claims[claim_index]
        if number["fragment_id"] not in claim["fragment_ids"]:
            raise ProvenanceError(
                f"liczba {number_id} nie pochodzi z fragmentu twierdzenia "
                f"{claim['claim_id']}"
            )
        bound = dict(selected)
        bound.update({
            "number_id": number_id,
            "value": number["value"],
            "claim_id": claim["claim_id"],
            "fragment_id": number["fragment_id"],
            "document_id": number["document_id"],
            "url": number["url"],
        })
        bound_numbers.append(bound)

    result["confirmed_claims"] = bound_claims
    result["citable_numbers"] = bound_numbers
    result["evidence_manifest"] = {
        "documents": list(index["documents"].values()),
        "fragments": list(index["fragments"].values()),
        "numbers": list(index["numbers"].values()),
    }
    result["provenance_version"] = LINEAGE_VERSION
    return result


def _is_abbreviation(text: str, period_index: int) -> bool:
    prefix = text[:period_index + 1]
    match = re.search(r"([A-Za-z][A-Za-z.]*)\.$", prefix)
    if not match:
        return False
    token = match.group(0).lower()
    return token in _ABBREVIATIONS or bool(re.fullmatch(r"(?:[a-z]\.){2,}", token))


def sentence_units(body: str) -> list[dict[str, Any]]:
    """Dzieli tekst deterministycznie i nadaje jednostkom stabilne ID."""
    units: list[dict[str, Any]] = []
    length = len(body)
    start = 0

    def skip_space(position: int) -> int:
        while position < length and body[position].isspace():
            position += 1
        return position

    def add(raw_start: int, raw_end: int) -> None:
        while raw_start < raw_end and body[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and body[raw_end - 1].isspace():
            raw_end -= 1
        if raw_start >= raw_end:
            return
        text = body[raw_start:raw_end]
        ordinal = len(units)
        units.append({
            "sentence_id": _stable_id("sent", ordinal, text),
            "ordinal": ordinal,
            "text": text,
            "start_offset": raw_start,
            "end_offset": raw_end,
        })

    start = skip_space(start)
    index = start
    while index < length:
        if body.startswith("\n\n", index):
            add(start, index)
            start = skip_space(index + 2)
            index = start
            continue
        char = body[index]
        if char in ".!?":
            if (char == "." and index > 0 and index + 1 < length
                    and body[index - 1].isdigit() and body[index + 1].isdigit()):
                index += 1
                continue
            if char == "." and _is_abbreviation(body[start:index + 1], index - start):
                index += 1
                continue
            end = index + 1
            while end < length and body[end] in _CLOSERS:
                end += 1
            if end == length or body[end].isspace():
                add(start, end)
                start = skip_space(end)
                index = start
                continue
        index += 1
    add(start, length)
    if not units and body.strip():
        raise ProvenanceError("nie udało się podzielić niepustego artykułu")
    return units


def bind_review(
    report: dict[str, Any], units: list[dict[str, Any]], card: dict[str, Any],
) -> dict[str, Any]:
    """Wymaga pełnego bijekcyjnego pokrycia jednostek i istniejących claim_id."""
    by_sentence = {unit["sentence_id"]: unit for unit in units}
    if len(by_sentence) != len(units):
        raise ProvenanceError("kolizja sentence_id")
    rows = list(report.get("sentences") or [])
    returned = [str(row.get("sentence_id") or "") for row in rows]
    if len(returned) != len(set(returned)):
        raise ProvenanceError("recenzja zwróciła sentence_id więcej niż raz")
    missing = sorted(set(by_sentence) - set(returned))
    unknown = sorted(set(returned) - set(by_sentence))
    if missing or unknown:
        raise ProvenanceError(
            f"niepełne pokrycie recenzji: brak={missing}, obce={unknown}"
        )
    claims = {
        str(claim.get("claim_id")): claim
        for claim in card.get("confirmed_claims") or []
        if claim.get("claim_id")
    }
    bound: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for row in rows:
        sentence_id = row["sentence_id"]
        claim_ids = list(row.get("claim_ids") or [])
        foreign = [claim_id for claim_id in claim_ids if claim_id not in claims]
        if foreign:
            raise ProvenanceError(
                f"zdanie {sentence_id} wskazuje obce claim_id {foreign}"
            )
        item = dict(row)
        item.update(by_sentence[sentence_id])
        item["supported"] = item["support"] == "SUPPORTED"
        bound.append(item)
        if item["class"] in {"FACT", "MIXED"} and not item["supported"]:
            unsupported.append({
                "sentence_id": sentence_id,
                "text": item["text"],
                "class": item["class"],
                "why": item.get("why", ""),
            })
    bound.sort(key=lambda item: item["ordinal"])
    return {
        "sentences": bound,
        "unsupported_facts": unsupported,
        "summary": str(report.get("summary") or ""),
        "provenance_version": LINEAGE_VERSION,
    }


def analyze_usage(
    card: dict[str, Any], evidence: list[dict[str, Any]],
    report: dict[str, Any], body: str,
) -> dict[str, Any]:
    """Wylicza faktyczne użycie i wykrywa liczby bez pełnego związania."""
    index = _evidence_index(evidence)
    claims = {
        claim["claim_id"]: claim for claim in card.get("confirmed_claims") or []
        if claim.get("claim_id")
    }
    numbers = {
        number["number_id"]: number for number in card.get("citable_numbers") or []
        if number.get("number_id")
    }
    numbers_by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for number in numbers.values():
        numbers_by_value[str(number.get("value") or "")].append(number)

    used_claim_ids: set[str] = set()
    used_number_ids: set[str] = set()
    findings: list[dict[str, str]] = []
    for sentence in report.get("sentences") or []:
        factual = sentence.get("class") in {"FACT", "MIXED"}
        supported = sentence.get("support") == "SUPPORTED"
        claim_ids = set(sentence.get("claim_ids") or [])
        if factual and supported:
            used_claim_ids.update(claim_ids)
        for token in numeric_tokens(str(sentence.get("text") or "")):
            candidates = numbers_by_value.get(token, [])
            if not candidates:
                continue  # osobna bramka LICZBA_SPOZA_KORPUSU
            linked = [
                item for item in candidates
                if factual and supported and item.get("claim_id") in claim_ids
            ]
            if not linked:
                findings.append({
                    "gate": "LICZBA_BEZ_LANCUCHA",
                    "detail": (
                        f"liczba {token!r} w {sentence.get('sentence_id')} nie jest "
                        "związana z twierdzeniem wspierającym tę jednostkę"
                    ),
                })
            else:
                used_number_ids.update(item["number_id"] for item in linked)

    used_fragment_ids: set[str] = set()
    for claim_id in used_claim_ids:
        used_fragment_ids.update(claims[claim_id].get("fragment_ids") or [])
    for number_id in used_number_ids:
        used_fragment_ids.add(numbers[number_id]["fragment_id"])

    used_document_ids = set(
        index["fragments"][fragment_id]["document_id"]
        for fragment_id in used_fragment_ids
    )
    citations = []
    article_fingerprint = _sha256(body)
    for document in index["documents"].values():
        if document["document_id"] not in used_document_ids:
            continue
        citations.append({
            "citation_id": _stable_id(
                "cite", article_fingerprint, document["document_id"]
            ),
            "ordinal": len(citations),
            "document_id": document["document_id"],
            "url": document["url"],
        })

    unused_by_document: dict[str, dict[str, Any]] = {}
    for document_id, document in index["documents"].items():
        unused_fragments = [
            fragment for fragment in index["fragments"].values()
            if fragment["document_id"] == document_id
            and fragment["fragment_id"] not in used_fragment_ids
        ]
        unused_numbers = [
            number for number in index["numbers"].values()
            if number["document_id"] == document_id
            and number["number_id"] not in used_number_ids
        ]
        if unused_fragments or unused_numbers:
            unused_by_document[document_id] = {
                **document,
                "fragments": copy.deepcopy(unused_fragments),
                "excerpts": [fragment["text"] for fragment in unused_fragments],
                "numbers": copy.deepcopy(unused_numbers),
            }

    return {
        "used_claim_ids": sorted(used_claim_ids),
        "used_number_ids": sorted(used_number_ids),
        "used_fragment_ids": sorted(used_fragment_ids),
        "citations": citations,
        "unused_evidence": list(unused_by_document.values()),
        "findings": findings,
    }


def finalize_card(
    card: dict[str, Any], evidence: list[dict[str, Any]],
    report: dict[str, Any], body: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Dołącza wyliczony ledger finalnego tekstu bez ufania deklaracji pisarza."""
    usage = analyze_usage(card, evidence, report, body)
    result = copy.deepcopy(card)
    for key in (
        "used_claim_ids", "used_number_ids", "used_fragment_ids", "citations",
        "unused_evidence",
    ):
        result[key] = usage[key]
    result["sentence_ledger"] = copy.deepcopy(report.get("sentences") or [])
    result["provenance_version"] = LINEAGE_VERSION
    return result, usage["findings"]


def citation_urls(card: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(
        str(item.get("url") or "") for item in card.get("citations") or []
        if item.get("url")
    ))


def _validate_final_graph(card: dict[str, Any]) -> None:
    manifest = card.get("evidence_manifest") or {}
    documents = {
        item.get("document_id"): item for item in manifest.get("documents") or []
    }
    fragments = {
        item.get("fragment_id"): item for item in manifest.get("fragments") or []
    }
    inventory_numbers = {
        item.get("number_id"): item for item in manifest.get("numbers") or []
    }
    if None in documents or None in fragments or None in inventory_numbers:
        raise ProvenanceError("manifest ma element bez ID")
    if (len(documents) != len(manifest.get("documents") or [])
            or len(fragments) != len(manifest.get("fragments") or [])
            or len(inventory_numbers) != len(manifest.get("numbers") or [])):
        raise ProvenanceError("manifest ma zduplikowane ID")
    for fragment_id, fragment in fragments.items():
        if fragment.get("document_id") not in documents:
            raise ProvenanceError(f"fragment {fragment_id} wskazuje obcy dokument")
        if _sha256(str(fragment.get("text") or "")) != fragment.get("text_sha256"):
            raise ProvenanceError(f"fragment {fragment_id} ma niespójny hash")

    claims = {
        item.get("claim_id"): item for item in card.get("confirmed_claims") or []
    }
    if None in claims or len(claims) != len(card.get("confirmed_claims") or []):
        raise ProvenanceError("karta ma brakujące albo zduplikowane claim_id")
    for claim_id, claim in claims.items():
        if not claim.get("fragment_ids") or any(
                fragment_id not in fragments for fragment_id in claim["fragment_ids"]):
            raise ProvenanceError(f"twierdzenie {claim_id} ma obcy fragment")

    selected_numbers = {
        item.get("number_id"): item for item in card.get("citable_numbers") or []
    }
    if None in selected_numbers or len(selected_numbers) != len(
            card.get("citable_numbers") or []):
        raise ProvenanceError("karta ma brakujące albo zduplikowane number_id")
    for number_id, number in selected_numbers.items():
        inventory = inventory_numbers.get(number_id)
        if inventory is None or inventory.get("value") != number.get("value"):
            raise ProvenanceError(f"liczba {number_id} nie zgadza się z manifestem")
        claim = claims.get(number.get("claim_id"))
        if claim is None or number.get("fragment_id") not in claim["fragment_ids"]:
            raise ProvenanceError(f"liczba {number_id} nie ma spójnego twierdzenia")

    used_claims = set(card.get("used_claim_ids") or [])
    used_numbers = set(card.get("used_number_ids") or [])
    if not used_claims <= set(claims) or not used_numbers <= set(selected_numbers):
        raise ProvenanceError("zestaw użytych ID wykracza poza kartę")
    sentences = card.get("sentence_ledger") or []
    sentence_ids = [item.get("sentence_id") for item in sentences]
    if None in sentence_ids or len(sentence_ids) != len(set(sentence_ids)):
        raise ProvenanceError("ledger zdań ma brakujące albo zduplikowane ID")
    for sentence in sentences:
        if any(claim_id not in claims for claim_id in sentence.get("claim_ids") or []):
            raise ProvenanceError(f"zdanie {sentence['sentence_id']} ma obce twierdzenie")

    expected_document_ids: set[str] = set()
    for claim_id in used_claims:
        for fragment_id in claims[claim_id]["fragment_ids"]:
            expected_document_ids.add(fragments[fragment_id]["document_id"])
    citation_ids = [item.get("citation_id") for item in card.get("citations") or []]
    citation_documents = {
        item.get("document_id") for item in card.get("citations") or []
    }
    if None in citation_ids or len(citation_ids) != len(set(citation_ids)):
        raise ProvenanceError("cytowania mają brakujące albo zduplikowane ID")
    if citation_documents != expected_document_ids:
        raise ProvenanceError("cytowania nie odpowiadają użytym dokumentom")


def persist_article_lineage(
    conn: sqlite3.Connection, article_id: int, card: dict[str, Any],
) -> None:
    """Zapisuje cały znormalizowany graf pochodzenia dla finalnej wersji."""
    if card.get("provenance_version") != LINEAGE_VERSION:
        raise ProvenanceError("karta nie ma aktywnej wersji pochodzenia")
    _validate_final_graph(card)
    manifest = card.get("evidence_manifest") or {}
    used_claims = set(card.get("used_claim_ids") or [])
    used_numbers = set(card.get("used_number_ids") or [])

    for document in manifest.get("documents") or []:
        conn.execute(
            "INSERT OR IGNORE INTO provenance_documents "
            "(document_id, url, content_sha256, publisher, title, source_class) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (document["document_id"], document["url"], document["content_sha256"],
             document.get("publisher"), document.get("title"),
             document.get("source_class")),
        )
    for fragment in manifest.get("fragments") or []:
        conn.execute(
            "INSERT OR IGNORE INTO provenance_fragments "
            "(fragment_id, document_id, text, start_offset, end_offset, text_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fragment["fragment_id"], fragment["document_id"], fragment["text"],
             fragment["start_offset"], fragment["end_offset"],
             fragment["text_sha256"]),
        )
    for claim in card.get("confirmed_claims") or []:
        conn.execute(
            "INSERT INTO article_claims "
            "(article_id, claim_id, claim_text, used) VALUES (?, ?, ?, ?)",
            (article_id, claim["claim_id"], claim["claim"],
             int(claim["claim_id"] in used_claims)),
        )
        for fragment_id in claim.get("fragment_ids") or []:
            conn.execute(
                "INSERT INTO claim_fragments (article_id, claim_id, fragment_id) "
                "VALUES (?, ?, ?)", (article_id, claim["claim_id"], fragment_id),
            )
    for number in card.get("citable_numbers") or []:
        conn.execute(
            "INSERT INTO article_numbers "
            "(article_id, number_id, value, claim_id, fragment_id, used) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (article_id, number["number_id"], number["value"], number["claim_id"],
             number["fragment_id"], int(number["number_id"] in used_numbers)),
        )
    for sentence in card.get("sentence_ledger") or []:
        conn.execute(
            "INSERT INTO article_sentences "
            "(article_id, sentence_id, ordinal, text, classification, support_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (article_id, sentence["sentence_id"], sentence["ordinal"],
             sentence["text"], sentence["class"], sentence["support"]),
        )
        for claim_id in sentence.get("claim_ids") or []:
            conn.execute(
                "INSERT INTO sentence_claims (article_id, sentence_id, claim_id) "
                "VALUES (?, ?, ?)", (article_id, sentence["sentence_id"], claim_id),
            )
    for citation in card.get("citations") or []:
        conn.execute(
            "INSERT INTO article_citations "
            "(article_id, citation_id, ordinal, document_id, url) "
            "VALUES (?, ?, ?, ?, ?)",
            (article_id, citation["citation_id"], citation["ordinal"],
             citation["document_id"], citation["url"]),
        )
