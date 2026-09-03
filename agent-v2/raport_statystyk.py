"""Co przyniosla kazda notka, restack i artykul — do czytania przez czlowieka.

Statystyki lezą w `data/statystyki.jsonl` jako historia pomiarow. Ten plik
zamienia je w tabele, ktora odpowiada na pytania wlasciciela:

    ile wejsc mial ten wpis
    ile polubien i komentarzy z tego wyszlo
    ilu ludzi z TEGO wpisu zaczelo subskrybowac albo obserwowac

DLACZEGO OSOBNY PLIK, A NIE WYDRUK W PRZEBIEGU: przebieg drukuje raz i ginie.
Licznik `zrobione` w run.py zyl dokladnie tak i przez dwa tygodnie nikt nie
wiedzial, ze polowa dzialan nie wychodzi. Raport ma dac sie odpalic kiedykolwiek,
bez przebiegu i bez przegladarki.

Uruchomienie:
    python agent-v2/raport_statystyk.py
    python agent-v2/raport_statystyk.py notka
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import statystyki  # noqa: E402


def _skrot(tekst: str, ile: int = 46) -> str:
    t = " ".join(str(tekst or "").split())
    return (t[: ile - 1] + "…") if len(t) > ile else t


# Dzien, w ktorym konto przestalo pisac o ukrytych systemach w zwyklych
# rzeczach, a zaczelo o AI. Wszystko starsze opisuje INNA publikacje i
# mieszanie tego z dzisiejszym stanem juz raz doprowadzilo do zlej decyzji.
PIVOT = "2026-08-25"

POLA = ("wyswietlenia", "polubienia", "odpowiedzi", "restacki",
        "subskrypcje", "obserwacje", "klikniecia_w_link")


def _mediana(liczby: list[int]) -> float:
    if not liczby:
        return 0.0
    s = sorted(liczby)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def dwie_epoki(najnowsze: dict) -> None:
    """Epoka AI osobno, epoka ukrytych systemow osobno.

    DZIELIMY PO DACIE WYSTAWIENIA, NIGDY PO DACIE POMIARU. Pole `zmierzone`
    mowi, kiedy PYTALISMY — a pytamy zawsze niedawno, takze o notki sprzed
    miesiaca. Podzial po nim daje dwie epoki, z ktorych jedna jest pusta; ta
    sama pomylka przepuscila juz raz filtr, ktory nie odfiltrowal niczego.

    `wystawione` dopisano do rekordu 31 sierpnia 2026. Pomiary starsze go nie
    maja i trafiaja do osobnej kolumny zamiast po cichu doliczyc sie do
    ktorejkolwiek epoki — bo doliczone po cichu skrzywilyby porownanie w
    strone, ktorej nie widac.
    """
    epoki: dict[str, list[dict]] = {"PRZED": [], "AI": [], "?": []}
    for r in najnowsze.values():
        data = str(r.get("wystawione") or "")[:10]
        if not data:
            epoki["?"].append(r)
        else:
            epoki["AI" if data >= PIVOT else "PRZED"].append(r)

    if not epoki["AI"] and not epoki["PRZED"]:
        print()
        print("PODZIAL NA EPOKI: zaden pomiar nie ma jeszcze daty wystawienia.")
        print("   Pole `wystawione` dopisano 31.08.2026 — pojawi sie przy")
        print("   nastepnym pomiarze kazdej pozycji.")
        return

    print()
    print("=" * 96)
    print("EPOKA AI (od %s) OSOBNO OD EPOKI UKRYTYCH SYSTEMOW" % PIVOT)
    print("=" * 96)
    if epoki["?"]:
        print("  bez daty wystawienia (pomiar sprzed 31.08): %d — NIE wliczone"
              " do zadnej epoki" % len(epoki["?"]))

    for rodzaj in sorted({str(r.get("rodzaj") or "?")
                          for r in najnowsze.values()}):
        wiersze = []
        for epoka in ("PRZED", "AI"):
            poz = [r for r in epoki[epoka]
                   if str(r.get("rodzaj") or "?") == rodzaj]
            if poz:
                wiersze.append((epoka, poz))
        if not wiersze:
            continue
        print()
        print("  %s" % rodzaj.upper())
        print("    %-8s %6s %10s %10s %10s %10s" % (
            "EPOKA", "ILE", "WEJSC", "MED.WEJSC", "POLUBIEN", "SUBSKR"))
        for epoka, poz in wiersze:
            wejscia = [int(r.get("wyswietlenia") or 0) for r in poz]
            print("    %-8s %6d %10d %10.1f %10d %10d" % (
                epoka, len(poz), sum(wejscia), _mediana(wejscia),
                sum(int(r.get("polubienia") or 0) for r in poz),
                sum(int(r.get("subskrypcje") or 0) for r in poz)))

    # POLA, KTORE NIGDY NIE DRGNELY. Pole zawsze zerowe wyglada w tabeli tak
    # samo jak pole, ktore po prostu dzis nic nie zebralo — a to zupelnie inna
    # informacja: pierwsze znaczy, ze mierzymy cos, czego nie dostajemy.
    martwe = [p for p in POLA
              if not any(int(r.get(p) or 0) for r in najnowsze.values())]
    if martwe:
        print()
        print("  MIERZONE, ALE ZAWSZE ZEROWE (we wszystkich epokach): %s"
              % ", ".join(martwe))

    print()
    print("  SKAD PRZYCHODZILY WEJSCIA, wg epoki:")
    for epoka in ("PRZED", "AI"):
        lic: dict[str, int] = {}
        for r in epoki[epoka]:
            for nazwa, ile in (r.get("powierzchnie") or {}).items():
                lic[str(nazwa)] = lic.get(str(nazwa), 0) + int(ile or 0)
        razem = sum(lic.values())
        if not razem:
            continue
        opis = ", ".join("%s %d (%d%%)" % (n, i, round(100 * i / razem))
                         for n, i in sorted(lic.items(), key=lambda x: -x[1])[:4])
        print("    %-6s %s" % (epoka, opis))


def wzrost_konta() -> None:
    """Ilu nas czyta i czy tego przybywa.

    To jedyna liczba, ktora mierzy CEL calego systemu wprost. Reszta raportu
    mowi, co przyniosl konkretny wpis; ta mowi, czy konto rosnie.

    Do 31 sierpnia 2026 nie byla nigdzie zapisywana — krzywa z panelu Substacka
    zyla wylacznie u Substacka.
    """
    import json as _json
    import browser as _browser

    if not _browser.WZROST.exists():
        return
    stany = []
    for linia in _browser.WZROST.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia:
            continue
        try:
            w = _json.loads(linia)
        except ValueError:
            continue
        if isinstance(w, dict):
            stany.append(w)
    if not stany:
        return

    print()
    print("=" * 96)
    print("ILU NAS CZYTA")
    print("=" * 96)
    # Jeden wiersz na DZIEN, nie na pomiar: mierzymy kilka razy dziennie,
    # a krzywa dzienna jest tym, o co chodzi.
    po_dniach: dict[str, dict] = {}
    for w in stany:
        po_dniach[str(w.get("kiedy") or "")[:10]] = w
    dni = sorted(po_dniach)
    print("%-12s %13s %13s %13s" % (
        "DZIEN", "SUBSKRYBENCI", "OBSERWUJACY", "MY SUBSKR."))
    for d in dni[-14:]:
        w = po_dniach[d]
        print("%-12s %13d %13d %13d" % (
            d, int(w.get("subskrybenci") or 0),
            int(w.get("obserwujacy") or 0),
            int(w.get("nasze_subskrypcje") or 0)))
    if len(dni) >= 2:
        a, b = po_dniach[dni[0]], po_dniach[dni[-1]]
        print("-" * 96)
        print("OD %s DO %s: subskrybentow %+d, obserwujacych %+d"
              % (dni[0], dni[-1],
                 int(b.get("subskrybenci") or 0) - int(a.get("subskrybenci") or 0),
                 int(b.get("obserwujacy") or 0) - int(a.get("obserwujacy") or 0)))
    else:
        print()
        print("   To pierwszy zapis — przyrostu nie ma jeszcze z czego policzyc.")


def kto_przyszedl() -> None:
    """Imiennie: kto sie zapisal i z ktorej pozycji.

    Karta `new_subscribers` panelu notki niesie to od zawsze i do 3 wrzesnia
    2026 nikt jej nie czytal. Raport twierdzil wtedy, ze notki nie przynosza
    nikogo — bo czytal pole `subskrypcje`, ktorego dla notki nie ma wcale.

    PO CO IMIONA, a nie sama liczba. Konto ma kilkudziesieciu czytelnikow.
    Przy tej skali „ta notka przyniosla dwoch" i „przyniosla TYCH dwoch" to
    dwie rozne informacje: druga pozwala sprawdzic, czy ten czlowiek zostal,
    czy odpisal, czy sam pisze o tym samym — czyli zobaczyc czytelnika jako
    czlowieka, a nie jako slupek.
    """
    poz = statystyki.najnowsze_per_pozycja()
    z_zapisami = [p for p in poz.values()
                  if p.get("zapisy_darmowe") or p.get("zapisy_platne")
                  or p.get("kto_sie_zapisal")]
    print()
    print("=" * 96)
    print("KTO SIE ZAPISAL I Z CZEGO  (karta `new_subscribers`, imiennie)")
    print("=" * 96)
    # BRAK POLA TO NIE ZERO. Pola pojawiaja sie od pierwszego pomiaru po
    # 3 wrzesnia 2026; starsze pozycje ich nie maja i nie wolno tego czytac
    # jako „nikt sie nie zapisal".
    zmierzone = [p for p in poz.values() if "zapisy_darmowe" in p]
    if not zmierzone:
        print("  Zadna pozycja nie ma jeszcze tego pomiaru — karta jest czytana")
        print("  od 3 wrzesnia 2026, wiec pojawi sie po najblizszym przebiegu.")
        print("  To NIE znaczy zero zapisow.")
        return
    print("  pozycji z tym pomiarem: %d z %d" % (len(zmierzone), len(poz)))
    if not z_zapisami:
        print("  Zadna zmierzona pozycja nie przyniosla zapisu.")
        return
    suma_f = sum(int(p.get("zapisy_darmowe") or 0) for p in z_zapisami)
    suma_p = sum(int(p.get("zapisy_platne") or 0) for p in z_zapisami)
    print("  zapisow razem: %d darmowych, %d platnych" % (suma_f, suma_p))
    print()
    for p in sorted(z_zapisami,
                    key=lambda r: -(int(r.get("zapisy_darmowe") or 0)
                                    + int(r.get("zapisy_platne") or 0))):
        print("  %-10s %-11s  %d free / %d paid   %s"
              % (p.get("rodzaj", "?"), p.get("id", "?"),
                 int(p.get("zapisy_darmowe") or 0),
                 int(p.get("zapisy_platne") or 0),
                 _skrot(p.get("tekst", ""), 44)))
        kto = p.get("kto_sie_zapisal") or []
        if kto:
            print("       kto: %s" % ", ".join(str(x) for x in kto[:8]))


def lepsze_od_sredniej() -> None:
    """Ktora pozycja pobila NASZA WLASNA srednia — panel podaje wzorzec sam.

    `impressions.graphData` niesie dwie serie: „This note" i „Your average".
    Do 3 wrzesnia 2026 czytalismy z tej karty tylko liczbe zbiorcza, wiec
    porownanie pozycji miedzy soba wymagalo zgadywania wieku — a panel przez
    caly czas podawal, ile mial nasz SREDNI wpis w tym samym momencie zycia.
    To jest jedyne porownanie, ktore cos zmienia: nie „duzo czy malo", tylko
    „lepiej czy gorzej niz zwykle robimy".
    """
    poz = statystyki.najnowsze_per_pozycja()
    maja = [p for p in poz.values() if p.get("nad_wzorcem_24h")]
    print()
    print("=" * 96)
    print("CO BYLO LEPSZE OD NASZEJ WLASNEJ SREDNIEJ  (pierwsze 24 h)")
    print("=" * 96)
    if not maja:
        print("  Zadna pozycja nie ma jeszcze krzywej z panelu — czytana od")
        print("  3 wrzesnia 2026. Panel oddaje ja dla czesci pozycji (zmierzone:")
        print("  63 z 159), wiec brak tu nie znaczy slabego wyniku.")
        return
    lepsze = [p for p in maja if float(p.get("nad_wzorcem_24h") or 0) >= 1]
    print("  pozycji z krzywa: %d | powyzej wlasnej sredniej: %d"
          % (len(maja), len(lepsze)))
    print()
    print("  %-10s %-11s %8s %8s %7s  %s"
          % ("RODZAJ", "NUMER", "NASZE24", "WZOR24", "RAZY", "TRESC"))
    print("  " + "-" * 82)
    for p in sorted(maja, key=lambda r: -float(r.get("nad_wzorcem_24h") or 0)):
        print("  %-10s %-11s %8s %8s %7s  %s"
              % (p.get("rodzaj", "?"), p.get("id", "?"),
                 p.get("nasza_po_24h", "—"), p.get("wzorzec_po_24h", "—"),
                 p.get("nad_wzorcem_24h"), _skrot(p.get("tekst", ""), 40)))
    # UDOSTEPNIENIA — druga rzecz, ktorej notka dotad nie miala.
    udost = [p for p in poz.values() if int(p.get("udostepnienia") or 0) > 0]
    if udost:
        print()
        print("  UDOSTEPNIENIA (karta `shareValues`):")
        for p in sorted(udost, key=lambda r: -int(r.get("udostepnienia") or 0)):
            print("     %2s x  %-10s %-11s %s"
                  % (p.get("udostepnienia"), p.get("rodzaj", "?"),
                     p.get("id", "?"), _skrot(p.get("tekst", ""), 40)))


def koszt_wobec_wyniku() -> None:
    """Ile kosztuje jedna pozycja i co za to przychodzi — w jednej tabeli.

    DWIE POLOWY, KTORE DOTAD LEZALY OSOBNO. Koszty siedza w bazie (`calls`),
    wyniki w pliku statystyk, i nikt ich nigdy nie podzielil przez siebie —
    a to jest jedyne pytanie, na ktore wlasciciel naprawde potrzebuje
    odpowiedzi: czy to, na co wydajemy, cokolwiek daje.

    KOSZT JEST BEZPOSREDNI, NIE CALKOWITY. Kolumna `akcja` znaczy kanal, do
    ktorego wywolanie zostalo napisane — pisanie notki, pisanie komentarza,
    odpowiedz. NIE obejmuje kosztow wspolnych: dobierania banku, szukania
    celow, sprawdzania faktow poza kanalem. Te sa wypisane osobno jako
    „nieprzypisane", zeby suma sie zgadzala i zeby nikt nie wzial kosztu
    bezposredniego za caly rachunek.

    WYNIK JEST PO ROWNYM CZASIE (24 h), bo inaczej starsza pozycja wygrywa
    wiekiem, a nie trescia. Okno kosztow i okno wynikow to DWA ROZNE okresy —
    `akcja` istnieje dopiero od 2 wrzesnia 2026, a pomiary siegaja dalej wstecz.
    Dlatego dzielimy koszt na sztuke przez wynik na sztuke, a nie sumy przez
    sumy: stosunek jest uczciwy, suma nie bylaby.
    """
    import db
    print()
    print("=" * 96)
    print("ILE KOSZTUJE JEDNA POZYCJA I CO ZA TO PRZYCHODZI")
    print("=" * 96)
    try:
        conn = db.connect()
        wiersze = list(conn.execute(
            "SELECT akcja, COUNT(*), SUM(cost_usd), MIN(substr(at,1,10)), "
            "MAX(substr(at,1,10)) FROM calls "
            "WHERE akcja IS NOT NULL AND akcja<>'' GROUP BY 1"))
        nieprzypisane = list(conn.execute(
            "SELECT COUNT(*), SUM(cost_usd) FROM calls "
            "WHERE akcja IS NULL OR akcja=''"))[0]
    except Exception as exc:
        print("  Nie umiem odczytac kosztow (%s)." % type(exc).__name__)
        return
    if not wiersze:
        print("  Zadne wywolanie nie ma jeszcze przypisanego kanalu.")
        print("  Kolumna `akcja` zapisuje sie od 2 wrzesnia 2026.")
        return

    # Kanaly komentarza sa dwa (pod artykulem i pod notka) — dla tej tabeli to
    # jeden koszt jednej pozycji, bo wynik tez mierzymy jednym rodzajem.
    koszty, ile_wywolan, od, do_ = {}, {}, None, None
    for akcja, n, suma, mn, mx in wiersze:
        klucz = "komentarz" if str(akcja).startswith("komentarz") else str(akcja)
        koszty[klucz] = koszty.get(klucz, 0.0) + float(suma or 0)
        ile_wywolan[klucz] = ile_wywolan.get(klucz, 0) + int(n or 0)
        od = mn if od is None or (mn and mn < od) else od
        do_ = mx if do_ is None or (mx and mx > do_) else do_

    ile_pozycji = _pozycje_w_okresie(od, do_)
    print("  koszty z okresu %s..%s   (kolumna `akcja`)" % (od, do_))
    print()
    print("  %-11s %9s %8s %10s %9s %9s %11s" % (
        "KANAL", "KOSZT", "SZTUK", "ZA SZTUKE", "WEJSC 24h", "ZA WEJSCIE",
        "ZA POLUBIENIE"))
    print("  " + "-" * 76)
    for kanal in sorted(koszty, key=lambda k: -koszty[k]):
        sztuk = ile_pozycji.get(kanal, 0)
        za_sztuke = koszty[kanal] / sztuk if sztuk else None
        okno = statystyki.po_godzinach(kanal, 24.0)["pozycje"]
        wej = [int(p.get("wyswietlenia") or 0) for p in okno.values()]
        pol = [int(p.get("polubienia") or 0) for p in okno.values()]
        sr_wej = (sum(wej) / len(wej)) if wej else 0.0
        sr_pol = (sum(pol) / len(pol)) if pol else 0.0
        print("  %-11s %9.4f %8s %10s %9.1f %9s %11s" % (
            kanal, koszty[kanal], sztuk if sztuk else "—",
            ("%.4f" % za_sztuke) if za_sztuke else "—",
            sr_wej,
            ("%.4f" % (za_sztuke / sr_wej)) if za_sztuke and sr_wej else "—",
            ("%.4f" % (za_sztuke / sr_pol)) if za_sztuke and sr_pol else "—"))
    print("  " + "-" * 76)
    print("  nieprzypisane do kanalu: %s wywolan, %.4f USD — dobieranie banku,"
          % (nieprzypisane[0], float(nieprzypisane[1] or 0)))
    print("  szukanie celow, sprawdzanie faktow i cala historia sprzed kolumny.")


def _pozycje_w_okresie(od: str, do_: str) -> dict:
    """Ile pozycji kazdego rodzaju powstalo miedzy tymi datami (dziennik)."""
    plik = config.DATA_DIR / "dziennik.jsonl"
    ile: dict[str, int] = {}
    if not (od and do_ and plik.exists()):
        return ile
    # NAZWY RODZAJOW SA INNE W DZIENNIKU NIZ W KOLUMNIE `akcja`, wiec mapujemy
    # je wprost. Milczace niedopasowanie dawaloby „—" wygladajace jak brak
    # danych, a nie jak literowka.
    MAPA = {"notka": "notka", "komentarz": "komentarz",
            "odpowiedz": "odpowiedz", "odpowiedz_pod_artykulem": "odpowiedz",
            "restack": "restack"}
    with plik.open(encoding="utf-8") as f:
        for linia in f:
            try:
                w = json.loads(linia)
            except Exception:
                continue
            kiedy = str(w.get("kiedy") or "")[:10]
            if not (od <= kiedy <= do_):
                continue
            rodzaj = MAPA.get(str(w.get("rodzaj") or w.get("co") or ""))
            if rodzaj:
                ile[rodzaj] = ile.get(rodzaj, 0) + 1
    return ile


def zrodla_zapisow() -> None:
    """SKAD NAPRAWDE przyszli ludzie — wlasne przypisanie Substacka.

    Osobna sekcja, a nie kolumna w tabeli wyzej, bo to inne zrodlo danych i
    inna jednostka: tamta tabela mierzy POZYCJE, ta odpowiada na pytanie
    „ktora droga ktos przyszedl". Sklejenie ich dawalo liczbe, ktora wyglada
    jak przypisanie, a nim nie jest.

    Czyta ostatnia linie `data/zrodla.jsonl`, ktora `zapisz_zrodla_ruchu`
    dokleja przy kazdym przebiegu. Gdy pliku nie ma, mowi to wprost zamiast
    milczec — brak pomiaru i zero to nie to samo.
    """
    plik = config.DATA_DIR / "zrodla.jsonl"
    print()
    print("=" * 96)
    print("SKAD NAPRAWDE PRZYSZLI LUDZIE  (przypisanie Substacka, nie okno czasowe)")
    print("=" * 96)
    if not plik.exists():
        print("  Brak `data/zrodla.jsonl` — tabela zrodel nie byla jeszcze czytana.")
        print("  To NIE znaczy zero zapisow; to znaczy, ze nikt nie pytal.")
        return
    ostatnia = None
    for linia in plik.read_text(encoding="utf-8").splitlines():
        if linia.strip():
            try:
                ostatnia = json.loads(linia)
            except Exception:
                continue
    if not ostatnia:
        print("  Plik jest, ale nie ma w nim ani jednego czytelnego odczytu.")
        return
    okno = ostatnia.get("okno") or {}
    pod = ostatnia.get("podsumowanie") or {}
    print("  odczyt z %s, okno %s..%s (%s dni)" % (
        str(ostatnia.get("kiedy"))[:16], okno.get("od"), okno.get("do"),
        okno.get("dni")))
    print("  zapisow razem: %s   ruch: %s wyswietlen / %s osob" % (
        pod.get("zapisy_ze_wzrostu", "?"), pod.get("wyswietlenia", "?"),
        pod.get("osoby", "?")))
    # ZGODNOSC DWOCH ADRESOW. Panel oddaje te sama liczbe dwoma drogami;
    # rozjazd znaczy, ze jedna z nich czytamy zle — i lepiej to wiedziec.
    if pod.get("zapisy_zgodne") is False:
        print("  UWAGA: dwa adresy panelu podaja ROZNE sumy zapisow (%s vs %s)"
              % (pod.get("zapisy_z_ruchu"), pod.get("zapisy_ze_wzrostu")))
    per = pod.get("zapisy_per_notka") or {}
    if per:
        teksty = {}
        for poz in statystyki.najnowsze_per_pozycja().values():
            teksty[str(poz.get("id"))] = poz.get("tekst", "")
        print()
        print("  KTORA NOTKA PRZYNIOSLA CZLOWIEKA:")
        for nid, ile in sorted(per.items(), key=lambda kv: -kv[1]):
            print("     %2s zapis(ow)  %-10s  %s"
                  % (ile, nid, _skrot(teksty.get(str(nid), ""), 58)))
        print("     razem z notek: %d" % sum(per.values()))
    else:
        print("  Panel nie przypisal zadnego zapisu do konkretnej notki.")
    # RUCH PER ZRODLO — druga polowa obrazu: co przyciaga oczy, a nie zapisy.
    rzedy = ((ostatnia.get("ruch") or {}).get("rows")) or []
    if rzedy:
        print()
        print("  RUCH WG ZRODLA:")
        for r in sorted(rzedy, key=lambda r: -(r.get("views") or 0))[:8]:
            print("     %-18s %6s wyswietlen  %5s osob  %s zapisow"
                  % (str(r.get("source"))[:18], r.get("views") if r.get("views") is not None else "—",
                     r.get("users") if r.get("users") is not None else "—",
                     r.get("free_signup") if r.get("free_signup") is not None else "—"))


def main() -> int:
    rodzaj = sys.argv[1] if len(sys.argv) > 1 else None

    najnowsze = statystyki.najnowsze_per_pozycja(rodzaj)
    if not najnowsze:
        print("Zadnych pomiarow jeszcze nie ma.")
        print()
        print("Statystyki zbieraja sie w cyklu dnia, razem z odpowiadaniem na")
        print("komentarze. Jesli plik jest pusty, a bot chodzi — sprawdz, czy")
        print("wystawione pozycje maja zapisane numery: bez numeru nie ma czego")
        print("pytac. Zmierzone 25 sierpnia: z 29 notek numer mialo szesc.")
        return 0

    # Sortujemy po tym, co wlasciciela interesuje najbardziej: ile osob z tego
    # zostalo. Przy remisie po zasiegu, bo to jedyna druga os, ktora mamy.
    pozycje = sorted(
        najnowsze.values(),
        key=lambda r: (r.get("subskrypcje", 0) + r.get("obserwacje", 0),
                       r.get("wyswietlenia", 0)),
        reverse=True,
    )

    print("=" * 96)
    print("CO PRZYNIOSLA KAZDA POZYCJA%s" % (
        "  (tylko: %s)" % rodzaj if rodzaj else ""))
    print("=" * 96)
    # KOLUMNA, KTORA MOWILA COS INNEGO, NIZ WSZYSCY CZYTALI.
    #
    # „SUBS" przy pozycji NIE jest przypisaniem zapisu do tej pozycji. Przy
    # artykule to `signups_within_1_day` z panelu wydawcy — czyli KTO ZAPISAL
    # SIE W CIAGU DOBY po wpisie, z dowolnego powodu. Przy notce tego pola nie
    # ma wcale, wiec stoi tam zero, ktore znaczy „nie mierzone", a wyglada jak
    # „nic nie przyniosla".
    #
    # Zmierzone 3 wrzesnia 2026 na tych samych danych: tabela pokazywala
    # 7 subskrypcji przy artykulach i 0 przy notkach, a wlasne przypisanie
    # Substacka (`stats/growth/sources`) mowilo dokladnie odwrotnie — 6 zapisow,
    # z tego 5 z notek i ANI JEDNEGO z artykulu. Kolumna zapraszala wiec do
    # odwrotnego wniosku niz prawda, i to przy jedynym pytaniu, ktore naprawde
    # sie liczy: co przynosi ludzi.
    #
    # Prawdziwe przypisanie jest nizej, w osobnej sekcji. Tu zostaje nazwa,
    # ktora nie udaje odpowiedzi na tamto pytanie.
    print("%-11s %-10s %6s %6s %5s %5s %5s  %s" % (
        "RODZAJ", "NUMER", "WEJSC", "POLUB", "KOM", "ZAP24", "OBS", "TRESC"))
    print("-" * 96)
    for r in pozycje:
        print("%-11s %-10s %6s %6s %5s %5s %5s  %s" % (
            r.get("rodzaj", "?"),
            r.get("id", "?"),
            r.get("wyswietlenia", 0),
            r.get("polubienia", 0),
            r.get("odpowiedzi", 0),
            r.get("subskrypcje", 0),
            r.get("obserwacje", 0),
            _skrot(r.get("tekst", ""))))

    p = statystyki.podsumowanie(rodzaj)
    print("-" * 96)
    print("RAZEM  pozycji %s | wejsc %s | polubien %s | komentarzy %s | "
          "subskrypcji %s | obserwacji %s | klikniec w link %s" % (
              p.get("pozycje", 0), p.get("wyswietlenia", 0),
              p.get("polubienia", 0), p.get("odpowiedzi", 0),
              p.get("subskrypcje", 0), p.get("obserwacje", 0),
              p.get("klikniecia_w_link", 0)))
    print("SREDNIO wejsc na pozycje: %s   (pomiarow w pliku: %s)" % (
        p.get("srednia_wyswietlen", 0), p.get("pomiary", 0)))

    # OSTRZEZENIE O ROZJEZDZIE. Substack podaje wlasna sume interakcji; my
    # sumujemy pozycje z listy. Gdy te dwie liczby sie roznia, znaczy to, ze
    # pojawil sie rodzaj interakcji, ktorego nie rozpoznajemy — czyli ze konto
    # dostaje sygnal, ktorego nie widzimy. Bez tego wydruku liczba byla
    # wyliczana i wyrzucana.
    _od_substacka = p.get("interakcje_razem", 0)
    _z_pozycji = p.get("interakcje_z_pozycji", 0)
    if _od_substacka != _z_pozycji:
        print()
        print("UWAGA: Substack liczy %s interakcji, a z rozpoznanych pozycji "
              "wychodzi %s." % (_od_substacka, _z_pozycji))
        print("       Roznica %s znaczy nowy rodzaj interakcji, ktorego nie "
              "nazywamy po imieniu." % abs(_od_substacka - _z_pozycji))
    naj = p.get("najlepsza")
    if naj:
        print("NAJLEPSZA: %s %s — %s wejsc, %s subskrypcji" % (
            naj.get("rodzaj", "?"), naj.get("id", "?"),
            naj.get("wyswietlenia", 0), naj.get("subskrypcje", 0)))
        print("           %s" % _skrot(naj.get("tekst", ""), 80))

    # Skad ludzie w ogole trafiaja — to decyduje, czy warto pisac wiecej notek,
    # czy raczej komentowac u innych.
    powierzchnie: dict[str, int] = {}
    for r in najnowsze.values():
        for nazwa, ile in (r.get("powierzchnie") or {}).items():
            powierzchnie[nazwa] = powierzchnie.get(nazwa, 0) + int(ile or 0)
    if powierzchnie:
        print()
        print("SKAD PRZYCHODZA WEJSCIA:")
        for nazwa, ile in sorted(powierzchnie.items(), key=lambda x: -x[1]):
            print("   %-16s %s" % (nazwa, ile))

    kto_przyszedl()
    lepsze_od_sredniej()
    koszt_wobec_wyniku()
    zrodla_zapisow()
    dwie_epoki(najnowsze)
    wzrost_konta()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
