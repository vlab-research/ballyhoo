"""Previews: each candidate in a run rendered into real templates with a sample headline, and checked.

Pure. A run's need folders hold candidates, and its brief names the templates
and the headline to preview them with. This module decides which previews to
render and what they are called, whether a template can take a candidate, and
what checks.yaml records. runs.py renders them and writes the files.
"""
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser

PREVIEWS = "previews"
CHECKS = "checks.yaml"
SLOT = "scene"  # a photo candidate goes into the template's <img id="scene">
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


def slot_src(source, slot=SLOT):
    """The src a template gives its slot, which a preview replaces: None when it has none."""
    tag, src = _element(source, slot)
    return src if tag == "img" else None


def slot_problems(name, source, slot=SLOT):
    """Why a template cannot take a candidate in `slot`; [] when it can."""
    tag, _ = _element(source, slot)
    if tag == "img":
        return []
    found = f"its #{slot} is a <{tag}>" if tag else f"it has no #{slot}"
    return [f'{name}: {found}; candidates go into an <img id="{slot}">']


def plan(needs, found, template_problems):
    """The previews to render. Returns (previews, errors); render nothing when there are errors.

    `found` maps each need that has a candidates file to its candidates, and `template_problems`
    maps each template those needs name to what stops it taking a candidate. Each candidate goes
    into each of its need's templates, in brief order.
    """
    previews, errors, templates = [], [], []
    for need in needs:
        if need.name not in found:
            continue
        if not need.templates:
            errors.append(f"{need.name}: the brief names no preview templates for it")
            continue
        templates += [t for t in need.templates if t not in templates]
        for c in found[need.name]:
            if c.full.startswith(URL):
                errors.append(f"{need.name}/{c.id}: its image is not in the run, only at {c.full}")
            else:
                previews += [Preview(need.name, c.id, c.full, t, SLOT, need.copy) for t in need.templates]
    for t in templates:
        errors += template_problems[t]
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
