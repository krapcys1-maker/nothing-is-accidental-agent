# -*- coding: utf-8 -*-
"""Ktore zrodla „o ludziach" naprawde dzialaja z NASZEGO serwera. Za darmo.

PO CO. Raport `docs/WYBOR_TEMATOW_2026-09-26.md` proponuje nowe zrodla
tematow: praca, zdrowie, szkola, pieniadze, prawo. Adresy pochodza
z wyszukiwarki, nie z pobrania, bo kontener, w ktorym powstal raport, nie ma
wyjscia do sieci. A regula spod `korpus_kanalow.KANALY` mowi wprost: kod
odpowiedzi nie jest sprawdzeniem. Sprawdzeniem jest tytul feedu i data
ostatniego wpisu. Dwa adresy z listy (KFF Health News, Rest of World) mialy we
wrzesniu zgloszone awarie w publicznym rejestrze feedow, wiec zgadywanie nie
wystarczy.

CO MIERZY, dla kazdego kandydata:
  - czy odpowiada i czy w ogole jest feedem,
  - czy przeczyta go NASZ parser z `korpus_kanalow` (RSS 1.0/RDF by nie przeszedl
    i korpus dostalby po cichu zero wpisow),
  - date najnowszego wpisu i liczbe wpisow z ostatnich 30 dni,
  - ile z nich jest o AI, liczone tym samym darmowym filtrem, ktory proponuje
    raport,
  - trzy przykladowe tytuly o AI, zeby czlowiek ocenil, czy to material.

DWA DODATKOWE ODCZYTY, oba do tego samego raportu:
  - SKLAD SPIZARNI: ktore osiem tekstow skaut dostalby TERAZ. Wolamy
    produkcyjne `korpus_kanalow` i `tresc_zrodel`, z wylaczonym zapisem stanu
    kanalow — to jest bezposredni sprawdzian diagnozy „8 miejsc, 4 blogi".
  - KOSZT WYBORU TEMATOW z ostatnich 30 dni, z bazy otwartej tylko do odczytu,
    tylko przebiegi produkcyjne (ta sama definicja co `karta_wynikow.koszt`).

NIC NIE KOSZTUJE: zero wywolan modelu, zero zapisow na dysk. Kilkadziesiat
zapytan HTTP, okolo minuty.

URUCHAMIANIE, z korzenia repozytorium, NA SERWERZE (z kontenera sie nie da):
    .venv/bin/python agent-v2/pomiary/zrodla_ludzie.py
    .venv/bin/python agent-v2/pomiary/zrodla_ludzie.py --kontakt adres@domena
`--kontakt` dokleja adres do User-Agent. SEC wymaga kontaktu w naglowku
i bez niego potrafi odpowiedziec 403.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config          # noqa: E402
import korpus_kanalow  # noqa: E402

OKNO_DNI = 30

# FILTR AI — ten sam, ktory raport proponuje dla feedow ogolnych (KFF, SEC,
# FTC). Celowo bez slowa „algorithm": w komunikatach SEC to najczesciej handel
# algorytmiczny, a nie to, o czym piszemy.
FILTR_AI = re.compile(
    r"\b(AI|A\.I\.|artificial intelligence|machine learning|chatbots?|"
    r"ChatGPT|OpenAI|Anthropic|Claude|Gemini|Copilot|LLMs?|"
    r"large language models?|generative|deepfakes?|facial recognition|"
    r"automated decision[- ]making|neural networks?)\b",
    re.IGNORECASE)

# SLAD CZLOWIEKA — czy tytul mowi o kims, kogo AI dotyka. Tylko pomiar,
# niczego nie odrzuca: raport potrzebuje wiedziec, ile takich tytulow daje
# zrodlo, a nie zgadywac.
SLAD_CZLOWIEKA = re.compile(
    r"\b(workers?|employees?|jobs?|wages?|hiring|students?|teachers?|schools?|"
    r"children|kids|teens?|parents?|patients?|doctors?|nurses?|hospitals?|"
    r"consumers?|customers?|users?|voters?|courts?|judges?|lawyers?|"
    r"attorneys?|tenants?|drivers?|families|people|americans|adults)\b",
    re.IGNORECASE)

FEDREG_API = "https://www.federalregister.gov/api/v1/documents.json"

# KANDYDACI: nazwa, styk, adresy do sprobowania po kolei, rodzaj, uwaga.
# `styk` to miejsce, w ktorym AI dotyka czytelnika. Zrodlo niesie go samo,
# wiec kod nie musi pytac modelu, o czym jest fakt.
KANDYDACI = [
    ("NBER, nowe prace", "praca",
     ["https://www.nber.org/papers.rss"], "rss", ""),
    ("NBER, Labor Studies", "praca",
     ["https://www.nber.org/programs/ls/papers.rss"], "rss", ""),
    ("arXiv cs.CY (komputery i spoleczenstwo)", "ludzie",
     ["https://rss.arxiv.org/rss/cs.CY"], "rss", "w weekendy pusty"),
    ("arXiv cs.HC (czlowiek i komputer)", "ludzie",
     ["https://rss.arxiv.org/rss/cs.HC"], "rss", "w weekendy pusty"),
    ("FTC, komunikaty", "pieniadze",
     ["https://www.ftc.gov/feeds/press-release.xml"], "rss", ""),
    ("FTC, ochrona konsumenta", "pieniadze",
     ["https://www.ftc.gov/feeds/press-release-consumer-protection.xml"],
     "rss", ""),
    ("SEC, komunikaty", "pieniadze",
     ["https://www.sec.gov/news/pressreleases.rss"], "rss",
     "wymaga kontaktu w User-Agent (--kontakt)"),
    ("Federal Register, dokumenty o AI", "prawo", [FEDREG_API], "fedreg",
     "juz jest w kodzie jako `korpus_fedreg`, ale bez filtra na AI"),
    ("CourtListener, orzeczenia o AI", "prawo",
     ["https://www.courtlistener.com/feed/search/"
      "?q=%22artificial+intelligence%22&type=o",
      "https://www.courtlistener.com/feed/search/"
      "?q=%22artificial+intelligence%22"], "rss", "format adresu z dokumentacji"),
    ("KFF Health News", "zdrowie",
     ["https://kffhealthnews.org/feed/"], "rss",
     "rejestr feedow zglaszal awarie we wrzesniu 2026"),
    ("Pew Research Center", "codziennosc",
     ["https://www.pewresearch.org/feed/"], "rss", ""),
    ("EdSurge", "szkola",
     ["https://www.edsurge.com/articles_rss"], "rss", ""),
    ("The 74 (szkoly w USA)", "szkola",
     ["https://www.the74million.org/feed/"], "rss", ""),
    ("Rest of World", "praca",
     ["https://restofworld.org/feed/latest", "https://restofworld.org/feed/"],
     "rss", "rejestr feedow zglaszal awarie we wrzesniu 2026"),
    ("Tech Policy Press", "prawo",
     ["https://www.techpolicy.press/feed/", "https://www.techpolicy.press/rss/"],
     "rss", "adres niepotwierdzony"),
    # ZBIORY DANYCH — nie feed, tylko strona z plikiem. Mierzymy, czy strona
    # odpowiada i czy da sie z niej wyciagnac adres pliku. Wlasciwe czytanie
    # (roznica tydzien do tygodnia) to etap 2 raportu.
    ("Baza orzeczen o zmyslonych cytatach (Charlotin)", "prawo",
     ["https://www.damiencharlotin.com/hallucinations/"], "dane", "CSV, CC BY 4.0"),
    ("FDA, urzadzenia medyczne z AI", "zdrowie",
     ["https://www.fda.gov/medical-devices/software-medical-device-samd/"
      "artificial-intelligence-enabled-medical-devices"], "dane", ""),
]

# JUZ W KORPUSIE, ale o ludziach — raport proponuje oznaczyc je stykiem.
# Adresy bierzemy z kodu, zeby pomiar sprawdzal to, co naprawde chodzi.
JUZ_W_KORPUSIE = (("Wpadki AI", "szkody"), ("Komisja UE", "prawo"),
                  ("Transformer", "prawo"))


def _lokalna(znacznik: str) -> str:
    """Nazwa znacznika bez przestrzeni nazw: `{http://...}item` -> `item`."""
    return znacznik.rsplit("}", 1)[-1]


def _dziecko(e: ET.Element, *nazwy: str) -> str:
    for d in e:
        if _lokalna(d.tag) in nazwy:
            if _lokalna(d.tag) == "link" and d.get("href"):
                return d.get("href") or ""
            return (d.text or "").strip()
    return ""


def _na_date(surowa: str) -> str:
    """RRRR-MM-DD z ISO (Atom, dc:date) albo RFC 822 (RSS 2.0)."""
    s = (surowa or "").strip()
    if s[:4].isdigit():
        return s[:10]
    try:
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return ""


def wpisy_feedu(xml: str) -> tuple[str, list[dict[str, str]]]:
    """Tytul feedu i wpisy — dla Atoma, RSS 2.0 i RSS 1.0 (RDF) naraz.

    Celowo NIE ten sam kod co w `korpus_kanalow`: tamten szuka `a:entry`
    albo golego `item`, wiec RDF (item w przestrzeni nazw RSS 1.0) daje mu
    zero wpisow. Ten parser ma zobaczyc wszystko, zeby porownanie z tamtym
    pokazalo roznice.
    """
    korzen = ET.fromstring(xml.encode("utf-8"))
    tytul = ""
    for e in korzen.iter():
        if _lokalna(e.tag) == "title":
            tytul = (e.text or "").strip()
            break
    out = []
    for e in korzen.iter():
        if _lokalna(e.tag) not in ("item", "entry"):
            continue
        out.append({
            "tytul": " ".join(_dziecko(e, "title").split()),
            "data": _na_date(_dziecko(e, "published", "updated", "pubDate",
                                      "date")),
            "url": _dziecko(e, "link"),
            "opis": " ".join(_dziecko(e, "summary", "description").split())[:400],
        })
    return tytul, out


def czyta_korpus(xml: str) -> int:
    """Ile wpisow zobaczy PRODUKCYJNY parser (`korpus_kanalow`)."""
    try:
        korzen = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        return 0
    poz = (korzen.findall(".//a:entry", korpus_kanalow.NS)
           or korzen.findall(".//item"))
    return sum(1 for e in poz if korpus_kanalow._data_wpisu(e))


def ocen_feed(xml: str, dzis: datetime) -> dict:
    """Czysta funkcja: tresc feedu -> liczby do decyzji. Bez sieci."""
    tytul, wpisy = wpisy_feedu(xml)
    prog = (dzis - timedelta(days=OKNO_DNI)).strftime("%Y-%m-%d")
    w_oknie = [w for w in wpisy if w["data"] and w["data"] >= prog]
    o_ai = [w for w in w_oknie
            if FILTR_AI.search("%s %s" % (w["tytul"], w["opis"]))]
    z_czlowiekiem = [w for w in o_ai if SLAD_CZLOWIEKA.search(w["tytul"])]
    najnowszy = max((w["data"] for w in wpisy if w["data"]), default="")
    if not wpisy:
        stan = "NIE FEED"
    elif not najnowszy or najnowszy < prog:
        stan = "MARTWY"
    elif not o_ai:
        stan = "BEZ AI"
    else:
        stan = "DZIALA"
    return {"stan": stan, "tytul_feedu": tytul, "wpisow": len(wpisy),
            "najnowszy": najnowszy, "w_oknie": len(w_oknie), "o_ai": len(o_ai),
            "z_czlowiekiem": len(z_czlowiekiem),
            "korpus_czyta": czyta_korpus(xml),
            "przyklady": [w["tytul"][:96] for w in o_ai[:3]]}


def ocen_fedreg(dane: dict, dzis: datetime) -> dict:
    prog = (dzis - timedelta(days=OKNO_DNI)).strftime("%Y-%m-%d")
    wyniki = dane.get("results") or []
    w_oknie = [d for d in wyniki if str(d.get("publication_date", "")) >= prog]
    rodzaje: dict[str, int] = {}
    for d in w_oknie:
        rodzaje[str(d.get("type"))] = rodzaje.get(str(d.get("type")), 0) + 1
    return {"stan": "DZIALA" if w_oknie else "BEZ AI",
            "tytul_feedu": "Federal Register API, term=artificial intelligence",
            "wpisow": len(wyniki),
            "najnowszy": max((str(d.get("publication_date", "")) for d in wyniki),
                             default=""),
            "w_oknie": len(w_oknie), "o_ai": len(w_oknie),
            "z_czlowiekiem": sum(1 for d in w_oknie
                                 if SLAD_CZLOWIEKA.search(d.get("title") or "")),
            "korpus_czyta": -1, "rodzaje": rodzaje,
            "przyklady": [str(d.get("title") or "")[:96] for d in w_oknie[:3]]}


def ocen_strone_z_danymi(html: str) -> dict:
    pliki = sorted(set(re.findall(
        r"""href=["']([^"']+\.(?:csv|xlsx?|json)(?:\?[^"']*)?)["']""", html,
        re.IGNORECASE)))
    return {"stan": "DZIALA" if pliki else "BEZ PLIKU",
            "tytul_feedu": "strona z plikiem danych", "wpisow": len(pliki),
            "najnowszy": "", "w_oknie": 0, "o_ai": 0, "z_czlowiekiem": 0,
            "korpus_czyta": -1, "przyklady": pliki[:3]}


def zmierz(klient, nazwa: str, styk: str, adresy: list[str], rodzaj: str,
           dzis: datetime) -> dict:
    ostatni_blad = ""
    for adres in adresy:
        try:
            if rodzaj == "fedreg":
                r = klient.get(adres, params={
                    "per_page": 100, "order": "newest",
                    "conditions[term]": '"artificial intelligence"',
                    "fields[]": ["title", "publication_date", "html_url",
                                 "type"]})
            else:
                r = klient.get(adres)
        except Exception as exc:
            ostatni_blad = type(exc).__name__
            continue
        if r.status_code != 200:
            ostatni_blad = "HTTP %s" % r.status_code
            continue
        try:
            if rodzaj == "fedreg":
                wynik = ocen_fedreg(r.json(), dzis)
            elif rodzaj == "dane":
                wynik = ocen_strone_z_danymi(r.text)
            else:
                wynik = ocen_feed(r.text, dzis)
        except Exception as exc:
            ostatni_blad = "nieczytelne (%s)" % type(exc).__name__
            continue
        wynik.update({"nazwa": nazwa, "styk": styk, "adres": adres})
        return wynik
    return {"nazwa": nazwa, "styk": styk, "adres": adresy[0],
            "stan": "BLOKADA", "blad": ostatni_blad, "wpisow": 0,
            "najnowszy": "", "w_oknie": 0, "o_ai": 0, "z_czlowiekiem": 0,
            "korpus_czyta": -1, "przyklady": []}


# ZRODLA W KORPUSIE, KTORE NIE SA BRANZA. Reszta `ZRODLA` to laboratoria,
# wydania bibliotek, strony awarii, blogi i podcasty o AI.
NIE_BRANZA = {n: s for n, s in JUZ_W_KORPUSIE}

# ETAPY, KTORE SKLADAJA SIE NA WYBOR TEMATU — nie na pisanie notki.
ETAPY_WYBORU = ("curiosity", "bank", "parowanie", "powtorka", "fedreg")


def sklad_spizarni() -> None:
    """Ktore osiem tekstow skaut dostalby teraz — produkcyjnym kodem."""
    import tresc_zrodel

    # STAN KANALOW CZYTAMY, ALE GO NIE ZMIENIAMY. Te trzy funkcje zapisuja
    # zapas tresci i licznik porazek; pomiar ma zostawic dysk nietkniety.
    for nazwa in ("_zapamietaj_tresc", "_zapisz_porazke", "_zapisz_sukces"):
        setattr(korpus_kanalow, nazwa, lambda *a, **k: None)
    korpus = korpus_kanalow.korpus_kanalow(30)
    z_youtube = sum(1 for w in korpus if "youtu" in str(w.get("url") or ""))
    teksty = tresc_zrodel.tresci_zrodel(korpus)
    print("\n" + "=" * 96)
    print("SKLAD SPIZARNI TERAZ: %d wpisow korpusu (z tego YouTube, ktorego"
          " spizarnia nie czyta: %d) -> %d tekstow z %d zrodel"
          % (len(korpus), z_youtube, len(teksty),
             len({t["kanal"] for t in teksty})))
    for t in teksty:
        print("   %s  %-16s %-8s %s" % (t["data"], t["kanal"][:16],
                                       NIE_BRANZA.get(t["kanal"], "branza"),
                                       t["temat"][:60]))
    print("   Przy niepustej spizarni skaut NIE SZUKA w sieci"
          " (`web_search = not _tresc` w `stages.znajdz_ciekawostki`).")


def koszt_wyboru(dni: int = 30) -> None:
    """Koszt etapow wyboru tematu, tylko przebiegi produkcyjne, tylko odczyt."""
    baza = Path(config.DB_PATH)
    print("\n" + "=" * 96)
    if not baza.exists():
        print("KOSZT: brak bazy %s" % baza)
        return
    od = (datetime.now(timezone.utc) - timedelta(days=dni)).strftime("%Y-%m-%d")
    conn = sqlite3.connect("file:%s?mode=ro" % baza, uri=True)
    try:
        wiersze = conn.execute(
            "SELECT c.purpose, COUNT(*), COALESCE(SUM(c.cost_usd), 0) "
            "FROM calls c JOIN runs r ON r.id = c.run_id "
            "WHERE r.tryb = 'produkcja' AND substr(c.at, 1, 10) >= ? "
            "GROUP BY c.purpose ORDER BY 3 DESC", (od,)).fetchall()
    finally:
        conn.close()
    razem = sum(w[2] for w in wiersze)
    wybor = [w for w in wiersze if w[0] in ETAPY_WYBORU]
    suma = sum(w[2] for w in wybor)
    print("KOSZT WYBORU TEMATU, %d dni od %s (produkcja):" % (dni, od))
    for etap, ile, usd in wybor:
        print("   %-10s %5d wywolan  %7.3f USD" % (etap, ile, usd))
    print("   razem wybor tematu: %.3f USD z %.3f USD calego rachunku (%.0f%%)"
          % (suma, razem, 100 * suma / razem if razem else 0))


def main(argv=None) -> int:
    import httpx

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--kontakt", default="",
                   help="adres e-mail doklejany do User-Agent (SEC go wymaga)")
    a = p.parse_args(argv)
    try:
        koszt_wyboru()
    except Exception as exc:
        print("KOSZT: nie odczytalem (%s)" % type(exc).__name__)
    try:
        sklad_spizarni()
    except Exception as exc:
        print("SPIZARNIA: nie odczytalem (%s)" % type(exc).__name__)
    ua = config.FETCH_USER_AGENT
    if a.kontakt:
        ua = "%s %s" % (ua, a.kontakt)
    dzis = datetime.now(timezone.utc)
    lista = list(KANDYDACI) + [
        ("%s (juz w korpusie)" % n, s, [korpus_kanalow.ZRODLA[n]], "rss", "")
        for n, s in JUZ_W_KORPUSIE if n in korpus_kanalow.ZRODLA]
    wyniki = []
    with httpx.Client(timeout=config.FETCH_TIMEOUT_S, follow_redirects=True,
                      headers={"User-Agent": ua}) as klient:
        for nazwa, styk, adresy, rodzaj, uwaga in lista:
            w = zmierz(klient, nazwa, styk, adresy, rodzaj, dzis)
            w["uwaga"] = uwaga
            wyniki.append(w)
            print("\n== %s  [%s]  %s" % (w["nazwa"], w["styk"], w["stan"]))
            print("   adres: %s" % w["adres"])
            if w.get("blad"):
                print("   blad: %s" % w["blad"])
            if w.get("tytul_feedu"):
                print("   feed: %s" % w["tytul_feedu"][:80])
            if w["stan"] not in ("BLOKADA",):
                print("   wpisow %d, najnowszy %s, z %d dni: %d, o AI: %d,"
                      " o AI z czlowiekiem w tytule: %d"
                      % (w["wpisow"], w["najnowszy"] or "?", OKNO_DNI,
                         w["w_oknie"], w["o_ai"], w["z_czlowiekiem"]))
            if w.get("rodzaje"):
                print("   rodzaje dokumentow: %s" % w["rodzaje"])
            if w["korpus_czyta"] == 0 and w["wpisow"]:
                print("   UWAGA: parser `korpus_kanalow` zobaczy tu ZERO wpisow"
                      " — przed dopisaniem trzeba go rozszerzyc")
            for t in w["przyklady"]:
                print("   · %s" % t)
            if uwaga:
                print("   (%s)" % uwaga)
            time.sleep(0.4)

    print("\n" + "=" * 96)
    print("%-44s %-11s %-9s %-10s %6s %5s %6s"
          % ("zrodlo", "styk", "stan", "najnowszy", "%d dni" % OKNO_DNI,
             "o AI", "czlow."))
    for w in wyniki:
        print("%-44s %-11s %-9s %-10s %6d %5d %6d"
              % (w["nazwa"][:44], w["styk"], w["stan"], w["najnowszy"] or "-",
                 w["w_oknie"], w["o_ai"], w["z_czlowiekiem"]))
    dziala = [w for w in wyniki if w["stan"] == "DZIALA"
              and w["korpus_czyta"] != 0]
    nowe = [w for w in dziala if "(juz w korpusie)" not in w["nazwa"]]
    stare = [w for w in dziala if "(juz w korpusie)" in w["nazwa"]]
    print("\nDO DOPISANIA DO `ZRODLA_LUDZIE` (dziala z tego serwera, ma AI"
          " w ostatnich %d dniach, korpus go przeczyta): %d"
          % (OKNO_DNI, len(nowe)))
    for w in nowe:
        print("    %r: {\"url\": %r, \"styk\": %r}," % (w["nazwa"], w["adres"],
                                                      w["styk"]))
    if stare:
        print("\nJUZ W KORPUSIE, DO OZNACZENIA STYKIEM: %s"
              % ", ".join("%s -> %s" % (w["nazwa"].split(" (")[0], w["styk"])
                          for w in stare))
    return 0


if __name__ == "__main__":
    sys.exit(main())
