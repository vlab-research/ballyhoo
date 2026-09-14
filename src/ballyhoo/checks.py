"""Whether a rendered creative passes.

Pure. Screenshots arrive as numpy arrays (as rendered; with the text made
transparent; with the text forced black, and forced white; and the figure alone),
layout as rects from fit.py, and slot images as the page measured them. Out come
failure messages, every failing check reported, not just the first.
"""
import math
import re
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .fit import Rect

MAX_TEXT_SHARE = 0.20  # text pixels as a share of the canvas; more hurts Meta delivery
TEXT_DIFF = 48         # a pixel is glyph if black and white text differ there by more than this
MIN_GLYPH_PX = 20      # fragments with fewer text pixels (a full stop) do not decide contrast
ALPHA_MIN = 40         # figure pixels fainter than this are not the figure
SPECK_PX = 500         # detached mask bits smaller than this are background-removal leftovers
BLANK_SHARE = 0.99     # one colour covering more than this means a layer failed to load
MAX_UPSCALE = 1.25     # a photo drawn larger than this, in either direction, looks soft


@dataclass(frozen=True)
class SlotImage:
    """An <img> in a slot (#scene), as the page drew it."""
    slot: str
    box: Rect
    natural: tuple    # (width, height) of the decoded image
    object_fit: str
    src: str          # the URL the element shows, which srcset or <picture> can make differ from src


def slot_images(raw):
    """Slot images from the page's measurements. Returns (images, errors); a slot must be an <img>."""
    images, errors = [], []
    for r in raw:
        if r["tag"] != "img":
            errors.append(f"#{r['slot']} must be an <img>, not a <{r['tag']}>")
        else:
            images.append(SlotImage(r["slot"], Rect.of(r["box"]), (r["naturalWidth"], r["naturalHeight"]),
                                    r["objectFit"], r["src"]))
    return images, errors


def drawn_scale(image):
    """How many times its natural size an image is drawn, (across, down), under its CSS object-fit."""
    across, down = image.box.w / image.natural[0], image.box.h / image.natural[1]
    fits = {"fill": (across, down), "cover": (max(across, down),) * 2, "contain": (min(across, down),) * 2,
            "none": (1.0, 1.0), "scale-down": (min(1.0, across, down),) * 2}
    if image.object_fit not in fits:
        raise ValueError(f"#{image.slot}: unsupported object-fit {image.object_fit!r}")
    return fits[image.object_fit]


def upscale_failures(image, max_scale=MAX_UPSCALE):
    across, down = drawn_scale(image)
    if max(across, down) <= max_scale:
        return []
    scale = f"{across:.2f}x" if across == down else f"{across:.2f}x across and {down:.2f}x down"
    (w, h), box = image.natural, image.box
    return [f"#{image.slot} is upscaled {scale} (max {max_scale:g}x): a {w}x{h} image in a {box.w:g}x{box.h:g} "
            f"box with object-fit: {image.object_fit}"]


def swap_failures(images, slot, src):
    """Whether the slot shows the image put into it."""
    shown = next((i.src for i in images if i.slot == slot), None)
    if shown == src:
        return []
    return [f"#{slot} shows {shown}, not the image put into it ({src})"]


def luminance(rgb):
    c = np.asarray(rgb, float)[:3] / 255
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(c @ [0.2126, 0.7152, 0.0722])


def contrast_ratio(a, b):
    """WCAG contrast ratio, 1 to 21."""
    hi, lo = sorted([luminance(a), luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def parse_css_color(css):
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*[\d.]+%?)?\s*\)", css.strip())
    if not m:
        raise ValueError(f"unsupported CSS colour {css!r}; expected rgb() or rgba()")
    return tuple(float(v) for v in m.groups())


def region(rect, shape, grow=0.0):
    """Array slices for a rect, grown by `grow` px and clipped to the image."""
    H, W = shape[:2]
    x0, y0 = max(0, math.floor(rect.x - grow)), max(0, math.floor(rect.y - grow))
    x1, y1 = min(W, math.ceil(rect.right + grow)), min(H, math.ceil(rect.bottom + grow))
    return slice(y0, max(y0, y1)), slice(x0, max(x0, x1))


def glyph_pixels(black_text, white_text):
    """Where the glyphs are, whatever colour the text and its background.

    Comparing the render with and without its text misses text that is close to
    its background colour, which is exactly the text the contrast check is for.
    Forcing the text black and then white always changes glyph pixels.
    """
    return np.abs(black_text[..., :3].astype(int) - white_text[..., :3].astype(int)).max(axis=2) > TEXT_DIFF


def worst_contrast(fragments, glyphs, notext):
    """Lowest contrast between a fragment's colour and what lies behind its glyphs, or None."""
    worst = None
    for f in fragments:
        ys, xs = region(f.rect, glyphs.shape)
        under = glyphs[ys, xs]
        if under.sum() < MIN_GLYPH_PX:
            continue
        behind = notext[ys, xs, :3][under].mean(axis=0)
        ratio = contrast_ratio(parse_css_color(f.color), behind)
        worst = ratio if worst is None else min(worst, ratio)
    return worst


def figure_mask(alpha, speck_px=None):
    """The figure's solid pixels, without detached specks."""
    labels, _ = ndimage.label(alpha > ALPHA_MIN)
    keep = np.bincount(labels.ravel()) >= (SPECK_PX if speck_px is None else speck_px)
    keep[0] = False
    return keep[labels]


def overlap_px(lines, mask, margin):
    """Figure pixels under any line box grown by `margin`, each pixel counted once."""
    covered = np.zeros(mask.shape, bool)
    for line in lines:
        covered[region(line, mask.shape, margin)] = True
    return int((covered & mask).sum())


def fit_failures(fit, settings):
    if fit.ok:
        return []
    why = f"{len(fit.lines)} lines (max {settings.max_lines})"
    if fit.overflows:
        why += ", overflows its box"
    return [f"does not fit at the {settings.min_size:g}px floor (template size {settings.start:g}px): {why}"]


def canvas_failures(image_shape, canvas, size):
    W, H = size
    placed = [round(v) for v in (canvas.x, canvas.y, canvas.w, canvas.h)]
    if tuple(image_shape[:2]) == (H, W) and placed == [0, 0, W, H]:
        return []
    return [f"#canvas is {canvas.w:g}x{canvas.h:g} at {canvas.x:g},{canvas.y:g}; template name says {W}x{H}"]


def blank_failures(full):
    q = full[..., :3].astype(int) >> 4
    codes = (q[..., 0] << 8 | q[..., 1] << 4 | q[..., 2]).ravel()
    if np.bincount(codes).max() / codes.size > BLANK_SHARE:
        return ["canvas is >99% one colour; a layer probably failed to load"]
    return []


def evaluate(fit, settings, canvas, size, full, notext, black_text, white_text, figure_alpha=None, images=()):
    """All checks on one render. Returns (failures, summary)."""
    glyphs = glyph_pixels(black_text, white_text)
    share = float(glyphs.mean())
    worst = worst_contrast(fit.fragments, glyphs, notext)

    failures = fit_failures(fit, settings) + canvas_failures(full.shape, canvas, size)
    if share > MAX_TEXT_SHARE:
        failures.append(f"text covers {share:.0%} of the canvas (max {MAX_TEXT_SHARE:.0%})")
    if worst is not None and worst < settings.min_contrast:
        failures.append(f"contrast {worst:.2f}:1 is below {settings.min_contrast:g}:1")
    if figure_alpha is not None:
        hits = overlap_px(fit.lines, figure_mask(figure_alpha), settings.collide_margin)
        if hits:
            failures.append(f"headline overlaps #figure ({hits} px)")
    for image in images:
        failures += upscale_failures(image)
    failures += blank_failures(full)

    summary = f"{fit.size:g}px, {len(fit.lines)} lines"
    if worst is not None:
        summary += f", contrast {worst:.1f}:1, text {share:.0%}"
    for image in images:
        summary += f", {image.slot} {max(drawn_scale(image)):.2f}x"
    return failures, summary
