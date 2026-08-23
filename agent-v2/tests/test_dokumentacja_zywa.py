"""Dokumentacja odtworzeniowa ma byc GENEROWANA, nie przepisywana.

Dokument JAK_ZBUDOWANY_JEST_BOT.md mowil o sobie w czterech miejscach:

    "Wygenerowany ze zrodel przez `ast`, wiec nie da sie go rozjechac z kodem."

Nic tego nie generowalo. `sklej.py` importowal wylacznie `pathlib` i `sys`,
a slowo `ast` wystepowalo w nim TYLKO wewnatrz naglowkow wpisywanych do
dokumentu — bylo twierdzeniem w tresci, nie kodem. Cztery czesci mechaniczne
byly zamrozonymi zrzutami i rozjechaly sie z kodem w ciagu trzech dni: nie
bylo w nich ani `rytm`, ani `losuj_odstep`, ani `_stale_sygnaly`, ani nowego
poziomu dlugosci THIN.

To jest ta sama klasa wady, ktora scigamy w agencie — obietnica bez pokrycia,
czytana jak gwarancja — tyle ze w dokumencie, ktorego CALY sens polega na tym,
zeby dalo sie z niego odtworzyc bota.

NAJWAZNIEJSZA ASERCJA jest ostatnia: zlozenie dokumentu na nowo nie moze
niczego zmienic. Jesli zmienia — dokument w repozytorium jest starszy niz kod
i ktos zapomnial go przebudowac.
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, "agent-v2")

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


SKLEJ = pathlib.Path("agent-v2/dokumentacja-zrodla/sklej.py")
PAPER = pathlib.Path("agent-v2/JAK_ZBUDOWANY_JEST_BOT.md")
sklej_src = SKLEJ.read_text(encoding="utf-8")

print("=== 1. GENERATOR NAPRAWDE GENERUJE ===")
sprawdz("sklej.py importuje ast", "\nimport ast" in sklej_src)
# KONTRDOWOD dla poprzedniej wersji: samo slowo `ast` w pliku nic nie znaczylo,
# bo stalo w napisie wpisywanym do dokumentu. Wymagamy UZYCIA.
sprawdz("i naprawde go uzywa, nie tylko wspomina",
        "ast.parse(" in sklej_src and "ast.get_source_segment(" in sklej_src)
sprawdz("czyta pliki .py z katalogu agenta", 'AGENT.glob("*.py")' in sklej_src)
sprawdz("i katalog promptow", "PROMPTY_KAT.glob" in sklej_src)
for czesc in ("moduly.md", "stale.md", "kod.md", "prompty.md",
              "zalacznik_prompty.md"):
    sprawdz("generuje %s" % czesc, '"%s"' % czesc in sklej_src)

print()
print("=== 2. NIC NIE ZNIKA PO CICHU ===")
# Modul, ktorego nie ma w spisie, MUSI zostac zgloszony. Cicho pominiety modul
# to ten sam blad co przedtem, tylko wolniejszy.
sprawdz("nieznany modul jest zglaszany", "nie ma go w spisie MODULY" in sklej_src)
sprawdz("znikniona funkcja z KOD_DOSLOWNIE tez",
        "takiej funkcji juz nie ma" in sklej_src)
sprawdz("i ostrzezenia zmieniaja kod wyjscia", "if ostrzezenia:" in sklej_src)

# Kazdy modul .py agenta ma byc w spisie — inaczej wypada z dokumentacji.
import importlib.util   # noqa: E402
spec = importlib.util.spec_from_file_location("sklej", SKLEJ)
sklej = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sklej)
wymienione = {n for n, _ in sklej.MODULY}
istniejace = {p.name for p in pathlib.Path("agent-v2").glob("*.py")}
sprawdz("kazdy modul agenta jest w spisie", istniejace <= wymienione,
        sorted(istniejace - wymienione))
sprawdz("i spis nie wymienia plikow, ktorych nie ma", wymienione <= istniejace,
        sorted(wymienione - istniejace))
# Kazda funkcja z KOD_DOSLOWNIE musi istniec.
brakujace = [w for w in sklej.KOD_DOSLOWNIE
             if sklej._zrodlo_funkcji(*w.split(".", 1)) is None]
sprawdz("kazda funkcja z KOD_DOSLOWNIE istnieje", not brakujace, brakujace)

print()
print("=== 3. DOKUMENT W REPOZYTORIUM JEST AKTUALNY ===")
# To jest cala pointa. Skladamy na nowo i porownujemy z tym, co lezy w repo.
przed = PAPER.read_text(encoding="utf-8")
wynik = subprocess.run([sys.executable, str(SKLEJ)],
                       capture_output=True, text=True)
po = PAPER.read_text(encoding="utf-8")
sprawdz("skladanie konczy sie bez ostrzezen", wynik.returncode == 0,
        wynik.stdout[-400:])
sprawdz("przebudowa NICZEGO nie zmienia — dokument jest aktualny",
        przed == po,
        "roznica %d znakow; uruchom: python agent-v2/dokumentacja-zrodla/sklej.py"
        % abs(len(przed) - len(po)))

print()
print("=== 4. TRESC ODPOWIADA DZISIEJSZEMU KODOWI ===")
# Kilka rzeczy, ktorych w starym dokumencie NIE BYLO, choc byly juz w kodzie.
# Gdyby generator dzialal pozornie, te asercje by tego nie przepuscily.
for co, gdzie in (("def rytm", "run.rytm"), ("losuj_odstep", "stages.losuj_odstep"),
                  ("_stale_sygnaly", "stages._stale_sygnaly"),
                  ("ostatnie_domeny", "stages.discovery")):
    sprawdz("dokument zna %s" % gdzie, co in po, co)
sprawdz("i zna poziom dlugosci THIN", '"THIN":' in po)
# Prompty maja byc te, ktore naprawde dostaje model.
skaut = pathlib.Path("agent-v2/prompts/skaut.md").read_text(encoding="utf-8")
probka = [l for l in skaut.splitlines() if len(l.strip()) > 60][3]
sprawdz("zalacznik promptow ma aktualna tresc skauta", probka.strip() in po,
        probka[:70])

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
