"""Deterministyczna ekstrakcja HTML → tekst (Etap 2, fala E1).

Czysta funkcja stdlib (html.parser), bez sieci i bez wykonywania JavaScriptu.
Reguły są celowo proste i zamknięte:

- zawartość ``script``/``style``/``noscript``/``template`` jest pomijana,
- elementy blokowe wprowadzają separator nowej linii (kanonizacja i tak
  zwija każdy biały znak do pojedynczej spacji — separator chroni wyłącznie
  przed sklejaniem słów z sąsiednich bloków),
- encje HTML są dekodowane (``convert_charrefs=True``),
- wejście niepoprawne składniowo nie podnosi wyjątku — parser stdlib jest
  odporny, a wynik pozostaje deterministyczną funkcją wejścia.
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


class _DeterministicTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth += 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        del attrs
        if tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def extract_text_from_html(html: str) -> str:
    """Zwraca widoczny tekst dokumentu HTML — czysta, deterministyczna funkcja."""
    extractor = _DeterministicTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()
