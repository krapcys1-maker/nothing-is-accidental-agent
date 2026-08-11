-- 0033: paid content-role executions join the canonical global model ledger.
--
-- 0032 made ARTICLE_REVIEWER execution durable before the provider boundary,
-- but its settled usage lived only in role_provider_executions.  Daily/monthly
-- gates and runs.cost_usd are derived from model_usage, so that split ledger
-- understated real spend.  This migration admits exactly the terminal,
-- authority-bound role execution as the request identity for one real usage
-- row and makes that row immutable.

DROP TRIGGER model_usage_requires_request_job_run_relation;
DROP TRIGGER model_usage_request_job_run_relation_on_update;

CREATE TRIGGER model_usage_requires_request_job_run_relation
BEFORE INSERT ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT (
  EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    WHERE p.request_id=NEW.request_id
      AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
      AND j.run_id=NEW.run_id AND r.id=NEW.run_id
      AND r.account_id=j.account_id
  )
  OR EXISTS (
    SELECT 1
    FROM role_provider_executions e
    JOIN jobs j ON j.id=e.job_id
    JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
      AND e.cost_usd IS NOT NULL
      AND e.run_id=NEW.run_id
      AND r.account_id=j.account_id
  )
)
BEGIN SELECT RAISE(ABORT, 'new real model_usage requires request->job->run relation'); END;

CREATE TRIGGER model_usage_request_job_run_relation_on_update
BEFORE UPDATE OF run_id,request_id,dry_run,is_legacy_usage ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT (
  EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    WHERE p.request_id=NEW.request_id
      AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
      AND j.run_id=NEW.run_id AND r.id=NEW.run_id
      AND r.account_id=j.account_id
  )
  OR EXISTS (
    SELECT 1
    FROM role_provider_executions e
    JOIN jobs j ON j.id=e.job_id
    JOIN runs r ON r.id=e.run_id
    WHERE e.execution_ref=NEW.request_id
      AND e.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
      AND e.cost_usd IS NOT NULL
      AND e.run_id=NEW.run_id
      AND r.account_id=j.account_id
  )
)
BEGIN SELECT RAISE(ABORT, 'updated real model_usage requires request->job->run relation'); END;

CREATE TRIGGER model_usage_role_execution_contract
BEFORE INSERT ON model_usage
WHEN NEW.request_id IS NOT NULL
AND EXISTS (
  SELECT 1 FROM role_provider_executions
  WHERE execution_ref=NEW.request_id
)
AND NOT EXISTS (
  SELECT 1
  FROM role_provider_executions e
  WHERE e.execution_ref=NEW.request_id
    AND e.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
    AND e.cost_usd IS NOT NULL
    AND NEW.run_id=e.run_id
    AND NEW.provider=e.provider
    AND NEW.model=e.technical_model_id
    AND NEW.task=lower(e.logical_role)
    AND NEW.input_tokens=e.input_tokens
    AND NEW.output_tokens=e.output_tokens
    AND NEW.cache_read_tokens=e.cache_read_tokens
    AND NEW.cache_write_tokens=e.cache_write_tokens
    AND NEW.web_search_requests=e.web_search_requests
    AND printf('%.6f', NEW.estimated_cost_usd)=e.cost_usd
    AND NEW.dry_run=0 AND NEW.is_legacy_usage=0
)
BEGIN SELECT RAISE(ABORT, 'model_usage does not match terminal role execution'); END;

CREATE TRIGGER model_usage_role_execution_no_update
BEFORE UPDATE ON model_usage
WHEN OLD.request_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM role_provider_executions
  WHERE execution_ref=OLD.request_id
)
BEGIN SELECT RAISE(ABORT, 'role execution model_usage is immutable'); END;

CREATE TRIGGER model_usage_role_execution_no_delete
BEFORE DELETE ON model_usage
WHEN OLD.request_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM role_provider_executions
  WHERE execution_ref=OLD.request_id
)
BEGIN SELECT RAISE(ABORT, 'role execution model_usage cannot be deleted'); END;
