# -*- coding: utf-8 -*-
"""Odpowiedzi na nasze komentarze POD CUDZYMI NOTKAMI (zdarzenie `note_reply`).

## Co bylo zepsute

`browser.odpowiedzi_na_nasze_komentarze` brala tylko `comment_reply`, czyli
odpowiedzi na nasze komentarze pod ARTYKULAMI. Odpowiedz na nasz komentarz
pod cudza NOTKA przychodzi jako `note_reply`, a `nieodpowiedziane` czyta
wylacznie nasze WLASNE notki — wiec nikt jej nie obslugiwal. Zmierzone
29.10.2026 na 162 naszych komentarzach: autorzy odpowiadali nam pod
artykulami w 13 watkach (odpisalismy w 9) i pod cudzymi notkami w 33
(odpisalismy w 0).

## Czego pilnuje ten test

1. `note_reply` na nasz komentarz w CUDZYM watku jest brany, z kontekstem,
   ktory nie mowi „post" (to notka), i z uchwytem rozmowcy.
2. NIE jest brany `note_reply`, ktorego celu nie znamy, ktory nie jest nasz,
   ktorego cel to nasza notka-korzen ani ktorego korzen watku jest nasz
   (to robi `nieodpowiedziane`).
3. Limit rozmowy dziala tak samo jak pod artykulami: dwie nasze odpowiedzi
   w galezi domykaja ja, a przy koncie siostrzanym — jedna.
4. Odpowiedz, na ktora juz odpisalismy PO ich wypowiedzi, nie wraca.
5. `comment_reply` dziala jak dotad.
6. Ta sama odpowiedz przyslana dwiema drogami zostaje raz
   (`run.bez_powtorzonych_odpowiedzi`), a przebieg wola odsiew po zebraniu
   trzech zrodel.

Bez sieci, bez przegladarki, bez platnych wywolan; produkcyjne pliki sa tylko
czytane (odciski na koncu).
"""
import hashlib
import pathlib
import re
import sys

sys.path.insert(0, "agent-v2")
import browser   # noqa: E402
import config    # noqa: E402
import run       # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def odcisk(p):
    p = pathlib.Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "brak"


PILNOWANE = [config.DB_PATH, config.DATA_DIR / "dziennik.jsonl"]
PRZED = {str(p): odcisk(p) for p in PILNOWANE}

MOJE = 528224862
SIOSTRA = sorted(config.KONTA_SIOSTRZANE)[0]


class Nic:
    def __getattr__(self, _nazwa):
        return lambda *a, **k: Nic()


# --- KANAL AKTYWNOSCI ------------------------------------------------------------
def zd(typ, ich, nasz, kiedy="2026-10-30T12:00:00.000Z", nadawca=111, post=None):
    return {"type": typ, "comment_id": ich, "target_comment_id": nasz,
            "target_post_id": post, "created_at": kiedy,
            "recent_sender_ids": [nadawca]}


def wpis(i, user, sciezka="", body="tekst", **reszta):
    return {"id": i, "user_id": user, "ancestor_path": sciezka, "body": body,
            "name": "Rozmowca%s" % i, "language": "en", **reszta}


KANAL = {
    "activityItems": [
        # A: nasz komentarz w cudzym watku -> BRANY
        zd("note_reply", 5001, 4001),
        # B: cel to nasza notka-korzen (sciezka pusta) -> nieodpowiedziane
        zd("note_reply", 5002, 4002),
        # C: korzen watku jest NASZ (nasza notka) -> nieodpowiedziane
        zd("note_reply", 5003, 4003),
        # D: cel nie jest nasz
        zd("note_reply", 5004, 4004),
        # E: celu nie ma w paczce
        zd("note_reply", 5005, 4005),
        # F: limit rozmowy wyczerpany (dwie nasze odpowiedzi w galezi)
        zd("note_reply", 5006, 4006),
        # G: odpisalismy PO ich wypowiedzi
        zd("note_reply", 5007, 4007),
        # H: komentarz pod artykulem -> jak dotad
        zd("comment_reply", 5008, 4008, post=7),
        # I: konto siostrzane, jedna nasza odpowiedz w galezi -> limit 1
        zd("note_reply", 5009, 4009, nadawca=SIOSTRA),
        # J: zwykly rozmowca, jedna nasza odpowiedz w galezi -> wolno (limit 2)
        zd("note_reply", 5010, 4010, nadawca=333),
        # polubienie nie jest odpowiedzia
        {"type": "note_like", "comment_id": None, "target_comment_id": 4001,
         "created_at": "2026-10-30T11:00:00.000Z"},
    ],
    "comments": [
        wpis(4001, MOJE, "9001"), wpis(5001, 111, "9001.4001", "A: odpowiedz na nasz komentarz"),
        wpis(4002, MOJE, ""), wpis(5002, 111, "4002", "B"),
        wpis(8003, MOJE, ""), wpis(4003, MOJE, "8003"), wpis(5003, 111, "8003.4003", "C"),
        wpis(4004, 222, "9004"), wpis(5004, 111, "9004.4004", "D"),
        wpis(5005, 111, "9005.4005", "E"),
        wpis(4006, MOJE, "9006"), wpis(5006, 111, "9006.4006", "F"),
        wpis(4007, MOJE, "9007"), wpis(5007, 111, "9007.4007", "G"),
        wpis(4008, MOJE, "", post_id=7), wpis(5008, 111, "4008", "H: pod artykulem", post_id=7),
        wpis(4009, MOJE, "9009"), wpis(5009, SIOSTRA, "9009.4009", "I"),
        wpis(4010, MOJE, "9010"), wpis(5010, 333, "9010.4010", "J"),
    ],
    "users": [{"id": 111, "name": "Ann", "handle": "ann"},
              {"id": SIOSTRA, "name": "Siostra", "handle": "siostra"},
              {"id": 333, "name": "Trzeci", "handle": "trzeci"}],
    "posts": [{"id": 7, "title": "Design Study #4",
               "canonical_url": "https://designerpublication.substack.com/p/design-study-4"}],
}


def galaz(*komentarze):
    return {"commentBranches": [{"comment": k} for k in komentarze]}


NASZE = lambda i, sciezka, data="2026-10-30T13:00:00.000Z": {   # noqa: E731
    "id": i, "user_id": MOJE, "ancestor_path": sciezka, "body": "nasza odpowiedz %s" % i,
    "date": data}

WATKI = {
    "5001": galaz(),                       # nikt nie odpisal po ich odpowiedzi
    "4001": galaz(),                       # galaz naszego komentarza: pusta
    "5002": galaz(), "4002": galaz(),
    "5003": galaz(), "4003": galaz(),
    "5004": galaz(), "4004": galaz(),
    "5005": galaz(), "4005": galaz(),
    # F: dwie nasze wypowiedzi w galezi 4006, ale NIE pod ich odpowiedzia 5006
    "5006": galaz(),
    "4006": galaz(NASZE(7001, "9006.4006.7000"), NASZE(7002, "9006.4006.7000")),
    # G: nasza odpowiedz pod ICH odpowiedzia, PO jej dacie (12:00 < 13:00)
    "5007": galaz(NASZE(7003, "9007.4007.5007")),
    "4007": galaz(NASZE(7003, "9007.4007.5007")),
    "5008": galaz(), "4008": galaz(),
    # I: konto siostrzane, jedna nasza odpowiedz w galezi 4009 (nie pod 5009)
    "5009": galaz(), "4009": galaz(NASZE(7004, "9009.4009.7000")),
    # J: zwykly rozmowca, jedna nasza odpowiedz w galezi 4010 (nie pod 5010)
    "5010": galaz(), "4010": galaz(NASZE(7005, "9010.4010.7000")),
}


def api(page, sciezka, baza=None):
    if "public_profile" in sciezka:
        return {"id": MOJE}
    if "activity-feed-web" in sciezka:
        return KANAL
    m = re.search(r"/reader/comment/(\d+)/replies", sciezka)
    if m:
        return WATKI.get(m.group(1))
    return None


oryg = (browser.api_json, browser.podlacz_sie, browser.wymagaj_sesji)
browser.api_json = api
browser.podlacz_sie = lambda: (Nic(), Nic(), Nic())
browser.wymagaj_sesji = lambda: None
try:
    print("=== 1. KTORE ZDARZENIA TRAFIAJA DO ODPOWIEDZI ===")
    czekaja = browser.odpowiedzi_na_nasze_komentarze(ile=50)
    numery = sorted(c["pod_id"] for c in czekaja)
    sprawdz("czekaja dokladnie: A (5001), H (5008), J (5010)",
            numery == [5001, 5008, 5010], numery)
    po = {c["pod_id"]: c for c in czekaja}

    a = po.get(5001, {})
    sprawdz("A: odpowiadamy ICH komentarzowi (5001), nie swojemu (4001)",
            a.get("pod_id") == 5001 and a.get("id") == 5001, a)
    sprawdz("A: miejsce to `komentarz_obcy` — ta sama sciezka publikacji co dotad",
            a.get("gdzie") == "komentarz_obcy", a.get("gdzie"))
    sprawdz("A: kontekst mowi o NOTCE, nie o poscie",
            "note" in (a.get("kontekst") or "") and "post" not in (a.get("kontekst") or ""),
            a.get("kontekst"))
    sprawdz("A: niesie nasz komentarz jako `pod_czym` i uchwyt rozmowcy",
            a.get("uchwyt") == "ann" and "tekst" in (a.get("pod_czym") or ""),
            (a.get("uchwyt"), a.get("pod_czym")))
    sprawdz("A: tresc to ich odpowiedz", (a.get("tekst") or "").startswith("A:"), a.get("tekst"))

    print()
    print("=== 2. CZEGO NIE BIERZEMY ===")
    sprawdz("B: cel to nasza notka-korzen -> zostaje `nieodpowiedziane`", 5002 not in po)
    sprawdz("C: korzen watku to NASZA notka -> zostaje `nieodpowiedziane`", 5003 not in po)
    sprawdz("D: cel nie jest nasz", 5004 not in po)
    sprawdz("E: celu nie ma w paczce, nie zgadujemy", 5005 not in po)
    sprawdz("polubienie nie jest odpowiedzia", all(c["pod_id"] is not None for c in czekaja))

    print()
    print("=== 3. LIMIT ROZMOWY I `JUZ ODPISALISMY` ===")
    sprawdz("F: dwie nasze odpowiedzi w galezi domykaja rozmowe (limit %d)"
            % config.MAKS_ODPOWIEDZI_W_ROZMOWIE, 5006 not in po)
    sprawdz("G: odpisalismy PO ich odpowiedzi -> nie wraca", 5007 not in po)
    sprawdz("I: konto siostrzane, jedna odpowiedz w galezi -> limit %d domyka"
            % config.MAKS_ODPOWIEDZI_KONTU_SIOSTRZANEMU, 5009 not in po)
    sprawdz("J: zwykly rozmowca, jedna odpowiedz w galezi -> jeszcze wolno (KONTRDOWOD do I)",
            5010 in po)
    sprawdz("limity to te, na ktorych test stoi (2 i 1)",
            config.MAKS_ODPOWIEDZI_W_ROZMOWIE == 2
            and config.MAKS_ODPOWIEDZI_KONTU_SIOSTRZANEMU == 1,
            (config.MAKS_ODPOWIEDZI_W_ROZMOWIE, config.MAKS_ODPOWIEDZI_KONTU_SIOSTRZANEMU))

    print()
    print("=== 4. `comment_reply` DZIALA JAK DOTAD ===")
    h = po.get(5008, {})
    sprawdz("H: komentarz pod artykulem nadal jest brany, z tytulem posta w kontekscie",
            h.get("pod_id") == 5008 and "Design Study" in (h.get("kontekst") or ""), h)

    print()
    print("=== 5. PUSTY KANAL I AWARIA ===")
    kanal_zapas = dict(KANAL)
    KANAL["activityItems"] = []
    sprawdz("pusty kanal -> pusta lista", browser.odpowiedzi_na_nasze_komentarze() == [])
    KANAL.update(kanal_zapas)
    browser.api_json = lambda page, sciezka, baza=None: (_ for _ in ()).throw(RuntimeError("padlo"))
    sprawdz("awaria API nie wywala przebiegu", browser.odpowiedzi_na_nasze_komentarze() == [])
finally:
    browser.api_json, browser.podlacz_sie, browser.wymagaj_sesji = oryg

print()
print("=== 6. POMOCNIK: `_nasz_komentarz_w_cudzym_watku` ===")
wp = {9001: {"user_id": 5}, 8003: {"user_id": MOJE}}
f = browser._nasz_komentarz_w_cudzym_watku
sprawdz("nasz, sciezka niepusta, korzen cudzy -> tak",
        f({"user_id": MOJE, "ancestor_path": "9001"}, MOJE, wp) is True)
sprawdz("nie nasz -> nie", f({"user_id": 5, "ancestor_path": "9001"}, MOJE, wp) is False)
sprawdz("sciezka pusta (nasza notka-korzen) -> nie",
        f({"user_id": MOJE, "ancestor_path": ""}, MOJE, wp) is False)
sprawdz("korzen znany i NASZ -> nie", f({"user_id": MOJE, "ancestor_path": "8003"}, MOJE, wp) is False)
sprawdz("korzen nieznany paczce -> tak (nie zgadujemy, ze jest nasz)",
        f({"user_id": MOJE, "ancestor_path": "9999"}, MOJE, wp) is True)
sprawdz("pusty wpis -> nie", f({}, MOJE, wp) is False and f(None, MOJE, wp) is False)

print()
print("=== 7. ODSIEW POWTOREK MIEDZY ZRODLAMI ===")
l = [{"id": 1, "z": "notki"}, {"id": 2, "z": "notki"}, {"id": "1", "z": "obcy"},
     {"id": 3, "z": "obcy"}, {"id": 2, "z": "obcy"}, {"z": "bez numeru"}, {"z": "bez numeru 2"}]
w = run.bez_powtorzonych_odpowiedzi(l)
sprawdz("powtorka po numerze (takze liczba kontra napis) odpada, pierwsze zrodlo wygrywa",
        [(x.get("id"), x["z"]) for x in w]
        == [(1, "notki"), (2, "notki"), (3, "obcy"), (None, "bez numeru"), (None, "bez numeru 2")],
        w)
sprawdz("pozycje bez numeru przechodza wszystkie", sum(1 for x in w if x.get("id") is None) == 2)
sprawdz("pusta lista -> pusta", run.bez_powtorzonych_odpowiedzi([]) == [])
zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
i_zrodla = zrodlo.index("browser.odpowiedzi_na_nasze_komentarze())")
i_odsiew = zrodlo.index("bez_powtorzonych_odpowiedzi(czekaja)", i_zrodla)
i_pytania = zrodlo.index("stages.zbierz_pytania(czekaja)", i_zrodla)
sprawdz("przebieg odsiewa PO zebraniu trzech zrodel i PRZED zbieraniem pytan",
        i_zrodla < i_odsiew < i_pytania, (i_zrodla, i_odsiew, i_pytania))

print()
print("=== PRODUKCJA: bez zmian ===")
zle = 0
for p in PILNOWANE:
    ok_p = odcisk(p) == PRZED[str(p)]
    zle += 0 if ok_p else 1
    print("  %-24s %s" % (pathlib.Path(p).name, "bez zmian" if ok_p else "ZMIENIONA"))

print()
print("=== WYNIK: %d zdanych, %d oblanych%s ===" %
      (zdane, oblane, ", PRODUKCJA RUSZONA" if zle else ""))
sys.exit(1 if (oblane or zle) else 0)
