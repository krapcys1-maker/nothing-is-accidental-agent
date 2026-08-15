-- Extend the existing operator-only reconciliation floor to the exact typed
-- ARTICLE_RESEARCH A1 lineage.  All other research and topic-generation
-- contracts remain unchanged.

DROP TRIGGER IF EXISTS provider_attempts_reconcile_requires_consistent_lineage;

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
     )
 )
BEGIN SELECT RAISE(ABORT, 'reconciled attempt requires a consistent supported lineage'); END;
