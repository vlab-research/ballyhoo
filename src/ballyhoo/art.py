"""Art on disk: images and their provenance sidecars.

The shell for provenance.py. It hashes images and reads and writes sidecars;
provenance.py decides whether a record is valid.
"""
import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

from . import cache, provenance


def file_digest(path):
    # Keyed on mtime and size, so a file rewritten within one process is hashed again.
    stat = Path(path).stat()
    return _digest(str(Path(path).resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=None)
def _digest(path, mtime_ns, size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sidecar(image):
    image = Path(image)
    return image.with_name(provenance.sidecar_name(image.name))


def write_sidecar(image, record):
    """Write a new sidecar. Never replaces one: that would rewrite where an image came from."""
    path = sidecar(image)
    with path.open("x") as f:
        yaml.safe_dump(record, f, sort_keys=False, allow_unicode=True)
    return path


def unsourced_images(template):
    """Every provenance problem among the images a template references, each naming its image."""
    template = Path(template)
    found = []
    for ref in provenance.image_refs(cache.template_refs(template.read_text())):
        image = (template.parent / ref).resolve()
        if not image.is_file():
            continue  # the render hash reports missing files
        record_path = sidecar(image)
        if not record_path.is_file():
            found.append(f"{ref} has no provenance: expected {record_path.name} beside it")
            continue
        record = yaml.safe_load(record_path.read_text())
        found += [f"{ref}: {p}" for p in provenance.problems(record, file_digest(image))]
    return found
