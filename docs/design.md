# ballyhoo: design

## Goal

Let an agent produce Meta recruitment creatives end to end from a text file.

- **Phase 1 (built):** designs and imagery are made by a human. The agent changes
  text only and re-renders. No image generation.
- **Phase 2:** the agent sources imagery (stock photos found through stock-photo
  APIs, or figures from an image model) and composites it into an existing design.
  A human picks every image.
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

The browser measures; Python decides. For each design × country × variant ×
template:

1. **Skip or render** (`cache`): skip when the hash of the inputs matches the one
   stored in the existing PNG.
2. Load the template in headless Chrome (Playwright, viewport exactly the canvas).
   Put the marked-up text into the `{{text}}` element; wait for every font, image
   and CSS image, and fail if any does not load.
3. **Measure:** in one call, the page sets every whole size from the CSS size down
   to `data-min-size` and returns the raw text rects at each.
4. **Autofit** (`fit`): choose the largest size whose line boxes sit inside
   `#headline` in at most `data-max-lines` lines, and set the page to it. Line
   boxes, not the content area the browser reports: with a tight line-height the
   content area overhangs while the glyphs sit inside.
5. **Screenshot** five times: as rendered; with the text transparent, for what lies
   behind it; with the text forced black and forced white, whose difference is
   where the glyphs are; and `#figure` alone on a transparent page, for its alpha.
6. **Check** (`checks`): run every check and report every failure, with design,
   country, variant, size and the font size reached.
7. Write `out/<design>_<country>_<variant>_<size>.png`, with the inputs hash in a
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
| Scene upscaled | `#scene` drawn > 1.25× its image's size, in either direction | a small photo stretched over an ad passes every other check and looks soft |
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
- **Find text by forcing its colour, not by removing it.** Diffing a render with
  and without its text cannot see text close to its background's colour, so the
  contrast check passed exactly the text it exists to catch.
- **Keep decisions out of the page.** Fit logic written as page JavaScript could
  only be tested through a browser; the page now returns measurements and Python
  decides, so the logic has fast unit tests.

## Phase 2 sketch: sourced imagery

Designs are only as varied as their art. Partner art is mostly young, urban
adults, and a study stratified to ages 60+ and to rural areas needs older people,
families and rural settings too. Who appears in a recruitment ad is a selection
decision, not decoration. The work plan is `planning/phase-2-imagery.md`.

Two sources, one pipeline: **search or generate → candidates → a human picks →
keep, recording provenance → place in a template.**

### Every image has provenance

Every image a template references has a sidecar, `<image>.provenance.yaml`, saying
where it came from and on what terms we use it: the stock photo and its
photographer and licence, the model, prompt and seed that generated it, or who
made it. Partner art is no exception. An image without a valid sidecar fails the
render, like a missing font, and fails it even when the PNG is up to date, because
provenance does not change pixels and so is not in the render hash.

The sidecar holds the image's sha256. An image replaced under an old sidecar would
otherwise credit the wrong photographer, or claim a licence the new file does not
have.

It also names the person who picked the image. The agent searches, generates and
shortlists; a human picks, and `keep` refuses to write a sidecar without that name.
ballyhoo takes picks only from a person: named as arguments, or read from the
`verdicts.yaml` a run's review page saves.

### Stock photos, through their APIs

- Search through the providers' APIs, never their websites: the APIs return
  photographer, licence and sizes as data, and every site's terms forbid scraping.
- **Pexels** first. Its licence (like Pixabay's) forbids showing someone "as
  suffering from, or medicating for, a physical or mental ailment", use "in a
  political context", and implying that a pictured person endorses anything.
- **Openverse** only with `cc0` or `pdm` licences: CC BY requires attribution that
  an ad cannot carry, and Openverse does not verify licences.
- **Not Unsplash, for now.** Its API guidelines ask for "non-automated" use away
  from advertising, and require a linked credit wherever the image is shown, which
  a Meta ad cannot carry. Revisit with written permission.
- No stock site warrants model releases. Never use an identifiable person in a way
  that implies they endorse the study, and tell the IRB the imagery is stock.
- Stock search has its own skew: "Morocco" returns tourist imagery. Queries are
  design decisions, so they are recorded with the pick.

### Generated images

- Generation can match a campaign's existing style (illustrated partner art),
  which stock photos cannot, and can show people stock libraries lack.
- Providers sit behind one interface, and a search and a generation produce the
  same candidates: Gemini image models on Vertex, FLUX (fal.ai or BFL), Adobe
  Firefly Services.
- **Keep the bytes the provider delivered.** Re-encoding breaks their C2PA
  credentials, which BFL's and Adobe's terms forbid removing.
- Seeds are recorded but are not a way to regenerate an image: Gemini's is best
  effort only. The kept file is the artefact.
- **Never let an image model draw the headline.** Accented Spanish and Arabic
  shaping are where glyphs garble. Text stays in CSS.
- Consistency across a campaign matters more than per-image quality.

### Scenes before cut-outs

No provider returns transparency, so sourced images go in as `scenes/`, placed
rectangles. *Never matte a figure out of a flattened PNG* still holds; a cut-out
needs a background-removal step (a matting model on an image generated against a
plain background) with its own mask check.

**Direction (the author, 2026-09-14):** photos come from stock, with queries tuned by
people and agents. Generated images will be drawings used as transparent cut-outs,
like the partner's characters, which a later step places in a `#figure` slot, where
the collision check already applies. How they are drawn and cut out is not settled.
Preview fills only `#scene` for now.

### Judging imagery (briefs, runs, preview and review built; the smoke run is next in `planning/imagery-pipeline.md`)

Whether an image is right for a study is a human judgement, but much of what makes
it wrong for an ad is not. The pipeline runs from a **brief** (what is needed,
per need: search queries and generation prompts) to a **run**, an immutable
folder of candidates. Each candidate is rendered into real templates with a sample
headline, so the existing checks screen out candidates that would not make a
working ad, and a person rates the rest against the need.

- **The smoke test is the pipeline itself** on a small brief kept in the repo, so
  it cannot drift from the tool. Tests never call a provider; a fake provider
  draws images with known geometry.
- **Files in, files out.** A person's ratings reach ballyhoo only as
  `verdicts.yaml`, whether they were made on a local review page or a published
  one.
- **Runs are compared, not overwritten.** Tuning a prompt or choosing a provider
  is a comparison of verdicts across runs.
- **Queries are what gets tuned.** Photos come from stock, so a run records, per
  query, how many results were new and how many an earlier query had already
  found. Every candidate lists each query that found it, and its provenance keeps
  the first.
- **Spending is refused before it happens, not after.** `--plan` sends nothing.
  Every request is built before any is sent, so a missing credential or a size a
  provider cannot make stops the run while it is still free. The estimate comes
  from prices written into each provider module with the date they were checked:
  a price in code goes stale, and the date says how stale. A provider with no
  published price counts as over the limit.
- **Stock originals are downloaded whole, as delivered.** Pexels originals reach
  20 MB, and its image host accepts imgix-style `w`/`h` parameters that would cap
  them. But Pexels does not document those parameters, and a resized copy is
  re-encoded (with imgix, `auto=compress` means quality 45 with the metadata
  stripped). The whole file is the photographer's own bytes, and it is exactly what
  is previewed, rated and kept. If art-library size becomes a problem, shrink at
  `keep`, as a recorded step.
- **The render digest follows imports.** It hashed every module in the package, so
  adding sourcing code would have re-rendered every study's ads without changing a
  pixel. It now covers `render.py` and whatever that imports, found by following
  relative imports. Nobody has to remember to list a module, so a list cannot go
  stale and leave an out-of-date ad in place.
- **Previews are not ads.** A candidate is rendered into real templates with the
  brief's sample headline and checked, but written only inside the run. Nothing is
  picked yet, so the image it replaces needs no provenance; every other image the
  template shows does, and `out/` still only ever holds ads that pass.
- **The page swaps the image; the template is never copied.** Preview sets
  `#scene`'s `src` to the candidate's `file://` URL before waiting for images, so
  the template's relative paths keep resolving. In Chrome, `decode()` called after
  `src` changes waits for the new image (checked against a delayed load), and an
  image from any directory loads, flag or no flag: only CORS-mode fetches such as
  masks need `--allow-file-access-from-files`. The page still reports the URL the slot
  shows, and a slot showing anything else fails, because `srcset` or a `<picture>`
  would quietly keep the placeholder.
- **A candidate fills a slot, named by id.** Photos go into `#scene`. Generated
  images are expected to be drawn cut-outs for `#figure` (above), so the slot is a
  field of a preview, not a name built into the code.
- **Scene upscaling is checked in every render, not only in previews.** A kept photo
  too small for its template looks as soft in the ad. The scale follows
  `object-fit`: `cover` draws at the larger of the width and height ratios, `contain`
  at the smaller.
- **Preview is its own command, not the end of `source`.** Previewing again after a
  template edit must not send provider requests again, and `source` needs no browser.
- **The smoke template's band is translucent on purpose.** Under an opaque band the
  headline's contrast would not depend on the photo, and a preview could never
  screen out a dark one.
- **A pick names a person, so verdicts are the one human input, and they are a file.**
  The review page saves `verdicts.yaml` whole, naming who rated, and `keep --verdicts`
  takes picks only from it. An agent may rate a run too, in `agent-verdicts.yaml`, which
  helps tune queries; the page shows its verdicts as hints and never fills in the
  person's controls, and `keep` refuses them. A record saying a person chose an image
  has to be true.
- **Verdicts are keyed by need, then candidate.** A candidate id names an image, and
  one stock photo can turn up under two needs in a run, where it is judged against
  each.
- **A query gets credit for every photo it found.** The same photo comes back from
  several queries, and crediting only the first query would make the later ones look
  as if they found nothing. The summary counts a photo once for its need and provider,
  and once for each query that found it.
- **The review page decides nothing.** Its data, the summary and validation are Python.
  The page shows them and posts what the person chose, and the server validates that
  before writing anything.
- **The review server is local and narrow.** It listens on 127.0.0.1 only and serves
  files from the run, never from outside it. It refuses a request addressed to any
  host name but 127.0.0.1 or localhost, and a save that is not JSON, because a page on
  another site can rebind its own host name to 127.0.0.1 or post a plain form.

## Phase 3 sketch: generated layouts

Out of scope until Phase 2 is trusted. It needs design judgement, so it needs a
human review gate before anything reaches Meta.
