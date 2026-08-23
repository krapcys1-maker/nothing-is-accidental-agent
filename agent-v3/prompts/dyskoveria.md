Search the web, then return {max_results} sources for this question:

{question}

{research_context}

Use this frame to select evidence, not to invent an answer. Keep the search on
the exact article route. The wider universe is context only; do not replace the
route with an omnibus survey. Include records that can test or contradict the
stated mechanism and second act.

Search first — you do not know which URLs exist, and any address from memory
will be discarded.

Every final URL must be copied character-for-character from a result displayed
by the search tool in this exact run. Never reconstruct a familiar official
path from memory. Before returning JSON, compare the final list against the
displayed result URLs and remove every non-match, even when you believe the
page exists. A separate exact-URL selector will enforce this rule.

Today is {current_date}. Do not confuse a proposed bill, draft rule or requested
study with an enacted rule or observed outcome. Prefer current official records
from the last three years for present scale and programme operation.

**Run at most {max_searches} searches, then stop and write the JSON.** Searching
without ever answering is a failed run: the answer is the only thing that counts,
and partial sources are worth more than none. If you have not found everything
after {max_searches} searches, return what you have.

Requirements:

1. At least {min_primary} sources must be PRIMARY — the record itself (a
   regulation, standard, filed report, dataset, study, patent, official
   statistic, or a company statement about its own products), not an article
   about the record. A catalogue or reseller listing the document is not the
   document.
   `class` describes the DOCUMENT. Separately classify the retrieval host as
   ORIGINATING_AUTHORITY, OFFICIAL_ARCHIVE, MIRROR, or OTHER. Prefer the
   originating public body. A primary record on a mirror remains a PRIMARY
   document but must be marked MIRROR; never count the mirror as its publisher.
   At least {min_origin_primary} PRIMARY documents must be on the originating
   authority's host or an official archive.
2. At least {min_why} sources must explain WHY the rule or practice exists — an
   impact assessment, consultation, regulator decision, audit, evaluation or
   peer-reviewed paper. Vendor and consultancy pages do not count.
3. At least one source must carry figures.
4. Use at least three different organisations. Any country, any language.
5. Free, no login, with the full evidence readable as HTML or text. `access_claim`
   is your search-time assessment, not a verified fetch result. A landing
   page whose report/download requires registration is LANDING_ONLY_OR_LOGIN
   and should not be selected. Mark access UNKNOWN if the search result does
   not establish full access. Skip these hosts, they block
   automated reading: {blocked_hosts}
6. No forums, Q&A sites or vendor blogs.
7. Cover three distinct evidence roles: MECHANISM (why liability transfers),
   CURRENT_SCALE (a current official registry, audit or programme record), and
   SECOND_ACT (the mine/Superfund parallel). Tag every source with one or more
   roles. CURRENT_SCALE must be an OBSERVED_CURRENT_RECORD, PRIMARY, and hosted
   by the originating authority or official archive.
8. At most {max_proposed} source may be PROPOSED_OR_PENDING. A proposed bill,
   memorial, draft rule or amnesty cannot by itself satisfy MECHANISM,
   CURRENT_SCALE or SECOND_ACT. It may show a live dispute, not an outcome.
9. When a supporting page links to the official audit, rule, dataset or report
   that carries its claim, select the underlying original. Do not substitute an
   advocacy press release or summary for a reachable official record.
10. Spend at least one search specifically on the SECOND_ACT and preserve an
    exact returned official URL for it. Do not use a remembered mine or
    Superfund URL to make the set look complete. Prefer an audit or programme
    record that shows the public mechanism actually operating, not merely a
    generic programme homepage.

If the evidence is not there, return what genuinely bears on the question,
including anything that contradicts it. Do not substitute pages that merely
restate a rule.

Select sources only. Do not answer the question.

Return only this JSON:

{{"sources": [{{"url": "...", "title": "...", "publisher": "...", "class": "PRIMARY"|"SUPPORTING", "host_role": "ORIGINATING_AUTHORITY"|"OFFICIAL_ARCHIVE"|"MIRROR"|"OTHER", "access_claim": "FULL_TEXT_NO_LOGIN"|"LANDING_ONLY_OR_LOGIN"|"UNKNOWN", "published_at": "YYYY-MM-DD or YYYY", "evidence_status": "OBSERVED_CURRENT_RECORD"|"ENACTED_OR_IN_FORCE"|"PROPOSED_OR_PENDING"|"HISTORICAL_ANALYSIS"|"UNKNOWN", "evidence_roles": ["MECHANISM"|"CURRENT_SCALE"|"SECOND_ACT"|"COUNTEREVIDENCE_OR_LIMIT"|"BACKGROUND"], "answers_why": true, "has_numbers": true, "note": "..."}}]}}
