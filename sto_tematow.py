"""Sto tematow naraz, zeby ocenic MASZYNE, a nie pojedynczy przypadek.

Wlasciciel: "niech da 100 tematow i sprawdzaj je czy sa ok". Pojedynczy przebieg
niczego nie dowodzi — dopiero rozklad pokazuje, czy siatka dziedzin i wzorcow
naprawde rozprasza tematy, czy tylko wyglada, ze rozprasza.

Sprawdzamy szesc rzeczy, kazda liczba, nie wrazeniem:

  1. CZY W OGOLE O AI. Publikacja jest o sztucznej inteligencji; temat o czyms
     innym to blad doktryny, nie gust.
  2. CZY MA ZRODLO I DATE. Bez daty bramka swiezosci nie ma czego sprawdzic.
  3. JAK STARE SA ZRODLA. Wlasciciel chce danych z ostatnich 2-3 miesiecy.
  4. CZY TEMATY SIE NIE POWTARZAJA MIEDZY SOBA. Osiem przebiegow moze oddac
     osiem razy to samo innymi slowami.
  5. CZY NIE POWTARZAJA TEGO, CO JUZ WYSZLO — notek i artykulow razem.
  6. JAK ROZKLADAJA SIE PO DZIEDZINACH. Jesli polowa wpada w jedna dziedzine,
     rotacja jest ozdoba.
"""
import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "agent-v2"))

import config
config.DRY_RUN = False
config.DAILY_LIMIT_USD = 12.0

import db        # noqa: E402
import stages    # noqa: E402

PLIK = Path("sto_tematow.json")
ILE_PRZEBIEGOW = int(sys.argv[1]) if len(sys.argv) > 1 else 14


def zbierz() -> list[dict]:
    """Kolejne przebiegi szukania ciekawostek, wszystko do jednego worka."""
    zebrane: list[dict] = []
    if PLIK.exists():
        try:
            zebrane = json.loads(PLIK.read_text(encoding="utf-8"))
            print("wczytane z poprzedniego razu: %d" % len(zebrane))
        except Exception:
            zebrane = []

    conn = db.connect()
    for i in range(ILE_PRZEBIEGOW):
        if len(zebrane) >= 100:
            break
        rid = db.start_run(conn, "sto-tematow-%d" % i)
        try:
            fakty = stages.znajdz_ciekawostki(conn, rid, ile=8)
        except Exception as exc:
            print("  przebieg %d padl: %s: %s"
                  % (i + 1, type(exc).__name__, str(exc)[:90]))
            continue
        zebrane.extend(fakty)
        print("  przebieg %2d: +%d  (razem %d)" % (i + 1, len(fakty), len(zebrane)))
        PLIK.write_text(json.dumps(zebrane, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return zebrane


def main() -> int:
    zebrane = zbierz()
    print()
    print("=" * 78)
    print("ZEBRANO %d TEMATOW — OCENA" % len(zebrane))
    print("=" * 78)
    if not zebrane:
        print("nic nie zebrano")
        return 1

    teksty = ["%s %s" % (f.get("domain") or "", f.get("fact") or "")
              for f in zebrane]

    # --- 1. czy o AI ---
    SLOWA_AI = ("ai", "artificial intelligence", "model", "llm", "chatbot",
                "machine learning", "neural", "openai", "anthropic", "gemini",
                "claude", "gpt", "deepseek", "transformer", "training",
                "inference", "algorithm", "automated", "agent", "dataset",
                "benchmark", "gpu", "compute")
    o_ai = [t for t in teksty
            if any(s in t.lower() for s in SLOWA_AI)]
    print()
    print("1. O SZTUCZNEJ INTELIGENCJI:  %d z %d  (%.0f%%)"
          % (len(o_ai), len(teksty), 100 * len(o_ai) / len(teksty)))
    for t in teksty:
        if t not in o_ai:
            print("   POZA TEMATEM: %s" % t[:96])

    # --- 2. zrodlo i data ---
    bez_url = [f for f in zebrane if not (f.get("url") or "").strip()]
    bez_daty = [f for f in zebrane if not (f.get("source_date") or "").strip()]
    print()
    print("2. ZRODLO I DATA")
    print("   bez adresu zrodla: %d" % len(bez_url))
    print("   bez daty zrodla:   %d" % len(bez_daty))

    # --- 3. wiek zrodel ---
    wieki = []
    for f in zebrane:
        w = stages.wiek_zrodla_w_dniach(f.get("source_date"))
        if w is not None:
            wieki.append(w)
    print()
    print("3. WIEK ZRODEL (dni)")
    if wieki:
        wieki.sort()
        print("   najswiezsze %d | mediana %d | najstarsze %d"
              % (wieki[0], wieki[len(wieki) // 2], wieki[-1]))
        for prog, opis in ((90, "do 3 miesiecy"), (180, "do pol roku"),
                           (365, "do roku")):
            ile = sum(1 for w in wieki if w <= prog)
            print("   %-16s %d z %d  (%.0f%%)"
                  % (opis, ile, len(wieki), 100 * ile / len(wieki)))
    else:
        print("   ZADNEGO nie da sie zmierzyc — brak dat")

    # --- 4. powtorki miedzy soba ---
    print()
    print("4. POWTORKI MIEDZY TEMATAMI")
    pary = []
    for i in range(len(teksty)):
        for j in range(i + 1, len(teksty)):
            if stages._o_tym_samym(teksty[i], teksty[j],
                                   **stages.POROWNANIE_MIEDZY_DNIAMI):
                pary.append((i, j))
    print("   kolidujacych par: %d z %d mozliwych"
          % (len(pary), len(teksty) * (len(teksty) - 1) // 2))
    for i, j in pary[:8]:
        print("   - %s" % teksty[i][:74])
        print("     %s" % teksty[j][:74])

    # --- 5. powtorki tego, co juz wyszlo ---
    print()
    print("5. POWTORKI TEGO, CO JUZ OPUBLIKOWANE")
    conn = db.connect()
    wydane = list(stages.tematy_do_porownania(conn)) + stages.ostatnie_notki(1000)
    zderzone = []
    for t in teksty:
        k = next((w for w in wydane if w and stages._o_tym_samym(
            t, w, **stages.POWTORKA_TEMATU)), None)
        if k:
            zderzone.append((t, k))
    print("   powtarza juz wydane: %d z %d" % (len(zderzone), len(teksty)))
    for t, k in zderzone[:6]:
        print("   - NOWY:  %s" % t[:74])
        print("     BYLO:  %s" % " ".join(str(k).split())[:74])

    # --- 6. rozklad po dziedzinach ---
    print()
    print("6. ROZKLAD PO DZIEDZINACH")
    licz = Counter((f.get("domain") or "?")[:44] for f in zebrane)
    print("   roznych dziedzin: %d na %d tematow" % (len(licz), len(zebrane)))
    for d, n in licz.most_common(10):
        print("   %2d x  %s" % (n, d))

    io.open("ocena_stu_tematow.txt", "w", encoding="utf-8").write(
        "\n".join("%s | %s | %s" % (f.get("source_date") or "brak",
                                    (f.get("domain") or "?")[:34],
                                    (f.get("fact") or "")[:150])
                  for f in zebrane))
    print()
    print(">> pelna lista w ocena_stu_tematow.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
