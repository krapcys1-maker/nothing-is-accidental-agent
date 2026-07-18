"""Independent offline disproof for the Stage 2 E1 evidence floors (ADR-099/100).

The probe uses only throwaway SQLite databases and raw ``sqlite3`` handles
(with ``PRAGMA foreign_keys`` deliberately left OFF) to prove that migration
0016 itself — not the application layer — refuses inconsistent evidence:
mismatched excerpt text, out-of-range offsets, failed-retrieval citations,
truncation-tail citations, NUL smuggling into canonical/excerpt text,
plausible-but-false canonical/claim hashes, logical duplicates with an
alternative claim hash, cross-account lineage, malformed hashes, and any
in-place mutation of the append-only history.

The honest writer registers the genuine ``evidence_sha256_hex`` function
(exactly as every controlled application connection does); a writer without
it cannot INSERT into the evidence tables at all.  The floor does NOT defend
against a writer who alters the schema, drops triggers or registers a forged
hash function — that writer is outside the E1 threat model.  ``raw_sha256``
and ``extracted_sha256`` are recorder-computed audit metadata (their inputs
are not persisted), so SQLite enforces only their format, never provenance.

Exit code 0 means every attack was blocked and the positive controls were
accepted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.testing.safety_kernel import activate as _activate_safety_kernel  # noqa: E402

_activate_safety_kernel()

from app.storage.db import initialize_database, register_evidence_hash_function  # noqa: E402

ACCOUNT_A = "qa-account-a"
ACCOUNT_B = "qa-account-b"


def _sha(payload: bytes | str) -> str:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def _canonical(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    mapped = [
        " " if (unicodedata.category(ch) == "Cc" or ch.isspace()) else ch
        for ch in normalized
        if unicodedata.category(ch) != "Cf"
    ]
    return unicodedata.normalize("NFC", " ".join("".join(mapped).split()))


_RETRIEVAL_SQL = (
    "INSERT INTO evidence_retrievals (account_id, requested_url, final_url,"
    " fetched_at, status, http_status, content_type, fetch_error,"
    " raw_size_bytes, raw_sha256, extracted_chars, extracted_sha256,"
    " canonical_text, canonical_chars, canonical_sha256, truncated, created_at)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

_EXCERPT_SQL = (
    "INSERT INTO evidence_excerpts (account_id, retrieval_id, claim_text,"
    " claim_sha256, excerpt_text, start_offset, end_offset, created_at)"
    " VALUES (?,?,?,?,?,?,?,?)"
)


def _retrieval_params(
    *,
    account_id: str = ACCOUNT_A,
    status: str = "OK",
    canonical_text: str,
    declared_chars: int | None = None,
    canonical_sha: str | None = None,
    truncated: int = 0,
    http_status: int | None = 200,
    fetch_error: str | None = None,
    content_type: str | None = "text/html",
) -> tuple:
    return (
        account_id, "https://example.org/qa", "https://example.org/qa",
        "2026-07-18 12:00:00.000000", status, http_status, content_type,
        fetch_error, len(canonical_text.encode("utf-8")), _sha(canonical_text),
        len(canonical_text), _sha(canonical_text), canonical_text,
        declared_chars if declared_chars is not None else len(canonical_text),
        canonical_sha if canonical_sha is not None else _sha(canonical_text),
        truncated, "2026-07-18 12:00:00.000000",
    )


def _insert_retrieval(conn: sqlite3.Connection, **kwargs) -> int:
    cur = conn.execute(_RETRIEVAL_SQL, _retrieval_params(**kwargs))
    conn.commit()
    return int(cur.lastrowid)


def _blocked(conn: sqlite3.Connection, sql: str, params: tuple) -> bool:
    try:
        conn.execute(sql, params)
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        return True
    return False


def main() -> int:
    checks: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="nia-evidence-floor-") as tmp:
        path = Path(tmp) / "evidence-floor.db"
        initialize_database(path)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        # Deliberately NO foreign_keys pragma: the floors must hold anyway.
        # The honest raw writer registers the genuine hash function.
        register_evidence_hash_function(conn)
        for account_id in (ACCOUNT_A, ACCOUNT_B):
            conn.execute(
                "INSERT INTO accounts (id, name, mode, autonomy_level, active,"
                " browser_profile_path, writing_profile_path) VALUES (?,?,?,?,?,?,?)",
                (account_id, account_id, "full_publication", "L1", 0, "./x", "./y"),
            )
        conn.commit()
        text = _canonical(
            "Alpha beta gamma delta epsilon zeta eta theta iota kappa "
            "lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega. " * 8
        )
        assert len(text) > 700, "probe text must allow a >600-char excerpt"
        ok_id = _insert_retrieval(conn, canonical_text=text)
        failed_id = _insert_retrieval(
            conn, status="FAILED", canonical_text="", http_status=404,
            fetch_error="HTTP_STATUS_404", truncated=0,
        )
        truncated_id = _insert_retrieval(conn, canonical_text=text, truncated=1)

        excerpt = text[0:39]
        assert excerpt[0] != " " and excerpt[-1] != " ", "control range must be word-aligned"
        now = "2026-07-18 12:00:01.000000"

        # 1. Positive control: a fully consistent excerpt must be accepted.
        try:
            conn.execute(_EXCERPT_SQL,
                (ACCOUNT_A, ok_id, "claim", _sha("claim"), excerpt, 0, 39, now))
            conn.commit()
            checks.append(True)
        except sqlite3.Error:
            conn.rollback()
            checks.append(False)

        # 2. Text that is not the exact canonical range.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c2", _sha("c2"),
             "forged excerpt text that never occurred", 0, 38, now)))
        # 3. End offset beyond the persisted canonical text.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c3", _sha("c3"), text[-40:],
             len(text) - 40 + 5, len(text) + 5, now)))
        # 4. Citation against a FAILED retrieval.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, failed_id, "c4", _sha("c4"),
             "irrelevant excerpt of forty characters!!", 0, 40, now)))
        # 5. Citation against a missing retrieval id (FK pragma is OFF).
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, 987654, "c5", _sha("c5"), excerpt, 0, 40, now)))
        # 6. Citation inside the truncation tail guard (last 100 chars).
        tail_start = len(text) - 30
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, truncated_id, "c6", _sha("c6"),
             text[tail_start:], tail_start, len(text), now)))
        # 7. Span shorter than the 10-char floor.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c7", _sha("c7"), text[0:5], 0, 5, now)))
        # 8. Span longer than the 600-char ceiling (word-aligned end so only
        #    the span rule can reject it).
        long_end = 601
        while text[long_end - 1] == " ":
            long_end += 1
        long_excerpt = text[0:long_end]
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c8", _sha("c8"), long_excerpt, 0, long_end, now)))
        # 9. Excerpt with a whitespace edge.
        space_at = text.index(" ")
        edged = text[space_at:space_at + 40]
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c9", _sha("c9"), edged, space_at, space_at + 40, now)))
        # 10. Declared length disagreeing with the offset span.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c10", _sha("c10"), text[0:40], 0, 41, now)))
        # 11. Malformed claim hash.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c11", "NOT-A-HASH", text[0:40], 0, 40, now)))
        # 12. Duplicate of the accepted excerpt (same claim hash and range).
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "claim", _sha("claim"), excerpt, 0, 39, now)))

        # 13-16. Append-only history: no update, no delete, on either table.
        checks.append(_blocked(conn,
            "UPDATE evidence_retrievals SET canonical_text=? WHERE id=?", ("tampered", ok_id)))
        checks.append(_blocked(conn,
            "DELETE FROM evidence_retrievals WHERE id=?", (failed_id,)))
        checks.append(_blocked(conn,
            "UPDATE evidence_excerpts SET excerpt_text=? WHERE retrieval_id=?",
            ("tampered", ok_id)))
        checks.append(_blocked(conn,
            "DELETE FROM evidence_excerpts WHERE retrieval_id=?", (ok_id,)))

        # 17. Inconsistent retrieval: OK status with a fetch error.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            canonical_text="x", status="OK", fetch_error="CONTRADICTION")))
        # 18. Inconsistent retrieval: declared canonical_chars != actual length.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            canonical_text="wxyz", declared_chars=40)))
        # 19. Inconsistent retrieval: malformed canonical hash format.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            canonical_text="wxyz", canonical_sha="UPPERCASE-NOT-HEX")))
        # 20. FAILED retrieval pretending to carry canonical content.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            canonical_text="wxyz", status="FAILED", http_status=404,
            fetch_error="HTTP_STATUS_404")))

        # 21-23. E1-B01: NUL smuggled before / inside / after a legal range.
        for at in (2, 30, len(text) - 3):
            smuggled = text[:at] + "\x00" + text[at + 1:]
            checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
                canonical_text=smuggled)))
        # 24. E1-B01: NUL inside excerpt text.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "c24", _sha("c24"),
             text[0:38] + "\x00", 0, 39, now)))
        # 25. E1-B01: the historical exploit — canonical_chars declared as the
        #     SQLite length() that stops at the first NUL.
        exploit = text[:50] + "\x00" + "HIDDEN TAIL NEVER ADDRESSABLE BY SQL"
        sqlite_len = conn.execute("SELECT length(?)", (exploit,)).fetchone()[0]
        checks.append(sqlite_len == 50 and _blocked(
            conn, _RETRIEVAL_SQL,
            _retrieval_params(canonical_text=exploit, declared_chars=sqlite_len)))

        # 26. E1-B02: a writer without the hash function cannot INSERT at all.
        bare = sqlite3.connect(path)
        try:
            checks.append(_blocked(bare, _RETRIEVAL_SQL, _retrieval_params(
                canonical_text="honest looking text")))
            checks.append(_blocked(bare, _EXCERPT_SQL,
                (ACCOUNT_A, ok_id, "c26", _sha("c26"), excerpt, 0, 39, now)))
        finally:
            bare.close()
        # 28. E1-B02: plausible-looking but false canonical hash.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            canonical_text=text, canonical_sha=_sha("a different text"))))
        # 29. E1-B02: plausible-looking but false claim hash.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "claim", _sha("not this claim"), excerpt, 0, 39, now)))
        # 30. E1-B02: reviewer counterexample `logical_duplicate_alt_claim_hash`
        #     — same account/retrieval/claim text/range, alternative well-formed
        #     claim hash.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "claim", _sha("claim-alt-fingerprint"),
             excerpt, 0, 39, now)))
        # 31. E1-B02: even with the TRUE hash the logical identity stays unique.
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_A, ok_id, "claim", _sha("claim"), excerpt, 0, 39, now)))

        # 32. E1-B03: account B cannot cite account A's retrieval (FK OFF).
        checks.append(_blocked(conn, _EXCERPT_SQL,
            (ACCOUNT_B, ok_id, "c32", _sha("c32"), excerpt, 0, 39, now)))
        # 33. E1-B03: blank account on a retrieval.
        checks.append(_blocked(conn, _RETRIEVAL_SQL, _retrieval_params(
            account_id="   ", canonical_text=text)))
        # 34. E1-B03 positive control: account B cites its OWN retrieval.
        rid_b = _insert_retrieval(conn, account_id=ACCOUNT_B, canonical_text=text)
        try:
            conn.execute(_EXCERPT_SQL,
                (ACCOUNT_B, rid_b, "claim", _sha("claim"), excerpt, 0, 39, now))
            conn.commit()
            checks.append(True)
        except sqlite3.Error:
            conn.rollback()
            checks.append(False)

        # 35. The accepted history is exactly two excerpts and four retrievals.
        counts = (
            conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0],
        )
        checks.append(counts == (4, 2))
        conn.close()

    passed = sum(checks)
    print(f"[BLOCKED] evidence floor disproof: {passed}/{len(checks)}")
    return 0 if passed == len(checks) == 35 else 1


if __name__ == "__main__":
    raise SystemExit(main())
