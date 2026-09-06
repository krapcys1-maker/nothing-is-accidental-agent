# -*- coding: utf-8 -*-
"""Zapora „ta sama nazwa" nie rozbraja sie tym, przed czym broni.

NIE Z AUDYTU. Znalezione przez uruchomienie zestawu NA SERWERZE po wdrozeniu:
`test_wspolna_nazwa` przechodzil na Windows i padal na Linuksie. Przyczyna nie
byla w systemie — test czytal ZYWY korpus opublikowanych notek, wiec jego
werdykt zalezal od tego, co bot zdazyl napisac. Pod tym siedzialy dwie
prawdziwe usterki.

USTERKA 1 — ZAPORA SLABLA, IM WIECEJ O CZYMS PISALISMY.

`wspolna_nazwa` przepuszcza nazwe, ktora jest CZESTA w korpusie, bo taka nic
nie odroznia (docstring: „nazwa, ktora pada w POLOWIE naszych notek"). Prog
stal jednak na stale: `maks_czestosc = 2`. Przy korpusie 80 notek nazwa w
TRZECH tekstach to 3,75% — a mimo to uchodzila za czesta.

Zmierzone na zywym korpusie, przed naprawa:

    glm53        3 wystapienia    NIE BLOKUJE JUZ
    openai       8 wystapien      NIE BLOKUJE JUZ

`glm53` to nazwa, DLA KTOREJ TA FUNKCJA POWSTALA — 31 sierpnia wyszly trzy
notki o GLM-5.3-Flash jednego dnia i wlasciciel nazwal to plaskoscia. Te same
trzy notki przekroczyly prog i wylaczyly zapore, ktora kazaly napisac. Czwarta
notka o GLM przeszlaby bez slowa.

Prog idzie teraz za rozmiarem korpusu (jedna dwudziesta, podloga 2). Po
naprawie, na tym samym zywym korpusie: `glm53` (3) BLOKUJE, `openai` (8) wolne
— czyli dokladnie tak, jak docstring obiecywal od poczatku.

USTERKA 2 — ZAPORA POCZATKU ZDANIA DZIALALA TYLKO DLA PIERWSZEGO WYRAZU.

`nazwy_wlasne` odrzuca wyraz na poczatku zdania, jesli nie ma cyfry ani wielkiej
litery w srodku — „Cheap" nie jest nazwa. Pozycje liczyly sie jednak przez
`m.start()` wzorca `(?:^|[.!?]\s+)`, czyli przez pozycje KROPKI, a slowo stoi
dopiero za spacja. Warunek nie trafial w nic poza samym poczatkiem tekstu.

Zmierzone na tym samym korpusie — do nazw wlasnych wchodzily:

    that 15x, same 9x, when 6x, what 5x, nothing 4x, nobody, under, difference

Po naprawie (`m.end()`) nazw w korpusie jest 111 zamiast 197, i ani jeden
z tych wyrazow nie jest juz nazwa.

CZEGO TEN TEST PILNUJE — obie usterki, kazda od strony skutku, nie ksztaltu.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_zapora_nazw_nie_slabnie.py
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


A = "GLM-5.3-Flash repeats itself more than the charts suggest."
B = "GLM-5.3-Flash runs on Chinese-made chips, not Nvidia."

print("=== 1. IM WIECEJ O CZYMS PISZEMY, TYM ZAPORA MA BYC NADAL SILNA ===")
# Rosnacy korpus, w ktorym `glm53` stanowi staly, MALY udzial. Przy progu
# wpisanym na stale zapora puszczala go juz przy trzecim wystapieniu.
for ile_notek in (20, 40, 80, 200):
    korpus = ["Something about GLM-5.3-Flash happened."] * 3
    korpus += ["A note about Jalapeno chips and Treasury filings %d." % i
               for i in range(ile_notek - 3)]
    sprawdz("korpus %3d notek, glm53 w 3 z nich -> nadal blokuje" % ile_notek,
            stages.wspolna_nazwa(A, B, korpus) == "glm53",
            stages.wspolna_nazwa(A, B, korpus))

print()
print("=== 2. NAZWA NAPRAWDE CZESTA NADAL PRZESTAJE BLOKOWAC ===")
# Bez tego naprawa zamienilaby jeden blad na drugi: zapora blokowalaby wszystko.
# `openai` w 8 z 80 notek to wlasnie ten przypadek z docstringa.
korpus80 = ["OpenAI changed something again."] * 8
korpus80 += ["A note about %d unrelated things." % i for i in range(72)]
sprawdz("openai w 8 z 80 notek -> wolne",
        not stages.wspolna_nazwa("OpenAI raised prices",
                                 "OpenAI hired someone", korpus80),
        stages.wspolna_nazwa("OpenAI raised prices",
                             "OpenAI hired someone", korpus80))
sprawdz("ale rzadka nazwa w tym samym korpusie nadal blokuje",
        stages.wspolna_nazwa("The Jalapeno chip is inference-only",
                             "Jalapeno ships in March", korpus80) == "jalapeno",
        stages.wspolna_nazwa("The Jalapeno chip is inference-only",
                             "Jalapeno ships in March", korpus80))

print()
print("=== 3. PODLOGA PRZY MALYM KORPUSIE ===")
# Przy trzech tekstach udzial nic nie znaczy — prog nie moze zjechac do zera,
# bo wtedy KAZDA nazwa bylaby czesta i zapora zniknelaby zupelnie.
sprawdz("przy 3 tekstach zapora nadal dziala",
        stages.wspolna_nazwa(A, B, [A, B, "coś innego"]) == "glm53",
        stages.wspolna_nazwa(A, B, [A, B, "coś innego"]))
sprawdz("bez korpusu wystarcza sama wspolna nazwa",
        stages.wspolna_nazwa(A, B) == "glm53", stages.wspolna_nazwa(A, B))

print()
print("=== 4. POCZATEK ZDANIA NIE JEST NAZWA — TAKZE W SRODKU TEKSTU ===")
# Tu byla usterka: warunek trafial tylko w pozycje 0, bo liczyl pozycje KROPKI.
TEKST = "Cheap models are fine. That was the point. Nothing else changed."
_n = stages.nazwy_wlasne(TEKST)
for slowo in ("cheap", "that", "nothing"):
    sprawdz("%-8s nie jest nazwa wlasna" % slowo, slowo not in _n, sorted(_n))

print()
print("=== 5. ALE PRAWDZIWA NAZWA NA POCZATKU ZDANIA ZOSTAJE ===")
# Regula ma odrzucac wyraz pospolity, a nie kazdy wyraz po kropce.
_p = stages.nazwy_wlasne("The run failed. GPT-5 changed the default. "
                         "DeepSeek shipped it anyway.")
sprawdz("GPT-5 zostaje (ma cyfre)", "gpt5" in _p, sorted(_p))
sprawdz("DeepSeek zostaje (wielka litera w srodku)", "deepseek" in _p, sorted(_p))

print()
print("=== 5b. DRUGI MIANOWNIK: KORPUS ZRODEL ===")
# ZMIERZONE NA ZYWO 6 wrzesnia 2026, przebieg 154: przydzial trzech notek,
# wydana JEDNA, a szesciu kandydatow odrzuconych na `astra`, `google`,
# `claude`, `anthropic`, `openai's`. Przy progu liczonym z naszych 84 notek
# blokowaly 123 nazwy ze 124 — czyli zapora byla w praktyce regula
# „jakakolwiek wspolna nazwa wlasna".
#
# Korpus kanalow (206 tematow z tego samego tygodnia) to widzi:
#     claude 9 (4,4%)   astra 13 (6,3%)   openai 14 (6,8%)
#     glm53  4 (1,9%)   astm  0           glm53flash 0
# Czyli nazwy do zwolnienia sa czeste w zrodlach, a ta, dla ktorej zapora
# powstala — nie jest.
NASZE = ["nasza notka numer %d" % i for i in range(84)]
# Nazwy MUSZA stac w srodku zdania: na poczatku ida do worka „niepewnych"
# i wtedy w ogole nie sa nazwami. Pierwsza wersja tego sprawdzenia miala je
# na poczatku i „przechodzila" z zupelnie innego powodu.
A1 = "This week Anthropic raised prices for its API."
A2 = "Last month Anthropic hired a new head of policy."
G1 = "The model GLM-5.3-Flash repeats itself more than charts suggest."
G2 = "In tests GLM-5.3-Flash ran on Chinese-made chips."
ZRODLA = (["Report says Anthropic did something %d" % i for i in range(20)]
          + ["Something unrelated %d" % i for i in range(60)])

sprawdz("bez korpusu zrodel anthropic BLOKUJE (stan sprzed zmiany)",
        stages.wspolna_nazwa(A1, A2, NASZE) == "anthropic")
sprawdz("z korpusem, gdzie jest czeste — juz NIE blokuje",
        not stages.wspolna_nazwa(A1, A2, NASZE, korpus_zrodel=ZRODLA),
        stages.wspolna_nazwa(A1, A2, NASZE, korpus_zrodel=ZRODLA))
sprawdz("a glm53 blokuje w OBU przypadkach",
        stages.wspolna_nazwa(G1, G2, NASZE) == "glm53"
        and stages.wspolna_nazwa(G1, G2, NASZE,
                                 korpus_zrodel=ZRODLA) == "glm53")
sprawdz("pusty korpus zrodel niczego nie zwalnia",
        stages.wspolna_nazwa(A1, A2, NASZE, korpus_zrodel=[]) == "anthropic")

print()
print("=== 5c. KORPUS ZRODEL NIE SIEGA DO SIECI Z TESTU ===")
# Ta funkcja jest wolana z `notki_dnia` przy kazdym wyborze materialu. Gdyby
# w tescie pobierala kanaly, kazde uruchomienie zestawu czekaloby na siec.
sprawdz("_tematy_zrodel w tescie oddaje pustke",
        stages._tematy_zrodel() == [], stages._tematy_zrodel()[:2])
_zr2 = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("i pyta o to config.W_TESCIE", "if config.W_TESCIE:" in _zr2)
sprawdz("a awaria pobierania nie podnosi wyjatku",
        "korpus zrodel niedostepny" in _zr2)

print()
print("=== 6. WYBOR NOTKI KORZYSTA Z TEGO SAMEGO PROGU ===")
# Zapora ma sens tylko wtedy, gdy siega po nia produkcja.
_zr = pathlib.Path("agent-v2/stages.py").read_text(encoding="utf-8")
sprawdz("wybor notki liczy rzadkosc w opublikowanych tekstach",
        "korpus = opublikowane_teksty() or teksty_wczesniej" in _zr)
sprawdz("prog nie jest juz wpisany na stale",
        "maks_czestosc: int = 2" not in _zr)
sprawdz("i liczy sie z dlugosci korpusu",
        "max(4, len(korpus) // 20)" in _zr and "len(korpus) < 20" in _zr)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
