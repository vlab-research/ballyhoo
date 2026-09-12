# Plan: Phase 2, sourced imagery (stock photos and generated images)

**Status: in progress on `feature/imagery`, 2026-09-12.** The rationale is in
`docs/design.md` § *Phase 2*; this file is the work. Delete it when Phase 2 is done and
its lessons are in the design doc.

## Why, and the first user

The first campaign to need it recruits adults in Kenya and Morocco, stratified by
age (18–29 up to 60+), gender, region and urban/rural. Round 1 (rendered
2026-09-11) used the partner's illustrated art: every person in it reads as 20s–30s
and urban, and Morocco's only woman is veiled. The authors want **older people and
families**, and the design needs **rural settings**. Round 2 of that campaign is the
acceptance test for this phase.

## Decisions

| Decision | Made |
|---|---|
| **Every image a template references needs a provenance sidecar**, partner art included (backfilled as `source: made`). A render with an image lacking one fails, even when its PNG is up to date. | Author, 2026-09-12 |
| **Picks are made on the study's review page**, which stores them. ballyhoo writes candidates the page can show and takes picks as arguments; it never talks to the page. | Author, 2026-09-12 |
| A search and a generation both produce **candidates** in one format, and one `keep` step moves a picked candidate into the art library with its sidecar. | Plan |
| **`picked.by` names the person** who picked, and `keep` requires it. The agent cannot fill it in for itself. | Plan |
| Every provider is called over **plain HTTP**: pure request builders and response parsers, a thin `httpx` shell. No provider SDKs. Vertex authenticates through application default credentials (`google-auth`). | Plan |
| No provider returns alpha (Gemini, FLUX and Firefly all return opaque images), so **sourced images go in as `scenes/`** first. Cut-outs wait for a background-removal step with a mask check. | Plan |
| The sidecar stores the file's **sha256**, so an image replaced under an old sidecar fails rather than crediting the wrong source. | Plan |

## Findings: the APIs as of 2026-09-12

Researched from the providers' current docs and terms. Details that bind go into
`docs/design.md`.

### Stock

| | Pexels | Unsplash | Openverse | Pixabay |
|---|---|---|---|---|
| Key | `PEXELS_API_KEY` (`Authorization: <key>`) | `UNSPLASH_ACCESS_KEY` (`Authorization: Client-ID <key>`) | none needed (anonymous); optional client credentials | `PIXABAY_API_KEY` (query param) |
| Search | `GET api.pexels.com/v1/search`, `per_page` ≤ 80 | `GET api.unsplash.com/search/photos`, `per_page` ≤ 30 | `GET api.openverse.org/v1/images/`, `page_size` ≤ 20 anonymous | `GET pixabay.com/api/`, `per_page` ≤ 200 |
| Limit | 200/h, 20k/month | 50/h demo, 1000/h production | 20/min, 200/day anonymous | 100/min; must cache 24 h |
| Full size | `src.original` | `urls.raw` / `urls.full`; must GET `links.download_location` on use | `url` (third-party host) | `largeImageURL` (1280 px) without full access |

- **Pexels and Pixabay** forbid use "in a way which portrays someone as suffering from, or
  medicating for, a physical or mental ailment" and "in a political context", and imply no
  endorsement. No model releases are warranted.
- **Unsplash's API is a poor fit for ads.** Its guidelines say the API is "to be used for
  non-automated, high-quality, and authentic experiences", to stay away from "displaying
  advertising near to the API content", and require attribution with a link wherever an
  image is displayed, which a Meta ad cannot carry. Hotlinking is waived for "a derivative
  creative image". **Do not build it until Unsplash says in writing that paid social ads made
  from API images are allowed.**
- **Openverse** licences vary per image. Restrict to `license=cc0,pdm`: CC BY needs
  attribution the ad cannot carry. Openverse does not verify licences, so the sidecar keeps
  its `foreign_landing_url` for checking by hand.

### Generation

| | Gemini (Vertex) | FLUX (fal.ai) | FLUX (BFL direct) | Firefly Services |
|---|---|---|---|---|
| Credentials | ADC; project + `location=global` | `FAL_KEY` | `BFL_API_KEY` | `FIREFLY_SERVICES_CLIENT_ID` / `_SECRET`, OAuth server-to-server; **enterprise contract** |
| Model | `gemini-3.1-flash-image` (`gemini-3-pro-image` for hero images) | `fal-ai/flux-2-pro` | `/v1/flux-2-pro` | `image5` (v4) or `image4_*` (v3) |
| Flow | sync `generateContent`; base64 inline, often JPEG | queue → poll → URL (7 days) | submit → poll → URL (**10 min**) | submit → poll → URL (1 h) |
| Seed | best effort only | yes | yes | yes |
| References | up to 4 characters, 10 objects (3.1 Flash) | `/edit` with `image_urls` | up to 8 input images | 1 reference (v4); style + structure refs (v3) |
| Price | ~$0.067 per 1K image | ~$0.03 per MP | ~$0.03 per MP | unpublished; 4 requests/min |
| Marks | SynthID always; C2PA on Vertex | none from BFL | signed C2PA; removal forbidden | Content Credentials required |

- **No alpha anywhere.** Generate on a plain background; cut-outs need a separate
  background-removal step (fal `birefnet/v2`, or Adobe `remove-background` on the Firefly
  credentials).
- **Keep the provider's bytes as delivered.** Re-encoding breaks C2PA, and BFL and Adobe
  forbid removing Content Credentials. The final ad is a new composite either way.
- **Gemini's person controls** (`person_generation`) work on Vertex only. Imagen's docs barred
  `allow_all` in MENA; check that Morocco prompts are not refused.
- **Indemnity:** Google indemnifies unmodified output of GA models on Vertex, not on the
  Developer API. Adobe indemnifies only with a purchased entitlement. BFL and fal do not.

## Provenance sidecar

`<image>.provenance.yaml` beside the image. Common fields: `source` and `sha256`.

| `source` | Required fields |
|---|---|
| `stock` | `provider`, `id`, `page_url`, `creator`, `creator_url`, `licence`, `licence_url`, `query`, `fetched`, `picked: {by, on}` |
| `generated` | `provider`, `model`, `prompt`, `seed`, `generated`, `picked: {by, on}`; optional `references` (sha256 of each reference image) |
| `made` | `by` (who made it, e.g. the partner and source document), `rights` (on what terms we use it) |

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | Rendering a template that references an image without a valid sidecar (missing, wrong sha256, missing fields) fails, naming the file, even when the PNG is up to date; a stale PNG is deleted |
| 2 | `ballyhoo provenance made FILE... --by --rights` writes sidecars and refuses to overwrite one |
| 3 | `ballyhoo stock search "<query>" --provider pexels --n 40 --out <dir>` writes `candidates.yaml`, thumbnails and a numbered contact sheet, without downloading full-size files |
| 4 | `ballyhoo generate "<prompt>" --provider gemini --n 4 --size 1080x1350 --out <dir>` writes the same format, keeping each image as delivered |
| 5 | `ballyhoo keep <dir>/candidates.yaml <id>[=<name>]... --to <art dir> --picked-by "<name>"` writes the full-size file and its sidecar, and does what the provider's terms require on use |
| 6 | The pure core has unit tests with synthetic JSON: request building, per-provider parsing, candidates, provenance validation, contact-sheet layout |
| 7 | Credentials come only from the environment. A missing one is an error naming the variable, never a skipped provider |
| 8 | Two 1080×1080 photo templates (full-bleed scene under a band; scene on one side, copy on the other) pass the existing checks with stand-in art |

## Increments

Each ends with the suite green and a commit.

1. **Provenance.** `provenance.py` (pure: validate a record against the file's sha256, which
   template refs are images, attribution text); the render check; `ballyhoo provenance made`;
   sidecars for test art. Then backfill `projects/recruitment-creative/` and confirm the LAC and
   SSO studies still render with `--check`.
2. **Candidates.** `candidates.py` (pure: the candidates file, ids, contact-sheet layout,
   `keep` decisions) and the shell, tested with a fake provider.
3. **Stock providers.** Openverse first (no key: spike it live), then Pexels. Unsplash waits on
   its answer.
4. **Generation providers.** Gemini on Vertex (credentials exist: spike it live), then FLUX on
   fal, then Firefly when credentials exist.
5. **Photo templates** (criterion 8).
6. **Review page.** A shortlist section on the SSO review page that stores picks, in the study
   repo. The agent reads picks from it and runs `keep`.
7. **Spike the round-2 briefs** with every working provider; write findings here.
8. **Docs.** README: commands, candidates and sidecar formats. Design doc: lessons.

## Round-2 briefs (the first real queries)

People using a phone in an everyday setting. Not tourist imagery, not poverty imagery.

- **Kenya:** woman 60+; man 60+; three-generation family; farmer or market-centre trader
  in a rural area; man and woman 45–59.
- **Morocco:** woman 60+, veiled and unveiled; man 60+; family at home; rural setting (a
  douar, the Atlas, the south); man and woman 45–59; an unveiled younger woman, which
  round 1 lacks.

## Constraints to carry into the design

- **No model releases** from any stock site: never imply that a pictured person endorses
  the study, and say in the IRB package that the imagery is licensed stock or generated.
- **Styles mix badly.** Round 1 is illustrated; photos next to it read as a different
  campaign. Either photo designs form their own family, or generated images match the
  illustrated style. The adaptive and Zhang arms must still get identical creative.

## Open questions for the author

- **Unsplash:** ask them, or drop it? (Pexels and Openverse cover the spike.)
- **FLUX through fal or BFL direct?** fal: one key also covers background removal, no C2PA.
  BFL: first party, signed C2PA; read its API Service Terms' licence to inputs and outputs first.
- **Firefly:** does vlab have, or want, an Adobe Firefly Services contract?
- **Which Google Cloud project pays for Vertex image generation?** The default gcloud
  project is `toixotoixo`.
- Stock photos or generated images as the default source of people: the spike decides.
