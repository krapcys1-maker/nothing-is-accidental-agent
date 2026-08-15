"""Deterministyczna ekstrakcja HTML → tekst (Etap 2, fala E1).

Czysta funkcja stdlib (html.parser), bez sieci i bez wykonywania JavaScriptu.
Reguły są celowo proste i zamknięte:

- zawartość ``script``/``style``/``noscript``/``template`` jest pomijana,
- statycznie ukryte poddrzewa NIE są treścią cytowalną: element z atrybutem
  ``hidden``, z ``aria-hidden="true"`` (dowolna wielkość liter i białe znaki)
  albo z inline ``style`` zawierającym ``display:none``,
  ``visibility:hidden`` lub ``content-visibility:hidden`` jest pomijany wraz
  z całym poddrzewem; to wąski, deterministyczny parser inline atrybutów —
  bez silnika CSS, zewnętrznych arkuszy, klas i layoutu,
- elementy blokowe wprowadzają separator nowej linii (kanonizacja i tak
  zwija każdy biały znak do pojedynczej spacji — separator chroni wyłącznie
  przed sklejaniem słów z sąsiednich bloków),
- encje HTML są dekodowane (``convert_charrefs=True``),
- wejście niepoprawne składniowo nie podnosi wyjątku — parser stdlib jest
  odporny, a wynik pozostaje deterministyczną funkcją wejścia; przy
  niedomkniętym ukrytym elemencie ekstraktor pozostaje fail-closed
  (woli pominąć za dużo, niż zacytować treść jawnie ukrytą).
"""
from __future__ import annotations

from html.parser import HTMLParser

_SKIPPED_ELEMENTS = frozenset({"script", "style", "noscript", "template"})
_BLOCK_ELEMENTS = frozenset({
    "address", "article", "aside", "blockquote", "body", "br", "caption",
    "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer",
    "form", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hr",
    "html", "legend", "li", "main", "nav", "ol", "option", "p", "pre",
    "section", "select", "summary", "table", "tbody", "td", "tfoot", "th",
    "thead", "title", "tr", "ul",
})
# Elementy void nie mają domykającego taga — nie wchodzą na stos ukrycia.
_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
_HIDING_STYLE_DECLARATIONS = frozenset({
    ("display", "none"),
    ("visibility", "hidden"),
    ("content-visibility", "hidden"),
})


def _inline_style_hides(style: str) -> bool:
    """Wąski parser inline ``style``: tylko deklaracje ``prop:value``."""
    for declaration in style.split(";"):
        prop, sep, value = declaration.partition(":")
        if not sep:
            continue
        prop = prop.strip().lower()
        value = value.strip().lower()
        if value.endswith("!important"):
            value = value[: -len("!important")].rstrip()
        if (prop, value) in _HIDING_STYLE_DECLARATIONS:
            return True
    return False


def _is_statically_hidden(attrs) -> bool:
    """Czy atrybuty jawnie ukrywają element (markery statyczne, bez CSS)."""
    for name, value in attrs:
        # ``hidden`` to atrybut boolowski HTML: sama obecność ukrywa element
        # (także ``hidden=""``, ``hidden="hidden"`` i ``hidden="until-found"``).
        if name == "hidden":
            return True
        if name == "aria-hidden" and value is not None and value.strip().lower() == "true":
            return True
        if name == "style" and value is not None and _inline_style_hides(value):
            return True
    return False


class _DeterministicTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        # Stos nazw otwartych elementów wewnątrz najbliższego ukrytego
        # poddrzewa; pusty stos = treść nie jest statycznie ukryta.
        self._hidden_stack: list[str] = []
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth += 1
            return
        if self._hidden_stack:
            if tag not in _VOID_ELEMENTS:
                self._hidden_stack.append(tag)
            return
        if _is_statically_hidden(attrs):
            if tag in _BLOCK_ELEMENTS:
                self._parts.append("\n")
            if tag not in _VOID_ELEMENTS:
                self._hidden_stack.append(tag)
            return
        if tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._hidden_stack:
            # Domykamy najbliższy pasujący element; obce tagi ignorujemy.
            if tag in self._hidden_stack:
                while self._hidden_stack:
                    if self._hidden_stack.pop() == tag:
                        break
                if not self._hidden_stack and tag in _BLOCK_ELEMENTS:
                    self._parts.append("\n")
            return
        if tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        # Element samodomykający nie ma poddrzewa — ukrycie nie ma czego
        # obejmować, zostaje wyłącznie separator blokowy.
        if self._hidden_stack:
            return
        if tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and not self._hidden_stack:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def extract_text_from_html(html: str) -> str:
    """Zwraca widoczny tekst dokumentu HTML — czysta, deterministyczna funkcja.

    "Widoczny" oznacza: poza ``script``/``style``/``noscript``/``template``
    oraz poza poddrzewami statycznie ukrytymi (``hidden``,
    ``aria-hidden="true"``, inline ``display:none`` /
    ``visibility:hidden`` / ``content-visibility:hidden``).
    """
    extractor = _DeterministicTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()
