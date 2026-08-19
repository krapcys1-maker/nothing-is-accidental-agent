"""Cztery bramki, które blokują. Reszta to notatki.

Wybór właściciela z 2026-08-15. Każda z tych czterech ma udokumentowane
trafienie na starym agencie; wszystko inne (styl, tytuł, brief, długość,
myślniki) niczego nie złapało, więc jest zapisywane i NIE zatrzymuje artykułu.

Podłogi porównują tekst z KORPUSEM, nie z alfabetem. Kontrola „czy jest tu
cyfra" daje fałszywe alarmy na zdaniach, które cytują materiał; właściwe
pytanie brzmi, czy ta liczba występuje w materiale dowodowym.
"""

from __future__ import annotations

import json
import re
from typing import Any

import config

# Zmyślone przeżycie. Celowo NIE łapie pierwszej osoby w ogóle — „my reading",
# „I cannot tell you" to jawne wnioskowanie i jest dozwolone. Łapie czasowniki
# doświadczenia: rzeczy, których model nie mógł zrobić.
FABRICATED_EXPERIENCE = re.compile(
    r"\bI\s+(stood|visited|watched|saw|went|drove|walked|bought|ate|drank|held|"
    r"spoke\s+to|asked|met|noticed|remember|counted|tried|tasted)\b"
    r"|\blast\s+(week|month|year|night),?\s+I\b"
    r"|\bwhen\s+I\s+was\b"
    r"|\bmy\s+(wife|husband|son|daughter|father|mother|friend|neighbou?r|colleague)\b",
    re.IGNORECASE,
)

# Powołanie na badanie bez nazwania go. „In a shelf-life study at 8 °C" jest
# w porządku — niesie szczegół z karty. „According to a recent study" nie.
VAGUE_STUDY = re.compile(
    r"\baccording\s+to\s+(a|one)\s+(recent|new|major|landmark)?\s*(study|report|survey|paper)\b"
    r"|\bstudies\s+have\s+shown\b"
    r"|\bresearch\s+has\s+shown\b"
    r"|\bscientists\s+(have\s+)?(found|discovered)\b"
    r"|\bexperts\s+(say|agree|believe)\b",
    re.IGNORECASE,
)

DIGITS = re.compile(r"\d[\d.,]*")


def _digit_tokens(text: str) -> set[str]:
    return {m.group(0).rstrip(".,") for m in DIGITS.finditer(text)}


def numbers_outside_corpus(body: str, card: dict[str, Any]) -> list[str]:
    """Liczby w tekście, których nie ma nigdzie w materiale dowodowym."""
    corpus = _digit_tokens(json.dumps(card, ensure_ascii=False))
    return sorted(t for t in _digit_tokens(body) if t not in corpus)


def deterministic_floors(body: str, card: dict[str, Any]) -> list[dict[str, str]]:
    """Trzy podłogi bez modelu: 0 USD, milisekundy, zero wywołań."""
    findings: list[dict[str, str]] = []

    for match in FABRICATED_EXPERIENCE.finditer(body):
        findings.append({
            "gate": "ZMYSLONE_PRZEZYCIE",
            "detail": body[max(0, match.start() - 60):match.end() + 60].strip(),
        })
    for match in VAGUE_STUDY.finditer(body):
        findings.append({
            "gate": "NIEISTNIEJACE_BADANIE",
            "detail": body[max(0, match.start() - 60):match.end() + 60].strip(),
        })
    for token in numbers_outside_corpus(body, card):
        findings.append({
            "gate": "LICZBA_SPOZA_KORPUSU",
            "detail": f"liczba {token!r} nie występuje w materiale dowodowym",
        })
    for fraza in frazy_z_instrukcji(body):
        findings.append({
            "gate": "FRAZA_Z_INSTRUKCJI",
            "detail": f"{fraza!r} — zdanie z promptu, nie z myślenia",
        })
    ile, hosty = szerokosc_podstawy(card)
    if ile < 2:
        findings.append({
            "gate": "WASKA_PODSTAWA",
            "detail": (f"artykuł stoi na {ile} źródle ({', '.join(hosty) or 'brak'})"
                       " — czytelnik zobaczy jeden odnośnik pod tekstem"),
        })
    return findings


def szerokosc_podstawy(card: dict[str, Any]) -> tuple[int, list[str]]:
    """Na ilu ODREBNYCH serwisach stoja potwierdzone twierdzenia.

    Artykul 0020 („The Fossil of a Vote") byl najlepszy z serii i mial pod
    soba JEDEN odnosnik — nekrolog z Columbii. Tekst byl skrupulatny wobec
    tego, co zapis mowi, ale post z jednym zrodlem wyglada cienko niezaleznie
    od tego, jak dobrze jest napisany. To uwaga, nie blokada: czasem jedno
    zrodlo to cala dokumentacja, jaka w ogole istnieje.
    """
    from urllib.parse import urlparse

    hosty: list[str] = []
    for c in card.get("confirmed_claims", []) or []:
        url = c.get("url")
        if not url:
            continue
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host and host not in hosty:
            hosty.append(host)
    return len(hosty), hosty


def frazy_z_instrukcji(body: str, dlugosc: int = 6) -> list[str]:
    """Czy pisarz wklein do tekstu wlasne polecenie.

    W 0020 wyszlo „in the simplest sentence that is still true" — dokladnie
    tak, jak stoi w `pisarz.md`. Czytelnik tego nie rozpozna, ale to nie jest
    zdanie z myslenia, tylko echo instrukcji, i wracajac w kolejnych tekstach
    staje sie podpisem maszyny.

    Porownujemy ciagi szesciu slow. Prompt to sam metatekst, wiec kazde takie
    pokrycie jest przeciekiem, nie zbiegiem okolicznosci — a sprawdzenie samo
    sie utrzymuje, gdy prompt sie zmieni.
    """
    def slowa_z(tekst: str) -> list[str]:
        return re.findall(r"[a-z]+", tekst.lower())

    def ciagi(slowa: list[str]) -> list[tuple[str, ...]]:
        return [tuple(slowa[i:i + dlugosc])
                for i in range(len(slowa) - dlugosc + 1)]

    try:
        instrukcja = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf-8")
    except OSError:
        return []
    z_promptu = set(ciagi(slowa_z(instrukcja)))
    slowa = slowa_z(body)
    trafione = [i for i, c in enumerate(ciagi(slowa)) if c in z_promptu]

    # Jedna wklejka daje kilka zachodzacych na siebie ciagow. Skladamy je
    # z powrotem w jedna, najdluzsza fraze — inaczej jeden blad wyglada jak piec.
    trafienia: list[str] = []
    i = 0
    while i < len(trafione):
        koniec = i
        while koniec + 1 < len(trafione) and trafione[koniec + 1] == trafione[koniec] + 1:
            koniec += 1
        fraza = " ".join(slowa[trafione[i]:trafione[koniec] + dlugosc])
        if fraza not in trafienia:
            trafienia.append(fraza)
        i = koniec + 1
    return trafienia


def verdict(findings: list[dict[str, str]]) -> tuple[str, str | None]:
    """Artykuł powstaje ZAWSZE. Decyzja właściciela z 2026-08-15.

    Skoro temat przeszedł odsiew, a research jest opłacony i zrobiony, nie ma
    stanu „zablokowany i koniec". Uwagi wracają do właściciela do przeczytania
    i ewentualnej poprawki — ale tekst istnieje. Zablokowany artykuł to czysta
    strata 1,30 USD researchu i zero informacji w zamian.
    """
    return "SAVED", None
