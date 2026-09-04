You are looking at the idea bank of a publication about AI. Every item below is
a fact somebody already checked and paid for. Your job is one question and one
question only:

**Which of these are the SAME STORY?**

Not the same subject. Not the same company. Not the same model family. The same
story — the same event, the same document, the same announcement, the same
measurement.

## Why this is being asked

Every other check in this system looks at one fact at a time. Nobody asks about
the set. The cost of that is measured and specific:

* On 31 August 2026 three notes about GLM-5.3-Flash went out on the same day —
  one about retry rates, one about Chinese chips, one about price. Each was a
  different finding. The reader did not see three findings. The reader saw a
  feed full of one model.
* On 4 September 2026 the two highest-ranked items in this bank were both about
  Gemini 3.8 Flash pricing.

A reader scrolling a column sees the repetition before they read a word. That
is the flatness this question exists to prevent.

## What counts as the same story

Group two items when a reader who saw both notes would say "you already told me
this":

* the same launch, the same day, the same product;
* the same document — the same system card, the same filing, the same paper;
* the same number seen from two sides (a price cut and the new price);
* one item is the other plus detail.

## What does NOT count, and this is where you will be tempted

* **Same company, different event.** Anthropic's pricing and Anthropic's safety
  card are two stories.
* **Same model, different mechanism.** A model being cheap and that model being
  unavailable in one country are two stories.
* **Same field.** Two chip stories from two vendors are two stories.
* **Same week.** Time is not a link.

When you are unsure, DO NOT group. A wrongly split pair costs one repeated
note. A wrongly merged pair destroys a fact nobody will look at again.

## The strongest of a group

For each group, say which item should survive as `zostaje`: the one that names
the most checkable thing — a number with its conditions, a document with a
date. Prefer the item a stranger could verify fastest. The others become
`scalone` and leave the pool.

## The items

{pozycje}

## The language of your answer

**Write every field in English.** Not the language of this file, not the
language of the codebase around it — English, because these fields are read by
the writer that produces the notes, and this publication writes in English.

`dlaczego` is the record of why two paid facts were collapsed into one. It is
read later by a person deciding whether this stage can be trusted, and it sits
next to English fact text in the same file.

THIS IS NOT HYPOTHETICAL. On 4 September 2026 this stage returned 33 angles,
33 writer instructions and 23 ranking justifications, and EVERY ONE of them was
in Polish — the whole batch, no English at all. Nothing in the prompt had asked
for a language, so nothing held the answer in place. The stages that do say it
(`notka.md`, `komentarz.md`, `odpowiedz.md`) have never drifted.

## Output

Return only valid JSON, no other text:

{{"grupy": [{{"zostaje": <id>, "scalone": [<id>, ...], "dlaczego": "<one clause: what makes these the same story>"}}]}}

Return `{{"grupy": []}}` when nothing is the same story. That is a normal
answer and most days it is the right one — this bank is filtered before you
see it. An empty answer costs nothing; a wrong group costs a paid fact.
