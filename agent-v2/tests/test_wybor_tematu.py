"""Caly lancuch wyboru tematu: skaut -> nasycenie -> watki -> pick_topic.

DLACZEGO. Skaut oddal dwanascie tematow i siedem z nich bylo kanonem
internetowego mythbustingu: zraszacze, ktore nie odpalaja wszystkie naraz,
chusteczki „flushable", karta hotelowa przy telefonie, mydlo antybakteryjne,
maszyna z pluszakami, data waznosci na lekach, wodoodpornosc telefonu.
O kazdym z nich sa tysiace tekstow.

AUDYT WYKAZAL TRZY PRZYCZYNY, wszystkie w kodzie, nie w modelu:

1. `pick_topic` sortowal po `ma_przekonanie` jako PIERWSZYM kluczu — a temat
   oklepany ma z definicji najostrzejsze „wszyscy zakladaja", bo dokladnie
   dlatego zostal oklepany. Ranking wybieral wiec cliche z KONSTRUKCJI.
2. `ma_stawke` w ogole nie bylo w tym rankingu. Skaut stawial systemy pod proba
   na czele, a wybor tematu spychal je na sam dol — piec dobrych tematow
   z przebiegu 20 sierpnia nie zostaloby wybranych NIGDY.
3. Skaut liczyl siedem ocen (w tym `originality`), ktorych NIE CZYTALA ani jedna
   linia kodu. Samoocena i tak dryfuje do gornej granicy, wiec nie byla warta
   naprawiania — zostala usunieta i zastapiona faktami do sprawdzenia.

Zamiast oceny: model wymienia, co jego zdaniem JUZ o tym napisano. Uzywamy jego
pamieci przeciw niemu — dostepnosc jest odwrotnoscia sygnalu, ktorego szukamy.
"""
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402
import stages   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def przetworz(topics):
    """Odtwarza petle ze `scout` — te sama, ktora liczy nosnosc i nasycenie."""
    for t in topics:
        wiara = str(t.get("broken_belief") or "").strip()
        t["ma_przekonanie"] = len(wiara.split()) >= 5
        moment = str(t.get("the_moment") or "").strip()
        wynik = str(t.get("open_outcome") or "").strip()
        zapis = str(t.get("governing_record") or "").strip()
        t["ma_stawke"] = (len(moment.split()) >= 4 and len(wynik.split()) >= 4
                          and len(zapis.split()) >= 3)
        t["nosny"] = bool(t["ma_przekonanie"] or t["ma_stawke"])
        juz = t.get("already_written")
        t["ile_juz_napisano"] = len(juz) if isinstance(juz, list) else 0
        t["nasycony"] = t["ile_juz_napisano"] >= config.NASYCENIE_OD_ILU
        w = t.get("threads")
        t["ile_watkow"] = len(w) if isinstance(w, list) else 0
    topics.sort(key=lambda t: (not t["nosny"], t["nasycony"], -t["ile_watkow"]))
    return topics


# --- PRAWDZIWE tematy z przebiegu 20 sierpnia, nie wymyslone -----------------
CLICHE = {
    "title": "The Wipe That Says Flushable", "kind": "BROKEN_BELIEF",
    "broken_belief": "Everyone assumes wipes labelled flushable break down in "
                     "water the way toilet paper does.",
    "already_written": ["utility companies on fatbergs",
                        "consumer testing of flushable claims",
                        "city sewer department warnings"],
    "threads": ["what the label legally means"],
}
CLICHE2 = {
    "title": "The Soap That Says Antibacterial", "kind": "BROKEN_BELIEF",
    "broken_belief": "Everyone assumes antibacterial soap kills more germs than plain.",
    "already_written": ["regulator ban coverage", "handwashing guidance pieces"],
    "threads": ["what the regulator actually banned"],
}
SWIEZY = {
    "title": "The Broken Machine at the Polling Place", "kind": "SYSTEM_UNDER_TEST",
    "the_moment": "a voter arrives and the machines are down",
    "open_outcome": "what happens to my vote if the machine fails while I am using it",
    "governing_record": "election statutes and provisional ballot rules",
    "already_written": [],
    "threads": ["what happens to a vote already cast",
                "who may authorise paper ballots",
                "how long a polling place may stay shut",
                "what happens to the count afterwards"],
}
SWIEZY2 = {
    "title": "The Bet Cut Short", "kind": "SYSTEM_UNDER_TEST",
    "the_moment": "a match you have money on is stopped midway",
    "open_outcome": "do I get my stake back or is it settled on the score so far",
    "governing_record": "sportsbook house rules and regulator codes",
    "already_written": [],
    "threads": ["when a stake is returned", "who decides a match is abandoned"],
}

print("=== 1. NASYCENIE: PAMIEC MODELU UZYTA PRZECIW NIEMU ===")
t = przetworz([dict(CLICHE), dict(SWIEZY)])
sprawdz("próg nasycenia to 2", config.NASYCENIE_OD_ILU == 2, config.NASYCENIE_OD_ILU)
c = next(x for x in t if x["title"].startswith("The Wipe"))
s = next(x for x in t if x["title"].startswith("The Broken"))
sprawdz("cliché rozpoznane jako nasycone", c["nasycony"] is True, c["ile_juz_napisano"])
sprawdz("świeży temat nie jest nasycony", s["nasycony"] is False)
sprawdz("świeży idzie PRZED cliché", t[0]["title"].startswith("The Broken"),
        [x["title"][:26] for x in t])
# KONTRDOWOD: jeden przypomniany tekst zdarza sie przy kazdym istniejacym
# temacie. Prog jeden zabilby wszystko.
jeden = przetworz([dict(CLICHE, already_written=["jakis tekst"])])[0]
sprawdz("jeden znany tekst NIE wystarcza", jeden["nasycony"] is False)

print()
print("=== 2. WATKI: JEDEN TEMAT NA PIEC ARTYKULOW BIJE PIEC NA JEDEN ===")
sprawdz("cliché ma jeden wątek", c["ile_watkow"] == 1, c["ile_watkow"])
sprawdz("świeży ma cztery", s["ile_watkow"] == 4, s["ile_watkow"])
t = przetworz([dict(SWIEZY2), dict(SWIEZY)])
sprawdz("przy równym nasyceniu wygrywa więcej wątków",
        t[0]["title"].startswith("The Broken"), [x["title"][:22] for x in t])

print()
print("=== 3. pick_topic — TU SIEDZIAL GLOWNY BLAD ===")
TEMATY = przetworz([dict(CLICHE), dict(CLICHE2), dict(SWIEZY)])
# Wykonalnosc ocenia wszystkie tak samo — chodzi wylacznie o ranking tematow.
OCENY = [{"index": i, "feasible": True, "confidence": 0.8,
          "expected_primary_sources": 3, "depth": "RICH"}
         for i in range(len(TEMATY))]
wybrany, _ = stages.pick_topic(TEMATY, OCENY)
print("    kolejność po przetworzeniu: %s" % [x["title"][:30] for x in TEMATY])
print("    wybrany: %s" % wybrany["title"])
sprawdz("wybiera świeży system, nie cliché",
        wybrany["title"].startswith("The Broken"), wybrany["title"])

# KONTRDOWOD 1: stary ranking sortowal po ma_przekonanie jako pierwszym kluczu.
# Cliche ma przekonanie, system pod proba NIE MA — wiec stary klucz wybralby
# cliche. Bez tego sprawdzenia test nie odroznia wersji.
po_staremu = sorted(OCENY, key=lambda a: (
    int(bool(TEMATY[a["index"]].get("ma_przekonanie"))),
    a["confidence"]), reverse=True)
stary_wybor = TEMATY[po_staremu[0]["index"]]
sprawdz("STARY ranking wziąłby cliché (test rozróżnia)",
        stary_wybor["title"].startswith("The Wipe")
        or stary_wybor["title"].startswith("The Soap"), stary_wybor["title"])
sprawdz("i NIE wziąłby systemu pod próbą",
        not stary_wybor["title"].startswith("The Broken"), stary_wybor["title"])

# KONTRDOWOD 2: temat bez niczego nie moze wygrac z niczym.
PUSTY = przetworz([{"title": "Nic", "kind": "BROKEN_BELIEF", "broken_belief": "x",
                    "already_written": [], "threads": []}])[0]
razem = przetworz([dict(CLICHE), PUSTY])
sprawdz("nienośny ląduje na końcu mimo zerowego nasycenia",
        razem[-1]["title"] == "Nic", [x["title"][:20] for x in razem])

print()
print("=== 4. NOSNOSC NADAL BIJE SWIEZOSC ===")
# Swiezy, ale nienosny temat nie moze wyprzedzic nosnego i oklepanego —
# lepiej napisac znany temat dobrze niz nieznany bez luki i bez stawki.
t = przetworz([dict(CLICHE), dict(PUSTY, already_written=[], threads=[])])
sprawdz("nośne cliché przed nienośną nowością", t[0]["title"].startswith("The Wipe"),
        [x["title"][:20] for x in t])

print()
print("=== 5. SIEDEM MARTWYCH OCEN USUNIETYCH ===")
p = (config.PROMPTS_DIR / "skaut.md").read_text(encoding="utf-8")
plaski = " ".join(p.split())
for martwa in ("score_breakdown", "visual_potential", "discussion_potential",
               "non_obvious", "universality"):
    sprawdz("prompt nie prosi już o %s" % martwa, martwa not in plaski)
sprawdz("i mówi wprost, czemu je usunięto",
        "Nothing ever read them" in plaski)
zrodlo = open("agent-v2/stages.py", encoding="utf-8").read()
sprawdz("kod nadal ich nie czyta (bo ich nie ma)",
        "score_breakdown" not in zrodlo)

print()
print("=== 6. SKAUT WIE, ZE PIERWSZY POMYSL JEST NAJGORSZY ===")
sprawdz("prompt nazywa gatunek po imieniu", "It is a **genre**" in plaski)
sprawdz("wymienia kanon, ktory ma omijać",
        all(x in plaski for x in ("sprinklers", "flushable", "antibacterial")))
sprawdz("tłumaczy mechanizm dostępności",
        "Availability is the opposite of the signal" in plaski)
sprawdz("ostrzega przed własną płynnością",
        "if the\ntopic assembled itself instantly" in p
        or "topic assembled itself instantly" in plaski)
sprawdz("wymaga pola already_written", "already_written" in plaski)
sprawdz("wymaga pola threads", "`threads`" in plaski)
sprawdz("zakazuje fałszowania w OBIE strony",
        "Do not fake this in either direction" in plaski)

print()
print("=== 7. KOTWICA TO JUZ NIE TYLKO PRZEDMIOT ===")
sprawdz("dopuszcza procedurę, przez którą przeszedł czytelnik",
        "a procedure the reader has been put through" in plaski)
sprawdz("dopuszcza moment, który wszyscy widzieli",
        "a moment everybody watched happen" in plaski)
sprawdz("i mówi, że przedmiot jest najbardziej wyczerpany",
        "the most exhausted" in plaski)

print()
print("=== 8. GLEBOKOSC LICZY SIE TEZ W PIONIE ===")
wyk = (config.PROMPTS_DIR / "wykonalnosc.md").read_text(encoding="utf-8")
plaski_w = " ".join(wyk.split())
sprawdz("RICH da się osiągnąć samymi wątkami",
        "three or more separate questions" in plaski_w)
sprawdz("prompt nazywa starą wadę wprost",
        "Depth was judged here only sideways" in plaski_w)
sprawdz("i daje przykład, który wcześniej wypadał jako THIN",
        "cannot agree" in plaski_w)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
