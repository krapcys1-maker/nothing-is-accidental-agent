-- Permit a controlled qualification PASS to carry paid web-search usage only
-- when that exact capability was present in the immutable owner approval.
-- Historical writer qualifications remain byte-logically no-search.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS model_qualification_runs_reserve_contract;
DROP TRIGGER IF EXISTS model_qualification_runs_settle_once;
DROP TRIGGER IF EXISTS model_qualification_runs_settle_envelope;
DROP TRIGGER IF EXISTS model_qualification_runs_no_delete;
DROP TRIGGER IF EXISTS model_capability_declarations_real_model_needs_controlled_run;

ALTER TABLE model_qualification_runs RENAME TO model_qualification_runs_0034_old;

CREATE TABLE model_qualification_runs (
    request_id TEXT PRIMARY KEY,
    approval_ref TEXT NOT NULL UNIQUE
        REFERENCES model_qualification_approvals(approval_ref) ON DELETE RESTRICT,
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    logical_role TEXT NOT NULL REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    pricing_ref TEXT NOT NULL
        REFERENCES model_pricing_profiles(pricing_ref) ON DELETE RESTRICT,
    pricing_profile_fingerprint TEXT NOT NULL CHECK (
        length(pricing_profile_fingerprint)=64
        AND pricing_profile_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    require_source_discovery INTEGER NOT NULL CHECK (require_source_discovery IN (0,1)),
    returned_model_id TEXT,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('IN_FLIGHT','PASS','FAIL','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens>=0),
    output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens>=0),
    cache_read_tokens INTEGER CHECK (
        cache_read_tokens IS NULL OR cache_read_tokens>=0
    ),
    cache_write_tokens INTEGER CHECK (
        cache_write_tokens IS NULL OR cache_write_tokens>=0
    ),
    web_search_requests INTEGER CHECK (
        web_search_requests IS NULL OR web_search_requests>=0
    ),
    cost_usd TEXT CHECK (
        cost_usd IS NULL
        OR (cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
            AND cost_usd NOT GLOB '*[^0-9.]*')
    ),
    qualification_ref TEXT,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(result_fingerprint)=64
        AND result_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    external_effect_started_at TEXT NOT NULL CHECK (
        length(external_effect_started_at)>=19
    ),
    reserved_at TEXT NOT NULL CHECK (length(reserved_at)>=19),
    settled_at TEXT CHECK (settled_at IS NULL OR length(settled_at)>=19),
    executed_at TEXT NOT NULL CHECK (length(executed_at)>=19),
    CHECK (
      (outcome='IN_FLIGHT' AND failure_kind IS NULL
       AND qualification_ref IS NULL AND settled_at IS NULL
       AND input_tokens IS NULL AND output_tokens IS NULL
       AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
       AND web_search_requests IS NULL AND cost_usd IS NULL
       AND returned_model_id IS NULL)
      OR
      (outcome='PASS' AND failure_kind IS NULL
       AND qualification_ref IS NOT NULL AND settled_at IS NOT NULL
       AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
       AND cost_usd IS NOT NULL)
      OR
      (outcome='FAIL'
       AND qualification_ref IS NOT NULL AND settled_at IS NOT NULL
       AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
       AND cost_usd IS NOT NULL)
      OR
      (outcome='NEEDS_VERIFICATION' AND failure_kind IS NOT NULL
       AND qualification_ref IS NULL AND settled_at IS NOT NULL)
    ),
    CHECK (
      outcome!='PASS'
      OR (cache_read_tokens=0 AND cache_write_tokens=0 AND (
          (require_source_discovery=0 AND web_search_requests=0)
          OR (require_source_discovery=1 AND web_search_requests>=1)
      ))
    )
);

INSERT INTO model_qualification_runs (
    request_id,approval_ref,model_registry_id,logical_role,provider,
    technical_model_id,pricing_ref,pricing_profile_fingerprint,
    require_source_discovery,returned_model_id,outcome,failure_kind,
    input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,
    web_search_requests,cost_usd,qualification_ref,result_json,
    result_fingerprint,external_effect_started_at,reserved_at,settled_at,executed_at
)
SELECT r.request_id,r.approval_ref,r.model_registry_id,r.logical_role,r.provider,
    r.technical_model_id,r.pricing_ref,r.pricing_profile_fingerprint,
    CASE WHEN json_extract(a.approval_json,'$.require_source_discovery')=1
         THEN 1 ELSE 0 END,
    r.returned_model_id,r.outcome,r.failure_kind,r.input_tokens,r.output_tokens,
    r.cache_read_tokens,r.cache_write_tokens,r.web_search_requests,r.cost_usd,
    r.qualification_ref,r.result_json,r.result_fingerprint,
    r.external_effect_started_at,r.reserved_at,r.settled_at,r.executed_at
FROM model_qualification_runs_0034_old r
JOIN model_qualification_approvals a ON a.approval_ref=r.approval_ref;

DROP TABLE model_qualification_runs_0034_old;

CREATE TRIGGER model_qualification_runs_reserve_contract
BEFORE INSERT ON model_qualification_runs
WHEN NEW.outcome!='IN_FLIGHT'
 OR NEW.result_fingerprint IS NOT evidence_sha256_hex(NEW.result_json)
 OR NOT EXISTS (
    SELECT 1
    FROM model_qualification_approvals a
    JOIN model_pricing_profiles pp ON pp.pricing_ref=a.pricing_ref
    WHERE a.approval_ref=NEW.approval_ref
      AND a.request_id=NEW.request_id
      AND a.consumed_at IS NOT NULL
      AND a.logical_role=NEW.logical_role
      AND a.model_registry_id=NEW.model_registry_id
      AND a.provider=NEW.provider
      AND a.technical_model_id=NEW.technical_model_id
      AND a.pricing_ref=NEW.pricing_ref
      AND pp.profile_fingerprint=NEW.pricing_profile_fingerprint
      AND NEW.require_source_discovery=
          CASE WHEN json_extract(a.approval_json,'$.require_source_discovery')=1
               THEN 1 ELSE 0 END
 )
BEGIN SELECT RAISE(ABORT, 'a qualification run is reserved IN_FLIGHT against its own consumed approval'); END;

CREATE TRIGGER model_qualification_runs_settle_once
BEFORE UPDATE ON model_qualification_runs
WHEN NOT (
    OLD.outcome='IN_FLIGHT'
    AND NEW.outcome IN ('PASS','FAIL','NEEDS_VERIFICATION')
    AND NEW.request_id=OLD.request_id AND NEW.approval_ref=OLD.approval_ref
    AND NEW.model_registry_id=OLD.model_registry_id
    AND NEW.logical_role=OLD.logical_role AND NEW.provider=OLD.provider
    AND NEW.technical_model_id=OLD.technical_model_id
    AND NEW.pricing_ref=OLD.pricing_ref
    AND NEW.pricing_profile_fingerprint=OLD.pricing_profile_fingerprint
    AND NEW.require_source_discovery=OLD.require_source_discovery
    AND NEW.external_effect_started_at=OLD.external_effect_started_at
    AND NEW.reserved_at=OLD.reserved_at
    AND NEW.settled_at IS NOT NULL
    AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
)
BEGIN SELECT RAISE(ABORT, 'a qualification run settles exactly once from IN_FLIGHT'); END;

CREATE TRIGGER model_qualification_runs_settle_envelope
BEFORE UPDATE ON model_qualification_runs
WHEN NEW.outcome IN ('PASS','FAIL')
 AND EXISTS (
    SELECT 1 FROM model_qualification_approvals a
    WHERE a.approval_ref=NEW.approval_ref
      AND (NEW.input_tokens>a.max_input_tokens
           OR NEW.output_tokens>a.max_output_tokens)
 )
BEGIN SELECT RAISE(ABORT, 'a qualifying run cannot exceed the approved token envelope'); END;

CREATE TRIGGER model_qualification_runs_no_delete
BEFORE DELETE ON model_qualification_runs
BEGIN SELECT RAISE(ABORT, 'model_qualification_runs is append-only'); END;

CREATE TRIGGER model_capability_declarations_real_model_needs_controlled_run
BEFORE INSERT ON model_capability_declarations
WHEN NEW.verification_state='VERIFIED'
AND EXISTS (
    SELECT 1 FROM model_catalogue_evidence e
    WHERE e.model_registry_id=NEW.model_registry_id
)
AND NOT EXISTS (
    SELECT 1
    FROM model_qualification_runs r
    JOIN model_qualification_approvals a ON a.approval_ref=r.approval_ref
    WHERE r.model_registry_id=NEW.model_registry_id
      AND r.outcome='PASS'
      AND r.settled_at IS NOT NULL
      AND a.consumed_at IS NOT NULL
      AND r.input_tokens<=a.max_input_tokens
      AND r.output_tokens<=a.max_output_tokens
      AND NEW.max_output_tokens<=a.max_output_tokens
      AND NEW.max_context_tokens<=(a.max_input_tokens + a.max_output_tokens)
      AND (
          (NEW.source_discovery IS NULL AND r.require_source_discovery=0)
          OR (
              NEW.source_discovery=1 AND r.require_source_discovery=1
              AND r.web_search_requests>=1
              AND json_extract(r.result_json,'$.source_discovery_ok')=1
          )
      )
)
BEGIN SELECT RAISE(ABORT, 'verified capability for a catalogue model requires its own settled PASS run'); END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0035_article_research_qualification', datetime('now'));
COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
