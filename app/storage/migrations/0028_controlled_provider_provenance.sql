-- PRE-C5 CONTROLLED PROVIDER PROVENANCE & PRICING AUTHORITY.
--
-- 0027 admitted the offline registry.  This migration makes that registry the
-- only way a paid CONTENT writer execution can name a model or a price.
--
-- Two independent gaps are closed here, both additive:
--
--   (1) Provenance.  Before this step a CONTROLLED_PROVIDER writer intent only
--       had to be "technically configured": four non-'UNVERIFIED' strings were
--       enough.  Any string passed.  Now the durable intent row — the v3-shaped
--       content_writer_intents table introduced by 0023 — cannot be written at
--       all unless a frozen model_intent_bindings row for exactly this job
--       already names the same registry entry, provider, technical model ID,
--       pricing profile, qualification evidence and capability evidence.
--
--   (2) Pricing authority.  Before this step the cost of a paid content attempt
--       was whatever number the caller reported.  model_pricing_profiles existed
--       but nothing in the content flow read it.  Now a paid model_usage row
--       requires a 1:1 settlement row priced from the exact frozen pricing_ref,
--       so the registry profile is the single authority for that attempt and
--       app/core/pricing.py stays scoped to RESEARCH / TOPIC_GENERATION.
--
-- One binding covers one content execution, not one attempt row: both the
-- first attempt and the rewrite share `<job_id>:content_writer`, so a promotion
-- landing between the two attempts cannot change the model mid-execution.
--
-- Nothing here enables a real provider, real discovery or a production
-- migration.  Real model IDs, prices and availability all remain UNVERIFIED.

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
      -- the durable columns must repeat the binding exactly
      AND b.provider=NEW.provider
      AND b.technical_model_id=NEW.api_model_id
      AND b.pricing_ref=NEW.pricing_profile
      -- and so must the canonical intent JSON the fingerprint is taken over
      AND b.role=json_extract(NEW.intent_json,'$.route.logical_role')
      AND b.family=json_extract(NEW.intent_json,'$.route.model_family')
      AND b.logical_version=json_extract(NEW.intent_json,'$.route.logical_version')
      AND b.model_registry_id=json_extract(NEW.intent_json,'$.route.model_registry_id')
      AND b.qualification_ref=json_extract(NEW.intent_json,'$.route.qualification_ref')
      AND b.capability_ref=json_extract(NEW.intent_json,'$.route.capability_ref')
      AND b.provider=json_extract(NEW.intent_json,'$.route.provider')
      AND b.technical_model_id=json_extract(NEW.intent_json,'$.route.api_model_id')
      AND b.pricing_ref=json_extract(NEW.intent_json,'$.route.pricing_profile')
      -- the content type decides the role; the legacy route key never does
      AND (
        (NEW.content_type='ARTICLE' AND b.role='ARTICLE_WRITER' AND b.family='FABLE')
        OR
        (NEW.content_type='NOTE' AND b.role='NOTE_WRITER' AND b.family='SONNET')
      )
      -- the frozen evidence must still resolve to this exact registry entry
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

CREATE TRIGGER content_writer_attempts_controlled_provider_binding
BEFORE INSERT ON content_writer_attempts
WHEN NEW.call_mode='CONTROLLED_PROVIDER' AND NOT EXISTS (
    SELECT 1
    FROM model_intent_bindings b
    WHERE b.intent_kind='content_writer'
      AND b.intent_id=NEW.job_id || ':content_writer'
      AND b.provider=NEW.provider
      AND b.technical_model_id=NEW.model
      AND b.fallback_policy='FORBIDDEN'
)
BEGIN SELECT RAISE(ABORT, 'controlled provider attempt must run the frozen model'); END;

-- The durable proof that one paid attempt was priced by one approved profile.
-- cost_usd is canonical six-decimal TEXT: the money boundary of this flow stays
-- Decimal, and the legacy REAL column in model_usage only mirrors it.
CREATE TABLE content_provider_cost_settlements (
    request_id TEXT PRIMARY KEY
        REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    intent_id TEXT NOT NULL UNIQUE
        REFERENCES content_writer_intents(intent_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    binding_intent_id TEXT NOT NULL,
    model_registry_id TEXT NOT NULL
        REFERENCES model_registry(registry_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    technical_model_id TEXT NOT NULL
        CHECK (length(trim(technical_model_id)) BETWEEN 1 AND 200),
    pricing_ref TEXT NOT NULL
        REFERENCES model_pricing_profiles(pricing_ref) ON DELETE RESTRICT,
    pricing_profile_fingerprint TEXT NOT NULL CHECK (
        length(pricing_profile_fingerprint)=64
        AND pricing_profile_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    qualification_ref TEXT NOT NULL,
    capability_ref TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency='USD'),
    unit TEXT NOT NULL CHECK (length(trim(unit)) BETWEEN 1 AND 100),
    input_tokens INTEGER NOT NULL CHECK (input_tokens>=0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens>=0),
    cache_read_tokens INTEGER NOT NULL CHECK (cache_read_tokens>=0),
    cache_write_tokens INTEGER NOT NULL CHECK (cache_write_tokens>=0),
    web_search_requests INTEGER NOT NULL CHECK (web_search_requests>=0),
    cost_usd TEXT NOT NULL CHECK (
        cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
        AND cost_usd NOT GLOB '*[^0-9.]*'
    ),
    settled_at TEXT NOT NULL CHECK (length(settled_at)>=19)
);

CREATE TRIGGER content_provider_cost_settlements_contract
BEFORE INSERT ON content_provider_cost_settlements
WHEN NOT EXISTS (
    SELECT 1
    FROM content_writer_attempts wa
    JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
    JOIN model_intent_bindings b
      ON b.intent_kind='content_writer'
     AND b.intent_id=wa.job_id || ':content_writer'
    JOIN model_pricing_profiles pp ON pp.pricing_ref=b.pricing_ref
    WHERE wa.request_id=NEW.request_id AND wa.intent_id=NEW.intent_id
      AND wa.job_id=NEW.job_id AND wa.run_id=NEW.run_id
      AND wa.content_id=NEW.content_id AND wa.attempt_no=NEW.attempt_no
      AND wi.call_mode='CONTROLLED_PROVIDER'
      -- the settlement may only name the binding this execution froze
      AND NEW.binding_intent_id=b.intent_id
      AND NEW.model_registry_id=b.model_registry_id
      AND NEW.provider=b.provider
      AND NEW.technical_model_id=b.technical_model_id
      AND NEW.pricing_ref=b.pricing_ref
      AND NEW.qualification_ref=b.qualification_ref
      AND NEW.capability_ref=b.capability_ref
      -- and it must agree with the attempt and intent it settles
      AND NEW.provider=wa.provider AND NEW.technical_model_id=wa.model
      AND NEW.pricing_ref=wi.pricing_profile
      -- exact approved numbers, not merely an equal-looking price list
      AND pp.verification_state='VERIFIED'
      AND pp.profile_fingerprint=NEW.pricing_profile_fingerprint
      AND pp.currency=NEW.currency AND pp.unit=NEW.unit
)
BEGIN SELECT RAISE(ABORT, 'cost settlement does not match the frozen pricing authority'); END;
CREATE TRIGGER content_provider_cost_settlements_no_update
BEFORE UPDATE ON content_provider_cost_settlements
BEGIN SELECT RAISE(ABORT, 'content_provider_cost_settlements is append-only'); END;
CREATE TRIGGER content_provider_cost_settlements_no_delete
BEFORE DELETE ON content_provider_cost_settlements
BEGIN SELECT RAISE(ABORT, 'content_provider_cost_settlements is append-only'); END;

-- No paid content cost without the frozen pricing identity that produced it.
CREATE TRIGGER model_usage_controlled_provider_settlement
BEFORE INSERT ON model_usage
WHEN NEW.request_id IS NOT NULL
AND EXISTS (
    SELECT 1
    FROM content_writer_attempts wa
    JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
    WHERE wa.request_id=NEW.request_id AND wi.call_mode='CONTROLLED_PROVIDER'
)
AND NOT EXISTS (
    SELECT 1
    FROM content_provider_cost_settlements s
    JOIN model_intent_bindings b
      ON b.intent_kind='content_writer' AND b.intent_id=s.binding_intent_id
    WHERE s.request_id=NEW.request_id
      AND NEW.dry_run=0
      AND s.provider=NEW.provider AND s.technical_model_id=NEW.model
      AND s.input_tokens=NEW.input_tokens
      AND s.output_tokens=NEW.output_tokens
      AND s.cache_read_tokens=NEW.cache_read_tokens
      AND s.cache_write_tokens=NEW.cache_write_tokens
      AND s.web_search_requests=NEW.web_search_requests
      AND s.provider=b.provider AND s.technical_model_id=b.technical_model_id
      AND s.model_registry_id=b.model_registry_id
      AND s.pricing_ref=b.pricing_ref
      AND s.qualification_ref=b.qualification_ref
      AND s.capability_ref=b.capability_ref
)
BEGIN SELECT RAISE(ABORT, 'controlled provider usage requires its frozen pricing settlement'); END;
