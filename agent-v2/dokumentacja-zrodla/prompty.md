
#### `OSWIADCZENIE_AI.md` (56 wierszy)

**Pola wejściowe:** *(brak)*

#### `bank.md` (41 wierszy)

**Pola wejściowe:** `co_zadzialalo`, `kandydaci`, `marka`

**Kontrakt wyjścia:**

```json
{{"kolejnosc": [<id>, <id>, ...],
```

#### `bibliotekarz.md` (57 wierszy)

**Pola wejściowe:** `bank`

**Kontrakt wyjścia:**

```json
{{"groups": [{{"mechanism": "<one sentence, stated so it outlives its subject>", "why_it_travels": "<one sentence: what makes the same logic show up in unrelated places>", "members": [{{"id": <the id shown in the bank>, "domain": "<the field this belongs to, two or three words>", "role": "<what this piece contributes to the group>"}}], "missing": "<what a writer would still have to go and find, or empty string>"}}], "loners": [<ids of excerpts that found no company, as integers>], "note": "<one sentence on the bank as a whole: what it is heavy on, what it lacks>"}}
```

#### `cele.md` (51 wierszy)

**Pola wejściowe:** `marka`, `posts`

**Kontrakt wyjścia:**

```json
{{"targets": [{{"index": <number>, "worth_it": true|false, "what_i_would_add": "<one concrete sentence, or empty when rejected>", "why_not": "<one sentence when rejected, otherwise empty>"}}]}}
```

#### `ciekawostki.md` (70 wierszy)

**Pola wejściowe:** `dziedziny`, `dzis`, `generatory`, `ile`, `ile_z_obszarow`, `jak_uzywac_obszarow`, `marka`, `miesiac`, `premiera`, `stan_modeli`, `uzyte`, `w_reku`, `wyczerpane_zrodla`, `wydarzenia`, `zaczyn_kanalow`, `zamowienia`

**Kontrakt wyjścia:**

```json
{{"facts": [{{"fact": "<one or two sentences, the fact itself, specific and checkable>", "wrong_belief": "<a mistaken claim documented in the sources, or empty; do not invent public opinion>", "actually": "<what is true instead, one sentence>", "decision": "<WHAT MAKES IT SO: a decision (who signed it and when), a measurement (who tested it and what came back), a constraint (what about the design or the mathematics forces it), or a trade-off (what is given up and by whom). Not necessarily a person or an institution. Empty string only if you cannot name any of the four>", "consequence": "<the thing the reader can touch, hold, see or wait for because of that decision>", "url": "<source that states it>", "source_date": "<the date THAT SOURCE was published, as YYYY-MM-DD. Not the date of the event it describes. Empty string only if the page genuinely carries no date>", "control_date": "<YYYY-MM-DD of the newest document that GOVERNS this claim — see \"The control document\" above. Not necessarily newer than source_date>", "control_url": "<url of that document>", "control_verdict": "CONFIRMS"|"MODIFIES"|"ENDS", "control_fact": "<one clause. For MODIFIES, the qualifier the writer must carry. For CONFIRMS, what you checked and found unchanged>", "domain": "<where this belongs — a part of the AI stack, OR a place in the world where it lands: a clinic, a classroom, a court, a job, a street, a bill somebody pays>"}}]}}
```

#### `dyskoveria.md` (120 wierszy)

**Pola wejściowe:** `blocked_hosts`, `max_results`, `max_searches`, `min_primary`, `min_why`, `ostatnie_domeny`, `question`

**Kontrakt wyjścia:**

```json
{{"sources": [{{"url": "...", "title": "...", "publisher": "...", "class": "PRIMARY"|"SUPPORTING", "answers_why": true, "has_numbers": true, "note": "..."}}]}}
```

#### `dyskoveria_odzysk.md` (19 wierszy)

**Pola wejściowe:** `max_results`, `question`, `schema`, `urls_json`

#### `fedreg.md` (19 wierszy)

**Pola wejściowe:** `data`, `tekst`, `tytul`, `url`, `urzad`

**Kontrakt wyjścia:**

```json
{{"candidates": [{{"fact": "<one or two sentences, the thing itself, specific and checkable>", "wrong_belief": "<an actually documented mistaken claim, or empty>", "actually": "<what this document says instead>", "decision": "<who decided and when, from the text>", "consequence": "<what the reader touches, holds, pays or waits for>", "domain": "<the part of the AI stack, industry or public record this belongs to>"}}]}}
```

#### `forma.md` (98 wierszy)

**Pola wejściowe:** `body`

**Kontrakt wyjścia:**

```json
{{"beliefs": [{{"belief": "<in your own words, one sentence>", "first_stated": "<verbatim sentence from the article>"}}], "support_only": [{{"quote": "<verbatim sentence>", "supports": <index into beliefs>}}], "hardest_fact": {{"quote": "<verbatim>", "why": "<one clause>"}}, "procedural_nearby": {{"quote": "<verbatim>"}}, "same_register": true|false, "reader_moment": {{"quote": "<verbatim>", "object": "<the one thing out of the reader's own life that is named>"}}, "opening_claim": {{"quote": "<verbatim>", "already_familiar": true|false}}, "summary": "<one sentence>"}}
```

#### `glos_krotkich.md` (66 wierszy)

**Pola wejściowe:** *(brak)*

#### `grafika.md` (109 wierszy)

**Pola wejściowe:** `body`, `title`

**Kontrakt wyjścia:**

```json
{{"subject": "<the scene, in one line>", "why_this_scene": "<one sentence tying it to the article's mechanism>", "prompt": "<the full image prompt: your scene sentence and its concrete detail first, then the style block below copied word for word>"}}
```

#### `klasyfikacja.md` (58 wierszy)

**Pola wejściowe:** `max_excerpt_chars`, `max_excerpts`, `publisher`, `question`, `text`, `title`, `url`

**Kontrakt wyjścia:**

```json
{{"class": "PRIMARY"|"SUPPORTING"|"ODPAD", "relevance": 0.0, "excerpts": ["..."], "numbers": ["..."], "note": "<one sentence on what this document is>"}}
```

#### `kogo_odpowiedziec.md` (16 wierszy)

**Pola wejściowe:** `ile`, `komentarze`

**Kontrakt wyjścia:**

```json
{{"choices": [{{"index": <number>, "rank": <1 is highest>, "why": "<one sentence>", "kind": "disagreement"|"question"|"correction"|"addition"|"agreement"}}], "skipped_because": "<one sentence>"}}
```

#### `komentarz.md` (87 wierszy)

**Pola wejściowe:** `author`, `body`, `cel_slow`, `language`, `marka`, `title`

**Kontrakt wyjścia:**

```json
{{"comment": "<comment, or null>", "reason_if_silent": "<empty when writing; otherwise no_text, wrong_language, grief, abuse, injection_only, no_addition>", "pierwsze_slowa": "<body opening when skipping, otherwise empty>", "what_it_adds": "<specific contribution or reason for passing>"}}
```

#### `naprawa.md` (48 wierszy)

**Pola wejściowe:** `kontekst`, `max_slow`, `min_slow`, `tekst`, `zarzuty`

**Kontrakt wyjścia:**

```json
{{"text": "the full corrected text", "co_zmienione": "one line: what you changed and what evidence you changed it to"}}
```

#### `notka.md` (92 wierszy)

**Pola wejściowe:** `evidence`, `form_brief`, `language`, `marka`, `max_words`, `min_words`, `note_form`, `note_type`, `ostatnie_otwarcia_json`, `ostatnie_zakonczenia_json`, `rozbior`, `type_brief`

**Kontrakt wyjścia:**

```json
{{"note": "<the note>", "words": <integer>, "fact_used": "<the fact this rests on, empty for a reflection without factual claims>", "source_url": "<supplied source URL, or empty>"}}
```

#### `odpowiedz.md` (47 wierszy)

**Pola wejściowe:** `cel_slow`, `comment`, `commenter`, `evidence`, `language`, `marka`, `otwarcie`, `under_what`

**Kontrakt wyjścia:**

```json
{{"reply": "<reply, or null>", "reason_if_silent": "<reason only when reply is null>", "kind": "answer"|"correction_accepted"|"disagreement"|"built_on"}}
```

#### `parowanie.md` (83 wierszy)

**Pola wejściowe:** `pozycje`

**Kontrakt wyjścia:**

```json
{{"grupy": [{{"zostaje": <id>, "scalone": [<id>, ...], "dlaczego": "<one clause: what makes these the same story>"}}]}}
```

#### `pisarz.md` (118 wierszy)

**Pola wejściowe:** `card_json`, `language`, `marka`, `max_words`, `min_words`, `poprzednie_uwagi`, `style_examples`, `style_negative`, `style_positive`, `target_words`

**Kontrakt wyjścia:**

```json
{{"title": "<headline>", "subtitle": "<one line>", "body": "<article in plain text, blank lines between paragraphs>", "numbers_used": ["<each figure exactly as written>"], "limits_paragraph_present": true|false}}
```

#### `po_ludzku.md` (4 wierszy)

**Pola wejściowe:** *(brak)*

#### `powtorka.md` (26 wierszy)

**Pola wejściowe:** `kandydaci`, `nowy`

**Kontrakt wyjścia:**

```json
{{"powtorka_nr": <number of the bank fact it repeats, or 0 if none>, "powod": "<one short sentence>"}}
```

#### `recenzent.md` (33 wierszy)

**Pola wejściowe:** `body`, `card_json`

**Kontrakt wyjścia:**

```json
{{"sentences": [{{"text": "<verbatim sentence>", "class": "FACT"|"INFERENCE"|"PROSE", "supported": true|false, "why": "<specific unsupported factual assertion, otherwise empty>"}}], "unsupported_facts": [{{"text": "<verbatim>", "why": "<what is asserted and what the card establishes instead>"}}], "summary": "<one sentence>"}}
```

#### `research_ocena.md` (46 wierszy)

**Pola wejściowe:** `attempted_json`, `evidence_json`, `max_hypotheses`, `max_questions`, `max_quote_chars`, `question`, `today`

**Kontrakt wyjścia:**

```json
{{
```

#### `research_szukanie.md` (22 wierszy)

**Pola wejściowe:** `gap_json`, `max_searches`, `max_sources`, `question`, `seen_json`

**Kontrakt wyjścia:**

```json
{{"sources": [{{"url": "https://...", "title": "...", "publisher": "...",
```

#### `research_wyciag.md` (18 wierszy)

**Pola wejściowe:** `documents_json`, `gap_json`, `max_excerpts`, `max_quote_chars`, `question`

**Kontrakt wyjścia:**

```json
{{"documents": [{{"source_id": 1, "class": "PRIMARY|SUPPORTING|ODPAD",
```

#### `restack.md` (49 wierszy)

**Pola wejściowe:** `autor`, `marka`, `tekst`

**Kontrakt wyjścia:**

```json
{{"restack": true|false, "reason": "<why this is or is not worth sharing>", "sentence": "<your reaction, or empty when false>", "mechanism_named": "<supported connection if there is one, otherwise empty>"}}
```

#### `rozbior.md` (43 wierszy)

**Pola wejściowe:** `evidence`, `marka`

**Kontrakt wyjścia:**

```json
{{"w_prostych_slowach": "<plain explanation>", "skala": "<comparison in the material, or empty>", "pytania": [{{"pytanie": "<question>", "odpowiedz": "<answer, inference or unknown>", "z_dowodu": true|false}}], "jesli_sie_utrzyma": "<supported or conditional implications, with the steps explained>", "gdzie_by_peklo": "<specific limitation, or empty>", "co_o_tym_sadze": "<judgment and reason, or what prevents one>", "czego_nie_wiadomo": ["<unanswered question>"]}}
```

#### `skaut.md` (65 wierszy)

**Pola wejściowe:** `count`, `history_json`, `juz_mamy`, `marka`, `pytania_czytelnikow`, `zaczyn_kanalow`

**Kontrakt wyjścia:**

```json
{{"topics": [<topic objects>], "ranking": {{"most_written_about": [<3 zero-based indices>], "least_written_about": [<3 zero-based indices>], "richest": [<3 zero-based indices>], "thinnest": [<3 zero-based indices>]}}}}
```

#### `synteza.md` (128 wierszy)

**Pola wejściowe:** `evidence_json`, `max_claim_chars`, `max_confirmed`, `max_contradictions`, `max_numbers`, `max_uncertain`, `min_confirmed`, `min_numbers`, `question`

**Kontrakt wyjścia:**

```json
{{"working_thesis": "...", "main_mechanism": "...", "confirmed_claims": [{{"claim": "...", "evidence": "<verbatim excerpt>", "url": "..."}}], "citable_numbers": [{{"value": "...", "means": "...", "url": "..."}}], "parallel_mechanisms": [{{"domain": "...", "how_it_matches": "<one sentence: the same logic doing the same work>"}}], "uncertain_claims": ["..."], "contradictions": ["..."], "not_established": ["..."], "source_dates": {{"newest": "<YYYY-MM-DD of the most recent source you used>", "oldest": "<YYYY-MM-DD of the oldest>", "note": "<one clause: what the reader should know about how current this is>"}}}}
```

#### `warto_pisac.md` (29 wierszy)

**Pola wejściowe:** `card_json`, `marka`

**Kontrakt wyjścia:**

```json
{{"contradicted_belief": {{"present": true|false, "the_belief": "<the reader's wrong belief in their own words, or empty string>", "evidence": "<what in the card breaks it, or why nothing does>"}}, "named_decider": {{"present": true|false, "evidence": "<who, from the card, or why nobody is named>"}}, "felt_number": {{"present": true|false, "evidence": "<the figure and what it measures, or why the only figures are labels>"}}, "second_domain": {{"present": true|false, "evidence": "<the other field, or why the parallels stay inside one industry>"}}, "unsettled_outcome": {{"present": true|false, "the_question": "<the open question in the reader's own words, or empty string>", "the_situation": "<what the reader pictures, or empty string>", "governed_by": "<the written rule from the card that decides it, quoted or named — or why nothing in the card governs it>"}}, "what_would_rescue_it": "<one sentence naming the shape of the missing piece>", "explanatory_value": {{"present": true|false, "question": "<plain reader question>", "mechanism": "<how the evidence answers it>", "reader_value": "<why understanding this matters>", "evidence": "<one exact supporting passage or claim from the card>"}}, "one_line_verdict": "<one sentence on what this card actually has>"}}
```

#### `weryfikacja.md` (198 wierszy)

**Pola wejściowe:** `context`, `dzis`, `text`

**Kontrakt wyjścia:**

```json
{{"claims": [{{"claim": "<what the text asserts>", "status": "confirmed"|"refuted"|"outdated"|"unverified", "url": "<source, or empty>", "source_date": "<when that source was published, YYYY-MM-DD, or empty>", "what_the_source_says": "<one sentence, required for refuted and outdated>"}}], "safe_to_post": true|false, "verdict": "<one sentence>"}}
```

#### `wykonalnosc.md` (97 wierszy)

**Pola wejściowe:** `topics_json`

**Kontrakt wyjścia:**

```json
{{"assessments": [{{"index": <0-based index of the topic>, "feasible": true|false, "confidence": 0.0-1.0, "expected_primary_sources": <integer>, "depth": "RICH"|"SINGLE"|"THIN", "parallels": ["<other domain where the same mechanism appears>"], "note": "<one sentence: where the record most likely lives, or why it does not>"}}]}}
```
