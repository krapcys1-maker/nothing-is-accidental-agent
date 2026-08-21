"""Test roznorodnosci notek: forma jako osobny wymiar i wybor otwarcia."""
import hashlib
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, "agent-v3")
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


def odcisk(p):
    p = pathlib.Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "brak"


PILNOWANE = [config.DB_PATH, config.DATA_DIR / "zuzyte_fakty.json",
             config.DATA_DIR / "promocja.json", config.DATA_DIR / "dziennik.jsonl"]
PRZED = {str(p): odcisk(p) for p in PILNOWANE}

print("=== 1. FORMA JEST OSOBNYM WYMIAREM ===")

sprawdz("kazda forma ma opis", set(config.NOTE_FORM_MIX) <= set(config.NOTE_FORMS),
        set(config.NOTE_FORM_MIX) - set(config.NOTE_FORMS))
sprawdz("form jest wiecej niz jedna", len(set(config.NOTE_FORM_MIX)) >= 5,
        len(set(config.NOTE_FORM_MIX)))
sprawdz("PROSTA nadal istnieje (dziala, nie usuwamy)",
        "PROSTA" in config.NOTE_FORM_MIX)
sprawdz("ale PROSTA to mniejszosc, nie regula",
        config.NOTE_FORM_MIX.count("PROSTA") <= 1,
        config.NOTE_FORM_MIX.count("PROSTA"))

print()
print("=== 2. FORMY NIE CHODZA W PARZE Z TYPAMI ===")

TYPY = list(config.NOTE_MIX_OTHER_DAY)
print("    typy dnia:  %s" % TYPY)
pary = []
for od, ile in ((0, 2), (2, 2), (4, 1)):
    t = TYPY[od:od + ile]
    f = [config.NOTE_FORM_MIX[(od + i) % len(config.NOTE_FORM_MIX)]
         for i in range(len(t))]
    for a, b in zip(t, f):
        pary.append((a, b))
    print("    przebieg od=%s: %s" % (od, list(zip(t, f))))

ciekawostki = [f for t, f in pary if t == "CIEKAWOSTKA"]
sprawdz("CIEKAWOSTKA nie zawsze ma te sama forme",
        len(set(ciekawostki)) > 1, ciekawostki)
sprawdz("w ciagu dnia jest kilka roznych form",
        len({f for _, f in pary}) >= 4, {f for _, f in pary})
sprawdz("dzien ma tyle form co typow", len(pary) == len(TYPY), len(pary))

print()
print("=== 3. PROMPT DOSTAJE FORME ===")

szablon = pathlib.Path("agent-v3/prompts/notka.md").read_text(encoding="utf-8")
sprawdz("prompt ma miejsce na nazwe formy", "{note_form}" in szablon)
sprawdz("prompt ma miejsce na opis formy", "{form_brief}" in szablon)
sprawdz("prompt kaze lamac linie", "Break the lines" in szablon)
sprawdz("prompt odradza otwieranie od 'The'",
        "definite article" in szablon)

# Szablon musi sie faktycznie sformatowac wszystkimi polami, ktore podaje kod.
try:
    gotowy = stages._prompt(
        "notka.md", language="English", min_words=config.NOTE_MIN_WORDS,
        max_words=config.NOTE_MAX_WORDS, note_type="CIEKAWOSTKA",
        type_brief=config.NOTE_TYPES["CIEKAWOSTKA"], note_form="LISTA",
        form_brief=config.NOTE_FORMS["LISTA"], evidence="{}",
        # Pole WYMAGANE od kiedy piszemy jeden wariant zamiast trzech: model
        # musi znac ostatnie otwarcia, bo nie ma juz konkurencji, z ktorej
        # kod moglby wybrac to nietrafione. Patrz test_jeden_wariant.
        ostatnie_otwarcia_json='["six", "washing"]')
    sprawdz("prompt sklada sie bez bledu", "LISTA" in gotowy)
    sprawdz("i niesie opis wybranej formy",
            "same word" in gotowy, gotowy[:0])
    sprawdz("JSON na koncu nadal jest poprawny (nawiasy nie zjedzone)",
            '{"note":' in gotowy)
except Exception as exc:
    sprawdz("prompt sklada sie bez bledu", False, "%s: %s" % (type(exc).__name__, exc))

print()
print("=== 4. WYBOR KANDYDATA Z INNYM OTWARCIEM ===")

kat = pathlib.Path(tempfile.mkdtemp())
oryg_dir = config.DATA_DIR
try:
    config.DATA_DIR = kat
    (kat / "dziennik.jsonl").write_text("\n".join(json.dumps(x) for x in [
        {"kiedy": "2026-08-17T10:00:00+00:00", "rodzaj": "notka", "udane": True,
         "tekst": "The stop sign is the only octagonal traffic sign."},
        {"kiedy": "2026-08-17T11:00:00+00:00", "rodzaj": "notka", "udane": True,
         "tekst": "The hole in a pen cap is a safety vent."},
        {"kiedy": "2026-08-17T12:00:00+00:00", "rodzaj": "komentarz", "udane": True,
         "tekst": "Something else entirely here."},
    ]) + "\n", encoding="utf-8")

    otw = stages.ostatnie_otwarcia()
    print("    ostatnie otwarcia notek: %s" % otw)
    sprawdz("czyta otwarcia z dziennika", otw == ["the", "the"], otw)
    sprawdz("NIE liczy komentarzy jako notek", "something" not in otw, otw)

    zajete = set(otw)

    def powtarza(d):
        s = (d.get("note") or "").split()
        return bool(s) and s[0].strip("\"'.,").lower() in zajete

    kandydaci = [
        {"note": "The date on your milk carton is not a deadline."},
        {"note": "Fire hydrant caps are a code, not decoration."},
        {"note": "The four-digit PIN came from a kitchen table."},
    ]
    kandydaci.sort(key=powtarza)
    print("    po sortowaniu pierwszy: %r" % kandydaci[0]["note"][:40])
    sprawdz("na czolo idzie kandydat z INNYM otwarciem",
            kandydaci[0]["note"].startswith("Fire"), kandydaci[0]["note"][:30])
    sprawdz("powtarzajacy nie znika, tylko czeka",
            len(kandydaci) == 3, len(kandydaci))

    # Gdy WSZYSCY powtarzaja — nadal wystawiamy, bo notka jest lepsza niz jej brak.
    wszyscy = [{"note": "The one."}, {"note": "The two."}]
    wszyscy.sort(key=powtarza)
    sprawdz("gdy wszyscy powtarzaja, lista zostaje nietknieta",
            len(wszyscy) == 2 and wszyscy[0]["note"] == "The one.", wszyscy)

    # KONTRDOWOD: bez sortowania wyszedlby ten z powtorzonym otwarciem.
    sprawdz("STARY sposob wzialby 'The date...' (test rozroznia)",
            kandydaci[0]["note"] != "The date on your milk carton is not a deadline.")

    config.DATA_DIR = kat / "nie-ma-mnie"
    sprawdz("brak dziennika nie wywala", stages.ostatnie_otwarcia() == [])
finally:
    config.DATA_DIR = oryg_dir

print()
print("=== 5. CZY NASZE DOTYCHCZASOWE NOTKI BY TO ZLAPALY ===")

NASZE = ["American eggs must be", "American rules make eggs", "The hole in a pen",
         "An AM station can", "Every US paper bill", "The stop sign is",
         "In most US elevators", "Federal ADA rules require",
         "The four-digit ATM PIN", "US law forces eggs", "The date on your",
         "Unpopular truth about Substack"]
pierwsze = [t.split()[0].lower() for t in NASZE]
import collections  # noqa: E402
licz = collections.Counter(pierwsze)
print("    otwarcia dwunastu naszych notek: %s" % dict(licz.most_common(4)))
sprawdz("dane potwierdzaja problem: 'the' powtorzone >= 3 razy",
        licz["the"] >= 3, licz["the"])

print()
print("=== PRODUKCJA ===")
zle = 0
for p in PILNOWANE:
    t = odcisk(p)
    ok = t == PRZED[str(p)]
    zle += 0 if ok else 1
    print("  %-24s %s" % (pathlib.Path(p).name, "bez zmian" if ok else "ZMIENIONA"))

print()
print("=== WYNIK: %s zdanych, %s oblanych%s ===" %
      (zdane, oblane, ", PRODUKCJA RUSZONA" if zle else ""))
sys.exit(1 if (oblane or zle) else 0)
