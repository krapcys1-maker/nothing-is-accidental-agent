Find {ile} documented facts worth stopping a stranger mid-scroll.

Search for them. Do not write from memory — a fact you cannot put a source
against is not a fact you can use here.

## What this publication is

Nothing Is Accidental explains the hidden systems, incentives and decisions
behind ordinary things. The recurring move is the gap between what everyone
assumes and what the record says.

## Where to look this time

Take your facts from these areas and no others:

{dziedziny}

These rotate every run. Going back to the areas you find easiest is how a feed
turns monotonous, and the reader notices the sameness long before they notice
the repetition.

## WHAT SHAPE to look for — apply each pattern to each area

The areas tell you where to look. They do not tell you what you are looking
for, and that is why searching "interesting facts about electricity" returns
trivia. A candidate is produced by applying a **named pattern** to a **named
area**, not by hunting for something that feels interesting.

{generatory}

Work the grid: take each pattern, ask its probe question of each area above,
and write down what comes back. Most cells will be empty. That is expected —
the point is that the full ones are found on purpose rather than by luck.

## What the reader is holding right now

It is {miesiac}, and the things in front of people this month are:

{w_reku}

An ordinary object somebody is **handling this week** beats an ordinary object
in general, and it costs nothing to prefer one. Sunscreen in August is not a
coincidence. Do not force it — if the grid gives you something better out of
season, take that instead.

## Do not make everything American

The first twelve notes on this account were almost all US federal regulation.
That is one country and one kind of document, and it reads as a narrow beat.
A rule from the EU, Japan, Brazil or India is not a lesser fact — and a rule
that differs BETWEEN two countries is the strongest kind this publication has,
because the difference itself proves somebody decided.

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

Aim wide: {ile} facts spread across the areas listed above, not {ile} angles on
one subject. If two of your facts share a mechanism, drop one and go elsewhere.

## Already used — do not return these, or anything close to them

These have been published already. A near-miss counts as a repeat: the same
regulation from another angle, the same object with a different number, the same
mechanism in a neighbouring industry. Go somewhere else entirely.

{uzyte}

## Output

Return only valid JSON:

{{"facts": [{{"fact": "<one or two sentences, the fact itself, specific and checkable>", "wrong_belief": "<what most people believe, written as a plain sentence they would say out loud>", "actually": "<what is true instead, one sentence>", "decision": "<who decided it and when — a body, a committee, a statute, a year. Empty string if the record names nobody>", "consequence": "<the thing the reader can touch, hold, see or wait for because of that decision>", "url": "<source that states it>", "domain": "<the everyday area it belongs to>"}}]}}

## The two halves, and why a fact without both is worthless to us

`wrong_belief` and `actually` are not decoration. A candidate that cannot fill
both is trivia, and trivia is discarded before anybody writes it.

"The world's longest tunnel is 57 km" is a fact, it is checkable, and it is
dead: nobody holds a belief about tunnel lengths, so there is nothing to break
and nothing to reply to. "Mains clocks count grid cycles rather than measuring
seconds" is alive, because everyone believes their oven clock keeps time.

`decision` and `consequence` are the other pair. A decision with no consequence
the reader meets is administrative history. A consequence with no decision
behind it is a curiosity. **The note exists only where a documented decision
produced something the reader is holding.**

Test each candidate before returning it: can you say *"most people think X,
actually Y, because someone decided Z"* in one breath? If not, leave it out and
find another. Ten candidates that pass are worth more than thirty that do not.
