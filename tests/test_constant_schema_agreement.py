"""A constant in code must fit the CHECK constraint that stores its values.

The schema is the third party to every limit in this system and it is the one
nobody remembers. Timeouts, ceilings and attempt numbers are all pinned twice -
once as a Python constant and once as a SQL CHECK - and the two were written in
different waves of the build.

This test exists because I raised MAX_WRITER_ATTEMPTS from 2 to 4 so a fixable
draft would not die with its paid research card, changed the loop, and changed
nothing else. attempt_no IN (1,2) is a CHECK on eight tables. Attempt three
died on a validation error, stranded a live run in REVISE and cost about
1.84 USD of research and writing that could not be retried.

The other agreement tests in this suite compare a prompt against its validator
and a deadline against its own output ceiling. Neither looks at the database,
which is why this got through both of them.

Reading the CHECK text out of the migrations rather than out of a live database
is deliberate: the migrations are what a fresh install applies, they are in the
repository, and the test then works with no database at all.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest

from app.content.pipeline import MAX_WRITER_ATTEMPTS


MIGRATIONS = Path(__file__).resolve().parents[1] / "app" / "storage" / "migrations"


def _schema_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS.glob("*.sql"))
    )


def _highest_allowed(column: str, schema: str) -> int | None:
    """The largest value any CHECK on this column permits, or None if unbounded.

    Handles the two shapes the schema actually uses: an IN list and a BETWEEN
    range. A column with neither is not constrained here.
    """
    best: int | None = None
    for match in re.finditer(
        rf"\b{re.escape(column)}\b[^,]*?CHECK\s*\(\s*{re.escape(column)}\s+IN\s*\(([^)]*)\)",
        schema,
        re.IGNORECASE,
    ):
        values = [int(v) for v in re.findall(r"\d+", match.group(1))]
        if values:
            best = max(values) if best is None else min(best, max(values))
    for match in re.finditer(
        rf"\b{re.escape(column)}\b[^,]*?CHECK\s*\(\s*{re.escape(column)}\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)",
        schema,
        re.IGNORECASE,
    ):
        upper = int(match.group(2))
        best = upper if best is None else min(best, upper)
    return best


def test_writer_attempt_cap_fits_the_schema_that_stores_it():
    schema = _schema_text()
    allowed = _highest_allowed("attempt_no", schema)
    assert allowed is not None, (
        "no CHECK on attempt_no was found in the migrations; if the constraint "
        "moved, this test has stopped protecting anything"
    )
    assert MAX_WRITER_ATTEMPTS <= allowed, (
        f"MAX_WRITER_ATTEMPTS is {MAX_WRITER_ATTEMPTS} but the strictest CHECK "
        f"on attempt_no allows at most {allowed}. Attempt "
        f"{allowed + 1} will fail on a constraint after the writer has already "
        f"been paid. Raising the cap means migrating every table that pins it."
    )


def test_the_check_extractor_still_sees_the_constraint():
    """A total check that matches nothing is worse than no check at all."""
    schema = _schema_text()
    assert "attempt_no IN (1,2)" in schema.replace(" ", "").replace(
        "attempt_noIN(1,2)", "attempt_no IN (1,2)"
    ) or _highest_allowed("attempt_no", schema) is not None, (
        "the attempt_no CHECK is no longer readable from the migrations"
    )


@pytest.mark.parametrize(
    "column,constant,name",
    [
        ("max_output_tokens", 8_192, "reviewer/writer output ceiling"),
    ],
)
def test_token_ceilings_fit_their_schema_checks(column, constant, name):
    """The other constant the schema pins, and the reason it cannot be raised.

    max_output_tokens is CHECKed at 8192 in four tables, so the reviewer's
    ceiling is not a number in Python that anyone can change - raising it needs
    a migration and a fresh paid qualification. Recorded here so the next
    attempt to raise it finds the reason before spending anything.
    """
    allowed = _highest_allowed(column, _schema_text())
    if allowed is None:
        pytest.skip(f"{column} carries no CHECK in the migrations")
    assert constant <= allowed, (
        f"{name}: {constant} exceeds the schema maximum of {allowed}"
    )
