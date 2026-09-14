"""A provider for tests, which searches and generates with no network and draws its images at test time.

It builds requests to https://fake.test as any provider builds requests to its
API, and `serve` answers them through httpx.MockTransport, so a run takes the
same code paths it takes with Pexels and Gemini. It is registered only in tests.

The query or prompt picks what comes back, so a test says in its brief which
outcome it wants:

- "bright": large and light, so a dark headline passes contrast;
- "dark": large and near a dark headline's colour, so contrast fails;
- "small": 400 px square, so a scene stretched over an ad is upscaled;
- "error": the server answers 503.

Seed 13 is always refused. Search results are numbered from the query's word
count, so queries of different lengths overlap as real ones do: "bright village"
finds bright-2 and bright-3, and "bright old village" finds bright-3 and bright-4.
"""
import base64
import io
import json
import re

import httpx
from PIL import Image, ImageDraw

from ballyhoo.candidates import Candidate
from ballyhoo.providers import Request

NAME = "fake"
MODEL = "fake-image-1"
UNPRICED_MODEL = "fake-image-unpriced"
HOST = "fake.test"
REFUSED_SEED = 13
SMALL = (400, 400)
STOCK_SIZE = (1600, 1200)  # covers a 1080 px ad without being enlarged
# Background and a centred disc, so no image is one flat colour.
COLOURS = {"bright": ((236, 232, 220), (205, 212, 196)), "small": ((236, 232, 220), (205, 212, 196)),
           "dark": ((28, 28, 32), (48, 46, 52))}
OUTCOME = re.compile(r"\b(bright|dark|small|error)\b")
PRICE = {"checked": "2026-09-14", "source": "tests/fake_provider.py", "per_request": 0.0,
         "per_image": {MODEL: 0.25}}


class Refused(Exception):
    pass


def search_price(n):
    return PRICE["per_request"]


def image_price(model, width, height):
    return PRICE["per_image"].get(model)


def search_request(query, page, per_page, env):
    return Request("GET", f"https://{HOST}/search", params={"query": query, "page": page, "per_page": per_page})


def parse_search(payload, query):
    found = [Candidate(f"{NAME}-{p['id']}", p["width"], p["height"], p["url"], p["thumb"],
                       {"source": "stock", "provider": NAME, "id": p["id"], "page_url": f"https://{HOST}/photo/{p['id']}",
                        "creator": "A. Photographer", "licence": "Fake Licence", "licence_url": f"https://{HOST}/licence",
                        "query": query})
             for p in payload["photos"]]
    return found, payload["more"]


def generate_request(prompt, seed, width, height, env, token=None, model=MODEL):
    return Request("POST", f"https://{HOST}/generate",
                   json={"prompt": prompt, "seed": seed, "width": width, "height": height, "model": model})


def parse_image(payload):
    if payload.get("refused"):
        raise Refused(payload["refused"])
    return base64.b64decode(payload["image"])


def draw(outcome, width, height, offset=0):
    """An image for an outcome; `offset` moves the disc, so different seeds give different bytes."""
    background, disc = COLOURS[outcome]
    image = Image.new("RGB", (width, height), background)
    r = min(width, height) // 4
    cx, cy = width // 2 + offset % 50, height // 2
    ImageDraw.Draw(image).ellipse((cx - r, cy - r, cx + r, cy + r), fill=disc)
    return image


def encode(image, format):
    buf = io.BytesIO()
    image.save(buf, format)
    return buf.getvalue()


def serve(request):
    """The fake API and image host: an httpx.MockTransport handler."""
    path = request.url.path
    if path.startswith("/images/"):
        _, _, outcome, name = path.split("/")
        width, height = SMALL if outcome == "small" else STOCK_SIZE
        return httpx.Response(200, content=encode(draw(outcome, width, height), "JPEG"))
    if path == "/search":
        query = request.url.params["query"]
        text = query
    elif path == "/generate":
        body = json.loads(request.content)
        text = body["prompt"]
    else:
        return httpx.Response(404, text=f"no such fake endpoint {path}")
    found = OUTCOME.search(text)
    if not found:
        return httpx.Response(400, text=f"say bright, dark, small or error in {text!r}")
    outcome = found[1]
    if outcome == "error":
        return httpx.Response(503, text="the fake provider is down")
    if path == "/search":
        first = len(query.split())
        width, height = SMALL if outcome == "small" else STOCK_SIZE
        photos = [{"id": f"{outcome}-{i}", "width": width, "height": height,
                   "url": f"https://{HOST}/images/{outcome}/{outcome}-{i}.jpg",
                   "thumb": f"https://{HOST}/images/{outcome}/{outcome}-{i}-thumb.jpg"}
                  for i in range(first, first + int(request.url.params["per_page"]))]
        return httpx.Response(200, json={"photos": photos, "more": False})
    if body["seed"] == REFUSED_SEED:
        return httpx.Response(200, json={"refused": f"seed {REFUSED_SEED} is always refused"})
    width, height = SMALL if outcome == "small" else (body["width"], body["height"])
    png = encode(draw(outcome, width, height, body["seed"]), "PNG")
    return httpx.Response(200, json={"image": base64.b64encode(png).decode()})
