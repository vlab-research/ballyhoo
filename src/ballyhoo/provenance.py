"""Provenance: where each image came from, and on what terms we use it.

Pure. Every image a template references has a sidecar, <image>.provenance.yaml.
The shell reads the sidecar and hashes the image; this module decides whether
the record is complete and belongs to that file. See docs/design.md.
"""
import datetime
import re

SUFFIX = ".provenance.yaml"
IMAGE = re.compile(r"\.(png|jpe?g|webp|gif|avif|svg)$", re.IGNORECASE)

REQUIRED = {
    "made": ("by", "rights"),
    "stock": ("provider", "id", "page_url", "creator", "licence", "licence_url", "query", "fetched", "picked"),
    "generated": ("provider", "model", "prompt", "seed", "generated", "picked"),
}
DATES = ("fetched", "generated")


def image_refs(refs):
    """The references that are images, and so need provenance. Fonts and CSS do not."""
    return [r for r in refs if IMAGE.search(r)]


def sidecar_name(image_name):
    return image_name + SUFFIX


def made(sha256, by, rights):
    """A record for an image a person made: a partner's art, or a test's stand-in."""
    return {"source": "made", "sha256": sha256, "by": by, "rights": rights}


def _is_date(value):
    if isinstance(value, datetime.date):
        return True
    try:
        datetime.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def problems(record, sha256):
    """What is wrong with a loaded sidecar for the file whose digest is `sha256`; [] if nothing."""
    if not isinstance(record, dict):
        return ["provenance must be a map"]
    source = record.get("source")
    if source not in REQUIRED:
        return [f"provenance source must be one of {', '.join(REQUIRED)}, not {source!r}"]
    found = []
    missing = [k for k in ("sha256", *REQUIRED[source]) if _blank(record.get(k))]
    if missing:
        found.append(f"provenance is missing {', '.join(missing)}")
    if not _blank(record.get("sha256")) and record["sha256"] != sha256:
        found.append("provenance sha256 is not this file's: the image changed after its provenance was written")
    for key in DATES:
        if key in REQUIRED[source] and not _blank(record.get(key)) and not _is_date(record[key]):
            found.append(f"provenance {key} must be a date")
    if "seed" in REQUIRED[source] and not _blank(record.get("seed")) and (
            isinstance(record["seed"], bool) or not isinstance(record["seed"], int)):
        found.append("provenance seed must be a whole number")
    picked = record.get("picked")
    if "picked" in REQUIRED[source] and picked is not None:
        if not isinstance(picked, dict) or _blank(picked.get("by")) or not _is_date(picked.get("on", "")):
            found.append("provenance picked needs by (the person who picked it) and on (a date)")
    return found
