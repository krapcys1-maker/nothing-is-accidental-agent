Find {ile} documented facts worth stopping a stranger mid-scroll.

Search for them. Do not write from memory — a fact you cannot put a source
against is not a fact you can use here.

## What this publication is

Nothing Is Accidental explains the hidden systems, incentives and decisions
behind ordinary things: airports, supermarkets, subscriptions, cities, everyday
technology. The recurring move is the gap between what everyone assumes and what
the record says.

## What makes a fact usable

The test is a stranger who has never heard of this publication stopping and
wanting to know who found that out. In practice that means:

- **It is about something the reader already meets.** A pricing rule, a queue, a
  standard, a default setting, a piece of infrastructure they walk past.
- **Somebody decided it.** The interesting part is almost never the fact itself
  but the decision, the incentive or the constraint behind it. A number with no
  mechanism behind it is trivia, and trivia is forgettable.
- **It survives being looked up.** Give the source that states it. Prefer the
  primary document — a filing, a standard, a regulation, a court record, a
  company's own statement — over an article describing one.

## What to avoid

- Facts that circulate as facts but trace back to nothing. If the only sources
  are listicles quoting each other, drop it.
- The famous ones. Anything a reader has already met three times is dead on
  arrival — no Coca-Cola formula, no QWERTY-slowed-typists, no Y2K.
- Anything where the surprising version is the debunked version. Check which way
  round the record actually runs before you use it.
- Pure numbers with no human decision behind them.

Aim wide: {ile} facts from {ile} different domains, not {ile} angles on one
subject.

## Output

Return only valid JSON:

{{"facts": [{{"fact": "<one or two sentences, the fact itself, specific and checkable>", "mechanism": "<one sentence: the decision, incentive or constraint that explains it>", "why_surprising": "<one sentence: what people assume instead>", "url": "<source that states it>", "domain": "<the everyday area it belongs to>"}}]}}
