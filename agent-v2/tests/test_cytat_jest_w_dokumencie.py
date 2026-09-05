# -*- coding: utf-8 -*-
"""Cytat wchodzi do karty tylko wtedy, gdy naprawde stoi w dokumencie.

CO SIE DZIALO (R8 z audytu researchu, potwierdzone na naszym kodzie).
`classify` przyjmowal KAZDY niepusty napis z pola `excerpts` — filtr brzmial
doslownie „to napis i nie jest pusty". Prompt bardzo dokladnie opisuje
obowiazek doslownego kopiowania, ale prosba nie jest bramka.

Odtworzenie audytu: dokument mowil „The only documented number is 12", model
oddal „A study found 97 percent effectiveness", a kod zachowal to jako dowod
klasy PRIMARY. Cytat istnial dlatego, ze model powiedzial, ze go skopiowal —
i szedl dalej jako podstawa artykulu.

TA SAMA RODZINA, CO DWA PRZEGRANE ARTYKULY: regula stala w prompcie i nikt
jej nie liczyl. Z ta roznica, ze tutaj skutkiem jest wymyslony dowod.

GRANICA TEGO SPRAWDZENIA — i ona jest tu najwazniejsza. Wyrownujemy bialy
znak i znaki typograficzne (apostrof, cudzyslow, myslnik), bo model przepisuje
je raz tak, raz inaczej i to nie jest przeklamanie cytatu. NIE ruszamy liczb,
jednostek, przeczen ani wielkosci liter: „12" wobec „97" i „is" wobec „is not"
MAJA sie roznic. Zbyt szerokie wyrownanie przepuscilo by dokladnie ten falsz,
przed ktorym ta bramka stoi.

CZEGO TO NIE DOWODZI: ze twierdzenie jest prawdziwe. Tylko ze zdanie stoi
w dokumencie, ktory pobralismy.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_cytat_jest_w_dokumencie.py
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v2")

import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import stages   # noqa: E402

zdane = 0
oblane = 0


def sprawdz(opis, warunek, dodatek=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % opis)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (opis, dodatek))


jest = stages.cytat_jest_w_dokumencie

DOK = ("The agency published its findings in March.\n"
       "The only documented number is 12, and the report says it is not "
       "a measurement of effectiveness.\n"
       "Costs rose 4.5 percent over the period 2024–2026.")

print("=== 1. PRZYPADEK Z AUDYTU ===")
sprawdz("wymyslony cytat NIE przechodzi",
        not jest("A study found 97 percent effectiveness.", DOK))
sprawdz("prawdziwy cytat przechodzi",
        jest("The only documented number is 12", DOK))

print()
print("=== 2. KSZTALT ZNAKOW WOLNO WYROWNAC ===")
# Model przepisuje apostrof, cudzyslow i myslnik raz tak, raz inaczej.
# To nie jest przeklamanie cytatu, a odrzucenie takiego fragmentu kosztowaloby
# nas dobre zrodlo.
sprawdz("zlamany wiersz w srodku cytatu nie przeszkadza",
        jest("in March. The only documented number is 12", DOK))
sprawdz("podwojna spacja nie przeszkadza",
        jest("The  only   documented number is 12", DOK))
sprawdz("myslnik typograficzny rowna sie zwyklemu",
        jest("the period 2024-2026", DOK))
sprawdz("i w druga strone tez",
        stages.cytat_jest_w_dokumencie("2024–2026",
                                       "the period 2024-2026"))
sprawdz("apostrof typograficzny rowna sie prostemu",
        stages.cytat_jest_w_dokumencie("the agency’s report",
                                       "we read the agency's report today"))

print()
print("=== 3. CZEGO WYROWNAC NIE WOLNO ===")
# Tu jest cala wartosc tej bramki. Zbyt szerokie wyrownanie przepuscilo by
# dokladnie ten falsz, ktory ma zatrzymac.
sprawdz("inna liczba to INNY cytat",
        not jest("The only documented number is 97", DOK))
sprawdz("usuniete przeczenie to INNY cytat",
        not jest("the report says it is a measurement of effectiveness", DOK))
sprawdz("zmieniona jednostka to INNY cytat",
        not jest("Costs rose 4.5 percent over the period 2024-2027", DOK))
sprawdz("dopisane slowo to INNY cytat",
        not jest("The only documented number is exactly 12", DOK))

print()
print("=== 4. PRZYPADKI BRZEGOWE NIE WYWALAJA PRZEBIEGU ===")
sprawdz("pusty cytat odpada", not jest("", DOK))
sprawdz("same biale znaki odpadaja", not jest("   \n  ", DOK))
sprawdz("pusty dokument odrzuca wszystko", not jest("cokolwiek", ""))
sprawdz("None nie wywala", not jest(None, DOK) and not jest("x", None))

print()
print("=== 5. KLASYFIKATOR NAPRAWDE Z TEGO KORZYSTA ===")
# Sama funkcja nic nie znaczy, jesli filtr jej nie wola — to ta sama rodzina
# wad, co martwy wpis EFFORT.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("classify odsiewa fragmenty spoza dokumentu",
        "cytat_jest_w_dokumencie(e, text)" in _zr)
sprawdz("i melduje to GLOSNO, a nie po cichu",
        "NIE MA w dokumencie" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
