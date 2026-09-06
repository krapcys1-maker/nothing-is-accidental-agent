# -*- coding: utf-8 -*-
"""SERIE TEMATYCZNE — kilka notek o jednym temacie, w kolejnych dobach.

PO CO TO ISTNIEJE. Zmierzone 6 września 2026 na żywej produkcji:

    artykuł      7 subskrypcji
    notka        0
    komentarz    0
    odpowiedź    0

Notki robią zasięg (32,6 wyświetlenia średnio, zero pozycji z zerem), który
NIE PROWADZI DONIKĄD. Powód jest prosty: pojedyncza notka nie daje nikomu
powodu, żeby wrócić. „Część 2 jutro" — daje. To jedyny mechanizm, jakiego to
konto nie próbowało, a który uderza dokładnie w tę zmierzoną słabość.

Drugi pomiar z tego samego dnia mówi, gdzie szukać skutku. Notki bez zaczepu
w bieżącym mają MNIEJ wyświetleń niż newsowe (27,4 wobec 38,8), ale WIĘCEJ
odwiedzin profilu (0,61 wobec 0,50) — a odwiedziny profilu to jedyny sygnał
kroku PRZED subskrypcją, jaki panel Substacka nam oddaje. Miary rozchodzą się
w przeciwne strony, więc serię trzeba oceniać po odwiedzinach i subskrypcjach,
NIE po polubieniach: audyt z 3 września wykazał, że reakcje nie odróżniają
dobrej notki od bełkotu (3,2 wobec 3,0 wobec 3,1 — płasko).

JAK TEMAT JEST WYBIERANY — i dlaczego NIE z góry. Pierwsza wersja tego modułu
miała brać temat z listy i czekać, aż bank dostarczy materiał. Zmierzone na
żywym banku (129 wolnych faktów): temat wybrany z góry potrafi nie mieć ANI
JEDNEGO pasującego faktu, a seria czekałaby w nieskończoność albo — gorzej —
wydałaby część nie na temat. Więc jest odwrotnie: **liczy się bank, a temat
wybiera ten, który bank naprawdę wyżywi.** Dziś to „Prąd i data centre"
(4 fakty powyżej progu); „AI w szkole" i „AI w medycynie" mają po jednym
i serii nie dostaną, dopóki materiał nie przyjdzie.

DLACZEGO PRÓG WYNOSI PIĘĆ. Punktowanie sprawdziłem na treści, nie na liczbach
— bo poprzednia próba (luźne słowa kluczowe) dawała ładne liczby i bezsensowne
przykłady: „AI w pracy" trafiało w aukcję upadłościową Spirit Airlines, cztery
razy z rzędu, każdy raz za dokładnie 3 punkty. Przy progu 5 wszystkie cztery
odpadają, a wszystko, co naprawdę jest na temat, zostaje. Progi 4, 5 i 6 dają
identyczny wynik — to płaskowyż, więc cięcie nie jest czułe na dokładną
wartość i nie dobrałem go pod jeden zbiór.

DLACZEGO TRAFIENIE W `domain` LICZY TRZY RAZY TYLE. `domain` to własna
etykieta banku, nadawana przez model przy zapisie faktu. Ma 127 różnych
wartości na 131 faktów, więc jako KATEGORIA jest bezużyteczna — ale jako OPIS
tematu jest mocniejsza niż samo zdanie faktu: „face recognition and your
child's classroom" mówi o szkole wprost, a treść faktu wspomina o niej raz.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any

import config

PLIK = config.DATA_DIR / "seria.json"

# ILE CZĘŚCI. Cztery, nie pięć i nie trzy. Trzy to za mało, żeby czytelnik
# zdążył zauważyć, że to seria; przy pięciu bank dziś nie wyżywiłby ani
# jednego tematu (przy czterech wyżywia dokładnie jeden).
ILE_CZESCI = 4

# PRÓG DOPASOWANIA — patrz nagłówek modułu. Jedno trafienie w `domain` (3 pkt)
# NIE wystarcza samo z siebie; potrzeba go plus czegoś w treści, albo pięciu
# trafień w samej treści.
PROG_DOPASOWANIA = 5

# ETYKIETY DLA CZYTELNIKA — po angielsku, bo notki są po angielsku
# (`config.ARTICLE_LANGUAGE`). Klucze `TEMATY` są po polsku, bo są dla nas:
# stoją w logu, w stanie i w tym pliku. Znacznik pod notką musi być w języku
# notki — polski tytuł serii pod angielskim tekstem byłby jedyną rzeczą na
# całym profilu, która zdradza, kto to pisze i skąd.
ETYKIETY: dict[str, str] = {
    "AI w szkole": "AI in the classroom",
    "AI w pracy": "AI and the job",
    "AI w medycynie": "AI in the clinic",
    "Prad i data centre": "Where the electricity goes",
    "Prawo i sady": "AI in court",
    "Kto na tym zarabia": "Who is actually paid",
}

# TEMATY. To NIE jest plan wydawniczy — to lista tego, co w ogóle wolno uznać
# za temat serii. Który z nich pójdzie, decyduje bank (patrz `mozliwe`).
#
# Terminy są po angielsku, bo bank jest po angielsku (`ARTICLE_LANGUAGE`).
# Formy mnogie wypisane osobno, bo dopasowanie idzie po przedrostku (`\bjob`
# złapałoby `jobs`, ale `\bstudent` nie złapie `pupils`) — a zgadywanie
# odmiany regeksem to dokładnie ten rodzaj sprytu, który potem cicho nie
# działa.
TEMATY: dict[str, tuple[str, ...]] = {
    "AI w szkole": (
        "student", "students", "school", "schools", "classroom", "teacher",
        "teachers", "teaching", "education", "educational", "university",
        "universities", "exam", "exams", "homework", "coursework", "campus",
        "pupil", "pupils", "tutor", "tutoring", "curriculum",
    ),
    "AI w pracy": (
        "job", "jobs", "worker", "workers", "employee", "employees",
        "employer", "employers", "hiring", "hired", "layoff", "layoffs",
        "salary", "salaries", "wages", "workforce", "freelancer",
        "freelance", "contractor", "contractors", "recruiter", "recruiting",
        "white-collar", "entry-level", "headcount", "staffing",
    ),
    "AI w medycynie": (
        "patient", "patients", "doctor", "doctors", "clinical", "clinician",
        "diagnosis", "diagnostic", "hospital", "hospitals", "medical",
        "medicine", "drug", "drugs", "clinical trial", "screening",
        "radiology", "radiologist", "oncology", "therapy", "disease",
    ),
    "Prad i data centre": (
        "data centre", "data centres", "data center", "data centers",
        "datacentre", "datacenter", "electricity", "power grid", "grid",
        "megawatt", "megawatts", "gigawatt", "gigawatts", "cooling",
        "water use", "emissions", "carbon", "nuclear", "energy",
    ),
    "Prawo i sady": (
        "lawsuit", "lawsuits", "court", "courts", "judge", "ruling",
        "rulings", "settlement", "copyright", "licensing", "regulation",
        "regulator", "regulators", "ai act", "legislation", "congress",
        "plaintiff", "plaintiffs", "sued", "injunction", "antitrust",
    ),
    "Kto na tym zarabia": (
        "revenue", "valuation", "funding", "raised", "investor", "investors",
        "profit", "profitable", "margin", "margins", "burn rate",
        "subscription", "subscriptions", "pricing", "price per", "billing",
        "ipo", "acquisition", "acquired",
    ),
}


def _dzis() -> str:
    """Doba w UTC. Ta sama podstawa, co przy wyborze pisarza w `stages.py`."""
    return datetime.now(timezone.utc).date().isoformat()


def _klucz(tekst: Any) -> str:
    """Postać faktu, po której wolno porównywać — po OBU stronach ta sama.

    ZLAPANE TESTEM, NIE ROZUMOWANIEM. Stan zapisuje tekst faktu OBCIETY do 200
    znakow (żeby plik nie puchł), a porównanie szło z PELNYM tekstem z banku —
    więc nigdy się nie zgadzały i część 2 wzięła dokładnie ten sam fakt, co
    część 1. Na produkcji wada byłaby częściowo zamaskowana, bo opublikowany
    fakt znika z banku przez `oznacz_uzyty` — ale zamaskowana to nie naprawiona:
    wystarczyłaby jedna nieudana publikacja, po której fakt wraca do puli.

    Dlatego klucz liczą OBIE strony tak samo: białe znaki znormalizowane,
    małe litery, dopiero potem obcięcie.
    """
    return " ".join(str(tekst or "").split()).lower()[:200]


def punkty(fakt: dict[str, Any], terminy: tuple[str, ...] | list[str]) -> int:
    """Ile temat pasuje do faktu. Trafienie w `domain` liczy 3, w treść 1.

    Liczone po ROŻNYCH terminach, nie po wystąpieniach — inaczej fakt, który
    dwadzieścia razy powtarza słowo `grid`, wygrywałby z faktem naprawdę
    o sieci energetycznej.
    """
    if not isinstance(fakt, dict):
        return 0
    dom = str(fakt.get("domain") or "").lower()
    tresc = " ".join(
        str(fakt.get(k) or "")
        for k in ("fact", "consequence", "wrong_belief", "actually")
    ).lower()
    suma = 0
    for t in terminy:
        wzorzec = r"\b%s" % re.escape(str(t).lower())
        if re.search(wzorzec, dom):
            suma += 3
        elif re.search(wzorzec, tresc):
            suma += 1
    return suma


def zdatne(zapas: list[dict[str, Any]], temat: str) -> list[tuple[int, dict[str, Any]]]:
    """Fakty na dany temat, od najlepiej dopasowanego, powyżej progu."""
    terminy = TEMATY.get(temat)
    if not terminy:
        return []
    oceny = [(punkty(f, terminy), f) for f in zapas if isinstance(f, dict)]
    return sorted((p for p in oceny if p[0] >= PROG_DOPASOWANIA),
                  key=lambda x: -x[0])


def mozliwe(zapas: list[dict[str, Any]], pomijaj: list[str] | None = None
            ) -> list[tuple[str, int]]:
    """Tematy, które ten bank wyżywi na CAŁĄ serię — od najlepiej zaopatrzonego.

    `pomijaj` to tematy zrobione niedawno: seria po serii o tym samym byłaby
    tym samym, czym jest dziś ciąg notek newsowych, tylko węższym.
    """
    omijane = set(pomijaj or ())
    wynik = []
    for temat in TEMATY:
        if temat in omijane:
            continue
        ile = len(zdatne(zapas, temat))
        if ile >= ILE_CZESCI:
            wynik.append((temat, ile))
    return sorted(wynik, key=lambda x: -x[1])


def _pusty() -> dict[str, Any]:
    return {"aktywna": None, "skonczone": []}


def stan() -> dict[str, Any]:
    """Cały zapis o seriach. Uszkodzony plik czytamy jako pusty, nie jako błąd.

    Ta sama zasada co przy banku (`_zapisz_indeks`): przebieg ubity w trakcie
    zapisu nie ma prawa zatrzymać notek na drugi dzień.
    """
    try:
        d = json.loads(PLIK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _pusty()
    if not isinstance(d, dict):
        return _pusty()
    d.setdefault("aktywna", None)
    d.setdefault("skonczone", [])
    return d


def _zapisz(d: dict[str, Any]) -> None:
    """Zapis atomowy z jedną kopią — dokładnie jak `_zapisz_indeks`.

    Bank raz już zniknął w całości przez zwykły `write_text`, który obcina plik
    i dopiero pisze. Tu w grze jest mniej, ale wada byłaby ta sama: przerwana
    seria bez śladu, po której nie da się powiedzieć, czy część 3 poszła.
    """
    PLIK.parent.mkdir(parents=True, exist_ok=True)
    if PLIK.exists():
        try:
            shutil.copy2(PLIK, PLIK.with_suffix(".json.kopia"))
        except OSError:
            pass
    tmp = PLIK.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PLIK)


def aktywna() -> dict[str, Any] | None:
    """Seria w toku, albo None. Skończona seria NIE jest aktywna."""
    a = stan().get("aktywna")
    if not isinstance(a, dict):
        return None
    if len(a.get("wydane") or []) >= int(a.get("czesci") or ILE_CZESCI):
        return None
    return a


def czesc_na_dzis(a: dict[str, Any] | None = None) -> int | None:
    """Numer części do wydania dziś (1..N), albo None.

    JEDNA CZĘŚĆ NA DOBĘ i to jest cały sens. Sześć przebiegów na dobę wydałoby
    całą serię przed obiadem, a wtedy „część 2 jutro" nie znaczy nic — czytelnik
    dostaje cztery notki naraz i nie ma po co wracać. Dlatego bramką jest DOBA
    ostatniej wydanej części, nie licznik w przebiegu.
    """
    a = a if a is not None else aktywna()
    if not a:
        return None
    wydane = a.get("wydane") or []
    if any((w or {}).get("doba") == _dzis() for w in wydane):
        return None
    return len(wydane) + 1


def propozycja(zapas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Część serii do napisania TERAZ — albo None. NIE ZAPISUJE NICZEGO.

    DLACZEGO NIC NIE ZAPISUJE. Stan zmienia się w tym module wyłącznie po
    potwierdzonej publikacji (`zapisz_czesc`), bo tak działa cała reszta konta:
    fakt odhacza się po `wyslane`, dzień promocji artykułu też. Gdyby seria
    zaczynała się już przy pisaniu, sprawdzenie na sucho albo przebieg bez
    `--wyslij` zaczynałby PRAWDZIWĄ serię, a pierwsza część nigdy by nie
    wyszła — czytelnik dostałby serię zaczynającą się od części drugiej.

    Wywołanie ZDEJMUJE wybrany fakt z `zapas`, tak samo jak `wybierz_material`,
    żeby ten sam materiał nie wyszedł drugi raz tego samego dnia.
    """
    a = aktywna()
    if a is None:
        # Żadna nie trwa — czy bank wyżywi nową? Temat wybiera BANK, nie plan.
        d = stan()
        ostatnie = [s.get("temat") for s in (d.get("skonczone") or [])][-2:]
        kandydaci = mozliwe(zapas, pomijaj=ostatnie)
        if not kandydaci:
            return None
        temat, ile = kandydaci[0]
        a = {"temat": temat, "czesci": ILE_CZESCI, "faktow_na_start": ile,
             "wydane": []}
    czesc = czesc_na_dzis(a)
    if czesc is None:
        return None
    fakt = wybierz_fakt(zapas, str(a.get("temat") or ""),
                        unikaj_faktow=[str((w or {}).get("fakt_klucz") or "")
                                       for w in (a.get("wydane") or [])])
    if fakt is None:
        # Seria CZEKA. Część nie na temat byłaby gorsza niż przerwa: przerwę
        # czytelnik przeoczy, notkę nie na temat przeczyta i seria przestaje
        # być serią.
        print("  [seria] \"%s\" część %d czeka — bank nie ma dziś nic na ten"
              " temat" % (a.get("temat"), czesc), flush=True)
        return None
    return {"temat": a.get("temat"), "czesc": czesc, "fakt": fakt,
            "kontekst": kontekst(czesc, a)}


def wybierz_fakt(zapas: list[dict[str, Any]], temat: str,
                 unikaj_faktow: list[str] | None = None
                 ) -> dict[str, Any] | None:
    """Najlepiej dopasowany fakt na temat serii — ZDJĘTY z zapasu.

    Zdejmowanie jest po to samo, co w `wybierz_material`: fakt wzięty przez
    serię nie może potem wyjść drugi raz jako zwykła notka tego samego dnia.

    Gdy nic nie pasuje, oddaje None i seria CZEKA. Część nie na temat byłaby
    gorsza niż przerwa: przerwę czytelnik przeoczy, notkę nie na temat
    przeczyta i seria przestaje być serią.
    """
    juz = {_klucz(t) for t in (unikaj_faktow or ()) if _klucz(t)}
    for _p, f in zdatne(zapas, temat):
        if _klucz(f.get("fact")) in juz:
            continue
        try:
            zapas.remove(f)
        except ValueError:
            pass
        return f
    return None


def zapisz_czesc(temat: str, czesc: int, id_notki: str | None,
                 otwarcie: str = "", fakt: str = "") -> None:
    """Zapisuje, że część NAPRAWDĘ poszła w świat. Zakłada serię, gdy trzeba.

    Wołane dopiero po udanej publikacji, nie po napisaniu — tak samo jak
    odhaczanie dnia promocji artykułu. Wystarczyło, że kandydat przeszedł
    bramkę, i nieudana publikacja po cichu zjadała jeden z pięciu dni promocji;
    tutaj zjadałaby część serii, a czytelnik dostałby część 1, 2 i 4.
    """
    d = stan()
    a = d.get("aktywna")
    if not isinstance(a, dict):
        # Pierwsza część zakłada serię — patrz `propozycja`, która celowo nie
        # zapisuje nic, dopóki notka nie wyszła w świat.
        if int(czesc) != 1:
            print("  [seria] część %d bez trwającej serii — nie zapisuję"
                  % czesc, flush=True)
            return
        a = {"temat": temat, "czesci": ILE_CZESCI, "zaczeta": _dzis(),
             "wydane": []}
        d["aktywna"] = a
        print("  [seria] zaczynam serię \"%s\" — %d części"
              % (temat, ILE_CZESCI), flush=True)
    elif str(a.get("temat") or "") != str(temat):
        # Temat się rozjechał — trwa inna seria. Cicha podmiana zrobiłaby
        # z dwóch serii jedną poszatkowaną.
        print("  [seria] część \"%s\" nie pasuje do trwającej \"%s\" —"
              " nie zapisuję" % (temat, a.get("temat")), flush=True)
        return
    wydane = a.setdefault("wydane", [])
    if any(int((w or {}).get("czesc") or 0) == int(czesc) for w in wydane):
        return
    wydane.append({
        "czesc": int(czesc),
        "id": str(id_notki) if id_notki else None,
        "doba": _dzis(),
        "kiedy": datetime.now(timezone.utc).isoformat(),
        "otwarcie": (otwarcie or "")[:160],
        # DWA POLA Z JEDNEGO FAKTU, i to nie jest nadmiar. `fakt` jest
        # CZYTELNY i idzie do promptu nastepnej czesci; `fakt_klucz` jest
        # POROWNYWALNY i sluzy tylko do tego, zeby ten sam material nie wyszedl
        # drugi raz. Jedno pole do obu rzeczy juz raz zawiodlo — patrz `_klucz`.
        "fakt": (fakt or "")[:200],
        "fakt_klucz": _klucz(fakt),
    })
    if len(wydane) >= int(a.get("czesci") or ILE_CZESCI):
        a["skonczona"] = _dzis()
        d.setdefault("skonczone", []).append(a)
        d["aktywna"] = None
        print("  [seria] seria \"%s\" skończona — %d części"
              % (a.get("temat"), len(wydane)), flush=True)
    _zapisz(d)


def kontekst(czesc: int, seria: dict[str, Any] | None = None
             ) -> dict[str, Any] | None:
    """To, co pisarz musi wiedzieć, żeby napisać CZĘŚĆ, a nie osobną notkę."""
    a = seria if seria is not None else aktywna()
    if not a:
        return None
    wydane = a.get("wydane") or []
    _temat = str(a.get("temat") or "")
    return {
        "temat": _temat,
        # ETYKIETA, NIE KLUCZ — to ona idzie pod notkę, patrz `ETYKIETY`.
        # Gdy tematu nie ma w tabeli (bo ktoś dopisał go do `TEMATY` i zapomniał
        # o etykiecie), lepszy jest klucz niż pusty znacznik: czytelnik zobaczy
        # dziwny napis, a nie notkę udającą, że nie jest częścią serii.
        "etykieta": ETYKIETY.get(_temat, _temat),
        "czesc": int(czesc),
        "ile_czesci": int(a.get("czesci") or ILE_CZESCI),
        "ostatnia": bool(int(czesc) >= int(a.get("czesci") or ILE_CZESCI)),
        "poprzednie_otwarcia": [str((w or {}).get("otwarcie") or "")
                                for w in wydane if (w or {}).get("otwarcie")],
        "poprzednie_fakty": [str((w or {}).get("fakt") or "")
                             for w in wydane if (w or {}).get("fakt")],
    }
