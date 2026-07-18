-- Stage 2 / Wave E1 (ADR-099, repaired per ADR-100): isolated local evidence
-- foundation with an explicit per-account scope.
--
-- A retrieval persists what was actually fetched for exactly one account:
-- request/response identity, the derivation hashes and exactly one canonical
-- text used for citation.  An evidence excerpt binds one claim to one
-- contiguous range of that persisted canonical text, inside the same account.
-- Offsets always address `canonical_text` code points; the pre-canonical
-- extraction is only fingerprinted, never addressed.
--
-- Nothing in this migration touches existing research tables or the meaning
-- of `verification_status`.  The research pipeline is not integrated yet; the
-- tables are the durable substrate for the next wave.
--
-- Trust boundary of the SQLite floor (stated honestly):
--   * `canonical_text`, `excerpt_text` and `claim_text` are enforced NUL-free
--     and stored as TEXT, so length()/substr() character semantics equal
--     Python code-point slicing and the historical length()-stops-at-NUL
--     behavior cannot be exploited.
--   * `canonical_sha256` and `claim_sha256` are bound to the actually
--     persisted text by triggers calling the deterministic application
--     function `evidence_sha256_hex` (registered by app.storage.db on every
--     controlled connection).  A writer without the function cannot INSERT at
--     all ("no such function" - fail closed); a writer with the genuine
--     function cannot persist a false hash.
--   * `raw_sha256` and `extracted_sha256` are audit metadata computed by the
--     application recorder from the real raw bytes and extracted text; those
--     inputs are NOT persisted, so SQLite can only enforce their format,
--     never their provenance.  They are not a self-verifying floor.
--   * None of the floors defends against a writer who alters the schema,
--     drops triggers, or deliberately registers a forged
--     `evidence_sha256_hex`; that writer is outside the E1 threat model.

CREATE TABLE evidence_retrievals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT CHECK (
        typeof(account_id) = 'text'
        AND length(trim(account_id, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
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
    -- NUL-free TEXT storage is the precondition for offset equivalence:
    -- SQLite length()/substr() stop counting at an embedded NUL, so a NUL
    -- would silently desynchronize SQL ranges from Python slicing.
    canonical_text TEXT NOT NULL CHECK (
        typeof(canonical_text) = 'text'
        AND instr(CAST(canonical_text AS BLOB), x'00') = 0
    ),
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

CREATE INDEX ix_evidence_retrievals_account_final_url
    ON evidence_retrievals(account_id, final_url);

CREATE TABLE evidence_excerpts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT CHECK (
        typeof(account_id) = 'text'
        AND length(trim(account_id, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    retrieval_id INTEGER NOT NULL REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    claim_text TEXT NOT NULL CHECK (
        typeof(claim_text) = 'text'
        AND instr(CAST(claim_text AS BLOB), x'00') = 0
        AND length(trim(claim_text, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    claim_sha256 TEXT NOT NULL CHECK (
        length(claim_sha256) = 64 AND claim_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    excerpt_text TEXT NOT NULL CHECK (
        typeof(excerpt_text) = 'text'
        AND instr(CAST(excerpt_text AS BLOB), x'00') = 0
    ),
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

-- Logical idempotency floor: the same claim TEXT for the same retrieval and
-- range is one record, no matter what the derived claim_sha256 claims to be.
-- This closes the reviewer counterexample `logical_duplicate_alt_claim_hash`.
CREATE UNIQUE INDEX ux_evidence_excerpts_claim_identity
    ON evidence_excerpts(retrieval_id, claim_text, start_offset, end_offset);

-- Authoritative hashes: the derived hash columns must equal the SHA-256 of
-- the actually persisted text, recomputed inside SQLite via the registered
-- deterministic application function.  Without the function every INSERT
-- fails closed; with it a plausible-looking false hash is rejected.
CREATE TRIGGER evidence_retrievals_authoritative_canonical_hash
BEFORE INSERT ON evidence_retrievals
WHEN NEW.canonical_sha256 IS NOT evidence_sha256_hex(NEW.canonical_text)
BEGIN
    SELECT RAISE(ABORT,
        'evidence_retrievals.canonical_sha256 must be the SHA-256 of the persisted canonical_text');
END;

CREATE TRIGGER evidence_excerpts_authoritative_claim_hash
BEFORE INSERT ON evidence_excerpts
WHEN NEW.claim_sha256 IS NOT evidence_sha256_hex(NEW.claim_text)
BEGIN
    SELECT RAISE(ABORT,
        'evidence_excerpts.claim_sha256 must be the SHA-256 of the persisted claim_text');
END;

-- Account lineage floor: an excerpt may only cite a retrieval of the same
-- account.  The trigger holds even when a raw writer disables PRAGMA
-- foreign_keys, because it re-reads the parent row itself.
CREATE TRIGGER evidence_excerpts_same_account_lineage
BEFORE INSERT ON evidence_excerpts
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_retrievals r
    WHERE r.id = NEW.retrieval_id
      AND r.account_id = NEW.account_id
)
BEGIN
    SELECT RAISE(ABORT,
        'evidence excerpt must cite a retrieval that belongs to the same account');
END;

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
