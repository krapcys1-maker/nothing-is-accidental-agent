"""Czy autor wpisu odpowiada komentujacym — cecha CELU, nie tekstu (E23, 28.10.2026).

Analiza 965 watkow i 24 tys. komentarzy (`docs/KOMENTARZE_STYL_I_ROZMOWA_2026-10-28.md`) pokazala,
ze najsilniejsza i najtrwalsza cecha celu to to, czy autor wpisu odpisuje komentujacym: autor, ktory
nikomu nie odpisuje, odpowiada nam w ok. 3% przypadkow, a taki, ktory odpisuje wiekszosci — w ok. 50%.
Ok. polowa naszych komentarzy trafiala do tych pierwszych. Cecha jest stala u autora (korelacja
rang ok. 0,57 miedzy jego watkami), wiec da sie ja ocenic z JEGO wczesniejszych watkow, zanim cokolwiek
napiszemy.

CO LICZYMY: odsetek komentarzy PIERWSZEGO poziomu od innych osob (bez nas, bez kont siostrzanych, bez
autora), pod ktorymi autor wpisu odpisal. Artykuly: ostatnie `ODPOWIADALNOSC_POSTY` wpisow publikacji z
co najmniej czterema takimi komentarzami; notki: sam watek tej notki (min. dwa komentarze), bo notki
nie maja „poprzednich watkow" dostepnych tanim zapytaniem.

CO Z TYM ROBIMY: `wedlug_odpowiadalnosci` odklada cele o niskiej odpowiadalnosci NA KONIEC kolejki. Nie
wykluczamy ich: kolejka sluzy do wypelnienia miejsc, wiec taki cel dostaje miejsce dopiero, gdy nie ma
lepszych. Czesc z nich (`ODPOWIADALNOSC_PROBA_BEZ_FILTRA`, losowana deterministycznie po adresie)
idzie bez kary — inaczej zamknelibysmy sie w kilku responsywnych kontach, a to wzmacnia petle wzajemnych
polubien i nie mierzy tego, o co nam chodzi.

NIEWIEDZA JEST NEUTRALNA. Brak zapytania, blad sieci, za malo komentarzy → klasa „nieznana", cel nie jest
karany. Odczyt idzie publicznym API Substacka (te same adresy, z ktorych korzysta przegladarka), bez
logowania, z krotka przerwa miedzy zapytaniami i z limitem zapytan oraz czasu na jedno wywolanie.
Bez modelu, bez kosztow.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

import config

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")
_PAUZA_S = 0.5
_TIMEOUT_S = 12


def _pobierz(url: str) -> Any:
    """JSON z publicznego adresu albo None (kazdy blad, takze 403/404/429, to „nie wiem")."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as f:
            dane = json.loads(f.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        dane = None
    time.sleep(_PAUZA_S)
    return dane


def _czas(napis: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(napis).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _dojrzaly(c: dict[str, Any], teraz: datetime | None, min_wiek_h: float) -> bool:
    """Czy komentarz mial juz czas na odpowiedz autora. Bez daty (albo bez ograniczenia) — tak."""
    if not min_wiek_h or teraz is None:
        return True
    t = _czas(c.get("date"))
    return t is None or (teraz - t) >= timedelta(hours=min_wiek_h)


def _wlasne_uchwyty() -> set[str]:
    return {str(x).lower().lstrip("@") for x in
            (config.SUBSTACK_HANDLE, *getattr(config, "UCHWYTY_SIOSTRZANE", ())) if x}


def _cudzy(c: dict[str, Any], uid_autorow: set[Any]) -> bool:
    """Komentarz od osoby spoza nas, kont siostrzanych i autora wpisu."""
    uid = c.get("user_id")
    if c.get("deleted") or uid is None:
        return False
    if (uid in uid_autorow or uid in getattr(config, "KONTA_SIOSTRZANE", frozenset())
            or uid in getattr(config, "KONTO_WLASNE_UID", frozenset())):
        return False
    if str((c.get("handle") or "")).lower().lstrip("@") in _wlasne_uchwyty():
        return False
    return not (c.get("metadata") or {}).get("is_author")


def _od_autora(c: dict[str, Any], uid_autorow: set[Any]) -> bool:
    return (not c.get("deleted")
            and (c.get("user_id") in uid_autorow or bool((c.get("metadata") or {}).get("is_author"))))


def policz_artykul(komentarze: list[dict[str, Any]], uid_autorow: set[Any], *,
                   teraz: datetime | None = None, min_wiek_h: float = 0) -> tuple[int, int]:
    """(komentarze 1. poziomu od innych, z nich z BEZPOSREDNIA odpowiedzia autora).

    Z `teraz` i `min_wiek_h` liczy tylko komentarze starsze niz `min_wiek_h` godzin: autor, ktory jeszcze nie
    zajrzal, nie jest autorem, ktory nie odpisuje (przeglad 28.10: bez tego 44% „niskich" z pierwszej godziny
    watku bylo w pelnym watku „ok").
    """
    ile = odp = 0
    for c in komentarze or []:
        if not isinstance(c, dict) or not _cudzy(c, uid_autorow) or not _dojrzaly(c, teraz, min_wiek_h):
            continue
        ile += 1
        if any(isinstance(d, dict) and _od_autora(d, uid_autorow) for d in (c.get("children") or [])):
            odp += 1
    return ile, odp


def _rozpakuj(x: Any) -> dict[str, Any]:
    """Odpowiedzi w watku notki bywaja opakowane `{type, comment}`."""
    if isinstance(x, dict) and isinstance(x.get("comment"), dict):
        return x["comment"]
    return x if isinstance(x, dict) else {}


def policz_notke(watek: dict[str, Any], *, teraz: datetime | None = None,
                 min_wiek_h: float = 0) -> tuple[int, int]:
    """To samo dla watku notki (`reader/comment/<id>/replies`): galezie = komentarze 1. poziomu.

    Odpowiedzia autora jest KAZDY jego komentarz w galezi (nie tylko bezposredni), bo API oddaje potomkow
    splaszczonych — odrobine hojniej niz w artykulach, gdzie liczy sie bezposrednie dziecko.
    """
    korzen = watek.get("rootComment") or {}
    uid_autorow = {korzen.get("user_id")} - {None}
    if not uid_autorow:
        return 0, 0
    ile = odp = 0
    for g in watek.get("commentBranches") or []:
        glowny = _rozpakuj(g.get("comment") if isinstance(g, dict) else None)
        if not glowny or not _cudzy(glowny, uid_autorow) or not _dojrzaly(glowny, teraz, min_wiek_h):
            continue
        ile += 1
        if any(_od_autora(_rozpakuj(d), uid_autorow) for d in (g.get("descendantComments") or [])):
            odp += 1
    return ile, odp


def _wynik(ile: int, odp: int, minimum: int) -> float | None:
    return round(odp / ile, 3) if ile >= minimum else None


def _klasa(wynik: float | None) -> str:
    if wynik is None:
        return "nieznana"
    return "niska" if wynik <= config.ODPOWIADALNOSC_NISKA else "ok"


def _artykul(host: str, wyklucz_slug: str, pobierz: Callable[[str], Any],
             teraz: datetime | None = None) -> dict[str, Any]:
    """Wynik autora z jego ostatnich wpisow (bez wpisu, ktory wlasnie rozwazamy)."""
    teraz = teraz or datetime.now(timezone.utc)
    min_wiek = config.ODPOWIADALNOSC_MIN_WIEK_KOMENTARZA_H
    lista = pobierz("https://%s/api/v1/archive?sort=new&search=&offset=0&limit=8" % host)
    if not isinstance(lista, list):
        return {"blad": True}
    od = teraz - timedelta(days=90)
    kand = [p for p in lista if isinstance(p, dict) and p.get("id")
            and p.get("slug") != wyklucz_slug and int(p.get("comment_count") or 0) >= 4
            and ((_czas(p.get("post_date")) or od) >= od)]
    ile = odp = nieudane = 0
    for p in kand[:config.ODPOWIADALNOSC_POSTY]:
        uid = {b.get("id") for b in (p.get("publishedBylines") or []) if isinstance(b, dict)} - {None}
        k = pobierz("https://%s/api/v1/post/%s/comments?token=&all_comments=true&sort=best_first"
                    % (host, p["id"]))
        if not isinstance(k, dict):
            nieudane += 1
            continue
        if not uid:
            continue
        a, b = policz_artykul(k.get("comments") or [], uid, teraz=teraz, min_wiek_h=min_wiek)
        ile, odp = ile + a, odp + b
    # ZA MALO Z POPRZEDNICH WPISOW (mala publikacja, malo komentarzy): dolicz watek wpisu, ktory wlasnie
    # rozwazamy. To tez zachowanie autora — odpowiada albo nie — a bez tego trzy czwarte malych publikacji
    # zostawaloby „nieznane" (proba na zywo 28.10: 3 z 4 artykulow). Kosztuje dwa zapytania, tylko w tym przypadku.
    if ile < config.ODPOWIADALNOSC_MIN_KOMENTARZY_ARTYKUL and wyklucz_slug:
        p = pobierz("https://%s/api/v1/posts/%s" % (host, quote(wyklucz_slug)))
        if isinstance(p, dict) and p.get("id"):
            uid = {b.get("id") for b in (p.get("publishedBylines") or []) if isinstance(b, dict)} - {None}
            k = pobierz("https://%s/api/v1/post/%s/comments?token=&all_comments=true&sort=best_first" % (host, p["id"]))
            if isinstance(k, dict) and uid:
                a, b = policz_artykul(k.get("comments") or [], uid, teraz=teraz, min_wiek_h=min_wiek)
                ile, odp = ile + a, odp + b
            elif not isinstance(k, dict):
                nieudane += 1
        elif not isinstance(p, dict):
            nieudane += 1
    wynik = _wynik(ile, odp, config.ODPOWIADALNOSC_MIN_KOMENTARZY_ARTYKUL)
    # Brak wyniku PRZEZ NIEUDANE POBRANIA to blad (krotki TTL), nie „autor ma za malo komentarzy" (dlugi TTL).
    if wynik is None and nieudane:
        return {"blad": True}
    return {"n": ile, "odp": odp, "wynik": wynik}


def _notka(nid: Any, pobierz: Callable[[str], Any], teraz: datetime | None = None) -> dict[str, Any]:
    d = pobierz("https://substack.com/api/v1/reader/comment/%s/replies?comment_id=%s"
                % (quote(str(nid)), quote(str(nid))))
    if not isinstance(d, dict):
        return {"blad": True}
    ile, odp = policz_notke(d, teraz=teraz or datetime.now(timezone.utc),
                            min_wiek_h=config.ODPOWIADALNOSC_MIN_WIEK_KOMENTARZA_H)
    return {"n": ile, "odp": odp, "wynik": _wynik(ile, odp, config.ODPOWIADALNOSC_MIN_KOMENTARZY_NOTKA)}


def _klucz(cel: dict[str, Any], notki: bool) -> str:
    """Klucz cache: host publikacji (artykuly) albo numer notki; pusty, gdy cel nie ma ani jednego."""
    if notki:
        return "note:%s" % cel.get("id") if cel.get("id") else ""
    host = urlparse(str(cel.get("url") or "")).netloc.lower()
    return "art:%s" % host if host else ""


def _slug(url: str) -> str:
    sciezka = urlparse(url or "").path.strip("/").split("/")
    return sciezka[1] if len(sciezka) >= 2 and sciezka[0] == "p" else ""


def _wczytaj(plik: Path) -> dict[str, Any]:
    try:
        d = json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _zapisz(plik: Path, dane: dict[str, Any]) -> None:
    """Atomowo, zeby przerwany przebieg nie zostawil polowy pliku."""
    try:
        plik.parent.mkdir(parents=True, exist_ok=True)
        tmp = plik.with_suffix(".tmp")
        tmp.write_text(json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(plik)
    except OSError:
        pass


def _swieze(wpis: Any, teraz: datetime, ttl: timedelta) -> bool:
    t = _czas((wpis or {}).get("t"))
    return t is not None and teraz - t < ttl


def ocen(cele: list[dict[str, Any]], *, notki: bool, teraz: datetime | None = None,
         plik: Path | None = None, pobierz: Callable[[str], Any] | None = None) -> list[dict[str, Any]]:
    """Nowe slowniki celow z `_odp_autora` = {"wynik": float|None, "n": int, "klasa": ...}."""
    pobierz = pobierz or _pobierz
    plik = plik or config.ODPOWIADALNOSC_PLIK
    teraz = teraz or datetime.now(timezone.utc)
    cache = _wczytaj(plik)
    ttl_ok = timedelta(hours=config.ODPOWIADALNOSC_TTL_NOTKI_H) if notki else timedelta(days=config.ODPOWIADALNOSC_TTL_DNI)
    ttl_blad = timedelta(hours=config.ODPOWIADALNOSC_BLAD_TTL_H)
    start = time.monotonic()
    zapytan = 0
    zmiana = False
    wyniki: dict[str, dict[str, Any]] = {}
    for cel in cele:
        klucz = _klucz(cel, notki)
        if not klucz or klucz in wyniki:
            continue
        wpis = cache.get(klucz)
        if _swieze(wpis, teraz, ttl_blad if (wpis or {}).get("blad") else ttl_ok):
            wyniki[klucz] = wpis
            continue
        if zapytan >= config.ODPOWIADALNOSC_MAKS_ZAPYTAN or time.monotonic() - start > config.ODPOWIADALNOSC_MAKS_SEKUND:
            wyniki[klucz] = {"wynik": None, "n": 0}
            continue
        zapytan += 1
        try:
            nowy = _notka(cel.get("id"), pobierz, teraz) if notki else _artykul(
                urlparse(str(cel.get("url") or "")).netloc, _slug(str(cel.get("url") or "")), pobierz, teraz)
        except Exception:               # noqa: BLE001 — to jest cecha pomocnicza, nie moze zatrzymac przebiegu
            nowy = {"blad": True}
        nowy["t"] = teraz.isoformat()
        cache[klucz] = nowy
        wyniki[klucz] = nowy
        zmiana = True
    if zmiana:
        # Wpisy starsze niz 30 dni nie sa potrzebne (TTL jest krotszy).
        granica = teraz - timedelta(days=30)
        cache = {k: v for k, v in cache.items() if (_czas((v or {}).get("t")) or granica) >= granica}
        _zapisz(plik, cache)
    out = []
    for cel in cele:
        w = wyniki.get(_klucz(cel, notki)) or {}
        wynik = None if w.get("blad") else w.get("wynik")
        out.append({**cel, "_odp_autora": {"wynik": wynik, "n": int(w.get("n") or 0), "klasa": _klasa(wynik)}})
    return out


def bez_kary(cel: dict[str, Any]) -> bool:
    """Czy ten cel o niskiej odpowiadalnosci idzie bez kary (probka eksploracyjna) — po adresie, stale."""
    klucz = str(cel.get("url") or cel.get("id") or "")
    los = int(hashlib.sha256(("odpowiadalnosc|%s" % klucz).encode()).hexdigest()[:8], 16) / 0x100000000
    return los < config.ODPOWIADALNOSC_PROBA_BEZ_FILTRA


def wedlug_odpowiadalnosci(cele: list[dict[str, Any]], *, notki: bool, **kw: Any) -> list[dict[str, Any]]:
    """Cele o niskiej odpowiadalnosci autora na koniec; reszta (i probka bez kary) w dotychczasowej kolejnosci."""
    if not cele or not config.ODPOWIADALNOSC_WLACZONA:
        return cele
    ocenione = ocen(cele, notki=notki, **kw)
    zdjete = [c for c in ocenione if c["_odp_autora"]["klasa"] == "niska" and not bez_kary(c)]
    reszta = [c for c in ocenione if not (c["_odp_autora"]["klasa"] == "niska" and not bez_kary(c))]
    znane = sum(1 for c in ocenione if c["_odp_autora"]["wynik"] is not None)
    niskie = sum(1 for c in ocenione if c["_odp_autora"]["klasa"] == "niska")
    print("  [cele] odpowiadalnosc autora (%s): znana u %d z %d, niska u %d (na koniec kolejki %d, bez kary %d)"
          % ("notki" if notki else "artykuly", znane, len(ocenione), niskie, len(zdjete), niskie - len(zdjete)),
          flush=True)
    return reszta + zdjete


def pola_dziennika(cel: dict[str, Any]) -> dict[str, Any]:
    """Pola do dziennika komentarza; brak oceny = brak pol (stare wpisy i atrapy bez zmian)."""
    o = cel.get("_odp_autora")
    if not isinstance(o, dict):
        return {}
    out: dict[str, Any] = {"autor_odp_klasa": o.get("klasa") or "nieznana"}
    if o.get("wynik") is not None:
        out["autor_odp"] = o["wynik"]
        out["autor_odp_n"] = int(o.get("n") or 0)
    return out
