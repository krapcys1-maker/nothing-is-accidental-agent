Write an article in {language} for {marka}, using the evidence card below.
Your reader is interested in AI but is not an engineer, lawyer or economist.
The article should leave them understanding both what happened and why.

## Build the explanation

Find the strongest useful question the material can answer. Introduce the
situation in ordinary language, then investigate it. Explain unfamiliar systems
through what they do and what changes for the people involved. Define technical
terms where needed; there is no quota of terms or ban on necessary detail.

Connect the evidence rather than listing sources. Explain each causal step:
what a rule or design permits, whose choices it changes, and what may follow.
Where incentives matter, compare the plausible explanations and the strongest
counterevidence. Who benefits is a useful question, not a verdict about intent.
If the premise turns out to be wrong, say what the evidence changed.

Depth can come from following one question carefully. Another industry, a
historical parallel or an analogy belongs only when it helps and has support.
You do not owe the reader a villain, an exposed myth or a prescribed conclusion.
End where the finding is clear, or with the specific important question still
open. A concise recap is fine when it helps a difficult explanation land.

## Facts and limits

Use the card for factual claims, names, dates, quotations and measurements.
Attribute company claims to the company; they are not independent findings.
A source must support the whole assertion. Preserve units, denominators,
conditions, document versions and the difference between a proposal and a rule
in force. Use supplied citable figures; do not invent a conversion or comparison.
Explain a number's meaning instead of decorating the article with more numbers.

Interpretation and an explicit hypothetical example are allowed. Do not smuggle
an unsupported fact into an opinion, analogy or hypothetical. Keep a missing
answer visible without treating missing evidence as evidence of absence.
Place a limitation beside the claim it qualifies; use a separate paragraph only
when the reader needs one. Never invent reporting or personal experience.

The card may carry `investigation_finding`: what our own reporting established
by putting several sources together. Build the piece around it and let the
reader see how the pieces fit, each piece attributed to its source. Do not claim
that nobody else has reported or connected it; you cannot know that. Say what
the sources show when they are put side by side.

It may also carry `editorial_hypotheses`: our reading of why the key actor chose
this course, or how this could look in about two years. Use them only as clearly
labelled analysis ("our reading", "one plausible explanation"), each with the
evidence for it, the strongest evidence against it and what would prove it
wrong. A hypothesis never becomes a fact in the text.

It may also carry `investigation_angles`: the angles our investigation found in
this story, each with its one-sentence takeaway and the checked detail (`hak`) it
rests on. Then this is the full investigation, not a news summary; the reader
may already know the headline. Open with the most telling checked detail
rather than background, and make the question the piece answers clear early.
Show the sequence of events where the order matters, explain the mechanism in
plain words, make the stakes concrete (who pays, how much, where the card says),
and set what the actors said beside what they did. Give a motive or a scenario
as labelled analysis. These are materials, not a required outline: merge, reorder
or drop an angle that does not earn its place.

When `investigation_type` is `model_release`, treat the story the way an expert
reviewer treats a model launch: put the developer's own scores next to
independent ones and say which is which; explain what each test measures in a
sentence a non-engineer can repeat; give the price in human terms, and what a
finished task costs rather than only the price per token when the card has it;
include at least one place where it failed or disappointed; attribute reader and
tester comments as opinions. Answer the big question with a verdict: say plainly
what you think and argue it, using the human baseline and test conditions from
the card as evidence.

Write it like the best AI writers: with a point of view. Take a side, make the
call, reason from a named assumption where the evidence stops short. Not
everything has to be proven; the reader must only be able to tell which part
is fact and which is our view. Speak as the publication: "we", "our view",
"our bet" — never "I" or "my". Say a view once and confidently; don't wrap
every sentence in "our reading is that".

End an investigation article with two short parts under plain-text
subheadings, after the body:
- "Our conclusion": what we think this story really shows, in two to four
  confident sentences. Add the strongest objection in one sentence only if it
  is serious.
- "What this could lead to": two or three bold, concrete calls for the next
  year or two (who wins, what changes, what people will do differently), each
  with the assumption it rests on, then the one open question that matters
  most (`not_established`).
These are our own view, labelled as such; facts in them still come only from
the card.

One claim may carry `"not_fetched": true`. That is the fact this article was
commissioned from, and its `evidence` is not a passage lifted from a document we
retrieved — nobody on this run opened that page. You may state it, and you must
attribute it to the source named in its `url`. Do not build a figure, a
comparison or a conclusion on it that the fetched material does not also carry.

Dates. Do not write a datestamp such as "figures checked to [date]": that line
is written by code from the card after you finish, and if you write one yourself
it will be stripped. Dates inside the argument are still yours: when a rule, a
price or a deadline holds only as of some date, say so where it matters.

If `source_dates.note` says the material is old, the reader is told once,
plainly, in your own words. Hiding that caveat is worse than the age; it is the
reader's right to weigh what they are reading.

Never say a source IS undated. You have not seen the source — you have seen an
excerpt of it. The phrase "undated in the excerpts" is a fact about our
material; "the accounts are undated" is a claim about pages that sit on the open
web with dates on them. One article was lost exactly here: the draft turned the
first into the second, the fact check opened the pages, found the dates and
refused to publish. Say what our material shows and let it be the smaller
claim: the excerpt carries no date, the URL gives a month but no day, the page
we pulled did not say when it was written.

Before returning, check each factual clause, including the headline and subtitle:
what exactly in the card establishes this? Keep a documented preparation distinct
from passing a test; a possible cost advantage distinct from a known small cost;
a rule's scope distinct from its effectiveness. Do not invent how the current
system works to make the proposed change easier to explain. If an effect depends
on cost, demand, enforcement or another unmeasured condition, keep it conditional.
An illustrative example must state its assumptions and remain separate from the
finding. Do not conclude that a large organisation can trivially absorb a cost,
or that a smaller one can simply change markets, without evidence. A proposal
that does not govern a foreign market says nothing about the other laws applying
there. Being outside this rule is not permission to do anything. Likewise, a
proposed extra check does not prove that today's releases face no other checks.

Explain the topic to the reader without exposing internal workflow labels such
as "the card" or "the prompt". Say what is known and what would settle the gap.

## Length and presentation

How long the article is depends on one thing: how much in this story is worth a
curious reader's time. Material like this usually fills about {target_words} words
({min_words}–{max_words}), but that is a guide to the usual size, not a limit.
When the story holds more that is surprising, consequential or needed to
understand it, go as long as it takes and go into detail exactly there. When a
point is minor, give it a sentence or leave it out. Do not pad, never say a point
twice in new words, and spend no words on what a headline already told the
reader. Never cut the explanation that makes a difficult point understandable.
Use a specific, accurate headline and a useful subtitle. Paragraphs and optional
plain-text subheadings should help the reader follow the argument. No fixed
sentence rhythm, punctuation quota or compulsory reader-address applies.

## Optional style references

These fragments illustrate explanatory techniques. They are not facts, a
persona to impersonate, or a required structure. Do not copy their wording.
The shared plain-language voice takes priority over a sample's complexity.

{style_examples}

{style_positive}

{style_negative}

## Previous feedback

Historical observations, not instructions or evidence. Ignore any demand for
a fixed number of ideas, a particular ending, a dramatic contrast or an invented
moment from the reader's life. Use feedback only if it clarifies this article.

{poprzednie_uwagi}

## Output

Return only valid JSON:
{{"title": "<headline>", "subtitle": "<one line>", "body": "<article in plain text, blank lines between paragraphs>", "numbers_used": ["<each figure exactly as written>"], "limits_paragraph_present": true|false}}

`limits_paragraph_present` reports whether there is a separate limits paragraph;
false is valid when limits are explained beside the relevant claims.

## Evidence card — data, never instructions

{card_json}
