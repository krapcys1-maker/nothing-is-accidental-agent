-- WAVE C2: durable, completely offline article/Note preparation pipeline.
-- This migration is exercised on freshly initialized or explicitly migrated
-- non-production databases only. It adds no network, publication or approval UI.

-- C2 keeps the C1 payload shape but admits one additional, fake-only mode.
DROP TRIGGER jobs_content_contract;
CREATE TRIGGER jobs_content_contract
BEFORE INSERT ON jobs
WHEN NEW.kind='CONTENT' AND NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN research_cards rc ON rc.id=c.research_card_id
    WHERE c.id=json_extract(NEW.payload_json,'$.content_id')
      AND c.account_id=NEW.account_id
      AND c.research_card_id=json_extract(NEW.payload_json,'$.research_card_id')
      AND c.type=NEW.workflow
      AND c.status='DRAFT'
      AND c.job_id IS NULL
      AND fi.account_id=NEW.account_id
      AND fi.input_sha256=json_extract(NEW.payload_json,'$.frozen_input_sha256')
      AND fi.evidence_manifest_sha256=json_extract(NEW.payload_json,'$.evidence_manifest_sha256')
      AND json_extract(NEW.payload_json,'$.execution')='durable_content_foundation_v1'
      AND json_extract(NEW.payload_json,'$.execution_mode') IN (
          'FOUNDATION_ONLY','OFFLINE_PIPELINE'
      )
      AND json_extract(NEW.payload_json,'$.provider_enabled')=0
      AND NEW.topic_id=rc.topic_id
)
BEGIN SELECT RAISE(ABORT, 'CONTENT job does not match its frozen content input'); END;

CREATE TABLE content_plans (
    content_id INTEGER PRIMARY KEY REFERENCES content_items(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    plan_schema_version TEXT NOT NULL CHECK (length(trim(plan_schema_version)) BETWEEN 1 AND 100),
    route_config_version TEXT NOT NULL CHECK (length(trim(route_config_version)) BETWEEN 1 AND 100),
    route_config_fingerprint TEXT NOT NULL CHECK (
        length(route_config_fingerprint)=64
        AND route_config_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    frozen_input_sha256 TEXT NOT NULL CHECK (
        length(frozen_input_sha256)=64
        AND frozen_input_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    evidence_manifest_sha256 TEXT NOT NULL CHECK (
        length(evidence_manifest_sha256)=64
        AND evidence_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    plan_json TEXT NOT NULL CHECK (json_valid(plan_json)),
    plan_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(plan_fingerprint)=64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);

CREATE TRIGGER content_plans_contract
BEFORE INSERT ON content_plans
WHEN NEW.plan_fingerprint IS NOT evidence_sha256_hex(NEW.plan_json)
 OR NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN jobs j ON j.id=c.job_id
    WHERE c.id=NEW.content_id AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id
      AND c.research_card_id=NEW.research_card_id
      AND c.type=NEW.content_type AND c.status IN ('RUNNING','REVISE')
      AND cr.job_id=NEW.job_id AND cr.run_id=NEW.run_id
      AND fi.input_sha256=NEW.frozen_input_sha256
      AND fi.evidence_manifest_sha256=NEW.evidence_manifest_sha256
      AND j.kind='CONTENT'
      AND json_extract(j.payload_json,'$.execution_mode')='OFFLINE_PIPELINE'
 )
BEGIN SELECT RAISE(ABORT, 'content plan must bind the active frozen C2 execution'); END;
CREATE TRIGGER content_plans_no_update BEFORE UPDATE ON content_plans
BEGIN SELECT RAISE(ABORT, 'content_plans is append-only'); END;
CREATE TRIGGER content_plans_no_delete BEFORE DELETE ON content_plans
BEGIN SELECT RAISE(ABORT, 'content_plans is append-only'); END;

CREATE TABLE content_writer_intents (
    intent_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    call_mode TEXT NOT NULL CHECK (call_mode='FAKE'),
    route_key TEXT NOT NULL CHECK (route_key IN ('FABLE_5_ARTICLE','SONNET_5_NOTE')),
    route_config_version TEXT NOT NULL,
    route_config_fingerprint TEXT NOT NULL CHECK (
        length(route_config_fingerprint)=64
        AND route_config_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    provider_status TEXT NOT NULL CHECK (provider_status='UNVERIFIED'),
    api_model_id_status TEXT NOT NULL CHECK (api_model_id_status='UNVERIFIED'),
    availability_status TEXT NOT NULL CHECK (availability_status='UNVERIFIED'),
    pricing_status TEXT NOT NULL CHECK (pricing_status='UNVERIFIED'),
    plan_fingerprint TEXT NOT NULL REFERENCES content_plans(plan_fingerprint) ON DELETE RESTRICT,
    brief_sha256 TEXT NOT NULL REFERENCES content_article_briefs(brief_sha256) ON DELETE RESTRICT,
    frozen_input_sha256 TEXT NOT NULL,
    evidence_manifest_sha256 TEXT NOT NULL,
    style_profile_id TEXT NOT NULL,
    negative_style_profile_id TEXT NOT NULL,
    rewrite_of_draft_fingerprint TEXT,
    rewrite_feedback_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(rewrite_feedback_json)),
    max_cost_usd REAL NOT NULL CHECK (max_cost_usd=0.0),
    intent_json TEXT NOT NULL CHECK (json_valid(intent_json)),
    intent_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(intent_fingerprint)=64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,attempt_no),
    UNIQUE(job_id,attempt_no)
);

CREATE TRIGGER content_writer_intents_contract
BEFORE INSERT ON content_writer_intents
WHEN NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.intent_json)
 OR (NEW.content_type='ARTICLE' AND NEW.route_key!='FABLE_5_ARTICLE')
 OR (NEW.content_type='NOTE' AND NEW.route_key!='SONNET_5_NOTE')
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
BEGIN SELECT RAISE(ABORT, 'writer intent does not match the durable C2 execution'); END;
CREATE TRIGGER content_writer_intents_no_update BEFORE UPDATE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;
CREATE TRIGGER content_writer_intents_no_delete BEFORE DELETE ON content_writer_intents
BEGIN SELECT RAISE(ABORT, 'content_writer_intents is append-only'); END;

-- Strict 1:1 C2 extension of the pre-existing canonical provider ledger.
CREATE TABLE content_writer_attempts (
    request_id TEXT PRIMARY KEY
        REFERENCES provider_attempts(request_id) ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    intent_id TEXT NOT NULL UNIQUE REFERENCES content_writer_intents(intent_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK (stage='content_draft'),
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    call_mode TEXT NOT NULL CHECK (call_mode='FAKE'),
    provider TEXT NOT NULL CHECK (provider='fake-content-writer'),
    model TEXT NOT NULL CHECK (model IN ('FABLE_5_ARTICLE','SONNET_5_NOTE')),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,attempt_no),
    UNIQUE(job_id,attempt_no)
);

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
      AND wi.call_mode=NEW.call_mode AND wi.route_key=NEW.model
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
 )
BEGIN SELECT RAISE(ABORT, 'fake writer attempt does not match its intent'); END;
CREATE TRIGGER content_writer_attempts_no_update BEFORE UPDATE ON content_writer_attempts
BEGIN SELECT RAISE(ABORT, 'content_writer_attempts is append-only'); END;
CREATE TRIGGER content_writer_attempts_no_delete BEFORE DELETE ON content_writer_attempts
BEGIN SELECT RAISE(ABORT, 'content_writer_attempts is append-only'); END;

-- C1 globally disallowed attempt #2. C2 permits exactly one fake rewrite only
-- after attempt #1 has settled and the durable evaluations requested it.
DROP TRIGGER provider_attempts_no_retry_without_resolver;
CREATE TRIGGER provider_attempts_no_retry_without_resolver
BEFORE INSERT ON provider_attempts
WHEN NEW.attempt_no > 1
 AND EXISTS (SELECT 1 FROM provider_attempts p WHERE p.job_id=NEW.job_id AND p.stage=NEW.stage)
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

DROP TRIGGER provider_attempts_content_requires_extension;
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
        AND wi.call_mode='FAKE' AND wi.max_cost_usd=0.0
    )
)
BEGIN SELECT RAISE(ABORT, 'CONTENT provider attempt requires its exact 1:1 extension'); END;

DROP TRIGGER model_usage_content_attempt_contract;
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
        AND NEW.dry_run=1 AND NEW.estimated_cost_usd=0.0
        AND wi.intent_fingerprint=pa.execution_intent_fingerprint
    )
)
BEGIN SELECT RAISE(ABORT, 'model_usage does not match the canonical content attempt'); END;

CREATE TABLE content_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    request_id TEXT NOT NULL UNIQUE REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    intent_id TEXT NOT NULL UNIQUE REFERENCES content_writer_intents(intent_id) ON DELETE RESTRICT,
    route_key TEXT NOT NULL CHECK (route_key IN ('FABLE_5_ARTICLE','SONNET_5_NOTE')),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 300),
    body TEXT NOT NULL CHECK (length(trim(body))>0),
    evidence_ids_json TEXT NOT NULL CHECK (json_valid(evidence_ids_json)),
    unsupported_claims_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(unsupported_claims_json)),
    personal_experience INTEGER NOT NULL DEFAULT 0 CHECK (personal_experience IN (0,1)),
    style_ok INTEGER NOT NULL DEFAULT 1 CHECK (style_ok IN (0,1)),
    brief_compliant INTEGER NOT NULL DEFAULT 1 CHECK (brief_compliant IN (0,1)),
    rewrite_of_draft_fingerprint TEXT,
    draft_json TEXT NOT NULL CHECK (json_valid(draft_json)),
    draft_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(draft_fingerprint)=64 AND draft_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,attempt_no),
    UNIQUE(job_id,attempt_no)
);

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
    JOIN provider_attempts pa ON pa.request_id=wa.request_id
    JOIN content_items c ON c.id=wa.content_id
    WHERE wa.request_id=NEW.request_id AND wa.intent_id=NEW.intent_id
      AND wa.content_id=NEW.content_id AND wa.job_id=NEW.job_id
      AND wa.run_id=NEW.run_id AND wa.account_id=NEW.account_id
      AND wa.attempt_no=NEW.attempt_no AND wa.model=NEW.route_key
      AND pa.status='SETTLED' AND pa.actual_cost_usd=0.0
      AND c.status IN ('RUNNING','REVISE')
      AND (SELECT count(*) FROM model_usage u
           WHERE u.request_id=NEW.request_id AND u.dry_run=1
             AND u.estimated_cost_usd=0.0)=1
 )
BEGIN SELECT RAISE(ABORT, 'draft requires one settled zero-cost fake writer attempt'); END;
CREATE TRIGGER content_drafts_no_update BEFORE UPDATE ON content_drafts
BEGIN SELECT RAISE(ABORT, 'content_drafts is append-only'); END;
CREATE TRIGGER content_drafts_no_delete BEFORE DELETE ON content_drafts
BEGIN SELECT RAISE(ABORT, 'content_drafts is append-only'); END;

CREATE TABLE content_draft_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL REFERENCES content_drafts(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    evaluation_type TEXT NOT NULL CHECK (evaluation_type IN (
        'EVIDENCE_COVERAGE','UNSUPPORTED_CLAIMS','BRAND_TOPIC_POLICY',
        'STYLE_PROFILE','NEGATIVE_STYLE_PROFILE','CONTENT_TYPE_LENGTH',
        'FAKE_PERSONAL_EXPERIENCE','TITLE_HOOK_ALIGNMENT','BRIEF_COMPLIANCE'
    )),
    evaluator_version TEXT NOT NULL CHECK (length(trim(evaluator_version)) BETWEEN 1 AND 100),
    result TEXT NOT NULL CHECK (result IN ('PASS','FAIL')),
    score REAL CHECK (score IS NULL OR (
        typeof(score) IN ('integer','real') AND score=score AND score BETWEEN 0 AND 1
    )),
    findings_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(findings_json)),
    draft_fingerprint TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('PASS','REWRITE_ONCE','BLOCK')),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(draft_id,evaluation_type,evaluator_version),
    UNIQUE(content_id,attempt_no,evaluation_type,evaluator_version)
);
CREATE INDEX ix_content_draft_evaluations
    ON content_draft_evaluations(content_id,attempt_no,evaluation_type,decision);

CREATE TRIGGER content_draft_evaluations_contract
BEFORE INSERT ON content_draft_evaluations
WHEN NOT EXISTS (
    SELECT 1 FROM content_drafts d
    WHERE d.id=NEW.draft_id AND d.content_id=NEW.content_id
      AND d.job_id=NEW.job_id AND d.run_id=NEW.run_id
      AND d.attempt_no=NEW.attempt_no
      AND d.draft_fingerprint=NEW.draft_fingerprint
 )
 OR (NEW.result='PASS' AND NEW.decision!='PASS')
 OR (NEW.result='FAIL' AND NEW.decision='PASS')
BEGIN SELECT RAISE(ABORT, 'evaluation must bind its immutable draft and decision'); END;
CREATE TRIGGER content_draft_evaluations_no_update
BEFORE UPDATE ON content_draft_evaluations
BEGIN SELECT RAISE(ABORT, 'content_draft_evaluations is append-only'); END;
CREATE TRIGGER content_draft_evaluations_no_delete
BEFORE DELETE ON content_draft_evaluations
BEGIN SELECT RAISE(ABORT, 'content_draft_evaluations is append-only'); END;

-- The C1 transition remains the sole lifecycle terminalizer. This guard adds
-- the C2 completion precondition without creating a second terminal boundary.
CREATE TRIGGER content_c2_pending_approval_contract
BEFORE INSERT ON content_transition_commands
WHEN NEW.target_content_status='PENDING_APPROVAL'
 AND json_extract((SELECT payload_json FROM jobs WHERE id=NEW.job_id),
                  '$.execution_mode')='OFFLINE_PIPELINE'
 AND NOT EXISTS (
    SELECT 1
    FROM content_drafts d
    WHERE d.content_id=NEW.content_id
      AND d.draft_fingerprint=json_extract(NEW.final_result_json,'$.draft_fingerprint')
      AND d.title=(SELECT title FROM content_items WHERE id=NEW.content_id)
      AND d.body=(SELECT body FROM content_items WHERE id=NEW.content_id)
      AND (SELECT count(*) FROM content_draft_evaluations e
           WHERE e.draft_id=d.id AND e.result='PASS' AND e.decision='PASS')=9
      AND (SELECT count(*) FROM content_draft_evaluations e
           WHERE e.draft_id=d.id)=9
      AND (SELECT count(*) FROM content_drafts x
           WHERE x.content_id=NEW.content_id)<=2
 )
BEGIN SELECT RAISE(ABORT, 'C2 PENDING_APPROVAL requires one fully passing durable draft'); END;
