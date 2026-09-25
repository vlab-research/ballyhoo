# Plan: one review page for a brief, alongside an agent thread

**Status: a plan, not built (2026-09-24).** It changes step 3 of
`planning/imagery-pipeline.md` (verdicts and review). Delete this file when it is built and
its lessons are in `docs/design.md`.

## Start here

- **Code:** branch `feature/imagery`, worktree `../ballyhoo-imagery`. Read `CLAUDE.md`,
  `README.md` § Review, `docs/design.md` § Judging imagery and `planning/imagery-pipeline.md`
  § 3 first. The server is `src/ballyhoo/review_server.py`; the page is
  `src/ballyhoo/review.html`, its data `review.py`, its files `runs.py`, the verdict format
  `verdicts.py`.
- **A real brief to try it on:** `projects/katelyn-romm-r01/ads/imagery/brief.yaml` and its
  four runs in `runs/` (2026-09-24-1 to -4), made in one afternoon of the loop below.

## What the author wants, and what they do not

The author, 2026-09-24:

> The goal of this is not to replace an AI agent. It's just to provide a visual to go
> alongside a thread with an agent.

> Why does every batch need a new server? … If we have to run a new server every time, it's
> basically like generating a static file.

The loop is a conversation. The author tells an agent what they want; the agent edits the
brief, runs `source` and `preview`, and says "have a look". The author looks, rates, and
answers in the thread; the agent reads the ratings and goes round again. The page is where
the author *sees* and *marks* the images. The agent does everything else.

So this builds a page that stays up for the whole conversation and shows each new round as
the agent makes it. It does **not** build generation, prompt editing or brief write-back in
the page: the author said "I don't think we need generate again. We'll do that here through
the agent prompt."

## What went wrong on 2026-09-24

One afternoon of that loop on the Katelyn Romm brief made four runs and needed four
servers:

1. **A server per run.** `ballyhoo review RUN` serves one run folder. Every new round was a
   new command, a new port and a new URL to send, and the author had three tabs open for one
   brief.
2. **Ratings sat unsaved.** The author rated two runs and said "I voted anyways", but
   neither run had a `verdicts.yaml`: Save had not been pressed ("Oops I saved now"). The
   page holds every mark in the browser until Save, and nothing on it says that marks are
   unsaved. The agent, reading the disk, saw no ratings and asked for letters in the thread.
3. **Nobody could name an image.** The agent labelled candidates A to P on contact sheets it
   built by hand, because the page has no short name for a candidate. The author and the
   agent need one name for the same image, in the thread and on the page.
4. **Previews stretched drawings.** Fixed on the branch (not yet committed): `SWAP_JS` in
   `render.py` gives a swapped-in `#figure` `object-fit: contain`, standing on the box's
   bottom edge. Commit it with this work, with a browser test that a 3:4 cut-out in a
   square `#figure` keeps its shape.
5. **Cut-outs were see-through.** Also fixed on the branch, not yet committed, with a unit
   test: `cut_out` ramped alpha by colour distance from the key everywhere, so pale or
   greenish paint inside a figure came out part transparent (a white man's green jacket took
   the colour of whatever it was placed on). The ramp now reaches only `RAMP` px from pixels
   that are the ground. All 39 drawings in the Katelyn Romm runs were re-cut with it: every
   drawing the author kept went from up to 46% see-through to under 1%. Two failures it does
   not fix: a figure that fills the frame to its edges (no border to read the key from) and a
   pale, washed-out ground. `mask_problems` now reports kept green paint as "still the key's
   green"; its thresholds were calibrated on the old key and want revisiting.

## What to build

### One server per brief, for as long as the thread lasts

- `ballyhoo review BRIEF_OR_RUNS_DIR` serves every run of a brief: the `runs/` next to the
  brief, or a runs directory given directly. `ballyhoo review RUN` keeps working and shows
  that run alone.
- **The page is read from disk on every request, as now, across all runs.** A run the agent
  makes while the server is up appears without a restart. The server holds no state.
- **The page notices new rounds.** A small JSON endpoint (`GET /state`: each run's name and
  the newest modification time under it) that the page polls every few seconds; when it
  changes, the page offers "New round: show it" rather than reloading under the author's
  cursor. Previews write their files as they finish, so a run is shown only once its
  `checks.yaml` files exist (preview has finished), or it is marked "previewing".
- Keep the security model exactly: 127.0.0.1 only, the Host check, JSON-only posts, and
  files served only from inside the runs directory.

### Newest round first, grouped by need

- Runs newest first, each headed with its date-number, its needs, and (from `brief.yaml` in
  the run) what changed from the run before: the prompt diff per need, in one or two lines.
  That is what the author compares round to round.
- Within a run, candidates by need, as now: preview renders large (the ad is what is judged),
  the cut-out on a plain ground beside it, then prompt, model, seed, checks and agent hint
  folded away.
- A filter bar: all, unrated, keep, and hide dropped.

### A short name for every candidate

- `<run number>.<n>`, e.g. **3.4** for the fourth candidate of today's third run, with the
  run's date shown in its heading. It is stable (`n` never changes), short enough to say in
  the thread, and the agent can resolve it from `manifest.yaml` and `candidates.yaml`
  without a lookup table. Show it large on every card, and accept it in the CLI:
  `ballyhoo keep RUNS 3.4 --to …`.
- Where runs span days, the number resets per day; a name is then `2026-09-24-3.4`, and the
  page shows the short form only where it is unambiguous.

### Every mark saves at once

- Replace the Save button with a save per change: each keep, maybe, drop, issue or note
  posts one entry (`POST /verdicts` with run, need, candidate and the entry), and the server
  merges it into that run's `verdicts.yaml` atomically (`write_atomically` exists).
- The name is asked once, on first mark, and remembered by the page (local storage); every
  later post carries it. A post from a second name to a run already rated by the first is
  refused with a message: one person rates a run, as now.
- A refused post shows its error on that card, in place, at once. Nothing is lost silently.
- Keep whole-file validation (`verdicts.parse`) on the merged result before writing.

### Notes the agent can read

- A free-text note per need per run ("less pensive", "none of these look 50"), saved in
  `verdicts.yaml` beside the per-candidate verdicts. Format: `needs.<need>.note` next to the
  candidate map would mix a string into a map of candidates, so add a top-level
  `notes: {<need>: text}` instead, and bump nothing else.
- `ballyhoo review RUNS --summary` summarises every run, newest first, notes included, so an
  agent reads one command's output to know where the author is.

## Found in the same session, for a separate plan: extending a cut-off drawing

The author's most common complaint on 2026-09-24 was a figure cut off at the sides ("Needs
full width generation (arms not cutoff)"): a prompt saying "filling the frame" draws arms
into the image edge, and the cut shows as a straight line in the ad. Two fixes, both needed:

- **Prompt:** frame the figures inside the picture with green on both sides, cut off only by
  the bottom edge. Not yet in the smoke brief or the Katelyn Romm brief's styles.
- **Extend what the author already likes.** Pad the generated image with the key colour to
  the next supported aspect ratio (1:1 to 3:2, 3:4 to 1:1) and send it to Gemini with an
  instruction to continue the shoulders and arms into the green, "add nothing new", and
  change nothing drawn. Done by hand-written script for five picks (under $1): three of five
  came back right first time; one added a second phone and one a strange arm, and both were
  right on a retry with "no second phone, no extra hands or arms". The provider has no
  image input today (`generate_request` sends text only), so this wants an `extend`
  operation that writes a new candidate whose provenance names the candidate it came from
  and the edit prompt.

## Not in scope

- Generating, regenerating or editing prompts from the page (the agent does this).
- Keeping from the page. `keep` stays a command the agent runs from the author's verdicts.
- Reaching the page from another device. The server listens on 127.0.0.1, so an author
  following the thread on a phone cannot open it. `imagery-pipeline.md` already expects "a
  published page later"; that is a separate plan, with its own access question.

## Steps

1. **Commit the two fixes above**, each with its test, before the server work.
2. **Serve a runs directory.** `review` takes a brief or runs directory; the page lists all
   runs newest first; `GET /state`; the page's new-round prompt. Tests: an integration test
   that starts the server on an empty runs directory, writes a run, and sees it in
   `/state` and on the page (no browser).
3. **Short names.** In the page data and on the cards; `keep` accepts them.
4. **Save per mark.** The single-entry post, the merge, the name kept by the page, errors
   shown in place. Tests: merge and refusal as unit tests on the pure core; the post through
   the real server.
5. **Notes and the cross-run summary.**
6. **Docs.** `README.md` § Review for usage; `docs/design.md` § Judging imagery for why the
   server lives for a thread and why the page never generates.

## Open questions for the author

- Should the page show only the latest round by default, with older rounds folded, or all
  rounds open?
- Is a per-need note enough, or do they want a note on the run as a whole too?
