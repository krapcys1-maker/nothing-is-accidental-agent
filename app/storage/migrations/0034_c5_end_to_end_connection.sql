-- C5 end-to-end connection substrate. Applied to new/temp databases only in
-- this wave; production remains on 0033 until separately authorised.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS model_role_policies_no_delete;
ALTER TABLE model_role_policies RENAME TO model_role_policies_0033_old;

CREATE TABLE model_role_policies (
    role TEXT PRIMARY KEY CHECK (role IN (
        'TOPIC_GENERATION','ARTICLE_RESEARCH','ARTICLE_PLAN','ARTICLE_WRITER',
        'ARTICLE_REVIEWER','NOTE_WRITER','COMMENT_WRITER'
    )),
    allowed_family TEXT NOT NULL CHECK (allowed_family IN ('SONNET','OPUS','FABLE')),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) BETWEEN 1 AND 100),
    capability_verification_state TEXT NOT NULL CHECK (capability_verification_state IN ('UNVERIFIED','VERIFIED')),
    require_structured_response INTEGER CHECK (require_structured_response IN (0,1)),
    min_context_tokens INTEGER,
    min_output_tokens INTEGER,
    pricing_verification_state TEXT NOT NULL CHECK (pricing_verification_state IN ('UNVERIFIED','VERIFIED')),
    max_input_per_mtok TEXT,
    max_output_per_mtok TEXT,
    max_cache_read_per_mtok TEXT,
    max_cache_write_per_mtok TEXT,
    max_web_search_per_1k TEXT,
    qualification_required INTEGER NOT NULL CHECK (qualification_required=1),
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    policy_fingerprint TEXT NOT NULL CHECK (length(policy_fingerprint)=64),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    updated_at TEXT NOT NULL CHECK (length(updated_at)>=19),
    allowed_provider TEXT,
    allowed_technical_model_id TEXT,
    require_source_discovery INTEGER CHECK (require_source_discovery IN (0,1)),
    CHECK (
      (role IN ('TOPIC_GENERATION','ARTICLE_RESEARCH','ARTICLE_PLAN','ARTICLE_WRITER','ARTICLE_REVIEWER')
       AND allowed_family='OPUS')
      OR (role IN ('NOTE_WRITER','COMMENT_WRITER') AND allowed_family='SONNET')
    ),
    CHECK (
      (capability_verification_state='UNVERIFIED' AND require_structured_response IS NULL
       AND min_context_tokens IS NULL AND min_output_tokens IS NULL)
      OR (capability_verification_state='VERIFIED' AND require_structured_response IS NOT NULL
       AND min_context_tokens>0 AND min_output_tokens>0)
    ),
    CHECK (
      (pricing_verification_state='UNVERIFIED' AND max_input_per_mtok IS NULL
       AND max_output_per_mtok IS NULL AND max_cache_read_per_mtok IS NULL
       AND max_cache_write_per_mtok IS NULL AND max_web_search_per_1k IS NULL)
      OR (pricing_verification_state='VERIFIED' AND length(max_input_per_mtok)>0
       AND length(max_output_per_mtok)>0 AND length(max_cache_read_per_mtok)>0
       AND length(max_cache_write_per_mtok)>0 AND length(max_web_search_per_1k)>0)
    ),
    CHECK ((allowed_provider IS NULL AND allowed_technical_model_id IS NULL)
      OR (length(trim(allowed_provider))>0 AND length(trim(allowed_technical_model_id))>0))
);

INSERT INTO model_role_policies (
    role,allowed_family,policy_version,capability_verification_state,
    require_structured_response,min_context_tokens,min_output_tokens,
    pricing_verification_state,max_input_per_mtok,max_output_per_mtok,
    max_cache_read_per_mtok,max_cache_write_per_mtok,max_web_search_per_1k,
    qualification_required,fallback_policy,policy_fingerprint,created_at,updated_at,
    allowed_provider,allowed_technical_model_id,require_source_discovery
)
SELECT role,CASE WHEN role IN ('TOPIC_GENERATION','ARTICLE_WRITER') THEN 'OPUS'
                 ELSE allowed_family END,
    policy_version,capability_verification_state,require_structured_response,
    min_context_tokens,min_output_tokens,pricing_verification_state,
    max_input_per_mtok,max_output_per_mtok,max_cache_read_per_mtok,
    max_cache_write_per_mtok,max_web_search_per_1k,qualification_required,
    fallback_policy,
    CASE WHEN role='TOPIC_GENERATION'
         THEN 'd81a5fe6a8c737632cce9606889b7c52d0a929e79940b0dc243dc9e1edc6332b'
         ELSE policy_fingerprint END,
    created_at,updated_at,NULL,NULL,NULL
FROM model_role_policies_0033_old;

DROP TABLE model_role_policies_0033_old;
CREATE TRIGGER model_role_policies_no_delete
BEFORE DELETE ON model_role_policies
BEGIN SELECT RAISE(ABORT, 'model_role_policies cannot be deleted'); END;

ALTER TABLE model_capability_declarations
ADD COLUMN source_discovery INTEGER CHECK (source_discovery IN (0,1));

ALTER TABLE research_source_candidates ADD COLUMN canonical_source_identity TEXT;
ALTER TABLE research_source_candidates ADD COLUMN discovery_result_identity TEXT;
ALTER TABLE research_source_candidates ADD COLUMN discovery_port TEXT;
ALTER TABLE research_source_candidates
ADD COLUMN discovery_job_id TEXT REFERENCES jobs(id) ON DELETE RESTRICT;

CREATE TABLE source_discovery_approvals (
    approval_ref TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    action_type TEXT NOT NULL CHECK (action_type='ARTICLE_RESEARCH_SOURCE_DISCOVERY'),
    model_registry_id TEXT NOT NULL REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    intent_fingerprint TEXT NOT NULL,
    cap_usd TEXT NOT NULL,
    max_retries INTEGER NOT NULL CHECK (max_retries=0),
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK (expires_at>approved_at),
    consumed_at TEXT,
    CHECK (provider='ANTHROPIC' AND technical_model_id='claude-opus-5'),
    CHECK (length(intent_fingerprint)=64)
);

CREATE TRIGGER source_discovery_approvals_no_delete
BEFORE DELETE ON source_discovery_approvals
BEGIN SELECT RAISE(ABORT, 'source_discovery_approvals is append-only'); END;

CREATE TRIGGER source_discovery_approvals_consume_once
BEFORE UPDATE ON source_discovery_approvals
WHEN OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL
  OR NEW.approval_ref IS NOT OLD.approval_ref
  OR NEW.job_id IS NOT OLD.job_id OR NEW.request_id IS NOT OLD.request_id
  OR NEW.account_id IS NOT OLD.account_id OR NEW.topic_id IS NOT OLD.topic_id
  OR NEW.action_type IS NOT OLD.action_type
  OR NEW.model_registry_id IS NOT OLD.model_registry_id
  OR NEW.provider IS NOT OLD.provider
  OR NEW.technical_model_id IS NOT OLD.technical_model_id
  OR NEW.intent_fingerprint IS NOT OLD.intent_fingerprint
  OR NEW.cap_usd IS NOT OLD.cap_usd
  OR NEW.max_retries IS NOT OLD.max_retries
  OR NEW.fallback_policy IS NOT OLD.fallback_policy
  OR NEW.approved_by IS NOT OLD.approved_by
  OR NEW.approved_at IS NOT OLD.approved_at OR NEW.expires_at IS NOT OLD.expires_at
BEGIN SELECT RAISE(ABORT, 'source_discovery approval may only be consumed once'); END;

CREATE TABLE source_candidate_fetch_approvals (
    approval_ref TEXT PRIMARY KEY,
    candidate_id INTEGER NOT NULL UNIQUE
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    source_identity TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    action_type TEXT NOT NULL CHECK (action_type='CONTROLLED_FETCH_SOURCE_CANDIDATE'),
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    expires_at TEXT NOT NULL CHECK (expires_at>approved_at),
    fetch_job_id TEXT UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE TRIGGER source_candidate_fetch_approvals_no_delete
BEFORE DELETE ON source_candidate_fetch_approvals
BEGIN SELECT RAISE(ABORT, 'source_candidate_fetch_approvals is append-only'); END;

CREATE TRIGGER source_candidate_fetch_approvals_no_update
BEFORE UPDATE ON source_candidate_fetch_approvals
BEGIN SELECT RAISE(ABORT, 'source_candidate_fetch_approvals is immutable'); END;

CREATE UNIQUE INDEX ux_source_candidates_canonical_identity
ON research_source_candidates(research_run_id, canonical_source_identity)
WHERE canonical_source_identity IS NOT NULL;

CREATE TRIGGER research_source_candidates_structured_provenance_insert
BEFORE INSERT ON research_source_candidates
WHEN NEW.canonical_source_identity IS NOT NULL AND (
    NEW.discovery_result_identity IS NULL OR NEW.discovery_port IS NULL
    OR NEW.discovery_job_id IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM jobs j JOIN research_runs rr ON rr.id=NEW.research_run_id
        WHERE j.id=NEW.discovery_job_id
          AND j.account_id=rr.account_id AND j.topic_id=rr.topic_id
          AND json_extract(j.payload_json,'$.execution')='article_research_source_discovery_v1'
    )
)
BEGIN SELECT RAISE(ABORT, 'source candidate requires structured discovery provenance'); END;

CREATE TRIGGER research_source_candidates_provenance_immutable
BEFORE UPDATE OF url,canonical_source_identity,discovery_result_identity,
    discovery_port,discovery_job_id,research_run_id ON research_source_candidates
WHEN NEW.url IS NOT OLD.url
 OR NEW.canonical_source_identity IS NOT OLD.canonical_source_identity
 OR NEW.discovery_result_identity IS NOT OLD.discovery_result_identity
 OR NEW.discovery_port IS NOT OLD.discovery_port
 OR NEW.discovery_job_id IS NOT OLD.discovery_job_id
 OR NEW.research_run_id IS NOT OLD.research_run_id
BEGIN SELECT RAISE(ABORT, 'source candidate provenance is immutable'); END;

CREATE TRIGGER source_candidate_fetch_approvals_contract
BEFORE INSERT ON source_candidate_fetch_approvals
WHEN NOT EXISTS (
    SELECT 1
    FROM research_source_candidates c
    JOIN research_runs rr ON rr.id=c.research_run_id
    JOIN jobs j ON j.id=NEW.fetch_job_id
    WHERE c.id=NEW.candidate_id
      AND c.canonical_source_identity=NEW.source_identity
      AND c.url=NEW.requested_url
      AND c.discovery_result_identity IS NOT NULL
      AND c.discovery_job_id IS NOT NULL
      AND rr.account_id=NEW.account_id AND rr.topic_id=NEW.topic_id
      AND j.account_id=NEW.account_id AND j.topic_id=NEW.topic_id
      AND json_extract(j.payload_json,'$.execution')='controlled_fetch_v1'
      AND json_extract(j.payload_json,'$.execution_intent.source_identity')=NEW.source_identity
      AND json_extract(j.payload_json,'$.execution_intent.requested_url')=NEW.requested_url
)
BEGIN SELECT RAISE(ABORT, 'fetch approval must bind one structured candidate and job'); END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0034_c5_end_to_end_connection', datetime('now'));
COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
