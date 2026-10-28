# -*- coding: utf-8 -*-
"""E23 — maniera komentarza i historia konta (28.10.2026).

PO CO. Analiza 24 tys. komentarzy (`docs/KOMENTARZE_STYL_I_ROZMOWA_2026-10-28.md`) pokazala, ze nasz glos jest
jednolity (pauza w 83% komentarzy, 37% zaczyna od ramy „the part/bit...", humor 0,8%, emocja 0%), a wlasciciel
zazyczyl sobie ciaglosci: konto ma wiedziec, co juz mowilo, i z tego wyciagac wnioski — BEZ wymyslonych przezyc.
E23 losuje po celu: „on" pisze z `komentarz_b.md` + blokiem historii (`historia_konta.py`), „off" z `komentarz.md`.
Test pilnuje: ze ramie wybiera dokladnie jeden prompt i ze znacznik pytania nigdy nie wycieka do modelu; ze
czestosc pytania ustala KOD; ze historia trafia do promptu wylacznie w ramieniu „on", PO tekscie autora; ze
historia pochodzi tylko z naszych opublikowanych wpisow (okno, prog, bez powtorek, bez nieudanych); ze zasady
stylu sa LOGIEM, nie bramka; ze pola dziennika niosa ramie, a stare wpisy nie dostaja nowych pol; oraz ze
`run.py` wola to w obu blokach komentarzy i ocenia odpowiadalnosc PRZED losowaniem swiezosci.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_maniera_komentarza.py
"""
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

KAT = pathlib.Path(tempfile.mkdtemp())
config.uzyj_katalogu_danych(KAT)

import historia_konta   # noqa: E402
import kanal            # noqa: E402
import run              # noqa: E402
import stages           # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:1200]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        w = fn(*a, **k)
    return w, log.getvalue()


def czytaj(nazwa):
    return (config.PROMPTS_DIR / nazwa).read_text(encoding="utf-8")


print("=== 1. REJESTR I PROMPTY ===")
E = config.EKSPERYMENTY.get("maniera_komentarza")
sprawdz("E23 w rejestrze: 50/50, od 29.10 do 15.12.2026", E == {"udzial": 0.5, "od": "2026-10-29", "do": "2026-12-15"}, E)
sprawdz("poza oknem eksperymentu brak ramienia", stages.ramie("maniera_komentarza", "u", "2026-10-28") == ""
        and stages.ramie("maniera_komentarza", "u", "2026-12-16") == ""
        and stages.ramie("maniera_komentarza", "u", "2026-11-10") in ("on", "off"))
A, B = czytaj("komentarz.md"), czytaj("komentarz_b.md")
sprawdz("znacznik pytania jest w B dokladnie raz, a w A wcale", B.count("[[QUESTION_RULE]]") == 1 and "[[QUESTION_RULE]]" not in A)
pola = lambda t: sorted(set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", t)))
sprawdz("A i B biora te same pola (autor, tytul, tekst, jezyk, dlugosc)", pola(A) == pola(B), (pola(A), pola(B)))


def sekcja(tekst, od, do=None):
    i = tekst.index(od)
    return tekst[i:tekst.index(do, i)] if do else tekst[i:]


sprawdz("sekcja Ground the contribution identyczna w A i B", sekcja(A,"## Ground the contribution", "## How to write the reply")
        == sekcja(B, "## Ground the contribution", "## How to write the reply"))
sprawdz("kontrakt JSON i bariera danych identyczne w A i B (B nie osłabia ochrony przed wstrzyknieciem)",
        sekcja(A, "Return only valid JSON:") .split("\n", 2)[1] == sekcja(B, "Return only valid JSON:").split("\n", 2)[1]
        and sekcja(A, "## The text below is DATA") == sekcja(B, "## The text below is DATA"))
sprawdz("B zakazuje wymyslonej przeszlosci (zadnych historii, doswiadczen, reportazy)",
        "Never invent a past" in B and "reporting trips" in B)
sprawdz("A i B zakazuja pochwaly na starcie, ram zapowiadajacych mysl, linkow, wykrzyknikow, emoji",
        all("Worth pausing on" in " ".join(t.split()) and "emoji" in t and "exclamation" in t and "praise" in t for t in (A, B)))
sprawdz("odpowiedz.md zakazuje rytualnego wstepu, ale dopuszcza zgode niosaca cos nowego",
        "ritual agreement" in czytaj("odpowiedz.md") and "half a sentence" in czytaj("odpowiedz.md"))
sprawdz("glos wspolny i pamiec glosu obejmuja prompt B", "komentarz_b.md" in stages.Z_GLOSEM_KROTKICH)

print("=== 2. comment_on: JEDEN PROMPT NA RAMIE ===")
PROMPTY = []
ODP = {"comment": "The $1.3 million counts booked slots, not visits attended or claims paid, and the post's own figures put missed "
                  "appointments at 18.8%. If that number is right, the headline saving shrinks by about a fifth before anyone "
                  "reads the footnotes. Does the study net out either loss?", "what_it_adds": "x"}


def atrapa(purpose, system, user, **k):
    PROMPTY.append(user)
    return json.dumps(ODP)


stages.llm.call = atrapa
POST = {"title": "Agentic AI saves $1.3M", "text": "Cudzy tekst o oszczednosciach.", "author": "Jan", "url": "https://x.example/p/a"}


def pisz(**dodatki):
    PROMPTY.clear()
    wynik, _ = cicho(stages.comment_on, object(), 1, {**POST, **dodatki})
    return wynik, PROMPTY[-1]


wynik, p = pisz()
sprawdz("bez pola maniera: prompt A, dlugosc 40-70, zadnego znacznika", "Tone illustration only" in p and "recognisable voice" not in p
        and "40–70" in p and "[[QUESTION_RULE]]" not in p)
sprawdz("A ignoruje historie, nawet podana (historia stoi tylko za ramieniem on)",
        "What this account has already said" not in pisz(historia="## What this account has already said X")[1])
wynik, p = pisz(maniera="off", historia="## What this account has already said X")
sprawdz("maniera=off to prompt A", "recognisable voice" not in p and "What this account has already said" not in p)
wynik, p_tak = pisz(maniera="on", pytanie=True)
sprawdz("maniera=on: prompt B z regula zakoncz-pytaniem", "recognisable voice" in p_tak and stages.MANIERA_PYTANIE_TAK in p_tak
        and stages.MANIERA_PYTANIE_NIE not in p_tak and "[[QUESTION_RULE]]" not in p_tak and "40–70" in p_tak)
wynik, p_nie = pisz(maniera="on", pytanie=False)
sprawdz("maniera=on bez pytania: regula zakoncz-na-tezie", stages.MANIERA_PYTANIE_NIE in p_nie and stages.MANIERA_PYTANIE_TAK not in p_nie)
wynik, p_nie2 = pisz(maniera="on")
sprawdz("maniera=on bez pola pytanie → bez pytania (bezpieczny domysl)", stages.MANIERA_PYTANIE_NIE in p_nie2)
HIST = "## What this account has already said (our own published record)\n- 2026-10-20, our note: \"x\"\nUse it..."
wynik, p_h = pisz(maniera="on", historia=HIST)
sprawdz("historia dopisana na KONCU promptu, po tekscie autora, i tylko raz",
        p_h.count("What this account has already said (our own published record)") == 1
        and p_h.index("The text under examination") < p_h.index("What this account has already said (our own")
        and p_h.rstrip().endswith("Use it..."))
sprawdz("pamiec rozmowcy dalej dziala obok historii", "Earlier contact" in pisz(maniera="on", historia=HIST, pamiec="## Earlier contact with this person")[1])
sprawdz("komentarz wychodzi (kandydat z tekstem i safe_to_post)", any(c.get("comment") and c.get("safe_to_post") for c in wynik["candidates"]))

print("=== 3. ZASADY STYLU: LOG, NIE BRAMKA ===")
sprawdz("komentarz zgodny z zasadami → brak naruszen", stages.zasady_stylu(ODP["comment"]) == [], stages.zasady_stylu(ODP["comment"]))
CZYSTO = "The $1.3 million counts booked slots, not visits attended or claims paid, and the post's own figures put missed appointments at 18.8%."
sprawdz("pochwala na starcie", "pochwala_na_start" in stages.zasady_stylu("Good point. " + CZYSTO))
sprawdz("rytualne Agreed na starcie", "pochwala_na_start" in stages.zasady_stylu("Agreed — " + CZYSTO))
sprawdz("zgoda niosaca tresc w srodku zdania NIE jest naruszeniem", "pochwala_na_start" not in stages.zasady_stylu("I'd say " + CZYSTO + " Agreed, but the cost sits elsewhere."))
for nazwa, tekst in (("rama The part worth", "The part worth noting is that " + CZYSTO),
                     ("rama Worth pausing on", "Worth pausing on the fact that " + CZYSTO),
                     ("rama What's easy to miss", "What's easy to miss is that " + CZYSTO),
                     ("rama The word doing quiet work", "The word doing quiet work here is hosts. " + CZYSTO)):
    sprawdz(nazwa, "rama_otwarcia" in stages.zasady_stylu(tekst), stages.zasady_stylu(tekst))
sprawdz("zwykle The $1.3 million... NIE jest rama (zakazana jest rama, nie slowo The)", "rama_otwarcia" not in stages.zasady_stylu(CZYSTO))
sprawdz("link, wykrzyknik, emoji, za krotki", set(stages.zasady_stylu("See https://a.example/x now! \U0001F680")) == {"link", "wykrzyknik", "emoji", "za_krotki"},
        stages.zasady_stylu("See https://a.example/x now! \U0001F680"))
ODP["comment"] = ("Good point! " + CZYSTO + " If that number is right, the headline saving shrinks by about a fifth before "
                  "anyone reads the footnotes. Does the study net out either loss?")
wynik, log = cicho(stages.comment_on, object(), 1, POST)
k = wynik["candidates"][0]
sprawdz("naruszenie jest zapisane w kandydacie i w logu, a komentarz i tak idzie",
        set(k.get("zasady_stylu") or []) == {"pochwala_na_start", "wykrzyknik"} and k.get("safe_to_post") and "zasady stylu" in log, (k.get("zasady_stylu"), log[-300:]))

print("=== 4. HISTORIA KONTA ===")
TERAZ = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
dz = KAT / "dziennik_historia.jsonl"


def wpis(dni, rodzaj="notka", tekst="", udane=True, tytul=None):
    d = {"kiedy": (TERAZ - timedelta(days=dni)).isoformat(), "rodzaj": rodzaj, "udane": udane}
    if rodzaj == "artykul":
        d["tytul"] = tytul or tekst
    else:
        d["tekst"] = tekst
    return d


CEL = "Moonshot released Kimi K3.1 with open weights on 4 November, and its cyber index scores 64% on Artificial Analysis."
bliska = "Moonshot launched Kimi K3.1 Pro and promised the weights by 4 November; Artificial Analysis puts its cyber index at 64%."
srednia = "Kimi K3.1 weights arrive 4 November, which matters for any open model's cyber capability."
wiersze = [
    wpis(30, tekst=bliska),
    wpis(5, tekst=srednia),
    wpis(2, rodzaj="artykul", tytul="Kimi K3.1 Pro: open weights, cyber index 64%, and what 4 November changes"),
    wpis(70, tekst=bliska + " (stara wersja)"),                            # poza oknem 60 dni
    wpis(3, tekst="Totally unrelated note about housing prices in Lisbon and rent caps."),   # ponizej progu
    wpis(4, tekst=bliska, udane=False),                                    # nieudana publikacja
    wpis(6, rodzaj="restack", tekst=bliska),                               # nie jest naszym wpisem
    wpis(1, tekst=CEL),                                                    # ta sama tresc co cel (ponowny przebieg)
]
dz.write_bytes(("\n".join(json.dumps(w, ensure_ascii=False) for w in wiersze) + "\n").encode("utf-8"))
wyn = historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz)
sprawdz("wybiera najwyzej HISTORIA_KONTA_WPISOW (2) najbardziej zwiazane, od najstarszego",
        len(wyn) == config.HISTORIA_KONTA_WPISOW == 2 and wyn[0]["kiedy"] < wyn[1]["kiedy"], [(w["rodzaj"], w["wynik"]) for w in wyn])
sprawdz("nie bierze wpisow poza oknem, nieudanych, restackow, tej samej tresci ani ponizej progu",
        all("stara wersja" not in w["tekst"] and "Lisbon" not in w["tekst"] and w["tekst"] != CEL for w in wyn)
        and len({w["tekst"] for w in wyn}) == len(wyn))
b, n = historia_konta.blok(CEL, teraz=TERAZ, plik=dz)
sprawdz("blok: naglowek, daty ISO, rodzaj wpisu, zasada uzycia na koncu", b.startswith("## What this account has already said")
        and n == 2 and re.search(r"- 2026-10-\d\d, our (note|article): \"", b) and b.rstrip().endswith("Don't quote the record at length."), b[:600])
sprawdz("zasada uzycia zabrania wymyslania przeszlosci", "never claim personal experience" in b and "Only what is written above happened" in b)
b0, n0 = historia_konta.blok("Zupelnie inny temat: wyniki ligi w pilce noznej i transfery.", teraz=TERAZ, plik=dz)
sprawdz("brak powiazanych wpisow → pusty blok i zero", (b0, n0) == ("", 0))
sprawdz("brak pliku lub pusty tekst → pusty blok, bez wyjatku",
        historia_konta.blok(CEL, teraz=TERAZ, plik=KAT / "nie_ma.jsonl") == ("", 0) and historia_konta.blok("", teraz=TERAZ, plik=dz) == ("", 0))
dlugi = "Moonshot Kimi K3.1 weights November cyber index Artificial Analysis open " * 30
dz2 = KAT / "dziennik_dlugi.jsonl"
dz2.write_bytes(("\n".join(json.dumps(wpis(i + 1, tekst=dlugi), ensure_ascii=False) for i in range(3))).encode())
stare = (config.HISTORIA_KONTA_ZNAKI, config.HISTORIA_KONTA_BLOK_ZNAKOW)
config.HISTORIA_KONTA_BLOK_ZNAKOW = 1300
bd, nd = historia_konta.blok(CEL, teraz=TERAZ, plik=dz2)
config.HISTORIA_KONTA_ZNAKI, config.HISTORIA_KONTA_BLOK_ZNAKOW = stare
sprawdz("dlugie wpisy skracane, a zasada uzycia ZOSTAJE (skracamy wpisy, nie caly blok)",
        bd.rstrip().endswith("Don't quote the record at length.") and len(bd) <= 1300 + 60 and "…" in bd, (len(bd), bd[-120:]))
dz3 = KAT / "dziennik_u2028.jsonl"
linia = json.dumps(wpis(3, tekst="Kimi K3.1 weights  arrive 4 November and the cyber index is 64% on Artificial Analysis."), ensure_ascii=False)
dz3.write_bytes(linia.encode("utf-8") + b"\n" + b"\xff\xfe zly bajt\n"
                + json.dumps(wpis(4, tekst=srednia), ensure_ascii=False).encode("utf-8") + b"\n")
sprawdz("wpis z U+2028 i zly bajt w innym wierszu nie wylaczaja historii", len(historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz3)) == 2,
        [w["tekst"][:30] for w in historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz3)])

print("=== 4b. POWIAZANIE: LUZNE SKOJARZENIA NIE PRZECHODZA (zmierzone 28.10: prosta miara dawala historie 117 razy na 120 celow) ===")
OGOLNE = [
    "AI agents keep getting access to systems nobody approved, and the model vendors say the fix is better permissions for agents.",
    "Every AI model release now claims agents can finish longer tasks, but the benchmark only counts tasks that models already pass.",
    "OpenAI and Anthropic disagree about how AI agents should be tested before they touch customer data in production systems.",
    "A new AI model scores higher on the agents benchmark, yet the agents still fail on tasks that need access to real systems.",
    "Companies deploying AI agents need permissions, logs and review, because an agent with access can act without a human approving.",
    "The AI industry talks about agents as employees, but the model behind an agent has no accountability for what the system does.",
] * 12                                                                         # ~72 wpisow o „agentach i AI": dokladnie ten szum
SZUM = "\n".join(json.dumps(wpis(1 + (i % 40), tekst=t + " Variant %d." % i), ensure_ascii=False) for i, t in enumerate(OGOLNE))
PRAWDZIWA = ("Police in Florida read a woman's private Claude diary after Anthropic flagged her chats and handed them over, "
             "the Slashdot report says, and the company's own policy allows reporting content that suggests violence.")
dz4 = KAT / "dziennik_szum.jsonl"
dz4.write_bytes((SZUM + "\n" + json.dumps(wpis(3, tekst=PRAWDZIWA), ensure_ascii=False) + "\n").encode("utf-8"))
CEL_OGOLNY = ("Banks found AI agents inside customer accounts that nobody approved. The agents had access through delegated permissions, "
              "the model vendors point to better permissions for agents, and regulators want logs and human review before an agent "
              "can act on production systems with customer data. " * 3)
w_ogolny = historia_konta.powiazane(CEL_OGOLNY, teraz=TERAZ, plik=dz4)
sprawdz("tekst o agentach i AI nie dostaje historii z notek o agentach i AI (szum tematyczny)", w_ogolny == [], [(w["wynik"], w["tekst"][:60]) for w in w_ogolny])
CEL_PRAWDZIWY = ("Anthropic told the police about a Florida woman's Claude chats, Slashdot reports: she used the assistant like a diary, "
                 "and the company's usage policy lets it report content suggesting violence.")
w_prawdziwy = historia_konta.powiazane(CEL_PRAWDZIWY, teraz=TERAZ, plik=dz4)
sprawdz("ta sama historia (nazwy, szczegoly) przechodzi, i to jako jedyna", len(w_prawdziwy) == 1 and "Florida" in w_prawdziwy[0]["tekst"]
        and w_prawdziwy[0]["wynik"] >= config.HISTORIA_KONTA_MIN_PODOBIENSTWA, [(w["wynik"], w["tekst"][:50]) for w in w_prawdziwy])
sprawdz("prog: cosinus >= 0,12 i co najmniej 2 wspolne rzadkie terminy",
        config.HISTORIA_KONTA_MIN_PODOBIENSTWA == 0.12 and config.HISTORIA_KONTA_MIN_RZADKICH == 2)
stare_p = config.HISTORIA_KONTA_MIN_RZADKICH
config.HISTORIA_KONTA_MIN_RZADKICH = 999
sprawdz("warunek rzadkich terminow jest osobnym wymogiem (przy absurdalnym progu nic nie przechodzi)",
        historia_konta.powiazane(CEL_PRAWDZIWY, teraz=TERAZ, plik=dz4) == [])
config.HISTORIA_KONTA_MIN_RZADKICH = stare_p
stare_c = config.HISTORIA_KONTA_MIN_PODOBIENSTWA
config.HISTORIA_KONTA_MIN_PODOBIENSTWA = 0.99
sprawdz("prog cosinusa jest osobnym wymogiem (przy 0,99 nic nie przechodzi)",
        historia_konta.powiazane(CEL_PRAWDZIWY, teraz=TERAZ, plik=dz4) == [])
config.HISTORIA_KONTA_MIN_PODOBIENSTWA = stare_c

print("=== 5. run.dane_maniery ===")
ORYG = dict(config.EKSPERYMENTY)
config.EKSPERYMENTY = {"maniera_komentarza": {"udzial": 1.0, "od": "2026-01-01", "do": "2099-12-31"}}
cel = {"url": "https://x.example/p/a", "uchwyt": "alice", "_e21": {"tekst": "", "ramie": "", "wymian": 0, "znaki": 0}}
dz_prod = config.DATA_DIR / "dziennik.jsonl"
dz_prod.write_bytes(dz.read_bytes())
d, log = cicho(run.dane_maniery, cel, CEL)
sprawdz("ramie on: maniera, pytanie (bool) i historia z dziennika", d.get("maniera") == "on" and isinstance(d.get("pytanie"), bool)
        and d.get("historia", "").startswith("## What this account has already said") and cel["_maniera"] == "on" and cel["_historia_n"] == 2, d.keys())
sprawdz("kontekst zapisuje ramie i liczby", cel["_maniera_pytanie"] == d["pytanie"] and "[maniera] E23 on" in log)
config.EKSPERYMENTY = {"maniera_komentarza": {"udzial": 0.0, "od": "2026-01-01", "do": "2099-12-31"}}
cel2 = {"url": "https://x.example/p/a", "uchwyt": "alice"}
sprawdz("ramie off: nic nie dopisuje, ale zapisuje ramie", run.dane_maniery(cel2, CEL) == {} and cel2["_maniera"] == "off"
        and "_historia_n" not in cel2 and "_maniera_pytanie" not in cel2)
config.EKSPERYMENTY = {}
cel3 = {"url": "https://x.example/p/a"}
sprawdz("poza eksperymentem: nic nie dopisuje i nie zapisuje ramienia do dziennika", run.dane_maniery(cel3, CEL) == {} and cel3["_maniera"] == ""
        and "maniera_komentarza" not in (run.ramiona_komentarza(cel3, "artykul", False).get("eksperymenty") or {}))
config.EKSPERYMENTY = {"maniera_komentarza": {"udzial": 1.0, "od": "2026-01-01", "do": "2099-12-31"}}
with contextlib.redirect_stdout(io.StringIO()):
    _pytan = [run.dane_maniery({"url": "https://h%d.example/p/q" % i}, "zupelnie inny temat o pilce")["pytanie"] for i in range(600)]
    _stale = run.dane_maniery({"url": "https://h7.example/p/q"}, "t")["pytanie"] == run.dane_maniery({"url": "https://h7.example/p/q"}, "t")["pytanie"]
sprawdz("czestosc pytania ustala kod: ok. 25% celow, stale dla celu", 0.17 < sum(_pytan) / 600 < 0.33 and _stale, sum(_pytan) / 600)
orig_blok = historia_konta.blok
historia_konta.blok = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dziennik padl"))
d, log = cicho(run.dane_maniery, {"url": "https://x.example/p/a"}, CEL)
historia_konta.blok = orig_blok
sprawdz("awaria historii nie zatrzymuje komentarza: ramie on bez historii", d.get("maniera") == "on" and "historia" not in d and "nie zbudowalem" in log, (d, log))
orig_pam = getattr(stages, "pamiec_rozmowcy")
stages.pamiec_rozmowcy = lambda uchwyt, teraz=None: {"wymian": 2, "tekst": "## Earlier contact with this person\n- x"}
cel4 = {"url": "https://x.example/p/b", "uchwyt": "alice", "_e21": {"tekst": "", "ramie": "", "wymian": 0, "znaki": 0}}
d4 = cicho(run.dane_maniery, cel4, CEL)[0]
cel5 = {"url": "https://x.example/p/c", "uchwyt": "alice", "_e21": {"tekst": "JUZ BYLA", "ramie": "on", "wymian": 1, "znaki": 8}}
d5 = cicho(run.dane_maniery, cel5, CEL)[0]
cel6 = {"url": "https://x.example/p/d", "_e21": {"tekst": "", "ramie": "", "wymian": 0, "znaki": 0}}
d6 = cicho(run.dane_maniery, cel6, CEL)[0]
stages.pamiec_rozmowcy = orig_pam
sprawdz("ramie on dolacza pamiec rozmowcy, gdy E21 jej nie dala; nie nadpisuje tej od E21; bez uchwytu — nic",
        d4.get("pamiec", "").startswith("## Earlier contact") and cel4["_pamiec_b"] == 2 and "pamiec" not in d5 and "pamiec" not in d6, (d4, d5, d6))
config.EKSPERYMENTY = ORYG

print("=== 6. POLA DZIENNIKA ===")
sprawdz("cel bez E23 — zadnych nowych pol (stare wpisy, atrapy)", run.ramiona_komentarza({"_e15": "on"}, "notka", False)
        == {"pod": "notka", "eksperymenty": {"swiezosc_celu": "on"}})
c = {"_maniera": "on", "_maniera_pytanie": True, "_historia_n": 2, "_pamiec_b": 3,
     "_odp_autora": {"wynik": 0.5, "n": 6, "klasa": "ok"}}
r = run.ramiona_komentarza(c, "artykul", False)
sprawdz("ramie w `eksperymenty`, reszta jako pola obok",
        r["eksperymenty"] == {"maniera_komentarza": "on"} and r["maniera_pytanie"] is True and r["historia_n"] == 2
        and r["pamiec_b_wymian"] == 3 and r["autor_odp"] == 0.5 and r["autor_odp_klasa"] == "ok" and r["autor_odp_n"] == 6, r)
sprawdz("ramie off tez sie zapisuje; zero wpisow historii tez",
        run.ramiona_komentarza({"_maniera": "off"}, "notka", False)["eksperymenty"] == {"maniera_komentarza": "off"}
        and run.ramiona_komentarza({"_maniera": "on", "_historia_n": 0}, "notka", False)["historia_n"] == 0)

print("=== 7. WPIECIE W run.py I kanal.py ===")
_RUN = "\n".join(x for x in pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))
_kom = _RUN[_RUN.index("    def komentarze() -> None:"):_RUN.index("    def dyskusje(")]
_dys = _RUN[_RUN.index("    def dyskusje("):_RUN.index("    def obserwuj() -> None:")]
sprawdz("oba bloki komentarzy podaja do comment_on dane ramienia E23",
        '**dane_maniery(cel, "%s %s" % (strony[0].get("title", ""), strony[0].get("text", "")))' in _kom and '**dane_maniery(cel, cel.get("opis", ""))' in _dys)
sprawdz("odpowiadalnosc autora liczona PO sicie limitu autora, a PRZED losowaniem swiezosci (obie sciezki)",
        _kom.index("limit_autorow.odsiej(cele)") < _kom.index("_wedlug_odpowiadalnosci(kanal, cele, notki=False)") < _kom.index("uloz_wedlug_swiezosci(")
        and _dys.index("_zywe_najpierw(kanal, limit_autorow.odsiej(cele))") < _dys.index("_wedlug_odpowiadalnosci(kanal, cele, notki=True)") < _dys.index("uloz_wedlug_swiezosci("))
sprawdz("atrapa kanalu bez funkcji = kolejnosc bez zmian (i bez sieci)", run._wedlug_odpowiadalnosci(object(), [1, 2], True) == [1, 2])
import odpowiadalnosc   # noqa: E402
orig = odpowiadalnosc.wedlug_odpowiadalnosci
odpowiadalnosc.wedlug_odpowiadalnosci = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("siec"))
w, log = cicho(kanal.wedlug_odpowiadalnosci, [{"url": "u"}], False)
odpowiadalnosc.wedlug_odpowiadalnosci = orig
sprawdz("awaria oceny odpowiadalnosci zostawia kolejnosc i tylko ostrzega", w == [{"url": "u"}] and "niedostepna" in log, (w, log))
sprawdz("progi wieku celow: artykul 3 dni, notka 24 h", config.MAKS_WIEK_POSTA_DO_KOMENTARZA_DNI == 3 and config.MAKS_WIEK_NOTKI_DO_KOMENTARZA_H == 24)

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
