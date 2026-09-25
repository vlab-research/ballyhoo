# ballyhoo

An AI design studio for recruitment ads. You write the copy; ballyhoo sets it
into designer-made templates, renders one image per design × country × variant
× size, and fails loudly when a headline no longer fits.

The interface is **change the text**. Everything else — sizing the headline,
compositing the art, checking the result — is ballyhoo's job. How it works and
where it is going: [docs/design.md](docs/design.md).

## Run

    uv sync
    uv run ballyhoo render path/to/creatives.yaml            # render what changed, skip the rest
    uv run ballyhoo render creatives.yaml --design dogs-band --country HN
    uv run ballyhoo render creatives.yaml --check            # render and check everything, write nothing
    uv run ballyhoo render creatives.yaml --force            # re-render even if up to date

From another directory: `uv run --project <path to ballyhoo> ballyhoo render creatives.yaml`.

It needs a Chrome or Chromium: `$BALLYHOO_CHROME`, else `google-chrome-stable`
(or `google-chrome`, `chromium`) on `PATH`, else Playwright's bundled Chromium
(`uv run playwright install chromium`). Exit status is non-zero if any creative
fails.

## A project

ballyhoo knows two kinds of file, and every path is relative to the file that
names it:

```
some-study/ads/creatives.yaml         the copy, and where the designs are
some-study/ads/out/                   renders (derived; do not commit)
shared/designs/<design>/<W>x<H>.html  templates; each names its own images and fonts
```

There is no notion of a library in the code. Designs shared across studies are
just a directory several copy files point at. At vlab-research that is
`projects/recruitment-creative/`, which holds the art, the designs and the fonts.

## The copy file

```yaml
designs: ../../recruitment-creative/designs   # default: ./designs

cats-band:
  AR:
    recarga:   "Sumate a la encuesta y recibí una *recarga de 3.000 pesos*."
    sin-monto: "Sumate a la encuesta y recibí una *recarga para tu celular*."
  HN:
    recarga:   "Tu opinión cuenta: encuesta corta con *L 90 de recarga*."
```

- design → country → **named** variant → headline. One creative per
  combination, per template size the design has.
- Variants are a map, never a list, and names are lowercase slugs. The output key
  `<design>/<country>/<variant>/<size>` becomes a vlab creative name, and vlab
  deletes a Meta ad set when a name changes. Add and remove variants freely;
  **never rename one.**
- A country missing from a design is skipped, not filled in from another.
- `*words*` marks the highlighted part of a headline. The template decides how
  it looks (and whether to upper-case, recolour or ignore it).
- `designs` is reserved; do not name a design that.
- YAML aliases (`&copy` / `*copy`) let several designs share one block of copy.

## Writing a template

One self-contained HTML file per design per size, named `<W>x<H>.html`.

- `#canvas`: the output size.
- `#headline`: the box the text must fit in. Its CSS `font-size` is the largest
  size. Attributes: `data-min-size` (px) and `data-max-lines`, required;
  `data-min-contrast` (default 3) and `data-collide-margin` (px, default 4),
  optional.
- Inside `#headline`, one element whose only content is `{{text}}`.
- `#figure`, optional: the cut-out the headline must not touch. As an
  `<img id="figure" src="…">` it is also the slot `preview` fills with a drawing.
- `#scene`, optional: `<img id="scene" src="…">`, a photo. It fails when drawn more
  than 1.25× its image's size, and it is the slot `preview` fills with a photograph.
  Give either slot a real `src` (a kept image, or a placeholder with provenance) so
  the template also renders on its own.
- Images, CSS images and fonts by relative path from the template. Pin fonts with
  `@font-face`; never rely on system fonts. Every image needs provenance (below).
- Use unitless `line-height` and `em` spacing so they scale when autofit shrinks
  the text.
- Say in a comment at the top what the design is based on and anything a reader
  would otherwise have to rediscover (placements, deliberate departures).

## Provenance

Every image a template references needs a sidecar beside it,
`<image>.provenance.yaml`, saying where it came from and on what terms we use it.
Without a valid one, the image's creatives fail, even when their PNGs are up to
date.

```yaml
# scenes/market-woman.jpg.provenance.yaml
source: stock
sha256: 9f2c…                    # of the image: replace the image and the record no longer matches
provider: pexels
id: '3573351'
page_url: https://www.pexels.com/photo/3573351/
creator: Lukas Rodriguez
licence: Pexels License
licence_url: https://www.pexels.com/license/
query: middle aged african woman portrait smiling
search_options: {orientation: square}   # only when the search set any
fetched: 2026-09-12
picked: {by: A. Author, on: 2026-09-12}
```

| `source` | Required besides `sha256` |
|---|---|
| `stock` | `provider`, `id`, `page_url`, `creator`, `licence`, `licence_url`, `query`, `fetched`, `picked` (`creator_url` and `search_options` optional). A photo downloaded before provenance existed is marked `backfilled: <date>` and may omit `query` |
| `generated` | `provider`, `model`, `prompt`, `seed`, `generated`, `picked`. A drawing kept as a cut-out also carries `style`, `key_colour`, and `raw_sha256`, the digest of the generation it was cut from |
| `made` | `by` (who made it, and the source document), `rights` (on what terms we use it) |

`picked.by` names the person who chose the image. For art a person made, such as
a partner's, write the records with

    uv run ballyhoo provenance made characters/*.png --by "<who, and the source document>" --rights "<terms>"

It never replaces an existing record, and writes none if any file cannot have one.

## Sourcing images

The agent searches or generates **candidates**; a person picks among them, on a run's
review page (§ Review) or by naming them to `keep`; `keep` copies a pick into the art
library with its provenance.

    uv run ballyhoo stock search "middle aged african woman portrait" --provider pexels --n 40 --out candidates/ea-woman
    GOOGLE_CLOUD_PROJECT=<project> uv run ballyhoo generate "<prompt>" --provider gemini --size 1080x1080 --n 4 --out candidates/ea-woman
    uv run ballyhoo keep candidates/ea-woman/candidates.yaml pexels-3573351=ea-woman-market \
        --to ../recruitment-creative/scenes --picked-by "<the person who picked>"

A candidates directory holds:

| Path | What |
|---|---|
| `candidates.yaml` | one entry per candidate: `n`, `id`, for stock `query` (the search that found it first) and `queries` (every search that found it, first first), `width`, `height`, `full` and `preview` (URLs, or paths in this directory), `thumb`, and the provenance record less `sha256`, `picked` and `fetched`. The record keeps the provider's description of a photo when it has one: Pexels's `alt`, Openverse's `title` |
| `originals/<id>.<ext>` | full-size stock files as delivered, when `source` made the directory; `full` and `preview` name them, and the record's `download_url` is the URL they came from |
| `thumbs/<id>.jpg` | 640 px on the long edge, for review pages |
| `sheet-01.png` … | contact sheets, 20 to a sheet, numbered by `n` |
| `generated/<id>.<ext>` | generated images, as delivered |
| `cutouts/<id>.png` | a drawing with its ground keyed out (§ Drawings): what its previews show and `keep` keeps |

Searches and generations append to the directory. Ids are `<provider>-<provider's
id>` for stock and `<provider>-<first 12 hex digits of sha256>` for generated
images, so the same image is never listed twice and numbers never change.

| `--provider` | Kind | Credentials | Notes |
|---|---|---|---|
| `pexels` | stock | `PEXELS_API_KEY` | `--orientation landscape\|portrait\|square`; `square` returns a different set and matches a 1080×1080 template |
| `openverse` | stock | none | CC0 and public domain only, which in practice means archive images |
| `gemini` | generate | Google application default credentials, and `GOOGLE_CLOUD_PROJECT` naming who pays | Vertex; `--image-size 1K`/`2K`/`4K`; `--size` sets the aspect ratio, which must be one Gemini supports |
| `fal` | generate | `FAL_KEY` | FLUX.2 [pro] at exactly `--size` |
| `firefly` | generate | `FIREFLY_SERVICES_CLIENT_ID`, `FIREFLY_SERVICES_CLIENT_SECRET` | Image 5; 1:1, 4:3, 3:4, 16:9 or 9:16 only |

A missing credential is an error naming the variable. `keep` writes the bytes the
provider delivered, never re-encoded (that would strip C2PA credentials); never
overwrites a file; and refuses a download that is not a JPEG, PNG or WebP. No
generator returns transparency, so a drawing is generated on flat green and cut out
here (§ Drawings); the cut-out is what is kept, and the generation stays beside it.

### Drawings

A drawing is a generation that names a `style` and a `subject` (§ Briefs and runs).
Its prompt is assembled from the subject, the style, the style's `guards` and
`framing`, the brief's `prompt_suffix`, and a sentence asking for a flat chroma-key
green ground. The generation is saved as delivered in `generated/`, and a colour key,
read from the image's border, cuts the figure out to `cutouts/<id>.png`. Alpha ramps
with distance from the key only within a few pixels of the ground, so paint inside
the figure stays opaque however green or pale it is.

Every cut-out's mask is checked, and what the check finds is recorded for a person to
judge, never acted on: a ground that is not green, too little or too much
transparency, a soft edge, stray specks, and the key's green left in or painted on
the figure. The candidate's entry in `candidates.yaml` gains
`cutout: {file, key, mask: {pass, failures}}`. A figure drawn to the edges of the
frame, leaving no border to read the key from, and a pale, washed-out ground are
not cut out cleanly.

## Briefs and runs

A **brief** says what imagery a study needs. `source` searches and generates it
into a **run**: a new folder of candidates, one candidates directory per need,
for a person to rate.

    uv run ballyhoo source brief.yaml --plan                  # print each request and the estimate; send nothing
    uv run --env-file .env ballyhoo source brief.yaml         # into runs/<date>-<n>/ next to the brief
    uv run ballyhoo source brief.yaml --providers pexels --out ../runs

```yaml
designs: designs                  # default ./designs, as in a copy file
defaults:                         # shared by every need; each can be set per need instead
  n: 2                            # results per query, images per prompt (default 2)
  size: 1080x1080                 # the shape to generate (default: the first preview template's)
  prompt_suffix: No text, signs or lettering anywhere in the image.   # appended to every prompt
  preview:
    templates: [photo-band/1080x1080]       # <design>/<W>x<H> in the designs directory
    copy: "Take a short survey and get KES 100 airtime."

styles:                           # how drawings are drawn; a named map, like the needs
  precise-pastel:
    style: The picture is hand drawn, extremely detailed … - pastel palette.
    guards: No lettering, signs, logos or brand names anywhere.    # optional
    framing: One figure, waist up, filling the frame.              # optional

ea-woman:
  need: A woman who reads as East African, middle-aged, in a photo that stops the scroll.
  search:
    pexels:                       # a query, or a list of queries
      - middle aged african woman portrait smiling
      - query: african woman grey hair portrait
        orientation: square       # the provider's own search options, per query
  generate:
    gemini: A woman in her fifties outside her home, reading her phone.
    fal:                          # the map form carries options
      prompt: A woman in her fifties outside her home.
      model: fal-ai/flux-2-max    # default: the provider's model
      seed: 81                    # default: --seed, else random

na-woman-drawn:
  need: A drawing of a woman who reads as North African or Arab, about 45 to 55.
  generate:                       # a style and a subject, instead of a prompt, make it a drawing
    gemini: {style: precise-pastel, subject: A cool woman in her fifties from Casablanca.}
  preview: {templates: [figure-band/1080x1080], copy: "Répondez à une courte enquête."}
```

- Needs are a named map, and need names are lowercase slugs. `designs`, `defaults`
  and `styles` are reserved.
- `need` is required: it is what a person rates candidates against. A need has
  `search`, `generate`, or both.
- A setting in a need replaces the default whole: a need's `preview` names its `templates`
  as well as its `copy`, even to change only the headline (a YAML anchor saves repeating
  them, as `smoke/brief.yaml` does).
- Search options: a query is text, or a map with `query` and the provider's own search
  options. Pexels takes `orientation` (`landscape`, `portrait` or `square`); Openverse takes
  none. An option a provider does not accept is an error naming it and listing what it does
  take, and so is a value it cannot use, both before anything is sent.
- Generation options: `model`, `seed`, and for Gemini `image_size` (`1K`, `2K` or
  `4K`; default `2K`). A generation either writes its `prompt` out, which makes a
  photograph, or names a `style` and a `subject`, which makes a drawing (§ Drawings).
  An unknown style, a style without a subject, and a style beside a written-out
  prompt are all errors.
- Paths resolve relative to the brief. Every mistake (unknown providers or keys, a
  missing `need`, a template that does not exist) is reported together, and
  nothing is sent.

Before sending anything, `source` builds every request, which catches a missing
credential or a size a provider cannot generate. The exception is Gemini's
application default credentials, which only the first request tests. It then
estimates the cost from the `PRICE` in each provider module, which records when
and where the price was checked, and refuses:

- a run estimated above `--max-cost`;
- a model with no published price (Firefly), unless `--allow-unpriced`.

The estimate is a floor: Gemini's prices are per output image, and prompt and
thinking tokens add a little.

| Flag | |
|---|---|
| `--plan` | print each request and the estimate; send and write nothing. Exits 1 if the run would be refused |
| `--providers p,q` | only these providers' requests |
| `--max-cost USD` | refuse a run estimated above this (default 2) |
| `--allow-unpriced` | also run models with no published price |
| `--seed N` | the first seed of generations whose brief sets none (default: random) |
| `--out DIR` | the directory runs go in (default: `runs/` next to the brief) |

```
runs/2026-09-14-1/         <UTC date>-<n>; a second run that day is -2, and no run is written into again
  brief.yaml               the brief as it was run; its relative paths mean what they meant beside the original
  manifest.yaml            what ran
  ea-woman/                a candidates directory (above), with stock originals in originals/
  review.html              the review page, read-only (§ Review); written by preview and by each save
  verdicts.yaml            a person's verdicts, saved from the review page; absent until someone rates
  agent-verdicts.yaml      an agent's verdicts, written by the agent; optional
```

One request's refusal or HTTP error is recorded, the other requests still run,
and the exit status is non-zero.

```yaml
# manifest.yaml
brief: ../../brief.yaml           # the original, relative to the run
started: 2026-09-14T10:02:11Z
finished: 2026-09-14T10:04:40Z
ballyhoo: 3f9a…                   # digest of all of ballyhoo's code
estimated_cost_usd: 0.33
requests:
- {need: ea-woman, provider: pexels, kind: search, query: african woman grey hair portrait, n: 2,
   orientation: square, results: 2, new: 1, already_found: 1, seconds: 1.2, estimated_usd: 0.0}
- {need: ea-woman, provider: gemini, kind: generate, model: gemini-3.1-flash-image, size: 1080x1080,
   seeds: [81, 82], prompt: "…", images: 1, refused: 1, seconds: 27.4, estimated_usd: 0.202}
errors:
- 'ea-woman/gemini generate: seed 82: no image (finish reason IMAGE_SAFETY)'
```

A drawing's request also records its `style`, how many images were `cut_out`, and
how many of those failed the mask check (`mask_failed`), which is a count for a
person to look at, not an error.

For a search, `new` counts the results that no earlier query for the same need
found in this run, and `already_found` counts the rest. A photo is downloaded
once. Its provenance keeps the first query that found it, and its `queries` in
`candidates.yaml` list every query that did, so each query's keep rate counts it.

## Previews

`preview` renders every candidate in a run into each template its need's `preview`
names, with the brief's `copy` as the headline, and runs the checks on each render.
A person then rates an ad, not a raw photo.

    uv run ballyhoo preview runs/2026-09-14-1

- A photograph replaces the template's `<img id="scene">` in the page, and a
  drawing's cut-out its `<img id="figure">`. The cut-out keeps its proportions inside
  the figure's box (`object-fit: contain`), standing on the box's bottom edge. A
  candidate goes into each of its need's templates that has its slot; the others are
  passed over. The template file is never copied or changed.
- A preview is not an ad. It is written inside the run, never to `out/`, whether or
  not it passes. The image the candidate replaces needs no provenance; every other
  image the template shows still does.
- Mistakes are reported together, and then nothing renders: a kind of candidate that
  none of its need's templates has a slot for, a file a template references that is missing or has no
  provenance, a need with candidates but no preview templates.
- A need with no candidates (every request for it failed) is skipped and named.
- Running it again, say after editing a template, re-renders every preview and
  rewrites `checks.yaml`. Nothing is sent to a provider.
- It also writes the run's `review.html`, a read-only copy of the review page
  (§ Review), so the previews can be looked at without a server.
- The exit status is non-zero for those mistakes and for a preview that did not
  render, not for a candidate that fails a check: screening candidates out is the
  point.

```
runs/2026-09-14-1/ea-woman/
  previews/<id>_<design>_<W>x<H>.png   every render, passing or not
  checks.yaml                          what the checks found
```

```yaml
# checks.yaml
copy: Take a short survey and get *KES 100* airtime.
templates: [photo-band/1080x1080]
previewed: 2026-09-14T10:12:03Z
ballyhoo: 3f9a…                        # digest of all of ballyhoo's code
summary: {candidates: 2, pass: 1, fail: 1}
candidates:                            # by candidate id, in candidates.yaml order
  pexels-3573351:
    pass: true                         # every preview of it passes
    previews:
      photo-band/1080x1080:
        status: pass                   # pass, fail, or error: it did not render
        file: previews/pexels-3573351_photo-band_1080x1080.png
        summary: 84px, 2 lines, contrast 5.6:1, text 3%, scene 0.90x
  pexels-7544779:
    pass: false
    previews:
      photo-band/1080x1080:
        status: fail
        file: previews/pexels-7544779_photo-band_1080x1080.png
        summary: 84px, 2 lines, contrast 1.2:1, text 4%, scene 0.34x
        failures: ['contrast 1.17:1 is below 3:1']
```

`smoke/designs/photo-band/1080x1080.html` is a photo template for trying the
pipeline: a scene under a band only 25% opaque, so a dark photo fails contrast.

## Review

`review` serves a review page on 127.0.0.1, where a person rates each candidate
against its need. `keep --verdicts` then keeps what they rated keep.

    uv run ballyhoo review brief.yaml                     # every run in runs/ next to the brief, or name a runs directory
    uv run ballyhoo review runs/2026-09-14-1              # one run; either prints the page's address; --port N (default: any free port)
    uv run ballyhoo review runs/2026-09-14-1 --summary    # print the counts below and exit; --agent counts agent-verdicts.yaml
    uv run ballyhoo keep runs/2026-09-14-1 --verdicts --need ea-woman --to ../recruitment-creative/scenes
    uv run ballyhoo keep brief.yaml 3.4 3.7=couple-park --to ../recruitment-creative/scenes --picked-by "<who picked>"

The page shows runs newest first, the newest open and older ones folded, each headed
with its needs and what it asked that the run before did not. The server reads the
runs from disk on every request, so a run made while it is up appears: the page
offers "New round: show it" rather than reloading under the cursor. A filter shows
all candidates, the unrated, the keeps, or all but the drops.

Within a run, the page groups candidates by need, in brief order. Each need opens with
what it asks for, the headline its previews used, and the summary. Each candidate shows
its preview renders large, with its cut-out or its photo beside them (click for the full
image), its provider and alt text; its queries or prompt, the photographer and licence
or the model and seed, the check failures, and an agent's verdict when there is one are
folded beneath.

**Names.** Each card shows its candidate's name large, such as **3.4**: the fourth
candidate of run 3, counting through the run's needs in the order of its `brief.yaml`
and each need's candidates in `candidates.yaml` order (not `candidates.yaml`'s own `n`,
which restarts in every need). Run numbers restart each day, so the full name is
`2026-09-24-3.4`; the page shows it in full wherever another run it shows is also
numbered 3. A name never changes once the run is sourced, so the author and the agent
can use it in the thread.

**`keep BRIEF|RUNS|RUN NAME... --to DIR --picked-by NAME`** keeps candidates by name,
each as `<name>` or `<name>=<file name>`, like picks by id. Given a brief (its `runs/`) or
a runs directory, a name is `3.4` or `2026-09-24-3.4`; `3.4` where two days both have a
run 3 is an error naming them, as is a name no run has. Given a run folder, `4` names its
fourth candidate. If any name picks nothing, nothing is kept. Each kept file is printed
with the name, run, need and id it resolved to.

- Rate with keep, maybe or drop, the issue boxes and a note. `k`, `m` and `d` rate the
  candidate last clicked, and the arrow keys move between candidates.
- Each need in a run has a note on its candidates as a whole, such as "less pensive"
  or "none of these look 50": what the next round should change, for the agent to read.
- Every mark saves as it is made: each keep, maybe, drop, issue, note or need's note (once
  typing pauses) is merged into the run's `verdicts.yaml`, dated that day. The page asks for your
  name at the top on your first mark and remembers it in this browser. Each card, and
  each need's note, says whether its mark is saved; one not saved has a dashed border and
  says why, such as a run already rated by someone else: one person rates a run, until
  every mark in it, notes included, is cleared. Clicking a card's verdict again clears it;
  a card's issues and note are saved only with a verdict, and a need's note on its own.
- Opened as a file, as `preview` and each saved mark write it, the page is read-only.
- The server listens only on 127.0.0.1, and serves the page and files in the run or
  runs directory, nothing else. A run's files, verdicts included, can be broken by hand;
  `review RUN` then reports every problem and does not start, and a page of runs shows
  them in place of that run.

```yaml
# verdicts.yaml
rated_by: A. Author
rated_on: 2026-09-14
needs:                            # need -> candidate id -> verdict
  ea-woman:
    pexels-3573351:
      verdict: keep               # keep, maybe or drop
      issues: [crop]              # optional, from the list below
      note: Tight on the right.   # optional
    pexels-7544779:
      verdict: drop
      issues: [age]
notes:                            # optional: need -> a note on its candidates as a whole
  ea-woman: Less pensive, and none of these look 50.
```

Every need and candidate must be in the run, and a candidate with no entry is unrated.
A note is on a need with candidates in the run; an empty one is no note.
Verdicts are keyed by need because one photo can be a candidate of two needs, and is
judged against each.

| Issue | Someone rating sees |
|---|---|
| `minor` | someone who could read as under 18 |
| `age` | someone who reads as older than middle age, even for an older stratum (`docs/creative-rules.md`) |
| `text` | text or lettering in the image |
| `tourist` | tourist imagery: landmarks, postcard scenes |
| `poverty` | poverty imagery |
| `artefact` | a visible artefact: hands, phones, faces |
| `off-brief` | not what the need asks for |
| `style` | a clash with the campaign |
| `brand` | a visible brand or logo |
| `crop` | no room for the headline |

**Agent verdicts.** An agent may rate a run too, in `agent-verdicts.yaml`: the same
format, with `rated_by` naming the agent and model, such as `claude-code
(claude-opus-5)`. The page shows each one as a small hint beside the person's controls,
never filled into them, and `review --summary --agent` counts them. `keep` never takes
picks from them: a pick names the person who made it.

**The summary** counts, per need, per provider and per query or prompt, the candidates
found, how many are keep (with the keep rate), maybe, drop and unrated, and each issue.
A photo that several queries found counts once for its need and provider, and once for
each of those queries.

```
ea-woman: 6 found, 1 keep (17%), 1 maybe, 3 drop, 1 unrated; issues: age 2
  pexels: 4 found, 1 keep (25%), 0 maybe, 2 drop, 1 unrated; issues: age 2
    query 'mature african woman phone': 3 found, 1 keep (33%), 0 maybe, 1 drop, 1 unrated; issues: age 1
    query 'african woman grey hair portrait': 2 found, 0 keep (0%), 0 maybe, 2 drop, 0 unrated; issues: age 2
  gemini: 2 found, 0 keep (0%), 1 maybe, 1 drop, 0 unrated
    prompt 'A woman in her fifties outside her home.': 2 found, 0 keep (0%), 1 maybe, 1 drop, 0 unrated
```

**`keep RUN --verdicts --need NEED --to DIR`** keeps every candidate of the need that
`verdicts.yaml` rates keep, named by its id, from the run's own files: `picked.by` is
`rated_by`, `picked.on` is `rated_on`, and a stock photo's `fetched` is the day the run
started. It refuses a run with no `verdicts.yaml` (agent verdicts or not), a need with
no candidates in the run, and a need with no keeps. Like every `keep`, it never
overwrites a file.

## Smoke test

`smoke/brief.yaml` runs the imagery pipeline end to end on real Pexels replies: three
needs, four queries of eight results each, stock only and free. Run it after changing
sourcing, preview or review, and use its summary to tune queries.

Its needs are regions, not countries — `ea-woman`, `na-man` and `na-woman` — because that
is what a photo has to read as (`docs/creative-rules.md` § Audience). One query sets
`orientation: square`, so a run exercises a provider search option against the live API.

    uv run --env-file .env ballyhoo source smoke/brief.yaml     # into smoke/runs/<date>-<n>/; needs PEXELS_API_KEY
    uv run ballyhoo preview smoke/runs/<run>                    # render and check every candidate
    uv run ballyhoo review smoke/runs/<run>                     # rate on the page
    uv run ballyhoo review smoke/runs/<run> --summary           # keep rate per need and query

- `na-woman`, an unveiled middle-aged woman who reads North African or Arab, is the known
  gap: Pexels has almost none. It stays in the brief so each run shows whether that is
  still true.
- pytest never runs it. `tests/integration/test_smoke_brief.py` checks, without a network,
  that the brief parses, its templates exist, its requests build, and it asks for no one
  older than middle age.

## What fails a creative

| Check | Fails when |
|---|---|
| Provenance | an image the template references has no valid provenance sidecar |
| Fit | at `data-min-size` the text still overflows `#headline` or needs more than `data-max-lines` |
| Figure collision | a headline line box (plus margin) touches `#figure`'s alpha; mask specks under 500 px are ignored |
| Contrast | WCAG ratio of a text colour against the pixels behind its glyphs is below `data-min-contrast` |
| Canvas | the render is not the size in the file name |
| Scene upscaled | `#scene` is drawn more than 1.25× its image's size in either direction: under `object-fit: cover` the larger of width and height ratios, under `contain` the smaller, under `fill` each |
| Text share | text pixels cover more than 20% of the canvas |
| Blank | more than 99% of the canvas is one colour |
| Load | an image, CSS image or font fails to load |

A failed creative is not written, and an old PNG for it is deleted, so `out/`
never holds an ad that does not pass.

## Caching

Each PNG stores a hash of its inputs: the code rendering runs (`render.py` and
every module it imports, so not the sourcing code), the text, the template, and
every file the template references. A render is skipped when the hash matches,
so editing one headline re-renders only that creative.

## Code layout

Functional core, imperative shell (see [CLAUDE.md](CLAUDE.md)): every decision is
a pure function, and the browser only measures and takes screenshots.

| Module | Decides |
|---|---|
| `copyfile.py` | which creatives exist: validates a loaded copy file, expands it into jobs, `*emphasis*` markup |
| `cache.py` | whether to render: the files a template references, the inputs digest |
| `fit.py` | the font size: template settings, line boxes, lines, the largest size that fits |
| `checks.py` | whether a render passes |
| `provenance.py` | whether an image's provenance record is complete and belongs to that image |
| `candidates.py` | the candidates file, ids, contact-sheet layout, and what keeping a pick writes |
| `brief.py` | what a brief sources: validates it, expands it into jobs, estimates their cost, checks every request can be built, names runs |
| `preview.py` | what a preview renders: which candidate goes into which template, file names, whether a template has an `<img id="scene">`, and `checks.yaml` |
| `verdicts.py` | whether a verdicts map is valid for a run, and what `keep --verdicts` keeps |
| `names.py` | run names and their order, and candidates' names (`3.4`): numbering, the short form a page shows, and which candidate a name picks |
| `review.py` | what the review page shows, the summary of verdicts per need, provider and query or prompt, and the page from its template (`review.html`) |
| `providers/` | each API's requests, candidates or images from its replies, and its prices |
| `render.py` | nothing; it is the shell. Reads files, drives Chrome (putting a candidate into a slot when asked), writes PNGs |
| `art.py` | nothing; the shell for provenance. Hashes images, reads and writes sidecars |
| `sourcing.py` | nothing; the shell for candidates and providers. Sends requests, polls queues, downloads originals, draws sheets, writes kept images |
| `runs.py` | nothing; the shell for briefs, previews and review. Makes the run folder, runs each job through `sourcing`, writes the manifest; renders previews through `render` and writes `checks.yaml` and `review.html`; reads a run for review, saves `verdicts.yaml` and keeps a need's keeps |
| `review_server.py` | nothing; the shell for the review page. Serves it and the run's files on 127.0.0.1, and saves what the page posts through `runs` |
| `cli.py` | the `ballyhoo` command |

## Tests

    uv run pytest -m "not browser"    # the pure core, in about half a second
    uv run pytest                     # everything, including real-browser tests (about a minute)
    uv run pytest --update-expected   # after an intentional layout change, rewrite the snapshot

- `tests/unit/` tests the core with plain data: no browser, no files.
- `tests/integration/test_render.py` runs the Phase 1 acceptance criteria and the
  provenance check through a real browser on a small synthetic template.
- `tests/integration/test_provenance_cli.py` runs `ballyhoo provenance made` on
  files, without a browser.
- `tests/integration/test_sourcing.py` runs search, generation (including queued
  providers), contact sheets and `keep` against a mock HTTP transport: no network.
- `tests/integration/test_source.py` runs `ballyhoo source` on briefs with
  `tests/fake_provider.py`, a provider registered only in tests. It answers through a
  mock transport and draws bright, dark and small images at test time. The query or
  prompt picks the image, "error" gets a 503, and seed 13 is refused.
- `tests/integration/test_preview_cli.py` renders the smoke template on its own, and runs
  `ballyhoo preview` on runs sourced from the fake provider: a dark candidate fails
  contrast, a 400 px one fails the upscale check, a bright one passes, and a template
  problem stops the preview before anything renders.
- `tests/integration/test_review_cli.py` runs the review server on an ephemeral port, on a
  run sourced from the fake provider, and drives it with httpx: the page, the run's files
  and nothing outside it, a save refused with every problem, a save written. It then runs
  `keep --verdicts` and its refusals, and `review --summary`. One browser test rates on the
  page, saves, and checks the read-only copy.
- `tests/integration/test_smoke_brief.py` checks that the committed smoke brief parses, its
  templates exist, its Pexels requests build, and no need or query asks for anyone older
  than middle age. No network.
- `tests/integration/test_code_digest.py` checks that the render cache's code digest
  covers the modules rendering imports and not the sourcing ones.
- `tests/integration/test_lac_designs.py` runs the seven LAC templates with stand-in
  art drawn by `tests/lac_art.py`: a snapshot of every creative's font size and line
  count (`tests/fixtures/lac/expected.yaml`), and a regression test for each bug
  found while building those ads.
