"""Candidates: images a search found or a generator made, waiting for a person to pick.

Pure. A search or a generation fills a directory with candidates.yaml, a
thumbnail per candidate and numbered contact sheets. The study's review page
shows them and records picks; `ballyhoo keep` copies a picked candidate into the
art library with its provenance. This module decides what those files hold and
what keeping a candidate writes.
"""
import math
import re
from dataclasses import dataclass

from . import provenance

FILE = "candidates.yaml"
THUMBS = "thumbs"
GENERATED = "generated"
ORIGINALS = "originals"
ROTATED = (5, 6, 7, 8)  # EXIF orientations that turn an image a quarter, so its width and height swap
THUMB_EDGE = 640   # px, long edge: enough to judge on a review page
SHEET_COLUMNS = 5
SHEET_ROWS = 4
SHEET_CELL = 320   # px square per candidate on a contact sheet
ID = re.compile(r"^[a-z0-9]+-[A-Za-z0-9_-]+$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FIELDS = ("id", "width", "height", "full", "preview", "provenance")


@dataclass(frozen=True)
class Candidate:
    id: str           # <provider>-<the provider's id>: what picks refer to, the same in every search
    width: int
    height: int
    full: str         # the full-size image: a URL, or a path relative to the candidates directory
    preview: str      # a smaller image to thumbnail: a URL, or a path relative to the candidates directory
    provenance: dict  # the sidecar, less what keeping adds: sha256, picked, and for stock, fetched

    @property
    def thumb(self):
        return f"{THUMBS}/{self.id}.jpg"

    @property
    def query(self):
        """The search that found a stock candidate first; None for a generated one."""
        return self.provenance.get("query")


@dataclass(frozen=True)
class Keep:
    candidate: Candidate
    name: str  # file name in the art directory, without extension: that comes from the bytes delivered


def generated_candidate(provider, model, prompt, seed, sha256, ext, width, height, today):
    """A generated image, named by its content, so generating the same bytes twice yields one candidate."""
    id_ = f"{provider}-{sha256[:12]}"
    path = f"{GENERATED}/{id_}{ext}"
    return Candidate(id_, width, height, path, path, {"source": "generated", "provider": provider, "model": model,
                                                      "prompt": prompt, "seed": seed, "generated": today})


def with_original(candidate, ext, width, height):
    """A stock candidate once its full-size file is downloaded into originals/.

    `full` and `preview` name that file and the size is the file's own, so what is previewed,
    rated and kept is exactly those bytes. The record keeps the URL they were fetched from.
    """
    path = f"{ORIGINALS}/{candidate.id}{ext}"
    return Candidate(candidate.id, width, height, path, path,
                     {**candidate.provenance, "download_url": candidate.full})


def displayed_size(width, height, orientation):
    """An image's size as shown, after its EXIF orientation."""
    return (height, width) if orientation in ROTATED else (width, height)


def merge(existing, found):
    """The existing candidates in order, then those not seen before, so a number never changes."""
    ids = {c.id for c in existing}
    merged = list(existing)
    for c in found:
        if c.id not in ids:
            ids.add(c.id)
            merged.append(c)
    return merged


def dump(candidates):
    """candidates.yaml as data. `n` is the number on the contact sheet; `query`, beside the id, repeats the
    record's so a person comparing queries can read it off at a glance."""
    return {"candidates": [{"n": n, "id": c.id, **({"query": c.query} if c.query else {}),
                            **{f: getattr(c, f) for f in FIELDS if f != "id"}, "thumb": c.thumb}
                           for n, c in enumerate(candidates, 1)]}


def load(data):
    """Candidates from a loaded candidates.yaml. Returns (candidates, errors)."""
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return [], ["expected a map holding a list of candidates"]
    found, errors = [], []
    for n, entry in enumerate(data["candidates"], 1):
        missing = [f for f in FIELDS if not isinstance(entry, dict) or entry.get(f) in (None, "")]
        if missing:
            errors.append(f"candidate {n}: missing {', '.join(missing)}")
        elif not ID.match(str(entry["id"])):
            errors.append(f"candidate {n}: id {entry['id']!r} is not <provider>-<id>")
        else:
            found.append(Candidate(str(entry["id"]), int(entry["width"]), int(entry["height"]),
                                   str(entry["full"]), str(entry["preview"]), dict(entry["provenance"])))
    return found, errors


def parse_picks(args):
    """`<id>` or `<id>=<file name>` arguments. Returns ([(id, name or None)], errors)."""
    picks, errors = [], []
    for arg in args:
        id_, eq, name = arg.partition("=")
        if not ID.match(id_) or (eq and not name):
            errors.append(f"{arg}: expected <candidate id> or <candidate id>=<file name>")
        else:
            picks.append((id_, name or None))
    return picks, errors


def plan_keep(candidates, picks, taken):
    """What keeping `picks` writes. `taken` holds the names already used in the art directory.

    Returns (keeps, errors); one bad pick does not stop the others.
    """
    by_id = {c.id: c for c in candidates}
    keeps, errors, used = [], [], set(taken)
    for id_, name in picks:
        name = name or id_.lower()
        if id_ not in by_id:
            errors.append(f"{id_}: not among these candidates")
        elif not NAME.match(name):
            errors.append(f"{id_}: file name {name!r} must be a lowercase slug")
        elif name in used:
            errors.append(f"{id_}: {name} is already taken in the art directory")
        else:
            used.add(name)
            keeps.append(Keep(by_id[id_], name))
    return keeps, errors


def extension(data):
    """The kept file's extension, from the bytes delivered. They are kept as they are, never converted."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("not a JPEG, PNG or WebP image")


def kept_record(candidate, sha256, picked_by, today):
    """The sidecar for a kept candidate. Returns (record, problems); write it only without problems."""
    record = {"source": candidate.provenance.get("source"), "sha256": sha256,
              **{k: v for k, v in candidate.provenance.items() if k != "source"},
              "picked": {"by": picked_by, "on": today}}
    if record["source"] == "stock":
        record["fetched"] = today
    return record, provenance.problems(record, sha256)


def sheets(count, per_sheet=SHEET_COLUMNS * SHEET_ROWS):
    """The candidate indexes on each contact sheet."""
    return [range(start, min(start + per_sheet, count)) for start in range(0, count, per_sheet)]


def sheet_size(count, columns=SHEET_COLUMNS, cell=SHEET_CELL):
    return columns * cell, math.ceil(count / columns) * cell


def cell_origin(i, columns=SHEET_COLUMNS, cell=SHEET_CELL):
    return (i % columns) * cell, (i // columns) * cell


def fit(width, height, edge):
    """The size that fits a square of side `edge`, keeping the aspect ratio; never enlarged."""
    scale = min(1, edge / width, edge / height)
    return max(1, round(width * scale)), max(1, round(height * scale))
