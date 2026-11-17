# -*- coding: utf-8 -*-
"""ADRES DOKUMENTU A WYNIKI WYSZUKIWARKI (17.11.2026): `research._w_wynikach`.

Na sucho: prospekt S-1 Anthropic stal w wynikach wyszukiwarki z doklejonymi parametrami sledzacymi, model oddal
adres czysty, a scisle porownanie go odrzucilo. Bez pytesta, bez sieci. Z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_dokument_adres.py
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import research as r  # noqa: E402

wyniki = {"ok": 0, "zle": 0}


def sprawdz(opis, warunek):
    wyniki["ok" if warunek else "zle"] += 1
    print("  %s  %s" % ("OK  " if warunek else "BLAD", opis))


K = r.url_key
REAL = {K("https://www.sec.gov/Archives/x/anthropicpbc-sx1.htm?kuid=f4&kref=https%3A%2F%2Fa.com"),
        K("https://example.org/report?id=7")}
sprawdz("czysty adres przechodzi, gdy wyniki maja ten sam adres z parametrami sledzacymi",
        r._w_wynikach(K("https://www.sec.gov/Archives/x/anthropicpbc-sx1.htm"), REAL))
sprawdz("dokladny adres przechodzi", r._w_wynikach(K("https://example.org/report?id=7"), REAL))
sprawdz("wlasny parametr modelu na prawdziwej sciezce NIE przechodzi",
        not r._w_wynikach(K("https://www.sec.gov/Archives/x/anthropicpbc-sx1.htm?id=9"), REAL))
sprawdz("inny parametr niz w wynikach NIE przechodzi", not r._w_wynikach(K("https://example.org/report?id=8"), REAL))
sprawdz("inna sciezka NIE przechodzi", not r._w_wynikach(K("https://www.sec.gov/Archives/y.htm"), REAL))
sprawdz("pusty adres NIE przechodzi", not r._w_wynikach("", REAL))
src = pathlib.Path("agent-v2/research.py").read_text(encoding="utf-8")
sprawdz("oba miejsca porownania uzywaja _w_wynikach (szukanie i dokument)",
        src.count("not _w_wynikach(key, real)") == 2 and "key not in real" not in src)
print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (wyniki["ok"], wyniki["zle"]))
sys.exit(1 if wyniki["zle"] else 0)
