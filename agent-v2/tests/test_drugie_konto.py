# -*- coding: utf-8 -*-
"""Drugi agent na INNYM koncie Substacka — co musi byc rozdzielone.

PO CO. Wlasciciel chce postawic na tym samym serwerze drugiego agenta,
piszacego na osobne konto. Serwer to udzwignie bez zajaknienia (11,7 GB RAM,
6 rdzeni, obciazenie 0,05; szczyt pamieci przebiegu 265-475 MB), a wiekszosc
stanu rozdziela sie SAMA, bo `DATA_DIR` liczy sie od polozenia katalogu:
zamek `agent.lock`, baza, dziennik, bank kandydatow, sesja przegladarki, stan
serii i `.env` sa per kopia repozytorium.

CO SIE NIE ROZDZIELALO i co ten test pilnuje:

 1. UCHWYT KONTA BYL ZAPISANY DWA RAZY. `config.SUBSTACK_HANDLE` sluzy adresom
    PUBLIKACJI (`uchwyt.substack.com`), a `browser.PROFIL_HANDLE` adresom
    PROFILU (`/@uchwyt/followers`). Obie stale mialy te sama wartosc wpisana
    recznie. Zmiana jednej bez drugiej znaczy, ze agent SPRAWDZA jeden profil,
    a PUBLIKUJE na drugim — i nie powie o tym ani slowa, bo obie sciezki
    dzialaja poprawnie osobno. To jest wada niezalezna od drugiego agenta.
 2. NAZWA MARKI BYLA WPISANA W DZIEWIECIU PROMPTACH. Drugi agent pisalby
    cudzym nazwiskiem. Teraz idzie jako pole `{marka}`, wstawiane przez
    `_prompt` przy KAZDYM wywolaniu — nie z miejsca wywolania, bo pierwsze
    zapomniane konczy sie `KeyError` w srodku platnego przebiegu.
 3. BUDZET LICZY SIE Z WLASNEJ BAZY. To zostaje i nie jest bledem, ale MUSI
    byc widoczne: dwaj agenci to dwa pelne sufity, czyli dwa razy rachunek,
    i zaden z nich tego nie zauwazy.

BEZ PYTESTA, zero sieci. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_drugie_konto.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import browser   # noqa: E402
import stages    # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


print("=== 1. UCHWYT KONTA MA JEDNO ZRODLO ===")
sprawdz("`browser.PROFIL_HANDLE` bierze sie z `config.SUBSTACK_HANDLE`",
        browser.PROFIL_HANDLE == config.SUBSTACK_HANDLE,
        (browser.PROFIL_HANDLE, config.SUBSTACK_HANDLE))
_zr_b = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
sprawdz("i NIE jest w `browser.py` wpisany recznie drugi raz",
        'PROFIL_HANDLE = "' not in _zr_b)
# KONTRDOWOD: gdyby test porownywal tylko wartosci, przeszedlby takze wtedy,
# gdy obie stale sa wpisane recznie i przypadkiem rowne.
sprawdz("KONTRDOWOD: dwie recznie wpisane, rowne stale by tu NIE przeszly",
        'PROFIL_HANDLE = config.SUBSTACK_HANDLE' in _zr_b)

print()
print("=== 2. ZADEN ADRES KONTA NIE JEST ZASZYTY W KODZIE ===")
# Adresy panelu publikacji i edytora artykulu byly wpisane z nazwa konta.
for plik in ("agent-v2/browser.py", "agent-v2/config.py", "agent-v2/stages.py",
             "agent-v2/run.py"):
    tresc = pathlib.Path(plik).read_text(encoding="utf-8")
    # W komentarzach nazwa wolno zostac — to opis, nie adres. Szukamy jej
    # w NAPISACH uzywanych jako adres.
    zle = [w for w in tresc.splitlines()
           if "nothingisaccidental" in w
           and not w.lstrip().startswith("#")
           and "_env(" not in w]
    sprawdz("%-22s bez zaszytego uchwytu w kodzie" % plik.split("/")[-1],
            not zle, zle[:2])

print()
print("=== 3. MARKA JEST POLEM, NIE TRESCIA PROMPTU ===")
_prompty = sorted(pathlib.Path("agent-v2/prompts").glob("*.md"))
_z_marka = [f.name for f in _prompty
            if "{marka}" in f.read_text(encoding="utf-8")]
_z_nazwa = [f.name for f in _prompty
            if "Nothing Is Accidental" in f.read_text(encoding="utf-8")]
sprawdz("prompty uzywaja pola `{marka}` (%d plikow)" % len(_z_marka),
        len(_z_marka) >= 9, _z_marka)
sprawdz("i zaden nie ma nazwy wpisanej w tresci", not _z_nazwa, _z_nazwa)

print()
print("=== 4. PODMIANA MARKI NAPRAWDE DOCHODZI DO PROMPTU ===")
# Zachowaniem, nie czytaniem kodu: sklejamy prompt przy dwoch roznych markach.


def _notka():
    return stages._prompt(
        "notka.md", rozbior="(brak — pisz z samego materialu)", ostatnie_zakonczenia_json="[]", language=config.ARTICLE_LANGUAGE, min_words=33,
        max_words=120, note_type="CIEKAWOSTKA", type_brief="x",
        note_form="PROSTA", form_brief="y", evidence="{}",
        ostatnie_otwarcia_json="[]")


_stara = config.MARKA
try:
    p1 = _notka()
    sprawdz("dzisiejsza marka jest w prompcie", _stara in p1)
    sprawdz("i nie zostal niepodstawiony `{marka}`", "{marka}" not in p1)
    config.MARKA = "Second Publication"
    p2 = _notka()
    sprawdz("po podmianie w prompcie jest NOWA marka",
            "Second Publication" in p2)
    sprawdz("a starej NIE MA — drugi agent nie pisze cudzym nazwiskiem",
            _stara not in p2, p2[:120])
finally:
    config.MARKA = _stara

print()
print("=== 5. UCHWYT I MARKA IDA ZE SRODOWISKA ===")
# Bez tego druga kopia repozytorium musialaby miec zmieniony KOD, a nie `.env`
# — czyli dwie galezie do utrzymania zamiast jednej.
_zr_c = pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8")
sprawdz('`SUBSTACK_HANDLE` czytany przez `_env`',
        '_env("SUBSTACK_HANDLE"' in _zr_c)
sprawdz('`MARKA` czytana przez `_env`', '_env("MARKA"' in _zr_c)

print()
print("=== 6. BUDZET JEST PER AGENT — I MA TO BYC WIDOCZNE ===")
# To NIE jest blad, ale jest pulapka: kazdy agent czyta swoje wydatki z
# WLASNEJ bazy, wiec kazdy uzna, ze ma pelny sufit. Dwaj agenci = dwa razy
# rachunek i zaden tego nie zauwazy.
_zr_l = pathlib.Path("agent-v2/llm.py").read_text(encoding="utf-8")
sprawdz("wydatki liczone z bazy (`db.spent_usd`), czyli per kopia",
        "db.spent_usd(conn" in _zr_l)
sprawdz("i ostrzezenie o tym stoi przy suficie w `config.py`",
        "DWAJ AGENCI" in _zr_c.upper(), "brak ostrzezenia")

print()
print("=== 7. SUFIT DRUGIEJ KOPII IDZIE ZE SRODOWISKA, NIE Z KODU ===")
# Bez tego druga kopia musialaby miec zmieniony KOD, czyli dwie galezie
# do utrzymania. I rzecz wazniejsza, niz wyglada: wrzesniowa PODWYZKA do
# 150 USD byla decyzja o TYM koncie — gdyby zostala stala, drugi agent
# odziedziczylby ja, nie prosiwszy o nia i nie majac powodu.
import os          # noqa: E402
import importlib   # noqa: E402


def _config_z(**srodowisko):
    """Swiezy `config` przy podanym srodowisku. Zawsze sprzatamy po sobie."""
    stare = {k: os.environ.get(k) for k in
             ("MONTHLY_LIMIT_USD", "PODWYZKA_MIESIECZNA_USD", "SUBSTACK_HANDLE",
              "MARKA")}
    for k in stare:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in srodowisko.items() if v is not None})
    try:
        return importlib.reload(config)
    finally:
        for k, v in stare.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


try:
    c = _config_z()
    sprawdz("bez zmiennych sufit bazowy jest jak byl (40)",
            c.MONTHLY_LIMIT_USD == 40.00, c.MONTHLY_LIMIT_USD)
    sprawdz("i wrzesniowa podwyzka jest jak byla (150)",
            c.PODWYZKA_MIESIECZNA_USD == 150.00, c.PODWYZKA_MIESIECZNA_USD)

    c = _config_z(MONTHLY_LIMIT_USD="25", PODWYZKA_MIESIECZNA_USD="0",
                  SUBSTACK_HANDLE="drugiekonto", MARKA="Second Publication")
    sprawdz("druga kopia dostaje swoj sufit", c.MONTHLY_LIMIT_USD == 25.0,
            c.MONTHLY_LIMIT_USD)
    sprawdz("i NIE dziedziczy wrzesniowej podwyzki",
            c.sufit_miesieczny("2026-09-07") == 25.0,
            c.sufit_miesieczny("2026-09-07"))
    sprawdz("uchwyt i marka tez ida ze srodowiska",
            c.SUBSTACK_HANDLE == "drugiekonto" and c.MARKA == "Second Publication",
            (c.SUBSTACK_HANDLE, c.MARKA))

    # POPSUTA WARTOSC MA ZNACZYC „ZOSTAW JAK JEST", NIE ZERO. Literowka
    # w `.env` nie moze uciszyc konta na caly miesiac.
    for zla, opis in (("dwadziescia", "literowka"), ("-5", "wartosc ujemna"),
                      ("", "pusta wartosc")):
        c = _config_z(MONTHLY_LIMIT_USD=zla)
        sprawdz("%-16s nie zeruje sufitu" % opis, c.MONTHLY_LIMIT_USD == 40.00,
                c.MONTHLY_LIMIT_USD)
    c = _config_z(MONTHLY_LIMIT_USD="12,50")
    sprawdz("przecinek dziesietny czytany poprawnie",
            c.MONTHLY_LIMIT_USD == 12.5, c.MONTHLY_LIMIT_USD)
finally:
    importlib.reload(config)

print()
print("=== 8. KOMUNIKATY SYSTEMOWE TEZ ZNAJA MARKE ===")
# ZNALEZIONE PRZEZ DRUGIEGO AGENTA U SIEBIE (`21a8039`: „Artykul pisala
# »anonymous editorial brand«, a notki pisala NIA"), sprawdzone u nas —
# i u nas bylo szerzej. Prompty UZYTKOWNIKA znaly marke od 7 wrzesnia, ale
# PIEC komunikatow systemowych nadal mowilo bezimiennie. Najgorszy przypadek:
# `NOTE_SYSTEM`, czyli glowny glos konta, mial identyfikacje slabsza niz
# skaut, ktory w tym samym pliku wie, o czym jest publikacja.
import stages as _st   # noqa: E402

_SYSTEMOWE = ("NOTE_SYSTEM", "IMAGE_SYSTEM", "TARGETS_SYSTEM",
              "CURIOSITY_SYSTEM", "COMMENT_SYSTEM", "SCOUT_SYSTEM",
              "WRITER_SYSTEM")
for _n in _SYSTEMOWE:
    _s = getattr(_st, _n, "")
    sprawdz("%-17s niesie marke" % _n, bool(_s) and config.MARKA in _s,
            _s[:70])
# I ZE NIE ZOSTALA GDZIES BEZIMIENNA FORMULKA. Samo „an anonymous editorial
# brand" w komunikacie systemowym znaczy, ze ten tor nie wie, dla kogo pisze.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
_bezimienne = [w.strip()[:66] for w in _zr.splitlines()
               if "an anonymous editorial" in w and "config.MARKA" not in w
               and not w.lstrip().startswith("#")]
sprawdz("zaden komunikat systemowy nie jest juz bezimienny",
        not _bezimienne, _bezimienne[:3])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
