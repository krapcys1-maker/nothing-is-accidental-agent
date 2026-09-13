"""Nowe modele wchodza same — po probie, nie po ogloszeniu.

DLACZEGO TO ISTNIEJE. 10 wrzesnia 2026 DeepSeek wydal V4.1 Flash, wycofal V4 Flash
i przekierowal jego nazwe na nowy model. Konto chodzilo na nowym modelu trzy dni,
nie wiedzac o tym, bo wywolania dalej konczyly sie sukcesem. Wyszlo przy
przegladzie konta 13 wrzesnia, i to w najgorszej postaci: V4.1 Flash nie ma
narzedzia wyszukiwania, wiec weryfikacja faktow przed publikacja przez trzy dni
oddawalo fakty z pamieci. A dzien pozniej ta sama zmiana czekala `deepseek-v4-pro`.

Wlasciciel: „moze warto dopisac cos takiego, zeby automatycznie sie zmienialo na
nowe modele, jak wychodza". Ten modul to robi — ale na dowodach, nie na nazwach.

JAK DZIALA, raz na dobe:

    1. lista modeli od dostawcow — `GET /v1/models` u Anthropic i `GET /models`
       u DeepSeeka. Za darmo i dokladnie: to jest spis tego, co da sie wywolac.
    2. dla kazdej roli najlepszy model W TEJ SAMEJ RODZINIE: Opus na Opusa,
       Flash na Flasha. Nazwa bez numeru u DeepSeeka (`deepseek-flash`) to jego
       wlasny sposob mowienia „najnowsza wersja" — wybierana przed numerowanymi.
    3. proba: nowy model musi odpowiedziec poprawnym JSON-em. Kilka tokenow.
    4. zamiana zapisana w `data/wybor_modeli.json`; `config` stosuje ja przy
       kazdym starcie, a tu dziala od razu, w biezacym przebiegu.
    5. proba wyszukiwania dla modeli DeepSeeka, ktore dzis nie szukaja. Gdy
       zaczna — wywolania z siecia wroca do nich same (`config.szuka_naprawde`).

CZEGO TU CELOWO NIE MA.

    - PRZESKOKU MIEDZY RODZINAMI. Opus na Fable to dwa razy wyzszy rachunek
      i inny glos artykulow. To decyzja wlasciciela, nie aktualizacja.
    - WERSJI preview, exp, beta, latest, vision. Nie buduje sie konta na czyms,
      co dostawca sam nazywa proba.
    - ZAMIANY NA STARSZA WERSJE, dopoki obecna odpowiada. Znikniecie z listy
      moze byc chwilowe; model, ktory odpowiada, nie jest zepsuty.
    - DECYZJI NA PUSTEJ LISCIE. Brak odpowiedzi dostawcy to brak danych,
      a nie dowod, ze wszystkie modele zniknely.
    - BRAMKI DLA PUBLIKACJI. Nic tutaj nie zatrzymuje notki ani komentarza:
      nieudana proba zostawia obecny model, ktory dziala.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import config

WAZNE_GODZIN = 24

# rola w config -> (dostawca, rodzina)
ROLE = {
    "CLAUDE": ("anthropic", "opus"),
    "SONNET": ("anthropic", "sonnet"),
    "HAIKU": ("anthropic", "haiku"),
    "FABLE": ("anthropic", "fable"),
    "DEEPSEEK": ("deepseek", "flash"),
    "DEEPSEEK_PRO": ("deepseek", "pro"),
}

ZAKAZANE_CZLONY = ("preview", "exp", "beta", "alpha", "latest", "vision", "test")

PROBA_JSON = 'Return only valid JSON, exactly this object: {"ok": true}'
PYTANIE_SZUKANIA = (
    "Use the web search tool, then answer in one sentence: what is one news "
    "headline published in the last 24 hours?"
)


# --- czysta logika: bez sieci, testowalna ------------------------------------

def wersja(identyfikator: str) -> tuple[int, ...]:
    """Numery wersji z identyfikatora. Data wydania (8 cyfr) nie jest wersja.

        claude-fable-5-1           -> (5, 1)
        claude-haiku-4-5-20251001  -> (4, 5)
        deepseek-v4.1-pro          -> (4, 1)
        deepseek-flash             -> ()
    """
    liczby: list[int] = []
    for czlon in re.split(r"[-.]", str(identyfikator).lower()):
        if re.fullmatch(r"v\d+", czlon):
            czlon = czlon[1:]
        if czlon.isdigit() and len(czlon) < 8:
            liczby.append(int(czlon))
    return tuple(liczby)


def w_rodzinie(identyfikator: str, dostawca: str, rodzina: str) -> bool:
    """Czy identyfikator nalezy do rodziny u tego dostawcy i nie jest proba."""
    nazwa = str(identyfikator).lower()
    prefiks = "deepseek" if dostawca == "deepseek" else "claude"
    if not nazwa.startswith(prefiks):
        return False
    czlony = re.split(r"[-.]", nazwa)
    return rodzina in czlony and not any(z in czlony for z in ZAKAZANE_CZLONY)


def najlepszy_w_rodzinie(dostawca: str, rodzina: str,
                         lista: dict[str, Any]) -> str | None:
    """Najlepszy kandydat rodziny z listy dostawcy `{identyfikator: data_wydania}`."""
    kandydaci = [m for m in lista if w_rodzinie(m, dostawca, rodzina)]
    if not kandydaci:
        return None
    kanoniczna = "deepseek-%s" % rodzina
    if dostawca == "deepseek" and kanoniczna in kandydaci:
        return kanoniczna
    return max(kandydaci, key=lambda m: (wersja(m), str(lista.get(m) or "")))


def zdecyduj(obecne: dict[str, str],
             listy: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Zamiany do sprawdzenia proba. Nic tu nie wola sieci."""
    decyzje: list[dict[str, Any]] = []
    for rola, (dostawca, rodzina) in ROLE.items():
        obecny = obecne.get(rola)
        lista = listy.get(dostawca)
        if not obecny or not lista:
            continue
        cel = najlepszy_w_rodzinie(dostawca, rodzina, lista)
        if not cel or cel == obecny:
            continue
        nieobecny = obecny not in lista
        if dostawca == "deepseek" and cel == "deepseek-%s" % rodzina:
            powod = "kanoniczna nazwa najnowszej wersji u dostawcy"
        elif wersja(cel) > wersja(obecny):
            powod = "nowsza wersja w tej samej rodzinie"
        elif nieobecny:
            powod = "obecnego modelu nie ma na liscie dostawcy"
        else:
            continue
        if nieobecny and "nie ma" not in powod:
            powod += "; obecnej nazwy nie ma juz na liscie"
        decyzje.append({
            "rola": rola, "dostawca": dostawca, "z": obecny, "na": cel,
            "powod": powod, "nieobecny": nieobecny,
            "starsza": bool(wersja(cel)) and wersja(cel) < wersja(obecny),
        })
    return decyzje


def odpowiedz_jest_ok(tekst: str) -> bool:
    """Czy odpowiedz proby to obiekt JSON z `ok: true`."""
    import llm
    try:
        dane = llm.parse_json(tekst or "")
    except Exception:
        return False
    return isinstance(dane, dict) and dane.get("ok") is True


def zastosuj_w_procesie(rola: str, stary: str, nowy: str) -> None:
    """Zamiana dziala od razu, bez czekania na nastepny start procesu."""
    setattr(config, rola, nowy)
    for etap, model in list(config.MODEL_FOR.items()):
        if model == stary:
            config.MODEL_FOR[etap] = nowy
    for etap, model in list(config.MODEL_DO_SZUKANIA.items()):
        if model == stary:
            config.MODEL_DO_SZUKANIA[etap] = nowy
    if config.MODEL_DO_SZUKANIA_DOMYSLNY == stary:
        config.MODEL_DO_SZUKANIA_DOMYSLNY = nowy
    if stary in config.WEB_SEARCH_TOOL and nowy not in config.WEB_SEARCH_TOOL:
        config.WEB_SEARCH_TOOL[nowy] = config.WEB_SEARCH_TOOL[stary]


# --- siec ---------------------------------------------------------------------

def _naglowki_anthropic() -> dict[str, str]:
    return {"x-api-key": str(config.ANTHROPIC_API_KEY),
            "anthropic-version": "2023-06-01", "content-type": "application/json"}


def _naglowki_deepseek() -> dict[str, str]:
    return {"Authorization": "Bearer %s" % config.DEEPSEEK_API_KEY}


def lista_modeli() -> dict[str, dict[str, Any] | None]:
    """Spis modeli u dostawcow. `None` przy bledzie albo pustej liscie."""
    import httpx

    listy: dict[str, dict[str, Any] | None] = {"anthropic": None, "deepseek": None}
    if config.ANTHROPIC_API_KEY:
        try:
            odp = httpx.get("https://api.anthropic.com/v1/models?limit=1000",
                            headers=_naglowki_anthropic(), timeout=30)
            odp.raise_for_status()
            listy["anthropic"] = {m["id"]: m.get("created_at")
                                  for m in odp.json().get("data", []) if m.get("id")} or None
        except Exception as exc:
            print("  [nowe modele] lista Anthropic niedostepna (%s) — bez decyzji"
                  % type(exc).__name__, flush=True)
    if config.DEEPSEEK_API_KEY:
        try:
            odp = httpx.get("%s/models" % config.DEEPSEEK_BASE_URL,
                            headers=_naglowki_deepseek(), timeout=30)
            odp.raise_for_status()
            listy["deepseek"] = {m["id"]: m.get("created")
                                 for m in odp.json().get("data", []) if m.get("id")} or None
        except Exception as exc:
            print("  [nowe modele] lista DeepSeeka niedostepna (%s) — bez decyzji"
                  % type(exc).__name__, flush=True)
    return listy


def proba_odpowiedzi(dostawca: str, model: str) -> tuple[bool, str, int, int]:
    """Czy model odpowiada poprawnym JSON-em. (ok, opis, tokeny_wej, tokeny_wyj)."""
    import httpx

    try:
        if dostawca == "anthropic":
            cialo = {"model": model, "max_tokens": 256,
                     "thinking": {"type": "disabled"},
                     "messages": [{"role": "user", "content": PROBA_JSON}]}
            odp = httpx.post("https://api.anthropic.com/v1/messages",
                             headers=_naglowki_anthropic(), json=cialo, timeout=90)
            if odp.status_code == 400 and "thinking" in odp.text:
                # Model bez przelacznika myslenia: to samo pytanie bez parametru.
                cialo.pop("thinking")
                cialo["max_tokens"] = 2048
                odp = httpx.post("https://api.anthropic.com/v1/messages",
                                 headers=_naglowki_anthropic(), json=cialo, timeout=90)
            dane = odp.json()
            if odp.status_code != 200:
                return False, "HTTP %s: %s" % (odp.status_code, str(dane.get("error"))[:160]), 0, 0
            tekst = "".join(b.get("text", "") for b in dane.get("content", [])
                            if b.get("type") == "text")
            uzycie = dane.get("usage") or {}
            tin, tout = int(uzycie.get("input_tokens", 0)), int(uzycie.get("output_tokens", 0))
        else:
            odp = httpx.post("%s/chat/completions" % config.DEEPSEEK_BASE_URL,
                             headers=_naglowki_deepseek(), timeout=90,
                             json={"model": model, "max_tokens": 256,
                                   "thinking": {"type": "disabled"},
                                   "messages": [{"role": "user", "content": PROBA_JSON}]})
            dane = odp.json()
            if odp.status_code != 200:
                return False, "HTTP %s: %s" % (odp.status_code, str(dane.get("error"))[:160]), 0, 0
            tekst = dane["choices"][0]["message"].get("content") or ""
            uzycie = dane.get("usage") or {}
            tin = int(uzycie.get("prompt_tokens", 0))
            tout = int(uzycie.get("completion_tokens", 0))
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, str(exc)[:160]), 0, 0
    ok = odpowiedz_jest_ok(tekst)
    return ok, ("odpowiada poprawnym JSON-em" if ok
                else "odpowiedz bez oczekiwanego JSON-a: %r" % tekst[:80]), tin, tout


def proba_wyszukiwania(model: str) -> tuple[bool, int, int, int, str]:
    """Czy model DeepSeeka NAPRAWDE wywoluje wyszukiwarke przez `/responses`.

    `tool_choice: required`, bo przy `auto` model moze uczciwie nie szukac —
    a pytamy o zdolnosc, nie o decyzje. Liczymy bloki `web_search_call` w
    odpowiedzi: V4.1 Flash przy `required` pisal udawane znaczniki w tekscie,
    wiec sam tekst odpowiedzi niczego nie dowodzi.
    """
    import httpx

    try:
        odp = httpx.post("%s/responses" % config.DEEPSEEK_BASE_URL,
                         headers=_naglowki_deepseek(), timeout=240,
                         json={"model": model, "input": PYTANIE_SZUKANIA,
                               "tools": [{"type": "web_search"}],
                               "tool_choice": "required",
                               "reasoning": {"effort": "low"},
                               "max_output_tokens": 1500})
        dane = odp.json()
        if odp.status_code != 200:
            return False, 0, 0, 0, "HTTP %s: %s" % (odp.status_code, str(dane.get("error"))[:160])
    except Exception as exc:
        return False, 0, 0, 0, "%s: %s" % (type(exc).__name__, str(exc)[:160])

    szukan = 0

    def licz(wezel: Any) -> None:
        nonlocal szukan
        if isinstance(wezel, dict):
            if wezel.get("type") == "web_search_call":
                szukan += 1
            for wartosc in wezel.values():
                licz(wartosc)
        elif isinstance(wezel, list):
            for wartosc in wezel:
                licz(wartosc)

    licz(dane.get("output", []))
    uzycie = dane.get("usage") or {}
    return (szukan > 0, szukan, int(uzycie.get("input_tokens", 0)),
            int(uzycie.get("output_tokens", 0)),
            "szuka (%d wyszukiwan)" % szukan if szukan else "nie wywoluje wyszukiwarki")


# --- stan i przebieg ------------------------------------------------------------

def wczytaj() -> dict[str, Any]:
    return config._wybor_modeli_z_pliku(config.plik_wyboru_modeli())


def zapisz(stan: dict[str, Any]) -> None:
    sciezka = config.plik_wyboru_modeli()
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_suffix(".json.tmp")
    tymczasowy.write_text(json.dumps(stan, ensure_ascii=False, indent=1), encoding="utf-8")
    tymczasowy.replace(sciezka)


def _mlodsze_niz(kiedy: Any, godzin: float) -> bool:
    try:
        chwila = datetime.fromisoformat(str(kiedy))
    except ValueError:
        return False
    if chwila.tzinfo is None:
        chwila = chwila.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - chwila < timedelta(hours=godzin)


def _do_dziennika(rodzaj: str, **pola: Any) -> None:
    """Wpis do dziennika dzialan. Nigdy nie przerywa przebiegu."""
    try:
        wpis = {"kiedy": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rodzaj": rodzaj, **pola}
        sciezka = config.DATA_DIR / "dziennik.jsonl"
        with open(sciezka, "a", encoding="utf-8") as plik:
            plik.write(json.dumps(wpis, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _wolno_placic(conn, run_id: int | None, model: str) -> str:
    """Pusty napis, gdy budzet i wylacznik pozwalaja na probe; inaczej powod.

    Przez `llm._preflight`, a nie wlasne liczenie: proba to tez wydatek
    i ma podlegac tym samym suficom co kazde inne wywolanie.
    """
    import llm
    # DRY_RUN SPRAWDZANY TU, NIE W `_preflight`. Tamta kontrola celowo go
    # przepuszcza, bo `llm.call` przy DRY_RUN konczy sie przed siecia. Proby
    # tego modulu ida do sieci WLASNA droga, wiec bez tej linii tryb „na sucho"
    # placilby naprawde. Zlapane testem przy pierwszym uruchomieniu.
    if config.DRY_RUN:
        return "DRY_RUN — proba pominieta"
    try:
        llm._preflight("nowe_modele", conn, run_id, model=model)
    except (llm.BudgetExceeded, llm.PreflightFailed) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
    return ""


def _zapisz_koszt(conn, run_id: int | None, dostawca: str, model: str,
                  tin: int, tout: int, szukan: int, ok: bool, opis: str) -> None:
    import db
    import llm
    usd, potwierdzona = llm._cost(model, tin, tout, szukan)
    db.record_call(conn=conn, run_id=run_id, provider=dostawca, model=model,
                   purpose="nowe_modele", tokens_in=tin, tokens_out=tout,
                   web_searches=szukan, cost_usd=usd,
                   price_verified=int(potwierdzona), ok=int(ok), note=opis[:500])


def sprawdz(conn=None, run_id: int | None = None, wymus: bool = False) -> dict[str, Any]:
    """Raz na dobe: lista, decyzje, proby, zapis. Nigdy nie wywala przebiegu."""
    stan = wczytaj()
    if not wymus and _mlodsze_niz(stan.get("_sprawdzone"), WAZNE_GODZIN):
        return {"pominiete": "sprawdzone w ciagu ostatniej doby"}
    if config.KILL_SWITCH:
        return {"pominiete": "KILL_SWITCH"}

    wlasne = None
    if conn is None:
        import db as _db
        conn = wlasne = _db.connect()
    teraz = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        listy = lista_modeli()
        obecne = {rola: getattr(config, rola) for rola in ROLE}
        wykonane: list[dict[str, Any]] = []
        odrzucone: list[dict[str, Any]] = []
        zamiany = dict(stan.get("zamiany") or {})

        for decyzja in zdecyduj(obecne, listy):
            powod = _wolno_placic(conn, run_id, decyzja["na"])
            if powod:
                odrzucone.append({**decyzja, "dlaczego": powod})
                continue
            ok, opis, tin, tout = proba_odpowiedzi(decyzja["dostawca"], decyzja["na"])
            _zapisz_koszt(conn, run_id, decyzja["dostawca"], decyzja["na"], tin, tout, 0, ok, opis)
            if not ok:
                odrzucone.append({**decyzja, "dlaczego": "proba nowego modelu: " + opis})
                continue
            if decyzja["starsza"]:
                ok_stary, opis_stary, tin, tout = proba_odpowiedzi(decyzja["dostawca"], decyzja["z"])
                _zapisz_koszt(conn, run_id, decyzja["dostawca"], decyzja["z"], tin, tout, 0,
                              ok_stary, opis_stary)
                if ok_stary:
                    odrzucone.append({**decyzja, "dlaczego":
                                      "zastepca jest starszy, a obecny dalej odpowiada"})
                    continue
            zamiany[decyzja["rola"]] = {"z": decyzja["z"], "na": decyzja["na"],
                                        "kiedy": teraz, "powod": decyzja["powod"]}
            zastosuj_w_procesie(decyzja["rola"], decyzja["z"], decyzja["na"])
            wykonane.append(decyzja)
            _do_dziennika("zmiana_modelu", udane=True, rola=decyzja["rola"],
                          z=decyzja["z"], na=decyzja["na"], powod=decyzja["powod"])
            print("  [nowe modele] ZAMIANA %s: %s -> %s (%s)"
                  % (decyzja["rola"], decyzja["z"], decyzja["na"], decyzja["powod"]), flush=True)

        for decyzja in odrzucone:
            print("  [nowe modele] bez zamiany %s: %s -> %s — %s"
                  % (decyzja["rola"], decyzja["z"], decyzja["na"], decyzja["dlaczego"]), flush=True)

        # PROBY WYSZUKIWANIA: tylko modele DeepSeeka w uzyciu, ktore dzis nie szukaja.
        wyszukiwanie = dict(stan.get("wyszukiwanie") or {})
        modele_deepseeka = sorted({getattr(config, r) for r, (d, _) in ROLE.items()
                                   if d == "deepseek"})
        for model in modele_deepseeka:
            if config.szuka_naprawde(model):
                continue
            ostatnia = wyszukiwanie.get(model) or {}
            if not wymus and _mlodsze_niz(ostatnia.get("kiedy"), WAZNE_GODZIN):
                continue
            if _wolno_placic(conn, run_id, model):
                continue
            dziala, szukan, tin, tout, opis = proba_wyszukiwania(model)
            _zapisz_koszt(conn, run_id, "deepseek", model, tin, tout, szukan, True, opis)
            wyszukiwanie[model] = {"dziala": dziala, "kiedy": teraz, "szukan": szukan, "opis": opis}
            config.PROBY_WYSZUKIWANIA[model] = wyszukiwanie[model]
            print("  [nowe modele] wyszukiwanie na %s: %s" % (model, opis), flush=True)
            if dziala:
                _do_dziennika("zmiana_modelu", udane=True, rola="wyszukiwanie", z="zastepca",
                              na=model, powod="proba potwierdzila, ze model znow szuka")

        historia = list(stan.get("historia") or [])[-50:]
        if wykonane or odrzucone:
            historia.append({"kiedy": teraz, "wykonane": wykonane, "odrzucone": odrzucone})
        zapisz({
            "_sprawdzone": teraz,
            "zamiany": zamiany,
            "wyszukiwanie": wyszukiwanie,
            "u_dostawcow": {k: (sorted(v) if v else None) for k, v in listy.items()},
            "historia": historia,
        })
        if not wykonane and not odrzucone:
            print("  [nowe modele] bez zmian: %s" % ", ".join(
                "%s=%s" % (r, getattr(config, r)) for r in ROLE), flush=True)
        return {"wykonane": wykonane, "odrzucone": odrzucone, "wyszukiwanie": wyszukiwanie}
    finally:
        if wlasne is not None:
            wlasne.close()


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    wynik = sprawdz(wymus="--wymus" in sys.argv)
    print(json.dumps(wynik, ensure_ascii=False, indent=1, default=str))
