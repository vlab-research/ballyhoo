"""Fitting the headline: which font size to use.

Pure. The page measures the text at every candidate size; this module turns
those measurements into line boxes and lines and picks the largest size at which
the text sits inside #headline in at most data-max-lines lines.
"""
import math
import re
from dataclasses import dataclass

TOLERANCE = 0.5  # px; layout rounding


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def cy(self):
        return self.y + self.h / 2

    def union(self, other):
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Rect(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)

    @classmethod
    def of(cls, d):
        return cls(float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))


@dataclass(frozen=True)
class Fragment:
    """A run of text on one line, as its line box, with its CSS colour."""
    rect: Rect
    color: str


@dataclass(frozen=True)
class Measurement:
    size: float
    fragments: tuple  # of Fragment
    boxes: tuple      # of Rect: per-line boxes an inline copy element draws (padding, background)
    box: Rect         # #headline, which everything must fit inside


@dataclass(frozen=True)
class Settings:
    start: float
    min_size: float
    max_lines: int
    min_contrast: float = 3.0
    collide_margin: float = 4.0


@dataclass(frozen=True)
class Fit:
    ok: bool
    size: float
    lines: tuple      # of Rect
    fragments: tuple  # of Fragment
    overflows: bool


def _number(attrs, key, errors, *, default=None, integer=False, allow_zero=False):
    name = "data-" + re.sub(r"[A-Z]", lambda m: "-" + m.group().lower(), key)
    raw = attrs.get(key)
    if raw is None or raw == "":
        if default is None:
            errors.append(f"#headline needs {name}")
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = math.nan
    if not (math.isfinite(value) and (value >= 0 if allow_zero else value > 0)
            and (value.is_integer() or not integer)):
        errors.append(f"{name}={raw!r} must be a {'non-negative' if allow_zero else 'positive'} "
                      f"{'whole number' if integer else 'number'}")
        return None
    return int(value) if integer else value


def parse_settings(attrs, start):
    """Fit settings from #headline's dataset (minSize, maxLines, ...) and CSS font size."""
    errors = []
    min_size = _number(attrs, "minSize", errors)
    max_lines = _number(attrs, "maxLines", errors, integer=True)
    min_contrast = _number(attrs, "minContrast", errors, default=3.0)
    margin = _number(attrs, "collideMargin", errors, default=4.0, allow_zero=True)
    if min_size is not None and start < min_size:
        errors.append(f"#headline font-size {start:g}px is below data-min-size {min_size:g}")
    if errors:
        return None, errors
    return Settings(start, min_size, max_lines, min_contrast, margin), []


def candidate_sizes(settings):
    """Whole pixel sizes from the template's size down to the floor, largest first."""
    return list(range(math.floor(settings.start), math.ceil(settings.min_size) - 1, -1))


def line_box(content, line_height):
    """The line box around a text rect.

    Browsers report text rects as the font's content area, which overhangs the line
    when line-height is tight (Manrope at line-height 1 overhangs by ~18%). The
    glyphs sit in the line box, centred on the same point.
    """
    if line_height is None or not math.isfinite(line_height):
        return content
    return Rect(content.x, content.cy - line_height / 2, content.w, line_height)


def measurement_from_page(raw):
    return Measurement(
        size=raw["size"],
        fragments=tuple(Fragment(line_box(Rect.of(f), f.get("lineHeight")), f["color"]) for f in raw["fragments"]),
        boxes=tuple(Rect.of(b) for b in raw["boxes"]),
        box=Rect.of(raw["box"]),
    )


def group_lines(rects):
    """Merge rects that share a line (same vertical centre, within half the shorter height)."""
    lines = []  # (union rect, centre of the first rect on the line)
    for r in sorted(rects, key=lambda r: r.y):
        for i, (line, cy) in enumerate(lines):
            if abs(cy - r.cy) < min(line.h, r.h) / 2:
                lines[i] = (line.union(r), cy)
                break
        else:
            lines.append((r, r.cy))
    return [line for line, _ in lines]


def inside(rects, box, tolerance=TOLERANCE):
    return bool(rects) and all(
        r.x >= box.x - tolerance and r.y >= box.y - tolerance
        and r.right <= box.right + tolerance and r.bottom <= box.bottom + tolerance
        for r in rects)


def choose(measurements, max_lines):
    """The largest size that fits, or the smallest measured size marked not ok."""
    if not measurements:
        raise ValueError("no measurements to choose a size from")
    for m in sorted(measurements, key=lambda m: m.size, reverse=True):
        rects = [f.rect for f in m.fragments]
        lines = group_lines(rects)
        fits = inside(rects + list(m.boxes), m.box)
        if fits and len(lines) <= max_lines:
            return Fit(True, m.size, tuple(lines), m.fragments, False)
    return Fit(False, m.size, tuple(lines), m.fragments, not fits)
