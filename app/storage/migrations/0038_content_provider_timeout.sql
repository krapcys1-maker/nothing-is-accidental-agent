-- Opus ARTICLE generation and semantic review may legitimately take longer
-- than 30 seconds. Preserve the complete immutable writer-intent contract and
-- widen only its bounded transport timeout to five minutes.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER content_writer_intents_contract;
DROP TRIGGER content_writer_intents_controlled_provider_binding;
DROP TRIGGER content_writer_intents_stable_role_contract;
DROP TRIGGER content_writer_intents_no_update;
DROP TRIGGER content_writer_intents_no_delete;

CREATE TABLE content_writer_intents_0038_new (
    intent_id TEXT PRIMARY KEY,
    intent_schema_version TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    call_mode TEXT NOT NULL CHECK (
        call_mode IN ('FAKE','PROVIDER_READY_OFFLINE','CONTROLLED_PROVIDER')
    ),
    route_key TEXT NOT NULL CHECK (
        route_key IN ('FABLE_5_ARTICLE','SONNET_5_NOTE')
    ),
    route_config_version TEXT NOT NULL,
    route_config_fingerprint TEXT NOT NULL CHECK (
        length(route_config_fingerprint)=64
        AND route_config_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    provider TEXT NOT NULL,
    api_model_id TEXT NOT NULL,
    availability_status TEXT NOT NULL CHECK (
        availability_status IN ('UNVERIFIED','CONFIGURED')
    ),
    pricing_profile TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL
        REFERENCES content_plans(plan_fingerprint) ON DELETE RESTRICT,
    brief_sha256 TEXT NOT NULL
        REFERENCES content_article_briefs(brief_sha256) ON DELETE RESTRICT,
    frozen_input_sha256 TEXT NOT NULL,
    evidence_manifest_sha256 TEXT NOT NULL,
    style_profile_id TEXT NOT NULL,
    negative_style_profile_id TEXT NOT NULL,
    prompt_fingerprint TEXT NOT NULL CHECK (
        length(prompt_fingerprint)=64
        AND prompt_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    max_input_tokens INTEGER NOT NULL CHECK (max_input_tokens>0),
    max_context_tokens INTEGER NOT NULL CHECK (
        max_context_tokens>=max_input_tokens
    ),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens>0),
    timeout_seconds REAL NOT NULL CHECK (
        timeout_seconds=timeout_seconds
        AND timeout_seconds>0.0 AND timeout_seconds<=300.0
    ),
    rewrite_of_draft_fingerprint TEXT,
    rewrite_feedback_json TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(rewrite_feedback_json)),
    max_cost_usd REAL NOT NULL CHECK (
        max_cost_usd=max_cost_usd AND max_cost_usd>=0.0
    ),
    intent_json TEXT NOT NULL CHECK (json_valid(intent_json)),
    intent_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(intent_fingerprint)=64
        AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,attempt_no),
    UNIQUE(job_id,attempt_no)
);

INSERT INTO content_writer_intents_0038_new SELECT * FROM content_writer_intents;
DROP TABLE content_writer_intents;
ALTER TABLE content_writer_intents_0038_new RENAME TO content_writer_intents;

CREATE TRIGGER content_writer_intents_contract
BEFORE INSERT ON content_writer_intents
WHEN NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.intent_json)
 OR (NEW.content_type='ARTICLE' AND NEW.route_key!='FABLE_5_ARTICLE')
 OR (NEW.content_type='NOTE' AND NEW.route_key!='SONNET_5_NOTE')
 OR (
    NEW.call_mode='FAKE' AND (
      NEW.provider!='UNVERIFIED' OR NEW.api_model_id!='UNVERIFIED'
      OR NEW.availability_status!='UNVERIFIED'
      OR NEW.pricing_profile!='UNVERIFIED' OR NEW.max_cost_usd!=0.0
    )
 )
 OR (
    NEW.call_mode='PROVIDER_READY_OFFLINE' AND (
      NEW.provider='UNVERIFIED' OR NEW.api_model_id='UNVERIFIED'
      OR NEW.availability_status!='CONFIGURED'
      OR NEW.pricing_profile='UNVERIFIED' OR NEW.max_cost_usd!=0.0
    )
 )
 OR (
    NEW.call_mode='CONTROLLED_PROVIDER' AND (
      NEW.provider='UNVERIFIED' OR NEW.api_model_id='UNVERIFIED'
      OR NEW.availability_status!='CONFIGURED'
      OR NEW.pricing_profile='UNVERIFIED' OR NEW.max_cost_usd<=0.0
    )
 )
 OR (NEW.attempt_no=1 AND (
       NEW.rewrite_of_draft_fingerprint IS NOT NULL
       OR NEW.rewrite_feedback_json!='[]'
    ))
 OR (NEW.attempt_no=2 AND NOT EXISTS (
       SELECT 1
       FROM content_drafts d
       JOIN content_draft_evaluations e ON e.draft_id=d.id
       JOIN content_items c ON c.id=d.content_id
       WHERE d.content_id=NEW.content_id AND d.attempt_no=1
         AND d.draft_fingerprint=NEW.rewrite_of_draft_fingerprint
         AND e.decision='REWRITE_ONCE' AND c.status='REVISE'
    ))
 OR (
    NEW.intent_schema_version='provider_ready_writer_intent_v1'
    AND (
      json_extract(NEW.intent_json,'$.schema_version')
          !=NEW.intent_schema_version
      OR json_extract(NEW.intent_json,'$.call_mode')!=NEW.call_mode
      OR json_extract(NEW.intent_json,'$.route.route_key')!=NEW.route_key
      OR json_extract(NEW.intent_json,'$.route.provider')!=NEW.provider
      OR json_extract(NEW.intent_json,'$.route.api_model_id')!=NEW.api_model_id
      OR json_extract(NEW.intent_json,'$.route.availability')
          !=NEW.availability_status
      OR json_extract(NEW.intent_json,'$.route.pricing_profile')
          !=NEW.pricing_profile
      OR json_extract(NEW.intent_json,'$.prompt_fingerprint')
          !=NEW.prompt_fingerprint
      OR json_extract(NEW.intent_json,'$.limits.max_input_tokens')
          !=NEW.max_input_tokens
      OR json_extract(NEW.intent_json,'$.limits.max_context_tokens')
          !=NEW.max_context_tokens
      OR json_extract(NEW.intent_json,'$.limits.max_output_tokens')
          !=NEW.max_output_tokens
      OR json_extract(NEW.intent_json,'$.limits.timeout_seconds')
          !=NEW.timeout_seconds
      OR json_extract(NEW.intent_json,'$.limits.max_cost_usd')
          !=NEW.max_cost_usd
    )
 )
 OR NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN content_plans p ON p.content_id=c.id
    JOIN content_article_briefs b ON b.content_id=c.id
    WHERE c.id=NEW.content_id AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id AND c.type=NEW.content_type
      AND c.status IN ('RUNNING','REVISE')
      AND cr.job_id=NEW.job_id AND cr.run_id=NEW.run_id
      AND fi.input_sha256=NEW.frozen_input_sha256
      AND fi.evidence_manifest_sha256=NEW.evidence_manifest_sha256
      AND p.plan_fingerprint=NEW.plan_fingerprint
      AND p.route_config_version=NEW.route_config_version
      AND p.route_config_fingerprint=NEW.route_config_fingerprint
      AND b.brief_sha256=NEW.brief_sha256
 )
BEGIN SELECT RAISE(ABORT, 'writer intent does not match the durable C3 execution'); END;

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
        (NEW.content_type='ARTICLE' AND b.role='ARTICLE_WRITER' AND b.family='OPUS')
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

CREATE TRIGGER content_writer_intents_stable_role_contract
BEFORE INSERT ON content_writer_intents
WHEN (
  NEW.content_type='ARTICLE' AND (
    json_extract(NEW.intent_json,'$.route.logical_role') IS NOT 'ARTICLE_WRITER'
    OR json_extract(NEW.intent_json,'$.route.model_family') IS NOT 'OPUS'
  )
) OR (
  NEW.content_type='NOTE' AND (
    json_extract(NEW.intent_json,'$.route.logical_role') IS NOT 'NOTE_WRITER'
    OR json_extract(NEW.intent_json,'$.route.model_family') IS NOT 'SONNET'
  )
)
BEGIN SELECT RAISE(ABORT, 'legacy route key cannot override stable role family policy'); END;

CREATE TRIGGER content_writer_intents_no_update
BEFORE UPDATE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;
CREATE TRIGGER content_writer_intents_no_delete
BEFORE DELETE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0038_content_provider_timeout', datetime('now'));
COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
