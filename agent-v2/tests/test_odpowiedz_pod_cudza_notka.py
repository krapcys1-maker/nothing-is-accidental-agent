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
        # K: korzen watku NIE ma wpisu w paczce (jak na zywym kanale), a jego
        # autorem jestesmy MY — to nasza odpowiedz pod NASZA notka, nie cudzy watek
        zd("note_reply", 5011, 4011),
        # L: odczyt wlasciciela korzenia zwraca nic -> pomin (w razie watpliwosci)
        zd("note_reply", 5012, 4012),
        # M: odczyt wlasciciela korzenia rzuca wyjatek -> pomin, reszta dziala
        zd("note_reply", 5013, 4013),
        # N: nadawca zdarzenia to kto inny niz autor odpowiedzi — uchwyt z `user_id`
        zd("note_reply", 5014, 4014, nadawca=333),
        # O: ten sam korzen co A (9001) -> jedno zapytanie na korzen, nie dwa
        zd("note_reply", 5015, 4015),
        # Q: pusta tresc odpowiedzi -> nic do odpisania
        zd("note_reply", 5016, 4016),
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
        wpis(4011, MOJE, "8011"), wpis(5011, 111, "8011.4011", "K"),
        wpis(4012, MOJE, "8012"), wpis(5012, 111, "8012.4012", "L"),
        wpis(4013, MOJE, "8013"), wpis(5013, 111, "8013.4013", "M"),
        wpis(4014, MOJE, "9014"), wpis(5014, 111, "9014.4014", "N: autor z user_id"),
        wpis(4015, MOJE, "9001"), wpis(5015, 111, "9001.4015", "O: ten sam korzen co A"),
        wpis(4016, MOJE, "9016"), wpis(5016, 111, "9016.4016", "   "),
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
    "5011": galaz(), "4011": galaz(), "5012": galaz(), "4012": galaz(),
    "5013": galaz(), "4013": galaz(), "5014": galaz(), "4014": galaz(),
    "5015": galaz(), "4015": galaz(), "5016": galaz(), "4016": galaz(),
}


def korzen(i, wlasciciel):
    """Odpowiedz `/replies` na korzen watku: niesie `rootComment` z autorem — tak jak
    na zywym kanale, gdzie korzenia NIE MA w paczce zdarzen i trzeba o niego zapytac."""
    return {"rootComment": {"id": i, "user_id": wlasciciel, "body": "cudza notka"},
            "commentBranches": []}


# KORZENIE WATKOW. Cudzy autor (5) dla tych, ktore maja byc brane; MY (MOJE) dla K;
# L nie ma wpisu wcale (odczyt oddaje None), M rzuca wyjatek (patrz `api`).
for _korzen in (9001, 9006, 9007, 9009, 9010, 9014, 9016):
    WATKI[str(_korzen)] = korzen(_korzen, 5)
WATKI["8011"] = korzen(8011, MOJE)

ZAPYTANIA = []


def api(page, sciezka, baza=None):
    if "public_profile" in sciezka:
        return {"id": MOJE}
    if "activity-feed-web" in sciezka:
        return KANAL
    m = re.search(r"/reader/comment/(\d+)/replies", sciezka)
    if m:
        ZAPYTANIA.append(m.group(1))
        if m.group(1) == "8013":
            raise RuntimeError("odczyt korzenia padl")
        return WATKI.get(m.group(1))
    return None


oryg = (browser.api_json, browser.podlacz_sie, browser.wymagaj_sesji)
browser.api_json = api
browser.podlacz_sie = lambda: (Nic(), Nic(), Nic())
browser.wymagaj_sesji = lambda: None
try:
    print("=== 1. KTORE ZDARZENIA TRAFIAJA DO ODPOWIEDZI ===")
    ZAPYTANIA.clear()
    czekaja = browser.odpowiedzi_na_nasze_komentarze(ile=50)
    numery = sorted(c["pod_id"] for c in czekaja)
    sprawdz("czekaja dokladnie: A (5001), H (5008), J (5010), N (5014), O (5015)",
            numery == [5001, 5008, 5010, 5014, 5015], numery)
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
    sprawdz("Q: pusta tresc ich odpowiedzi -> nic do odpisania", 5016 not in po)

    print()
    print("=== 2b. WLASCICIEL KORZENIA WATKU: PRZEGLAD 1.11.2026 ===")
    # NA ZYWYM KANALE KORZENIA WATKU NIE MA W PACZCE, wiec samo sito z paczki
    # uznawalo nasza odpowiedz pod NASZA notka za komentarz w cudzym watku
    # i bot odpisywalby drugi raz, omijajac limit rozmowy. Wlasciciela ustala
    # jedno zapytanie o korzen, a w razie watpliwosci pomijamy.
    sprawdz("K: korzen poza paczka, wlasciciel to MY -> pomin (nasza notka)", 5011 not in po)
    sprawdz("L: odczyt wlasciciela korzenia nic nie oddal -> pomin (w razie watpliwosci)",
            5012 not in po)
    sprawdz("M: odczyt wlasciciela korzenia rzucil wyjatek -> pomin, reszta dziala",
            5013 not in po and len(po) == 5)
    sprawdz("A: korzen poza paczka, wlasciciel CUDZY -> brany", 5001 in po)
    sprawdz("jedno zapytanie na korzen, nie na zdarzenie (A i O dziela korzen 9001)",
            ZAPYTANIA.count("9001") == 1, ZAPYTANIA.count("9001"))
    n = po.get(5014, {})
    sprawdz("N: autor i uchwyt z `user_id` odpowiedzi, nie z pierwszego nadawcy zdarzenia",
            n.get("uchwyt") == "ann", (n.get("uchwyt"), n.get("autor")))
    sprawdz("O: drugie zdarzenie z tego samego korzenia tez brane", 5015 in po)
    ZAPYTANIA.clear()
    sprawdz("`ile` ogranicza liczbe oddanych odpowiedzi",
            len(browser.odpowiedzi_na_nasze_komentarze(ile=1)) == 1)

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
sprawdz("korzen nieznany paczce -> helper przepuszcza; o wlascicielu rozstrzyga `_wlasciciel_korzenia`",
        f({"user_id": MOJE, "ancestor_path": "9999"}, MOJE, wp) is True)
sprawdz("pusty wpis -> nie", f({}, MOJE, wp) is False and f(None, MOJE, wp) is False)
sprawdz("brak naszego numeru -> nie (None == None nie moze uznac cudzego wpisu za nasz)",
        f({"user_id": None, "ancestor_path": "9001"}, None, wp) is False
        and f({}, None, wp) is False)

print()
print("=== 6b. `_wlasciciel_korzenia` ===")
g = browser._wlasciciel_korzenia
zap = []
oryg_api = browser.api_json


def api_korzen(page, sciezka, baza=None):
    zap.append(sciezka)
    if "/777/" in sciezka:
        return {"rootComment": {"id": 777, "user_id": 42}}
    if "/778/" in sciezka:
        raise RuntimeError("padlo")
    if "/779/" in sciezka:
        return {"commentBranches": []}                     # brak `rootComment`
    if "/780/" in sciezka:
        return {"rootComment": {"id": 780}}                # brak `user_id`
    return None


browser.api_json = api_korzen
try:
    cache = {}
    sprawdz("z paczki: bez zapytania", g(None, "9001", {9001: {"user_id": 5}}, cache) == 5 and zap == [], zap)
    sprawdz("z paczki takze po kluczu napisowym", g(None, "9002", {"9002": {"user_id": 6}}, cache) == 6)
    sprawdz("z zapytania: `rootComment.user_id`", g(None, "777", {}, cache) == 42 and len(zap) == 1, zap)
    sprawdz("drugie pytanie o ten sam korzen nie idzie do sieci", g(None, "777", {}, cache) == 42 and len(zap) == 1, zap)
    sprawdz("wyjatek -> None, i to zapamietane", g(None, "778", {}, cache) is None and "778" in cache)
    sprawdz("brak `rootComment` -> None", g(None, "779", {}, cache) is None)
    sprawdz("`rootComment` bez `user_id` -> None", g(None, "780", {}, cache) is None)
    sprawdz("odpowiedz zamiast slownika (None) -> None", g(None, "781", {}, cache) is None)
finally:
    browser.api_json = oryg_api

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
m_zrodla = re.search(r"czekaja = \(browser\.nieodpowiedziane\(\)\s*\+ browser\.komentarze_pod_artykulami\(\)"
                     r"\s*\+ browser\.odpowiedzi_na_nasze_komentarze\(\)\)", zrodlo)
m_odsiew = re.search(r"^\s+czekaja = bez_powtorzonych_odpowiedzi\(czekaja\)\s*$", zrodlo, re.M)
m_pytania = re.search(r"stages\.zbierz_pytania\(czekaja\)", zrodlo)
sprawdz("przebieg sklada trzy zrodla w tej kolejnosci (wlasne notki sa pierwsze, wiec wygrywaja)",
        bool(m_zrodla), "brak `czekaja = (nieodpowiedziane + komentarze_pod_artykulami + odpowiedzi_na_nasze_komentarze)`")
sprawdz("odsiew jest PRZYPISANY (nie samo wywolanie) i stoi po zebraniu zrodel, przed zbieraniem pytan",
        bool(m_zrodla and m_odsiew and m_pytania) and m_zrodla.start() < m_odsiew.start() < m_pytania.start(),
        (m_zrodla and m_zrodla.start(), m_odsiew and m_odsiew.start(), m_pytania and m_pytania.start()))

print()
print("=== 8. WYLACZNIK PROB: NOWA SCIEZKA NIE WRACA W KAZDYM PRZEBIEGU ===")
# `wystaw_odpowiedz` zapisuje kazda probe jako `odpowiedz` z `gdzie=note/c-<numer
# komentarza, na ktory odpisujemy>`, a porazke jako `udane=False`. Sciezka z
# `note_reply` nie byla uzyta na produkcji, wiec ma ten sam wylacznik co artykuly:
# po `MAKS_NIEUDANYCH_ODPOWIEDZI_POD_ARTYKULEM` porazkach nie wraca.
import json as _json   # noqa: E402
import tempfile        # noqa: E402

KAT8 = pathlib.Path(tempfile.mkdtemp())
stary_dziennik = browser.DZIENNIK
browser.DZIENNIK = KAT8 / "dziennik.jsonl"
MAKS = config.MAKS_NIEUDANYCH_ODPOWIEDZI_POD_ARTYKULEM


def zapisz_dziennik(*wpisy):
    browser.DZIENNIK.write_text("".join(_json.dumps(w) + chr(10) for w in wpisy), encoding="utf-8")


def odp(gdzie, udane, rodzaj="odpowiedz"):
    return {"kiedy": "2026-10-31T10:00:00+00:00", "rodzaj": rodzaj, "udane": udane, "gdzie": gdzie}


CEL = {"gdzie": "komentarz_obcy", "pod_id": 5001, "autor": "Ann"}
try:
    sprawdz("limit prob to liczba, na ktorej test stoi (2)", MAKS == 2, MAKS)
    sprawdz("brak dziennika -> nie blokuje", run.odpowiedz_zablokowana(CEL) is False)
    zapisz_dziennik(*[odp("note/c-5001", False)] * (MAKS - 1))
    sprawdz("o jedna porazke za malo -> nie blokuje", run.odpowiedz_zablokowana(CEL) is False)
    zapisz_dziennik(*[odp("note/c-5001", False)] * MAKS)
    sprawdz("dokladnie limit porazek -> BLOKUJE (bez modelu i bez przerwy)",
            run.odpowiedz_zablokowana(CEL) is True)
    zapisz_dziennik(*[odp("note/c-5001", False)] * MAKS, odp("note/c-5002", False))
    sprawdz("porazki INNEGO komentarza nie blokuja tego",
            run.odpowiedz_zablokowana({"gdzie": "komentarz_obcy", "pod_id": 5003, "autor": "X"}) is False)
    zapisz_dziennik(*[odp("note/c-5001", True)] * 5, odp("note/c-5001", False))
    sprawdz("udane proby nie liczą sie jako porazki", run.odpowiedz_zablokowana(CEL) is False)
    # Wpis `komentarz` z slowem „odpowiedz" W INNYM POLU: szybki filtr tekstowy go przepusci,
    # wiec o odrzuceniu decyduje dopiero sprawdzenie rodzaju (mutacja W4).
    zapisz_dziennik(*[dict(odp("note/c-5001", False, rodzaj="komentarz"), typ="odpowiedz")] * MAKS)
    sprawdz("porazki `komentarz` (wejscie pod cudza notke) nie liczą sie jako porazki odpowiedzi",
            run.odpowiedz_zablokowana(CEL) is False)
    zapisz_dziennik(*[odp("note/c-50011", False)] * MAKS)
    sprawdz("numer 50011 to NIE numer 5001 (dopasowanie calego adresu, nie prefiksu)",
            run.odpowiedz_zablokowana(CEL) is False)
    browser.DZIENNIK.write_text("{to nie json 5001 odpowiedz\n" + _json.dumps(odp("note/c-5001", False)) + chr(10),
                                encoding="utf-8")
    sprawdz("uszkodzona linia nie przerywa liczenia", browser.nieudane_odpowiedzi_w_watku(5001) == 1)
    sprawdz("odpowiedzi pod WLASNA notka (inne `gdzie`) nie sa objete wylacznikiem",
            run.odpowiedz_zablokowana({"gdzie": "notka", "pod_id": 5001, "autor": "Ann"}) is False)
finally:
    browser.DZIENNIK = stary_dziennik

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
