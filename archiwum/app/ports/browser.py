"""BrowserPort — automatyzacja przeglądarki (Substack).

STUB w walking skeleton. Playwright włączamy dopiero w Etapie 4 i tylko po ręcznym
logowaniu użytkownika (patrz docs/archive/superseded_plans/SUBSTACK_INTEGRATION.md (archiwum; obowiazuje MASTER_ARCHITECTURE.md §8.2)).
Model językowy NIGDY nie wywołuje tego portu bezpośrednio — tylko orchestrator po
walidacji Policy Engine.
"""
from __future__ import annotations

from typing import Any, Protocol


class BrowserPort(Protocol):
    def is_logged_in(self, account_id: str) -> bool: ...
    def open_feed(self, account_id: str) -> None: ...
    def read_post(self, account_id: str, url: str) -> dict: ...
    def create_article_draft(self, account_id: str, item: Any) -> str: ...
    def publish_note(self, account_id: str, item: Any) -> str: ...
    def publish_comment(self, account_id: str, interaction: Any) -> str: ...
    def collect_metrics(self, account_id: str) -> dict: ...
    def take_screenshot(self, account_id: str, label: str) -> str: ...


class DisabledBrowser:
    """Blokuje jakiekolwiek działania na Substacku w MVP-0.

    Każda metoda podnosi wyjątek, aby żaden przepływ nie mógł przypadkiem
    dotknąć konta. To celowe zabezpieczenie, nie brak implementacji.
    """

    _MSG = ("Warstwa przeglądarki jest wyłączona w MVP-0. Publikacja/odczyt na "
            "Substacku uruchomimy w Etapie 4 po ręcznym zalogowaniu i jawnej zgodzie.")

    def is_logged_in(self, account_id: str) -> bool:
        return False

    def open_feed(self, account_id: str) -> None:
        raise NotImplementedError(self._MSG)

    def read_post(self, account_id: str, url: str) -> dict:
        raise NotImplementedError(self._MSG)

    def create_article_draft(self, account_id: str, item) -> str:
        raise NotImplementedError(self._MSG)

    def publish_note(self, account_id: str, item) -> str:
        raise NotImplementedError(self._MSG)

    def publish_comment(self, account_id: str, interaction) -> str:
        raise NotImplementedError(self._MSG)

    def collect_metrics(self, account_id: str) -> dict:
        raise NotImplementedError(self._MSG)

    def take_screenshot(self, account_id: str, label: str) -> str:
        raise NotImplementedError(self._MSG)
