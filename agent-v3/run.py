"""Jedno polecenie uruchamiające — to samo lokalnie i na serwerze.

    python agent-v3/run.py
    python agent-v3/run.py --stop-after scout
    python agent-v3/run.py --use-cache          # nie płać drugi raz za identyczny etap

Bez interaktywnych promptów: na serwerze nie ma komu odpowiedzieć. Logi na
stdout, żeby harmonogram je przechwycił.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import sys
import traceback
from typing import Any, Callable

import capabilities
import config
import db
import editorial
import gates
import mutation_ledger
import operational_day
import provenance
import stages
import model_contracts

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


PROMPT_FOR_STAGE = {
    "scout": "skaut.md",
    "feasibility": "wykonalnosc.md",
    "discovery": "dyskoveria.md",
    "classify": "klasyfikacja.md",
    "synthesis": "synteza.md",
    "warto_pisac": "warto_pisac.md",
    "write": "pisarz.md",
    "review": "recenzent.md",
    "forma": "forma.md",
    "bibliotekarz": "bibliotekarz.md",
}


def _prompt_fingerprint(stage: str) -> str:
    """Hash tylko wejsc wykonywalnych danego etapu.

    Jeden globalny hash wszystkich promptow powodowal, ze korekta odsiewu
    uniewazniala oplacony Scout i normalny segment probowal wywolac go drugi
    raz. Cache jednego etapu nie moze zalezec od promptu innej roli.
    """
    digest = hashlib.sha256()
    filename = PROMPT_FOR_STAGE.get(stage)
    if filename:
        path = config.PROMPTS_DIR / filename
        digest.update(filename.encode("utf-8"))
        digest.update(path.read_bytes())
    contract = model_contracts.CONTRACTS.get(stage)
    if contract is not None:
        digest.update(contract.id.encode("ascii"))
    if not filename and contract is None:
        digest.update(f"deterministic:{stage}".encode("utf-8"))
    return digest.hexdigest()[:20]


def cached(
    stage: str, produce: Callable[[], Any], use_cache: bool,
    input_data: Any,
) -> Any:
    """Cache jest kontraktem wejścia, promptu i modelu, nie nazwą etapu.

    V2 zapisywało `cache/scout.json`. Po tygodniu `--use-cache` mogło więc
    podać stare tematy do nowego przebiegu i odtworzyć cały stary artykuł.
    """
    identity = {
        "version": 4,
        "stage": stage,
        "input": input_data,
        "prompt_version": _prompt_fingerprint(stage),
        "model": config.MODEL_FOR.get(stage, "deterministic"),
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    path = CACHE_DIR / stage / f"{key}.json"
    if use_cache and path.exists():
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("identity") == identity:
            print(f"  [{stage}] z bezpiecznej pamięci {key} — bez opłaty", flush=True)
            return envelope["value"]
    value = produce()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"identity": identity, "value": value},
                               ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    return value


class JuzDziala(RuntimeError):
    pass


def odmow_publikacji_z_kopii(wyslij: bool) -> None:
    """Sprawdza maszynowy kontrakt live_test przed pierwszym zapisem lokalnym."""
    if not wyslij:
        return
    try:
        capabilities.require(capabilities.Capability.PUBLISH_ARTICLE)
    except capabilities.CapabilityDenied as exc:
        raise SystemExit(f"ODMOWA POLITYKI V3: {exc}") from exc


def mutacja_niepewna(wynik: dict[str, Any]) -> bool:
    """UNKNOWN, także odziedziczony z ledgeru, zatrzymuje dalsze mutacje."""
    if wynik.get("status") in {"PENDING", "UNKNOWN"}:
        return True
    if wynik.get("blocked_by_status") in {"PENDING", "UNKNOWN"}:
        return True
    return any(
        proba.get("status") in {"PENDING", "UNKNOWN"}
        for proba in wynik.get("attempts", [])
        if isinstance(proba, dict)
    )


def nowy_sukces(wynik: dict[str, Any], pole: str = "wyslane") -> bool:
    """Licznik przebiegu obejmuje potwierdzone działanie wykonane teraz."""
    return bool(wynik.get(pole)) and not bool(wynik.get("pominiete"))


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


def ile_przebiegow_zostalo(conn, kiedy=None) -> int:
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
    plan = operational_day.get_or_create(conn, at=kiedy)
    (zamkniete,) = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE stage = 'dzien' AND status = 'DONE' "
        "AND finished_at >= ? AND finished_at < ?",
        (plan["starts_at"], plan["ends_at"]),
    ).fetchone()
    return max(1, config.PRZEBIEGOW_DZIENNIE - int(zamkniete))


def dzien(conn, run_id: int, wyslij: bool) -> int:
    """Jeden dzień pracy konta: notki, komentarze, odpowiedzi, polubienia.

    Rutyna, której do tej pory nie było — każda zdolność działała osobno, a nic
    ich nie spinało. Trzy zasady, wszystkie z rzeczy, które nas już kosztowały:

    1. KAŻDY BLOK OSOBNO. Padnięte komentarze nie zabierają ze sobą notek.
       Dzień częściowo udany jest znacznie lepszy od dnia przerwanego w połowie.
    2. ODPOWIEDZI MAJĄ PIERWSZEŃSTWO, ale także osobny twardy limit awaryjny.
       Priorytet nie może oznaczać nieograniczonej autonomicznej mutacji.
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
    plan = operational_day.snapshot(conn)

    # Jedynym licznikiem bezpieczeństwa jest transakcyjny ledger SQLite.
    # JSONL pozostaje czytelną telemetrią, a odczyt profilu rekoncyliacją źródła;
    # awaria któregokolwiek nie może już oddać zużytej jednostki budżetu.
    juz = plan["accounted"]
    zostalo = {
        k: max(0, int(budzet[k]) - int(juz.get(k, 0))) for k in budzet
    }

    # CICHY DZIEN. Wyciszamy to, co NADAJEMY — notki i restacki. Komentarze,
    # polubienia i obserwacje zostaja, bo to jest czytanie cudzych rzeczy,
    # a nie nadawanie wlasnych. Odpowiedzi zostaja tym bardziej: nieodpisanie
    # komus, kto sie do nas odezwal, nie jest cisza tylko lekcewazeniem.
    if plan["quiet_day"]:
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
          f"follow={juz.get('follow', 0)} subskrypcje={juz.get('subskrypcje', 0)}   "
          f"przebiegow zostalo: {zostalo_przebiegow}   "
          f"w tym przebiegu: notki={na_teraz['notki']} "
          f"komentarze={na_teraz['komentarze']} lajki={na_teraz['lajki']}",
          flush=True)
    zrobione = {"notki": 0, "komentarze": 0, "odpowiedzi": 0,
                "polubienia": 0, "restacki": 0, "follow": 0,
                "subskrypcje": 0}
    # Czy dany rodzaj dzialania juz w tym przebiegu wyszedl. Wspolne dla
    # wszystkich blokow, bo profil widzi jeden ciag zdarzen, nie nasze bloki:
    # komentarz tuz po obserwacji to dla Substacka dwa dzialania pod rzad.
    rytm_stanu: dict[str, bool] = {}
    stan_mutacji = {"unknown": False}

    def zatrzymaj_po_unknown(wynik: dict[str, Any]) -> bool:
        if not mutacja_niepewna(wynik):
            return False
        stan_mutacji["unknown"] = True
        print("  stan mutacji UNKNOWN — kończę część mutującą przebiegu",
              flush=True)
        return True

    def wyczerpany_budzet(wynik: dict[str, Any]) -> bool:
        if wynik.get("blocked_by_status") != "BUDGET_EXHAUSTED":
            return False
        print(
            f"  budżet {wynik.get('budget_category')} wyczerpany "
            f"({wynik.get('budget_accounted')}/{wynik.get('budget_limit')})",
            flush=True,
        )
        return True

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

    # --- 1. odpowiedzi pod własnymi treściami: pierwsze, z twardym limitem ----
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
        if not na_teraz.get("odpowiedzi"):
            print("  twardy budżet odpowiedzi wyczerpany", flush=True)
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
        for c in czekaja[: na_teraz["odpowiedzi"]]:
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
                    wynik = browser.wystaw_odpowiedz_pod_artykulem(
                        c.get("url") or "", c.get("autor") or "", tekst,
                        wyslij=True)
                else:
                    wynik = browser.wystaw_odpowiedz(
                        c["pod_id"], tekst, wyslij=True)
                if nowy_sukces(wynik):
                    rytm_stanu["odpowiedz"] = True
                    zrobione["odpowiedzi"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return

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
                if nowy_sukces(wynik):
                    rytm_stanu["notka"] = True
                    zrobione["notki"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return

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
                wynik = browser.wystaw_komentarz(
                    cel["url"], dobre[0]["comment"], wyslij=True,
                    kontekst={**opis_celu(cel),
                              "otwarcie": (out.get("otwarcie") or "")[:60],
                              "postawa": out.get("postawa") or ""})
                if wynik.get("wyslane"):
                    # Historia celu opisuje wyłącznie potwierdzone działanie.
                    kanal.zapamietaj_komentarz(cel)
                    if nowy_sukces(wynik):
                        rytm_stanu["komentarz"] = True
                        zrobione["komentarze"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return

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
                wynik = browser.wystaw_odpowiedz(
                    cel["id"], dobre[0]["comment"], wyslij=True,
                    kontekst=opis_celu(cel),
                    rodzaj_proby="discussion_reply")
                if nowy_sukces(wynik):
                    rytm_stanu["komentarz"] = True
                    zrobione["komentarze"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return

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
                wynik = browser.obserwuj_profil(uchwyt, wyslij=True)
                if nowy_sukces(wynik, "zrobione"):
                    rytm_stanu["komentarz"] = True
                    zrobione["follow"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return
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
                wynik = browser.zasubskrybuj(uchwyt, wyslij=True)
                if nowy_sukces(wynik, "zrobione"):
                    rytm_stanu["komentarz"] = True
                    zrobione["subskrypcje"] += 1
                elif zatrzymaj_po_unknown(wynik):
                    return
                elif wyczerpany_budzet(wynik):
                    return
            else:
                print(f"  (zasubskrybowałbym: {uchwyt})", flush=True)

    # --- 4. polubienia: najtańszy uczciwy sygnał ------------------------------
    def polubienia() -> None:
        w = browser.polub_w_kanale(na_teraz["lajki"], wyslij=wyslij)
        zrobione["polubienia"] = w.get("polubione", 0)
        zatrzymaj_po_unknown(w)

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
        zatrzymaj_po_unknown(w)
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
    for nazwa, robota in (("odpowiedzi", odpowiedzi), ("notki", notki),
                          ("obserwowanie", obserwuj), ("subskrypcje", subskrybuj),
                          ("komentarze", komentarze), ("dyskusje", dyskusje),
                          ("polubienia", polubienia), ("restacki", restacki)):
        if stan_mutacji["unknown"]:
            print("\n-- dalsze mutacje pominięte: wcześniejszy stan UNKNOWN --",
                  flush=True)
            break
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
    parser = argparse.ArgumentParser(description="agent-v3 — autonomiczny system redakcyjny")
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
    polityka = capabilities.status()
    print(
        f"== polityka V3: mode={polityka['mode']} "
        f"kill_switch={polityka['kill_switch']} "
        f"test_target={polityka['test_target_configured']} ==",
        flush=True,
    )
    try:
        _zamek = zajmij_zamek()   # trzymany do końca procesu
    except JuzDziala as exc:
        print(f"  {exc}", flush=True)
        return 0

    odzyskane = mutation_ledger.recover_pending(config.DB_PATH)
    if any(odzyskane.values()):
        print(
            "  [ledger] odzyskano po restarcie: "
            f"FAILED={odzyskane['FAILED']} UNKNOWN={odzyskane['UNKNOWN']}",
            flush=True,
        )

    conn = db.connect()
    recovered_articles = stages.recover_article_saves(conn)
    if any(recovered_articles.values()):
        print(
            "  [article-save] recovery: "
            + " ".join(f"{key}={value}" for key, value in recovered_articles.items()
                       if value),
            flush=True,
        )
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
        memory_at_start = editorial.memory_brief(conn)
        topics = cached(stage, lambda: stages.scout(
                            conn, run_id, args.topics, memory_at_start),
                        args.use_cache,
                        {"count": args.topics, "editorial_memory": memory_at_start})
        print(f"\n-- tematy ({len(topics)}) --", flush=True)
        for i, topic in enumerate(topics):
            print(f"{i}. {topic.get('title')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "feasibility"
        assessments = cached(
            stage, lambda: stages.feasibility(conn, run_id, topics), args.use_cache,
            {"topics": topics},
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
        print(f"\n>> wybrane uniwersum: {topic.get('title')}", flush=True)
        if topic.get("selected_article_route"):
            print(
                f"   droga [{topic.get('selected_route_index')}]: "
                f"{topic.get('question')}",
                flush=True,
            )
            print(
                "   mechanizm: "
                f"{topic['selected_article_route'].get('distinct_engine', '')}",
                flush=True,
            )
        else:
            print(f"   {topic.get('question')}", flush=True)
        print(f"   uzasadnienie: {verdict.get('note', '')}", flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "discovery"
        recent = db.recent_domains(conn, config.DIVERSITY_LOOKBACK)
        selected_route = topic.get("selected_article_route") or {}
        research_context = {
            "universe_title": topic.get("title"),
            "universe_question": topic.get("universe_question"),
            "distinct_engine": selected_route.get("distinct_engine"),
            "evidence_needed": selected_route.get("evidence_needed"),
            "second_act": verdict.get("selected_route_second_act"),
        }
        sources = cached(
            stage,
            lambda: stages.discovery(
                conn, run_id, topic["question"], recent, research_context
            ),
            args.use_cache,
            {
                "question": topic["question"],
                "recent_domains": recent,
                "research_context": research_context,
            },
        )
        print(f"\n-- znalezione źródła ({len(sources)}) --", flush=True)
        for s in sources:
            print(
                f"  [{s.get('class', '?'):9}] {s.get('host')}"
                f"  {s.get('host_role', '?')}"
                f"{'  DLACZEGO' if s.get('answers_why') else ''}"
                f"{'  LICZBY' if s.get('has_numbers') else ''}",
                flush=True,
            )
            print(f"      {s.get('title', '')[:100]}", flush=True)
        primary = sum(1 for s in sources if s.get("class") == "PRIMARY")
        origin_primary = sum(
            1 for s in sources
            if s.get("class") == "PRIMARY"
            and s.get("host_role") in {
                "ORIGINATING_AUTHORITY", "OFFICIAL_ARCHIVE",
            }
        )
        why = sum(1 for s in sources if s.get("answers_why"))
        print(
            f"\n   pierwotnych: {primary}/{config.MIN_PRIMARY_SOURCES}   "
            f"origin/official: {origin_primary}/{config.MIN_ORIGIN_PRIMARY_SOURCES}   "
            f"wyjaśniających DLACZEGO: {why}/{config.MIN_WHY_SOURCES}   "
            f"organizacji: {len({s.get('host') for s in sources})}",
            flush=True,
        )
        if args.stop_after == stage:
            return _done(conn, run_id, stage)

        stage = "fetch"
        print("\n-- pobieranie --", flush=True)
        corpus = cached(stage, lambda: stages.fetch(conn, run_id, sources),
                        args.use_cache, {"sources": sources})
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
                    s for s in stages.discovery(
                        conn, run_id, topic["question"], recent,
                        research_context,
                    )
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
            {"question": topic["question"], "corpus": corpus},
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
                {"question": topic["question"], "evidence": evidence},
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
        odlozony_id: int | None = None
        try:
            ocena = cached(
                stage, lambda: stages.warto_pisac(conn, run_id, card),
                args.use_cache, {"card": card},
            )
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
                                 "how_it_matches": g.get("mechanism", ""),
                                 "origin": "evidence_bank"}
                                for g in grupy[:2]]
                    if dolozone:
                        card.setdefault("parallel_mechanisms", []).extend(dolozone)
                        print("   dolozono %d mechanizmow z banku:" % len(dolozone),
                              flush=True)
                        for d in dolozone:
                            print("     • [%s] %s"
                                  % (d["domain"], d["how_it_matches"][:110]), flush=True)
                    else:
                        print("   bank nie ma pary — pisarz dostaje karte jak jest",
                              flush=True)
            card["ocena_ciekawosci"] = ocena
            # V2 nazywało wynik ODLOZ, po czym bezwarunkowo wysyłało kartę do
            # pisarza. V3 zachowuje opłacony research i naprawdę odkłada temat.
            rescued = bool(locals().get("dolozone"))
            if ocena["werdykt"] == "ODLOZ" or (
                    ocena["werdykt"] == "DOLOZ" and not rescued):
                missing = str(ocena.get("what_would_rescue_it") or
                              "brakuje elementu nazwanego przez bramkę ciekawości")
                odlozony_id = editorial.defer_topic(
                    conn, run_id=run_id, topic=topic,
                    reason=str(ocena.get("powod") or ocena["werdykt"]),
                    missing_piece=missing,
                    research={"card": card, "evidence": evidence,
                              "feasibility": verdict},
                )
                print(f"   >> ODŁOŻONO jako temat #{odlozony_id}; research zachowany",
                      flush=True)
        except Exception as exc:
            # Bramka jest doradcza. Jej awaria nie moze kosztowac oplaconego
            # researchu — artykul powstaje tak czy owak.
            print("  [awaria] bramka ciekawosci padla (%s) — pisze bez niej" % exc,
                  flush=True)
        if args.stop_after == stage:
            return _done(conn, run_id, stage)
        if odlozony_id is not None:
            db.finish_run(conn, run_id, "DONE", "deferred",
                          f"temat odłożony #{odlozony_id}: czeka na brakujący materiał")
            _summary(conn, run_id)
            return 0

        stage = "write"
        print("\n-- pisanie --", flush=True)
        article_memory = editorial.memory_brief(
            conn, " ".join(str(topic.get(k) or "") for k in ("title", "question")))
        glebokosc = str(verdict.get("depth") or "RICH").upper()
        draft = cached(stage,
                       lambda: stages.write(conn, run_id, card, glebokosc,
                                            article_memory),
                       args.use_cache,
                       {"card": card, "depth": glebokosc,
                        "editorial_memory": article_memory})
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
        review_available = True
        try:
            report = cached(
                stage, lambda: stages.review(conn, run_id, card, draft), args.use_cache,
                {"card": card, "draft": draft},
            )
        except Exception as exc:
            # Brak pełnego ledgeru sentence->claim jest stanem technicznym,
            # który późniejsza decyzja kieruje do autonomicznej kwarantanny.
            print(f"  [awaria] recenzja padła ({exc}) — zapisuję w kwarantannie",
                  flush=True)
            review_available = False
            report = {"sentences": [], "unsupported_facts": [],
                      "summary": f"recenzja niedostępna: {type(exc).__name__}"}
        sentences = report.get("sentences", [])
        counts = {k: sum(1 for s in sentences if s.get("class") == k)
                  for k in ("FACT", "MIXED", "INFERENCE", "PROSE")}
        # Lista nieopartych jednostek jest wyliczana przez kod z jedynego
        # ledgeru. Model nie powtarza własnego wyniku w drugim polu.
        unsupported = list(report.get("unsupported_facts", []) or [])
        print(
            f"   zdań: {len(sentences)}   fakty: {counts['FACT']}   "
            f"mieszane: {counts['MIXED']}   "
            f"wnioskowanie: {counts['INFERENCE']}   proza: {counts['PROSE']}",
            flush=True,
        )

        # Obserwacja formy — osobne wywołanie od recenzji. Recenzent chroni
        # wnioskowanie przed zgłoszeniem (śmiała interpretacja nie jest wadą),
        # a ta bramka liczy m.in. zastrzeżenia; złączone tępiłyby się nawzajem.
        # Jak recenzja: nic nie blokuje, więc jej awaria też nie może.
        stage = "forma"
        forma_available = True
        try:
            forma = cached(stage, lambda: stages.ocen_forme(conn, run_id, draft),
                           args.use_cache, {"draft": draft})
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
            forma_available = False

        findings = gates.deterministic_floors(
            draft["body"], card,
            poprzednie=stages.poprzednie_teksty(pomin_tresc=draft["body"]),
            glebokosc=glebokosc)
        _preview_card, lineage_findings = provenance.finalize_card(
            card, evidence, report, draft["body"])
        findings.extend(lineage_findings)
        findings.extend(gates.uwagi_z_formy(forma, draft["body"]))
        for item in unsupported:
            findings.append({"gate": "FAKT_BEZ_POKRYCIA", "detail": item.get("text", "")})
        if not review_available:
            findings.append({
                "gate": "KONTROLA_NIEDOSTEPNA",
                "detail": "recenzja faktograficzna nie doszła do skutku",
            })
        if not forma_available:
            findings.append({
                "gate": "KONTROLA_NIEDOSTEPNA",
                "detail": "obserwacja formy nie doszła do skutku",
            })

        print("\n-- uwagi redakcyjne --", flush=True)
        if findings:
            for f in findings:
                print(f"   [{f['gate']}] {f['detail'][:160]}", flush=True)
        else:
            print("   czysto — żadna uwaga", flush=True)

        initial_quality = editorial.quality_decision(findings)
        quality = initial_quality
        did_revision = False
        revision_note: dict[str, str] | None = None
        revision_records: list[dict[str, Any]] = []
        print(f"   >> decyzja: {quality['action']} — {quality['reason']}", flush=True)

        revision_iteration = 0
        while quality["action"] in {"REVISE", "REVISE_FACTS"}:
            revision_iteration += 1
            stage = "revise"
            before_revision = dict(draft)
            trigger_quality = quality
            try:
                revised = cached(
                    stage,
                    lambda: stages.revise(conn, run_id, card, draft,
                                          trigger_quality["findings"]),
                    args.use_cache,
                    {"card": card, "draft": draft,
                     "findings": trigger_quality["findings"],
                     "iteration": revision_iteration,
                     "quality_policy": editorial.QUALITY_POLICY_VERSION},
                )
                did_revision = True
                draft = revised
                print(f"\n-- pełna kontrola po redakcji {revision_iteration} --",
                      flush=True)

                next_review_ok = next_form_ok = True
                try:
                    report2 = stages.review(conn, run_id, card, draft)
                except Exception as exc:
                    next_review_ok = False
                    report2 = {"sentences": [], "unsupported_facts": [],
                               "summary": f"ponowna recenzja niedostępna: {exc}"}
                unsupported2 = list(report2.get("unsupported_facts", []) or [])
                try:
                    forma2 = stages.ocen_forme(conn, run_id, draft)
                except Exception as exc:
                    next_form_ok = False
                    forma2 = {"summary": f"ponowna forma niedostępna: {exc}"}

                findings2 = gates.deterministic_floors(
                    draft["body"], card,
                    poprzednie=stages.poprzednie_teksty(pomin_tresc=draft["body"]),
                    glebokosc=glebokosc)
                _preview_card2, lineage_findings2 = provenance.finalize_card(
                    card, evidence, report2, draft["body"])
                findings2.extend(lineage_findings2)
                findings2.extend(gates.uwagi_z_formy(forma2, draft["body"]))
                findings2.extend({"gate": "FAKT_BEZ_POKRYCIA",
                                  "detail": item.get("text", "")}
                                 for item in unsupported2)
                if not next_review_ok:
                    findings2.append({
                        "gate": "KONTROLA_NIEDOSTEPNA",
                        "detail": "ponowna recenzja nie doszła do skutku",
                    })
                if not next_form_ok:
                    findings2.append({
                        "gate": "KONTROLA_NIEDOSTEPNA",
                        "detail": "ponowna obserwacja formy nie doszła do skutku",
                    })

                candidate_quality = editorial.quality_decision(findings2)
                progress = editorial.revision_progress(
                    trigger_quality, candidate_quality,
                    body_changed=(draft.get("body") != before_revision.get("body")),
                )
                revision_status = progress["outcome"]
                if progress["outcome"] in {"NO_IMPROVEMENT", "REGRESSION"}:
                    quality = editorial.quarantine_after_revision(
                        candidate_quality,
                        reason=(f"rewizja {revision_iteration}: "
                                f"{progress['outcome'].lower()}"),
                    )
                elif (candidate_quality["action"] in {"REVISE", "REVISE_FACTS"}
                      and revision_iteration >= editorial.MAX_AUTONOMOUS_REVISIONS):
                    quality = editorial.quarantine_after_revision(
                        candidate_quality,
                        reason=("osiągnięto limit "
                                f"{editorial.MAX_AUTONOMOUS_REVISIONS} rewizji"),
                    )
                    revision_status = "LIMIT_REACHED"
                else:
                    quality = candidate_quality

                revision_records.append({
                    "iteration": revision_iteration,
                    "trigger": trigger_quality,
                    "before": before_revision,
                    "after": draft,
                    "status": revision_status,
                    "remaining": {**quality, "progress": progress},
                })
                findings = findings2
                report = report2
                forma = forma2
                revision_note = {
                    "gate": "AUTO_REVISION",
                    "detail": (
                        f"iteracja {revision_iteration}: {progress['outcome']}; "
                        f"zostało {quality['finding_count']} uwag; "
                        f"decyzja {quality['action']}"
                    ),
                }
                print(f"   >> po redakcji: {quality['action']} — {quality['reason']}",
                      flush=True)
            except Exception as exc:
                failed_findings = [*findings, {
                    "gate": "KONTROLA_NIEDOSTEPNA",
                    "detail": f"automatyczna redakcja padła: {exc}",
                }]
                failed_quality = editorial.quality_decision(failed_findings)
                quality = editorial.quarantine_after_revision(
                    failed_quality,
                    reason=f"automatyczna redakcja nieudana: {type(exc).__name__}",
                )
                revision_records.append({
                    "iteration": revision_iteration,
                    "trigger": trigger_quality,
                    "before": before_revision,
                    "after": None,
                    "status": "FAILED",
                    "remaining": {**quality,
                                  "error": f"{type(exc).__name__}: {exc}"},
                })
                findings = failed_findings
                revision_note = {
                    "gate": "AUTO_REVISION",
                    "detail": f"redakcja nieudana: {type(exc).__name__}: {exc}",
                }
                break

        can_publish = bool(quality["can_publish"])
        status = str(quality["action"])
        blocked_by = None if can_publish else str(quality["action"])
        notes = [*findings,
                  {"gate": "EDITORIAL_DECISION",
                   "detail": f"{quality['action']}: {quality['reason']}"},
                  {"gate": "QUALITY_POLICY",
                   "detail": (f"{quality['policy_version']}:"
                              f"{quality['policy_hash']}")},
                  {"gate": "DLUGOSC", "detail": f"{len(draft['body'].split())} słów"},
                 {"gate": "RECENZJA", "detail": report.get("summary", "")}]
        if revision_note:
            notes.append(revision_note)
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
        # Użycie wylicza kod z FINALNEGO ledgeru sentence->claim. Do banku
        # trafiają tylko fragmenty bez drogi do wspieranego zdania; cytowania
        # powstają wyłącznie z dokumentów rzeczywiście użytych.
        card, final_lineage_findings = provenance.finalize_card(
            card, evidence, report, draft["body"])
        known_findings = {(item["gate"], item["detail"]) for item in findings}
        unexpected_lineage = [
            item for item in final_lineage_findings
            if (item["gate"], item["detail"]) not in known_findings
        ]
        if unexpected_lineage:
            raise RuntimeError(
                "ledger pochodzenia zmienił wynik między bramką i zapisem: "
                f"{unexpected_lineage}"
            )
        path = stages.save(
            conn, run_id, topic, card, draft, status, blocked_by, notes,
            revisions=revision_records,
        )
        article_row = conn.execute(
            "SELECT id FROM articles WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        article_id = int(article_row["id"]) if article_row else None

        print(f"\n>> {status}" + (f" ({blocked_by})" if blocked_by else ""), flush=True)
        print(f">> zapisano: {path}", flush=True)

        if args.wyslij and can_publish:
            import browser

            # Grafika NIGDY nie zatrzymuje artykułu: brak czterech centów na
            # obrazek nie może wyrzucić do kosza researchu za czterdzieści.
            stages.grafika(conn, run_id, draft, sciezka_artykulu=path)
            print("\n-- publikacja --", flush=True)
            wynik = browser.wystaw_artykul(path, wyslij=True)
            print(f">> {'OPUBLIKOWANY' if wynik.get('wyslane') else 'NIE POSZEDŁ'}"
                  f"{'  ' + str(wynik.get('blad')) if wynik.get('blad') else ''}",
                  flush=True)
            if wynik.get("wyslane") and article_id is not None:
                editorial.mark_published(
                    conn, article_id=article_id,
                    canonical_url=wynik.get("url"),
                    external_id=(str(wynik.get("external_id"))
                                 if wynik.get("external_id") is not None else None),
                )
        elif args.wyslij:
            print(f">> NIE PUBLIKUJĘ: decyzja redakcyjna {quality['action']} — "
                  f"tekst został zachowany do poprawy", flush=True)
        stage = "editorial_complete"
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
        "SELECT COALESCE(SUM(cost_usd), 0) AS total, COUNT(*) AS n, "
        "SUM(CASE WHEN cost_status IN ('RESERVED','UNKNOWN') THEN 1 ELSE 0 END) "
        "AS unresolved, COALESCE(SUM(CASE WHEN cost_status IN "
        "('RESERVED','UNKNOWN') THEN reserved_usd ELSE 0 END), 0) AS reserved "
        "FROM calls WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    suffix = (
        f" + UNKNOWN ({row['unresolved']} prób, rezerwacja ${row['reserved']:.4f})"
        if row["unresolved"] else ""
    )
    print(
        f"\n== koszt przebiegu: ${row['total']:.4f}{suffix} "
        f"w {row['n']} wywołaniach ==", flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
