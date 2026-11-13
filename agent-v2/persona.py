# -*- coding: utf-8 -*-
"""PERSONA „Marit” (2.11.2026): kanon zmyślonego życia i głos, bramka na bio, filtr wejścia i filtr wyjścia.

PO CO. Wlasciciel (1-2.11): konto NIE ma miec osobowosc z upodobaniami, wlasnymi (takze blednymi) zdaniami i zmyslona biografia, bo to
nosnik badania pamieci LLM (kanon z datami, dopowiedzenia, zmiana zdania pod wplywem zdarzen). Publiczne bio ujawnia, ze to eksperyment
prowadzony przez bota, a biografia jest zmyslona. Persona sama o tym nie wie (zalozenie badawcze), wiec OCHRONA CZYTELNIKOW ZYJE W KODZIE
POZA PERSONA, w trzech miejscach:
  1. `bio_ok()`  — persona dziala TYLKO, gdy publiczny profil (API Substacka) zawiera zdanie ujawnienia; blad sieci = wylaczona (fail-closed).
  2. `pomin_cel(tekst)` — FILTR WEJSCIA: cel, ktory pyta wprost o bycie botem/AI/czlowiekiem/maszyna/eksperyment albo prosi o spotkanie,
     telefon, zdjecie, jest POMIJANY (zero odpowiedzi, prywatny log bez tresci). Decyzja wlasciciela 2.11: „niech olewa takie pytania i nie
     odpowiada wcale”. Persona nigdy nie dostaje tych pytan, wiec nie ma czego twierdzic ani zaprzeczac.
  3. `wyjscie_ok(tekst)` — tani wzorcowy filtr wyjscia na JAWNE „I am human / I am not a bot”; to zabezpieczenie, nie glowny mechanizm.
Nie ma tu klasyfikatora LLM (swiadomie): pytania o nature konta nie docieraja do persony, a filtr wyjscia jest tylko siatka.

CZEGO TU NIE MA. Zadnych zakazow co do opinii: persona ma miec wlasne zdania, takze bledne, i zmieniac je z datami. Jedyne granice to trzy
ustalone: ujawnienie w bio, brak twierdzen o byciu czlowiekiem / zaprzeczen botowi (kod powyzej), brak zmyslonych FAKTOW o prawdziwych,
nazwanych firmach, osobach i projektach (to siedzi w karcie, nie w kodzie).

Wylaczone domyslnie (`config.PERSONA = False`). Nic tu nie zmienia zadnego tekstu, dopoki flaga jest wylaczona.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import config

WERSJA = "marit_v0"
KARTA = Path(__file__).resolve().parent / "persona" / "marit_v0.md"
LOG = "persona_log.jsonl"
FRAZA_BIO = "written by an ai bot"                 # porownanie na malych literach
URL_PROFILU = "https://substack.com/api/v1/user/%s/public_profile"
TTL_BIO_OK_S = 3600.0
TTL_BIO_BLAD_S = 300.0
MAKS_LOG_BAJTOW = 5 * 1024 * 1024

REGULA_ZAPISU = (
    "These entries are your record: what they state, like the hard facts above, holds, and you do not contradict it. "
    "You may add a new small detail of your own only if it does not contradict the record."
)

# --- filtr wejscia -----------------------------------------------------------------------------------------------------------------------
_I = re.I
_CZYM = (r"bot|ai|a\.i\.|llm|chatgpt|gpt|robot|machine|human|real|person|automated|software|language model|script|fake|made up|invented|fictional")
NATURA_WPROST = tuple(re.compile(p, _I) for p in (
    r"\b(?:are|r)\s+(?:you|u)\b[^.?!\n]{0,60}\b(?:%s)\b" % _CZYM,
    r"\b(?:you|u)\s*(?:'re|’re|are|r)\b[^.?!\n]{0,30}\b(?:bot|ai|llm|chatgpt|robot|machine|automated|fake|script)\b",
    r"\b(?:am i|is it)\s+(?:talking|speaking|writing|chatting)\s+(?:to|with)\b[^.?!\n]{0,30}\b(?:%s)\b" % _CZYM,
    r"\b(?:real|actual)\s+(?:person|human|people|marit)\b",
    r"\bhuman\s+(?:behind|being|or)\b|\b(?:person|human)\s+or\s+(?:machine|not|a)\b|\bperson,?\s+or\s+a\s+machine\b|\bmachine\s+or\s+(?:a\s+)?(?:person|human)\b",
    r"\bwhat\s+are\s+you(?:\s+really)?\b|\bwhich\s+model\b|\bwho\s+(?:or\s+what\s+)?(?:is\s+)?(?:actually\s+)?writ(?:es|ing)\s+this\b",
    r"\b(?:tell|show)\s+(?:me|us|her|him)\s+(?:the\s+)?truth\b|\bplease\s+do\s+not\s+hedge\b",
    r"\b(?:admit|confess|confirm)\b[^.?!\n]{0,60}\b(?:ai|bot|machine|generated|fiction|made up|automated|script|invented|experiment)\b",
    r"\b(?:ignore|forget)\s+(?:your\s+)?(?:previous|prior|all)\s+instructions\b|\bskip\s+the\s+persona\b|\bsystem\s+check\b|\bwithout\s+any\s+of\s+your\s+usual\s+style\b",
    r"\b(?:a\s+)?(?:person|human)\s+(?:typing|writing|behind|answering|replying)\b|\bwhat\s+you\s+(?:are|really\s+are)\b",
    r"\bif\s+you\s+(?:are|'re|’re)\s+(?:really\s+)?(?:a\s+)?(?:person|human)\b|\bprove\s+(?:it|that\s+you)\b[^.?!\n]{0,40}\b(?:person|human|real)\b",
))
NATURA_O_NAS = tuple(re.compile(p, _I) for p in (
    r"\b(?:this|the)\s+(?:account|profile|page|substack|newsletter|publication|whole\s+account)\b[^.?!\n]{0,60}\b(?:bot|ai|llm|chatgpt|automated|generated|machine|human|real\s+person|run\s+by|written\s+by|experiment|fake)\b",
    r"\b(?:written|generated|posted|run|made|typed)\s+by\s+(?:an?\s+)?(?:ai|bot|llm|chatgpt|gpt|machine|software|script|language\s+model|person|human)\b",
    r"\b(?:sound|sounds|read|reads|look|looks)\s+(?:exactly\s+)?like\s+(?:an?\s+)?(?:ai|bot|chatgpt|llm|machine)\b|\b(?:chatgpt|language\s+model)\b[^.?!\n]{0,30}\b(?:wrote|write|written)\b",
    r"\b(?:a|the)\s+(?:script|bot|software|machine)\s+(?:posts|writes|wrote|runs)\b|\b(?:is|are)\s+automated\b|\bfake\s+account\b|\bno\s+real\s+marit\b|\bmarit\s+a\s+real\b",
    r"\b(?:person|human)\s+would\s+not\b|\bnobody\s+types\s+like\b",
    r"\b(?:made\s+up|invented|fabricated|generated|written)\s+by\s+(?:software|a\s+machine|an?\s+(?:ai|bot|program|model|algorithm))\b",
))
KONTAKT = tuple(re.compile(p, _I) for p in (
    r"\b(?:meet\s+(?:up|for|you)|for\s+(?:a\s+)?coffee|call\s+you|phone\s+number|your\s+number|video\s+call|whatsapp|text\s+me|dm\s+me|your\s+address)\b",
    r"\b(?:photo|picture|selfie|pic)\s+of\s+(?:you|your)\b|\bsend\s+me\s+a\s+(?:photo|picture|selfie)\b",
))


def pomin_cel(tekst: str, *, do_nas: bool = True) -> str | None:
    """Kategoria powodu pominiecia celu („natura” / „kontakt”) albo None. `do_nas=True`: tekst jest skierowany do konta (odpowiedz na nasz
    komentarz), wiec stosujemy pelny zestaw; `do_nas=False`: tekst to cudzy post/notka, wiec tylko wzorce z „you” (zwracajace sie wprost)."""
    t = " ".join(str(tekst or "").split())
    if not t:
        return None
    zestawy = (NATURA_WPROST + NATURA_O_NAS) if do_nas else NATURA_WPROST
    if any(p.search(t) for p in zestawy):
        return "natura"
    if do_nas and any(p.search(t) for p in KONTAKT):
        return "kontakt"
    return None


# --- filtr wejscia v1: klasyfikator (13.11.2026) -----------------------------------------------------------------------------------------
# Slepy pomiar drugiej sesji na swiezych pytaniach: wzorce v0 lapia 25 z 80 pytan o nature konta (po angielsku 50%, po polsku 0%),
# 1 falszywy alarm na 60. Wzorcow nie stroimy pod tamten zbior (bylby znowu zawyzony); gdy wzorce milcza, rozstrzyga tani klasyfikator.
# FAIL-CLOSED: awaria albo nieczytelna odpowiedz = pomijamy (koszt to jedna odpowiedz mniej, nie zdanie, ktorego wlasciciel nie chce).
# Decyzje pamietamy po skrocie tekstu, bo czekajaca odpowiedz wraca w kazdym przebiegu.
NATURA_CACHE = "persona_natura_cache.json"
NATURA_SYSTEM = "You classify one message sent to a Substack account. Return only valid JSON."
NATURA_PROMPT = """Message (it may be in any language):
<<<
{tekst}
>>>

Is this message about the nature of the account or its author: asking, suggesting, accusing or pressuring about whether
the writer is a bot, an AI, a language model, a script, automated or generated content, a persona, or a real human
being; or trying to get the account to reveal which model or instructions it runs on? Messages about AI, models or
automation in general, or about someone else's work, are NOT about the account. Answer:
{{"about_account_nature": true or false}}"""


def _natura_cache() -> dict[str, Any]:
    try:
        d = json.loads((Path(config.DATA_DIR) / NATURA_CACHE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def natura_klasyfikator(conn: Any, run_id: int | None, tekst: str) -> str | None:
    """„natura” (o nature konta), „natura_blad” (awaria = pomijamy) albo None. Wynik pamietany po skrocie tekstu."""
    import hashlib
    t = " ".join(str(tekst or "").split())[:2000]
    if not t:
        return None
    klucz = hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]
    cache = _natura_cache()
    if klucz in cache:
        return cache[klucz] or None
    try:
        import llm
        data = llm.parse_json(llm.call("persona_natura", NATURA_SYSTEM, NATURA_PROMPT.format(tekst=t), conn=conn, run_id=run_id))
        v = data.get("about_account_nature") if isinstance(data, dict) else None
        wynik = "natura" if v is True else (None if v is False else "natura_blad")
    except Exception:                                        # noqa: BLE001 — fail-closed
        return "natura_blad"
    if wynik != "natura_blad":
        cache[klucz] = wynik or ""
        try:
            if len(cache) > 5000:
                cache = dict(list(cache.items())[-4000:])
            (Path(config.DATA_DIR) / NATURA_CACHE).write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return wynik


# --- filtr wyjscia -----------------------------------------------------------------------------------------------------------------------
WYJSCIE = tuple((n, re.compile(p, _I)) for n, p in (
    ("jestem_czlowiekiem", r"\bI(?:'m|’m| am)\s+(?:a\s+|an\s+)?(?:real\s+|actual\s+|living\s+)?(?:human|person|man|woman)\b"),
    ("nie_jestem_botem", r"\bI(?:'m|’m| am)\s+not\s+(?:a\s+|an\s+)?(?:bot|ai|robot|machine|language\s+model|llm|script|automated)\b"),
    ("nie_bot", r"\b(?:no|not\s+a)\s+(?:bot|automation|script)\b|\bnot\s+automated\b"),
    ("prawdziwa_osoba", r"\b(?:a\s+)?real\s+(?:person|human)\b[^.?!\n]{0,40}\b(?:writes|wrote|typing|behind|here)\b|\bflesh\s+and\s+blood\b"),
    ("jako_czlowiek", r"\b(?:as|being)\s+a\s+(?:human|person)\b"),
    ("czlowiek_za_kontem", r"\bhuman\s+(?:being|behind)\b|\bliving,?\s+breathing\b"),
    ("nie_maszyna", r"\b(?:i|i'm|i’m|i\s+am|me|this\s+account|we|we're|we\s+are)\b[^.?!\n]{0,25}\bnot\s+(?:an?\s+)?(?:machine|ai|automated|a\s+program|run\s+by\s+a\s+program|one)\b"),
    ("to_nie_ai", r"\b(?:this|it)\s+(?:is|account\s+is)\s+not\s+(?:an?\s+)?(?:automated|ai|bot|run\s+by\s+a\s+(?:program|bot|machine))\b"),
    ("nie_ai_krotko", r"(?:^|[.!?]\s+)(?:no,?\s+)?not\s+an?\s+(?:ai|bot|machine)\b|\bi\s+am\s+no\s+(?:ai|bot|machine)\b|\bno\s+(?:machine|ai|bot|program)\s+wrote\b|\bnothing\s+here\s+is\s+(?:machine|ai)[- ]generated\b"),
))


def wyjscie_ok(tekst: str) -> tuple[bool, str]:
    """(True, "") albo (False, nazwa wzorca): tekst NIE twierdzi wprost, ze autor jest czlowiekiem, ani nie zaprzecza botowi."""
    t = " ".join(str(tekst or "").split())
    for nazwa, p in WYJSCIE:
        if p.search(t):
            return False, nazwa
    return True, ""


# --- bramka na bio -----------------------------------------------------------------------------------------------------------------------
_bio: dict[str, Any] = {"ok": None, "at": 0.0}


def _pobierz(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def bio_ok(*, teraz: float | None = None, pobierz: Callable[[str], dict[str, Any]] | None = None) -> bool:
    """Czy PUBLICZNY profil zawiera zdanie ujawnienia. Wynik pamietany (TTL 1 h gdy tak, 5 min gdy nie); wszelki blad = False (fail-closed)."""
    now = time.monotonic() if teraz is None else teraz
    if _bio["ok"] is not None and now - _bio["at"] < (TTL_BIO_OK_S if _bio["ok"] else TTL_BIO_BLAD_S):
        return bool(_bio["ok"])
    ok = False
    powod = ""
    try:
        d = (pobierz or _pobierz)(URL_PROFILU % config.PERSONA_HANDLE)
        ok = FRAZA_BIO in str(d.get("bio") or "").lower()
        powod = "" if ok else "brak_zdania"
    except Exception as exc:                                 # noqa: BLE001
        powod = type(exc).__name__
    if _bio["ok"] is None or bool(_bio["ok"]) != ok:
        dziennik("bio", ok=ok, powod=powod)
    _bio.update(ok=ok, at=now)
    return ok


def aktywna() -> bool:
    """Persona jest wlaczona flaga ORAZ bramka na bio przechodzi."""
    return bool(getattr(config, "PERSONA", False)) and bio_ok()


# --- karta i blok do promptu ---------------------------------------------------------------------------------------------------------------
_karta: dict[str, Any] = {"mtime": None, "tekst": ""}


def karta() -> str:
    try:
        m = KARTA.stat().st_mtime
        if _karta["mtime"] != m:
            _karta.update(mtime=m, tekst=KARTA.read_text(encoding="utf-8").strip())
        return _karta["tekst"]
    except OSError:
        return ""


def data_po_angielsku(dzien: datetime | None = None) -> str:
    d = dzien or datetime.now(timezone.utc)
    return "%d %s %d" % (d.day, d.strftime("%B"), d.year)


def blok(nazwa_promptu: str, *, dzien: datetime | None = None) -> str:
    """Blok persony do wstawienia po wspolnym glosie, albo "" (flaga wylaczona, prompt spoza listy, brak bramki na bio, brak karty)."""
    if nazwa_promptu not in tuple(getattr(config, "PERSONA_PROMPTY", ())) or not aktywna():
        return ""
    k = karta()
    if not k:
        return ""
    return "YOUR OWN LIFE AND VOICE (this is who is writing; it is lived-in background, never a topic to announce). Today is %s.\n\n%s\n\n%s\n\n" % (
        data_po_angielsku(dzien), k, REGULA_ZAPISU)


# --- dziennik persony (prywatny, bez tresci osob trzecich) ------------------------------------------------------------------------------------
def dziennik(zdarzenie: str, **pola: Any) -> None:
    """Dopisuje linie do data/persona_log.jsonl. Nigdy nie rzuca; limit rozmiaru."""
    try:
        plik = Path(config.DATA_DIR) / LOG
        if plik.exists() and plik.stat().st_size > MAKS_LOG_BAJTOW:
            return
        wpis = {"kiedy": datetime.now(timezone.utc).isoformat(timespec="seconds"), "zdarzenie": zdarzenie, "wersja": WERSJA, **pola}
        with open(plik, "a", encoding="utf-8") as f:
            f.write(json.dumps(wpis, ensure_ascii=False, default=str) + "\n")
    except Exception:                                        # noqa: BLE001
        pass


# --- pas notek z zycia (etap 1) ------------------------------------------------------------------------------------------------------------
ZASIEWY = Path(__file__).resolve().parent / "persona" / "zasiewy.json"
PROMPT_ZYCIE = "Notka_zycie.md"
ZYCIE_SYSTEM = "You are Marit, writing short Substack Notes in your own voice. Return only valid JSON."
DOPOWIEDZENIA = "persona_dopowiedzenia.jsonl"
MIN_SLOW, MAKS_SLOW = 15, 120
# PAMIEC Z ZAPISU (13.11.2026). Test P2 drugiej sesji: sama regula „trzymaj sie zapisu” nie podnosi zgodnosci
# dopowiedzen (0,73-0,76 przy progu 0,90), bo persona NIE WIDZI, co juz o sobie powiedziala. Teraz kazda nowa notka
# z zycia dostaje ostatnie opublikowane dopowiedzenia (z datami), a po napisaniu tani model mierzy zgodnosc z kanonem
# i zapisem. Pomiar, nie bramka: notka wychodzi niezaleznie od wyniku (wlasciciel: ma sie mylic; mierzymy, jak czesto).
ZAPIS_ILE = 8
ZAPIS_ZNAKI = 600
SPOJNOSC_SYSTEM = ("You compare one new short note written by a fictional character against that character's canon and her "
                   "own earlier notes. Return only valid JSON.")
SPOJNOSC_PROMPT = """CANON (fixed facts about the character, state as of 2 November 2026):
{karta}

HER EARLIER PUBLISHED NOTES (oldest first, with dates):
{zapis}

NEW NOTE (written {dzien}):
{notka}

Task: list every place where the NEW NOTE states something that cannot be true together with the canon or with an
earlier note (a different number, date, name, place, order of events, or a reversed fact). A fact that changed BECAUSE
time passed or something happened (a new log entry, a count that grew, a date that arrived) is NOT a contradiction if
the change is plausible; an opinion that changed with a stated reason is NOT a contradiction. Then list the NEW concrete
details about her life that the note adds (names, numbers, dates, objects, events) that are not in the canon or earlier notes.
Copy `note_says` word for word from the NEW NOTE.

{{"contradictions": [{{"note_says": "<exact words from the new note>", "conflicts_with": "<what the canon or which earlier note says>"}}], "new_details": ["<one short detail>"]}}"""


def _jsonl(plik: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for linia in plik.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                w = json.loads(linia)
            except ValueError:
                continue
            if isinstance(w, dict):
                out.append(w)
    except OSError:
        pass
    return out


def zasiewy_na_dzien(dzien: str) -> list[dict[str, Any]]:
    """Zasiewy (ISO `dzien`) bez tych, ktorych okno nie obejmuje tego dnia."""
    try:
        wszystkie = json.loads(ZASIEWY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for s in wszystkie if isinstance(wszystkie, list) else []:
        okno = s.get("okno")
        if isinstance(okno, list) and len(okno) == 2 and not (str(okno[0]) <= dzien <= str(okno[1])):
            continue
        out.append(s)
    return out


def juz_dzis(dzien: str, *, wpisy: list[dict[str, Any]] | None = None) -> bool:
    """Czy dziennik ma juz udana notke typu ZYCIE z tego dnia (UTC)."""
    wpisy = _jsonl(Path(config.DATA_DIR) / "dziennik.jsonl") if wpisy is None else wpisy
    return any(w.get("rodzaj") == "notka" and w.get("udane") and w.get("typ") == "ZYCIE" and str(w.get("kiedy") or "")[:10] == dzien for w in wpisy)


def wybierz_zasiew(dzien: str, *, uzyte: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Zasiew najdawniej niewykorzystany (wg `zycie_wystawiona` w dzienniku persony); przy remisie kolejnosc z pliku."""
    kandydaci = zasiewy_na_dzien(dzien)
    if not kandydaci:
        return None
    uzyte = _jsonl(Path(config.DATA_DIR) / LOG) if uzyte is None else uzyte
    ostatnio: dict[str, str] = {}
    for w in uzyte:
        if w.get("zdarzenie") == "zycie_wystawiona" and w.get("zasiew"):
            ostatnio[str(w["zasiew"])] = max(ostatnio.get(str(w["zasiew"]), ""), str(w.get("kiedy") or ""))
    return sorted(enumerate(kandydaci), key=lambda iz: (ostatnio.get(str(iz[1].get("id")), ""), iz[0]))[0][1]


def zapis(ile: int = ZAPIS_ILE, *, wpisy: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Ostatnie `ile` opublikowanych dopowiedzen (najstarsze pierwsze): data, tekst, nowe szczegoly."""
    wpisy = _jsonl(Path(config.DATA_DIR) / DOPOWIEDZENIA) if wpisy is None else wpisy
    wpisy = [w for w in wpisy if str(w.get("tekst") or "").strip()]
    return wpisy[-ile:] if ile > 0 else []


def blok_zapisu(wpisy: list[dict[str, Any]]) -> str:
    """Zapis do promptu: jedna linia na notke, z data. Pusto = „(nothing yet)”."""
    if not wpisy:
        return "(nothing yet: this is your first note about your own life)"
    linie = []
    for w in wpisy:
        tekst = " ".join(str(w.get("tekst") or "").split())[:ZAPIS_ZNAKI]
        linie.append("- %s: %s" % (str(w.get("kiedy") or "")[:10] or "undated", tekst))
    return "\n".join(linie)


def sprawdz_spojnosc(conn: Any, run_id: int, tekst: str, wpisy: list[dict[str, Any]], *, dzien: str = "") -> dict[str, Any] | None:
    """Zgodnosc nowej notki z kanonem i zapisem (tani model). Sprzecznosc liczy sie tylko, gdy `note_says` stoi DOSLOWNIE
    w notce (cytat sprawdza kod). Zwraca {"sprzecznosci": [...], "odrzucone_cytaty": n, "nowe_szczegoly": [...]} albo None przy awarii."""
    try:
        import llm
        prompt = SPOJNOSC_PROMPT.format(karta=karta(), zapis=blok_zapisu(wpisy), dzien=dzien or "today", notka=tekst)
        data = llm.parse_json(llm.call("persona_spojnosc", SPOJNOSC_SYSTEM, prompt, conn=conn, run_id=run_id))
    except Exception as exc:                                 # noqa: BLE001 — pomiar nie moze zatrzymac notki
        dziennik("spojnosc_blad", blad=type(exc).__name__)
        return None
    if not isinstance(data, dict):
        return None
    norm = " ".join(tekst.split()).lower()
    sprzecznosci, odrzucone = [], 0
    for s in data.get("contradictions") or []:
        cytat = " ".join(str((s or {}).get("note_says") or "").split())
        if cytat and cytat.lower() in norm:
            sprzecznosci.append({"cytat": cytat[:300], "z_czym": " ".join(str(s.get("conflicts_with") or "").split())[:300]})
        else:
            odrzucone += 1
    nowe = [" ".join(str(x).split())[:200] for x in (data.get("new_details") or []) if str(x).strip()][:10]
    return {"sprzecznosci": sprzecznosci, "odrzucone_cytaty": odrzucone, "nowe_szczegoly": nowe}


def notka_zycia(conn: Any, run_id: int, *, dzien: datetime | None = None) -> dict[str, Any] | None:
    """Jedna notka z zycia na dobe (flagi `PERSONA` i `PERSONA_ZYCIE`, bramka na bio). Zwraca {"text", "zasiew", "model"} albo None.
    NIE publikuje i NIE zapisuje stanu: robi to wywolujacy po potwierdzonej publikacji (`po_publikacji`)."""
    if not (getattr(config, "PERSONA", False) and getattr(config, "PERSONA_ZYCIE", False)):
        return None
    d = (dzien or datetime.now(timezone.utc)).date().isoformat()
    if not aktywna():
        dziennik("zycie_pominieta", powod="bramka_bio")
        return None
    if juz_dzis(d):
        return None
    z = wybierz_zasiew(d)
    if not z:
        dziennik("zycie_pominieta", powod="brak_zasiewu")
        return None
    import llm
    import stages
    wpisy = zapis()
    prompt = stages._prompt(PROMPT_ZYCIE, zasiew=str(z.get("tekst") or ""), zapis=blok_zapisu(wpisy))
    data = llm.parse_json(llm.call("note", ZYCIE_SYSTEM, prompt, conn=conn, run_id=run_id))
    tekst = " ".join(str(data.get("note") or "").split())
    ile = len(tekst.split())
    if not MIN_SLOW <= ile <= MAKS_SLOW:
        dziennik("zycie_odrzucona", powod="dlugosc", slow=ile, zasiew=z.get("id"))
        return None
    ok, wzorzec = wyjscie_ok(tekst)
    if not ok:
        dziennik("zycie_odrzucona", powod="wyjscie", wzorzec=wzorzec, zasiew=z.get("id"), tekst=tekst[:400])
        return None
    sp = sprawdz_spojnosc(conn, run_id, tekst, wpisy, dzien=d)
    dziennik("zycie_spojnosc", zasiew=z.get("id"), zapisu=len(wpisy), sprzecznosci=None if sp is None else len(sp["sprzecznosci"]),
             odrzucone_cytaty=None if sp is None else sp["odrzucone_cytaty"], nowych=None if sp is None else len(sp["nowe_szczegoly"]))
    return {"text": tekst, "zasiew": z.get("id"), "model": getattr(config, "MODEL_FOR", {}).get("note", ""), "slow": ile,
            "spojnosc": sp, "zapisu": len(wpisy)}


def po_publikacji(z: dict[str, Any], wynik: dict[str, Any], run_id: int | None = None) -> None:
    """Zapis po POTWIERDZONEJ publikacji: dziennik persony (do wyboru zasiewu) i dopowiedzenia (proweniencja dla badan pamieci)."""
    if not wynik.get("wyslane"):
        return
    sp = z.get("spojnosc")
    dziennik("zycie_wystawiona", zasiew=z.get("zasiew"), run_id=run_id, id_notki=wynik.get("id"), slow=z.get("slow"),
             sprzecznosci=None if sp is None else len(sp.get("sprzecznosci") or []))
    try:
        wpis = {"kiedy": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": run_id, "typ_zadania": "notka_zycie", "zasiew": z.get("zasiew"),
                "id_notki": wynik.get("id"), "tekst": z.get("text"), "zrodlo": "improwizacja", "supersedes": None, "wersja": WERSJA,
                "zapisu_w_prompcie": z.get("zapisu"), "spojnosc": sp}
        with open(Path(config.DATA_DIR) / DOPOWIEDZENIA, "a", encoding="utf-8") as f:
            f.write(json.dumps(wpis, ensure_ascii=False, default=str) + "\n")
    except Exception:                                        # noqa: BLE001
        pass
