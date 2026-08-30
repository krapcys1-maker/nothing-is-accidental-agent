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

## What to throw away, and be strict about it

Mark `wyrzuc: true` when any of these is true. A weak candidate kept in the bank
costs money every time it is considered and eventually gets published on a thin
day.

- **Not about artificial intelligence.** This is the most common one and the
  least forgivable. A fact about pharmaceutical regulation, food labelling or
  car dealerships is not our subject however good it is. Judge the SUBJECT, not
  whether the word "AI" appears somewhere in the sentence.
- **Nothing to check.** An opinion, a forecast, a claim about what people
  believe, or a figure with no source behind it.
- **Already common knowledge.** If the reader could have told you this, there is
  no piece in it.
- **The mechanism is missing.** It says what happened and cannot say what makes
  it so.

## Which ones could carry a whole article

An article runs about a thousand words, so it needs more than a complete fact:
it needs **a second act** (something happened after — a reversal, a court case,
an amendment, a company changing course) **or reach beyond one place** (the same
arrangement runs in another company, country or product).

A fact with neither is a good note and a bad article: complete in two sentences,
and a thousand words of it would be padding. Most candidates are notes. Say so.

## Output

Return only valid JSON. `kolejnosc` lists every id exactly once, strongest
first. Do not omit any id and do not invent one.

{{"kolejnosc": [<id>, <id>, ...],
  "oceny": [{{"id": <id>, "wyrzuc": true|false, "powod_wyrzucenia": "<one clause, empty when keeping>", "na_artykul": true|false, "dlaczego_mocny": "<one clause — what would make a stranger stop>"}}]}}

## The candidates

{kandydaci}
