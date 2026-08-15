-- 0042: owner conservative adjudication reaches ambiguous RESEARCH attempts.
--
-- The 0040 ledger was built during a CONTENT incident and its trigger therefore
-- requires content_writer_results, content_writer_intents and content_items to
-- exist for the attempt.  A RESEARCH provider attempt has none of those rows, so
-- an ARTICLE_RESEARCH synthesis whose outcome is unknown could never be
-- adjudicated at all.  On 2026-08-14 two such attempts (topics 96 and 82) each
-- retained a live reservation with no usage row, and because
-- NEEDS_VERIFICATION_PRESENT counts unresolved exposure, one of them closed the
-- controlled-live gate for every topic in the account until a human read the
-- provider console.  The policy is unchanged - the owner books the exact full
-- retained reservation and actual_cost_usd stays NULL - only its reach widens.
--
-- The CONTENT branch below is preserved verbatim.  The trigger aborts only when
-- NEITHER shape matches.
DROP TRIGGER conservative_content_reconciliations_provider_source;
CREATE TRIGGER conservative_content_reconciliations_provider_source
BEFORE INSERT ON conservative_content_reconciliations
WHEN NEW.source_type = 'PROVIDER_ATTEMPT' AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id = p.job_id
    JOIN runs r ON r.id = j.run_id
    JOIN content_writer_results wr ON wr.request_id = p.request_id
    JOIN content_writer_intents wi ON wi.intent_id = wr.intent_id
    JOIN content_items c ON c.id = wr.content_id
    WHERE p.request_id = NEW.source_identity
      AND p.job_id = NEW.job_id
      AND p.status = 'NEEDS_RECONCILIATION'
      AND p.request_started_at IS NOT NULL
      AND p.actual_cost_usd IS NULL
      AND j.kind = 'CONTENT' AND j.workflow = 'ARTICLE'
      AND j.run_id = NEW.run_id AND r.id = NEW.run_id
      AND c.id = NEW.content_id AND c.job_id = j.id AND c.run_id = r.id
      AND wr.job_id = j.id AND wr.run_id = r.id
      AND wi.job_id = j.id AND wi.run_id = r.id AND wi.content_id = c.id
      AND wi.attempt_no = p.attempt_no
      AND wi.intent_fingerprint = p.execution_intent_fingerprint
      AND wr.provider = NEW.provider AND wr.api_model_id = NEW.model
      AND printf('%.6f', p.reserved_amount_usd) = NEW.reserved_amount_usd
      AND NEW.previous_status = 'NEEDS_RECONCILIATION'
      AND NOT EXISTS (
          SELECT 1 FROM model_usage u
          WHERE u.request_id = p.request_id
      )
) AND NOT EXISTS (
    -- RESEARCH attempt.  Identity is the job, its run and the frozen execution
    -- intent, because no content row exists to bind.  content_id must be NULL
    -- so a research adjudication can never claim a content effect.
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id = p.job_id
    JOIN runs r ON r.id = j.run_id
    WHERE p.request_id = NEW.source_identity
      AND p.job_id = NEW.job_id
      AND p.status = 'NEEDS_RECONCILIATION'
      AND p.request_started_at IS NOT NULL
      AND p.actual_cost_usd IS NULL
      AND j.kind = 'RESEARCH' AND j.workflow = 'RESEARCH'
      AND j.run_id = NEW.run_id AND r.id = NEW.run_id
      AND NEW.content_id IS NULL
      AND NEW.provider = json_extract(j.payload_json, '$.execution_intent.provider')
      AND NEW.model = json_extract(j.payload_json, '$.execution_intent.model')
      AND printf('%.6f', p.reserved_amount_usd) = NEW.reserved_amount_usd
      AND NEW.previous_status = 'NEEDS_RECONCILIATION'
      AND NOT EXISTS (
          SELECT 1 FROM model_usage u
          WHERE u.request_id = p.request_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'unsupported or non-ambiguous provider attempt');
END;
