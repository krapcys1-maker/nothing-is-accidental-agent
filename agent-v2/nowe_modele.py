"""Daily API-catalog updates for every configured model family.

Text candidates must return JSON; DeepSeek candidates must also really search.
Image candidates must generate an image with production settings. Persist the
selection before applying it to the running process. See docs/AUTOMATYCZNE_MODELE.md.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import cennik_dostawcy
import config
from model_registry import ROLE, version as wersja, in_family as w_rodzinie

WAZNE_GODZIN = 24

# rola w config -> (dostawca, rodzina)
WERSJA_STANU = 2

PROBA_JSON = 'Return only valid JSON, exactly this object: {"ok": true}'
PYTANIE_SZUKANIA = (
    "Use the web search tool, then answer in one sentence: what is one news "
    "headline published in the last 24 hours?"
)


# --- czysta logika: bez sieci, testowalna ------------------------------------

def najlepszy_w_rodzinie(dostawca: str, rodzina: str,
                         lista: dict[str, Any]) -> str | None:
    """Najlepszy kandydat rodziny z listy dostawcy `{identyfikator: data_wydania}`."""
    kandydaci = [m for m in lista if w_rodzinie(m, dostawca, rodzina)]
    if not kandydaci:
        return None
    kanoniczna = "deepseek-%s" % rodzina
    if dostawca == "deepseek" and kanoniczna in kandydaci:
        return kanoniczna
    # Keep the full-quality image role. A faster sibling is not a newer version.
    # Prefer the stable name over a dated snapshot of the same version.
    return max(kandydaci, key=lambda m: (
        wersja(m), 0 if "flare" in m.split("-") else 1,
        not bool(re.search(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$", m)),
        str(lista.get(m) or "")))


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
        if etap == "write" and config._writer:
            continue  # An explicit one-run writer override remains pinned.
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

    listy: dict[str, dict[str, Any] | None] = {"anthropic": None, "deepseek": None, "openai": None}
    if config.ANTHROPIC_API_KEY:
        try:
            znalezione = {}
            cursor = None
            for _ in range(20):
                params = {"limit": 1000}
                if cursor:
                    params["after_id"] = cursor
                odp = httpx.get("https://api.anthropic.com/v1/models",
                                params=params, headers=_naglowki_anthropic(), timeout=30)
                odp.raise_for_status()
                dane = odp.json()
                znalezione.update({m["id"]: m.get("created_at")
                                   for m in dane.get("data", []) if m.get("id")})
                if not dane.get("has_more"):
                    listy["anthropic"] = znalezione or None
                    break
                nowy_cursor = dane.get("last_id")
                if not nowy_cursor or nowy_cursor == cursor:
                    raise ValueError("niekompletna paginacja listy modeli")
                cursor = nowy_cursor
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
    if config.OPENAI_API_KEY:
        try:
            odp = httpx.get("https://api.openai.com/v1/models",
                            headers={"Authorization": "Bearer " + config.OPENAI_API_KEY}, timeout=30)
            odp.raise_for_status()
            listy["openai"] = {m["id"]: m.get("created") for m in odp.json().get("data", [])
                               if w_rodzinie(m.get("id", ""), "openai", "gpt-image")} or None
        except Exception as exc:
            print("  [nowe modele] lista OpenAI niedostepna (%s) — bez decyzji"
                  % type(exc).__name__, flush=True)
    return listy


def proba_obrazu(model: str, conn, run_id: int | None) -> tuple[bool, str]:
    """Generate one real image with production size/quality before switching."""
    import hashlib
    import struct
    import llm
    try:
        obraz = llm.obraz("A simple blue circle on a white background, no text.",
                          conn=conn, run_id=run_id, model=model)
        if (not obraz.startswith(b"\x89PNG\r\n\x1a\n") or len(obraz) < 45
                or obraz[12:16] != b"IHDR" or b"IEND" not in obraz[-16:]):
            raise ValueError("odpowiedz nie zawiera kompletnego obrazu PNG")
        rozmiar = struct.unpack(">II", obraz[16:24])
        if rozmiar != tuple(map(int, config.IMAGE_SIZE.split("x"))):
            raise ValueError("obraz ma inny rozmiar niz produkcja")
        folder = config.DATA_DIR / "model-probes"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (hashlib.sha256(model.encode()).hexdigest()[:16] + ".png")).write_bytes(obraz)
        return True, "obraz PNG %sx%s, parametry produkcyjne" % rozmiar
    except Exception as exc:
        return False, "proba obrazu: " + type(exc).__name__


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
    """Czy model DeepSeeka NAPRAWDE wyszukuje — TA SAMA droga co produkcja.

    Endpoint zgodny z API Anthropic (`config.DEEPSEEK_ANTHROPIC_BASE_URL`), bo
    przez niego ida wywolania z siecia (`llm._call_deepseek_z_siecia`). Proba na
    innej drodze niz produkcja mierzylaby cos innego niz to, na czym stoi konto:
    13 wrzesnia V4.1 Flash nie szukal przez `/responses`, a przez ten endpoint tak.

    Liczymy `usage.server_tool_use.web_search_requests` z odpowiedzi serwera,
    nie tekst — model potrafi pisac udawane znaczniki wyszukiwania.
    """
    import httpx

    try:
        odp = httpx.post("%s/v1/messages" % config.DEEPSEEK_ANTHROPIC_BASE_URL,
                         headers={"x-api-key": str(config.DEEPSEEK_API_KEY),
                                  "anthropic-version": "2023-06-01",
                                  "content-type": "application/json"},
                         timeout=240,
                         json={"model": model, "max_tokens": 1500,
                               "messages": [{"role": "user", "content": PYTANIE_SZUKANIA}],
                               "tools": [{"type": config.NARZEDZIE_WYSZUKIWANIA_DEEPSEEK,
                                          "name": "web_search", "max_uses": 2}]})
        dane = odp.json()
        if odp.status_code != 200:
            return False, 0, 0, 0, "HTTP %s: %s" % (odp.status_code, str(dane.get("error"))[:160])
    except Exception as exc:
        return False, 0, 0, 0, "%s: %s" % (type(exc).__name__, str(exc)[:160])

    uzycie = dane.get("usage") or {}
    szukan = int((uzycie.get("server_tool_use") or {}).get("web_search_requests") or 0)
    return (szukan > 0, szukan, int(uzycie.get("input_tokens") or 0),
            int(uzycie.get("output_tokens") or 0),
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
    if (not wymus and stan.get("wersja") == WERSJA_STANU
            and _mlodsze_niz(stan.get("_sprawdzone"), WAZNE_GODZIN)):
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
        wyszukiwanie = dict(stan.get("wyszukiwanie") or {})
        sprawdzone_szukanie = set()

        def sprawdz_szukanie(model):
            dziala, szukan, tin, tout, opis = proba_wyszukiwania(model)
            _zapisz_koszt(conn, run_id, "deepseek", model, tin, tout, szukan, dziala, opis)
            sprawdzone_szukanie.add(model)
            # A timeout/HTTP error is not proof that a previously working tool
            # disappeared. A new candidate still cannot pass this gate.
            if dziala or opis == "nie wywoluje wyszukiwarki":
                wyszukiwanie[model] = {"dziala": dziala, "kiedy": teraz,
                    "szukan": szukan, "opis": opis, "droga": config.DROGA_WYSZUKIWANIA_DEEPSEEK}
            print("  [nowe modele] wyszukiwanie na %s: %s" % (model, opis), flush=True)
            return dziala, opis

        # CENY ZAMIAN ZROBIONYCH, ZANIM SPRAWDZALISMY CENY — raz, darmowym GET.
        # Nastepca bez wpisu w cenniku i bez zapisanej ceny liczyl sie stawka
        # rodziny; teraz dostaje stawke z cennika dostawcy, jesli ten ja podaje.
        ceny_nowe: dict[str, dict[str, Any]] = {}
        for wpis in zamiany.values():
            if (not isinstance(wpis, dict) or wpis.get("cena")
                    or str(wpis.get("na") or "") in config.PRICING):
                continue
            cena, zrodlo = cennik_dostawcy.stawka_u_dostawcy(
                str(wpis.get("na")), wzor=config.stawka_modelu(str(wpis.get("z"))))
            if cena:
                wpis["cena"], wpis["cena_zrodlo"] = cena, zrodlo
                ceny_nowe[str(wpis["na"])] = cena
                print("  [nowe modele] cena %s z cennika: %s (%s)"
                      % (wpis["na"], cena, zrodlo), flush=True)

        for decyzja in zdecyduj(obecne, listy):
            # CENA NASTEPCY PRZED PLATNA PROBA. Z cennika dostawcy; gdy go nie
            # da sie odczytac, nastepca liczy sie jak poprzednik (1:1) — decyzja
            # wlasciciela z 26.09.2026. Wyraznie drozszy nie wchodzi sam: czeka.
            wzor = config.stawka_modelu(decyzja["z"])
            cena, zrodlo_ceny = cennik_dostawcy.stawka_u_dostawcy(decyzja["na"], wzor=wzor)
            if cena and cennik_dostawcy.podwyzka(cena, wzor) > config.MAKS_PODWYZKA_PRZY_ZAMIANIE:
                odrzucone.append({**decyzja, "dlaczego":
                                  "drozszy o %.0f%% wg %s — zamiana czeka na decyzje wlasciciela"
                                  % (100 * cennik_dostawcy.podwyzka(cena, wzor), zrodlo_ceny)})
                continue
            decyzja["cena"] = cena
            decyzja["cena_zrodlo"] = zrodlo_ceny if cena else "jak poprzednik: " + zrodlo_ceny
            powod = _wolno_placic(conn, run_id, decyzja["na"])
            if powod:
                odrzucone.append({**decyzja, "dlaczego": powod})
                continue
            if decyzja["dostawca"] == "openai":
                ok, opis = proba_obrazu(decyzja["na"], conn, run_id)
            else:
                ok, opis, tin, tout = proba_odpowiedzi(decyzja["dostawca"], decyzja["na"])
                _zapisz_koszt(conn, run_id, decyzja["dostawca"], decyzja["na"], tin, tout, 0, ok, opis)
            if not ok:
                odrzucone.append({**decyzja, "dlaczego": "proba nowego modelu: " + opis})
                continue
            decyzja["proba"] = opis
            if decyzja["dostawca"] == "deepseek":
                powod = _wolno_placic(conn, run_id, decyzja["na"])
                if powod:
                    odrzucone.append({**decyzja, "dlaczego": powod})
                    continue
                szuka, opis_szukania = sprawdz_szukanie(decyzja["na"])
                if not szuka:
                    odrzucone.append({**decyzja, "dlaczego":
                                      "nowa wersja nie przeszla proby wyszukiwania: " + opis_szukania})
                    continue
            if decyzja["starsza"]:
                powod = _wolno_placic(conn, run_id, decyzja["z"])
                if powod:
                    odrzucone.append({**decyzja, "dlaczego": powod})
                    continue
                if decyzja["dostawca"] == "openai":
                    ok_stary, opis_stary = proba_obrazu(decyzja["z"], conn, run_id)
                else:
                    ok_stary, opis_stary, tin, tout = proba_odpowiedzi(decyzja["dostawca"], decyzja["z"])
                    _zapisz_koszt(conn, run_id, decyzja["dostawca"], decyzja["z"], tin, tout, 0,
                                  ok_stary, opis_stary)
                if ok_stary:
                    odrzucone.append({**decyzja, "dlaczego":
                                      "zastepca jest starszy, a obecny dalej odpowiada"})
                    continue
            zamiany[decyzja["rola"]] = {"z": decyzja["z"], "na": decyzja["na"],
                                        "kiedy": teraz, "powod": decyzja["powod"],
                                        "cena_zrodlo": decyzja["cena_zrodlo"]}
            if decyzja["cena"]:
                zamiany[decyzja["rola"]]["cena"] = decyzja["cena"]
                ceny_nowe[decyzja["na"]] = decyzja["cena"]
            wykonane.append(decyzja)

        for decyzja in odrzucone:
            print("  [nowe modele] bez zamiany %s: %s -> %s — %s"
                  % (decyzja["rola"], decyzja["z"], decyzja["na"], decyzja["dlaczego"]), flush=True)

        # PROBY WYSZUKIWANIA NA KAZDYM MODELU DEEPSEEKA W UZYCIU — takze na tym,
        # ktory dzis szuka. 10 wrzesnia narzedzie zniknelo po cichu i trwalo to
        # trzy dni; proba raz na dobe skraca to do jednego przebiegu. Na modelu,
        # ktory nie szuka, kosztuje ulamek centa, na szukajacym Pro okolo 3 centy.
        modele_deepseeka = sorted({getattr(config, r) for r, (d, _) in ROLE.items()
                                   if d == "deepseek"})
        for model in modele_deepseeka:
            if model in sprawdzone_szukanie:
                continue
            ostatnia = wyszukiwanie.get(model) or {}
            # Wynik innej drogi nie jest swiezy, niezaleznie od daty.
            if (not wymus and ostatnia.get("droga") == config.DROGA_WYSZUKIWANIA_DEEPSEEK
                    and _mlodsze_niz(ostatnia.get("kiedy"), WAZNE_GODZIN)):
                continue
            if _wolno_placic(conn, run_id, model):
                continue
            sprawdz_szukanie(model)

        historia = list(stan.get("historia") or [])[-50:]
        if wykonane or odrzucone:
            historia.append({"kiedy": teraz, "wykonane": wykonane, "odrzucone": odrzucone})
        zapisz({
            "wersja": WERSJA_STANU,
            "_sprawdzone": teraz,
            "zamiany": zamiany,
            "wyszukiwanie": wyszukiwanie,
            "u_dostawcow": {k: (sorted(v) if v else None) for k, v in listy.items()},
            "historia": historia,
        })
        # Persist first. A failed write must leave both the routing and the
        # success journal unchanged; a fresh process can replay this state.
        # Ceny tak samo: najpierw zapisane, potem wazne w tym procesie.
        for nazwa, cena in ceny_nowe.items():
            config.CENY_ZAMIAN[nazwa] = {**cena, "verified": False}
        for decyzja in wykonane:
            zastosuj_w_procesie(decyzja["rola"], decyzja["z"], decyzja["na"])
            _do_dziennika("zmiana_modelu", udane=True, rola=decyzja["rola"],
                          z=decyzja["z"], na=decyzja["na"], powod=decyzja["powod"])
            print("  [nowe modele] ZAMIANA %s: %s -> %s (%s; cena: %s)"
                  % (decyzja["rola"], decyzja["z"], decyzja["na"], decyzja["powod"],
                     decyzja["cena_zrodlo"]), flush=True)
        for model, wynik in wyszukiwanie.items():
            bylo = config.szuka_naprawde(model)
            config.PROBY_WYSZUKIWANIA[model] = wynik
            if wynik["dziala"] != bylo:
                _do_dziennika("zmiana_modelu", udane=True, rola="wyszukiwanie",
                              z=model, na=model if wynik["dziala"] else config.model_do_szukania("factcheck"),
                              powod="model znow szuka" if wynik["dziala"] else "model PRZESTAL szukac")
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
