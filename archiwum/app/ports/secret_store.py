"""SecretStorePort — dostęp do sekretów. Lokalnie: zmienne środowiskowe z .env.

Przechowuje wyłącznie klucze API. NIGDY haseł do Substacka (logowanie jest ręczne).
"""
from __future__ import annotations

import os
from typing import Protocol


class SecretStorePort(Protocol):
    def get(self, key: str) -> str | None: ...
    def require(self, key: str) -> str: ...


class EnvSecretStore:
    """Adapter na zmienne środowiskowe (uzupełniane z .env przez load_dotenv)."""

    def get(self, key: str) -> str | None:
        return os.getenv(key)

    def require(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise KeyError(f"Brak wymaganego sekretu w środowisku: {key}")
        return value
