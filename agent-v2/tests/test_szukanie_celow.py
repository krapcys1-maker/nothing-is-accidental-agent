# -*- coding: utf-8 -*-
"""Agent ma szukac celow o AI i szukac ich, AZ ZNAJDZIE.

DWIE WADY, JEDNA UKRYTA POD DRUGA.

1. HASLA WYSZUKIWANIA BYLY Z EPOKI PRZEDMIOTOW — dziesiaty raz ta sama
   choroba w jednej sesji. Wszystkie osiemnascie opisywalo poprzednie pismo:

       "food labeling rules", "packaging regulation", "building codes
       regulation", "transport standards", "product recall", "zoning"...

   ANI JEDNO nie dotyczylo AI. Piec dni po przestawieniu konta, po poprawieniu
   dwudziestu blokow w dziewieciu promptach, po wyczyszczeniu banku tematow
   i po zaostrzeniu reguly celow — hasel nikt nie tknal.

   SKUTEK BYL ODWROTNY DO WYGLADU. Agent szukal „przepisow o etykietowaniu
   zywnosci", dostawal posty o etykietowaniu zywnosci, a regula `cele.md`
   POPRAWNIE je odrzucala, bo nie dotycza AI. W logu wygladalo to na
   wybrednosc modelu:

       [cele] warte komentarza: 0/15
       [cele] warte komentarza: 1/13

   a bylo szukaniem nie tego, czego trzeba.

2. JEDNA PULA, JEDNA OCENA, KONIEC. Jesli z trzynastu kandydatow przechodzil
   jeden, wychodzil JEDEN komentarz — przy planie pietnastu. Przebieg nie
   probowal drugi raz.

Wlasciciel: „niech szuka celi (...) i niech szuka az znajdzie i komentuje".

CO TA POPRAWKA CELOWO ZOSTAWIA BEZ ZMIAN: odstepy. Wiecej celow to nie
szybsze pisanie — `rytm()` nadal trzyma 5-15 minut miedzy komentarzami,
a `ODSTEP_DNI_NA_PUBLIKACJE` cztery dni na te sama publikacje. Wlasciciel byl
jednoznaczny juz wczesniej: „nie chodzi o LICZBE, tylko o ODSTEPY".

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repo.
"""
import pathlib
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


print("=== 1. HASLA SZUKAJA AI, NIE PRZEDMIOTOW ===")
hasla = [h.lower() for h in config.HASLA_SZUKANIA]
# Lista slow, po ktorych poznajemy nasz rewir. Jawna i krotka, zeby dalo sie
# ja przeczytac i zakwestionowac — a nie zgadywac, co test uznaje za „o AI".
ZNAKI_AI = ("ai", "model", "algorithm", "automated", "machine learning",
            "training data", "data center", "chips", "open source",
            "llm", "agent")


def o_ai(h: str) -> bool:
    return any(z in h for z in ZNAKI_AI)


nie_o_ai = [h for h in hasla if not o_ai(h)]
sprawdz("kazde haslo dotyczy AI", not nie_o_ai, nie_o_ai)

# KONKRETNE HASLA Z POPRZEDNIEGO PISMA — te, ktore realnie sprowadzaly posty
# o jedzeniu i opakowaniach. Wymienione z nazwy, zeby nie wrocily „przy okazji".
for zle in ("food labeling", "packaging regulation", "building codes",
            "transport standards", "product recall", "zoning", "hidden fees"):
    sprawdz("  zniknelo: %s" % zle,
            not any(zle in h for h in hasla))

print()
print("=== 2. PULA JEST SZERSZA NIZ JEDNA NISZA ===")
# Samo „AI" w kazdym hasle nie wystarczy: dwadziescia hasel o tym samym daje
# te sama garstke kont. Rewir ma obejmowac takze to, co AI ZMIENIA.
sprawdz("hasel jest wiecej niz bylo (18)", len(hasla) > 18, len(hasla))
for obszar, slowa in (("praca i ludzie", ("work", "hiring", "education",
                                          "healthcare")),
                      ("prawo i wladza", ("regulation", "policy", "copyright",
                                          "privacy", "accountability")),
                      ("pieniadze i sprzet", ("startups", "infrastructure",
                                              "energy", "chips"))):
    sprawdz("  rewir obejmuje: %s" % obszar,
            any(any(s in h for s in slowa) for h in hasla))

print()
print("=== 3. WIECEJ HASEL NA PRZEBIEG ===")
# Trzy z osiemnastu to jedna szosta rewiru na raz — przy zaostrzonej regule
# celow waska pula zamieniala sie w zero kandydatow.
sprawdz("na przebieg idzie wiecej niz 3 hasla",
        config.ILE_HASEL_NA_PRZEBIEG > 3, config.ILE_HASEL_NA_PRZEBIEG)
sprawdz("ale nie cala pula naraz — zostaje co losowac",
        config.ILE_HASEL_NA_PRZEBIEG < len(hasla))

print()
print("=== 4. SZUKA, AZ ZNAJDZIE — I MA GDZIE PRZESTAC ===")
rp = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
sprawdz("przebieg dobiera kolejne partie celow",
        "runda %d szukania" in rp)
sprawdz("warunkiem jest NIEDOBOR wobec planu",
        'len(cele) < na_teraz["komentarze"]' in rp)
sprawdz("jest sufit rund", "config.RUNDY_SZUKANIA_CELOW" in rp)
sprawdz("i sufit stoi w configu, nie w kodzie przebiegu",
        isinstance(getattr(config, "RUNDY_SZUKANIA_CELOW", None), int)
        and config.RUNDY_SZUKANIA_CELOW >= 2,
        getattr(config, "RUNDY_SZUKANIA_CELOW", None))
sprawdz("czas przebiegu nadal przerywa szukanie",
        'zostal_czas("komentarze")' in rp.split("runda %d szukania")[0][-900:])
# BEZ TEGO PETLA MIELILABY TO SAMO. Wyszukiwarka oddaje skonczona pule;
# runda bez ani jednego nowego adresu znaczy, ze kolejna tez nic nie doda.
sprawdz("runda bez nowych adresow konczy szukanie",
        "nie oddaje juz nic nowego" in rp)

print()
print("=== 5. NIE POWTARZAMY TYCH SAMYCH CELOW ===")
sprawdz("nowe partie sa filtrowane przez `widziane`",
        'x["url"] not in widziane' in rp)
sprawdz("i platne publikacje odsiewane takze w kolejnych rundach",
        rp.count("not in platne") >= 2, rp.count("not in platne"))

print()
print("=== 6. ODSTEPY ZOSTAJA NIETKNIETE ===")
# To jest ta czesc, ktorej poprawka NIE MOZE ruszyc. Wlasciciel: „nie chodzi
# o LICZBE, tylko o ODSTEPY" i „nie ma nakurwiac na jednym profilu".
sprawdz("odstep dni na te sama publikacje bez zmian",
        config.ODSTEP_DNI_NA_PUBLIKACJE >= 4,
        config.ODSTEP_DNI_NA_PUBLIKACJE)
sprawdz("rytm miedzy komentarzami nadal obowiazuje",
        'rytm("komentarz", "komentarze", rytm_stanu)' in rp)
dolny, gorny = config.ODSTEPY["komentarz"]
sprawdz("i jest liczony w minutach, nie sekundach",
        dolny >= 240, (dolny, gorny))

print()
print("=== 7. KONTRDOWOD: STARA PULA MUSI TU POLEC ===")
STARA = ("building codes regulation", "food labeling rules",
         "safety standards history", "why prices are set", "product recall")
sprawdz("zadne ze starych hasel nie przechodzi testu na AI",
        not any(o_ai(h) for h in STARA))
sprawdz("a nowe przechodza wszystkie",
        all(o_ai(h) for h in hasla))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
