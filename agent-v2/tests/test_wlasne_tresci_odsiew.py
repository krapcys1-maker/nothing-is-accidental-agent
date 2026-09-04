# -*- coding: utf-8 -*-
"""Agent nie moze skomentowac WLASNEJ notki.

ZNALEZIONE 4 wrzesnia 2026 audytem zewnetrznym (pozycja A31), potwierdzone
w naszym kodzie. Odsiew wlasnych tresci pytal WYLACZNIE o adres:

    if config.SUBSTACK_HANDLE in (kandydat["url"] or ""):

Adres notki ma postac `substack.com/note/c-<id>` i NIE NIESIE uchwytu w ogole,
wiec ten warunek byl falszywy dla KAZDEJ notki — takze naszej. Publicznie
wyglada to jak bot rozmawiajacy sam ze soba.

Uchwyt autora lezal w tej samej strukturze, jedna linie wyzej
(`"uchwyt": kom.get("handle")`), i nikt go nie pytal. Ten sam plik ma zreszta
poprawne porownanie w innym miejscu (`c.get("handle") == SUBSTACK_HANDLE`) —
czyli w kodzie stalo obok siebie rozwiazanie dobre i zle.

DRUGA POLOWA (A32): porownanie PODCIAGIEM wycina CUDZE publikacje. Uchwyt
„art" odrzucilby `smartinvestor.substack.com`, „news" — `thenewsletter...`.
Nasz uchwyt ma 19 znakow, wiec dzis by nie zaszkodzil, ale to wlasnosc naszej
NAZWY, nie kodu.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_wlasne_tresci_odsiew.py
Zero wywolan modelu, zero sieci.
"""
import pathlib
import re
import sys

sys.path.insert(0, "agent-v2")
import config  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


H = config.SUBSTACK_HANDLE


def odsiew(uchwyt, url):
    """Ta sama decyzja co w `kanal.py` — uchwyt DOKLADNIE, adres jako zapas."""
    return (str(uchwyt or "").lower() == H.lower()) or (H in (url or ""))


print("=== 1. WLASNA NOTKA ODPADA, CHOC ADRES NIE NIESIE UCHWYTU ===")
sprawdz("nasza notka jest rozpoznana jako nasza",
        odsiew(H, "https://substack.com/note/c-329518656"))
sprawdz("KONTRDOWOD: sam adres notki NIE wystarczy — na tym polegal blad",
        not (H in "https://substack.com/note/c-329518656"))
sprawdz("nasz artykul nadal odpada po adresie",
        odsiew("", "https://nothingisaccidental.substack.com/p/cokolwiek"))

print()
print("=== 2. CUDZE TRESCI MAJA PRZECHODZIC ===")
sprawdz("cudza notka przechodzi",
        not odsiew("someoneelse", "https://substack.com/note/c-111"))
sprawdz("cudza publikacja przechodzi",
        not odsiew("smartinvestor", "https://smartinvestor.substack.com/p/x"))
sprawdz("pusty uchwyt i pusty adres nie wywracaja", not odsiew("", ""))
sprawdz("uchwyt roznica wielkosci liter to nadal nasz",
        odsiew(H.upper(), "https://substack.com/note/c-222"))

print()
print("=== 3. KONTRDOWOD NA PODCIAG (A32) ===")
# Gdyby porownanie szlo PODCIAGIEM uchwytu, krotki uchwyt wycinalby cudze
# publikacje. Sprawdzamy na uchwycie zastepczym, bo nasz ma 19 znakow.
def odsiew_podciagiem(uchwyt_nasz, url):
    return uchwyt_nasz in (url or "")


sprawdz("podciag 'art' wycinalby smartinvestor — dlatego go nie uzywamy",
        odsiew_podciagiem("art", "https://smartinvestor.substack.com/p/x"))
sprawdz("a porownanie dokladne go przepuszcza",
        not ("art" == "smartinvestor"))

print()
print("=== 4. KOD NAPRAWDE TAK ROBI ===")
zrodlo = pathlib.Path("agent-v2/kanal.py").read_text(encoding="utf-8")
sprawdz("odsiew notek pyta o uchwyt, nie tylko o adres",
        re.search(r"kandydat\.get\(\"uchwyt\"\)", zrodlo) is not None)
sprawdz("odsiew postow tez pyta o uchwyt publikacji",
        "_uchwyt" in zrodlo)
sprawdz("porownanie uchwytu jest DOKLADNE, nie podciagiem",
        "== config.SUBSTACK_HANDLE.lower()" in zrodlo)
sprawdz("adres zostaje jako zapas, nie znika",
        zrodlo.count("config.SUBSTACK_HANDLE in") >= 2,
        zrodlo.count("config.SUBSTACK_HANDLE in"))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
