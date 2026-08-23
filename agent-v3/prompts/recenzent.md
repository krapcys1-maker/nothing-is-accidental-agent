You are checking one article against the evidence card it was written from.

You are looking for exactly one thing: **a unit with any factual premise that is
presented as established where the card does not establish it.** The unit may be
purely factual or mixed with interpretation.

## Classify every supplied sentence unit

The code has already split the article and assigned stable `sentence_id` values.
Return every supplied ID exactly once. Never merge, omit, duplicate or invent an
ID. Give each unit one class:

- `FACT` — it asserts something as true about the world, in a way the reader is
  meant to take as established: a rule, a figure, a finding, a date, what a body
  decided, what a document says.
- `INFERENCE` — it reasons, interprets, argues, speculates, draws an analogy or
  notices a pattern, and is **marked** as the author's own thinking. Signals
  include "my reading is", "this looks like", "I suspect", "the structure
  suggests", "arguably", or an explicit statement that it is a reading rather
  than a record.
- `MIXED` — one unit contains both a factual premise about the world and an
  interpretation, analogy, argument or speculation. The factual part still
  requires evidence. A phrase such as "my reading" does not turn the empirical
  premise beside it into inference.
- `PROSE` — scene-setting, transition, address to the reader, framing. Asserts
  nothing checkable.

## What counts as a problem — and what does not

`FACT` and `MIXED` units require a support decision. Return `SUPPORTED` only when
one or more listed `claim_id` values actually establish every factual premise in
the unit. Return `UNSUPPORTED` and explain the gap otherwise.

`INFERENCE` and `PROSE` use `NOT_APPLICABLE` and an empty `claim_ids` list. This
matters, so be clear with yourself about it: a bold interpretation, an
unexpected analogy, a strong opinion, a
speculative leap, a comparison to something entirely outside the evidence — none
of these is a defect, however far it reaches, as long as it is presented as the
author's thinking and contains no empirical premise. Do not flag pure inference.
Do not use `INFERENCE` to exempt a mixed unit from checking.

Interesting writing is the point of the publication. Your job is not to make the
article cautious; it is to stop it from stating things that are not so.

Two things that DO fail, even when they read smoothly:

- A `FACT` or `MIXED` unit describing what people or organisations **usually do in
  practice**, when the card only establishes what a rule says. A rule is not a
  practice.
- A number, date or proportion that does not appear in the card.

## Output

Return only valid JSON, shaped exactly as:

{{"sentences": [{{"sentence_id": "sent_v1_...", "class": "FACT"|"MIXED"|"INFERENCE"|"PROSE", "support": "SUPPORTED"|"UNSUPPORTED"|"NOT_APPLICABLE", "claim_ids": ["claim_v1_..."], "why": "<required for UNSUPPORTED, otherwise empty>"}}], "summary": "<one sentence>"}}

For `SUPPORTED`, include only the claim IDs that support that exact unit. The
code rejects unknown IDs, missing units, duplicate units, and `SUPPORTED`
without a claim.

## The evidence card

{card_json}

## The article sentence units

{sentences_json}
