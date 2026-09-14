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
- `#figure`, optional: the cut-out the headline must not touch.
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
query: older woman phone market kenya
fetched: 2026-09-12
picked: {by: A. Author, on: 2026-09-12}
```

| `source` | Required besides `sha256` |
|---|---|
| `stock` | `provider`, `id`, `page_url`, `creator`, `licence`, `licence_url`, `query`, `fetched`, `picked` (`creator_url` optional). A photo downloaded before provenance existed is marked `backfilled: <date>` and may omit `query` |
| `generated` | `provider`, `model`, `prompt`, `seed`, `generated`, `picked` |
| `made` | `by` (who made it, and the source document), `rights` (on what terms we use it) |

`picked.by` names the person who chose the image. For art a person made, such as
a partner's, write the records with

    uv run ballyhoo provenance made characters/*.png --by "<who, and the source document>" --rights "<terms>"

It never replaces an existing record, and writes none if any file cannot have one.

## Sourcing images

The agent searches or generates **candidates**; a person picks among them on the
study's review page; `keep` copies a pick into the art library with its provenance.

    uv run ballyhoo stock search "older woman phone market" --provider pexels --n 40 --out candidates/ke-older
    GOOGLE_CLOUD_PROJECT=<project> uv run ballyhoo generate "<prompt>" --provider gemini --size 1080x1080 --n 4 --out candidates/ke-older
    uv run ballyhoo keep candidates/ke-older/candidates.yaml pexels-3573351=ke-woman-market \
        --to ../recruitment-creative/scenes --picked-by "<the person who picked>"

A candidates directory holds:

| Path | What |
|---|---|
| `candidates.yaml` | one entry per candidate: `n`, `id`, `query` (for stock, the search that found it first), `width`, `height`, `full` and `preview` (URLs, or paths in this directory), `thumb`, and the provenance record less `sha256`, `picked` and `fetched` |
| `originals/<id>.<ext>` | full-size stock files as delivered, when `source` made the directory; `full` and `preview` name them, and the record's `download_url` is the URL they came from |
| `thumbs/<id>.jpg` | 640 px on the long edge, for review pages |
| `sheet-01.png` … | contact sheets, 20 to a sheet, numbered by `n` |
| `generated/<id>.<ext>` | generated images, as delivered |

Searches and generations append to the directory. Ids are `<provider>-<provider's
id>` for stock and `<provider>-<first 12 hex digits of sha256>` for generated
images, so the same image is never listed twice and numbers never change.

| `--provider` | Kind | Credentials | Notes |
|---|---|---|---|
| `pexels` | stock | `PEXELS_API_KEY` | |
| `openverse` | stock | none | CC0 and public domain only, which in practice means archive images |
| `gemini` | generate | Google application default credentials, and `GOOGLE_CLOUD_PROJECT` naming who pays | Vertex; `--image-size 1K`/`2K`/`4K`; `--size` sets the aspect ratio, which must be one Gemini supports |
| `fal` | generate | `FAL_KEY` | FLUX.2 [pro] at exactly `--size` |
| `firefly` | generate | `FIREFLY_SERVICES_CLIENT_ID`, `FIREFLY_SERVICES_CLIENT_SECRET` | Image 5; 1:1, 4:3, 3:4, 16:9 or 9:16 only |

A missing credential is an error naming the variable. `keep` writes the bytes the
provider delivered, never re-encoded (that would strip C2PA credentials); never
overwrites a file; and refuses a download that is not a JPEG, PNG or WebP. None of
the generators return transparency, so kept images are scenes, not cut-outs.

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

ke-older-woman:
  need: A Kenyan woman aged 60 or more, in a rural setting, using a mobile phone.
  search:
    pexels:                       # a query, or a list of queries
      - older african woman mobile phone village
      - kenyan grandmother phone
  generate:
    gemini: A Kenyan woman in her sixties outside her home, reading her phone.
    fal:                          # the map form carries options
      prompt: A Kenyan woman in her sixties outside her home.
      model: fal-ai/flux-2-max    # default: the provider's model
      seed: 81                    # default: --seed, else random
```

- Needs are a named map, and need names are lowercase slugs. `designs` and
  `defaults` are reserved.
- `need` is required: it is what a person rates candidates against. A need has
  `search`, `generate`, or both.
- Generation options: `prompt` (required), `model`, `seed`, and for Gemini
  `image_size` (`1K`, `2K` or `4K`; default `2K`).
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
runs/2026-09-14-1/         <date>-<n>; a second run that day is -2, and no run is written into again
  brief.yaml               the brief as it was run; its relative paths mean what they meant beside the original
  manifest.yaml            what ran
  ke-older-woman/          a candidates directory (above), with stock originals in originals/
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
- {need: ke-older-woman, provider: pexels, kind: search, query: kenyan grandmother phone, n: 2,
   results: 2, new: 1, already_found: 1, seconds: 1.2, estimated_usd: 0.0}
- {need: ke-older-woman, provider: gemini, kind: generate, model: gemini-3.1-flash-image, size: 1080x1080,
   seeds: [81, 82], prompt: "…", images: 1, refused: 1, seconds: 27.4, estimated_usd: 0.202}
errors:
- 'ke-older-woman/gemini generate: seed 82: no image (finish reason IMAGE_SAFETY)'
```

For a search, `new` counts the results that no earlier query for the same need
found in this run, and `already_found` counts the rest. A photo is downloaded
once, and it keeps the first query that found it.

## What fails a creative

| Check | Fails when |
|---|---|
| Provenance | an image the template references has no valid provenance sidecar |
| Fit | at `data-min-size` the text still overflows `#headline` or needs more than `data-max-lines` |
| Figure collision | a headline line box (plus margin) touches `#figure`'s alpha; mask specks under 500 px are ignored |
| Contrast | WCAG ratio of a text colour against the pixels behind its glyphs is below `data-min-contrast` |
| Canvas | the render is not the size in the file name |
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
| `providers/` | each API's requests, candidates or images from its replies, and its prices |
| `render.py` | nothing; it is the shell. Reads files, drives Chrome, writes PNGs |
| `art.py` | nothing; the shell for provenance. Hashes images, reads and writes sidecars |
| `sourcing.py` | nothing; the shell for candidates and providers. Sends requests, polls queues, downloads originals, draws sheets, writes kept images |
| `runs.py` | nothing; the shell for briefs. Makes the run folder, runs each job through `sourcing`, writes the manifest |
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
- `tests/integration/test_code_digest.py` checks that the render cache's code digest
  covers the modules rendering imports and not the sourcing ones.
- `tests/integration/test_lac_designs.py` runs the seven LAC templates with stand-in
  art drawn by `tests/lac_art.py`: a snapshot of every creative's font size and line
  count (`tests/fixtures/lac/expected.yaml`), and a regression test for each bug
  found while building those ads.
