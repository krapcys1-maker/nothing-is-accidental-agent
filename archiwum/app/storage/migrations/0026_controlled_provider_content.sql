-- PRE-C5 repair: admit the durable *contract* for a controlled, paid CONTENT
-- writer execution.  Nothing here enables a real provider: it only makes the
-- paid execution mode representable so the paid-usage invariant can be proved
-- with a fake caller instead of being untestable.
--
-- Why 0025 is not enough: the `jobs_content_contract` SQL floor introduced in
-- 0021 and widened in 0022 hard-pins every CONTENT job payload to
-- execution_mode IN ('FOUNDATION_ONLY','OFFLINE_PIPELINE') AND
-- provider_enabled=0.  That predicate is a table trigger, so no application
-- change can express a paid CONTENT execution while it stands — the row is
-- rejected before any Python runs.  This migration widens exactly that one
-- predicate and changes nothing else: no new table, no relaxed append-only
-- rule, and every other condition of the floor is preserved byte-for-byte.
--
-- The new mode remains inert by default.  Declaring it is not authorization:
-- the dispatcher must additionally be composed with paid content enabled, and
-- the storage boundary still requires a positive cap plus a fully configured
-- route before a paid attempt may be created.

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
      AND (
        -- (a) the unchanged offline contract: never provider-enabled
        (
          json_extract(NEW.payload_json,'$.execution_mode') IN (
              'FOUNDATION_ONLY','OFFLINE_PIPELINE'
          )
          AND json_extract(NEW.payload_json,'$.provider_enabled')=0
        )
        -- (b) the controlled provider contract, which must declare itself
        OR (
          json_extract(NEW.payload_json,'$.execution_mode')
              ='CONTROLLED_PROVIDER_PIPELINE'
          AND json_extract(NEW.payload_json,'$.provider_enabled')=1
        )
      )
      AND NEW.topic_id=rc.topic_id
)
BEGIN SELECT RAISE(ABORT, 'CONTENT job does not match its frozen content input'); END;

-- The plan contract is pinned to the C2 execution mode. A paid execution
-- builds exactly the same durable plan from exactly the same frozen input, so
-- the mode list is widened and every other condition is preserved.
DROP TRIGGER content_plans_contract;
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
      AND json_extract(j.payload_json,'$.execution_mode') IN (
          'OFFLINE_PIPELINE','CONTROLLED_PROVIDER_PIPELINE'
      )
 )
BEGIN SELECT RAISE(ABORT, 'content plan must bind the active frozen C2 execution'); END;

-- The completion precondition must APPLY to a paid execution too. Leaving the
-- guard scoped to OFFLINE_PIPELINE would silently exempt the paid mode from
-- the nine-evaluation requirement, which is the opposite of the intent.
DROP TRIGGER content_c2_pending_approval_contract;
CREATE TRIGGER content_c2_pending_approval_contract
BEFORE INSERT ON content_transition_commands
WHEN NEW.target_content_status='PENDING_APPROVAL'
 AND json_extract((SELECT payload_json FROM jobs WHERE id=NEW.job_id),
                  '$.execution_mode') IN (
     'OFFLINE_PIPELINE','CONTROLLED_PROVIDER_PIPELINE'
 )
 AND NOT EXISTS (
    SELECT 1
    FROM content_drafts d
    WHERE d.content_id=NEW.content_id
      AND d.draft_fingerprint=json_extract(NEW.final_result_json,'$.draft_fingerprint')
      AND d.title=(SELECT title FROM content_items WHERE id=NEW.content_id)
      AND d.body=(SELECT body FROM content_items WHERE id=NEW.content_id)
      AND (SELECT count(*) FROM content_draft_evaluations e
           WHERE e.draft_id=d.id)=9
      AND (SELECT count(DISTINCT e.evaluation_type)
           FROM content_draft_evaluations e WHERE e.draft_id=d.id)=9
      AND (SELECT count(*) FROM content_drafts x
           WHERE x.content_id=NEW.content_id)<=2
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
BEGIN SELECT RAISE(ABORT, 'PENDING_APPROVAL requires a complete evaluated C2 draft'); END;
