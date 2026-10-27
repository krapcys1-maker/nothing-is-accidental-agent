# -*- coding: utf-8 -*-
"""Spojnosc nowej notki serii z tym, co JUZ wyszlo pod naszym nazwiskiem (27.10.2026).

PO CO. Notki serii lezą w kolejce kilka dni, a pisarz widzi tylko karte WLASNEGO sledztwa —
nie to, co w miedzyczasie opublikowalismy. Sprawdzenie faktow szuka w SIECI, wiec tez tego
nie widzi. Efekt zlapany recznie 27.10: notka 506-2 przeczyla opublikowanym 499-1 i 499-4,
a zadna bramka nie mogla tego zobaczyc. Tu pytamy DZIENNIKA — w chwili publikacji, na
aktualnym stanie.

JAK (w kolejnosci, kazdy krok tanszy od nastepnego):
  1. KOD wybiera z dziennika z ostatnich 21 dni opublikowane notki powiazane z nowa
     (wspolne slowa tresci i liczby), najwyzej 12. Brak kandydatow = zero wywolan.
  2. FLASH Z MYSLENIEM (`spojnosc`, wysilek `medium`, DWA niezalezne przebiegi, wyniki sie sumuja)
     wskazuje najwyzej trzy pary i CYTUJE obie strony. Dwa przebiegi, bo wykrywanie jest losowe: zmierzone
     na zywo 27.10 — wyrazne sprzecznosci lapie 16/16, ale subtelna („znano od lat” kontra „wykryto
     w sierpniu”) tylko co drugi raz; drugi przebieg podnosi to do ok. trzech na cztery za ok. 0,003 USD.
  3. KOD sprawdza cytaty doslownie — cytat, ktorego nie ma w tekscie, odrzuca znalezisko.
     Model, ktory wymysli sprzecznosc, zostaje tu zlapany bez kosztu.
  4. OPUS (`spojnosc_potwierdz`) dostaje PELNE obie notki i material, z ktorego powstala nowa
     (rekord plus to, co sprawdzenie w sieci powiedzialo o niej przed chwila), i ocenia:
     sprzecznosc, aktualizacja albo zgodnosc, oraz ktora strone popiera material. Przy odmowie
     Opusa (klasyfikatory „cyber” — nasze historie bywaja o lukach) robi to Flash z myslenie,
     a po pierwszej odmowie kolejne potwierdzenia TEGO przebiegu ida od razu do zapasu.

KAZDA ODPOWIEDZ MODELU MUSI MIEC OCZEKIWANY KSZTALT. Poprawny JSON o zlych kluczach (`{}`,
`{"results": ...}`, numeracja od zera, mniej ocen niz par) to NIE „nic nie znaleziono” — to brak
odpowiedzi: potwierdzenie przechodzi do zapasu, a gdy i on zawiedzie, stan to `nie_sprawdzone`.
Puste `{"findings": []}` jest normalna, uczciwa odpowiedzia i oznacza `czysto`.

CO Z WYNIKIEM. To NIE jest bramka (decyzja wlasciciela: nic nie blokuje publikacji). Potwierdzona
sprzecznosc, ktora materialem NIE jest rozstrzygnieta na korzysc nowej notki, idzie do tej samej
naprawy co obalony fakt (`stages.napraw_obalone`, jedna proba) jako zarzut „nasza wlasna notka mowi
inaczej”; naprawiony tekst jest sprawdzany tu jeszcze raz, a w `stages.note` takze w sieci (tekst
czysty w sieci nie moze zostac zamieniony na obalony). Gdy sprzecznosc stoi dalej, notka wychodzi
taka, jaka jest, a dziennik to zapisuje (`fc.spojnosc`). Gdy material popiera NOWA notke, nie
przepisujemy jej wbrew zrodlom — zapis i tyle (to byloby sprostowanie wczesniejszej notki).

CZEGO TO NIE LAPIE. Bledu rozumowania w obrebie jednej notki (prawdziwe fakty, zly wniosek) ani
sprzecznosci z notka, ktora nie weszla do okna kandydatow (inny temat slowami, stare, spoza 21 dni).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
import llm
import stages

SYSTEM = (
    "You compare one new short text with texts we already published and report only real "
    "contradictions, quoting both sides exactly. Return only valid JSON."
)
SYSTEM_POTWIERDZ = (
    "You judge suspected contradictions between a new text and an earlier published text, "
    "strictly and only from the evidence given. Return only valid JSON."
)

_CYTAT_MIN_SLOW = 3
_CYTAT_MAKS_SLOW = 40
_MATERIAL_ZNAKI = 6000          # ile znakow materialu (siec + rekord) widzi potwierdzenie
_WERDYKTY = ("CONTRADICTION", "UPDATE", "CONSISTENT")
_ZNAKI = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                        "–": "-", "—": "-", "−": "-", " ": " "})
_LICZBA = re.compile(r"\d[\d.,]*\d|\d")

# Po pierwszej odmowie Opusa w TYM procesie (jeden przebieg) nastepne potwierdzenia ida od razu do
# zapasu: odmowa klasyfikatora „cyber” dotyczy tematu i powtarzalaby sie przy kazdej notce serii.
_OPUS_ODMOWIL = False


def _norm(tekst: Any) -> str:
    """Tekst do porownan doslownych: male litery, zwykle cudzyslowy i myslniki, jedna spacja."""
    return " ".join(str(tekst or "").translate(_ZNAKI).lower().split())


def _jedna_linia(tekst: Any) -> str:
    return " ".join(str(tekst or "").split())


def _liczby(tekst: Any) -> set[str]:
    """Liczby z tekstu bez separatorow; jednocyfrowe odpadaja (numeracja, „1 of 5”)."""
    out = set()
    for m in _LICZBA.findall(str(tekst or "")):
        n = m.rstrip(".,").replace(",", "")
        if len(n) >= 2:
            out.add(n)
    return out


def _slowa(tekst: Any) -> set[str]:
    import sledztwo                      # leniwie: ciezki modul, a tu liczy sie jeden helper
    return sledztwo._slowa_tresci(tekst)


def _czas(wartosc: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(wartosc))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def wczesniejsze_notki(tekst: str, *, teraz: datetime | None = None,
                       plik: Path | None = None) -> list[dict[str, Any]]:
    """Opublikowane notki z okna dni, najbardziej zwiazane z `tekst`, od najstarszej (E1, E2...).

    Powiazanie = wspolne slowa tresci plus dwa razy wspolne liczby; ponizej progu notka nie jest
    kandydatem. Ta sama tresc co nowa notka (ponowny przebieg) jest pomijana.

    DZIENNIK CZYTAMY PO `\\n`, NIE `splitlines()` i z `errors="replace"`: autor `json.dumps(...,
    ensure_ascii=False)` zostawia U+2028/U+2029/U+0085 nieucieczone, a `splitlines()` rozcialoby
    po nich wiersz (notka znikalaby z kandydatow bez sladu); jeden zly bajt UTF-8 w pliku
    wylaczylby zas cale sprawdzenie dla wszystkich notek.
    """
    plik = plik or (config.DATA_DIR / "dziennik.jsonl")
    teraz = teraz or datetime.now(timezone.utc)
    od = teraz - timedelta(days=config.SPOJNOSC_OKNO_DNI)
    try:
        linie = plik.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return []
    moje_slowa, moje_liczby, moja_tresc = _slowa(tekst), _liczby(tekst), _norm(tekst)
    widziane: set[str] = set()
    kandydaci: list[dict[str, Any]] = []
    for linia in linie:
        linia = linia.strip()
        if not linia:
            continue
        try:
            w = json.loads(linia)
        except ValueError:
            continue
        if not isinstance(w, dict) or w.get("rodzaj") != "notka" or not w.get("udane"):
            continue
        cudza = _jedna_linia(w.get("tekst"))
        kiedy = _czas(w.get("kiedy"))
        if not cudza or kiedy is None or kiedy < od or kiedy > teraz:
            continue
        tresc = _norm(cudza)
        if tresc == moja_tresc or tresc in widziane:
            continue
        widziane.add(tresc)
        wynik = (len(moje_slowa & _slowa(cudza))
                 + 2 * len(moje_liczby & _liczby(cudza)))
        if wynik < config.SPOJNOSC_MIN_WSPOLNYCH:
            continue
        kandydaci.append({"kiedy": kiedy, "tekst": cudza, "wynik": wynik})
    kandydaci.sort(key=lambda k: (-k["wynik"], -k["kiedy"].timestamp()))
    wybrane = sorted(kandydaci[:config.SPOJNOSC_KANDYDATOW], key=lambda k: k["kiedy"])
    for i, k in enumerate(wybrane, 1):
        k["nr"] = "E%d" % i
    return wybrane


def _cytat_w_tekscie(zrodlo: str, cytat: Any) -> str:
    """Cytat modelu, gdy stoi w `zrodlo` doslownie (z dokladnoscia do wielkosci liter, cudzyslowow
    i spacji) i ma 3-40 slow; inaczej pusty napis."""
    c = _norm(cytat).strip(" \"'.…")
    slow = len(c.split())
    if not (_CYTAT_MIN_SLOW <= slow <= _CYTAT_MAKS_SLOW) or c not in _norm(zrodlo):
        return ""
    return _jedna_linia(cytat).strip(" \"'“”")


def material_z_audytu(audyt: dict[str, Any] | None, kontekst: str) -> str:
    """Material dla potwierdzenia: NAJPIERW to, co sprawdzenie w sieci powiedzialo o nowej notce
    przed chwila (krotki blok, nie ucinany), potem rekord, z ktorego notka powstala.

    Bez tego Opus ocenia „kto ma racje” po samym rekordzie, a zdanie notki, ktore siec wlasnie
    POTWIERDZILA, wygladalo dla niego na niepoparte i szlo do naprawy w strone starszej notki."""
    linie = []
    for c in ((audyt or {}).get("claims") or [])[:8]:
        if isinstance(c, dict) and c.get("claim"):
            linie.append("- [%s] %s%s" % (
                stages._status_twierdzenia(c), _jedna_linia(c.get("claim"))[:160],
                (" — " + _jedna_linia(c.get("what_the_source_says"))[:200]) if c.get("what_the_source_says") else ""))
    blok = ("WEB FACT-CHECK OF THE NEW NOTE (run just now against sources; status per claim):\n"
            + "\n".join(linie) + "\n\n") if linie else ""
    return blok + str(kontekst or "")


def _ta_sama_para(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Ta sama sprzecznosc podana dwa razy: ta sama wczesniejsza notka i cytat nowej strony, ktory jest
    fragmentem drugiego (model raz cytuje zdanie, raz jego poczatek). Dwa ROZNE zdania nowej notki
    zderzone z ta sama wczesniejsza notka to dwie sprawy."""
    if a["nr"] != b["nr"]:
        return False
    na, nb = _norm(a["nowy_cytat"]), _norm(b["nowy_cytat"])
    return na in nb or nb in na


def _wykryj(conn, run_id: int, tekst: str, kandydaci: list[dict[str, Any]],
            dzis: str) -> tuple[list[dict[str, Any]], int]:
    """(znaleziska z cytatami potwierdzonymi kodem, ile odrzucono za cytat spoza tekstu).

    Rzuca `ValueError`, gdy odpowiedz nie ma listy `findings` — brak klucza to nie to samo co pusta lista."""
    wczesniejsze = "\n\n".join(
        "[%s | %s]\n%s" % (k["nr"], k["kiedy"].strftime("%Y-%m-%d"), k["tekst"][:900]) for k in kandydaci)
    nowa = _jedna_linia(tekst)
    prompt = stages._prompt("spojnosc.md", nowa=nowa[:1500], wczesniejsze=wczesniejsze,
                            maks=config.SPOJNOSC_MAKS_PAR, dzis=dzis)
    dane = llm.parse_json(llm.call("spojnosc", SYSTEM, prompt, conn=conn, run_id=run_id))
    lista = dane.get("findings") if isinstance(dane, dict) else None
    if not isinstance(lista, list):
        raise ValueError("odpowiedz bez listy `findings`")
    po_nr = {k["nr"]: k for k in kandydaci}
    znalezione: list[dict[str, Any]] = []
    odrzucone = 0
    for x in lista[:2 * config.SPOJNOSC_MAKS_PAR]:
        k = po_nr.get(str(x.get("id") or "").strip().upper()) if isinstance(x, dict) else None
        nowy = _cytat_w_tekscie(nowa, x.get("new_quote")) if k else ""
        stary = _cytat_w_tekscie(k["tekst"], x.get("earlier_quote")) if k else ""
        if not (k and nowy and stary):
            odrzucone += 1
            continue
        para = {"nr": k["nr"], "kiedy": k["kiedy"].strftime("%Y-%m-%d"),
                "nowy_cytat": nowy, "wczesniejszy_cytat": stary,
                "wczesniejsza_pelna": k["tekst"], "dlaczego": _jedna_linia(x.get("why"))[:200]}
        if not any(_ta_sama_para(para, juz) for juz in znalezione):   # powtorka nie zjada miejsca innej pary
            znalezione.append(para)
    return znalezione, odrzucone


def _oceny(dane: Any, ile: int) -> list[dict[str, str]]:
    """Oceny w kolejnosci par. Rzuca `ValueError`, gdy odpowiedz jest bezuzyteczna: brak listy `pairs`,
    para bez oceny (zly albo brakujacy numer, numeracja od zera, mniej wpisow niz par) albo werdykt
    spoza trzech dozwolonych. Nieznane `supported_by` to NEITHER (material nie rozstrzyga)."""
    lista = dane.get("pairs") if isinstance(dane, dict) else None
    if not isinstance(lista, list):
        raise ValueError("odpowiedz bez listy `pairs`")
    oceny: list[dict[str, str]] = [{} for _ in range(ile)]
    for x in lista:
        if not isinstance(x, dict):
            continue
        m = re.search(r"\d+", str(x.get("n")))
        werdykt = str(x.get("verdict") or "").strip().upper()
        if not m or werdykt not in _WERDYKTY or not 1 <= int(m.group()) <= ile or oceny[int(m.group()) - 1]:
            continue
        popiera = str(x.get("supported_by") or "").strip().upper()
        oceny[int(m.group()) - 1] = {"werdykt": werdykt,
                                      "popiera": popiera if popiera in ("NEW", "EARLIER", "NEITHER") else "NEITHER",
                                      "dlaczego": _jedna_linia(x.get("why"))[:200]}
    if not all(oceny):
        raise ValueError("pary bez oceny: %s" % [i + 1 for i, o in enumerate(oceny) if not o])
    return oceny


def _potwierdz(conn, run_id: int, tekst: str, znalezione: list[dict[str, Any]], dowod: str,
               dzis: str) -> tuple[list[dict[str, str]], str]:
    """(oceny w kolejnosci znalezisk, kto ocenial: „opus” albo „zapas”). Rzuca, gdy zawiodly oba."""
    global _OPUS_ODMOWIL
    pary = "\n\n".join(
        "PAIR %d\nEARLIER NOTE (%s, published %s):\n%s\nSENTENCE IN THE NEW NOTE: \"%s\"\nSENTENCE IN THE EARLIER NOTE: \"%s\""
        % (i, z["nr"], z["kiedy"], z["wczesniejsza_pelna"][:900], z["nowy_cytat"], z["wczesniejszy_cytat"])
        for i, z in enumerate(znalezione, 1))
    prompt = stages._prompt("spojnosc_potwierdz.md", dowod=(dowod or "(none)")[:_MATERIAL_ZNAKI],
                            nowa=_jedna_linia(tekst)[:1500], pary=pary, dzis=dzis)
    oceny, kto = None, "opus"
    if not _OPUS_ODMOWIL:
        try:
            oceny = _oceny(llm.parse_json(llm.call("spojnosc_potwierdz", SYSTEM_POTWIERDZ, prompt,
                                                   conn=conn, run_id=run_id)), len(znalezione))
        except stages.PRZERYWAJA:
            raise
        except Exception as exc:                                # noqa: BLE001
            # Odmowa Opusa (klasyfikator „cyber”), zly JSON, odpowiedz w zlym ksztalcie, timeout:
            # te sama prace robi Flash z myslenie.
            _OPUS_ODMOWIL = _OPUS_ODMOWIL or isinstance(exc, llm.OdmowaDostawcy)
            print("    [spojnosc] potwierdzenie Opusa nie wyszlo (%s) — robi to Flash"
                  % type(exc).__name__, flush=True)
    if oceny is None:
        kto = "zapas"
        oceny = _oceny(llm.parse_json(llm.call("spojnosc_potwierdz_zapas", SYSTEM_POTWIERDZ, prompt,
                                               conn=conn, run_id=run_id)), len(znalezione))
    return oceny, kto


@stages._na_kanal("notka")
def sprawdz(conn, run_id: int, tekst: str, dowod: str = "", *, teraz: datetime | None = None,
            plik: Path | None = None) -> dict[str, Any]:
    """Wynik sprawdzenia `tekst` wobec dziennika. NIGDY nie rzuca, poza stanem konta (`PRZERYWAJA`).

    `dowod` = material z `material_z_audytu`. `stan`: wylaczone | brak_kandydatow | czysto |
    nowa_lepsza | sprzecznosc | nie_sprawdzone. `sprzecznosci` = potwierdzone, a nie rozstrzygniete
    na korzysc nowej notki (do naprawy); `nowa_lepsza` = potwierdzone, ale material popiera nowa notke.
    """
    wynik: dict[str, Any] = {"stan": "wylaczone", "kandydatow": 0, "znalezione": 0, "przebiegi": 0,
                             "cytaty_odrzucone": 0, "sprzecznosci": [], "nowa_lepsza": [],
                             "potwierdzil": ""}
    if not config.SPOJNOSC_Z_DZIENNIKIEM or not str(tekst or "").strip():
        return wynik
    dzis = (teraz or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    try:
        kandydaci = wczesniejsze_notki(tekst, teraz=teraz, plik=plik)
        wynik["kandydatow"] = len(kandydaci)
        if not kandydaci:
            wynik["stan"] = "brak_kandydatow"
            return wynik
        znalezione, odrzucone, ostatni_blad = [], 0, None
        for _ in range(max(1, int(config.SPOJNOSC_PRZEBIEGI))):
            try:
                z, o = _wykryj(conn, run_id, tekst, kandydaci, dzis)
            except stages.PRZERYWAJA:
                raise
            except Exception as exc:                                # noqa: BLE001
                ostatni_blad = exc
                print("    [spojnosc] przebieg wykrywania %d nie wyszedl (%s)" % (wynik["przebiegi"] + 1, type(exc).__name__),
                      flush=True)
                continue
            wynik["przebiegi"] += 1
            odrzucone += o
            znalezione += [p for p in z if not any(_ta_sama_para(p, juz) for juz in znalezione)]
            if len(znalezione) >= config.SPOJNOSC_MAKS_PAR:
                break                                               # komplet: drugi przebieg niczego nie doda
        if not wynik["przebiegi"]:
            raise ostatni_blad                                      # ani jeden przebieg nie dal uzytecznej odpowiedzi
        znalezione = znalezione[:config.SPOJNOSC_MAKS_PAR]
        wynik["znalezione"], wynik["cytaty_odrzucone"] = len(znalezione), odrzucone
        if odrzucone:
            print("    [spojnosc] %d znalezisk odrzuconych: cytat spoza tekstu" % odrzucone, flush=True)
        if not znalezione:
            wynik["stan"] = "czysto"
            return wynik
        oceny, wynik["potwierdzil"] = _potwierdz(conn, run_id, tekst, znalezione, dowod, dzis)
        for z, o in zip(znalezione, oceny):
            if o["werdykt"] != "CONTRADICTION":
                continue
            pelne = {"nr": z["nr"], "kiedy": z["kiedy"], "nowy_cytat": z["nowy_cytat"],
                     "wczesniejszy_cytat": z["wczesniejszy_cytat"], "werdykt": o["werdykt"],
                     "popiera": o["popiera"], "dlaczego": o["dlaczego"] or z["dlaczego"]}
            (wynik["nowa_lepsza"] if o["popiera"] == "NEW" else wynik["sprzecznosci"]).append(pelne)
        wynik["stan"] = ("sprzecznosc" if wynik["sprzecznosci"]
                         else "nowa_lepsza" if wynik["nowa_lepsza"] else "czysto")
        for s in wynik["sprzecznosci"] + wynik["nowa_lepsza"]:
            print("    [spojnosc] %s z %s (%s): \"%s\" vs \"%s\"" % (
                "SPRZECZNOSC" if s in wynik["sprzecznosci"] else "sprzecznosc, materialem wygrywa nowa",
                s["nr"], s["kiedy"], s["nowy_cytat"][:70], s["wczesniejszy_cytat"][:70]), flush=True)
        return wynik
    except stages.PRZERYWAJA:
        raise
    except Exception as exc:                                    # noqa: BLE001
        # „NIE SPRAWDZILEM” TO NIE „CZYSTO” — stan mowi to wprost, tak jak `nie_sprawdzone` przy faktach.
        print("    [spojnosc] nie sprawdzone (%s: %s) — notka idzie dalej"
              % (type(exc).__name__, str(exc)[:80]), flush=True)
        wynik["stan"] = "nie_sprawdzone"
        wynik["sprzecznosci"], wynik["nowa_lepsza"] = [], []
        return wynik


def jako_zarzuty(sprzecznosci: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sprzecznosci w ksztalcie zarzutow sprawdzenia faktow — material dla `stages.napraw_obalone`."""
    return [{
        "claim": s["nowy_cytat"],
        "status": "refuted",
        "what_the_source_says": (
            "OUR OWN NOTE, already published on %s, says: \"%s\". The sentence above says the opposite "
            "or cannot stand beside it (%s). Correct the sentence so that it agrees with what we "
            "already published, and keep its point." % (s["kiedy"], s["wczesniejszy_cytat"],
                                                       s.get("dlaczego") or "contradiction")),
        "url": "our earlier note, %s" % s["kiedy"],
    } for s in sprzecznosci]


def skrot(sp: dict[str, Any]) -> dict[str, Any]:
    """Zapis do dziennika (`fc.spojnosc`): liczby i znaczniki plus, gdy cos znaleziono, krotkie
    cytaty (do trzech) — zeby dalo sie przeczytac, CO i Z KTORA notka sie zderzylo."""
    szczegoly = [{"rodzaj": rodzaj, "kiedy": str(s.get("kiedy") or ""), "popiera": str(s.get("popiera") or ""),
                  "nowy": str(s.get("nowy_cytat") or "")[:160], "wczesniejszy": str(s.get("wczesniejszy_cytat") or "")[:160]}
                 for rodzaj, lista in (("sprzecznosc", sp.get("sprzecznosci")), ("nowa_lepsza", sp.get("nowa_lepsza")))
                 for s in (lista or [])][:3]
    out = {"stan": str(sp.get("stan") or ""),
           "kandydatow": int(sp.get("kandydatow") or 0),
           "znalezione": int(sp.get("znalezione") or 0),
           "cytaty_odrzucone": int(sp.get("cytaty_odrzucone") or 0),
           "przebiegi": int(sp.get("przebiegi") or 0),
           "sprzecznosci": len(sp.get("sprzecznosci") or []),
           "nowa_lepsza": len(sp.get("nowa_lepsza") or []),
           "naprawiona": bool(sp.get("naprawiona")),
           "stoi": bool(sp.get("stoi")),
           "naprawa_odrzucona": bool(sp.get("naprawa_odrzucona")),
           "powod_odrzucenia": str(sp.get("powod_odrzucenia") or ""),
           "potwierdzil": str(sp.get("potwierdzil") or "")}
    if szczegoly:
        out["szczegoly"] = szczegoly
    return out
