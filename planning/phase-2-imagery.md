# Plan: Phase 2, sourced imagery (stock photos and generated figures)

**Status: plan, 2026-09-11. Nothing is built.** The rationale is in `docs/design.md`
§ *Phase 2 sketch*; this file is the work. Delete it when Phase 2 is done and its
lessons are in the design doc.

## Why, and the first user

The first campaign to need it recruits adults in Kenya and Morocco, stratified by
age (18–29 up to 60+), gender, region and urban/rural. Round 1 (rendered
2026-09-11) used the partner's illustrated art: every person in it reads as 20s–30s
and urban, and Morocco's only woman is veiled. The authors want **older people and
families**, and the design needs **rural settings**. Round 2 of that campaign is the
acceptance test for this phase.

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | `ballyhoo stock search` queries Pexels and Unsplash and returns results in one normalised form, with provenance, without downloading full-size files |
| 2 | Results render as a numbered contact sheet that an agent can read and cite by number |
| 3 | A shortlist becomes a sheet or review page for a human pick; nothing enters the art library without one |
| 4 | `ballyhoo stock fetch <provider>:<id>` downloads the full-size file, writes a provenance sidecar, and does whatever the provider's terms require on use (Unsplash: call the download endpoint) |
| 5 | Rendering a template whose art has no provenance sidecar fails, naming the file (decide: all art, or only art added after Phase 2) |
| 6 | The pure core has unit tests with synthetic JSON fixtures: request building, per-provider normalisation, dedupe, provenance record, attribution text |
| 7 | API keys come only from the environment (`PEXELS_API_KEY`, `UNSPLASH_ACCESS_KEY`). A missing key is an error naming the variable, never a silently skipped provider |
| 8 | A generated figure goes through the same pick and provenance steps (model, prompt, seed in place of photographer and URL) |

## Steps

1. **Keys.** Sign up for Pexels and Unsplash API keys and put them in the environment.
   *Author.* Unsplash starts on a demo tier (about 50 requests an hour) and needs an
   application for production; Pexels allows about 200 an hour. Re-check both before building.
2. **Spike, no repo code.** Run plain `curl` searches for the round-2 briefs below and
   look at what exists. The question is whether stock photos can show everyday older,
   rural Kenyans and Moroccans at all, or whether generation has to carry it. Write the
   findings here.
3. **Read the terms** in force (Unsplash API guidelines and licence, Pexels licence and
   API terms) and write the constraints that bind into `docs/design.md`.
4. **Core, `stock.py` (pure).** Request builders per provider; response normalisers into
   a `Photo` dataclass (provider, id, page_url, photographer, photographer_url, licence,
   width, height, urls by size, alt text, provider extras such as Unsplash's
   `download_location`); dedupe; attribution string; provenance record. Tests use small
   synthetic JSON, not recorded real responses and not real photos (public repo).
5. **Shell.** HTTP client, thumbnail download, contact sheet (Pillow), `fetch` writing
   `<file>.provenance.yaml` beside the image.
6. **CLI.** `ballyhoo stock search "<query>" --provider pexels,unsplash --n 40 --out <dir>`
   and `ballyhoo stock fetch pexels:12345 --to <art dir>/scenes/`.
7. **Photo templates.** At least two 1080×1080 layouts built for photos: full-bleed photo
   under a band, and photo on one side with copy on the other. The collision and contrast
   checks apply unchanged.
8. **Generated figures.** `generate_figure(prompt, seed, size) -> RGBA PNG` behind a
   provider switch, with the same sidecar.
9. **Review.** A picker: extend the study's review page with a shortlist section, or add a
   `ballyhoo sheet` command (also proposed by the LAC creative review).
10. **Docs.** README: the commands and the provenance format. Design doc: lessons.

## Round-2 briefs (the first real queries)

People using a phone in an everyday setting. Not tourist imagery, not poverty imagery.

- **Kenya:** woman 60+; man 60+; three-generation family; farmer or market-centre trader
  in a rural area; man and woman 45–59.
- **Morocco:** woman 60+, veiled and unveiled; man 60+; family at home; rural setting (a
  douar, the Atlas, the south); man and woman 45–59; an unveiled younger woman, which
  round 1 lacks.

## Constraints to carry into the design

- **No model releases** on either stock site: never imply that a pictured person endorses
  the study, and say in the IRB package that the imagery is licensed stock or generated.
- **Styles mix badly.** Round 1 is illustrated; photos next to it read as a different
  campaign. Either photo designs form their own family, or generated figures match the
  illustrated style. The adaptive and Zhang arms must still get identical creative.
- **Photos are scenes, not cut-outs,** until a background-removal step with a mask check
  exists.

## Open decisions

- Stock photos or generated figures as the default source of people.
- Whether a missing provenance sidecar fails every render or only newly added art.
- Which background-removal tool, if photo cut-outs are wanted at all.
- Where picks are made: the study's review page, or a `ballyhoo sheet` output.
