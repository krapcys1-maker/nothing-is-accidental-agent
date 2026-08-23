"""Addytywny schemat SQLite V3 bez destrukcyjnych migracji i triggerów.

Schemat powstaje z `CREATE TABLE IF NOT EXISTS` przy starcie. Zmiana schematu to
zmiana tego pliku — nie ma drabiny wersji, bo poprzedni agent miał 42 migracje
i to one blokowały produkcję, nie brak funkcji.

Limitów nie ma w `CHECK`-ach celowo: limit przypięty w schemacie to drugie
miejsce, w którym żyje ta sama liczba, a wtedy podniesienie jej w kodzie wywala
produkcję (stary agent: `attempt_no IN (1,2)` w ośmiu tabelach, 1,84 USD do kosza).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


class ModelBudgetExceeded(RuntimeError):
    """Atomowa rezerwacja nie mieści się w jednym z limitów modelu."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,          -- RUNNING / DONE / FAILED
    stage       TEXT,                   -- na czym stanęło
    cost_usd    REAL NOT NULL DEFAULT 0,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER,
    at             TEXT NOT NULL,
    provider       TEXT NOT NULL,       -- anthropic / deepseek
    model          TEXT NOT NULL,
    purpose        TEXT NOT NULL,       -- scout / discovery / write / ...
    tokens_in      INTEGER NOT NULL DEFAULT 0,
    tokens_out     INTEGER NOT NULL DEFAULT 0,
    -- Trafienia w cache byly LICZONE do kosztu i nigdzie nie zapisywane, wiec
    -- nie dalo sie sprawdzic, czy w ogole trafiamy. To ma znaczenie, bo cache
    -- jest 30x tanszy od zwyklego wejscia ($0,022 wobec $0,66 u pro), a nasza
    -- najdrozsza pozycja — dyskoveria — przesyla cala rozmowe w kazdej rundzie.
    -- Bez tej kolumny nie da sie odroznic „prefiks peka" od „prefiks trafia,
    -- a cena bierze sie skadinad".
    cache_hit      INTEGER NOT NULL DEFAULT 0,
    web_searches   INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0,
    cost_status    TEXT NOT NULL DEFAULT 'KNOWN'
                   CHECK (cost_status IN ('RESERVED', 'KNOWN', 'UNKNOWN')),
    reserved_usd   REAL NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
    provider_request_id TEXT,
    reconciled_at  TEXT,
    price_verified INTEGER NOT NULL DEFAULT 1,  -- 0 = stawka niepotwierdzona
    ok             INTEGER NOT NULL DEFAULT 1,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    created_at   TEXT NOT NULL,
    topic        TEXT,
    title        TEXT,
    body         TEXT,
    evidence     TEXT,                  -- karta dowodowa, JSON
    status       TEXT NOT NULL,         -- SAVED / BLOCKED
    blocked_by   TEXT,                  -- która z czterech bramek
    notes        TEXT,                  -- niesblokujące uwagi, JSON
    artifact_key TEXT,
    file_path    TEXT,
    file_sha256  TEXT,
    notes_path   TEXT,
    notes_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS article_save_intents (
    artifact_key  TEXT PRIMARY KEY,
    run_id        INTEGER NOT NULL,
    article_id    INTEGER,
    target_path   TEXT NOT NULL,
    temp_path     TEXT NOT NULL,
    file_sha256   TEXT NOT NULL,
    notes_path    TEXT,
    notes_temp_path TEXT,
    notes_sha256  TEXT,
    status        TEXT NOT NULL
                  CHECK (status IN ('PREPARED','COMPLETE','ROLLED_BACK','BROKEN')),
    created_at    TEXT NOT NULL,
    finished_at   TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    at           TEXT NOT NULL,
    url          TEXT NOT NULL,
    domain       TEXT NOT NULL,         -- do reguły różnorodności
    title        TEXT,
    source_class TEXT,                  -- PRIMARY / SUPPORTING / ODPAD
    fetched_ok   INTEGER NOT NULL DEFAULT 0,
    fail_reason  TEXT,                  -- np. blokada botów
    requested_url TEXT,                 -- dokładny kandydat discovery
    final_url     TEXT,                 -- dokument po redirectach
    redirect_chain_json TEXT NOT NULL DEFAULT '[]',
    resolved_ips_json   TEXT NOT NULL DEFAULT '{}',
    document_id         TEXT,
    content_sha256      TEXT
);

CREATE TABLE IF NOT EXISTS operational_days (
    id             TEXT PRIMARY KEY,
    account        TEXT NOT NULL,
    day_key        TEXT NOT NULL,
    timezone       TEXT NOT NULL,
    starts_at      TEXT NOT NULL,
    ends_at        TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    policy_hash    TEXT NOT NULL,
    ramp_up        INTEGER NOT NULL,
    quiet_day      INTEGER NOT NULL,
    budget_json    TEXT NOT NULL,
    UNIQUE(account, day_key)
);

CREATE TABLE IF NOT EXISTS mutation_attempts (
    id               TEXT PRIMARY KEY,
    idempotency_key  TEXT NOT NULL,
    sequence         INTEGER NOT NULL,
    account          TEXT NOT NULL,
    kind             TEXT NOT NULL,
    target           TEXT NOT NULL,
    payload_sha256   TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    dispatched_at    TEXT,
    finished_at      TEXT,
    status           TEXT NOT NULL,
    source_ref       TEXT,
    error            TEXT,
    request_json     TEXT NOT NULL DEFAULT '{}',
    result_json      TEXT NOT NULL DEFAULT '{}',
    UNIQUE(idempotency_key, sequence)
);

CREATE INDEX IF NOT EXISTS idx_mutation_attempts_key
ON mutation_attempts(idempotency_key, sequence DESC);

CREATE TABLE IF NOT EXISTS action_budget_reservations (
    attempt_id          TEXT PRIMARY KEY,
    operational_day_id  TEXT NOT NULL,
    category            TEXT NOT NULL,
    units               INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL,
    reserved_at         TEXT NOT NULL,
    finished_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_action_budget_day_category
ON action_budget_reservations(operational_day_id, category, status);

CREATE TABLE IF NOT EXISTS model_contract_checks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    at           TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    contract_id  TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_contract_checks_run
ON model_contract_checks(run_id, purpose, contract_id);

CREATE TABLE IF NOT EXISTS provenance_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    at          TEXT NOT NULL,
    stage       TEXT NOT NULL,
    subject_id  TEXT,
    ok          INTEGER NOT NULL,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_provenance_checks_run
ON provenance_checks(run_id, stage, subject_id);

CREATE TABLE IF NOT EXISTS provenance_documents (
    document_id    TEXT PRIMARY KEY,
    url            TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    publisher      TEXT,
    title          TEXT,
    source_class   TEXT
);

CREATE TABLE IF NOT EXISTS provenance_fragments (
    fragment_id  TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL,
    text         TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset   INTEGER NOT NULL,
    text_sha256  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_claims (
    article_id INTEGER NOT NULL,
    claim_id   TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    used       INTEGER NOT NULL,
    PRIMARY KEY(article_id, claim_id)
);

CREATE TABLE IF NOT EXISTS claim_fragments (
    article_id  INTEGER NOT NULL,
    claim_id    TEXT NOT NULL,
    fragment_id TEXT NOT NULL,
    PRIMARY KEY(article_id, claim_id, fragment_id)
);

CREATE TABLE IF NOT EXISTS article_numbers (
    article_id  INTEGER NOT NULL,
    number_id   TEXT NOT NULL,
    value       TEXT NOT NULL,
    claim_id    TEXT NOT NULL,
    fragment_id TEXT NOT NULL,
    used        INTEGER NOT NULL,
    PRIMARY KEY(article_id, number_id)
);

CREATE TABLE IF NOT EXISTS article_sentences (
    article_id     INTEGER NOT NULL,
    sentence_id    TEXT NOT NULL,
    ordinal        INTEGER NOT NULL,
    text           TEXT NOT NULL,
    classification TEXT NOT NULL,
    support_status TEXT NOT NULL,
    PRIMARY KEY(article_id, sentence_id),
    UNIQUE(article_id, ordinal)
);

CREATE TABLE IF NOT EXISTS sentence_claims (
    article_id  INTEGER NOT NULL,
    sentence_id TEXT NOT NULL,
    claim_id    TEXT NOT NULL,
    PRIMARY KEY(article_id, sentence_id, claim_id)
);

CREATE TABLE IF NOT EXISTS article_citations (
    article_id  INTEGER NOT NULL,
    citation_id TEXT NOT NULL,
    ordinal     INTEGER NOT NULL,
    document_id TEXT NOT NULL,
    url         TEXT NOT NULL,
    PRIMARY KEY(article_id, citation_id),
    UNIQUE(article_id, ordinal)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Otwiera bazę i zakłada schemat, jeśli go nie ma."""
    db_path = path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _dopisz_brakujace_kolumny(conn)
    # V3 rozszerza bazę o pamięć redakcyjną. Import lokalny unika cyklu:
    # `editorial` nie jest potrzebny narzędziom, które tylko czytają db.py.
    import editorial
    editorial.ensure_schema(conn)
    conn.commit()
    return conn


# Kolumny dopisane do `calls` PO tym, jak baza produkcyjna juz istniala.
# `CREATE TABLE IF NOT EXISTS` istniejacej tabeli NIE rusza, wiec bez tego
# pierwszy zapis do starej bazy konczy sie bledem „no such column".
#
# To nie jest system migracji i ma nim nie byc — projekt stoi na zasadzie
# „zmiana schematu to nowa kolumna z wartoscia domyslna, nigdy przepisywanie
# danych". Ta funkcja robi dokladnie tyle i ani kroku wiecej.
NOWE_KOLUMNY = {
    "calls": {
        "cache_hit": "INTEGER NOT NULL DEFAULT 0",
        "cost_status": (
            "TEXT NOT NULL DEFAULT 'KNOWN' "
            "CHECK (cost_status IN ('RESERVED', 'KNOWN', 'UNKNOWN'))"
        ),
        "reserved_usd": "REAL NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0)",
        "provider_request_id": "TEXT",
        "reconciled_at": "TEXT",
    },
    # Prototypowa tabela mogła powstać podczas wcześniejszej próby N-005 pod
    # nazwą `external_id`. Referencja UI nie zawsze jest ID obiektu platformy,
    # więc nowy kontrakt używa uczciwszej nazwy i nie przepisuje starej kolumny.
    "mutation_attempts": {"source_ref": "TEXT"},
    "sources": {
        "requested_url": "TEXT",
        "final_url": "TEXT",
        "redirect_chain_json": "TEXT NOT NULL DEFAULT '[]'",
        "resolved_ips_json": "TEXT NOT NULL DEFAULT '{}'",
        "document_id": "TEXT",
        "content_sha256": "TEXT",
    },
    "articles": {
        "artifact_key": "TEXT",
        "file_path": "TEXT",
        "file_sha256": "TEXT",
        "notes_path": "TEXT",
        "notes_sha256": "TEXT",
    },
}


def _dopisz_brakujace_kolumny(conn: sqlite3.Connection) -> None:
    for tabela, kolumny in NOWE_KOLUMNY.items():
        try:
            maja = {w[1] for w in conn.execute("PRAGMA table_info(%s)" % tabela)}
        except sqlite3.Error:
            continue
        for nazwa, typ in kolumny.items():
            if nazwa not in maja:
                try:
                    conn.execute("ALTER TABLE %s ADD COLUMN %s %s"
                                 % (tabela, nazwa, typ))
                    print("  [baza] dopisano kolumne %s.%s" % (tabela, nazwa),
                          flush=True)
                except sqlite3.Error as exc:
                    print("  [baza] nie dopisalem %s.%s: %s" % (tabela, nazwa, exc),
                          flush=True)
    # Indeks powstaje dopiero po addytywnym dopisaniu kolumny. Umieszczenie go
    # w SCHEMA wywracałoby otwarcie starszej bazy zanim migrator zdąży zadziałać.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_artifact_key "
        "ON articles(artifact_key) WHERE artifact_key IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_article_save_intents_status "
        "ON article_save_intents(status, created_at)"
    )


def start_run(conn: sqlite3.Connection, stage: str = "start") -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at, status, stage) VALUES (?, 'RUNNING', ?)",
        (now(), stage),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection, run_id: int, status: str, stage: str, note: str = ""
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, stage = ?, note = ?,"
        " cost_usd = (SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE run_id = ?)"
        " WHERE id = ?",
        (now(), status, stage, note, run_id, run_id),
    )
    conn.commit()


def record_call(conn: sqlite3.Connection, **fields: Any) -> None:
    """Zapisuje wywołanie po sprawdzeniu ścisłego kontraktu finansowego.

    Wcześniej lista kolumn była stała, a brakujące pola szły jako `fields.get(k)`
    — czyli jawny NULL. SQL-owe `DEFAULT 0` wtedy NIE dziala: default wchodzi
    tylko wtedy, gdy kolumny w INSERT nie ma wcale, a nie gdy jest z NULL-em.
    Skutkiem był `IntegrityError: NOT NULL constraint failed` u każdego, kto nie
    podał kompletu.

    Kosztowało to okładkę artykułu 0025 i — groźniej — przykrywało prawdziwe
    błędy API: gdy wywołanie tekstowe padało, ścieżka błędu próbowała je zapisać,
    wywalała się na tej samej kolumnie i to `IntegrityError` szedł w górę zamiast
    prawdziwej przyczyny.

    V2 filtrowało nieznane pola. Literówka `cost_used=0.53` znikała wtedy bez
    błędu, a baza zapisywała `cost_usd=0`. V3 odrzuca nieznane pola oraz brak
    każdej pozycji koniecznej do uczciwego zaksięgowania wywołania.
    """
    allowed = (
        "run_id", "provider", "model", "purpose", "tokens_in", "tokens_out",
        "cache_hit", "web_searches", "cost_usd", "cost_status", "reserved_usd",
        "provider_request_id", "reconciled_at", "price_verified", "ok", "note",
    )
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise TypeError("nieznane pola calls: %s" % ", ".join(unknown))
    required = {"provider", "model", "purpose", "cost_usd", "price_verified", "ok"}
    missing = sorted(required - set(fields))
    if missing:
        raise TypeError("brak wymaganych pól calls: %s" % ", ".join(missing))
    if fields.get("cost_usd") is None:
        raise TypeError("cost_usd nie może być None")
    status = fields.get("cost_status", "KNOWN")
    if status not in {"RESERVED", "KNOWN", "UNKNOWN"}:
        raise ValueError("nieznany cost_status: %r" % status)
    cost = float(fields["cost_usd"])
    reserved = float(fields.get("reserved_usd", 0) or 0)
    if cost < 0 or reserved < 0:
        raise ValueError("koszt i rezerwacja nie mogą być ujemne")
    if status in {"RESERVED", "UNKNOWN"} and (cost != 0 or reserved <= 0):
        raise ValueError(
            "%s wymaga cost_usd=0 i dodatniej reserved_usd" % status
        )
    if status == "KNOWN" and reserved != 0:
        raise ValueError("KNOWN nie może zachowywać rezerwacji")
    keys = [k for k in allowed if k in fields]
    conn.execute(
        f"INSERT INTO calls (at, {', '.join(keys)})"
        f" VALUES (?, {', '.join('?' * len(keys))})",
        [now(), *(fields[k] for k in keys)],
    )
    conn.commit()


def reserve_call(
    conn: sqlite3.Connection, *, run_id: int | None, provider: str, model: str,
    purpose: str, reserved_usd: float,
) -> int:
    """Niskopoziomowy insert bez kontroli limitów, dla testu/rekoncyliacji.

    Aktywny runtime musi używać `reserve_model_budget`, które atomowo łączy
    sprawdzenie ekspozycji i insert. Ta funkcja zachowuje interfejs N-017 do
    budowania izolowanych stanów RESERVED/UNKNOWN.
    """
    if reserved_usd <= 0:
        raise ValueError("rezerwacja modelu musi być dodatnia")
    cur = conn.execute(
        "INSERT INTO calls "
        "(run_id, at, provider, model, purpose, cost_usd, cost_status, "
        " reserved_usd, price_verified, ok, note) "
        "VALUES (?, ?, ?, ?, ?, 0, 'RESERVED', ?, 0, 0, ?)",
        (
            run_id, now(), provider, model, purpose, float(reserved_usd),
            "rezerwacja przed dispatch",
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def settle_reserved_call(
    conn: sqlite3.Connection, call_id: int, *, tokens_in: int,
    tokens_out: int, cache_hit: int, web_searches: int, cost_usd: float,
    price_verified: bool, ok: bool, note: str | None = None,
    provider_request_id: str | None = None,
) -> None:
    """Atomowo zamienia rezerwację w koszt znany, także znane zero."""
    if cost_usd < 0:
        raise ValueError("koszt nie może być ujemny")
    cur = conn.execute(
        "UPDATE calls SET tokens_in=?, tokens_out=?, cache_hit=?, "
        "web_searches=?, cost_usd=?, cost_status='KNOWN', reserved_usd=0, "
        "provider_request_id=COALESCE(?, provider_request_id), "
        "price_verified=?, ok=?, note=? "
        "WHERE id=? AND cost_status='RESERVED'",
        (
            int(tokens_in), int(tokens_out), int(cache_hit), int(web_searches),
            float(cost_usd), provider_request_id, int(price_verified), int(ok),
            note, call_id,
        ),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise RuntimeError("wywołanie nie jest aktywną rezerwacją")
    conn.commit()


def mark_call_cost_unknown(
    conn: sqlite3.Connection, call_id: int, *, note: str,
    provider_request_id: str | None = None,
) -> None:
    """Zachowuje rezerwację po błędzie, który mógł nastąpić po dispatch."""
    cur = conn.execute(
        "UPDATE calls SET cost_status='UNKNOWN', "
        "provider_request_id=COALESCE(?, provider_request_id), ok=0, note=? "
        "WHERE id=? AND cost_status='RESERVED'",
        (provider_request_id, note[:500], call_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise RuntimeError("wywołanie nie jest aktywną rezerwacją")
    conn.commit()


def reconcile_unknown_call(
    conn: sqlite3.Connection, call_id: int, *, cost_usd: float,
    evidence_ref: str, tokens_in: int | None = None,
    tokens_out: int | None = None, provider_request_id: str | None = None,
) -> None:
    """Rozlicza UNKNOWN dokładnie raz, zachowując odnośnik do dowodu."""
    if cost_usd < 0:
        raise ValueError("koszt nie może być ujemny")
    if not evidence_ref.strip():
        raise ValueError("rekoncyliacja wymaga evidence_ref")
    cur = conn.execute(
        "UPDATE calls SET cost_usd=?, cost_status='KNOWN', reserved_usd=0, "
        "tokens_in=COALESCE(?, tokens_in), tokens_out=COALESCE(?, tokens_out), "
        "provider_request_id=COALESCE(?, provider_request_id), "
        "reconciled_at=?, note=? WHERE id=? AND cost_status='UNKNOWN'",
        (
            float(cost_usd), tokens_in, tokens_out, provider_request_id, now(),
            ("RECONCILED: " + evidence_ref.strip())[:500], call_id,
        ),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise RuntimeError("rekoncyliować można wyłącznie koszt UNKNOWN")
    conn.commit()


def provider_has_unresolved_cost(conn: sqlite3.Connection, provider: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM calls WHERE provider=? "
        "AND cost_status IN ('RESERVED', 'UNKNOWN') LIMIT 1",
        (provider,),
    ).fetchone()
    return row is not None


def financial_exposure(
    conn: sqlite3.Connection, *, run_id: int | None = None,
    start: str | None = None, end: str | None = None,
) -> float:
    """Znany koszt plus zachowane rezerwacje RESERVED/UNKNOWN."""
    clauses: list[str] = []
    params: list[Any] = []
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if start is not None:
        clauses.append("at >= ?")
        params.append(start)
    if end is not None:
        clauses.append("at < ?")
        params.append(end)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd + CASE "
        "WHEN cost_status IN ('RESERVED', 'UNKNOWN') THEN reserved_usd "
        "ELSE 0 END), 0) AS total FROM calls" + where,
        params,
    ).fetchone()
    return float(row["total"])


def reserve_model_budget(
    conn: sqlite3.Connection, *, run_id: int | None, provider: str, model: str,
    purpose: str, at: str, run_limit_usd: float,
    day_limit_usd: float | None = None, day_start: str | None = None,
    day_end: str | None = None, month_limit_usd: float | None = None,
    month_start: str | None = None, month_end: str | None = None,
    fixed_price_usd: float | None = None,
) -> tuple[int, float]:
    """Atomowo sprawdza wszystkie limity i tworzy `calls.RESERVED`.

    `BEGIN IMMEDIATE` serializuje konkurujące procesy przed pierwszym odczytem
    ekspozycji. Funkcja nie może zatwierdzić cudzej, rozpoczętej wcześniej
    transakcji połączenia — aktywna transakcja jest więc błędem kontraktu.
    """
    run_limit = float(run_limit_usd)
    if run_limit <= 0:
        raise ValueError("limit przebiegu musi być dodatni")
    if not str(provider or "").strip():
        raise ValueError("rezerwacja wymaga dostawcy")
    if not str(model or "").strip() or not str(purpose or "").strip():
        raise ValueError("rezerwacja wymaga modelu i celu")
    if not str(at or "").strip():
        raise ValueError("rezerwacja wymaga świadomego czasu")
    periods = (
        ("dzienny", day_limit_usd, day_start, day_end),
        ("miesięczny", month_limit_usd, month_start, month_end),
    )
    for label, limit, start, end in periods:
        if limit is None:
            if start is not None or end is not None:
                raise ValueError(f"{label} przedział bez limitu")
            continue
        if float(limit) <= 0 or not start or not end or start >= end:
            raise ValueError(f"nieprawidłowy {label} limit lub przedział")
    if fixed_price_usd is not None and float(fixed_price_usd) <= 0:
        raise ValueError("stała cena musi być dodatnia")
    if conn.in_transaction:
        raise RuntimeError(
            "atomowa rezerwacja wymaga połączenia bez aktywnej transakcji")

    try:
        conn.execute("BEGIN IMMEDIATE")
        if provider_has_unresolved_cost(conn, provider):
            raise ModelBudgetExceeded(
                f"dostawca {provider!r} ma nierozliczony koszt "
                "RESERVED/UNKNOWN"
            )

        remaining = run_limit
        if run_id is not None:
            run_exposure = financial_exposure(conn, run_id=run_id)
            remaining = min(remaining, run_limit - run_exposure)

        for _label, limit, start, end in periods:
            if limit is None:
                continue
            exposure = financial_exposure(conn, start=start, end=end)
            remaining = min(remaining, float(limit) - exposure)

        if remaining <= 1e-12:
            raise ModelBudgetExceeded(
                f"brak wolnego budżetu dla etapu {purpose!r}")
        if fixed_price_usd is not None:
            expected = float(fixed_price_usd)
            if expected > remaining + 1e-12:
                raise ModelBudgetExceeded(
                    f"brak ${expected:.6f} na etap {purpose!r}; "
                    f"pozostało ${remaining:.6f}"
                )
            reserved = expected
        else:
            # Nigdy nie zaokrąglamy w górę ponad wyliczone saldo.
            reserved = min(remaining, round(remaining, 6))
            if reserved <= 0:
                raise ModelBudgetExceeded(
                    f"saldo etapu {purpose!r} jest mniejsze od precyzji księgi")

        cur = conn.execute(
            "INSERT INTO calls "
            "(run_id, at, provider, model, purpose, cost_usd, cost_status, "
            " reserved_usd, price_verified, ok, note) "
            "VALUES (?, ?, ?, ?, ?, 0, 'RESERVED', ?, 0, 0, ?)",
            (
                run_id, at, provider, model, purpose, reserved,
                "atomowa rezerwacja przed dispatch",
            ),
        )
        conn.commit()
        return int(cur.lastrowid), float(reserved)
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def record_contract_check(
    conn: sqlite3.Connection | None, *, run_id: int | None, purpose: str,
    contract_id: str, ok: bool, error: str = "",
) -> None:
    """Zapisuje wersję i wynik walidacji oddzielnie od sukcesu transportu LLM."""
    if conn is None:
        return
    conn.execute(
        "INSERT INTO model_contract_checks "
        "(run_id, at, purpose, contract_id, ok, error) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, now(), purpose, contract_id, int(ok), error[:500] or None),
    )
    conn.commit()


def record_provenance_check(
    conn: sqlite3.Connection | None, *, run_id: int | None, stage: str,
    subject_id: str | None, ok: bool, error: str = "",
) -> None:
    """Zapisuje wynik wiązania kontekstowego poza samym schematem JSON."""
    if conn is None:
        return
    conn.execute(
        "INSERT INTO provenance_checks "
        "(run_id, at, stage, subject_id, ok, error) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, now(), stage, subject_id, int(ok), error[:500] or None),
    )
    conn.commit()


def spent_usd(conn: sqlite3.Connection, since_prefix: str) -> float:
    """Suma kosztów od znacznika czasu zaczynającego się danym prefiksem.

    `since_prefix` to `YYYY-MM-DD` dla doby albo `YYYY-MM` dla miesiąca — daty są
    zapisane w ISO 8601 UTC, więc porównanie prefiksem wystarczy i nie wymaga
    drugiej reprezentacji czasu w bazie.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM calls WHERE at LIKE ?",
        (f"{since_prefix}%",),
    ).fetchone()
    return float(row["total"])


def spent_usd_between(
    conn: sqlite3.Connection, start: str, end: str,
) -> float:
    """Suma kosztów w półotwartym przedziale UTC ``[start, end)``.

    Limity dobowe nie mogą filtrować prefiksem daty UTC, gdy doba redakcyjna
    jest zdefiniowana w innej strefie. Znaczniki zapisujemy w UTC, dlatego
    uporządkowanie ISO 8601 daje dokładny i odporny na DST przedział.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM calls "
        "WHERE at >= ? AND at < ?", (start, end),
    ).fetchone()
    return float(row["total"])


def recent_domains(conn: sqlite3.Connection, limit: int) -> list[str]:
    """Domeny z ostatnich N artykułów — wejście do reguły różnorodności."""
    rows = conn.execute(
        "SELECT DISTINCT s.domain FROM sources s"
        " JOIN articles a ON a.run_id = s.run_id"
        " WHERE a.status = 'SAVED'"
        " AND a.run_id IN (SELECT run_id FROM articles WHERE status = 'SAVED'"
        "                  ORDER BY id DESC LIMIT ?)",
        (limit,),
    ).fetchall()
    return [r["domain"] for r in rows]
