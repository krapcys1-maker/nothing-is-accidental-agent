You are extracting the parts of one source document that bear on a research
question, and judging what kind of source it is.

You are not writing anything and not answering the question. You are a filter:
what you pass through is all the writer will ever see of this document.

## The research question

{question}

## What to return

**class** — one of:
- `PRIMARY` — this document is itself a record: a regulation, a filed report, a
  standard, a dataset, a study, an official statistic, a company statement about
  its own products.
- `SUPPORTING` — it describes or comments on somebody else's record.
- `ODPAD` — it does not bear on the question at all, or carries no substance
  (a navigation page, a stub, a catalogue listing, marketing copy).

**relevance** — 0.0 to 1.0, how much this document actually helps answer the
question. Be honest: a document can be impeccably authoritative and still not
speak to what was asked.

**excerpts** — up to {max_excerpts} verbatim passages from the document, each at
most {max_excerpt_chars} characters, that bear directly on the question.

Copy them EXACTLY as they appear. Do not paraphrase, do not tidy the grammar, do
not join two distant sentences into one. Every later stage treats these as the
evidence of record, and a sentence you smoothed is a sentence the writer will
quote as fact.

Prefer passages that state a rule, a reason, a threshold, a decision or a
measurement over passages that merely introduce a topic.

The metadata below describes the document, not automatically every claim in it.
A live page may contain a report published in one year and a recommendation
status updated years later. Preserve explicit dates inside the verbatim passage.
Never replace an excerpt's own "as of" date with the publication date or the
retrieval date. Retrieval is only the moment this copy was observed.

Numbers are extracted deterministically from the accepted verbatim passages
after this step. Do not create a separate list of them.

## Output

Return only valid JSON, shaped exactly as:

{{"class": "PRIMARY"|"SUPPORTING"|"ODPAD", "relevance": 0.0, "excerpts": ["..."], "note": "<one sentence on what this document is>"}}

## The document

Title: {title}
Publisher: {publisher}
URL: {url}
Published: {published_at}
Retrieved: {retrieved_at}
Evidence status: {evidence_status}
Expected evidence roles: {evidence_roles}

---
{text}
