"""NotificationPort — powiadomienia i prośby o akceptację. Lokalnie: log. Później: webhook/mobile."""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("nia.notify")


class NotificationPort(Protocol):
    def notify(self, level: str, title: str, message: str,
               account_id: str | None = None) -> None: ...
    def request_approval(self, account_id: str, object_type: str, object_id: int) -> None: ...


class LogNotification:
    """Adapter logujący do standardowego logging (widoczny w konsoli)."""

    def notify(self, level: str, title: str, message: str,
               account_id: str | None = None) -> None:
        prefix = f"[{account_id}] " if account_id else ""
        logger.log(getattr(logging, level.upper(), logging.INFO),
                   "%s%s — %s", prefix, title, message)

    def request_approval(self, account_id: str, object_type: str, object_id: int) -> None:
        logger.info("[APPROVAL] konto=%s obiekt=%s#%s czeka na decyzję człowieka",
                    account_id, object_type, object_id)
