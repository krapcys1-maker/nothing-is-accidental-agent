-- Stage 2 / Wave E1 (ADR-099): isolated local evidence foundation.
--
-- A retrieval persists what was actually fetched: request/response identity,
-- the derivation hashes and exactly one canonical text used for citation.
-- An evidence excerpt binds one claim to one contiguous range of that
-- persisted canonical text.  Offsets always address `canonical_text` code
-- points; the pre-canonical extraction is only fingerprinted, never addressed.
--
-- Nothing in this migration touches existing research tables or the meaning
-- of `verification_status`.  The research pipeline is not integrated yet; the
-- tables are the durable substrate for the next wave.
--
-- SQLite cannot recompute SHA-256, so hash *values* are re-verified by the
-- application verifier; the floors below enforce every relation SQLite can
-- prove: exact substring equality against the persisted canonical text,
-- offset bounds, retrieval state, truncation guard and append-only history.
-- The application canonicalization guarantees NUL-free text, so length() and
-- substr() character semantics match Python code-point semantics.

CREATE TABLE evidence_retrievals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_url TEXT NOT NULL CHECK (
        length(trim(requested_url, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    final_url TEXT NOT NULL CHECK (
        length(trim(final_url, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    fetched_at TEXT NOT NULL CHECK (length(fetched_at) >= 19),
    status TEXT NOT NULL CHECK (status IN ('OK','FAILED')),
    http_status INTEGER CHECK (http_status IS NULL OR (http_status BETWEEN 100 AND 599)),
    content_type TEXT CHECK (content_type IS NULL OR length(content_type) > 0),
    fetch_error TEXT CHECK (fetch_error IS NULL OR length(fetch_error) > 0),
    raw_size_bytes INTEGER NOT NULL CHECK (raw_size_bytes >= 0),
    raw_sha256 TEXT NOT NULL CHECK (
        length(raw_sha256) = 64 AND raw_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    extracted_chars INTEGER NOT NULL CHECK (extracted_chars >= 0),
    extracted_sha256 TEXT NOT NULL CHECK (
        length(extracted_sha256) = 64 AND extracted_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    canonical_text TEXT NOT NULL,
    canonical_chars INTEGER NOT NULL CHECK (canonical_chars = length(canonical_text)),
    canonical_sha256 TEXT NOT NULL CHECK (
        length(canonical_sha256) = 64 AND canonical_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    truncated INTEGER NOT NULL CHECK (truncated IN (0, 1)),
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    -- NULL-proof branch contract: every nullable column is first pinned with
    -- IS NULL / IS NOT NULL so three-valued logic cannot let a row through.
    CHECK (
        (status = 'OK'
            AND fetch_error IS NULL
            AND http_status IS NOT NULL
            AND http_status BETWEEN 200 AND 299
            AND content_type IS NOT NULL
            AND canonical_chars > 0)
        OR
        (status = 'FAILED'
            AND fetch_error IS NOT NULL
            AND canonical_chars = 0
            AND truncated = 0)
    )
);

CREATE INDEX ix_evidence_retrievals_final_url ON evidence_retrievals(final_url);

CREATE TABLE evidence_excerpts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_id INTEGER NOT NULL REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    claim_text TEXT NOT NULL CHECK (
        length(trim(claim_text, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    claim_sha256 TEXT NOT NULL CHECK (
        length(claim_sha256) = 64 AND claim_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    excerpt_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    UNIQUE (retrieval_id, claim_sha256, start_offset, end_offset),
    -- Excerpt length is the offset span; bounds are the same constants the
    -- application verifier enforces (MIN_EXCERPT_CHARS / MAX_EXCERPT_CHARS).
    CHECK (length(excerpt_text) = end_offset - start_offset),
    CHECK (end_offset - start_offset BETWEEN 10 AND 600),
    -- Canonical text uses single ASCII spaces as its only whitespace, so an
    -- edge-space test is a complete "clean citation edge" floor.
    CHECK (excerpt_text NOT LIKE ' %' AND excerpt_text NOT LIKE '% ')
);

CREATE INDEX ix_evidence_excerpts_retrieval ON evidence_excerpts(retrieval_id);

-- The floor: an excerpt can only ever be the exact persisted canonical range
-- of one successful retrieval, and a truncated document refuses citations
-- inside its final 100 characters (the cut may have split a sentence).
CREATE TRIGGER evidence_excerpts_require_consistent_evidence
BEFORE INSERT ON evidence_excerpts
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_retrievals r
    WHERE r.id = NEW.retrieval_id
      AND r.status = 'OK'
      AND NEW.end_offset <= r.canonical_chars
      AND (r.truncated = 0 OR NEW.end_offset <= r.canonical_chars - 100)
      AND substr(r.canonical_text, NEW.start_offset + 1,
                 NEW.end_offset - NEW.start_offset) = NEW.excerpt_text
)
BEGIN
    SELECT RAISE(ABORT,
        'evidence excerpt must exactly match one persisted canonical range of a successful retrieval');
END;

-- Retrievals and excerpts are evidence: append-only, never edited in place.
CREATE TRIGGER evidence_retrievals_no_update
BEFORE UPDATE ON evidence_retrievals
BEGIN SELECT RAISE(ABORT, 'evidence_retrievals is append-only'); END;

CREATE TRIGGER evidence_retrievals_no_delete
BEFORE DELETE ON evidence_retrievals
BEGIN SELECT RAISE(ABORT, 'evidence_retrievals is append-only'); END;

CREATE TRIGGER evidence_excerpts_no_update
BEFORE UPDATE ON evidence_excerpts
BEGIN SELECT RAISE(ABORT, 'evidence_excerpts is append-only'); END;

CREATE TRIGGER evidence_excerpts_no_delete
BEFORE DELETE ON evidence_excerpts
BEGIN SELECT RAISE(ABORT, 'evidence_excerpts is append-only'); END;
