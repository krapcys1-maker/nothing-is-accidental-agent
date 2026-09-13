"""Automatyczna zamiana modeli: w rodzinie, po probie, nigdy na slepo.

DLACZEGO TO POWSTALO. 10 wrzesnia 2026 DeepSeek wycofal V4 Flash i przekierowal
jego nazwe na V4.1 Flash. Konto chodzilo na nowym modelu trzy dni, nie wiedzac
o tym. Wlasciciel: „moze warto dopisac cos takiego, zeby automatycznie sie
zmienialo na nowe modele, jak wychodza".

Listy dostawcow w sekcji 2 to PRAWDZIWE odpowiedzi `GET /v1/models` i
`GET /models` z 13 wrzesnia 2026. Kontrdowod z produkcji: stan konta z tamtego
dnia daje dokladnie jedna zamiane, te, ktorej zabraklo.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config       # noqa: E402
import db           # noqa: E402
import nowe_modele  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


print("=== 1. WERSJE Z IDENTYFIKATOROW ===")
for ident, oczekiwana in (
    ("claude-fable-5-1", (5, 1)),
    ("claude-opus-5", (5,)),
    ("claude-opus-4-8", (4, 8)),
    ("claude-haiku-4-5-20251001", (4, 5)),
    ("claude-3-5-sonnet-20241022", (3, 5)),
    ("deepseek-v4-pro", (4,)),
    ("deepseek-v4.1-pro", (4, 1)),
    ("deepseek-flash", ()),
):
    sprawdz("%-28s -> %s" % (ident, oczekiwana), nowe_modele.wersja(ident) == oczekiwana,
            nowe_modele.wersja(ident))
sprawdz("Opus 5 nowszy od Opusa 4.8", nowe_modele.wersja("claude-opus-5") > nowe_modele.wersja("claude-opus-4-8"))
sprawdz("Fable 5.1 nowszy od Fable 5", nowe_modele.wersja("claude-fable-5-1") > nowe_modele.wersja("claude-fable-5"))

print()
print("=== 2. DECYZJE NA PRAWDZIWYCH LISTACH Z 13 WRZESNIA 2026 ===")
ANTHROPIC = {
    "claude-fable-5-1": "2026-08-28", "claude-opus-5": "2026-07-24",
    "claude-sonnet-5": "2026-06-29", "claude-fable-5": "2026-06-07",
    "claude-opus-4-8": "2026-05-28", "claude-opus-4-7": "2026-04-14",
    "claude-sonnet-4-6": "2026-02-17", "claude-opus-4-6": "2026-02-04",
    "claude-opus-4-5-20251101": "2025-11-24", "claude-haiku-4-5-20251001": "2025-10-15",
    "claude-sonnet-4-5-20250929": "2025-09-29",
}
DEEPSEEK = {"deepseek-flash": None, "deepseek-v4-pro": None}
STAN_10_13_WRZESNIA = {
    "CLAUDE": "claude-opus-5", "SONNET": "claude-sonnet-5",
    "HAIKU": "claude-haiku-4-5-20251001", "FABLE": "claude-fable-5-1",
    "DEEPSEEK": "deepseek-v4-flash", "DEEPSEEK_PRO": "deepseek-v4-pro",
}


def zamiany(obecne, anthropic=ANTHROPIC, deepseek=DEEPSEEK):
    return [(d["rola"], d["z"], d["na"]) for d in nowe_modele.zdecyduj(
        obecne, {"anthropic": anthropic, "deepseek": deepseek})]


sprawdz("KONTRDOWOD Z PRODUKCJI: stan z 10-13 wrzesnia daje jedna zamiane, te brakujaca",
        zamiany(STAN_10_13_WRZESNIA) == [("DEEPSEEK", "deepseek-v4-flash", "deepseek-flash")],
        zamiany(STAN_10_13_WRZESNIA))
PO = dict(STAN_10_13_WRZESNIA, DEEPSEEK="deepseek-flash")
sprawdz("po zamianie: cisza", zamiany(PO) == [], zamiany(PO))
sprawdz("kod po naprawie jest juz w tym stanie",
        {r: getattr(config, r) for r in nowe_modele.ROLE} == PO,
        {r: getattr(config, r) for r in nowe_modele.ROLE})

sprawdz("nowy Opus zamienia wylacznie Opusa",
        zamiany(PO, dict(ANTHROPIC, **{"claude-opus-5-1": "2026-10-01"}))
        == [("CLAUDE", "claude-opus-5", "claude-opus-5-1")])
sprawdz("nowy Fable zmienia tylko role FABLE — Opus nie przeskakuje na drozsza rodzine",
        zamiany(PO, dict(ANTHROPIC, **{"claude-fable-6": "2026-11-01"}))
        == [("FABLE", "claude-fable-5-1", "claude-fable-6")])
sprawdz("wersja preview nie wchodzi",
        zamiany(PO, dict(ANTHROPIC, **{"claude-opus-6-preview": "2026-11-01"})) == [])
sprawdz("V4.1 Pro pod nazwa kanoniczna zamienia Pro",
        zamiany(PO, deepseek=dict(DEEPSEEK, **{"deepseek-pro": None}))
        == [("DEEPSEEK_PRO", "deepseek-v4-pro", "deepseek-pro")])
sprawdz("V4.1 Pro pod nazwa z numerem tez",
        zamiany(PO, deepseek=dict(DEEPSEEK, **{"deepseek-v4.1-pro": None}))
        == [("DEEPSEEK_PRO", "deepseek-v4-pro", "deepseek-v4.1-pro")])
sprawdz("brak listy od dostawcy to brak decyzji, nie „wszystko zniknelo”",
        nowe_modele.zdecyduj(STAN_10_13_WRZESNIA, {"anthropic": None, "deepseek": None}) == [])
bez_opusa = {k: v for k, v in ANTHROPIC.items() if k != "claude-opus-5"}
d = nowe_modele.zdecyduj(PO, {"anthropic": bez_opusa, "deepseek": DEEPSEEK})
sprawdz("znikniety Opus i tylko starszy w rodzinie: zamiana oznaczona jako starsza",
        len(d) == 1 and d[0]["na"] == "claude-opus-4-8" and d[0]["starsza"] and d[0]["nieobecny"], d)

print()
print("=== 3. CO WOLNO WCZYTAC Z PLIKU ZAMIAN ===")
dane = {"zamiany": {
    "DEEPSEEK": {"na": "deepseek-flash"},
    "CLAUDE": {"na": "claude-opus-5-1"},
    "NIEZNANA_ROLA": {"na": "claude-opus-9"},
    "SONNET": {"na": "claude sonnet; rm -rf"},
    "HAIKU": {"na": "deepseek-flash"},
}}
wynik = config.zamiany_z_danych(dane)
sprawdz("przyjete dwie poprawne", wynik == {"DEEPSEEK": "deepseek-flash", "CLAUDE": "claude-opus-5-1"}, wynik)
sprawdz("pusty albo zepsuty plik nie zmienia niczego",
        config.zamiany_z_danych({}) == {} and config.zamiany_z_danych(None) == {})
sprawdz("testy dostaja modele z kodu, nie z pliku produkcji", config._STAN_WYBORU == {})

print()
print("=== 4. PELNY PRZEBIEG sprawdz() — BEZ SIECI ===")
_zapas = {
    "rolami": {r: getattr(config, r) for r in nowe_modele.ROLE},
    "model_for": dict(config.MODEL_FOR), "szukanie": dict(config.MODEL_DO_SZUKANIA),
    "szukanie_dom": config.MODEL_DO_SZUKANIA_DOMYSLNY, "narzedzia": dict(config.WEB_SEARCH_TOOL),
    "proby": dict(config.PROBY_WYSZUKIWANIA), "wolno": config.WOLNO_WOLAC_MODEL,
    "ka": config.ANTHROPIC_API_KEY, "kd": config.DEEPSEEK_API_KEY, "sucho": config.DRY_RUN,
    "lista": nowe_modele.lista_modeli, "odp": nowe_modele.proba_odpowiedzi,
    "szuk": nowe_modele.proba_wyszukiwania,
}
wolane = []


def przywroc_config():
    for rola, model in _zapas["rolami"].items():
        setattr(config, rola, model)
    config.MODEL_FOR.clear()
    config.MODEL_FOR.update(_zapas["model_for"])
    config.MODEL_DO_SZUKANIA.clear()
    config.MODEL_DO_SZUKANIA.update(_zapas["szukanie"])
    config.MODEL_DO_SZUKANIA_DOMYSLNY = _zapas["szukanie_dom"]
    config.WEB_SEARCH_TOOL.clear()
    config.WEB_SEARCH_TOOL.update(_zapas["narzedzia"])
    config.PROBY_WYSZUKIWANIA.clear()
    config.PROBY_WYSZUKIWANIA.update(_zapas["proby"])


def cofnij_do_stanu_z_10_wrzesnia():
    """Konto tak, jak chodzilo: stala i routing na starej nazwie."""
    przywroc_config()
    config.DEEPSEEK = "deepseek-v4-flash"
    for etap, model in list(config.MODEL_FOR.items()):
        if model == "deepseek-flash":
            config.MODEL_FOR[etap] = "deepseek-v4-flash"


zdjecie = config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
try:
    config.ANTHROPIC_API_KEY = "atrapa"
    config.DEEPSEEK_API_KEY = "atrapa"
    nowe_modele.lista_modeli = lambda: {"anthropic": dict(ANTHROPIC), "deepseek": dict(DEEPSEEK)}

    def odp_ok(dostawca, model):
        wolane.append(("odpowiedz", model))
        return True, "odpowiada poprawnym JSON-em", 20, 5

    def szuk_nie(model):
        wolane.append(("szukanie", model))
        return False, 0, 60, 30, "nie wywoluje wyszukiwarki"

    nowe_modele.proba_odpowiedzi = odp_ok
    nowe_modele.proba_wyszukiwania = szuk_nie
    conn = db.connect()

    # 4a. DARMOWY TEST NIE MOZE ZAPLACIC — _preflight odmawia, proba nie idzie.
    cofnij_do_stanu_z_10_wrzesnia()
    config.DRY_RUN = False
    config.WOLNO_WOLAC_MODEL = False
    wynik = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    sprawdz("bez zgody na wywolania: zadna proba nie poszla", wolane == [], wolane)
    sprawdz("zamiana odlozona z powodem, nie wykonana na slepo",
            not wynik["wykonane"] and wynik["odrzucone"]
            and "PreflightFailed" in wynik["odrzucone"][0]["dlaczego"], wynik)
    sprawdz("stala zostala na starej nazwie", config.DEEPSEEK == "deepseek-v4-flash")

    # 4a'. DRY_RUN — `_preflight` go przepuszcza, wiec pilnuje tego sam modul.
    config.WOLNO_WOLAC_MODEL = True
    config.DRY_RUN = True
    wynik = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    sprawdz("KONTRDOWOD: tryb na sucho nie robi zadnej platnej proby", wolane == [], wolane)
    sprawdz("i nie zamienia modelu bez proby",
            not wynik["wykonane"] and config.DEEPSEEK == "deepseek-v4-flash", wynik)
    config.DRY_RUN = False

    # 4b. NIEUDANA PROBA NOWEGO MODELU — zostaje obecny.
    nowe_modele.proba_odpowiedzi = lambda dostawca, model: (False, "HTTP 404: model_not_found", 0, 0)
    wynik = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    sprawdz("KONTRDOWOD: nowy model, ktory nie odpowiada, NIE wchodzi",
            not wynik["wykonane"] and config.DEEPSEEK == "deepseek-v4-flash", wynik)

    # 4c. UDANA PROBA — zamiana w pliku, w procesie, w dzienniku i w ksiedze.
    nowe_modele.proba_odpowiedzi = odp_ok
    wolane.clear()
    wynik = nowe_modele.sprawdz(conn=conn, run_id=None, wymus=True)
    sprawdz("zamiana wykonana",
            [(d["rola"], d["na"]) for d in wynik["wykonane"]] == [("DEEPSEEK", "deepseek-flash")], wynik)
    sprawdz("dziala od razu w tym procesie", config.DEEPSEEK == "deepseek-flash")
    sprawdz("routing etapow przepiety w calosci",
            "deepseek-v4-flash" not in config.MODEL_FOR.values(), sorted(set(config.MODEL_FOR.values())))
    stan = json.loads(config.plik_wyboru_modeli().read_text(encoding="utf-8"))
    sprawdz("plik zamian czyta sie z powrotem jako ta sama zamiana",
            config.zamiany_z_danych(stan) == {"DEEPSEEK": "deepseek-flash"}, stan.get("zamiany"))
    sprawdz("lista dostawcow zapisana obok", stan["u_dostawcow"]["deepseek"] == ["deepseek-flash", "deepseek-v4-pro"])
    sprawdz("proba wyszukiwania na KAZDYM DeepSeeku w uzyciu, takze na szukajacym Pro",
            ("szukanie", "deepseek-flash") in wolane and ("szukanie", "deepseek-v4-pro") in wolane
            and stan["wyszukiwanie"]["deepseek-flash"]["dziala"] is False, wolane)
    # Atrapa mowi, ze Pro nie szuka — tak wygladalaby cicha utrata z 10 wrzesnia.
    sprawdz("KONTRDOWOD: Pro, ktory przestal szukac, od razu schodzi z wyszukiwania",
            not config.szuka_naprawde("deepseek-v4-pro"))
    dziennik = (config.DATA_DIR / "dziennik.jsonl").read_text(encoding="utf-8")
    sprawdz("zamiana w dzienniku dzialan", '"rodzaj": "zmiana_modelu"' in dziennik)
    sprawdz("utrata wyszukiwania tez w dzienniku", "PRZESTAL szukac" in dziennik)
    wiersze = conn.execute("select model, purpose from calls where purpose='nowe_modele'").fetchall()
    sprawdz("proby zapisane w ksiedze kosztow pod wlasnym etapem", len(wiersze) >= 2, [tuple(w) for w in wiersze])

    # 4d. DRUGIE WYWOLANIE W TEJ SAMEJ DOBIE — nic nie robi.
    sprawdz("raz na dobe: drugie wywolanie bez --wymus jest pominiete",
            "pominiete" in nowe_modele.sprawdz(conn=conn, run_id=None))
    conn.close()
finally:
    nowe_modele.lista_modeli = _zapas["lista"]
    nowe_modele.proba_odpowiedzi = _zapas["odp"]
    nowe_modele.proba_wyszukiwania = _zapas["szuk"]
    config.WOLNO_WOLAC_MODEL = _zapas["wolno"]
    config.DRY_RUN = _zapas["sucho"]
    config.ANTHROPIC_API_KEY = _zapas["ka"]
    config.DEEPSEEK_API_KEY = _zapas["kd"]
    przywroc_config()
    config.przywroc_katalog_danych(zdjecie)

print()
print("=== 5. PRZEBIEG DNIA WOLA SPRAWDZENIE I NIE DAJE SIE NIM WYWROCIC ===")
zrodlo = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
dzien = zrodlo[zrodlo.index("def dzien("):]
dzien = dzien[:dzien.index("\ndef ", 10)]
sprawdz("dzien() wola nowe_modele.sprawdz", "nowe_modele.sprawdz(conn=conn, run_id=run_id)" in dzien)
poczatek = dzien.index("nowe_modele.sprawdz")
sprawdz("przed etapami publikacji", poczatek < dzien.index("ile_dzis_wystawione"))
okno = dzien[max(0, poczatek - 400):poczatek + 400]
sprawdz("owiniete w try/except, zeby nie zatrzymac dnia", "try:" in okno and "except Exception" in okno)

print()
print("wynik: %d OK, %d BLAD" % (zdane, oblane))
sys.exit(1 if oblane else 0)
