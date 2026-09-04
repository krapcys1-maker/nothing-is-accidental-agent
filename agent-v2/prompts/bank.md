Rank these candidate facts against each other, strongest first, and say which
ones this publication should throw away.

Nothing Is Accidental is a publication **about artificial intelligence**: what
these systems actually do, how they are built, who decides what they are allowed
to do, and what that arrangement hands the people who built it.

## You are RANKING, not scoring

Put them in order, best to worst. Every position is different — there are no
ties and there is no "all of these are good".

This is deliberate. Asked to score things one by one, a model gives almost
everything the same high mark and the ranking carries no information. Asked to
put them in order, it has to decide. So the order is the answer; a number would
not be.

## What actually landed on this account — read this before ranking

Not opinions about what performs. These are our own notes with the reception
they measurably got: likes, replies, and how many people were shown them.

{co_zadzialalo}

Read the two groups against each other before you rank anything, and notice
what separates them rather than what they are about. Then say, for the ones you
put near the top, which side they resemble.

Two warnings about reading this evidence, both from real mistakes:

- **Views are not success.** A note shown to fifty people and liked by two did
  worse than one shown to twenty-three and answered by five. The measure that
  matters is whether anybody did something that costs them a moment — and a
  reply costs more than a like.
- **Do not copy the subjects, copy what made them work.** The strongest note on
  this account happens to be about how reasoning models present their reasoning.
  That does not mean "write more about reasoning models". It means the reader
  recognised something they had personally seen and had wrong.

## What makes one stronger than another

In roughly this order of weight:

1. **A stranger would stop scrolling for it.** Not "this is important" — would
   somebody who does not work in this field read the second sentence?
2. **It is checkable and the check would be interesting.** A specific figure, a
   named document, a measurement somebody ran.
3. **It explains a mechanism the reader has met without understanding.** Why the
   answer arrives that fast, why the middle of a long chat is forgotten, why one
   provider's bill is five times another's for the same model.
4. **The consequence reaches the reader.** Something they hold, pay, wait for or
   are judged by — not something that happens to an industry.
5. **It is not the news everybody already ran.** A model launch that three
   channels covered this week is not a finding.

## What to throw away — and the bar is high, on purpose

Throwing away is **permanent**. The candidate was paid for, and once it is gone
it never comes back. Keeping a mediocre one costs a single further look.

So `wyrzuc: true` is for things that are **definitionally not ours**, never for
things that are merely weaker than their neighbours. Weaker belongs at the
bottom of the order — that is what the order is for.

There are exactly three grounds, and you must name which one applies by its
code. You are choosing from a list of three, not writing a sentence — if none
of the three fits, the candidate is not being thrown away.

- **`NOT_AI`** — not about artificial intelligence. The most common one and the
  least forgivable. A fact about pharmaceutical regulation, food labelling or
  car dealerships is not our subject however good it is. Judge the SUBJECT, not
  whether the word "AI" appears somewhere in the sentence.
- **`NOTHING_TO_CHECK`** — an opinion, a forecast, a claim about what people
  believe, or a figure with no source behind it.
- **`NO_MECHANISM`** — it says what happened and cannot say what makes it so,
  not even badly. **Read the candidate's own `decision` line before choosing
  this one.** Every candidate here already passed a gate that measured that
  line, so if it names a decision, a measurement, a constraint or a trade-off,
  this ground does not apply and the code will refuse the deletion.

**Do NOT throw away for being widely covered, for being a product launch, or
for being less interesting than the others.** Those are ranking judgements and
they go into the order.

This rule exists because of a real loss. A candidate about a company's first
custom inference chip was discarded as "a widely covered product launch" — and
the fact carried, inside it, that the chip was designed in about nine months
when custom silicon normally takes years. That is a mechanism, and it went in
the bin with the press release. Bury a launch at the bottom of the order if you
must; do not delete it.

## Which ones could carry a whole article

An article runs about a thousand words, so it needs more than a complete fact:
it needs **a second act** (something happened after — a reversal, a court case,
an amendment, a company changing course) **or reach beyond one place** (the same
arrangement runs in another company, country or product).

A fact with neither is a good note and a bad article: complete in two sentences,
and a thousand words of it would be padding. Most candidates are notes. Say so.

**This is a selection, not a verdict on each one in turn.** Asked candidate by
candidate whether something could carry a thousand words, almost everything gets
a yes — measured here at two thirds of the bank, in batches where the honest
answer was a handful. So pick: **at most a third of the list**, and only where
you can name the second act or the second place out loud. Anything past that
share is cut by the order anyway, strongest kept, so a generous list does not
help the candidates in it — it only hides which ones you actually meant.

## How many notes each one can carry

Some facts are one note. Some carry two or three, and the difference is not
length — it is whether the fact contains more than one thing a stranger
believes wrongly.

A model release is the clearest case. The release itself is one note ("it
shipped and here is the number nobody expected"). The evaluation table is a
second, and a different reader is wrong about a different thing ("a benchmark
score is a ranking" — no, it is a measurement of one workload). The price
against the promise is a third. Those are three notes, not one note told three
times.

The test is strict and it is the same test as everywhere on this account: each
angle must break a DIFFERENT belief. If two angles would puncture the same
assumption, that is one angle written twice — return one.

For each candidate return `katy`. An angle is a short instruction to the
writer, not a headline: say what to lead with and which belief it breaks.

**Work this as a forced choice, not a free option.** Asked for "one to three"
you will return one every time — measured on 4 September 2026, sixteen
candidates in one batch, one angle each, sixteen times out of sixteen. That is
not judgement, it is the cheapest answer.

So for every candidate, before you write `katy`, find the SECOND angle and say
what happens to it in `drugi_kat`:

* if the second angle breaks a genuinely different belief, it goes into `katy`
  alongside the first, and `drugi_kat` says "wzięty";
* if it would break the same belief in other words, `drugi_kat` names that
  belief and says why the two collapse into one.

An empty or missing `drugi_kat` is a failed answer for that candidate. You may
still end with one angle — most facts honestly carry one — but you must have
looked, and the record must show what you looked at.

Where an angle needs something we do not have — a comparison table, a
side-by-side with the previous version, the vendor's own eval page — say so in
`czego_brakuje` for that angle. That is not a complaint; it is the next search
we should run.

## The language of your answer

**Write every field in English.** Not the language of this file, not the
language of the codebase around it — English, because these fields are read by
the writer that produces the notes, and this publication writes in English.

`kat` is a direct instruction handed to that writer. `lamie` becomes the belief
the note has to break. A field in another language arrives at the writer as a
foreign order and either leaks into a published note or gets ignored.

THIS IS NOT HYPOTHETICAL. On 4 September 2026 this stage returned 33 angles,
33 writer instructions and 23 ranking justifications, and EVERY ONE of them was
in Polish — the whole batch, no English at all. Nothing in the prompt had asked
for a language, so nothing held the answer in place. The stages that do say it
(`notka.md`, `komentarz.md`, `odpowiedz.md`) have never drifted.

## Output

Return only valid JSON. `kolejnosc` lists every id exactly once, strongest
first. Do not omit any id and do not invent one.

{{"kolejnosc": [<id>, <id>, ...],
  "oceny": [{{"id": <id>, "wyrzuc": true|false, "kod_wyrzucenia": "NOT_AI"|"NOTHING_TO_CHECK"|"NO_MECHANISM"|"", "powod_wyrzucenia": "<one clause saying why that code applies, empty when keeping>", "na_artykul": true|false, "dlaczego_mocny": "<one clause — what would make a stranger stop>", "podobne_do": "<which side of the measured evidence this resembles, and in what respect — one clause; empty if neither>", "drugi_kat": "<the second angle you considered: 'wzięty' if it is in `katy`, otherwise the belief it would have broken and why that is the same belief as the first>", "katy": [{{"kat": "<what to lead with — one clause to the writer>", "lamie": "<the belief this one angle breaks — different for every angle>", "czego_brakuje": "<what we would have to find to write it, empty when we already have enough>"}}]}}]}}

`kod_wyrzucenia` must be one of the three codes whenever `wyrzuc` is true, and
empty otherwise. A deletion with any other value is refused and the candidate is
kept — so a code you cannot honestly pick is a candidate you are not deleting.

## The candidates

{kandydaci}
