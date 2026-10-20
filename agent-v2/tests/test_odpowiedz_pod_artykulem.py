# -*- coding: utf-8 -*-
"""Odpowiedz pod komentarzem pod NASZYM artykulem: pole i przycisk z formularza pod
komentarzem, tylko aktywny przycisk, limit dwoch prob (20.10.2026).

WADA. `browser.wystaw_odpowiedz_pod_artykulem` wpisywala tekst w
`page.locator("textarea").first`, a pierwsza na stronie jest GLOWNA ramka
„Write a comment..." nad komentarzami. Sonda z 20.10 (`robocze/sonda_odpowiedz_artykul.py`,
na zywej stronie, nic nie wpisane): przed kliknieciem „Reply" jedna forma, po nim
druga — z wlasnym polem i wlasnym „Reply" (submit, wylaczony, dopoki pole jest
puste). Od 18.10 dziewiec prob z rzedu: tekst do glownej ramki, klik czekal 30 s
na wylaczony „Reply", w kazdym przebiegu wywolanie modelu i przerwa rytmu.

DRUGA WADA TEJ SAMEJ FUNKCJI, znaleziona przy pisaniu tego testu: przycisk
odpowiedzi wybierany jako NAJBLIZSZY nazwisku autora. Przy dwoch komentarzach
najblizszy bywa „Reply" POPRZEDNIEGO — stoi tuz nad nazwiskiem, a wlasny jest pod
trescia. Teraz kandydat musi stac ponizej autora.

Test mierzy ZACHOWANIE na prawdziwej przegladarce (Chromium bez okna) i atrapie
strony z dwoma komentarzami i glowna ramka. KONTRDOWOD jest odtworzony, nie
opisany: ten sam scenariusz przechodzi przez `browser.py` z commita `42c7d45`
(sprzed poprawki), wczytany jako osobny modul.

BEZ PYTESTA, zero sieci zewnetrznej i zero modelu; dziennik w katalogu tymczasowym.
Z korzenia repo:  python agent-v2/tests/test_odpowiedz_pod_artykulem.py
"""
import functools
import http.server
import json
import pathlib
import socketserver
import subprocess
import sys
import tempfile
import threading
import types

sys.path.insert(0, "agent-v2")
import config  # noqa: E402

KATALOG = pathlib.Path(tempfile.mkdtemp(prefix="nie-odp-artykul-"))
STARE_SCIEZKI = config.uzyj_katalogu_danych(KATALOG) if hasattr(config, "uzyj_katalogu_danych") else None
import browser  # noqa: E402
import run      # noqa: E402

KORZEN = pathlib.Path(__file__).resolve().parents[2]
ODNIESIENIE = "42c7d45"          # browser.py SPRZED poprawki, przypiety do SHA
TEKST = "Two concrete points about the tripwire."

zdane = oblane = 0


def sprawdz(nazwa, warunek, szczegol=""):
    global zdane, oblane
    if warunek:
        zdane += 1
        print("  OK    %s" % nazwa)
    else:
        oblane += 1
        print("  BLAD  %s   %s" % (nazwa, szczegol))


# --- ATRAPA STRONY ARTYKULU ----------------------------------------------------
# Uklad jak na zywo (sonda 20.10): glowna forma z polem „Write a comment..." na
# gorze; „Reply" przy komentarzu to DIV (nie przycisk), ktory dokleja pod
# komentarzem druga forme z polem, „Cancel" i wylaczonym „Reply" (submit).
# Tresc komentarzy jest dluga, wiec „Reply" pierwszego komentarza stoi BLIZEJ
# nazwiska drugiego autora niz jego wlasny.
STRONA = """<!doctype html><html><head><meta charset="utf-8"><style>
body{font:16px sans-serif;width:700px;margin:8px}
.comment{margin:10px 0;padding:6px;border:1px solid #ccc}
.tekst{min-height:140px}
</style></head><body>
<h1>Artykul</h1>
<form id="glowna"><textarea placeholder="Write a comment..."></textarea>
<button type="submit" id="post" style="display:none">Post</button></form>
<div class="comment" id="c1"><div class="kto"><a>Inny Czytelnik</a></div>
<div class="tekst">Pierwszy komentarz.</div><div class="reply-trigger">Reply</div></div>
<div class="comment" id="c2"><div class="kto"><a>NIA</a></div>
<div class="tekst">Drugi komentarz.</div><div class="reply-trigger">Reply</div></div>
<ul id="wyslane"></ul>
<script>%s</script>
<script>
const g = document.querySelector('#glowna textarea');
const post = document.getElementById('post');
g.addEventListener('input', () => { post.style.display = g.value ? '' : 'none'; });
document.getElementById('glowna').addEventListener('submit', e => {
  e.preventDefault(); zapisz('GLOWNA', g.value); });
document.querySelectorAll('.reply-trigger').forEach(t => t.addEventListener('click', () => {
  const c = t.closest('.comment');
  if (c.querySelector('form') || window.BEZ_FORMULARZA) return;
  const f = document.createElement('form');
  f.innerHTML = '<textarea placeholder="Write a comment..."></textarea>' +
                '<button type="button">Cancel</button><button type="submit" disabled>Reply</button>';
  c.appendChild(f);
  const ta = f.querySelector('textarea'), sb = f.querySelector('button[type=submit]');
  ta.addEventListener('input', () => { if (!window.ZAWSZE_WYLACZONY) sb.disabled = !ta.value; });
  f.addEventListener('submit', e => { e.preventDefault(); zapisz('ODPOWIEDZ:' + c.id, ta.value); });
}));
function zapisz(gdzie, tekst) {
  const li = document.createElement('li'); li.textContent = gdzie + '|' + tekst;
  document.getElementById('wyslane').appendChild(li); }
</script></body></html>"""

WARIANTY = {"dobry": "", "wylaczony": "window.ZAWSZE_WYLACZONY = true;",
            "bez-formy": "window.BEZ_FORMULARZA = true;"}
WWW = pathlib.Path(tempfile.mkdtemp(prefix="nie-odp-www-"))
for nazwa, skrypt in WARIANTY.items():
    d = WWW / "p" / nazwa / "comments"
    d.mkdir(parents=True)
    (d / "index.html").write_text(STRONA % skrypt, encoding="utf-8")


class _Cichy(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


SERWER = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(_Cichy, directory=str(WWW)))
threading.Thread(target=SERWER.serve_forever, daemon=True).start()
ADRES = "http://127.0.0.1:%d/p/%%s" % SERWER.server_address[1]

try:
    from playwright.sync_api import sync_playwright
    _p = sync_playwright().start()
    _b = _p.chromium.launch()
    _b.close()
    _p.stop()
except Exception as exc:                                   # noqa: BLE001
    print("=== POMINIETY: brak przegladarki do testu (%s) ===" % type(exc).__name__)
    SERWER.shutdown()
    sys.exit(0)

STAN = {}


class _Kontekst:
    """Prawdziwy kontekst Chromium; zapamietuje strone, zeby odczytac jej stan."""

    def __init__(self, ctx):
        self.ctx = ctx

    def new_page(self):
        STAN["page"] = self.ctx.new_page()
        return STAN["page"]


def _stan_strony():
    page = STAN.get("page")
    if page is None or page.is_closed():
        return
    STAN["wyslane"] = page.evaluate(
        "() => [...document.querySelectorAll('#wyslane li')].map(li => li.textContent)")
    STAN["glowna"] = page.evaluate("() => document.querySelector('#glowna textarea').value")
    STAN["formy_pod"] = page.evaluate(
        "() => [...document.querySelectorAll('.comment')].filter(c => c.querySelector('form')).map(c => c.id)")


def przygotuj(modul):
    modul.naprawde_wyslac = lambda wyslij, co: True
    modul.wymagaj_sesji = lambda: None
    modul.SETTLE_MS = 0

    def podlacz():
        p = sync_playwright().start()
        b = p.chromium.launch()
        return p, b, _Kontekst(b.new_context(viewport={"width": 900, "height": 1400}))

    def potwierdz(page, url, tekst):
        _stan_strony()
        return any(x.startswith("ODPOWIEDZ:") and x.endswith(tekst) for x in STAN.get("wyslane", []))

    def dopisz(rodzaj, wynik, **k):
        _stan_strony()          # `finally` zapisuje PRZED zamknieciem strony
        STAN["wpis"] = dict(k, rodzaj=rodzaj, wyslane=wynik.get("wyslane"), blad=wynik.get("blad"))

    modul.podlacz_sie = podlacz
    modul.potwierdz_komentarz = potwierdz
    modul.dopisz_wynik = dopisz
    return modul


def odpowiedz(modul, wariant):
    STAN.clear()
    w = modul.wystaw_odpowiedz_pod_artykulem(ADRES % wariant, "NIA", TEKST, wyslij=True)
    return w, STAN.get("wyslane", []), STAN.get("glowna", ""), STAN.get("wpis", {}), STAN.get("formy_pod", [])


def modul_z_commita(commit):
    proc = subprocess.run(["git", "-C", str(KORZEN), "show", "%s:agent-v2/browser.py" % commit],
                          capture_output=True)
    if proc.returncode != 0:
        print("=== POMINIETE: brak wersji %s w historii gita ===" % commit)
        return None
    m = types.ModuleType("browser_%s" % commit)
    m.__dict__["__name__"] = "browser_%s" % commit
    m.__dict__["__file__"] = "agent-v2/browser.py"
    exec(compile(proc.stdout.decode("utf-8"), "agent-v2/browser.py(%s)" % commit, "exec"), m.__dict__)
    return przygotuj(m)


try:
    przygotuj(browser)

    print("=== 1. ODPOWIEDZ IDZIE DO FORMULARZA POD WLASCIWYM KOMENTARZEM ===")
    w, wyslane, glowna, wpis, formy = odpowiedz(browser, "dobry")
    sprawdz("formularz otwarty pod komentarzem autora, nie pod poprzednim (c1)", formy == ["c2"], formy)
    sprawdz("SEDNO: odpowiedz wyszla pod komentarzem autora (c2), potwierdzona",
            wyslane == ["ODPOWIEDZ:c2|" + TEKST] and w.get("wyslane") is True, (wyslane, w.get("blad")))
    sprawdz("glowna ramka „Write a comment...” zostaje pusta (zadnego komentarza pod artykulem)",
            glowna == "" and not any(x.startswith("GLOWNA") for x in wyslane), (glowna, wyslane))
    sprawdz("wpis w dzienniku niesie znacznik metody (po nim liczy sie limit prob)",
            wpis.get("metoda") == browser.METODA_ODPOWIEDZI_POD_ARTYKULEM, wpis)

    print()
    print("=== 2. NIEAKTYWNY PRZYCISK I BRAK FORMULARZA — BEZPIECZNA PORAZKA ===")
    w, wyslane, glowna, wpis, _ = odpowiedz(browser, "wylaczony")
    sprawdz("przycisk nieaktywny po wpisaniu: jasny blad, nic nie wyszlo",
            "nieaktywny" in str(w.get("blad")) and wyslane == [] and w.get("wyslane") is False,
            (w.get("blad"), wyslane))
    sprawdz("i tekst nie trafil do glownej ramki", glowna == "", glowna)
    w, wyslane, glowna, wpis, _ = odpowiedz(browser, "bez-formy")
    sprawdz("formularz sie nie otworzyl: blad „0 nowych pol”, nic nie wpisane",
            "0 nowych pol" in str(w.get("blad")) and glowna == "" and wyslane == []
            and not w.get("wpisane"), (w.get("blad"), glowna))

    print()
    print("=== 3. KONTRDOWOD: TEN SAM SCENARIUSZ NA KODZIE Z %s ===" % ODNIESIENIE)
    stary = modul_z_commita(ODNIESIENIE)
    if stary is not None:
        ws, wyslane_s, glowna_s, _, formy_s = odpowiedz(stary, "dobry")
        sprawdz("stary kod otwieral formularz pod POPRZEDNIM komentarzem (najblizszy „Reply”)",
                formy_s == ["c1"], formy_s)
        sprawdz("stary kod wpisywal odpowiedz do GLOWNEJ ramki", glowna_s == TEKST, glowna_s)
        sprawdz("i nic nie wysylal (klik w wylaczony „Reply” konczyl sie po 30 s)",
                wyslane_s == [] and ws.get("wyslane") is False and "Timeout" in str(ws.get("blad")),
                (wyslane_s, ws.get("blad")))

    print()
    print("=== 4. LIMIT PROB: DWIE PORAZKI OBECNEJ METODY ===")
    dziennik = KATALOG / "dziennik_limitu.jsonl"
    browser.DZIENNIK = dziennik
    M = browser.METODA_ODPOWIEDZI_POD_ARTYKULEM
    URL = "https://example.substack.com/p/x"

    def wpis_(udane, metoda=M, kid=None, komu="NIA", gdzie=URL):
        d = {"kiedy": "2026-10-20T11:00:00+00:00", "rodzaj": "odpowiedz_pod_artykulem",
             "udane": udane, "gdzie": gdzie, "komu": komu}
        if metoda:
            d["metoda"] = metoda
        if kid:
            d["komentarz_id"] = kid
        return json.dumps(d)

    dziennik.write_text("\n".join([wpis_(False, metoda=None)] * 9) + "\n", encoding="utf-8")
    sprawdz("dziewiec porazek STAREJ metody nie odbiera nowej szansy",
            browser.nieudane_odpowiedzi_pod_artykulem(111, URL, "NIA") == 0)
    dziennik.write_text("\n".join([wpis_(False, kid=111), wpis_(False, kid=111), wpis_(False, kid=222),
                                   wpis_(True, kid=111)]) + "\n", encoding="utf-8")
    sprawdz("liczy porazki nowej metody po numerze komentarza (udane sie nie licza)",
            browser.nieudane_odpowiedzi_pod_artykulem(111, URL, "NIA") == 2
            and browser.nieudane_odpowiedzi_pod_artykulem(222, URL, "NIA") == 1)
    dziennik.write_text("\n".join([wpis_(False), wpis_(False, komu="Ktos")]) + "\n", encoding="utf-8")
    sprawdz("wpis bez numeru: po artykule i autorze",
            browser.nieudane_odpowiedzi_pod_artykulem(None, URL, "NIA") == 1)
    dziennik.write_text("\n".join([wpis_(False, kid=111)] * 2) + "\n", encoding="utf-8")
    c = {"gdzie": "artykul", "id": 111, "url": URL, "autor": "NIA", "pod_czym": "Artykul"}
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()) as _log:
        zablokowana = run.odpowiedz_zablokowana(c)
    sprawdz("SEDNO: po dwoch porazkach komentarz odpada przed wyborem i pisaniem",
            zablokowana and "nie probuje dalej" in _log.getvalue(), _log.getvalue())
    sprawdz("jedna porazka to jeszcze nie blokada",
            not run.odpowiedz_zablokowana(dict(c, id=222)))
    sprawdz("odpowiedzi pod notkami limit nie dotyczy",
            not run.odpowiedz_zablokowana(dict(c, gdzie="notka")))
    sprawdz("limit zapisany w konfiguracji: 2", config.MAKS_NIEUDANYCH_ODPOWIEDZI_POD_ARTYKULEM == 2)

    print()
    print("=== 5. RUN.PY: SITO PRZED WYBOREM, NUMER KOMENTARZA DO DZIENNIKA ===")
    zrodlo = (KORZEN / "agent-v2" / "run.py").read_text(encoding="utf-8")
    i_sito = zrodlo.find("czekaja = [c for c in czekaja if not odpowiedz_zablokowana(c)]")
    i_wybor = zrodlo.find("czekaja = stages.wybierz_do_odpowiedzi(conn, run_id, czekaja)")
    sprawdz("sito zablokowanych stoi PRZED platnym wyborem odpowiedzi", 0 < i_sito < i_wybor, (i_sito, i_wybor))
    sprawdz("odpowiedz pod artykulem przekazuje `komentarz_id`",
            '**({"komentarz_id": c["id"]} if c.get("id") else {})' in zrodlo)
finally:
    SERWER.shutdown()
    if STARE_SCIEZKI is not None and hasattr(config, "przywroc_katalog_danych"):
        config.przywroc_katalog_danych(STARE_SCIEZKI)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
