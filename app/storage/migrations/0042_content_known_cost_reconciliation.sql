-- Forward-only: the operator reconciliation floor learns the CONTENT lineage.
--
-- WHY THIS MIGRATION IS REQUIRED (proof, not assumption)
-- -----------------------------------------------------
-- A CONTENT provider attempt whose exact cost IS already durably recorded in
-- model_usage could not be terminalized at all.  Three triggers gate every
-- NEEDS_RECONCILIATION -> RECONCILED_SETTLED transition and each of them
-- structurally excludes CONTENT:
--
--   * provider_attempts_reconcile_requires_consistent_lineage (0036) admits only
--     j.kind='RESEARCH' or j.kind='TOPIC_GENERATION';
--   * provider_attempts_terminal_requires_terminal_lifecycle (0020) and
--     provider_attempts_terminal_requires_consistent_cost_cache (0020) admit the
--     same two kinds only.
--
-- A CONTENT/ARTICLE job has no research_runs row (its run lives in
-- content_runs), so the RESEARCH branches cannot match, and j.kind='CONTENT'
-- fails the enumerations outright.  The conservative 0040 ledger is not an
-- alternative: its CHECKs pin resolution='CONSERVATIVE_MAX_CHARGED',
-- conservative_cost_usd=reserved_amount_usd and actual_cost_usd IS NULL, so it
-- can only charge the reservation - which UNDERSTATES a known larger cost.
--
-- WHAT THIS MIGRATION DOES NOT CHANGE
-- -----------------------------------
-- The RESEARCH and TOPIC_GENERATION branches are reproduced verbatim from their
-- latest definitions (0036 and 0020).  Only a new CONTENT branch is added, in
-- exactly the way 0020 previously added TOPIC_GENERATION to the same triggers.
--
-- Costs still never live on the attempt.  RECONCILED_SETTLED keeps
-- actual_cost_usd NULL (0014 table CHECK and provider_attempts_controlled_transition)
-- and the canonical charge remains the pre-existing model_usage row.  The
-- reconciliation records THAT the known cost was charged, never a second copy
-- of the amount.

DROP TRIGGER provider_attempts_reconcile_requires_consistent_lineage;
CREATE TRIGGER provider_attempts_reconcile_requires_consistent_lineage
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   LEFT JOIN topic_generation_approvals a ON a.job_id=j.id
   LEFT JOIN source_discovery_approvals sa ON sa.job_id=j.id
   LEFT JOIN content_runs cr ON cr.run_id=j.run_id
   LEFT JOIN content_items ci ON ci.id=cr.content_id
   WHERE j.id=NEW.job_id
     AND (
       (j.kind='RESEARCH' AND j.workflow='RESEARCH'
        AND r.account_id=j.account_id AND r.workflow='RESEARCH'
        AND rr.account_id=j.account_id AND rr.topic_id=j.topic_id
        AND json_extract(j.payload_json,'$.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.topic_id')=j.topic_id
        AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.topic_id')=j.topic_id
        AND (
          rr.flow='single'
          OR
          (rr.flow='staged'
           AND json_extract(j.payload_json,'$.execution')=
               'article_research_source_discovery_v1'
           AND json_extract(j.payload_json,'$.dry_run')=0
           AND NEW.stage='research_discover' AND NEW.attempt_no=1
           AND NEW.request_id=NEW.job_id || ':research_discover:1'
           AND json_extract(j.payload_json,'$.execution_intent.provider')='anthropic'
           AND json_extract(j.payload_json,'$.execution_intent.model')='claude-opus-5'
           AND json_extract(j.payload_json,'$.execution_intent.fingerprint')=
               NEW.execution_intent_fingerprint
           AND sa.account_id=j.account_id AND sa.topic_id=j.topic_id
           AND sa.request_id=NEW.request_id AND sa.consumed_at IS NOT NULL
           AND lower(sa.provider)=
               json_extract(j.payload_json,'$.execution_intent.provider')
           AND sa.technical_model_id=
               json_extract(j.payload_json,'$.execution_intent.model')
           AND sa.intent_fingerprint=NEW.execution_intent_fingerprint)
        ))
       OR
       (j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
        AND j.topic_id IS NULL AND rr.id IS NULL
        AND r.account_id=j.account_id AND r.workflow='TOPIC_GENERATION'
        AND NEW.stage='topics' AND NEW.attempt_no=1
        AND NEW.request_id=NEW.job_id || ':topics:1'
        AND json_extract(j.payload_json,'$.execution')='durable_topic_generation_v1'
        AND json_extract(j.payload_json,'$.dry_run')=0
        AND json_extract(j.payload_json,'$.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.workflow')='TOPIC_GENERATION'
        AND json_extract(j.payload_json,'$.execution_intent.stage')='topics'
        AND json_type(j.payload_json,'$.execution_intent.topic_id') IS NULL
        AND a.account_id=j.account_id AND a.consumed_at IS NOT NULL
        AND a.intent_fingerprint=NEW.execution_intent_fingerprint
        AND a.execution_intent_json=json_extract(j.payload_json,'$.execution_intent'))
       OR
       -- CONTENT/ARTICLE known-cost lineage.  The run is a content run, never a
       -- research run, and the whole account/job/run/content relation must agree.
       -- Only the writer stage can hold a reconcilable CONTENT charge; reviewer
       -- executions settle in role_provider_executions, not here.
       (j.kind='CONTENT' AND j.workflow='ARTICLE'
        AND rr.id IS NULL
        AND r.account_id=j.account_id AND r.workflow='ARTICLE'
        AND cr.job_id=j.id AND cr.account_id=j.account_id
        AND cr.workflow='ARTICLE' AND cr.run_id=j.run_id
        AND ci.id=cr.content_id AND ci.job_id=j.id AND ci.run_id=j.run_id
        AND ci.account_id=j.account_id
        AND NEW.stage='content_draft'
        AND NEW.request_id=NEW.job_id || ':content_draft:' || NEW.attempt_no
        AND NEW.request_started_at IS NOT NULL)
     )
 )
BEGIN SELECT RAISE(ABORT, 'reconciled attempt requires a consistent supported lineage'); END;

DROP TRIGGER provider_attempts_terminal_requires_terminal_lifecycle;
CREATE TRIGGER provider_attempts_terminal_requires_terminal_lifecycle
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   LEFT JOIN content_runs cr ON cr.run_id=j.run_id
   LEFT JOIN content_items ci ON ci.id=cr.content_id
   WHERE j.id=NEW.job_id
     AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
     AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
     AND (
       (j.kind='RESEARCH' AND j.workflow='RESEARCH'
        AND (
          (NEW.reconciliation_resolution LIKE '%:EXECUTION_FAILED'
           AND j.status='FAILED' AND r.status='FAILED' AND rr.status='FAILED'
           AND rr.research_card_id IS NULL)
          OR
          (NEW.reconciliation_resolution LIKE '%:RESULT_ALREADY_FINALIZED'
           AND j.status='DONE' AND r.status='SUCCESS' AND rr.status='COMPLETE'
           AND rr.research_card_id IS NOT NULL)
        ))
       OR
       (j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
        AND j.topic_id IS NULL AND r.workflow='TOPIC_GENERATION'
        AND r.account_id=j.account_id AND rr.id IS NULL
        AND NEW.reconciliation_resolution LIKE '%:EXECUTION_FAILED'
        AND j.status='FAILED' AND r.status='FAILED'
        AND j.external_effect_started_at IS NULL
        AND NOT EXISTS (
          SELECT 1 FROM generated_topics g
          WHERE g.job_id=j.id OR g.run_id=j.run_id OR g.request_id=NEW.request_id
        ))
       OR
       -- CONTENT: a cost reconciliation terminalizes an execution that ALREADY
       -- failed.  It may only ever produce the failed lifecycle, so
       -- RESULT_ALREADY_FINALIZED is not offered here and the content item can
       -- never be carried to an approved or published state by this path.
       -- The run keeps the terminal failed state the overrun produced.  Its
       -- status/current_state are owned by the content transition contract
       -- (0039), so a cost reconciliation asserts that state instead of
       -- manufacturing a transition command.
       (j.kind='CONTENT' AND j.workflow='ARTICLE'
        AND rr.id IS NULL AND r.workflow='ARTICLE'
        AND r.account_id=j.account_id
        AND NEW.reconciliation_resolution='CHARGED_KNOWN:EXECUTION_FAILED'
        AND j.status IN ('NEEDS_VERIFICATION','FAILED')
        AND r.status IN ('STOPPED','FAILED')
        AND cr.job_id=j.id AND cr.run_id=j.run_id
        AND cr.status IN ('NEEDS_VERIFICATION','FAILED')
        AND ci.id=cr.content_id
        AND ci.status IN ('NEEDS_VERIFICATION','FAILED','REVISE','DRAFT'))
     )
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires a terminal consistent lifecycle'); END;

DROP TRIGGER provider_attempts_terminal_requires_consistent_cost_cache;
CREATE TRIGGER provider_attempts_terminal_requires_consistent_cost_cache
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND (
       (j.kind='RESEARCH'
        AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task IN
              ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005
        AND abs(rr.total_cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task IN
              ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005)
       OR
       (j.kind='TOPIC_GENERATION' AND rr.id IS NULL
        AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task='topics'),0)) < 0.0000005)
       OR
       -- CONTENT cost cache mirrors SqliteStorage._set_run_cost_from_content_usage
       -- exactly: writer usage on the content_draft task plus every settled role
       -- execution of the same run.  The cache must already equal the canonical
       -- ledger, so the reconciliation never re-adds the known charge.
       (j.kind='CONTENT' AND rr.id IS NULL
        AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id
                AND (u.task='content_draft' OR u.request_id IN (
                  SELECT e.execution_ref FROM role_provider_executions e
                  WHERE e.run_id=j.run_id))),0)) < 0.0000005)
     )
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires cost caches equal to the canonical ledger'); END;

-- A charged CONTENT reconciliation has exactly ONE canonical writer usage row,
-- bound to the same run and to the frozen writer identity.  The generic 0014
-- floor only proves that some canonical usage exists; this trigger proves it is
-- the right one, that there is exactly one, and that the operator is not
-- charging against a reviewer or foreign-run row.  It also forbids the
-- RECONCILED_RELEASED (NOT_CHARGED) direction for CONTENT: a writer attempt with
-- durable usage was charged by definition.
CREATE TRIGGER provider_attempts_content_reconcile_requires_usage_identity
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND EXISTS (SELECT 1 FROM jobs j WHERE j.id=NEW.job_id AND j.kind='CONTENT')
 AND NOT (
   NEW.status='RECONCILED_SETTLED'
   AND NEW.reconciliation_resolution='CHARGED_KNOWN:EXECUTION_FAILED'
   AND (SELECT count(*) FROM model_usage u
        WHERE u.request_id=NEW.request_id AND u.dry_run=0 AND u.is_legacy_usage=0)=1
   AND EXISTS (
     SELECT 1 FROM model_usage u
     JOIN jobs j ON j.id=NEW.job_id
     JOIN content_writer_results wr ON wr.request_id=NEW.request_id
     WHERE u.request_id=NEW.request_id AND u.run_id=j.run_id
       AND u.dry_run=0 AND u.is_legacy_usage=0
       AND u.task='content_draft'
       AND u.estimated_cost_usd > 0.0
       AND wr.job_id=j.id AND wr.run_id=j.run_id
       AND u.provider=wr.provider AND u.model=wr.api_model_id
   )
 )
BEGIN SELECT RAISE(ABORT, 'charged content reconciliation requires exactly one canonical writer usage identity'); END;
