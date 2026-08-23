"""Ustawienia, ktore wygladaja jak decyzje, a nie robia nic.

Trzy usterki jednej rodziny, wszystkie potwierdzone na produkcji:

1. EFFORT ma szesc wpisow i przez trzydziesci dni dotarl do API DOKLADNIE
   JEDEN. Cztery etapy chodza na DeepSeeku, ktory tego pokretla nie czyta,
   a piaty (`forma`) nie wywolal sie ani razu. Wpis czyta sie jak decyzja
   o kosztach i nie robi nic — i nie widac tego nigdzie.

2. Limit MIESIECZNY byl egzekwowany twardym wyjatkiem przed kazdym platnym
   wywolaniem, ale nikt o nim nie ostrzegal. Pierwszym sygnalem bylby agent
   padajacy w polowie artykulu: research oplacony, tekstu nie ma.

3. Okladka powstawala WEWNATRZ galezi `--wyslij`. Kazdy przebieg bez
   publikacji zapisywal artykul bez okladki, a sciezka graficzna sprawdzala
   sie wylacznie na zywo, za prawdziwe pieniadze. Dlatego okladka zgubiona
   przez usterke zapisu wywolan wyszla na jaw dopiero po fakcie.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


run_src = pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8")
llm_src = pathlib.Path("agent-v2/llm.py").read_text(encoding="utf-8")
alarm_src = pathlib.Path("agent-v2/alarm.py").read_text(encoding="utf-8")

print("=== 1. MARTWY WPIS EFFORT MOWI O SOBIE ===")
sprawdz("EFFORT nadal wyraza intencje dla wszystkich etapow",
        len(config.EFFORT) >= 6, sorted(config.EFFORT))

# TEN TEST BYL LUSTREM. Sprawdzal `"NIE MA SKUTKU" in llm_src`, czyli obecnosc
# NAPISU w pliku — i przechodzil, chociaz ostrzezenie stalo w `_call_claude`,
# do ktorej nie ma jak wejsc nic spoza Claude. Wykrywacz martwych obietnic sam
# byl martwa obietnica. Teraz wolamy `llm.call` naprawde i patrzymy, co wypisze.
import contextlib   # noqa: E402
import io           # noqa: E402
import sqlite3      # noqa: E402
import tempfile     # noqa: E402

import db           # noqa: E402
import llm          # noqa: E402


def _co_wypisze(purpose):
    """Odpala `llm.call` w DRY_RUN i oddaje to, co poszlo na ekran."""
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(pathlib.Path(tmp) / "t.db")
        run_id = db.start_run(conn)
        llm._EFFORT_BEZ_SKUTKU.clear()
        stary = config.DRY_RUN
        config.DRY_RUN = True
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                llm.call(purpose, "s", "u", conn=conn, run_id=run_id)
        finally:
            config.DRY_RUN = stary
            conn.close()
        return buf.getvalue()


deepseekowe = [p for p in config.EFFORT
               if config.MODEL_FOR.get(p, "").startswith("deepseek")]
claudowe = [p for p in config.EFFORT
            if not config.MODEL_FOR.get(p, "").startswith("deepseek")]
sprawdz("sa etapy z EFFORT chodzace na DeepSeeku", bool(deepseekowe), deepseekowe)
sprawdz("i sa chodzace na Claude", bool(claudowe), claudowe)

if deepseekowe:
    wyjscie = _co_wypisze(deepseekowe[0])
    sprawdz("etap deepseekowy DOSTAJE ostrzezenie (naprawde, nie w napisie)",
            "NIE MA SKUTKU" in wyjscie, repr(wyjscie[:160]))
    sprawdz("i ostrzezenie nazywa model", config.MODEL_FOR[deepseekowe[0]] in wyjscie)
if claudowe:
    # KONTRDOWOD: tam, gdzie pokretlo DZIALA, nie wolno straszyc.
    sprawdz("etap claudowy NIE dostaje ostrzezenia",
            "NIE MA SKUTKU" not in _co_wypisze(claudowe[0]))
# Raz na proces: drugie wywolanie tego samego etapu ma juz milczec.
if deepseekowe:
    with tempfile.TemporaryDirectory() as tmp2:
        c2 = db.connect(pathlib.Path(tmp2) / "t.db")
        r2 = db.start_run(c2)
        llm._EFFORT_BEZ_SKUTKU.clear()
        st = config.DRY_RUN
        config.DRY_RUN = True
        b1, b2 = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(b1):
            llm.call(deepseekowe[0], "s", "u", conn=c2, run_id=r2)
        with contextlib.redirect_stdout(b2):
            llm.call(deepseekowe[0], "s", "u", conn=c2, run_id=r2)
        config.DRY_RUN = st
        c2.close()
        sprawdz("pierwsze wywolanie mowi", "NIE MA SKUTKU" in b1.getvalue())
        sprawdz("drugie juz milczy", "NIE MA SKUTKU" not in b2.getvalue())
# I sprawdzenie, ze ostrzezenie NIE wrocilo do funkcji, ktora go nie widzi.
import ast as _ast   # noqa: E402
for _w in _ast.walk(_ast.parse(llm_src)):
    if isinstance(_w, _ast.FunctionDef) and _w.name == "_call_claude":
        _seg = _ast.get_source_segment(llm_src, _w) or ""
        sprawdz("ostrzezenia nie ma w _call_claude (tam jest nieosiagalne)",
                "NIE MA SKUTKU" not in _seg)
# KONTRDOWOD: samo ostrzezenie nie moze zastapic dzialania tam, gdzie pokretlo
# DZIALA. Model Claude ma nadal dostawac output_config.
sprawdz("na Claude pokretlo nadal dziala",
        'kwargs["output_config"] = {"effort": config.EFFORT[purpose]}' in llm_src)
sprawdz("i komentarz nazywa granice: to pokretlo tylko dla Claude",
        "POKRETLO WYLACZNIE DLA MODELI CLAUDE"
        in pathlib.Path("agent-v2/config.py").read_text(encoding="utf-8"))
# DeepSeek ma osobne, JEDNO pokretlo i ma nim zostac.
sprawdz("DeepSeek ma swoje osobne ustawienie",
        isinstance(config.DEEPSEEK_EFFORT, str) and config.DEEPSEEK_EFFORT)

print()
print("=== 2. LIMIT MIESIECZNY: OSTRZEGA, ZANIM ZATRZYMA ===")
sprawdz("alarm patrzy tez na miesiac", "MONTHLY_LIMIT_USD" in alarm_src)
sprawdz("i mowi, ile dni zostalo", "zostalo_dni" in alarm_src)
sprawdz("prog miesieczny jest nizszy niz dzienny",
        "MONTHLY_LIMIT_USD * 0.75" in alarm_src
        and "DAILY_LIMIT_USD * 0.9" in alarm_src)
# NIE ZACZYNAJ TEGO, CZEGO NIE SKONCZYSZ — ta sama zasada co przy przerwach.
sprawdz("artykul nie startuje, gdy miesiac nie udzwignie calego",
        "MIESIAC NA WYCZERPANIU" in run_src)
sprawdz("i porownuje sie z kosztem CALEGO przebiegu, nie jednego wywolania",
        "config.RUN_LIMIT_USD" in run_src.split("MIESIAC NA WYCZERPANIU")[0][-700:])
sprawdz("limity sa uporzadkowane: przebieg < doba < miesiac",
        config.RUN_LIMIT_USD < config.DAILY_LIMIT_USD < config.MONTHLY_LIMIT_USD,
        (config.RUN_LIMIT_USD, config.DAILY_LIMIT_USD, config.MONTHLY_LIMIT_USD))
# KONTRDOWOD: doba musi udzwignac co najmniej jeden caly artykul, inaczej
# artykul nie powstalby NIGDY, a agent milczalby o przyczynie.
sprawdz("doba udzwignie caly artykul",
        config.DAILY_LIMIT_USD >= config.RUN_LIMIT_USD * 2,
        (config.DAILY_LIMIT_USD, config.RUN_LIMIT_USD))

print()
print("=== 3. OKLADKA POWSTAJE Z ARTYKULEM, NIE Z PUBLIKACJA ===")
przed_publikacja = run_src.split("if args.wyslij:")
sprawdz("galaz publikacji istnieje", len(przed_publikacja) >= 2)
# Grafika ma stac PRZED galezia publikacji — czyli w czesci wspolnej.
i_graf = run_src.find("stages.grafika(")
i_wyslij = run_src.find("if args.wyslij:\n            import browser")
sprawdz("grafika jest wolana", i_graf > 0)
sprawdz("i stoi PRZED galezia publikacji", 0 < i_graf < i_wyslij,
        (i_graf, i_wyslij))
# KONTRDOWOD: przeniesienie nie moze zabrac jej wciecia funkcji — gdyby
# wyladowala na poziomie modulu, wolalaby sie przy imporcie.
linia_graf = next(l for l in run_src.splitlines() if "stages.grafika(" in l)
sprawdz("z wcieciem ciala funkcji, nie modulu",
        linia_graf.startswith("        stages.grafika("), repr(linia_graf[:24]))
sprawdz("i nadal nie zatrzymuje artykulu przy awarii",
        "NIGDY nie zatrzymuje" in run_src)

print()
print("=== 4. KAZDY MODEL ANTHROPIC UMIE SZUKAC ===")
# Bylo `config.WEB_SEARCH_TOOL[model]` — surowy odczyt ze slownika, ktory mial
# wpisy tylko dla dwoch modeli. Trzeci, `claude-fable-5`, to ten, NA KTORYM
# CHODZI PISARZ. KeyError wypadalby w srodku platnego wywolania, po oplaceniu
# wszystkich wczesniejszych etapow — czyli w najdrozszym mozliwym miejscu.
sprawdz("kazdy model Claude z routingu ma wpis albo galaz awaryjna",
        all(config.narzedzie_wyszukiwania(m)[0]
            for m in (config.CLAUDE, config.SONNET, config.FABLE)))
for m in (config.CLAUDE, config.SONNET, config.FABLE):
    sprawdz("  %s bez ostrzezenia (ma wlasny wpis)" % m,
            config.narzedzie_wyszukiwania(m)[1] == "")
# KONTRDOWOD: nieznany model NIE moze wywalic przebiegu, ale MUSI byc slyszalny.
nazwa, uwaga = config.narzedzie_wyszukiwania("claude-czegos-takiego-nie-ma")
sprawdz("nieznany model dostaje narzedzie zamiast wyjatku", bool(nazwa))
sprawdz("i glosne ostrzezenie", "nie ma wpisu w WEB_SEARCH_TOOL" in uwaga)
sprawdz("llm nie czyta juz slownika wprost",
        "config.WEB_SEARCH_TOOL[" not in llm_src)
sprawdz("tylko przez funkcje", "_narzedzie_wyszukiwania(model)" in llm_src)
sprawdz("i mowi o braku raz na proces", "_WYSZUKIWANIE_BEZ_WPISU" in llm_src)
# Kazdy model uzywany przez etapy z web_search musi byc obslugiwany.
modele_z_routingu = {m for m in config.MODEL_FOR.values()
                     if m.startswith("claude")}
sprawdz("zaden model z routingu nie wywala sie na wyszukiwaniu",
        all(config.narzedzie_wyszukiwania(m)[0] for m in modele_z_routingu),
        sorted(modele_z_routingu))

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
