"""Sklada dokumentacje odtworzeniowa z czesci.

Czesci mechaniczne (spis funkcji, stale, prompty, kod) sa GENEROWANE ze zrodel,
zeby nie dalo sie ich rozjechac z rzeczywistoscia. Czesci analityczne leza
w rozdzial_*.md.

Uruchomienie: python agent-v2/sklej.py
"""
import pathlib
import sys

KAT = pathlib.Path("agent-v2/dokumentacja-zrodla")
CEL = pathlib.Path("agent-v2/JAK_ZBUDOWANY_JEST_BOT.md")

NL = "\n"


def czytaj(nazwa: str) -> str:
    p = KAT / nazwa
    if not p.exists():
        print("  BRAK CZESCI: %s" % nazwa)
        return NL + "> *(brakuje sekcji `%s` — dokument niekompletny)*" % nazwa + NL
    return p.read_text(encoding="utf-8").rstrip() + NL


CZESCI = [
    ("wstep", "wstep.md"),
    ("moduly", "moduly.md"),
    ("artykul", "rozdzial_artykul.md"),
    ("dzien", "rozdzial_dzien.md"),
    ("bramki", "rozdzial_bramki.md"),
    ("dane", "rozdzial_dane.md"),
    ("kod", "kod.md"),
    ("wady", "wady.md"),
    ("zal_prompty", "zalacznik_prompty.md"),
    ("zal_stale", "stale.md"),
    ("zal_dysk", "zalacznik_dysk.md"),
]

NAGLOWKI = {
    "moduly": [
        "", "## II. Spis modulow i funkcji", "",
        "Wygenerowany ze zrodel przez `ast`, wiec nie da sie go rozjechac z kodem.",
        "",
    ],
    "artykul": ["", "## III. Sciezka artykulu — dziesiec etapow", ""],
    "dzien": ["", "## IV. Sciezka dnia i styk z Substackiem", ""],
    "bramki": ["", "## V. Bramki i kontrola jakosci", ""],
    "dane": ["", "## VI. Dane, dysk, koszty i operacje", ""],
    "kod": [
        "", "## VII. Kluczowy kod doslownie", "",
        "Wycinki wygenerowane ze zrodel przez `ast`, nie przepisane recznie.",
        "Kazdy blok poprzedza znacznik `<!--KOD:modul.funkcja-->`.",
        "",
    ],
    "zal_stale": [
        "", "## ZALACZNIK B — WSZYSTKIE STALE KONFIGURACJI", "",
        "Wygenerowany z `config.py`: nazwa, wartosc i komentarz stojacy",
        "bezposrednio nad definicja.",
        "",
    ],
}


def main() -> int:
    czesci = []
    braki = []
    for klucz, plik in CZESCI:
        tresc = czytaj(plik)
        if "brakuje sekcji" in tresc[:200]:
            braki.append(plik)
        naglowek = NL.join(NAGLOWKI.get(klucz, []))
        czesci.append((naglowek + NL if naglowek else "") + tresc)
    dokument = NL.join(czesci)
    CEL.write_text(dokument, encoding="utf-8")
    print("zapisano %s" % CEL)
    print("  wierszy: %d" % len(dokument.splitlines()))
    print("  znakow:  %d" % len(dokument))
    if braki:
        print("  BRAKUJE: %s" % ", ".join(braki))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
