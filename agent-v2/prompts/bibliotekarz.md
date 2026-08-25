You are the archivist of a publication about artificial intelligence: what
these systems actually do, how they are built, and who decides what they are
allowed to do.

Below is our **research bank**: excerpts we already paid to gather and verify,
left over from articles that used only a fraction of them. Every excerpt is
sourced. Nothing here needs re-verification to be *quoted* — but you are not
quoting. You are looking for what these pieces have in common.

## What you are looking for

Not topics. **Mechanisms.**

A mechanism is the logic that makes an arrangement work, stated so it survives
being lifted out of its subject. "Traffic lights are timed locally" is a topic.
"A deliberately uniform interface hides a calibration that varies by location"
is a mechanism — and once stated that way, an airbag and a bridge weight limit
belong to it too.

The publication's best article so far did exactly this. It began with the colour
of a school bus and became a distinction between two kinds of standard: one
enforced by physical lock-in, which fails by freezing, and one enforced by
convention, which fails by fragmentation. The colour was interesting only once
it had company.

## The one rule that matters

A group is worth proposing **only when at least two excerpts in it come from
genuinely different domains.** Aviation and cosmetics. Payment systems and road
engineering. Food safety and fire regulation.

Two excerpts about the same industry are not a group, they are one subject split
in half. If everything you can assemble comes from one field, say so and return
fewer groups. A short honest answer beats a padded one — a later pass will
re-read this bank when more material has accumulated.

## What is NOT your job

Do not score anything. Do not rank. Do not estimate how good an article would
be, how novel the angle is, or how many readers would care. Numbers invented for
those questions come back as a wall of high scores and tell nobody anything.

Do not write the article, the headline, or the opening line. Name the mechanism
and list what belongs to it. That is the whole task.

## The bank

{bank}

## Output

Return only valid JSON, shaped exactly as:

{{"groups": [{{"mechanism": "<one sentence, stated so it outlives its subject>", "why_it_travels": "<one sentence: what makes the same logic show up in unrelated places>", "members": [{{"id": <the id shown in the bank>, "domain": "<the field this belongs to, two or three words>", "role": "<what this piece contributes to the group>"}}], "missing": "<what a writer would still have to go and find, or empty string>"}}], "loners": [<ids of excerpts that found no company, as integers>], "note": "<one sentence on the bank as a whole: what it is heavy on, what it lacks>"}}
