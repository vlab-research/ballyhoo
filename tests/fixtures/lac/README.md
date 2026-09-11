# LAC fixture

The seven designs built for the LAC Healthy Diets recruitment ads (copied from
`projects/recruitment-creative/designs/` on 2026-09-11), their fonts, and the
headline copy written for Argentina and Honduras. `expected.yaml` records the
font size and line count each creative fits at.

The art is not here. It is licensed, but no test needs it: `tests/lac_art.py`
draws stand-ins into a temporary copy at test time. They have the real files' aspect ratios and, where a regression
test depends on it, the real geometry on the page (where a head or hairline
starts, the speck in man-scarf's mask).

Fonts are under the SIL Open Font License; see `library/fonts/OFL-*.txt`.
