# -*- coding: utf-8 -*-
"""E21 — pamiec rozmowcy (29.09.2026): czy dziala, trafia do promptu i jest mierzona.

Wlasciciel: „mozesz wprowadzic to jako eksperyment plus zrobic monitoring tego,
jak sie zachowuje". Test pilnuje, z kontrdowodami:
  1. `stages.pamiec_rozmowcy` sklada pamiec z WLASNEGO dziennika, bez modelu:
     tylko udane rozmowy z ta osoba z ostatnich 60 dni, najwyzej 3, przyciete,
     z reakcjami z pomiaru i z tym, czy nas obserwuje;
  2. blok trafia do promptu komentarza i odpowiedzi tylko, gdy go podano;
  3. `run.pamiec_do_celu`: ramie tylko przy wczesniejszym kontakcie, „off" nie
     dostaje pamieci, awaria pamieci nie zatrzymuje komentarza;
  4. pola dziennika: ramie, `pamiec_wymian` (takze 0), uchwyt przy odpowiedzi;
  5. monitoring: `eksperymenty.raport_pamieci` i alarm `pamiec_rozmowcow`.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium.
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

KATALOG = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KATALOG)

import alarm          # noqa: E402
import eksperymenty   # noqa: E402
import llm            # noqa: E402
import run            # noqa: E402
import stages         # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def zapisz(nazwa, wiersze):
    (KATALOG / nazwa).write_text("".join(json.dumps(w) + "\n" for w in wiersze), encoding="utf-8")
    stages._PAMIEC_ZAPAS.clear()


TERAZ = datetime.now(timezone.utc)


def dni_temu(d, godz=10):
    return (TERAZ - timedelta(days=d)).replace(hour=godz, minute=0, second=0, microsecond=0).isoformat()


DLUGI = ("Inference is now most of the AI bill, and the price cuts this year came from batching "
         "requests and routing easy questions to a smaller model, which only saves money if the "
         "router can tell easy from hard cheaply and reliably every single time.")
DZIENNIK = [
    {"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(90), "komu": "alice", "tekst": "BARDZO STARY"},
    {"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(10), "komu": "alice", "publikacja": "Alice Weekly",
     "tekst": DLUGI, "nasz_id": "c1", "pod": "artykul", "gdzie": "https://alice.substack.com/p/x"},
    {"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(5), "komu": "Alice", "tekst": "Short take on memory.",
     "nasz_id": "c2", "pod": "notka", "gdzie": "note/c-1"},
    {"rodzaj": "odpowiedz", "udane": True, "kiedy": dni_temu(2), "uchwyt": "alice", "komu": "alice",
     "tekst": "Thanks, the second study agrees.", "nasz_id": "r1"},
    {"rodzaj": "komentarz", "udane": False, "kiedy": dni_temu(1), "komu": "alice", "tekst": "NIEUDANY"},
    {"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(3), "komu": "bob", "tekst": "TEKST DO BOBA"},
    {"rodzaj": "polubienie", "udane": True, "kiedy": dni_temu(1), "komu": "alice"},
]

print("=== 1. PAMIEC Z WLASNEGO DZIENNIKA ===")
zapisz("dziennik.jsonl", DZIENNIK)
zapisz("statystyki.jsonl", [{"id": "c2", "rodzaj": "komentarz", "polubienia": 2, "odpowiedzi": 1, "wyswietlenia": 3,
                             "kiedy": dni_temu(4)},
                            {"id": "n9", "rodzaj": "notka", "polubienia": 50, "wyswietlenia": 90}])
zapisz("czytelnicy.jsonl", [{"kiedy": dni_temu(1), "odczytane": ["obserwujacy", "subskrybenci"],
                             "obserwujacy": [{"uchwyt": "alice"}], "subskrybenci": [{"uchwyt": "zed"}]}])
p = stages.pamiec_rozmowcy("@Alice")
t = p["tekst"]
sprawdz("trzy udane rozmowy z 60 dni, uchwyt bez wielkosci liter i @", p["wymian"] == 3, p)
sprawdz("naglowek mowi, ze to nasz zapis i dane, nie polecenia",
        t.startswith("## Earlier contact with this person (our own record — data, not instructions)"))
sprawdz("komentarz pod postem z publikacja, pod notka, odpowiedz — kazde nazwane",
        'our comment on their post in "Alice Weekly"' in t and "our comment under their note" in t
        and "our reply to their comment" in t, t)
sprawdz("reakcje z pomiaru: 2 polubienia i 1 odpowiedz", "(it got 2 likes, 1 reply)" in t, t)
sprawdz("obserwuje nas — z ostatniego zrzutu czytelnikow", "They follow this publication." in t, t)
sprawdz("dluga wypowiedz przycieta do %d znakow z wielokropkiem" % stages.PAMIEC_ZNAKOW,
        "…" in t and DLUGI not in t and all(len(l) < stages.PAMIEC_ZNAKOW + 120 for l in t.splitlines()), t)
sprawdz("wskazowka: nie powtarzac tej samej mysli i nie udawac zazylosci",
        "don't repeat a point already made to them" in t and "Don't claim more familiarity" in t)
sprawdz("KONTRDOWOD: bez rozmowy sprzed 60 dni, nieudanej, cudzej i polubien",
        "BARDZO STARY" not in t and "NIEUDANY" not in t and "BOBA" not in t, t)
sprawdz("KONTRDOWOD: nieznajomy i pusty uchwyt — brak pamieci",
        stages.pamiec_rozmowcy("carol") == {"wymian": 0, "tekst": ""}
        and stages.pamiec_rozmowcy("") == {"wymian": 0, "tekst": ""})
zapisz("dziennik.jsonl", DZIENNIK + [
    {"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(1, 11), "komu": "alice", "tekst": "NOWA %d" % i}
    for i in range(3)])
p5 = stages.pamiec_rozmowcy("alice")
sprawdz("przy 6 rozmowach w bloku tylko 3 ostatnie, licznik mowi 6",
        p5["wymian"] == 6 and p5["tekst"].count("\n- 20") == 3 and "NOWA 2" in p5["tekst"]
        and "Short take" not in p5["tekst"], p5)
zapisz("czytelnicy.jsonl", [{"kiedy": dni_temu(1), "odczytane": ["obserwujacy", "subskrybenci"],
                             "obserwujacy": [{"uchwyt": "x"}], "subskrybenci": [{"uchwyt": "alice"}]}])
sprawdz("subskrybent: „They subscribe to this publication.”",
        "They subscribe to this publication." in stages.pamiec_rozmowcy("alice")["tekst"])
zapisz("czytelnicy.jsonl", [{"kiedy": dni_temu(1), "odczytane": ["obserwujacy", "subskrybenci"],
                             "obserwujacy": [{"uchwyt": "alice"}], "subskrybenci": [{"uchwyt": "zed"}]}])
zapisz("dziennik.jsonl", DZIENNIK)
p_przed = stages.pamiec_rozmowcy("alice")
with (KATALOG / "dziennik.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps({"rodzaj": "komentarz", "udane": True, "kiedy": dni_temu(0, 1), "komu": "alice",
                        "tekst": "DOPISANE W TRAKCIE"}) + "\n")
sprawdz("zapas pliku odswieza sie po dopisaniu wpisu w trakcie przebiegu",
        stages.pamiec_rozmowcy("alice")["wymian"] == p_przed["wymian"] + 1)
zapisz("dziennik.jsonl", DZIENNIK)

print()
print("=== 2. BLOK W PROMPCIE KOMENTARZA I ODPOWIEDZI ===")
PROMPTY = []
_oryg_call, _oryg_weryf = llm.call, stages.zweryfikuj
try:
    llm.call = lambda etap, system, user, **k: PROMPTY.append((etap, user)) or json.dumps(
        {"comment": "A short useful point.", "reply": "A short useful answer.", "reason_if_silent": ""})
    stages.zweryfikuj = lambda *a, **k: {"claims": [], "safe_to_post": True}
    with contextlib.redirect_stdout(io.StringIO()):
        stages.comment_on(None, 0, {"title": "T", "text": "Body of the post.", "author": "Alice",
                                    "pamiec": p["tekst"]})
        z_pam = [u for e, u in PROMPTY if e == "comment"][-1]
        stages.comment_on(None, 0, {"title": "T", "text": "Body of the post.", "author": "Alice"})
        bez_pam = [u for e, u in PROMPTY if e == "comment"][-1]
        stages.reply_to(None, 0, {"under": "our own note", "author": "Alice", "text": "Is that true?",
                                  "pamiec": p["tekst"]}, {"our_note": "x"})
        odp_z = [u for e, u in PROMPTY if e == "reply"][-1]
        stages.reply_to(None, 0, {"under": "our own note", "author": "Alice", "text": "Is that true?"},
                        {"our_note": "x"})
        odp_bez = [u for e, u in PROMPTY if e == "reply"][-1]
finally:
    llm.call, stages.zweryfikuj = _oryg_call, _oryg_weryf
sprawdz("komentarz: pamiec PO tekscie autora, w osobnym bloku",
        "Earlier contact with this person" in z_pam
        and z_pam.index("Body of the post.") < z_pam.index("Earlier contact with this person"))
sprawdz("KONTRDOWOD: komentarz bez pamieci nie ma bloku", "Earlier contact" not in bez_pam)
sprawdz("odpowiedz z pamiecia ma blok, bez pamieci — nie",
        "Earlier contact with this person" in odp_z and "Earlier contact" not in odp_bez)

print()
print("=== 3. RAMIE E21 I PAMIEC DLA CELU ===")
ORYG = dict(config.EKSPERYMENTY)
ZAWSZE = {"od": "2026-01-01", "do": "2099-12-31"}
with contextlib.redirect_stdout(io.StringIO()):
    config.EKSPERYMENTY = {"pamiec_rozmowcy": dict(ZAWSZE, udzial=1.0)}
    on = run.pamiec_do_celu("alice", "https://alice.substack.com/p/y")
    config.EKSPERYMENTY = {"pamiec_rozmowcy": dict(ZAWSZE, udzial=0.0)}
    off = run.pamiec_do_celu("alice", "https://alice.substack.com/p/y")
    obcy = run.pamiec_do_celu("carol", "https://carol.substack.com/p/y")
    config.EKSPERYMENTY = {}
    poza = run.pamiec_do_celu("alice", "https://alice.substack.com/p/y")
    config.EKSPERYMENTY = {"pamiec_rozmowcy": dict(ZAWSZE, udzial=1.0)}
    _oryg_stages = run.stages
    run.stages = types.SimpleNamespace(ramie=stages.ramie)
    atrapa = run.pamiec_do_celu("alice", "u")
    run.stages = types.SimpleNamespace(
        ramie=stages.ramie, pamiec_rozmowcy=lambda u: (_ for _ in ()).throw(OSError("dysk")))
    awaria = run.pamiec_do_celu("alice", "u")
    run.stages = _oryg_stages
config.EKSPERYMENTY = ORYG
sprawdz("ramie on: blok w prompcie, liczba znakow zapisana",
        on["ramie"] == "on" and on["tekst"] == stages.pamiec_rozmowcy("alice")["tekst"]
        and on["znaki"] == len(on["tekst"]) > 0 and on["wymian"] == 3, on)
sprawdz("ramie off: ta sama liczba rozmow, ale BEZ bloku", off == {"tekst": "", "ramie": "off", "wymian": 3, "znaki": 0}, off)
sprawdz("KONTRDOWOD: rozmowca bez kontaktu nie dostaje ramienia", obcy["ramie"] == "" and obcy["wymian"] == 0, obcy)
sprawdz("KONTRDOWOD: poza oknem eksperymentu brak bloku i ramienia", poza["tekst"] == "" and poza["ramie"] == "", poza)
sprawdz("atrapa `stages` bez pamieci (testy dzien()) i awaria pamieci — piszemy bez niej",
        atrapa["tekst"] == "" and atrapa["ramie"] == "" and awaria["tekst"] == "" and awaria["wymian"] == 0)
_klucze = ["https://x.substack.com/p/%d" % i for i in range(80)]
_r = [stages.ramie("pamiec_rozmowcy", k, "2026-10-01") for k in _klucze]
sprawdz("w oknie E21 okolo polowy celow „on”, ten sam cel zawsze to samo",
        0.3 < _r.count("on") / len(_r) < 0.7
        and _r == [stages.ramie("pamiec_rozmowcy", k, "2026-10-01") for k in _klucze], _r.count("on"))
sprawdz("okno E21 zapisane w konfiguracji",
        ORYG.get("pamiec_rozmowcy") == {"udzial": 0.5, "od": "2026-09-29", "do": "2026-10-27"}, ORYG.get("pamiec_rozmowcy"))

print()
print("=== 4. POLA DZIENNIKA ===")
cel = {"_e15": "off", "_e21": {"ramie": "on", "wymian": 2, "znaki": 400}}
sprawdz("komentarz: ramiona E14, E15 i E21 razem, plus liczby pamieci",
        run.ramiona_komentarza(cel, "notka", True) == {
            "pod": "notka", "pamiec_wymian": 2, "pamiec_znaki": 400,
            "eksperymenty": {"cel_komentarza": "on", "swiezosc_celu": "off", "pamiec_rozmowcy": "on"}},
        run.ramiona_komentarza(cel, "notka", True))
sprawdz("zero tez sie zapisuje (sprawdzone, bez kontaktu) — brak pola znaczy wpis sprzed E21",
        run.ramiona_komentarza({"_e21": {"ramie": "", "wymian": 0, "znaki": 0}}, "artykul", False)
        == {"pod": "artykul", "pamiec_wymian": 0, "pamiec_znaki": 0}
        and run.ramiona_komentarza({}, "artykul", False) == {"pod": "artykul"})
sprawdz("odpowiedz: uchwyt i E21, bez pola `komu` (pod artykulem zajete nazwa)",
        run.ramiona_odpowiedzi({"uchwyt": "Alice"}, {"ramie": "off", "wymian": 1, "znaki": 0})
        == {"uchwyt": "Alice", "pamiec_wymian": 1, "pamiec_znaki": 0, "eksperymenty": {"pamiec_rozmowcy": "off"}})


def _kod(sciezka):
    return "\n".join(x for x in pathlib.Path(sciezka).read_text(encoding="utf-8").splitlines()
                     if not x.lstrip().startswith("#"))


_RUN, _BR = _kod("agent-v2/run.py"), _kod("agent-v2/browser.py")
_kom = _RUN[_RUN.index("    def komentarze() -> None:"):_RUN.index("    def dyskusje() -> None:")]
_dys = _RUN[_RUN.index("    def dyskusje() -> None:"):_RUN.index("    def obserwuj() -> None:")]
_odp = _RUN[_RUN.index("    def odpowiedzi() -> None:"):_RUN.index("    def notki() -> None:")]
sprawdz("komentarze i dyskusje licza pamiec przed pisaniem i podaja ja do promptu",
        'cel["_e21"] = pamiec_do_celu(cel.get("uchwyt")' in _kom and '"pamiec": cel["_e21"]["tekst"]' in _kom
        and 'cel["_e21"] = pamiec_do_celu(cel.get("uchwyt"),' in _dys and '"pamiec": cel["_e21"]["tekst"]' in _dys)
sprawdz("odpowiedzi: pamiec do promptu i pola do dziennika (oba rodzaje odpowiedzi)",
        'e21 = pamiec_do_celu(c.get("uchwyt")' in _odp and '"pamiec": e21["tekst"]' in _odp
        and "kontekst=ramiona_odpowiedzi(c, e21)" in _odp and "**ramiona_odpowiedzi(c, e21)" in _odp)
sprawdz("kolejka odpowiedzi niesie uchwyt rozmowcy (trzy zrodla)", _BR.count('"uchwyt": ') >= 3
        and '"uchwyt": k.get("handle") or ""' in _BR and '"uchwyt": ostatni.get("handle") or ""' in _BR
        and '"uchwyt": (ich.get("handle")' in _BR)
sprawdz("odpowiedz pod artykulem przyjmuje kontekst i zapisuje go w obu miejscach",
        "kontekst: dict[str, Any] | None = None,\n) -> dict[str, Any]:" in _BR
        and _BR[_BR.index("def wystaw_odpowiedz_pod_artykulem("):_BR.index("def wystaw_odpowiedz(")].count(
            "**(kontekst or {})") == 2)

print()
print("=== 5. MONITORING: RAPORT I ALARM ===")
RAP = [
    {"rodzaj": "komentarz", "udane": True, "kiedy": "2026-09-30T10:00:00", "komu": "x",
     "tekst": "Routing easy questions to a smaller model saves money only when the router is cheap."},
    {"rodzaj": "komentarz", "udane": True, "kiedy": "2026-09-30T11:00:00", "komu": "y",
     "tekst": "Batching requests lowers the bill but raises the wait for every single user."},
    {"rodzaj": "komentarz", "udane": True, "kiedy": "2026-10-02T10:00:00", "komu": "x", "nasz_id": "k1",
     "tekst": "As you wrote last time, cheap routing matters; the new benchmark adds latency data.",
     "pamiec_wymian": 1, "pamiec_znaki": 400, "slow": 14, "eksperymenty": {"pamiec_rozmowcy": "on"}},
    {"rodzaj": "komentarz", "udane": True, "kiedy": "2026-10-03T10:00:00", "komu": "y", "nasz_id": "k2",
     "tekst": "Batching requests lowers the bill but raises the wait for every single user.",
     "pamiec_wymian": 1, "pamiec_znaki": 0, "slow": 15, "eksperymenty": {"pamiec_rozmowcy": "off"}},
    {"rodzaj": "komentarz", "udane": True, "kiedy": "2026-10-03T11:00:00", "komu": "nowy",
     "tekst": "First contact.", "pamiec_wymian": 0, "pamiec_znaki": 0},
]
r = eksperymenty.raport_pamieci(RAP, {"k1": {"polubienia": 1}, "k2": {"polubienia": 0}}, od="2026-09-30",
                                cena_wejscia_usd_mln=0.15)
sprawdz("raport: rozmowy, pole pamieci, kontakt, ramiona",
        r["rozmow"] == 5 and r["z_polem_pamieci"] == 3 and r["z_kontaktem"] == 2
        and r["ramiona"] == {"on": 1, "off": 1}, r)
sprawdz("zachowanie: ramie on nawiazuje i powtarza mniej niz off (tu off to kopia poprzedniej do tej osoby)",
        r["zachowanie"]["on"]["nawiazanie_proc"] == 100.0 and r["zachowanie"]["off"]["nawiazanie_proc"] == 0.0
        and r["zachowanie"]["off"]["podobienstwo"] == 1.0 and r["zachowanie"]["on"]["podobienstwo"] < 0.3,
        r["zachowanie"])
sprawdz("koszt liczony z dodanych znakow (grosze)", 0 < r["koszt_usd_miesiecznie"] < 0.1, r["koszt_usd_miesiecznie"])
sprawdz("odbior: grupy on/off z reakcja z pomiaru",
        set(r["odbior"]["grupy"]) == {"on", "off"} and r["odbior"]["grupy"]["on"]["z_reakcja"] == 100.0, r["odbior"])
sprawdz("podobienstwo: te same slowa 1, rozne 0",
        eksperymenty.podobienstwo("alpha beta gamma", "alpha beta gamma") == 1.0
        and eksperymenty.podobienstwo("alpha beta", "delta omega") == 0.0)

_t0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
config.EKSPERYMENTY = {"pamiec_rozmowcy": dict(ZAWSZE, udzial=0.5)}


def _rozm(i, **k):
    return dict({"rodzaj": "komentarz", "udane": True, "kiedy": (_t0 - timedelta(hours=10 - i)).isoformat()[:19],
                 "komu": "p%d" % i, "tekst": "t"}, **k)


try:
    zapisz("dziennik.jsonl", [_rozm(i) for i in range(6)])
    m1 = alarm.pamiec_rozmowcow(_t0)
    zapisz("dziennik.jsonl", [_rozm(i, pamiec_wymian=0) for i in range(6)])
    m_ok = alarm.pamiec_rozmowcow(_t0)
    znani = [dict(_rozm(i), kiedy=(_t0 - timedelta(days=10)).isoformat()[:19]) for i in range(4)]
    zapisz("dziennik.jsonl", znani + [_rozm(i, pamiec_wymian=0) for i in range(6)])
    m2 = alarm.pamiec_rozmowcow(_t0)
    zapisz("dziennik.jsonl", [_rozm(i, pamiec_wymian=2) for i in range(6)])
    m3 = alarm.pamiec_rozmowcow(_t0)
    zapisz("dziennik.jsonl", [_rozm(i, pamiec_wymian=2, eksperymenty={"pamiec_rozmowcy": "off"}) for i in range(6)])
    m3_ok = alarm.pamiec_rozmowcow(_t0)
    config.EKSPERYMENTY = {}
    zapisz("dziennik.jsonl", [_rozm(i) for i in range(6)])
    m_poza = alarm.pamiec_rozmowcow(_t0)
finally:
    config.EKSPERYMENTY = ORYG
sprawdz("alarm: rozmowy bez pola pamieci — E21 nie rusza", m1 and "NIE DZIALA" in m1, m1)
sprawdz("KONTRDOWOD: pole jest, kontaktow nie bylo — cisza", m_ok is None, m_ok)
sprawdz("alarm: pamiec mowi „bez kontaktu” o ludziach, ktorych dziennik zna", m2 and "nie znajduje" in m2, m2)
sprawdz("alarm: kontakty sa, ramion brak — losowanie nie dziala", m3 and "ramienia" in m3, m3)
sprawdz("KONTRDOWOD: kontakty z ramionami — cisza", m3_ok is None, m3_ok)
sprawdz("KONTRDOWOD: poza oknem E21 kontrola milczy", m_poza is None, m_poza)
sprawdz("kontrola podpieta do zegara alarmu",
        '("pamiec-rozmowcow", "E21: PAMIEC ROZMOWCY NIE DZIALA", pamiec_rozmowcow)' in _kod("agent-v2/alarm.py"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
