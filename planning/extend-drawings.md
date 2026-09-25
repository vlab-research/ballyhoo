# Plan: drawings not cut off at the sides, and extending the ones that are

**Status: open, not planned in detail (found 2026-09-24).** Follows the drawings work in
`planning/imagery-pipeline.md`. Delete this file when it is built and its lessons are in
`docs/design.md`.

## The problem

The author's most common complaint on the Katelyn Romm brief (2026-09-24) was a figure cut
off at the sides: "Needs full width generation (arms not cutoff)". A prompt saying "filling
the frame" draws arms into the image's side edges, and the cut shows as a straight line in
the ad. A figure drawn to the edges also leaves no border to read the key colour from.

Two fixes, both needed.

## 1. Frame the figure inside the picture

The style's `framing` asks for the figure inside the picture with green on both sides, cut
off only by the bottom edge.

- **Done** in `smoke/brief.yaml` (both framing lines), and README § Drawings says so.
- **Done** in the Katelyn Romm brief's styles
  (`projects/katelyn-romm-r01/ads/imagery/brief.yaml`, "whole inside the picture"). Its
  next run shows whether the wording is enough, and how often extending is still needed.

## 2. Extend what the author already likes

Pad the generated image with the key colour to the next aspect ratio Gemini supports (1:1 to
3:2, 3:4 to 1:1) and send it to Gemini with an instruction to continue the shoulders and arms
into the green, add nothing new, and change nothing drawn.

Tried by a hand-written script on five of the author's picks (under $1): three of five came
back right first time; one added a second phone and one a strange arm, and both were right on
a retry with "no second phone, no extra hands or arms".

What building it needs:

- The providers send no image today (`generate_request` sends text only), so Gemini's request
  builder needs an image input.
- An `extend` operation that writes a **new candidate** into a run, whose provenance names the
  candidate it came from and the edit prompt, and which is cut out and mask-checked like any
  drawing. The original is never changed.
- Padding to the target ratio is a pure decision (which ratio, how many pixels each side); the
  shell sends and writes.
- How the agent asks for it (a command naming a candidate, such as `3.4`, or an entry in the
  brief) is open.
