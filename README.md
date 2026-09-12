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
| `stock` | `provider`, `id`, `page_url`, `creator`, `licence`, `licence_url`, `query`, `fetched`, `picked` (`creator_url` optional) |
| `generated` | `provider`, `model`, `prompt`, `seed`, `generated`, `picked` |
| `made` | `by` (who made it, and the source document), `rights` (on what terms we use it) |

`picked.by` names the person who chose the image. For art a person made, such as
a partner's, write the records with

    uv run ballyhoo provenance made characters/*.png --by "<who, and the source document>" --rights "<terms>"

It never replaces an existing record, and writes none if any file cannot have one.

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

Each PNG stores a hash of its inputs: ballyhoo's own code, the text, the
template, and every file the template references. A render is skipped when the
hash matches, so editing one headline re-renders only that creative.

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
| `render.py` | nothing; it is the shell. Reads files, drives Chrome, writes PNGs |
| `art.py` | nothing; the shell for provenance. Hashes images, reads and writes sidecars |
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
- `tests/integration/test_lac_designs.py` runs the seven LAC templates with stand-in
  art drawn by `tests/lac_art.py`: a snapshot of every creative's font size and line
  count (`tests/fixtures/lac/expected.yaml`), and a regression test for each bug
  found while building those ads.
