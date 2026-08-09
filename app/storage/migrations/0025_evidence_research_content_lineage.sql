-- PRE-C5: let real-compatible evidence research (E3) write the SAME
-- authoritative claim->excerpt->retrieval->source lineage that CONTENT already
-- requires, instead of a second parallel evidence graph.
--
-- 0017 introduced the lineage chain for the offline E2-A spine and made the
-- candidate->retrieval link exclusive to that intent by pinning
-- json_extract(payload,'$.execution')='offline_evidence_v1' AND dry_run=1.
-- That exclusivity is why a correct E3 PROCEED card could never satisfy
-- prepare_content_job.  This migration widens exactly that one predicate to
-- also admit the durable evidence-research execution, and changes nothing
-- else: the same account/run/candidate/URL chain is still required, the
-- tables are unchanged, and every row stays append-only.

DROP TRIGGER evidence_candidate_retrievals_integrity;

CREATE TRIGGER evidence_candidate_retrievals_integrity
BEFORE INSERT ON evidence_candidate_retrievals
WHEN NOT EXISTS (
    SELECT 1
    FROM research_source_candidates c
    JOIN research_runs rr ON rr.id = c.research_run_id
    JOIN runs r ON r.id = rr.id
    JOIN jobs j ON j.run_id = rr.id
    JOIN evidence_retrievals er ON er.id = NEW.retrieval_id
    WHERE c.id = NEW.candidate_id
      AND c.research_run_id = NEW.research_run_id
      AND rr.account_id = NEW.account_id
      AND r.account_id = NEW.account_id
      AND r.workflow = 'RESEARCH'
      AND j.account_id = NEW.account_id
      AND j.topic_id = rr.topic_id
      AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH'
      AND er.account_id = NEW.account_id
      AND (
        -- (a) the unchanged offline E2-A spine
        (
          json_extract(j.payload_json, '$.execution') = 'offline_evidence_v1'
          AND json_extract(j.payload_json, '$.dry_run') = 1
          AND er.requested_url = c.url
        )
        -- (b) the durable evidence-research execution, whose approved corpus
        --     is pinned in the frozen execution intent.  A redirect means the
        --     card source may legitimately carry the final URL.
        OR (
          json_extract(j.payload_json, '$.execution_intent.evidence_input')
            IS NOT NULL
          AND (er.requested_url = c.url OR er.final_url = c.url)
        )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid account/run/candidate/retrieval evidence lineage');
END;
