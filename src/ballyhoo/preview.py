"""Previews: each candidate in a run rendered into real templates with a sample headline, and checked.

Pure. A run's need folders hold candidates, and its brief names the templates
and the headline to preview them with. This module decides which previews to
render and what they are called, which slot a candidate fills and whether a
template has it, and what checks.yaml records. runs.py renders them and writes
the files.

A photograph goes into a template's #scene, and a drawing, which reaches a run
as a cut-out, into its #figure, where the collision check already applies.
"""
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser

PREVIEWS = "previews"
CHECKS = "checks.yaml"
SCENE, FIGURE = "scene", "figure"
SLOTS = (SCENE, FIGURE)
KIND = {SCENE: "photo", FIGURE: "drawing"}  # what each slot takes
URL = ("http://", "https://")


@dataclass(frozen=True)
class Preview:
    need: str
    candidate: str  # the candidate's id
    image: str      # its full-size file, relative to the need's folder
    template: str   # <design>/<W>x<H>
    slot: str       # the id of the <img> the candidate goes into
    copy: str

    @property
    def file(self):
        """previews/<id>_<design>_<W>x<H>.png, relative to the need's folder."""
        design, size = self.template.split("/")
        return f"{PREVIEWS}/{self.candidate}_{design}_{size}.png"


@dataclass(frozen=True)
class Outcome:
    preview: Preview
    failures: tuple        # the checks that failed
    summary: str | None    # font size, lines, contrast, text share, scene scale; None when it did not render
    error: str | None = None

    @property
    def status(self):
        return "error" if self.error else "fail" if self.failures else "pass"


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.found.setdefault(attrs["id"], (tag, attrs.get("src")))


def _element(source, slot):
    parser = _Ids()
    parser.feed(source)
    return parser.found.get(slot, (None, None))


def slot_src(source, slot):
    """The src a template gives a slot, which a preview replaces: None when it has no image there."""
    tag, src = _element(source, slot)
    return src if tag == "img" else None


def slot_problems(name, source, slot):
    """Why a template cannot take a candidate in `slot`; [] when it can."""
    tag, _ = _element(source, slot)
    if tag == "img":
        return []
    found = f"its #{slot} is a <{tag}>" if tag else f"it has no #{slot}"
    return [f'{name}: {found}; a {KIND[slot]} goes into an <img id="{slot}">']


def slot_for(candidate):
    """Where a candidate goes: a photograph fills the scene, and a drawing, being a cut-out, the figure."""
    return FIGURE if candidate.cutout else SCENE


def wanted(needs, found):
    """Every (template, slot) a run's previews may need, for the shell to check each template for.

    Both slots of every template, not only the ones this run's candidates fill: a template that
    takes neither previews nothing, whatever was sourced, and that is worth saying.
    """
    pairs = [(t, slot) for need in needs if need.name in found for t in need.templates for slot in SLOTS]
    return list(dict.fromkeys(pairs))


def plan(needs, found, template_problems):
    """The previews to render. Returns (previews, errors); render nothing when there are errors.

    `found` maps each need that has a candidates file to its candidates, and `template_problems` what
    stops each (template, slot) pair taking one, as `wanted` lists them. A candidate goes into every
    one of its need's templates that takes its kind, in brief order. A template that takes the other
    kind is passed over, since a photo template cannot show a drawing; a kind that none of a need's
    templates takes is an error naming what stops each of them.
    """
    previews, errors, missing = [], [], []
    for need in needs:
        if need.name not in found:
            continue
        if not need.templates:
            errors.append(f"{need.name}: the brief names no preview templates for it")
            continue
        for c in found[need.name]:
            if c.image.startswith(URL):
                errors.append(f"{need.name}/{c.id}: its image is not in the run, only at {c.image}")
                continue
            slot = slot_for(c)
            usable = [t for t in need.templates if not template_problems[(t, slot)]]
            if not usable:
                missing += [p for t in need.templates for p in template_problems[(t, slot)]]
            previews += [Preview(need.name, c.id, c.image, t, slot, need.copy) for t in usable]
    errors += [p for p in dict.fromkeys(missing) if p not in errors]
    clashes = Counter((p.need, p.file) for p in previews)
    errors += [f"{need}: two previews would both be {file}" for (need, file), n in clashes.items() if n > 1]
    return previews, errors


def checks_data(need, outcomes, ballyhoo, previewed):
    """One need's checks.yaml: per candidate, per template, pass or what failed.

    A candidate passes when every one of its previews does. `ballyhoo` is the digest of the code
    that previewed, and `previewed` when.
    """
    candidates = {}
    for o in outcomes:
        entry = candidates.setdefault(o.preview.candidate, {"pass": True, "previews": {}})
        record = {"status": o.status}
        if o.status != "error":
            record["file"] = o.preview.file
        if o.summary:
            record["summary"] = o.summary
        if o.failures or o.error:
            record["failures"] = [o.error] if o.error else list(o.failures)
        entry["previews"][o.preview.template] = record
        entry["pass"] = entry["pass"] and o.status == "pass"
    passed = sum(e["pass"] for e in candidates.values())
    return {"copy": need.copy, "templates": list(need.templates), "previewed": previewed, "ballyhoo": ballyhoo,
            "summary": {"candidates": len(candidates), "pass": passed, "fail": len(candidates) - passed},
            "candidates": candidates}
