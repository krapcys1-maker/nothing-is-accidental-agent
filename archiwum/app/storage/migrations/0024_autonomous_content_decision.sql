-- WAVE C4: durable, provider-independent content decision ledger.
-- This step does not migrate production by itself and does not add any
-- provider, browser or publication capability.

CREATE TABLE autonomous_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL UNIQUE,
    decision_schema_version TEXT NOT NULL
        CHECK (decision_schema_version='content_decision_v1'),
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    draft_id INTEGER NOT NULL REFERENCES content_drafts(id) ON DELETE RESTRICT,
    draft_fingerprint TEXT NOT NULL CHECK (
        length(draft_fingerprint)=64
        AND draft_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    autonomy_level TEXT NOT NULL CHECK (
        autonomy_level IN ('LEVEL_0','LEVEL_1','LEVEL_2','LEVEL_3')
    ),
    account_mode TEXT NOT NULL CHECK (
        account_mode IN (
            'FULL_PUBLICATION','COMMENT_ONLY','DRAFT_ONLY','RESEARCH_ONLY'
        )
    ),
    actor_kind TEXT NOT NULL CHECK (
        actor_kind IN ('HUMAN_REQUIRED','AUTONOMOUS')
    ),
    outcome TEXT NOT NULL CHECK (
        outcome IN (
            'HUMAN_REQUIRED','APPROVED','REJECTED',
            'STALE_INPUT','TECHNICAL_ERROR'
        )
    ),
    reason_code TEXT NOT NULL
        CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    lifecycle_status TEXT NOT NULL CHECK (
        lifecycle_status IN (
            'PENDING_APPROVAL','APPROVED','REJECTED',
            'NEEDS_VERIFICATION','FAILED'
        )
    ),
    policy_version TEXT NOT NULL
        CHECK (length(trim(policy_version)) BETWEEN 1 AND 100),
    threshold REAL NOT NULL CHECK (
        typeof(threshold) IN ('integer','real')
        AND threshold=threshold AND threshold BETWEEN 0.0 AND 1.0
    ),
    score REAL CHECK (
        score IS NULL OR (
            typeof(score) IN ('integer','real')
            AND score=score AND score BETWEEN 0.0 AND 1.0
        )
    ),
    input_json TEXT NOT NULL CHECK (json_valid(input_json)),
    input_fingerprint TEXT NOT NULL CHECK (
        length(input_fingerprint)=64
        AND input_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    decision_json TEXT NOT NULL CHECK (json_valid(decision_json)),
    decision_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(decision_fingerprint)=64
        AND decision_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    approval_id INTEGER REFERENCES approvals(id) ON DELETE RESTRICT,
    lease_owner TEXT NOT NULL,
    execution_generation INTEGER NOT NULL CHECK (execution_generation>0),
    lease_expires_at TEXT NOT NULL CHECK (length(lease_expires_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0,1)),
    CHECK (
        (outcome='HUMAN_REQUIRED' AND actor_kind='HUMAN_REQUIRED'
         AND lifecycle_status='PENDING_APPROVAL' AND approval_id IS NOT NULL)
        OR
        (outcome='APPROVED' AND actor_kind='AUTONOMOUS'
         AND lifecycle_status='APPROVED' AND approval_id IS NULL)
        OR
        (outcome='REJECTED' AND actor_kind='AUTONOMOUS'
         AND lifecycle_status='REJECTED' AND approval_id IS NULL)
        OR
        (outcome='STALE_INPUT' AND actor_kind='AUTONOMOUS'
         AND lifecycle_status='NEEDS_VERIFICATION' AND approval_id IS NULL)
        OR
        (outcome='TECHNICAL_ERROR' AND actor_kind='AUTONOMOUS'
         AND lifecycle_status='FAILED' AND approval_id IS NULL)
    )
);

CREATE UNIQUE INDEX ux_autonomous_decisions_terminal_content
ON autonomous_decisions(content_id)
WHERE outcome IN ('HUMAN_REQUIRED','APPROVED','REJECTED');
CREATE INDEX ix_autonomous_decisions_content_created
ON autonomous_decisions(content_id,created_at,id);

CREATE TRIGGER autonomous_decisions_contract
BEFORE INSERT ON autonomous_decisions
WHEN NEW.applied!=0
 OR NEW.input_fingerprint IS NOT evidence_sha256_hex(NEW.input_json)
 OR NEW.decision_fingerprint IS NOT evidence_sha256_hex(NEW.decision_json)
 OR json_extract(NEW.decision_json,'$.decision_id') IS NOT NEW.decision_id
 OR json_extract(NEW.decision_json,'$.content_id') IS NOT NEW.content_id
 OR json_extract(NEW.decision_json,'$.account_id') IS NOT NEW.account_id
 OR json_extract(NEW.decision_json,'$.job_id') IS NOT NEW.job_id
 OR json_extract(NEW.decision_json,'$.run_id') IS NOT NEW.run_id
 OR json_extract(NEW.decision_json,'$.draft_id') IS NOT NEW.draft_id
 OR json_extract(NEW.decision_json,'$.draft_fingerprint')
        IS NOT NEW.draft_fingerprint
 OR json_extract(NEW.decision_json,'$.content_type') IS NOT NEW.content_type
 OR json_extract(NEW.decision_json,'$.autonomy_level')
        IS NOT NEW.autonomy_level
 OR json_extract(NEW.decision_json,'$.account_mode') IS NOT NEW.account_mode
 OR json_extract(NEW.decision_json,'$.actor') IS NOT NEW.actor_kind
 OR json_extract(NEW.decision_json,'$.outcome') IS NOT NEW.outcome
 OR json_extract(NEW.decision_json,'$.reason_code') IS NOT NEW.reason_code
 OR json_extract(NEW.decision_json,'$.lifecycle_status')
        IS NOT NEW.lifecycle_status
 OR json_extract(NEW.decision_json,'$.policy_version')
        IS NOT NEW.policy_version
 OR json_extract(NEW.decision_json,'$.threshold') IS NOT NEW.threshold
 OR json_extract(NEW.decision_json,'$.score') IS NOT NEW.score
 OR json_extract(NEW.decision_json,'$.input_fingerprint')
        IS NOT NEW.input_fingerprint
 OR NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id AND cr.run_id=c.run_id
    JOIN jobs j ON j.id=c.job_id AND j.run_id=cr.run_id
    JOIN accounts a ON a.id=c.account_id
    JOIN account_policies ap ON ap.account_id=a.id
    JOIN content_drafts d ON d.id=NEW.draft_id
    WHERE c.id=NEW.content_id AND c.account_id=NEW.account_id
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.type=NEW.content_type AND c.status IN ('RUNNING','REVISE')
      AND cr.status=c.status AND cr.job_id=NEW.job_id
      AND d.content_id=c.id AND d.job_id=j.id AND d.run_id=cr.run_id
      AND d.draft_fingerprint=NEW.draft_fingerprint
      AND d.attempt_no=(
          SELECT max(x.attempt_no) FROM content_drafts x
          WHERE x.content_id=c.id
      )
      AND a.mode=NEW.account_mode
      AND a.autonomy_level=NEW.autonomy_level
      AND j.kind='CONTENT' AND j.status IN ('LEASED','RUNNING')
      AND j.lease_owner=NEW.lease_owner
      AND j.lease_expires_at=NEW.lease_expires_at
      AND j.execution_generation=NEW.execution_generation
 )
 OR (
    NEW.outcome IN ('HUMAN_REQUIRED','APPROVED','REJECTED')
    AND (
      (SELECT count(*) FROM content_draft_evaluations e
       WHERE e.draft_id=NEW.draft_id)!=9
      OR
      (SELECT count(DISTINCT e.evaluation_type)
       FROM content_draft_evaluations e
       WHERE e.draft_id=NEW.draft_id)!=9
    )
 )
 OR (
    NEW.outcome IN ('HUMAN_REQUIRED','APPROVED')
    AND (
      SELECT count(*) FROM content_draft_evaluations e
      WHERE e.draft_id=NEW.draft_id
        AND e.result='PASS' AND e.decision='PASS'
    )!=9
 )
 OR (
    NEW.outcome='HUMAN_REQUIRED'
    AND NOT EXISTS (
      SELECT 1 FROM approvals p
      WHERE p.id=NEW.approval_id AND p.account_id=NEW.account_id
        AND p.object_type='CONTENT_ITEM' AND p.object_id=NEW.content_id
        AND p.decision='PENDING' AND p.decided_at IS NULL
    )
 )
BEGIN SELECT RAISE(ABORT, 'autonomous decision contract mismatch'); END;

CREATE TRIGGER autonomous_decisions_no_delete
BEFORE DELETE ON autonomous_decisions
BEGIN SELECT RAISE(ABORT, 'autonomous_decisions is append-only'); END;

CREATE TRIGGER autonomous_decisions_no_update
BEFORE UPDATE ON autonomous_decisions
WHEN NOT (
    OLD.applied=0 AND NEW.applied=1
    AND NEW.id IS OLD.id
    AND NEW.decision_id IS OLD.decision_id
    AND NEW.decision_schema_version IS OLD.decision_schema_version
    AND NEW.content_id IS OLD.content_id
    AND NEW.account_id IS OLD.account_id
    AND NEW.job_id IS OLD.job_id
    AND NEW.run_id IS OLD.run_id
    AND NEW.draft_id IS OLD.draft_id
    AND NEW.draft_fingerprint IS OLD.draft_fingerprint
    AND NEW.content_type IS OLD.content_type
    AND NEW.autonomy_level IS OLD.autonomy_level
    AND NEW.account_mode IS OLD.account_mode
    AND NEW.actor_kind IS OLD.actor_kind
    AND NEW.outcome IS OLD.outcome
    AND NEW.reason_code IS OLD.reason_code
    AND NEW.lifecycle_status IS OLD.lifecycle_status
    AND NEW.policy_version IS OLD.policy_version
    AND NEW.threshold IS OLD.threshold
    AND NEW.score IS OLD.score
    AND NEW.input_json IS OLD.input_json
    AND NEW.input_fingerprint IS OLD.input_fingerprint
    AND NEW.decision_json IS OLD.decision_json
    AND NEW.decision_fingerprint IS OLD.decision_fingerprint
    AND NEW.approval_id IS OLD.approval_id
    AND NEW.lease_owner IS OLD.lease_owner
    AND NEW.execution_generation IS OLD.execution_generation
    AND NEW.lease_expires_at IS OLD.lease_expires_at
    AND NEW.created_at IS OLD.created_at
)
BEGIN SELECT RAISE(ABORT, 'autonomous_decisions is append-only'); END;

DROP TRIGGER content_items_closed_transition;
CREATE TRIGGER content_items_closed_transition
BEFORE UPDATE OF status ON content_items
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status='DRAFT' AND NEW.status='PREPARED')
    OR
    (OLD.status='PREPARED' AND NEW.status IN (
        'RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='RUNNING' AND NEW.status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='REVISE' AND NEW.status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (
      OLD.status='PENDING_APPROVAL' AND NEW.status IN ('APPROVED','REJECTED')
      AND EXISTS (
        SELECT 1 FROM autonomous_decisions ad
        WHERE ad.content_id=OLD.id AND ad.job_id=OLD.job_id
          AND ad.run_id=OLD.run_id AND ad.lifecycle_status=NEW.status
          AND ad.reason_code=NEW.reason_code
          AND ad.decision_json=NEW.final_result_json
          AND ad.score IS NEW.score AND ad.applied=1
      )
    )
)
BEGIN SELECT RAISE(ABORT, 'illegal content item lifecycle transition'); END;

DROP TRIGGER content_items_status_matches_run;
CREATE TRIGGER content_items_status_matches_run
BEFORE UPDATE OF status,reason_code,final_result_json,score ON content_items
WHEN NEW.run_id IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM content_runs cr
    WHERE cr.run_id=NEW.run_id AND cr.content_id=NEW.id
      AND cr.status=NEW.status
      AND cr.reason_code IS NEW.reason_code
      AND cr.final_result_json IS NEW.final_result_json
      AND cr.score IS NEW.score
)
AND NOT EXISTS (
    SELECT 1 FROM autonomous_decisions ad
    WHERE ad.content_id=OLD.id AND ad.job_id=OLD.job_id
      AND ad.run_id=OLD.run_id AND OLD.status='PENDING_APPROVAL'
      AND ad.lifecycle_status=NEW.status
      AND ad.reason_code=NEW.reason_code
      AND ad.decision_json=NEW.final_result_json
      AND ad.score IS NEW.score AND ad.applied=1
)
BEGIN SELECT RAISE(ABORT, 'content item lifecycle must mirror run or C4 decision'); END;

DROP TRIGGER content_items_require_transition_command;
CREATE TRIGGER content_items_require_transition_command
BEFORE UPDATE OF status,reason_code,final_result_json,score,updated_at
ON content_items
WHEN OLD.run_id IS NOT NULL
AND (
    NEW.status IS NOT OLD.status
    OR NEW.reason_code IS NOT OLD.reason_code
    OR NEW.final_result_json IS NOT OLD.final_result_json
    OR NEW.score IS NOT OLD.score
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.run_id
      AND cmd.job_id=OLD.job_id
      AND cmd.content_id=OLD.id
      AND cmd.source_content_status=OLD.status
      AND cmd.target_content_status=NEW.status
      AND cmd.reason_code IS NEW.reason_code
      AND cmd.final_result_json IS NEW.final_result_json
      AND cmd.score IS NEW.score
      AND cmd.created_at=NEW.updated_at
      AND cmd.applied=0
)
AND NOT EXISTS (
    SELECT 1 FROM autonomous_decisions ad
    WHERE ad.content_id=OLD.id AND ad.job_id=OLD.job_id
      AND ad.run_id=OLD.run_id AND OLD.status='PENDING_APPROVAL'
      AND ad.lifecycle_status=NEW.status
      AND ad.reason_code=NEW.reason_code
      AND ad.decision_json=NEW.final_result_json
      AND ad.score IS NEW.score
      AND ad.created_at=NEW.updated_at AND ad.applied=1
)
BEGIN SELECT RAISE(ABORT, 'content_items requires a transition command or C4 decision'); END;

DROP TRIGGER content_c2_pending_approval_contract;
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
BEGIN SELECT RAISE(ABORT, 'C4 completion requires one exact durable decision draft'); END;

CREATE TRIGGER autonomous_decisions_apply
AFTER UPDATE OF applied ON autonomous_decisions
WHEN OLD.applied=0 AND NEW.applied=1
BEGIN
    UPDATE content_items
    SET status=NEW.lifecycle_status,
        reason_code=NEW.reason_code,
        final_result_json=NEW.decision_json,
        score=NEW.score,
        updated_at=NEW.created_at
    WHERE id=NEW.content_id AND job_id=NEW.job_id AND run_id=NEW.run_id
      AND status='PENDING_APPROVAL'
      AND NEW.outcome IN ('APPROVED','REJECTED');
    SELECT CASE
      WHEN NEW.outcome NOT IN ('APPROVED','REJECTED') THEN NULL
      WHEN changes()=1 THEN NULL
      ELSE RAISE(ABORT, 'C4 decision must update exactly one content item')
    END;
END;
