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

## Before anything else: read the audit

`docs/AUDYT_ETAP3_2026-08-14.md` is the shortest path into this codebase. It
records 22 live-fixed defects as four patterns and gives two concrete designs -
allowing a second approval after a technical failure, and filtering unbound
claims before the lineage write - that together stop a single hiccup destroying
a paid research card. Start there, not with the code.

## Historical: the pipeline was blocked

Every controlled-live run is refused with `NEEDS_VERIFICATION_PRESENT`. One
research attempt (`article-research-evidence-96:research:1`) holds a `0.485760`
reservation whose charge was never established, because the synthesis exceeded
the then-120s client deadline and returned no usage row. That single unresolved
exposure closes the gate for topic generation, research and content alike.

Only the owner can clear it, by reading the exact cost from the Anthropic console
and reconciling as `CHARGED_KNOWN`, or confirming `NOT_CHARGED`. The system will
not let you guess, and that refusal is correct: `CHARGE_UNKNOWN` cannot be paired
with `EXECUTION_FAILED`. Details in `docs/HANDOVER_ARTICLE_QUALITY.md`.

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

- One article ≈ 1.10 USD at six candidates. Discovery alone ranged 0.47-1.17 USD and is
  the dominant cost; expect more now that A1 asks for ten.
- The `{0.3, 0.5, 0.6, 1.0}` cap enum is gone (ADR-150). The A1 cap is a bounded range in
  `(0, 3.000000]`, default `2.000000`, and `max_results` runs to 12. The default cap is
  extrapolated, not measured — replace it with a real number after the first live A1.
- Do not re-roll topics hoping a problem goes away. Four topics were burned that way. Find
  the mechanism first.
- Before any paid run, state the expected cost. If a run fails, diagnose before repeating.

## Simplification is an explicit goal, not a side effect

The owner's read after 2026-08-14 is that **complexity is what broke this**, and he is right
about where. A single article currently needs six serial paid stages, each with its own job,
approval, reservation and preflight. Any one of them failing kills the whole chain and costs
money — and on that day four separate mechanisms did exactly that: cost calibration, a
UNIQUE collision between packer and fetch loop, source 403s, and corpus packing.

Simplify the **orchestration**, keep the **durable core**. Concretely worth collapsing:

- **Discovery and synthesis as one paid call** instead of two jobs with two reservations.
  Half the failures were coordination between stages, not the work itself.
- **Reservations with a real margin** (measured cost x3), not a fixed enum
  `{0.3, 0.5, 0.6, 1.0}`. The enum was the single most expensive defect of the day.
- **Fetch with tolerance**: request 10-12 candidates, expect half to 403, require three from
  what survives. Six candidates at a ~50% failure rate leaves exactly the minimum and zero
  slack.
- **Fewer preflight guards, better aimed.** Three of the seven were measuring the wrong
  thing and blocked every run permanently.

What must **not** be simplified away: reservation-before-call and settle-after, the
append-only ledgers, immutable provenance, and reviewer v3. Those are the parts that behaved
correctly under abuse and are the reason no money or data was lost.

## Suggested order of work

**A. ~~Close the last article-pipeline defect.~~ Done on 2026-08-14 (ADR-149).**
`REWRITE_ONCE` did not trigger writer attempt 2. The loop was never at fault: the job was
terminalised inside attempt 1 because `UNSUPPORTED_CLAIMS` was pinned to `BLOCK` and `BLOCK`
outranks `REWRITE_ONCE` in the C2 aggregate, so the reviewer's own verdict was overruled.
A claim-level failure on attempt 1 now yields `REWRITE_ONCE`; from attempt 2 it stays
`BLOCK`. Worth carrying forward as a pattern: two authorities answering the same question
will eventually answer it differently.

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
