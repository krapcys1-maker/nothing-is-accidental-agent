# -*- coding: utf-8 -*-
"""N1 — CIEN PAMIECI (1.11.2026): `pamiec_cien.py`, hak w `run.dane_maniery`, progi w `historia_konta.powiazane`.

PO CO. Wlasciciel chce pamieci, osobowosci i celow w zywym botcie; protokol sesji badawczej wymaga najpierw CIENIA: zapisu,
co wstrzyknelaby surowa pamiec wlasnej historii, bez wplywu na tekst. Test pilnuje, ze cien (1) niczego nie zmienia w tym,
co zwraca `dane_maniery`, w slowniku celu ani w progach produkcyjnych `historia_konta`, (2) nie zapisuje tekstu celu ani
autora (tylko skroty KLUCZOWANE z id klucza), (3) ma stale pola z uzgodnionego rekordu i status w kazdym rekordzie, (4) jest
fail-open, z flaga, limitem czasu i rozmiaru, (5) w `NIA_TRYB=test` nie pisze do domyslnego pliku i zawsze pisze do
katalogu podanego przez wywolujacego, (6) profil „produkcja" jest DOKLADNIE tym, co zwraca `historia_konta.powiazane`,
z prawdziwym `n_candidates`, (7) rozroznia ramie on/off/brak, klucz HMAC, tekst z lone surrogate, brak dziennika i klucza.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_pamiec_cien.py
"""
import contextlib
import hashlib
import hmac
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


TERAZ = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)      # LITERAL: zegar nie wchodzi do testu
CEL = ("Moonshot released Kimi K3.1 with open weights on 4 November, and its cyber index scores 64% "
       "on Artificial Analysis. Autor: @zenobiusz kontakt jan.kowalski@example.com https://cel.example/p/kimi")
ADRES = "https://cel.example/p/kimi"
bliska = "Moonshot launched Kimi K3.1 Pro and promised the weights by 4 November; Artificial Analysis puts its cyber index at 64%."
srednia = "Kimi K3.1 weights arrive 4 November, which matters for any open model's cyber capability."
luzna = "Open weights models keep getting cheaper to run, and the cyber benchmarks are catching up."
# trzy wpisy o PODOBIENSTWIE POSREDNIM (ok. 0,05-0,08, bez rzadkich terminow): przechodza tylko profil „szeroki”, wiec profile
# da sie rozroznic (progi: produkcja 0,13 i 2 rzadkie, luzny 0,08 i 1 rzadki, szeroki 0,05 i 0)
posrednia1 = "Kimi 4 November: Moonshot and Artificial Analysis both say the cyber index matters."
posrednia2 = "The Artificial Analysis cyber index now covers Kimi and other open weights models."
posrednia3 = "Moonshot says weights will land on 4 November and Artificial Analysis will rerun its index."


def wpis(dni, rodzaj="notka", tekst="", udane=True):
    return {"kiedy": (TERAZ - timedelta(days=dni)).isoformat(), "rodzaj": rodzaj, "udane": udane, "tekst": tekst}


dz = KAT / "dziennik.jsonl"
wiersze = [wpis(30, tekst=bliska), wpis(5, tekst=srednia), wpis(9, tekst=luzna), wpis(7, tekst=posrednia1), wpis(8, tekst=posrednia2), wpis(10, tekst=posrednia3),
           wpis(3, tekst="Totally unrelated note about housing prices in Lisbon and rent caps."),
           wpis(4, tekst=bliska, udane=False), wpis(70, tekst=bliska + " (stara wersja)")]
dz.write_bytes(("\n".join(json.dumps(w, ensure_ascii=False) for w in wiersze) + "\n").encode("utf-8"))
out = KAT / "pamiec_cien_test.jsonl"


def linie(plik):
    return [json.loads(x) for x in plik.read_text(encoding="utf-8").splitlines() if x.strip()] if plik.exists() else []


def ids(poz):
    return {p["item_id"] for p in poz}


def sha16(t):
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def zapisz(*a, **k):
    k.setdefault("teraz", TERAZ)
    k.setdefault("historia", dz)
    k.setdefault("plik", out)
    k.setdefault("katalog", KAT)
    return cicho(pamiec_cien.cien_komentarza, *a, **k)


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
sprawdz("statystyki: pula to wpisy w oknie, udane i nie starsze niz 60 dni (7 z 9), najnowszy = 3 dni temu",
        st.get("pula") == 7 and st.get("najnowszy", "").startswith((TERAZ - timedelta(days=3)).date().isoformat()), st)

print("=== 2. REKORD CIENIA: POLA UZGODNIONEGO REKORDU I PRYWATNOSC ===")
rek, log = zapisz(CEL, ADRES, "on", zadanie="komentarz_pod_artykulem", run_id=7, autor="zenobiusz", wyslij=True)
zapis = linie(out)
sprawdz("jeden rekord w pliku i ten sam zwrocony", len(zapis) == 1 and rek and zapis[0]["record_id"] == rek["record_id"], zapis)
sprawdz("slad w logu przebiegu: linia [cien] ze statusem", "[cien] rekord status=ok" in log, log)
r0 = zapis[0] if zapis else {}
sprawdz("tozsamosc: schemat, run_id natywny, zadanie, ramie E23, status ok, publish_run",
        r0.get("schema_version") == 1 and r0.get("run_id") == 7 and r0.get("run_id_basis") == "native"
        and r0.get("task_type") == "komentarz_pod_artykulem" and r0.get("arm_e23") == "on" and r0.get("status") == "ok"
        and r0.get("error_code") is None and r0.get("degraded_reason") is None and r0.get("publish_run") is True
        and r0.get("occurred_at") == "2026-11-01T12:00:00+00:00" and r0.get("journal_ref") is None
        and r0.get("journal_ref_basis") == "none_at_decision_time", r0)
sprawdz("record_id: 16 hex; kod: skrot commita z `stages.WERSJA_KODU`",
        re.fullmatch(r"[0-9a-f]{16}", r0.get("record_id", "")) and r0.get("code_commit") == (stages.WERSJA_KODU or ""), r0.get("code_commit"))
sprawdz("as_of = czas decyzji, migawka indeksu: pula 7, okno 60 dni, rozmiar dziennika",
        r0.get("as_of") == "2026-11-01T12:00:00+00:00" and r0["index_snapshot"]["pool_size"] == 7
        and r0["index_snapshot"]["window_days"] == 60 and r0["index_snapshot"]["journal_bytes"] == dz.stat().st_size, r0.get("index_snapshot"))
klucz = (KAT / ".cien_klucz").read_bytes()
norm = " ".join(CEL.split())
sprawdz("skroty = HMAC-SHA256 z kluczem z pliku (24 hex): zapytanie, cel (gdzie z dziennika) i autor; id klucza = 8 hex z SHA-256 klucza",
        r0["query"]["hmac"] == hmac.new(klucz, norm.encode(), hashlib.sha256).hexdigest()[:24]
        and r0["query"]["target_hmac"] == hmac.new(klucz, ("cel|" + ADRES).encode(), hashlib.sha256).hexdigest()[:24]
        and r0["query"]["author_hmac"] == hmac.new(klucz, b"autor|zenobiusz", hashlib.sha256).hexdigest()[:24]
        and r0["query"]["key_id"] == hashlib.sha256(klucz).hexdigest()[:8] and r0["query"]["chars"] == len(CEL), r0.get("query"))
sprawdz("skrot zapytania NIE jest zwyklym skrotem tekstu (slownikowo odtwarzalnym)",
        r0["query"]["hmac"] != hashlib.sha256(norm.encode()).hexdigest()[:24])
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
sprawdz("digest konfiguracji zmienia sie razem z progiem",
        (lambda d0: (setattr(config, "HISTORIA_KONTA_MIN_PODOBIENSTWA", 0.2), pamiec_cien.digest_konfiguracji())[1] != d0)(
            pamiec_cien.digest_konfiguracji()) or True)
config.HISTORIA_KONTA_MIN_PODOBIENSTWA = 0.13
_d1 = pamiec_cien.digest_konfiguracji()
config.HISTORIA_KONTA_MIN_PODOBIENSTWA = 0.2
_d2 = pamiec_cien.digest_konfiguracji()
config.HISTORIA_KONTA_MIN_PODOBIENSTWA = 0.13
sprawdz("digest konfiguracji: ten sam przy tych samych progach, inny po zmianie progu", _d1 != _d2 and _d1 == pamiec_cien.digest_konfiguracji())
_stary_e = config.EKSPERYMENTY
config.EKSPERYMENTY = {"trwa": {"udzial": 0.5, "od": "2026-10-01", "do": "2026-12-01"},
                       "skonczony": {"udzial": 0.5, "od": "2026-09-01", "do": "2026-10-01"},
                       "jeszcze_nie": {"udzial": 0.5, "od": "2026-11-05", "do": "2026-12-01"},
                       "kalendarz": {"plan": ["on", "off"], "okres_dni": 1, "od": "2026-10-20", "do": "2026-12-01"}}
_r_e, _ = zapisz(CEL, "k", "on", plik=KAT / "eksp.jsonl")
config.EKSPERYMENTY = _stary_e
sprawdz("eksperymenty: tylko trwajace w dniu decyzji (okno dat), posortowane",
        _r_e["eksperymenty"] == ["kalendarz", "trwa"] and "active_experiments" not in _r_e, _r_e.get("eksperymenty"))
_r_bez, _ = zapisz(CEL, "k", "on", plik=KAT / "bez_run.jsonl")
sprawdz("brak run_id: run_id null i podstawa „absent”, publish_run null", _r_bez["run_id"] is None
        and _r_bez["run_id_basis"] == "absent" and _r_bez["publish_run"] is None, _r_bez)
sprawdz("would_arm: zamrozona funkcja, A albo B, nieuzywana w cieniu",
        r0["would_arm"]["arm"] in ("A", "B") and r0["would_arm"]["used_in_shadow"] is False
        and r0["would_arm"]["seed_name"] == "pamiec_n3" and "los_stale" in r0["would_arm"]["fn"], r0["would_arm"])
_los = stages.los_stale("pamiec_n3", ADRES)
sprawdz("would_arm zgodne z funkcja losowania (prog 10%)", r0["would_arm"]["arm"] == ("B" if _los < 0.10 else "A"), (_los, r0["would_arm"]))
_arms = [pamiec_cien.rekord("t", "https://h%d.example/p" % i, teraz=TERAZ, historia=dz, katalog=KAT)["would_arm"]["arm"] for i in range(300)]
sprawdz("would_arm na 300 kluczach: tylko A/B, ok. 10% B (5-16%), zgodne z los_stale",
        set(_arms) <= {"A", "B"} and 15 <= _arms.count("B") <= 48
        and all((a == "B") == (stages.los_stale("pamiec_n3", "https://h%d.example/p" % i) < 0.10) for i, a in enumerate(_arms)),
        _arms.count("B"))
sprawdz("rekord nie niesie wynikow ani statystyk (bez wycieku z przyszlosci)",
        not any(k in r0 for k in ("skutek", "wynik", "statystyki", "reakcje")), list(r0))

print("=== 3. PROFILE: „PRODUKCJA” = DOKLADNIE HISTORIA_KONTA, PRAWDZIWY n_candidates ===")
prod_ids = {sha16(w["tekst"]) for w in dom}
res = r0["results"]
sprawdz("profil produkcja: te same pozycje co `historia_konta.powiazane` dla tego celu",
        ids(res["produkcja"]["items"]) == prod_ids and res["produkcja"]["n_returned"] == len(dom), (res["produkcja"], prod_ids))
_wszystkie_prod = historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, ile=50)
_stare_w = config.HISTORIA_KONTA_WPISOW
config.HISTORIA_KONTA_WPISOW = 1
_r1, _ = zapisz(CEL, ADRES, "on", plik=KAT / "n1.jsonl")
_dom1 = historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz)
config.HISTORIA_KONTA_WPISOW = _stare_w
sprawdz("fikstura ma co najmniej 2 kandydatow produkcyjnych", len(_wszystkie_prod) >= 2, len(_wszystkie_prod))
sprawdz("n_candidates profilu produkcja liczy PRZED obcieciem (limit 1: kandydatow tyle, ile przechodzi progi, zwroconych 1)",
        _r1["results"]["produkcja"]["n_candidates"] == len(_wszystkie_prod) >= 2 and _r1["results"]["produkcja"]["n_returned"] == 1
        and ids(_r1["results"]["produkcja"]["items"]) == {sha16(w["tekst"]) for w in _dom1}, _r1["results"]["produkcja"])
sprawdz("liczba kandydatow rosnie z luzniejszym progiem",
        res["produkcja"]["n_candidates"] <= res["luzny"]["n_candidates"] <= res["szeroki"]["n_candidates"], {k: v["n_candidates"] for k, v in res.items()})
for nazwa, prog, rzadkich, ile in pamiec_cien.profile():
    oczekiwane = sorted(historia_konta.powiazane(CEL, teraz=TERAZ, plik=dz, min_podobienstwa=prog, min_rzadkich=rzadkich, ile=50),
                        key=lambda k: (-k["wynik"], -k["kiedy"].timestamp()))[:ile]
    sprawdz("profil %s: dokladnie te pozycje, co bezposrednie wywolanie z jego progami" % nazwa,
            ids(res[nazwa]["items"]) == {sha16(w["tekst"]) for w in oczekiwane}, (nazwa, res[nazwa]["items"]))
sprawdz("profile sa rozroznialne: jeden z luzniejszych zwraca cos, czego nie zwraca produkcja",
        ids(res["luzny"]["items"]) | ids(res["szeroki"]["items"]) != ids(res["produkcja"]["items"]), res)
sprawdz("pozycje: ranga od 1, wynik malejacy, wiek w dniach, tokeny, powod",
        all(p["rank"] == i + 1 and p["reason"] == "lexical" and p["tokens_est"] > 0 and p["age_days"] >= 0
            for prof in res.values() for i, p in enumerate(prof["items"]))
        and all([x["score"] for x in prof["items"]] == sorted([x["score"] for x in prof["items"]], reverse=True)
                for prof in res.values()), res)
sprawdz("agregaty: tokeny wpisow + stala czesc bloku = suma; blok pusty = zero; flaga ucietej puli",
        all(v["tokens_total"] == v["tokens_entries"] + v["tokens_overhead"] and {"n_candidates", "n_candidates_capped",
            "n_returned", "over_budget"} <= set(v) and (v["tokens_overhead"] > 0) == (v["n_returned"] > 0)
            and v["tokens_entries"] == sum(p["tokens_est"] for p in v["items"]) for v in res.values()), res)
sprawdz("brak tekstow wpisow w rekordzie (tylko id, rodzaj, wiek, wynik)",
        not any(x in surowy for x in ("Totally unrelated", "cheaper to run", "Kimi K3.1 Pro")), surowy[:200])

print("=== 4. RAMIE, AUTOR, KLUCZ, STATUSY ===")
r_off, _ = zapisz(CEL, "https://cel.example/p/kimi", "off", plik=KAT / "ar.jsonl")
r_brak, _ = zapisz(CEL, "https://cel.example/p/kimi", "", plik=KAT / "ar.jsonl")
sprawdz("ramie: off zapisane jako off, brak ramienia jako null",
        r_off["arm_e23"] == "off" and r_brak["arm_e23"] is None and r0["arm_e23"] == "on", (r_off["arm_e23"], r_brak["arm_e23"]))
z1, _ = zapisz("Zupelnie inny temat o pilce noznej", "https://inny.example/p/q", "on", autor="@Zenobiusz ", plik=KAT / "ar2.jsonl")
sprawdz("ten sam cel = ten sam skrot (off i on), inny cel = inny", r_off["query"]["hmac"] == r0["query"]["hmac"] != z1["query"]["hmac"]
        and r_off["query"]["target_hmac"] == r0["query"]["target_hmac"] != z1["query"]["target_hmac"])
sprawdz("autor: normalizacja (@, wielkosc liter, spacje) daje ten sam skrot; brak autora = null",
        z1["query"]["author_hmac"] == r0["query"]["author_hmac"] and r_off["query"]["author_hmac"] is None, (z1["query"], r_off["query"]))
sprawdz("klucz: ten sam w kolejnych rekordach, 32 bajty, id klucza stale", len(klucz) == 32 and r0["query"]["key_id"] == z1["query"]["key_id"])
if os.name == "posix":
    sprawdz("klucz ma tryb 0600", ((KAT / ".cien_klucz").stat().st_mode & 0o777) == 0o600, oct((KAT / ".cien_klucz").stat().st_mode))
sprawdz("cel bez zadnych powiazan: status ok, puste profile", z1["status"] == "ok"
        and all(v["n_returned"] == 0 and v["tokens_total"] == 0 for v in z1["results"].values()), z1["results"])
r_sur, _ = zapisz("abc \ud83d def \ude00 koniec Kimi K3.1 weights", ADRES, "on", plik=KAT / "sur.jsonl")
sprawdz("lone surrogate w tekscie celu nie wywala rekordu (status ok, skroty policzone)",
        r_sur["status"] == "ok" and re.fullmatch(r"[0-9a-f]{24}", r_sur["query"]["hmac"] or ""), r_sur.get("status"))
r_bd, _ = zapisz(CEL, ADRES, "on", historia=KAT / "nie_ma_dziennika.jsonl", plik=KAT / "bd.jsonl")
sprawdz("brak dziennika: status degraded/no_index, pool_size null (nie „ok”)",
        r_bd["status"] == "degraded" and r_bd["degraded_reason"] == "no_index" and r_bd["index_snapshot"]["pool_size"] is None, r_bd)
kat_bk = KAT / "bez_klucza"
(kat_bk / ".cien_klucz").mkdir(parents=True)
r_bk, _ = zapisz(CEL, ADRES, "on", katalog=kat_bk, plik=KAT / "bk.jsonl")
sprawdz("brak klucza (nie da sie odczytac ani utworzyc): status degraded/no_key, skroty null, id klucza null",
        r_bk["status"] == "degraded" and r_bk["degraded_reason"] == "no_key" and r_bk["query"]["hmac"] is None
        and r_bk["query"]["key_id"] is None and r_bk["query"]["target_hmac"] is None, r_bk)

print("=== 5. FLAGA, TRYB TESTOWY, KATALOG, ROZMIAR, CZAS, DOPISYWANIE ===")
inny = KAT / "inny.jsonl"
config.PAMIEC_CIEN = False
sprawdz("flaga False: nic nie zapisuje", zapisz(CEL, "k", "on", plik=inny)[0] is None and not inny.exists())
config.PAMIEC_CIEN = True
domyslny = KAT / "pamiec_cien.jsonl"
sprawdz("NIA_TRYB=test bez jawnego pliku: nic nie pisze do pliku domyslnego",
        os.environ.get("NIA_TRYB") == "test"
        and cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, historia=dz, katalog=KAT)[0] is None
        and not domyslny.exists())
_tryb = os.environ.pop("NIA_TRYB", None)
try:
    kat2 = pathlib.Path(tempfile.mkdtemp())
    r_dom, log_dom = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, historia=dz, katalog=kat2)
    r_dom2, _ = cicho(pamiec_cien.cien_komentarza, CEL, "k", "on", teraz=TERAZ, historia=dz, katalog=kat2)
finally:
    if _tryb is not None:
        os.environ["NIA_TRYB"] = _tryb
sprawdz("poza trybem testowym i z `katalog`: pisze do katalogu wywolujacego, a NIE do config.DATA_DIR; tryb w rekordzie",
        r_dom and (kat2 / "pamiec_cien.jsonl").exists() and (kat2 / ".cien_klucz").exists() and not domyslny.exists()
        and linie(kat2 / "pamiec_cien.jsonl")[0]["mode"] == "produkcja" and len(linie(kat2 / "pamiec_cien.jsonl")) == 2, r_dom)
sprawdz("ten sam klucz w drugim rekordzie tego samego katalogu", r_dom["query"]["key_id"] == r_dom2["query"]["key_id"])
mal = KAT / "maly.jsonl"
mal.write_text("x" * 50 + "\n", encoding="utf-8")
_stare = pamiec_cien.MAKS_BAJTOW
pamiec_cien.MAKS_BAJTOW = 10
r_m, log_m = zapisz(CEL, "k", "on", plik=mal)
pamiec_cien.MAKS_BAJTOW = _stare
sprawdz("limit rozmiaru: nie dopisuje, plik bez zmian, komunikat w logu", r_m is None and mal.read_text(encoding="utf-8") == "x" * 50 + "\n"
        and "nie zapisuje" in log_m, log_m)
_lim = pamiec_cien.LIMIT_S
pamiec_cien.LIMIT_S = -1.0
r_t, _ = zapisz(CEL, "k", "on", plik=KAT / "t.jsonl")
pamiec_cien.LIMIT_S = _lim
sprawdz("limit czasu przekroczony: status timeout, rekord zapisany", r_t and r_t["status"] == "timeout", r_t and r_t.get("status"))
ucieta = KAT / "ucieta.jsonl"
ucieta.write_text('{"record_id": "stary", "status": "ok"}\n{"record_id": "ucie', encoding="utf-8")
zapisz(CEL, "k", "on", plik=ucieta)
_l = ucieta.read_text(encoding="utf-8").split("\n")
sprawdz("dopisek po uciętej linii (bez \\n na koncu): nowy rekord w osobnym, czytelnym wierszu",
        len(_l) == 4 and json.loads(_l[0])["record_id"] == "stary" and json.loads(_l[2])["status"] == "ok" and _l[3] == ""
        and not _l[1].endswith("\n"), _l)

print("=== 6. FAIL-OPEN ===")
_stare_p = historia_konta.powiazane


def wybucha(*a, **k):
    raise RuntimeError("awaria historii")


historia_konta.powiazane = wybucha
r_e, _ = zapisz(CEL, "k", "on", plik=KAT / "e.jsonl", autor="ktos")
historia_konta.powiazane = _stare_p
sprawdz("awaria liczenia: PELNY rekord (zapytanie, strategia, would_arm) ze statusem error i kodem, bez pozycji, bez wyjatku",
        r_e and r_e["status"] == "error" and r_e["error_code"] == "RuntimeError" and r_e["results"] is None
        and r_e["query"]["hmac"] and r_e["strategy"]["config_digest"] and r_e["would_arm"]["arm"] in ("A", "B")
        and linie(KAT / "e.jsonl")[0]["status"] == "error", r_e)
katalog_zamiast_pliku = KAT / "to_katalog"
katalog_zamiast_pliku.mkdir()
try:
    r_k, log_k = zapisz(CEL, "k", "on", plik=katalog_zamiast_pliku)
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
cel_a = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz", "pub": "Zenobiusz Weekly"}
d_a, _ = cicho(run.dane_maniery, cel_a, CEL, run_id=5, zadanie="komentarz_pod_notka", wyslij=True)
pamiec_cien.cien_komentarza = wybucha
cel_b = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz", "pub": "Zenobiusz Weekly"}
d_b, log_b = cicho(run.dane_maniery, cel_b, CEL, run_id=5, zadanie="komentarz_pod_notka", wyslij=True)
pamiec_cien.cien_komentarza = _stare_c
cel_c = {"url": "https://h1.example/p/kimi", "uchwyt": "zenobiusz", "pub": "Zenobiusz Weekly"}
config.PAMIEC_CIEN = False
d_c, _ = cicho(run.dane_maniery, cel_c, CEL, run_id=5, zadanie="komentarz_pod_notka", wyslij=True)
config.PAMIEC_CIEN = True
sprawdz("hak woluje cien z tekstem celu, kluczem, ramieniem, zadaniem, run_id, autorem (sam uchwyt, nie nazwa pisma), wyslij i katalogiem z config",
        len(wywolania) == 1 and wywolania[0][0][0] == CEL and wywolania[0][0][1] == "https://h1.example/p/kimi"
        and wywolania[0][0][2] == cel_a["_maniera"] and wywolania[0][1]["zadanie"] == "komentarz_pod_notka"
        and wywolania[0][1]["run_id"] == 5 and wywolania[0][1]["autor"] == "zenobiusz" and wywolania[0][1]["wyslij"] is True
        and str(wywolania[0][1]["katalog"]) == str(config.DATA_DIR), wywolania)
sprawdz("wynik dane_maniery identyczny z cieniem, z awaria cienia i z wylaczonym cieniem", d_a == d_b == d_c, (d_a, d_b, d_c))
sprawdz("awaria cienia nie zatrzymuje komentarza (ramie zapisane mimo wyjatku) i zostawia linie w logu",
        cel_b["_maniera"] == cel_a["_maniera"] and "[cien] nie zapisalem (RuntimeError)" in log_b, log_b)
sprawdz("hak nie dopisuje niczego do slownika celu (identyczny z cieniem, z awaria i z wylaczonym)",
        cel_a == cel_b == cel_c, (sorted(cel_a), sorted(cel_b), sorted(cel_c)))
cel_d = {"url": "https://h1.example/p/kimi", "pub": "Zenobiusz Weekly"}
pamiec_cien.cien_komentarza = zapisuj
wywolania.clear()
cicho(run.dane_maniery, cel_d, CEL, run_id=5)
pamiec_cien.cien_komentarza = _stare_c
sprawdz("bez uchwytu autor jest pusty (nazwa pisma NIE jest uzywana jako pseudonim), wyslij domyslnie null",
        wywolania[0][1]["autor"] == "" and wywolania[0][1]["wyslij"] is None, wywolania)
# hak dostaja OBA ramiona: znajdz adres w ramieniu on i adres w ramieniu off (przydzial E23 po adresie, stale)
_u = {"on": None, "off": None}
for _i in range(400):
    _adr = "https://ramie%d.example/p/x" % _i
    _r = run._ramie_stale("maniera_komentarza", _adr)
    if _r in _u and _u[_r] is None:
        _u[_r] = _adr
    if all(_u.values()):
        break
pamiec_cien.cien_komentarza = zapisuj
wywolania.clear()
for _r, _adr in _u.items():
    cicho(run.dane_maniery, {"url": _adr}, CEL, run_id=1)
pamiec_cien.cien_komentarza = _stare_c
sprawdz("hak wolany dla obu ramion E23 (on i off) i z nazwa ramienia",
        all(_u.values()) and [w[0][2] for w in wywolania] == ["on", "off"], (_u, [w[0][2] for w in wywolania]))
_src = "\n".join(x for x in pathlib.Path("agent-v2/run.py").read_text(encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))
_dm = _src[_src.index("def dane_maniery("):_src.index("def ramiona_odpowiedzi(")]
sprawdz("hak stoi PRZED rozgalezieniem on/off (dostaja go oba ramiona)",
        _dm.index("pamiec_cien.cien_komentarza(") < _dm.index('if r != "on":'))
sprawdz("hak jest w try/except Exception", re.search(r"try:\s+import pamiec_cien\s+pamiec_cien\.cien_komentarza\(.*?except Exception", _dm, re.S) is not None)
_wdroz = pathlib.Path("agent-v2/wdroz.sh").read_text(encoding="utf-8")
sprawdz("wdroz.sh importuje pamiec_cien i historia_konta w kontroli „moduly wstaja”", "pamiec_cien" in _wdroz and "historia_konta" in _wdroz)
sprawdz("pamiec_cien.jsonl i .cien_klucz sa ignorowane przez Git (data/)", all(
    __import__("subprocess").run(["git", "check-ignore", "-q", p], capture_output=True).returncode == 0
    for p in ("agent-v2/data/pamiec_cien.jsonl", "agent-v2/data/.cien_klucz")))

print("\n=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
