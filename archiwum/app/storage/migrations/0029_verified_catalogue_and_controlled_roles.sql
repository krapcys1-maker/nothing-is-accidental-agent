-- PRE-C5 VERIFIED ANTHROPIC CATALOGUE & CONTROLLED ARTICLE LIVE ROOT.
--
-- Additive, forward-only.  Nothing here enables a real call: it makes the
-- remaining C5 preconditions representable so they can be proved offline.
--
-- Five separate things are admitted, each fail-closed:
--
--  (1) Pricing validity.  A promotional rate is a real price for a real
--      period.  0027 had no way to say that, so an expired promotion could
--      have priced new intents forever.  Two additive columns plus one trigger
--      make a binding refuse a profile that is not effective when it is frozen.
--
--  (2) Owner-verified catalogue evidence.  "The provider publishes this model
--      ID at this price" is evidence about a catalogue.  It is NOT evidence
--      that the model passes this project's regression suite, so it is stored
--      separately from qualification and can never imply it.
--
--  (3) Controlled qualification bootstrap.  A real model reaches PASS only
--      through one separately approved, separately audited request. This is
--      deliberately NOT a content attempt and does not reuse the content
--      lifecycle; it is the one bootstrap that may precede qualification.
--
--  (4) One-time L1 content approval.  A paid CONTENT execution needs a durable
--      single-use approval bound to the exact job, role, registry entry,
--      technical model, pricing ref, token ceiling, cost cap and expiry.
--      There is no global "live enabled" flag anywhere in this contract.
--
--  (5) Role provider executions.  ARTICLE_PLAN and ARTICLE_REVIEWER get one
--      shared durable provenance/usage/cost record keyed by logical role,
--      rather than two parallel subsystems.
--
-- Production is not migrated by this file and remains on 0020.

-- ---------------------------------------------------------------------------
-- (1) Pricing validity window
-- ---------------------------------------------------------------------------

ALTER TABLE model_pricing_profiles ADD COLUMN effective_from TEXT;
ALTER TABLE model_pricing_profiles ADD COLUMN effective_until TEXT;

-- A binding may only freeze a price list that is effective at the moment it is
-- bound.  An expired promotional profile therefore blocks NEW intents while
-- leaving every already-frozen intent byte-identical.
CREATE TRIGGER model_intent_bindings_pricing_validity
BEFORE INSERT ON model_intent_bindings
WHEN EXISTS (
    SELECT 1 FROM model_pricing_profiles pp
    WHERE pp.pricing_ref=NEW.pricing_ref
      AND (
        (pp.effective_from IS NOT NULL AND NEW.bound_at < pp.effective_from)
        OR
        (pp.effective_until IS NOT NULL AND NEW.bound_at > pp.effective_until)
      )
)
BEGIN SELECT RAISE(ABORT, 'pricing profile is not effective at binding time'); END;

-- ---------------------------------------------------------------------------
-- (2) Owner-verified catalogue evidence
-- ---------------------------------------------------------------------------

CREATE TABLE model_catalogue_evidence (
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
    -- The exact runtime shape this evidence was verified against. C5 runs with
    -- every one of these disabled, so a later change of any of them invalidates
    -- the evidence rather than silently inheriting it.
    inference_geography TEXT NOT NULL CHECK (inference_geography='GLOBAL_DEFAULT'),
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
CREATE TRIGGER model_catalogue_evidence_contract
BEFORE INSERT ON model_catalogue_evidence
WHEN NEW.evidence_fingerprint IS NOT evidence_sha256_hex(NEW.evidence_json)
 OR NOT EXISTS (
    SELECT 1 FROM model_registry m
    WHERE m.registry_id=NEW.model_registry_id
      AND m.provider=NEW.provider
      AND m.technical_model_id=NEW.technical_model_id
 )
BEGIN SELECT RAISE(ABORT, 'catalogue evidence must match its registry identity'); END;
CREATE TRIGGER model_catalogue_evidence_no_update
BEFORE UPDATE ON model_catalogue_evidence
BEGIN SELECT RAISE(ABORT, 'model_catalogue_evidence is append-only'); END;
CREATE TRIGGER model_catalogue_evidence_no_delete
BEFORE DELETE ON model_catalogue_evidence
BEGIN SELECT RAISE(ABORT, 'model_catalogue_evidence is append-only'); END;

-- ---------------------------------------------------------------------------
-- (3) Controlled qualification bootstrap
-- ---------------------------------------------------------------------------

CREATE TABLE model_qualification_approvals (
    approval_ref TEXT PRIMARY KEY
        CHECK (length(trim(approval_ref)) BETWEEN 1 AND 200),
    request_id TEXT NOT NULL UNIQUE
        CHECK (length(trim(request_id)) BETWEEN 1 AND 200),
    logical_role TEXT NOT NULL REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    pricing_ref TEXT NOT NULL
        REFERENCES model_pricing_profiles(pricing_ref) ON DELETE RESTRICT,
    purpose TEXT NOT NULL CHECK (purpose='CONTROLLED_LIVE_QUALIFICATION'),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 8192),
    max_input_tokens INTEGER NOT NULL CHECK (max_input_tokens BETWEEN 1 AND 200000),
    cap_usd TEXT NOT NULL CHECK (
        length(cap_usd)>0 AND cap_usd NOT GLOB '*[^0-9.]*'
    ),
    max_retries INTEGER NOT NULL CHECK (max_retries=0),
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    approved_by TEXT NOT NULL CHECK (length(trim(approved_by)) BETWEEN 1 AND 200),
    approved_at TEXT NOT NULL CHECK (length(approved_at)>=19),
    expires_at TEXT NOT NULL CHECK (length(expires_at)>=19 AND expires_at>approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at)>=19),
    approval_json TEXT NOT NULL CHECK (json_valid(approval_json)),
    approval_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(approval_fingerprint)=64
        AND approval_fingerprint NOT GLOB '*[^0-9a-f]*'
    )
);
CREATE TRIGGER model_qualification_approvals_contract
BEFORE INSERT ON model_qualification_approvals
WHEN NEW.approval_fingerprint IS NOT evidence_sha256_hex(NEW.approval_json)
 OR NEW.consumed_at IS NOT NULL
 OR NOT EXISTS (
    SELECT 1
    FROM model_registry m
    JOIN model_role_policies p ON p.role=NEW.logical_role
    JOIN model_pricing_profiles pp ON pp.pricing_ref=NEW.pricing_ref
    WHERE m.registry_id=NEW.model_registry_id
      AND m.provider=NEW.provider
      AND m.technical_model_id=NEW.technical_model_id
      AND m.family=p.allowed_family
      AND m.pricing_ref=NEW.pricing_ref
      AND pp.verification_state='VERIFIED'
      AND pp.provider=m.provider
      AND pp.technical_model_id=m.technical_model_id
      AND (pp.effective_from IS NULL OR NEW.approved_at>=pp.effective_from)
      AND (pp.effective_until IS NULL OR NEW.approved_at<=pp.effective_until)
      AND p.fallback_policy='FORBIDDEN'
 )
BEGIN SELECT RAISE(ABORT, 'qualification approval must bind one exact registry entry and effective price'); END;
CREATE TRIGGER model_qualification_approvals_consume_once
BEFORE UPDATE ON model_qualification_approvals
WHEN NOT (
    OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL
    AND NEW.approval_ref=OLD.approval_ref AND NEW.request_id=OLD.request_id
    AND NEW.logical_role=OLD.logical_role
    AND NEW.model_registry_id=OLD.model_registry_id
    AND NEW.provider=OLD.provider
    AND NEW.technical_model_id=OLD.technical_model_id
    AND NEW.pricing_ref=OLD.pricing_ref AND NEW.purpose=OLD.purpose
    AND NEW.max_output_tokens=OLD.max_output_tokens
    AND NEW.max_input_tokens=OLD.max_input_tokens
    AND NEW.cap_usd=OLD.cap_usd AND NEW.max_retries=OLD.max_retries
    AND NEW.fallback_policy=OLD.fallback_policy
    AND NEW.approved_by=OLD.approved_by AND NEW.approved_at=OLD.approved_at
    AND NEW.expires_at=OLD.expires_at
    AND NEW.approval_json=OLD.approval_json
    AND NEW.approval_fingerprint=OLD.approval_fingerprint
)
BEGIN SELECT RAISE(ABORT, 'qualification approval permits exactly one immutable consumption'); END;
CREATE TRIGGER model_qualification_approvals_no_delete
BEFORE DELETE ON model_qualification_approvals
BEGIN SELECT RAISE(ABORT, 'model_qualification_approvals is append-only'); END;

-- One durable bootstrap execution: its own usage, its own Decimal cost, its own
-- outcome.  Deliberately separate from content attempts and from model_usage.
-- One durable bootstrap execution: reserved BEFORE the provider boundary, then
-- settled exactly once.  The row must already exist when the caller runs, so a
-- timeout, an ambiguous exception or a crash leaves durable evidence that the
-- request may have happened instead of leaving a consumed approval with no
-- record at all.
--
-- Usage and cost are NULLABLE on purpose.  A run whose usage never came back is
-- not a run that cost nothing; writing 0 there would be a fabricated fact.
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
    returned_model_id TEXT,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('IN_FLIGHT','PASS','FAIL','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    -- Recordable when non-zero: a provider reporting usage for a feature the
    -- request never enabled is exactly the anomaly this row exists to preserve.
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
    -- The durable proof that a provider request may already have been issued.
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
      -- A PASS is clean by definition; a FAIL records why it failed. Both are
      -- settled results, so both must carry the usage they were priced from.
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
    -- A PASS may never carry usage for a feature C5 disables, and never usage
    -- outside the ceilings a human approved.
    CHECK (
      outcome!='PASS'
      OR (cache_read_tokens=0 AND cache_write_tokens=0
          AND web_search_requests=0)
    )
);
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
 )
BEGIN SELECT RAISE(ABORT, 'a qualification run is reserved IN_FLIGHT against its own consumed approval'); END;

-- The only legal mutation in a run's life: exactly one settlement of the
-- in-flight row, with every identity column byte-identical.
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
    AND NEW.external_effect_started_at=OLD.external_effect_started_at
    AND NEW.reserved_at=OLD.reserved_at
    AND NEW.settled_at IS NOT NULL
    AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
)
BEGIN SELECT RAISE(ABORT, 'a qualification run settles exactly once from IN_FLIGHT'); END;

-- A settled run may never claim usage outside the ceilings a human approved.
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

-- 0027 admitted only LOCAL_FIXTURE evidence, which was correct while no
-- controlled run could exist.  A controlled qualification produces genuinely
-- different evidence and must not be recorded as a local fixture, so the source
-- list is widened by rebuild.  Every existing row is preserved verbatim.
CREATE TABLE model_qualification_results_v2 (
    qualification_ref TEXT PRIMARY KEY
        CHECK (length(trim(qualification_ref)) BETWEEN 1 AND 200),
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('PASS','FAIL')),
    suite_version TEXT NOT NULL CHECK (length(trim(suite_version)) BETWEEN 1 AND 100),
    fixture_set_ref TEXT NOT NULL CHECK (length(trim(fixture_set_ref)) BETWEEN 1 AND 200),
    source TEXT NOT NULL CHECK (source IN ('LOCAL_FIXTURE','CONTROLLED_LIVE')),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(result_fingerprint)=64
        AND result_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    evaluated_at TEXT NOT NULL CHECK (length(evaluated_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);
INSERT INTO model_qualification_results_v2 (
    qualification_ref,model_registry_id,state,suite_version,fixture_set_ref,
    source,result_json,result_fingerprint,evaluated_at,created_at
)
SELECT qualification_ref,model_registry_id,state,suite_version,fixture_set_ref,
       source,result_json,result_fingerprint,evaluated_at,created_at
FROM model_qualification_results;

-- SQLite refuses to drop a table any trigger body still reads, so every
-- dependent trigger is dropped first and recreated below with semantically
-- identical predicates and behaviour. Three are byte-identical to the
-- 0027/0028 originals; the fourth differs only in dropped SQL comments. Only
-- the source CHECK of the rebuilt table changed.
DROP TRIGGER model_registry_current_evidence_contract;
DROP TRIGGER model_role_activations_contract_insert;
DROP TRIGGER model_role_activations_contract_update;
DROP TRIGGER content_writer_intents_controlled_provider_binding;
DROP TRIGGER model_qualification_results_no_update;
DROP TRIGGER model_qualification_results_no_delete;
DROP TABLE model_qualification_results;
ALTER TABLE model_qualification_results_v2 RENAME TO model_qualification_results;

CREATE TRIGGER model_role_activations_contract_insert
BEFORE INSERT ON model_role_activations
WHEN NOT EXISTS (
    SELECT 1
    FROM model_registry m
    JOIN model_role_policies p ON p.role=NEW.role
    JOIN model_capability_declarations c
      ON c.capability_ref=m.current_capability_ref AND c.model_registry_id=m.registry_id
    JOIN model_qualification_results q
      ON q.qualification_ref=m.current_qualification_ref AND q.model_registry_id=m.registry_id
    JOIN model_pricing_profiles pp ON pp.pricing_ref=m.pricing_ref
    WHERE m.registry_id=NEW.model_registry_id
      AND m.family=p.allowed_family AND m.lifecycle_state='ACTIVE'
      AND m.technical_model_id IS NOT NULL AND m.availability_state='AVAILABLE'
      AND m.current_qualification_state='PASS' AND q.state='PASS'
      AND c.verification_state='VERIFIED' AND pp.verification_state='VERIFIED'
      AND pp.provider=m.provider AND pp.technical_model_id=m.technical_model_id
      AND p.capability_verification_state='VERIFIED'
      AND p.pricing_verification_state='VERIFIED'
      AND p.qualification_required=1 AND p.fallback_policy='FORBIDDEN'
)
BEGIN SELECT RAISE(ABORT, 'role activation requires one qualified eligible model'); END;
CREATE TRIGGER model_role_activations_contract_update
BEFORE UPDATE ON model_role_activations
WHEN NEW.role!=OLD.role OR NOT EXISTS (
    SELECT 1
    FROM model_registry m
    JOIN model_role_policies p ON p.role=NEW.role
    JOIN model_capability_declarations c
      ON c.capability_ref=m.current_capability_ref AND c.model_registry_id=m.registry_id
    JOIN model_qualification_results q
      ON q.qualification_ref=m.current_qualification_ref AND q.model_registry_id=m.registry_id
    JOIN model_pricing_profiles pp ON pp.pricing_ref=m.pricing_ref
    WHERE m.registry_id=NEW.model_registry_id
      AND m.family=p.allowed_family AND m.lifecycle_state='ACTIVE'
      AND m.technical_model_id IS NOT NULL AND m.availability_state='AVAILABLE'
      AND m.current_qualification_state='PASS' AND q.state='PASS'
      AND c.verification_state='VERIFIED' AND pp.verification_state='VERIFIED'
      AND pp.provider=m.provider AND pp.technical_model_id=m.technical_model_id
      AND p.capability_verification_state='VERIFIED'
      AND p.pricing_verification_state='VERIFIED'
      AND p.qualification_required=1 AND p.fallback_policy='FORBIDDEN'
)
BEGIN SELECT RAISE(ABORT, 'role activation requires one qualified eligible model'); END;

CREATE TRIGGER content_writer_intents_controlled_provider_binding
BEFORE INSERT ON content_writer_intents
WHEN NEW.call_mode='CONTROLLED_PROVIDER' AND NOT EXISTS (
    SELECT 1
    FROM model_intent_bindings b
    JOIN model_registry m ON m.registry_id=b.model_registry_id
    JOIN model_pricing_profiles pp ON pp.pricing_ref=b.pricing_ref
    JOIN model_qualification_results q ON q.qualification_ref=b.qualification_ref
    JOIN model_capability_declarations c ON c.capability_ref=b.capability_ref
    WHERE b.intent_kind='content_writer'
      AND b.intent_id=NEW.job_id || ':content_writer'
      AND b.fallback_policy='FORBIDDEN'
      AND b.provider=NEW.provider
      AND b.technical_model_id=NEW.api_model_id
      AND b.pricing_ref=NEW.pricing_profile
      AND b.role=json_extract(NEW.intent_json,'$.route.logical_role')
      AND b.family=json_extract(NEW.intent_json,'$.route.model_family')
      AND b.logical_version=json_extract(NEW.intent_json,'$.route.logical_version')
      AND b.model_registry_id=json_extract(NEW.intent_json,'$.route.model_registry_id')
      AND b.qualification_ref=json_extract(NEW.intent_json,'$.route.qualification_ref')
      AND b.capability_ref=json_extract(NEW.intent_json,'$.route.capability_ref')
      AND b.provider=json_extract(NEW.intent_json,'$.route.provider')
      AND b.technical_model_id=json_extract(NEW.intent_json,'$.route.api_model_id')
      AND b.pricing_ref=json_extract(NEW.intent_json,'$.route.pricing_profile')
      AND (
        (NEW.content_type='ARTICLE' AND b.role='ARTICLE_WRITER' AND b.family='FABLE')
        OR
        (NEW.content_type='NOTE' AND b.role='NOTE_WRITER' AND b.family='SONNET')
      )
      AND m.provider=b.provider AND m.family=b.family
      AND m.logical_version=b.logical_version
      AND m.technical_model_id=b.technical_model_id
      AND q.model_registry_id=b.model_registry_id AND q.state='PASS'
      AND c.model_registry_id=b.model_registry_id
      AND c.verification_state='VERIFIED'
      AND pp.verification_state='VERIFIED'
      AND pp.provider=b.provider
      AND pp.technical_model_id=b.technical_model_id
)
BEGIN SELECT RAISE(ABORT, 'controlled provider intent requires its frozen registry binding'); END;

CREATE TRIGGER model_registry_current_evidence_contract
BEFORE UPDATE ON model_registry
WHEN (
  NEW.current_capability_ref IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM model_capability_declarations c
    WHERE c.capability_ref=NEW.current_capability_ref
      AND c.model_registry_id=NEW.registry_id
  )
) OR (
  NEW.current_qualification_ref IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM model_qualification_results q
    WHERE q.qualification_ref=NEW.current_qualification_ref
      AND q.model_registry_id=NEW.registry_id
      AND q.state=NEW.current_qualification_state
  )
)
BEGIN SELECT RAISE(ABORT, 'model current evidence does not match registry identity'); END;

CREATE TRIGGER model_qualification_results_no_update
BEFORE UPDATE ON model_qualification_results
BEGIN SELECT RAISE(ABORT, 'model_qualification_results is append-only'); END;
CREATE TRIGGER model_qualification_results_no_delete
BEFORE DELETE ON model_qualification_results
BEGIN SELECT RAISE(ABORT, 'model_qualification_results is append-only'); END;

-- Real (owner-verified catalogue) entries may only reach a qualification state
-- through the SETTLED controlled run that produced it.  A consumed approval is
-- an authorisation, not a result: on its own it proves only that a request was
-- allowed to start, so it can never stand in for evidence that one finished.
--
-- Every identity on the path is joined rather than trusted: result -> run ->
-- approval -> registry -> pricing profile, plus the approved token ceilings.
-- LOCAL_FIXTURE remains legal for models WITHOUT catalogue evidence; it simply
-- cannot give a real, owner-verified provider model paid-execution authority.
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
      -- the result names exactly the run that produced it
      AND r.qualification_ref=NEW.qualification_ref
      AND r.model_registry_id=NEW.model_registry_id
      AND r.outcome=NEW.state
      AND r.outcome IN ('PASS','FAIL')
      AND r.settled_at IS NOT NULL
      -- and that run was authorised, consumed and identity-consistent
      AND a.consumed_at IS NOT NULL
      AND a.model_registry_id=r.model_registry_id
      AND a.logical_role=r.logical_role
      AND a.provider=r.provider
      AND a.technical_model_id=r.technical_model_id
      AND a.pricing_ref=r.pricing_ref
      AND m.provider=r.provider
      AND m.technical_model_id=r.technical_model_id
      AND pp.profile_fingerprint=r.pricing_profile_fingerprint
      -- and it stayed inside the envelope a human approved
      AND r.input_tokens IS NOT NULL AND r.output_tokens IS NOT NULL
      AND r.input_tokens<=a.max_input_tokens
      AND r.output_tokens<=a.max_output_tokens
)
BEGIN SELECT RAISE(ABORT, 'an owner-verified catalogue model requires its own settled controlled qualification run'); END;

-- Capability evidence for a real model has the same provenance requirement:
-- VERIFIED capability may only come from the settled PASS run of that model.
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
      -- the declared envelope may not exceed what the run actually established
      AND NEW.max_output_tokens<=a.max_output_tokens
      AND NEW.max_context_tokens<=(a.max_input_tokens + a.max_output_tokens)
)
BEGIN SELECT RAISE(ABORT, 'verified capability for a catalogue model requires its own settled PASS run'); END;

-- ---------------------------------------------------------------------------
-- (4) One-time L1 approval for a paid CONTENT execution
-- ---------------------------------------------------------------------------

CREATE TABLE content_provider_approvals (
    approval_ref TEXT PRIMARY KEY
        CHECK (length(trim(approval_ref)) BETWEEN 1 AND 200),
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    logical_role TEXT NOT NULL REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    pricing_ref TEXT NOT NULL
        REFERENCES model_pricing_profiles(pricing_ref) ON DELETE RESTRICT,
    purpose TEXT NOT NULL CHECK (purpose='CONTROLLED_ARTICLE_EXECUTION'),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 8192),
    cap_usd TEXT NOT NULL CHECK (
        length(cap_usd)>0 AND cap_usd NOT GLOB '*[^0-9.]*'
    ),
    max_retries INTEGER NOT NULL CHECK (max_retries=0),
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    approved_by TEXT NOT NULL CHECK (length(trim(approved_by)) BETWEEN 1 AND 200),
    approved_at TEXT NOT NULL CHECK (length(approved_at)>=19),
    expires_at TEXT NOT NULL CHECK (length(expires_at)>=19 AND expires_at>approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at)>=19),
    approval_json TEXT NOT NULL CHECK (json_valid(approval_json)),
    approval_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(approval_fingerprint)=64
        AND approval_fingerprint NOT GLOB '*[^0-9a-f]*'
    )
);
CREATE TRIGGER content_provider_approvals_contract
BEFORE INSERT ON content_provider_approvals
WHEN NEW.approval_fingerprint IS NOT evidence_sha256_hex(NEW.approval_json)
 OR NEW.consumed_at IS NOT NULL
 OR NOT EXISTS (
    SELECT 1
    FROM jobs j
    JOIN model_registry m ON m.registry_id=NEW.model_registry_id
    JOIN model_role_policies p ON p.role=NEW.logical_role
    JOIN model_pricing_profiles pp ON pp.pricing_ref=NEW.pricing_ref
    WHERE j.id=NEW.job_id AND j.kind='CONTENT' AND j.account_id=NEW.account_id
      AND json_extract(j.payload_json,'$.execution_mode')
          ='CONTROLLED_PROVIDER_PIPELINE'
      AND json_extract(j.payload_json,'$.provider_enabled')=1
      AND m.provider=NEW.provider
      AND m.technical_model_id=NEW.technical_model_id
      AND m.family=p.allowed_family
      AND m.pricing_ref=NEW.pricing_ref
      AND m.current_qualification_state='PASS'
      AND m.lifecycle_state='ACTIVE'
      AND pp.verification_state='VERIFIED'
      AND (pp.effective_from IS NULL OR NEW.approved_at>=pp.effective_from)
      AND (pp.effective_until IS NULL OR NEW.approved_at<=pp.effective_until)
      AND p.fallback_policy='FORBIDDEN'
 )
BEGIN SELECT RAISE(ABORT, 'content provider approval must bind one qualified active model and effective price'); END;
CREATE TRIGGER content_provider_approvals_consume_once
BEFORE UPDATE ON content_provider_approvals
WHEN NOT (
    OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL
    AND NEW.approval_ref=OLD.approval_ref AND NEW.job_id=OLD.job_id
    AND NEW.account_id=OLD.account_id AND NEW.logical_role=OLD.logical_role
    AND NEW.model_registry_id=OLD.model_registry_id
    AND NEW.provider=OLD.provider
    AND NEW.technical_model_id=OLD.technical_model_id
    AND NEW.pricing_ref=OLD.pricing_ref AND NEW.purpose=OLD.purpose
    AND NEW.max_output_tokens=OLD.max_output_tokens
    AND NEW.cap_usd=OLD.cap_usd AND NEW.max_retries=OLD.max_retries
    AND NEW.fallback_policy=OLD.fallback_policy
    AND NEW.approved_by=OLD.approved_by AND NEW.approved_at=OLD.approved_at
    AND NEW.expires_at=OLD.expires_at AND NEW.approval_json=OLD.approval_json
    AND NEW.approval_fingerprint=OLD.approval_fingerprint
)
BEGIN SELECT RAISE(ABORT, 'content provider approval permits exactly one immutable consumption'); END;
CREATE TRIGGER content_provider_approvals_no_delete
BEFORE DELETE ON content_provider_approvals
BEGIN SELECT RAISE(ABORT, 'content_provider_approvals is append-only'); END;

-- ---------------------------------------------------------------------------
-- (5) ARTICLE_PLAN / ARTICLE_REVIEWER durable provider executions
-- ---------------------------------------------------------------------------

CREATE TABLE role_provider_executions (
    execution_ref TEXT PRIMARY KEY
        CHECK (length(trim(execution_ref)) BETWEEN 1 AND 200),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    logical_role TEXT NOT NULL CHECK (
        logical_role IN ('ARTICLE_PLAN','ARTICLE_REVIEWER')
    ),
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
    outcome TEXT NOT NULL CHECK (
        outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    input_tokens INTEGER NOT NULL CHECK (input_tokens>=0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens>=0),
    cache_read_tokens INTEGER NOT NULL CHECK (cache_read_tokens>=0),
    cache_write_tokens INTEGER NOT NULL CHECK (cache_write_tokens>=0),
    web_search_requests INTEGER NOT NULL CHECK (web_search_requests>=0),
    cost_usd TEXT NOT NULL CHECK (
        cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
        AND cost_usd NOT GLOB '*[^0-9.]*'
    ),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(result_fingerprint)=64
        AND result_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id, logical_role),
    CHECK (
      (outcome='SUCCESS' AND failure_kind IS NULL)
      OR (outcome!='SUCCESS' AND failure_kind IS NOT NULL)
    )
);
CREATE TRIGGER role_provider_executions_contract
BEFORE INSERT ON role_provider_executions
WHEN NEW.result_fingerprint IS NOT evidence_sha256_hex(NEW.result_json)
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
CREATE TRIGGER role_provider_executions_no_update
BEFORE UPDATE ON role_provider_executions
BEGIN SELECT RAISE(ABORT, 'role_provider_executions is append-only'); END;
CREATE TRIGGER role_provider_executions_no_delete
BEFORE DELETE ON role_provider_executions
BEGIN SELECT RAISE(ABORT, 'role_provider_executions is append-only'); END;
