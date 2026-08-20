"""Sklada dokumentacje odtworzeniowa z czesci.

Czesci mechaniczne (spis funkcji, stale, prompty, kod) sa GENEROWANE ze zrodel,
zeby nie dalo sie ich rozjechac z rzeczywistoscia. Czesci analityczne pisza
ludzie/agenci i leza w .tmp_rozdzial_*.md.

Uruchomienie: python agent-v2/.tmp_sklej.py
"""
import pathlib
import sys

KAT = pathlib.Path("agent-v2")
CEL = KAT / "JAK_ZBUDOWANY_JEST_BOT.md"


def czytaj(nazwa: str, wymagany: bool = True) -> str:
    p = KAT / nazwa
    if not p.exists():
        if wymagany:
            print("  BRAK CZESCI: %s" % nazwa)
            return "\n> *(brakuje sekcji `%s` — dokument niekompletny)*\n" % nazwa
        return ""
    return p.read_text(encoding="utf-8").rstrip() + "\n"


CZESCI = [
    ("wstep",            ".tmp_wstep.md",              True),
    ("moduly",           ".tmp_moduly.md",             True),
    ("artykul",          ".tmp_rozdzial_artykul.md",   True),
    ("dzien",            ".tmp_rozdzial_dzien.md",     True),
    ("bramki",           ".tmp_rozdzial_bramki.md",    True),
    ("dane",             ".tmp_rozdzial_dane.md",      True),
    ("kod",              ".tmp_kod.md",                True),
    ("wady",             ".tmp_wady.md",               True),
    ("zal_prompty",      ".tmp_zalacznik_prompty.md",  True),
    ("zal_stale",        ".tmp_stale.md",              True),
    ("zal_dysk",         ".tmp_zalacznik_dysk.md",     True),
]

NAGLOWKI = {
    "moduly": "\n## II. Spis modulow i funkcji\n\nWygenerowany ze zrodel, wiec nie da sie go rozjechac z kodem.\n",
    "kod": "\n## VII. Kluczowy kod doslownie\n\nWycinki wygenerowane ze zrodel przez `ast`, nie przepisane recznie.\nKazdy blok jest poprzedzony znacznikiem `<!--KOD:modul.funkcja-->`.\n",
    "zal_stale": "\n## ZALACZNIK B — WSZYSTKIE STALE KONFIGURACJI\n\nWygenerowany z `config.py`: nazwa, wartosc i komentarz stojacy bezposrednio\nnad definicja. 150 pozycji.\n",
}


def main() -> int:
    czesci = []
    braki = []
    for klucz, plik, wymagany in CZESCI:
        tresc = czytaj(plik, wymagany)
        if "brakuje sekcji" in tresc[:200]:
            braki.append(plik)
        czesci.append(NAGLOWKI.get(klucz, "") + tresc)
    dokument = "\n".join(czesci)
    CEL.write_text(dokument, encoding="utf-8")
    wierszy = len(dokument.splitlines())
    print("zapisano %s" % CEL)
    print("  wierszy: %d" % wierszy)
    print("  znakow:  %d" % len(dokument))
    if braki:
        print("  BRAKUJE: %s" % ", ".join(braki))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
