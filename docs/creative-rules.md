# Creative rules

What the imagery and copy in vlab recruitment ads should and should not show. These rules
are for the people and agents who write briefs, search queries and prompts, and
who rate candidates. `README.md` covers how ballyhoo enforces what it can;
`docs/design.md` covers why the tool works the way it does.

Every rule says why, so an edge case can be judged against the reason. A rule
comes from the author, not from a pattern in past picks. When the author states a
new one, add it here.

## Audience

### It looks like a professional local ad, made for the people it reaches

We design for local audiences. An ad in Kenya should look like the ads an average
Kenyan sees in Kenya, including Kenyans in small towns. It should not look like what
a foreign audience expects Kenya to look like.

- **Not National Geographic.** No documentary or ethnographic portraits and no
  tourist imagery: those are made for foreign audiences.
- **Not overly traditional.** Most people do not live that way today, and the people
  who answer an ad on their mobile phone are even less likely to. Traditional dress
  and village life as a spectacle are out.
- **Not a white person's idea of what a Kenyan looks like.**
- **The region is what matters, not the country.** A person who reads as East African
  serves a Kenyan study, and one who reads as North African or Arab serves a Moroccan
  one. Searching for the exact country finds documentary work and little else.

**Why:** we need to read as a professional local institution, because that is what
earns trust. Imagery made for outsiders tells the audience the ad is not for them.

### Show the aspirational version of the person we target

Always make the person slightly more urban, refined, well-off and young than the
person we are actually targeting. The audience should recognise themselves, but
the way advertising shows people: the conventionally better-looking version of
themselves.

Stay a little interesting, not generic. The image has to be distinctive enough to
notice, while staying within what passes for a professional local ad.

**Why:** this is how local advertising shows its audience, and looking like local
advertising builds trust. People identify with the idealised version of themselves.
Being slightly interesting keeps the ad from being ignored.

This works with the age rule below: show someone who looks younger than the stratum.

## Photography

### People pick photos, not agents

An agent may search, download and screen out what plainly breaks a rule (text in the
image, a child as the subject, a failed check). It does not decide which photograph
is good. A person looks at the candidates and picks.

**Why:** the author, 2026-09-16, after three rounds in which agent ratings tracked
the rules but not the photographs: "I think AI agents shouldn't be allowed to pick
photos. It's just not going to work."

### Eye-catching first

The most important quality in a photo is that it is eye-catching. A photo that does
not stop the scroll fails, however well it meets every other rule. Competent but
bland is a fail: a neutral smile on a plain background reads as generic stock.

**Why:** the author, 2026-09-16. "To be a good photo, it's most important that it's
eye catching."

**This is a judgement, not a checklist.** Do not reduce it to attributes and score
them. Look at the image and decide whether it catches the eye and whether it is a
good photo. An agent rating candidates does the same: look, then judge.

The author's own picks are the reference. Look at `scenes/kids-peeking.png` and
`scenes/father-toddler-blanket.png` before rating.

### A working description, from the author's two picks

This comes from `scenes/kids-peeking.png` and `scenes/father-toddler-blanket.png`.
The author called it a good analysis on 2026-09-14. It is to be refined with a
reference set of photos the author would and would not use.

It describes what those two photos have in common. It is not a test to score a
candidate against: a photo that ticks every line here and still does not catch the
eye is a drop.

- **It captures a moment rather than posing someone for a portrait.** Expression
  and personality come first: a pulled face, a laugh. Who the person is comes second.
- **The person looks into the camera**, close up, with faces filling much of the
  frame.
- **The background falls away:** shallow depth of field. The setting is incidental,
  such as a wall or a blanket, never a village, a market or a landmark.
- **The colour grade is warm and filmic**, with one saturated accent.
- **It reads as lifestyle or editorial photography**, never documentary, studio or
  corporate stock.

## People

### No one looks older than middle age, even for older strata

Show people up to about their fifties. For a 60+ stratum, show someone who looks
about 50, not 65 and never 80.

**Why:** people identify with someone younger than they are. A 65- or 70-year-old
does not see themselves in an 80-year-old, and responds to someone who looks
about 50.

- In needs, queries and prompts, write "middle-aged" or "in their fifties". Never
  write "elderly", "old", "senior", "grandmother" or "grandfather", or any age
  above about 55.
- When rating, drop a candidate who reads as elderly, even if the need is for a
  60+ stratum.

### Realistic people do not smile at the camera

A realistic person, drawn or photographed, is caught in their own moment:
looking at their phone, at each other, or off to one side. They do not look at
the viewer and smile.

**Why:** the author, 2026-09-24, keeping the one couple looking at their phone
over those looking out: a person smiling at the camera "is pretty boring and
very, like, advertising."

- The rule is for realistic people. A funny or cartoon figure, such as the cats
  and dogs in sunglasses, may look straight out.
- In prompts, say where the person is looking ("looking down at the phone
  together", "looking off into the distance"). Never ask for them to look at us.
- When rating, a realistic person looking at the viewer and smiling is a drop.

## Where images come from

### Photos come from stock; generated images are drawings

Photographs are searched for on stock sites. Image models make drawings
(illustrated figures used as cut-outs, like the existing character art), never
photographs.

**Why:** in the author's judgement, drawings from image models work much better
than generated photographs.

### Drawings are prompted for the house style, not copied from reference images

A generation prompt describes the style in words, based on the prompts the author
used for the existing art. Existing art is not passed to the model as a reference
image.

**Why:** it is the author's preference. The existing art was generated in the
author's own account, so using it as a reference is permitted if that changes.

### Drawing styles the author has used

There is no single house style. These are the styles in the author's Firefly
prompts (shared 2026-09-14), quoted verbatim, typos included. Several of them made
the existing art in `recruitment-creative/`.

**Precise hand drawing in pastel colour.** Ordinary people with character, never
model-pretty: slightly wrong proportions, and a stylish haircut that is not well
cut. The pose is phone in hand, looking off into the distance, seen at an angle.

> A cool woman, in her thirties, from Honduras. She has her mobile phone in his
> hand, but she's looking off into the distance. We see her at an angle. She’s not
> pretty, her features are not the right proportions. Her eyes dont sit at exactly
> the same level, although close. Her eyebrows are bushy. Hair is cut stylishly,
> but not cut well. She would never be a model. The picture is hand draw, but
> extremely detailed, precise, accurate, not stylized...but in brilliant colors,
> which are stylized. - pastel palette.

The same prompt was used for a man and a woman from Buenos Aires. The man's
version swaps the eyebrows for "His ears stick out too much."

**A brightly coloured line drawing.** A cool-looking person on the phone, looking
at the viewer.

> I’d like you to create an image of a very cool-looking woman in Nairobi, Kenya.
> It should be a line drawing, brightly colored. She should be on her mobile phone,
> but looking at us.

It was also used for a man in Nairobi, and for a man in Jakarta "with a 2-year-old
child in his arms".

**A black-and-white technical line drawing.** Used for animals and for the survey
itself.

> I would like a hand-drawn technical drawing, black and white, of two fat cats
> with sunglasses

> Please create an abstract black-and-white technical line drawing depicting a
> survey being filled out. It should be paper and pencil, but relatively easy to
> fill out. The individual taking the survey should be a cute rodent with big
> glasses.

A variant has the survey alone, "floating in space, abstractly".

**A technical drawing in coloured pencil.**

> Please create an abstract technical line drawing depicting a survey being filled
> out. The image should be colored, brightly colored, as though with colored
> pencil. The survey should be paper and pencil, but relatively easy to fill out.
> The individual taking the survey should be a cute dog with big glasses. The dog
> should be at a table, filling the survey.

**Why these styles:** the author has not stated reasons yet. The people prompts
suggest showing people the audience sees as like themselves, rather than models.
The animal and survey prompts suggest light, friendly images of the survey itself.
Confirm both before relying on them.

## Copy and Meta review

Meta's ad review reads the image text, the primary text and the WhatsApp or
Messenger welcome message together, and an automated reviewer reads them first.
Write for that reader as well as for the respondent.

### An incentive comes with its conditions, on the image and in the primary text

Say who qualifies, what they have to do, and when the payment arrives. The image
keeps a short headline and carries the conditions in a fine-print strip (a
variant's `fine_print`, in a design with a `#fine-print` slot); the primary text
says the same at more length.

**Why:** Meta disapproved the SSO Morocco ads (November 2026) under *Fraud, Scams
and Deceptive Practices* for "a guaranteed reward without explaining how it
works". Meta allows a payment for a survey when the conditions are clear.

### Take the conditions from the consent, word for word where possible

The consent already states the eligibility, the duration and the condition for
payment ("If you qualify and complete this survey, you will get…"), and it has
certified translations. Reuse that sentence rather than writing a new one.

**Why:** the ad cannot then promise more than the consent, and the IRB reviews
less new text. Promise no delivery time the payment system cannot keep: failed
payments wait until someone fixes them, so say "at the end of the survey", not
"within 24 hours".

### Address people living in the country, never a nationality

"People living in Morocco aged 18 or older", not "Moroccans" or "Moroccan
citizens", even where the screener checks citizenship. The screener and "if you
qualify" carry the rest of the eligibility.

**Why:** the author's rule, for every study: a nationality can read as an ethnic
group.

### Do not name the institution running the study

Say "a research survey" or "a research study". The institution belongs in the
consent form, not in the ad, the fine print or the welcome message.

**Why:** the author's rule, especially for a Western institution recruiting in a
non-Western country, where the name can change who answers and how. The ad
still shows who is advertising: the Facebook Page it runs from.

### Call it a payment, never a prize or a reward

No *free*, *win*, *gift*, *voucher* or *prize*; no currency symbol; no word that
reads as account balance or credit (*saldo*, *crédito*, *رصيد*). Prefer the
amount and the form of the payment ("a 10-dirham top-up", "KES 100 airtime").

**Why:** Meta disapproved the LAC Healthy Diets ads (September 2026) for "$",
*ganá*, *saldo* and *crédito* as financial or commercial. Columbia's IRB asked in
October 2026 for "compensation" or "payment" instead of "prize" or "reward".

### The amount is not the big type

When the amount is on the image, prefer it in the fine print, with the headline
naming the survey or the airtime without a number.

**Why:** Columbia's IRB asked in 2024 for the dollar amounts in smaller,
non-bold type, and a large amount is what reads as a payout offer to Meta.
Whether the headline carries the amount is still the author's call per study.

### Name no politics, government or elections

Even when the survey asks about them.

**Why:** Meta classes such ads as social-issue ads, which need an authorised
advertiser.

### The welcome message states the topic and carries no money words

**Why:** Meta reviews it with the ad, and an IRB precedent (Kenya) asked that the
first message state the survey's topic, not only the payment.

### Upload a no-amount rung of every creative as a template

So a disapproval can be answered without a new upload. It is not a fix on its
own: a promise of airtime without conditions is still a promise without
conditions.

## Already enforced by ballyhoo

- **Text is set in CSS, never drawn by an image model.** An image with text or
  lettering in it is a defect.
- **Every image has provenance, and a named person picks it.** See `README.md`
  § Provenance.

## Proposed, not yet confirmed by the author

These come from the review-issue list in `planning/imagery-pipeline.md`. Move one
up once the author confirms it.

- No one who could read as a respondent under 18: no teenagers, and no child as
  the subject. A small child held by a parent is a different case, since the author
  has prompted for one (the Jakarta father) and picked one (the father-toddler scene).
- No poverty imagery. Tourist and documentary imagery is already ruled out under
  § Audience.
- No visible brands or logos.
