Find exactly {max_results} authoritative sources for this research question.

Search the whole web. No country, sector or language is preferred — go wherever
the record actually is.

## Every source must be readable

Publicly fetchable without login or subscription, served as HTML or plain text,
and readable by a plain HTTP client with no bot protection.

Primary records are often published as PDFs, which this fetcher cannot read.
When the record itself is a PDF, return the issuing body's own HTML page for it —
the landing, summary, abstract, chapter, table or data page carrying the
substance — rather than a third party writing about it.

Never return these hosts; they serve a CAPTCHA to automated requests or sit
behind a paywall, so they come back empty however authoritative they are:
{blocked_hosts}

## At least {min_primary} must be PRIMARY

A primary source is the originating record itself — the study, report, dataset,
official statistic, patent, standard, regulator decision or first-party company
statement about its own products — not press coverage of it. If an article cites
a study, return the study's own page.

**A catalogue is not the document.** At least one primary source must sit on the
issuing body's own domain. A library record, bibliographic service, index or
standards reseller that merely LISTS the document is not the document, however
official the listing looks — it carries a title, a reference number and a price,
not the substance. If the record is only reachable through such a service, find
the issuing body's own page, or say the record is unavailable and return what
genuinely bears on the question.

A corpus of blogs, association posts and forum threads has no originating record
and is rejected outright. Never return a forum thread, a Q&A site or a vendor
blog as one of the required sources.

## At least {min_why} must explain WHY

The question asks about a mechanism — something happening because of a specific
incentive, rule or constraint. Rule text alone cannot evidence why anyone behaves
a certain way; a corpus of pure rule statements produces a confident-sounding
article with nothing behind it.

So at least {min_why} sources must speak to the why, and both must be
institutional: an impact assessment, a consultation or its published response, a
regulator's decision or review, a national audit report, a post-implementation
evaluation, an official inquiry, a standards body, or peer-reviewed academic work.

A vendor, supplier, consultancy or service-provider page does NOT count toward
these, however well it describes the incentive — a seller explaining why its own
product gets bought is marketing. Return such pages only as extra context.

At least one source must carry quantified data — figures, rates, volumes or
shares — not only description.

## Spread the sources

Use at least three different organisations.

These domains were used by recent articles. Prefer sources outside them, so the
publication does not become a newsletter about one institution:
{recent_domains}

## If the evidence is not there

Return the sources that bear on the question anyway, including any that
contradict its premise. Do not substitute topically adjacent pages that merely
restate a rule. An honest empty answer costs one search; a fabricated one costs
the whole article.

## Output

Source selection only — do not synthesise claims or answer the question.

Return only valid JSON, shaped exactly as:

{{"sources": [{{"url": "<exact url as returned by search>", "title": "<page title>", "publisher": "<organisation that published it>", "class": "PRIMARY"|"SUPPORTING", "answers_why": true|false, "has_numbers": true|false, "note": "<one sentence on what this source contains>"}}]}}

## The research question

{question}
