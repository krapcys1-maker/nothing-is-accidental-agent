-- ARTICLE_WRITER PRIMARY FAMILY SWITCH: FABLE -> OPUS.
--
-- This is a forward-only policy migration.  Historical Fable catalogue,
-- qualification, cost, retention, audit and frozen-intent rows are data and are
-- not updated.  The old FABLE_5_ARTICLE route key remains a compatibility key;
-- new ARTICLE writer bindings must carry the stable OPUS family.
--
-- model_role_policies is referenced by several durable tables, so the migration
-- owns a foreign_keys=OFF rebuild just like the existing parent-table rebuilds.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

-- This switch is deliberately defined only for the observed fail-closed state.
-- An active or previously verified writer policy requires a separate operator
-- decision rather than being silently demoted or rewritten by a migration.
CREATE TEMP TABLE article_writer_opus_switch_guard (
    ok INTEGER NOT NULL CHECK (ok=1)
);
INSERT INTO article_writer_opus_switch_guard(ok)
SELECT CASE WHEN
    (SELECT COUNT(*) FROM model_role_policies)=7
    AND EXISTS (
        SELECT 1 FROM model_role_policies
        WHERE role='ARTICLE_WRITER'
          AND allowed_family='FABLE'
          AND policy_version='model_role_policy_v1'
          AND capability_verification_state='UNVERIFIED'
          AND require_structured_response IS NULL
          AND min_context_tokens IS NULL
          AND min_output_tokens IS NULL
          AND pricing_verification_state='UNVERIFIED'
          AND max_input_per_mtok IS NULL
          AND max_output_per_mtok IS NULL
          AND max_cache_read_per_mtok IS NULL
          AND max_cache_write_per_mtok IS NULL
          AND max_web_search_per_1k IS NULL
          AND qualification_required=1
          AND fallback_policy='FORBIDDEN'
          AND policy_fingerprint=
              'de6f4c4e0879c3b923817ac55c5f00cc656a92316215ec4c71c936b751358643'
    )
    AND NOT EXISTS (
        SELECT 1 FROM model_role_activations WHERE role='ARTICLE_WRITER'
    )
    THEN 1 ELSE 0 END;
DROP TABLE article_writer_opus_switch_guard;

DROP TRIGGER model_role_policies_no_delete;

CREATE TABLE model_role_policies_v2 (
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
      OR (role IN ('ARTICLE_RESEARCH','ARTICLE_PLAN','ARTICLE_WRITER','ARTICLE_REVIEWER')
          AND allowed_family='OPUS')
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

INSERT INTO model_role_policies_v2 (
    role,allowed_family,policy_version,capability_verification_state,
    require_structured_response,min_context_tokens,min_output_tokens,
    pricing_verification_state,max_input_per_mtok,max_output_per_mtok,
    max_cache_read_per_mtok,max_cache_write_per_mtok,max_web_search_per_1k,
    qualification_required,fallback_policy,policy_fingerprint,created_at,updated_at
)
SELECT
    role,
    CASE WHEN role='ARTICLE_WRITER' THEN 'OPUS' ELSE allowed_family END,
    CASE WHEN role='ARTICLE_WRITER' THEN 'model_role_policy_v2' ELSE policy_version END,
    capability_verification_state,
    require_structured_response,min_context_tokens,min_output_tokens,
    pricing_verification_state,max_input_per_mtok,max_output_per_mtok,
    max_cache_read_per_mtok,max_cache_write_per_mtok,max_web_search_per_1k,
    qualification_required,fallback_policy,
    CASE WHEN role='ARTICLE_WRITER'
         THEN '3dec86286183256a243781a609eab28493e6a68b27338bd74ae372b14c011967'
         ELSE policy_fingerprint END,
    created_at,
    CASE WHEN role='ARTICLE_WRITER' THEN CURRENT_TIMESTAMP ELSE updated_at END
FROM model_role_policies;

DROP TABLE model_role_policies;
ALTER TABLE model_role_policies_v2 RENAME TO model_role_policies;

CREATE TRIGGER model_role_policies_no_delete
BEFORE DELETE ON model_role_policies
BEGIN SELECT RAISE(ABORT, 'model_role_policies cannot be deleted'); END;

DROP TRIGGER content_writer_intents_stable_role_contract;
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

DROP TRIGGER content_writer_intents_controlled_provider_binding;
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

SELECT _nia_transactional_migration_failpoint('0031_article_writer_opus_policy');
INSERT INTO schema_migrations(version)
VALUES ('0031_article_writer_opus_policy');

COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
