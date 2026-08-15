-- Forward-only: the durable floor learns what APPROVE now means.
--
-- 0039 let a review-only APPROVE reach PENDING_APPROVAL when every segment
-- entry passed.  The first real REVIEW-ONLY live proved that is not the same
-- as a good article: all 29 body segments passed while the title promised an
-- arithmetic the body never explained.  The reviewer contract now also returns
-- a whole-article verdict, so the storage floor must require it too — otherwise
-- the old, weaker meaning of APPROVE survives at the layer that matters most.
--
-- Only the review-only branch of the existing trigger changes.  The C2
-- evaluation branch above it is reproduced verbatim.
--
-- CANONICAL ENTRY CONTRACT v3
-- ---------------------------
-- The application-side rule lives in
-- ``app/content/quality_gate.classification_contract_error`` plus the parser's
-- JSON type checks.  Two persistent boundaries now carry the SAME rule, because
-- an earlier fix lived only in the application layers: the public
-- ``settle_content_review_resume_execution`` wrote its payload verbatim and the
-- PENDING_APPROVAL trigger inspected only ``outcome='PASS'``, so a caller that
-- skipped the parser could store decision=APPROVE over entries classified
-- ARGUMENT_OR_INFERENCE with contains_external_fact=true.
--
-- The clause below is reproduced byte-identically in both triggers (only the
-- row reference differs).  Semantics, matching the application contract:
--   * reviewer_version is exactly production_article_reviewer_opus_v3
--   * entries is a non-empty JSON array of JSON objects
--   * classification and outcome are JSON text; outcome is PASS or BLOCK
--   * evidence_ids is a JSON array; contains_external_fact is a JSON boolean
--   * EVIDENCE_GROUNDED_FACT cites at least one id unless it is a BLOCK
--   * ARGUMENT_OR_INFERENCE / NON_FACTUAL_PROSE cite nothing and are JSON false
--   * any other classification is rejected
-- Every per-entry test is wrapped in ``IS NOT 1`` so a missing or wrong-typed
-- field yields NULL and therefore fails closed rather than passing silently.

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
      -- >>> CANONICAL ENTRY CONTRACT v3 >>>
      AND json_extract(e.result_json,'$.reviewer_version')='production_article_reviewer_opus_v3'
      AND json_type(e.result_json,'$.entries')='array'
      AND json_array_length(json_extract(e.result_json,'$.entries'))>0
      AND NOT EXISTS (
        SELECT 1 FROM json_each(CASE WHEN json_type(e.result_json,'$.entries')='array'
               THEN json_extract(e.result_json,'$.entries') ELSE json_array() END) y
        WHERE (
          json_type(y.value)='object'
          AND (SELECT count(*) FROM json_each(y.value))=7
          AND (SELECT count(*) FROM json_each(y.value) k WHERE k.key IN (
                'segment_id','segment_fingerprint','classification','evidence_ids',
                'reason','outcome','contains_external_fact'))=7
          AND json_type(y.value,'$.segment_id')='text'
          AND length(json_extract(y.value,'$.segment_id'))>0
          AND json_type(y.value,'$.segment_fingerprint')='text'
          AND length(json_extract(y.value,'$.segment_fingerprint'))>0
          AND json_type(y.value,'$.classification')='text'
          AND json_type(y.value,'$.outcome')='text'
          AND json_extract(y.value,'$.outcome') IN ('PASS','BLOCK')
          AND json_type(y.value,'$.evidence_ids')='array'
          AND NOT EXISTS (
            SELECT 1 FROM json_each(CASE
              WHEN json_type(y.value,'$.evidence_ids')='array'
              THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END) ev
            WHERE ev.type!='text' OR length(ev.value)=0
          )
          AND json_type(y.value,'$.reason')='text'
          AND length(trim(json_extract(y.value,'$.reason')))>0
          AND json_extract(y.value,'$.reason')=
              trim(json_extract(y.value,'$.reason'))
          AND json_type(y.value,'$.contains_external_fact') IN ('true','false')
          AND (
            (json_extract(y.value,'$.classification')='EVIDENCE_GROUNDED_FACT'
             AND json_type(y.value,'$.contains_external_fact')='true'
             AND (json_array_length(CASE WHEN json_type(y.value,'$.evidence_ids')='array'
                    THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END)>0
                  OR json_extract(y.value,'$.outcome')='BLOCK'))
            OR
            (json_extract(y.value,'$.classification') IN
               ('ARGUMENT_OR_INFERENCE','NON_FACTUAL_PROSE')
             AND json_array_length(CASE WHEN json_type(y.value,'$.evidence_ids')='array'
                    THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END)=0
             AND json_type(y.value,'$.contains_external_fact')='false')
          )
        ) IS NOT 1
      )
      AND (SELECT count(DISTINCT json_extract(v.value,'$.segment_id'))
           FROM json_each(json_extract(e.result_json,'$.entries')) v)
          =json_array_length(json_extract(e.result_json,'$.entries'))
      -- <<< CANONICAL ENTRY CONTRACT v3 <<<
      -- The whole-article verdict must exist and must be the exact canonical
      -- v3 document.  Counting six keys and testing value!=1 was not enough:
      -- six arbitrary names satisfied the count, and SQLite reports JSON true
      -- as the integer 1, so a literal 1 (or any truthy number) passed too.
      -- Names and JSON types are therefore both pinned.
      AND json_type(e.result_json,'$.document_review')='object'
      AND (SELECT count(*) FROM json_each(
            json_extract(e.result_json,'$.document_review')))=4
      AND (SELECT count(*) FROM json_each(
            json_extract(e.result_json,'$.document_review')) dkey
           WHERE dkey.key IN ('approved','checks','failed_checks','findings'))=4
      AND json_type(e.result_json,'$.document_review.approved')='true'
      AND json_type(e.result_json,'$.document_review.checks')='object'
      -- exactly six keys, and exactly the six canonical names, each JSON true
      AND (SELECT count(*) FROM json_each(
            json_extract(e.result_json,'$.document_review.checks')))=6
      AND (SELECT count(*) FROM json_each(
            json_extract(e.result_json,'$.document_review.checks')) c
           WHERE c.type='true' AND c.key IN (
             'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',
             'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',
             'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE'))=6
      AND json_type(e.result_json,'$.document_review.failed_checks')='array'
      AND json_type(e.result_json,'$.document_review.findings')='array'
      AND json_array_length(
            json_extract(e.result_json,'$.document_review.failed_checks'))=0
      AND json_array_length(
            json_extract(e.result_json,'$.document_review.findings'))=0
 )
BEGIN SELECT RAISE(ABORT, 'PENDING_APPROVAL requires evaluated C2 or exact review-only approval'); END;

-- The settlement boundary itself.  0039 validated lifecycle, identity and the
-- result fingerprint, but never the payload's entries, so the public
-- settle_content_review_resume_execution API accepted a decision=APPROVE result
-- whose entries contradicted their own classification.  A SUCCESS settlement
-- now carries the same canonical entry contract as PENDING_APPROVAL, and the
-- surrounding BEGIN IMMEDIATE makes the refusal atomic: no partial row, no
-- stored APPROVE, no inconsistent payload.
DROP TRIGGER content_review_resume_executions_settle;
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
 -- >>> CANONICAL ENTRY CONTRACT v3 >>>
 OR (NEW.outcome='SUCCESS' AND (
      json_extract(NEW.result_json,'$.reviewer_version')='production_article_reviewer_opus_v3'
      AND json_type(NEW.result_json,'$.entries')='array'
      AND json_array_length(json_extract(NEW.result_json,'$.entries'))>0
      AND NOT EXISTS (
        SELECT 1 FROM json_each(CASE WHEN json_type(NEW.result_json,'$.entries')='array'
               THEN json_extract(NEW.result_json,'$.entries') ELSE json_array() END) y
        WHERE (
          json_type(y.value)='object'
          AND (SELECT count(*) FROM json_each(y.value))=7
          AND (SELECT count(*) FROM json_each(y.value) k WHERE k.key IN (
                'segment_id','segment_fingerprint','classification','evidence_ids',
                'reason','outcome','contains_external_fact'))=7
          AND json_type(y.value,'$.segment_id')='text'
          AND length(json_extract(y.value,'$.segment_id'))>0
          AND json_type(y.value,'$.segment_fingerprint')='text'
          AND length(json_extract(y.value,'$.segment_fingerprint'))>0
          AND json_type(y.value,'$.classification')='text'
          AND json_type(y.value,'$.outcome')='text'
          AND json_extract(y.value,'$.outcome') IN ('PASS','BLOCK')
          AND json_type(y.value,'$.evidence_ids')='array'
          AND NOT EXISTS (
            SELECT 1 FROM json_each(CASE
              WHEN json_type(y.value,'$.evidence_ids')='array'
              THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END) ev
            WHERE ev.type!='text' OR length(ev.value)=0
          )
          AND json_type(y.value,'$.reason')='text'
          AND length(trim(json_extract(y.value,'$.reason')))>0
          AND json_extract(y.value,'$.reason')=
              trim(json_extract(y.value,'$.reason'))
          AND json_type(y.value,'$.contains_external_fact') IN ('true','false')
          AND (
            (json_extract(y.value,'$.classification')='EVIDENCE_GROUNDED_FACT'
             AND json_type(y.value,'$.contains_external_fact')='true'
             AND (json_array_length(CASE WHEN json_type(y.value,'$.evidence_ids')='array'
                    THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END)>0
                  OR json_extract(y.value,'$.outcome')='BLOCK'))
            OR
            (json_extract(y.value,'$.classification') IN
               ('ARGUMENT_OR_INFERENCE','NON_FACTUAL_PROSE')
             AND json_array_length(CASE WHEN json_type(y.value,'$.evidence_ids')='array'
                    THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END)=0
             AND json_type(y.value,'$.contains_external_fact')='false')
          )
        ) IS NOT 1
      )
      AND (SELECT count(DISTINCT json_extract(v.value,'$.segment_id'))
           FROM json_each(json_extract(NEW.result_json,'$.entries')) v)
          =json_array_length(json_extract(NEW.result_json,'$.entries'))
      -- The durable document is exact and internally derived.  This applies
      -- to REWRITE_ONCE and HUMAN_REQUIRED too: malformed failures are not
      -- safer than malformed approvals because resume consumes both.
      AND json_type(NEW.result_json,'$.document_review')='object'
      AND (SELECT count(*) FROM json_each(
            json_extract(NEW.result_json,'$.document_review')))=4
      AND (SELECT count(*) FROM json_each(
            json_extract(NEW.result_json,'$.document_review')) dk
           WHERE dk.key IN ('approved','checks','failed_checks','findings'))=4
      AND json_type(NEW.result_json,'$.document_review.approved') IN ('true','false')
      AND json_type(NEW.result_json,'$.document_review.checks')='object'
      AND (SELECT count(*) FROM json_each(
            json_extract(NEW.result_json,'$.document_review.checks')))=6
      AND (SELECT count(*) FROM json_each(
            json_extract(NEW.result_json,'$.document_review.checks')) c
           WHERE c.type IN ('true','false') AND c.key IN (
             'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',
             'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',
             'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE'))=6
      AND json_type(NEW.result_json,'$.document_review.failed_checks')='array'
      AND json_type(NEW.result_json,'$.document_review.findings')='array'
      AND NOT EXISTS (
        SELECT 1 FROM json_each(json_extract(
          NEW.result_json,'$.document_review.failed_checks')) f
        WHERE f.type!='text' OR f.value NOT IN (
          'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',
          'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',
          'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE')
          OR json_type(NEW.result_json,
             '$.document_review.checks.' || f.value)!='false'
      )
      AND (SELECT count(DISTINCT f.value) FROM json_each(json_extract(
            NEW.result_json,'$.document_review.failed_checks')) f)
          =json_array_length(json_extract(
            NEW.result_json,'$.document_review.failed_checks'))
      AND json_array_length(json_extract(
            NEW.result_json,'$.document_review.failed_checks'))
          =(SELECT count(*) FROM json_each(json_extract(
             NEW.result_json,'$.document_review.checks')) c WHERE c.type='false')
      AND NOT EXISTS (
        SELECT 1 FROM json_each(json_extract(
          NEW.result_json,'$.document_review.findings')) f
        WHERE f.type!='text' OR length(trim(f.value))=0 OR f.value!=trim(f.value)
      )
      AND (
        (json_type(NEW.result_json,'$.document_review.approved')='true'
         AND NOT EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.document_review.checks')) c WHERE c.type!='true')
         AND json_array_length(json_extract(
               NEW.result_json,'$.document_review.failed_checks'))=0
         AND json_array_length(json_extract(
               NEW.result_json,'$.document_review.findings'))=0)
        OR
        (json_type(NEW.result_json,'$.document_review.approved')='false'
         AND EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.document_review.checks')) c WHERE c.type='false')
         AND json_array_length(json_extract(
               NEW.result_json,'$.document_review.failed_checks'))>0
         AND json_array_length(json_extract(
               NEW.result_json,'$.document_review.findings'))>0)
      )
      AND json_type(NEW.result_json,'$.decision')='text'
      AND (
        (json_extract(NEW.result_json,'$.decision')='APPROVE'
         AND NOT EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.entries')) z
             WHERE json_extract(z.value,'$.outcome')!='PASS')
         AND json_type(NEW.result_json,'$.document_review.approved')='true')
        OR
        (json_extract(NEW.result_json,'$.decision')='REWRITE_ONCE'
         AND OLD.writer_attempt_no=1
         AND (EXISTS (SELECT 1 FROM json_each(json_extract(
                NEW.result_json,'$.entries')) z
              WHERE json_extract(z.value,'$.outcome')='BLOCK')
              OR json_type(NEW.result_json,'$.document_review.approved')='false'))
        OR
        (json_extract(NEW.result_json,'$.decision')='HUMAN_REQUIRED'
         AND OLD.writer_attempt_no=2
         AND (EXISTS (SELECT 1 FROM json_each(json_extract(
                NEW.result_json,'$.entries')) z
              WHERE json_extract(z.value,'$.outcome')='BLOCK')
              OR json_type(NEW.result_json,'$.document_review.approved')='false'))
      )
    ) IS NOT 1)
 -- <<< CANONICAL ENTRY CONTRACT v3 <<<
BEGIN SELECT RAISE(ABORT, 'review execution admits one effect stamp and settlement'); END;

-- Ordinary ARTICLE_REVIEWER executions settle in the shared role ledger, not
-- in the REVIEW-ONLY table.  Recreate that lifecycle trigger with an
-- additional v3 structural floor so bypassing the application settlement
-- validator cannot store a contradictory reviewer SUCCESS.
DROP TRIGGER role_provider_executions_settle;
CREATE TRIGGER role_provider_executions_settle
BEFORE UPDATE ON role_provider_executions
WHEN NEW.execution_ref!=OLD.execution_ref
 OR NEW.job_id!=OLD.job_id OR NEW.run_id!=OLD.run_id
 OR NEW.content_id!=OLD.content_id OR NEW.logical_role!=OLD.logical_role
 OR NEW.attempt_no!=OLD.attempt_no OR NEW.binding_intent_id!=OLD.binding_intent_id
 OR NEW.model_registry_id!=OLD.model_registry_id OR NEW.provider!=OLD.provider
 OR NEW.technical_model_id!=OLD.technical_model_id OR NEW.pricing_ref!=OLD.pricing_ref
 OR NEW.pricing_profile_fingerprint!=OLD.pricing_profile_fingerprint
 OR NEW.qualification_ref!=OLD.qualification_ref OR NEW.capability_ref!=OLD.capability_ref
 OR NEW.reserved_cost_usd!=OLD.reserved_cost_usd OR NEW.reserved_at!=OLD.reserved_at
 OR NEW.created_at!=OLD.created_at
 OR NOT (
      (OLD.outcome='IN_FLIGHT' AND NEW.outcome='IN_FLIGHT'
       AND OLD.external_effect_started_at IS NULL
       AND NEW.external_effect_started_at IS NOT NULL
       AND NEW.settled_at IS NULL AND NEW.result_json IS NULL
       AND NEW.result_fingerprint IS NULL AND NEW.failure_kind IS NULL
       AND NEW.returned_model_id IS NULL AND NEW.cost_usd IS NULL)
      OR
      (OLD.outcome='IN_FLIGHT'
       AND NEW.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
       AND NEW.external_effect_started_at IS OLD.external_effect_started_at
       AND NEW.settled_at IS NOT NULL AND NEW.result_json IS NOT NULL
       AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
       AND NOT (NEW.returned_model_id IS NOT NULL
                AND NEW.returned_model_id!=NEW.technical_model_id
                AND NEW.outcome='SUCCESS'))
 )
 OR (NEW.logical_role='ARTICLE_REVIEWER' AND NEW.outcome='SUCCESS' AND (
      json_extract(NEW.result_json,'$.payload.reviewer_version')=
        'production_article_reviewer_opus_v3'
      AND json_type(NEW.result_json,'$.payload.entries')='array'
      AND json_array_length(json_extract(NEW.result_json,'$.payload.entries'))>0
      AND NOT EXISTS (
        SELECT 1 FROM json_each(CASE
          WHEN json_type(NEW.result_json,'$.payload.entries')='array'
          THEN json_extract(NEW.result_json,'$.payload.entries') ELSE json_array() END) y
        WHERE (
          json_type(y.value)='object'
          AND (SELECT count(*) FROM json_each(y.value))=7
          AND (SELECT count(*) FROM json_each(y.value) k WHERE k.key IN (
                'segment_id','segment_fingerprint','classification','evidence_ids',
                'reason','outcome','contains_external_fact'))=7
          AND json_type(y.value,'$.segment_id')='text'
          AND length(json_extract(y.value,'$.segment_id'))>0
          AND json_type(y.value,'$.segment_fingerprint')='text'
          AND length(json_extract(y.value,'$.segment_fingerprint'))>0
          AND json_type(y.value,'$.classification')='text'
          AND json_type(y.value,'$.outcome')='text'
          AND json_extract(y.value,'$.outcome') IN ('PASS','BLOCK')
          AND json_type(y.value,'$.evidence_ids')='array'
          AND NOT EXISTS (
            SELECT 1 FROM json_each(CASE
              WHEN json_type(y.value,'$.evidence_ids')='array'
              THEN json_extract(y.value,'$.evidence_ids') ELSE json_array() END) ev
            WHERE ev.type!='text' OR length(ev.value)=0
          )
          AND json_type(y.value,'$.reason')='text'
          AND length(trim(json_extract(y.value,'$.reason')))>0
          AND json_extract(y.value,'$.reason')=trim(json_extract(y.value,'$.reason'))
          AND json_type(y.value,'$.contains_external_fact') IN ('true','false')
          AND (
            (json_extract(y.value,'$.classification')='EVIDENCE_GROUNDED_FACT'
             AND json_type(y.value,'$.contains_external_fact')='true'
             AND (json_array_length(json_extract(y.value,'$.evidence_ids'))>0
                  OR json_extract(y.value,'$.outcome')='BLOCK'))
            OR
            (json_extract(y.value,'$.classification') IN
               ('ARGUMENT_OR_INFERENCE','NON_FACTUAL_PROSE')
             AND json_array_length(json_extract(y.value,'$.evidence_ids'))=0
             AND json_type(y.value,'$.contains_external_fact')='false')
          )
        ) IS NOT 1
      )
      AND (SELECT count(DISTINCT json_extract(v.value,'$.segment_id'))
           FROM json_each(json_extract(NEW.result_json,'$.payload.entries')) v)
          =json_array_length(json_extract(NEW.result_json,'$.payload.entries'))
      AND json_type(NEW.result_json,'$.payload.document_review')='object'
      AND (SELECT count(*) FROM json_each(json_extract(
            NEW.result_json,'$.payload.document_review')))=4
      AND (SELECT count(*) FROM json_each(json_extract(
            NEW.result_json,'$.payload.document_review')) dk
           WHERE dk.key IN ('approved','checks','failed_checks','findings'))=4
      AND json_type(NEW.result_json,'$.payload.document_review.approved') IN ('true','false')
      AND json_type(NEW.result_json,'$.payload.document_review.checks')='object'
      AND (SELECT count(*) FROM json_each(json_extract(
            NEW.result_json,'$.payload.document_review.checks')))=6
      AND (SELECT count(*) FROM json_each(json_extract(
            NEW.result_json,'$.payload.document_review.checks')) c
           WHERE c.type IN ('true','false') AND c.key IN (
             'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',
             'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',
             'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE'))=6
      AND json_type(NEW.result_json,'$.payload.document_review.failed_checks')='array'
      AND json_type(NEW.result_json,'$.payload.document_review.findings')='array'
      AND NOT EXISTS (
        SELECT 1 FROM json_each(json_extract(
          NEW.result_json,'$.payload.document_review.failed_checks')) f
        WHERE f.type!='text' OR f.value NOT IN (
          'TITLE_REFLECTS_BODY','TITLE_PROMISE_FULFILLED',
          'TITLE_MECHANISM_EXPLAINED','BRIEF_QUESTION_ANSWERED',
          'THESIS_CONSISTENT','CONCLUSIONS_WITHIN_EVIDENCE')
          OR json_type(NEW.result_json,
             '$.payload.document_review.checks.' || f.value)!='false'
      )
      AND (SELECT count(DISTINCT f.value) FROM json_each(json_extract(
            NEW.result_json,'$.payload.document_review.failed_checks')) f)
          =json_array_length(json_extract(
            NEW.result_json,'$.payload.document_review.failed_checks'))
      AND json_array_length(json_extract(
            NEW.result_json,'$.payload.document_review.failed_checks'))
          =(SELECT count(*) FROM json_each(json_extract(
             NEW.result_json,'$.payload.document_review.checks')) c WHERE c.type='false')
      AND NOT EXISTS (
        SELECT 1 FROM json_each(json_extract(
          NEW.result_json,'$.payload.document_review.findings')) f
        WHERE f.type!='text' OR length(trim(f.value))=0 OR f.value!=trim(f.value)
      )
      AND (
        (json_type(NEW.result_json,'$.payload.document_review.approved')='true'
         AND NOT EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.payload.document_review.checks')) c
             WHERE c.type!='true')
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.failed_checks'))=0
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.findings'))=0)
        OR
        (json_type(NEW.result_json,'$.payload.document_review.approved')='false'
         AND EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.payload.document_review.checks')) c
             WHERE c.type='false')
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.failed_checks'))>0
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.findings'))>0)
      )
      AND json_type(NEW.result_json,'$.payload.decision')='text'
      AND (
        (json_extract(NEW.result_json,'$.payload.decision')='APPROVE'
         AND NOT EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.payload.entries')) z
             WHERE json_extract(z.value,'$.outcome')!='PASS')
         AND json_type(NEW.result_json,'$.payload.document_review.approved')='true'
         AND NOT EXISTS (SELECT 1 FROM json_each(json_extract(
               NEW.result_json,'$.payload.document_review.checks')) c
             WHERE c.type!='true')
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.failed_checks'))=0
         AND json_array_length(json_extract(
               NEW.result_json,'$.payload.document_review.findings'))=0)
        OR
        (json_extract(NEW.result_json,'$.payload.decision')='REWRITE_ONCE'
         AND OLD.attempt_no=1
         AND (EXISTS (SELECT 1 FROM json_each(json_extract(
                NEW.result_json,'$.payload.entries')) z
              WHERE json_extract(z.value,'$.outcome')='BLOCK')
              OR json_type(NEW.result_json,
                   '$.payload.document_review.approved')='false'))
        OR
        (json_extract(NEW.result_json,'$.payload.decision')='HUMAN_REQUIRED'
         AND OLD.attempt_no=2
         AND (EXISTS (SELECT 1 FROM json_each(json_extract(
                NEW.result_json,'$.payload.entries')) z
              WHERE json_extract(z.value,'$.outcome')='BLOCK')
              OR json_type(NEW.result_json,
                   '$.payload.document_review.approved')='false'))
      )
    ) IS NOT 1)
BEGIN SELECT RAISE(ABORT, 'role provider execution admits one effect stamp and one settlement'); END;
