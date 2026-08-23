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
sprawdz("llm mowi, gdy wpis nie ma skutku", "NIE MA SKUTKU" in llm_src)
sprawdz("i mowi raz na proces, nie przy kazdym wywolaniu",
        "_EFFORT_BEZ_SKUTKU" in llm_src
        and llm_src.count("_EFFORT_BEZ_SKUTKU") >= 3,
        llm_src.count("_EFFORT_BEZ_SKUTKU"))
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
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
