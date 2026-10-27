# -*- coding: utf-8 -*-
"""Ksiega zakladow (27.10.2026): zgadywania z opublikowanych notek, sprawdzane wyszukiwarka i rozliczane notka.

PO CO. Rozkmina, ktora moze sie mylic, ma wartosc tylko wtedy, gdy ktos liczy, ile razy trafila. Test na atrapie
`llm.call` (bez sieci, bez platnych wywolan) pilnuje:
  1. wyboru grup notek do wyciagu: dojrzalosc doby, okno, dublowanie, notki rozliczajace nie karmia ksiegi;
  2. czyszczenia zakladow z odpowiedzi modelu: numer notki z listy, tresc, daty w oknie, zero cen akcji, zero dubli;
  3. sprawdzenia: rozstrzygniecie TYLKO z adresem zwroconym przez wyszukiwarke; wygasanie po terminie; niejasne
     dwa razy = nie do rozstrzygniecia; awaria nie zapisuje nic; wyczerpany budzet nie jest polykany;
  4. rozliczenia: notka w kolejce serii (gotowy tekst, fakty = dowod), odstep, prog kolejki, wylacznik;
  5. statystyk: trafienia z przedzialem Wilsona, wynik Briera, kalibracja, pusta ksiega;
  6. przebiegu bez `--wyslij` (zero wywolan modelu, zero zapisow) i podlaczenia do przebiegu sledztwa.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zaklady.py
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm        # noqa: E402
import sledztwo   # noqa: E402
import stages     # noqa: E402
import zaklady    # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:900]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = fn(*a, **k)
    return wynik, log.getvalue()


CONN = sqlite3.connect(":memory:")
WYWOLANIA = []
ODPOWIEDZI = []
ZNALEZIONE = []          # adresy, ktore „wyszukiwarka" zwroci w nastepnym wywolaniu z siecia
_prawdziwy = llm.call


def atrapa(purpose, system, prompt, conn=None, run_id=None, web_search=False, collect_urls=None, **k):
    WYWOLANIA.append({"purpose": purpose, "prompt": prompt, "siec": web_search})
    if web_search and collect_urls is not None:
        collect_urls.extend(ZNALEZIONE)
    o = ODPOWIEDZI.pop(0) if ODPOWIEDZI else "{}"
    if isinstance(o, BaseException):
        raise o
    return o if isinstance(o, str) else json.dumps(o)


llm.call = atrapa

DZIS = date(2026, 10, 27)
TERAZ = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)


def czysc():
    for nazwa in (zaklady.PLIK, "dziennik.jsonl", sledztwo.PLIK_KOLEJKI):
        try:
            (config.DATA_DIR / nazwa).unlink()
        except OSError:
            pass
    WYWOLANIA.clear()
    ODPOWIEDZI.clear()
    ZNALEZIONE.clear()


def dziennik(wiersze):
    with (config.DATA_DIR / "dziennik.jsonl").open("a", encoding="utf-8") as f:
        for w in wiersze:
            f.write(json.dumps(dict({"rodzaj": "notka", "udane": True}, **w), ensure_ascii=False) + "\n")


def notka(nid, godzin_temu, pid="", tekst="We think the lab will ship the model before December.", **k):
    kiedy = (TERAZ - timedelta(hours=godzin_temu)).isoformat()
    return dict({"id": str(nid), "kiedy": kiedy, "tekst": tekst, "przeslanie_id": pid}, **k)


def zaklad_surowy(nr=1, bet="We guess that the lab will release its next model before the end of December.",
                  obali="No release is announced by December 31.", od="2026-11-10", do="2026-12-31", p=0.4):
    return {"note": nr, "bet": bet, "wrong_if": obali, "check_from": od, "check_by": do, "probability": p}


def czas_zdarzenia(godzin_temu):
    return (TERAZ - timedelta(hours=godzin_temu)).isoformat()


print("=== 1. GRUPY NOTEK DO WYCIAGU ===")
czysc()
dziennik([notka(1, 30, "202610261300-506-1-reveal"), notka(2, 26, "202610261300-506-2-motive"),
          notka(3, 5, "202610271300-507-1-reveal"),                       # za swieza: grupa nie dojrzala
          notka(4, 30 * 24, "202610011300-400-1-reveal"),                  # poza oknem 8 dni
          notka(5, 30, "202610261900-506-3-rozliczenie"),                  # notka rozliczajaca nie karmi ksiegi
          notka(6, 40, "", typ="MYSL", tekst="A thought, maybe wrong, about who pays."),
          notka(7, 41, "", typ="CIEKAWOSTKA"),                              # zwykla notka z banku — nie
          notka(8, 30, "202610261300-506-4-people", tekst="")])             # pusty tekst — nie
g = zaklady.grupy_do_wyciagu(DZIS)
klucze = sorted(x["klucz"] for x in g)
sprawdz("seria dojrzala po dobie i MYSL tworza grupy; swieza seria, stare notki, rozliczenia, banki i puste odpadaja",
        klucze == ["mysl:" + (TERAZ - timedelta(hours=40)).date().isoformat(), "seria:202610261300-506"], klucze)
sprawdz("grupa serii niesie obie notki w kolejnosci publikacji",
        [n["id"] for n in next(x for x in g if x["klucz"].startswith("seria"))["notki"]] == ["1", "2"], g)
zaklady.dopisz({"zdarzenie": "wyciag", "seria": "seria:202610261300-506", "notki": ["1", "2"], "zakladow": 0})
g2 = zaklady.grupy_do_wyciagu(DZIS)
sprawdz("notka przerobiona raz (nawet z zerem zakladow) nie wraca", [x["klucz"] for x in g2 if x["klucz"].startswith("seria")] == [],
        g2)

print()
print("=== 2. CZYSZCZENIE ODPOWIEDZI MODELU ===")
czysc()
notki = [notka(1, 30, "202610261300-506-1-reveal"), notka(2, 26, "202610261300-506-2-motive")]
surowe = {"bets": [
    zaklad_surowy(1),                                                                         # dobry
    zaklad_surowy(9, bet="We guess that a lab we never mentioned will do something unknown soon."),   # numer spoza listy
    zaklad_surowy(2, bet="We guess it will.", obali="It will not."),                          # za krotki
    zaklad_surowy(2, bet="We guess that the share price of the lab will rise above its record by March."),   # akcje
    zaklad_surowy(2, bet="We guess the regulator will open a formal probe into the data centre deal by January.",
                  obali="No probe by January 31.", od="2020-01-01", do="2099-01-01", p=7),    # daty i pewnosc do okna
    zaklad_surowy("x"),                                                                       # numer nie jest liczba
    zaklad_surowy(1, bet="We guess that the lab will release its next model before the end of December, probably."),  # dubel
]}
out = zaklady.oczysc_zaklady(surowe, notki, DZIS)
sprawdz("zostaja dwa dobre zaklady (limit na grupe), reszta odpada z powodu", len(out) == 2, [o["bet"] for o in out])
sprawdz("zaklad niesie notke zrodlowa i jej numer przeslania", out[0]["notka_id"] == "1" and out[0]["przeslanie_id"].endswith("reveal"), out[0])
d = out[1]
sprawdz("daty z odpowiedzi modelu ciete do okna: od najwczesniej jutro, do najpozniej za `MAKS_DNI_DO_TERMINU`",
        d["check_from"] == (DZIS + timedelta(days=1)).isoformat()
        and d["check_by"] == (DZIS + timedelta(days=zaklady.MAKS_DNI_DO_TERMINU)).isoformat(), d)
sprawdz("pewnosc poza zakresem ciagnieta do 0,05-0,95; brak liczby = 0,5",
        d["probability"] == 0.95 and zaklady._prawdopodobienstwo("abc") == 0.5 and zaklady._prawdopodobienstwo(-3) == 0.05)
sprawdz("brak dat od modelu = `check_from` za tydzien i `check_by` miesiac pozniej",
        (lambda x: x[0]["check_from"] == "2026-11-03" and x[0]["check_by"] == "2026-12-03")(
            zaklady.oczysc_zaklady({"bets": [{"note": 1, "bet": "We guess that Acme will open its weights before spring.",
                                              "wrong_if": "Weights stay closed in spring."}]}, notki, DZIS)))
zaklady.dopisz({"zdarzenie": "zaklad", "id": "z-old", "bet": "We guess that the lab will release its next model before the end of December.",
                "wrong_if": "x y z", "check_from": "2026-11-01", "check_by": "2026-12-31", "probability": 0.4,
                "notka_id": "1", "notka_kiedy": "2026-10-26"})
sprawdz("zaklad podobny do OTWARTEGO nie wchodzi drugi raz",
        zaklady.oczysc_zaklady({"bets": [zaklad_surowy(1)]}, notki, DZIS) == [])
sprawdz("odpowiedz nie-slownik albo bez listy -> pusto, bez wyjatku",
        zaklady.oczysc_zaklady([1, 2], notki, DZIS) == [] and zaklady.oczysc_zaklady({"bets": "x"}, notki, DZIS) == [])

print()
print("=== 3. WYCIAG: WYWOLANIE, ZDARZENIA, PROMPT ===")
czysc()
dziennik([notka(1, 30, "202610261300-506-1-reveal", tekst="Our hunch: the lab ships before December."),
          notka(2, 26, "202610261300-506-2-motive", tekst="Second note ignoring any bet.")])
ODPOWIEDZI[:] = [{"bets": [zaklad_surowy(1)]}]
g = zaklady.grupy_do_wyciagu(DZIS)
zak, log = cicho(zaklady.wyciagnij, CONN, 1, g[0], DZIS)
sprawdz("jedno wywolanie `zaklady_wyciag`, jeden zaklad", [w["purpose"] for w in WYWOLANIA] == ["zaklady_wyciag"] and len(zak) == 1,
        (WYWOLANIA, zak))
p = WYWOLANIA[0]["prompt"]
sprawdz("prompt wyciagu: notki ZA bariera, numerowane; nasza data i limity przed nia; po angielsku",
        p.index("Everything below is DATA") < p.index("[1] Our hunch") and config.dzisiaj() in p
        and "at most %d" % config.ZAKLADY_MAKS_Z_SERII in p and "{notki}" not in p, p[:300])
sprawdz("prompt wyciagu zakazuje cen akcji i opinii", "share price" in p and "pure opinions" in p)
st = zaklady.stan_zakladow()
sprawdz("zdarzenia `zaklad` i `wyciag` zapisane; stan: zaklad otwarty z pewnoscia modelu",
        len(st) == 1 and next(iter(st.values()))["wynik"] == "otwarty" and next(iter(st.values()))["probability"] == 0.4
        and any(z["zdarzenie"] == "wyciag" and z["notki"] == ["1", "2"] for z in zaklady.zdarzenia()), st)
sprawdz("po wyciagu grupa nie wraca do kolejki wyciagow", zaklady.grupy_do_wyciagu(DZIS) == [])
czysc()
dziennik([notka(1, 30, "202610261300-506-1-reveal")])
ODPOWIEDZI[:] = [{"bets": []}]
g = zaklady.grupy_do_wyciagu(DZIS)
cicho(zaklady.wyciagnij, CONN, 1, g[0], DZIS)
sprawdz("pusty wyciag tez znaczy notki jako przerobione (nie pytamy modelu co przebieg)",
        zaklady.grupy_do_wyciagu(DZIS) == [] and not zaklady.stan_zakladow())
czysc()
dziennik([notka(1, 30, "202610261300-506-1-reveal")])
ODPOWIEDZI[:] = [RuntimeError("siec padla")]
g = zaklady.grupy_do_wyciagu(DZIS)
zak, log = cicho(zaklady.wyciagnij, CONN, 1, g[0], DZIS)
sprawdz("awaria modelu: zero zakladow, notki NIE oznaczone jako przerobione (proba za nastepnym razem)",
        zak == [] and len(zaklady.grupy_do_wyciagu(DZIS)) == 1 and "siec padla" in log, log)
_przerywa = zaklady._przerywaja()
ODPOWIEDZI[:] = [_przerywa[0]("budzet")]
try:
    cicho(zaklady.wyciagnij, CONN, 1, g[0], DZIS)
    przepuszczony = False
except BaseException as exc:    # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: wyczerpany budzet NIE jest polykany jako „brak zakladow”", przepuszczony)

print()
print("=== 4. SPRAWDZENIE ZAKLADOW ===")


def otworz(i="z-1", od="2026-10-30", do="2026-12-31", p=0.4, kiedy="2026-10-26"):
    zaklady.dopisz({"zdarzenie": "zaklad", "id": i, "bet": "We guess that the lab will ship the model before December %s." % i,
                    "wrong_if": "No release by the end of December.", "check_from": od, "check_by": do, "probability": p,
                    "notka_id": "1", "notka_kiedy": kiedy, "kiedy": czas_zdarzenia(24)})


czysc()
otworz()
b = zaklady.stan_zakladow()["z-1"]
ZNALEZIONE[:] = ["https://lab.example/blog/release/", "https://news.example/story#top"]
ODPOWIEDZI[:] = [{"result": "yes", "evidence": "The lab announced the model on 3 December.",
                  "sources": ["https://lab.example/blog/release", "https://invented.example/made-up"]}]
w, _ = cicho(zaklady.sprawdz, CONN, 1, b, date(2026, 12, 5))
st = zaklady.stan_zakladow()["z-1"]
sprawdz("„yes” z adresem zwroconym przez wyszukiwarke = trafiony; zrodla tylko prawdziwe (bez slash i bez wymyslonych)",
        w == "trafiony" and st["wynik"] == "trafiony" and st["zrodla"] == ["https://lab.example/blog/release"]
        and "3 December" in st["dowod"], st)
sprawdz("sprawdzenie idzie z siecia i z prompem: zaklad ZA bariera, daty z etykietami",
        WYWOLANIA[0]["siec"] is True and WYWOLANIA[0]["prompt"].index("Everything below is DATA") < WYWOLANIA[0]["prompt"].index("We guess that")
        and "Expires after: 2026-12-31" in WYWOLANIA[0]["prompt"], WYWOLANIA[0]["prompt"][-500:])
czysc()
otworz()
b = zaklady.stan_zakladow()["z-1"]
ZNALEZIONE[:] = ["https://real.example/a"]
ODPOWIEDZI[:] = [{"result": "yes", "evidence": "It happened.", "sources": ["https://invented.example/x"]}]
w, log = cicho(zaklady.sprawdz, CONN, 1, b, date(2026, 12, 5))
sprawdz("KONTRDOWOD: „yes” z adresem spoza wyszukiwania NIE rozstrzyga — zaklad zostaje otwarty",
        w == "jeszcze_nie" and zaklady.stan_zakladow()["z-1"]["wynik"] == "otwarty" and "bez adresu" in log, (w, log))
czysc()
otworz()
b = zaklady.stan_zakladow()["z-1"]
ZNALEZIONE[:] = []
ODPOWIEDZI[:] = [{"result": "no", "evidence": "Nothing.", "sources": ["https://x.example/a"]}]
w, _ = cicho(zaklady.sprawdz, CONN, 1, b, date(2026, 12, 5))
sprawdz("brak jakichkolwiek adresow z wyszukiwania (dostawca nic nie zwrocil) = nie rozstrzygamy", w == "jeszcze_nie", w)
czysc()
otworz()
b = zaklady.stan_zakladow()["z-1"]
ZNALEZIONE[:] = ["https://lab.example/b"]
ODPOWIEDZI[:] = [{"result": "no", "evidence": "No release; the lab postponed.", "sources": ["https://lab.example/b"]}]
w, _ = cicho(zaklady.sprawdz, CONN, 1, b, date(2027, 1, 5))
sprawdz("„no” z adresem po terminie = chybiony", w == "chybiony" and zaklady.stan_zakladow()["z-1"]["wynik"] == "chybiony", w)
czysc()
otworz(do="2026-11-20")
b = zaklady.stan_zakladow()["z-1"]
ODPOWIEDZI[:] = [{"result": "not_yet", "evidence": "", "sources": []}]
w, _ = cicho(zaklady.sprawdz, CONN, 1, b, date(2026, 12, 1))
sprawdz("„not_yet” po terminie = wygasl", w == "wygasl" and zaklady.stan_zakladow()["z-1"]["wynik"] == "wygasl", w)
czysc()
otworz()
b = zaklady.stan_zakladow()["z-1"]
ODPOWIEDZI[:] = [{"result": "not_yet", "evidence": "", "sources": []}]
w, _ = cicho(zaklady.sprawdz, CONN, 1, b, date(2026, 11, 5))
sprawdz("„not_yet” przed terminem = nadal otwarty, sprawdzenie policzone",
        w == "jeszcze_nie" and zaklady.stan_zakladow()["z-1"]["wynik"] == "otwarty" and zaklady.stan_zakladow()["z-1"]["sprawdzen"] == 1, w)
czysc()
otworz()
for _ in range(2):
    ODPOWIEDZI[:] = [{"result": "unclear", "evidence": "Sources conflict.", "sources": []}]
    cicho(zaklady.sprawdz, CONN, 1, zaklady.stan_zakladow()["z-1"], date(2026, 11, 5))
sprawdz("dwa razy „unclear” = nie do rozstrzygniecia (nie dreczymy go w nieskonczonosc)",
        zaklady.stan_zakladow()["z-1"]["wynik"] == "nie_da_sie", zaklady.stan_zakladow()["z-1"])
czysc()
otworz()
ODPOWIEDZI[:] = [RuntimeError("siec padla")]
w, log = cicho(zaklady.sprawdz, CONN, 1, zaklady.stan_zakladow()["z-1"], date(2026, 11, 5))
sprawdz("awaria sprawdzenia nie zapisuje nic i nie wywala", w == "blad" and zaklady.stan_zakladow()["z-1"]["sprawdzen"] == 0, w)
ODPOWIEDZI[:] = [_przerywa[0]("budzet")]
try:
    cicho(zaklady.sprawdz, CONN, 1, zaklady.stan_zakladow()["z-1"], date(2026, 11, 5))
    przepuszczony = False
except BaseException as exc:    # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: budzet nie jest polykany takze przy sprawdzeniu", przepuszczony)
czysc()
otworz("z-a", od="2026-10-27", do="2026-12-01")
otworz("z-b", od="2026-10-27", do="2026-11-15")
otworz("z-c", od="2026-11-20", do="2026-12-31")
zaklady.dopisz({"zdarzenie": "sprawdzenie", "id": "z-a", "wynik": "jeszcze_nie", "kiedy": (TERAZ - timedelta(days=2)).isoformat()})
sprawdz("do sprawdzenia: tylko po `check_from`, nie pytane przez 6 dni, najblizszy termin pierwszy",
        [x["id"] for x in zaklady.zaklady_do_sprawdzenia(DZIS)] == ["z-b"], [x["id"] for x in zaklady.zaklady_do_sprawdzenia(DZIS)])
sprawdz("po 6 dniach zaklad z-a wraca do sprawdzania, nadal po terminie z-b",
        [x["id"] for x in zaklady.zaklady_do_sprawdzenia(DZIS + timedelta(days=5))] == ["z-b", "z-a"])

print()
print("=== 5. ROZLICZENIE: NOTKA W KOLEJCE SERII ===")
czysc()
otworz()
zaklady.dopisz({"zdarzenie": "sprawdzenie", "id": "z-1", "wynik": "trafiony", "dowod": "The lab announced the model on 3 December.",
                "zrodla": ["https://lab.example/release"], "kiedy": "2026-12-03T10:00:00+00:00"})
b = zaklady.stan_zakladow()["z-1"]
TEKST = ("We guessed in late October that the lab would ship before December, and it did, on the third. "
         "Being right is cheap here: we still do not know why they moved so early.")
ODPOWIEDZI[:] = [{"tekst": TEKST}]
t, _ = cicho(zaklady.napisz_rozliczenie, CONN, 1, b)
sprawdz("notka rozliczajaca: jedno wywolanie `zaklady_notka`, wynik w prompcie, dowod ZA bariera",
        t == TEKST and WYWOLANIA[0]["purpose"] == "zaklady_notka" and "We were RIGHT." in WYWOLANIA[0]["prompt"]
        and WYWOLANIA[0]["prompt"].index("Everything below is DATA") < WYWOLANIA[0]["prompt"].index("announced the model"),
        WYWOLANIA)
for opis, tekst in (("za krotka", "We were right."), ("z adresem", "We guessed it would ship and it did, see https://x.example for all the details we found today.")):
    ODPOWIEDZI[:] = [{"tekst": tekst}]
    t2, _ = cicho(zaklady.napisz_rozliczenie, CONN, 1, b)
    sprawdz("notka %s odpada (pusty tekst)" % opis, t2 == "")
sprawdz("zaklad rozstrzygniety, bez notki -> na liscie do rozliczenia", [x["id"] for x in zaklady.zaklady_do_rozliczenia()] == ["z-1"])
ok, _ = cicho(zaklady.kolejkuj_rozliczenie, b, TEKST, 7)
kol = sledztwo._kolejka()
sprawdz("wpis ROZLICZENIE w kolejce: gotowy tekst, fakt = zaklad + dowod + adres, pelny sufit serii na dobe",
        ok and len(kol) == 1 and kol[0]["rodzaj"] == "ROZLICZENIE" and kol[0]["gotowy_tekst"] == TEKST
        and kol[0]["fakty"][0]["evidence"].startswith("The lab announced") and kol[0]["fakty"][0]["url"] == "https://lab.example/release"
        and kol[0]["na_dobe"] == sledztwo.PRZESLAN_NA_DOBE and kol[0]["id"].endswith("-7-1-rozliczenie"), kol)
st = zaklady.stan_zakladow()["z-1"]
sprawdz("zdarzenie `rozliczenie_w_kolejce` zdejmuje zaklad z listy do rozliczenia i niesie id wpisu",
        st["w_kolejce"] and st["przeslanie_id"] == kol[0]["id"] and zaklady.zaklady_do_rozliczenia() == [], st)
kol[0]["kiedy"] = (TERAZ - timedelta(days=1)).isoformat()
sledztwo._zapisz_kolejke(kol)
wydane = sledztwo.wez_przeslanie()
sprawdz("nastepnego dnia kolejka serii wydaje wpis jak kazdy inny (nie blokuje reszty)",
        wydane is not None and wydane["rodzaj"] == "ROZLICZENIE", wydane)
sprawdz("notka rozliczajaca po publikacji nie karmi wyciagu zakladow",
        zaklady._klucz_grupy({"przeslanie_id": kol[0]["id"], "typ": "CIEKAWOSTKA"}) == "")

print()
print("=== 6. OBIEG `obsluz`: NA SUCHO, WYLACZNIK, ODSTEP, KOLEJKA ===")
czysc()
dziennik([notka(1, 30, "202610261300-506-1-reveal")])
otworz("z-due", od="2026-10-27", do="2026-12-31")
w, log = cicho(zaklady.obsluz, CONN, 1, False, DZIS)
sprawdz("bez `--wyslij`: zero wywolan modelu i zero zapisow, tylko opis w logu",
        not WYWOLANIA and w["grup"] == 1 and len(zaklady.zdarzenia()) == 1 and "na sucho" in log, (w, log, WYWOLANIA))
config.ZAKLADY_WLACZONE = False
w, _ = cicho(zaklady.obsluz, CONN, 1, True, DZIS)
sprawdz("wylacznik `ZAKLADY_WLACZONE` zatrzymuje caly obieg", not WYWOLANIA and w["grup"] == 0)
config.ZAKLADY_WLACZONE = True
ZNALEZIONE[:] = ["https://lab.example/c"]
ODPOWIEDZI[:] = [{"bets": [zaklad_surowy(1, bet="We guess that Acme will open the weights of its flagship before spring, to answer rivals.")]},
                 {"result": "yes", "evidence": "It shipped.", "sources": ["https://lab.example/c"]},
                 {"tekst": TEKST}]
w, log = cicho(zaklady.obsluz, CONN, 1, True, DZIS)
sprawdz("pelny obieg w jednym przebiegu: wyciag, sprawdzenie zakladu po terminie, notka rozliczajaca w kolejce",
        [x["purpose"] for x in WYWOLANIA] == ["zaklady_wyciag", "zaklady_sprawdzenie", "zaklady_notka"]
        and w == {"grup": 1, "zakladow": 1, "sprawdzen": 1, "rozstrzygnietych": 1, "rozliczen": 1}, (w, [x["purpose"] for x in WYWOLANIA], log))
otworz("z-2", od="2026-10-28", do="2026-12-31")
zaklady.dopisz({"zdarzenie": "sprawdzenie", "id": "z-2", "wynik": "chybiony", "dowod": "It did not.", "zrodla": ["https://x.example/2"]})
WYWOLANIA.clear()
ODPOWIEDZI[:] = [{"tekst": TEKST}]
w, _ = cicho(zaklady.obsluz, CONN, 2, True, DZIS)
sprawdz("druga notka rozliczajaca w tej samej dobie nie wychodzi (odstep `ODSTEP_ROZLICZEN_DNI`)",
        w["rozliczen"] == 0 and not [x for x in WYWOLANIA if x["purpose"] == "zaklady_notka"], (w, WYWOLANIA))
zdarz = zaklady.zdarzenia()
for z in zdarz:
    if z.get("zdarzenie") == "rozliczenie_w_kolejce":
        z["kiedy"] = (TERAZ - timedelta(days=5)).isoformat()
(config.DATA_DIR / zaklady.PLIK).write_text("".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zdarz), encoding="utf-8")
for i in range(3):
    kol = sledztwo._kolejka()
    kol.append({"id": "202610270000-9-%d-reveal" % i, "wazny_do": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "kiedy": TERAZ.isoformat(), "rodzaj": "REVEAL"})
    sledztwo._zapisz_kolejke(kol)
WYWOLANIA.clear()
ODPOWIEDZI[:] = [{"tekst": TEKST}]
w, _ = cicho(zaklady.obsluz, CONN, 3, True, DZIS)
sprawdz("pelna kolejka serii (>= progu): notka rozliczajaca czeka, nie zjada miejsca sledztwom",
        w["rozliczen"] == 0 and not [x for x in WYWOLANIA if x["purpose"] == "zaklady_notka"], (w, WYWOLANIA))

print()
print("=== 7. STATYSTYKI ===")
czysc()
sprawdz("pusta ksiega: zero zakladow, sekcja raportu to wyjasnia i nie dzieli przez zero",
        zaklady.statystyki()["zakladow"] == 0 and "pusta" in " ".join(zaklady.tekst_statystyk()))
prawdop = [(0.2, "chybiony"), (0.3, "chybiony"), (0.5, "trafiony"), (0.7, "trafiony"), (0.8, "trafiony"), (0.9, "chybiony")]
for i, (p, w) in enumerate(prawdop):
    otworz("z-%d" % i, p=p, kiedy="2026-10-20")
    zaklady.dopisz({"zdarzenie": "sprawdzenie", "id": "z-%d" % i, "wynik": w, "dowod": "d", "zrodla": ["https://x.example/%d" % i],
                    "kiedy": "2026-11-%02dT10:00:00+00:00" % (1 + i)})
otworz("z-open")
otworz("z-exp", do="2026-11-02")
zaklady.dopisz({"zdarzenie": "sprawdzenie", "id": "z-exp", "wynik": "wygasl", "kiedy": "2026-11-03T10:00:00+00:00"})
s = zaklady.statystyki()
brier = sum((p - (1.0 if w == "trafiony" else 0.0)) ** 2 for p, w in prawdop) / len(prawdop)
sprawdz("liczniki: 8 zakladow, 3 trafione, 3 chybione, 1 otwarty, 1 wygasly", s["zakladow"] == 8 and s["wg_stanu"] == {
    "otwarty": 1, "trafiony": 3, "chybiony": 3, "wygasl": 1, "nie_da_sie": 0}, s)
sprawdz("odsetek 3/6 z przedzialem Wilsona obejmujacym 50% i szerokim (maly zbior)",
        s["odsetek_trafien"] == 0.5 and s["przedzial_95"][0] < 0.2 and s["przedzial_95"][1] > 0.8, s["przedzial_95"])
sprawdz("wynik Briera policzony z pewnosci modelu i wyniku", abs(s["brier"] - round(brier, 3)) < 1e-9, (s["brier"], brier))
sprawdz("kalibracja w trzech przedzialach pewnosci (2 niskie, 2 srednie, 2 wysokie)",
        [(k["n"], k["trafionych"]) for k in s["kalibracja"]] == [(2, 0), (2, 1), (2, 2)] or
        [(k["n"], k["trafionych"]) for k in s["kalibracja"]] == [(2, 0), (1, 1), (3, 2)], s["kalibracja"])
txt = "\n".join(zaklady.tekst_statystyk(s))
sprawdz("raport mowi, ze 6 rozstrzygniec to szum, i podaje przedzial", "szum" in txt and "przedzial 95%" in txt, txt)
sprawdz("przedzial Wilsona: 0 z 0 = brak, 10 z 10 nie dochodzi do 100%", zaklady.wilson(0, 0) is None and zaklady.wilson(10, 10)[1] == 1.0
        and zaklady.wilson(10, 10)[0] < 0.75)

print()
print("=== 8. PODLACZENIE DO PRZEBIEGU SLEDZTWA ===")
kod = open("agent-v2/artykul_z_puli.py", encoding="utf-8").read()
sprawdz("przebieg sledztwa wola ksiege PO sledztwie (finally), a nie przed nim",
        "finally:" in kod and "_zaklady_przy_okazji(conn, run_id)" in kod
        and kod.index("return _przebieg_sledztwa(conn, run_id)") < kod.index("_zaklady_przy_okazji(conn, run_id)"))
import artykul_z_puli   # noqa: E402
WYWOLANIA.clear()
for flaga in (["--sledztwo", "--z-sledztwa", "7", "--wyslij"], ["--sledztwo", "--historia", "2", "--wyslij"]):
    stare = sys.argv
    sys.argv = ["x"] + flaga
    try:
        cicho(artykul_z_puli._zaklady_przy_okazji, CONN, 1)
    finally:
        sys.argv = stare
sprawdz("proby reczne (`--z-sledztwa`, `--historia`) nie ruszaja ksiegi", not WYWOLANIA)
_obsluz = zaklady.obsluz
zaklady.obsluz = lambda *a, **k: 1 / 0
stare = sys.argv
sys.argv = ["x", "--sledztwo", "--wyslij"]
try:
    _, log = cicho(artykul_z_puli._zaklady_przy_okazji, CONN, 1)
    polkniete = "ksiega pominieta" in log
finally:
    sys.argv = stare
    zaklady.obsluz = _obsluz
sprawdz("awaria ksiegi nie wywala przebiegu sledztwa, tylko wpis w logu", polkniete)
sprawdz("etapy ksiegi maja model, rozumowanie i limit tokenow w configu",
        all(config.MODEL_FOR.get(e) for e in ("zaklady_wyciag", "zaklady_sprawdzenie", "zaklady_notka"))
        and all(config.MAX_TOKENS.get(e) for e in ("zaklady_wyciag", "zaklady_sprawdzenie", "zaklady_notka"))
        and config.max_szukan("zaklady_sprawdzenie") == 3)

llm.call = _prawdziwy
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
