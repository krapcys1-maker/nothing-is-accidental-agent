"""Jedno polecenie uruchamiające — to samo lokalnie i na serwerze.

    python agent-v2/run.py
    python agent-v2/run.py --stop-after scout
    python agent-v2/run.py --use-cache          # nie płać drugi raz za etap N-1

Bez interaktywnych promptów: na serwerze nie ma komu odpowiedzieć. Logi na
stdout, żeby harmonogram je przechwycił.
"""

from __future__ import annotations

import argparse
import os
import json
import sys
import traceback
from typing import Any, Callable

import config
import db
import gates
import stages

STAGES = (
    "scout", "feasibility", "discovery", "fetch",
    "classify", "synthesis", "warto_pisac", "write", "review", "forma",
)

CACHE_DIR = config.DATA_DIR / "cache"


def _utf8_stdout() -> None:
    """Konsola Windows domyślnie cp1252 i wywala się na polskich znakach.

    Serwer ma UTF-8, więc bez tego błąd wychodzi wyłącznie na jednym z tych
    dwóch komputerów — czyli najgorszy możliwy rodzaj błędu.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cached(stage: str, produce: Callable[[], Any], use_cache: bool) -> Any:
    """Zapisuje wynik etapu i oddaje go z dysku zamiast płacić drugi raz.

    Zasada z briefu: testując etap N, użyj zapisanego wyniku etapu N-1.
    """
    path = CACHE_DIR / f"{stage}.json"
    if use_cache and path.exists():
        print(f"  [{stage}] z pamięci podręcznej — bez opłaty", flush=True)
        return json.loads(path.read_text(encoding="utf-8"))
    value = produce()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


class JuzDziala(RuntimeError):
    pass


ZNACZNIK_KOPII_TESTOWEJ = config.AGENT_DIR / "TO_JEST_KOPIA_TESTOWA"


def odmow_publikacji_z_kopii(wyslij: bool) -> None:
    """Kopia testowa nie ma prawa nic opublikowac. Nigdy.

    Wlasciciel: „nie odpalaj go na produkcji, wersja v2 ma byc jako test".
    Sama dyscyplina nie wystarczy — wystarczy raz dopisac `--wyslij` z pamieci
    miesnowej i eksperyment wyjdzie na zywe konto, czego nie da sie cofnac.
    Wiec kopia testowa nosi plik-znacznik obok `config.py`, a ten plik odbiera
    jej prawo publikowania. Produkcja znacznika nie ma i dziala normalnie.
    """
    if wyslij and ZNACZNIK_KOPII_TESTOWEJ.exists():
        raise SystemExit(
            "ODMOWA: to jest kopia testowa (%s), a --wyslij publikuje NA ZYWO. "
            "Produkcja stoi w ~/nothing-is-accidental-agent na galezi main. "
            "Jesli naprawde chcesz publikowac stad, usun ten plik swiadomie."
            % ZNACZNIK_KOPII_TESTOWEJ
        )


def zajmij_zamek():
    """Nie pozwala dwóm przebiegom działać naraz.

    Na serwerze harmonogram odpali agenta o stałej godzinie niezależnie od tego,
    czy poprzedni przebieg się skończył. Dwa procesy naraz to dwa razy ten sam
    artykuł i dwa razy ta sama notka — a tego nie da się cofnąć. To nie jest
    kwestia „czy", tylko „kiedy", więc zamek jest przed pierwszym uruchomieniem
    z harmonogramu, nie po pierwszej wpadce.

    Zamek trzyma system plików, nie my: przy zabiciu procesu blokada znika sama,
    więc nie zostawia po sobie zakleszczenia, które trzeba by odblokowywać ręcznie.
    """
    sciezka = config.DATA_DIR / "agent.lock"
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    uchwyt = open(sciezka, "w", encoding="utf-8")
    try:
        try:                      # Linux, czyli serwer
            import fcntl
            fcntl.flock(uchwyt, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:       # Windows, czyli komputer właściciela
            import msvcrt
            msvcrt.locking(uchwyt.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        uchwyt.close()
        raise JuzDziala(
            f"Inny przebieg już działa (zamek: {sciezka}). Kończę bez zmian."
        ) from None
    uchwyt.write(f"{os.getpid()}\n")
    uchwyt.flush()
    return uchwyt


def opis_celu(cel: dict) -> dict:
    """Co wiedzielismy o celu w chwili pisania — do dziennika.

    Te liczby juz mamy w reku przy wyborze celu i dotad je wyrzucalismy. Bez nich
    przeglad po kilku dniach mowi tylko „napisano osiemnascie komentarzy", a nie
    umie odpowiedziec na jedyne pytanie, ktore cos zmienia: czy komentarz jako
    piaty wraca czesciej niz jako piecdziesiaty i ktore hasla przynosza rozmowy.
    """
    import kanal

    return {
        "publikacja": (cel.get("pub") or "")[:80],
        "skad": (cel.get("skad") or "")[:60],
        # Ilu bylo przed nami. To jest ta liczba, o ktora chodzi najbardziej.
        "komentarzy_przed": int(cel.get("komentarze") or 0),
        "reakcje_celu": int(cel.get("reakcje") or 0),
        "wiek_celu_min": round(kanal._wiek_minut(cel.get("data", "")), 1),
    }


_KONIEC_CZASU: float | None = None


def zostal_czas(na_co: str = "", potrzeba_s: float = 0.0) -> bool:
    """Czy zdazymy jeszcze cokolwiek zrobic przed koncem czasu przebiegu.

    Systemd tnie przebieg po `TimeoutStartSec` i robi to SIGTERM-em w dowolnym
    momencie — takze w polowie wpisywania komentarza. Zdarzylo sie naprawde:
    przebieg z szesnastoma komentarzami do wystawienia zostal ubity po 2,5 h.
    Lepiej skonczyc dzien krocej niz zostac przerwanym w srodku dzialania,
    ktorego nie da sie cofnac.
    """
    import time

    if _KONIEC_CZASU is None:
        return True
    zostalo = _KONIEC_CZASU - time.time()
    if zostalo > potrzeba_s:
        return True
    if potrzeba_s:
        print(f"  czas przebiegu wyczerpany — odpuszczam {na_co or 'reszte'}"
              f" (przerwa {potrzeba_s / 60:.0f} min nie zmiesci sie"
              f" w {max(0.0, zostalo) / 60:.0f} min; dokoncze w nastepnym"
              f" przebiegu)", flush=True)
    else:
        print(f"  czas przebiegu wyczerpany — odpuszczam {na_co or 'reszte'}"
              f" (dokoncze w nastepnym przebiegu)", flush=True)
    return False


def rytm(co: str, na_co: str, stan: dict) -> bool:
    """Przerwa MIEDZY dwoma dzialaniami tego samego rodzaju.

    Trzeci raz ta sama wada, tym razem zamknieta w jednym miejscu dla wszystkich
    blokow. Przerwa byla odsypiana PO dzialaniu, wiec:

      1. po OSTATNIEJ notce w bloku agent spal jeszcze 45-90 minut, choc nie
         mial juz czego robic — to jest dokladnie ta sama usterka, ktora
         naprawilem wczesniej dla restackow i ktorej wtedy nie poszukalem
         nigdzie indziej;
      2. sen zaczynal sie BEZ pytania, czy sie zmiesci. `zostal_czas` mowilo
         tylko „czy zostala jakakolwiek sekunda", wiec przepuszczalo
         dziewiecdziesieciominutowa przerwe przy dwudziestu minutach na zegarze.

    Teraz przerwa jest najpierw losowana, potem sprawdzana wobec konca
    przebiegu, i dopiero wtedy odsypiana — a pierwsze dzialanie w przebiegu nie
    czeka na nic, bo nie ma na co.
    """
    import stages as _s

    if not stan.get(co):
        return zostal_czas(na_co)
    przerwa = _s.losuj_odstep(co)
    if not zostal_czas(na_co, przerwa):
        return False
    _s.odczekaj(co, przerwa)
    return True


def zmiesci_sie(rodzaj: str, ile: int, udzial: float = 1.0) -> int:
    """Ile z zaplanowanych dzialan NAPRAWDE zmiesci sie w czasie przebiegu.

    Rozdzielnik dzielil dzienna norme, nie patrzac na zegar. Po wydluzeniu
    odstepow miedzy notkami do 45-90 minut wieczorna rutyna dostala cztery notki
    — od trzech do szesciu godzin samego czekania przy budzecie 2h15. Zdazyla
    jedna i do komentarzy nie doszla w ogole.

    Obietnica, ktorej nie da sie dotrzymac, jest gorsza od mniejszej: blokuje
    reszte przebiegu. Lepiej wystawic dwie notki i czternascie komentarzy niz
    obiecac cztery notki i nie zrobic nic poza jedna.
    """
    import time

    if _KONIEC_CZASU is None or ile <= 0:
        return ile
    dol, gora = config.ODSTEPY.get(rodzaj, config.ODSTEP_MIEDZY_DZIALANIAMI)
    odstep = (dol + gora) / 2
    zostalo = max(0.0, _KONIEC_CZASU - time.time()) * udzial

    # PRZERW JEST O JEDNA MNIEJ NIZ DZIALAN. Przy dwoch notkach czekamy raz, nie
    # dwa — pierwsza wersja liczyla przerwe po kazdej i wychodzilo o polowe za malo.
    def potrzeba(n: int) -> float:
        return n * config.CZAS_DZIALANIA_S + max(0, n - 1) * odstep

    mozliwe = ile
    while mozliwe > 0 and potrzeba(mozliwe) > zostalo:
        mozliwe -= 1
    if mozliwe < ile:
        print(f"  [czas] {rodzaj}: {ile} sie nie zmiesci, biore {mozliwe}"
              f" (odstep ~{odstep / 60:.0f} min, zostalo {zostalo / 60:.0f} min)",
              flush=True)
    return mozliwe


def ile_przebiegow_zostalo(conn) -> int:
    """Ile przebiegow dnia jeszcze bedzie, wliczajac biezacy.

    Sluzy do dzielenia dziennej normy. Liczymy przebiegi ZAKONCZONE dzis, wiec
    ten, ktory wlasnie trwa, jeszcze sie nie liczy — i dobrze, bo ma cos wziac.

    Przebieg PRZERWANY tez sie nie liczy, i to jest cala pointa: gdy jeden padnie,
    kolejne widza, ze zostalo ich mniej, i dobieraja wiecej, zamiast zostawic
    dzien niedomkniety. Ostatni dzieli przez jeden, czyli bierze cala reszte.

    Nie pytamy systemd o harmonogram, choc to on odpala agenta. Godziny sa w pliku
    `.timer` i powtorzenie ich tutaj zlamaloby zasade jednej liczby w jednym
    miejscu — a rozjazd miedzy nimi wychodzilby dopiero po zmianie harmonogramu.
    """
    from datetime import datetime, timezone

    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        (zamkniete,) = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE stage = 'dzien' AND status = 'DONE'"
            " AND finished_at LIKE ?", (f"{dzis}%",)).fetchone()
    except Exception:
        zamkniete = 0             # licznik nie moze zatrzymac przebiegu
    return max(1, config.PRZEBIEGOW_DZIENNIE - int(zamkniete))


def dzien(conn, run_id: int, wyslij: bool) -> int:
    """Jeden dzień pracy konta: notki, komentarze, odpowiedzi, polubienia.

    Rutyna, której do tej pory nie było — każda zdolność działała osobno, a nic
    ich nie spinało. Trzy zasady, wszystkie z rzeczy, które nas już kosztowały:

    1. KAŻDY BLOK OSOBNO. Padnięte komentarze nie zabierają ze sobą notek.
       Dzień częściowo udany jest znacznie lepszy od dnia przerwanego w połowie.
    2. ODPOWIEDZI POZA LIMITEM. U siebie jesteśmy gospodarzem; pytanie bez
       odpowiedzi pod własnym tekstem szkodzi bardziej niż komentarz za dużo.
    3. NIC NIE WYCHODZI BEZ `--wyslij`. Domyślnie agent pokazuje, co by zrobił.
    """
    import time

    import alarm
    import browser
    import kanal

    global _KONIEC_CZASU
    _KONIEC_CZASU = time.time() + max(
        60, config.LIMIT_CZASU_PRZEBIEGU_S - config.ZAPAS_CZASU_S)

    budzet = stages.budzet_dnia(conn)

    # ILE JUZ DZIS POSZLO — pytamy Substacka, nie wlasnej ksiegowosci.
    # Wlasciciel zauwazyl, ze dwie notki wyszly trzy minuty po sobie: caly
    # dzienny przydzial szedl w jednym ciagu, bo przebieg robil wszystko naraz.
    # Teraz zegar odpala agenta KILKA RAZY DZIENNIE, a kazdy przebieg dobiera
    # tylko brakujaca czesc — dzieki temu notki rozkladaja sie na godziny,
    # a nie na minuty.
    juz = browser.ile_dzis_wystawione()
    # OBSERWACJE I SUBSKRYPCJE TEZ, i to jest naprawa z 20 sierpnia. Bloki 3c
    # i 3d braly `budzet["follow"]` oraz `budzet["subskrypcje"]` — czyli PELNY
    # dzienny przydzial — w KAZDYM z trzech przebiegow. Realny wolumen wychodzil
    # okolo trzykrotnosci konfiguracji: ~60-70 obserwacji miesiecznie zamiast
    # 20-30 i ~27 subskrypcji zamiast 6-12. Kazda subskrypcja to poczta do
    # skrzynki wlasciciela, wiec to nie byla pomylka kosmetyczna.
    zostalo = {k: max(0, budzet[k] - juz.get(k, 0))
               for k in ("notki", "komentarze", "lajki", "restacki",
                         "follow", "subskrypcje")}

    # CICHY DZIEN. Wyciszamy to, co NADAJEMY — notki i restacki. Komentarze,
    # polubienia i obserwacje zostaja, bo to jest czytanie cudzych rzeczy,
    # a nie nadawanie wlasnych. Odpowiedzi zostaja tym bardziej: nieodpisanie
    # komus, kto sie do nas odezwal, nie jest cisza tylko lekcewazeniem.
    if config.cichy_dzien():
        print("   >> CICHY DZIEN — nie nadajemy wlasnych tresci. Rozmowa idzie"
              " normalnie: odpowiedzi, komentarze i czytanie bez zmian.",
              flush=True)
        zostalo["notki"] = 0
        zostalo["restacki"] = 0
    # Reszte dzielimy przez przebiegi, ktore JESZCZE dzis beda — nie przez
    # wszystkie. Dzielenie przez wszystkie systematycznie zaniza: przy budzecie
    # 16 komentarzy trzy przebiegi braly 5, 4 i 2, czyli 11 zamiast 16. Przez
    # pozostale wychodzi 5, 6 i 5. Ostatni przebieg dnia dzieli przez jeden,
    # wiec dobiera cala reszte i norma sie domyka.
    zostalo_przebiegow = ile_przebiegow_zostalo(conn)
    na_teraz = {k: max(1, round(v / zostalo_przebiegow)) if v else 0
                for k, v in zostalo.items()}
    # Obietnica przyciete do zegara. Notki maja pierwszenstwo, ale nie caly przebieg.
    na_teraz["notki"] = zmiesci_sie("notka", na_teraz["notki"],
                                    config.UDZIAL_CZASU_NA_NOTKI)
    na_teraz["komentarze"] = zmiesci_sie("komentarz", na_teraz["komentarze"])
    print(f"   dzis juz: notki={juz.get('notki', 0)} "
          f"komentarze={juz.get('komentarze', 0)} lajki={juz.get('lajki', 0)}   "
          f"przebiegow zostalo: {zostalo_przebiegow}   "
          f"w tym przebiegu: notki={na_teraz['notki']} "
          f"komentarze={na_teraz['komentarze']} lajki={na_teraz['lajki']}",
          flush=True)
    zrobione = {"notki": 0, "komentarze": 0, "odpowiedzi": 0, "polubienia": 0,
                "restacki": 0}
    # Czy dany rodzaj dzialania juz w tym przebiegu wyszedl. Wspolne dla
    # wszystkich blokow, bo profil widzi jeden ciag zdarzen, nie nasze bloki:
    # komentarz tuz po obserwacji to dla Substacka dwa dzialania pod rzad.
    rytm_stanu: dict[str, bool] = {}

    # OKNO PUBLIKACJI liczone w strefie CZYTELNIKOW. Poza nim agent nie milczy
    # calkiem — polubienia i odpowiedzi zostaja, bo czytanie o polnocy jest
    # ludzkie, a odpowiedz gospodarza nie moze czekac do rana. Nie wychodza za to
    # NOWE tresci, ktore konkuruja o miejsce w kanale.
    wolno, powod = config.pora_na_publikacje()
    print(f"   okno publikacji: {'TAK' if wolno else 'NIE'} — {powod}", flush=True)
    if not wolno:
        na_teraz["notki"] = 0
        na_teraz["komentarze"] = 0

    def blok(nazwa: str, robota) -> None:
        try:
            robota()
        except Exception as exc:
            print(f"  [{nazwa}] blok padł: {type(exc).__name__}: {exc}"[:160],
                  flush=True)
            traceback.print_exc()

    # --- 1. odpowiedzi pod własnymi treściami: pierwsze i bez limitu ----------
    def odpowiedzi() -> None:
        # Pod notkami I pod artykułami. Kanał profilu pokazuje tylko notki, więc
        # bez drugiego pytania czytelnik mógłby zadać pytanie pod tekstem
        # i nie doczekać się odpowiedzi.
        # Trzy zrodla, bo rozmowa toczy sie w trzech miejscach. Trzeciego —
        # odpowiedzi na NASZE komentarze u obcych — agent nie widzial wcale
        # i takiej odpowiedzi nie podjalby nigdy, nie „pozniej".
        # Najpierw dopisujemy, co wynikło z tego, co juz zrobilismy — bez tego
        # dziennik mowi tylko, co wystawilismy, a nie czy ktokolwiek zauwazyl.
        browser.dopisz_skutki()
        czekaja = (browser.nieodpowiedziane()
                   + browser.komentarze_pod_artykulami()
                   + browser.odpowiedzi_na_nasze_komentarze())
        if not czekaja:
            return
        # PYTANIA CZYTELNIKOW DO PULI TEMATOW. Zbieramy tutaj, bo tutaj i tak
        # trzymamy w reku wszystko, co do nas przyszlo — a w przebiegu artykulu
        # kazde dodatkowe otwarcie sesji to koszt i ryzyko. Pytanie, ktore ktos
        # zadal, a na ktore nikt nie odpowiedzial, jest najlepszym zrodlem
        # tematow, jakie ma kazda publikacja; dotad wyrzucalismy je co dzien.
        try:
            stages.zbierz_pytania(czekaja)
        except Exception as exc:
            print(f"  (nie zebralem pytan: {type(exc).__name__})", flush=True)
        # Przy dwóch odpowiada się obu. Przy dwustu odpowiedź pod każdym wygląda
        # jak maszyna, więc powyżej progu agent wybiera — z pierwszeństwem dla
        # niezgody, bo nieodpowiedziany zarzut zostaje ostatnim słowem.
        czekaja = stages.wybierz_do_odpowiedzi(conn, run_id, czekaja)
        for c in czekaja:
            if not zostal_czas("odpowiedzi"):
                return
            out = stages.reply_to(
                conn, run_id,
                {"under": c.get("kontekst") or "our own note",
                 "author": c["autor"], "text": c["tekst"]},
                {"our_note": c["pod_czym"]})
            kandydaci = [k for k in out["candidates"] if k.get("reply")]
            if not kandydaci:
                continue
            tekst = kandydaci[0]["reply"]
            if wyslij:
                # Pod artykulem odpowiada sie inaczej niz pod notka — inny
                # edytor i inny adres. Na razie obslugujemy notki; komentarze
                # pod artykulami trafiaja do logu, zeby nie ginely.
                # Dwa różne mechanizmy, bo Substack ma je różne: pod notką wątek
                # jest płaski i odpowiada się w polu pod całą notką, pod
                # artykułem każdy komentarz ma własny przycisk odpowiedzi —
                # i tylko wtedy rozmówca dostaje powiadomienie.
                if not rytm("odpowiedz", "odpowiedzi", rytm_stanu):
                    return
                if c.get("gdzie") == "artykul":
                    browser.wystaw_odpowiedz_pod_artykulem(
                        c.get("url") or "", c.get("autor") or "", tekst,
                        wyslij=True)
                else:
                    browser.wystaw_odpowiedz(c["pod_id"], tekst, wyslij=True)
                rytm_stanu["odpowiedz"] = True
            zrobione["odpowiedzi"] += 1

    # --- 2. notki: pięć dziennie, każda z innego faktu ------------------------
    def notki() -> None:
        if not na_teraz["notki"]:
            print("  dzienny przydzial notek juz wyczerpany", flush=True)
            return
        # Losowa zwloka PRZED pierwsza notka. Bez niej pierwsza notka
        # wychodzila zawsze kilka minut po starcie zegara, wiec trzy razy
        # dziennie o tej samej porze co do kwadransa. Godziny zostaja te,
        # ktore wybralismy; przewidywalne przestaja byc minuty.
        if wyslij:
            import random as _r
            ile = _r.uniform(*config.ZWLOKA_PRZED_NOTKAMI)
            print(f"  (zwloka {ile / 60:.0f} min przed pierwsza notka)", flush=True)
            time.sleep(ile)
        for n in stages.notki_dnia(conn, run_id, ile=na_teraz["notki"],
                                   od=juz.get("notki", 0)):
            if not zostal_czas("notki"):
                return
            gotowe = [k for k in n["candidates"]
                      if k.get("safe_to_post") and k.get("length_ok")]
            if not gotowe:
                continue
            if wyslij:
                if not rytm("notka", "notki", rytm_stanu):
                    return
                wynik = browser.wystaw_notke(gotowe[0]["note"].strip(), wyslij=True)
                # Fakt odhaczamy DOPIERO po potwierdzonej publikacji. Wczesniej
                # znikal juz przy znalezieniu, wiec przepadal takze wtedy, gdy
                # notka nie poszla albo gdy przebieg byl tylko sprawdzeniem.
                if wynik.get("wyslane") and n.get("fakt"):
                    stages.zapisz_zuzyte([n["fakt"]])
                # Dzien promocji artykulu tez odhaczamy dopiero po publikacji —
                # inaczej artykul dostawal mniej niz piec notek promujacych,
                # a nikt by tego nie zauwazyl.
                if wynik.get("wyslane") and n.get("promocja_url"):
                    stages.odhacz_promocje(n["promocja_url"])
                rytm_stanu["notka"] = True
            zrobione["notki"] += 1

    # --- 3. komentarze u innych ----------------------------------------------
    def komentarze() -> None:
        # NOWE KONTA NAJPIERW. Kanal czytelnika pokazuje wylacznie to, co juz
        # znamy — jedenascie publikacji, ktore same z siebie nikogo nowego nie
        # przyprowadza. Wyszukiwarka Substacka oddaje ludzi spoza kregu, i to
        # z zywymi dyskusjami. Kanal zostaje jako uzupelnienie, bo tam sa nasi
        # dotychczasowi rozmowcy.
        # Tylko ARTYKULY. Notki trafialy tu razem z postami i szly sciezka
        # artykulow — a notka nie istnieje pod adresem artykulow, wiec
        # potwierdzenie zawsze padalo. Notki maja wlasny blok nizej.
        pula = [x for x in kanal.szukaj_nowych() + kanal.posty_z_kanalu()
                if x.get("rodzaj") != "notka"]
        widziane, unikalne = set(), []
        for x in pula:
            if x.get("url") and x["url"] not in widziane:
                widziane.add(x["url"])
                unikalne.append(x)
        cele = stages.wybierz_cele(conn, run_id, unikalne)
        for cel in cele[: na_teraz["komentarze"]]:
            if not zostal_czas("komentarze"):
                return
            # Pytamy o prawo do komentowania PRZED pisaniem. Inaczej caly koszt
            # — strona, trzy warianty, sprawdzenie faktow — szedl na tekst,
            # ktorego i tak nie da sie wystawic, a miejsce z dziennego limitu
            # i tak przepadalo.
            if not browser.mozna_komentowac(cel["url"]):
                continue
            strony = browser.read_pages([cel["url"]])
            if not strony or not strony[0].get("text"):
                continue
            out = stages.comment_on(conn, run_id, strony[0])
            dobre = [k for k in out["candidates"]
                     if k.get("comment") and k.get("safe_to_post")]
            if not dobre:
                continue
            if wyslij:
                if not rytm("komentarz", "komentarze", rytm_stanu):
                    return
                browser.wystaw_komentarz(
                    cel["url"], dobre[0]["comment"], wyslij=True,
                    kontekst={**opis_celu(cel),
                              "otwarcie": (out.get("otwarcie") or "")[:60],
                              "postawa": out.get("postawa") or ""})
                # Zapamietujemy U KOGO, zeby nie wracac tam za kilka dni.
                kanal.zapamietaj_komentarz(cel)
                rytm_stanu["komentarz"] = True
            zrobione["komentarze"] += 1

    # --- 3b. dyskusje pod cudzymi notkami -------------------------------------
    def dyskusje() -> None:
        """Wejscie w rozmowe pod cudza notka.

        Dla swiezego konta to najwazniejsze miejsce: pod notkami toczy sie
        rozmowa, a kanal promuje watki, ktore zyja. Komentarz pod artykulem
        czyta kilka osob; sensowna uwaga pod zywa notka trafia do calego watku.
        """
        if not na_teraz["komentarze"]:
            return
        # Dwa zrodla, bo jedno bylo glodowe: przeglad pokazal DWA cele na
        # przebieg, oba z zerem odpowiedzi. Wyszukiwarka oddaje notki spoza
        # naszego kregu, czyli dokladnie tych ludzi, o ktorych nam chodzi.
        notki = kanal.notki_z_kanalu() + [
            {"id": x.get("id"), "tekst": x.get("opis") or x.get("tytul") or "",
             "autor": x.get("pub") or "", "reakcje": x.get("reakcje") or 0,
             "odpowiedzi": x.get("komentarze") or 0, "url": x.get("url") or "",
             "data": x.get("data") or "", "skad": x.get("skad") or ""}
            for x in kanal.szukaj_nowych() if x.get("rodzaj") == "notka"]
        notki = [n for n in notki if n.get("id")]
        if not notki:
            return
        cele = stages.wybierz_cele(
            conn, run_id,
            [{"tytul": n["tekst"][:120], "opis": n["tekst"], "pub": n["autor"],
              "komentarze": n["odpowiedzi"], "reakcje": n["reakcje"],
              "url": n["url"], "id": n["id"], "data": n.get("data", ""),
              "skad": n.get("skad", "kanal")} for n in notki])
        for cel in cele[: max(1, na_teraz["komentarze"] // 2)]:
            if not zostal_czas("dyskusje"):
                return
            out = stages.comment_on(
                conn, run_id,
                {"title": cel.get("tytul", ""), "text": cel.get("opis", ""),
                 "author": cel.get("pub", ""), "url": cel.get("url", "")})
            dobre = [k for k in out["candidates"]
                     if k.get("comment") and k.get("safe_to_post")]
            if not dobre:
                continue
            if wyslij:
                if not rytm("komentarz", "dyskusje", rytm_stanu):
                    return
                browser.wystaw_odpowiedz(cel["id"], dobre[0]["comment"],
                                         wyslij=True,
                                         kontekst=opis_celu(cel))
                rytm_stanu["komentarz"] = True
            zrobione["komentarze"] += 1

    # --- 3c. obserwowanie nowych: to, co poszerza krąg ------------------------
    def obserwuj() -> None:
        """Obserwuje autorów, których teksty faktycznie czytaliśmy.

        Bez tego agent kręciłby się w kółko po tych samych jedenastu
        publikacjach: kanał czytelnika pokazuje to, co obserwujemy, a my nie
        obserwowaliśmy nikogo. Każda nowa obserwacja poszerza pulę ludzi, do
        których w ogóle możemy się odezwać.

        Obserwujemy TYLKO tych, u których naprawdę byliśmy — nie z listy
        podpowiedzi. Obserwowanie kogoś, kogo się nie czytało, to zbieranie
        nazwisk, a nie budowanie kręgu.
        """
        if not na_teraz.get("follow"):
            return
        znani = set(kanal._historia())
        if not znani:
            return
        import random

        kandydaci = [h for h in znani if h and h != f"{config.SUBSTACK_HANDLE}.substack.com"]
        random.shuffle(kandydaci)
        for host in kandydaci[: na_teraz["follow"]]:
            if not zostal_czas("obserwowanie"):
                return
            # Nie `host.split(".")[0]`: przy wlasnej domenie dawalo to "www"
            # i agent probowal obserwowac konto o tej nazwie.
            uchwyt = browser.uchwyt_publikacji(host)
            if not uchwyt:
                print(f"  (nie ustalilem konta dla {host} — pomijam)", flush=True)
                continue
            if wyslij:
                if not rytm("komentarz", "obserwowanie", rytm_stanu):
                    return
                # OBSERWUJEMY, nie subskrybujemy. To dwie rozne rzeczy i maja
                # osobne widelki: obserwacja nie przysyla nic mailem.
                browser.obserwuj_profil(uchwyt, wyslij=True)
                rytm_stanu["komentarz"] = True
            else:
                print(f"  (obserwowałbym: {uchwyt})", flush=True)

    # --- 3d. subskrypcje: rzadko, bo lądują w skrzynce właściciela ------------
    def subskrybuj() -> None:
        """Subskrybuje NIELICZNE publikacje, ktore naprawde czytamy.

        Budzet `subskrypcje` byl liczony i nigdy nieuzywany — blokiem sterowal
        budzet `follow`, a funkcja i tak klikala „Subscribe". Agent subskrybowal
        wiec w tempie obserwacji: do 44 miesiecznie zamiast 6-12, i kazda z nich
        przysylala poczte do skrzynki wlasciciela.
        """
        if not na_teraz.get("subskrypcje"):
            return
        znani = set(kanal._historia())
        if not znani:
            return
        import random

        kandydaci = [h for h in znani
                     if h and h != f"{config.SUBSTACK_HANDLE}.substack.com"]
        random.shuffle(kandydaci)
        for host in kandydaci[: na_teraz["subskrypcje"]]:
            if not zostal_czas("subskrypcje"):
                return
            uchwyt = browser.uchwyt_publikacji(host)
            if not uchwyt:
                continue
            if wyslij:
                if not rytm("komentarz", "subskrypcje", rytm_stanu):
                    return
                browser.zasubskrybuj(uchwyt, wyslij=True)
                rytm_stanu["komentarz"] = True
            else:
                print(f"  (zasubskrybowałbym: {uchwyt})", flush=True)

    # --- 4. polubienia: najtańszy uczciwy sygnał ------------------------------
    def polubienia() -> None:
        w = browser.polub_w_kanale(na_teraz["lajki"], wyslij=wyslij)
        zrobione["polubienia"] = w.get("polubione", 0)

    # --- 5. restacki: cudza notka plus nasze zdanie ---------------------------
    def restacki() -> None:
        """Podanie dalej trafia do kanału NASZYCH obserwujących i powiadamia
        autora oryginału — za cenę jednego zdania zamiast całej notki.

        Stoi po polubieniach świadomie: polubienie nic nie twierdzi, restack
        stawia nasze nazwisko obok cudzego tekstu. Jeśli dzień się kończy
        i coś ma wypaść, ma wypaść to, co niesie więcej ryzyka.
        """
        ile = na_teraz.get("restacki", 0)
        if not ile:
            print("  budżet na dziś: 0 — pomijam", flush=True)
            return
        w = browser.restackuj_w_kanale(
            ile, lambda n: stages.ocen_restack(conn, run_id, n), wyslij=wyslij)
        zrobione["restacki"] = w.get("restackowane", 0)
        if w.get("odmowy"):
            print(f"  odmów: {len(w['odmowy'])} — milczenie jest pełnym wynikiem",
                  flush=True)

    # KOLEJNOSC DECYDUJE O TYM, CO SIE W OGOLE WYDARZY. Zegar przebiegu
    # sprawdzaja bloki od odpowiedzi po subskrypcje; polubienia i restacki nie
    # patrza na niego wcale. Wiec gdy czas sie konczy, wypadaja dokladnie te
    # bloki, ktore sa uczciwe wobec zegara.
    #
    # Obserwowanie stalo za komentarzami — czyli za jedynym blokiem, ktory
    # potrafi zjesc caly budzet czasu (kazdy komentarz to pobranie strony, trzy
    # warianty i sprawdzenie faktow). Skutek zmierzony na dzienniku: przez piec
    # dni ZERO obserwacji przy budzecie 30-44 miesiecznie. Blok nie chodzil
    # w ogole, a nikt tego nie zauwazyl, bo brak wpisu wyglada jak brak okazji.
    #
    # Obserwowanie i subskrypcje ida teraz PRZED komentarze. Sa tanie (jedno
    # wejscie na profil, zero wywolan modelu), maja twardy limit miesieczny,
    # ktorego nie da sie nadrobic pozniej, i to one poszerzaja krag ludzi,
    # do ktorych w ogole mozemy sie potem odezwac.
    # --- 6. kopia listy subskrybentow, gdy sie zestarzala --------------------
    def kopia_listy() -> None:
        """Jedyne aktywo, ktorego nie da sie odtworzyc — i jedyne miejsce,
        gdzie wlasciciel musial dotad cos kliknac.

        Czyta z WLASNEGO panelu wlasna sesja, ta sama droga, ktora agent
        wystawia notki. Odmowa nie jest awaria przebiegu: kopia to
        zabezpieczenie, a nie warunek pracy. Gdy sie nie uda, alarm i tak
        krzyknie nastepnego ranka i wtedy zostaje reczny eksport.
        """
        from datetime import datetime, timezone

        katalog = config.DATA_DIR / "kopie"
        kopie = sorted(katalog.glob("subskrybenci-*.csv"))
        if kopie:
            wiek = (datetime.now(timezone.utc)
                    - datetime.fromtimestamp(kopie[-1].stat().st_mtime,
                                             timezone.utc)).days
            if wiek < config.KOPIA_SUBSKRYBENTOW_CO_ILE_DNI:
                print(f"  ostatnia kopia ma {wiek} dni — jeszcze swieza",
                      flush=True)
                return
        if not wyslij:
            print("  (pobralbym liste subskrybentow)", flush=True)
            return
        try:
            import kopia_subskrybentow
            kopia_subskrybentow.main()
        except Exception as exc:
            print(f"  nie zrobilem kopii: {type(exc).__name__}: {exc}"[:160],
                  flush=True)

    for nazwa, robota in (("odpowiedzi", odpowiedzi), ("notki", notki),
                          ("obserwowanie", obserwuj), ("subskrypcje", subskrybuj),
                          ("komentarze", komentarze), ("dyskusje", dyskusje),
                          ("polubienia", polubienia), ("restacki", restacki),
                          ("kopia listy", kopia_listy)):
        print(f"\n-- {nazwa} --", flush=True)
        blok(nazwa, robota)

    print("\n== dzień zamknięty ==", flush=True)
    for k, v in zrobione.items():
        print(f"   {k}: {v}", flush=True)
    if not wyslij:
        print("   (tryb sprawdzenia — nic nie poszło w świat)", flush=True)
    alarm.sprawdz_sesje_i_ostrzez()
    return 0


def _sygnal_ma_zostawic_slad() -> None:
    """Zamienia SIGTERM na wyjatek, zeby przebieg zdazyl sie zapisac.

    Systemd konczy przebieg SIGTERM-em po `TimeoutStartSec`. Python nie widzi
    sygnalu jako wyjatku, wiec proces po prostu znikal: `finish_run` sie nie
    wykonywalo i wiersz wisial w bazie jako RUNNING az do kontroli zdrowia,
    nawet trzy godziny. Przez ten czas rozdzielnik dziennej normy nie wiedzial,
    czy przebieg trwa, czy zginal.

    Teraz sygnal podnosi wyjatek, wiec dziala ta sama sciezka co przy kazdej
    innej awarii: status FAILED i powod w notatce. Systemd daje jeszcze
    `TimeoutStopSec` (domyslnie 90 s) przed SIGKILL — na zapisanie jednego
    wiersza to bardzo duzo.
    """
    import signal

    def podnies(numer, _ramka):
        raise KeyboardInterrupt(f"przerwany sygnalem {signal.Signals(numer).name}")

    for s in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(s, podnies)
        except (ValueError, OSError, AttributeError):
            pass          # nie glowny watek albo system bez tego sygnalu


def main() -> int:
    _utf8_stdout()
    _sygnal_ma_zostawic_slad()
    try:
        _zamek = zajmij_zamek()   # trzymany do końca procesu
    except JuzDziala as exc:
        print(f"  {exc}", flush=True)
        return 0
    parser = argparse.ArgumentParser(description="agent-v2 — jeden artykuł do szuflady")
    parser.add_argument("--stop-after", choices=STAGES, help="zatrzymaj się po tym etapie")
    parser.add_argument("--use-cache", action="store_true", help="użyj zapisanych wyników etapów")
    parser.add_argument("--topics", type=int, default=6, help="ile tematów ma zwrócić skaut")
    parser.add_argument("--dzien", action="store_true",
                        help="rutyna dnia: notki, komentarze, odpowiedzi, polubienia")
    parser.add_argument("--wyslij", action="store_true",
                        help="NAPRAWDĘ wystaw treści (domyślnie tylko pokazuje)")
    args = parser.parse_args()
    # Musi stac PO parse_args (inaczej `args` jeszcze nie istnieje) i PRZED
    # pierwszym dotknieciem bazy — zeby kopia testowa odpadala, zanim
    # cokolwiek zapisze.
    odmow_publikacji_z_kopii(args.wyslij)

    conn = db.connect()
    run_id = db.start_run(conn)
    stage = "start"

    print(f"== przebieg {run_id} ==", flush=True)
    if args.dzien:
        # `finally` zamykalo przebieg jako DONE takze wtedy, gdy sie wywalil —
        # i tak wlasnie zapisal sie przebieg, ktory padl na `KeyError: notki`.
        # Dwie szkody: statystyka bledow milczala, a rozdzielnik dziennej normy
        # liczyl ten przebieg jako odbyty i chcial wcisnac cala reszte w jeden
        # nastepny. Przerwany przebieg ma byc widoczny jako przerwany.
        try:
            wynik = dzien(conn, run_id, args.wyslij)
        except BaseException as exc:
            db.finish_run(conn, run_id, "FAILED", "dzien",
                          f"{type(exc).__name__}: {exc}"[:500])
            _summary(conn, run_id)
            raise
        db.finish_run(conn, run_id, "DONE", "dzien", "")
        _summary(conn, run_id)
        return wynik
    print(
        f"   baza: {config.DB_PATH}   "
        f"sufit przebiegu: {config.RUN_LIMIT_USD} USD"
        f"{'   TANIO (DeepSeek)' if config.CHEAP_MODE else ''}"
        f"{'   DRY_RUN' if config.DRY_RUN else ''}",
        flush=True,
    )

    # NIE ZACZYNAJ TEGO, CZEGO NIE SKONCZYSZ — ta sama zasada co przy przerwach
    # miedzy dzialaniami. Sufit miesieczny jest egzekwowany PRZED KAZDYM
    # wywolaniem, wiec artykul mogl paść w dowolnym miejscu: po oplaconym
    # researchu i przed napisaniem, albo po napisaniu i przed recenzja.
    # Pieniadze wydane, artykulu nie ma. Skoro znamy koszt calego przebiegu
    # (RUN_LIMIT_USD), umiemy o to zapytac zawczasu.
    if not config.NO_LIMIT:
        from datetime import datetime as _dt, timezone as _tz

        _m = _dt.now(_tz.utc).strftime("%Y-%m")
        _zostalo = config.MONTHLY_LIMIT_USD - db.spent_usd(conn, _m)
        if _zostalo < config.RUN_LIMIT_USD:
            print(f"   MIESIAC NA WYCZERPANIU: zostalo ${_zostalo:.2f}, a caly "
                  f"artykul to do ${config.RUN_LIMIT_USD}. Nie zaczynam — "
                  f"lepiej nie napisac nic niz zaplacic za polowe.", flush=True)
            return _done(conn, run_id, "budzet")

    try:
        stage = "scout"
        topics = cached(stage, lambda: stages.scout(conn, run_id, args.topics), args.use_cache)
        print(f"\n-- tematy ({len(topics)}) --", flush=True)
        for i, topic in enumerate(topics):
            print(f"{i}. {topic.get('title')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "feasibility"
        assessments = cached(
            stage, lambda: stages.feasibility(conn, run_id, topics), args.use_cache
        )
        topic, verdict = stages.pick_topic(topics, assessments, run_id)
        print("\n-- odsiew wykonalności --", flush=True)
        for a in assessments:
            mark = "TAK " if a.get("feasible") else "nie "
            print(
                f"  {mark} [{a.get('index')}] pewność={a.get('confidence')}"
                f" źródeł~{a.get('expected_primary_sources')}  {a.get('note', '')[:110]}",
                flush=True,
            )
        print(f"\n>> wybrany temat: {topic.get('title')}", flush=True)
        print(f"   {topic.get('question')}", flush=True)
        print(f"   uzasadnienie: {verdict.get('note', '')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "discovery"
        recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
        sources = cached(
            stage,
            lambda: stages.discovery(conn, run_id, topic["question"], recent),
            args.use_cache,
        )
        print(f"\n-- znalezione źródła ({len(sources)}) --", flush=True)
        for s in sources:
            print(
                f"  [{s.get('class', '?'):9}] {s.get('host')}"
                f"{'  DLACZEGO' if s.get('answers_why') else ''}"
                f"{'  LICZBY' if s.get('has_numbers') else ''}",
                flush=True,
            )
            print(f"      {s.get('title', '')[:100]}", flush=True)
        primary = sum(1 for s in sources if s.get("class") == "PRIMARY")
        why = sum(1 for s in sources if s.get("answers_why"))
        print(
            f"\n   pierwotnych: {primary}/{config.MIN_PRIMARY_SOURCES}   "
            f"wyjaśniających DLACZEGO: {why}/{config.MIN_WHY_SOURCES}   "
            f"organizacji: {len({s.get('host') for s in sources})}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "fetch"
        print("\n-- pobieranie --", flush=True)
        corpus = cached(stage, lambda: stages.fetch(conn, run_id, sources), args.use_cache)
        chars = sum(len(s.get("text", "")) for s in corpus)
        print(
            f"\n   pobrano {len(corpus)}/{len(sources)}   "
            f"{chars} znaków   pierwotnych: "
            f"{sum(1 for s in corpus if s.get('class') == 'PRIMARY')}",
            flush=True,
        )
        # --- druga runda, gdy korpus wyszedl chudy ---------------------------
        # Artykul o SPF poszedl do pisarza z TRZEMA zrodlami z dziesieciu
        # proponowanych. To nie jest wada stylu, tylko wada materialu: cienka
        # karta dowodowa znaczy mniej liczb, slabsze paralele i wiecej miejsc,
        # gdzie pisarz musi dolozyc cos z pamieci — i wlasnie tam wyszedl
        # jedyny fakt bez pokrycia w tym tekscie.
        #
        # Druga dyskoveria kosztuje ~$0,28. Artykul napisany z trzech zrodel
        # kosztuje caly przebieg i wychodzi cienki, wiec to sie oplaca.
        if len(corpus) < config.MIN_ZRODEL_DO_PISANIA:
            print(f"\n-- za chudo ({len(corpus)} < {config.MIN_ZRODEL_DO_PISANIA})"
                  " — druga runda --", flush=True)
            try:
                juz_mamy = {s.get("host") or s.get("url", "") for s in corpus}
                dodatkowe = [
                    s for s in stages.discovery(conn, run_id, topic["question"],
                                                recent)
                    if (s.get("host") or s.get("url", "")) not in juz_mamy
                ]
                if dodatkowe:
                    dobrane = stages.fetch(conn, run_id, dodatkowe)
                    corpus = corpus + dobrane
                    print(f"   dobrano {len(dobrane)} z {len(dodatkowe)} nowych"
                          f" — korpus ma teraz {len(corpus)} zrodel", flush=True)
                else:
                    print("   druga runda nie znalazla nowych adresow", flush=True)
            except Exception as exc:
                # Dobieranie jest premia, nie warunkiem. Jego awaria nie moze
                # zabic przebiegu, za ktorego research juz zaplacilismy.
                print(f"  [awaria] druga runda padla ({exc}) — pisze z tego, co jest",
                      flush=True)

        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "classify"
        print("\n-- klasyfikacja i wyciąg fragmentów --", flush=True)
        evidence = cached(
            stage,
            lambda: stages.classify(conn, run_id, topic["question"], corpus),
            args.use_cache,
        )
        n_ex = sum(len(s["excerpts"]) for s in evidence)
        n_num = sum(len(s["numbers"]) for s in evidence)
        print(
            f"\n   materiał dowodowy: {len(evidence)} źródeł, {n_ex} fragmentów, "
            f"{n_num} liczb   pierwotnych: "
            f"{sum(1 for s in evidence if s['class'] == 'PRIMARY')}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        # Od tego miejsca artykuł MUSI powstać. Temat jest wybrany, research
        # zrobiony i opłacony — żaden dalszy etap nie ma prawa zabić przebiegu.
        stage = "synthesis"
        print("\n-- synteza --", flush=True)
        try:
            card = cached(
                stage,
                lambda: stages.synthesis(conn, run_id, topic["question"], evidence),
                args.use_cache,
            )
        except Exception as exc:
            print(f"  [awaria] synteza padła ({exc}) — składam kartę z dowodów", flush=True)
            card = stages.fallback_card(topic["question"], evidence)
        print(f"\n   teza: {card.get('working_thesis', '')}", flush=True)
        print(f"\n   mechanizm: {card.get('main_mechanism', '')[:400]}", flush=True)
        print(f"\n   potwierdzone twierdzenia ({len(card.get('confirmed_claims', []))}):", flush=True)
        for c in card.get("confirmed_claims", []):
            print(f"     • {c.get('claim', '')[:150]}", flush=True)
        print(f"\n   liczby ({len(card.get('citable_numbers', []))}):", flush=True)
        for n in card.get("citable_numbers", []):
            print(f"     • {n.get('value')} — {n.get('means', '')[:110]}", flush=True)
        for label, key in (("niepewne", "uncertain_claims"),
                           ("sprzeczności", "contradictions"),
                           ("czego nie ustalono", "not_established")):
            items = card.get(key) or []
            if items:
                print(f"\n   {label} ({len(items)}):", flush=True)
                for item in items:
                    print(f"     • {str(item)[:150]}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        # --- czy jest tu luka, ktora obcy poczuje ----------------------------
        # Bramka stoi PRZED pisarzem, bo po nim byloby za pozno: research
        # oplacony, a artykul i tak martwy. Nic nie blokuje — werdykt DOLOZ
        # wysyla nas do banku po pare, zamiast zatrzymywac przebieg.
        stage = "warto_pisac"
        print("\n-- czy jest tu luka --", flush=True)
        try:
            ocena = stages.warto_pisac(conn, run_id, card)
            wiara = (ocena.get("contradicted_belief") or {}).get("the_belief", "")
            print("   zlamane przekonanie: %s"
                  % ("TAK" if ocena["przekonanie"] else "NIE"), flush=True)
            if wiara:
                print('   czytelnik wierzy: "%s"' % str(wiara)[:120], flush=True)
            print("   filary: %d z 3  (%s)" % (
                ocena["ile_filarow"],
                ", ".join(k for k, v in ocena["filary"].items() if v) or "zaden"),
                flush=True)
            print("   >> %s — %s" % (ocena["werdykt"], ocena["powod"]), flush=True)

            if ocena["werdykt"] == "DOLOZ":
                # TO JEST MOMENT, DLA KTOREGO BANK ISTNIEJE. Temat ma luke, ale
                # za malo materialu, zeby ja rozwinac. Bibliotekarz szuka
                # w zaplaconych resztkach mechanizmu z INNEJ dziedziny —
                # tak wlasnie powstal najlepszy tekst serii.
                print("   szukam pary w banku...", flush=True)
                bank = stages.bank_fragmentow(conn)
                if not bank:
                    print("   bank pusty — pisarz dostaje karte jak jest", flush=True)
                else:
                    grupy = stages.bibliotekarz(conn, run_id, bank).get("groups") or []
                    dolozone = [{"domain": ", ".join(g.get("dziedziny", [])),
                                 "mechanism": g.get("mechanism", ""), "z_banku": True}
                                for g in grupy[:2]]
                    if dolozone:
                        card.setdefault("parallel_mechanisms", []).extend(dolozone)
                        print("   dolozono %d mechanizmow z banku:" % len(dolozone),
                              flush=True)
                        for d in dolozone:
                            print("     • [%s] %s"
                                  % (d["domain"], d["mechanism"][:110]), flush=True)
                    else:
                        print("   bank nie ma pary — pisarz dostaje karte jak jest",
                              flush=True)
            card["ocena_ciekawosci"] = ocena
        except Exception as exc:
            # Bramka jest doradcza. Jej awaria nie moze kosztowac oplaconego
            # researchu — artykul powstaje tak czy owak.
            print("  [awaria] bramka ciekawosci padla (%s) — pisze bez niej" % exc,
                  flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "write"
        print("\n-- pisanie --", flush=True)
        try:
            glebokosc = str(verdict.get("depth") or "RICH").upper()
            draft = cached(stage,
                           lambda: stages.write(conn, run_id, card, glebokosc),
                           args.use_cache)
        except Exception as exc:
            # Jedno powtórzenie na Opusie, bo tu ginie cały opłacony research.
            # Opus jest sprawdzonym pisarzem tego potoku; jeśli skonfigurowany
            # model odmówił albo padł, powtórka na nim ma największą szansę.
            print(
                f"  [awaria] pisarz ({config.MODEL_FOR['write']}) padł: {exc}"
                f" — powtarzam na {config.CLAUDE}",
                flush=True,
            )
            config.MODEL_FOR["write"] = config.CLAUDE
            draft = stages.write(conn, run_id, card, glebokosc)
        words = len(draft["body"].split())
        print(f"\n   tytuł: {draft.get('title')}", flush=True)
        print(f"   podtytuł: {draft.get('subtitle', '')}", flush=True)
        print(
            f"   długość: {words} słów "
            f"(cel {config.TARGET_WORDS}, zakres {config.MIN_WORDS}-{config.MAX_WORDS})",
            flush=True,
        )
        print(f"   akapit o granicach: {draft.get('limits_paragraph_present')}", flush=True)
        # Czy liczba jest w korpusie, liczy WYŁĄCZNIE gates.py. Stała tu druga
        # implementacja tego samego pytania i natychmiast dała inną odpowiedź
        # (uznała 'E 938' za zmyślone) — to jest ta sama choroba, przez którą
        # przepisujemy starego agenta.
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "review"
        print("\n-- recenzja --", flush=True)
        try:
            report = cached(
                stage, lambda: stages.review(conn, run_id, card, draft), args.use_cache
            )
        except Exception as exc:
            # Recenzja nic nie blokuje, więc jej brak też nie może. Artykuł
            # trafia do szuflady z adnotacją, że nie został rozliczony zdanie
            # po zdaniu — właściciel wie, na co patrzy.
            print(f"  [awaria] recenzja padła ({exc}) — zapisuję bez niej", flush=True)
            report = {"sentences": [], "unsupported_facts": [],
                      "summary": f"recenzja niedostępna: {type(exc).__name__}"}
        sentences = report.get("sentences", [])
        counts = {k: sum(1 for s in sentences if s.get("class") == k)
                  for k in ("FACT", "INFERENCE", "PROSE")}
        # SKLADAMY Z DWOCH ZRODEL, NIE Z JEDNEGO. Recenzent klasyfikuje KAZDE
        # zdanie (`supported`) i osobno powtarza te nieoparte w zbiorczej
        # liscie. Czytalismy wylacznie liste — czyli ufali, ze model poprawnie
        # przepisze wlasny wynik w drugie miejsce. Zdanie oznaczone jako
        # nieoparte, ale niepowtorzone, przepadalo bez sladu, i to jest glowny
        # sygnal jakosci faktograficznej calego potoku.
        #
        # Na przebiegu 25 model sie nie pomylil (1 oznaczone, 1 w liscie). To
        # dowod, ze raz nie zawiodl, a nie ze nie zawiedzie — a redundancja
        # miedzy dwoma polami tej samej odpowiedzi jest dokladnie tym, czego
        # kod nie powinien zakladac.
        unsupported = list(report.get("unsupported_facts", []) or [])
        znane = {str(x.get("text", ""))[:60] for x in unsupported}
        dopisane = 0
        for s in sentences:
            if s.get("class") != "FACT" or s.get("supported") is not False:
                continue
            if str(s.get("text", ""))[:60] in znane:
                continue
            unsupported.append({"text": s.get("text", ""),
                                "why": s.get("why", "")})
            dopisane += 1
        if dopisane:
            print(f"   [recenzja] {dopisane} zdań oznaczonych jako nieoparte, "
                  f"których model nie powtórzył w liście zbiorczej — dopisuję",
                  flush=True)
        print(
            f"   zdań: {len(sentences)}   fakty: {counts['FACT']}   "
            f"wnioskowanie: {counts['INFERENCE']}   proza: {counts['PROSE']}",
            flush=True,
        )

        # ZATRZYMANIE PO RECENZJI. `review` i `forma` byly w STAGES, wiec
        # argparse przyjmowal je jako `--stop-after` bez slowa sprzeciwu —
        # a po nich NIE BYLO ani jednego sprawdzenia. `--stop-after review
        # --wyslij` szedl wiec do konca i PUBLIKOWAL. Flaga, ktora ma
        # zatrzymac przed publikacja, a publikuje, jest gorsza od jej braku:
        # brak widac od razu, cicha bezczynnosc dopiero po fakcie.
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        # Obserwacja formy — osobne wywołanie od recenzji. Recenzent chroni
        # wnioskowanie przed zgłoszeniem (śmiała interpretacja nie jest wadą),
        # a ta bramka liczy m.in. zastrzeżenia; złączone tępiłyby się nawzajem.
        # Jak recenzja: nic nie blokuje, więc jej awaria też nie może.
        stage = "forma"
        try:
            forma = cached(stage, lambda: stages.ocen_forme(conn, run_id, draft),
                           args.use_cache)
            przekonania = forma.get("beliefs") or []
            slow = len(draft["body"].split("## Sources")[0].split())
            print(f"   przekonania czytelnika: {len(przekonania)}"
                  f"   (samo wsparcie: {len(forma.get('support_only') or [])})"
                  f"   jedno co {slow / max(1, len(przekonania)):.0f} słów",
                  flush=True)
            moment = (forma.get("reader_moment") or {}).get("quote", "")
            gdzie = gates.pozycja_w_tekscie(moment, draft["body"])
            print("   przyłapanie czytelnika: %s"
                  % (f"{100 * gdzie:.0f}% głębokości" if gdzie is not None
                     else ("jest, ale nie znalazłem w tekście" if moment else "brak")),
                  flush=True)
        except Exception as exc:
            print(f"  [awaria] obserwacja formy padła ({exc}) — idę dalej",
                  flush=True)
            forma = {}

        findings = gates.deterministic_floors(
            draft["body"], card, poprzednie=stages.poprzednie_teksty(pomin_tresc=draft["body"]))
        findings.extend(gates.uwagi_z_formy(forma, draft["body"]))
        for item in unsupported:
            findings.append({"gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")})

        print("\n-- uwagi (nic nie blokuje) --", flush=True)
        if findings:
            for f in findings:
                print(f"   [{f['gate']}] {f['detail'][:160]}", flush=True)
        else:
            print("   czysto — żadna uwaga", flush=True)

        status, blocked_by = gates.verdict(findings)
        notes = [*findings,
                 {"gate": "DLUGOSC", "detail": f"{len(draft['body'].split())} słów"},
                 {"gate": "RECENZJA", "detail": report.get("summary", "")}]
        # Temat wzięty MIMO odrzucenia przez odsiew ma o tym powiedzieć.
        # `pick_topic` ustawiał flagę i pisał w komentarzu, że „zapisuje to
        # w uwagach" — a nie zapisywał: `verdict` żyje dalej tylko po to, by
        # oddać `depth`. Właściciel czytający `.uwagi.md` nie dowiadywał się,
        # że tekst powstał z tematu, którego wykonalność odrzuciła.
        if verdict.get("mimo_odrzucenia"):
            notes.append({
                "gate": "TEMAT_MIMO_ODRZUCENIA",
                "detail": ("żaden temat nie przeszedł odsiewu wykonalności — "
                           "wzięty najlepszy z odrzuconych (pewność %.2f, "
                           "spodziewane źródła %s)"
                           % (float(verdict.get("confidence") or 0),
                              verdict.get("expected_primary_sources"))),
            })
        if args.stop_after == "forma":
            return _done(conn, run_id, "forma")

        # Fragmenty, których artykuł nie zużył, zostają zapisane razem z kartą.
        # Każdy przebieg zbiera ich kilkadziesiąt, a tekst bierze kilka — reszta
        # to gotowe, ocytowane fakty na notki w dni bez artykułu.
        card["unused_evidence"] = [
            {"url": s["url"], "publisher": s.get("publisher"), "excerpts": s["excerpts"],
             "numbers": s["numbers"]}
            for s in evidence
        ]
        path = stages.save(conn, run_id, topic, card, draft, status, blocked_by, notes)

        print(f"\n>> {status}" + (f" ({blocked_by})" if blocked_by else ""), flush=True)
        print(f">> zapisano: {path}", flush=True)

        # OKLADKA POWSTAJE Z ARTYKULEM, NIE Z PUBLIKACJA. Stala wczesniej
        # wewnatrz galezi `--wyslij`, wiec kazdy przebieg bez publikacji
        # zapisywal na dysk artykul BEZ okladki, a cala sciezka graficzna
        # sprawdzala sie wylacznie na zywo, za prawdziwe pieniadze i przy
        # prawdziwej publikacji. Dlatego okladka zgubiona przez usterke
        # zapisu wywolan wyszla na jaw dopiero po fakcie: nie bylo ani
        # jednego przebiegu, w ktorym mogla sie zepsuc bezpiecznie.
        #
        # Grafika NIGDY nie zatrzymuje artykulu: brak czterech centow na
        # obrazek nie moze wyrzucic do kosza researchu za czterdziesci.
        stages.grafika(conn, run_id, draft, sciezka_artykulu=path)

        if args.wyslij:
            import browser

            print("\n-- publikacja --", flush=True)
            wynik = browser.wystaw_artykul(path, wyslij=True)
            print(f">> {'OPUBLIKOWANY' if wynik.get('wyslane') else 'NIE POSZEDŁ'}"
                  f"{'  ' + str(wynik.get('blad')) if wynik.get('blad') else ''}",
                  flush=True)
        return _done(conn, run_id, stage)

    except Exception as exc:
        db.finish_run(conn, run_id, "FAILED", stage, f"{type(exc).__name__}: {exc}"[:500])
        print(f"\n!! stanęło na etapie {stage}: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        _summary(conn, run_id)
        return 1
    finally:
        conn.close()


def _done(conn, run_id: int, stage: str) -> int:
    db.finish_run(conn, run_id, "DONE", stage, f"zatrzymany po etapie {stage}")
    _summary(conn, run_id)
    return 0


def _summary(conn, run_id: int) -> None:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total, COUNT(*) AS n FROM calls WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    print(f"\n== koszt przebiegu: ${row['total']:.4f} w {row['n']} wywołaniach ==", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
