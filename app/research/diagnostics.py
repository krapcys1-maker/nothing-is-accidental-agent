"""Prywatny zapis diagnostyczny surowych odpowiedzi modelu (research).

Powód: przy dwóch dotychczasowych incydentach (2026-07-11, 2026-07-12) model
zwracał ucięty/niepoprawny JSON, ale nie mieliśmy zapisanej SUROWEJ odpowiedzi ani
`stop_reason` z API — przyczyna ucięcia zostawała tylko hipotezą ("prawdopodobnie
max_tokens"). Ten moduł zapisuje KAŻDĄ REALNĄ odpowiedź (sukces i błąd) do lokalnego,
prywatnego pliku, żeby przyszłe incydenty dało się zdiagnozować na pewno, nie na oko.

Zasady bezpieczeństwa (obowiązkowe):
- WYŁĄCZNIE dla realnych wywołań (dry_run=False) — FakeResearchClient nie ma czego
  zapisywać (nie ma prawdziwej odpowiedzi).
- Zapisujemy TYLKO treść odpowiedzi modelu i metadane liczbowe (tokeny, stop_reason,
  długość) — NIGDY klucza API, nagłówków autoryzacyjnych, ani obiektu żądania.
- Cały `data/` jest w .gitignore (`data/*`) — te pliki NIE trafiają do repo. Dodatkowo
  jawna reguła `data/debug/` w .gitignore, żeby to było widoczne bez doczytywania
  ogólnej reguły.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import BinaryIO, Callable
from uuid import uuid4

from app.core.sanitization import sanitize_persistent_text


@dataclass
class ResponseDiagnostics:
    run_id: str
    stage: str  # np. "A1", "A2_source_12", "B", "B_attempt_2" — patrz write_diagnostics()
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_search_requests: int
    raw_response: str
    parse_error_location: str | None = None

    @property
    def response_length_chars(self) -> int:
        return len(self.raw_response)


def diagnostics_dir(data_dir: Path, run_id: str) -> Path:
    return Path(data_dir) / "debug" / "research" / run_id


def _fsync_directory(directory: Path) -> None:
    if os.name != "nt":
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    barrier = directory / f".dirsync-{uuid4().hex}.tmp"
    fd = os.open(str(barrier), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(b"directory durability barrier\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    barrier.unlink()


@dataclass(frozen=True)
class _DiagnosticFileOps:
    open_file: Callable[[str, int], int]
    write_file: Callable[[BinaryIO, bytes], object]
    fsync_file: Callable[[int], None]
    replace_file: Callable[[Path, Path], None]
    fsync_directory: Callable[[Path], None]


_DEFAULT_FILE_OPS = _DiagnosticFileOps(
    open_file=os.open,
    write_file=lambda handle, data: handle.write(data),
    fsync_file=os.fsync,
    replace_file=os.replace,
    fsync_directory=_fsync_directory,
)


def _atomic_text_replace(
    path: Path,
    text: str,
    *,
    file_ops: _DiagnosticFileOps,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    encoded = text.encode("utf-8")
    try:
        fd = file_ops.open_file(
            str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                file_ops.write_file(handle, encoded)
                handle.flush()
                file_ops.fsync_file(handle.fileno())
        finally:
            os.close(fd)
        file_ops.replace_file(temporary, path)
        file_ops.fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def write_diagnostics(
    data_dir: Path,
    diag: ResponseDiagnostics,
    *,
    _file_ops: _DiagnosticFileOps = _DEFAULT_FILE_OPS,
) -> Path:
    """Zapisuje surową odpowiedź do
    `data/debug/research/<run_id>/<stage>_raw_response.txt`.

    `stage` musi być już rozróżnialny między wywołaniami tego samego run_id (np.
    etap A2 wywoływany jest raz NA ŹRÓDŁO — wołający przekazuje np.
    "A2_source_<candidate_id>", nie gołe "A2", żeby kolejne źródła się nie nadpisywały).
    Nadpisuje plik przy KOLEJNEJ próbie tego samego, już rozróżnionego etapu — to
    diagnostyka NAJNOWSZEJ próby danego wywołania, nie archiwum wszystkich prób.

    Zwraca ścieżkę zapisanego pliku (dla logów/testów).
    """
    run_dir = diagnostics_dir(data_dir, diag.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{diag.stage}_raw_response.txt"

    header_lines = [
        f"run_id: {diag.run_id}",
        f"stage: {diag.stage}",
        f"stop_reason: {diag.stop_reason}",
        f"input_tokens: {diag.input_tokens}",
        f"output_tokens: {diag.output_tokens}",
        f"cache_read_tokens: {diag.cache_read_tokens}",
        f"cache_write_tokens: {diag.cache_write_tokens}",
        f"web_search_requests: {diag.web_search_requests}",
        f"response_length_chars: {diag.response_length_chars}",
        f"parse_error_location: {diag.parse_error_location}",
        "-" * 70,
        "",
    ]
    safe_raw_response = sanitize_persistent_text(diag.raw_response)
    safe_header = sanitize_persistent_text("\n".join(header_lines))
    return _atomic_text_replace(
        path,
        safe_header + safe_raw_response,
        file_ops=_file_ops,
    )
