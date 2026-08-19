"""Kopia listy subskrybentow — jedyne aktywo, ktorego nie da sie odtworzyc.

Teksty, karty dowodowe, okladki i cala historia kosztow powstaja lokalnie
i leza w gicie. Lista subskrybentow nie: zyje wylacznie u Substacka. Przy
tempie 6-12 subskrypcji miesiecznie lista stu osob to okolo jedenastu miesiecy
pracy systemu, a regulamin pozwala zamknac konto natychmiast i w wylacznej
ocenie Substacka.

To jest jedyna pozycja, ktorej zaniechanie jest NIEODWRACALNE.

Uruchamiac recznie albo z zegara:
    python agent-v2/kopia_subskrybentow.py

Zapisuje do `data/kopie/subskrybenci-RRRR-MM-DD.csv` i zostawia ostatnie
`ILE_KOPII` sztuk. Nic nie publikuje i nic nie kasuje na koncie.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import browser   # noqa: E402
import config    # noqa: E402

KATALOG = config.DATA_DIR / "kopie"
ILE_KOPII = 30
PUBLIKACJA = "https://%s.substack.com" % config.SUBSTACK_HANDLE

# Substack oddaje liste kilkoma droznami zaleznie od wersji panelu. Probujemy
# po kolei i bierzemy pierwsza, ktora zwroci CSV — zamiast zakladac jedna
# i przewracac sie, gdy zmienia interfejs.
SCIEZKI = (
    "/api/v1/subscriber/csv",
    "/api/v1/subscriptions/csv",
    "/api/v1/publication/subscriber/csv",
)


def pobierz(page) -> tuple[str, str]:
    """Zwraca (tresc CSV, sciezka ktora zadziala) albo ('','')."""
    for sciezka in SCIEZKI:
        url = PUBLIKACJA + sciezka
        try:
            odp = page.request.get(url, timeout=60_000)
        except Exception as exc:
            print("  %-42s %s" % (sciezka, type(exc).__name__), flush=True)
            continue
        tresc = ""
        try:
            tresc = odp.text()
        except Exception:
            pass
        # CSV poznajemy po naglowku z przecinkami, nie po statusie: Substack
        # potrafi oddac 200 ze strona logowania.
        wyglada = (odp.status == 200 and "," in tresc.split("\n")[0]
                   and "<html" not in tresc[:200].lower())
        print("  %-42s HTTP %s  %6d znakow  %s"
              % (sciezka, odp.status, len(tresc),
                 "CSV" if wyglada else "to nie CSV"), flush=True)
        if wyglada:
            return tresc, sciezka
    return "", ""


def main() -> int:
    print("== kopia listy subskrybentow ==", flush=True)
    print("   publikacja: %s" % PUBLIKACJA, flush=True)
    browser.wymagaj_sesji()
    p, b, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    try:
        tresc, skad = pobierz(page)
    finally:
        page.close()
        b.close()
        p.stop()

    if not tresc:
        print("\n  NIE UDALO SIE. Zadna ze sciezek nie oddala CSV.", flush=True)
        print("  Substack eksportuje liste takze recznie:", flush=True)
        print("    Dashboard -> Subscribers -> ... -> Export", flush=True)
        print("  Zrob to raz recznie i wklej sciezke, ktora zadziala.", flush=True)
        return 1

    KATALOG.mkdir(parents=True, exist_ok=True)
    dzis = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plik = KATALOG / ("subskrybenci-%s.csv" % dzis)
    plik.write_text(tresc, encoding="utf-8")
    wiersze = [w for w in tresc.splitlines() if w.strip()]
    print("\n  ZAPISANE: %s" % plik, flush=True)
    print("  zrodlo: %s" % skad, flush=True)
    print("  wierszy: %d (w tym naglowek)" % len(wiersze), flush=True)
    print("  kolumny: %s" % wiersze[0][:120] if wiersze else "", flush=True)

    # Zostawiamy ostatnie ILE_KOPII. Kopia, ktora rosnie bez konca, po roku
    # jest problemem, a nie zabezpieczeniem.
    stare = sorted(KATALOG.glob("subskrybenci-*.csv"))
    for x in stare[:-ILE_KOPII]:
        x.unlink()
        print("  usunieta stara kopia: %s" % x.name, flush=True)
    print("  kopii w katalogu: %d" % len(sorted(KATALOG.glob("subskrybenci-*.csv"))),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
