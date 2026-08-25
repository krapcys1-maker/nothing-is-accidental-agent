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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import statystyki  # noqa: E402


def _skrot(tekst: str, ile: int = 46) -> str:
    t = " ".join(str(tekst or "").split())
    return (t[: ile - 1] + "…") if len(t) > ile else t


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
    print("%-11s %-10s %6s %6s %5s %5s %5s  %s" % (
        "RODZAJ", "NUMER", "WEJSC", "POLUB", "KOM", "SUBS", "OBS", "TRESC"))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
