# -*- coding: utf-8 -*-
"""Odmowa dostawcy to odmowa JEDNEJ tresci, nie stan konta.

SKAD. 21 wrzesnia 2026 o 19:39 Anthropic odmowil napisania notki (kategoria
„reasoning_extraction"). `llm.py` zamienial kazda odmowe na `PreflightFailed`,
a ta w `run.py` znaczy „nie ma pieniedzy albo dziala wylacznik": blok notek
wypisal „to nie jest awaria bloku, tylko stan konta" i przebieg skonczyl sie
w polowie. Ta sama odmowa pisarza artykulu nie uruchomilaby powtorki na Opusie,
ktora `run.py` i `artykul_z_puli.py` maja zapisana — oplacony research szedlby
do kosza, a komentarz nad powtorka mowi wprost, ze jest wlasnie na odmowe.

CO SPRAWDZA:
  1. odmowa z API konczy sie `OdmowaDostawcy`, nie `PreflightFailed`;
  2. `OdmowaDostawcy` jest poza `PRZERYWAJA` we wszystkich trzech modulach;
  3. nie jest ponawiana jak zerwane lacze (odmowa powtorzy sie identycznie);
  4. drzewem skladni: oba miejsca pisarza artykulu maja powtorke dla wyjatku
     spoza `PRZERYWAJA`, a blok dnia puszcza taki wyjatek dalej, do nastepnego
     bloku, zamiast konczyc dzien.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_odmowa_dostawcy.py
"""
import ast
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import config  # noqa: E402
import llm  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


class _Wiadomosc:
    stop_reason = "refusal"
    stop_details = "RefusalStopDetails(category='reasoning_extraction')"
    content: list = []
    usage = None


class _Strumien:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return _Wiadomosc()


class _Klient:
    def __init__(self, **kwargs):
        self.messages = self

    def stream(self, **kwargs):
        return _Strumien()


print("=== 1. ODMOWA Z API ===")
stary_klient = llm.anthropic.Anthropic
llm.anthropic.Anthropic = _Klient
try:
    try:
        llm._call_claude("write", "system", "tresc", web_search=False,
                         model=config.FABLE)
        wynik = None
    except Exception as exc:                                  # noqa: BLE001
        wynik = exc
finally:
    llm.anthropic.Anthropic = stary_klient
sprawdz("odmowa konczy sie OdmowaDostawcy",
        isinstance(wynik, llm.OdmowaDostawcy), type(wynik).__name__)
sprawdz("i NIE jest PreflightFailed (stanem konta)",
        not isinstance(wynik, llm.PreflightFailed))
sprawdz("powod odmowy zostaje w komunikacie",
        "reasoning_extraction" in str(wynik), str(wynik)[:80])

print()
print("=== 2. NIE PRZERYWA PRZEBIEGU ===")
import artykul_z_puli  # noqa: E402
import run  # noqa: E402
import stages  # noqa: E402

for nazwa, modul in (("run", run), ("stages", stages), ("artykul_z_puli", artykul_z_puli)):
    sprawdz("%s.PRZERYWAJA nie obejmuje odmowy" % nazwa,
            not issubclass(llm.OdmowaDostawcy, modul.PRZERYWAJA))
sprawdz("KONTRDOWOD: brak pieniedzy nadal przerywa",
        issubclass(llm.BudgetExceeded, run.PRZERYWAJA)
        and issubclass(llm.PreflightFailed, run.PRZERYWAJA))

print()
print("=== 3. NIE JEST PONAWIANA ===")
sprawdz("odmowa nie jest przejsciowa", llm.przejsciowy(llm.OdmowaDostawcy("x")) is False)

print()
print("=== 4. KTO JA LAPIE ===")


def nazwy_wyjatkow(handler):
    t = handler.type
    if t is None:
        return {"*"}
    elts = t.elts if isinstance(t, ast.Tuple) else [t]
    return {e.id if isinstance(e, ast.Name) else ast.unparse(e) for e in elts}


def wola(wezly, co):
    return any(isinstance(n, ast.Call) and ast.unparse(n.func) == co
               for w in wezly for n in ast.walk(w))


for plik in ("run.py", "artykul_z_puli.py"):
    drzewo = ast.parse(pathlib.Path("agent-v2", plik).read_text(encoding="utf-8"))
    # Najblizszy `try` wokol pisarza. W `run.py` cala sciezka artykulu stoi
    # jeszcze w zewnetrznym `try`, ktory zamyka przebieg — liczy sie ten
    # najciasniejszy, bo to on decyduje o powtorce.
    proby = sorted((t for t in ast.walk(drzewo) if isinstance(t, ast.Try)
                    and wola(t.body, "stages.write")),
                   key=lambda t: t.end_lineno - t.lineno)
    sprawdz("%s: pisarz artykulu stoi w try" % plik, bool(proby), len(proby))
    if not proby:
        continue
    handlery = proby[0].handlers
    pierwszy = nazwy_wyjatkow(handlery[0])
    sprawdz("%s: PRZERYWAJA lapane PIERWSZE i puszczane dalej" % plik,
            pierwszy == {"PRZERYWAJA"}
            and any(isinstance(n, ast.Raise) for n in handlery[0].body), pierwszy)
    reszta = [h for h in handlery[1:] if "Exception" in nazwy_wyjatkow(h)]
    sprawdz("%s: wszystko inne (w tym odmowa) idzie do powtorki na Opusie" % plik,
            bool(reszta) and wola(reszta[0].body, "stages.write")
            and "config.CLAUDE" in ast.unparse(reszta[0]), [nazwy_wyjatkow(h) for h in handlery])

drzewo = ast.parse(pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8"))
blok = [f for f in ast.walk(drzewo) if isinstance(f, ast.FunctionDef) and f.name == "blok"]
sprawdz("run.py: blok dnia istnieje", len(blok) == 1)
if blok:
    proba = [t for t in ast.walk(blok[0]) if isinstance(t, ast.Try)][0]
    zwykly = [h for h in proba.handlers if "Exception" in nazwy_wyjatkow(h)]
    sprawdz("blok dnia: zwykly wyjatek nie konczy dnia (bez raise)",
            bool(zwykly) and not any(isinstance(n, ast.Raise)
                                     for n in ast.walk(zwykly[0])))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
