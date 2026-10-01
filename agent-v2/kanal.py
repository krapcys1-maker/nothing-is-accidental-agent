"""Kanal czytelnika — jedyne zrodlo celow do komentowania.

Osobny plik, bo to jest CZYTANIE CUDZYCH tresci przez zalogowana sesje, a nie
publikowanie: browser.py rosl juz do tysiaca linii i mieszanie w nim odczytu
z dzialaniem utrudnialo czytanie obu.
"""

from __future__ import annotations

from typing import Any

import browser
import config

HISTORIA_KOMENTARZY = config.DATA_DIR / "gdzie_komentowalismy.json"


def _historia() -> dict:
    import json

    if not HISTORIA_KOMENTARZY.exists():
        return {}
    try:
        return json.loads(HISTORIA_KOMENTARZY.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def zapamietaj_komentarz(post: dict) -> None:
    """Odnotowuje, u kogo dzis komentowalismy."""
    import json
    from datetime import datetime, timezone

    h = _historia()
    h[klucz_publikacji(post)] = datetime.now(timezone.utc).isoformat()
    HISTORIA_KOMENTARZY.parent.mkdir(parents=True, exist_ok=True)
    HISTORIA_KOMENTARZY.write_text(json.dumps(h, ensure_ascii=False, indent=1),
                                   encoding="utf-8")


def klucz_publikacji(post: dict) -> str:
    """Kim jest autor posta. Z ADRESU, bo nazwa publikacji bywa pusta w kanale."""
    from urllib.parse import urlparse

    return urlparse(post.get("url") or "").netloc or (post.get("pub") or "?")


def _wiek_minut(data: str) -> float:
    from datetime import datetime, timezone

    try:
        kiedy = datetime.fromisoformat(str(data).replace("Z", "+00:00"))
    except ValueError:
        return 1e9        # nieznana data = traktujemy jak stary, nie blokujemy
    return (datetime.now(timezone.utc) - kiedy).total_seconds() / 60


def _za_swiezy(post: dict, widelki: tuple[int, int] | None = None) -> bool:
    """Czy post jest na tyle swiezy, ze komentarz wygladalby jak czujka bota.

    Widelki sa ROZNE dla artykulu i dla notki, bo te dwie rzeczy zyja w innym
    tempie. Artykul czyta sie tygodniami, notka gasnie tego samego dnia.
    """
    import random

    prog = random.uniform(*(widelki or config.MIN_WIEK_POSTA_MIN))
    return _wiek_minut(post.get("data", "")) < prog


def wartosc_celu(x: dict) -> tuple:
    """Klucz sortowania celow: WCZESNIE przed GLOSNO.

    Sortowalismy malejaco po `reakcje * 2 + komentarze * 3`, czyli im wiekszy
    tlok, tym wyzej. Dla konta z kilkoma czytelnikami to jest odwrotnie, niz
    trzeba: pod tekstem ze 126 komentarzami nasza uwaga nie zostanie przeczytana
    przez nikogo, a caly koszt jej napisania i tak ponosimy.

    Wiec najpierw teksty, ktore maja ZYWA PUBLICZNOSC, ale jeszcze malo
    komentarzy — tam da sie byc jednym z pierwszych glosow. Zatloczone zostaja
    na koncu, jako uzupelnienie, a nie jako pierwszy wybor.
    """
    kom = int(x.get("komentarze") or 0)
    rea = int(x.get("reakcje") or 0)
    jest_tlok = kom > config.KOMFORTOWO_KOMENTARZY
    # W grupie „jeszcze jest miejsce" wygrywa najzywsza publicznosc.
    # W grupie „tlok" wygrywa ten, gdzie tloku najmniej.
    return (1 if jest_tlok else 0, kom if jest_tlok else -rea)


def _za_niedawno_u_nich(post: dict) -> bool:
    """Czy komentowalismy u tej publikacji w ostatnich dniach."""
    from datetime import datetime, timedelta, timezone

    ostatnio = _historia().get(klucz_publikacji(post))
    if not ostatnio:
        return False
    try:
        kiedy = datetime.fromisoformat(ostatnio)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - kiedy) < timedelta(
        days=config.ODSTEP_DNI_NA_PUBLIKACJE)


# --- SITO CELOW: WIEK, ZYCIE WATKU, AUTOR (1.10.2026, decyzja wlasciciela) ---
#
# Przeglad tresci z 1.10.2026: komentarze NIE byly madre, ale stawiane tam,
# gdzie nikt nie czyta — pod tekstami sprzed miesiecy i lat, pod notkami bez
# jednego komentarza, i ciagle u tych samych osob. Sito stoi PRZED platna ocena
# celow (`stages.wybierz_cele`), tak jak sita platnych i martwych hostow.

def _komentarze_celu(x: dict) -> int:
    """Liczba komentarzy pod celem — notki z kanalu nazywaja ja `odpowiedzi`."""
    return int(x.get("komentarze", x.get("odpowiedzi")) or 0)


def za_stary_cel(x: dict, notka: bool) -> bool:
    """Cel starszy niz `config.MAKS_WIEK_*_DO_KOMENTARZA` — tam nikt juz nie czyta.

    Nieznana data liczy sie jako stara (`_wiek_minut` oddaje wtedy 1e9).
    """
    wiek = _wiek_minut(x.get("data", ""))
    if notka:
        return wiek > config.MAKS_WIEK_NOTKI_DO_KOMENTARZA_H * 60
    return wiek > config.MAKS_WIEK_POSTA_DO_KOMENTARZA_DNI * 24 * 60


def zywy_watek(x: dict) -> bool:
    """Watek, w ktorym ktos juz jest: `ZYWY_WATEK_KOMENTARZY` albo `ZYWY_WATEK_REAKCJI`."""
    return (_komentarze_celu(x) >= config.ZYWY_WATEK_KOMENTARZY
            or int(x.get("reakcje") or 0) >= config.ZYWY_WATEK_REAKCJI)


def cichy_watek(x: dict) -> bool:
    """Zero reakcji i zero komentarzy — komentarz pod tym przeczyta tylko autor."""
    return _komentarze_celu(x) == 0 and int(x.get("reakcje") or 0) == 0


def zywe_najpierw(cele: list[dict]) -> list[dict]:
    """Zywe watki przed cichymi, w obrebie grup kolejnosc bez zmian.

    Kolejnosc po ocenie celow decyduje, ktore miejsca zostana wypelnione
    (`cele[:przydzial]`), wiec cichy cel idzie tylko jako uzupelnienie.
    """
    return [x for x in cele if zywy_watek(x)] + [x for x in cele if not zywy_watek(x)]


def _klucz_autora(wartosc: Any) -> str:
    return " ".join(str(wartosc or "").casefold().split()).lstrip("@")


class LimitAutorow:
    """Ile komentarzy i restackow zrobilismy u kazdego autora w ostatnich 7 dniach.

    DWA JEZYKI W DZIENNIKU. Komentarz zapisuje `komu` (uchwyt) i `publikacja`
    (nazwe), restack — `komu` jako NAZWE, bo przycisk w kanale nie zna uchwytu.
    Liczymy wiec po wszystkich kluczach, jakie wpis ma, a cel sprawdzamy po
    wszystkich swoich: komentarz u osoby podnosi licznik jej nazwy, wiec restack
    (znajacy tylko nazwe) widzi takze komentarze.

    SIOSTRA BEZ WYJATKU: limit dotyczy tez drugiego konta — rozmowe w watku
    (odpowiedzi) nadal prowadzimy, ale wlasne wejscia pod jego notki ida pod ten
    sam sufit, co u kazdego.
    """

    POLA = ("uchwyt", "handle", "komu", "pub", "autor", "publikacja")

    def __init__(self, licznik: dict | None = None, maks: int | None = None):
        from collections import Counter

        self.licznik = Counter(licznik or {})
        self.maks = config.MAKS_DZIALAN_U_AUTORA_7_DNI if maks is None else maks

    @classmethod
    def klucze(cls, x: dict) -> list[str]:
        out: list[str] = []
        for pole in cls.POLA:
            k = _klucz_autora(x.get(pole))
            if k and k not in out:
                out.append(k)
        return out

    @classmethod
    def z_dziennika(cls, dni: int = 7) -> "LimitAutorow":
        """Licznik z dziennika: udane komentarze i restacki z ostatnich `dni`."""
        import json
        from datetime import datetime, timedelta, timezone

        granica = (datetime.now(timezone.utc) - timedelta(days=dni)).isoformat()
        out = cls()
        try:
            linie = (config.DATA_DIR / "dziennik.jsonl").read_text(
                encoding="utf-8").splitlines()
        except OSError:
            return out
        for linia in linie:
            if '"komentarz"' not in linia and '"restack"' not in linia:
                continue
            try:
                w = json.loads(linia)
            except ValueError:
                continue
            if (not isinstance(w, dict) or w.get("rodzaj") not in ("komentarz", "restack")
                    or not w.get("udane") or str(w.get("kiedy") or "") < granica):
                continue
            out.zapisz(w)
        return out

    def ile(self, x: dict) -> int:
        return max((self.licznik[k] for k in self.klucze(x)), default=0)

    def wolno(self, x: dict) -> bool:
        return self.ile(x) < self.maks

    def zapisz(self, x: dict) -> None:
        for k in self.klucze(x):
            self.licznik[k] += 1

    def odsiej(self, cele: list[dict]) -> list[dict]:
        """Cele, ktore mieszcza sie w limicie — takze lacznie w tej samej liscie.

        Licznik obiektu sie nie zmienia: rosnie dopiero po udanym wystawieniu
        (`zapisz`), bo cel z listy nie musi zostac skomentowany.
        """
        proba = LimitAutorow(self.licznik, self.maks)
        out = []
        for x in cele:
            if proba.wolno(x):
                proba.zapisz(x)
                out.append(x)
        return out


def odsiej_cele(cele: list[dict], limit: LimitAutorow, notki: bool) -> list[dict]:
    """Sito przed ocena celow: za stare, (pod notkami) ciche, ponad limit autora."""
    przed = len(cele)
    stare = sum(1 for x in cele if za_stary_cel(x, notki))
    cele = [x for x in cele if not za_stary_cel(x, notki)]
    ciche = 0
    if notki:
        ciche = sum(1 for x in cele if cichy_watek(x))
        cele = zywe_najpierw([x for x in cele if not cichy_watek(x)])
    po_limicie = limit.odsiej(cele)
    if przed != len(po_limicie):
        print("  [cele] sito: %d -> %d (za stare %d, ciche %d, limit autora %d)"
              % (przed, len(po_limicie), stare, ciche, len(cele) - len(po_limicie)),
              flush=True)
    return po_limicie

JS_KANAL = """
() => null
"""


def posty_z_kanalu(ile: int = 25) -> list[dict[str, Any]]:
    """Ostatnie posty z kanalu czytelnika, z liczba komentarzy i reakcji."""
    browser.wymagaj_sesji()
    p, br, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    try:
        dane = browser.api_json(page, "/api/v1/reader/posts") or {}
        posty = []
        odrzucone = {"swieze": 0, "za_czesto": 0}
        for x in (dane.get("posts") or [])[:ile]:
            if not isinstance(x, dict):
                continue
            # NASZE wlasne teksty wypadaja od razu. Kanal czytelnika pokazuje
            # tez nas samych, a wybor celow przy pierwszym uruchomieniu uznal
            # nasz artykul o jajkach za wart skomentowania — agent
            # komentowalby sam siebie.
            adres = x.get("canonical_url") or ""
            _uchwyt = ((x.get("publication") or {}).get("subdomain") or "")
            if (str(_uchwyt).lower() == config.SUBSTACK_HANDLE.lower()
                    or config.SUBSTACK_HANDLE in adres):
                continue
            kandydat = {
                "tytul": (x.get("title") or "")[:120],
                "opis": (x.get("subtitle") or x.get("description") or "")[:300],
                "pub": ((x.get("publication") or {}).get("name") or ""),
                # UCHWYT OBOK NAZWY, nie zamiast niej. Nazwa jest do czytania
                # („Naval"), uchwyt do LACZENIA — dziennik polubien trzyma pod
                # polem `komu` wlasnie uchwyt („genieai"), a komentarz zapisywal
                # sama nazwe. Dwa kanaly mowily o tych samych ludziach dwoma
                # jezykami, wiec pytanie „czy ten, komu polubilismy notke,
                # dostal tez komentarz" nie mialo jak sie policzyc.
                "uchwyt": ((x.get("publication") or {}).get("subdomain") or ""),
                "komentarze": x.get("comment_count") or 0,
                "reakcje": x.get("reaction_count") or 0,
                "url": x.get("canonical_url") or "",
                "data": x.get("post_date") or "",   # pelna, do liczenia wieku
                "skad": "kanal czytelnika",
                "rodzaj": "post",
            }
            # DWA SITA, oba o ZACHOWANIU, nie o tresci.
            if _za_swiezy(kandydat):
                odrzucone["swieze"] += 1
                continue
            if _za_niedawno_u_nich(kandydat):
                odrzucone["za_czesto"] += 1
                continue
            posty.append(kandydat)
        # NOWI LUDZIE NAJPIERW. Cztery dni odstepu chronia przed nachodzeniem
        # tej samej osoby, ale nie robia z nas kogos, kto poznaje nowych.
        # Konto, ktore krazy miedzy pieciona znajomymi nazwiskami, nie rosnie —
        # a wlasnie o nowych ludzi nam chodzi.
        znani = set(_historia())
        posty.sort(key=lambda x: klucz_publikacji(x) in znani)
        nowi = sum(1 for x in posty if klucz_publikacji(x) not in znani)

        print(f"  [kanał] postów: {len(posty)}   nowych autorów: {nowi}"
              f"   odrzucone: {odrzucone['swieze']} za świeżych,"
              f" {odrzucone['za_czesto']} bo niedawno tam komentowaliśmy",
              flush=True)
        return posty
    finally:
        page.close()
        br.close()
        p.stop()


def notki_z_kanalu(ile: int = 25) -> list[dict]:
    """Cudze notki, pod ktorymi mozna wejsc w dyskusje.

    Dla swiezego konta to najwazniejsze miejsce: pod notkami toczy sie rozmowa,
    a kanal Substacka promuje watki, ktore zyja. Komentarz pod artykulem czyta
    kilka osob; sensowna uwaga pod zywa notka trafia do calego jej watku.
    """
    browser.wymagaj_sesji()
    p, br, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    try:
        dane = browser.api_json(page, "/api/v1/reader/feed?tab=for-you&type=base") or {}
        notki = []
        odrzucone = 0
        for x in (dane.get("items") or [])[:ile * 2]:
            c = (x or {}).get("comment") or {}
            if not c.get("body") or c.get("post_id"):
                continue                     # to nie notka, tylko komentarz
            if c.get("handle") == config.SUBSTACK_HANDLE:
                continue                     # nasza wlasna
            kandydat = {
                "id": c.get("id"), "autor": c.get("name") or "",
                "handle": c.get("handle") or "",
                "tekst": (c.get("body") or "")[:1200],
                "reakcje": c.get("reaction_count") or 0,
                "odpowiedzi": c.get("children_count") or 0,
                "data": c.get("date") or "",
                "url": f"https://substack.com/note/c-{c.get('id')}",
                "rodzaj": "notka",
            }
            if _za_swiezy(kandydat, config.MIN_WIEK_NOTKI_MIN):
                odrzucone += 1
                continue
            notki.append(kandydat)
        # Najzywsze najpierw: tam nasza uwaga zostanie przeczytana.
        # Pod notkami liczy sie to samo co pod artykulami: zywa publicznosc,
        # ale jeszcze miejsce, zeby nasza uwaga zostala przeczytana.
        notki.sort(key=lambda n: wartosc_celu(
            {"komentarze": n["odpowiedzi"], "reakcje": n["reakcje"]}))
        print(f"  [notki innych] {len(notki)} do rozwazenia"
              f"   ({odrzucone} odrzuconych jako za swieze)", flush=True)
        return notki[:ile]
    finally:
        page.close()
        br.close()
        p.stop()


def szukaj_nowych(ile: int = 20) -> list[dict]:
    """Szuka NOWYCH kont wyszukiwarka Substacka, poza naszym kregiem.

    Wlasciciel postawil sprawe jasno: agent ma szukac nowych kont, a nie
    komentowac wciaz u tych samych. Kanal czytelnika pokazuje wylacznie to,
    co juz znamy — jedenascie publikacji, ktore same z siebie nikogo nowego nie
    przyprowadza.

    Wyszukiwarka oddaje posty i notki spoza kregu. Filtrujemy je tak samo jak
    kanal: nie swieze, nie u tych, u ktorych niedawno bylismy, nie u nas.
    """
    import random

    browser.wymagaj_sesji()
    hasla = random.sample(list(config.HASLA_SZUKANIA),
                          k=min(config.ILE_HASEL_NA_PRZEBIEG,
                                len(config.HASLA_SZUKANIA)))
    p, br, ctx = browser.podlacz_sie()
    page = ctx.new_page()
    znalezione: dict[str, dict] = {}
    odrzucone = {"swieze": 0, "za_czesto": 0, "nasze": 0}
    try:
        for haslo in hasla:
            dane = browser.api_json(
                page, "/api/v1/top/search?query="
                      + haslo.replace(" ", "+") + "&fromSuggestedSearch=false") or {}
            for x in (dane.get("items") or []):
                post = (x or {}).get("post") or {}
                kom = (x or {}).get("comment") or {}
                pub = (x or {}).get("publication") or {}
                if post.get("title") and post.get("canonical_url"):
                    kandydat = {
                        "tytul": post.get("title", "")[:120],
                        "opis": (post.get("subtitle") or post.get("description") or "")[:300],
                        "pub": pub.get("name") or pub.get("subdomain") or "",
                        "uchwyt": pub.get("subdomain") or "",
                        "komentarze": post.get("comment_count") or 0,
                        "reakcje": post.get("reaction_count") or 0,
                        "url": post.get("canonical_url"),
                        "data": post.get("post_date") or "",
                        "skad": f"szukanie: {haslo}",
                        "rodzaj": "post",
                    }
                elif kom.get("body") and not kom.get("post_id"):
                    kandydat = {
                        "tytul": (kom.get("body") or "")[:120],
                        "opis": (kom.get("body") or "")[:600],
                        "pub": kom.get("name") or kom.get("handle") or "",
                        "uchwyt": kom.get("handle") or "",
                        "komentarze": kom.get("children_count") or 0,
                        "reakcje": kom.get("reaction_count") or 0,
                        "url": f"https://substack.com/note/c-{kom.get('id')}",
                        "id": kom.get("id"),
                        "data": kom.get("date") or "",
                        "skad": f"szukanie: {haslo}",
                        "rodzaj": "notka",
                    }
                else:
                    continue

                # NAJPIERW UCHWYT, DOPIERO POTEM ADRES — i to nie jest
                # ostroznosc, tylko dziura, przez ktora agent mogl komentowac
                # WLASNA notke.
                #
                # Adres notki ma postac `substack.com/note/c-<id>` i NIE NIESIE
                # uchwytu w ogole, wiec warunek na adresie byl falszywy dla
                # kazdej notki — takze naszej. Publicznie wyglada to jak bot
                # rozmawiajacy sam ze soba. Uchwyt autora lezal w tej samej
                # strukturze, jedna linie wyzej (`"uchwyt": kom.get("handle")`),
                # i nikt go nie pytal.
                #
                # UCHWYT POROWNUJEMY DOKLADNIE, nie podciagiem. Podciag wycina
                # CUDZE publikacje: uchwyt „art" odrzucilby smartinvestor,
                # „news" odrzucilby thenewsletter. Nasz uchwyt jest dlugi, wiec
                # dzis by nie zaszkodzil — ale to wlasnosc naszej nazwy, nie
                # kodu, a nazwa moze sie zmienic.
                if (str(kandydat.get("uchwyt") or "").lower()
                        == config.SUBSTACK_HANDLE.lower()
                        or config.SUBSTACK_HANDLE in (kandydat["url"] or "")):
                    odrzucone["nasze"] += 1
                    continue
                if _za_swiezy(kandydat,
                              config.MIN_WIEK_NOTKI_MIN
                              if kandydat["rodzaj"] == "notka" else None):
                    odrzucone["swieze"] += 1
                    continue
                if _za_niedawno_u_nich(kandydat):
                    odrzucone["za_czesto"] += 1
                    continue
                znalezione[kandydat["url"]] = kandydat

        wynik = sorted(znalezione.values(), key=wartosc_celu)[:ile]
        print(f"  [szukanie] hasla: {', '.join(hasla)}", flush=True)
        print(f"  [szukanie] nowych celow: {len(wynik)}"
              f"   (odrzucone: {odrzucone['swieze']} świeżych,"
              f" {odrzucone['za_czesto']} znanych, {odrzucone['nasze']} naszych)",
              flush=True)
        return wynik
    finally:
        page.close()
        br.close()
        p.stop()
