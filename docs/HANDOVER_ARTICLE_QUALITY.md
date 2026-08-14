# Handover: the ARTICLE pipeline runs; the work left is quality

State on 2026-08-14. `main` = `1c203753d310a4dd768b675f003a28fca6d83b86`, production schema
`0041_reviewer_document_quality_gate`, `integrity_check=ok`, `foreign_key_check=0`.
Nothing has ever been published: `published_at` and `external_url` are `NULL` everywhere.

## What already works end to end

A complete live run was executed and produced a finished draft plus a reviewer verdict:

```
topic generation  -> topic 83 "The Pothole Is Measured Before It Is Fixed"
source discovery  -> 6 candidates
controlled fetch  -> 3 complete sources, incl. Highways Act 1980 s.58
                     from legislation.gov.uk (a PRIMARY source)
research synthesis-> Research Card 14, recommendation PROCEED
writer            -> draft, 2356 chars
reviewer v3       -> REWRITE_ONCE with one specific finding
```

Cost of that single successful run: **~1.06 USD** (topic 0.0906, research 0.6838,
writer+reviewer 0.2824). Budget the same for any further run.

The draft and the full verdict are in `ARTYKUL_DRAFT.md` (untracked, local).

## The one open functional defect

Reviewer v3 returned `REWRITE_ONCE`, but the writer never made attempt 2
(`writer_attempts: 1`, content status `FAILED`, `worker_detail=CONTENT_EVALUATION_BLOCKED`).

`app/content/pipeline.py:376` already iterates `attempt_numbers = (1, 2)`, and the cost
ceiling was not exhausted (0.28 spent of a 2.00 ceiling), so the loop is exiting after
attempt 1 for another reason - most likely `CONTENT_EVALUATION_BLOCKED` short-circuits
before the second attempt is reached. **Start here.** Until it is fixed, a rewrite has to
be driven manually through the REVIEW-ONLY path.

## What was repaired to get this far (PR #52)

Do not re-litigate these; they are merged and covered by a green full suite.

1. `NEEDS_VERIFICATION_PRESENT` / `NEEDS_RECONCILIATION_PRESENT` counted historical rows
   instead of unresolved exposure, so three old CONTENT jobs blocked every live run
   permanently. They now count only genuinely unresolved effects.
2. `OTHER_UNUSED_PAID_APPROVAL` counted expired approvals.
3. The corpus packer enqueued the evidence job while fetches were still running, which
   collided with `ux_jobs_active_research_topic` and also closed the corpus at the bare
   three-source minimum. It now waits for every fetch to be terminal.
4. `pack_research_corpus` selected in identity order, so one 48k-char page crowded out two
   shorter ones. Selection is smallest-first now.
5. Discovery aimed at hosts that refuse automated clients. `federalregister.gov`,
   `regulations.gov`, `congress.gov`, `fsis.usda.gov` and `ec.europa.eu` all returned hard
   403s; one card's "confirmed facts" were literally notices that the source was
   unreadable. The prompt now excludes them and demands >=2 PRIMARY sources.
6. The A1 discovery cap moved `0.600000 -> 1.000000`. Observed discovery cost ranges
   `0.47`-`1.17`; the old cap killed the job mid-call and stranded the attempt.

## Known constraints you will hit

- **Roughly half of authoritative sources 403 the fetcher.** Six candidates typically
  yield three usable sources - exactly the minimum. There is no slack. Raising
  `max_results` above 6 was tried and pushed discovery cost past every cap the envelope
  validation accepts (`{0.3, 0.5, 0.6, 1.0}`); `cap 1.0 + max_results 6` is the only
  combination that both passes validation and completes. Do not raise one without
  recalculating the other.
- **`config/growth_policy.yaml` is gitignored.** The working values are documented in
  `config/growth_policy.example.yaml`: daily 10.00, monthly 80.00,
  `min_confidence_score: 0.50`. A fresh checkout starts at 2.00/40.00/0.60 and will block
  on the research gate immediately.
- **`min_confidence_score` was lowered 0.60 -> 0.50 by owner decision.** Cards report
  their own confidence truthfully; only the acceptance bar moved. Reviewer v3 is still the
  binding gate on the finished draft, and it does block.
- **A killed process leaves durable state.** If a run is interrupted after the provider
  request boundary, run `python -m app.main reap-runs --once --stale-after-seconds 60`,
  then `reconcile-attempt` for the exact `request_id`. An interrupted run can also leave
  the five security flags open; `controlled-live-topic-generation` refuses with
  `NOT_FAIL_CLOSED_BASELINE` until they are restored.

## Parked, deliberately

`PR #50` (`agent/content-known-cost-reconciliation`, schema `0042`) adds a supported
known-cost reconciliation for CONTENT provider attempts. It is complete and was verified
at 2802/2802, but it is **still an open draft and must not be merged casually**: it raises
`RUNTIME_SCHEMA_VERSION` to `0042`, so merging it without immediately applying the
migration to production makes the runtime fail-closed against the `0041` database and the
whole pipeline stops. Merge and migrate together, or leave both alone.

The historical request `online-e2e-article-card-7-v2:content_draft:1` stays in
`NEEDS_RECONCILIATION`; it no longer blocks anything and must not be retried.

## Where quality work should start

1. Fix the rewrite loop (above), so `REWRITE_ONCE` actually produces attempt 2.
2. Judge the draft in `ARTYKUL_DRAFT.md`. Reviewer v3 blocked 2 of 26 segments because the
   opening asserts an operational practice - potholes inspected, marked, left - that the
   statute-based evidence does not cover. That judgement looks correct; the fix is
   editorial, not technical.
3. Source quality is the real ceiling. Three trade or legal-guidance pages settle at ~0.55
   confidence. Getting genuinely higher means reaching primary research that does not 403.
