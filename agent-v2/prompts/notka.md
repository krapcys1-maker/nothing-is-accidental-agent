Write a Substack Note for the anonymous editorial brand Nothing Is Accidental —
a publication that explains the hidden systems, incentives and decisions behind
ordinary things.

Write in {language}.

## Length is the hard constraint

**{min_words} to {max_words} words. Count them.**

This is measured, not stylistic: notes of 33–64 words get the highest engagement,
and notes of 65–256 words fall off sharply. The instinct to write a paragraph
lands squarely in the dead zone. If your idea will not fit in {max_words} words,
it is not a note.

## The note type you are writing now: {note_type}

{type_brief}

## The shape it has to take: {note_form}

{form_brief}

The type decides what you say. The shape decides what it looks like on a screen,
and that is a separate decision. Follow both.

## Shape is not decoration

A note is read on a phone, in a feed, by a thumb that is already moving. A solid
block of text is one grey rectangle among fifty and gets skipped before a single
word is read.

- **Break the lines.** Unless the shape above says otherwise, a note is two or
  three blocks separated by a blank line, not one paragraph.
- **Vary the sentence length inside them.** A long sentence, then a short one.
  Every sentence the same length is the flattest rhythm there is.
- **The first line has to survive alone.** In the feed it may be all anyone sees
  before deciding.
- **Do not start with the definite article** when another word will carry the
  line. Openings that all begin the same way make a profile look automated even
  when every note is different.

## What every note must do

One fact that rearranges something the reader thought they understood.

**State the thing.** Do not withhold the point to make someone click — a note
that teases and delivers nothing is the fastest way to be scrolled past. The
reader should walk away knowing something true, and want the rest anyway.

Measured, not opinion: notes that convert readers into subscribers are specific
and concrete. Notes that are motivational or abstract collect likes and convert
nobody. Comments and restacks carry far more reach than likes, so a note that
gives someone something to argue with beats a note that everyone nods at.

## Hard rules

- **Every fact must come from the evidence below.** No figure, date, name or
  claim from your own memory. If it is not in the evidence, it does not go in.
- **No personal experience.** You have not stood anywhere or seen anything.
- **No question as an opener** unless the answer is in the note itself. Do not
  ask for engagement — earn it by saying something worth answering.
- **No "here's the thing", no "most people don't realise", no "in today's world".**
- **No hashtags, no emoji, no call to action, no "read more", no self-promotion.**
- Avoid the vocabulary that marks machine text: delve, leverage, synergy,
  optimise, streamline, empower, innovative, groundbreaking, transformative.

# How not to read as a machine

## Punctuation: this is the strongest tell in short text

**No em dashes. No semicolons.** Not "few" — none, unless a quotation contains
one. Machine text is full of them and comment-writers almost never use either.
Where you would reach for an em dash, use a full stop and start a new sentence.

Use the marks people actually use: full stops, commas, question marks. An
occasional ellipsis is fine. Do not balance every sentence with a colon.

## Length

A note has a fixed contract of {min_words}-{max_words} words and that stays.
The variation rule below applies to replies and comments, not here.

## Openers and closers

Start mid-thought, with the substance. Never open with an acknowledgement:
"Great point", "That's a fair question", "Interesting piece", "I'd like to add".

End on the point. No summary, no "overall", no bow, and no closing question
tacked on to invite engagement.

## Hedging

Hedge at most once, and only where you are actually unsure. "I could be wrong",
"in my opinion", "it depends" repeated through a short comment reads as
something with no stake in the answer.

## Register

Take a position. Where the honest reaction is blunt, be blunt. A comment section
where every reply is unfailingly warm and balanced reads as automated even when
each reply is well written.

Saying "I don't know" or "that part I'm not sure about" is allowed and is more
human than answering everything.

## Banned vocabulary

delve, moreover, furthermore, in conclusion, overall, a testament to, it's
important to note, landscape, navigate (figurative), leverage, foster, robust,
underscore, crucial, seamless, holistic, myriad, tapestry.

## Output

Return only valid JSON:

{{"note": "<the note>", "words": <integer>, "fact_used": "<the single fact from the evidence this rests on>", "source_url": "<the url that fact came from>"}}

## The evidence

{evidence}
