"""FetchPort — lokalne pobieranie treści źródeł (Etap 2, fala E1).

W tej fali istnieją wyłącznie adaptery offline: `FakeFetch` dla testów oraz
`DisabledFetch` jako fail-closed placeholder composition rootów. Realny adapter
sieciowy (HTTP) powstanie w późniejszej fali Etapu 2 i będzie wymagał osobnej
zgody właściciela — dokładnie jak `DisabledBrowser` w warstwie przeglądarki.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class FetchedDocument:
    """Surowy wynik jednego pobrania — dane wejściowe warstwy evidence.

    `body` to surowe bajty odpowiedzi (przed dekodowaniem i ekstrakcją);
    `error` opisuje błąd transportu, przy którym status/treść są niewiarygodne.
    """

    requested_url: str
    final_url: str
    fetched_at: datetime
    http_status: int | None
    content_type: str | None
    body: bytes
    error: str | None = None


class FetchPort(Protocol):
    def fetch(self, url: str) -> FetchedDocument: ...


class FakeFetch:
    """Deterministyczny adapter in-memory dla testów — nigdy nie dotyka sieci."""

    def __init__(self, documents: dict[str, FetchedDocument] | None = None) -> None:
        self._documents: dict[str, FetchedDocument] = dict(documents or {})
        self.calls: list[str] = []

    def register(self, document: FetchedDocument) -> None:
        self._documents[document.requested_url] = document

    def fetch(self, url: str) -> FetchedDocument:
        self.calls.append(url)
        document = self._documents.get(url)
        if document is None:
            raise KeyError(f"FakeFetch has no registered document for {url!r}.")
        return document


class DisabledFetch:
    """Blokuje każde pobranie treści, dopóki realny adapter nie zostanie
    autoryzowany w późniejszej fali. Celowe zabezpieczenie, nie brak implementacji."""

    _MSG = ("Warstwa fetch jest wyłączona w fali E1 Etapu 2. Realny adapter "
            "sieciowy wymaga osobnej fali i jawnej zgody właściciela.")

    def fetch(self, url: str) -> FetchedDocument:
        raise NotImplementedError(self._MSG)
