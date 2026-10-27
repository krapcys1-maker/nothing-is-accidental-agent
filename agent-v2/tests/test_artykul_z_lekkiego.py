# -*- coding: utf-8 -*-
"""Artykul tygodnia z lekkiego sledztwa i rozkminy (27.10.2026): teza z co najmniej dwoma NIEZALEZNYMI zrodlami.

PO CO. Wlasciciel: „artykul z najlepszej rozkminy, z co najmniej dwoma niezaleznymi zrodlami pod teza naglowka”. Do tej
pory kandydata na artykul tygodnia dawal tylko ciezki tor (poziom L/XL, ksiega pytan, rekordy pierwotne); lekki tor i
rozkmina, ktore chodza codziennie, nie mialy jak go uniesc i tydzien szedl artykulem z puli. Test na atrapie `llm.call`
(bez sieci, bez platnych wywolan) pilnuje:
  1. KODU NAD MODELEM: teza liczy sie tylko z co najmniej trzema faktami ZA od co najmniej dwoch roznych WYDAWCOW (domena
     rejestrowana — ten sam wydawca pod trzema adresami to jedno zrodlo), z numerami z karty, warunkiem pomylki i trescia;
  2. promptu tezy (fakty i nasze notatki ZA bariera) oraz awarii (smieci, siec, budzet);
  3. wyboru stanu: rozkmina przed sledztwem, odrzucenie starych, test, juz uzytych i ciezkich; granica kosztu (najwyzej
     `MAKS_STANOW_DO_TEZY` wywolan); wylacznik `ARTYKUL_Z_LEKKIEGO`;
  4. karty dla pisarza: teza jako ustalenie i PIERWSZA hipoteza z dowodami za i przeciw, przeczucia jako „nasze zgadywanie”;
  5. calosci `_artykul_ze_sledztwa`: lekki stan przed pula, znacznik artykulu po publikacji, powrot do puli bez kandydata.

BEZ PYTESTA. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_artykul_z_lekkiego.py
"""
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import llm                    # noqa: E402
import sledztwo               # noqa: E402
import artykul_z_puli as azp  # noqa: E402

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, str(szczegol)[:900]))


def cicho(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()) as log:
        wynik = fn(*a, **k)
    return wynik, log.getvalue()


CONN = sqlite3.connect(":memory:")
WYWOLANIA = []
ODPOWIEDZI = []
_prawdziwy = llm.call


def atrapa(purpose, system, prompt, conn=None, run_id=None, **k):
    WYWOLANIA.append({"purpose": purpose, "prompt": prompt})
    o = ODPOWIEDZI.pop(0) if ODPOWIEDZI else "{}"
    if isinstance(o, BaseException):
        raise o
    return o if isinstance(o, str) else json.dumps(o)


llm.call = atrapa

HOSTY = ["404media.co", "www.reuters.com", "blog.openai.com", "news.ycombinator.com", "www.theverge.com", "arxiv.org",
         "www.wired.com", "latent.space", "www.bbc.co.uk", "techcrunch.com", "www.ft.com", "sansec.io"]


def karta(n=12, hosty=None):
    hosty = hosty or HOSTY
    tw = [{"claim": "Claim number %d about the story, stated plainly." % i, "evidence": "Evidence text %d." % i,
           "url": "https://%s/p/%d" % (hosty[(i - 1) % len(hosty)], i), "kind": "FACT", "as_of": "2026-10-%02d" % (10 + i)}
          for i in range(1, n + 1)]
    return {"confirmed_claims": tw,
            "citable_numbers": [{"value": "12%", "means": "number from claim 1", "url": tw[0]["url"]},
                                {"value": "70%", "means": "number from an unrelated story", "url": "https://elsewhere.example/x"}] if tw else [],
            "not_established": ["Whether claim number 1 about the story, stated plainly, holds beyond the press reports.",
                                "Whether the weights ever ship."],
            "contradictions": ["Claim number 2 about the story, stated plainly, is partly contradicted by the disclosure."],
            "working_thesis": "A thesis about everything this week.", "main_mechanism": "A mechanism across three stories.", "voices": [],
            "parallel_mechanisms": [{"domain": "elections", "mechanism": "A mechanism from a different story about elections."}],
            "sprawdzenie_karty": {"przyjete": n, "do_niepewnych": ["Rejected claim about the PHP release from another story."],
                                  "klasy_zrodel": {"https://elsewhere.example/x": "SECONDARY"}},
            "investigation": {"question": "Q about everything. Hunches to ground or test: PHP hunch; Kimi weights hunch; IPO hunch.",
                              "path": "C:/secret/path.json", "created_at": "2026-10-26", "stop_reason": "done", "cost_usd": 0.5,
                              "assessment": {"hypotheses": [{"h": "A Kimi weights hypothesis from another story."}]}},
            "source_dates": {"newest": "2026-10-26", "oldest": "2026-10-01", "note": ""}}


def stan(rid, typ="rozkmina", dni=1, **k):
    s = {"run_id": str(rid), "kiedy": (datetime.now(timezone.utc) - timedelta(days=dni)).isoformat(), "tryb": "produkcja", "na_serio": True,
         "tryb_badania": "lekkie", "typ": typ, "poziom": {"poziom": "LEKKI", "n_max": 4}, "karta": karta(),
         "katy": [{"rodzaj": "REVEAL", "tekst": "A first note. It makes a point about the story.", "wniosek": "A first note.", "przeslanie": "A first note.",
                   "fakty": [{"claim": "Claim number 1 about the story, stated plainly."}]},
                  {"rodzaj": "MOTIVE", "tekst": "A second note about why the actors chose this.", "wniosek": "A second note.", "przeslanie": "A second note.",
                   "fakty": [{"claim": "Claim number 2 about the story, stated plainly."}]},
                  {"rodzaj": "REVEAL", "tekst": "A third note about a different story altogether.", "wniosek": "A third note.", "przeslanie": "A third note.",
                   "fakty": [{"claim": "Claim number 9 about the story, stated plainly."}]}],
         "wybrana": {"tytul": "Story %s" % rid, "przeczucia": [
             {"mysl": "Anthropic's IPO prices a narrow enterprise rent stream like economy-wide productivity, so concentration is the story.", "pozycje": [1, 2]},
             {"mysl": "Open weights make code transparency a security liability instead of an asset.", "pozycje": [3, 4]}] if typ == "rozkmina" else None},
         "brief": {"title": "Working title %s" % rid, "question": "What is going on?"}, "evidence": [{"url": "https://x.example/e", "text": "e"}]}
    s.update(k)
    return s


def zapisz_stan(s):
    katalog = config.DATA_DIR / azp.KATALOG_SLEDZTW
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / ("%s.json" % s["run_id"])).write_text(json.dumps(s), encoding="utf-8")


def czysc():
    katalog = config.DATA_DIR / azp.KATALOG_SLEDZTW
    for p in katalog.glob("*.json") if katalog.exists() else []:
        p.unlink()
    WYWOLANIA.clear()
    ODPOWIEDZI.clear()


def teza_surowa(**k):
    return dict({"thesis": "Anthropic's IPO prices a narrow enterprise rent stream as if it were economy-wide productivity.",
                 "title": "The rent behind the IPO", "for": [1, 2, 3, 4], "against": [5], "wrong_if": "Customer concentration falls below a tenth of revenue.",
                 "how_sources_combine": "Reuters and 404 Media each show a different part of the same concentration."}, **k)


print("=== 1. DOMENA WYDAWCY I KONTROLA TEZY PRZEZ KOD ===")
sprawdz("domena rejestrowana: podstrony i subdomeny jednego wydawcy to jedno zrodlo; co.uk i com.au zachowuja trzy czlony",
        sledztwo._domena("https://www.news.example.com/a") == "example.com" and sledztwo._domena("https://blog.example.com/b") == "example.com"
        and sledztwo._domena("https://www.bbc.co.uk/x") == "bbc.co.uk" and sledztwo._domena("https://news.site.com.au/y") == "site.com.au"
        and sledztwo._domena("") == "" and sledztwo._domena("nie adres") == "")
sprawdz("KLUCZ WYDAWCY: port, kropka koncowa, dane logowania i wielkosc liter nie tworza drugiego wydawcy",
        len({sledztwo._domena(u) for u in ("https://example.com/a", "https://example.com:8443/b", "https://Example.COM./c", "https://user:pw@www.example.com/d")}) == 1)
sprawdz("KLUCZ WYDAWCY: dwa niezalezne newslettery na substack.com i dwa blogi na github.io to DWOCH wydawcow, a nie jeden",
        sledztwo._domena("https://thezvi.substack.com/p/x") != sledztwo._domena("https://oneusefulthing.substack.com/p/y")
        and sledztwo._domena("https://a.github.io/x") != sledztwo._domena("https://b.github.io/x")
        and sledztwo._domena("https://open.substack.com/pub/thezvi/p/x") == sledztwo._domena("https://thezvi.substack.com/p/z"))
sprawdz("KLUCZ WYDAWCY: serwisy kont (github.com/org, x.com/konto; twitter.com = x.com) rozrozniaja konta; domeny jednego koncernu to jeden wydawca",
        sledztwo._domena("https://github.com/org-a/repo") != sledztwo._domena("https://github.com/org-b/repo")
        and sledztwo._domena("https://twitter.com/alice/status/1") == sledztwo._domena("https://x.com/alice/status/2")
        and sledztwo._domena("https://blog.google/a") == sledztwo._domena("https://deepmind.google/b") == sledztwo._domena("https://research.google/c")
        and sledztwo._domena("https://openai.com/a") == sledztwo._domena("https://chatgpt.com/b")
        and sledztwo._domena("https://www.example.or.jp/a") == "example.or.jp" and sledztwo._domena("https://www.service.gouv.fr/a") == "service.gouv.fr")
sprawdz("KLUCZ WYDAWCY: agregator (Yahoo Finance, feed Euronext) nie jest wydawca", sledztwo._domena("https://live.euronext.com/news/1") == ""
        and sledztwo._domena("https://finance.yahoo.com/news/x") == "" and sledztwo._domena("https://www.reuters.com/x") == "reuters.com")
_tekst = "Customers account for most of the quarterly revenue, the filing says, and five customers alone paid more than two billion dollars"
_bazowe = {"claim": "Concentration claim.", "evidence": _tekst}
sprawdz("KONTRDOWOD: przedruk tego samego fragmentu pod drugim hostem (Reuters i kopia na Euronext/innej domenie) to JEDEN wydawca",
        sledztwo.wydawcy_niezalezni([dict(_bazowe, url="https://www.reuters.com/a"), dict(_bazowe, url="https://copy-site.example/b"),
                                     dict(_bazowe, url="https://www.reuters.com/c")]) == ["reuters.com"])
sprawdz("KONTRDOWOD: przedruk z dopiskiem (ten sam fragment w dluzszym tekscie agregujacej strony) tez liczy sie raz",
        sledztwo.wydawcy_niezalezni([dict(_bazowe, url="https://www.reuters.com/a"),
                                     dict(_bazowe, evidence=_tekst + " plus a good deal of extra commentary words wrapped around the quote by the site that copied it, with more filler vocabulary besides",
                                          url="https://copy-site.example/b")]) == ["reuters.com"])
sprawdz("rozne teksty pod dwoma hostami to dwoch wydawcow",
        len(sledztwo.wydawcy_niezalezni([dict(_bazowe, url="https://www.reuters.com/a"),
                                         {"claim": "Other.", "evidence": "A separate report on how the valuation compares with listed software companies this year", "url": "https://www.ft.com/b"}])) == 2)
sprawdz("KONTRDOWOD: glos, wpis cennika i wszystkie twierdzenia interesowanej strony razem NIE tworza niezaleznych wydawcow",
        sledztwo.wydawcy_niezalezni([{"claim": "Voice.", "evidence": "I think so, one reader wrote", "url": "https://news.ycombinator.com/item?id=1", "kind": "VOICE"},
                                     {"claim": "List.", "evidence": "Price listing text", "url": "https://openrouter.ai/x", "kind": "LISTING"},
                                     {"claim": "Own 1.", "evidence": "The company says one thing here", "url": "https://openai.com/a", "kind": "VENDOR_CLAIM"},
                                     {"claim": "Own 2.", "evidence": "The company says another thing there", "url": "https://other-company.example/b", "kind": "VENDOR_CLAIM"}]) == ["aktor"])
_vendor = [{"claim": "Own %d." % i, "evidence": "The company says thing number %d about itself in its own words" % i,
            "url": "https://%s/p/%d" % (h, i), "kind": "VENDOR_CLAIM"} for i, h in ((1, "openai.com"), (2, "chatgpt.com"), (3, "vendor.example"))]
sprawdz("KONTRDOWOD: trzy twierdzenia jednej firmy z trzech jej domen to jedno zrodlo -> brak tezy",
        sledztwo.oczysc_teze(teza_surowa(**{"for": [1, 2, 3], "against": []}), _vendor) is None)
tw = sledztwo._twierdzenia(karta())
t = sledztwo.oczysc_teze(teza_surowa(), tw)
sprawdz("dobra teza: numery z karty, 4 fakty ZA od 4 wydawcow, przeciw osobno, warunek pomylki, twierdzenia jako tekst",
        t and t["za"] == [1, 2, 3, 4] and t["przeciw"] == [5] and len(t["niezalezne_zrodla"]) == 4
        and t["twierdzenia_za"][0].startswith("Claim number 1") and t["co_obali"].startswith("Customer concentration"), t)
tk = sledztwo.oczysc_teze(teza_surowa(context=[4, 5, 6, 7, 8, 9, 10, 11, 99, "x", 6]), tw)
sprawdz("`context`: tylko numery z karty spoza ZA i PRZECIW, bez dubli, co najwyzej `MAKS_KONTEKSTU_TEZY` (6)",
        tk["kontekst"] == [6, 7, 8, 9, 10, 11] and len(tk["kontekst"]) == sledztwo.MAKS_KONTEKSTU_TEZY, tk["kontekst"])
sprawdz("numery spoza karty, nie-liczby i dubli odpadaja; „przeciw” nie powtarza „za”",
        sledztwo.oczysc_teze(teza_surowa(**{"for": [1, "2", 2, 99, "x", 0, 3], "against": [1, 6, 6]}), tw)["za"] == [1, 2, 3]
        and sledztwo.oczysc_teze(teza_surowa(**{"for": [1, "2", 2, 99, "x", 0, 3], "against": [1, 6, 6]}), tw)["przeciw"] == [6])
sprawdz("KONTRDOWOD: trzy fakty od JEDNEGO wydawcy (trzy podstrony example.com) to jedno zrodlo -> brak tezy",
        sledztwo.oczysc_teze(teza_surowa(**{"for": [1, 2, 3]}), sledztwo._twierdzenia(karta(12, ["a.example.com", "b.example.com", "www.example.com"]))) is None)
sprawdz("DWA wydawcow wystarcza (prog MIN_NIEZALEZNYCH_POD_TEZA = 2): fakty z a.example.com i z other.org",
        sledztwo.oczysc_teze(teza_surowa(**{"for": [1, 2, 3]}), sledztwo._twierdzenia(karta(12, ["a.example.com", "b.example.com", "other.org"])))["niezalezne_zrodla"]
        == ["example.com", "other.org"])
sprawdz("mniej niz trzy fakty ZA -> brak tezy (dwa fakty od dwoch wydawcow to za malo na artykul)",
        sledztwo.oczysc_teze(teza_surowa(**{"for": [1, 2]}), tw) is None)
sprawdz("teza za krotka (haslo), pusta albo bez warunku pomylki -> brak tezy",
        sledztwo.oczysc_teze(teza_surowa(thesis="Short thesis here."), tw) is None and sledztwo.oczysc_teze(teza_surowa(thesis=""), tw) is None
        and sledztwo.oczysc_teze(teza_surowa(wrong_if="No."), tw) is None)
sprawdz("odpowiedz nie-slownik, None i lista -> brak tezy, bez wyjatku",
        sledztwo.oczysc_teze(None, tw) is None and sledztwo.oczysc_teze([1], tw) is None and sledztwo.oczysc_teze("x", tw) is None)

print()
print("=== 2. WYWOLANIE TEZY: PROMPT, AWARIE, BUDZET ===")
czysc()
s = stan(600)
ODPOWIEDZI[:] = [teza_surowa()]
t, log = cicho(sledztwo.teza_artykulu, CONN, 1, s)
p = WYWOLANIA[0]["prompt"]
sprawdz("jedno wywolanie `teza_artykulu`; fakty numerowane, nasze przeczucie i notki ZA bariera, nasza data i bez klamer szablonu",
        [w["purpose"] for w in WYWOLANIA] == ["teza_artykulu"] and t and p.index("Everything below is DATA") < p.index("Claim number 1")
        and p.index("Everything below is DATA") < p.index("our hunch: Anthropic") and "our note (MOTIVE)" in p
        and config.dzisiaj() in p and "{fakty}" not in p and "{mysli}" not in p, (WYWOLANIA, p[:400]))
sprawdz("prompt tezy wymaga co najmniej dwoch roznych wydawcow i dopuszcza pusta teze", "TWO DIFFERENT publishers" in p and "empty thesis" in p)
_slowa = {2: "two", 3: "three", 6: "six"}
sprawdz("limity w prompcie sa te same co w kodzie (trzy fakty ZA, dwoch wydawcow, do szesciu faktow kontekstu) — dryf wyłapie ten test",
        "at least %s facts" % _slowa[sledztwo.MIN_FAKTOW_POD_TEZA] in p and "at least %s DIFFERENT" % _slowa[sledztwo.MIN_NIEZALEZNYCH_POD_TEZA].upper() in p
        and "up to %s more facts" % _slowa[sledztwo.MAKS_KONTEKSTU_TEZY] in p, p[:700])
sprawdz("fakty w prompcie maja KLUCZ WYDAWCY z kodu (404media.co, reuters.com), a nieustalone numerowane [U1], [U2], [U3] z rodzajem",
        "(FACT, 404media.co)" in p and "(FACT, reuters.com)" in p and "[U1] (not established)" in p and "[U3] (contradiction)" in p, p[-900:])
sprawdz("host z poddomena (blog.openai.com) jest w prompcie pod kluczem wydawcy z kodu (rodzina „openai”), nie pod swoim hostem",
        "(FACT, openai)" in p and "blog.openai.com" not in p, p[-1500:])
ODPOWIEDZI[:] = [teza_surowa(unsettled=[1])]
t_uns, _ = cicho(sledztwo.teza_artykulu, CONN, 1, s)
sprawdz("`teza_artykulu` przenosi wskazane przez model zastrzezenie (U1 = pierwsze nieustalone) do tezy", t_uns and t_uns["zastrzezenia"] == [{"lista": "not_established", "nr": 0}], t_uns)
sprawdz("model i limity tokenow etapu `teza_artykulu` sa w configu", config.MODEL_FOR.get("teza_artykulu") and config.MAX_TOKENS.get("teza_artykulu"))
ODPOWIEDZI[:] = ["to nie jest json"] * 3
t, _ = cicho(sledztwo.teza_artykulu, CONN, 1, s)
sprawdz("smieci zamiast JSON-a -> brak tezy, bez wyjatku", t is None)
ODPOWIEDZI[:] = [RuntimeError("siec padla")]
t, log = cicho(sledztwo.teza_artykulu, CONN, 1, s)
sprawdz("awaria sieci -> brak tezy i komunikat", t is None and "siec padla" in log, log)
ODPOWIEDZI[:] = [{"thesis": ""}]
t, log = cicho(sledztwo.teza_artykulu, CONN, 1, s)
sprawdz("pusta teza od modelu = uczciwe „w tym tygodniu nie ma co argumentowac”", t is None and "brak tezy" in log, log)
WYWOLANIA.clear()
t, _ = cicho(sledztwo.teza_artykulu, CONN, 1, stan(601, karta={"confirmed_claims": karta(2)["confirmed_claims"]}))
sprawdz("karta z dwoma faktami: zero wywolan modelu (nie placimy za teze, ktorej nie da sie podeprzec)", t is None and not WYWOLANIA)
_przerywa = sledztwo._przerywaja()
ODPOWIEDZI[:] = [_przerywa[0]("budzet")]
try:
    cicho(sledztwo.teza_artykulu, CONN, 1, s)
    przepuszczony = False
except BaseException as exc:    # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: wyczerpany budzet NIE jest polykany jako „brak tezy”", przepuszczony)

print()
print("=== 3. BRAKI STANU I WYBOR KANDYDATA ===")
sprawdz("dobry stan: zero brakow", azp._braki_stanu_lekkiego(stan(610)) == [])
for opis, zmiana, fragment in (("bez --wyslij", {"na_serio": False}, "bez --wyslij"), ("tryb test", {"tryb": "test"}, "trybie test"),
                               ("stary (6 dni)", {"kiedy": (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()}, "stan sprzed"),
                               ("artykul z tego stanu juz byl", {"artykul": {"kod": 0}}, "juz byl"), ("przerwany", {"przerwane": "budzet"}, "przerwane"),
                               ("mniej niz dwa katy", {"katy": [{"rodzaj": "REVEAL"}]}, "dwa katy"),
                               ("za malo twierdzen", {"karta": karta(6)}, "twierdzen z"),
                               ("za malo serwisow", {"karta": karta(12, ["a.example.com", "b.example.com", "c.example.com"])}, "serwisow")):
    sprawdz("brak: %s" % opis, any(fragment in b for b in azp._braki_stanu_lekkiego(stan(611, **zmiana))), azp._braki_stanu_lekkiego(stan(611, **zmiana)))
sprawdz("stan bez daty -> brak „stan bez daty”", any("bez daty" in b for b in azp._braki_stanu_lekkiego(stan(612, kiedy="zle"))))

czysc()
zapisz_stan(stan(620, "sledztwo", dni=1))
zapisz_stan(stan(621, "rozkmina", dni=2))
ODPOWIEDZI[:] = [teza_surowa(), teza_surowa(**{"for": [1, 2, 3, 4, 5, 6, 7]})]
w, log = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("ROZKMINA przed zwyklym sledztwem (nawet starsza i z mniejsza liczba wydawcow pod teza) — wlasciciel chce artykul z rozkminy",
        w is not None and w["run_id"] == "621" and w["teza_artykulu"]["niezalezne_zrodla"], (w and w["run_id"], log))
sprawdz("kazdy stan platny za teze raz (2 wywolania)", len(WYWOLANIA) == 2, WYWOLANIA)
czysc()
zapisz_stan(stan(630, "rozkmina", dni=1))
zapisz_stan(stan(631, "sledztwo", dni=1))
ODPOWIEDZI[:] = [{"thesis": ""}, teza_surowa()]          # rozkmina bez tezy (kolejnosc: najnowsze pierwsze — sprawdz kolejnosc)
w, log = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("stan bez tezy (uczciwa pusta teza) odpada, a drugi, z teza, zostaje", w is not None and w["teza_artykulu"], (w and w["run_id"], log))
czysc()
zapisz_stan(stan(640, "sledztwo", dni=1))
zapisz_stan(stan(641, "sledztwo", dni=2))
ODPOWIEDZI[:] = [teza_surowa(**{"for": [1, 2, 3, 4]}), teza_surowa(**{"for": [1, 2, 3, 4, 5, 6]})]
w, _ = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("dwa zwykle sledztwa: wygrywa wiecej niezaleznych wydawcow pod teza (6 faktow od 6 wydawcow wobec 4 od 4)",
        w is not None and len(w["teza_artykulu"]["niezalezne_zrodla"]) == 6, w and w["teza_artykulu"])
czysc()
for i in range(7):
    zapisz_stan(stan(650 + i, "sledztwo", dni=1 + i * 0.1))
ODPOWIEDZI[:] = [{"thesis": ""}] * 10
w, _ = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("GRANICA KOSZTU: z siedmiu dobrych stanow teze dostaje najwyzej `MAKS_STANOW_DO_TEZY` (4) najnowszych; brak tezy = brak kandydata",
        w is None and len(WYWOLANIA) == azp.MAKS_STANOW_DO_TEZY == 4, len(WYWOLANIA))
czysc()
zapisz_stan(stan(660, "rozkmina", dni=1, poziom={"poziom": "L"}, tryb_badania="gleboko"))
zapisz_stan(stan(661, "rozkmina", dni=1, tryb="test"))
zapisz_stan(stan(662, "rozkmina", dni=7))
zapisz_stan(stan(663, "rozkmina", dni=1, artykul={"kod": 0}))
w, _ = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("ciezki tor (ocenia go `_kandydat_ze_sledztwa`), tryb test, stan sprzed 7 dni i stan z artykulem nie wchodza i nie kosztuja ani jednej tezy",
        w is None and not WYWOLANIA, (w, WYWOLANIA))
czysc()
zapisz_stan(stan(670, "rozkmina", dni=1))
config.ARTYKUL_Z_LEKKIEGO = False
w, _ = cicho(azp._kandydat_lekki, CONN, 1)
config.ARTYKUL_Z_LEKKIEGO = True
sprawdz("wylacznik `ARTYKUL_Z_LEKKIEGO` = False wraca do starego zachowania (zero wywolan, brak kandydata)", w is None and not WYWOLANIA)
(config.DATA_DIR / azp.KATALOG_SLEDZTW / "zepsuty.json").write_text("{nie json", encoding="utf-8")
(config.DATA_DIR / azp.KATALOG_SLEDZTW / "lista.json").write_text("[1, 2]", encoding="utf-8")
ODPOWIEDZI[:] = [teza_surowa()]
w, _ = cicho(azp._kandydat_lekki, CONN, 1)
sprawdz("zepsute pliki stanu (nie-JSON, lista) sa pomijane, dobry stan nadal wygrywa", w is not None and w["run_id"] == "670")

print()
print("=== 4. KARTA DLA PISARZA ===")
s = stan(680)
s["teza_artykulu"] = sledztwo.oczysc_teze(teza_surowa(unsettled=["U1", 3, "U4", 3]), sledztwo._twierdzenia(s["karta"]), sledztwo.zastrzezenia_karty(s["karta"]))
sprawdz("`unsettled`: numery z listy zastrzezen (z „U” i bez), bez dubli i spoza listy; trafia tam tylko to, co wskazal model",
        s["teza_artykulu"]["zastrzezenia"] == [{"lista": "not_established", "nr": 0}, {"lista": "contradictions", "nr": 0}], s["teza_artykulu"]["zastrzezenia"])
sprawdz("teza bez `unsettled` ma pusta liste zastrzezen (nic nie jest zgadywane slowami)", sledztwo.oczysc_teze(teza_surowa(), tw)["zastrzezenia"] == [])
_z = sledztwo.zastrzezenia_karty({"not_established": ["Item %d is unsettled." % i for i in range(9)], "contradictions": ["C%d clash" % i for i in range(5)],
                                  "uncertain_claims": [{"claim": "D%d doubt" % i} for i in range(5)] + [{}, ""]})
sprawdz("`zastrzezenia_karty`: najwyzej 6 nieustalonych, 3 sprzecznosci i 3 watpliwosci (prompt nie puchnie); wpisy-slowniki czytane po `claim`; puste pomijane",
        [x[0] for x in _z].count("not_established") == 6 and [x[0] for x in _z].count("contradictions") == 3
        and [x[0] for x in _z].count("uncertain_claims") == 3 and _z[-1][2] == "D2 doubt", _z)
brief, card = azp._karta_artykulu(s)
sprawdz("teza idzie jako ustalenie (`investigation_finding`) z faktami ZA, a tytul roboczy zastepuje tytul briefu",
        card["investigation_finding"]["finding"].startswith("Anthropic's IPO prices") and card["investigation_finding"]["claims"]
        and brief["title"] == "The rent behind the IPO" and brief["sledztwo_run_id"] == "680", (brief, card.get("investigation_finding")))
h = card["editorial_hypotheses"]
sprawdz("PIERWSZA hipoteza to teza z dowodami ZA i PRZECIW oraz warunkiem pomylki (ksztalt, ktorego wymaga `pisarz.md`)",
        h[0]["rodzaj"] == "THESIS" and len(h[0]["za"]) == 4 and len(h[0]["przeciw"]) == 1 and h[0]["co_obali"].startswith("Customer concentration"), h[0])
hunche = [x for x in h if x.get("rodzaj") == "HUNCH"]
sprawdz("JEDNO przeczucie, najblizsze tezie, idzie jako JAWNIE nasze zgadywanie; przeczucie o innej historii (otwarte wagi) zostaje poza artykulem",
        len(hunche) == 1 and hunche[0]["zalozenie"] == "our guess, not a fact" and hunche[0]["przeslanie"].startswith("Anthropic's IPO prices"), hunche)
sprawdz("KARTA ZAWEZONA DO TEZY: zostaja tylko fakty ZA (1-4) i PRZECIW (5), a nie wszystkie 12 z trzech historii rozkminy",
        [c["claim"][13:15].strip() for c in card["confirmed_claims"]] == ["1", "2", "3", "4", "5"] and len(card["confirmed_claims"]) == 5,
        [c["claim"] for c in card["confirmed_claims"]])
sprawdz("liczby tylko ze zrodel wybranych faktow (12% zostaje, 70% z cudzej historii odpada)",
        [n["value"] for n in card["citable_numbers"]] == ["12%"], card["citable_numbers"])
sprawdz("nieustalone i sprzecznosci tylko te, ktore wskazal model tezy (o wagach z innej historii nie ma mowy); teza i mechanizm nadpisuja wspolne dla calej karty",
        card["not_established"] == ["Whether claim number 1 about the story, stated plainly, holds beyond the press reports."]
        and len(card["contradictions"]) == 1 and card["uncertain_claims"] == [] and card["working_thesis"].startswith("Anthropic's IPO")
        and "three stories" not in card["main_mechanism"], (card["not_established"], card["working_thesis"], card["main_mechanism"]))
sprawdz("KONTRDOWOD (stary filtr slow): wlasne zastrzezenie o tej samej sprawie, ale innymi slowami niz fakty, ZOSTAJE, gdy model je wskazal",
        azp._karta_artykulu(dict(s, karta=dict(s["karta"], not_established=["Whether the valuation multiple holds once the lock-up period ends is unknown.", "Whether the weights ever ship."]),
                                 teza_artykulu=dict(s["teza_artykulu"], zastrzezenia=[{"lista": "not_established", "nr": 0}])))[1]["not_established"]
        == ["Whether the valuation multiple holds once the lock-up period ends is unknown."])
tekst_karty = json.dumps(card)
sprawdz("KONTRDOWOD (rozlew): w karcie pisarza nie ma przeczuc ani hipotez badania o PHP/Kimi/wyborach, sciezki pliku, mechanizmu z wyborow ani odrzuconych twierdzen z innych zrodel",
        "PHP hunch" not in tekst_karty and "Kimi weights" not in tekst_karty and "secret/path" not in tekst_karty and "elections" not in tekst_karty
        and "PHP release" not in tekst_karty and "elsewhere.example" not in tekst_karty, [k for k in ("PHP hunch", "Kimi", "secret", "elections", "PHP release", "elsewhere") if k in tekst_karty])
sprawdz("pytanie badania w karcie to TEZA; parallel_mechanisms puste; sprawdzenie_karty usuniete",
        card["investigation"]["question"].startswith("Anthropic's IPO prices") and "assessment" not in card["investigation"] and card["parallel_mechanisms"] == []
        and "sprawdzenie_karty" not in card, (card.get("investigation"), card.get("parallel_mechanisms")))
sprawdz("daty zrodel przeliczone z twierdzen tezy (1-5): najstarsze 2026-10-11, najnowsze 2026-10-15; notatka o wieku zostaje",
        card["source_dates"]["oldest"] == "2026-10-11" and card["source_dates"]["newest"] == "2026-10-15" and "note" in card["source_dates"], card["source_dates"])
sprawdz("katy serii (`investigation_angles`) tylko z notek, ktore stoja na faktach tezy (dwie z trzech; trzecia o innej historii odpada)",
        len(card["investigation_angles"]) == 2 and all("third" not in str(a) for a in card["investigation_angles"]), card.get("investigation_angles"))
s2 = stan(681, "sledztwo")
brief2, card2 = azp._karta_artykulu(s2)
sprawdz("stan bez tezy (ciezki tor) dostaje karte jak dotad: wszystkie 12 faktow, bez `investigation_finding` z tezy, bez hipotez THESIS i HUNCH",
        "investigation_finding" not in card2 and not [x for x in card2["editorial_hypotheses"] if x.get("rodzaj") in ("THESIS", "HUNCH")]
        and len(card2["confirmed_claims"]) == 12 and brief2["title"] == "Working title 681", (brief2, card2.get("investigation_finding")))
s3 = stan(682)
s3["teza_artykulu"] = s["teza_artykulu"]
s3["nowosc"] = {"jest": True, "ustalenie": "A finding from the deep path.", "powod": "Because.", "twierdzenia": [1, 2]}
_, card3 = azp._karta_artykulu(s3)
sprawdz("ustalenie z ciezkiego toru ma pierwszenstwo przed teza (`investigation_finding` nie jest nadpisane)",
        card3["investigation_finding"]["finding"] == "A finding from the deep path.", card3["investigation_finding"])

print()
print("=== 5. CALOSC: `_artykul_ze_sledztwa` ===")
czysc()
zapisz_stan(stan(690, "rozkmina", dni=1))
ZAPISANE = []
OZNACZONE = []
_napisz = azp._napisz_i_zapisz
_ciezki = azp._kandydat_ze_sledztwa
_oznacz = sledztwo.oznacz_artykul
azp._kandydat_ze_sledztwa = lambda w_tescie=False: None
sledztwo.oznacz_artykul = lambda rid: OZNACZONE.append(rid)


def atrapa_pisarza(conn, run_id, brief, card, evidence=None):
    ZAPISANE.append({"brief": brief, "card": card, "evidence": evidence})
    return 0


azp._napisz_i_zapisz = atrapa_pisarza
stare_argv = sys.argv
sys.argv = ["x", "--wyslij"]
ODPOWIEDZI[:] = [teza_surowa()]
try:
    kod, log = cicho(azp._artykul_ze_sledztwa, CONN, 5)
finally:
    sys.argv = stare_argv
sprawdz("brak ciezkiego kandydata: lekki stan z rozkmina idzie do pisarza (kod 0), z karta z teza i dowodami",
        kod == 0 and len(ZAPISANE) == 1 and ZAPISANE[0]["card"]["investigation_finding"]["finding"].startswith("Anthropic")
        and ZAPISANE[0]["evidence"] and "BIORE sledztwo 690" in log, (kod, log))
stan_po = json.loads((config.DATA_DIR / azp.KATALOG_SLEDZTW / "690.json").read_text(encoding="utf-8"))
sprawdz("po artykule stan dostaje znacznik `artykul` (nie wroci w przyszlym tygodniu), a sledztwo liczy artykul do limitu tygodnia",
        stan_po.get("artykul", {}).get("kod") == 0 and OZNACZONE == ["690"], (stan_po.get("artykul"), OZNACZONE))
ZAPISANE.clear()
WYWOLANIA.clear()
ODPOWIEDZI[:] = []
kod, log = cicho(azp._artykul_ze_sledztwa, CONN, 6)
sprawdz("stan z artykulem jest zuzyty: brak kandydata -> None (artykul z puli, jak dotad) i ZERO wywolan modelu",
        kod is None and not ZAPISANE and not WYWOLANIA and "artykul z puli" in log, (kod, log))
czysc()
zapisz_stan(stan(691, "rozkmina", dni=1))
ODPOWIEDZI[:] = [{"thesis": ""}]
kod, log = cicho(azp._artykul_ze_sledztwa, CONN, 7)
sprawdz("rozkmina bez tezy z dwoma wydawcami: nie piszemy artykulu z jednego zrodla — wraca pula", kod is None and not ZAPISANE, (kod, log))
czysc()
zapisz_stan(stan(692, "rozkmina", dni=1))
ODPOWIEDZI[:] = [_przerywa[0]("budzet")]
try:
    cicho(azp._artykul_ze_sledztwa, CONN, 8)
    przepuszczony = False
except BaseException as exc:    # noqa: BLE001
    przepuszczony = isinstance(exc, _przerywa)
sprawdz("KONTRDOWOD: wyczerpany budzet przy wyborze tezy przechodzi przez `_artykul_ze_sledztwa` (nie jest podmieniany na pule)", przepuszczony)
azp._napisz_i_zapisz = _napisz
azp._kandydat_ze_sledztwa = _ciezki
sledztwo.oznacz_artykul = _oznacz
llm.call = _prawdziwy
print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
