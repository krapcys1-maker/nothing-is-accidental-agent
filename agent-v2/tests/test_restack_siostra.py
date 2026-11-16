# -*- coding: utf-8 -*-
"""RESTACK NIE IDZIE DO KONTA SIOSTRZANEGO (16.11.2026): 16 ze 170 restackow poszlo do drugiego bota wlasciciela.

BEZ PYTESTA, bez sieci. Z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_restack_siostra.py
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import browser  # noqa: E402

wyniki = {"ok": 0, "zle": 0}


def sprawdz(opis, warunek):
    wyniki["ok" if warunek else "zle"] += 1
    print("  %s  %s" % ("OK  " if warunek else "BLAD", opis))


u = browser.uchwyty_z_odsylaczy(["https://substack.com/@NIA1503032?utm=x", "/@kaanyagci", "/@kaanyagci/note/c-1", "", None, "/p/x"])
sprawdz("uchwyty z odsylaczy: male litery, bez powtorzen, bez smieci", u == ["nia1503032", "kaanyagci"])
siostra = config.UCHWYTY_SIOSTRZANE[0].lower()
sprawdz("notka siostry odpada", browser.notka_konta_siostrzanego({"uchwyty": [siostra]}))
sprawdz("„siostra restackowala kogos” tez odpada", browser.notka_konta_siostrzanego({"uchwyty": ["kaanyagci", siostra]}))
sprawdz("zwykla notka przechodzi", not browser.notka_konta_siostrzanego({"uchwyty": ["kaanyagci"]}))
sprawdz("brak pola uchwyty przechodzi (stary ksztalt)", not browser.notka_konta_siostrzanego({"tekst": "x"}))
src = pathlib.Path("agent-v2/browser.py").read_text(encoding="utf-8")
i_f = src.index("if notka_konta_siostrzanego(notka):")
sprawdz("filtr stoi w petli restackow przed decyzja modelu (zero kosztu)",
        src.index("def restackuj_w_kanale(") < i_f < src.index("ocena = decyzja(notka)"))
sprawdz("kontener notki zbiera odsylacze do profili", '"uchwyty": uchwyty_z_odsylaczy(' in src)
print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (wyniki["ok"], wyniki["zle"]))
sys.exit(1 if wyniki["zle"] else 0)
