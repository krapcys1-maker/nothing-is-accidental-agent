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


def _nazwa_zrodla(conn: sqlite3.Connection, url: str) -> str:
    """Nazwa źródła zamiast gołego adresu.

    Lista surowych URL-i pod tekstem wygląda jak zrzut z narzędzia, a nie jak
    przypisy — a oświadczenie o AI obiecuje czytelnikowi, że źródła są do
    sprawdzenia. Sprawdza je ten, kto widzi, CO otwiera.
    """
    row = conn.execute(
        "SELECT title FROM sources WHERE url = ? AND title IS NOT NULL AND title != ''"
        " ORDER BY id DESC LIMIT 1",
        (url,),
    ).fetchone()
    tytul = (row["title"] if row else "") or ""
    tytul = " ".join(tytul.split())
    if not tytul:
        # Bez tytułu lepszy jest sam host niż stumetrowy adres z parametrami.
        return urlparse(url).netloc.replace("www.", "")
    if len(tytul) > 90:
        tytul = tytul[:87].rstrip(" ,.–—-") + "…"
    return f"{tytul} — {urlparse(url).netloc.replace('www.', '')}"


def save(
    conn: sqlite3.Connection, run_id: int, topic: dict[str, Any],
    card: dict[str, Any], draft: dict[str, Any], status: str,
    blocked_by: str | None, notes: list[dict[str, str]],
) -> Path:
    """Etap 9 — zapis. Artykuł do szuflady: baza + plik .md."""
    config.ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (draft.get("title") or "artykul").lower()).strip("-")
    path = config.ARTICLES_DIR / f"{run_id:04d}-{slug[:60]}.md"
    # Plik ma być GOTOWY DO WKLEJENIA, a nie mieszanką tekstu i naszych notatek.
    # Wcześniej trafiał tu nagłówek "Źródła" po polsku — w artykule pisanym po
    # angielsku — oraz sekcja "Status: SAVED", czyli zapis wewnętrzny, który
    # czytelnikowi nic nie mówi. Status i tak siedzi w tabeli `articles`, więc
    # w pliku był duplikatem.
    urls = list(dict.fromkeys(
        c.get("url") for c in card.get("confirmed_claims", []) if c.get("url")
    ))
    path.write_text(
        f"# {draft.get('title', '')}\n\n*{draft.get('subtitle', '')}*\n\n"
        f"{draft['body']}\n\n---\n\n## Sources\n\n"
        + "\n".join(f"- [{_nazwa_zrodla(conn, url)}]({url})" for url in urls)
        + "\n",
        encoding="utf-8",
    )
    # Wszystko, co jest naszą notatką, a nie tekstem dla czytelnika, ląduje obok
    # — i tylko wtedy, gdy jest co zapisać.
    if status != "SAVED" or blocked_by or notes:
        path.with_suffix(".uwagi.md").write_text(
            f"# Uwagi wewnętrzne — {draft.get('title', '')}\n\n"
            f"Status: {status}" + (f" — {blocked_by}" if blocked_by else "") + "\n\n"
            + "\n".join(f"- {n}" for n in notes) + "\n",
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


REPLY_SYSTEM = (
    "You reply to comments under your own publication's articles, notes and "
    "comments. You are the host: you answer, you accept corrections, you never "
    "invent facts. Return only valid JSON."
)


def reply_to(
    conn: sqlite3.Connection, run_id: int, comment: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Odpowiedź na komentarz pod własną treścią — do szuflady."""
    prompt = _prompt(
        "odpowiedz.md",
        language=config.ARTICLE_LANGUAGE,
        under_what=comment.get("under", ""),
        commenter=comment.get("author", ""),
        comment=comment.get("text", "")[:3000],
        evidence=json.dumps(evidence, ensure_ascii=False, indent=2)[:7000],
    )
    candidates: list[dict[str, Any]] = []
    for i in range(config.COMMENT_CANDIDATES):
        try:
            raw = llm.call("reply", REPLY_SYSTEM, prompt, conn=conn, run_id=run_id)
            data = llm.parse_json(raw)
        except Exception as exc:
            print(f"  [odpowiedź {i + 1}] nie wyszła: {exc}", flush=True)
            continue
        text = data.get("reply")
        print(
            f"  [odpowiedź {i + 1}] "
            + (f"{len(text.split())} słów [{data.get('kind')}] {text[:70]}"
               if text else f"MILCZY — {data.get('reason_if_silent', '')[:60]}"),
            flush=True,
        )
        candidates.append(data)
    return {"comment": comment.get("text", "")[:200], "candidates": candidates}


def plan_tygodnia(dzien_artykulu: int = 6) -> list[dict[str, Any]]:
    """Harmonogram tygodnia: co i kiedy wychodzi.

    Godziny w czasie wschodnioamerykańskim, bo tam jest publiczność. Niedziela
    (6) to dzień artykułu — pokrywa się z najlepszym oknem dla notek, więc
    artykuł i notki o nim wzmacniają się nawzajem.
    """
    dni = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek",
           "sobota", "niedziela"]
    plan: list[dict[str, Any]] = []
    for numer, nazwa in enumerate(dni):
        dzien_art = numer == dzien_artykulu
        if dzien_art:
            typy = config.NOTE_MIX_ARTICLE_DAY
        else:
            # Obrót zestawu wg numeru dnia: bez tego poniedziałek i sobota
            # dostawały identyczny plan i tydzień wyglądał jak jeden dzień
            # powtórzony sześć razy.
            mix = config.NOTE_MIX_OTHER_DAY
            typy = tuple(mix[(numer + i) % len(mix)] for i in range(len(mix)))
        # Najlepsze okna najpierw, resztę rozkładamy przez dzień; piątkowego
        # południa unikamy, bo tam zmierzono czterokrotnie gorszy wynik.
        godziny = [6, 8, 10, 15, 19] if nazwa != "piątek" else [6, 8, 10, 16, 20]
        plan.append({
            "dzien": nazwa,
            "artykul": dzien_art,
            "notki": [{"godzina_et": g, "typ": t} for g, t in zip(godziny, typy)],
            "komentarze": config.COMMENTS_PER_DAY,
        })
    return plan


NOTE_SYSTEM = (
    "You write very short Substack Notes for an anonymous editorial brand. "
    "Every fact comes from the supplied evidence, never from your own memory. "
    "Return only valid JSON."
)


IMAGE_SYSTEM = (
    "You write image briefs for the header illustrations of an anonymous "
    "editorial publication. The visual style is fixed and not yours to change. "
    "Return only valid JSON."
)


def grafika(
    conn: sqlite3.Connection, run_id: int, draft: dict[str, Any],
    sciezka_artykulu: Path | None = None,
) -> dict[str, Any]:
    """Nagłówek graficzny artykułu.

    Rozpoznawalność bierze się z powtarzalności, nie z pomysłowości: model
    wybiera PRZEDMIOT, a sposób pokazania go jest przepisywany dosłownie z
    `prompts/grafika.md`. Dzięki temu tożsamość wizualna zmienia się w jednym
    miejscu, a nie osobno przy każdym artykule.
    """
    prompt = _prompt(
        "grafika.md",
        title=draft.get("title", ""),
        body=draft.get("body", "")[:6000],
    )
    brief = llm.parse_json(
        llm.call("grafika", IMAGE_SYSTEM, prompt, conn=conn, run_id=run_id)
    )
    opis = brief.get("prompt") or ""
    if not opis:
        raise ValueError("brief graficzny bez promptu")
    print(f"  [grafika] przedmiot: {brief.get('subject', '')}", flush=True)

    dane = llm.obraz(opis, conn=conn, run_id=run_id)
    if not dane:
        return brief   # DRY_RUN
    cel = (sciezka_artykulu.with_suffix(".png") if sciezka_artykulu
           else config.ARTICLES_DIR / f"{run_id:04d}-naglowek.png")
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_bytes(dane)
    brief["plik"] = str(cel)
    print(f"  [grafika] zapisana: {cel.name}  {len(dane) // 1024} KB", flush=True)
    return brief


ZUZYTE_FAKTY = config.DATA_DIR / "zuzyte_fakty.json"


def _klucz_faktu(tekst: str) -> str:
    """Odcisk faktu odporny na przestawienie słów i inną liczbę w tym samym zdaniu."""
    slowa = re.findall(r"[a-z]{4,}", tekst.lower())
    return " ".join(sorted(set(slowa))[:12])


def wczytaj_zuzyte() -> list[str]:
    if not ZUZYTE_FAKTY.exists():
        return []
    try:
        return json.loads(ZUZYTE_FAKTY.read_text(encoding="utf-8"))
    except Exception:
        return []


def zapisz_zuzyte(nowe: list[str]) -> None:
    """Pamięć zużytych ciekawostek — poza bazą, bo budżet to cztery tabele."""
    wszystkie = wczytaj_zuzyte() + [t for t in nowe if t]
    ZUZYTE_FAKTY.parent.mkdir(parents=True, exist_ok=True)
    ZUZYTE_FAKTY.write_text(
        json.dumps(wszystkie[-config.CURIOSITY_MEMORY * 3:], ensure_ascii=False,
                   indent=1),
        encoding="utf-8",
    )


CURIOSITY_SYSTEM = (
    "You find documented facts about ordinary things for an anonymous editorial "
    "brand. You search before you answer and you never state a fact you cannot "
    "put a source against. Return only valid JSON."
)


def znajdz_ciekawostki(
    conn: sqlite3.Connection, run_id: int, ile: int = config.CURIOSITY_BATCH
) -> list[dict[str, Any]]:
    """Materiał na notki w dni bez artykułu.

    Notka typu CIEKAWOSTKA nie ma artykułu, z którego mogłaby wziąć dowody, a
    cztery z pięciu notek dziennie są właśnie takie. Bez tego etapu jedyne
    źródło to pamięć modelu — czyli dokładnie to, co wycięliśmy z komentarzy.
    """
    zuzyte = wczytaj_zuzyte()
    prompt = _prompt(
        "ciekawostki.md", ile=ile,
        uzyte=("\n".join(f"- {t}" for t in zuzyte[-config.CURIOSITY_MEMORY:])
               or "(nothing yet — this is the first batch)"),
    )
    try:
        raw = llm.call("curiosity", CURIOSITY_SYSTEM, prompt,
                       conn=conn, run_id=run_id, web_search=True)
        fakty = llm.parse_json(raw).get("facts") or []
    except Exception as exc:
        print(f"  [ciekawostki] nie wyszły ({exc})", flush=True)
        return []
    fakty = [f for f in fakty if f.get("fact") and f.get("url")]
    # Druga siatka na powtórki: model bywa głuchy na własną listę zakazów, a to
    # samo szukanie codziennie oddaje te same słynne fakty. Odsiewamy w kodzie.
    znane = {_klucz_faktu(t) for t in zuzyte}
    swieze = [f for f in fakty if _klucz_faktu(f["fact"]) not in znane]
    if len(swieze) < len(fakty):
        print(f"  [ciekawostki] odrzucone jako już użyte: {len(fakty) - len(swieze)}",
              flush=True)
    fakty = swieze
    zapisz_zuzyte([f["fact"] for f in fakty])
    print(f"  [ciekawostki] z pokryciem: {len(fakty)}", flush=True)
    for f in fakty:
        print(f"    · [{f.get('domain', '')[:18]}] {f.get('fact', '')[:88]}", flush=True)
    return fakty


def note(
    conn: sqlite3.Connection, run_id: int, note_type: str, evidence: dict[str, Any],
    link: str | None = None,
) -> dict[str, Any]:
    """Jedna notka danego typu — do szuflady.

    `evidence` to karta artykułu albo fragmenty, których artykuł nie zużył.
    W obu wypadkach notka stoi na materiale ocytowanym, więc nie ma skąd
    zmyślać liczby. Generujemy kilku kandydatów; wybór należy do właściciela.
    """
    prompt = _prompt(
        "notka.md",
        language=config.ARTICLE_LANGUAGE,
        min_words=config.NOTE_MIN_WORDS,
        max_words=config.NOTE_MAX_WORDS,
        note_type=note_type,
        type_brief=config.NOTE_TYPES[note_type],
        evidence=json.dumps(evidence, ensure_ascii=False, indent=2)[:9000],
    )
    candidates: list[dict[str, Any]] = []
    for i in range(config.NOTE_CANDIDATES):
        try:
            raw = llm.call("note", NOTE_SYSTEM, prompt, conn=conn, run_id=run_id)
            data = llm.parse_json(raw)
        except Exception as exc:
            print(f"  [notka {i + 1}] nie wyszła: {exc}", flush=True)
            continue
        text = (data.get("note") or "").strip()
        words = len(text.split())
        data["words_actual"] = words
        in_range = config.NOTE_MIN_WORDS <= words <= config.NOTE_MAX_WORDS
        data["length_ok"] = in_range
        print(
            f"  [notka {i + 1}] {words:>3} słów {'OK ' if in_range else 'POZA'}"
            f"  {text[:78]}",
            flush=True,
        )
        if text and link:
            # Adres dokłada KOD, nie model. Model potrafi przekręcić URL, a zły
            # link pod notką promującą artykuł to notka wyrzucona do kosza.
            # Doklejamy po pomiarze długości, żeby adres nie liczył się jako słowa.
            data["note"] = text = f"{text}\n\n{link}"
        if text:
            # Notka mówi fakt publicznie tak samo jak komentarz, więc idzie tym
            # samym pasem: blokuje wyłącznie fakt obalony przez źródło.
            audyt = zweryfikuj(conn, run_id, text, f"Substack note, type {note_type}")
            data["weryfikacja"] = audyt
            data["safe_to_post"] = bool(audyt.get("safe_to_post"))
            if not data["safe_to_post"]:
                print(f"    ODPADA: {str(audyt.get('verdict', ''))[:76]}", flush=True)
        candidates.append(data)
    return {"type": note_type, "candidates": candidates}


def notki_dnia(
    conn: sqlite3.Connection, run_id: int, dzien_artykulu: bool = False,
    karta: dict[str, Any] | None = None,
    ciekawostki: list[dict[str, Any]] | None = None,
    link_artykulu: str | None = None,
) -> list[dict[str, Any]]:
    """Pięć notek na jeden dzień, każda z innego materiału.

    Podawanie modelowi całej puli faktów naraz nie daje różnorodności, tylko
    pięć wariantów tego samego: przy pierwszym realnym przebiegu cztery z pięciu
    kandydatur chwyciły ten sam fakt o windzie. Jedna notka dostaje więc jeden
    fakt i zestaw dnia różni się z konstrukcji, a nie z nadziei.
    """
    typy = (config.NOTE_MIX_ARTICLE_DAY if dzien_artykulu
            else config.NOTE_MIX_OTHER_DAY)
    if ciekawostki is None:
        ciekawostki = znajdz_ciekawostki(conn, run_id)
    zapas = list(ciekawostki)
    dzien: list[dict[str, Any]] = []
    for typ in typy:
        if typ == "ARTYKUL" and karta:
            material = karta
        else:
            if not zapas:
                zapas = znajdz_ciekawostki(conn, run_id)
                if not zapas:
                    print("  [notki] brak materiału — kończę dzień krócej", flush=True)
                    break
            material = {"fact": zapas.pop(0)}
        print(f"  [{typ}]", flush=True)
        # Adres artykułu leci TYLKO pod notką, która ten artykuł promuje.
        # Pod ciekawostką byłby reklamą doklejoną do faktu i psułby ją.
        dzien.append(note(conn, run_id, typ, material,
                          link=link_artykulu if typ == "ARTYKUL" else None))
    return dzien


COMMENT_SYSTEM = (
    "You write comments under other people's Substack posts as an anonymous "
    "editorial brand. Silence is the default: you comment only when you have "
    "something of your own to add. Return only valid JSON."
)


FACTCHECK_SYSTEM = (
    "You search the web and return only facts you actually found, each with the "
    "URL it came from. You never fill gaps from memory. Return only valid JSON."
)


def sprawdz_fakty(
    conn: sqlite3.Connection, run_id: int, post: dict[str, Any]
) -> list[dict[str, Any]]:
    """Szuka faktów do komentarza, zamiast pozwolić modelowi pisać z pamięci.

    Bez tego komentarze były erudycją z pamięci. Sprawdzone na żywym przykładzie:
    model twierdził, że Osborne Executive nie był kompatybilny z IBM, a zapis
    mówi coś innego i ostrzejszego — firma REKLAMOWAŁA kompatybilność, której
    nigdy nie dostarczyła. Publicznego komentarza z błędnym faktem nie da się
    cofnąć, więc te ~4 centy to najtańsze ubezpieczenie w całym potoku.
    """
    prompt = (
        "Search the web for verifiable facts about the subject of the post below.\n\n"
        "Return at most 8 facts. Each must be something you found in a search "
        "result, with the URL. Prefer dates, figures, filings, official records "
        "and named decisions over commentary. If a widely repeated claim about "
        "this subject turns out to be disputed, say so — that is the most "
        "valuable kind of fact here.\n\n"
        "Do NOT fill gaps from memory. A short honest list beats a long one.\n\n"
        'Return only: {"facts": [{"fact": "...", "url": "..."}]}\n\n'
        f"--- POST ---\nTitle: {post.get('title', '')}\n\n{post.get('text', '')[:6000]}"
    )
    try:
        raw = llm.call(
            "factcheck", FACTCHECK_SYSTEM, prompt,
            conn=conn, run_id=run_id, web_search=True,
        )
        fakty = llm.parse_json(raw).get("facts") or []
    except Exception as exc:
        print(f"  [fakty] nie udało się sprawdzić ({exc}) — komentarz bez pokrycia",
              flush=True)
        return []
    print(f"  [fakty] zweryfikowanych: {len(fakty)}", flush=True)
    return fakty


def zweryfikuj(
    conn: sqlite3.Connection, run_id: int, tekst: str, kontekst: str = "",
) -> dict[str, Any]:
    """Sprawdza to, co model NAPISAŁ — nie to, czego szukał przed pisaniem.

    Sprawdzanie faktów przed pisaniem nie przewidzi, jakiego faktu model użyje.
    Dowód z życia: wszystkie trzy kandydatury oparły się na tym, że Butlin i wsp.
    wykluczyli IIT — twierdzeniu prawdziwym, ale nieobecnym na liście wcześniej
    zweryfikowanych faktów. Tym razem pamięć modelu trafiła. Nie ma powodu zakładać,
    że trafi zawsze.
    """
    prompt = _prompt("weryfikacja.md", context=kontekst, text=tekst)
    try:
        raw = llm.call("factcheck", FACTCHECK_SYSTEM, prompt,
                       conn=conn, run_id=run_id, web_search=True)
        out = llm.parse_json(raw)
    except Exception as exc:
        # Awaria weryfikacji to nie jest dowód fałszu. Komentarz i tak stoi na faktach
        # zebranych przed pisaniem — druga siatka pękła, pierwsza trzyma.
        return {"claims": [], "safe_to_post": True,
                "verdict": f"weryfikacja nie doszła do skutku ({exc}) — puszczam na pierwszej siatce"}
    # Próg mieszka tutaj, nie w ocenie modelu: blokuje wyłącznie fakt OBALONY.
    # Nieznalezione to nie nieprawdziwe. Teza o mechanizmach, motywach czy skutkach
    # jest stanowiskiem, a stanowisko ma prawo być głośne i sporne — po to jest to pismo.
    obalone = [c for c in out.get("claims", []) if c.get("status") == "refuted"]
    for c in out.get("claims", []):
        if c.get("status") != "confirmed":
            print(f"    {'! OBALONE' if c.get('status') == 'refuted' else '· nieznalezione'}: "
                  f"{str(c.get('claim'))[:80]}", flush=True)
    out["safe_to_post"] = not obalone
    return out


def comment_on(
    conn: sqlite3.Connection, run_id: int, post: dict[str, Any],
    fakty: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Komentarz do cudzego posta — do szuflady.

    Generuje kilku kandydatów i oddaje wszystkich; wybór należy do właściciela.
    Milczenie jest pełnoprawną odpowiedzią i nie jest porażką.
    """
    if fakty is None:
        fakty = sprawdz_fakty(conn, run_id, post)
    if not fakty:
        # Przy artykule brak dowodów oznacza gorszy artykuł, ale artykuł musi powstać.
        # Przy komentarzu jest odwrotnie: milczenie jest pełnoprawną odpowiedzią, a
        # publicznego komentarza z wymyślonym faktem nie da się cofnąć. Więc bez
        # pokrycia nie komentujemy.
        print("  [komentarz] brak zweryfikowanych faktów — nie komentuję", flush=True)
        return {
            "post": post.get("url"), "title": post.get("title"),
            "candidates": [{"comment": None,
                            "reason_if_silent": "Nie udało się zweryfikować żadnego faktu."}],
            "fakty": [],
        }
    if fakty:
        post = dict(post)
        post["text"] = (
            post.get("text", "")[:9000]
            + "\n\n--- VERIFIED FACTS (checked against sources; use only these "
            "for anything factual, and cite nothing that is not here) ---\n"
            + "\n".join(f"- {f.get('fact')}  [{f.get('url')}]" for f in fakty)
        )
    prompt = _prompt(
        "komentarz.md",
        language=config.ARTICLE_LANGUAGE,
        author=post.get("author", ""),
        title=post.get("title", ""),
        body=post.get("text", "")[:12000],
    )
    candidates: list[dict[str, Any]] = []
    for i in range(config.COMMENT_CANDIDATES):
        try:
            raw = llm.call("comment", COMMENT_SYSTEM, prompt, conn=conn, run_id=run_id)
            data = llm.parse_json(raw)
        except Exception as exc:
            print(f"  [komentarz {i + 1}] nie wyszedł: {exc}", flush=True)
            continue
        text = data.get("comment")
        words = len(text.split()) if text else 0
        print(
            f"  [komentarz {i + 1}] "
            + (f"{words} słów — {data.get('what_it_adds', '')[:70]}"
               if text else f"MILCZY — {data.get('reason_if_silent', '')[:70]}"),
            flush=True,
        )
        if text:
            audyt = zweryfikuj(conn, run_id, text, post.get("title", ""))
            data["weryfikacja"] = audyt
            data["safe_to_post"] = bool(audyt.get("safe_to_post"))
            print(f"    -> {'PRZECHODZI' if data['safe_to_post'] else 'ODPADA'}: "
                  f"{str(audyt.get('verdict', ''))[:78]}", flush=True)
        candidates.append(data)
    return {
        "post": post.get("url"),
        "title": post.get("title"),
        "candidates": candidates,
        "fakty": fakty,   # zostaje w zapisie: po wystawieniu da się sprawdzić, na czym stał
    }


def fallback_card(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Karta złożona z dowodów bez modelu — gdy synteza padnie.

    Zasada właściciela: skoro temat jest wybrany, a research zrobiony i opłacony,
    artykuł MUSI powstać. Ta karta jest gorsza od syntezy — nie waży dowodów, nie
    znajduje sprzeczności — ale pozwala pisarzowi ruszyć, zamiast wyrzucać
    opłacony research do kosza.
    """
    claims = [
        {"claim": e["excerpts"][0][: config.CARD_MAX_CLAIM_CHARS],
         "evidence": e["excerpts"][0], "url": e["url"]}
        for e in evidence if e.get("excerpts")
    ][: config.CARD_MAX_CONFIRMED]
    numbers = [
        {"value": n, "means": e.get("title", ""), "url": e["url"]}
        for e in evidence for n in e.get("numbers", [])
    ][: config.CARD_MAX_NUMBERS]
    return {
        "working_thesis": question,
        "main_mechanism": "",
        "confirmed_claims": claims,
        "citable_numbers": numbers,
        "uncertain_claims": [],
        "contradictions": [],
        "not_established": [
            "This card was assembled mechanically because the synthesis step "
            "failed; nothing here has been weighed against anything else."
        ],
        "_fallback": True,
    }


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
        print(
            f"  [uwaga] po klasyfikacji {primary} źródeł pierwotnych zamiast "
            f"{config.MIN_PRIMARY_SOURCES}",
            flush=True,
        )
    if not kept:
        raise ValueError("klasyfikacja odrzuciła wszystko — nie ma materiału")
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
                if response.status_code >= 400:
                    reason = f"HTTP {response.status_code}"
                else:
                    text = trafilatura.extract(body, include_comments=False) or ""
                    # Frazy odmowy sprawdzamy w WYDOBYTYM TEKŚCIE, nie w surowym
                    # HTML-u. Surowy HTML zawiera skrypty i konfigurację: każda
                    # strona Substacka niesie klucz "captcha_site_key" formularza
                    # logowania, więc kontrola na HTML-u uznawała za zablokowane
                    # strony, które nikogo nie blokują. To ta sama lekcja co przy
                    # podłogach artykułu — porównuj z treścią, nie z alfabetem.
                    lowered = text.lower()
                    if any(phrase in lowered for phrase in config.REFUSAL_PHRASES):
                        reason = "host odmówił automatowi"
                    elif len(text) < config.FETCH_MIN_CHARS:
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
        # Ostrzeżenie, nie bramka. Nic nie blokuje artykułu — decyzja właściciela.
        print(
            f"  [uwaga] po pobraniu {primary} źródeł pierwotnych zamiast "
            f"{config.MIN_PRIMARY_SOURCES} — artykuł będzie ostrożniejszy",
            flush=True,
        )
    if not fetched:
        raise ValueError("nie pobrano ani jednej strony — nie ma z czego pisać")
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
        max_searches=config.DISCOVERY_MAX_SEARCHES,
        min_primary=config.MIN_PRIMARY_SOURCES,
        min_why=config.MIN_WHY_SOURCES,
        blocked_hosts=", ".join(config.BLOCKED_HOSTS),
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

    # Brak wyników wyszukiwania znaczy, że model NIE SZUKAŁ i podaje adresy
    # z pamięci. Zamykamy się, a nie otwieramy: pierwsza wersja tego filtru
    # miała warunek „jeśli są wyniki, sprawdzaj", więc przy zerze wyników
    # przepuściła dziesięć zmyślonych adresów, z których pobrały się trzy,
    # a klasyfikacja odrzuciła wszystkie.
    if not real_urls:
        raise ValueError(
            "dyskoveria nie wykonała ani jednego wyszukiwania — zwrócone adresy "
            "pochodzą z pamięci modelu, nie z sieci"
        )
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

    print(
        f"  [dyskoveria] {len(real_urls)} wyników wyszukiwania -> "
        f"{len(sources)} zaproponowanych -> {len(kept)} po filtrze",
        flush=True,
    )
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
