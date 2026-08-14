# Prompt for the next agent

Copy everything below the line into a fresh session.

---

You are continuing work on **Nothing Is Accidental** — a semi-autonomous Substack agent in
`C:\Users\user\Desktop\agent project`. Read `docs/HANDOVER_ARTICLE_QUALITY.md` first; it is
short and it is accurate as of 2026-08-14.

## The goal

A fully autonomous Substack account that:

1. finds an article topic,
2. researches it against real sources,
3. writes the article,
4. has it reviewed for factual grounding,
5. publishes it,
6. writes Substack **notes**, leaves **comments**, gives **likes**,
7. periodically checks account statistics and takes corrective action when reach drops.

It must eventually run on a server, but it has to stay runnable on this Windows machine for
testing.

## Where the project actually is

**Stages 1-4 work and are merged on `main`.** A verified live run went: topic generation →
source discovery → controlled fetch → Research Card `PROCEED` → writer → reviewer v3
verdict. One article costs about **1.10 USD**. Production database is at schema `0041`,
`integrity_check=ok`.

**Stages 5-7 do not exist at all.** There is no browser module, no Substack integration, no
publishing code, no statistics collection. `app/` contains no `browser/`, `publishing/` or
`substack/` package. Treat that half of the goal as greenfield, not as something to debug.

**Nothing has ever been published.** `published_at` and `external_url` are `NULL` on every
row. The first publication will be a genuine first, and it is irreversible in public.

## Rules that are not negotiable

1. **Never publish, post, comment or like without explicit per-action owner approval**,
   until the owner has seen the full flow work and says otherwise in writing. Publication is
   outward-facing and cannot be undone. This is the single highest-risk thing in the project.
2. **Do not dismantle the safety architecture.** Reservation-before-call, settle-after,
   fail-closed preflight, immutable provenance and the append-only ledgers are load-bearing.
   On 2026-08-14 processes were killed mid-call repeatedly and the system never lost track of
   a dollar and never corrupted the database. If a guard blocks you, fix what it is measuring
   — do not delete it.
3. **Reviewer v3 is the quality gate and stays binding.** It blocks drafts whose claims
   exceed the evidence, and it has been correct every time so far. Do not lower its bar to
   force a pass.
4. **Per ADR-018 the account does not publicly disclose that it is AI**, but never
   impersonate a specific real person, never lie if asked directly, and never use technical
   evasion to defeat platform detection.
5. **Credentials**: the owner enters Substack credentials himself. Never type, store or
   handle the password, and never bypass a login challenge or CAPTCHA.

## Cost discipline — read this before spending anything

On 2026-08-14 a full day cost **8.32 USD** and produced one draft. Roughly 3.5 USD of that
was burned on calls that returned nothing, because cost reservations were too tight and
every overrun killed a whole topic. Lessons that cost real money:

- One article ≈ 1.10 USD. Discovery alone ranges 0.47-1.17 USD and is the dominant cost.
- `cap 1.0 + max_results 6` is the only discovery combination that both passes envelope
  validation and completes. Changing one without recalculating the other kills jobs.
- Do not re-roll topics hoping a problem goes away. Four topics were burned that way. Find
  the mechanism first.
- Before any paid run, state the expected cost. If a run fails, diagnose before repeating.

## Suggested order of work

**A. Close the last article-pipeline defect (cheap, no new design).**
`REWRITE_ONCE` does not trigger writer attempt 2 — `pipeline.py:376` already iterates
`(1, 2)` and the cost ceiling was not the cause, so something short-circuits after attempt 1.
Until this is fixed a rewrite must be driven manually.

**B. Judge and improve output quality.**
`ARTYKUL_DRAFT.md` holds the draft, nine evaluations and the reviewer verdict. The reviewer
blocked 2 of 26 segments because the opening asserts an operational practice the
statute-based evidence does not cover — that judgement looks right, and the fix is
editorial. The real ceiling is source quality: roughly half of authoritative sources return
`403` to the fetcher, so a corpus is usually three pages and confidence settles near 0.55.
Reaching primary research that does not block automated access is the highest-value
improvement available.

**C. Design the publication path — new work, propose before building.**
Decide how a `PENDING_APPROVAL` draft becomes a Substack post: browser automation versus
API, where the one-shot owner approval sits, how the published URL and timestamp become
durable, and how a partial failure is recovered without double-posting. Mirror the existing
approval/reservation/settlement pattern rather than inventing a second one.

**D. Notes, comments, likes.**
Each is an outward-facing write and needs the same approval discipline as publishing.
Engagement actions carry reputational risk that content generation does not: a bad comment
cannot be recalled. Start read-only — observe, draft, show the owner — before anything is
sent.

**E. Statistics and the corrective loop.**
Only after the above. Collect real metrics first, establish a baseline, and let the owner
approve what "reach dropped, do something" is allowed to mean. Do not let an autonomous loop
take engagement actions on a metric it has never been calibrated against.

## Parked, deliberately

`PR #50` (branch `agent/content-known-cost-reconciliation`, schema `0042`) is complete and
verified at 2802/2802 but is still an open draft. It raises `RUNTIME_SCHEMA_VERSION` to
`0042`, so merging it without applying the migration to production in the same authorised
step makes the runtime fail-closed against the `0041` database and stops the whole pipeline.
Merge and migrate together, or leave both alone.

## Operating notes

- `config/growth_policy.yaml` is gitignored. Working values are documented in
  `config/growth_policy.example.yaml`.
- If a run is interrupted after the provider request boundary:
  `python -m app.main reap-runs --once --stale-after-seconds 60`, then `reconcile-attempt`
  for the exact `request_id`. An interrupted run can also leave the five security flags
  open, and `controlled-live-topic-generation` will refuse with `NOT_FAIL_CLOSED_BASELINE`
  until they are restored.
- Work in the same session until the goal is reached or a real blocker needs an owner
  decision. Report honestly: if something failed, say so with the output.
