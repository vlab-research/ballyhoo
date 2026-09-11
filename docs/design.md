# ballyhoo: design

## Goal

Let an agent produce Meta recruitment creatives end to end from a text file.

- **Phase 1 (built):** designs and imagery are made by a human. The agent changes
  text only and re-renders. No image generation.
- **Phase 2:** the agent generates figures with an image model and composites them
  into an existing design.
- **Phase 3:** the agent composes new layouts and selects imagery, behind a human
  review gate.

> The interface is: **change the text.** Everything else is the pipeline's job.
> The one thing that must be reliable is checking that the text still fits.

Copy is the localisation axis (countries, Spanish variants, incentive amounts)
and it changes on every creative. When it is baked into partner-delivered PNGs,
changing one word is a round trip to the partner.

Amounts are **just text**. There is no incentive model, currency table or
interpolation. The value is not managing amounts; it is that a changed string
re-renders correctly and provably fits.

**Non-goal:** replacing the designer. A human defines each design and supplies its
layers; ballyhoo re-types and re-composites them.

## The copy file

Design → country → named variant → headline. See the README for the format.

### Variant keys are load-bearing: never a list

The output key `<design>/<country>/<variant>/<size>` flows through the media
manifest into vlab creative names. vlab's sections reference each other by name,
and a stratum's id is a Meta ad set name, so renaming a creative deletes that ad
set on the next reconcile, with its delivery learning.

A list would make every key a function of position: inserting a variant at the
top would silently rename everything below it. A named map is stable under
insertion and reordering. ballyhoo rejects lists and never generates names.
Renaming a variant is a deliberate, destructive act.

- The amount is part of the string, deliberately.
- Variant names need not match across countries; nothing pairs them.
- A country absent from a design is skipped, never defaulted from another
  country's Spanish.

## Templates

One self-contained HTML file per design per size. The template **is** the layout
spec; there is no parallel config to drift out of sync. The renderer measures
the real elements, so the box the headline must fit in is whatever the CSS gives
`#headline`.

Per-size layouts are separate files, not a derived transform. Reflowing 1:1 into
1.91:1 is design work and looks wrong when automated.

Paths resolve relative to the file that names them, so templates live next to the
art they use and the code has no idea what a "library" is.

## Rendering

For each design × country × variant × template:

1. Load the template in headless Chrome (Playwright, viewport exactly the canvas).
2. Put the marked-up text into the `{{text}}` element; wait for every font,
   image and CSS image, and fail if any does not load.
3. **Autofit:** shrink the headline 1px at a time from its CSS size until its line
   boxes sit inside `#headline` in at most `data-max-lines` lines. Line boxes, not
   the font's content area: with a tight line-height the content area overhangs
   while the glyphs sit inside.
4. Screenshot three times: as rendered, with the text transparent, and with only
   `#figure` visible on a transparent page. The differences give text pixels,
   what lies behind them, and the figure's alpha.
5. Run the checks. Any failure is fatal for that creative, and is reported with its
   design, country, variant and size and the font size reached.
6. Write `out/<design>_<country>_<variant>_<size>.png`, with the inputs hash in a
   PNG text chunk.

Creatives render in parallel on one browser; skipped ones cost only a hash.

## The checks

This is the core of Phase 1: the only thing between a typo and a broken ad on Meta.

| Check | Fails when | Why |
|---|---|---|
| Fit | text overflows the box, or more lines than allowed, at the minimum size | clipped copy; silent reflow on a longer locale |
| Figure collision | a line box touches `#figure`'s alpha (specks < 500 px ignored) | headline across someone's face |
| Contrast | text colour vs pixels behind its glyphs < `data-min-contrast` (default 3:1) | headline drifting onto a dark band |
| Canvas | render ≠ template size | a viewport bug |
| Text share | text pixels > 20% of canvas | correlates with worse Meta delivery |
| Blank | > 99% one colour | a layer silently failed |
| Load | any font or image fails | fallback fonts and missing art look plausible |

Collision and contrast catch real localisation failures: a headline two words
longer than the one the design was made for is how a creative ends up with text
on a face or on a dark band. In practice they caught layouts that were fine for
the partner's copy and broke for the rewrite.

Contrast is 3:1, WCAG's large-text level, not 4.5:1: headlines are large, and
partner designs themselves sit near 3:1 (a template can lower it with a comment
saying why).

There is no alpha-holes check. The hole-in-the-hand failure came from matting a
figure out of a flattened PNG; figures now arrive with the designer's own mask.

## Acceptance criteria (Phase 1)

| # | Criterion | Status |
|---|---|---|
| 1 | Renders every design × country × variant × template | built |
| 2 | Editing one string re-renders only that creative | tested |
| 3 | Adding a variant first changes no other key and re-renders nothing else | tested |
| 4 | An over-long headline fails, naming design, country, variant, size and size reached | tested |
| 5 | A headline over the figure fails collision | tested |
| 6 | One failure does not stop the others; exit is still non-zero | tested |
| 7 | `--check` writes nothing | tested |
| 8 | Uploading twice gives the same manifest and no new assets | upload not built |
| 9 | ~~≥90% pixel match with the partner original~~ | dropped: the aim is good creative, not replicas; templates depart from partner layouts where those were weak |

## Upload and hand-off to vlab (not built)

Reuse the house pattern (`projects/lac-healthy-diets/upload_media.py`):

- POST multipart to `${FLY_API_BASE}/media/upload` with `Authorization: Bearer
  $FLY_API_KEY` (base default `https://fly-dashboard-api.vlab.digital/api/v1`).
  The server dedupes on (account, content hash) and returns the existing asset,
  so re-running is free.
- Write `creative_media.json` next to the copy file as `{key: url}`.
- Downstream is unchanged: `push_study` creatives → `plan_study` →
  `apply_instruction`. Campaigns are created PAUSED; activation stays manual.
- The ad's primary text is reviewed by Meta too. It should come from the same copy
  file, so the image and the text cannot drift apart.

## Lessons from building it

- **Never matte a figure out of a flattened PNG.** Flood fill eats light skin and
  fur. Ask designers for layered exports; Adobe Express's PSD export keeps its
  background-removal mask, its PNG export does not.
- **Never trace shapes by colour-matching a flattened PNG.** Anti-aliased edges
  fall within tolerance of neighbouring colours.
- **Pin fonts as files.** A dev machine's font list is mostly terminal fonts, and
  a fallback looks plausible. When a partner's font is unknown, choose a
  substitute by glyph overlap against their artwork, then judge by eye.
- **CSS masks from file:// need `--allow-file-access-from-files`**: mask images
  are fetched in CORS mode.
- **Headless Chrome's `--screenshot` CLI** gives a viewport shorter than
  `--window-size` and needs `--virtual-time-budget` for webfonts. Playwright avoids
  both.
- **Cut-out masks carry specks** left by background removal. Invisible on a light
  ground, but they trip a pixel-exact collision test.

## Phase 2 sketch: generated figures

- Image generation behind one swappable function,
  `generate_figure(prompt, seed, size) -> RGBA PNG`; the provider is config.
- Candidates: Gemini image models (reference/editing mode holds a character
  consistent across a campaign), FLUX via fal.ai, Adobe Firefly Services.
- Generate on a transparent or plain background, so there is no matting.
- **Never let an image model draw the headline.** Accented Spanish is where glyphs
  garble. Text stays in CSS.
- Consistency across a campaign matters more than per-image quality.

## Phase 3 sketch: generated layouts

Out of scope until Phase 2 is trusted. It needs design judgement, so it needs a
human review gate before anything reaches Meta.
