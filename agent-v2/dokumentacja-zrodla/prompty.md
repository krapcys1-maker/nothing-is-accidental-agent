
#### `OSWIADCZENIE_AI.md` (56 wierszy)

**Pola wejściowe:** *(brak)*

#### `bibliotekarz.md` (54 wierszy)

**Pola wejściowe:** `bank`

**Kontrakt wyjścia:**

```json
{{"groups": [{{"mechanism": "<one sentence, stated so it outlives its subject>", "why_it_travels": "<one sentence: what makes the same logic show up in unrelated places>", "members": [{{"id": <the id shown in the bank>, "domain": "<the field this belongs to, two or three words>", "role": "<what this piece contributes to the group>"}}], "missing": "<what a writer would still have to go and find, or empty string>"}}], "loners": [<ids of excerpts that found no company, as integers>], "note": "<one sentence on the bank as a whole: what it is heavy on, what it lacks>"}}
```

#### `cele.md` (53 wierszy)

**Pola wejściowe:** `posts`

**Kontrakt wyjścia:**

```json
{{"targets": [{{"index": <number>, "worth_it": true|false, "what_i_would_add": "<one concrete sentence, or empty when worth_it is false>", "why_not": "<one sentence, only when worth_it is false>"}}]}}
```

#### `ciekawostki.md` (254 wierszy)

**Pola wejściowe:** `dziedziny`, `dzis`, `generatory`, `ile`, `miesiac`, `stan_modeli`, `uzyte`, `w_reku`, `zaczyn_kanalow`

**Kontrakt wyjścia:**

```json
{{"facts": [{{"fact": "<one or two sentences, the fact itself, specific and checkable>", "wrong_belief": "<what most people believe, written as a plain sentence they would say out loud>", "actually": "<what is true instead, one sentence>", "decision": "<who decided it and when — a body, a committee, a statute, a year. Empty string if the record names nobody>", "consequence": "<the thing the reader can touch, hold, see or wait for because of that decision>", "url": "<source that states it>", "source_date": "<the date THAT SOURCE was published, as YYYY-MM-DD. Not the date of the event it describes. Empty string only if the page genuinely carries no date>", "domain": "<the everyday area it belongs to>"}}]}}
```

#### `dyskoveria.md` (41 wierszy)

**Pola wejściowe:** `blocked_hosts`, `max_results`, `max_searches`, `min_primary`, `min_why`, `ostatnie_domeny`, `question`

**Kontrakt wyjścia:**

```json
{{"sources": [{{"url": "...", "title": "...", "publisher": "...", "class": "PRIMARY"|"SUPPORTING", "answers_why": true, "has_numbers": true, "note": "..."}}]}}
```

#### `fedreg.md` (92 wierszy)

**Pola wejściowe:** `data`, `tekst`, `tytul`, `url`, `urzad`

**Kontrakt wyjścia:**

```json
{{"candidates": [{{"fact": "<one or two sentences, the thing itself, specific and checkable>", "wrong_belief": "<what an ordinary reader would assume, in their words>", "actually": "<what this document says instead>", "decision": "<who decided and when, from the text>", "consequence": "<what the reader touches, holds, pays or waits for>", "domain": "<the everyday area this belongs to>"}}]}}
```

#### `forma.md` (87 wierszy)

**Pola wejściowe:** `body`

**Kontrakt wyjścia:**

```json
{{"beliefs": [{{"belief": "<in your own words, one sentence>", "first_stated": "<verbatim sentence from the article>"}}], "support_only": [{{"quote": "<verbatim sentence>", "supports": <index into beliefs>}}], "hardest_fact": {{"quote": "<verbatim>", "why": "<one clause>"}}, "procedural_nearby": {{"quote": "<verbatim>"}}, "same_register": true|false, "reader_moment": {{"quote": "<verbatim>", "object": "<the thing the reader holds>"}}, "opening_claim": {{"quote": "<verbatim>", "already_familiar": true|false}}, "summary": "<one sentence>"}}
```

#### `grafika.md` (78 wierszy)

**Pola wejściowe:** `body`, `title`

**Kontrakt wyjścia:**

```json
{{"subject": "<the object, in a few words>", "why_this_object": "<one sentence tying it to the article's mechanism>", "prompt": "<the full image prompt: your subject sentence first, then the style block below copied word for word>"}}
```

#### `klasyfikacja.md` (54 wierszy)

**Pola wejściowe:** `max_excerpt_chars`, `max_excerpts`, `publisher`, `question`, `text`, `title`, `url`

**Kontrakt wyjścia:**

```json
{{"class": "PRIMARY"|"SUPPORTING"|"ODPAD", "relevance": 0.0, "excerpts": ["..."], "numbers": ["..."], "note": "<one sentence on what this document is>"}}
```

#### `kogo_odpowiedziec.md` (46 wierszy)

**Pola wejściowe:** `ile`, `komentarze`

**Kontrakt wyjścia:**

```json
{{"choices": [{{"index": <number>, "rank": <1 is highest>, "why": "<one sentence>", "kind": "disagreement"|"question"|"correction"|"addition"|"agreement"}}], "skipped_because": "<one sentence about the ones you left out>"}}
```

#### `komentarz.md` (171 wierszy)

**Pola wejściowe:** `author`, `body`, `cel_slow`, `language`, `otwarcie`, `postawa`, `postawa_opis`, `title`

**Kontrakt wyjścia:**

```json
{{"comment": "<the comment, or null>", "reason_if_silent": "<one sentence, only when comment is null>", "what_it_adds": "<one sentence naming what this comment contributes that the post did not say>"}}
```

#### `notka.md` (280 wierszy)

**Pola wejściowe:** `evidence`, `form_brief`, `language`, `max_words`, `min_words`, `note_form`, `note_type`, `ostatnie_otwarcia_json`, `type_brief`

**Kontrakt wyjścia:**

```json
{{"note": "<the note>", "words": <integer>, "fact_used": "<the single fact from the evidence this rests on>", "source_url": "<the url that fact came from>"}}
```

#### `odpowiedz.md` (183 wierszy)

**Pola wejściowe:** `cel_slow`, `comment`, `commenter`, `evidence`, `language`, `otwarcie`, `under_what`

**Kontrakt wyjścia:**

```json
{{"reply": "<the reply, or null>", "reason_if_silent": "<one sentence, only when reply is null>", "kind": "answer"|"correction_accepted"|"disagreement"|"built_on"}}
```

#### `pisarz.md` (433 wierszy)

**Pola wejściowe:** `card_json`, `ile_paraleli`, `kotwica_dlugosci`, `language`, `max_words`, `min_words`, `ruch_koncowy`, `ruch_koncowy_nazwa`, `style_examples`, `style_negative`, `style_positive`, `target_words`

**Kontrakt wyjścia:**

```json
{{"title": "<the published headline>", "subtitle": "<one line>", "body": "<the article, plain text with blank lines between paragraphs>", "numbers_used": ["<each figure you wrote, exactly as written>"], "limits_paragraph_present": true|false}}
```

#### `recenzent.md` (59 wierszy)

**Pola wejściowe:** `body`, `card_json`

**Kontrakt wyjścia:**

```json
{{"sentences": [{{"text": "<the sentence, verbatim>", "class": "FACT"|"INFERENCE"|"PROSE", "supported": true|false, "why": "<only when class is FACT and supported is false: what is asserted and what the card lacks>"}}], "unsupported_facts": [{{"text": "...", "why": "..."}}], "summary": "<one sentence>"}}
```

#### `restack.md` (82 wierszy)

**Pola wejściowe:** `autor`, `tekst`

**Kontrakt wyjścia:**

```json
{{"restack": true|false, "reason": "<one sentence: why this is or is not worth passing on>", "sentence": "<your sentence, or empty string if restack is false>", "mechanism_named": "<the other place this same logic runs, or empty string>"}}
```

#### `skaut.md` (499 wierszy)

**Pola wejściowe:** `count`, `history_json`, `pytania_czytelnikow`, `zaczyn_kanalow`

**Kontrakt wyjścia:**

```json
{{"when": "<roughly when>", "what_happened": "<what people saw, in one sentence>", "what_changed": "<the rule or practice that came out of it, or 'nothing'>"}}
```

#### `synteza.md` (95 wierszy)

**Pola wejściowe:** `evidence_json`, `max_claim_chars`, `max_confirmed`, `max_contradictions`, `max_numbers`, `max_uncertain`, `min_confirmed`, `min_numbers`, `question`

**Kontrakt wyjścia:**

```json
{{"working_thesis": "...", "main_mechanism": "...", "confirmed_claims": [{{"claim": "...", "evidence": "<verbatim excerpt>", "url": "..."}}], "citable_numbers": [{{"value": "...", "means": "...", "url": "..."}}], "parallel_mechanisms": [{{"domain": "...", "how_it_matches": "<one sentence: the same logic doing the same work>"}}], "uncertain_claims": ["..."], "contradictions": ["..."], "not_established": ["..."]}}
```

#### `warto_pisac.md` (143 wierszy)

**Pola wejściowe:** `card_json`

**Kontrakt wyjścia:**

```json
{{"contradicted_belief": {{"present": true|false, "the_belief": "<the reader's wrong belief in their own words, or empty string>", "evidence": "<what in the card breaks it, or why nothing does>"}}, "named_decider": {{"present": true|false, "evidence": "<who, from the card, or why nobody is named>"}}, "felt_number": {{"present": true|false, "evidence": "<the figure and what it measures, or why the only figures are labels>"}}, "second_domain": {{"present": true|false, "evidence": "<the other field, or why the parallels stay inside one industry>"}}, "unsettled_outcome": {{"present": true|false, "the_question": "<the open question in the reader's own words, or empty string>", "the_situation": "<what the reader pictures, or empty string>", "governed_by": "<the written rule from the card that decides it, quoted or named — or why nothing in the card governs it>"}}, "what_would_rescue_it": "<one sentence naming the shape of the missing piece>", "one_line_verdict": "<one sentence on what this card actually has>"}}
```

#### `weryfikacja.md` (139 wierszy)

**Pola wejściowe:** `context`, `dzis`, `text`

**Kontrakt wyjścia:**

```json
{{"claims": [{{"claim": "<what the text asserts>", "status": "confirmed"|"refuted"|"outdated"|"unverified", "url": "<source, or empty>", "source_date": "<when that source was published, YYYY-MM-DD, or empty>", "what_the_source_says": "<one sentence, required for refuted and outdated>"}}], "safe_to_post": true|false, "verdict": "<one sentence>"}}
```

#### `wykonalnosc.md` (95 wierszy)

**Pola wejściowe:** `topics_json`

**Kontrakt wyjścia:**

```json
{{"assessments": [{{"index": <0-based index of the topic>, "feasible": true|false, "confidence": 0.0-1.0, "expected_primary_sources": <integer>, "depth": "RICH"|"SINGLE"|"THIN", "parallels": ["<other domain where the same mechanism appears>"], "note": "<one sentence: where the record most likely lives, or why it does not>"}}]}}
```
