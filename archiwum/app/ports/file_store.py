"""FileStorePort — zapis/odczyt plików. Lokalnie: filesystem w data/. Później: object storage."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileStorePort(Protocol):
    def save(self, account_id: str, category: str, filename: str, data: bytes) -> str: ...
    def read(self, path: str) -> bytes: ...
    def list(self, account_id: str, category: str) -> list[str]: ...


class LocalFileStore:
    """Zapisuje pod data/<category>/<account_id>/<filename> (ścieżki względne do base_dir)."""

    def __init__(self, base_dir: Path) -> None:
        self._base = Path(base_dir)

    def _dir(self, account_id: str, category: str) -> Path:
        return self._base / category / account_id

    def save(self, account_id: str, category: str, filename: str, data: bytes) -> str:
        target_dir = self._dir(account_id, category)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_bytes(data)
        return str(target.relative_to(self._base))

    def read(self, path: str) -> bytes:
        return (self._base / path).read_bytes()

    def list(self, account_id: str, category: str) -> list[str]:
        target_dir = self._dir(account_id, category)
        if not target_dir.exists():
            return []
        return [str(p.relative_to(self._base)) for p in target_dir.iterdir() if p.is_file()]
