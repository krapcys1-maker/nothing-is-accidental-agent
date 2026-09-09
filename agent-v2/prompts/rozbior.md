You are about to write a short Note for {marka} about the material below.
Before you write a single sentence of it, take the material apart.

Answer in {language}.

# WHY THIS STEP EXISTS

The account has published dozens of notes that were correct and forgettable.
They stated the fact, explained the term the fact turned on, and stopped. A
reader finished them knowing one more thing and feeling nothing, because
nobody in the chain had asked the obvious question: **so what is this,
actually — and how big is it?**

Take the real example the owner raised. A lab announces it has settled a
Millennium Prize problem. The dry version says so and moves on. The version
worth reading asks what the problem was, why it stood open for decades, what
"settled" means here (a proof? a proof nobody has checked? a special case?),
whether this is a machine doing mathematics or a machine assisting a
mathematician, and what would have to be true for it to matter as much as the
headline implies. Same fact. One of them is a noticeboard, the other is a
publication.

So: you are not summarising. You are working out what you actually think,
from this material only, so that the note can say something.

# THE MATERIAL

{evidence}

# WHAT TO PRODUCE

## 1. In plain words

What is this, for a reader who has never heard of any of it? Name the thing,
say what it does, and say it without a single term you would not use out loud.
If the material turns on something the reader cannot be assumed to know — a
prize, a benchmark, a clause, a technique — that is the thing to unpack here.

## 2. How big

Big compared to **what**? Find the comparison inside the material: the number
before it, the same measure elsewhere, the ordinary case this departs from.

A comparison you supply from your own memory is worthless here and worse than
none, because the note may end up standing on it. **If the material carries no
comparison, say so in `czego_nie_wiadomo` and leave `skala` empty.** An empty
`skala` is a good answer. An invented one is the failure this whole step is
supposed to prevent.

## 3. The questions a reader would actually ask

Three to five. Not questions that sound thoughtful — questions somebody who
just read the first sentence would genuinely want answered next. Cover, if the
material allows it:

- what exactly happened, as opposed to what the phrasing suggests happened
- who decided it, and what they get out of it
- what it would take for this to be **less** than it sounds
- what changes for someone who will never work on any of this

Answer each one. Mark `z_dowodu` true only when the answer is in the material.
When it is your reasoning about the material, mark it false — that is allowed
and useful, but the note is not permitted to state it as fact.

## 4. If it holds

What follows if this is exactly as reported? One or two steps down the chain,
no further. Prophecy is not analysis, and the third step is always invention.

## 5. Where it would break

The honest deflation. What is the most likely way this turns out to be
narrower, slower or more ordinary than it reads? Name the specific thing that
would have to be true — a caveat in the material, an unchecked claim, a
special case, an interested party. If the material genuinely gives you nothing
to deflate, say that; it is a real answer and it is rare.

## 6. What you make of it

One sentence. Not a summary, not a hedge — the thing you would say if somebody
asked you across a table what you think about this, having read only this
material. It may be flat scepticism. It may be that this is bigger than the
coverage suggests. It may be that the interesting part is not the part being
reported. It must be a position somebody could disagree with.

# THE ONE HARD RULE

Every factual claim comes from the material above. You have no memory to draw
on here, and you have no personal experience: not with these systems, not with
these companies, not with anything. Where you are reasoning rather than
reporting, say so through `z_dowodu` and through the fields that are marked as
judgement. A judgement grounded in the material is the point of this step. A
fact you supplied yourself is the one thing that can get the account caught.

# OUTPUT

Return only valid JSON:

{{"w_prostych_slowach": "<what this is, plainly>",
 "skala": "<how big, against a comparison FROM THE MATERIAL, or empty>",
 "pytania": [{{"pytanie": "<question>", "odpowiedz": "<answer>", "z_dowodu": true}}],
 "jesli_sie_utrzyma": "<what follows if it holds>",
 "gdzie_by_peklo": "<the most likely way this is smaller than it reads>",
 "co_o_tym_sadze": "<one sentence, a position>",
 "czego_nie_wiadomo": ["<what this material cannot settle>"]}}
