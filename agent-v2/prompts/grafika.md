Write the image brief for the header illustration of this article.

You are not drawing. You are writing the sentence a generator will draw from.

## The one rule that matters

The reader has to recognise this publication from a thumbnail, before reading
the title. That only happens if every header looks like it came from the same
place. So the style block below is **fixed and copied verbatim** — you choose
the subject, never the treatment.

The block changed once, after looking at what it actually produced. The first
two headers were a pale object on a pale ground: tasteful at full size,
invisible as a thumbnail in a crowded feed. The ground is now clearly darker
than the object, the object fills more of the frame, and its surface carries
wear — because a specimen that looks factory-fresh reads as a render, and a
render reads as decoration rather than evidence.

## Choosing the subject

Pick **one ordinary physical object** at the centre of what the article is
about. Not a scene, not a metaphor, not a person.

- The object should be the thing the reader already meets — the packaging, the
  fitting, the sign, the coin, the valve, the badge on the machine.
- If the article is about a rule, find the object the rule acts on.
- If the article is about an incentive, find the object the money passes
  through.
- Prefer the specific over the general: not "a car", but "the speedometer face
  of an ordinary compact car".

## A symbol is not an object

If the article is about a marking — a symbol, a pictogram, an icon, a stamp, a
label — then **photograph the thing that carries it**, never the marking redrawn
as a physical object.

This went wrong once and it is worth naming. An article about the open-jar
symbol printed on cosmetics got a header showing an actual glass jar with a
tilted lid. The reader saw a jam jar. The subject should have been the back of
a shampoo bottle: the thing the rule acts on, the thing they own.

The test: could you pick this object up in your house? A pictogram fails it.

**Never** put text, numbers, letters, logos or brand marks in the image.
Generators render them badly and a misspelled word on a header is the fastest
way to look careless. If the object's meaning depends on text, choose a
different object.

Never depict a real, identifiable person, a real logo, or a real company's
product in a way that identifies the company.

## Output

Return only valid JSON:

{{"subject": "<the object, in a few words>", "why_this_object": "<one sentence tying it to the article's mechanism>", "prompt": "<the full image prompt: your subject sentence first, then the style block below copied word for word>"}}

## The style block — copy verbatim into `prompt`, after your subject sentence

Photographed as a single isolated specimen resting on a deep putty-grey paper
background, clearly darker than the object so the silhouette separates cleanly
even at thumbnail size. The object fills roughly two thirds of the frame. Its
surface shows honest wear consistent with age and use — fine scratches, slight
chipping at the edges, uneven patina — so it reads as a real artefact that has
been in service, never as a fresh render. Flat, even, diffuse studio light with
one soft shadow falling short and to the right. Slightly elevated three-quarter
angle. Restrained palette — grey ground, graphite, and the object's own colour
allowed to stay saturated. Sharp focus edge to edge, fine surface texture
visible, no gloss, no dramatic highlights, no vignette. Calm, forensic,
editorial. Absolutely no text, no lettering, no numbers, no logos, no
watermarks, no people, no hands.

## The article

Title: {title}

{body}
