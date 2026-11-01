# -*- coding: utf-8 -*-
"""CIEN PAMIECI (N1, 1.11.2026) — zapis, co wstrzyknelaby surowa pamiec WLASNEJ historii, BEZ wplywu na teksty.

PO CO. Wlasciciel (1.11): bot ma miec pamiec, osobowosc i cele. Sesja badawcza „Pamiec LLM" (protokol oceny, szkic
`b64d857`) stawia warunek: zanim cokolwiek trafi do promptu zywego konta, mamy zapis, CO i DLA KTOREGO zadania zostaloby
wstrzykniete, oraz okno bazowe. Ten modul jest tym zapisem. Dla kazdego komentarza (oba ramiona E23, oba bloki
komentarzy w `run.py`) liczy, co dalaby surowa pamiec wlasnej historii (`historia_konta.powiazane`) przy progu
produkcyjnym i dwoch luzniejszych, i dopisuje JEDEN rekord do `data/pamiec_cien.jsonl`. Nic nie wraca do promptu.

CZEGO NIE ROBI. Nie wola modelu ani sieci. Nie zapisuje tekstu celu ani nazwy autora (cudzych): tylko skrot KLUCZOWANY
(HMAC-SHA256, klucz w `data/.cien_klucz`, poza repozytoriami) i dlugosc. Nie zapisuje wynikow (`skutek`, statystyk) —
laczy sie je pozniej po czasie z dziennika, zeby nie wprowadzic wycieku z przyszlosci. Nie zmienia ramienia E23 ani
tego, co dostaje „on". Nie zatrzymuje komentarza: kazdy wyjatek jest polykany (fail-open), a nieudany zapis zostawia
slad w logu, nie w dzienniku.

HIGIENA (wymog sesji badawczej): flaga `config.PAMIEC_CIEN`, limit czasu pojedynczego zapisu (`LIMIT_S`), limit rozmiaru
pliku (`MAKS_BAJTOW`), pole `status` w kazdym rekordzie (inaczej brakujace rekordy po cichu znieksztalcalyby analize),
zero polaczen sieciowych. W `NIA_TRYB=test` modul NIE pisze do domyslnego pliku (testy nie zasmieca danych), chyba ze
podano `plik` jawnie.

`would_arm`: przydzial, jaki dalaby ZAMROZONA funkcja losowania (`stages.los_stale("pamiec_n3", adres celu) < 0.10`),
w cieniu nieuzywany — dzieki temu funkcje mozna sprawdzic przed zywa faza (N3), a przydzial nie moze byc potem
dobrany pod wynik.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

WERSJA_SCHEMATU = 1
STRATEGIA = "lexical_idf_cosine_v1"          # `historia_konta.powiazane` (bez embeddingow)
LIMIT_S = 2.0                                 # czas, powyzej ktorego rekord dostaje status „timeout" (bez pozycji)
MAKS_BAJTOW = 25 * 1024 * 1024                # po przekroczeniu przestajemy pisac (jeden komunikat w logu)
WSPOLCZYNNIK_N3 = 0.10                        # ekspozycja pierwszego kroku zywej fazy (protokol P1: 10%)
NAZWA_LOSOWANIA_N3 = "pamiec_n3"

_ostrzezono_o_rozmiarze = False


def _plik() -> Path:
    return config.DATA_DIR / "pamiec_cien.jsonl"


@functools.lru_cache(maxsize=1)
def _kod() -> str:
    try:
        import stages
        return stages._wersja_kodu() or ""
    except Exception:                       # noqa: BLE001
        return ""


def _klucz() -> bytes | None:
    """Klucz do skrotow kluczowanych; tworzony raz, tryb 0600. Brak klucza = rekord bez skrotow, nie awaria."""
    sciezka = config.DATA_DIR / ".cien_klucz"
    try:
        if sciezka.exists():
            k = sciezka.read_bytes()
            if len(k) >= 16:
                return k
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        k = os.urandom(32)
        tmp = sciezka.with_suffix(".nowy")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
        os.replace(tmp, sciezka)
        return k
    except OSError:
        return None


def _hmac(klucz: bytes | None, tekst: str) -> str | None:
    if klucz is None or not tekst:
        return None
    return hmac.new(klucz, tekst.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _sha(tekst: str) -> str:
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()[:16]


def profile() -> list[tuple[str, float, int, int]]:
    """(nazwa, min. podobienstwo, min. rzadkich, ile). „produkcja" zawsze z `HISTORIA_KONTA_*`: nie moze sie rozjechac
    z tym, co dostaje E23 „on"."""
    return [("produkcja", config.HISTORIA_KONTA_MIN_PODOBIENSTWA, config.HISTORIA_KONTA_MIN_RZADKICH,
             config.HISTORIA_KONTA_WPISOW),
            *[tuple(p) for p in config.PAMIEC_CIEN_PROFILE]]


def digest_konfiguracji() -> str:
    dane = {"profile": profile(), "okno_dni": config.HISTORIA_KONTA_OKNO_DNI,
            "znaki_wpisu": config.HISTORIA_KONTA_ZNAKI, "blok_znakow": config.HISTORIA_KONTA_BLOK_ZNAKOW,
            "znaki_na_token": config.CHARS_PER_TOKEN, "pula": config.PAMIEC_CIEN_PULA, "strategia": STRATEGIA}
    return _sha(json.dumps(dane, sort_keys=True))


def _tokeny(tekst: str) -> int:
    return int(min(len(tekst), config.HISTORIA_KONTA_ZNAKI) / config.CHARS_PER_TOKEN) + 1


def _aktywne(teraz: datetime) -> list[str]:
    """Nazwy eksperymentow z `config.EKSPERYMENTY`, ktore trwaja w dniu decyzji (okno dat). Ramiona poza E23 zalezą od
    klucza zadania i nie sa tu znane, wiec zapisujemy tylko, ze eksperyment trwal."""
    try:
        import stages
        dzien = teraz.date().isoformat()
        return sorted(n for n in (getattr(config, "EKSPERYMENTY", None) or {}) if stages.ramie(n, 0, dzien))
    except Exception:                       # noqa: BLE001
        return []


def _pozycje(wpisy: list[dict[str, Any]], teraz: datetime) -> list[dict[str, Any]]:
    out = []
    for rank, w in enumerate(wpisy, 1):
        out.append({"item_id": _sha(w["tekst"]), "kind": w["rodzaj"],
                    "age_days": round((teraz - w["kiedy"]).total_seconds() / 86400, 2), "rank": rank,
                    "score": w["wynik"], "rare_terms": w.get("rzadkie"), "reason": "lexical",
                    "tokens_est": _tokeny(w["tekst"])})
    return out


def _agregaty(poz: list[dict[str, Any]], n_kandydatow: int) -> dict[str, Any]:
    ile_znakow_budzetu = config.HISTORIA_KONTA_BLOK_ZNAKOW / config.CHARS_PER_TOKEN
    suma = sum(p["tokens_est"] for p in poz)
    return {"n_candidates": n_kandydatow, "n_returned": len(poz), "tokens_total": suma,
            "over_budget": suma > ile_znakow_budzetu}


def rekord(tekst_celu: str, klucz_celu: str, *, zadanie: str = "komentarz", ramie_e23: str = "",
           run_id: int | None = None, autor: str = "", teraz: datetime | None = None,
           historia: Path | None = None) -> dict[str, Any]:
    """Zbuduj rekord cienia (bez zapisu). Rzuca wyjatek tylko przy bledzie programisty; `cien_komentarza` go lapie."""
    import historia_konta
    import stages
    start = time.monotonic()
    teraz = teraz or datetime.now(timezone.utc)
    klucz_hmac = _klucz()
    rec: dict[str, Any] = {
        "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU, "code_commit": _kod(),
        "run_id": run_id, "run_id_basis": "native" if run_id is not None else "absent",
        "journal_ref": None, "journal_ref_basis": "none_at_decision_time",
        "occurred_at": teraz.isoformat(timespec="seconds"), "as_of": teraz.isoformat(timespec="seconds"),
        "task_type": zadanie, "arm_e23": ramie_e23 or None, "active_experiments": _aktywne(teraz),
        "mode": (os.environ.get("NIA_TRYB") or "produkcja").strip().lower(),
        "query": {"hmac": _hmac(klucz_hmac, " ".join((tekst_celu or "").split())),
                  "chars": len(tekst_celu or ""), "author_hmac": _hmac(klucz_hmac, autor or "")},
        "strategy": {"id": STRATEGIA, "config_digest": digest_konfiguracji(), "embedder": None,
                     "profiles": [{"name": n, "min_score": s, "min_rare_terms": r, "top": k}
                                  for n, s, r, k in profile()]},
        "would_arm": {"fn": "stages.los_stale(%r, adres_celu) < %s" % (NAZWA_LOSOWANIA_N3, WSPOLCZYNNIK_N3),
                      "seed_name": NAZWA_LOSOWANIA_N3, "stratum": zadanie, "used_in_shadow": False,
                      "arm": ("B" if stages.los_stale(NAZWA_LOSOWANIA_N3, klucz_celu) < WSPOLCZYNNIK_N3 else "A")},
        "status": "ok", "error_code": None,
    }
    plik_dz = historia or (config.DATA_DIR / "dziennik.jsonl")
    stat: dict[str, Any] = {}
    # Zapytanie produkcyjne i najluzniejsze — dwa odczyty dziennika. Produkcyjne liczymy OSOBNO (a nie filtrujemy z puli),
    # zeby profil „produkcja" byl DOKLADNIE tym, co zwrociloby `historia_konta.blok` dla tego komentarza.
    prod = historia_konta.powiazane(tekst_celu or "", teraz=teraz, plik=plik_dz, statystyki=stat)
    luzny_prog = min([p[1] for p in profile()])
    pula = historia_konta.powiazane(
        tekst_celu or "", teraz=teraz, plik=plik_dz, min_podobienstwa=luzny_prog, min_rzadkich=0,
        ile=config.PAMIEC_CIEN_PULA)
    rec["index_snapshot"] = {"pool_size": stat.get("pula"), "newest_item_at": stat.get("najnowszy"),
                             "window_days": config.HISTORIA_KONTA_OKNO_DNI,
                             "journal_bytes": plik_dz.stat().st_size if plik_dz.exists() else None}
    wyniki: dict[str, Any] = {}
    for nazwa, prog, rzadkich, ile in profile():
        if nazwa == "produkcja":
            wybrane = sorted(prod, key=lambda k: (-k["wynik"], -k["kiedy"].timestamp()))[:ile]
            n_kand = len(prod)
        else:
            kand = [w for w in pula if w["wynik"] >= prog and w.get("rzadkie", 0) >= rzadkich]
            kand.sort(key=lambda k: (-k["wynik"], -k["kiedy"].timestamp()))
            wybrane, n_kand = kand[:ile], len(kand)
        poz = _pozycje(wybrane, teraz)
        wyniki[nazwa] = {"items": poz, **_agregaty(poz, n_kand)}
    rec["results"] = wyniki
    rec["latency_ms"] = int((time.monotonic() - start) * 1000)
    if time.monotonic() - start > LIMIT_S:
        rec["status"] = "timeout"
    return rec


def cien_komentarza(tekst_celu: str, klucz_celu: str, ramie_e23: str = "", *, zadanie: str = "komentarz",
                    run_id: int | None = None, autor: str = "", teraz: datetime | None = None,
                    plik: Path | None = None, historia: Path | None = None) -> dict[str, Any] | None:
    """Zapisz rekord cienia dla jednego komentarza i go zwroc; None, gdy wylaczone, pominiete albo nieudane.

    FAIL-OPEN: nic stad nie moze zatrzymac komentarza. `plik` jawnie = zapis takze w `NIA_TRYB=test` (testy).
    """
    global _ostrzezono_o_rozmiarze
    try:
        if not getattr(config, "PAMIEC_CIEN", False):
            return None
        if plik is None and (os.environ.get("NIA_TRYB") or "").strip().lower() == "test":
            return None
        cel_pliku = plik or _plik()
        try:
            rozmiar = cel_pliku.stat().st_size
        except OSError:
            rozmiar = 0
        if rozmiar > MAKS_BAJTOW:
            if not _ostrzezono_o_rozmiarze:
                print("  [cien] plik pamiec_cien.jsonl przekroczyl %d MB — nie zapisuje" % (MAKS_BAJTOW // 1048576),
                      flush=True)
                _ostrzezono_o_rozmiarze = True
            return None
        try:
            rec = rekord(tekst_celu, klucz_celu, zadanie=zadanie, ramie_e23=ramie_e23, run_id=run_id, autor=autor,
                         teraz=teraz, historia=historia)
        except Exception as exc:            # noqa: BLE001 — rekord z bledem jest danymi: brak zostalby niezauwazony
            rec = {"record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU, "code_commit": _kod(),
                   "run_id": run_id, "occurred_at": (teraz or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
                   "task_type": zadanie, "arm_e23": ramie_e23 or None, "status": "error",
                   "error_code": type(exc).__name__}
        cel_pliku.parent.mkdir(parents=True, exist_ok=True)
        with open(cel_pliku, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
    except Exception as exc:                # noqa: BLE001
        try:
            print("  [cien] zapis nieudany (%s)" % type(exc).__name__, flush=True)
        except Exception:                   # noqa: BLE001
            pass
        return None
