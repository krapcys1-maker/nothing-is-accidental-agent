# -*- coding: utf-8 -*-
"""SKRACANIE PRZEPISANIEM (13.11.2026): `stages.skroc_notke` i jego wpiecie w `stages.note`.

Proba na sucho: przy poleceniu 40-70 slow pisarz oddawal 84-159. Notka ponad `config.NOTE_SKROC_POWYZEJ` wraca do pisarza;
krotsza wersja wchodzi tylko, gdy jest naprawde krotsza i nie krotsza niz minimum; awaria = pierwsza wersja.

BEZ PYTESTA, bez sieci, bez modelu (atrapy). Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_skracanie_notek.py
"""
import json
import pathlib
import re
import sys
from unittest.mock import patch

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

wyniki = {"ok": 0, "zle": 0}


def sprawdz(opis: str, warunek: bool) -> None:
    wyniki["ok" if warunek else "zle"] += 1
    print("  %s  %s" % ("OK  " if warunek else "BLAD", opis))


DLUGA = " ".join(["word"] * 120)


def odpowiedz(tekst):
    return lambda *a, **k: json.dumps({"note": tekst})


print("=== 1. skroc_notke ===")
with patch.object(stages.llm, "call", odpowiedz(" ".join(["short"] * 60))):
    sprawdz("krotsza w oknie wchodzi", stages.skroc_notke(None, 1, "note", DLUGA, 40, 70) == " ".join(["short"] * 60))
with patch.object(stages.llm, "call", odpowiedz(" ".join(["long"] * 130))):
    sprawdz("dluzsza od pierwszej nie wchodzi", stages.skroc_notke(None, 1, "note", DLUGA, 40, 70) is None)
with patch.object(stages.llm, "call", odpowiedz(" ".join(["tiny"] * 20))):
    sprawdz("ponizej minimum nie wchodzi (zadnych aforyzmow)", stages.skroc_notke(None, 1, "note", DLUGA, 40, 70) is None)
with patch.object(stages.llm, "call", odpowiedz("")):
    sprawdz("pusta nie wchodzi", stages.skroc_notke(None, 1, "note", DLUGA, 40, 70) is None)


def pada(*a, **k):
    raise RuntimeError("siec")


with patch.object(stages.llm, "call", pada):
    sprawdz("awaria modelu = None (idzie pierwsza wersja)", stages.skroc_notke(None, 1, "note", DLUGA, 40, 70) is None)
przechwycony = {}


def lap(etap, system, prompt, **k):
    przechwycony.update(etap=etap, prompt=prompt)
    return json.dumps({"note": " ".join(["s"] * 50)})


with patch.object(stages.llm, "call", lap):
    stages.skroc_notke(None, 1, "notka_przeslania", DLUGA, 40, 70)
sprawdz("ten sam pisarz (etap)", przechwycony.get("etap") == "notka_przeslania")
sprawdz("prompt ma szkic, okno i zakaz dodawania faktow",
        DLUGA in przechwycony.get("prompt", "") and "40-70" in przechwycony.get("prompt", "")
        and "nothing new added" in przechwycony.get("prompt", ""))

print("=== 2. wpiecie w note() i konfiguracja ===")
src = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("prog w konfiguracji 75", config.NOTE_SKROC_POWYZEJ == 75)
sprawdz("skracanie jest w note() po dopieciu pytania E18",
        0 < src.index('data["note"] = dopnij_pytanie(') < src.index("_krotsza = skroc_notke(conn, run_id, etap,"))
sprawdz("skracanie przed bramka/wiernoscia (sprawdzaja tekst, ktory pojdzie)",
        src.index("_krotsza = skroc_notke(conn, run_id, etap,") < src.index("data = _przez_bramke_notki(conn, run_id, etap,"))
sprawdz("formy dlugie wylaczone",
        re.search(r"if \(note_form not in config\.FORMY_DLUGIE\s+and isinstance\(data\.get\(\"note\"\), str\)\s+"
                  r"and len\(data\[\"note\"\]\.split\(\)\) > config\.NOTE_SKROC_POWYZEJ\)", src) is not None)

print("=== 3. skracanie po naprawie faktu (14.11.2026) ===")
_i_napr = src.index('data["tekst_przed_naprawa"] = data.get("note")')
_i_skr = src.index('_krotsza = skroc_notke(conn, run_id, etap, poprawka["tekst"],')
_i_wer = src.index('data["weryfikacja"] = audyt')
sprawdz("drugie skracanie siedzi w galezi naprawy, przed zapisem weryfikacji", _i_napr < _i_skr < _i_wer)
_blok = src[_i_skr:_i_wer]
sprawdz("krotsza po naprawie jest sprawdzana od nowa (zweryfikuj)", "zweryfikuj(conn, run_id, _krotsza, kontekst)" in _blok)
sprawdz("obalone albo niesprawdzone = zostaje naprawiona wersja",
        '_audyt_k.get("nie_sprawdzone") or _obalone_k' in _blok and '"refuted", "outdated"' in _blok)
sprawdz("krotsza przechodzi zapore notki", "_zapora_notki(_krotsza)" in _blok)

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (wyniki["ok"], wyniki["zle"]))
sys.exit(1 if wyniki["zle"] else 0)
