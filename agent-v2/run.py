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
    "classify", "synthesis", "write", "review",
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


def zostal_czas(na_co: str = "") -> bool:
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
    if zostalo > 0:
        return True
    print(f"  czas przebiegu wyczerpany — odpuszczam {na_co or 'reszte'}"
          f" (dokoncze w nastepnym przebiegu)", flush=True)
    return False


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
    zostalo = {k: max(0, budzet[k] - juz.get(k, 0))
               for k in ("notki", "komentarze", "lajki")}
    # Reszte dzielimy przez przebiegi, ktore JESZCZE dzis beda — nie przez
    # wszystkie. Dzielenie przez wszystkie systematycznie zaniza: przy budzecie
    # 16 komentarzy trzy przebiegi braly 5, 4 i 2, czyli 11 zamiast 16. Przez
    # pozostale wychodzi 5, 6 i 5. Ostatni przebieg dnia dzieli przez jeden,
    # wiec dobiera cala reszte i norma sie domyka.
    zostalo_przebiegow = ile_przebiegow_zostalo(conn)
    na_teraz = {k: max(1, round(v / zostalo_przebiegow)) if v else 0
                for k, v in zostalo.items()}
    print(f"   dzis juz: notki={juz.get('notki', 0)} "
          f"komentarze={juz.get('komentarze', 0)} lajki={juz.get('lajki', 0)}   "
          f"przebiegow zostalo: {zostalo_przebiegow}   "
          f"w tym przebiegu: notki={na_teraz['notki']} "
          f"komentarze={na_teraz['komentarze']} lajki={na_teraz['lajki']}",
          flush=True)
    zrobione = {"notki": 0, "komentarze": 0, "odpowiedzi": 0, "polubienia": 0}

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
                if c.get("gdzie") == "artykul":
                    browser.wystaw_odpowiedz_pod_artykulem(
                        c.get("url") or "", c.get("autor") or "", tekst,
                        wyslij=True)
                else:
                    browser.wystaw_odpowiedz(c["pod_id"], tekst, wyslij=True)
                stages.odczekaj("odpowiedz")
            zrobione["odpowiedzi"] += 1

    # --- 2. notki: pięć dziennie, każda z innego faktu ------------------------
    def notki() -> None:
        if not na_teraz["notki"]:
            print("  dzienny przydzial notek juz wyczerpany", flush=True)
            return
        for n in stages.notki_dnia(conn, run_id, ile=na_teraz["notki"],
                                   od=juz.get("notki", 0)):
            if not zostal_czas("notki"):
                return
            gotowe = [k for k in n["candidates"]
                      if k.get("safe_to_post") and k.get("length_ok")]
            if not gotowe:
                continue
            if wyslij:
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
                stages.odczekaj("notka")
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
                browser.wystaw_komentarz(
                    cel["url"], dobre[0]["comment"], wyslij=True,
                    kontekst={**opis_celu(cel),
                              "otwarcie": (out.get("otwarcie") or "")[:60],
                              "postawa": out.get("postawa") or ""})
                # Zapamietujemy U KOGO, zeby nie wracac tam za kilka dni.
                kanal.zapamietaj_komentarz(cel)
                stages.odczekaj("komentarz")
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
                browser.wystaw_odpowiedz(cel["id"], dobre[0]["comment"],
                                         wyslij=True,
                                         kontekst=opis_celu(cel))
                stages.odczekaj("komentarz")
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
        if not budzet.get("follow"):
            return
        znani = set(kanal._historia())
        if not znani:
            return
        import random

        kandydaci = [h for h in znani if h and h != f"{config.SUBSTACK_HANDLE}.substack.com"]
        random.shuffle(kandydaci)
        for host in kandydaci[: budzet["follow"]]:
            if not zostal_czas("obserwowanie"):
                return
            # Nie `host.split(".")[0]`: przy wlasnej domenie dawalo to "www"
            # i agent probowal obserwowac konto o tej nazwie.
            uchwyt = browser.uchwyt_publikacji(host)
            if not uchwyt:
                print(f"  (nie ustalilem konta dla {host} — pomijam)", flush=True)
                continue
            if wyslij:
                # OBSERWUJEMY, nie subskrybujemy. To dwie rozne rzeczy i maja
                # osobne widelki: obserwacja nie przysyla nic mailem.
                browser.obserwuj_profil(uchwyt, wyslij=True)
                stages.odczekaj("komentarz")
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
        if not budzet.get("subskrypcje"):
            return
        znani = set(kanal._historia())
        if not znani:
            return
        import random

        kandydaci = [h for h in znani
                     if h and h != f"{config.SUBSTACK_HANDLE}.substack.com"]
        random.shuffle(kandydaci)
        for host in kandydaci[: budzet["subskrypcje"]]:
            if not zostal_czas("subskrypcje"):
                return
            uchwyt = browser.uchwyt_publikacji(host)
            if not uchwyt:
                continue
            if wyslij:
                browser.zasubskrybuj(uchwyt, wyslij=True)
                stages.odczekaj("komentarz")
            else:
                print(f"  (zasubskrybowałbym: {uchwyt})", flush=True)

    # --- 4. polubienia: najtańszy uczciwy sygnał ------------------------------
    def polubienia() -> None:
        w = browser.polub_w_kanale(na_teraz["lajki"], wyslij=wyslij)
        zrobione["polubienia"] = w.get("polubione", 0)

    for nazwa, robota in (("odpowiedzi", odpowiedzi), ("notki", notki),
                          ("komentarze", komentarze), ("dyskusje", dyskusje),
                          ("obserwowanie", obserwuj), ("subskrypcje", subskrybuj),
                          ("polubienia", polubienia)):
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
        topic, verdict = stages.pick_topic(topics, assessments)
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

        stage = "write"
        print("\n-- pisanie --", flush=True)
        try:
            draft = cached(stage, lambda: stages.write(conn, run_id, card), args.use_cache)
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
            draft = stages.write(conn, run_id, card)
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
        unsupported = report.get("unsupported_facts", []) or []
        print(
            f"   zdań: {len(sentences)}   fakty: {counts['FACT']}   "
            f"wnioskowanie: {counts['INFERENCE']}   proza: {counts['PROSE']}",
            flush=True,
        )

        findings = gates.deterministic_floors(draft["body"], card)
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

        if args.wyslij:
            import browser

            # Grafika NIGDY nie zatrzymuje artykułu: brak czterech centów na
            # obrazek nie może wyrzucić do kosza researchu za czterdzieści.
            stages.grafika(conn, run_id, draft, sciezka_artykulu=path)
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
