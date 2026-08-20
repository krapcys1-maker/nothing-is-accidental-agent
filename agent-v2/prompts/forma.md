You are reading one finished article and reporting what is physically in it.

You are not scoring it. You are not suggesting improvements. You are not deciding
whether it is good. You quote what is there and answer four questions about it.
Something else does the arithmetic and reaches the verdict.

Every answer must be anchored to a **verbatim quote** from the article. If you
cannot quote it, the answer is "no" or `null`. Never paraphrase into a quote
field.

## 1. Beats

A **beat** is a claim that changes the reader's model of the world.

Restating a claim already made, with different evidence, is **not** a new beat.
This is the whole point of the exercise, so be strict about it. If paragraph 3
says a mark looked like a certification because of its shape, and paragraph 4
says the mark was mandated by state law and so appeared everywhere, both are
evidence for the same claim — that the mark spread beyond what it certified. The
second is not a new beat.

Ask of each candidate: after reading this, does the reader believe something
they did not believe one sentence earlier? Or do they merely believe the same
thing more firmly?

Walk the article in order. For each beat, give the sentence that carries it.

## 2. The hardest fact

Find the single most damning or most consequential fact in the article — the one
a reader would repeat to someone else.

Then find a **procedural** sentence near it: a standards number, a date, a
committee name, an administrative detail. Quote both.

Then answer one question: are they delivered in the same register — same
sentence shape, same temperature, same distance — or does the hard fact land
differently? Judge only what is on the page.

## 3. The reader moment

Is there a place where the article stops talking about people in general and
addresses **this reader**, holding **one concrete object**?

"68% of Americans believe" is not this. That is a statistic about other people.
"The carton in your door shelf" is this.

Quote it if it exists, and name the object. If there is none, return `null`.

## 4. The opening claim

Quote the central claim of the first paragraph.

Then answer: is that claim already widely circulated — the kind of thing a
reader interested in the subject would likely have met before? Answer only about
that opening claim, not about the article as a whole.

## Output

Return only valid JSON, shaped exactly as:

{{"beats": [{{"quote": "<verbatim sentence>", "claim": "<what changes in the reader's model>", "new": true|false, "restates": <index of the earlier beat, or null>}}], "hardest_fact": {{"quote": "<verbatim>", "why": "<one clause>"}}, "procedural_nearby": {{"quote": "<verbatim>"}}, "same_register": true|false, "reader_moment": {{"quote": "<verbatim>", "object": "<the thing the reader holds>"}}, "opening_claim": {{"quote": "<verbatim>", "already_familiar": true|false}}, "summary": "<one sentence>"}}

`reader_moment` is `null` when there is none. Include every beat, in order,
including restatements — mark them `"new": false` and point `restates` at the
beat they repeat.

## The article

{body}
