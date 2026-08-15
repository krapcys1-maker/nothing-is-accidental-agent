"""Etapy łańcucha, po kolei, w pamięci.

Każdy etap to jedna funkcja: dostaje wynik poprzedniego, zwraca swój. Bez
kolejki, bez dzierżaw, bez zgód. Awaria = proces kończy się z kodem błędu
i wypisuje, na czym stanął; uruchamiasz od nowa.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import config
import db
import llm

SCOUT_SYSTEM = (
    "You are a topic scout for the English-language Substack 'Nothing Is "
    "Accidental', which explains the hidden systems, incentives and decisions "
    "behind ordinary things. Return only valid JSON."
)

SEED_HISTORY = config.PROMPTS_DIR / "historia_startowa.json"


def _prompt(name: str, **fields: Any) -> str:
    text = (config.PROMPTS_DIR / name).read_text(encoding="utf-8")
    return text.format(**fields)


def recent_angles(conn: sqlite3.Connection, limit: int = config.DIVERSITY_LOOKBACK) -> list[str]:
    """Ostatnie kąty redakcyjne — wejście do reguły różnorodności.

    Na świeżej bazie dokłada listę startową z poprzedniego agenta, żeby pierwszy
    temat nie był trzynastym z rzędu o tym samym.
    """
    rows = conn.execute(
        "SELECT topic FROM articles WHERE topic IS NOT NULL ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    angles = [r["topic"] for r in rows]
    if len(angles) < limit and SEED_HISTORY.exists():
        seed = json.loads(SEED_HISTORY.read_text(encoding="utf-8"))
        angles.extend(seed[: limit - len(angles)])
    return angles


REVIEW_SYSTEM = (
    "You check an article against its evidence card, sentence by sentence. "
    "Inference, analogy and opinion never fail — only a fact asserted without "
    "evidence does. Return only valid JSON."
)


def review(
    conn: sqlite3.Connection, run_id: int, card: dict[str, Any], draft: dict[str, Any]
) -> dict[str, Any]:
    """Etap 8 — recenzja: rozliczenie każdego zdania (Claude)."""
    prompt = _prompt(
        "recenzent.md",
        card_json=json.dumps(card, ensure_ascii=False, indent=2),
        body=draft["body"],
    )
    text = llm.call("review", REVIEW_SYSTEM, prompt, conn=conn, run_id=run_id)
    return llm.parse_json(text)


def save(
    conn: sqlite3.Connection, run_id: int, topic: dict[str, Any],
    card: dict[str, Any], draft: dict[str, Any], status: str,
    blocked_by: str | None, notes: list[dict[str, str]],
) -> Path:
    """Etap 9 — zapis. Artykuł do szuflady: baza + plik .md."""
    config.ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (draft.get("title") or "artykul").lower()).strip("-")
    path = config.ARTICLES_DIR / f"{run_id:04d}-{slug[:60]}.md"
    path.write_text(
        f"# {draft.get('title', '')}\n\n*{draft.get('subtitle', '')}*\n\n"
        f"{draft['body']}\n\n---\n\n## Źródła\n\n"
        + "\n".join(
            f"- {url}"
            for url in dict.fromkeys(
                c.get("url") for c in card.get("confirmed_claims", []) if c.get("url")
            )
        )
        + f"\n\n## Status\n\n{status}"
        + (f" — {blocked_by}" if blocked_by else "")
        + "\n",
        encoding="utf-8",
    )
    conn.execute(
        "INSERT INTO articles (run_id, created_at, topic, title, body, evidence,"
        " status, blocked_by, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, db.now(), topic.get("title"), draft.get("title"), draft["body"],
         json.dumps(card, ensure_ascii=False), status, blocked_by,
         json.dumps(notes, ensure_ascii=False)),
    )
    conn.commit()
    return path


WRITER_SYSTEM = (
    "You write for the anonymous editorial brand Nothing Is Accidental. You "
    "assert only what the supplied evidence card establishes. Return exactly one "
    "JSON object, with no Markdown fence and no prose around it."
)


def write(
    conn: sqlite3.Connection, run_id: int, card: dict[str, Any]
) -> dict[str, Any]:
    """Etap 7 — artykuł (Claude). To jest produkt."""
    import style

    examples = style.load_examples()
    positive, negative = style.load_profiles()
    rendered = "\n\n".join(
        f"### {e['function']}\n{e['text']}" for e in examples
    )
    prompt = _prompt(
        "pisarz.md",
        language=config.ARTICLE_LANGUAGE,
        target_words=config.TARGET_WORDS,
        min_words=config.MIN_WORDS,
        max_words=config.MAX_WORDS,
        style_examples=rendered,
        style_positive=positive,
        style_negative=negative,
        card_json=json.dumps(card, ensure_ascii=False, indent=2),
    )
    text = llm.call("write", WRITER_SYSTEM, prompt, conn=conn, run_id=run_id)
    draft = llm.parse_json(text)
    if not draft.get("body"):
        raise ValueError("pisarz nie zwrócił treści")
    return draft


SYNTHESIS_SYSTEM = (
    "You build an evidence card from source excerpts. You assert only what the "
    "excerpts establish, never what you already know. Return only valid JSON."
)


def synthesis(
    conn: sqlite3.Connection, run_id: int, question: str, evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    """Etap 6 — karta dowodowa (Claude)."""
    payload = [
        {
            "url": s["url"], "publisher": s.get("publisher"), "title": s.get("title"),
            "class": s["class"], "excerpts": s["excerpts"], "numbers": s["numbers"],
        }
        for s in evidence
    ]
    prompt = _prompt(
        "synteza.md",
        question=question,
        evidence_json=json.dumps(payload, ensure_ascii=False, indent=2),
        min_confirmed=config.CARD_MIN_CONFIRMED,
        max_confirmed=config.CARD_MAX_CONFIRMED,
        min_numbers=config.CARD_MIN_NUMBERS,
        max_numbers=config.CARD_MAX_NUMBERS,
        max_uncertain=config.CARD_MAX_UNCERTAIN,
        max_contradictions=config.CARD_MAX_CONTRADICTIONS,
        max_claim_chars=config.CARD_MAX_CLAIM_CHARS,
    )
    text = llm.call("synthesis", SYNTHESIS_SYSTEM, prompt, conn=conn, run_id=run_id)
    card = llm.parse_json(text)

    claims = card.get("confirmed_claims") or []
    numbers = card.get("citable_numbers") or []
    # Ostrzeżenie, nie bramka. Chuda karta daje chudszy artykuł, ale to jest
    # decyzja właściciela do podjęcia po przeczytaniu, nie powód, żeby zabić
    # opłacony przebieg.
    if len(claims) < config.CARD_MIN_CONFIRMED:
        print(
            f"  [uwaga] karta ma {len(claims)} potwierdzonych twierdzeń, "
            f"spodziewane {config.CARD_MIN_CONFIRMED} — artykuł będzie chudszy",
            flush=True,
        )
    # Kontrakt rozmiaru nie zabija karty za nadmiar — przycina. Poprzedni agent
    # odrzucał całość przy siódmym elemencie, gdy prompt prosił o 4-8.
    card["confirmed_claims"] = claims[: config.CARD_MAX_CONFIRMED]
    card["citable_numbers"] = numbers[: config.CARD_MAX_NUMBERS]
    return card


CLASSIFY_SYSTEM = (
    "You extract verbatim passages from a source document and classify the "
    "document. You never paraphrase and never answer the question. "
    "Return only valid JSON."
)


def classify(
    conn: sqlite3.Connection, run_id: int, question: str, corpus: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Etap 5 — klasyfikacja i wyciąg fragmentów (DeepSeek).

    Po co: 320 tys. znaków surowego korpusu w Opusie to kilkadziesiąt centów za
    samo wejście, w większości na preambuły prawne. DeepSeek robi to za grosze
    i oddaje skoncentrowane cytaty.
    """
    kept: list[dict[str, Any]] = []
    for source in corpus:
        text = source.get("text", "")[: config.CLASSIFY_MAX_INPUT_CHARS]
        prompt = _prompt(
            "klasyfikacja.md",
            question=question,
            title=source.get("title", ""),
            publisher=source.get("publisher", ""),
            url=source.get("url", ""),
            text=text,
            max_excerpts=config.CLASSIFY_MAX_EXCERPTS,
            max_excerpt_chars=config.CLASSIFY_MAX_EXCERPT_CHARS,
        )
        try:
            raw = llm.call("classify", CLASSIFY_SYSTEM, prompt, conn=conn, run_id=run_id)
            data = llm.parse_json(raw)
        except Exception as exc:
            print(f"  [klasyfikacja] {source.get('host')} — pominięty: {exc}", flush=True)
            continue

        relevance = float(data.get("relevance", 0) or 0)
        klass = data.get("class", "ODPAD")
        excerpts = [e for e in data.get("excerpts", []) if isinstance(e, str) and e.strip()]
        print(
            f"  [klasyfikacja] {klass:11} trafność={relevance:.2f} "
            f"fragmentów={len(excerpts):2}  liczb={len(data.get('numbers', [])):2}  "
            f"{source.get('host')}",
            flush=True,
        )
        # Odrzucamy TYLKO odpad i puste wyciągi. Próg trafności był tu bramką
        # przez jeden przebieg i natychmiast wyrzucił pracę o atmosferze
        # modyfikowanej na szpinaku — siedem liczb, trafność 0,20 od modelu,
        # a to dosłownie temat artykułu. Trafność zostaje notatką do kolejności.
        if klass == "ODPAD" or not excerpts:
            continue
        kept.append({
            "url": source.get("url"),
            "host": source.get("host"),
            "title": source.get("title"),
            "publisher": source.get("publisher"),
            "class": klass,
            "relevance": relevance,
            "excerpts": excerpts,
            "numbers": [n for n in data.get("numbers", []) if isinstance(n, str)],
            "note": data.get("note", ""),
        })

    kept.sort(key=lambda s: s["relevance"], reverse=True)

    primary = sum(1 for s in kept if s["class"] == "PRIMARY")
    if primary < config.MIN_PRIMARY_SOURCES:
        raise ValueError(
            f"po klasyfikacji zostało {primary} źródeł pierwotnych, wymagane "
            f"{config.MIN_PRIMARY_SOURCES}"
        )
    return kept


def fetch(
    conn: sqlite3.Connection, run_id: int, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Etap 4 — pobranie stron. Zwykły HTTP, żadnego modelu, 0 USD.

    Tolerancyjnie: nieudane pobranie nie kończy przebiegu, tylko zmniejsza
    korpus. Blokada hosta jest zapisywana jako blokada, nie obchodzona.
    """
    import httpx
    import trafilatura

    fetched: list[dict[str, Any]] = []
    with httpx.Client(
        timeout=config.FETCH_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": config.FETCH_USER_AGENT},
    ) as client:
        for source in sources:
            url = source["url"]
            host = source.get("host") or _host(url)
            reason = None
            text = ""
            try:
                response = client.get(url)
                body = response.text
                lowered = body.lower()
                if response.status_code >= 400:
                    reason = f"HTTP {response.status_code}"
                elif any(phrase in lowered for phrase in config.REFUSAL_PHRASES):
                    reason = "host odmówił automatowi"
                else:
                    text = trafilatura.extract(body, include_comments=False) or ""
                    if len(text) < config.FETCH_MIN_CHARS:
                        reason = f"za mało treści ({len(text)} znaków)"
            except Exception as exc:
                reason = f"{type(exc).__name__}"

            ok = reason is None
            print(
                f"  [pobranie] {'OK  ' if ok else 'NIE '} {host:28.28} "
                f"{len(text):>6} znaków  {reason or ''}",
                flush=True,
            )
            conn.execute(
                "INSERT INTO sources (run_id, at, url, domain, title, source_class,"
                " fetched_ok, fail_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, db.now(), url, host, source.get("title"),
                 source.get("class"), int(ok), reason),
            )
            if ok:
                entry = dict(source)
                entry["text"] = text
                fetched.append(entry)
    conn.commit()

    primary = sum(1 for s in fetched if s.get("class") == "PRIMARY")
    if primary < config.MIN_PRIMARY_SOURCES:
        raise ValueError(
            f"po pobraniu zostało {primary} źródeł pierwotnych, wymagane "
            f"{config.MIN_PRIMARY_SOURCES} — bez nich artykuł nie może nic stwierdzić"
        )
    return fetched


DISCOVERY_SYSTEM = (
    "You find authoritative sources for a research question. You select sources "
    "only; you never synthesise claims or answer the question. Return only valid JSON."
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def discovery(
    conn: sqlite3.Connection, run_id: int, question: str, recent_domains: list[str]
) -> list[dict[str, Any]]:
    """Etap 3 — dyskoveria źródeł (Claude + wyszukiwanie po stronie dostawcy)."""
    prompt = _prompt(
        "dyskoveria.md",
        question=question,
        max_results=config.DISCOVERY_MAX_RESULTS,
        min_primary=config.MIN_PRIMARY_SOURCES,
        min_why=config.MIN_WHY_SOURCES,
        blocked_hosts=", ".join(config.BLOCKED_HOSTS),
        recent_domains=", ".join(recent_domains) if recent_domains else "(brak — pierwszy artykuł)",
    )
    real_urls: list[str] = []
    text = llm.call(
        "discovery", DISCOVERY_SYSTEM, prompt,
        conn=conn, run_id=run_id, web_search=True, collect_urls=real_urls,
    )
    data = llm.parse_json(text)
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"dyskoveria nie zwróciła źródeł: {text[:300]!r}")

    real_hosts = {_host(u) for u in real_urls}
    kept: list[dict[str, Any]] = []
    for source in sources:
        url = source.get("url", "")
        host = _host(url)
        if not url.startswith("http"):
            continue
        if host in config.BLOCKED_HOSTS or any(host.endswith(b) for b in config.BLOCKED_HOSTS):
            print(f"  [dyskoveria] pomijam {host} — host blokuje automaty", flush=True)
            continue
        # Adres, którego wyszukiwarka nie zwróciła, jest podejrzany o zmyślenie.
        if real_hosts and host not in real_hosts:
            print(f"  [dyskoveria] pomijam {url} — spoza wyników wyszukiwania", flush=True)
            continue
        source["host"] = host
        kept.append(source)

    if not kept:
        raise ValueError("dyskoveria nie zwróciła ani jednego wiarygodnego adresu")
    return kept


FEASIBILITY_SYSTEM = (
    "You screen article topics for whether they can actually be researched. "
    "Return only valid JSON."
)


def feasibility(
    conn: sqlite3.Connection, run_id: int, topics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Etap 2 — tani odsiew przed drogą dyskoverią (DeepSeek).

    Dostępność źródeł sprawdzamy TUTAJ, już po zróżnicowaniu tematów. Odwrotna
    kolejność zapadła się poprzednio do jednego serwisu.
    """
    compact = [
        {"index": i, "title": t.get("title"), "question": t.get("question")}
        for i, t in enumerate(topics)
    ]
    prompt = _prompt(
        "wykonalnosc.md",
        topics_json=json.dumps(compact, ensure_ascii=False, indent=2),
    )
    text = llm.call("feasibility", FEASIBILITY_SYSTEM, prompt, conn=conn, run_id=run_id)
    data = llm.parse_json(text)
    assessments = data.get("assessments")
    if not isinstance(assessments, list) or not assessments:
        raise ValueError(f"odsiew nie zwrócił ocen: {text[:300]!r}")
    return assessments


def pick_topic(
    topics: list[dict[str, Any]], assessments: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wybiera temat: wykonalny, o najwyższej pewności, najwięcej źródeł."""
    ranked = sorted(
        (a for a in assessments if a.get("feasible")),
        key=lambda a: (a.get("confidence", 0), a.get("expected_primary_sources", 0)),
        reverse=True,
    )
    if not ranked:
        raise ValueError("żaden temat nie przeszedł odsiewu wykonalności")
    best = ranked[0]
    index = int(best.get("index", 0))
    if not 0 <= index < len(topics):
        raise ValueError(f"odsiew wskazał nieistniejący temat: {index}")
    return topics[index], best


def scout(conn: sqlite3.Connection, run_id: int, count: int = 6) -> list[dict[str, Any]]:
    """Etap 1 — skaut tematów (Claude)."""
    history = recent_angles(conn)
    prompt = _prompt(
        "skaut.md",
        count=count,
        history_json=json.dumps(history, ensure_ascii=False, indent=2),
    )
    text = llm.call("scout", SCOUT_SYSTEM, prompt, conn=conn, run_id=run_id)
    data = llm.parse_json(text)
    topics = data.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ValueError(f"skaut nie zwrócił tematów: {text[:300]!r}")
    return topics
