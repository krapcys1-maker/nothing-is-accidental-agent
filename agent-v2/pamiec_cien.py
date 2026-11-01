# -*- coding: utf-8 -*-
"""CIEN PAMIECI (N1, 1.11.2026) — zapis, co wstrzyknelaby surowa pamiec WLASNEJ historii, BEZ wplywu na teksty.

PO CO. Wlasciciel (1.11): bot ma miec pamiec, osobowosc i cele. Sesja badawcza „Pamiec LLM" (protokol oceny) stawia
warunek: zanim cokolwiek trafi do promptu zywego konta, mamy zapis, CO i DLA KTOREGO zadania zostaloby wstrzykniete, oraz
okno bazowe. Ten modul jest tym zapisem. Przy kazdej PROBIE komentarza (oba ramiona E23, oba bloki komentarzy w `run.py`;
rekord powstaje przy wyborze celu, a nie przy publikacji — patrz `publish_run` i `journal_ref`) liczy, co dalaby surowa
pamiec wlasnej historii (`historia_konta.powiazane`) przy progu produkcyjnym i dwoch luzniejszych, i dopisuje JEDEN rekord
do `data/pamiec_cien.jsonl`. Nic nie wraca do promptu.

CZEGO NIE ROBI. Nie wola modelu ani sieci. Nie zapisuje tekstu celu ani nazwy autora (cudzych): tylko skrot KLUCZOWANY
(HMAC-SHA256) i dlugosc. KLUCZ LEZY w `data/.cien_klucz`, w tym samym katalogu co rekordy: chroni go `.gitignore` (`data/`) i
tryb 0600, a NIE polozenie poza drzewem. Repozytorium bota na GitHubie jest PUBLICZNE, wiec nigdy nie wolno kopiowac
`data/` w calosci do laboratorium ani do repo; eksportowac mozna tylko `pamiec_cien.jsonl`, bez klucza. Nie zapisuje wynikow (`skutek`,
statystyk) — laczy sie je pozniej z dziennikiem, zeby nie wprowadzic wycieku z przyszlosci. Nie zmienia ramienia E23 ani
tego, co dostaje „on". Nie zatrzymuje komentarza: kazdy wyjatek jest polykany (fail-open), a po awarii zostaje linia
`[cien] ...` w logu przebiegu.

LACZENIE Z DZIENNIKIEM. Wpis dziennika powstaje po publikacji, wiec rekord ma `journal_ref: null`. Klucz zlaczenia to
`query.target_hmac` = HMAC dokladnie tej wartosci, ktora `run` zapisuje w dzienniku jako `gdzie` (adres artykulu albo id
notki, ucieta do 200 znakow), plus czas. `query.hmac` (skrot tresci zapytania) sluzy do sprawdzania powtorek, nie do zlaczen.

HIGIENA (wymog sesji badawczej): flaga `config.PAMIEC_CIEN`, `LIMIT_S` (ETYKIETA `timeout` nadawana po policzeniu, nie
przerwanie), limit rozmiaru pliku (`MAKS_BAJTOW`), pole `status` w kazdym rekordzie: `ok`, `degraded` (cien policzony, ale
bez klucza albo bez dziennika: `degraded_reason`), `timeout`, `error` (inaczej brakujace i niepelne rekordy po cichu
znieksztalcalyby analize), zero polaczen sieciowych. W `NIA_TRYB=test` modul NIE pisze do domyslnego pliku, chyba ze
podano `plik` jawnie. Katalog danych wskazuje wywolujacy (`katalog=`), zeby testy z podmieniona konfiguracja `run` nie
pisaly do prawdziwego `data/`.

`would_arm`: przydzial, jaki dalaby ZAMROZONA funkcja losowania (`stages.los_stale("pamiec_n3", adres celu) < 0.10`),
w cieniu nieuzywany — dzieki temu funkcje mozna sprawdzic przed zywa faza (N3), a przydzial nie moze byc potem
dobrany pod wynik.
"""
from __future__ import annotations

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
LIMIT_S = 2.0                                 # po przekroczeniu rekord dostaje status „timeout” (etykieta, nie przerwanie)
MAKS_BAJTOW = 25 * 1024 * 1024                # po przekroczeniu przestajemy pisac (jeden komunikat w logu na proces)
WSPOLCZYNNIK_N3 = 0.10                        # ekspozycja pierwszego kroku zywej fazy (protokol P1: 10%)
NAZWA_LOSOWANIA_N3 = "pamiec_n3"

_ostrzezono_o_rozmiarze = False


def _katalog(katalog: Path | str | None) -> Path:
    return Path(katalog) if katalog else Path(config.DATA_DIR)


def _kod() -> str:
    try:
        import stages
        return getattr(stages, "WERSJA_KODU", "") or ""
    except Exception:                       # noqa: BLE001
        return ""


def _klucz(katalog: Path) -> tuple[bytes | None, str | None]:
    """(klucz, id klucza). Tworzony raz, tryb 0600. Brak klucza = (None, None): rekord ma status `degraded`.

    Id klucza (8 hex z SHA-256 klucza) trafia do kazdego rekordu, zeby utrata albo wymiana klucza byla WIDOCZNA w danych
    (inaczej ten sam cel dostalby po cichu inny skrot i analiza dzielilaby rekordy na rozlaczne grupy)."""
    sciezka = katalog / ".cien_klucz"
    try:
        if sciezka.exists():
            k = sciezka.read_bytes()
            if len(k) >= 16:
                return k, hashlib.sha256(k).hexdigest()[:8]
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        k = os.urandom(32)
        tmp = sciezka.with_suffix(".nowy")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k)
        os.replace(tmp, sciezka)
        return k, hashlib.sha256(k).hexdigest()[:8]
    except OSError:
        return None, None


def _hmac(klucz: bytes | None, tekst: str) -> str | None:
    if klucz is None or not tekst:
        return None
    return hmac.new(klucz, tekst.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:24]


def _sha(tekst: str) -> str:
    return hashlib.sha256(tekst.encode("utf-8", "replace")).hexdigest()[:16]


def _uchwyt(autor: str) -> str:
    """Znormalizowany uchwyt (jak w dzienniku: bez @, male litery); pusty, gdy go nie ma."""
    return (autor or "").strip().lstrip("@").lower()[:60]


def profile() -> list[tuple[str, float, int, int]]:
    """(nazwa, min. podobienstwo, min. rzadkich terminow, ile). „produkcja" zawsze z `HISTORIA_KONTA_*`: nie moze sie rozjechac
    z tym, co dostaje E23 „on"."""
    return [("produkcja", config.HISTORIA_KONTA_MIN_PODOBIENSTWA, config.HISTORIA_KONTA_MIN_RZADKICH,
             config.HISTORIA_KONTA_WPISOW),
            *[tuple(p) for p in config.PAMIEC_CIEN_PROFILE]]


def digest_konfiguracji() -> str:
    dane = {"profile": profile(), "okno_dni": config.HISTORIA_KONTA_OKNO_DNI,
            "znaki_wpisu": config.HISTORIA_KONTA_ZNAKI, "blok_znakow": config.HISTORIA_KONTA_BLOK_ZNAKOW,
            "znaki_na_token": config.CHARS_PER_TOKEN, "pula": config.PAMIEC_CIEN_PULA, "strategia": STRATEGIA}
    return _sha(json.dumps(dane, sort_keys=True))


def _tokeny_wpisu(tekst: str) -> int:
    return int(min(len(tekst), config.HISTORIA_KONTA_ZNAKI) / config.CHARS_PER_TOKEN) + 1


def _tokeny_naglowka() -> int:
    """Stala czesc bloku (naglowek i zasada uzycia z `historia_konta.blok`), liczona tylko gdy blok niepusty."""
    import historia_konta
    return int((len(historia_konta._NAGLOWEK) + len(historia_konta._ZASADA) + 30) / config.CHARS_PER_TOKEN) + 1


def _aktywne(teraz: datetime) -> list[str]:
    """Nazwy eksperymentow z `config.EKSPERYMENTY`, ktore trwaja w dniu decyzji (okno dat). Ramiona poza E23 zaleza od
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
                    "tokens_est": _tokeny_wpisu(w["tekst"])})
    return out


def _agregaty(poz: list[dict[str, Any]], n_kandydatow: int, ucieta_pula: bool) -> dict[str, Any]:
    wpisy = sum(p["tokens_est"] for p in poz)
    naglowek = _tokeny_naglowka() if poz else 0
    suma = wpisy + naglowek
    return {"n_candidates": n_kandydatow, "n_candidates_capped": ucieta_pula, "n_returned": len(poz),
            "tokens_entries": wpisy, "tokens_overhead": naglowek, "tokens_total": suma,
            "over_budget": suma > config.HISTORIA_KONTA_BLOK_ZNAKOW / config.CHARS_PER_TOKEN}


def rekord(tekst_celu: str, klucz_celu: str, *, zadanie: str = "komentarz", ramie_e23: str = "",
           run_id: int | None = None, autor: str = "", wyslij: bool | None = None, teraz: datetime | None = None,
           historia: Path | None = None, katalog: Path | str | None = None) -> dict[str, Any]:
    """Zbuduj rekord cienia (bez zapisu). Szkielet powstaje PRZED wyszukiwaniem, wiec awaria wyszukiwania zostawia pelny
    rekord ze `status: error` (bez pozycji), a nie okrojony."""
    import historia_konta
    import stages
    start = time.monotonic()
    teraz = teraz or datetime.now(timezone.utc)
    kat = _katalog(katalog)
    klucz_hmac, id_klucza = _klucz(kat)
    gdzie = str(klucz_celu or "")[:200]                       # DOKLADNIE to, co `run` zapisuje w dzienniku jako `gdzie`
    rec: dict[str, Any] = {
        "record_id": uuid.uuid4().hex[:16], "schema_version": WERSJA_SCHEMATU, "code_commit": _kod(),
        "run_id": run_id, "run_id_basis": "native" if run_id is not None else "absent",
        "journal_ref": None, "journal_ref_basis": "none_at_decision_time",
        "occurred_at": teraz.isoformat(timespec="seconds"), "as_of": teraz.isoformat(timespec="seconds"),
        "task_type": zadanie, "arm_e23": ramie_e23 or None, "eksperymenty": _aktywne(teraz),
        "mode": (os.environ.get("NIA_TRYB") or "produkcja").strip().lower(), "publish_run": wyslij,
        "query": {"hmac": _hmac(klucz_hmac, " ".join((tekst_celu or "").split())), "key_id": id_klucza,
                  "chars": len(tekst_celu or ""),
                  "author_hmac": _hmac(klucz_hmac, "autor|" + _uchwyt(autor)) if _uchwyt(autor) else None,
                  "target_hmac": _hmac(klucz_hmac, "cel|" + gdzie) if gdzie else None},
        "strategy": {"id": STRATEGIA, "config_digest": digest_konfiguracji(), "embedder": None,
                     "profiles": [{"name": n, "min_score": s, "min_rare_terms": r, "top": k}
                                  for n, s, r, k in profile()]},
        "would_arm": {"fn": "stages.los_stale(%r, adres_celu) < %s" % (NAZWA_LOSOWANIA_N3, WSPOLCZYNNIK_N3),
                      "seed_name": NAZWA_LOSOWANIA_N3, "stratum": zadanie, "used_in_shadow": False,
                      "arm": ("B" if stages.los_stale(NAZWA_LOSOWANIA_N3, klucz_celu) < WSPOLCZYNNIK_N3 else "A")},
        "index_snapshot": None, "results": None,
        "status": "ok", "degraded_reason": None, "error_code": None,
    }
    plik_dz = historia or (kat / "dziennik.jsonl")
    try:
        stat: dict[str, Any] = {}
        luzny_prog = min(p[1] for p in profile())
        pula = historia_konta.powiazane(
            tekst_celu or "", teraz=teraz, plik=plik_dz, min_podobienstwa=luzny_prog, min_rzadkich=0,
            ile=config.PAMIEC_CIEN_PULA, statystyki=stat)
        ucieta = len(pula) >= config.PAMIEC_CIEN_PULA
        rec["index_snapshot"] = {"pool_size": stat.get("pula"), "newest_item_at": stat.get("najnowszy"),
                                 "window_days": config.HISTORIA_KONTA_OKNO_DNI,
                                 "journal_bytes": plik_dz.stat().st_size if plik_dz.exists() else None}
        wyniki: dict[str, Any] = {}
        for nazwa, prog, rzadkich, ile in profile():
            if nazwa == "produkcja" and ucieta:
                # Pula ucieta do PAMIEC_CIEN_PULA wg wyniku bez progu rzadkich: profil produkcyjny liczymy wprost, zeby
                # byl dokladnie tym, co zwraca `historia_konta.powiazane` (i `n_candidates` byl prawdziwy).
                kand = historia_konta.powiazane(tekst_celu or "", teraz=teraz, plik=plik_dz, min_podobienstwa=prog,
                                                min_rzadkich=rzadkich, ile=config.PAMIEC_CIEN_PULA)
                ucieta_profil = len(kand) >= config.PAMIEC_CIEN_PULA
            else:
                kand = [w for w in pula if w.get("cos", w["wynik"]) >= prog and w.get("rzadkie", 0) >= rzadkich]
                ucieta_profil = ucieta
            kand = sorted(kand, key=lambda k: (-k["wynik"], -k["kiedy"].timestamp()))
            poz = _pozycje(kand[:ile], teraz)
            wyniki[nazwa] = {"items": poz, **_agregaty(poz, len(kand), ucieta_profil)}
        rec["results"] = wyniki
        if stat.get("pula") is None:
            rec["status"], rec["degraded_reason"] = "degraded", "no_index"
        if klucz_hmac is None:
            rec["status"], rec["degraded_reason"] = "degraded", "no_key"
    except Exception as exc:                # noqa: BLE001 — rekord z bledem jest danymi: brak zostalby niezauwazony
        rec["status"], rec["error_code"] = "error", type(exc).__name__
    rec["latency_ms"] = int((time.monotonic() - start) * 1000)
    if rec["status"] == "ok" and time.monotonic() - start > LIMIT_S:
        rec["status"] = "timeout"
    return rec


def _dopisz(plik: Path, rec: dict[str, Any]) -> None:
    plik.parent.mkdir(parents=True, exist_ok=True)
    koniec_ok = True
    try:
        with open(plik, "rb") as f:
            f.seek(0, 2)
            if f.tell():
                f.seek(-1, 2)
                koniec_ok = f.read(1) == b"\n"
    except OSError:
        pass
    with open(plik, "a", encoding="utf-8") as f:
        if not koniec_ok:                    # ucieta linia po ENOSPC/zabitym procesie nie skleja sie z nastepnym rekordem
            f.write("\n")
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cien_komentarza(tekst_celu: str, klucz_celu: str, ramie_e23: str = "", *, zadanie: str = "komentarz",
                    run_id: int | None = None, autor: str = "", wyslij: bool | None = None,
                    teraz: datetime | None = None, plik: Path | None = None, historia: Path | None = None,
                    katalog: Path | str | None = None) -> dict[str, Any] | None:
    """Zapisz rekord cienia dla jednej proby komentarza i go zwroc; None, gdy wylaczone, pominiete albo nieudane.

    FAIL-OPEN: nic stad nie moze zatrzymac komentarza. `plik` jawnie = zapis takze w `NIA_TRYB=test` (testy).
    Kazdy zapis i kazda awaria zostawia jedna linie `[cien] ...` w logu przebiegu (pozytywny slad z produkcji).
    """
    global _ostrzezono_o_rozmiarze
    try:
        if not getattr(config, "PAMIEC_CIEN", False):
            return None
        if plik is None and (os.environ.get("NIA_TRYB") or "").strip().lower() == "test":
            return None
        cel_pliku = plik or (_katalog(katalog) / "pamiec_cien.jsonl")
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
        rec = rekord(tekst_celu, klucz_celu, zadanie=zadanie, ramie_e23=ramie_e23, run_id=run_id, autor=autor,
                     wyslij=wyslij, teraz=teraz, historia=historia, katalog=katalog)
        _dopisz(cel_pliku, rec)
        poz = ((rec.get("results") or {}).get("produkcja") or {}).get("n_returned")
        print("  [cien] rekord status=%s pozycji(produkcja)=%s ms=%s" % (rec["status"], poz, rec.get("latency_ms")),
              flush=True)
        return rec
    except Exception as exc:                # noqa: BLE001
        try:
            print("  [cien] zapis nieudany (%s)" % type(exc).__name__, flush=True)
        except Exception:                   # noqa: BLE001
            pass
        return None
