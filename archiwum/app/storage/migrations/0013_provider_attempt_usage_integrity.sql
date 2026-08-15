-- WAVE 0B closeout: every runtime durable attempt stores the canonical hash of
-- its request-affecting execution intent. Historical rows can remain NULL:
-- they predate durable_provider_v2 and must not be fabricated retroactively.
ALTER TABLE provider_attempts
    ADD COLUMN execution_intent_fingerprint TEXT;

CREATE TRIGGER provider_attempts_execution_intent_fingerprint_is_immutable
BEFORE UPDATE OF execution_intent_fingerprint ON provider_attempts
WHEN NEW.execution_intent_fingerprint IS NOT OLD.execution_intent_fingerprint
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt execution intent fingerprint is immutable');
END;

CREATE TRIGGER provider_attempts_durable_v2_requires_execution_intent_fingerprint
BEFORE INSERT ON provider_attempts
WHEN json_extract((SELECT payload_json FROM jobs WHERE id = NEW.job_id), '$.execution')
         = 'durable_provider_v2'
  AND (
      NEW.execution_intent_fingerprint IS NULL
      OR length(NEW.execution_intent_fingerprint) != 64
      OR NEW.execution_intent_fingerprint GLOB '*[^0-9a-f]*'
  )
BEGIN
    SELECT RAISE(ABORT, 'durable_provider_v2 attempt requires immutable execution intent fingerprint');
END;

-- A non-legacy real usage is evidence of a provider request. SQLite cannot
-- express this relation as a normal foreign key because request_id is a unique
-- alternate key, so the durable integrity rule lives in this DB-level trigger.
-- It also protects DELETE jobs: the provider_attempt FK cascade reaches this
-- trigger and therefore cannot silently orphan a non-legacy usage row.
CREATE TRIGGER provider_attempts_no_delete_with_nonlegacy_usage
BEFORE DELETE ON provider_attempts
WHEN EXISTS (
    SELECT 1
    FROM model_usage u
    WHERE u.request_id = OLD.request_id
      AND u.dry_run = 0
      AND u.is_legacy_usage = 0
)
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt is referenced by non-legacy model_usage');
END;
