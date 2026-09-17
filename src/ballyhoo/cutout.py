"""Cutting a generated drawing out of the flat green it was drawn on, and checking the mask.

Pure. Drawings are generated on a flat chroma-key green and a numpy colour key
takes them out. Against the eleven cut-outs Adobe Express made of the same art
the key scored an IoU of 0.997 and lost nothing, where every matting model left
a green cast in the edge band (planning/phase-2-imagery.md § Spike results).

No remover is good enough to trust unseen, so every cut-out is checked and a
person looks at it before it is adopted: mask_problems says what a cut-out gets
wrong, with what it measured, and the shell records that rather than stopping.
"""
import numpy as np
from scipy import ndimage

# The ground a drawing must be generated on for the key to work, appended to its prompt. Glow is
# spelled out because Gemini paints a phone screen's light into the green, which no remover can take
# back out, and a frame because Gemini Pro reads "background" as the page a picture is mounted on.
BACKGROUND = ("The whole background is one completely flat, solid chroma-key green, the same green in every corner, "
              "with no shadow, gradient, scenery, frame or border, and no light or glow falling on the green.")

BORDER = 8             # px band around the edge the key colour is read from
NEAR, FAR = 30.0, 110.0  # colour distance from the key: transparent at NEAR, opaque at FAR
SPILL_RADIUS = 3       # px around the mask's edge where the key bled into the drawing
GREEN_MARGIN = 10      # green this far above the mean of red and blue is the key's, not the drawing's
CLEAR, SOLID, FULL = 8, 128, 248  # alpha: below CLEAR is background, above SOLID is the figure, FULL is opaque

# Calibrated against the eleven Express cut-outs: these flag none of them, and catch fake
# transparency, a bad white key and green fringes (planning/phase-2-imagery.md § Spike results).
MIN_TRANSPARENT, MAX_TRANSPARENT = 0.05, 0.95
MAX_SOFT = 0.01
SPECK_PX = 500         # a detached mask bit smaller than this is background the key left behind
EDGE_BAND = 4          # px inside the figure's outline, where a fringe would be
MAX_RESIDUAL, MAX_RESIDUAL_EDGE = 0.003, 0.02
MAX_PAINTED = 0.0015   # provisional: from four images the spike had with a painted-on glow
MIN_AGREEMENT = 0.90   # IoU between the mask and a plain colour key over the same image


def key_colour(rgb, border=BORDER):
    """The key colour, read from the image's border: generated green runs from (9,193,18) to (8,251,5)."""
    a = np.asarray(rgb)[..., :3]
    edges = np.concatenate([a[:border].reshape(-1, 3), a[-border:].reshape(-1, 3),
                            a[:, :border].reshape(-1, 3), a[:, -border:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(edges, axis=0))


def distance(rgb, key):
    """How far each pixel is from the key colour, in RGB."""
    return np.linalg.norm(np.asarray(rgb)[..., :3].astype(np.float32) - np.asarray(key, np.float32), axis=-1)


def green_dominant(rgb, margin=GREEN_MARGIN):
    """Where green rises above the mean of red and blue: what spill looks like, whatever the exact key."""
    c = np.asarray(rgb, np.float32)
    return c[..., 1] > (c[..., 0] + c[..., 2]) / 2 + margin


def edge_band(alpha, radius=SPILL_RADIUS):
    """The figure's pixels within `radius` of the mask's edge, where the key bled into the drawing."""
    return ndimage.binary_dilation(alpha < 1, iterations=radius) & (alpha > 0)


def cut_out(rgb, key=None):
    """The drawing alone, as RGBA. Returns (image, the key colour used).

    Alpha ramps from transparent at NEAR to opaque at FAR, the key's share is taken back out of the
    edge pixels it bled into, and green is limited around the mask's edge, where spill lives; green
    in the middle of a drawing is the artist's, and mask_problems reports it instead. Transparent
    pixels keep their colour, so a colour key over the result reproduces the mask.
    """
    rgb = np.asarray(rgb)[..., :3]
    key = tuple(key) if key is not None else key_colour(rgb)
    alpha = np.clip((distance(rgb, key) - NEAR) / (FAR - NEAR), 0, 1)
    out = rgb.astype(np.float32)
    mixed = (alpha > 0) & (alpha < 1)
    share = alpha[mixed][:, None]
    out[mixed] = (out[mixed] - (1 - share) * np.asarray(key, np.float32)) / share
    out = np.clip(out, 0, 255)
    spill = edge_band(alpha) & green_dominant(out)
    out[..., 1] = np.where(spill, (out[..., 0] + out[..., 2]) / 2, out[..., 1])
    return np.dstack([out.round().astype(np.uint8), (alpha * 255).round().astype(np.uint8)]), key


def _share(part, whole):
    return float(part.sum()) / whole if whole else 0.0


def mask_problems(rgba, key):
    """What is wrong with a cut-out, each failure naming what it measured; [] when nothing is.

    `key` is the colour that was keyed out. A drawing generated on anything but green is reported
    too: the key reads its colour from the border, so a ground that is not green keys out whatever
    happens to be there.
    """
    rgba = np.asarray(rgba)
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    solid, area = alpha >= SOLID, alpha.size
    figure = int(solid.sum())
    found = []
    if not green_dominant(np.asarray(key, np.float32)):
        found.append(f"the ground is {tuple(int(v) for v in key)}, not chroma-key green: "
                     "the drawing was not generated on green")

    transparent = _share(alpha < CLEAR, area)
    if not MIN_TRANSPARENT <= transparent <= MAX_TRANSPARENT:
        found.append(f"{transparent:.0%} of the image is transparent "
                     f"(expected {MIN_TRANSPARENT:.0%} to {MAX_TRANSPARENT:.0%})")

    soft = _share((alpha >= CLEAR) & (alpha < FULL), area)
    if soft > MAX_SOFT:
        found.append(f"{soft:.1%} of the image is part transparent (max {MAX_SOFT:.0%}): a blur, not a cut-out")

    sizes = np.bincount(ndimage.label(solid)[0].ravel())[1:]
    specks = sizes[sizes < SPECK_PX]
    if specks.size:
        found.append(f"{specks.size} stray speck{'s' if specks.size > 1 else ''} in the mask "
                     f"(largest {int(specks.max())} px, under {SPECK_PX} px is a speck): ground the key left behind")

    near = distance(rgb, key) <= FAR
    green = green_dominant(rgb) & solid
    residual = _share(green & near, figure)
    if residual > MAX_RESIDUAL:
        found.append(f"{residual:.2%} of the figure is still the key's green (max {MAX_RESIDUAL:.2%})")
    band = solid & ~ndimage.binary_erosion(solid, iterations=EDGE_BAND)
    fringe = _share(green & near & band, int(band.sum()))
    if fringe > MAX_RESIDUAL_EDGE:
        found.append(f"{fringe:.0%} of the figure's edge is still the key's green (max {MAX_RESIDUAL_EDGE:.0%})")
    painted = _share(green & ~near, figure)
    if painted > MAX_PAINTED:
        found.append(f"{painted:.2%} of the figure is green light painted on to it (max {MAX_PAINTED:.2%}): "
                     "no remover takes that out")

    keyed = distance(rgb, key) > (NEAR + FAR) / 2
    agreement = _share(keyed & solid, int((keyed | solid).sum()))
    if agreement < MIN_AGREEMENT:
        found.append(f"the mask and a plain colour key agree on {agreement:.0%} of the figure "
                     f"(min {MIN_AGREEMENT:.0%})")
    return found
