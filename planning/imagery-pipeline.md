# Plan: briefs, runs and review — the imagery pipeline end to end

**Status: steps 1 (brief and source), 2 (scene slot and preview) and 3 (verdicts and review)
built 2026-09-14, and step 3's review reworked for a thread with an agent 2026-09-25 (§ 3,
"Reworked"); step 4's first live run made 2026-09-14, with the author's ratings pending;
step 5 built 2026-09-16. Drawings (styles, the chroma-key cut-out, the `#figure` slot) are
built too; the direction note below predates them. Open next work is § 6.** It continues `planning/phase-2-imagery.md`, whose increments 1–4
(provenance, candidates, stock and generation providers) are built. The author delegated the
decisions below ("do what you think is best for now"); revisit any of them freely before
building. Delete this file when the steps are done and their lessons are in `docs/design.md`.

**Direction, 2026-09-14 (the author):** photos come from stock (Pexels), with queries tuned by
people and agents. Generated images will be drawings used as transparent cut-outs, like the
partner's character art, which a later step puts into a `#figure` slot. That step's design
(drawing prompts, background removal, the mask check) is not settled. Step 2 builds the photo
slot, `#scene`, only; a candidate's slot is a field (`Preview.slot`), so adding `#figure`
means a new slot value and its checks, not a restructuring.

## Start here

- **Code:** branch `feature/imagery`, worktree `../ballyhoo-imagery` (`git log
  main..feature/imagery`). Not merged, not pushed. If the worktree is gone:
  `git worktree add ../ballyhoo-imagery feature/imagery && cd ../ballyhoo-imagery && uv sync`.
- **Read first:** `CLAUDE.md` (functional core, imperative shell; comment rules; tests never
  pixel-exact), `README.md` (§ Provenance, § Sourcing images), `docs/design.md` (§ Phase 2),
  `planning/phase-2-imagery.md` (API findings and spike results), then this file.
- **Tests:** `uv run pytest -m "not browser"` (about 1 s), `uv run pytest` (about 50 s).
  205 pass on the branch, 22 of them in a browser.
- **Credentials:** `.env` in the main checkout holds `PEXELS_API_KEY`, `FAL_KEY` and
  `GOOGLE_CLOUD_PROJECT`. The worktree has no `.env` of its own, so run
  `uv run --env-file ../ballyhoo/.env ballyhoo …`. Gemini also uses gcloud application default
  credentials (they work). There are no Firefly credentials.
- **Called live:** Openverse and Gemini (2026-09-12), Pexels (2026-09-13), fal (2026-09-14).
  **Never called live:** Firefly.
- **The art library has provenance** (2026-09-14): every image in `recruitment-creative/` has a
  valid record, so SSO (72) and LAC (42) pass `--check` on this branch and merging it breaks no
  study. Two of them are backfilled Pexels records (`backfilled:` marks a download made before
  provenance existed, which may omit `query`). Spend so far: about ten Gemini images, under $1.

## What this builds, and why

The author wants an easy, repeatable way to run the imagery process end to end and have a
person judge the result against the need. Tests must not touch external services.

One pipeline serves three purposes: the **smoke test** of the tool, **authors picking
imagery** for a study, and, later, **tuning prompts and providers** by comparing runs.

```
brief.yaml ──source──▶ run/<need>/candidates ──preview──▶ run/<need>/previews ──review──▶ verdicts.yaml ──keep──▶ art library
 what is needed        search + generate        each candidate rendered into     a person rates      picks, with
                                                real templates, and checked      each candidate      provenance
```

- **The smoke test is the real pipeline on a small brief checked into the repo.** There is no
  separate harness to drift out of step with the tool.
- **The machine judges what it can; a person judges the rest.** Each candidate is rendered
  into real templates with a sample headline, and the existing checks (fit, contrast, text
  share, blank, load) run on it, plus a new check for an upscaled scene. The person sees
  the ad, not a raw photo, and judges fit to the need.
- **A run is an immutable folder.** Comparing a prompt change means comparing two folders.
- **Files in, files out.** `verdicts.yaml` is the only human input ballyhoo reads. Where the
  rating UI runs (a local server now, a published page later) is interchangeable.
- **pytest never calls a provider.** A fake provider, registered only in tests, draws images
  with known geometry at test time.

## Decisions

| Decision | Why |
|---|---|
| A photo template marks its swappable image `<img id="scene" src="…">`. This is the only change to the template contract. | Preview must know which image to swap. An id matches `#canvas`, `#headline` and `#figure`. |
| Preview sets `#scene`'s `src` in the page to the candidate's absolute `file://` URL **before** `PREPARE_JS` awaits images. Template files are never copied or edited. | Relative paths keep resolving, and no temporary templates land in a designs directory. |
| **Preview renders are not ads.** They are written only inside the run, never to `out/`. The substituted scene is exempt from the provenance check (nothing is picked yet); every other image the template references still needs provenance. | `out/` only ever holds ads that pass, provenance included. |
| New check, **scene upscaled**: fails when `#scene` is drawn more than 1.25× its natural size in either direction. The page measures (rect, `naturalWidth`, `naturalHeight`, `object-fit`); Python decides. | A 640 px candidate stretched over a 1080 px ad passes every other check and looks soft. |
| **`ballyhoo review <run>` serves the review page on 127.0.0.1** (stdlib `http.server`) and writes `verdicts.yaml` when the page saves. Opened as a plain file, the page is read-only. | No copy-paste, and no dependency on the artifact runtime for a smoke test. |
| The same page, published as an Artifact with a database, is the remote-author version (a later step). The agent exports its database to `verdicts.yaml`. | This keeps the author's decision that picks happen on a review page, without ballyhoo talking to it. |
| Verdicts are a **named map by need, then candidate id**. | Ids are stable; positions are not (the same reason variants are maps). One stock photo can be a candidate of two needs, judged against each. |
| `picked.by` comes from the verdicts' `rated_by`, which the review page requires before saving. | A pick names a person. |
| `source` downloads full-size stock files into the run, and `keep --verdicts` copies from the run. | Preview needs local files, and the kept bytes are exactly the ones that were previewed and rated. |
| **Spend guard:** `source --plan` prints requests and estimated cost and sends nothing. `source` refuses above `--max-cost` (default $2). A provider with no published price (Firefly) counts as over the limit unless `--allow-unpriced`. | Fail loudly before spending, not after. |
| `smoke/` at the repo root holds `brief.yaml` and one photo template. | It is a tool fixture, like `tests/fixtures/`, and everything in it is cleared to publish. |
| `runs/` is gitignored; `source` writes to `runs/` next to the brief unless `--out` says otherwise. | Runs are derived. |

## Formats

### The brief

Paths resolve relative to the brief. Need names are lowercase slugs and a named map, never a list.

```yaml
designs: designs                  # default ./designs, as in a copy file
defaults:
  n: 2                            # results per query, images per prompt
  size: 1080x1080                 # shape to generate; default: the first preview template's size
  prompt_suffix: >-               # appended to every generation prompt
    Natural daylight, everyday clothes, candid and dignified; not tourist imagery and not
    poverty imagery. No text, signs or lettering anywhere in the image.
  preview:
    templates: [photo-band/1080x1080]
    copy: "Take a short survey and get KES 100 airtime."

ea-woman:
  need: A woman who reads as East African, middle-aged, in a photo that stops the scroll.
  search:
    pexels: middle aged african woman portrait smiling     # a string, or a list of queries
  generate:
    gemini: Photograph of a woman in her fifties sitting outside her home, reading a message on her mobile phone.
    fal:                                                   # the map form carries provider options
      prompt: Photograph of a woman in her fifties …
      model: fal-ai/flux-2-max

na-man:
  need: A man who reads as North African or Arab, middle-aged, in his own shop.
  generate:
    gemini: {prompt: "…", image_size: 1K}
  n: 4                            # any default can be overridden per need
```

- `need` is required: it is what the person rates against, and it is shown on the review page.
- A need must have `search` or `generate`, or both.
- Unknown providers, unknown keys and a template that does not exist are errors, all reported
  together, before any request (as `copyfile.parse` does).
- `designs` and `defaults` are reserved names.

### The run folder

```
runs/2026-09-13-1/
  brief.yaml               the brief as it was run (a copy)
  manifest.yaml            what ran: see below
  ea-woman/
    candidates.yaml        the existing candidates format
    thumbs/  sheet-01.png  generated/
    originals/<id>.<ext>   full-size stock files, as delivered
    previews/<id>_<design>_<W>x<H>.png
    checks.yaml            per candidate per template: pass or the failure messages, and the summary
  review.html
  verdicts.yaml            written by the review page; absent until someone rates
```

Run names are `<date>-<n>`, with n counting up from 1 for that day. `source` never writes
into an existing run.

### manifest.yaml

```yaml
brief: ../../smoke/brief.yaml
started: 2026-09-13T10:02:11Z
finished: 2026-09-13T10:04:40Z
ballyhoo: <code digest, as the render cache uses>
estimated_cost_usd: 0.86
requests:
  - {need: ea-woman, provider: pexels, kind: search, query: "…", results: 2}
  - {need: ea-woman, provider: gemini, kind: generate, model: gemini-3.1-flash-image, seeds: [81, 82], images: 2, refused: 0, seconds: 27.4}
errors: []
```

### verdicts.yaml

As built in step 3, keyed by need and then candidate id:

```yaml
rated_by: A. Author
rated_on: 2026-09-13
needs:
  ma-older-man:
    gemini-e7cf824177a6:
      verdict: keep               # keep | maybe | drop
      issues: [tourist]           # from the fixed list below
      note: Good face; the kasbah looks like a postcard.
    pexels-7544779:
      verdict: drop
      issues: [off-brief]
```

Issues, fixed in code (`verdicts.ISSUES`): `minor` (anyone could read as under 18), `age`
(reads older than middle age; `docs/creative-rules.md`), `text` (text or lettering in the
image), `tourist`, `poverty`, `artefact` (hands, phones, faces), `off-brief`, `style`
(clashes with the campaign), `brand` (a visible logo), `crop` (no room for the headline).

### The review page

One static HTML file built from the run data: a pure function makes the data, and a
template in the package wraps it. It groups candidates by need; the need's text is at the
top of each group, then the summary table. For each candidate it shows:

- the thumbnail and the preview renders, with any check failures shown on them;
- the provider, and the query or prompt;
- the photographer and licence, or the model and seed;
- keep / maybe / drop, the issue checkboxes and a note.

A name field is required before saving, and the page saves the whole verdicts map in one
go (superseded: each mark saves as it is made; § 3, "Reworked"). With no server (opened as a
file) the controls are disabled. As built, it also shows
alt text, every query that found a photo, and an agent's verdict as a hint.

## Modules

| Module | Kind | Does |
|---|---|---|
| `brief.py` | pure | Validates a loaded brief. Expands it into source jobs (need, provider, kind, query or prompt, n, options). Estimates cost from each provider's `PRICE`. Names the run. |
| `preview.py` | pure | Which (candidate, template) previews to render and their file names; the scene-upscale check; `checks.yaml` data. |
| `verdicts.py` | pure | Validates verdicts; picks from verdicts (`keep` ids per need). |
| `review.py` | pure | The review page's data from a run's candidates, checks and verdicts; the summary of verdicts per need, provider and query or prompt. |
| `runs.py` | shell | Creates the run folder, runs the source jobs through `sourcing`, downloads stock originals, writes the manifest, renders previews, builds `review.html`. |
| `render.py` | shell | Gains an optional scene override per job (`Job.scene: Path \| None`), and returns the `#scene` measurements. |
| `review_server.py` | shell | The 127.0.0.1 server: GET the page and run files; POST verdicts, validated by `verdicts.py` before writing. |
| `providers/*.py` | pure | Each gains `PRICE` (a dict keyed by model and size, with the date it was checked). |
| `cli.py` | shell | `source`, `review`, and `keep <run> --verdicts --need <need> --to <dir>`. |

`sourcing.search` and `sourcing.generate` take the provider module, so `runs.py` takes a
**provider registry** (`{"pexels": pexels, …}`) instead of importing `cli.STOCK`. Tests
pass `{"fake": fake_provider}`.

## Steps

Each step ends with the suite green, a commit, and the docs updated in a separate commit.

### 1. Brief and source (built 2026-09-14)

`brief.py`, `runs.py` (sourcing only), `ballyhoo source BRIEF [--plan] [--providers p,q]
[--max-cost 2] [--allow-unpriced] [--out DIR]`.

- A brief with every kind of mistake reports all of them and sends nothing.
- `--plan` prints each request and the estimated cost, and writes nothing.
- Over `--max-cost`, it exits non-zero before any request.
- `source` on the fake provider writes a run folder with `brief.yaml`, `manifest.yaml`, and
  per need `candidates.yaml`, thumbnails, a sheet and `originals/`.
- One provider's refusal or HTTP error is recorded in the manifest and does not stop the
  other needs; the exit status is non-zero.
- Tests: unit tests for brief parsing, expansion, cost and run naming. An integration test
  (no browser) runs `source` with the fake provider through `httpx.MockTransport`.

**Built as planned, with these differences:**

- `--out DIR` is the directory runs go in, not the run itself. `--seed N` was added (as on
  `generate`); without it a run's seeds are random.
- Before any request, `brief.request_problems` builds every request without sending it, so a
  missing credential or a size the provider refuses (Gemini's aspect ratios) stops the run
  while it is free. It cannot check Gemini's application default credentials.
- The manifest's `ballyhoo` is a digest of the whole package, not the render digest: a run
  depends on the sourcing code, which the render digest now leaves out. Each request also
  records `seconds` and `estimated_usd`; a generation records `size`, its options and `prompt`;
  a search records `new` and `already_found`, because the author tunes queries and needs to see
  how much each one adds.
- Stock candidates' `full` and `preview` name the downloaded `originals/<id>.<ext>`, their
  record gains `download_url`, and thumbnails are made from the original (no second download).
  Each `candidates.yaml` entry shows `query` beside its id.
- Stock originals are **not capped** (see `docs/design.md` § Judging imagery). `download_url` is
  Pexels's `src.original`.
- `sourcing.generate` returns refusals separately from errors, for the manifest's `refused`.
- `n` defaults to 2. An explicit `size` (in the need or in `defaults`) wins over the preview
  template's size. `preview` is optional for now.
- The provider registry is `cli.PROVIDERS`, keyed by each module's `NAME` (stock providers
  gained one); `runs` takes it as an argument, and tests pass `{"fake": fake_provider}`.
- Every provider has `PRICE` and `search_price` or `image_price`; Gemini also lists
  `OPTIONS` (`image_size`). Prices and their sources are in `planning/phase-2-imagery.md`.
- The render cache's `code_digest` now covers only `render.py` and what it imports
  (`cache.code_modules`), so the new modules re-render nothing. Merging the branch still
  re-renders every study once, because `render.py` and `cache.py` changed.

**For step 2:**

- `Need.templates` and `Need.copy` are parsed and checked (a template must exist) but not
  used yet. Decide whether preview requires them.
- `tests/fake_provider.py` draws `bright` and `dark` images at 1600×1200 for stock and at the
  requested size for generation, and `small` ones at 400×400. Its dark palette is
  near-black (28, 28, 32), so a dark-headline contrast failure needs the headline over the scene,
  not over an opaque band. Make the smoke template's band translucent, or put the headline
  directly on the scene.
- Previews are written into an existing run, which `source` never reuses. The manifest is
  written once, when `source` ends; if preview needs its own record, add a file rather than
  editing the manifest.

**For step 3:** `sourcing.keep` already reads a candidate's `full` as a path relative to the
candidates directory, so keeping from a run copies the rated bytes from `originals/` or
`generated/` without any change.

### 2. Scene slot and preview (built 2026-09-14)

`preview.py`; `render.py` scene override; the scene-upscale check; `smoke/designs/photo-band/1080x1080.html`.

- A preview renders each candidate into each template and writes `previews/` and `checks.yaml`.
- A template without `#scene` is an error naming the template.
- A dark candidate fails contrast under the headline, and a 400 px candidate fails the upscale
  check. A bright, large candidate passes. Assert pass/fail and messages, not pixels.
- `render` of a real copy file is unchanged: the Phase 1 tests and the LAC snapshot still pass.
- Preview never writes to `out/`, and does not require provenance for the substituted scene.
- Tests: unit tests for the upscale decision and preview naming; browser integration tests
  with fake-provider images.

**The smoke template.** A photo full-bleed (`object-fit: cover`) under a CSS-drawn band
(no image), headline in Hind Bold. It references the font at
`../../../tests/fixtures/lac/library/fonts/Hind-Bold.ttf` rather than committing a second
copy. Its default `#scene` `src` is `scene-placeholder.png`, a small committed flat image
with a `made` sidecar, so the template also renders on its own.

**Built as planned, with these differences:**

- **`ballyhoo preview RUN` is its own command**, not the end of `source`. Previewing again
  after a template edit must not spend on providers again, and `source` stays browser-free, so
  its tests need no browser. The smoke flow is `source`, then `preview`, then `review`.
- **No `Job.scene`.** `render.render(browser, template, text, swap=None)` takes a
  `(slot, image path)` pair, and `render.SLOTS = ("scene",)` lists the slots the page
  measures. `preview.Preview` has a `slot` field, so `#figure` would be a new value, not a
  new field.
- **The upscale check runs in every render**, in `checks.py` with the other checks, not only
  in previews: a kept photo too small for its template is as soft in the ad. The real
  hamster-band draws its 2048 px scene at 900 px (0.44×) and passes. The LAC stand-in hamster
  was redrawn at 900 px, because at 450 px it failed. Summaries gain `scene <scale>x`.
- **A swap guard.** The page reports the URL the slot shows (`currentSrc`), and a slot that
  does not show the candidate fails: `srcset` or a `<picture>` would keep the placeholder.
- **Every problem stops the whole preview before anything renders**, as a brief's mistakes
  stop `source`: a template without an `<img id="scene">`, a file a template references that is
  missing, an image other than the slot's own without provenance, a need with candidates but
  no preview templates, a candidate whose image is only a URL, and two previews with one file
  name. Preview requires templates; the brief still does not.
- **Previews are written whether or not they pass**, since the review page shows failures on
  them, and a new preview deletes the need's old `previews/*.png` first. The exit status is
  non-zero for errors and for a preview that did not render, not for failed checks.
- `checks.yaml` holds `copy`, `templates`, `previewed`, `ballyhoo` (the package digest, as in
  the manifest) and a `summary` count. Per candidate it holds `pass`, and per template
  `status` (`pass`, `fail` or `error`), `file`, `summary` and `failures`. There is no separate
  preview record, and the manifest is not touched.
- The run's `brief.yaml` is read with its paths resolved beside the original brief (the
  manifest's `brief`), so moving a run away from its brief makes preview an error.
- The integration tests are `tests/integration/test_preview_cli.py`, because pytest cannot
  collect two modules named `test_preview`. The `sent` fixture moved to `tests/conftest.py`.
- The smoke template's band is 25% cream: the fake dark image gives 1.17:1 and fails contrast,
  and the bright one gives 5.6:1. Its placeholder is a flat 1080 px PNG (5 KB), because a
  smaller one would fail the upscale check when the template renders on its own.

**For step 3:**

- Read `<need>/checks.yaml`. Candidates are keyed by id in `candidates.yaml` order. Each has
  `pass` and `previews[<template>]` with `status`, `file` (relative to the need's folder;
  absent for `error`), `summary` and `failures`. A need with no `checks.yaml` had no candidates
  or has not been previewed.
- Failure messages are sentences for people (`contrast 1.17:1 is below 3:1`, `#scene is
  upscaled 2.70x (max 1.25x): …`). Show them as they are rather than parsing them.
- Previews are full-size PNGs, so the page may want to scale them down.
- Previewing again rewrites `previews/` and `checks.yaml`. Verdicts are keyed by need and
  candidate id, so they survive it.

### 3. Verdicts and review (built 2026-09-14)

`verdicts.py`, `review.py`, `review_server.py`, `ballyhoo review RUN [--port]`,
`ballyhoo keep RUN --verdicts --need NEED --to DIR`.

- Saving from the page writes `verdicts.yaml`. An invalid save (unknown id, unknown issue,
  no name) is rejected with a message and writes nothing.
- `keep --verdicts` keeps every `keep` candidate of the need, copying from the run, with
  `picked.by` from `rated_by`. It refuses a run without verdicts.
- Tests: unit tests for verdict validation and picks. An integration test drives the server
  with `httpx` against a real `http.server` on an ephemeral port (no browser needed), then
  `keep`.

**Built as planned, with these differences:**

- **Verdicts are keyed by need, then candidate id** (`needs: {need: {id: verdict}}`), not by
  id alone. `known` is per need, so one stock photo can be a candidate of two needs in a run,
  and a verdict is a judgement against a need.
- **The `age` issue** was added (`docs/creative-rules.md` in `main`: nobody older than middle
  age, even for 60+ strata). Validation reports every problem together, including unknown
  keys and a date with a time.
- **Agent verdicts**, `agent-verdicts.yaml`, have the same format, with `rated_by` naming the
  agent and model. The page shows them as a small hint and never pre-fills the person's
  controls; `keep --verdicts` refuses a run that has only them. `review --summary --agent`
  counts them, and also validates the file.
- **Every query that found a candidate is recorded**, as `queries` in `candidates.yaml`
  (`candidates.merge`); the provenance `query` stays the first. Pexels's `alt` and Openverse's
  `title` were already in the record, and the page shows them.
- **A summary**, per need, provider and query or prompt: found, keep, maybe, drop, unrated,
  keep rate and issue counts. A photo found by two queries counts for both. It heads each need
  on the page, comes back from each save, and `ballyhoo review RUN --summary` prints it
  without starting a server.
- **`review.html`** is written by `preview` and rewritten by each save, read-only, so a run
  can be viewed without the server. Served, the page is built from disk on each GET.
- **The server** also refuses a request whose `Host` is not 127.0.0.1 or localhost, and a
  save that is not `application/json`, so another site cannot write through the browser.
  It serves any file under the run, resolved with symlinks, and nothing outside it.
- **`keep --verdicts`** sets `picked.on` to `rated_on`, and `fetched` to the day the run
  started, when `source` downloaded the originals (`sourcing.keep` gained `fetched`).
- The page's name field is remembered per browser (`localStorage`). Saving puts every verdict
  in the file under the saver's name: two people rating one run overwrite each other's
  attribution. One rater per run for now.
- The run's `brief.yaml` is read as preview reads it, so `review` also needs the brief's
  designs to still exist.
- Tests: `tests/unit/test_verdicts.py`, `tests/unit/test_review.py`, and
  `tests/integration/test_review_cli.py`, which includes one browser test that rates on the
  page and saves.

**Reworked for a thread with an agent (built 2026-09-25).** One afternoon of the loop on the
Katelyn Romm brief needed a server per run, left ratings unsaved (nothing said Save had not
been pressed), and had the agent naming images A to P on hand-drawn contact sheets. So:

- `review BRIEF|RUNS` serves every run of a brief for as long as the thread lasts: newest
  open, older folded, each headed with what it asked that the run before did not; `GET
  /state`, polled by the page, which offers "New round: show it"; runs still sourcing or
  previewing say so. `review RUN` still serves one run.
- Every candidate has a short name, `3.4` (`names.py`), counting through the run in brief
  order; `keep BRIEF|RUNS|RUN 3.4 … --to … --picked-by …` takes names.
- Every mark saves as it is made (`verdicts.merge`, `runs.save_mark`); one rater per run until
  every mark is cleared; a mark not saved says why on its card.
- A note per need (`notes:` in `verdicts.yaml`), and `review BRIEF --summary` for the agent.
- Usage is in README § Review; the reasons are in `docs/design.md` § Judging imagery.

**For step 4:**

- The smoke flow is `source`, `preview`, then `review` (which prints its URL), then
  `review --summary`. Write the smoke brief's needs in line with `docs/creative-rules.md`:
  "in their fifties", never "elderly" or "60 or more", even for 60+ strata, and give each need
  several Pexels queries, since the summary's per-query keep rate is what tunes them.
- An agent can pre-rate a run into `agent-verdicts.yaml` and compare its summary with the
  person's (`--summary --agent`).
- Drawings for `#figure` are not built; their candidates would show `prompt`, `model` and
  `seed` on the page already, but preview fills only `#scene`.

### 4. Smoke brief and the first live run (run 2026-09-14; the author's ratings are pending)

`smoke/brief.yaml`: three needs, each a woman or man who looks to be in their fifties, with
four Pexels queries of eight results. It is stock only, since photos come from stock and
drawings are not built:

- `ke-woman`: a Kenyan woman in her fifties, rural;
- `ma-man`: a Moroccan man in his fifties, in the rural south;
- `ma-woman`: an unveiled Moroccan woman in her fifties, in a town. This is the known gap. It
  stays in the brief so each run shows whether stock still lacks it.

Each need says a visible phone is not required and that look-alikes from other countries are
still an open question. Queries follow the spikes' lessons: short, small towns, no "phone", no
clothing words, no negation. Preview copy is English for Kenya and French for Morocco, because
Hind has no Arabic glyphs. `tests/integration/test_smoke_brief.py` keeps the brief parsing and
its wording within the age rule, without a network.

**What ran**, into `smoke/runs/2026-09-14-1` (gitignored):

1. `uv run --env-file ../ballyhoo/.env ballyhoo source smoke/brief.yaml --plan`: 12 requests, $0.00.
2. The same without `--plan`: 12 searches in 2 minutes, 0 errors. It found 85 candidates
   (ke-woman 28, ma-man 27, ma-woman 30) and 198 MB of originals, 1667×2500 to 7952×5304.
3. `uv run ballyhoo preview smoke/runs/2026-09-14-1`: 85 previews in 5 min 54 s (401 s of CPU),
   0 errors. 23 pass and 62 fail, and every failure is contrast under the 25% band:
   ke-woman 11 pass and 17 fail, ma-man 8 and 19, ma-woman 4 and 26. The English copy set at
   84 px on 2 lines, the French at 78 px on 3.
4. An agent pre-rated every candidate into `agent-verdicts.yaml`, then ran
   `ballyhoo review RUN --summary --agent` (below).
5. `ballyhoo review RUN --port 0` served the page (editable), thumbnails and previews. A path
   outside the run got 404, and a request with another `Host` got 403.

**Nothing broke on real Pexels replies.** Checked in particular:

- **EXIF orientation:** every original is orientation 1, and every recorded size matches its file.
- **Alt text:** every photo has one.
- **Duplicates:** 4, 5 and 2 photos per need came back from more than one query, and each query
  is credited. Two photos were candidates of both women's needs, rated per need.
- **Upscaling:** portrait photos under `object-fit: cover` drew at 0.20x to 0.65x, never near
  1.25x. Pexels originals are always big enough for a 1080 px ad.
- **Preview timing:** a render takes about 2 s, and writing its PNG 0.3 to 0.6 s; a 7952×5304
  original adds 0.6 to 1.7 s over a 1600 px copy of the same photo. The four workers reached only
  120% CPU, because each render's screenshots become arrays and are checked in Python on the one
  event loop. Fine for a smoke run; run the checks off the loop if runs grow.
- **Stopping the server:** `review` started as a background job of a non-interactive shell
  inherits SIGINT as ignored, so "Ctrl+C stops" does not apply. Stop it with SIGTERM.

**Findings:**

- **The template's centre crop puts faces under the headline.** Most people shots are portrait
  head-and-shoulders. `cover` centred on a square, under a band across the top third, runs the
  headline over the forehead or eyes in 8 of the 10 photos the agent rated keep or maybe.
  Nothing detects it (the face check under step 5). A per-template or per-candidate
  `object-position` is the likely fix; the author decides.
- **The checks and the need barely overlap.** Of the 23 candidates that pass the checks, the
  agent dropped 20. Of the 7 it rated keep or maybe that fail, all fail contrast under this
  deliberately translucent band; a study's opaque band would pass them.
- **Alt text predicts age.** It says "elderly", "senior" or "elder" for 38 of the 85; the agent
  marked 38 `age`, 32 of them the same photos. "middle aged" in a query does not stop this.
- **`ma-woman` found no fit, as the spikes did.** Every woman wears a headscarf and half read as
  elderly, and "woman shopkeeper Morocco" returns men in souks.

**The agent's verdicts** (`claude-code (claude-opus-5)`, graded strictly against the need and
`docs/creative-rules.md`). A photo found by two queries counts for both, and "new" is what
`source` reported as not already found.

| Need | Query | New | Keep | Maybe | Drop |
|---|---|---|---|---|---|
| ke-woman | middle aged woman farmer Kenya | 8 | 0 | 2 | 6 |
| ke-woman | middle aged Kenyan woman | 8 | 0 | 2 | 6 |
| ke-woman | mature woman Kenya village | 6 | 0 | 0 | 8 |
| ke-woman | middle aged woman Nyeri | 6 | 0 | 0 | 8 |
| ma-man | middle aged man Tiznit | 8 | 0 | 2 | 6 |
| ma-man | middle aged man Taroudant | 4 | 1 | 1 | 6 |
| ma-man | Moroccan village man | 8 | 0 | 2 | 6 |
| ma-man | middle aged farmer Morocco | 7 | 1 | 1 | 6 |
| ma-woman | each of its four queries | 8, 7, 7, 8 | 0 | 0 | 8 |

Per need: ke-woman 0 keep and 4 maybe of 28; ma-man 1 keep (4%, `pexels-12573207`) and 5 maybe of
27; ma-woman 0 of 30. The commonest issues are `off-brief` (59) and `age` (38), then `tourist`
(15) and `crop` (8).

**Still to do:**

1. The author rates the run on its review page (`ballyhoo review smoke/runs/2026-09-14-1`),
   saving `verdicts.yaml`.
2. Compare the author's summary with the agent's (`--summary` and `--summary --agent`), record
   the keep rate per query in `planning/phase-2-imagery.md` § Spike results, and adjust the queries.
3. Decide how photo templates place a portrait photo (above).

### 5. Provider search options, and a smoke brief written around regions

The regional spike (2026-09-16, recorded in `planning/phase-2-imagery.md` § Spike results)
found 33 fits where the country-level spikes found almost none, and it asked for one tool
change: Pexels's `orientation`.

**Search options, generally.** A search takes provider options the way a generation already
does, so nothing about this is special to Pexels:

- a stock provider lists what it accepts in `SEARCH_OPTIONS`, as a generator lists `OPTIONS`;
- in a brief, a query is a string or a map with `query` and those options, per query;
- an option the provider does not accept is an error that names it and lists what that
  provider takes, reported with the brief's other problems, before anything is sent;
- an option's *value* is checked by the provider's own request builder, so a bad one is
  reported by `request_problems` alongside a missing credential;
- Openverse declares no options, so an option named for it is that same error rather than a
  silently ignored key;
- `ballyhoo stock search` gains `--orientation`, refused for a provider that does not take it;
- the manifest records the options with the query, and each candidate's provenance keeps them
  as `search_options`, so a photo can be traced to the exact search that found it.

**Only `orientation`, and deliberately not `size` or `color`.** The spike ran all three
against the API. `size=large` only reorders toward the biggest files: every result was
already 3000 px or more, an ad is 1080 px, and `source` downloads `src.original` whatever
`size` says, so it changes nothing that matters. `color=orange` actively selects the look
§ Audience bars — it returned keffiyehs in dusty alleys and earth-toned elders, because a
colour filter selects the palette documentary photography already has. `orientation=square`
earns its place: it returns a genuinely different set (8000 matches against 5061 for the same
query) and it is the shape the 1080×1080 templates want, so it removes a crop decision.
Curated and featured collections are seasonal moodboards and cannot serve a demographic need.

**The smoke brief is rewritten around regions**, replacing `ke-woman`, `ma-man` and
`ma-woman`: `ea-woman`, `na-man` and `na-woman`, each with the spike's best three queries and
one new query worth trying, at n=8. One need's best query also sets `orientation: square`, so
the option is exercised live and this run's keep rate for it can be read against the spike's
unfiltered result for the same query.

**Built as planned (2026-09-16), with these differences:**

- **`SEARCH_OPTIONS`, not `OPTIONS`.** A module can both search and generate (the test provider
  does), so the two lists cannot share a name.
- **A query is a string or a map** with `query` and the options; an unknown key names the query
  by its position in the list (`ke/search/pexels query 2: …`) and lists what that provider takes.
  An option's *value* is checked by the provider's own request builder, which raises ValueError,
  so a bad one is reported by `request_problems` beside a missing credential.
- **`candidates.with_search_options`** puts the options in the record as `search_options`;
  `sourcing.search` applies it to what a search returns, so every provider gets it for free.
- **The need texts were written twice.** They first spelled out what makes a photo
  eye-catching; the author then settled that it is a judgement, not a checklist, so each need
  now says the rater decides by looking and names the two reference photos in the art library.
- **The run's copy of `brief.yaml` was updated with the corrected need prose**, so the author
  rates against the right instruction. The queries in it are untouched, so it still records what
  was searched.

**What ran**, into `smoke/runs/2026-09-16-1` (gitignored):

1. `source --plan`: 12 requests, $0.00, with `orientation: square` printed under its query.
2. `source`: 12 searches, 0 errors, 96 candidates, **no duplicates at all** (96 of 96 new).
   Originals 1963×2919 to 7728×5152; the 8 square results are 2048×2048 and up.
3. `preview`: 96 previews, 16 pass, 80 fail, 0 errors. Every failure is contrast under the
   translucent band, as in the first live run.
4. An agent pre-rated all 96 into `agent-verdicts.yaml` and ran `review --summary --agent`.
   Keep rates per query are in `planning/phase-2-imagery.md` § Spike results.

**Nothing broke on real data.** The option reached the API, the manifest recorded it beside the
query, and the 8 candidates it found carry `search_options: {orientation: square}` in their
provenance while the other 88 carry none.

### 6. Later, not planned in detail

- `ballyhoo runs summary runs/*`: keep rate and issues by need, provider, model and prompt.
- `ballyhoo doctor`: one cheap call per provider with credentials, to catch expired keys and
  API changes.
- **A page the author can reach from another device.** The review server listens on
  127.0.0.1, so an author following the thread on a phone cannot open it. Publishing the
  review page as an Artifact with a database, and exporting its database to `verdicts.yaml`,
  is one way; it wants its own plan, with its own access question.
- **Extending a cut-off drawing**, and framing drawings so they are not cut off:
  `planning/extend-drawings.md`.
- A face check for photo templates (a headline over a face). Nothing detects it now; the
  person does.
- Photo templates for real studies, in `recruitment-creative/designs/`, around real picks.

## Testing

| Tier | What | External services |
|---|---|---|
| Unit | Every pure module above, with plain data | none |
| Integration | `source`, preview, review server and `keep --verdicts`, with the fake provider and `httpx.MockTransport`; preview through a real browser (`@pytest.mark.browser`) | none |
| Smoke | `ballyhoo source smoke/brief.yaml` then `ballyhoo review`; a person rates | yes, by design; never run by pytest |

**`tests/fake_provider.py`** implements both the stock and the generator interfaces
(`search_request`/`parse_search`, `generate_request`/`parse_image`), with `NAME = "fake"`,
`PRICE` and `Refused`. Its images are drawn at test time with known geometry:

- `bright`: large and light, so a dark headline passes contrast;
- `dark`: large and near the headline colour, so contrast fails;
- `small`: 400 px, so the upscale check fails;
- seed 13: always refused.

The prompt or query picks the image, so a test says which outcome it wants in the brief.
It is a module, not a mock, so `runs.py` exercises the same code paths it will with
Pexels and Gemini.

## Things to verify while building

- ~~Pexels originals can be 20+ MB; cap them with imgix-style parameters?~~ Settled in step 1:
  not capped. Pexels documents only its preset sizes, not custom `w`/`h`, and resized copies
  are re-encoded. The URL fetched is recorded as `download_url`.
- ~~Setting `#scene`'s `src` to a `file://` path outside the template's directory, and that
  `decode()` waits for the new image, not the placeholder.~~ Settled in step 2, in Chrome
  through Playwright. After `src` changes, `decode()` resolved only once a replacement delayed
  1.5 s over HTTP had arrived, reporting its `naturalWidth` and `currentSrc`. A `file://` image in
  another directory tree loads with or without `--allow-file-access-from-files`, which only
  CORS-mode fetches (masks) need. A missing file rejects `decode()` with `EncodingError`, which
  `PREPARE_JS` reports as a load failure. The preview test asserts the candidate's scale
  (0.90x), not the placeholder's (1.00x).
- ~~The `code_digest` render cache hashes every `*.py` in the package.~~ Settled in step 1: it
  follows `render.py`'s imports instead, so sourcing and pipeline modules are left out without
  having to be listed. If step 2's `render.py` imports `preview.py`, that module is covered
  automatically.

## Open questions for the author (carried over)

- FLUX through fal or BFL direct; whether vlab has an Adobe Firefly Services contract;
  whether to ask Unsplash or drop it.
- Which Google Cloud project pays for Gemini.
