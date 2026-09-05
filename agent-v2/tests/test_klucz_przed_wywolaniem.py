# -*- coding: utf-8 -*-
"""Brak klucza zatrzymuje KAZDY etap, nie trzy wybrane.

CO ZMIERZONO. `_preflight` porownywalo model do trzech KONKRETNYCH
identyfikatorow: `CLAUDE` (`claude-opus-5`), `DEEPSEEK` (`deepseek-v4-flash`)
i `IMAGE_MODEL`. W systemie sa jednak jeszcze dwa:

    FABLE        = "claude-fable-5-1"   -> etap `write`, czyli ARTYKUL
    DEEPSEEK_PRO = "deepseek-v4-pro"    -> jedenascie etapow, m.in. comment,
                                           reply, restack, discovery, synthesis

Te etapy przy braku klucza NIE zatrzymywaly sie na kontroli wstepnej: szly do
sieci i wywracaly sie na odpowiedzi HTTP, wiec komunikat mowil o transporcie,
a nie o brakujacym kluczu. Cala idea `_preflight` to „nie place za wywolanie
niemozliwe od pierwszej sekundy" — a nie dzialala dla dwoch modeli z pieciu,
w tym dla tego, ktory pisze artykuly.

Znalazl to obcy model mapujacy repozytorium (repo `nia-substack-bot`,
`docs/ROZWIAZYWANIE_PROBLEMOW.md` §3). Ten test nie powtarza jego opisu —
przechodzi po WSZYSTKICH etapach z `config.MODEL_FOR` i dla kazdego sprawdza,
ze brak wlasciwego klucza konczy sie `PreflightFailed`. Dopisanie nowego
modelu bez klucza obleje go automatycznie.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    PYTHONIOENCODING=utf-8 python agent-v2/tests/test_klucz_przed_wywolaniem.py
Zero wywolan modelu (kontrola wstepna oblewa PRZED siecia), zero zapisow.
"""
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import llm      # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


KLUCZE = {"anthropic": "ANTHROPIC_API_KEY",
          "deepseek": "DEEPSEEK_API_KEY",
          "openai": "OPENAI_API_KEY"}


class Polaczenie:
    """`conn` nie jest dotykane: kontrola klucza oblewa przed zapytaniem."""

    def execute(self, *a, **k):
        raise AssertionError("kontrola klucza puscila dalej, a nie powinna")


def bez_klucza(dostawca_nazwa, purpose):
    """Czy `_preflight` oblewa, gdy brakuje klucza TEGO dostawcy."""
    stare = {n: getattr(config, n) for n in KLUCZE.values()}
    stary_kill = config.KILL_SWITCH
    stare_wolno = config.WOLNO_WOLAC_MODEL
    try:
        # Wszystkie klucze ustawione, POZA badanym — inaczej test nie mowi,
        # ktorego brak zatrzymal wywolanie.
        for nazwa in KLUCZE.values():
            setattr(config, nazwa, "atrapa")
        setattr(config, KLUCZE[dostawca_nazwa], "")
        config.KILL_SWITCH = False
        config.WOLNO_WOLAC_MODEL = True
        try:
            llm._preflight(purpose, Polaczenie(), None)
        except llm.PreflightFailed as exc:
            return str(exc)
        return ""
    finally:
        for nazwa, wartosc in stare.items():
            setattr(config, nazwa, wartosc)
        config.KILL_SWITCH = stary_kill
        config.WOLNO_WOLAC_MODEL = stare_wolno


print("=== 1. DOSTAWCA LICZONY Z MODELU — WSZYSTKIE PIEC IDENTYFIKATOROW ===")
# Nazwy modeli biore z configu, nie wpisuje: gdy dojdzie szosty, ten test
# ma o nim wiedziec bez mojej pomocy.
MODELE = {n: getattr(config, n) for n in
          ("CLAUDE", "DEEPSEEK", "DEEPSEEK_PRO", "FABLE", "FABLE_5", "IMAGE_MODEL")
          if hasattr(config, n)}
for nazwa, model in sorted(MODELE.items()):
    d = llm.dostawca(model)
    sprawdz("%-13s (%s) -> %s" % (nazwa, model, d), d in KLUCZE, d)

print()
print("=== 2. KAZDY ETAP Z `MODEL_FOR` ZATRZYMUJE SIE NA BRAKU KLUCZA ===")
# To jest cala pointa: nie „trzy modele", a KAZDY etap, ktory bot potrafi
# odpalic. Etapow jest dzis ponad dwadziescia i wiekszosc chodzi codziennie.
bez_ochrony = []
for purpose in sorted(config.MODEL_FOR):
    model = config.MODEL_FOR[purpose]
    d = llm.dostawca(model)
    komunikat = bez_klucza(d, purpose)
    if not komunikat:
        bez_ochrony.append((purpose, model, d))
sprawdz("wszystkie %d etapow zatrzymuje sie bez klucza" % len(config.MODEL_FOR),
        not bez_ochrony, bez_ochrony)
# I KOMUNIKAT MA MOWIC, CZEGO BRAKUJE — inaczej diagnoza zaczyna sie od zlego
# konca, dokladnie tak jak przy bledzie transportu.
for purpose in ("write", "comment", "reply", "note"):
    if purpose not in config.MODEL_FOR:
        continue
    d = llm.dostawca(config.MODEL_FOR[purpose])
    komunikat = bez_klucza(d, purpose)
    sprawdz("komunikat dla `%s` nazywa brakujacy klucz (%s)" % (purpose, KLUCZE[d]),
            KLUCZE[d] in komunikat and purpose in komunikat, komunikat)

print()
print("=== 3. KONTRDOWOD: STARA REGULA PRZEPUSZCZALA DWA MODELE Z PIECIU ===")
# Odtwarzamy tamte trzy porownania na tych samych modelach. Gdyby stara regula
# dawala to samo co nowa, cala poprawka byla by bez znaczenia.


def stara_regula(model):
    """Regula sprzed 3 wrzesnia 2026: porownanie do trzech nazw modeli."""
    if model == config.CLAUDE:
        return "sprawdzany"
    if model == config.DEEPSEEK:
        return "sprawdzany"
    if model == config.IMAGE_MODEL:
        return "sprawdzany"
    return "PRZEPUSZCZONY"


przepuszczone = sorted(n for n, m in MODELE.items()
                       if stara_regula(m) == "PRZEPUSZCZONY")
sprawdz("stara regula przepuszczala: %s" % (", ".join(przepuszczone) or "nic"),
        set(przepuszczone) >= {"FABLE", "DEEPSEEK_PRO"}, przepuszczone)
sprawdz("a nowa nie przepuszcza zadnego",
        all(llm.dostawca(m) in KLUCZE for m in MODELE.values()))
# ILE ETAPOW BYLO BEZ OCHRONY. Liczba, nie przymiotnik.
ile_bylo = sum(1 for p, m in config.MODEL_FOR.items()
               if stara_regula(m) == "PRZEPUSZCZONY")
sprawdz("bez ochrony bylo %d etapow z %d" % (ile_bylo, len(config.MODEL_FOR)),
        ile_bylo >= 10, ile_bylo)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
