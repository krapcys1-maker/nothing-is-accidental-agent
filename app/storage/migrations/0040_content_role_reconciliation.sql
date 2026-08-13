-- Owner-authorised conservative resolution for historical CONTENT provider
-- effects whose request-level provider charge cannot be proven.  This ledger is
-- deliberately separate from actual model_usage: the provider cost remains
-- unknown while the full preserved reservation becomes effective budget spend.

CREATE TABLE conservative_content_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('PROVIDER_ATTEMPT', 'ROLE_EXECUTION')),
    source_identity TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    content_id INTEGER REFERENCES content_items(id) ON DELETE RESTRICT,
    run_id TEXT REFERENCES runs(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    resolution TEXT NOT NULL
        CHECK (resolution = 'CONSERVATIVE_MAX_CHARGED'),
    reserved_amount_usd TEXT NOT NULL
        CHECK (
            CAST(reserved_amount_usd AS REAL) > 0.0
            AND printf('%.6f', CAST(reserved_amount_usd AS REAL)) = reserved_amount_usd
        ),
    conservative_cost_usd TEXT NOT NULL
        CHECK (
            conservative_cost_usd = reserved_amount_usd
            AND printf('%.6f', CAST(conservative_cost_usd AS REAL)) = conservative_cost_usd
        ),
    actual_cost_usd REAL CHECK (actual_cost_usd IS NULL),
    evidence_kind TEXT NOT NULL
        CHECK (evidence_kind = 'OWNER_CONSERVATIVE_ADJUDICATION'),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    approved_by TEXT NOT NULL CHECK (length(trim(approved_by)) BETWEEN 1 AND 128),
    approved_at TEXT NOT NULL,
    approval_json TEXT NOT NULL CHECK (json_valid(approval_json)),
    approval_fingerprint TEXT NOT NULL UNIQUE
        CHECK (length(approval_fingerprint) = 64),
    created_at TEXT NOT NULL,
    audit_json TEXT NOT NULL CHECK (json_valid(audit_json)),
    audit_fingerprint TEXT NOT NULL UNIQUE
        CHECK (length(audit_fingerprint) = 64),
    UNIQUE (source_type, source_identity)
);

CREATE INDEX ix_conservative_content_reconciliations_created
    ON conservative_content_reconciliations(created_at, source_type);

-- The decomposed columns, immutable owner approval and audit envelope must all
-- describe exactly the same decision.  Fingerprints use the canonical JSON
-- emitted by the storage boundary; SQLite verifies the persisted bytes.
CREATE TRIGGER conservative_content_reconciliations_contract
BEFORE INSERT ON conservative_content_reconciliations
WHEN NEW.approval_fingerprint != evidence_sha256_hex(NEW.approval_json)
 OR NEW.audit_fingerprint != evidence_sha256_hex(NEW.audit_json)
 OR json_extract(NEW.approval_json, '$.schema_version') != 'conservative_content_reconciliation_approval_v1'
 OR json_extract(NEW.approval_json, '$.source_type') != NEW.source_type
 OR json_extract(NEW.approval_json, '$.source_identity') != NEW.source_identity
 OR json_extract(NEW.approval_json, '$.job_id') != NEW.job_id
 OR json_extract(NEW.approval_json, '$.content_id') IS NOT NEW.content_id
 OR json_extract(NEW.approval_json, '$.run_id') IS NOT NEW.run_id
 OR json_extract(NEW.approval_json, '$.provider') != NEW.provider
 OR json_extract(NEW.approval_json, '$.model') != NEW.model
 OR json_extract(NEW.approval_json, '$.resolution') != NEW.resolution
 OR json_extract(NEW.approval_json, '$.expected_reserved_amount_usd') != NEW.reserved_amount_usd
 OR json_extract(NEW.approval_json, '$.evidence_kind') != NEW.evidence_kind
 OR json_extract(NEW.approval_json, '$.reason') != NEW.reason
 OR json_extract(NEW.approval_json, '$.approved_by') != NEW.approved_by
 OR json_extract(NEW.approval_json, '$.approved_at') != NEW.approved_at
 OR json_extract(NEW.audit_json, '$.schema_version') != 'conservative_content_reconciliation_audit_v1'
 OR json_extract(NEW.audit_json, '$.reconciliation_id') != NEW.reconciliation_id
 OR json_extract(NEW.audit_json, '$.source_type') != NEW.source_type
 OR json_extract(NEW.audit_json, '$.source_identity') != NEW.source_identity
 OR json_extract(NEW.audit_json, '$.job_id') != NEW.job_id
 OR json_extract(NEW.audit_json, '$.content_id') IS NOT NEW.content_id
 OR json_extract(NEW.audit_json, '$.run_id') IS NOT NEW.run_id
 OR json_extract(NEW.audit_json, '$.provider') != NEW.provider
 OR json_extract(NEW.audit_json, '$.model') != NEW.model
 OR json_extract(NEW.audit_json, '$.previous_status') != NEW.previous_status
 OR json_extract(NEW.audit_json, '$.resolution') != NEW.resolution
 OR json_extract(NEW.audit_json, '$.reserved_amount_usd') != NEW.reserved_amount_usd
 OR json_extract(NEW.audit_json, '$.conservative_cost_usd') != NEW.conservative_cost_usd
 OR json_type(NEW.audit_json, '$.actual_cost_usd') != 'null'
 OR json_extract(NEW.audit_json, '$.evidence_kind') != NEW.evidence_kind
 OR json_extract(NEW.audit_json, '$.reason') != NEW.reason
 OR json_extract(NEW.audit_json, '$.approved_by') != NEW.approved_by
 OR json_extract(NEW.audit_json, '$.approved_at') != NEW.approved_at
 OR json_extract(NEW.audit_json, '$.approval_fingerprint') != NEW.approval_fingerprint
 OR json_extract(NEW.audit_json, '$.created_at') != NEW.created_at
BEGIN
    SELECT RAISE(ABORT, 'conservative reconciliation approval/audit contract mismatch');
END;

-- A writer source is accepted only from the frozen CONTENT/ARTICLE lineage that
-- actually crossed REQUEST_STARTED, returned no usage/cost and is still blocked
-- for reconciliation.  The writer result supplies the frozen provider/model and
-- content identity even for legacy rows predating content_provider_attempts.
CREATE TRIGGER conservative_content_reconciliations_provider_source
BEFORE INSERT ON conservative_content_reconciliations
WHEN NEW.source_type = 'PROVIDER_ATTEMPT' AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id = p.job_id
    JOIN runs r ON r.id = j.run_id
    JOIN content_writer_results wr ON wr.request_id = p.request_id
    JOIN content_writer_intents wi ON wi.intent_id = wr.intent_id
    JOIN content_items c ON c.id = wr.content_id
    WHERE p.request_id = NEW.source_identity
      AND p.job_id = NEW.job_id
      AND p.status = 'NEEDS_RECONCILIATION'
      AND p.request_started_at IS NOT NULL
      AND p.actual_cost_usd IS NULL
      AND j.kind = 'CONTENT' AND j.workflow = 'ARTICLE'
      AND j.run_id = NEW.run_id AND r.id = NEW.run_id
      AND c.id = NEW.content_id AND c.job_id = j.id AND c.run_id = r.id
      AND wr.job_id = j.id AND wr.run_id = r.id
      AND wi.job_id = j.id AND wi.run_id = r.id AND wi.content_id = c.id
      AND wi.attempt_no = p.attempt_no
      AND wi.intent_fingerprint = p.execution_intent_fingerprint
      AND wr.provider = NEW.provider AND wr.api_model_id = NEW.model
      AND printf('%.6f', p.reserved_amount_usd) = NEW.reserved_amount_usd
      AND NEW.previous_status = 'NEEDS_RECONCILIATION'
      AND NOT EXISTS (
          SELECT 1 FROM model_usage u
          WHERE u.request_id = p.request_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'unsupported or non-ambiguous CONTENT provider attempt');
END;

-- A role source must be the immutable terminal uncertainty created after the
-- external-effect marker.  No token or cost fields may have become known.
CREATE TRIGGER conservative_content_reconciliations_role_source
BEFORE INSERT ON conservative_content_reconciliations
WHEN NEW.source_type = 'ROLE_EXECUTION' AND NOT EXISTS (
    SELECT 1
    FROM role_provider_executions e
    JOIN jobs j ON j.id = e.job_id
    JOIN runs r ON r.id = e.run_id
    JOIN content_items c ON c.id = e.content_id
    WHERE e.execution_ref = NEW.source_identity
      AND e.job_id = NEW.job_id AND e.run_id = NEW.run_id
      AND e.content_id = NEW.content_id
      AND e.provider = NEW.provider AND e.technical_model_id = NEW.model
      AND e.outcome = 'NEEDS_VERIFICATION'
      AND e.external_effect_started_at IS NOT NULL
      AND e.cost_usd IS NULL AND e.input_tokens IS NULL AND e.output_tokens IS NULL
      AND e.cache_read_tokens IS NULL AND e.cache_write_tokens IS NULL
      AND e.web_search_requests IS NULL
      AND j.kind = 'CONTENT' AND j.workflow = 'ARTICLE'
      AND c.job_id = j.id AND c.run_id = r.id
      AND printf('%.6f', CAST(e.reserved_cost_usd AS REAL)) = NEW.reserved_amount_usd
      AND NEW.previous_status = 'NEEDS_VERIFICATION'
      AND NOT EXISTS (
          SELECT 1 FROM model_usage u
          WHERE u.request_id = e.execution_ref
      )
)
BEGIN
    SELECT RAISE(ABORT, 'unsupported or non-ambiguous CONTENT role execution');
END;

CREATE TRIGGER conservative_content_reconciliations_no_update
BEFORE UPDATE ON conservative_content_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'conservative reconciliation audit is immutable');
END;

CREATE TRIGGER conservative_content_reconciliations_no_delete
BEFORE DELETE ON conservative_content_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'conservative reconciliation audit is immutable');
END;
