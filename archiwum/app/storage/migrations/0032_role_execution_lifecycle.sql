-- ROLE PROVIDER EXECUTION LIFECYCLE: add a durable pre-effect state.
--
-- 0029 created role_provider_executions as a terminal-only, append-only record:
-- a row could not exist until the provider had already answered.  That makes it
-- impossible to state durably, BEFORE an external effect, that a paid role call
-- is about to happen -- which is exactly what a restart has to be able to read.
--
-- This migration widens only that lifecycle.  Every authority constraint from
-- 0029 (frozen content_role binding, VERIFIED pricing profile, fallback
-- FORBIDDEN, job/run consistency, returned-model identity) is preserved
-- verbatim.  Nothing else in the schema is touched.
--
-- role_provider_executions has no incoming foreign keys, so the rebuild does not
-- need foreign_keys=OFF and the runner owns the transaction and the ledger row.

PRAGMA legacy_alter_table = ON;

DROP TRIGGER role_provider_executions_contract;
DROP TRIGGER role_provider_executions_no_update;
DROP TRIGGER role_provider_executions_no_delete;

CREATE TABLE role_provider_executions_v2 (
    execution_ref TEXT PRIMARY KEY
        CHECK (length(trim(execution_ref)) BETWEEN 1 AND 200),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    logical_role TEXT NOT NULL CHECK (
        logical_role IN ('ARTICLE_PLAN','ARTICLE_REVIEWER')
    ),
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    binding_intent_id TEXT NOT NULL,
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    returned_model_id TEXT,
    pricing_ref TEXT NOT NULL
        REFERENCES model_pricing_profiles(pricing_ref) ON DELETE RESTRICT,
    pricing_profile_fingerprint TEXT NOT NULL CHECK (
        length(pricing_profile_fingerprint)=64
        AND pricing_profile_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    qualification_ref TEXT NOT NULL,
    capability_ref TEXT NOT NULL,
    reserved_cost_usd TEXT NOT NULL CHECK (
        reserved_cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
        AND reserved_cost_usd NOT GLOB '*[^0-9.]*'
    ),
    -- IN_FLIGHT is the reserved, pre-effect state.  It is not an outcome and it
    -- is never a terminal answer; exactly one settlement may leave it.
    outcome TEXT NOT NULL CHECK (
        outcome IN ('IN_FLIGHT','SUCCESS','FAILURE','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    -- Usage and cost stay NULL while the answer is unknown.  Writing zero there
    -- would assert that a request was free, which nobody established.
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
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    result_fingerprint TEXT UNIQUE CHECK (
        result_fingerprint IS NULL
        OR (length(result_fingerprint)=64
            AND result_fingerprint NOT GLOB '*[^0-9a-f]*')
    ),
    reserved_at TEXT NOT NULL CHECK (length(reserved_at)>=19),
    external_effect_started_at TEXT CHECK (
        external_effect_started_at IS NULL
        OR length(external_effect_started_at)>=19
    ),
    settled_at TEXT CHECK (settled_at IS NULL OR length(settled_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id, logical_role, attempt_no),
    -- A reserved row carries no answer at all.
    CHECK (
      outcome!='IN_FLIGHT'
      OR (returned_model_id IS NULL AND failure_kind IS NULL
          AND input_tokens IS NULL AND output_tokens IS NULL
          AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
          AND web_search_requests IS NULL AND cost_usd IS NULL
          AND result_json IS NULL AND result_fingerprint IS NULL
          AND settled_at IS NULL)
    ),
    -- Known terminal results carry the complete settlement 0029 required.
    -- NEEDS_VERIFICATION may instead carry literal unknown usage/cost after an
    -- external effect whose result could not be recovered.  NULL means unknown;
    -- zero remains a known zero and is never synthesized for this state.
    CHECK (
      outcome='IN_FLIGHT'
      OR (outcome IN ('SUCCESS','FAILURE')
          AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
          AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL
          AND web_search_requests IS NOT NULL AND cost_usd IS NOT NULL
          AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL
          AND settled_at IS NOT NULL)
      OR (outcome='NEEDS_VERIFICATION'
          AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL
          AND settled_at IS NOT NULL
          AND (
            (input_tokens IS NOT NULL AND output_tokens IS NOT NULL
             AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL
             AND web_search_requests IS NOT NULL AND cost_usd IS NOT NULL)
            OR
            (input_tokens IS NULL AND output_tokens IS NULL
             AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
             AND web_search_requests IS NULL AND cost_usd IS NULL)
          ))
    ),
    CHECK (
      (outcome='SUCCESS' AND failure_kind IS NULL)
      OR (outcome IN ('FAILURE','NEEDS_VERIFICATION') AND failure_kind IS NOT NULL)
      OR (outcome='IN_FLIGHT' AND failure_kind IS NULL)
    )
);

INSERT INTO role_provider_executions_v2 (
    execution_ref,job_id,run_id,content_id,logical_role,attempt_no,binding_intent_id,
    model_registry_id,provider,technical_model_id,returned_model_id,pricing_ref,
    pricing_profile_fingerprint,qualification_ref,capability_ref,reserved_cost_usd,outcome,
    failure_kind,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,
    web_search_requests,cost_usd,result_json,result_fingerprint,
    reserved_at,external_effect_started_at,settled_at,created_at
)
SELECT
    execution_ref,job_id,run_id,content_id,logical_role,1,binding_intent_id,
    model_registry_id,provider,technical_model_id,returned_model_id,pricing_ref,
    pricing_profile_fingerprint,qualification_ref,capability_ref,cost_usd,outcome,
    failure_kind,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,
    web_search_requests,cost_usd,result_json,result_fingerprint,
    -- Historical rows were only ever written after the answer existed, so their
    -- reservation, effect and settlement all collapse onto their created_at.
    created_at,created_at,created_at,created_at
FROM role_provider_executions;

DROP TABLE role_provider_executions;
ALTER TABLE role_provider_executions_v2 RENAME TO role_provider_executions;

-- Authority contract, unchanged from 0029 except that a reserved row is not yet
-- required to carry a result.  A row still cannot exist at all without the exact
-- frozen content_role binding, its VERIFIED pricing profile and fallback
-- FORBIDDEN, so reserving is already an authorised act.
CREATE TRIGGER role_provider_executions_contract
BEFORE INSERT ON role_provider_executions
WHEN (NEW.result_json IS NOT NULL
      AND NEW.result_fingerprint IS NOT evidence_sha256_hex(NEW.result_json))
 OR NOT EXISTS (
    SELECT 1
    FROM model_intent_bindings b
    JOIN model_pricing_profiles pp ON pp.pricing_ref=b.pricing_ref
    JOIN content_items c ON c.id=NEW.content_id
    WHERE b.intent_kind='content_role'
      AND b.intent_id=NEW.binding_intent_id
      AND b.intent_id=NEW.job_id || ':' || NEW.logical_role
      AND b.role=NEW.logical_role
      AND b.model_registry_id=NEW.model_registry_id
      AND b.provider=NEW.provider
      AND b.technical_model_id=NEW.technical_model_id
      AND b.pricing_ref=NEW.pricing_ref
      AND b.qualification_ref=NEW.qualification_ref
      AND b.capability_ref=NEW.capability_ref
      AND b.fallback_policy='FORBIDDEN'
      AND pp.verification_state='VERIFIED'
      AND pp.profile_fingerprint=NEW.pricing_profile_fingerprint
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
 )
 -- Same rule as the writer: another model's answer is never a normal success.
 OR (NEW.returned_model_id IS NOT NULL
     AND NEW.returned_model_id!=NEW.technical_model_id
     AND NEW.outcome='SUCCESS')
BEGIN SELECT RAISE(ABORT, 'role provider execution must match its frozen role binding'); END;

-- Exactly two mutations are legal on a reserved row, and nothing else ever is:
--
--   1. the pre-effect stamp   IN_FLIGHT -> IN_FLIGHT, external_effect_started_at
--      written once, still carrying no answer;
--   2. the settlement         IN_FLIGHT -> SUCCESS | FAILURE | NEEDS_VERIFICATION,
--      complete and hashed, once.
--
-- Identity, authority and reservation columns are immutable in both, a terminal
-- row can never be reopened or re-terminalized, and a settled SUCCESS must still
-- name the model that was actually authorised.
CREATE TRIGGER role_provider_executions_settle
BEFORE UPDATE ON role_provider_executions
WHEN NEW.execution_ref!=OLD.execution_ref
 OR NEW.job_id!=OLD.job_id
 OR NEW.run_id!=OLD.run_id
 OR NEW.content_id!=OLD.content_id
 OR NEW.logical_role!=OLD.logical_role
 OR NEW.attempt_no!=OLD.attempt_no
 OR NEW.binding_intent_id!=OLD.binding_intent_id
 OR NEW.model_registry_id!=OLD.model_registry_id
 OR NEW.provider!=OLD.provider
 OR NEW.technical_model_id!=OLD.technical_model_id
 OR NEW.pricing_ref!=OLD.pricing_ref
 OR NEW.pricing_profile_fingerprint!=OLD.pricing_profile_fingerprint
 OR NEW.qualification_ref!=OLD.qualification_ref
 OR NEW.capability_ref!=OLD.capability_ref
 OR NEW.reserved_cost_usd!=OLD.reserved_cost_usd
 OR NEW.reserved_at!=OLD.reserved_at
 OR NEW.created_at!=OLD.created_at
 OR NOT (
      (   -- 1. pre-effect stamp
          OLD.outcome='IN_FLIGHT' AND NEW.outcome='IN_FLIGHT'
          AND OLD.external_effect_started_at IS NULL
          AND NEW.external_effect_started_at IS NOT NULL
          AND NEW.settled_at IS NULL
          AND NEW.result_json IS NULL
          AND NEW.result_fingerprint IS NULL
          AND NEW.failure_kind IS NULL
          AND NEW.returned_model_id IS NULL
          AND NEW.cost_usd IS NULL
      )
      OR
      (   -- 2. settlement
          OLD.outcome='IN_FLIGHT'
          AND NEW.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
          AND NEW.external_effect_started_at IS OLD.external_effect_started_at
          AND NEW.settled_at IS NOT NULL
          AND NEW.result_json IS NOT NULL
          AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
          AND NOT (NEW.returned_model_id IS NOT NULL
                   AND NEW.returned_model_id!=NEW.technical_model_id
                   AND NEW.outcome='SUCCESS')
      )
 )
BEGIN SELECT RAISE(ABORT, 'role provider execution admits one effect stamp and one settlement'); END;

CREATE TRIGGER role_provider_executions_no_delete
BEFORE DELETE ON role_provider_executions
BEGIN SELECT RAISE(ABORT, 'role_provider_executions is append-only'); END;

PRAGMA legacy_alter_table = OFF;
