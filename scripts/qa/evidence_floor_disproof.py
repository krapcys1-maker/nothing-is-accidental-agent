"""Independent offline disproof for the Stage 2 E1 evidence floors (ADR-099).

The probe uses only throwaway SQLite databases and raw ``sqlite3`` handles
(with ``PRAGMA foreign_keys`` deliberately left OFF) to prove that migration
0016 itself — not the application layer — refuses inconsistent evidence:
mismatched excerpt text, out-of-range offsets, failed-retrieval citations,
truncation-tail citations, malformed hashes, and any in-place mutation of the
append-only history.  Exit code 0 means every attack was blocked and one
consistent excerpt (the positive control) was accepted.
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

from app.storage.db import initialize_database  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    mapped = [
        " " if (unicodedata.category(ch) == "Cc" or ch.isspace()) else ch
        for ch in normalized
        if unicodedata.category(ch) != "Cf"
    ]
    return unicodedata.normalize("NFC", " ".join("".join(mapped).split()))


def _insert_retrieval(
    conn: sqlite3.Connection,
    *,
    status: str = "OK",
    canonical_text: str,
    truncated: int = 0,
    http_status: int | None = 200,
    fetch_error: str | None = None,
    content_type: str | None = "text/html",
) -> int:
    cur = conn.execute(
        "INSERT INTO evidence_retrievals (requested_url, final_url, fetched_at,"
        " status, http_status, content_type, fetch_error, raw_size_bytes,"
        " raw_sha256, extracted_chars, extracted_sha256, canonical_text,"
        " canonical_chars, canonical_sha256, truncated, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "https://example.org/qa", "https://example.org/qa",
            "2026-07-18 12:00:00.000000", status, http_status, content_type,
            fetch_error, len(canonical_text.encode("utf-8")),
            _sha(canonical_text), len(canonical_text), _sha(canonical_text),
            canonical_text, len(canonical_text), _sha(canonical_text),
            truncated, "2026-07-18 12:00:00.000000",
        ),
    )
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
        insert_sql = (
            "INSERT INTO evidence_excerpts (retrieval_id, claim_text, claim_sha256,"
            " excerpt_text, start_offset, end_offset, created_at) VALUES (?,?,?,?,?,?,?)"
        )
        now = "2026-07-18 12:00:01.000000"

        # 1. Positive control: a fully consistent excerpt must be accepted.
        try:
            conn.execute(insert_sql, (ok_id, "claim", _sha("claim"), excerpt, 0, 39, now))
            conn.commit()
            checks.append(True)
        except sqlite3.Error:
            conn.rollback()
            checks.append(False)

        # 2. Text that is not the exact canonical range.
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c2", _sha("c2"), "forged excerpt text that never occurred", 0, 38, now)))
        # 3. End offset beyond the persisted canonical text.
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c3", _sha("c3"), text[-40:], len(text) - 40 + 5, len(text) + 5, now)))
        # 4. Citation against a FAILED retrieval.
        checks.append(_blocked(conn, insert_sql,
            (failed_id, "c4", _sha("c4"), "irrelevant excerpt of forty characters!!", 0, 40, now)))
        # 5. Citation against a missing retrieval id (FK pragma is OFF).
        checks.append(_blocked(conn, insert_sql,
            (987654, "c5", _sha("c5"), excerpt, 0, 40, now)))
        # 6. Citation inside the truncation tail guard (last 100 chars).
        tail_start = len(text) - 30
        checks.append(_blocked(conn, insert_sql,
            (truncated_id, "c6", _sha("c6"), text[tail_start:], tail_start, len(text), now)))
        # 7. Span shorter than the 10-char floor.
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c7", _sha("c7"), text[0:5], 0, 5, now)))
        # 8. Span longer than the 600-char ceiling (word-aligned end so only
        #    the span rule can reject it).
        long_end = 601
        while text[long_end - 1] == " ":
            long_end += 1
        long_excerpt = text[0:long_end]
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c8", _sha("c8"), long_excerpt, 0, long_end, now)))
        # 9. Excerpt with a whitespace edge.
        space_at = text.index(" ")
        edged = text[space_at:space_at + 40]
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c9", _sha("c9"), edged, space_at, space_at + 40, now)))
        # 10. Declared length disagreeing with the offset span.
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c10", _sha("c10"), text[0:40], 0, 41, now)))
        # 11. Malformed claim hash.
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "c11", "NOT-A-HASH", text[0:40], 0, 40, now)))
        # 12. Duplicate of the accepted excerpt (same claim hash and range).
        checks.append(_blocked(conn, insert_sql,
            (ok_id, "claim", _sha("claim"), excerpt, 0, 39, now)))

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
        checks.append(_blocked(conn,
            "INSERT INTO evidence_retrievals (requested_url, final_url, fetched_at,"
            " status, http_status, content_type, fetch_error, raw_size_bytes,"
            " raw_sha256, extracted_chars, extracted_sha256, canonical_text,"
            " canonical_chars, canonical_sha256, truncated, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("https://x", "https://x", "2026-07-18 12:00:00.000000", "OK", 200,
             "text/html", "CONTRADICTION", 1, _sha("x"), 1, _sha("x"), "x", 1,
             _sha("x"), 0, "2026-07-18 12:00:00.000000")))
        # 18. Inconsistent retrieval: declared canonical_chars != actual length.
        checks.append(_blocked(conn,
            "INSERT INTO evidence_retrievals (requested_url, final_url, fetched_at,"
            " status, http_status, content_type, fetch_error, raw_size_bytes,"
            " raw_sha256, extracted_chars, extracted_sha256, canonical_text,"
            " canonical_chars, canonical_sha256, truncated, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("https://x", "https://x", "2026-07-18 12:00:00.000000", "OK", 200,
             "text/html", None, 4, _sha("wxyz"), 4, _sha("wxyz"), "wxyz", 40,
             _sha("wxyz"), 0, "2026-07-18 12:00:00.000000")))
        # 19. Inconsistent retrieval: malformed canonical hash format.
        checks.append(_blocked(conn,
            "INSERT INTO evidence_retrievals (requested_url, final_url, fetched_at,"
            " status, http_status, content_type, fetch_error, raw_size_bytes,"
            " raw_sha256, extracted_chars, extracted_sha256, canonical_text,"
            " canonical_chars, canonical_sha256, truncated, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("https://x", "https://x", "2026-07-18 12:00:00.000000", "OK", 200,
             "text/html", None, 4, _sha("wxyz"), 4, _sha("wxyz"), "wxyz", 4,
             "UPPERCASE-NOT-HEX", 0, "2026-07-18 12:00:00.000000")))
        # 20. FAILED retrieval pretending to carry canonical content.
        checks.append(_blocked(conn,
            "INSERT INTO evidence_retrievals (requested_url, final_url, fetched_at,"
            " status, http_status, content_type, fetch_error, raw_size_bytes,"
            " raw_sha256, extracted_chars, extracted_sha256, canonical_text,"
            " canonical_chars, canonical_sha256, truncated, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("https://x", "https://x", "2026-07-18 12:00:00.000000", "FAILED", 404,
             "text/html", "HTTP_STATUS_404", 4, _sha("wxyz"), 4, _sha("wxyz"),
             "wxyz", 4, _sha("wxyz"), 0, "2026-07-18 12:00:00.000000")))

        # 21. The accepted history is exactly one excerpt and three retrievals.
        counts = (
            conn.execute("SELECT COUNT(*) FROM evidence_retrievals").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM evidence_excerpts").fetchone()[0],
        )
        checks.append(counts == (3, 1))
        conn.close()

    passed = sum(checks)
    print(f"[BLOCKED] evidence floor disproof: {passed}/{len(checks)}")
    return 0 if passed == len(checks) == 21 else 1


if __name__ == "__main__":
    raise SystemExit(main())
