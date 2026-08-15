"""Głos redakcyjny: korpus próbek i dwa profile stylu.

Jedyna rzecz odróżniająca to konto od tysiąca innych. Korpus jest przypięty
hashem SHA-256 i loader ODMAWIA, jeśli się nie zgadza — nie po to, żeby było
formalnie, tylko żeby nikt po cichu nie podmienił głosu, na który właściciel
się zgodził.

Do promptu trafia 3-5 krótkich fragmentów dobranych wg funkcji retorycznej,
nigdy cały korpus. Fragment ilustruje RUCH, nie frazę do przepisania — dlatego
wszystko dłuższe niż 900 znaków jest odrzucane.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import config

MIN_EXAMPLE_CHARS = 150
MAX_EXAMPLE_CHARS = 900

# Selekcja zatwierdzona przez właściciela i sprawdzona na produkcji: po jednym
# akapicie na funkcję retoryczną. Ordynał ORAZ skrót treści są przypięte, więc
# edycja korpusu, która przesunie akapit, wywali się zamiast po cichu zmienić
# przykłady. Wartości przeniesione z `archiwum/app/content/style_examples.py`.
APPROVED_EXAMPLES = (
    ("OPENING", 65, "974f069d90"),
    ("CONCRETE_TO_SYSTEM", 45, "256abfccb2"),
    ("MECHANISM", 60, "39432e9c97"),
    ("COUNTERARGUMENT", 70, "a139cf852d"),
    ("ENDING", 76, "17d1efd98e"),
)


class StyleError(RuntimeError):
    pass


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_paragraphs(raw: bytes) -> tuple[str, ...]:
    """Deterministyczny podział na akapity; styl końca linii nie zmienia numeracji."""
    normalized = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalized.split("\n\n")]
    return tuple(block for block in blocks if block)


def load_examples() -> list[dict[str, str]]:
    """Zwraca zatwierdzone fragmenty stylu albo rzuca, jeśli korpus się nie zgadza."""
    path = config.STYLE_CORPUS
    if not path.exists():
        raise StyleError(f"brak korpusu stylu: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != config.STYLE_CORPUS_SHA256:
        raise StyleError(
            "korpus stylu nie zgadza się z przypiętym hashem — odmawiam uczenia "
            f"pisarza nieprzejrzanego głosu.\n  oczekiwano: {config.STYLE_CORPUS_SHA256}"
            f"\n  jest:       {digest}"
        )

    paragraphs = split_paragraphs(raw)
    examples: list[dict[str, str]] = []
    for function, ordinal, pinned in APPROVED_EXAMPLES:
        if ordinal >= len(paragraphs):
            raise StyleError(f"korpus ma {len(paragraphs)} akapitów, brak {ordinal}")
        text = paragraphs[ordinal]
        if _sha256(text)[:10] != pinned:
            raise StyleError(
                f"akapit {ordinal} ({function}) nie zgadza się z przypiętym skrótem: "
                f"{_sha256(text)[:10]} zamiast {pinned}"
            )
        if not MIN_EXAMPLE_CHARS <= len(text) <= MAX_EXAMPLE_CHARS:
            raise StyleError(
                f"akapit {ordinal} ma {len(text)} znaków, poza {MIN_EXAMPLE_CHARS}"
                f"-{MAX_EXAMPLE_CHARS}"
            )
        examples.append({"function": function, "text": text})
    return examples


def load_profiles() -> tuple[str, str]:
    """Profil pozytywny i negatywny stylu artykułu."""
    base = config.STYLE_PROFILES_DIR
    positive = base / "ARTICLE_STYLE_PROFILE_V1.md"
    negative = base / "ARTICLE_NEGATIVE_STYLE_PROFILE_V1.md"
    for path in (positive, negative):
        if not path.exists():
            raise StyleError(f"brak profilu stylu: {path}")
    return (
        positive.read_text(encoding="utf-8"),
        negative.read_text(encoding="utf-8"),
    )


def corpus_words() -> set[str]:
    """Wszystkie słowa korpusu — podłoga porównuje tekst z korpusem, nie z alfabetem.

    Kontrola typu „czy jest tu cyfra" daje fałszywe alarmy na zdaniach, które
    cytują materiał. Właściwe pytanie brzmi: czy ta liczba występuje w korpusie.
    """
    raw = config.STYLE_CORPUS.read_bytes().decode("utf-8", "replace")
    return {w.lower() for w in raw.split()}
