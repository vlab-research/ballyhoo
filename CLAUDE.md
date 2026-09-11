# Working on ballyhoo

ballyhoo renders recruitment ads from a copy file and checks that each headline
fits. Adapted from the conventions in `vlab-research/fly`; the parts about
Kubernetes, Docker and fly's own subagent types are left out because they do not
apply here.

## Default mode: direct and lightweight

Work directly: read the docs, read the code, make the change, run the tests. Use
subagents when a task benefits from parallelism or isolation, not by default.

## Documentation first

**A hard rule.**

| Location | Describes | Contains |
|---|---|---|
| `README.md` | the PARTS | running it, the copy-file format, the template contract, the checks, caching |
| `docs/design.md` | the DESIGN | goals and phases, why things are the way they are, acceptance criteria, lessons, roadmap |
| `planning/` | WORK | plans and findings for work in progress; temporary, delete when done |

**Before any work,** read `README.md` and `docs/design.md` and treat them as ground
truth for intended behaviour. If the code disagrees with them, that is a finding:
say so rather than silently following the code.

**After exploration that surfaces undocumented behaviour,** update the docs as a
separate step, not mixed into the exploration or the code change. Usage and
contracts go in `README.md`; rationale and lessons go in `docs/design.md`.

A template's header comment is its documentation: what it is based on, where its
placements came from, and any deliberate departure from the source design.

## Core principles

### 1. Clarify before you code
- Ask when a request is unclear or broad.
- Write the plan down (in `planning/` for anything multi-step) before implementing.
- Get confirmation on approach and priorities; pivot quickly when the user
  clarifies.

### 2. Incremental progress
- Small, focused changes that can be tested immediately.
- Add complexity a little at a time; keep the suite green between steps.
- Complete one component fully before starting the next.
- Follow the existing patterns and naming.

### 3. Functional core, imperative shell
**The organising rule of this codebase.**

- **All decisions are pure functions**: deterministic, no IO, testable with plain
  data. Parsing and validating the copy file, markup, cache keys and the
  skip/render decision, line grouping and choosing a font size, and every check
  (contrast, collision, text share, blank canvas, canvas size, fit).
- **IO lives in a thin shell**: reading files, globbing templates, driving the
  browser, taking screenshots, writing PNGs. The shell gathers data, calls the
  core, and carries out what the core decided.
- **The browser measures; Python decides.** Code that runs in the page returns raw
  measurements (rectangles, colours, sizes). Logic that could live in Python does
  not live in page JavaScript, where Python tests cannot reach it.
- **Separate "decide" from "do"**: compute the list of failures, the size to use,
  whether to skip, then act on it.
- Prefer data transformations over mutation. Pass numpy arrays and small
  dataclasses, not page handles, into the core.
- **If a function is hard to test, it is doing too much or mixing concerns.** Split
  it rather than reaching for a browser in a unit test.

### 4. Fail fast and loud
- A creative that fails any check is never written, and a stale PNG for it is
  deleted. `out/` only ever holds ads that pass.
- Every failure names design, country, variant and size, and says what was
  measured (font size reached, line count, contrast ratio, overlap in px).
- No silent fallbacks: a missing font, image or country is an error, never a
  substitute. A fallback font or another country's Spanish looks plausible and
  ships.
- Exit non-zero when anything failed, and report every failure, not just the
  first.

## Testing

- **Unit tests cover the pure core**, with no browser, and run in well under a
  second. Every pure function has them. Build inputs with plain data: small numpy
  arrays, rectangles as dicts, YAML as dicts.
- **Integration tests cover the shell**: that the browser, files and core are wired
  together. Mark them `@pytest.mark.browser`.
- **Every bug gets a regression test**, at the lowest layer that can express it.
- **Commit only what a test needs.** Prefer stand-in art drawn at test time with
  the geometry a test depends on (`tests/lac_art.py`); commit real art only when a
  test cannot work without it. The repo is public, so everything committed must be
  cleared to publish: the LAC templates, copy and art are, and the fonts are OFL.
- Assert layout facts (font size, line count, pass/fail and message), not exact
  pixels: Chrome updates shift anti-aliasing and pixel-exact tests fail for nothing.

```
uv run pytest -m "not browser"   # fast inner loop
uv run pytest                    # everything, before committing
uv run pytest --update-expected  # after an intentional layout change
```

## Invariants of the domain

- **Variant names are identifiers.** They become vlab creative names, and renaming
  one deletes a Meta ad set. Variants are a named map, never a list; ballyhoo never
  generates or rewrites names.
- **Text is always set in CSS,** never drawn by an image model.
- **Fonts are pinned as files** via `@font-face`; never rely on system fonts.
- **Paths resolve relative to the file that names them.** There is no library or
  project concept in the code.
- **This repo holds the tool, not the ads.** Copy files, designs, art and renders
  live with the studies that use them; `tests/fixtures/` is the only exception.

## Quality gates

- Zero warnings from the test run.
- All tests pass before a commit.
- Docs updated when behaviour or structure changes.
- Clear commits that say what changed and why.
- Working software over perfect architecture.

## Git

Use a worktree for any change that runs code; docs-only changes can stay on `main`.

```
git worktree add ../ballyhoo-<feature> -b feature/<feature>
cd ../ballyhoo-<feature> && uv sync
# ... work, test, commit ...
git worktree remove ../ballyhoo-<feature>
git branch -d feature/<feature>
```

Each worktree needs its own `uv sync`.

## When things go wrong

- **Tests break:** go back to the last green state, then find the cause and fix
  that, not the symptom.
- **Requirements change mid-work:** stop, clarify with the user, update the plan,
  agree before continuing.
- **Complexity gets out of hand:** step back to the real problem, simplify, and
  break it into smaller pieces.
