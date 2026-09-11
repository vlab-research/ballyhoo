"""Render ad creatives from a copy file and check that the text fits.

The copy file maps design -> country -> named variant -> headline, and says
where the designs live (`designs:`, default ./designs). Every path is resolved
relative to the file that names it: the copy file names the designs directory,
and each template names its own images and fonts. Output goes to out/ next to
the copy file, one PNG per design x country x variant x template:
out/<design>_<country>_<variant>_<W>x<H>.png.

An output is skipped when the hash of its inputs (ballyhoo's code, the text, the
template and every file the template references) matches the hash stored in the
PNG. A creative that fails any check is not written, and a stale PNG for it is
deleted.

This module is the imperative shell: it reads files, drives the browser and
writes PNGs. Every decision is made by the pure modules it calls: copyfile
(which creatives), cache (whether to render), fit (which font size) and checks
(whether the result passes).
"""
import asyncio
import hashlib
import io
import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, PngImagePlugin
from playwright.async_api import async_playwright

from . import cache, checks, copyfile, fit
from .copyfile import Job

WORKERS = 4
HASH_KEY = "render-inputs"

# Mask images are fetched in CORS mode, which file:// pages fail without this flag.
CHROME_ARGS = ["--allow-file-access-from-files", "--font-render-hinting=none"]

HIDE_TEXT = """#headline, #headline * { color: transparent !important;
  text-shadow: none !important; -webkit-text-stroke: 0 !important; }"""
FIGURE_ONLY = """html, body, #canvas { background: transparent !important; }
  #canvas * { visibility: hidden !important; }
  #canvas #figure { visibility: visible !important; }"""

# Put the copy in and wait until every font and image has loaded (or failed loudly).
PREPARE_JS = """async (copyHtml) => {
  const canvas = document.getElementById('canvas');
  const headline = document.getElementById('headline');
  if (!canvas || !headline) throw new Error('template needs #canvas and #headline');
  const slot = [headline, ...headline.querySelectorAll('*')].find(
    e => e.children.length === 0 && e.textContent.trim() === '{{text}}');
  if (!slot) throw new Error('#headline needs an element whose only content is {{text}}');
  slot.innerHTML = copyHtml;
  slot.setAttribute('data-copy', '');
  await Promise.all([...document.fonts].map(f => f.load().catch(() => {
    throw new Error('font failed to load: ' + f.family); })));
  await document.fonts.ready;
  const urls = new Set();
  for (const el of canvas.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    for (const v of [cs.backgroundImage, cs.maskImage, cs.webkitMaskImage])
      for (const m of (v || '').matchAll(/url\\("?([^")]+)"?\\)/g)) urls.add(m[1]);
  }
  await Promise.all([
    ...[...canvas.querySelectorAll('img')].map(i => i.decode()
        .then(() => { if (!i.naturalWidth) throw 0; })
        .catch(() => { throw new Error('image failed to load: ' + i.getAttribute('src')); })),
    ...[...urls].map(u => { const i = new Image(); i.src = u;
        return i.decode().catch(() => { throw new Error('CSS image failed to load: ' + u); }); }),
  ]);
}"""

READ_JS = """() => {
  const h = document.getElementById('headline');
  const c = document.getElementById('canvas').getBoundingClientRect();
  return {attrs: {...h.dataset}, start: parseFloat(getComputedStyle(h).fontSize),
          canvas: {x: c.left, y: c.top, w: c.width, h: c.height},
          hasFigure: !!document.getElementById('figure')};
}"""

# Measure only: the raw text rects at each size. fit.choose decides.
MEASURE_JS = """(sizes) => {
  const h = document.getElementById('headline');
  const copy = h.matches('[data-copy]') ? h : h.querySelector('[data-copy]');
  const rect = r => ({x: r.left, y: r.top, w: r.width, h: r.height});
  return sizes.map(size => {
    h.style.fontSize = size + 'px';
    const fragments = [];
    const walk = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
    for (let n; (n = walk.nextNode());) {
      if (!n.nodeValue.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      const cs = getComputedStyle(n.parentElement), lh = parseFloat(cs.lineHeight);
      for (const r of range.getClientRects())
        if (r.width > 0.5) fragments.push({...rect(r), lineHeight: Number.isNaN(lh) ? null : lh, color: cs.color});
    }
    const boxes = getComputedStyle(copy).display === 'inline' ? [...copy.getClientRects()].map(rect) : [];
    return {size, fragments, boxes, box: rect(h.getBoundingClientRect())};
  });
}"""

SET_SIZE_JS = "(size) => { document.getElementById('headline').style.fontSize = size + 'px'; }"


class TemplateError(Exception):
    pass


@dataclass(frozen=True)
class Result:
    job: Job
    status: str  # "ok", "skip" or "FAIL"
    message: str
    size: float | None = None  # font size chosen, when rendered
    lines: int | None = None


def chrome_path():
    """A system Chrome if there is one; None means Playwright's bundled Chromium."""
    if os.environ.get("BALLYHOO_CHROME"):
        return os.environ["BALLYHOO_CHROME"]
    names = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")
    return next((p for p in map(shutil.which, names) if p), None)


@lru_cache(maxsize=None)
def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=None)
def code_digest():
    h = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(path.name.encode() + file_digest(path).encode())
    return h.hexdigest()


def load_jobs(creatives):
    creatives = Path(creatives)
    data = yaml.safe_load(creatives.read_text())
    root, errors = copyfile.designs_dir(data, creatives.parent)
    if errors:
        return [], [f"{creatives}: {e}" for e in errors]
    root = root.resolve()
    if not root.is_dir():
        return [], [f"{creatives}: designs directory {root} does not exist"]
    templates = {name: sorted((root / name).glob("*.html")) for name in copyfile.design_names(data)}
    return copyfile.parse(data, templates, root)


def inputs_hash(job):
    source = job.template.read_text()
    ref_digests = {}
    for ref in cache.template_refs(source):
        path = (job.template.parent / ref).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{job.template} references missing file {ref}")
        ref_digests[ref] = file_digest(path)
    return cache.inputs_digest(code_digest(), job.text, source, ref_digests)


def stored_hash(path):
    try:
        with Image.open(path) as im:
            return im.text.get(HASH_KEY)
    except (OSError, AttributeError):
        return None


async def screenshot(page, W, H, css=None, omit_background=False):
    tag = await page.add_style_tag(content=css) if css else None
    png = await page.screenshot(clip={"x": 0, "y": 0, "width": W, "height": H}, omit_background=omit_background)
    if tag:
        await tag.evaluate("e => e.remove()")
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


async def render(browser, job):
    """Returns (image, failures, summary, fit)."""
    W, H = job.size
    page = await browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    try:
        await page.goto(job.template.as_uri(), wait_until="load")
        await page.evaluate(PREPARE_JS, copyfile.markup(job.text))
        info = await page.evaluate(READ_JS)
        settings, errors = fit.parse_settings(info["attrs"], info["start"])
        if errors:
            raise TemplateError("; ".join(errors))
        measured = await page.evaluate(MEASURE_JS, fit.candidate_sizes(settings))
        chosen = fit.choose([fit.measurement_from_page(m) for m in measured], settings.max_lines)
        await page.evaluate(SET_SIZE_JS, chosen.size)
        full = await screenshot(page, W, H)
        notext = await screenshot(page, W, H, HIDE_TEXT)
        figure = await screenshot(page, W, H, FIGURE_ONLY, omit_background=True) if info["hasFigure"] else None
    finally:
        await page.close()
    failures, summary = checks.evaluate(chosen, settings, fit.Rect.of(info["canvas"]), (W, H), full, notext,
                                        None if figure is None else figure[..., 3])
    return full[..., :3], failures, summary, chosen


async def process(browser, sem, job, out_dir, check, force):
    out = out_dir / job.out_name
    async with sem:
        try:
            digest = inputs_hash(job)
            if not cache.should_render(stored_hash(out) if out.exists() else None, digest, check, force):
                return "skip", "up to date", None
            image, failures, summary, chosen = await render(browser, job)
        except Exception as e:  # attribute every failure to its creative
            return "FAIL", f"{type(e).__name__}: {e}", None
    if failures:
        if not check and out.exists():
            out.unlink()
        return "FAIL", "; ".join(failures) + f" [{summary}]", chosen
    if not check:
        info = PngImagePlugin.PngInfo()
        info.add_text(HASH_KEY, digest)
        tmp = out.with_suffix(".tmp.png")
        Image.fromarray(image).save(tmp, pnginfo=info)
        tmp.replace(out)
    return "ok", summary, chosen


async def render_all(creatives, out=None, design=None, country=None, variant=None, size=None,
                     check=False, force=False):
    """Render every creative in a copy file that matches the filters.

    Returns (results sorted by key, copy-file errors)."""
    creatives = Path(creatives)
    out = Path(out) if out else creatives.parent / "out"
    jobs, errors = load_jobs(creatives)
    jobs = copyfile.select(jobs, design=design, country=country, variant=variant, size=size)
    if not jobs:
        return [], errors
    if not check:
        out.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(WORKERS)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome_path(), args=CHROME_ARGS)
        try:
            statuses = await asyncio.gather(*(process(browser, sem, j, out, check, force) for j in jobs))
        finally:
            await browser.close()
    results = [Result(j, status, message, chosen and chosen.size, chosen and len(chosen.lines))
               for j, (status, message, chosen) in zip(jobs, statuses)]
    return sorted(results, key=lambda r: r.job.key), errors


def run(creatives, **kwargs):
    return asyncio.run(render_all(creatives, **kwargs))
