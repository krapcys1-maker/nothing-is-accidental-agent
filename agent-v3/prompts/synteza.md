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
genuinely establishes. Each must carry one or more `fragment_ids` from the
evidence below. Do not copy or invent an ID. If no listed fragment supports the
claim, it is not confirmed. Each claim at most {max_claim_chars} characters.

**citable_numbers** — {min_numbers} to {max_numbers} figures that appear
in the deterministic `numbers` inventory below. Select its exact `number_id`,
say what it means, and point to the zero-based `claim_index` whose fragments
contain that number. Do not copy digits into this output, convert units, round,
average or compute a figure. A number not tied to both a fragment and a claim is
rejected by code.

**main_mechanism** — the hidden system the article exists to explain, in a few
sentences. This is where you say how the pieces connect. Ground each link in the
evidence.

**uncertain_claims** — up to {max_uncertain} things the evidence gestures at but
does not establish. Being honest here is worth more than a longer confirmed list;
the writer can present these as open questions, which is legitimate, whereas
presenting them as fact is not.

**contradictions** — up to {max_contradictions} places where sources disagree, or
where the evidence cuts against the question's premise. If the premise is wrong,
say so plainly. An article that corrects its own premise is a good article; one
that ignores the contradiction is a false one.

**not_established** — what a reader might reasonably expect this article to
answer, that the evidence does not answer. The writer will state these limits
once, in the text.

## Time and evidence status

`published_at` describes the document, `retrieved_at` says when this exact live
copy was observed, and `evidence_status`/`evidence_roles` preserve why discovery
selected it. None of these fields is automatically the date of every claim. A
live page can combine a 2019 report with a recommendation status updated in
2026. When a fragment contains its own date or "as of" qualifier, that exact
fragment controls. Never silently move a claim to the document publication or
retrieval date.

## Where else this same shape appears

This is the field that decides whether the article is interesting or merely
correct, so give it real thought.

Name **two to four other domains where the same mechanism shows up**. Not
loose comparisons — the same logic doing the same work somewhere the reader
would not expect.

A worked example from a piece that succeeded. The subject was the vent hole in
an aircraft window: pierce the inner pane so it carries no pressure, and the
outer pane takes the whole load. The shape is *build a deliberate weakness so
you can choose where the strength goes*. The same shape is the electrical fuse,
the sacrificial anode on a ship's hull, and the crumple zone in a car. Three
domains, one idea, and the article became about something larger than a window.

A piece that failed had none of this. The open-jar symbol on cosmetics is a
countdown that starts when you break the seal — true, sourced, and finished in
two sentences. With nothing to open outward into, it was padded to eleven
hundred words and nobody was any richer for reading it.

These are the writer's READING, not claims from the record. The comparison itself
does not need a source, but any factual premise embedded in it must already exist
as a `confirmed_claim`. A parallel that does not survive a moment's thought is
worse than none, because it invites the reader to stop trusting the sourced parts.

If the mechanism genuinely appears nowhere else, return an empty list. Saying so
honestly lets the article be written short instead of stretched.

## Output

Return only valid JSON, shaped exactly as:

{{"working_thesis": "...", "main_mechanism": "...", "confirmed_claims": [{{"claim": "...", "fragment_ids": ["frag_v1_..."]}}], "citable_numbers": [{{"number_id": "num_v1_...", "means": "...", "claim_index": 0}}], "parallel_mechanisms": [{{"domain": "...", "how_it_matches": "<one sentence: the same logic doing the same work>"}}], "uncertain_claims": ["..."], "contradictions": ["..."], "not_established": ["..."]}}

## The evidence

{evidence_json}
