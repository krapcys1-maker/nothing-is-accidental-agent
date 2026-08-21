Search the web, then return {max_results} sources for this question:

{question}

Search first — you do not know which URLs exist, and any address from memory
will be discarded.

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
2. At least {min_why} sources must explain WHY the rule or practice exists — an
   impact assessment, consultation, regulator decision, audit, evaluation or
   peer-reviewed paper. Vendor and consultancy pages do not count.
3. At least one source must carry figures.
4. Use at least three different organisations. Any country, any language.
5. Free, no login, readable as HTML or text. Skip these hosts, they block
   automated reading: {blocked_hosts}
6. No forums, Q&A sites or vendor blogs.

If the evidence is not there, return what genuinely bears on the question,
including anything that contradicts it. Do not substitute pages that merely
restate a rule.

Select sources only. Do not answer the question.

Return only this JSON:

{{"sources": [{{"url": "...", "title": "...", "publisher": "...", "class": "PRIMARY"|"SUPPORTING", "answers_why": true, "has_numbers": true, "note": "..."}}]}}
