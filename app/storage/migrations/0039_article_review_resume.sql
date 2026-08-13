-- Forward-only REVIEW-ONLY chain authority and execution ledger.
--
-- Production remains on 0038 until a separately authorised schema operation.
-- One L1 approval binds the complete conditional chain:
-- reviewer #1 -> optional canonical writer attempt #2 -> reviewer #2.

CREATE TABLE content_review_resume_approvals (
    approval_ref TEXT PRIMARY KEY CHECK (length(trim(approval_ref)) BETWEEN 1 AND 200),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE RESTRICT,
    source_draft_fingerprint TEXT NOT NULL CHECK (
        length(source_draft_fingerprint)=64
        AND source_draft_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    initial_review_execution_ref TEXT NOT NULL UNIQUE
        CHECK (length(trim(initial_review_execution_ref)) BETWEEN 1 AND 200),
    writer_execution_ref TEXT NOT NULL UNIQUE
        CHECK (length(trim(writer_execution_ref)) BETWEEN 1 AND 200),
    post_review_execution_ref TEXT NOT NULL UNIQUE
        CHECK (length(trim(post_review_execution_ref)) BETWEEN 1 AND 200),
    reviewer_provider TEXT NOT NULL CHECK (reviewer_provider='ANTHROPIC'),
    reviewer_model_id TEXT NOT NULL CHECK (reviewer_model_id='claude-opus-5'),
    writer_provider TEXT NOT NULL CHECK (writer_provider='ANTHROPIC'),
    writer_model_id TEXT NOT NULL CHECK (writer_model_id='claude-opus-5'),
    reviewer_max_output_tokens INTEGER NOT NULL CHECK (reviewer_max_output_tokens=8192),
    writer_max_output_tokens INTEGER NOT NULL CHECK (writer_max_output_tokens=8192),
    reviewer_max_cost_usd TEXT NOT NULL,
    writer_max_cost_usd TEXT NOT NULL,
    chain_cap_usd TEXT NOT NULL,
    daily_limit_usd TEXT NOT NULL,
    monthly_limit_usd TEXT NOT NULL,
    approved_by TEXT NOT NULL CHECK (length(trim(approved_by)) BETWEEN 1 AND 200),
    approved_at TEXT NOT NULL CHECK (length(approved_at)>=19),
    expires_at TEXT NOT NULL CHECK (length(expires_at)>=19 AND expires_at>approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at)>=19),
    approval_json TEXT NOT NULL CHECK (json_valid(approval_json)),
    approval_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(approval_fingerprint)=64
        AND approval_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    CHECK (initial_review_execution_ref!=post_review_execution_ref),
    CHECK (initial_review_execution_ref!=writer_execution_ref),
    CHECK (post_review_execution_ref!=writer_execution_ref),
    CHECK (CAST(reviewer_max_cost_usd AS REAL)>0),
    CHECK (CAST(writer_max_cost_usd AS REAL)>0),
    CHECK (CAST(chain_cap_usd AS REAL)>0),
    CHECK (CAST(daily_limit_usd AS REAL)>0),
    CHECK (CAST(monthly_limit_usd AS REAL)>0),
    CHECK (
      CAST(chain_cap_usd AS REAL) >=
      2*CAST(reviewer_max_cost_usd AS REAL)+CAST(writer_max_cost_usd AS REAL)
    )
);

CREATE TRIGGER content_review_resume_approvals_contract
BEFORE INSERT ON content_review_resume_approvals
WHEN NEW.consumed_at IS NOT NULL
 OR NEW.approval_fingerprint IS NOT evidence_sha256_hex(NEW.approval_json)
 OR json_extract(NEW.approval_json,'$.schema') IS NOT 'article_review_chain_approval_v1'
 OR json_extract(NEW.approval_json,'$.approval_ref') IS NOT NEW.approval_ref
 OR json_extract(NEW.approval_json,'$.job_id') IS NOT NEW.job_id
 OR json_extract(NEW.approval_json,'$.run_id') IS NOT NEW.run_id
 OR json_extract(NEW.approval_json,'$.content_id') IS NOT NEW.content_id
 OR json_extract(NEW.approval_json,'$.source_draft_fingerprint')
      IS NOT NEW.source_draft_fingerprint
 OR json_extract(NEW.approval_json,'$.initial_review_execution_ref')
      IS NOT NEW.initial_review_execution_ref
 OR json_extract(NEW.approval_json,'$.writer_execution_ref')
      IS NOT NEW.writer_execution_ref
 OR json_extract(NEW.approval_json,'$.post_review_execution_ref')
      IS NOT NEW.post_review_execution_ref
 OR json_extract(NEW.approval_json,'$.reviewer.provider') IS NOT NEW.reviewer_provider
 OR json_extract(NEW.approval_json,'$.reviewer.technical_model_id')
      IS NOT NEW.reviewer_model_id
 OR json_extract(NEW.approval_json,'$.reviewer.max_output_tokens')
      IS NOT NEW.reviewer_max_output_tokens
 OR json_extract(NEW.approval_json,'$.reviewer.max_cost_usd')
      IS NOT NEW.reviewer_max_cost_usd
 OR json_extract(NEW.approval_json,'$.reviewer.inference_config.thinking.type')
      IS NOT 'adaptive'
 OR (SELECT count(*) FROM json_each(
      json_extract(NEW.approval_json,'$.reviewer.inference_config.thinking')))!=1
 OR json_extract(NEW.approval_json,'$.reviewer.inference_config.output_config.effort')
      IS NOT 'low'
 OR json_extract(NEW.approval_json,'$.writer.provider') IS NOT NEW.writer_provider
 OR json_extract(NEW.approval_json,'$.writer.technical_model_id')
      IS NOT NEW.writer_model_id
 OR json_extract(NEW.approval_json,'$.writer.max_output_tokens')
      IS NOT NEW.writer_max_output_tokens
 OR json_extract(NEW.approval_json,'$.writer.max_cost_usd')
      IS NOT NEW.writer_max_cost_usd
 OR json_extract(NEW.approval_json,'$.writer.inference_config.thinking.type')
      IS NOT 'adaptive'
 OR (SELECT count(*) FROM json_each(
      json_extract(NEW.approval_json,'$.writer.inference_config.thinking')))!=1
 OR json_extract(NEW.approval_json,'$.writer.inference_config.output_config.effort')
      IS NOT 'high'
 OR json_extract(NEW.approval_json,'$.chain_cap_usd') IS NOT NEW.chain_cap_usd
 OR json_extract(NEW.approval_json,'$.daily_limit_usd') IS NOT NEW.daily_limit_usd
 OR json_extract(NEW.approval_json,'$.monthly_limit_usd') IS NOT NEW.monthly_limit_usd
 OR json_extract(NEW.approval_json,'$.max_retries') IS NOT 0
 OR json_extract(NEW.approval_json,'$.fallback_policy') IS NOT 'FORBIDDEN'
 OR json_extract(NEW.approval_json,'$.publication') IS NOT 'FORBIDDEN'
 OR NEW.writer_execution_ref IS NOT NEW.job_id || ':content_draft:2'
 OR EXISTS (
    SELECT 1 FROM content_writer_attempts
    WHERE content_id=NEW.content_id AND attempt_no=2
 )
 OR NOT EXISTS (
    SELECT 1 FROM content_items c
    JOIN jobs j ON j.id=c.job_id
    JOIN runs r ON r.id=c.run_id
    JOIN content_runs cr ON cr.run_id=c.run_id AND cr.content_id=c.id
    JOIN content_drafts d ON d.content_id=c.id AND d.attempt_no=1
    JOIN model_intent_bindings rb
      ON rb.intent_kind='content_role'
     AND rb.intent_id=j.id || ':ARTICLE_REVIEWER'
    JOIN model_intent_bindings wb
      ON wb.intent_kind='content_writer'
     AND wb.intent_id=j.id || ':content_writer'
    WHERE c.id=NEW.content_id AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.status IN ('FAILED','NEEDS_VERIFICATION')
      AND cr.status=c.status
      AND j.status IN ('FAILED','NEEDS_VERIFICATION')
      AND r.status IN ('FAILED','STOPPED')
      AND d.draft_fingerprint=NEW.source_draft_fingerprint
      AND rb.role='ARTICLE_REVIEWER'
      AND rb.provider=NEW.reviewer_provider
      AND rb.technical_model_id=NEW.reviewer_model_id
      AND rb.fallback_policy='FORBIDDEN'
      AND wb.role='ARTICLE_WRITER'
      AND wb.provider=NEW.writer_provider
      AND wb.technical_model_id=NEW.writer_model_id
      AND wb.fallback_policy='FORBIDDEN'
 )
BEGIN SELECT RAISE(ABORT, 'review resume approval must bind one exact terminal chain'); END;

CREATE TRIGGER content_review_resume_approvals_consume_once
BEFORE UPDATE ON content_review_resume_approvals
WHEN NOT (
    OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL
    AND NEW.approval_ref=OLD.approval_ref
    AND NEW.job_id=OLD.job_id AND NEW.run_id=OLD.run_id
    AND NEW.content_id=OLD.content_id
    AND NEW.source_draft_fingerprint=OLD.source_draft_fingerprint
    AND NEW.initial_review_execution_ref=OLD.initial_review_execution_ref
    AND NEW.writer_execution_ref=OLD.writer_execution_ref
    AND NEW.post_review_execution_ref=OLD.post_review_execution_ref
    AND NEW.reviewer_provider=OLD.reviewer_provider
    AND NEW.reviewer_model_id=OLD.reviewer_model_id
    AND NEW.writer_provider=OLD.writer_provider
    AND NEW.writer_model_id=OLD.writer_model_id
    AND NEW.reviewer_max_output_tokens=OLD.reviewer_max_output_tokens
    AND NEW.writer_max_output_tokens=OLD.writer_max_output_tokens
    AND NEW.reviewer_max_cost_usd=OLD.reviewer_max_cost_usd
    AND NEW.writer_max_cost_usd=OLD.writer_max_cost_usd
    AND NEW.chain_cap_usd=OLD.chain_cap_usd
    AND NEW.daily_limit_usd=OLD.daily_limit_usd
    AND NEW.monthly_limit_usd=OLD.monthly_limit_usd
    AND NEW.approved_by=OLD.approved_by
    AND NEW.approved_at=OLD.approved_at AND NEW.expires_at=OLD.expires_at
    AND NEW.approval_json=OLD.approval_json
    AND NEW.approval_fingerprint=OLD.approval_fingerprint
    AND NEW.created_at=OLD.created_at
)
BEGIN SELECT RAISE(ABORT, 'review resume approval is immutable and consumed once'); END;
CREATE TRIGGER content_review_resume_approvals_no_delete
BEFORE DELETE ON content_review_resume_approvals
BEGIN SELECT RAISE(ABORT, 'content_review_resume_approvals is append-only'); END;

CREATE TABLE content_review_resume_sessions (
    approval_ref TEXT PRIMARY KEY
        REFERENCES content_review_resume_approvals(approval_ref) ON DELETE RESTRICT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE RESTRICT,
    lease_owner TEXT NOT NULL CHECK (length(trim(lease_owner)) BETWEEN 1 AND 200),
    execution_generation INTEGER NOT NULL CHECK (execution_generation>0),
    lease_expires_at TEXT NOT NULL CHECK (length(lease_expires_at)>=19),
    source_content_status TEXT NOT NULL CHECK (
        source_content_status IN ('FAILED','NEEDS_VERIFICATION')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION')
    ),
    started_at TEXT NOT NULL CHECK (length(started_at)>=19),
    finished_at TEXT,
    CHECK (
      (status='ACTIVE' AND finished_at IS NULL)
      OR (status!='ACTIVE' AND finished_at IS NOT NULL)
    )
);
CREATE TRIGGER content_review_resume_sessions_insert_contract
BEFORE INSERT ON content_review_resume_sessions
WHEN NEW.status!='ACTIVE' OR NEW.finished_at IS NOT NULL OR NOT EXISTS (
  SELECT 1 FROM content_review_resume_approvals a
  JOIN jobs j ON j.id=a.job_id
  JOIN runs r ON r.id=a.run_id
  JOIN content_items c ON c.id=a.content_id
  JOIN content_runs cr ON cr.run_id=a.run_id AND cr.content_id=a.content_id
  WHERE a.approval_ref=NEW.approval_ref AND a.consumed_at IS NOT NULL
    AND a.job_id=NEW.job_id AND a.run_id=NEW.run_id AND a.content_id=NEW.content_id
    AND c.status=NEW.source_content_status AND cr.status=NEW.source_content_status
    AND j.status IN ('FAILED','NEEDS_VERIFICATION')
    AND r.status IN ('FAILED','STOPPED')
    AND NEW.execution_generation=j.execution_generation+1
)
BEGIN SELECT RAISE(ABORT, 'review resume session requires one consumed terminal chain'); END;
CREATE TRIGGER content_review_resume_sessions_settle_once
BEFORE UPDATE ON content_review_resume_sessions
WHEN NOT (
  OLD.status='ACTIVE' AND NEW.status IN ('PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION')
  AND NEW.finished_at IS NOT NULL
  AND NEW.approval_ref=OLD.approval_ref AND NEW.job_id=OLD.job_id
  AND NEW.run_id=OLD.run_id AND NEW.content_id=OLD.content_id
  AND NEW.lease_owner=OLD.lease_owner
  AND NEW.execution_generation=OLD.execution_generation
  AND NEW.lease_expires_at=OLD.lease_expires_at
  AND NEW.source_content_status=OLD.source_content_status
  AND NEW.started_at=OLD.started_at
)
BEGIN SELECT RAISE(ABORT, 'review resume session settles exactly once'); END;
CREATE TRIGGER content_review_resume_sessions_no_delete
BEFORE DELETE ON content_review_resume_sessions
BEGIN SELECT RAISE(ABORT, 'content_review_resume_sessions is append-only'); END;

-- Preserve the canonical writer-intent table and all of its checks.  The only
-- added admission is attempt 2 backed by this chain's exact durable
-- REWRITE_ONCE result instead of the superseded failed C2 evaluation set.
DROP TRIGGER content_writer_intents_contract;
CREATE TRIGGER content_writer_intents_contract
BEFORE INSERT ON content_writer_intents
WHEN NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.intent_json)
 OR (NEW.content_type='ARTICLE' AND NEW.route_key!='FABLE_5_ARTICLE')
 OR (NEW.content_type='NOTE' AND NEW.route_key!='SONNET_5_NOTE')
 OR (NEW.call_mode='FAKE' AND (
      NEW.provider!='UNVERIFIED' OR NEW.api_model_id!='UNVERIFIED'
      OR NEW.availability_status!='UNVERIFIED'
      OR NEW.pricing_profile!='UNVERIFIED' OR NEW.max_cost_usd!=0.0))
 OR (NEW.call_mode='PROVIDER_READY_OFFLINE' AND (
      NEW.provider='UNVERIFIED' OR NEW.api_model_id='UNVERIFIED'
      OR NEW.availability_status!='CONFIGURED'
      OR NEW.pricing_profile='UNVERIFIED' OR NEW.max_cost_usd!=0.0))
 OR (NEW.call_mode='CONTROLLED_PROVIDER' AND (
      NEW.provider='UNVERIFIED' OR NEW.api_model_id='UNVERIFIED'
      OR NEW.availability_status!='CONFIGURED'
      OR NEW.pricing_profile='UNVERIFIED' OR NEW.max_cost_usd<=0.0))
 OR (NEW.attempt_no=1 AND (
       NEW.rewrite_of_draft_fingerprint IS NOT NULL OR NEW.rewrite_feedback_json!='[]'))
 OR (NEW.attempt_no=2 AND NOT (
      EXISTS (
       SELECT 1 FROM content_drafts d
       JOIN content_draft_evaluations e ON e.draft_id=d.id
       JOIN content_items c ON c.id=d.content_id
       WHERE d.content_id=NEW.content_id AND d.attempt_no=1
         AND d.draft_fingerprint=NEW.rewrite_of_draft_fingerprint
         AND e.decision='REWRITE_ONCE' AND c.status='REVISE'
      )
      OR EXISTS (
       SELECT 1 FROM content_review_resume_sessions s
       JOIN content_review_resume_executions e ON e.approval_ref=s.approval_ref
       JOIN content_review_resume_approvals a ON a.approval_ref=s.approval_ref
       WHERE s.content_id=NEW.content_id AND s.job_id=NEW.job_id
         AND s.run_id=NEW.run_id AND s.status='ACTIVE'
         AND e.review_no=1 AND e.outcome='SUCCESS'
         AND json_extract(e.result_json,'$.decision')='REWRITE_ONCE'
         AND a.source_draft_fingerprint=NEW.rewrite_of_draft_fingerprint
         AND a.writer_execution_ref=NEW.job_id || ':content_draft:2'
         AND json_array_length(NEW.rewrite_feedback_json)>0
      )
    ))
 OR (NEW.intent_schema_version='provider_ready_writer_intent_v1' AND (
      json_extract(NEW.intent_json,'$.schema_version')!=NEW.intent_schema_version
      OR json_extract(NEW.intent_json,'$.call_mode')!=NEW.call_mode
      OR json_extract(NEW.intent_json,'$.route.route_key')!=NEW.route_key
      OR json_extract(NEW.intent_json,'$.route.provider')!=NEW.provider
      OR json_extract(NEW.intent_json,'$.route.api_model_id')!=NEW.api_model_id
      OR json_extract(NEW.intent_json,'$.route.availability')!=NEW.availability_status
      OR json_extract(NEW.intent_json,'$.route.pricing_profile')!=NEW.pricing_profile
      OR json_extract(NEW.intent_json,'$.prompt_fingerprint')!=NEW.prompt_fingerprint
      OR json_extract(NEW.intent_json,'$.limits.max_input_tokens')!=NEW.max_input_tokens
      OR json_extract(NEW.intent_json,'$.limits.max_context_tokens')!=NEW.max_context_tokens
      OR json_extract(NEW.intent_json,'$.limits.max_output_tokens')!=NEW.max_output_tokens
      OR json_extract(NEW.intent_json,'$.limits.timeout_seconds')!=NEW.timeout_seconds
      OR json_extract(NEW.intent_json,'$.limits.max_cost_usd')!=NEW.max_cost_usd))
 OR NOT EXISTS (
    SELECT 1 FROM content_items c
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
      AND b.brief_sha256=NEW.brief_sha256)
BEGIN SELECT RAISE(ABORT, 'writer intent does not match C3 or exact review resume'); END;

-- The shared provider ledger normally treats every attempt number above one
-- as a retry that needs reconciliation.  Canonical ARTICLE_WRITER attempt two
-- is the single deliberate exception: either the ordinary C3 evaluation or
-- this exact, settled review-chain decision must have requested REWRITE_ONCE.
DROP TRIGGER IF EXISTS provider_attempts_no_retry_without_resolver;
CREATE TRIGGER provider_attempts_no_retry_without_resolver
BEFORE INSERT ON provider_attempts
WHEN NEW.attempt_no > 1
 AND EXISTS (
   SELECT 1 FROM provider_attempts p
   WHERE p.job_id=NEW.job_id AND p.stage=NEW.stage
 )
 AND EXISTS (
   SELECT 1 FROM content_writer_attempts wa
   WHERE wa.request_id=NEW.request_id AND wa.job_id=NEW.job_id
     AND wa.stage=NEW.stage AND wa.attempt_no=NEW.attempt_no
 )
 AND NOT (
    NEW.attempt_no=2
    AND EXISTS (
        SELECT 1
        FROM content_writer_attempts wa
        JOIN content_writer_intents wi ON wi.intent_id=wa.intent_id
        JOIN provider_attempts p1
          ON p1.job_id=NEW.job_id AND p1.stage=NEW.stage AND p1.attempt_no=1
        WHERE wa.request_id=NEW.request_id AND wa.job_id=NEW.job_id
          AND wa.stage=NEW.stage AND wa.attempt_no=2
          AND wi.attempt_no=2 AND p1.status='SETTLED'
          AND (
            EXISTS (
                SELECT 1
                FROM content_drafts d
                JOIN content_draft_evaluations e ON e.draft_id=d.id
                WHERE d.request_id=p1.request_id AND e.decision='REWRITE_ONCE'
            )
            OR EXISTS (
                SELECT 1
                FROM content_review_resume_sessions s
                JOIN content_review_resume_executions re
                  ON re.approval_ref=s.approval_ref
                WHERE s.job_id=NEW.job_id AND s.status='ACTIVE'
                  AND re.review_no=1 AND re.outcome='SUCCESS'
                  AND json_extract(re.result_json,'$.decision')='REWRITE_ONCE'
            )
          )
    )
 )
BEGIN SELECT RAISE(ABORT, 'provider_attempt retry requires explicit reconciliation resolver'); END;

CREATE TABLE content_review_resume_executions (
    execution_ref TEXT PRIMARY KEY,
    approval_ref TEXT NOT NULL
        REFERENCES content_review_resume_approvals(approval_ref) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    draft_fingerprint TEXT NOT NULL CHECK (
        length(draft_fingerprint)=64 AND draft_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    writer_attempt_no INTEGER NOT NULL CHECK (writer_attempt_no IN (1,2)),
    review_no INTEGER NOT NULL CHECK (review_no IN (1,2)),
    request_intent_json TEXT NOT NULL CHECK (json_valid(request_intent_json)),
    request_intent_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(request_intent_fingerprint)=64
        AND request_intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    provider TEXT NOT NULL CHECK (provider='ANTHROPIC'),
    technical_model_id TEXT NOT NULL CHECK (technical_model_id='claude-opus-5'),
    returned_model_id TEXT,
    reserved_cost_usd TEXT NOT NULL CHECK (CAST(reserved_cost_usd AS REAL)>0),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('IN_FLIGHT','SUCCESS','FAILURE','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens>=0),
    output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens>=0),
    cache_read_tokens INTEGER CHECK (cache_read_tokens IS NULL OR cache_read_tokens>=0),
    cache_write_tokens INTEGER CHECK (cache_write_tokens IS NULL OR cache_write_tokens>=0),
    web_search_requests INTEGER CHECK (web_search_requests IS NULL OR web_search_requests>=0),
    cost_usd TEXT,
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    result_fingerprint TEXT UNIQUE,
    reserved_at TEXT NOT NULL CHECK (length(reserved_at)>=19),
    external_effect_started_at TEXT,
    settled_at TEXT,
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,review_no),
    CHECK (writer_attempt_no=review_no),
    CHECK (
      (outcome='IN_FLIGHT' AND failure_kind IS NULL AND returned_model_id IS NULL
       AND input_tokens IS NULL AND output_tokens IS NULL
       AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
       AND web_search_requests IS NULL AND cost_usd IS NULL
       AND result_json IS NULL AND result_fingerprint IS NULL AND settled_at IS NULL)
      OR
      (outcome IN ('SUCCESS','FAILURE') AND settled_at IS NOT NULL
       AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
       AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL
       AND web_search_requests IS NOT NULL AND cost_usd IS NOT NULL
       AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL)
      OR
      (outcome='NEEDS_VERIFICATION' AND failure_kind IS NOT NULL
       AND settled_at IS NOT NULL AND input_tokens IS NULL AND output_tokens IS NULL
       AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
       AND web_search_requests IS NULL AND cost_usd IS NULL
       AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL)
    )
);

CREATE TRIGGER content_review_resume_executions_contract
BEFORE INSERT ON content_review_resume_executions
WHEN NEW.outcome!='IN_FLIGHT'
 OR NEW.request_intent_fingerprint IS NOT evidence_sha256_hex(NEW.request_intent_json)
 OR json_extract(NEW.request_intent_json,'$.schema') IS NOT 'article_review_request_intent_v1'
 OR json_extract(NEW.request_intent_json,'$.execution_ref') IS NOT NEW.execution_ref
 OR json_extract(NEW.request_intent_json,'$.job_id') IS NOT NEW.job_id
 OR json_extract(NEW.request_intent_json,'$.run_id') IS NOT NEW.run_id
 OR json_extract(NEW.request_intent_json,'$.content_id') IS NOT NEW.content_id
 OR json_extract(NEW.request_intent_json,'$.draft_fingerprint') IS NOT NEW.draft_fingerprint
 OR json_extract(NEW.request_intent_json,'$.writer_attempt_no') IS NOT NEW.writer_attempt_no
 OR json_extract(NEW.request_intent_json,'$.review_no') IS NOT NEW.review_no
 OR json_extract(NEW.request_intent_json,'$.provider') IS NOT NEW.provider
 OR json_extract(NEW.request_intent_json,'$.technical_model_id') IS NOT NEW.technical_model_id
 OR json_extract(NEW.request_intent_json,'$.max_output_tokens') IS NOT 8192
 OR json_extract(NEW.request_intent_json,'$.timeout_seconds') IS NOT 300.0
 OR json_extract(NEW.request_intent_json,'$.streaming') IS NOT 1
 OR json_extract(NEW.request_intent_json,'$.max_retries') IS NOT 0
 OR json_extract(NEW.request_intent_json,'$.fallback_policy') IS NOT 'FORBIDDEN'
 OR json_extract(NEW.request_intent_json,'$.inference_config.thinking.type') IS NOT 'adaptive'
 OR (SELECT count(*) FROM json_each(
      json_extract(NEW.request_intent_json,'$.inference_config.thinking')))!=1
 OR json_extract(NEW.request_intent_json,'$.inference_config.output_config.effort') IS NOT 'low'
 OR NOT EXISTS (
    SELECT 1 FROM content_review_resume_approvals a
    JOIN content_drafts d ON d.content_id=a.content_id
    WHERE a.approval_ref=NEW.approval_ref AND a.consumed_at IS NOT NULL
      AND a.job_id=NEW.job_id AND a.run_id=NEW.run_id AND a.content_id=NEW.content_id
      AND d.attempt_no=NEW.writer_attempt_no
      AND d.draft_fingerprint=NEW.draft_fingerprint
      AND NEW.execution_ref=CASE NEW.review_no
        WHEN 1 THEN a.initial_review_execution_ref
        WHEN 2 THEN a.post_review_execution_ref END
      AND NEW.provider=a.reviewer_provider
      AND NEW.technical_model_id=a.reviewer_model_id
      AND CAST(NEW.reserved_cost_usd AS REAL)<=CAST(a.reviewer_max_cost_usd AS REAL)
      AND (NEW.review_no=1 OR EXISTS (
        SELECT 1 FROM content_review_resume_sessions s
        WHERE s.approval_ref=a.approval_ref AND s.status='ACTIVE'
      ))
 )
BEGIN SELECT RAISE(ABORT, 'review execution requires its exact chain stage'); END;

CREATE TRIGGER content_review_resume_executions_settle
BEFORE UPDATE ON content_review_resume_executions
WHEN NEW.execution_ref!=OLD.execution_ref OR NEW.approval_ref!=OLD.approval_ref
 OR NEW.job_id!=OLD.job_id OR NEW.run_id!=OLD.run_id
 OR NEW.content_id!=OLD.content_id OR NEW.draft_fingerprint!=OLD.draft_fingerprint
 OR NEW.writer_attempt_no!=OLD.writer_attempt_no OR NEW.review_no!=OLD.review_no
 OR NEW.request_intent_json!=OLD.request_intent_json
 OR NEW.request_intent_fingerprint!=OLD.request_intent_fingerprint
 OR NEW.provider!=OLD.provider OR NEW.technical_model_id!=OLD.technical_model_id
 OR NEW.reserved_cost_usd!=OLD.reserved_cost_usd
 OR NEW.reserved_at!=OLD.reserved_at OR NEW.created_at!=OLD.created_at
 OR NOT (
   (OLD.outcome='IN_FLIGHT' AND NEW.outcome='IN_FLIGHT'
    AND OLD.external_effect_started_at IS NULL
    AND NEW.external_effect_started_at IS NOT NULL
    AND NEW.result_json IS NULL AND NEW.settled_at IS NULL)
   OR
   (OLD.outcome='IN_FLIGHT'
    AND NEW.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
    AND NEW.external_effect_started_at IS OLD.external_effect_started_at
    AND NEW.settled_at IS NOT NULL
    AND NEW.result_json IS NOT NULL
    AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
    AND NOT (NEW.outcome='SUCCESS'
             AND NEW.returned_model_id!=NEW.technical_model_id))
 )
BEGIN SELECT RAISE(ABORT, 'review execution admits one effect stamp and settlement'); END;
CREATE TRIGGER content_review_resume_executions_no_delete
BEFORE DELETE ON content_review_resume_executions
BEGIN SELECT RAISE(ABORT, 'content_review_resume_executions is append-only'); END;

-- A terminal CONTENT job may be reopened exactly once only while the consumed
-- chain session is ACTIVE.  Normal content transitions remain command-owned.
DROP TRIGGER content_runs_closed_transition;
CREATE TRIGGER content_runs_closed_transition
BEFORE UPDATE OF status ON content_runs
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status='PREPARED' AND NEW.status IN ('RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status='RUNNING' AND NEW.status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status='REVISE' AND NEW.status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status IN ('FAILED','NEEDS_VERIFICATION') AND NEW.status='RUNNING'
        AND EXISTS (SELECT 1 FROM content_review_resume_sessions s
          WHERE s.run_id=OLD.run_id AND s.content_id=OLD.content_id
            AND s.job_id=OLD.job_id AND s.status='ACTIVE'))
)
BEGIN SELECT RAISE(ABORT, 'illegal content lifecycle transition'); END;

DROP TRIGGER content_items_closed_transition;
CREATE TRIGGER content_items_closed_transition
BEFORE UPDATE OF status ON content_items
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status='DRAFT' AND NEW.status='PREPARED')
    OR (OLD.status='PREPARED' AND NEW.status IN ('RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status='RUNNING' AND NEW.status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status='REVISE' AND NEW.status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'))
    OR (OLD.status IN ('FAILED','NEEDS_VERIFICATION') AND NEW.status='RUNNING'
        AND EXISTS (SELECT 1 FROM content_review_resume_sessions s
          WHERE s.content_id=OLD.id AND s.run_id=OLD.run_id
            AND s.job_id=OLD.job_id AND s.status='ACTIVE'))
    OR (OLD.status='PENDING_APPROVAL' AND NEW.status IN ('APPROVED','REJECTED')
        AND EXISTS (SELECT 1 FROM autonomous_decisions ad
          WHERE ad.content_id=OLD.id AND ad.job_id=OLD.job_id AND ad.run_id=OLD.run_id
            AND ad.lifecycle_status=NEW.status AND ad.reason_code=NEW.reason_code
            AND ad.decision_json=NEW.final_result_json AND ad.score IS NEW.score
            AND ad.applied=1))
)
BEGIN SELECT RAISE(ABORT, 'illegal content item lifecycle transition'); END;

DROP TRIGGER content_runs_require_transition_command;
CREATE TRIGGER content_runs_require_transition_command
BEFORE UPDATE OF status,reason_code,final_result_json,score,updated_at,finished_at
ON content_runs
WHEN (
    NEW.status IS NOT OLD.status OR NEW.reason_code IS NOT OLD.reason_code
    OR NEW.final_result_json IS NOT OLD.final_result_json OR NEW.score IS NOT OLD.score
    OR NEW.finished_at IS NOT OLD.finished_at
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.run_id AND cmd.job_id=OLD.job_id
      AND cmd.content_id=OLD.content_id AND cmd.source_content_status=OLD.status
      AND cmd.target_content_status=NEW.status AND cmd.reason_code IS NEW.reason_code
      AND cmd.final_result_json IS NEW.final_result_json AND cmd.score IS NEW.score
      AND cmd.created_at=NEW.updated_at AND cmd.applied=0
)
AND NOT (
  OLD.status IN ('FAILED','NEEDS_VERIFICATION') AND NEW.status='RUNNING'
  AND NEW.reason_code IS NULL AND NEW.final_result_json IS NULL
  AND NEW.score IS NULL AND NEW.finished_at IS NULL
  AND EXISTS (SELECT 1 FROM content_review_resume_sessions s
    WHERE s.run_id=OLD.run_id AND s.content_id=OLD.content_id
      AND s.job_id=OLD.job_id AND s.status='ACTIVE' AND s.started_at=NEW.updated_at)
)
BEGIN SELECT RAISE(ABORT, 'content_runs may change only through a transition command or review resume'); END;

DROP TRIGGER content_items_require_transition_command;
CREATE TRIGGER content_items_require_transition_command
BEFORE UPDATE OF status,reason_code,final_result_json,score,updated_at
ON content_items
WHEN OLD.run_id IS NOT NULL
AND (
    NEW.status IS NOT OLD.status OR NEW.reason_code IS NOT OLD.reason_code
    OR NEW.final_result_json IS NOT OLD.final_result_json OR NEW.score IS NOT OLD.score
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.run_id AND cmd.job_id=OLD.job_id AND cmd.content_id=OLD.id
      AND cmd.source_content_status=OLD.status AND cmd.target_content_status=NEW.status
      AND cmd.reason_code IS NEW.reason_code AND cmd.final_result_json IS NEW.final_result_json
      AND cmd.score IS NEW.score AND cmd.created_at=NEW.updated_at AND cmd.applied=0
)
AND NOT EXISTS (
    SELECT 1 FROM autonomous_decisions ad
    WHERE ad.content_id=OLD.id AND ad.job_id=OLD.job_id AND ad.run_id=OLD.run_id
      AND OLD.status='PENDING_APPROVAL' AND ad.lifecycle_status=NEW.status
      AND ad.reason_code=NEW.reason_code AND ad.decision_json=NEW.final_result_json
      AND ad.score IS NEW.score AND ad.created_at=NEW.updated_at AND ad.applied=1
)
AND NOT (
  OLD.status IN ('FAILED','NEEDS_VERIFICATION') AND NEW.status='RUNNING'
  AND NEW.reason_code IS NULL AND NEW.final_result_json IS NULL AND NEW.score IS NULL
  AND EXISTS (SELECT 1 FROM content_review_resume_sessions s
    WHERE s.content_id=OLD.id AND s.run_id=OLD.run_id AND s.job_id=OLD.job_id
      AND s.status='ACTIVE' AND s.started_at=NEW.updated_at)
)
BEGIN SELECT RAISE(ABORT, 'content_items requires a transition command, decision or review resume'); END;

DROP TRIGGER runs_content_require_transition_command;
CREATE TRIGGER runs_content_require_transition_command
BEFORE UPDATE OF status,current_state,finished_at,error ON runs
WHEN EXISTS (SELECT 1 FROM content_runs cr WHERE cr.run_id=OLD.id)
AND (
    NEW.status IS NOT OLD.status OR NEW.current_state IS NOT OLD.current_state
    OR NEW.finished_at IS NOT OLD.finished_at OR NEW.error IS NOT OLD.error
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.id AND cmd.target_run_status=NEW.status
      AND cmd.target_content_status=NEW.current_state
      AND cmd.created_at=NEW.finished_at AND cmd.applied=0
)
AND NOT (
  OLD.status IN ('FAILED','STOPPED') AND NEW.status='RUNNING'
  AND NEW.current_state='RUNNING' AND NEW.finished_at IS NULL AND NEW.error IS NULL
  AND EXISTS (SELECT 1 FROM content_review_resume_sessions s
    WHERE s.run_id=OLD.id AND s.status='ACTIVE')
)
BEGIN SELECT RAISE(ABORT, 'content run may change only through a transition command or review resume'); END;

DROP INDEX ux_content_one_terminal_command;
CREATE UNIQUE INDEX ux_content_one_terminal_command
    ON content_transition_commands(run_id,execution_generation)
    WHERE target_content_status IN ('SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION');

DROP TRIGGER content_c2_pending_approval_contract;
CREATE TRIGGER content_c2_pending_approval_contract
BEFORE INSERT ON content_transition_commands
WHEN NEW.target_content_status='PENDING_APPROVAL'
 AND json_extract((SELECT payload_json FROM jobs WHERE id=NEW.job_id),
                  '$.execution_mode') IN ('OFFLINE_PIPELINE','CONTROLLED_PROVIDER_PIPELINE')
 AND NOT EXISTS (
    SELECT 1 FROM content_drafts d
    WHERE d.content_id=NEW.content_id
      AND d.draft_fingerprint=json_extract(NEW.final_result_json,'$.draft_fingerprint')
      AND d.title=(SELECT title FROM content_items WHERE id=NEW.content_id)
      AND d.body=(SELECT body FROM content_items WHERE id=NEW.content_id)
      AND (SELECT count(*) FROM content_draft_evaluations e WHERE e.draft_id=d.id)=9
      AND (SELECT count(DISTINCT e.evaluation_type)
           FROM content_draft_evaluations e WHERE e.draft_id=d.id)=9
      AND (SELECT count(*) FROM content_drafts x WHERE x.content_id=NEW.content_id)<=2
      AND (
        (SELECT count(*) FROM content_draft_evaluations e
         WHERE e.draft_id=d.id AND e.result='PASS' AND e.decision='PASS')=9
        OR EXISTS (
          SELECT 1 FROM autonomous_decisions ad
          WHERE ad.content_id=NEW.content_id AND ad.job_id=NEW.job_id
            AND ad.run_id=NEW.run_id AND ad.draft_id=d.id
            AND ad.outcome='REJECTED' AND ad.applied=0
        )
      )
 )
 AND NOT EXISTS (
    SELECT 1 FROM content_review_resume_sessions s
    JOIN content_review_resume_executions e ON e.approval_ref=s.approval_ref
    JOIN content_drafts d ON d.content_id=s.content_id AND d.attempt_no=1
    WHERE s.job_id=NEW.job_id AND s.run_id=NEW.run_id
      AND s.content_id=NEW.content_id AND s.status='ACTIVE'
      AND s.execution_generation=NEW.execution_generation
      AND e.review_no=1 AND e.outcome='SUCCESS'
      AND json_extract(e.result_json,'$.decision')='APPROVE'
      AND d.draft_fingerprint=json_extract(NEW.final_result_json,'$.draft_fingerprint')
      AND d.title=(SELECT title FROM content_items WHERE id=NEW.content_id)
      AND d.body=(SELECT body FROM content_items WHERE id=NEW.content_id)
      AND json_array_length(json_extract(e.result_json,'$.entries'))>0
      AND NOT EXISTS (
        SELECT 1 FROM json_each(json_extract(e.result_json,'$.entries')) x
        WHERE json_extract(x.value,'$.outcome')!='PASS'
      )
 )
BEGIN SELECT RAISE(ABORT, 'PENDING_APPROVAL requires evaluated C2 or exact review-only approval'); END;

-- Review-resume requests join the canonical usage ledger only after a known
-- settlement.  Unknown transport outcomes intentionally retain NULL cost.
DROP TRIGGER model_usage_requires_request_job_run_relation;
DROP TRIGGER model_usage_request_job_run_relation_on_update;
CREATE TRIGGER model_usage_requires_request_job_run_relation
BEFORE INSERT ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT (
  EXISTS (
    SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    WHERE p.request_id=NEW.request_id
      AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
      AND j.run_id=NEW.run_id AND r.id=NEW.run_id AND r.account_id=j.account_id
  ) OR EXISTS (
    SELECT 1 FROM role_provider_executions e JOIN jobs j ON j.id=e.job_id
    JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
      AND e.cost_usd IS NOT NULL AND e.run_id=NEW.run_id AND r.account_id=j.account_id
  ) OR EXISTS (
    SELECT 1 FROM content_review_resume_executions e
    JOIN jobs j ON j.id=e.job_id JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE') AND e.cost_usd IS NOT NULL
      AND e.run_id=NEW.run_id AND r.account_id=j.account_id
  )
)
BEGIN SELECT RAISE(ABORT, 'new real model_usage requires request->job->run relation'); END;
CREATE TRIGGER model_usage_request_job_run_relation_on_update
BEFORE UPDATE OF run_id,request_id,dry_run,is_legacy_usage ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT (
  EXISTS (
    SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    WHERE p.request_id=NEW.request_id
      AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
      AND j.run_id=NEW.run_id AND r.id=NEW.run_id AND r.account_id=j.account_id
  ) OR EXISTS (
    SELECT 1 FROM role_provider_executions e JOIN jobs j ON j.id=e.job_id
    JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
      AND e.cost_usd IS NOT NULL AND e.run_id=NEW.run_id AND r.account_id=j.account_id
  ) OR EXISTS (
    SELECT 1 FROM content_review_resume_executions e
    JOIN jobs j ON j.id=e.job_id JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE') AND e.cost_usd IS NOT NULL
      AND e.run_id=NEW.run_id AND r.account_id=j.account_id
  )
)
BEGIN SELECT RAISE(ABORT, 'updated real model_usage requires request->job->run relation'); END;
CREATE TRIGGER model_usage_review_resume_contract
BEFORE INSERT ON model_usage
WHEN NEW.request_id IS NOT NULL
AND EXISTS (SELECT 1 FROM content_review_resume_executions WHERE execution_ref=NEW.request_id)
AND NOT EXISTS (
  SELECT 1 FROM content_review_resume_executions e
  WHERE e.execution_ref=NEW.request_id
    AND e.outcome IN ('SUCCESS','FAILURE') AND e.cost_usd IS NOT NULL
    AND NEW.run_id=e.run_id AND NEW.provider=e.provider
    AND NEW.model=e.technical_model_id AND NEW.task='article_reviewer_resume'
    AND NEW.input_tokens=e.input_tokens AND NEW.output_tokens=e.output_tokens
    AND NEW.cache_read_tokens=e.cache_read_tokens
    AND NEW.cache_write_tokens=e.cache_write_tokens
    AND NEW.web_search_requests=e.web_search_requests
    AND printf('%.6f',NEW.estimated_cost_usd)=e.cost_usd
    AND NEW.dry_run=0 AND NEW.is_legacy_usage=0
)
BEGIN SELECT RAISE(ABORT, 'model_usage does not match review resume execution'); END;
CREATE TRIGGER model_usage_review_resume_no_update
BEFORE UPDATE ON model_usage
WHEN OLD.request_id IS NOT NULL
 AND EXISTS (SELECT 1 FROM content_review_resume_executions WHERE execution_ref=OLD.request_id)
BEGIN SELECT RAISE(ABORT, 'review resume model_usage is immutable'); END;
CREATE TRIGGER model_usage_review_resume_no_delete
BEFORE DELETE ON model_usage
WHEN OLD.request_id IS NOT NULL
 AND EXISTS (SELECT 1 FROM content_review_resume_executions WHERE execution_ref=OLD.request_id)
BEGIN SELECT RAISE(ABORT, 'review resume model_usage cannot be deleted'); END;
