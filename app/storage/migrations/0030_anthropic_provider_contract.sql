-- C5 PROVIDER CONTRACT FREEZE: GLOBAL / STANDARD / RETENTION / REFUSAL.
--
-- Forward-only and offline-tested. This migration does not enable a real call,
-- accept Fable retention on the owner's behalf, or migrate production.

-- 0029 recorded the preflight assumption as GLOBAL_DEFAULT. Rebuild the narrow
-- evidence table so the durable record names the actual request-time authority
-- and the optional response-time values exposed by anthropic-sdk 0.116.0.
DROP TRIGGER model_qualification_results_real_model_needs_controlled_run;
DROP TRIGGER model_capability_declarations_real_model_needs_controlled_run;
DROP TRIGGER model_catalogue_evidence_contract;
DROP TRIGGER model_catalogue_evidence_no_update;
DROP TRIGGER model_catalogue_evidence_no_delete;

CREATE TABLE model_catalogue_evidence_v2 (
    evidence_ref TEXT PRIMARY KEY
        CHECK (length(trim(evidence_ref)) BETWEEN 1 AND 200),
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    technical_model_id TEXT NOT NULL
        CHECK (length(trim(technical_model_id)) BETWEEN 1 AND 200),
    source TEXT NOT NULL CHECK (source='OWNER_VERIFIED_PROVIDER_DOCUMENTATION'),
    verified_by TEXT NOT NULL CHECK (length(trim(verified_by)) BETWEEN 1 AND 200),
    verified_at TEXT NOT NULL CHECK (length(verified_at)>=19),
    inference_geography TEXT NOT NULL CHECK (inference_geography='global'),
    service_tier_request TEXT NOT NULL CHECK (service_tier_request='standard_only'),
    expected_response_inference_geo TEXT NOT NULL
        CHECK (expected_response_inference_geo='global'),
    expected_response_service_tier TEXT NOT NULL
        CHECK (expected_response_service_tier='standard'),
    fast_mode INTEGER NOT NULL CHECK (fast_mode=0),
    prompt_caching INTEGER NOT NULL CHECK (prompt_caching=0),
    server_web_tools INTEGER NOT NULL CHECK (server_web_tools=0),
    batch_api INTEGER NOT NULL CHECK (batch_api=0),
    provider_fallback_api INTEGER NOT NULL CHECK (provider_fallback_api=0),
    notes TEXT,
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    evidence_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(evidence_fingerprint)=64
        AND evidence_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(model_registry_id, source)
);

WITH upgraded_catalogue_evidence AS (
    SELECT evidence_ref,model_registry_id,provider,technical_model_id,source,
           verified_by,verified_at,fast_mode,prompt_caching,server_web_tools,
           batch_api,provider_fallback_api,notes,created_at,
           json_set(
               evidence_json,
               '$.runtime_shape.inference_geography','global',
               '$.runtime_shape.service_tier_request','standard_only',
               '$.runtime_shape.expected_response_inference_geo','global',
               '$.runtime_shape.expected_response_service_tier','standard'
           ) AS upgraded_evidence_json
    FROM model_catalogue_evidence
)
INSERT INTO model_catalogue_evidence_v2 (
    evidence_ref,model_registry_id,provider,technical_model_id,source,
    verified_by,verified_at,inference_geography,service_tier_request,
    expected_response_inference_geo,expected_response_service_tier,fast_mode,
    prompt_caching,server_web_tools,batch_api,provider_fallback_api,notes,
    evidence_json,evidence_fingerprint,created_at
)
SELECT evidence_ref,model_registry_id,provider,technical_model_id,source,
       verified_by,verified_at,'global','standard_only','global','standard',
       fast_mode,prompt_caching,server_web_tools,batch_api,
       provider_fallback_api,notes,upgraded_evidence_json,
       evidence_sha256_hex(upgraded_evidence_json),created_at
FROM upgraded_catalogue_evidence;

DROP TABLE model_catalogue_evidence;
ALTER TABLE model_catalogue_evidence_v2 RENAME TO model_catalogue_evidence;

CREATE TRIGGER model_catalogue_evidence_contract
BEFORE INSERT ON model_catalogue_evidence
WHEN NEW.evidence_fingerprint IS NOT evidence_sha256_hex(NEW.evidence_json)
 OR json_extract(NEW.evidence_json,'$.runtime_shape.inference_geography')
      IS NOT NEW.inference_geography
 OR json_extract(NEW.evidence_json,'$.runtime_shape.service_tier_request')
      IS NOT NEW.service_tier_request
 OR json_extract(NEW.evidence_json,'$.runtime_shape.expected_response_inference_geo')
      IS NOT NEW.expected_response_inference_geo
 OR json_extract(NEW.evidence_json,'$.runtime_shape.expected_response_service_tier')
      IS NOT NEW.expected_response_service_tier
 OR NOT EXISTS (
    SELECT 1 FROM model_registry m
    WHERE m.registry_id=NEW.model_registry_id
      AND m.provider=NEW.provider
      AND m.technical_model_id=NEW.technical_model_id
 )
BEGIN SELECT RAISE(ABORT, 'catalogue evidence must match its registry identity and frozen provider contract'); END;
CREATE TRIGGER model_catalogue_evidence_no_update
BEFORE UPDATE ON model_catalogue_evidence
BEGIN SELECT RAISE(ABORT, 'model_catalogue_evidence is append-only'); END;
CREATE TRIGGER model_catalogue_evidence_no_delete
BEFORE DELETE ON model_catalogue_evidence
BEGIN SELECT RAISE(ABORT, 'model_catalogue_evidence is append-only'); END;

-- Owner acceptance is exact and expiring: provider, Fable model, approval,
-- request/job identity and lifecycle scope. No row is inserted automatically.
CREATE TABLE fable_retention_acceptances (
    acceptance_ref TEXT PRIMARY KEY
        CHECK (length(trim(acceptance_ref)) BETWEEN 1 AND 200),
    scope TEXT NOT NULL CHECK (
        scope IN ('CONTROLLED_LIVE_QUALIFICATION','CONTROLLED_ARTICLE_EXECUTION')
    ),
    approval_ref TEXT NOT NULL CHECK (length(trim(approval_ref)) BETWEEN 1 AND 200),
    request_identity TEXT NOT NULL
        CHECK (length(trim(request_identity)) BETWEEN 1 AND 200),
    provider TEXT NOT NULL CHECK (provider='ANTHROPIC'),
    technical_model_id TEXT NOT NULL CHECK (technical_model_id='claude-fable-5'),
    requirement TEXT NOT NULL CHECK (requirement='30_DAY_RETENTION_ACCEPTED'),
    provider_policy_ref TEXT NOT NULL
        CHECK (length(trim(provider_policy_ref)) BETWEEN 1 AND 500),
    accepted_by TEXT NOT NULL CHECK (length(trim(accepted_by)) BETWEEN 1 AND 200),
    accepted_at TEXT NOT NULL CHECK (length(accepted_at)>=19),
    expires_at TEXT NOT NULL CHECK (length(expires_at)>=19 AND expires_at>accepted_at),
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    evidence_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(evidence_fingerprint)=64
        AND evidence_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(scope,approval_ref,request_identity)
);
CREATE TRIGGER fable_retention_acceptances_contract
BEFORE INSERT ON fable_retention_acceptances
WHEN NEW.evidence_fingerprint IS NOT evidence_sha256_hex(NEW.evidence_json)
 OR json_extract(NEW.evidence_json,'$.acceptance_ref') IS NOT NEW.acceptance_ref
 OR json_extract(NEW.evidence_json,'$.scope') IS NOT NEW.scope
 OR json_extract(NEW.evidence_json,'$.approval_ref') IS NOT NEW.approval_ref
 OR json_extract(NEW.evidence_json,'$.request_identity') IS NOT NEW.request_identity
 OR json_extract(NEW.evidence_json,'$.provider') IS NOT NEW.provider
 OR json_extract(NEW.evidence_json,'$.technical_model_id') IS NOT NEW.technical_model_id
 OR json_extract(NEW.evidence_json,'$.requirement') IS NOT NEW.requirement
 OR json_extract(NEW.evidence_json,'$.provider_policy_ref') IS NOT NEW.provider_policy_ref
 OR json_extract(NEW.evidence_json,'$.accepted_by') IS NOT NEW.accepted_by
 OR json_extract(NEW.evidence_json,'$.accepted_at') IS NOT NEW.accepted_at
 OR json_extract(NEW.evidence_json,'$.expires_at') IS NOT NEW.expires_at
BEGIN SELECT RAISE(ABORT, 'retention acceptance evidence must match its exact contract'); END;
CREATE TRIGGER fable_retention_acceptances_no_update
BEFORE UPDATE ON fable_retention_acceptances
BEGIN SELECT RAISE(ABORT, 'fable_retention_acceptances is append-only'); END;
CREATE TRIGGER fable_retention_acceptances_no_delete
BEFORE DELETE ON fable_retention_acceptances
BEGIN SELECT RAISE(ABORT, 'fable_retention_acceptances is append-only'); END;

-- Recreate the two 0029 evidence floors after the narrow catalogue rebuild.
CREATE TRIGGER model_qualification_results_real_model_needs_controlled_run
BEFORE INSERT ON model_qualification_results
WHEN EXISTS (
    SELECT 1 FROM model_catalogue_evidence e
    WHERE e.model_registry_id=NEW.model_registry_id
)
AND NOT EXISTS (
    SELECT 1
    FROM model_qualification_runs r
    JOIN model_qualification_approvals a ON a.approval_ref=r.approval_ref
    JOIN model_registry m ON m.registry_id=r.model_registry_id
    JOIN model_pricing_profiles pp ON pp.pricing_ref=r.pricing_ref
    WHERE NEW.source='CONTROLLED_LIVE'
      AND r.qualification_ref=NEW.qualification_ref
      AND r.model_registry_id=NEW.model_registry_id
      AND r.outcome=NEW.state
      AND r.outcome IN ('PASS','FAIL')
      AND r.settled_at IS NOT NULL
      AND a.consumed_at IS NOT NULL
      AND a.model_registry_id=r.model_registry_id
      AND a.logical_role=r.logical_role
      AND a.provider=r.provider
      AND a.technical_model_id=r.technical_model_id
      AND a.pricing_ref=r.pricing_ref
      AND m.provider=r.provider
      AND m.technical_model_id=r.technical_model_id
      AND pp.profile_fingerprint=r.pricing_profile_fingerprint
      AND r.input_tokens IS NOT NULL AND r.output_tokens IS NOT NULL
      AND r.input_tokens<=a.max_input_tokens
      AND r.output_tokens<=a.max_output_tokens
)
BEGIN SELECT RAISE(ABORT, 'an owner-verified catalogue model requires its own settled controlled qualification run'); END;

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
)
BEGIN SELECT RAISE(ABORT, 'verified capability for a catalogue model requires its own settled PASS run'); END;
