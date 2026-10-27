# -*- coding: utf-8 -*-
"""Czujnik „co klika teraz” (27.10.2026): przebicia w publicznych archiwach czolowych AI-Substackow.

PO CO. Wlasciciel: wesprzec sledczego wyszukiwaniem watkow z juz napisanych artykulow, ktore sie klikaja, i
ekstrapolowaniem. Badanie z 25.10 dalo wagi kategorii; tu jest zywy sygnal i dziennik do uczenia. Test na atrapie
archiwum (bez sieci) pilnuje: przebicie liczone wzgledem MEDIANY publikacji (duze nie zaglusza malych), progi
(przebicie, minimum reakcji, okno dni), filtr AI, pominiecie platnych, limit, zapas 12 h, dziennik bez dubli
i ze awaria sieci lub czujnika daje pusta liste, nie wyjatek.

Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_co_klika.py
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import sledztwo   # noqa: E402

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


def dzis(dni_temu=0):
    return (datetime.now(timezone.utc) - timedelta(days=dni_temu)).isoformat()


def wpis(tytul, reakcje, dni_temu=1, **k):
    return dict({"title": tytul, "reaction_count": reakcje, "post_date": dzis(dni_temu), "audience": "everyone",
                 "canonical_url": "https://pub.example/p/" + tytul.lower().replace(" ", "-"), "comment_count": 3}, **k)


def archiwum_z(dane):
    def f(host):
        if isinstance(dane.get(host), BaseException):
            raise dane[host]
        return dane.get(host, [])
    return f


def tlo(n=10, baza=100):
    return [wpis("Older AI post %d" % i, baza, dni_temu=60 + i) for i in range(n)]


def odswiez():
    """Zapas 12 h kasujemy, zeby kazdy przypadek liczyl sie od zera."""
    try:
        (config.DATA_DIR / sledztwo.PLIK_CO_KLIKA_ZAPAS).unlink()
    except OSError:
        pass


HOSTY = sledztwo.SUBSTACKI_SYGNAL

print("=== 1. PRZEBICIE WZGLEDEM MEDIANY PUBLIKACJI ===")
odswiez()
dane = {
    HOSTY[0]: tlo() + [wpis("AI agents quietly rewrite how teams work", 420, 2),      # 4.2x mediany 100
                       wpis("A new AI benchmark nobody trusts", 90, 2),                # 0.9x — nie
                       wpis("AI paywalled deep dive", 900, 1, audience="only_paid")],  # platny — nie
    HOSTY[1]: tlo(baza=1000) + [wpis("AI model safety card read closely", 1700, 3),     # 1.7x mediany 1000
                                wpis("Gardening tips for spring", 5000, 1)],            # nie o AI — filtr
}
w, log = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
tyt = [e["temat"] for e in w]
sprawdz("przebija wpis 4,2x mediany, a 0,9x i wpis platny odpadaja", "AI agents quietly rewrite how teams work" in tyt
        and "A new AI benchmark nobody trusts" not in tyt and "AI paywalled deep dive" not in tyt, tyt)
sprawdz("duza publikacja nie zaglusza: 1,7x mediany 1000 (1700 reakcji) tez przebija, wpis nie o AI odpada",
        "AI model safety card read closely" in tyt and "Gardening tips for spring" not in tyt, tyt)
sprawdz("kolejnosc po sile przebicia; pozycja ma znacznik `sygnal`, `przebicie` i adres",
        w[0]["przebicie"] >= w[-1]["przebicie"] and "4.2x" in w[0]["sygnal"] and w[0]["url"].startswith("https://pub.example/"), w)
sprawdz("pozycja ma ksztalt pozycji korpusu (temat, kanal, data, rola) — wchodzi do rozkminy jak naglowek",
        all(k in w[0] for k in ("temat", "surowy", "kanal", "data", "url", "styk", "rola")), w[0].keys())

print()
print("=== 2. PROGI I OKNO ===")
odswiez()
dane = {HOSTY[0]: tlo() + [wpis("AI old breakout from last month", 900, 40),             # poza oknem 14 dni
                           wpis("AI tiny breakout", 30, 1),                              # ponizej minimum 40 reakcji
                           wpis("AI small publication gem", 120, 1)]}                    # 1.2x — ponizej progu 1.5
w, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
sprawdz("poza oknem dni, ponizej minimum reakcji i ponizej progu przebicia nic nie wchodzi", w == [], w)
odswiez()
dane = {HOSTY[0]: tlo(baza=20) + [wpis("AI small publication surprise", 45, 1)]}      # 2,25x mediany 20, 45 >= 40
w, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
sprawdz("mala publikacja: przebicie liczy sie wzgledem JEJ mediany, jesli reakcji jest co najmniej minimum", len(w) == 1, w)
odswiez()
dane = {HOSTY[0]: tlo(n=5) + [wpis("AI too few posts to judge", 900, 1)]}              # <8 wpisow: brak mediany
w, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
sprawdz("mniej niz osiem wpisow w archiwum = brak wiarygodnej mediany, pomijamy", w == [], w)
odswiez()
dane = {HOSTY[i]: tlo() + [wpis("AI breakout number %d" % i, 300 + i, 1)] for i in range(15)}   # 15 publikacji po jednym przebiciu
w, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
sprawdz("limit pozycji (12), najsilniejsze pierwsze", len(w) == 12 and w[0]["reakcje"] == 314 and w[-1]["reakcje"] == 303,
        [e["reakcje"] for e in w])

print()
print("=== 3. AWARIE, ZAPAS 12 h, DZIENNIK ===")
odswiez()
w, log = cicho(sledztwo.popularne_substack,
               archiwum=archiwum_z({HOSTY[0]: ConnectionError("siec"), HOSTY[1]: RuntimeError("x")}))
sprawdz("awaria archiwum pojedynczej publikacji nie wywraca reszty; wynik pusty, bez wyjatku", w == [], w)
odswiez()
try:
    (config.DATA_DIR / sledztwo.PLIK_CO_KLIKA).unlink()      # dziennik od zera (wczesniejsze przypadki tez do niego pisaly)
except OSError:
    pass
dane = {HOSTY[2]: tlo() + [wpis("AI breakout for the cache", 500, 1)]}
w1, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
w2, log2 = cicho(sledztwo.popularne_substack, archiwum=archiwum_z({}))     # atrapa pusta — gdyby pytal, wyszloby []
sprawdz("zapas 12 h: drugie wywolanie bierze z pliku, nie pyta publikacji", w1 and w2 == w1 and "z zapasu" in log2,
        (w1, w2, log2))
plik = config.DATA_DIR / sledztwo.PLIK_CO_KLIKA
wiersze = [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()]
sprawdz("dziennik `co_klika.jsonl` ma przebicie z data wykrycia i liczbami do pozniejszego uczenia",
        len(wiersze) == 1 and wiersze[0]["przebicie"] >= 1.5 and wiersze[0].get("wykryto") and wiersze[0]["mediana"] == 100,
        wiersze)
odswiez()
cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
wiersze2 = [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()]
sprawdz("ten sam wpis wykryty drugi raz nie dubluje sie w dzienniku", len(wiersze2) == 1, len(wiersze2))
odswiez()
w, log = cicho(sledztwo.popularne_substack, archiwum=lambda h: 1 / 0)
sprawdz("awaria archiwum w kazdej publikacji = pusta lista, nie wyjatek", w == [], (w, log))

print()
print("=== 3b. ETYKIETA KANALU (27.10: trzy `newsletter.*` zlewaly sie w „Substack newsletter”) ===")
nazwy = {h: sledztwo._nazwa_publikacji(h) for h in HOSTY}
sprawdz("kazda publikacja z listy ma wlasna nazwe (zadnych kolizji, zadnej nazwy-poddomeny)",
        len(set(nazwy.values())) == len(HOSTY) and not {"newsletter", "magazine", "www", "substack"} & set(nazwy.values()),
        {n: [h for h in HOSTY if nazwy[h] == n] for n in set(nazwy.values()) if list(nazwy.values()).count(n) > 1})
sprawdz("poddomena `newsletter.`/`magazine.` nie jest nazwa; `*.substack.com` daje pierwszy czlon; `www.` odpada",
        (nazwy["newsletter.semianalysis.com"], nazwy["magazine.sebastianraschka.com"], nazwy["thezvi.substack.com"],
         nazwy["www.oneusefulthing.org"], nazwy["newsletter.pragmaticengineer.com"])
        == ("semianalysis", "sebastianraschka", "thezvi", "oneusefulthing", "pragmaticengineer"), nazwy)
sprawdz("brzegi: wielkie litery, kropka na koncu, pusty adres i adres bez kropki nie rzucaja",
        (sledztwo._nazwa_publikacji("Newsletter.Example.COM."), sledztwo._nazwa_publikacji(""),
         sledztwo._nazwa_publikacji("localhost")) == ("example", "", "localhost"),
        (sledztwo._nazwa_publikacji("Newsletter.Example.COM."), sledztwo._nazwa_publikacji(""),
         sledztwo._nazwa_publikacji("localhost")))
odswiez()
dane = {"newsletter.semianalysis.com": tlo() + [wpis("AI chip supply breakout one", 400, 1)],
        "newsletter.pragmaticengineer.com": tlo() + [wpis("AI engineering breakout two", 410, 1)]}
w, _ = cicho(sledztwo.popularne_substack, archiwum=archiwum_z(dane))
sprawdz("pozycje z dwoch `newsletter.*` trafiaja do korpusu pod dwoma ROZNYMI kanalami",
        {e["kanal"] for e in w} == {"Substack semianalysis", "Substack pragmaticengineer"}, [e["kanal"] for e in w])

print()
print("=== 4. PODLACZENIE ===")
kod = open("agent-v2/artykul_z_puli.py", encoding="utf-8").read()
sprawdz("przebieg rozkminy dokleja przebicia do korpusu", "sledztwo.popularne_hn() + sledztwo.popularne_substack()" in kod)
wyb = open("agent-v2/prompts/rozkmina_wybor.md", encoding="utf-8").read()
sprawdz("prompt wyboru przeczuc tlumaczy znacznik breakout i zakazuje kopiowania ujecia",
        "[breakout:" in wyb and "never copy its angle" in wyb)
src = open("agent-v2/sledztwo.py", encoding="utf-8").read()
sprawdz("lista pozycji dla wyboru niesie `sygnal` obok naglowka", 'e["sygnal"]' in src)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
