# -*- coding: utf-8 -*-
"""Cele wywolan, modele, ceny i prompty sledztwa — fala 1 (25.10.2026).

PO CO (spec §9 pkt 2). `llm.call` na celu, ktorego nie ma w `config.MODEL_FOR`,
rzuca `KeyError`, a ogolne `except` w przebiegu sledztwa puszczalo wtedy po cichu
stara sciezke — oplacone etapy szly do kosza. Jeden niepodwojony nawias w prompcie
dawal to samo: `str.format` pada, etap pada, zostaje zapas. Proba na kopii danych
25.10 pisala innym modelem niz produkcja, a w `calls` nie bylo sladu, bo kolumna
`model` mowi, o co PROSILISMY, nie co odpowiedzialo.

Test pilnuje, kazde z kontrdowodem:
  1. kazdy LITERAL celu podany do `llm.call` / `llm.ratuj_json` / `research._call`
     w calym `agent-v2/*.py` (oraz `etap="..."` i `etap_pisarza = "..."`) jest
     w `MODEL_FOR` i `MAX_TOKENS` — skaner widzi to, co ma widziec (kontrdowod
     na sztucznym zrodle);
  2. cele z kontraktu fali 1 maja model, sufit, wysilek (Claude) i myslenie
     (DeepSeek) dokladnie wedlug tabeli; `llm.call` w DRY_RUN przechodzi na kazdym;
  3. kazdy prompt z `prompts/` renderuje sie przez `str.format` z atrapami pol;
     karta artykulu dostaje prompt bez trybu sledczego;
  4. `effort` idzie wedlug dostawcy i rodziny, nie rownosci ze stala;
  5. model zwrocony przez API laduje w `calls.model_served` (migracja idempotentna);
  6. ceny Opusa 5.5, Sonneta 5.5 i Fable 5.1 potwierdzone; sprawdzenie modeli sledztwa;
  7. `llm.call(max_szukan=...)` dociera do transportu, bez niego atrapy dzialaja jak dotad.

BEZ PYTESTA, bez sieci, bez platnych wywolan. Uruchamiac z korzenia repozytorium:
    NIA_TRYB=test PYTHONIOENCODING=utf-8 python agent-v2/tests/test_cele_modeli.py
"""
import ast
import contextlib
import io
import pathlib
import sqlite3
import string
import sys
import tempfile

sys.path.insert(0, "agent-v2")
import config   # noqa: E402

config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))

import db       # noqa: E402
import llm      # noqa: E402
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


KORZEN = pathlib.Path("agent-v2")


def cele_w_zrodle(tekst, nazwa_pliku):
    """{cel: [miejsca]} — literaly celow z drzewa skladni jednego pliku."""
    out = {}

    def dodaj(cel, wezel):
        out.setdefault(cel, []).append("%s:%d" % (nazwa_pliku, wezel.lineno))

    for w in ast.walk(ast.parse(tekst)):
        if isinstance(w, ast.Call):
            f = w.func
            nazwa = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            baza = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
            arg = None
            if nazwa in ("call", "ratuj_json") and (baza == "llm" or (nazwa_pliku == "llm.py" and not baza)):
                arg = w.args[0] if w.args else None
            elif nazwa == "_call" and (baza == "research" or (nazwa_pliku == "research.py" and not baza)):
                arg = w.args[2] if len(w.args) > 2 else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                dodaj(arg.value, w)
            # `etap="naprawa"` przy `napraw_obalone`, `note`, `przenies_zastrzezenie`
            # (`purpose=` NIE: tak nazywa sie tez kolumna w `db.record_call`).
            for kw in w.keywords:
                if kw.arg == "etap" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    dodaj(kw.value.value, w)
        elif isinstance(w, ast.Assign) and isinstance(w.value, ast.Constant) \
                and isinstance(w.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == "etap_pisarza" for t in w.targets):
                dodaj(w.value.value, w)
    return out


print("=== 1. KAZDY LITERAL CELU MA MODEL I SUFIT ===")
CELE = {}
for p in sorted(KORZEN.glob("*.py")):
    for cel, gdzie in cele_w_zrodle(p.read_text(encoding="utf-8"), p.name).items():
        CELE.setdefault(cel, []).extend(gdzie)
for cel in config.PISARZE_NOTEK:
    CELE.setdefault(cel, []).append("config.PISARZE_NOTEK")
sprawdz("skaner znalazl cele w kodzie (co najmniej 30)", len(CELE) >= 30, sorted(CELE))
for cel in ("przeslania", "notka_przeslania", "notka_przeslania_fakt", "wiernosc_notki",
            "factcheck", "synthesis", "naprawa"):
    sprawdz("skaner widzi %r" % cel, cel in CELE, sorted(CELE))
bez_modelu = sorted("%s (%s)" % (c, g[0]) for c, g in CELE.items() if c not in config.MODEL_FOR)
bez_sufitu = sorted("%s (%s)" % (c, g[0]) for c, g in CELE.items()
                    if c not in config.MAX_TOKENS and c not in config.BEZ_TOKENOW)
sprawdz("kazdy cel z kodu jest w MODEL_FOR", not bez_modelu, bez_modelu)
sprawdz("kazdy cel z kodu ma sufit w MAX_TOKENS", not bez_sufitu, bez_sufitu)
# KONTRDOWOD: skaner lapie cel, ktorego nie ma — z kazdej z trzech drog.
SZTUCZNY = (
    "import llm, research\n"
    "def f(conn):\n"
    "    llm.call('nie_ma_takiego_celu', 's', 'u', conn=conn)\n"
    "    research._call(conn, 1, 'nie_ma_tez_tego', 'p')\n"
    "    llm.ratuj_json('i_tego', 't', '{}', conn=conn)\n"
    "    etap_pisarza = 'ani_tego'\n")
_sztuczne = cele_w_zrodle(SZTUCZNY, "sztuczny.py")
sprawdz("KONTRDOWOD: skaner widzi cel spoza tabel z kazdej drogi",
        {"nie_ma_takiego_celu", "nie_ma_tez_tego", "i_tego", "ani_tego"} <= set(_sztuczne)
        and not any(c in config.MODEL_FOR for c in _sztuczne), _sztuczne)

print()
print("=== 2. CELE Z KONTRAKTU FALI 1 WEDLUG TABELI ===")
H = config.THINKING_HEADROOM_TOKENS
# cel: (model, sufit dokladny albo None = „co najmniej", sufit bazowy, effort, myslenie)
KONTRAKT = {
    "pytania_ciekawosci": (config.SONNET, 8000 + H, "medium", None),
    "pytania_ciekawosci_zapas": (config.DEEPSEEK, 8000 + H, None, "enabled"),
    "krytyk_sledztwa": (config.SONNET, 4000 + H, "medium", None),
    "krytyk_sledztwa_zapas": (config.DEEPSEEK, 4000 + H, None, "enabled"),
    "ksiega": (config.DEEPSEEK, 6000, None, "disabled"),
    "investigation_document": (config.DEEPSEEK, 6000, None, "disabled"),
    "przeslania": (config.CLAUDE, 12000 + H, "medium", None),
    "przeslania_zapas": (config.DEEPSEEK, 12000 + H, None, "enabled"),
    "naglowek_naprawa": (config.DEEPSEEK, 600, None, "disabled"),
    "ten_sam_punkt": (config.DEEPSEEK, 1500, None, "disabled"),
    "notka_przeslania": (config.CLAUDE, config.MAX_TOKENS.get("notka_przeslania"), "medium", None),
    "notka_przeslania_fakt": (config.CLAUDE, config.MAX_TOKENS.get("notka_przeslania"), "medium", None),
    "wiernosc_notki": (config.DEEPSEEK, 1500, None, "disabled"),
}
for cel, (model, sufit, wysilek, myslenie) in KONTRAKT.items():
    sprawdz("%-26s model %s" % (cel, model), config.MODEL_FOR.get(cel) == model,
            config.MODEL_FOR.get(cel))
    sprawdz("%-26s sufit %s" % (cel, sufit), config.MAX_TOKENS.get(cel) == sufit,
            config.MAX_TOKENS.get(cel))
    sprawdz("%-26s wysilek %s" % (cel, wysilek), config.EFFORT.get(cel) == wysilek,
            config.EFFORT.get(cel))
    # Myslenie DeepSeeka sprawdzamy tylko dla celow na DeepSeeku — wpis przy celu
    # Claude (np. `przeslania`) jest zapisem intencji na wypadek przepiecia.
    if model == config.DEEPSEEK:
        sprawdz("%-26s myslenie %s" % (cel, myslenie),
                (config.DEEPSEEK_MYSLENIE.get(cel) or {}).get("type") == myslenie,
                config.DEEPSEEK_MYSLENIE.get(cel))
for cel in ("investigation_search", "investigation_extract", "nowosc", "synthesis"):
    sprawdz("%-26s istnieje bez zmian modelu" % cel, config.MODEL_FOR.get(cel) == config.DEEPSEEK
            and cel in config.MAX_TOKENS, config.MODEL_FOR.get(cel))
sprawdz("dokument pierwotny: najwyzej dwa szukania",
        config.max_szukan("investigation_document") == 2, config.max_szukan("investigation_document"))
sprawdz("D1: notki serii z katow faktow pisze ten sam Opus co prowadzace",
        config.MODEL_FOR["notka_przeslania_fakt"] == config.MODEL_FOR["notka_przeslania"] == config.CLAUDE)
sprawdz("karta sledztwa: 16 twierdzen, artykul zostaje przy 8",
        config.CARD_MAX_CONFIRMED_SLEDZTWO == 16 and config.CARD_MAX_CONFIRMED == 8)
sprawdz("sufit syntezy liczony z wiekszego trybu",
        config.MAX_TOKENS["synthesis"] > config._tokens_for(
            16 * (config.CARD_MAX_CLAIM_CHARS + config.CLASSIFY_MAX_EXCERPT_CHARS)) + H - 1)

# NAPRAWDE: `llm.call` w DRY_RUN na kazdym nowym celu (bez KeyError, bez sieci).
_stare = (config.DRY_RUN, config.ANTHROPIC_API_KEY, config.DEEPSEEK_API_KEY)
with tempfile.TemporaryDirectory() as _tmp:
    _conn = db.connect(pathlib.Path(_tmp) / "t.db")
    _run = db.start_run(_conn, tryb="test")
    config.DRY_RUN, config.ANTHROPIC_API_KEY, config.DEEPSEEK_API_KEY = True, "atrapa", "atrapa"
    bledy = []
    try:
        for cel in KONTRAKT:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    llm.call(cel, "s", "u", conn=_conn, run_id=_run)
            except Exception as exc:     # noqa: BLE001 — mierzymy, co wylatuje
                bledy.append("%s: %s" % (cel, type(exc).__name__))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                llm.call("cel_spoza_tabel", "s", "u", conn=_conn, run_id=_run)
            _kontr = False
        except KeyError:
            _kontr = True
    finally:
        config.DRY_RUN, config.ANTHROPIC_API_KEY, config.DEEPSEEK_API_KEY = _stare
        _conn.close()
sprawdz("llm.call przechodzi kontrole na kazdym celu kontraktu", not bledy, bledy)
sprawdz("KONTRDOWOD: cel spoza tabel nadal konczy sie KeyError", _kontr)

print()
print("=== 3. KAZDY PROMPT RENDERUJE SIE PRZEZ str.format ===")


class Atrapa(str):
    """Wartosc pola, ktora przezyje `{x.y}`, `{x[0]}` i `{x:>5}`."""

    def __getattr__(self, nazwa):
        return Atrapa("x")

    def __getitem__(self, klucz):
        return Atrapa("x")

    def __format__(self, spec):
        return "x"


def renderuj(tekst):
    """Formatuje prompt atrapami pol — ale TYLKO pol o ksztalcie identyfikatora.

    Niepodwojony nawias JSON-u (`{"a": 1}`) wyglada dla `str.format` jak pole
    o nazwie `"a"`. Zaden kod takiego pola nie poda, wiec tu tez go nie dostaje
    i format pada — dokladnie tak, jak padlby w przebiegu.
    """
    import re
    pola = {}
    for _, pole, _, _ in string.Formatter().parse(tekst):
        if pole:
            korzen = pole.split(".")[0].split("[")[0]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", korzen):
                pola[korzen] = Atrapa("x")
    return tekst.format(**pola)


prompty = sorted((KORZEN / "prompts").glob("*.md"))
sprawdz("prompty sa w katalogu (co najmniej 30)", len(prompty) >= 30, len(prompty))
zle = []
for p in prompty:
    try:
        renderuj(p.read_text(encoding="utf-8"))
    except (KeyError, ValueError, IndexError, AttributeError) as exc:
        zle.append("%s: %s" % (p.name, exc))
sprawdz("kazdy prompt z prompts/*.md renderuje sie", not zle, zle)
for nazwa in ("wiernosc_notki.md", "synteza.md", "notka.md"):
    sprawdz("%s jest w katalogu" % nazwa, (KORZEN / "prompts" / nazwa).exists())
try:
    renderuj('Return {"a": 1} and {pole}')
    _nawias = False
except (ValueError, KeyError, IndexError):
    _nawias = True
sprawdz("KONTRDOWOD: niepodwojony nawias JSON-u pada", _nawias)

# Karta artykulu bez trybu sledczego — a sledztwa z nim.
PROMPTY_SYNTEZY = []
_stary_call = llm.call
llm.call = lambda purpose, system, user, **k: (PROMPTY_SYNTEZY.append(user) or
                                               '{"confirmed_claims": [], "citable_numbers": []}')
try:
    with contextlib.redirect_stdout(io.StringIO()):
        DOWOD = [{"url": "https://a.example/x", "class": "PRIMARY", "excerpts": ["e"],
                  "numbers": [], "data": "2026-10-23"}]
        stages.synthesis(None, 1, "Q?", DOWOD)
        stages.synthesis(None, 1, "Q?", DOWOD, tryb="sledztwo")
finally:
    llm.call = _stary_call
art, sl = PROMPTY_SYNTEZY
sprawdz("artykul: prompt bez trybu sledczego", "Investigation mode" not in art)
sprawdz("artykul: koniec ksztaltu JSON dokladnie jak przed zmiana",
        'how current this is>"}}\n\n## The evidence' in art, art[-400:])
sprawdz("artykul: bez daty zrodla w danych (prompt jak dotad)", '"date"' not in art)
sprawdz("artykul: 5 do 8 twierdzen", "5 to 8" in art and "5 to 16" not in art)
sprawdz("sledztwo: tryb sledczy, 16 twierdzen, sloty i glosy",
        "Investigation mode" in sl and "5 to 16" in sl
        and "PRICE_ACCESS" in sl and '"voices"' in sl, sl[:200])
sprawdz("sledztwo: data zrodla w danych dla as_of", '"date": "2026-10-23"' in sl)

print()
print("=== 4. EFFORT WEDLUG DOSTAWCY I RODZINY ===")
for model, oczekiwane in (("claude-opus-5-5", True), ("claude-sonnet-5-5", True),
                          ("claude-fable-5-1", True), ("claude-opus-5-5-20261101", True),
                          ("claude-opus-5", True), ("claude-haiku-4-5-20251001", False),
                          ("claude-opus-4-1", False), ("deepseek-flash", False),
                          ("mimo-v2.6-flash", False)):
    sprawdz("effort_dziala(%s) = %s" % (model, oczekiwane), llm.effort_dziala(model) is oczekiwane)

WYSLANE = []


class _Wiadomosc:
    def __init__(self, model):
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.model = model
        self.content = [type("B", (), {"type": "text", "text": '{"ok": 1}'})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5,
                                    "server_tool_use": None})()


class _Strumien:
    def __init__(self, kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return _Wiadomosc(self.kwargs["model"] + "-20261101")


class _Klient:
    def __init__(self, **k):
        self.messages = self

    def stream(self, **kwargs):
        WYSLANE.append(kwargs)
        return _Strumien(kwargs)


_stary_klient = llm.anthropic.Anthropic
llm.anthropic.Anthropic = _Klient
try:
    # Pisarz podany z boku (np. `AGENT_V2_WRITER`), rozny od stalych CLAUDE/SONNET/FABLE.
    llm._call_claude("notka_przeslania", "s", "u", False, model="claude-opus-5-5-20261101")
    llm._call_claude("notka_przeslania", "s", "u", False, model="claude-haiku-4-5-20251001")
finally:
    llm.anthropic.Anthropic = _stary_klient
sprawdz("model spoza stalych dostaje output_config.effort",
        WYSLANE[0].get("output_config") == {"effort": "medium"}, WYSLANE[0].get("output_config"))
sprawdz("KONTRDOWOD: Haiku pokretla nie dostaje (odrzucilby je bledem)",
        "output_config" not in WYSLANE[1], WYSLANE[1].get("output_config"))
sprawdz("stary warunek (rownosc ze stala) przepuscilby model z boku bez wysilku",
        "claude-opus-5-5-20261101" not in (config.CLAUDE, config.SONNET, config.FABLE))

print()
print("=== 5. MODEL ZWROCONY PRZEZ API W calls.model_served ===")
with tempfile.TemporaryDirectory() as _tmp:
    # Stara baza: tabela `calls` bez nowej kolumny.
    sciezka = pathlib.Path(_tmp) / "stara.db"
    surowa = sqlite3.connect(sciezka)
    surowa.execute("CREATE TABLE calls (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER,"
                   " at TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,"
                   " purpose TEXT NOT NULL, tokens_in INTEGER NOT NULL DEFAULT 0,"
                   " tokens_out INTEGER NOT NULL DEFAULT 0, web_searches INTEGER NOT NULL DEFAULT 0,"
                   " cost_usd REAL NOT NULL DEFAULT 0, price_verified INTEGER NOT NULL DEFAULT 1,"
                   " ok INTEGER NOT NULL DEFAULT 1, note TEXT)")
    surowa.commit()
    surowa.close()
    b1 = io.StringIO()
    with contextlib.redirect_stdout(b1):
        c1 = db.connect(sciezka)
    c1.close()
    b2 = io.StringIO()
    with contextlib.redirect_stdout(b2):
        conn = db.connect(sciezka)
    kolumny = {w[1] for w in conn.execute("PRAGMA table_info(calls)")}
    sprawdz("stara baza dostaje calls.model_served", "model_served" in kolumny, sorted(kolumny))
    sprawdz("migracja mowi o tym raz", "calls.model_served" in b1.getvalue()
            and "model_served" not in b2.getvalue(), (b1.getvalue(), b2.getvalue()))
    run = db.start_run(conn, tryb="test")
    _stare = (llm._call_deepseek, config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL, config.DRY_RUN)

    def _deepseek_z_modelem(purpose, system, user):
        llm._zapamietaj_model("deepseek-v4-pro")
        return '{"x": 1}', 10, 5, 0, 0

    def _deepseek_bez_modelu(purpose, system, user):
        return '{"x": 1}', 10, 5, 0, 0

    config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL, config.DRY_RUN = "atrapa", True, False
    llm._INNY_MODEL.clear()
    try:
        llm._call_deepseek = _deepseek_z_modelem
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            llm.call("wiernosc_notki", "s", "u", conn=conn, run_id=run)
            llm.call("wiernosc_notki", "s", "u", conn=conn, run_id=run)
        llm._call_deepseek = _deepseek_bez_modelu
        with contextlib.redirect_stdout(io.StringIO()):
            llm.call("wiernosc_notki", "s", "u", conn=conn, run_id=run)
    finally:
        llm._call_deepseek, config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL, config.DRY_RUN = _stare
    wiersze = conn.execute("SELECT model, model_served FROM calls WHERE purpose = 'wiernosc_notki'"
                           " ORDER BY id").fetchall()
    sprawdz("zapis ma model, o ktory prosilismy, i ten, ktory odpowiedzial",
            [tuple(w) for w in wiersze[:2]] == [(config.DEEPSEEK, "deepseek-v4-pro")] * 2,
            [tuple(w) for w in wiersze])
    sprawdz("rozjazd prosba/odpowiedz w logu, raz na proces",
            log.getvalue().count("odpowiedzial deepseek-v4-pro") == 1, log.getvalue())
    sprawdz("KONTRDOWOD: transport bez pola modelu zapisuje NULL, nie stara wartosc",
            len(wiersze) == 3 and wiersze[2][1] is None, [tuple(w) for w in wiersze])
    conn.close()

# Transport Claude naprawde przekazuje `message.model`.
_stary_klient = llm.anthropic.Anthropic
llm.anthropic.Anthropic = _Klient
try:
    llm._zapamietaj_model(None)
    llm._call_claude("przeslania", "s", "u", False, model="claude-opus-5-5")
    _podany = llm._model_z_odpowiedzi()
finally:
    llm.anthropic.Anthropic = _stary_klient
sprawdz("transport Claude zapamietuje model z odpowiedzi", _podany == "claude-opus-5-5-20261101",
        _podany)

print()
print("=== 6. CENY I MODELE SLEDZTWA ===")
for model, (wej, wyj, cache) in (("claude-opus-5-5", (4.0, 20.0, 0.20)),
                                 ("claude-sonnet-5-5", (2.0, 10.0, 0.10)),
                                 ("claude-fable-5-1", (10.0, 50.0, 0.25))):
    c = config.PRICING.get(model) or {}
    sprawdz("%s: %s/%s, cache %s, verified" % (model, wej, wyj, cache),
            (c.get("in"), c.get("out"), c.get("cache"), c.get("verified")) == (wej, wyj, cache, True), c)
    sprawdz("%s: wywolanie zapisuje sie z potwierdzona stawka" % model,
            llm._cost(model, 1000, 1000, 0)[1] is True)
sprawdz("nieznany model rodziny nadal NIEPOTWIERDZONY",
        config.stawka_modelu("claude-opus-9")["verified"] is False)
sprawdz("modele sledztwa 5.5 z cena: bez uwag",
        config.modele_sledztwa_ponizej({"CLAUDE": "claude-opus-5-5", "SONNET": "claude-sonnet-5-5"}) == [])
_uwagi = config.modele_sledztwa_ponizej({"CLAUDE": "claude-opus-5", "SONNET": "claude-sonnet-5-5"})
sprawdz("KONTRDOWOD: Opus 5 zamiast 5.5 (kopia danych z 25.10) jest zglaszany",
        len(_uwagi) == 1 and "CLAUDE=claude-opus-5" in _uwagi[0], _uwagi)
_uwagi = config.modele_sledztwa_ponizej({"CLAUDE": "claude-opus-6", "SONNET": "claude-sonnet-5-5"})
sprawdz("nowszy model bez wpisu w cenniku jest zglaszany (liczony stawka rodziny)",
        len(_uwagi) == 1 and "cenniku" in _uwagi[0], _uwagi)

print()
print("=== 7. NIZSZY LIMIT SZUKANIA JEDNEGO WYWOLANIA ===")
DOSTALO = []


def _z_siecia(purpose, system, user, model=None, **k):
    DOSTALO.append(k)
    return '{"claims": []}', 10, 5, 1, [], 0


with tempfile.TemporaryDirectory() as _tmp:
    conn = db.connect(pathlib.Path(_tmp) / "t.db")
    run = db.start_run(conn, tryb="test")
    _stare = (llm._call_deepseek_z_siecia, config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL,
              config.DRY_RUN)
    config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL, config.DRY_RUN = "atrapa", True, False
    try:
        llm._call_deepseek_z_siecia = _z_siecia
        with contextlib.redirect_stdout(io.StringIO()):
            llm.call("factcheck", "s", "u", conn=conn, run_id=run, web_search=True, max_szukan=2)
            llm.call("factcheck", "s", "u", conn=conn, run_id=run, web_search=True)
    finally:
        (llm._call_deepseek_z_siecia, config.DEEPSEEK_API_KEY, config.WOLNO_WOLAC_MODEL,
         config.DRY_RUN) = _stare
        conn.close()
sprawdz("limit dociera do transportu", DOSTALO[:1] == [{"max_szukan": 2}], DOSTALO)
sprawdz("KONTRDOWOD: bez limitu transport nie dostaje nowego argumentu", DOSTALO[1:] == [{}], DOSTALO)

print()
print("=== WYNIK: %d zdanych, %d oblanych ===" % (zdane, oblane))
sys.exit(1 if oblane else 0)
