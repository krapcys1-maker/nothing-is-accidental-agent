# -*- coding: utf-8 -*-
"""Pamiec „kogo obserwujemy" SCALA sie, zamiast przepisywac z obcietej listy (31.10.2026).

## Co bylo zepsute

`browser.odswiez_kogo_obserwujemy` przepisywala pamiec w calosci z zakladki
`/@my/following`, a ta oddaje tylko ok. 46 osob przy wiekszej liczbie
obserwowanych. Zmierzone 31.10.2026 na produkcji: w pamieci stalo 41 uchwytow,
a bot zaobserwowal 134. Wszystko, co `obserwuj_profil` dopisal po drodze
(`zapamietaj_obserwowanego`), znikalo przy najblizszym przebiegu i to samo
konto wracalo do losowania — od 1.10 ok. 130 wejsc na profil zakonczonych
„juz obserwujemy".

## Czego pilnuje ten test

1. Cykl, ktory byl bledem: konto dopisane po drodze PRZEZYWA odswiezenie
   z listy, ktorej to konto nie zawiera.
2. Zakladka tylko DOPISUJE; pierwszy zapisany czas konta zostaje.
3. Dziennik odtwarza pamiec: udana `obserwacja` i `obserwacja_pominieta` z powodem
   „juz obserwujemy ..." — ale NIE pominiecia za duzych kont, nieudane proby ani
   „nie ustalilem konta".
4. Pusta zakladka nie kasuje pamieci (jak dotad), a dziennik i tak ja uzupelnia.
5. Awaria odczytu zakladki: `None`, pamiec bez zmian.
6. Mapa host -> uchwyt zostaje (nie wypada razem z uchwytem, ktorego nie ma na liscie).
7. Brak dziennika i uszkodzone linie niczego nie przerywaja; odswiezenie jest
   idempotentne.

Bez sieci i bez przegladarki; pamiec i dziennik sa tymczasowe, produkcyjne pliki
tylko czytane (odciski na koncu).
"""
import hashlib
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import browser   # noqa: E402
import config    # noqa: E402

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


PILNOWANE = [config.DATA_DIR / "kogo_obserwujemy.json", config.DATA_DIR / "dziennik.jsonl"]
PRZED = {str(p): odcisk(p) for p in PILNOWANE}

KAT = pathlib.Path(tempfile.mkdtemp())
PAMIEC = KAT / "kogo_obserwujemy.json"
DZIENNIK = KAT / "dziennik.jsonl"


# --- ATRAPA STRONY: zakladka /following z lista uchwytow --------------------------
class Link:
    def __init__(self, uchwyt):
        self._u = uchwyt

    def get_attribute(self, _):
        return "/@%s" % self._u

    def inner_text(self):
        return self._u.upper()


class Lokator:
    def __init__(self, linki):
        self._l = linki

    def all(self):
        return self._l


class Strona:
    def __init__(self, uchwyty, wybuch=None):
        self._u, self._wybuch = uchwyty, wybuch

    def goto(self, *a, **k):
        if self._wybuch:
            raise self._wybuch

    def wait_for_timeout(self, _ms):
        pass

    def locator(self, _selektor):
        return Lokator([Link(u) for u in self._u])


def dziennik(*wpisy):
    DZIENNIK.write_text("".join(json.dumps(w, ensure_ascii=False) + "\n" for w in wpisy),
                        encoding="utf-8")


def pamiec():
    return json.loads(PAMIEC.read_text(encoding="utf-8"))


def w(rodzaj, komu, udane=True, powod=None, kiedy="2026-10-10T10:00:00+00:00"):
    out = {"kiedy": kiedy, "rodzaj": rodzaj, "udane": udane, "komu": komu}
    if powod:
        out["powod"] = powod
    return out


stare = (browser.OBSERWOWANI, browser.DZIENNIK)
browser.OBSERWOWANI, browser.DZIENNIK = PAMIEC, DZIENNIK
try:
    print("=== 1. CYKL, KTORY BYL BLEDEM ===")
    dziennik()
    browser.zapamietaj_obserwowanego("dopisany_po_drodze", host="dopisany.example")
    sprawdz("po `zapamietaj_obserwowanego` konto jest w pamieci",
            "dopisany_po_drodze" in pamiec()["uchwyty"])
    ilu = browser.odswiez_kogo_obserwujemy(Strona(["a", "b", "c"]))
    sprawdz("po odswiezeniu z listy BEZ tego konta ono PRZEZYWA (stary kod je kasowal)",
            "dopisany_po_drodze" in pamiec()["uchwyty"], sorted(pamiec()["uchwyty"]))
    sprawdz("lista z zakladki zostala dopisana",
            {"a", "b", "c"} <= set(pamiec()["uchwyty"]), sorted(pamiec()["uchwyty"]))
    sprawdz("zwraca liczbe ZNANYCH kont po scaleniu (4), nie liczbe z listy (3)", ilu == 4, ilu)
    sprawdz("mapa host -> uchwyt zostaje, choc uchwytu nie ma na liscie",
            pamiec()["hosty"].get("dopisany.example") == "dopisany_po_drodze", pamiec()["hosty"])
    sprawdz("`czy_juz_obserwujemy` widzi to konto po hoscie",
            browser.czy_juz_obserwujemy("dopisany.example") is True)

    print()
    print("=== 2. ZAKLADKA TYLKO DOPISUJE; PIERWSZY CZAS ZOSTAJE ===")
    # LITERALNY STARY CZAS, nie odczyt „przed": zapis ma dokladnosc do sekundy,
    # a test dziala krocej, wiec kod nadpisujacy czas „teraz" dawal ten sam napis
    # i test przechodzil albo nie zaleznie od zegara.
    pierwszy = "2026-01-02T03:04:05+00:00"
    wpis_pamieci = pamiec()
    wpis_pamieci["uchwyty"]["a"] = pierwszy
    PAMIEC.write_text(json.dumps(wpis_pamieci), encoding="utf-8")
    browser.odswiez_kogo_obserwujemy(Strona(["a", "d"]))
    p = pamiec()
    sprawdz("nowe konto z zakladki dopisane", "d" in p["uchwyty"])
    sprawdz("poprzednie konta (b, c) zostaja mimo ze zakladka ich juz nie oddala",
            {"b", "c"} <= set(p["uchwyty"]), sorted(p["uchwyty"]))
    sprawdz("pierwszy zapisany czas konta zostaje", p["uchwyty"]["a"] == pierwszy,
            (p["uchwyty"]["a"], pierwszy))
    sprawdz("`zrzut` mowi, kiedy ostatnio czytalismy zakladke", bool(p["zrzut"]))

    print()
    print("=== 3. DZIENNIK ODTWARZA PAMIEC ===")
    PAMIEC.unlink()
    dziennik(
        w("obserwacja", "zaobserwowany_przez_bota"),
        w("obserwacja", "z_malpa", kiedy="2026-10-11T10:00:00+00:00"),
        w("obserwacja_pominieta", "juz_mielismy",
          powod="juz obserwujemy juz_mielismy — menu pokazuje 'Unfollow'"),
        w("obserwacja_pominieta", "za_duze_konto",
          powod="account exceeds the size limit or its size is unknown"),
        w("obserwacja", "nieudana", udane=False),
        w("obserwacja_pominieta", "www.jakis.host", powod="nie ustalilem konta autora dla www.jakis.host"),
        w("komentarz", "nie_obserwacja"),
        {"kiedy": "2026-10-12T10:00:00+00:00", "rodzaj": "obserwacja", "udane": True},   # bez `komu`
    )
    browser.odswiez_kogo_obserwujemy(Strona(["z_listy"]))
    u = pamiec()["uchwyty"]
    sprawdz("udana `obserwacja` wraca do pamieci", "zaobserwowany_przez_bota" in u, sorted(u))
    sprawdz("`@` w uchwycie nie psuje klucza", "z_malpa" in u)
    sprawdz("pominiecie „juz obserwujemy ...\" wraca do pamieci", "juz_mielismy" in u)
    sprawdz("pominiecie ZA DUZE konto NIE wraca (nie obserwujemy go)", "za_duze_konto" not in u)
    sprawdz("nieudana proba NIE wraca", "nieudana" not in u)
    sprawdz("„nie ustalilem konta\" NIE wraca (to host, nie uchwyt)",
            "www.jakis.host" not in u)
    sprawdz("inny rodzaj wpisu NIE wraca", "nie_obserwacja" not in u)
    sprawdz("wpis bez `komu` nie wprowadza pustego uchwytu", "" not in u, sorted(u))
    sprawdz("lista z zakladki tez jest", "z_listy" in u)
    sprawdz("czas z dziennika zostaje przy koncie", u["z_malpa"] == "2026-10-11T10:00:00+00:00",
            u.get("z_malpa"))

    print()
    print("=== 4. PUSTA ZAKLADKA NIE KASUJE PAMIECI, DZIENNIK UZUPELNIA ===")
    # STARY, LITERALNY ZNACZNIK: `zrzut` jest zapisywany z dokladnoscia do sekundy,
    # a test dziala krocej — porownanie z prawdziwym „przed" przechodzilo takze
    # wtedy, gdy kod przesuwal `zrzut` na „teraz" (mutacja O9 przezyla).
    zrzut_przed = "2026-01-01T00:00:00+00:00"
    wpis_pamieci = pamiec()
    wpis_pamieci["zrzut"] = zrzut_przed
    PAMIEC.write_text(json.dumps(wpis_pamieci), encoding="utf-8")
    przed = pamiec()
    ilu0 = browser.odswiez_kogo_obserwujemy(Strona([]))
    sprawdz("pusta zakladka -> 0, pamiec bez zmian",
            ilu0 == 0 and pamiec()["uchwyty"] == przed["uchwyty"], ilu0)
    sprawdz("`zrzut` NIE jest przesuwany, gdy zakladki nie czytalismy",
            pamiec()["zrzut"] == zrzut_przed)
    dziennik(w("obserwacja", "nowy_z_dziennika"))
    ilu1 = browser.odswiez_kogo_obserwujemy(Strona([]))
    sprawdz("pusta zakladka, ale dziennik zna nowe konto -> trafia do pamieci",
            ilu1 == 0 and "nowy_z_dziennika" in pamiec()["uchwyty"]
            and "z_listy" in pamiec()["uchwyty"], pamiec()["uchwyty"].keys())
    sprawdz("   ... a `zrzut` nadal stoi w miejscu", pamiec()["zrzut"] == zrzut_przed)

    print()
    print("=== 5. AWARIA ZAKLADKI ===")
    przed = PAMIEC.read_text(encoding="utf-8")
    wynik = browser.odswiez_kogo_obserwujemy(Strona(["x"], wybuch=RuntimeError("net::ERR")))
    sprawdz("wyjatek przy odczycie -> None", wynik is None, wynik)
    sprawdz("pamiec bez zmian", PAMIEC.read_text(encoding="utf-8") == przed)

    print()
    print("=== 6. BRZEGI: BRAK DZIENNIKA, USZKODZONE LINIE, IDEMPOTENCJA ===")
    DZIENNIK.unlink()
    PAMIEC.unlink()
    ilu = browser.odswiez_kogo_obserwujemy(Strona(["a", "b"]))
    sprawdz("brak dziennika nie przerywa odswiezenia", ilu == 2 and set(pamiec()["uchwyty"]) == {"a", "b"},
            (ilu, pamiec()["uchwyty"]))
    DZIENNIK.write_text('{"rodzaj": "obserwacja", "udane": true, "komu": "ok1"}\n'
                        '{to nie jest json "obserwacja"\n'
                        '"obserwacja" tylko tekst\n'
                        '{"rodzaj": "obserwacja", "udane": true, "komu": "ok2"}\n', encoding="utf-8")
    browser.odswiez_kogo_obserwujemy(Strona(["a"]))
    sprawdz("uszkodzone linie dziennika sa pomijane, dobre czytane",
            {"ok1", "ok2"} <= set(pamiec()["uchwyty"]), sorted(pamiec()["uchwyty"]))
    p1 = pamiec()["uchwyty"]
    browser.odswiez_kogo_obserwujemy(Strona(["a"]))
    sprawdz("drugie odswiezenie niczego nie zmienia (idempotentne)", pamiec()["uchwyty"] == p1)

    print()
    print("=== 7. FUNKCJA POMOCNICZA I ZRODLO ===")
    dziennik(w("obserwacja", "@zmalpa2"), w("obserwacja", "  spacje  "),
             w("obserwacja_pominieta", "x", powod="juz obserwujemy x — menu pokazuje 'Unfollow'"),
             w("obserwacja_pominieta", "y", powod="inny powod juz obserwujemy"))
    z = browser._obserwowani_z_dziennika()
    sprawdz("`@` i spacje zdjete z uchwytow", {"zmalpa2", "spacje", "x"} == set(z), sorted(z))
    sprawdz("powod musi ZACZYNAC sie od „juz obserwujemy\" (nie tylko zawierac)", "y" not in z)
    zrodlo = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
    sprawdz("odswiezenie nie przepisuje juz pamieci z samej listy",
            "swiezi = {x[\"uchwyt\"]" not in zrodlo)
finally:
    browser.OBSERWOWANI, browser.DZIENNIK = stare

print()
print("=== PRODUKCJA: bez zmian ===")
zle = 0
for p in PILNOWANE:
    ok_p = odcisk(p) == PRZED[str(p)]
    zle += 0 if ok_p else 1
    print("  %-26s %s" % (pathlib.Path(p).name, "bez zmian" if ok_p else "ZMIENIONA"))

print()
print("=== WYNIK: %d zdanych, %d oblanych%s ===" %
      (zdane, oblane, ", PRODUKCJA RUSZONA" if zle else ""))
sys.exit(1 if (oblane or zle) else 0)
