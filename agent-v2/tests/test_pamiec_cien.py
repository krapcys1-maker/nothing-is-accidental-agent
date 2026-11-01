# -*- coding: utf-8 -*-
"""N1 — CIEN PAMIECI (1.11.2026): `pamiec_cien.py`, hak w `run.dane_maniery`, progi w `historia_konta.powiazane`.

PO CO. Wlasciciel chce pamieci, osobowosci i celow w zywym botcie; protokol sesji badawczej (`b64d857`) wymaga najpierw
CIENIA: zapisu, co wstrzyknelaby surowa pamiec wlasnej historii, bez wplywu na tekst. Test pilnuje, ze cien (1) niczego
nie zmienia w tym, co zwraca `dane_maniery` ani w progach produkcyjnych `historia_konta`, (2) nie zapisuje tekstu celu
ani autora (tylko skroty kluczowane), (3) ma stale pola z protokolu i status w kazdym rekordzie, (4) jest fail-open,
z flaga, limitem czasu i rozmiaru, (5) w `NIA_TRYB=test` nie pisze do domyslnego pliku, (6) profil „produkcja" jest
DOKLADNIE tym, co zwraca `historia_konta.powiazane` dla tego samego celu.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_pamiec_cien.py
"""
import contextlib
import hashlib
import io
import json
import os
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
import pamiec_cien      # noqa: E402
import run              # noqa: E402

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


TERAZ = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)      # LITERAL: zegar nie wchodzi do testu
CEL = ("Moonshot released Kimi K3.1 with open weights on 4 November, and its cyber index scores 64% "
       "on Artificial Analysis. Autor: @zenobiusz kontakt jan.kowalski@example.com https://cel.example/p/kimi")
bliska = "Moonshot launched Kimi K3.1 Pro and promised the weights by 4 November; Artificial Analysis puts its cyber index at 64%."
srednia = "Kimi K3.1 weights arrive 4 November, which matters for any open model's cyber capability."
luzna = "Open weights models keep getting cheaper to run, and the cyber benchmarks are catching up."


def wpis(dni, rodzaj="notka", tekst="", udane=True):
    return {"kiedy": (TERAZ - timedelta(days=dni)).isoformat(), "rodzaj": rodzaj, "udane": udane, "tekst": tekst}


dz = KAT / "dziennik.jsonl"
wiersze = [wpis(30, tekst=bliska), wpis(5, tekst=srednia), wpis(9, tekst=luzna),
           wpis(3, tekst="Totally unrelated note about housing prices in Lisbon and rent caps."),
           wpis(4, tekst=bliska, udane=False), wpis(70, tekst=bliska + " (stara wersja)")]
dz.write_bytes(("\n".join(json.dumps(w, ensure_ascii=False) for w in wiersze) + "\n").encode("utf-8"))
out = KAT / "pamiec_cien_test.jsonl"


def linie(plik):
    return [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()] if plik.exists() else []


print("=== 1. HISTORIA_KONTA: PROGI OPCJONALNE, DOMYSLNIE JAK DOTAD ===")
dom = historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz)
jawne = historia_konta.powiazane(
    CEL, teraz=TERAZ, plik=dz, min_podobienstwa=config.HISTORIA_KONTA_MIN_PODOBIENSTWA,
    min_rzadkich=config.HISTORIA_KONTA_MIN_RZADKICH, ile=config.HISTORIA_KONTA_WPISOW)
sprawdz("jawne progi rowne config daja ten sam wynik co domyslne", [w["tekst"] for w in dom] == [w["tekst"] for w in jawne]
        and len(dom) >= 1, [w["tekst"][:30] for w in dom])
sprawdz("prog 0,99 nie zwraca nic", historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, min_podobienstwa=0.99) == [])
sprawdz("min_rzadkich=99 nie zwraca nic, a 0 zwraca (parametr dziala)",
        historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, min_podobienstwa=0.05, min_rzadkich=99) == []
        and len(historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, min_podobienstwa=0.05, min_rzadkich=0)) >= 1)
sprawdz("luzniejszy prog daje co najmniej tyle samo", len(historia_konta.powiazane(
    CEL, teraz=TERAZ, plik=dz, min_podobienstwa=0.05, min_rzadkich=0, ile=50)) >= len(dom))
sprawdz("wynik niesie liczbe rzadkich terminow", all(isinstance(w.get("rzadkie"), int) for w in dom), dom)
st = {}
historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, statystyki=st)
sprawdz("statystyki: pula to wpisy w oknie, udane i nie starsze niz 60 dni (4 z 6), najnowszy = 3 dni temu",
        st.get("pula") == 4 and st.get("najnowszy", "").startswith((TERAZ - timedelta(days=3)).date().isoformat()), st)

print("=== 2. REKORD CIENIA: POLA PROTOKOLU I PRYWATNOSC ===")
rek, log = cicho(pamiec_cien.cien_komentarza, CEL, "https://cel.example/p/kimi", "on", zadanie="komentarz_pod_artykulem",
                 run_id=7, autor="zenobiusz", teraz=TERAZ, plik=out, historia=dz)
zapis = linie(out)
sprawdz("jeden rekord w pliku i ten sam zwrocony", len(zapis) == 1 and rek and zapis[0]["record_id"] == rek["record_id"], zapis)
r0 = zapis[0] if zapis else {}
sprawdz("tozsamosc: schemat, run_id natywny, zadanie, ramie E23, status ok",
        r0.get("schema_version") == 1 and r0.get("run_id") == 7 and r0.get("run_id_basis") == "native"
        and r0.get("task_type") == "komentarz_pod_artykulem" and r0.get("arm_e23") == "on" and r0.get("status") == "ok"
        and r0.get("error_code") is None and re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$", r0.get("occurred_at", "")), r0)
sprawdz("as_of = czas decyzji, migawka indeksu: pula 4, okno 60 dni, rozmiar dziennika",
        r0.get("as_of") == "2026-11-01T12:00:00+00:00" and r0["index_snapshot"]["pool_size"] == 4
        and r0["index_snapshot"]["window_days"] == 60 and r0["index_snapshot"]["journal_bytes"] == dz.stat().st_size, r0.get("index_snapshot"))
sprawdz("zapytanie: skrot kluczowany 24 hex i dlugosc; autor tez skrot",
        re.fullmatch(r"[0-9a-f]{24}", r0["query"]["hmac"] or "") and r0["query"]["chars"] == len(CEL)
        and re.fullmatch(r"[0-9a-f]{24}", r0["query"]["author_hmac"] or ""), r0.get("query"))
surowy = out.read_text(encoding="utf-8")
sprawdz("PRYWATNOSC: w pliku nie ma tekstu celu, uchwytu autora, e-maila ani adresu celu",
        not any(x in surowy for x in ("Moonshot", "zenobiusz", "kowalski", "example.com", "cel.example", "Artificial Analysis")), surowy[:300])
sprawdz("strategia: id, digest konfiguracji, brak embeddera, trzy profile",
        r0["strategy"]["id"] == "lexical_idf_cosine_v1" and re.fullmatch(r"[0-9a-f]{16}", r0["strategy"]["config_digest"])
        and r0["strategy"]["embedder"] is None
        and [p["name"] for p in r0["strategy"]["profiles"]] == ["produkcja", "luzny", "szeroki"], r0["strategy"])
_p0 = r0["strategy"]["profiles"][0]
sprawdz("metadane profilu produkcja = progi z config (nie moga sie rozjechac z E23 on)",
        _p0 == {"name": "produkcja", "min_score": config.HISTORIA_KONTA_MIN_PODOBIENSTWA,
                "min_rare_terms": config.HISTORIA_KONTA_MIN_RZADKICH, "top": config.HISTORIA_KONTA_WPISOW}, _p0)
_stary_e = config.EKSPERYMENTY
config.EKSPERYMENTY = {"trwa": {"udzial": 0.5, "od": "2026-10-01", "do": "2026-12-01"},
                       "skonczony": {"udzial": 0.5, "od": "2026-09-01", "do": "2026-10-01"},
                       "jeszcze_nie": {"udzial": 0.5, "od": "2026-11-05", "do": "2026-12-01"},
                       "kalendarz": {"plan": ["on", "off"], "okres_dni": 1, "od": "2026-10-20", "do": "2026-12-01"}}
_r_e, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=KAT / "eksp.jsonl", historia=dz)
config.EKSPERYMENTY = _stary_e
sprawdz("active_experiments: tylko eksperymenty trwajace w dniu decyzji (okno dat), posortowane",
        _r_e["active_experiments"] == ["kalendarz", "trwa"], _r_e.get("active_experiments"))
_r_bez, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=KAT / "bez_run.jsonl", historia=dz)
sprawdz("brak run_id: run_id null i podstawa „absent”", _r_bez["run_id"] is None and _r_bez["run_id_basis"] == "absent", _r_bez)
sprawdz("would_arm: zamrozona funkcja, A albo B, nieuzywana w cieniu",
        r0["would_arm"]["arm"] in ("A", "B") and r0["would_arm"]["used_in_shadow"] is False
        and r0["would_arm"]["seed_name"] == "pamiec_n3" and "los_stale" in r0["would_arm"]["fn"], r0["would_arm"])
import stages   # noqa: E402
_los = stages.los_stale("pamiec_n3", "https://cel.example/p/kimi")
sprawdz("would_arm zgodne z funkcja losowania (prog 10%)", r0["would_arm"]["arm"] == ("B" if _los < 0.10 else "A"), (_los, r0["would_arm"]))
sprawdz("rekord nie niesie wynikow ani statystyk (bez wycieku z przyszlosci)",
        not any(k in r0 for k in ("skutek", "wynik", "statystyki", "reakcje")), list(r0))

print("=== 3. PROFILE: „PRODUKCJA” = DOKLADNIE HISTORIA_KONTA ===")
prod_ids = {hashlib.sha256(w["tekst"].encode()).hexdigest()[:16] for w in dom}
res = r0["results"]
sprawdz("profil produkcja: te same pozycje co `historia_konta.powiazane` dla tego celu",
        {p["item_id"] for p in res["produkcja"]["items"]} == prod_ids and res["produkcja"]["n_returned"] == len(dom),
        (res["produkcja"], prod_ids))
sprawdz("liczba kandydatow rosnie z luzniejszym progiem",
        res["produkcja"]["n_candidates"] <= res["luzny"]["n_candidates"] <= res["szeroki"]["n_candidates"], {k: v["n_candidates"] for k, v in res.items()})
sprawdz("pozycje: ranga od 1, wynik malejacy, wiek w dniach, tokeny, powod",
        all(p["rank"] == i + 1 and p["reason"] == "lexical" and p["tokens_est"] > 0 and p["age_days"] >= 0
            for prof in res.values() for i, p in enumerate(prof["items"]))
        and all([x["score"] for x in prof["items"]] == sorted([x["score"] for x in prof["items"]], reverse=True)
                for prof in res.values()), res)
sprawdz("agregaty: n_candidates, n_returned, tokens_total, over_budget",
        all({"n_candidates", "n_returned", "tokens_total", "over_budget"} <= set(v) for v in res.values()), res)
sprawdz("brak tekstow wpisow w rekordzie (tylko id, rodzaj, wiek, wynik)",
        not any(x in surowy for x in ("Totally unrelated", "cheaper to run", "Kimi K3.1 Pro")), surowy[:200])

print("=== 4. SKROTY KLUCZOWANE ===")
cicho(pamiec_cien.cien_komentarza, CEL, "https://cel.example/p/kimi", "off", zadanie="komentarz_pod_notka", teraz=TERAZ, plik=out, historia=dz)
cicho(pamiec_cien.cien_komentarza, "Zupelnie inny temat o pilce noznej", "https://inny.example/p/q", "on", teraz=TERAZ, plik=out, historia=dz)
z = linie(out)
sprawdz("ten sam cel = ten sam skrot, inny cel = inny", z[0]["query"]["hmac"] == z[1]["query"]["hmac"] != z[2]["query"]["hmac"], [x["query"]["hmac"] for x in z])
sprawdz("brak autora = brak skrotu autora", z[1]["query"]["author_hmac"] is None, z[1]["query"])
klucz = KAT / ".cien_klucz"
sprawdz("klucz w katalogu danych, 32 bajty", klucz.exists() and len(klucz.read_bytes()) == 32)
if os.name == "posix":
    sprawdz("klucz ma tryb 0600", (klucz.stat().st_mode & 0o777) == 0o600, oct(klucz.stat().st_mode))
sprawdz("cel bez zadnych powiazan: status ok, puste profile", z[2]["status"] == "ok"
        and all(v["n_returned"] == 0 for v in z[2]["results"].values()), z[2]["results"])

print("=== 5. FLAGA, TRYB TESTOWY, ROZMIAR, CZAS ===")
inny = KAT / "inny.jsonl"
config.PAMIEC_CIEN = False
sprawdz("flaga False: nic nie zapisuje", cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=inny, historia=dz)[0] is None
        and not inny.exists())
config.PAMIEC_CIEN = True
domyslny = KAT / "pamiec_cien.jsonl"
sprawdz("NIA_TRYB=test bez jawnego pliku: nic nie pisze do pliku domyslnego",
        os.environ.get("NIA_TRYB") == "test" and cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, historia=dz)[0] is None
        and not domyslny.exists())
_tryb = os.environ.pop("NIA_TRYB", None)
try:
    r_dom, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, historia=dz)
finally:
    if _tryb is not None:
        os.environ["NIA_TRYB"] = _tryb
sprawdz("poza trybem testowym: pisze do data/pamiec_cien.jsonl, tryb w rekordzie", r_dom and domyslny.exists()
        and linie(domyslny)[0]["mode"] == "produkcja", r_dom)
mal = KAT / "maly.jsonl"
mal.write_text("x" * 50 + "\n", encoding="utf-8")
_stare = pamiec_cien.MAKS_BAJTOW
pamiec_cien.MAKS_BAJTOW = 10
r_m, log_m = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=mal, historia=dz)
pamiec_cien.MAKS_BAJTOW = _stare
sprawdz("limit rozmiaru: nie dopisuje, plik bez zmian, komunikat w logu", r_m is None and mal.read_text(encoding="utf-8") == "x" * 50 + "\n"
        and "nie zapisuje" in log_m, log_m)
_lim = pamiec_cien.LIMIT_S
pamiec_cien.LIMIT_S = -1.0
r_t, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=KAT / "t.jsonl", historia=dz)
pamiec_cien.LIMIT_S = _lim
sprawdz("limit czasu przekroczony: status timeout, rekord zapisany", r_t and r_t["status"] == "timeout", r_t and r_t.get("status"))

print("=== 6. FAIL-OPEN ===")
_stare_p = historia_konta.powiazane


def wybucha(*a, **k):
    raise RuntimeError("awaria historii")


historia_konta.powiazane = wybucha
r_e, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=KAT / "e.jsonl", historia=dz)
historia_konta.powiazane = _stare_p
sprawdz("awaria liczenia: rekord ze statusem error i kodem, bez wyjatku", r_e and r_e["status"] == "error"
        and r_e["error_code"] == "RuntimeError" and linie(KAT / "e.jsonl")[0]["status"] == "error", r_e)
katalog_zamiast_pliku = KAT / "to_katalog"
katalog_zamiast_pliku.mkdir()
try:
    r_k, log_k = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, plik=katalog_zamiast_pliku, historia=dz)
    wyjatek = None
except Exception as exc:       # noqa: BLE001
    r_k, log_k, wyjatek = "WYJATEK", "", exc
sprawdz("nieudany zapis (sciezka to katalog): None, bez wyjatku, slad w logu", r_k is None and wyjatek is None and "zapis nieudany" in log_k, (r_k, wyjatek, log_k))

print("=== 7. HAK W run.dane_maniery: NIE ZMIENIA TEGO, CO DOSTAJE MODEL ===")
wywolania = []


def zapisuj(*a, **k):
    wywolania.append((a, k))
    return None


_stare_c = pamiec_cien.cien_komentarza
pamiec_cien.cien_komentarza = zapisuj
cel_a = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz"}
d_a, _ = cicho(run.dane_maniery, cel_a, CEL, run_id=5, zadanie="komentarz_pod_notka")
pamiec_cien.cien_komentarza = wybucha
cel_b = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz"}
d_b, _ = cicho(run.dane_maniery, cel_b, CEL, run_id=5, zadanie="komentarz_pod_notka")
pamiec_cien.cien_komentarza = _stare_c
cel_c = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz"}
config.PAMIEC_CIEN = False
d_c, _ = cicho(run.dane_maniery, cel_c, CEL, run_id=5, zadanie="komentarz_pod_notka")
config.PAMIEC_CIEN = True
sprawdz("hak woluje cien z tekstem celu, kluczem, ramieniem, zadaniem, run_id i autorem",
        len(wywolania) == 1 and wywolania[0][0][0] == CEL and wywolania[0][0][1] == "https://h1.example/p/kimi"
        and wywolania[0][0][2] == cel_a["_maniera"] and wywolania[0][1]["zadanie"] == "komentarz_pod_notka"
        and wywolania[0][1]["run_id"] == 5 and wywolania[0][1]["autor"] == "zenobiusz", wywolania)
sprawdz("wynik dane_maniery identyczny z cieniem, z awaria cienia i z wylaczonym cieniem", d_a == d_b == d_c, (d_a, d_b, d_c))
sprawdz("awaria cienia nie zatrzymuje komentarza (ramie zapisane mimo wyjatku)", cel_b["_maniera"] == cel_a["_maniera"])
sprawdz("hak nie dopisuje niczego do slownika celu (identyczny z cieniem, z awaria i z wylaczonym)",
        cel_a == cel_b == cel_c, (sorted(cel_a), sorted(cel_b), sorted(cel_c)))
_src = "\n".join(x for x in pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))
_dm = _src[_src.index("def dane_maniery("):_src.index("def ramiona_odpowiedzi(")]
sprawdz("hak stoi PRZED rozgalezieniem on/off (dostaja go oba ramiona)",
        _dm.index("pamiec_cien.cien_komentarza(") < _dm.index('if r != "on":'))
sprawdz("hak jest w try/except Exception", re.search(r"try:\s+import pamiec_cien\s+pamiec_cien\.cien_komentarza\(.*?except Exception", _dm, re.S) is not None)

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
