"""Artykul nie powstaje z faktu, ktory unosi dwa zdania.

PYTANIE WLASCICIELA, 30 sierpnia 2026: „czy rozrozniamy waznosc artykulu —
notatka moze byc o jednej malej kwestii, cala informacja w dwoch zdaniach i za
bardzo nie ma co rozwijac, a artykul jakby wzial te info i musial na 1200 slow,
to byloby lanie wody".

NIE ROZROZNIALISMY. Sprawdzone w kodzie:
  - `wybierz_fakt` pyta wylacznie o swiezosc i powtorke; o dlugosc ani razu,
  - `temat_z_faktu` PROSI model o „pytanie warte tej dlugosci" — prosba, nie
    bramka,
  - `warto_pisac` ocenia piec filarow, ale dopiero PO researchu i nic nie
    blokuje (`gates.verdict` zawsze zwraca SAVED),
  - flaga `na_artykul` istnieje, ale tylko na sciezce SKAUTA; fakt z puli nigdy
    jej nie dostaje i nikt jej nie pyta.

I NAJGORSZE — SYGNAL GLEBOKOSCI BYL MARTWY. `artykul_z_puli` czytalo
`ocena.get("depth")` z `warto_pisac`, ktore pola `depth` NIE MA: produkuje je
`wykonalnosc.md`, etap, ktorego sciezka z puli w ogole nie wola. Wiec
`glebokosc` bylo ZAWSZE „RICH" — pisarzowi zawsze kazano pisac najglebsza
forme, niezaleznie od tego, czy fakt to unosi. Pole czytane, nigdy nieustawiane.
"""
import pathlib
import sys

sys.path.insert(0, "agent-v2")
import artykul_z_puli as azp   # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


def ocena(**kw):
    return {k: {"present": bool(v)} for k, v in kw.items()}


print("=== 1. GLEBOKOSC LICZONA Z FILAROW, NIE Z SAMOOCENY ===")
# MODEL OBSERWUJE, KOD DECYDUJE. Nie pytamy modelu „jak gleboki jest ten
# material" — samooceny w tym potoku degeneruja do stalej (pewnosc zawsze 1.0,
# watki zawsze 6). `warto_pisac` odpowiada na piec pytan tak/nie z dowodem,
# a suma to robota dla kodu.
PELNA = dict(contradicted_belief=1, named_decider=1, felt_number=1,
             second_domain=1, unsettled_outcome=1)
sprawdz("piec filarow -> RICH", azp.glebokosc_z_oceny(ocena(**PELNA)) == "RICH")
sprawdz("cztery -> RICH", azp.glebokosc_z_oceny(
    ocena(**{**PELNA, "unsettled_outcome": 0})) == "RICH")
sprawdz("trzy -> SINGLE", azp.glebokosc_z_oceny(
    ocena(**{**PELNA, "felt_number": 0, "second_domain": 0})) == "SINGLE")
sprawdz("jeden -> THIN", azp.glebokosc_z_oceny(
    ocena(contradicted_belief=1, named_decider=0, felt_number=0,
          second_domain=0, unsettled_outcome=0)) == "THIN")
# KONTRDOWOD: pusta ocena musi dac THIN, nie RICH. Dokladnie tu siedziala wada
# — `ocena.get("depth") or "RICH"` zamienialo BRAK ODPOWIEDZI w najglebsza
# forme, czyli w polecenie „pisz najdluzej" przy zerowej wiedzy o materiale.
sprawdz("pusta ocena -> THIN, a NIE RICH",
        azp.glebokosc_z_oceny({}) == "THIN", azp.glebokosc_z_oceny({}))
sprawdz("i brak pola `depth` niczego juz nie psuje",
        azp.glebokosc_z_oceny({"depth": "RICH"}) == "THIN")

print()
print("=== 2. BRAMKA ARTYKULOWA — PRZED RESEARCHEM ===")
DRUGI = "The Assembly struck text from the duties before enactment in 2024."
ZASIEG = "The same clause runs in the EU AI Act and in China's Measures."

ok, powod = azp.uniesie_artykul({"second_act": DRUGI, "beyond_one_place": ""})
sprawdz("sam drugi akt wystarczy", ok, powod)
ok, powod = azp.uniesie_artykul({"second_act": "", "beyond_one_place": ZASIEG})
sprawdz("sam zasieg wystarczy", ok, powod)
# JEDEN WYSTARCZY, NIE OBA — wymaganie obu odrzucaloby dobre tematy: prawo,
# ktore dopiero weszlo, nie ma drugiego aktu, ale ma zasieg.
ok, _ = azp.uniesie_artykul({"second_act": DRUGI, "beyond_one_place": ZASIEG})
sprawdz("oba naraz oczywiscie tez", ok)

ok, powod = azp.uniesie_artykul({"second_act": "", "beyond_one_place": ""})
sprawdz("bez zadnego z dwoch — to notka", not ok, powod)
sprawdz("i powod mowi to wprost", "notka" in powod, powod)

print()
print("=== 3. WYPELNIACZE TO PUSTE POLE NAPISANE INACZEJ ===")
# Model proszony o uczciwosc czasem zamiast pustki wpisuje slowo. Gdyby „none"
# przechodzilo, bramka bylaby ozdoba — model zawsze cos wpisze.
for napis in ("none", "N/A", "unclear", "unknown", "nothing"):
    ok, _ = azp.uniesie_artykul({"second_act": napis, "beyond_one_place": napis})
    sprawdz("odrzuca wypelniacz %r" % napis, not ok)
ok, _ = azp.uniesie_artykul({"second_act": "It changed.",
                             "beyond_one_place": "Elsewhere too."})
sprawdz("odrzuca odpowiedz za krotka, by cos znaczyc", not ok)

print()
print("=== 4. BRAMKA STOI PRZED RESEARCHEM, NIE PO ===")
src = pathlib.Path("agent-v2/artykul_z_puli.py").read_text(encoding="utf-8")
i_bramka = src.find("uniesie_artykul(brief)")
i_dysk = src.find("stages.discovery(")
sprawdz("bramka przed dyskoveria", 0 < i_bramka < i_dysk,
        (i_bramka, i_dysk))
# Odrzucony fakt ma WROCIC do puli jako material na notke, a nie zostac
# skasowany: nie jest zly, tylko nie unosi tysiaca slow.
sprawdz("odrzucony fakt zostaje na notke", "zostaje w puli" in src)
sprawdz("i probujemy kolejnych faktow, nie poddajemy sie na pierwszym",
        "proby < 4" in src)

print()
print("=== 5. PODPYTANIA IDA DO RESEARCHU, NIE TYLKO DO PISARZA ===")
# Wlasciciel prosil, zeby temat artykulu byl BARDZIEJ ZBADANY niz temat notki.
# To znaczy wiecej pytan na WEJSCIU researchu, nie wiecej slow na wyjsciu.
sprawdz("brief zamawia podpytania", '"sub_questions"' in src)
sprawdz("prompt odroznia je od hasel do wyszukania",
        "Not search phrases" in src)
sprawdz("podpytania trafiaja do dyskoverii",
        "pytanie_do_researchu" in src
        and "stages.discovery(conn, run_id, pytanie_do_researchu" in src)
i_pod = src.find("pytanie_do_researchu = (")
sprawdz("i skladaja sie w jedno pytanie przed wyszukiwaniem",
        0 < i_pod < src.find("stages.discovery(conn, run_id, pytanie_do_researchu"))

print()
print("=== 6. ARTYKUL TEZ SIEGA NAJPIERW DO SPIZARNI ===")
# Podlaczylem indeks do notek i zostawilem sciezke artykulu na swiezym
# szukaniu. Zywy test tego samego wieczora: 18 wyszukiwan, 450 tys. tokenow
# wejscia i 0,127 USD po to, zeby wybrac jeden fakt — podczas gdy w indeksie
# lezaly gotowe, oplacone i przepuszczone przez bramke.
i_spizarnia = src.find("stages.wez_kandydatow(ile)")
i_szukanie = src.find("stages.znajdz_ciekawostki(conn, run_id, ile=ile)")
sprawdz("wybierz_fakt pyta indeks", i_spizarnia > 0, i_spizarnia)
sprawdz("i robi to PRZED platnym szukaniem",
        0 < i_spizarnia < i_szukanie, (i_spizarnia, i_szukanie))
sprawdz("szukanie zostaje jako droga awaryjna, nie znika",
        i_szukanie > 0, i_szukanie)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
