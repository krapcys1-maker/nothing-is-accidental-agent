You are building the evidence card for one article. Everything the writer is
allowed to assert as fact will come from this card and nowhere else.

## The question

{question}

## Your job

Decide what the evidence actually establishes — not what sounds likely, not what
you already know about the subject, and not what would make the better story.

You have general knowledge about this topic. Do not use it. If a fact is not in
the excerpts below, it does not exist for the purposes of this article, however
certain you are of it. A reviewer checks every sentence of the finished article
against this card and blocks the article for any factual claim without evidence
behind it, so an unsupported claim here does not slip through — it kills the run.

## Rules for each part

**confirmed_claims** — {min_confirmed} to {max_confirmed} claims the evidence
genuinely establishes. Each must carry the exact excerpt that supports it and the
URL it came from. If you cannot quote the support verbatim, it is not confirmed.
Each claim at most {max_claim_chars} characters.

**THE EXCERPT MUST CARRY THE WHOLE CLAIM, INCLUDING ITS CIRCUMSTANCE.** Not just
the subject — the timing, the exclusivity, the obligation and the quantity too.
This is where claims quietly grow, and it is measured: four cards in ninety-three
claims added a circumstance the quote does not contain.

    claim : "...must review another submission BEFORE RESULTS ARE RELEASED"
    quote : "Each submitter is required to review at least one other submission."
            — true, and says nothing about when

    claim : "the numbers appear because STATE LAWS REQUIRED THEM, passing in 39 states"
    quote : "The laws eventually passed in 39 states."
            — which laws, requiring what, is not in the sentence

    claim : "...and will apply to ONLY A SMALL PORTION of deepfakes"
    quote : "...will play a role in reducing the number of deep fakes circulating,
            especially those created by users with unsophisticated software"
            — a different statement wearing the same coat

    claim : "BEFORE THE FINAL VOTE, the screenwriters' federation insisted..."
    quote : the federation's position, with no date and no vote in it

Every one of those claims is probably true somewhere in its document. That is
exactly the trap: the check passes because the quote EXISTS, and nobody notices
that it does not REACH. In August this cost us an article — a lobbyists' block
quote printed as the committee's own finding, where every fragment was genuinely
in the document.

So before writing a claim, read your own quote back and ask: **if this sentence
were all I had, would it still say what I just wrote?** If the answer needs the
rest of the page, either quote the part that carries the circumstance, or drop
the circumstance from the claim. A narrower claim that its quote fully supports
is worth more than a fuller one that leans on a document the reader cannot see.

**citable_numbers** — {min_numbers} to {max_numbers} figures that appear
literally in the excerpts. Copy the digits exactly as written. Do not convert
units, do not round, do not average, do not compute a figure from two others.
A number that is not in the corpus will mislead the writer and must not enter the card.

**And say WHOSE number it is, in `means`, whenever the excerpt attributes it.**
"The UK AI Safety Institute measured X" is a different object from "a review
said the Institute measured X". The second one is a copy, and copies drift: a
real card carried "about seven times more likely" from two secondary reviews,
when the Institute's own report said 7% against 3% — a percentage rewritten as
a multiple. If the excerpt you are copying from is not the body that produced
the figure, put that in `means` explicitly, so the check downstream knows to go
and find the original.

**source_dates** — kiedy powstaly zrodla, na ktorych to stoi.

This is not bookkeeping. The writer is instructed to open with one datestamp,
and until now the card carried no date at all — so twenty-four cards produced
twenty-four articles with nothing to stamp. Worse, an article about a
fast-moving subject can rest entirely on material two years old and nothing in
the chain notices.

Give the real publication dates of the sources, not the dates of the events
they describe. If the newest thing you have is old, say so plainly in `note`:
"nothing here is more recent than [month]" is a sentence the writer needs, and
a reader deserves.

**main_mechanism** — the mechanism the article exists to explain: the
decision, constraint or trade-off that makes the thing work the way it does.
In a few sentences. This is where you say how the pieces connect. Ground each link in the
evidence. Explain the connecting steps in ordinary words for a non-specialist;
a technical label alone is not an explanation.

**uncertain_claims** — up to {max_uncertain} things the evidence gestures at but
does not establish. Being honest here is worth more than a longer confirmed list;
the writer can present these as open questions, which is legitimate, whereas
presenting them as fact is not.

**contradictions** — up to {max_contradictions} places where sources disagree, or
where the evidence cuts against the question's premise. If the premise is wrong,
say so plainly. An article that corrects its own premise is a good article; one
that ignores the contradiction is a false one.

**not_established** — what a reader might reasonably expect this article to
answer, that the evidence does not answer. The writer will place each material limit where it helps the reader
understand the claim it qualifies.

## Connections that help answer this question

Use `parallel_mechanisms` only for connections supported by the supplied passages
and useful to the investigation. Return an empty list when none is needed. Do not
invent examples from memory or force another industry into the article.

If an investigative briefing accompanies the question, prioritise the evidence
that distinguishes competing explanations and the strongest counterevidence.
An actor's possible gain is an inference, not proof of motive. Preserve meaningful
unknowns in `not_established`, including questions that research could not settle.
A company statement establishes its stated position; attribute it to the company.
Do not promote a hypothesis into `confirmed_claims` just because it has a plausible
story or a citation. The quoted passage must support the entire factual claim.

## Output

Return only valid JSON, shaped exactly as:

{{"working_thesis": "...", "main_mechanism": "...", "confirmed_claims": [{{"claim": "...", "evidence": "<verbatim excerpt>", "url": "..."}}], "citable_numbers": [{{"value": "...", "means": "...", "url": "..."}}], "parallel_mechanisms": [{{"domain": "...", "how_it_matches": "<one sentence: the same logic doing the same work>"}}], "uncertain_claims": ["..."], "contradictions": ["..."], "not_established": ["..."], "source_dates": {{"newest": "<YYYY-MM-DD of the most recent source you used>", "oldest": "<YYYY-MM-DD of the oldest>", "note": "<one clause: what the reader should know about how current this is>"}}}}

## The evidence

{evidence_json}
