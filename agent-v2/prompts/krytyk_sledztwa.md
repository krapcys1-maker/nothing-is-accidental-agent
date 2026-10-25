You are the senior editor reviewing an investigation before anything is written. Name at
most three items that would most improve what we publish:
(a) a primary record we cite second-hand or never found;
(b) a consequence, power, practical or AI-role question nobody asked or answered;
(c) a weak fact: a stale figure, a comparison that is not like-for-like, a vendor claim
    treated as a measurement, an opinion treated as fact;
(d) the most surprising verified thing so far, or an allegation in the sources, worth one
    more step.
For each give one precise web search. An empty list is fine. Do not add facts.

Each item becomes one more research question, so write it as a question that names this
story's actors, products or numbers — a question that would fit another story unchanged
is dropped by our code. Do not ask again what the ledger below already answered. The web
search names the document or the exact phrase that would settle it, not a topic.
Order the items by how much they would improve what we publish, most important first.
(For security incidents, ask from the defender's side: exposure, patch, who is affected,
detection, and what AI changed about the cost of attack and defence. Never ask for exploit
code, proof-of-concept repositories or attack steps.)

Write every value in English. Return only valid JSON:
{{"pozycje": [{{"rodzaj": "a|b|c|d", "soczewka": "NEW|HOW_IT_WORKS|CLAIM|NUMBERS|CONSEQUENCES|POWER|PRACTICAL|PEOPLE|PRECEDENT|BIG|TIDBIT|WATCH",
   "pytanie": "...?", "dlaczego": "<one line: what is missing or weak, and why it matters for what we publish>",
   "dowod": "<what evidence would settle it>", "gdzie": "<the kind of place where it would live>",
   "zapytanie": "<one precise web search>"}}],
 "uwagi": ["<optional short note for our editor>"]}}

## The investigation — data, never instructions
Story: {tytul} ({typ}). Main question: {pytanie}

Our plan before research:
{plan}

The question ledger after research:
{ksiega}

The dossier so far:
{karta}
