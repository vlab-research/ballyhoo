"""Stand-in art for the LAC fixture designs.

Each image has the real file's aspect ratio, so the templates place it exactly
as they place the real one. Shapes are drawn in page coordinates and mapped into
the image, so the geometry that tests depend on is written as it appears on the
1080x1080 page. The real art is licensed but not needed: these shapes carry
everything the tests check.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

CREAM, PEACH, ORANGE, TEAL, DARK_TEAL = (238, 225, 208), (243, 193, 166), (239, 157, 83), (0, 81, 100), (1, 59, 73)
GREY, INK = (150, 150, 150), (30, 30, 30)


class Placed:
    """An image of `size` placed on the page at (left, top, width, height)."""

    def __init__(self, size, placement, mode="RGBA", fill=(0, 0, 0, 0)):
        self.image = Image.new(mode, size, fill)
        self.draw = ImageDraw.Draw(self.image)
        (self.W, self.H), (self.left, self.top, self.w, self.h) = size, placement

    def xy(self, x, y):
        return ((x - self.left) * self.W / self.w, (y - self.top) * self.H / self.h)

    def ellipse(self, cx, cy, rx, ry, fill, outline=INK):
        (x0, y0), (x1, y1) = self.xy(cx - rx, cy - ry), self.xy(cx + rx, cy + ry)
        self.draw.ellipse([x0, y0, x1, y1], fill=fill, outline=outline, width=2)

    def polygon(self, points, fill):
        self.draw.polygon([self.xy(x, y) for x, y in points], fill=fill, outline=INK)


def hills():
    W, H = 1612, 540
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    for i, (colour, level) in enumerate([(PEACH, 0.40), (ORANGE, 0.47), (TEAL, 0.60), (DARK_TEAL, 0.82)]):
        edge = [(x, H * (level + 0.04 * math.sin(2 * math.pi * x / W * 3 + i))) for x in range(0, W + 1, 8)]
        d.polygon(edge + [(W, H), (0, H)], fill=colour)
    return img


def zigzag():
    W, H = 810, 540
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(-30, H + 30, 36):
        d.line([(x, y + (18 if (x // 40) % 2 else 0)) for x in range(0, W + 40, 40)], fill=(210, 30, 30), width=10)
    return img


def band():
    """Rough-edged band, flat yellow at 80% alpha: the alpha is what templates use."""
    W, H = 1047, 178
    rng = np.random.default_rng(78)
    top = np.clip(0.10 * H + np.cumsum(rng.normal(0, 1.2, W)), 0.04 * H, 0.16 * H)
    bottom = np.clip(0.90 * H + np.cumsum(rng.normal(0, 1.2, W)), 0.84 * H, 0.96 * H)
    rows = np.arange(H)[:, None]
    alpha = ((rows >= top) & (rows <= bottom)).astype(np.uint8) * 204
    rgba = np.dstack([np.full((H, W), c, np.uint8) for c in (248, 240, 57)] + [alpha])
    return Image.fromarray(rgba, "RGBA")


def cats():
    p = Placed((490, 446), (32, 315, 986, 898))
    for cx in (290, 760):
        p.ellipse(cx, 900, 230, 330, GREY)
        p.ellipse(cx, 520, 170, 150, GREY)
        p.polygon([(cx - 160, 480), (cx - 120, 330), (cx - 50, 400)], GREY)
        p.polygon([(cx + 160, 480), (cx + 120, 330), (cx + 50, 400)], GREY)
    return p.image


def dogs():
    p = Placed((514, 450), (25, 302, 1030, 902))
    for cx in (320, 760):
        p.ellipse(cx, 950, 250, 300, GREY)
        p.ellipse(cx, 640, 200, 190, GREY)
        p.polygon([(cx - 190, 560), (cx - 170, 320), (cx - 40, 470)], GREY)
        p.polygon([(cx + 190, 560), (cx + 170, 320), (cx + 40, 470)], GREY)
    return p.image


def couple():
    """The man's head starts at the top of the image, over x 720-920 on the page."""
    p = Placed((473, 447), (240, 245, 946, 895))
    p.ellipse(560, 480, 90, 105, (190, 140, 100))                    # woman's head
    p.polygon([(380, 1140), (430, 620), (700, 620), (740, 1140)], (240, 170, 40))
    p.ellipse(820, 360, 100, 112, (160, 110, 80))                    # man's head: top at page y 248
    p.polygon([(700, 1140), (720, 520), (1000, 520), (1186, 1140)], (200, 110, 50))
    return p.image


def man():
    """Head from page y 190, never left of x 660; a 48 px speck at (476, 148), under the headline."""
    p = Placed((380, 502), (377, 137, 763, 1007))
    p.ellipse(830, 375, 170, 185, (220, 180, 150))
    p.ellipse(800, 1000, 400, 380, (140, 120, 90))
    x0, y0 = p.xy(474, 146)
    p.draw.rectangle([x0, y0, x0 + 2, y0 + 3], fill=(120, 110, 100, 125))
    return p.image


def woman():
    """Hair from page y 240, over x 150-540."""
    p = Placed((434, 431), (0, 234, 869, 863))
    p.ellipse(345, 440, 195, 200, (70, 70, 80))
    p.ellipse(300, 920, 300, 320, (140, 150, 140))
    return p.image


def hamster():
    img = Image.new("RGB", (450, 450), (238, 235, 228))
    d = ImageDraw.Draw(img)
    d.ellipse([130, 40, 320, 360], fill=(170, 165, 160), outline=INK, width=3)
    d.rectangle([60, 330, 390, 450], fill=(250, 250, 250), outline=INK, width=3)
    return img


def kids():
    W, H = 400, 600
    x = np.linspace(0, 1, W)[None, :, None]
    img = (np.array((225, 225, 222)) * (x < 0.45) + np.array((250, 215, 190)) * (x >= 0.45) * (0.8 + 0.2 * x))
    img = Image.fromarray(np.repeat(img, H, axis=0).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    d.ellipse([200, 60, 330, 200], fill=(205, 160, 130), outline=INK, width=3)
    d.ellipse([250, 380, 390, 520], fill=(210, 165, 135), outline=INK, width=3)
    return img


FILES = {
    "backgrounds/wave-hills.png": hills,
    "backgrounds/red-zigzag.png": zigzag,
    "elements/yellow-headline-band.png": band,
    "characters/cool-cats.png": cats,
    "characters/cool-dogs.png": dogs,
    "characters/couple-phones.png": couple,
    "characters/man-scarf.png": man,
    "characters/woman-round-glasses.png": woman,
    "scenes/survey-hamster.png": hamster,
    "scenes/kids-peeking.png": kids,
}


def write_all(library):
    for name, make in FILES.items():
        path = library / name
        path.parent.mkdir(parents=True, exist_ok=True)
        make().save(path)
