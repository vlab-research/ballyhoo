# Plan: briefs, runs and review — the imagery pipeline end to end

**Status: plan, 2026-09-13. Nothing in this file is built.** It continues
`planning/phase-2-imagery.md`, whose increments 1–4 (provenance, candidates, stock and
generation providers) are built. The author delegated the decisions below ("do what you
think is best for now"); revisit any of them freely before building. Delete this file
when the steps are done and their lessons are in `docs/design.md`.

## Start here

- **Code:** branch `feature/imagery`, worktree `../ballyhoo-imagery` (`git log
  main..feature/imagery`). Not merged, not pushed. If the worktree is gone:
  `git worktree add ../ballyhoo-imagery feature/imagery && cd ../ballyhoo-imagery && uv sync`.
- **Read first:** `CLAUDE.md` (functional core, imperative shell; comment rules; tests never
  pixel-exact), `README.md` (§ Provenance, § Sourcing images), `docs/design.md` (§ Phase 2),
  `planning/phase-2-imagery.md` (API findings and spike results), then this file.
- **Tests:** `uv run pytest -m "not browser"` (about 1 s), `uv run pytest` (about 50 s).
  122 pass on the branch.
- **Credentials:** `.env` in the main checkout holds `PEXELS_API_KEY` and a fal key named
  `FAL_API_KEY` (the code reads `FAL_KEY`: rename it, or map it when running). The worktree
  has no `.env` of its own, so run `uv run --env-file ../ballyhoo/.env ballyhoo …`. Gemini uses
  gcloud application default credentials (they work) plus `GOOGLE_CLOUD_PROJECT`; the spikes
  used `toixotoixo`, but the author has not said which project should pay. There are no
  Firefly credentials.
- **Called live:** Openverse and Gemini (2026-09-12), Pexels (2026-09-13), fal (2026-09-14).
  **Never called live:** Firefly. Spend so far: about ten Gemini images, under $1.

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
| Verdicts are a **named map by candidate id**. | Ids are stable; positions are not (the same reason variants are maps). |
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

ke-older-woman:
  need: A Kenyan woman aged 60 or more, in a rural setting, using a mobile phone.
  search:
    pexels: older african woman mobile phone village     # a string, or a list of queries
  generate:
    gemini: Photograph of a Kenyan woman in her sixties sitting outside her home in a rural village, reading a message on her mobile phone.
    fal:                                                   # the map form carries provider options
      prompt: Photograph of a Kenyan woman in her sixties …
      model: fal-ai/flux-2-max

ma-older-man:
  need: A Moroccan man aged 60 or more, rural south, using a mobile phone.
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
  ke-older-woman/
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
  - {need: ke-older-woman, provider: pexels, kind: search, query: "…", results: 2}
  - {need: ke-older-woman, provider: gemini, kind: generate, model: gemini-3.1-flash-image, seeds: [81, 82], images: 2, refused: 0, seconds: 27.4}
errors: []
```

### verdicts.yaml

```yaml
rated_by: A. Author
rated_on: 2026-09-13
candidates:
  gemini-e7cf824177a6:
    verdict: keep                 # keep | maybe | drop
    issues: [tourist]             # from the fixed list below
    note: Good face; the kasbah looks like a postcard.
  pexels-7544779:
    verdict: drop
    issues: [off-brief]
```

Issues, fixed in code for now: `minor` (anyone could read as under 18), `text` (text or
lettering in the image), `tourist`, `poverty`, `artefact` (hands, phones, faces),
`off-brief`, `style` (clashes with the campaign), `brand` (a visible logo), `crop`
(no room for the headline).

### The review page

One static HTML file built from the run data: a pure function makes the data, and a
template in the package wraps it. It groups candidates by need; the need's text is at the
top of each group. For each candidate it shows:

- the thumbnail and the preview renders, with any check failures shown on them;
- the provider, and the query or prompt;
- the photographer and licence, or the model and seed;
- keep / maybe / drop, the issue checkboxes and a note.

A name field is required before saving, and the page saves the whole verdicts map in one
go. With no server (opened as a file) the controls are disabled.

## Modules

| Module | Kind | Does |
|---|---|---|
| `brief.py` | pure | Validates a loaded brief. Expands it into source jobs (need, provider, kind, query or prompt, n, options). Estimates cost from each provider's `PRICE`. Names the run. |
| `preview.py` | pure | Which (candidate, template) previews to render and their file names; the scene-upscale check; `checks.yaml` data. |
| `verdicts.py` | pure | Validates verdicts; picks from verdicts (`keep` ids per need); later, the runs summary. |
| `review.py` | pure | The review page's data from a run's candidates, checks and verdicts. |
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

### 1. Brief and source

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

### 2. Scene slot and preview

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

### 3. Verdicts and review

`verdicts.py`, `review.py`, `review_server.py`, `ballyhoo review RUN [--port]`,
`ballyhoo keep RUN --verdicts --need NEED --to DIR`.

- Saving from the page writes `verdicts.yaml`. An invalid save (unknown id, unknown issue,
  no name) is rejected with a message and writes nothing.
- `keep --verdicts` keeps every `keep` candidate of the need, copying from the run, with
  `picked.by` from `rated_by`. It refuses a run without verdicts.
- Tests: unit tests for verdict validation and picks. An integration test drives the server
  with `httpx` against a real `http.server` on an ephemeral port (no browser needed), then
  `keep`.

### 4. Smoke brief and the first live run

`smoke/brief.yaml`: three needs × two images, Pexels and Gemini at 1K. Estimated under $1.
Suggested needs: Kenyan woman 60+ rural; Moroccan woman 60+ unveiled in a town; Moroccan man
60+ rural south.

1. Run `uv run --env-file ../ballyhoo/.env ballyhoo source smoke/brief.yaml`, then
   `ballyhoo review runs/<run>`.
2. The author rates the candidates.
3. Record what the verdicts say (keep rate per provider, common issues) in
   `planning/phase-2-imagery.md` § Spike results, and adjust the brief's prompts.
4. README: a *Smoke test* section with those two commands.

### 5. Later, not planned in detail

- `ballyhoo runs summary runs/*`: keep rate and issues by need, provider, model and prompt.
- `ballyhoo doctor`: one cheap call per provider with credentials, to catch expired keys and
  API changes.
- Publishing the review page as an Artifact with a database for remote authors, and exporting
  its database to `verdicts.yaml`.
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

- Pexels originals can be 20+ MB. `images.pexels.com` URLs take imgix-style parameters
  (`?auto=compress&w=2160`); check that a capped download still counts as the photo, and
  record the URL actually fetched in the provenance.
- Setting `#scene`'s `src` to a `file://` path outside the template's directory, with
  `--allow-file-access-from-files`, and that `decode()` waits for the new image, not the
  placeholder.
- The `code_digest` render cache hashes every `*.py` in the package, so adding modules
  re-renders every study's ads once. Consider excluding `providers/`, `sourcing.py` and the
  new pipeline modules from it.

## Open questions for the author (carried over)

- **Partner art is backfilled** (2026-09-14) except `scenes/kids-peeking.png`, a Pexels or
  Unsplash photo whose source is not yet found; LAC's `kids-boxes` fails until it has a record.
  A `stock` record requires `query`, `fetched` and `picked`, which nobody knows for an old
  download. Decide whether a backfilled stock record may omit them (marked, say,
  `backfilled: <date>`), or whether the photo is re-found and re-picked through `keep`.
- FLUX through fal or BFL direct; whether vlab has an Adobe Firefly Services contract;
  whether to ask Unsplash or drop it.
- Which Google Cloud project pays for Gemini.
