# -*- coding: utf-8 -*-
"""ZMIANY Z ANALIZY PRZYROSTU 16.11.2026: E25 forma trzech wierszy, naprawa MYSL, subskrypcje 3, rozkmina co 4 dni,
polecenia o zrodle pierwotnym i o dopowiedzeniach.

BEZ PYTESTA, bez sieci, bez modelu (atrapy). Z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_analiza_przyrostu_16_11.py
"""
import json
import pathlib
import sys
from unittest.mock import patch

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

wyniki = {"ok": 0, "zle": 0}


def sprawdz(opis, warunek, szczegol=""):
    wyniki["ok" if warunek else "zle"] += 1
    print("  %s  %s%s" % ("OK  " if warunek else "BLAD", opis, "" if warunek else "   " + str(szczegol)[:200]))


SRC = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
PR = lambda n: pathlib.Path("agent-v2/prompts/" + n).read_text(encoding="utf-8")  # noqa: E731

print("=== 1. E25 forma trzech wierszy ===")
e = config.EKSPERYMENTY.get("forma_trzy_wiersze") or {}
sprawdz("eksperyment 50/50 od 17.11 do 28.12", e == {"udzial": 0.5, "od": "2026-11-17", "do": "2026-12-28"}, e)
f = config.NOTE_FORMS.get("TRZY_WIERSZE", "")
sprawdz("forma istnieje i zakazuje przezyc", "never as something you saw, did or lived" in f and "Three short lines" in f)
sprawdz("forma NIE jest w zwyklej rotacji (tylko przez eksperyment)", "TRZY_WIERSZE" not in config.NOTE_FORM_MIX)
_i = SRC.index('_ramie_formy = ramie("forma_trzy_wiersze", od + nr)')
_blok = SRC[_i - 600:_i + 300]
sprawdz("bez MYSL, promocji, czesci serii i form dlugich",
        'if typ not in ("MYSL", "ARTYKUL") and not seria_kontekst and forma not in config.FORMY_DLUGIE:' in _blok)
sprawdz("ramie ustawia forme przed pisarzem",
        _i < SRC.index("wynik = note(conn, run_id, typ, material,", _i) and 'forma = "TRZY_WIERSZE"' in _blok)
sprawdz("ramie idzie do dziennika", '("forma_trzy_wiersze", _ramie_formy)) if r}' in SRC)
sprawdz("ramie zerowane przy kazdej notce", '_ramie_formy = ""   # E25' in SRC)
_d = "2026-11-20"
_r = [stages.ramie("forma_trzy_wiersze", i, _d) for i in range(400)]
sprawdz("los ok. polowa w oknie", 0.4 < _r.count("on") / 400 < 0.6, _r.count("on"))
sprawdz("przed oknem brak ramienia", stages.ramie("forma_trzy_wiersze", 1, "2026-11-16") == "")
_k = [stages.ramie("krotka_notka", i, _d) for i in range(400)]
sprawdz("los niezalezny od E17/E18 (rozne hasze)", _r != _k)

print("=== 2. naprawa MYSL ===")
OBAL = {"zarzuty": [{"claim": "48% of schools switched it off", "status": "refuted"}]}
CZYSTY = {"zarzuty": [], "claims": [], "safe_to_post": True}


def model(tekst):
    return lambda *a, **k: json.dumps({"text": tekst, "co_zmienione": "removed the number"})


stages._NAPRAW_ZUZYTE.clear()
with patch.object(stages.llm, "call", model("Schools keep the switch, but the default decides.")), \
        patch.object(stages, "zweryfikuj", lambda *a, **k: CZYSTY):
    w = stages.napraw_mysl(None, 901, "48% of schools switched it off, so the default decides.", OBAL,
                           kontekst="", min_slow=5, max_slow=70)
sprawdz("czysta poprawka wchodzi", bool(w) and w["tekst"].startswith("Schools keep") and w["obalonych_po"] == 0, w)
stages._NAPRAW_ZUZYTE.clear()
with patch.object(stages.llm, "call", model("Still 48% of schools.")), \
        patch.object(stages, "zweryfikuj", lambda *a, **k: OBAL):
    sprawdz("nadal obalone = None", stages.napraw_mysl(None, 902, "x 48%", OBAL, kontekst="", min_slow=1, max_slow=70) is None)
stages._NAPRAW_ZUZYTE.clear()
with patch.object(stages.llm, "call", model("Clean.")), \
        patch.object(stages, "zweryfikuj", lambda *a, **k: {"zarzuty": [], "nie_sprawdzone": True}):
    sprawdz("niesprawdzona = None", stages.napraw_mysl(None, 903, "x 48%", OBAL, kontekst="", min_slow=1, max_slow=70) is None)
with patch.object(stages.llm, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nie wolno wolac"))):
    sprawdz("bez obalonych nie ma wywolania", stages.napraw_mysl(None, 904, "x", CZYSTY, kontekst="", min_slow=1, max_slow=70) is None)
sprawdz("note() wola napraw_mysl dla MYSL zamiast pomijac naprawe",
        'napraw_mysl(conn, run_id, proza, audyt_do_naprawy' in SRC and 'if note_type == "MYSL" else napraw_obalone(' in SRC)
sprawdz("polecenie MYSL zakazuje dodawania liczb", "Add no number, date, study, statistic or named organisation" in stages.NAPRAWA_MYSLI)

print("=== 3. konfiguracja i polecenia ===")
sprawdz("subskrypcje 3 dziennie, stopien rampy od 17.11",
        config.SUBSKRYPCJE_DZIENNIE == 3 and config.rampa_aktywnosci("2026-11-17")[1] == 3
        and config.rampa_aktywnosci("2026-11-16")[1] == 1)
sprawdz("rozkmina co 4 dni", config.ROZKMINA_CO_DNI == 4)
sprawdz("sprawdzanie faktow ocenia dopowiedzenia i przypisanie zrodla",
        "loaded characterisations" in PR("weryfikacja.md") and "\"independent\"" in PR("weryfikacja.md"))
sprawdz("pisarze: zrodlo pierwotne przed streszczeniem",
        "credit that document, not the outlet" in PR("seria_lekka.md") and "credit it rather than the press summary" in PR("przeslania.md"))
print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (wyniki["ok"], wyniki["zle"]))
sys.exit(1 if wyniki["zle"] else 0)
