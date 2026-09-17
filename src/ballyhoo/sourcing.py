"""Searching, generating and keeping: the shell for candidates.py and the providers.

Sends the requests providers build, saves generated images, downloads
thumbnails, draws contact sheets and writes kept images, as delivered, with
their provenance.
"""
import datetime
import hashlib
import io
import os
import time
from pathlib import Path

import google.auth
import google.auth.transport.requests
import httpx
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import art, candidates as cands, cutout
from .providers import Request

TIMEOUT = 120
POLL_SECONDS = 2
POLL_LIMIT = 300
USER_AGENT = "ballyhoo/0.1 (recruitment ads; https://github.com/vlab-research/ballyhoo)"
EXIF_ORIENTATION = 0x0112


def client(**kwargs):
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}, **kwargs)


def send(http, request):
    response = http.request(request.method, request.url, params=request.params, headers=request.headers,
                            json=request.json, data=request.data)
    if response.is_error:  # the provider's explanation is in the body, not the status
        raise httpx.HTTPStatusError(f"{response.status_code} from {request.url}: {response.text[:500]}",
                                    request=response.request, response=response)
    return response


def google_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def auth_token(http, provider, env):
    if hasattr(provider, "token_request"):
        return provider.parse_token(send(http, provider.token_request(env)).json())
    if getattr(provider, "AUTH", None) == "google-adc":
        return google_token()
    return None


def image_bytes(http, provider, request, env, token, sleep):
    """The generated image, waiting on the provider's queue if it has one."""
    reply = send(http, request).json()
    if not hasattr(provider, "parse_submission"):
        return provider.parse_image(reply)
    status_url, result_url = provider.parse_submission(reply)
    for _ in range(POLL_LIMIT):
        status = send(http, provider.poll_request(status_url, env, token)).json()
        if provider.parse_status(status):
            break
        sleep(getattr(provider, "POLL_SECONDS", POLL_SECONDS))
    else:
        raise TimeoutError(f"{provider.NAME} had not finished after {POLL_LIMIT} polls")
    result = status if result_url == status_url else send(http, provider.poll_request(result_url, env, token)).json()
    # Result URLs are pre-signed or public: sending the provider's credentials to them would leak the credentials.
    return send(http, Request("GET", provider.parse_result(result))).content


def write_cutout(directory, candidate, data, style, digest):
    """Key a drawing out of its ground, beside the file as delivered, and record what the check found."""
    with Image.open(io.BytesIO(data)) as im:
        rgba, key = cutout.cut_out(np.asarray(im.convert("RGB")))
    path = Path(directory) / cands.cutout_file(candidate.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path)
    return cands.with_cutout(candidate, key, cutout.mask_problems(rgba, key), style, digest)


def generate(http, provider, prompt, n, seed, width, height, directory, env=None, today=None, sleep=time.sleep,
             model=None, style=None, **options):
    """Generate with seeds seed .. seed+n-1, keeping each image as delivered under <directory>/generated/.

    Returns (candidates, refusals, errors). A refusal is reported and the other seeds still run;
    an HTTP error or a timeout stops the run, since the next seed would meet it too.

    `style` names the style a drawing was prompted in; a drawing is also cut out of its ground, into
    <directory>/cutouts/, and a mask check that fails is recorded rather than stopping anything.
    """
    env = os.environ if env is None else env
    token = auth_token(http, provider, env)
    model = model or provider.MODEL
    found, refused, errors = [], [], []
    for s in range(seed, seed + n):
        request = provider.generate_request(prompt, s, width, height, env, token, model=model, **options)
        try:
            data = image_bytes(http, provider, request, env, token, sleep)
        except provider.Refused as e:
            refused.append(f"seed {s}: {e}")
            continue
        except (httpx.HTTPError, TimeoutError) as e:
            errors.append(f"seed {s}: {e}")
            break
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        digest = hashlib.sha256(data).hexdigest()
        c = cands.generated_candidate(provider.NAME, model, prompt, s, digest, cands.extension(data), w, h,
                                      today or datetime.date.today())
        path = Path(directory) / c.full
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        found.append(write_cutout(directory, c, data, style, digest) if style else c)
    return found, refused, errors


def search(http, provider, query, n, env=None, **options):
    """Up to `n` candidates, paging until there are enough or the provider has no more.

    `options` are the provider's own search options, which its record keeps.
    """
    env = os.environ if env is None else env
    found, page = [], 1
    while len(found) < n:
        request = provider.search_request(query, page, n, env, **options)
        batch, more = provider.parse_search(send(http, request).json(), query)
        found = cands.merge(found, batch)
        if not (more and batch):
            break
        page += 1
    return [cands.with_search_options(c, options) for c in found[:n]]


def download_originals(http, directory, found):
    """Download each stock candidate's full-size file into <directory>/originals/, as delivered.

    Returns (the candidates, now naming their files, errors). A download that fails or is not an
    image is reported, and its candidate left out.
    """
    downloaded, errors = [], []
    for c in found:
        try:
            data = send(http, Request("GET", c.full)).content
            ext = cands.extension(data)
            with Image.open(io.BytesIO(data)) as im:
                width, height = cands.displayed_size(*im.size, im.getexif().get(EXIF_ORIENTATION))
        except (httpx.HTTPError, ValueError, OSError) as e:
            errors.append(f"{c.id}: {e}")
            continue
        local = cands.with_original(c, ext, width, height)
        path = Path(directory) / local.full
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        downloaded.append(local)
    return downloaded, errors


def read_image(http, directory, ref):
    """An image by URL, or by path relative to the candidates directory."""
    if ref.startswith(("https://", "http://")):
        return send(http, Request("GET", ref)).content
    return (Path(directory) / ref).read_bytes()


def write_thumb(path, data):
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        path.parent.mkdir(parents=True, exist_ok=True)
        im.resize(cands.fit(*im.size, cands.THUMB_EDGE), Image.LANCZOS).save(path, quality=85)


def draw_sheets(directory, candidates):
    """Numbered contact sheets, sheet-01.png onwards, from the thumbnails."""
    number_font, size_font = ImageFont.load_default(size=40), ImageFont.load_default(size=18)
    paths = []
    for s, indexes in enumerate(cands.sheets(len(candidates)), 1):
        sheet = Image.new("RGB", cands.sheet_size(len(indexes)), "white")
        draw = ImageDraw.Draw(sheet)
        for slot, i in enumerate(indexes):
            c, (x, y) = candidates[i], cands.cell_origin(slot)
            with Image.open(directory / c.thumb) as thumb:
                w, h = cands.fit(*thumb.size, cands.SHEET_CELL - 12)
                sheet.paste(thumb.resize((w, h), Image.LANCZOS),
                            (x + (cands.SHEET_CELL - w) // 2, y + (cands.SHEET_CELL - h) // 2))
            label = str(i + 1)
            box = draw.textbbox((x + 10, y + 8), label, font=number_font)
            draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="black")
            draw.text((x + 10, y + 8), label, font=number_font, fill="white")
            draw.text((x + 10, y + cands.SHEET_CELL - 30), f"{c.width}x{c.height}", font=size_font, fill="black",
                      stroke_width=2, stroke_fill="white")
        path = directory / f"sheet-{s:02d}.png"
        sheet.save(path)
        paths.append(path)
    return paths


def add_candidates(directory, found, http):
    """Add candidates to a directory: candidates.yaml, a thumbnail each, and contact sheets.

    Returns (all candidates in the directory, sheet paths).
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / cands.FILE
    existing = []
    if path.exists():
        existing, errors = cands.load(yaml.safe_load(path.read_text()))
        if errors:
            raise ValueError(f"{path}: " + "; ".join(errors))
    merged = cands.merge(existing, found)
    for c in merged:
        if not (directory / c.thumb).exists():
            write_thumb(directory / c.thumb, read_image(http, directory, c.preview))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(cands.dump(merged), sort_keys=False, allow_unicode=True))
    tmp.replace(path)
    return merged, draw_sheets(directory, merged)


def keep(candidates_file, picks, to_dir, picked_by, http, today=None, fetched=None):
    """Write each picked candidate into `to_dir` with its sidecar. Returns (written paths, errors).

    `today` is the day it was picked; `fetched`, when a stock candidate's file was downloaded, by default `today`.
    """
    candidates_file, to_dir = Path(candidates_file), Path(to_dir)
    found, errors = cands.load(yaml.safe_load(candidates_file.read_text()))
    if errors:
        return [], [f"{candidates_file}: {e}" for e in errors]
    taken = {p.name.split(".")[0] for p in to_dir.iterdir()} if to_dir.is_dir() else set()
    keeps, errors = cands.plan_keep(found, picks, taken)
    written = []
    for k in keeps:
        try:
            data = read_image(http, candidates_file.parent, k.candidate.full)
            digest = hashlib.sha256(data).hexdigest()
            record, problems = cands.kept_record(k.candidate, digest, picked_by, today or datetime.date.today(), fetched)
            if problems:
                errors.append(f"{k.candidate.id}: {'; '.join(problems)}")
                continue
            image = to_dir / (k.name + cands.extension(data))
            to_dir.mkdir(parents=True, exist_ok=True)
            with image.open("xb") as f:
                f.write(data)
            art.write_sidecar(image, record)
            written.append(image)
        except (httpx.HTTPError, OSError, ValueError) as e:
            errors.append(f"{k.candidate.id}: {type(e).__name__}: {e}")
    return written, errors
