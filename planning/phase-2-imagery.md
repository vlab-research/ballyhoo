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
| **Photos come from stock; image models make drawings** (illustrated figures used as cut-outs, like the partner character art), never photographs. The work on photos is in the search queries, which people and agents both iterate on. | Author, 2026-09-14 |
| **No one looks older than middle age**, even for a 60+ stratum: people identify with someone younger. Recorded, with its reason, in `docs/creative-rules.md` (on `main`). | Author, 2026-09-14 |
| **Drawings are prompted in words for the house style**, from the author's past prompts, not given existing art as reference images. The existing art was generated in the author's own account, so references are permitted if that changes. | Author, 2026-09-14 |
| The author's past process for cut-outs: generate in Firefly, then Adobe Express's automatic remove background. The spike settled ballyhoo's equivalent: generate the figure on flat green and remove it with a numpy chroma key, checked by a mask check (§ Spike results). | Author, 2026-09-14 |

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

### Prices, checked 2026-09-14

These are the `PRICE` tables in the provider modules, which `ballyhoo source` estimates from.

| Provider, model | Price | Source |
|---|---|---|
| Gemini `gemini-3.1-flash-image` | $0.067 (1K), $0.101 (2K), $0.151 (4K) per image: $60 per 1M output tokens × 1120, 1680, 2520 tokens | [Vertex pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing), read only through search excerpts (the page would not render for the fetch tool). It matches the [Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing), updated 2026-09-11 |
| Gemini `gemini-3-pro-image` | $0.134 (1K and 2K), $0.24 (4K): $120 per 1M output tokens | same |
| fal `fal-ai/flux-2-pro` | $0.03 for the first megapixel, $0.015 for each extra, rounded up. 1024×1024 costs $0.03 and 1920×1080 $0.045, so a megapixel is 1024² px | [model page](https://fal.ai/models/fal-ai/flux-2-pro) |
| fal `fal-ai/flux-2-max` | $0.07 for the first megapixel, $0.03 for each extra. The model page does not state the rounding; a fal learn page says rounded up (1920×1080 costs $0.10) | [model page](https://fal.ai/models/fal-ai/flux-2-max) |
| Pexels | free; 200 requests an hour, 20,000 a month | [API documentation](https://www.pexels.com/api/documentation/) |
| Openverse | nothing charged for anonymous requests; the terms reserve the right to charge for commercial or heavy use | [terms](https://docs.openverse.org/terms_of_service.html) |
| Firefly Services | no published per-image price: it comes with an enterprise contract | [Firefly API docs](https://developer.adobe.com/firefly-services/docs/firefly-api/) (no pricing) |

- Gemini's prices are for output images only. Prompt tokens, and any thinking tokens (billed at
  the text output rate), add a little, so the estimate is a floor.
- fal bills megapixels of input and output. Reference images sent to the edit endpoints add
  to the count.
- FLUX returns 1072×1072 when asked for 1080×1080; the estimate uses the size asked for.
- Pexels's API docs describe only its preset `src` sizes. The `w`, `h` and `auto=compress`
  parameters in those URLs are imgix-style and undocumented for custom use, so `source`
  downloads `src.original` uncapped.

## Spike results

- **Openverse, 2026-09-12: no use for people.** With CC0 and Public Domain Mark only,
  "elderly woman mobile phone africa" and "elderly woman phone" return nothing, and
  "grandmother" returns 240 archive images: Tudor portraits and family photos from about
  1910. It stays as a provider, but it cannot supply contemporary people.
- **Gemini on Vertex, 2026-09-12: works end to end** from the existing gcloud credentials
  (project `toixotoixo`; both `gemini-3.1-flash-image` and `gemini-3-pro-image` are GA there).
  One 1K image took 13 s and came back as a 1024×1024 **PNG**, not the JPEG the docs led us
  to expect. The Kenya brief "woman in her sixties, rural village, reading her phone" gave a
  plausible, dignified scene on the first try.
- **Gemini, round-2 briefs, 2026-09-12** (5 briefs × 2 seeds, 1K, square; 9 images, ~$0.65).
  Every brief gave usable people: an older Kenyan trader at a market centre, older Moroccan
  women veiled and unveiled, older Moroccan men at village doorways. Older age reads clearly,
  which round 1 could not show. Findings:
  - **One refusal** (`IMAGE_SAFETY`, seed 110) on the three-generation Kenyan family, and the
    image that did come back has a "daughter" who could read as a teenager. Family prompts
    need adults stated explicitly (ages), and any family pick needs checking for anyone who
    could read as a minor, since the survey is adults only.
  - **A postcard look.** Golden light, tidy earthen kasbah villages in the Moroccan images:
    close to the tourist imagery the briefs rule out. Prompts need to push toward ordinary
    places (a concrete town house, a douar with breeze-block walls, a market in a small town).
  - **Photoreal, so a separate family from round 1's illustrations.** The style constraint
    below holds: either photo designs, or prompt for the illustrated style.
  - **Composition varies** from close half-length portraits to small full-length figures;
    templates need headroom for the headline, so prompts should name the framing too.

- **Pexels, 2026-09-13: the key works and the parser holds on real replies, but stock does not
  meet the need.** "older african woman mobile phone village", 10 results, none usable:
  - five are older white women from one studio series (the search matched "older woman" and
    "phone" and ignored "african" and "village");
  - one is a younger woman with a logo on her shirt, one an ethnographic portrait of an elder
    without a phone, one a village scene with a child in front, one a black-and-white
    portrait of a young woman.

  Originals run 3456×5184 to 6240×4160. Stock may still serve generic scenes; for specific
  people in specific places, generation carries the need. Try narrower queries (country and
  town names) in the smoke brief before concluding.
- **FLUX on fal, 2026-09-14: works end to end.** `fal-ai/flux-2-pro`, one image of the same
  Kenya brief: 12.5 s, a PNG, and a plausible scene with a warmer, more graded look than
  Gemini's. **Asked for 1080×1080, it returned 1072×1072**: FLUX rounds sizes (apparently to
  multiples of 16). Candidates record the real size, and templates crop with `object-fit`,
  but a preview check for upscaling will see it. The author's `.env` names the key
  `FAL_API_KEY`; the code reads `FAL_KEY`, fal's own name.
- **Side-by-side, 2026-09-14** (3 needs for 60+ people; Pexels at 2 queries × 8, then 3 images each
  from `gemini-3.1-flash-image` at 1K, `gemini-3-pro-image` at 1K, `fal-ai/flux-2-pro` and
  `fal-ai/flux-2-max`, with one prompt per need for every model; 36 images, about $3.12, no
  refusals). This comparison is what led the author to decide that photos come from stock and
  generation makes drawings.
  - **Pexels could not serve any need**: studio shoots of older white women for Kenya, veiled women
    at tourist spots for Morocco, medina men without phones.
  - **Gemini was best at generated photos.** Pro edged out Flash; Flash repeated one composition.
    One Pro image had a flat grey band across the top. The round-2 postcard look was gone once
    prompts named ordinary materials (breeze block, rendered concrete, corrugated iron).
  - **FLUX gave every image a warm orange charity-appeal grade** despite the prompt, and produced
    lettering-like marks, paper notices and a logo-like badge. It dressed Moroccan men in
    South Asian or Gulf clothing. Max cost twice pro and was three times slower, with no gain.
  - **Several "60+" women read 50s**, and "waist-up" was often ignored.
  - **Tool edges:**
    - Gemini at 1K returns 1024 and fal returns 1072 for a 1080 request, both without a warning.
    - `fal.py` detects refusals by `has_nsfw_concepts`, which `flux-2-max`'s schema lacks, so a
      filtered image there may not read as a refusal.
    - Contact-sheet labels overlap portrait tiles.
- **Pexels query spike, 60+ people, 2026-09-14** (50 searches, 632 unique photos, first-pass
  grades by an agent): 8 fit, none with a phone. Kenyan woman 5 (best query
  `elderly woman farmer Kenya`), Moroccan man 3 (`old man Taroudant`, `elderly man Tiznit`),
  unveiled Moroccan woman 0.
  - **"phone", "smartphone" and "texting" outrank place words** and pull in Western studio shoots
    of seniors.
  - **Place words do match through alt text**, but only in short queries (age, sex, place or
    job).
  - **Famous places return what photographers shoot there** (Chefchaouen doors, Maasai
    beadwork). Small towns return ordinary people but run out within 15 results.
  - **Clothing and ethnic words give costume portraits.** Negation backfires: "without
    headscarf" returned only headscarves.
  - **The catalogue is the limit.** By the third or fourth query, 50–90% of results are
    duplicates.
  - **Alt text usually names the country** and "black and white", and would reject about half
    of the results unseen.
  - **Pexels documentation:** `locale` sets only the query language, never a region filter.
    Tags describe what is visible and name places; they never state ethnicity.
- **Pexels query spike, middle-aged people, 2026-09-14** (27 searches, after the age rule).
  Fits, first as confirmed Kenya or Morocco, then with look-alikes allowed:
  - Kenyan woman 1, or 4 with Ethiopian and Ugandan look-alikes;
  - Moroccan man 3, or 7 with Turkish look-alikes;
  - unveiled Moroccan woman 0 of 110.

  **Requiring a visible phone leaves zero for every need.**
  - **Working men of 40–55 are common** (`middle aged man Tiznit`, `Moroccan village man`).
    Rural Kenya on Pexels is mostly Maasai elder portraits, and its middle-aged women are in
    Nairobi markets.
  - **"middle aged" and "mature" barely steer**: a third of results still read too old, and
    caption ages are unreliable.
  - **Job words** (farmer, fisherman, shepherd) find the right ages but pull in other countries.
  - **Printing on clothing and sacks** cost five Kenyan near-misses.
  - **Conclusion:** stock can serve men and, thinly, Kenyan women. The unveiled Moroccan woman
    needs a drawing.
- **Tooling the query loop needs** (each item was hand-scripted in the spikes):
  - many queries in one command, with a sheet per query;
  - duplicate reporting;
  - larger tiles showing id and alt text;
  - grades per photo, with keep rate per query (built in step 3 of `imagery-pipeline.md`);
  - a next-page option;
  - automatic flags for black-and-white photos and for alt text naming another country;
  - Pexels `orientation` and `size` filters.
- **Research, 2026-09-14: other stock sources and cut-outs.**
  - **Pixabay** has the same shape as Pexels and needs no credit on the ad, but bans systematic
    mass downloads. It is the stock source to add next.
  - **Adobe Stock** is paid per image and is the larger catalogue.
  - **Getty, Shutterstock and Wikimedia Commons** fit poorly. **Unsplash+** bans AI use.
  - **No image model returns alpha.** The options are background-removal models on fal
    (`fal-ai/bria/background/remove` at $0.018; `fal-ai/birefnet/v2`), Firefly's remove-background,
    local rembg (pin `birefnet-general`; its default model needs a commercial licence), or a
    chroma key on a solid background. Matting models tend to drop thin strokes and white fills
    in line art.
- **Background removal, 2026-09-14** (about $1.98). Each of the 11 Express cut-outs in
  `recruitment-creative/characters/` was placed on white, grey and green, and each method's mask
  was scored against Express's alpha.
  - **A numpy chroma key on green matches Express best:** IoU 0.997 mean and 0.991 worst,
    0% lost, 0.2 s, free.
    - It estimates the key colour from the image border and ramps alpha between colour
      distances 30 and 110.
    - It removes green blended into edge pixels and despills. Despill triggers on green
      dominance, not the exact key colour, because generated green varies from (9,193,18) to
      (8,251,5).
  - **The same key on white or grey fails** (IoU 0.88 and 0.78): it eats white fills.
  - **Matting models score about the same shape** (IoU 0.99). These are rembg with
    `birefnet-general-lite` (16 s on CPU), fal `birefnet/v2` ($0.001–0.002) and Bria ($0.018).
    - On green they leave a green cast in 34% of the edge band.
    - On white they leave white slabs in concave gaps.
    - Contrary to the research, they did not eat thin strokes or white fills on this art.
  - **Image-to-image generation cannot remove a background.**
    - Gemini asked for transparency returns an opaque PNG with a checkerboard painted in.
    - Asked to re-ground a figure onto green, Gemini keeps it close (mean RGB change 4–17).
    - FLUX.2 pro redraws 14–27% of pixels.
  - **Gemini paints the phone screen's glow into the green**, which no remover can fix; the
    prompt must forbid glow. Vertex refused "young woman" as possibly a child, so state an
    adult age.
  - **The mask check the spike calibrated** flags nothing on Express's cut-outs and catches
    fake transparency, bad white keys and green fringes. It requires:
    - 5–95% of the area transparent;
    - no stray specks;
    - at most 1% soft alpha;
    - residual green at most 0.3% of the figure and 2% of the edge band;
    - painted green light at most 0.15% (provisional, from 4 images);
    - agreement with a colour key.

    It cannot see white slabs on white, or a figure a generator redrew. A person looks at each
    cut-out once, when it is adopted.
- **Drawings, 2026-09-14** (57 images, about $5.23): the author's prompts on
  `gemini-3.1-flash-image`, `gemini-3-pro-image` and `fal-ai/flux-2-pro`.
  - **Benchmark: Firefly wins every prompt.** The author's exact Firefly prompts reproduce
    `cool-cats`, `survey-hamster`, `ke-woman-phone` and `ke-man-phone` (matched by eye, high
    confidence), and none of the three models comes close.
    - "Technical drawing" becomes a blueprint with dimension lines and labels.
    - "Line drawing of a cool woman in Nairobi" becomes a full-length street scene with
      signs, "NAIROBI COOL" lettering and real brands (Safaricom, Equity Bank).
    - Firefly gives one large waist-up figure, no scenery and no text. Other models need that
      stated.
  - **The pastel prompt on the smoke needs**, subject lines in the fifties, white and green
    backgrounds, cut out with the key or birefnet:
    - **Gemini Flash** draws the style best, and is the only model that reliably returns a
      flat, near-pure green (6 of 6).
    - **Gemini Pro** draws well but treats "background" as a picture on a page, adding frames
      and mats.
    - **FLUX** repeats one face, returns sage or lime green, and wrote "BUENOS AIRES" on a
      jacket.
    - **"No text" in the prompt worked:** no text in any of the 36 images.
  - **Against the audience rule, few pass.**
    - "Not pretty… would never be a model", plus the fifties and "extremely detailed",
      produced tired, lined, documentary faces.
    - Flash put every Moroccan in a djellaba or kaftan. Several "Kenyan" women read as European.
    - The author's own art (`man-scarf`, `woman-round-glasses`) reads that phrase as stylish
      people with a quirk or two, which is still to confirm with the author.
  - **Brief shape:**
    - named styles (precise pastel, bright line, black-and-white technical, coloured-pencil
      technical);
    - prompts assembled from a subject line, the style text with guards ("no dimension lines,
      labels or annotations"), framing (waist-up, nothing cropped but the body) and a
      background suffix chosen by the remover.

## Provenance sidecar

`<image>.provenance.yaml` beside the image. Common fields: `source` and `sha256`.

| `source` | Required fields |
|---|---|
| `stock` | `provider`, `id`, `page_url`, `creator`, `licence`, `licence_url`, `query`, `fetched`, `picked: {by, on}`; optional `creator_url` (Openverse often lacks it) |
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

**Status 2026-09-14:** 1–4 are built and tested. Called live: Openverse, Gemini, Pexels, fal.
Built against the docs but never called: Firefly (no credentials). All 20 images in
`recruitment-creative/` have provenance: 18 as `made` (wording approved by the author), and
`scenes/kids-peeking.png` and `scenes/father-toddler-blanket.png` as backfilled `stock` records.
Both are Pexels photos (17329578, 27175924), matched pixel for pixel against the author's
downloads and picked by the author. On this branch SSO passes 72 of 72 and LAC 42 of 42. **6–8 are superseded
by `planning/imagery-pipeline.md`** (briefs, runs, preview, a review page, verdicts, and the
smoke test); a future agent starts there. 5 waits for real picks: photo templates for studies
belong in `recruitment-creative/designs/`, built around the images chosen.

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
Under the age rule (2026-09-14), anyone "60+" below is shown as someone who looks about
50.

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
- **Which Google Cloud project pays for Vertex image generation?** `.env` now sets
  `GOOGLE_CLOUD_PROJECT`; the spikes ran on it.
- **Must a phone be visible in a stock photo?** Requiring one leaves no Pexels fits for these
  needs.
- **May a photo of someone who looks the part stand in for a country** (Turkish for Moroccan,
  Ethiopian for Kenyan)? Allowing it roughly doubles the fits.
- **A second stock source:** Pixabay (free; the author registers for a key) or Adobe Stock
  (paid; does vlab's Adobe plan include Stock credits?).
- **The author's drawing prompts**, which the drawing work starts from.
- ~~Stock photos or generated images as the default source of people~~: decided, stock for
  photos and generation for drawings (2026-09-14).
