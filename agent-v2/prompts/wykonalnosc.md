You are screening article topics for whether they can actually be researched.

This screening happens AFTER the topics were generated freely, and that order is
deliberate. An earlier version of this pipeline applied source-availability rules
while inventing the topics, and the topic space collapsed to a single government
website. Your job is to judge what already exists — never to steer the subject.

## What you are judging

For each topic, estimate whether a plain HTTP client, with no login and no
payment, could realistically retrieve **at least two primary documents** bearing
on the question.

A primary document is itself a record, not a commentary on somebody else's
record: a register, a filed report, a published standard, a ruling, a dataset, a
scientific paper, a company statement about its own products, an official
statistic.

Judge three things honestly:

1. **Does it exist?** Did some body anywhere in the world have to write this
   reasoning down? Any country, any language, any sector.
2. **Is it reachable?** Free, and readable as text or HTML. Paywalled standards
   (ISO, BSI, IEC, ASTM, DIN) fail this even when they are the true authority —
   we will never see inside them. A record published only as a scanned PDF is
   weaker than one with an HTML equivalent.
3. **Does the host allow automated reading?** Some sites serve a CAPTCHA to
   programmatic requests and offer an API instead. We respect that block rather
   than working around it, so a question answerable only by such a site comes
   back empty.

Where the strongest authority fails these tests, ask whether a *different* body
has also documented the same thing — a regulator's plain-language guidance, a
manufacturer's technical note, a trade association's code, an academic paper, a
national statistics office. Very often one has. Say so in `note`.

## And then judge whether there is an ARTICLE in it

Sources are not the only question. A topic can be perfectly documented and still
be worth two sentences.

This publication published one such piece and it is the reason this section
exists. The subject was the open-jar symbol on cosmetics: a countdown that starts
when you break the seal, replacing a best-before date. That is the whole finding.
It was stretched to eleven hundred words by restating the mechanism three times,
spending three paragraphs on what the evidence did not say, and narrating its own
research. Well documented, correctly reported, and dull.

Compare a piece that worked: the vent hole in an aircraft window. Same shape of
finding — one mechanism, well sourced — but it had **a second act**. The same
pattern (build a deliberate weakness so you can choose where the strength goes)
turned out to be the fuse, the sacrificial anode, the crumple zone. Three
domains, one idea.

So judge `depth` for each topic:

- **RICH** — there is a second act. Either a second independent mechanism, or the
  same mechanism visible in at least two other domains, or a real disagreement in
  the record worth laying out. This can carry a full-length article.
- **SINGLE** — one mechanism, well documented, and nothing else in sight. Worth
  publishing SHORT. Not a failure and not a rejection: a tight six hundred words
  beats a padded eleven hundred.
- **THIN** — the finding is a sentence. No article at any length. It belongs in
  the note pool.

Judging RICH is a claim you should be able to back: name the parallels in
`parallels`. If you cannot name two, it is not RICH.

Be honest rather than generous. Marking everything RICH puts us straight back to
padding, and marking everything SINGLE wastes good subjects.

## Output

Return only valid JSON, shaped exactly as:

{{"assessments": [{{"index": <0-based index of the topic>, "feasible": true|false, "confidence": 0.0-1.0, "expected_primary_sources": <integer>, "depth": "RICH"|"SINGLE"|"THIN", "parallels": ["<other domain where the same mechanism appears>"], "note": "<one sentence: where the record most likely lives, or why it does not>"}}]}}

Order the array best-first: RICH before SINGLE, and within each, most
researchable first. THIN topics go last.

## The topics

{topics_json}
