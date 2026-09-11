# Plan: functional core, imperative shell

Goal: `render.py` follows CLAUDE.md §3. Every decision is a pure function with unit
tests; the browser only measures and screenshots. Delete this file when done.

## Module map

| Module | Pure | Decides |
|---|---|---|
| `copyfile.py` | yes | which creatives exist: validating a loaded copy file, expanding it into jobs, filtering, `*emphasis*` markup |
| `cache.py` | yes | what a render depends on: template references, the inputs digest, render-or-skip |
| `fit.py` | yes | the font size: template settings, line boxes, grouping fragments into lines, containment, choosing the largest size that fits |
| `checks.py` | yes | whether a render passes: contrast, collision (with speck removal), text share, blank, canvas, fit messages |
| `render.py` | no | the shell: reads files, drives the browser, writes PNGs, calls the core |

The page stops deciding: one call returns the raw text rectangles at every candidate
size, Python chooses, and the page is set to that size before screenshots.

## Steps

1. Pure modules and unit tests. Unit suite green.
2. Rewire `render.py` onto the core. Whole suite green; the 42 LAC renders are
   pixel-identical to the pre-refactor renders.
3. Realistic fixtures: the seven real templates with generated art and the real
   fonts; a layout snapshot (font size and line count per creative); one regression
   test per bug found while building the LAC ads.
4. Docs: README (module layout, tests), design.md (rendering flow), CLAUDE.md
   (remove "Work in flight"). Delete this plan.
