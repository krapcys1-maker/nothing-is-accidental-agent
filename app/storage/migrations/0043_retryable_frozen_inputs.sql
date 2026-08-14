-- 0043: one LIVE frozen input per hash, not one frozen input per hash ever.
--
-- A paid Research Card costs roughly 0.89 USD and today a single technical
-- hiccup destroys it permanently.  On 2026-08-14 four of five CONTENT runs died
-- without the article ever being judged bad: content 16, 17 and 19 on our own
-- quality-gate defects and content 18 because the reviewer's JSON answer hit
-- the 8192-token output ceiling and arrived truncated.  None of those four can
-- ever be retried, because `content_frozen_inputs.input_sha256` was globally
-- UNIQUE and its preimage deliberately contains no job_id, no content_id and no
-- attempt ordinal - it hashes the exact model input, which is the whole point.
-- The retry therefore recomputes the same hash and collides with the corpse of
-- the attempt that failed.
--
-- The invariant that was actually worth defending is narrower than the one that
-- was written down: no two *live* content items may share one frozen input, so
-- the account can never pay twice for the same article at the same time.  A
-- second attempt after the first one is terminal was never the thing to forbid.
-- 0043 states the real invariant as a partial unique index over live rows and
-- lets the inline UNIQUE go.
--
-- Liveness is a nullable `superseded_at` marker.  It is stamped by a trigger on
-- `content_transition_commands` rather than by Python, so no future code path
-- can terminalise a content item and leave its frozen input holding the live
-- slot.  0039 lets an owner-approved review resume take a FAILED item back to
-- RUNNING; the matching revive trigger re-takes the live slot for the resumed
-- item, and if a retry already holds it the whole resume transaction fails
-- closed on the index instead of letting two live items share one input.
--
-- Superseding spends nothing.  It only removes a block: an actual retry still
-- needs an explicit run with a new job_id and its own approval.  Only FAILED is
-- superseded.  NEEDS_VERIFICATION and SKIPPED are the ambiguous bucket where the
-- provider may already have produced and charged for an article, and releasing
-- those is a money decision with its own owner-approval ledger, not a schema
-- decision - deliberately left for a follow-on migration.
--
-- The table is rebuilt because the inline UNIQUE cannot be removed in place.
-- foreign_keys=OFF is mandatory (content_evidence_items.content_id REFERENCES
-- content_frozen_inputs(content_id) ON DELETE RESTRICT) and legacy_alter_table
-- is mandatory too: eight surviving triggers on other tables name
-- content_frozen_inputs and SQLite >= 3.25 would otherwise re-parse them during
-- the RENAME.  Because foreign-key enforcement is off, the copy is verified by
-- guard tables BEFORE the old table is dropped; RAISE() is illegal outside a
-- trigger program, so a CHECK-constrained temp table carries the assertion (the
-- same house pattern as 0035).

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER content_frozen_inputs_authoritative_hashes;
DROP TRIGGER content_frozen_inputs_bind_content;
DROP TRIGGER content_frozen_inputs_no_update;
DROP TRIGGER content_frozen_inputs_no_delete;

CREATE TABLE content_frozen_inputs_0043_new (
    content_id INTEGER PRIMARY KEY REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    input_schema_version TEXT NOT NULL CHECK (length(trim(input_schema_version)) BETWEEN 1 AND 100),
    output_schema_version TEXT NOT NULL CHECK (length(trim(output_schema_version)) BETWEEN 1 AND 100),
    prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
    style_guide_version TEXT NOT NULL CHECK (length(trim(style_guide_version)) BETWEEN 1 AND 200),
    article_brief_placeholder_json TEXT NOT NULL CHECK (json_valid(article_brief_placeholder_json)),
    article_brief_placeholder_sha256 TEXT NOT NULL CHECK (
        length(article_brief_placeholder_sha256)=64
        AND article_brief_placeholder_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    research_card_snapshot_json TEXT NOT NULL CHECK (json_valid(research_card_snapshot_json)),
    evidence_manifest_json TEXT NOT NULL CHECK (json_valid(evidence_manifest_json)),
    evidence_manifest_sha256 TEXT NOT NULL CHECK (
        length(evidence_manifest_sha256)=64
        AND evidence_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    evidence_item_count INTEGER NOT NULL CHECK (evidence_item_count > 0),
    input_snapshot_json TEXT NOT NULL CHECK (json_valid(input_snapshot_json)),
    -- The inline UNIQUE is deliberately gone; ux_content_frozen_inputs_live
    -- below carries the real invariant.  The shape CHECK is unchanged.
    input_sha256 TEXT NOT NULL CHECK (
        length(input_sha256)=64 AND input_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    superseded_at TEXT CHECK (
        superseded_at IS NULL
        OR (length(superseded_at)>=19 AND superseded_at>=created_at)
    )
);

-- Explicit column list: the column count differs, so SELECT * would be wrong.
-- The backfill derives a fact that already exists in content_items - the moment
-- the attempt terminalised as FAILED - and invents nothing.  Guard 3 below
-- asserts that it stamped exactly the FAILED rows and no others.
INSERT INTO content_frozen_inputs_0043_new (
    content_id, account_id, research_card_id, content_type,
    input_schema_version, output_schema_version, prompt_version,
    style_guide_version, article_brief_placeholder_json,
    article_brief_placeholder_sha256, research_card_snapshot_json,
    evidence_manifest_json, evidence_manifest_sha256, evidence_item_count,
    input_snapshot_json, input_sha256, created_at, superseded_at
)
SELECT fi.content_id, fi.account_id, fi.research_card_id, fi.content_type,
    fi.input_schema_version, fi.output_schema_version, fi.prompt_version,
    fi.style_guide_version, fi.article_brief_placeholder_json,
    fi.article_brief_placeholder_sha256, fi.research_card_snapshot_json,
    fi.evidence_manifest_json, fi.evidence_manifest_sha256,
    fi.evidence_item_count, fi.input_snapshot_json, fi.input_sha256,
    fi.created_at,
    (
        SELECT c.updated_at FROM content_items c
        WHERE c.id=fi.content_id AND c.status='FAILED'
    )
FROM content_frozen_inputs fi;

CREATE TEMP TABLE migration_0043_row_guard (
    discrepancy INTEGER NOT NULL CHECK (discrepancy=0)
);

-- Guard 1: no row was lost or invented by the copy.
INSERT INTO migration_0043_row_guard(discrepancy)
SELECT (SELECT count(*) FROM content_frozen_inputs)
     - (SELECT count(*) FROM content_frozen_inputs_0043_new);
DELETE FROM migration_0043_row_guard;

-- Guard 2: every surviving row is byte-identical in both hash-bearing columns
-- and in its content_id, in both directions.
INSERT INTO migration_0043_row_guard(discrepancy)
SELECT count(*) FROM content_frozen_inputs old
LEFT JOIN content_frozen_inputs_0043_new new
       ON new.content_id=old.content_id
      AND new.input_sha256=old.input_sha256
      AND new.input_snapshot_json=old.input_snapshot_json
      AND new.evidence_manifest_sha256=old.evidence_manifest_sha256
      AND new.article_brief_placeholder_sha256=old.article_brief_placeholder_sha256
      AND new.created_at=old.created_at
WHERE new.content_id IS NULL;
DELETE FROM migration_0043_row_guard;
INSERT INTO migration_0043_row_guard(discrepancy)
SELECT count(*) FROM content_frozen_inputs_0043_new new
LEFT JOIN content_frozen_inputs old
       ON old.content_id=new.content_id
      AND old.input_sha256=new.input_sha256
      AND old.input_snapshot_json=new.input_snapshot_json
WHERE old.content_id IS NULL;
DELETE FROM migration_0043_row_guard;

-- Guard 3: the backfill stamped exactly the FAILED attempts.
INSERT INTO migration_0043_row_guard(discrepancy)
SELECT (
    SELECT count(*) FROM content_frozen_inputs_0043_new
    WHERE superseded_at IS NOT NULL
) - (
    SELECT count(*) FROM content_frozen_inputs fi
    JOIN content_items c ON c.id=fi.content_id
    WHERE c.status='FAILED'
);
DELETE FROM migration_0043_row_guard;

-- Guard 4: the live slot is already single-occupancy, so the partial unique
-- index below can be built.  Fail closed rather than half-apply.
INSERT INTO migration_0043_row_guard(discrepancy)
SELECT count(*) FROM (
    SELECT input_sha256 FROM content_frozen_inputs_0043_new
    WHERE superseded_at IS NULL
    GROUP BY input_sha256 HAVING count(*)>1
);
DROP TABLE migration_0043_row_guard;

DROP TABLE content_frozen_inputs;
ALTER TABLE content_frozen_inputs_0043_new RENAME TO content_frozen_inputs;

-- The actual invariant: at most one LIVE content item may hold a given frozen
-- input.  Nothing reads content_frozen_inputs by input_sha256 alone, so this is
-- the only index the column needs.
CREATE UNIQUE INDEX ux_content_frozen_inputs_live
    ON content_frozen_inputs(input_sha256) WHERE superseded_at IS NULL;

-- Re-created because DROP TABLE destroyed the table's own triggers.  The hash
-- floor additionally refuses a row that would be born already superseded: only
-- the terminal-transition trigger may ever set the marker.
CREATE TRIGGER content_frozen_inputs_authoritative_hashes
BEFORE INSERT ON content_frozen_inputs
WHEN NEW.article_brief_placeholder_sha256
        IS NOT evidence_sha256_hex(NEW.article_brief_placeholder_json)
 OR NEW.evidence_manifest_sha256
        IS NOT evidence_sha256_hex(NEW.evidence_manifest_json)
 OR NEW.input_sha256 IS NOT evidence_sha256_hex(NEW.input_snapshot_json)
 OR NEW.superseded_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'content frozen input hash does not match its preimage or is born superseded'); END;

-- Re-created verbatim.
CREATE TRIGGER content_frozen_inputs_bind_content
BEFORE INSERT ON content_frozen_inputs
WHEN NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN research_cards rc ON rc.id=NEW.research_card_id
    JOIN topics t ON t.id=rc.topic_id
    WHERE c.id=NEW.content_id
      AND c.account_id=NEW.account_id
      AND c.research_card_id=NEW.research_card_id
      AND c.type=NEW.content_type
      AND c.status='DRAFT'
      AND t.account_id=NEW.account_id
      AND rc.publication_recommendation='PROCEED'
)
BEGIN SELECT RAISE(ABORT, 'frozen content input must bind one account-scoped PROCEED card'); END;

-- Replaces content_frozen_inputs_no_update.  Every frozen column is still
-- immutable; the ONLY writable field is the liveness marker, and only along the
-- two transitions the lifecycle actually authorises:
--   NULL -> timestamp  requires a durable FAILED transition command for that
--                      content_id stamped at exactly that instant;
--   timestamp -> NULL  requires an ACTIVE owner-approved review resume session
--                      for that content_id (0039), which re-takes the live slot.
-- The abort message still says "append-only" because that remains the contract
-- everywhere except the marker.
CREATE TRIGGER content_frozen_inputs_supersede_only
BEFORE UPDATE ON content_frozen_inputs
WHEN NOT (
    NEW.content_id IS OLD.content_id
    AND NEW.account_id IS OLD.account_id
    AND NEW.research_card_id IS OLD.research_card_id
    AND NEW.content_type IS OLD.content_type
    AND NEW.input_schema_version IS OLD.input_schema_version
    AND NEW.output_schema_version IS OLD.output_schema_version
    AND NEW.prompt_version IS OLD.prompt_version
    AND NEW.style_guide_version IS OLD.style_guide_version
    AND NEW.article_brief_placeholder_json IS OLD.article_brief_placeholder_json
    AND NEW.article_brief_placeholder_sha256 IS OLD.article_brief_placeholder_sha256
    AND NEW.research_card_snapshot_json IS OLD.research_card_snapshot_json
    AND NEW.evidence_manifest_json IS OLD.evidence_manifest_json
    AND NEW.evidence_manifest_sha256 IS OLD.evidence_manifest_sha256
    AND NEW.evidence_item_count IS OLD.evidence_item_count
    AND NEW.input_snapshot_json IS OLD.input_snapshot_json
    AND NEW.input_sha256 IS OLD.input_sha256
    AND NEW.created_at IS OLD.created_at
    AND (
        (
            OLD.superseded_at IS NULL AND NEW.superseded_at IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM content_transition_commands tc
                WHERE tc.content_id=NEW.content_id
                  AND tc.target_content_status='FAILED'
                  AND tc.created_at=NEW.superseded_at
            )
        )
        OR (
            OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS NULL
            AND EXISTS (
                SELECT 1 FROM content_review_resume_sessions s
                WHERE s.content_id=NEW.content_id AND s.status='ACTIVE'
            )
        )
    )
)
BEGIN SELECT RAISE(ABORT, 'content_frozen_inputs is append-only apart from its supersede marker'); END;

-- Re-created verbatim.
CREATE TRIGGER content_frozen_inputs_no_delete
BEFORE DELETE ON content_frozen_inputs
BEGIN SELECT RAISE(ABORT, 'content_frozen_inputs is append-only'); END;

-- The stamping point.  transition_content_execution never touches content_items
-- itself: it inserts one content_transition_commands row and the trigger chain
-- carries it to content_runs and then to content_items.  Owning the stamp here
-- means no future path can terminalise a card and leave its input live.  Order
-- relative to content_transition_commands_apply is unspecified in SQLite and
-- irrelevant: the two touch disjoint tables.
CREATE TRIGGER content_frozen_inputs_supersede_on_terminal
AFTER INSERT ON content_transition_commands
WHEN NEW.target_content_status='FAILED'
BEGIN
    UPDATE content_frozen_inputs SET superseded_at=NEW.created_at
     WHERE content_id=NEW.content_id AND superseded_at IS NULL;
    SELECT CASE changes()
        WHEN 1 THEN NULL
        ELSE RAISE(ABORT, 'terminal FAILED must supersede exactly one frozen input')
    END;
END;

-- 0039 permits FAILED -> RUNNING under an ACTIVE resume session.  Without this
-- the resumed item and a retry that already took the live slot would both be
-- live on one frozen input and both could pay.  The resume re-takes the slot;
-- if a retry holds it, ux_content_frozen_inputs_live fails the resume closed
-- before begin_content_review_resume_session mutates any job, run or content
-- run, because the session row is inserted first.
CREATE TRIGGER content_frozen_inputs_revive_on_resume
AFTER INSERT ON content_review_resume_sessions
BEGIN
    UPDATE content_frozen_inputs SET superseded_at=NULL
     WHERE content_id=NEW.content_id AND superseded_at IS NOT NULL;
END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0043_retryable_frozen_inputs', datetime('now'));
COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
