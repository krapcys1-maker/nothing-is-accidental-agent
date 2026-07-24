-- WAVE C3: provider-ready writer persistence without a live composition root.
-- The migration preserves C2 rows, keeps the two-attempt lifecycle and adds
-- exact logical-route/provider/model/pricing separation plus typed results.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER content_writer_intents_contract;
DROP TRIGGER content_writer_intents_no_update;
DROP TRIGGER content_writer_intents_no_delete;
DROP TRIGGER content_writer_attempts_contract;
DROP TRIGGER content_writer_attempts_no_update;
DROP TRIGGER content_writer_attempts_no_delete;
DROP TRIGGER provider_attempts_no_retry_without_resolver;
DROP TRIGGER provider_attempts_content_requires_extension;
DROP TRIGGER model_usage_content_attempt_contract;
DROP TRIGGER content_drafts_contract;

CREATE TABLE content_writer_intents_v3 (
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
        AND timeout_seconds>0.0 AND timeout_seconds<=30.0
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

INSERT INTO content_writer_intents_v3 (
    intent_id,intent_schema_version,job_id,run_id,content_id,account_id,
    content_type,attempt_no,call_mode,route_key,route_config_version,
    route_config_fingerprint,provider,api_model_id,availability_status,
    pricing_profile,plan_fingerprint,brief_sha256,frozen_input_sha256,
    evidence_manifest_sha256,style_profile_id,negative_style_profile_id,
    prompt_fingerprint,max_input_tokens,max_context_tokens,max_output_tokens,
    timeout_seconds,rewrite_of_draft_fingerprint,rewrite_feedback_json,
    max_cost_usd,intent_json,intent_fingerprint,created_at
)
SELECT
    intent_id,
    COALESCE(json_extract(intent_json,'$.schema_version'),'offline_writer_intent_v1'),
    job_id,run_id,content_id,account_id,content_type,attempt_no,call_mode,
    route_key,route_config_version,route_config_fingerprint,
    provider_status,api_model_id_status,availability_status,pricing_status,
    plan_fingerprint,brief_sha256,frozen_input_sha256,evidence_manifest_sha256,
    style_profile_id,negative_style_profile_id,
    printf('%064d',0),1,1,1,1.0,rewrite_of_draft_fingerprint,
    rewrite_feedback_json,max_cost_usd,intent_json,intent_fingerprint,created_at
FROM content_writer_intents;

CREATE TEMP TABLE content_writer_attempts_backup AS
SELECT request_id,intent_id,job_id,run_id,content_id,account_id,stage,
       attempt_no,call_mode,provider,model,created_at
FROM content_writer_attempts;

DROP TABLE content_writer_attempts;
DROP TABLE content_writer_intents;
ALTER TABLE content_writer_intents_v3 RENAME TO content_writer_intents;

CREATE TABLE content_writer_attempts_v3 (
    request_id TEXT PRIMARY KEY
        REFERENCES provider_attempts(request_id) ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    intent_id TEXT NOT NULL UNIQUE
        REFERENCES content_writer_intents(intent_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK (stage='content_draft'),
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    call_mode TEXT NOT NULL CHECK (
        call_mode IN ('FAKE','PROVIDER_READY_OFFLINE','CONTROLLED_PROVIDER')
    ),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,attempt_no),
    UNIQUE(job_id,attempt_no)
);

INSERT INTO content_writer_attempts_v3 (
    request_id,intent_id,job_id,run_id,content_id,account_id,stage,
    attempt_no,call_mode,provider,model,created_at
)
SELECT request_id,intent_id,job_id,run_id,content_id,account_id,stage,
       attempt_no,call_mode,provider,model,created_at
FROM content_writer_attempts_backup;

ALTER TABLE content_writer_attempts_v3 RENAME TO content_writer_attempts;
DROP TABLE content_writer_attempts_backup;

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
CREATE TRIGGER content_writer_intents_no_update
BEFORE UPDATE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;
CREATE TRIGGER content_writer_intents_no_delete
BEFORE DELETE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;

CREATE TRIGGER content_writer_attempts_contract
BEFORE INSERT ON content_writer_attempts
WHEN NEW.request_id != NEW.job_id || ':' || NEW.stage || ':' || NEW.attempt_no
 OR NOT EXISTS (
    SELECT 1
    FROM content_writer_intents wi
    JOIN content_items c ON c.id=wi.content_id
    WHERE wi.intent_id=NEW.intent_id AND wi.job_id=NEW.job_id
      AND wi.run_id=NEW.run_id AND wi.content_id=NEW.content_id
      AND wi.account_id=NEW.account_id AND wi.attempt_no=NEW.attempt_no
      AND wi.call_mode=NEW.call_mode
      AND (
        (wi.call_mode='FAKE' AND NEW.provider='fake-content-writer'
         AND NEW.model=wi.route_key)
        OR
        (wi.call_mode!='FAKE' AND NEW.provider=wi.provider
         AND NEW.model=wi.api_model_id)
      )
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
 )
BEGIN SELECT RAISE(ABORT, 'writer attempt does not match its intent'); END;
CREATE TRIGGER content_writer_attempts_no_update
BEFORE UPDATE ON content_writer_attempts
BEGIN SELECT RAISE(ABORT, 'content_writer_attempts is append-only'); END;
CREATE TRIGGER content_writer_attempts_no_delete
BEFORE DELETE ON content_writer_attempts
BEGIN SELECT RAISE(ABORT, 'content_writer_attempts is append-only'); END;

CREATE TABLE content_writer_results (
    request_id TEXT PRIMARY KEY
        REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    intent_id TEXT NOT NULL UNIQUE
        REFERENCES content_writer_intents(intent_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    outcome TEXT NOT NULL CHECK (outcome IN ('SUCCESS','FAILURE')),
    failure_kind TEXT,
    uncertain INTEGER NOT NULL CHECK (uncertain IN (0,1)),
    provider TEXT NOT NULL,
    route_key TEXT NOT NULL,
    api_model_id TEXT,
    stop_reason TEXT,
    provider_request_id TEXT,
    usage_json TEXT CHECK (usage_json IS NULL OR json_valid(usage_json)),
    draft_fingerprint TEXT,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    result_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(result_fingerprint)=64
        AND result_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    CHECK (
      (outcome='SUCCESS' AND failure_kind IS NULL AND uncertain=0
       AND usage_json IS NOT NULL AND draft_fingerprint IS NOT NULL)
      OR
      (outcome='FAILURE' AND failure_kind IS NOT NULL
       AND draft_fingerprint IS NULL)
    )
);

CREATE TRIGGER content_writer_results_contract
BEFORE INSERT ON content_writer_results
WHEN NEW.result_fingerprint IS NOT evidence_sha256_hex(NEW.result_json)
 OR NOT EXISTS (
    SELECT 1
    FROM content_writer_attempts wa
    JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
    JOIN provider_attempts pa ON pa.request_id=wa.request_id
    WHERE wa.request_id=NEW.request_id AND wa.intent_id=NEW.intent_id
      AND wa.job_id=NEW.job_id AND wa.run_id=NEW.run_id
      AND wa.content_id=NEW.content_id AND wa.attempt_no=NEW.attempt_no
      AND wi.route_key=NEW.route_key AND wa.provider=NEW.provider
      AND (
        (wi.call_mode='FAKE' AND NEW.api_model_id IS NULL)
        OR
        (wi.call_mode!='FAKE' AND NEW.api_model_id=wa.model)
      )
      AND pa.status IN ('REQUEST_STARTED','SETTLED')
 )
 OR json_extract(NEW.result_json,'$.status')!=NEW.outcome
 OR json_extract(NEW.result_json,'$.provider')!=NEW.provider
 OR json_extract(NEW.result_json,'$.route_key')!=NEW.route_key
BEGIN SELECT RAISE(ABORT, 'writer result does not match its canonical attempt'); END;
CREATE TRIGGER content_writer_results_no_update
BEFORE UPDATE ON content_writer_results
BEGIN SELECT RAISE(ABORT, 'content_writer_results is append-only'); END;
CREATE TRIGGER content_writer_results_no_delete
BEFORE DELETE ON content_writer_results
BEGIN SELECT RAISE(ABORT, 'content_writer_results is append-only'); END;

CREATE TRIGGER provider_attempts_no_retry_without_resolver
BEFORE INSERT ON provider_attempts
WHEN NEW.attempt_no > 1
 AND EXISTS (
   SELECT 1 FROM provider_attempts p
   WHERE p.job_id=NEW.job_id AND p.stage=NEW.stage
 )
 AND NOT (
    NEW.attempt_no=2
    AND EXISTS (
        SELECT 1
        FROM content_writer_attempts wa
        JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
        JOIN provider_attempts p1
          ON p1.job_id=NEW.job_id AND p1.stage=NEW.stage AND p1.attempt_no=1
        JOIN content_drafts d ON d.request_id=p1.request_id
        JOIN content_draft_evaluations e ON e.draft_id=d.id
        WHERE wa.request_id=NEW.request_id AND wa.job_id=NEW.job_id
          AND wa.stage=NEW.stage AND wa.attempt_no=2
          AND wi.attempt_no=2 AND p1.status='SETTLED'
          AND e.decision='REWRITE_ONCE'
    )
 )
BEGIN SELECT RAISE(ABORT, 'provider_attempt retry requires explicit reconciliation resolver'); END;

CREATE TRIGGER provider_attempts_content_requires_extension
BEFORE INSERT ON provider_attempts
WHEN EXISTS (SELECT 1 FROM jobs j WHERE j.id=NEW.job_id AND j.kind='CONTENT')
AND NOT (
    EXISTS (
      SELECT 1 FROM content_provider_attempts cpa
      JOIN content_call_intents ci ON ci.intent_id=cpa.intent_id
      WHERE cpa.request_id=NEW.request_id AND cpa.job_id=NEW.job_id
        AND cpa.stage=NEW.stage AND cpa.attempt_no=NEW.attempt_no
        AND ci.intent_fingerprint=NEW.execution_intent_fingerprint
    )
    OR EXISTS (
      SELECT 1 FROM content_writer_attempts wa
      JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
      WHERE wa.request_id=NEW.request_id AND wa.job_id=NEW.job_id
        AND wa.stage=NEW.stage AND wa.attempt_no=NEW.attempt_no
        AND wi.intent_fingerprint=NEW.execution_intent_fingerprint
        AND (
          (wi.call_mode IN ('FAKE','PROVIDER_READY_OFFLINE')
           AND wi.max_cost_usd=0.0)
          OR
          (wi.call_mode='CONTROLLED_PROVIDER' AND wi.max_cost_usd>0.0)
        )
    )
)
BEGIN SELECT RAISE(ABORT, 'CONTENT provider attempt requires its exact 1:1 extension'); END;

CREATE TRIGGER model_usage_content_attempt_contract
BEFORE INSERT ON model_usage
WHEN NEW.request_id IS NOT NULL
AND (
    EXISTS (SELECT 1 FROM content_provider_attempts WHERE request_id=NEW.request_id)
    OR EXISTS (SELECT 1 FROM content_writer_attempts WHERE request_id=NEW.request_id)
)
AND NOT (
    EXISTS (
      SELECT 1 FROM content_provider_attempts cpa
      JOIN content_call_intents ci ON ci.intent_id=cpa.intent_id
      JOIN provider_attempts pa ON pa.request_id=cpa.request_id
      WHERE cpa.request_id=NEW.request_id AND pa.job_id=cpa.job_id
        AND pa.stage=cpa.stage AND pa.attempt_no=cpa.attempt_no
        AND NEW.run_id=cpa.run_id AND NEW.provider=cpa.provider
        AND NEW.model=cpa.model AND NEW.task=cpa.stage
        AND ci.intent_fingerprint=pa.execution_intent_fingerprint
    )
    OR EXISTS (
      SELECT 1 FROM content_writer_attempts wa
      JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
      JOIN provider_attempts pa ON pa.request_id=wa.request_id
      WHERE wa.request_id=NEW.request_id AND pa.job_id=wa.job_id
        AND pa.stage=wa.stage AND pa.attempt_no=wa.attempt_no
        AND NEW.run_id=wa.run_id AND NEW.provider=wa.provider
        AND NEW.model=wa.model AND NEW.task=wa.stage
        AND wi.intent_fingerprint=pa.execution_intent_fingerprint
        AND (
          (wi.call_mode IN ('FAKE','PROVIDER_READY_OFFLINE')
           AND NEW.dry_run=1 AND NEW.estimated_cost_usd=0.0)
          OR
          (wi.call_mode='CONTROLLED_PROVIDER' AND NEW.dry_run=0)
        )
    )
)
BEGIN SELECT RAISE(ABORT, 'model_usage does not match the canonical content attempt'); END;

CREATE TRIGGER content_drafts_contract
BEFORE INSERT ON content_drafts
WHEN NEW.draft_fingerprint IS NOT evidence_sha256_hex(NEW.draft_json)
 OR (NEW.attempt_no=1 AND NEW.rewrite_of_draft_fingerprint IS NOT NULL)
 OR (NEW.attempt_no=2 AND NOT EXISTS (
       SELECT 1 FROM content_drafts d
       WHERE d.content_id=NEW.content_id AND d.attempt_no=1
         AND d.draft_fingerprint=NEW.rewrite_of_draft_fingerprint
    ))
 OR NOT EXISTS (
    SELECT 1
    FROM content_writer_attempts wa
    JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
    JOIN content_writer_results wr ON wr.request_id=wa.request_id
    JOIN provider_attempts pa ON pa.request_id=wa.request_id
    JOIN content_items c ON c.id=wa.content_id
    WHERE wa.request_id=NEW.request_id AND wa.intent_id=NEW.intent_id
      AND wa.content_id=NEW.content_id AND wa.job_id=NEW.job_id
      AND wa.run_id=NEW.run_id AND wa.account_id=NEW.account_id
      AND wa.attempt_no=NEW.attempt_no AND wi.route_key=NEW.route_key
      AND wr.outcome='SUCCESS'
      AND wr.draft_fingerprint=NEW.draft_fingerprint
      AND pa.status='SETTLED' AND pa.actual_cost_usd>=0.0
      AND c.status IN ('RUNNING','REVISE')
      AND (SELECT count(*) FROM model_usage u
           WHERE u.request_id=NEW.request_id)=1
 )
BEGIN SELECT RAISE(ABORT, 'draft requires one settled canonical writer result'); END;

SELECT _nia_transactional_migration_failpoint('0023_provider_ready_writer');
INSERT INTO schema_migrations(version)
VALUES ('0023_provider_ready_writer');

COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
