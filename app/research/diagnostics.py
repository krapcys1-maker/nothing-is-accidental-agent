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
from pathlib import Path


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


def write_diagnostics(data_dir: Path, diag: ResponseDiagnostics) -> Path:
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
    path.write_text("\n".join(header_lines) + diag.raw_response, encoding="utf-8")
    return path
