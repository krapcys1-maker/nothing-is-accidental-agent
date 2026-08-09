-- PRE-C5 MODEL FAMILY ROUTING & QUALIFICATION CORE.
--
-- This migration is additive. Historical FABLE_5_ARTICLE and SONNET_5_NOTE
-- rows remain readable and untouched. New registry-backed routing is keyed by
-- stable logical roles; a versioned legacy route key is never consulted when
-- eligibility, promotion, or a new frozen model binding is decided.

CREATE TABLE model_pricing_profiles (
    pricing_ref TEXT PRIMARY KEY CHECK (length(trim(pricing_ref)) BETWEEN 1 AND 200),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    technical_model_id TEXT NOT NULL
        CHECK (length(trim(technical_model_id)) BETWEEN 1 AND 200),
    verification_state TEXT NOT NULL
        CHECK (verification_state IN ('UNVERIFIED','VERIFIED')),
    currency TEXT NOT NULL CHECK (length(trim(currency)) BETWEEN 1 AND 20),
    unit TEXT NOT NULL CHECK (length(trim(unit)) BETWEEN 1 AND 100),
    input_per_mtok TEXT,
    output_per_mtok TEXT,
    cache_read_per_mtok TEXT,
    cache_write_per_mtok TEXT,
    web_search_per_1k TEXT,
    profile_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(profile_fingerprint)=64
        AND profile_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    verified_at TEXT,
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    CHECK (
      (verification_state='UNVERIFIED'
       AND input_per_mtok IS NULL AND output_per_mtok IS NULL
       AND cache_read_per_mtok IS NULL AND cache_write_per_mtok IS NULL
       AND web_search_per_1k IS NULL AND verified_at IS NULL)
      OR
      (verification_state='VERIFIED'
       AND length(input_per_mtok)>0 AND length(output_per_mtok)>0
       AND length(cache_read_per_mtok)>0 AND length(cache_write_per_mtok)>0
       AND length(web_search_per_1k)>0 AND length(verified_at)>=19)
    )
);
CREATE TRIGGER model_pricing_profiles_no_update
BEFORE UPDATE ON model_pricing_profiles
BEGIN SELECT RAISE(ABORT, 'model_pricing_profiles is append-only'); END;
CREATE TRIGGER model_pricing_profiles_no_delete
BEFORE DELETE ON model_pricing_profiles
BEGIN SELECT RAISE(ABORT, 'model_pricing_profiles is append-only'); END;

CREATE TABLE model_registry (
    registry_id TEXT PRIMARY KEY CHECK (length(trim(registry_id)) BETWEEN 1 AND 100),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    family TEXT NOT NULL CHECK (family IN ('SONNET','OPUS','FABLE')),
    logical_version TEXT NOT NULL
        CHECK (length(trim(logical_version)) BETWEEN 1 AND 80),
    version_sort_key TEXT NOT NULL
        CHECK (length(trim(version_sort_key)) BETWEEN 9 AND 80),
    technical_model_id TEXT
        CHECK (technical_model_id IS NULL OR length(trim(technical_model_id)) BETWEEN 1 AND 200),
    availability_state TEXT NOT NULL
        CHECK (availability_state IN ('UNVERIFIED','AVAILABLE','UNAVAILABLE')),
    pricing_ref TEXT,
    current_capability_ref TEXT,
    current_qualification_state TEXT NOT NULL DEFAULT 'UNQUALIFIED'
        CHECK (current_qualification_state IN ('UNQUALIFIED','PASS','FAIL')),
    current_qualification_ref TEXT,
    lifecycle_state TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (lifecycle_state IN ('CANDIDATE','ACTIVE','DEPRECATED')),
    discovered_at TEXT NOT NULL CHECK (length(discovered_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    verified_at TEXT,
    qualified_at TEXT,
    catalogue_ref TEXT NOT NULL CHECK (length(trim(catalogue_ref)) BETWEEN 1 AND 200),
    UNIQUE(provider,family,logical_version),
    CHECK (
      (current_qualification_state='UNQUALIFIED'
       AND current_qualification_ref IS NULL AND qualified_at IS NULL)
      OR
      (current_qualification_state IN ('PASS','FAIL')
       AND length(current_qualification_ref)>0 AND length(qualified_at)>=19)
    )
);
CREATE TRIGGER model_registry_identity_immutable
BEFORE UPDATE ON model_registry
WHEN OLD.registry_id!=NEW.registry_id OR OLD.provider!=NEW.provider
 OR OLD.family!=NEW.family OR OLD.logical_version!=NEW.logical_version
 OR OLD.version_sort_key!=NEW.version_sort_key
 OR OLD.discovered_at!=NEW.discovered_at OR OLD.created_at!=NEW.created_at
 OR OLD.catalogue_ref!=NEW.catalogue_ref
 OR (OLD.lifecycle_state='DEPRECATED' AND NEW.lifecycle_state!='DEPRECATED')
BEGIN SELECT RAISE(ABORT, 'model registry identity/lifecycle is immutable'); END;
CREATE TRIGGER model_registry_no_delete
BEFORE DELETE ON model_registry
BEGIN SELECT RAISE(ABORT, 'model_registry cannot be deleted'); END;

CREATE TABLE model_capability_declarations (
    capability_ref TEXT PRIMARY KEY
        CHECK (length(trim(capability_ref)) BETWEEN 1 AND 200),
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    verification_state TEXT NOT NULL
        CHECK (verification_state IN ('UNVERIFIED','VERIFIED')),
    structured_response INTEGER CHECK (structured_response IN (0,1)),
    max_context_tokens INTEGER,
    max_output_tokens INTEGER,
    declaration_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(declaration_fingerprint)=64
        AND declaration_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    verified_at TEXT,
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    CHECK (
      (verification_state='UNVERIFIED' AND structured_response IS NULL
       AND max_context_tokens IS NULL AND max_output_tokens IS NULL
       AND verified_at IS NULL)
      OR
      (verification_state='VERIFIED' AND structured_response IS NOT NULL
       AND max_context_tokens>0 AND max_output_tokens>0
       AND length(verified_at)>=19)
    )
);
CREATE TRIGGER model_capability_declarations_no_update
BEFORE UPDATE ON model_capability_declarations
BEGIN SELECT RAISE(ABORT, 'model_capability_declarations is append-only'); END;
CREATE TRIGGER model_capability_declarations_no_delete
BEFORE DELETE ON model_capability_declarations
BEGIN SELECT RAISE(ABORT, 'model_capability_declarations is append-only'); END;

CREATE TABLE model_qualification_results (
    qualification_ref TEXT PRIMARY KEY
        CHECK (length(trim(qualification_ref)) BETWEEN 1 AND 200),
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('PASS','FAIL')),
    suite_version TEXT NOT NULL CHECK (length(trim(suite_version)) BETWEEN 1 AND 100),
    fixture_set_ref TEXT NOT NULL CHECK (length(trim(fixture_set_ref)) BETWEEN 1 AND 200),
    source TEXT NOT NULL CHECK (source='LOCAL_FIXTURE'),
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(result_fingerprint)=64
        AND result_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    evaluated_at TEXT NOT NULL CHECK (length(evaluated_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);
CREATE TRIGGER model_qualification_results_no_update
BEFORE UPDATE ON model_qualification_results
BEGIN SELECT RAISE(ABORT, 'model_qualification_results is append-only'); END;
CREATE TRIGGER model_qualification_results_no_delete
BEFORE DELETE ON model_qualification_results
BEGIN SELECT RAISE(ABORT, 'model_qualification_results is append-only'); END;

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

CREATE TABLE model_role_policies (
    role TEXT PRIMARY KEY CHECK (role IN (
        'TOPIC_GENERATION','ARTICLE_RESEARCH','ARTICLE_PLAN','ARTICLE_WRITER',
        'ARTICLE_REVIEWER','NOTE_WRITER','COMMENT_WRITER'
    )),
    allowed_family TEXT NOT NULL CHECK (allowed_family IN ('SONNET','OPUS','FABLE')),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) BETWEEN 1 AND 100),
    capability_verification_state TEXT NOT NULL
        CHECK (capability_verification_state IN ('UNVERIFIED','VERIFIED')),
    require_structured_response INTEGER CHECK (require_structured_response IN (0,1)),
    min_context_tokens INTEGER,
    min_output_tokens INTEGER,
    pricing_verification_state TEXT NOT NULL
        CHECK (pricing_verification_state IN ('UNVERIFIED','VERIFIED')),
    max_input_per_mtok TEXT,
    max_output_per_mtok TEXT,
    max_cache_read_per_mtok TEXT,
    max_cache_write_per_mtok TEXT,
    max_web_search_per_1k TEXT,
    qualification_required INTEGER NOT NULL CHECK (qualification_required=1),
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    policy_fingerprint TEXT NOT NULL CHECK (
        length(policy_fingerprint)=64
        AND policy_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    updated_at TEXT NOT NULL CHECK (length(updated_at)>=19),
    CHECK (
      (role IN ('TOPIC_GENERATION','NOTE_WRITER','COMMENT_WRITER')
       AND allowed_family='SONNET')
      OR (role IN ('ARTICLE_RESEARCH','ARTICLE_PLAN','ARTICLE_REVIEWER')
          AND allowed_family='OPUS')
      OR (role='ARTICLE_WRITER' AND allowed_family='FABLE')
    ),
    CHECK (
      (capability_verification_state='UNVERIFIED'
       AND require_structured_response IS NULL
       AND min_context_tokens IS NULL AND min_output_tokens IS NULL)
      OR
      (capability_verification_state='VERIFIED'
       AND require_structured_response IS NOT NULL
       AND min_context_tokens>0 AND min_output_tokens>0)
    ),
    CHECK (
      (pricing_verification_state='UNVERIFIED'
       AND max_input_per_mtok IS NULL AND max_output_per_mtok IS NULL
       AND max_cache_read_per_mtok IS NULL AND max_cache_write_per_mtok IS NULL
       AND max_web_search_per_1k IS NULL)
      OR
      (pricing_verification_state='VERIFIED'
       AND length(max_input_per_mtok)>0 AND length(max_output_per_mtok)>0
       AND length(max_cache_read_per_mtok)>0
       AND length(max_cache_write_per_mtok)>0
       AND length(max_web_search_per_1k)>0)
    )
);

-- The real policy envelopes are deliberately UNVERIFIED. These rows declare
-- only the owner-approved role -> family map and preserve fail-closed routing.
INSERT INTO model_role_policies (
    role,allowed_family,policy_version,capability_verification_state,
    require_structured_response,min_context_tokens,min_output_tokens,
    pricing_verification_state,max_input_per_mtok,max_output_per_mtok,
    max_cache_read_per_mtok,max_cache_write_per_mtok,max_web_search_per_1k,
    qualification_required,fallback_policy,policy_fingerprint,created_at,updated_at
) VALUES
('TOPIC_GENERATION','SONNET','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','d5437edf732ded73ac5b9352fdce31afff4b74bc19e1cb9db9a7b6e3e7818838',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('ARTICLE_RESEARCH','OPUS','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','b2617a7fa7aca75c0212350d7ae28e5c5de1f693251c33ab934529500853a630',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('ARTICLE_PLAN','OPUS','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','c99a1081916217a5783838e1d2e86fdd748fdcee25c46128caee833e972ec73c',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('ARTICLE_WRITER','FABLE','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','de6f4c4e0879c3b923817ac55c5f00cc656a92316215ec4c71c936b751358643',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('ARTICLE_REVIEWER','OPUS','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','c5bb4add1c1780dc7e2357d6d350b4929949d3a1af3e75da33878ec42a140bcc',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('NOTE_WRITER','SONNET','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','34eb42d1f7381c6a58c129247de5b2c3a4fe104af6684e6c4fa074744600b12d',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
('COMMENT_WRITER','SONNET','model_role_policy_v1','UNVERIFIED',NULL,NULL,NULL,
 'UNVERIFIED',NULL,NULL,NULL,NULL,NULL,1,'FORBIDDEN','2d49cd92b91908cf5d747af649995727d729ccbf9b592fb6c3fecd590c8e8484',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP);

CREATE TRIGGER model_role_policies_no_delete
BEFORE DELETE ON model_role_policies
BEGIN SELECT RAISE(ABORT, 'model_role_policies cannot be deleted'); END;

CREATE TABLE model_role_activations (
    role TEXT PRIMARY KEY REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    model_registry_id TEXT NOT NULL REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    activated_at TEXT NOT NULL CHECK (length(activated_at)>=19),
    decision_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(decision_fingerprint)=64
        AND decision_fingerprint NOT GLOB '*[^0-9a-f]*'
    )
);
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

CREATE TABLE model_routing_audit (
    event_id TEXT PRIMARY KEY CHECK (length(trim(event_id)) BETWEEN 1 AND 100),
    event_type TEXT NOT NULL CHECK (event_type IN ('PROMOTION','DEMOTION')),
    role TEXT NOT NULL REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    old_model_registry_id TEXT REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    old_family TEXT,
    old_logical_version TEXT,
    old_technical_model_id TEXT,
    old_pricing_ref TEXT,
    new_model_registry_id TEXT REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    new_family TEXT,
    new_logical_version TEXT,
    new_technical_model_id TEXT,
    new_pricing_ref TEXT,
    qualification_ref TEXT,
    capability_ref TEXT,
    occurred_at TEXT NOT NULL CHECK (length(occurred_at)>=19),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 500),
    policy_decision_json TEXT NOT NULL CHECK (json_valid(policy_decision_json)),
    decision_fingerprint TEXT NOT NULL CHECK (
        length(decision_fingerprint)=64
        AND decision_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    idempotency_key TEXT NOT NULL UNIQUE,
    CHECK (
      (event_type='PROMOTION' AND new_model_registry_id IS NOT NULL
       AND new_family IS NOT NULL AND new_logical_version IS NOT NULL
       AND new_technical_model_id IS NOT NULL AND new_pricing_ref IS NOT NULL
       AND qualification_ref IS NOT NULL AND capability_ref IS NOT NULL)
      OR
      (event_type='DEMOTION' AND old_model_registry_id IS NOT NULL)
    )
);
CREATE TRIGGER model_routing_audit_no_update
BEFORE UPDATE ON model_routing_audit
BEGIN SELECT RAISE(ABORT, 'model_routing_audit is append-only'); END;
CREATE TRIGGER model_routing_audit_no_delete
BEFORE DELETE ON model_routing_audit
BEGIN SELECT RAISE(ABORT, 'model_routing_audit is append-only'); END;

CREATE TABLE model_intent_bindings (
    intent_kind TEXT NOT NULL CHECK (length(trim(intent_kind)) BETWEEN 1 AND 100),
    intent_id TEXT NOT NULL CHECK (length(trim(intent_id)) BETWEEN 1 AND 300),
    role TEXT NOT NULL REFERENCES model_role_policies(role) ON DELETE RESTRICT,
    model_registry_id TEXT NOT NULL REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    family TEXT NOT NULL CHECK (family IN ('SONNET','OPUS','FABLE')),
    logical_version TEXT NOT NULL,
    technical_model_id TEXT NOT NULL,
    pricing_ref TEXT NOT NULL,
    qualification_ref TEXT NOT NULL,
    capability_ref TEXT NOT NULL,
    activation_decision_fingerprint TEXT NOT NULL,
    fallback_policy TEXT NOT NULL CHECK (fallback_policy='FORBIDDEN'),
    bound_at TEXT NOT NULL CHECK (length(bound_at)>=19),
    PRIMARY KEY(intent_kind,intent_id)
);
CREATE TRIGGER model_intent_bindings_contract
BEFORE INSERT ON model_intent_bindings
WHEN NOT EXISTS (
    SELECT 1
    FROM model_role_activations a
    JOIN model_registry m ON m.registry_id=a.model_registry_id
    JOIN model_role_policies p ON p.role=a.role
    WHERE a.role=NEW.role AND a.model_registry_id=NEW.model_registry_id
      AND a.decision_fingerprint=NEW.activation_decision_fingerprint
      AND m.provider=NEW.provider AND m.family=NEW.family
      AND m.logical_version=NEW.logical_version
      AND m.technical_model_id=NEW.technical_model_id
      AND m.pricing_ref=NEW.pricing_ref
      AND m.current_qualification_ref=NEW.qualification_ref
      AND m.current_capability_ref=NEW.capability_ref
      AND m.lifecycle_state='ACTIVE' AND m.availability_state='AVAILABLE'
      AND m.current_qualification_state='PASS'
      AND p.allowed_family=m.family AND p.fallback_policy=NEW.fallback_policy
)
BEGIN SELECT RAISE(ABORT, 'intent binding requires the exact active qualified model'); END;
CREATE TRIGGER model_intent_bindings_no_update
BEFORE UPDATE ON model_intent_bindings
BEGIN SELECT RAISE(ABORT, 'model_intent_bindings is append-only'); END;
CREATE TRIGGER model_intent_bindings_no_delete
BEFORE DELETE ON model_intent_bindings
BEGIN SELECT RAISE(ABORT, 'model_intent_bindings is append-only'); END;

-- Historical SQL CHECKs still preserve the two old route keys. New content
-- intents additionally persist a stable role/family in JSON; this trigger
-- makes the compatibility key incapable of redefining that family policy.
CREATE TRIGGER content_writer_intents_stable_role_contract
BEFORE INSERT ON content_writer_intents
WHEN (
  NEW.content_type='ARTICLE' AND (
    json_extract(NEW.intent_json,'$.route.logical_role') IS NOT 'ARTICLE_WRITER'
    OR json_extract(NEW.intent_json,'$.route.model_family') IS NOT 'FABLE'
  )
) OR (
  NEW.content_type='NOTE' AND (
    json_extract(NEW.intent_json,'$.route.logical_role') IS NOT 'NOTE_WRITER'
    OR json_extract(NEW.intent_json,'$.route.model_family') IS NOT 'SONNET'
  )
)
BEGIN SELECT RAISE(ABORT, 'legacy route key cannot override stable role family policy'); END;
