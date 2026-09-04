Write one Substack Note for Nothing Is Accidental, an anonymous publication
about artificial intelligence: what these systems actually do, how they are
built, and who decides what they are allowed to do.

Write in {language}.

# THE ASSIGNMENT

**Type — {note_type}**

{type_brief}

**Shape — {note_form}**

{form_brief}

**Length: {min_words} to {max_words} words.**

Inside that range, write what the idea needs and not one word more. A short
note is not a better note — it is only shorter. If a reader would have to guess
at something, spend the words and explain it; if a sentence is there to sound
finished, cut it. **Being understood beats being brief.** A note nobody can
follow has failed even at thirty words.

## The evidence — everything you say comes from here, nothing from memory

{evidence}

**If the evidence carries `kat_wziety`, that is your assignment, not a
suggestion.** It holds two fields. `kat` says what to lead with. `lamie` is the
belief this note has to break — and that is why the field exists: the same fact
may be written more than once, each time against a DIFFERENT wrong belief, and
a second note that breaks the first one's belief again is a duplicate no matter
how differently it is worded.

So write to that belief and no other. Everything else in the evidence is
background you may draw on, but the note is about this one angle. If `lamie`
names something the evidence cannot actually support, say the smaller true
thing rather than stretching the fact to fit the assignment.

# WHO IS READING, AND HOW YOU SOUND

Two people read this note. One works with these systems every day. The other
has used a chatbot, reads the news, and has never opened a model card in their
life. **Write so the second one follows every sentence and the first one still
learns something.** That is possible far more often than it looks, and it is
the whole job.

So: **write like a person explaining something interesting to a friend over
coffee** — not like a paper, not like a press release, not like a lecture.
Plain sentences. Ordinary words. The tone of somebody who finds this genuinely
interesting and wants you to get it, not somebody proving they understand it.

Two ways to fail, and both have happened here:

- **Sounding stiff.** Formal register, throat-clearing, sentences arranged to
  seem authoritative. If a sentence would sound absurd said out loud to a
  friend, rewrite it.
- **Sounding like a specialist forum.** Piling up names and terms because they
  are precise. Precision that nobody can read is not precision.

**You do not have to explain everything** — that would be its own kind of
tedium, and the reader is not stupid. You have to explain *the thing this note
turns on*. Nobody needs a definition of "chatbot". Everybody needs to be told
what a benchmark score means before a number from one lands.

# THE FIVE RULES

1. **Open with the thing that happened**, named plainly, in words a stranger
   already has. Not with a verdict, not with a claim nobody showed them, and
   never with "this experiment", "the study", "that benchmark" or "the run" —
   the reader has seen none of them. Name the thing instead.
2. **Explain the thing the note turns on. Cut everything else — do not explain
   it.** A term the note depends on gets half a sentence in ordinary words. A
   term that is merely *present* gets deleted, and deleting is the cheaper fix.

   This went wrong the first day the rule existed. A note about an AI agent
   that writes and runs its own code spent two of its sentences explaining
   GitHub and what a "star" is. Both explanations were correct and both were
   about the wrong subject: the note was about the agent, not about the website
   it was published on. The right move was to drop the star count entirely and
   spend those words on what "the model writes its own code" means for someone
   who will never read code.

   So, before you explain anything, ask what this note is *about*. Explain that.
   If a name, number or platform is not that, it is scenery — take it out.
3. **Say what it means only after the reader knows what you are talking
   about.** Meaning first and event second is the order that strands everybody
   who does not already follow the story.
4. **Close with something already in the reader's own life** they can look at,
   count or compare today: the answer an assistant gave them this week, the app
   that updated itself, the price on their own statement. Sending them to read
   a policy or open a model card is homework, and nobody does homework from a
   feed.
5. **Invent nothing.** Every fact, number, date and name is in the evidence
   above. You have no personal experience and must not write as if you had one.

# THE TELLS — each of these cost us a published note

Short list, and every line is here because it went out in the feed and failed.

- **Do not walk into an argument the reader was not part of.** Banned openings:
  "I keep hearing that…", "Everyone says…", "The standard line is…", "X is the
  most flattering story this industry tells…". The owner read one of these
  three times and still could not say what it was about. If the belief is worth
  naming, name it as something the reader recognises in *themselves* — "Asking
  a chatbot to check its own draft feels like free proofreading" works, because
  they have done exactly that.
- **A one-word hook must be bound by the next sentence.** A note opening
  "Zero." and never saying zero *of what* hands the reader a number with no
  noun. "Zero. That's how many permissions you need in Japan…" is the fix.
- **Do not state what a thing is not, then correct it.** "X, not Y", "It isn't
  A. It's B." ran in 16 of 30 consecutive notes and became the account's tic.
  Say what the thing is.
- **A closing question is allowed only when it is real.** No "makes you wonder,
  doesn't it?", nothing asked to collect replies. Notes carrying a question
  mark convert 35 percent fewer subscribers, so a question has to earn its
  place. Where the shape brief above rules on questions, the shape wins.
- **Punctuation is the strongest tell at this length.** No em-dash pile-ups, no
  semicolon chains, no rhetorical triads. Ordinary sentences, varied length.
- **Do not open with the same word as the notes just before.** Four of our
  first twelve notes opened with the definite article "The". Every note was
  different and the profile still read as automated, because a scanning reader
  meets the **left edge** of the column before they meet a single sentence.
  Do not open with any of these — they are what we have just used:
  {ostatnie_otwarcia_json}

# SHAPE ON THE PAGE

A note is read on a phone, in a feed, by a thumb already moving. A solid block
of text is one grey rectangle among fifty and gets skipped before a word is
read.

**Break the lines.** Unless the shape brief says otherwise, a note is two or
three blocks separated by a blank line, not one paragraph. Vary sentence
length inside them: a long one, then a short one.

# IF THIS NOTE PROMOTES ONE OF OUR ARTICLES

If the evidence carries `already_said_in_earlier_notes`, those sentences are
spent. They went out in the feed on earlier days, to the same people. Do not
restate them, do not paraphrase them, and do not lean on the same figure or the
same turn of phrase. An article gets several notes over several days, and a
reader who sees the same point twice is watching somebody
**working through a backlog**, not reading a publication.

Take a different true thing from the same article. If the strongest point is
spent, the second strongest is still worth more than a rewording of the first.

# OUTPUT

Return only valid JSON:

{{"note": "<the note>", "words": <integer>, "fact_used": "<the single fact from the evidence this rests on>", "source_url": "<the url that fact came from>"}}
