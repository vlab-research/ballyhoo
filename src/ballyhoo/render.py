"""Render ad creatives from a copy file and check that the text fits.

The copy file maps design -> country -> named variant -> headline, and says
where the designs live (`designs:`, default ./designs). Every path is resolved
relative to the file that names it: the copy file names the designs directory,
and each template names its own images and fonts. Output goes to out/ next to
the copy file, one PNG per design x country x variant x template:
out/<design>_<country>_<variant>_<W>x<H>.png.

An output is skipped when the hash of its inputs (this module, the text, the
template and every file the template references) matches the hash stored in the
PNG. A creative that fails any check is not written, and a stale PNG for it is
deleted.
"""
import asyncio
import hashlib
import html
import io
import os
import re
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, PngImagePlugin
from playwright.async_api import async_playwright
from scipy import ndimage

WORKERS = 4
HASH_KEY = "render-inputs"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TEMPLATE_NAME = re.compile(r"^(\d+)x(\d+)\.html$")
REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+)["']?\s*\)""")
RESERVED = {"designs"}
MAX_TEXT_SHARE = 0.20
# Detached bits of a cut-out mask smaller than this are background-removal
# leftovers, not the subject (one LAC figure has a 112 px one by the headline).
SPECK_PX = 500

# Mask images are fetched in CORS mode, which file:// pages fail without this flag.
CHROME_ARGS = ["--allow-file-access-from-files", "--font-render-hinting=none"]

HIDE_TEXT = """#headline, #headline * { color: transparent !important;
  text-shadow: none !important; -webkit-text-stroke: 0 !important; }"""
FIGURE_ONLY = """html, body, #canvas { background: transparent !important; }
  #canvas * { visibility: hidden !important; }
  #canvas #figure { visibility: visible !important; }"""

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

# Shrink the headline 1px at a time from its CSS size until the text sits inside
# #headline's box in at most data-max-lines lines, stopping at data-min-size.
AUTOFIT_JS = """() => {
  const h = document.getElementById('headline');
  const copy = h.matches('[data-copy]') ? h : h.querySelector('[data-copy]');
  const min = parseFloat(h.dataset.minSize), maxLines = parseInt(h.dataset.maxLines);
  if (!(min > 0) || !(maxLines > 0)) throw new Error('#headline needs data-min-size and data-max-lines');
  const start = parseFloat(getComputedStyle(h).fontSize);
  if (start < min) throw new Error(`#headline font-size ${start}px is below data-min-size ${min}`);
  const rect = r => ({x: r.left, y: r.top, w: r.width, h: r.height});
  const measure = () => {
    const frags = [];
    const walk = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
    for (let n; (n = walk.nextNode());) {
      if (!n.nodeValue.trim()) continue;
      const range = document.createRange(); range.selectNodeContents(n);
      const cs = getComputedStyle(n.parentElement), lh = parseFloat(cs.lineHeight);
      // Text rects span the font's content area, which overhangs the line box when
      // line-height is tight; measure the line box, where the glyphs actually sit.
      for (const r of range.getClientRects()) if (r.width > 0.5)
        frags.push(isNaN(lh) ? {...rect(r), color: cs.color}
                             : {x: r.left, y: r.top + (r.height - lh) / 2, w: r.width, h: lh, color: cs.color});
    }
    // An inline copy element draws its own per-line boxes (padding, background).
    const boxes = getComputedStyle(copy).display === 'inline' ? [...copy.getClientRects()].map(rect) : [];
    const lines = [];
    for (const f of [...frags].sort((a, b) => a.y - b.y)) {
      const cy = f.y + f.h / 2;
      const l = lines.find(l => Math.abs(l.cy - cy) < Math.min(l.h, f.h) / 2);
      if (!l) { lines.push({x: f.x, y: f.y, w: f.w, h: f.h, cy}); continue; }
      const x0 = Math.min(l.x, f.x), y0 = Math.min(l.y, f.y);
      const x1 = Math.max(l.x + l.w, f.x + f.w), y1 = Math.max(l.y + l.h, f.y + f.h);
      Object.assign(l, {x: x0, y: y0, w: x1 - x0, h: y1 - y0});
    }
    const all = [...frags, ...boxes], b = h.getBoundingClientRect();
    const fits = all.length > 0
      && Math.min(...all.map(r => r.x)) >= b.left - 0.5 && Math.min(...all.map(r => r.y)) >= b.top - 0.5
      && Math.max(...all.map(r => r.x + r.w)) <= b.right + 0.5 && Math.max(...all.map(r => r.y + r.h)) <= b.bottom + 0.5;
    return {frags, lines: lines.map(({cy, ...l}) => l), fits};
  };
  const base = {start, min, maxLines,
    minContrast: parseFloat(h.dataset.minContrast || '3'),
    collideMargin: parseFloat(h.dataset.collideMargin || '4'),
    hasFigure: !!document.getElementById('figure'),
    canvas: rect(document.getElementById('canvas').getBoundingClientRect())};
  let m;
  for (let s = Math.floor(start); s >= min; s--) {
    h.style.fontSize = s + 'px';
    m = measure();
    if (m.fits && m.lines.length <= maxLines) return {...base, ...m, ok: true, size: s};
  }
  return {...base, ...m, ok: false, size: min};
}"""


@dataclass(frozen=True)
class Job:
    design: str
    country: str
    variant: str
    text: str
    template: Path

    @property
    def size(self):
        w, h = TEMPLATE_NAME.match(self.template.name).groups()
        return int(w), int(h)

    @property
    def key(self):
        return f"{self.design}/{self.country}/{self.variant}/{self.template.stem}"

    def out(self, out_dir):
        return out_dir / f"{self.design}_{self.country}_{self.variant}_{self.template.stem}.png"


@dataclass(frozen=True)
class Result:
    job: Job
    status: str  # "ok", "skip" or "FAIL"
    message: str


def chrome_path():
    """A system Chrome if there is one; None means Playwright's bundled Chromium."""
    if os.environ.get("BALLYHOO_CHROME"):
        return os.environ["BALLYHOO_CHROME"]
    names = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")
    return next((p for p in map(shutil.which, names) if p), None)


def load_jobs(path):
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return [], [f"{path}: expected a map of design -> country -> variant -> text"]
    designs = data.get("designs", "designs")
    if not isinstance(designs, str):
        return [], [f"{path}: designs must be a path to the templates directory"]
    root = (path.parent / designs).resolve()
    if not root.is_dir():
        return [], [f"{path}: designs directory {root} does not exist"]
    jobs, errors = [], []
    for design, countries in data.items():
        if design in RESERVED:
            continue
        templates = sorted(p for p in (root / str(design)).glob("*.html") if TEMPLATE_NAME.match(p.name))
        if not templates:
            errors.append(f"{design}: no <W>x<H>.html templates in {root / str(design)}")
            continue
        if not isinstance(countries, dict):
            errors.append(f"{design}: expected a map of country -> variants")
            continue
        for country, variants in countries.items():
            where = f"{design}/{country}"
            if not isinstance(country, str):
                errors.append(f"{where}: country must be a string (quote it; YAML reads NO as false)")
            elif not isinstance(variants, dict):
                # A list would make output keys depend on order; see docs/design.md.
                errors.append(f"{where}: variants must be a named map, not a {type(variants).__name__}")
            else:
                for variant, text in variants.items():
                    where = f"{design}/{country}/{variant}"
                    if not isinstance(variant, str) or not SLUG.match(variant):
                        errors.append(f"{where}: variant names are lowercase slugs")
                    elif not isinstance(text, str) or not text.strip():
                        errors.append(f"{where}: text must be a non-empty string")
                    elif text.count("*") % 2:
                        errors.append(f"{where}: unbalanced * in {text!r}")
                    else:
                        jobs += [Job(design, country, variant, text.strip(), t) for t in templates]
    return jobs, errors


def markup(text):
    """*word* marks emphasis (the highlighted part); the template decides how it looks."""
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html.escape(text))


@lru_cache(maxsize=None)
def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_hash(job):
    h = hashlib.sha256()
    h.update(file_digest(Path(__file__).resolve()).encode())
    h.update(job.text.encode())
    source = job.template.read_text()
    h.update(source.encode())
    for ref in sorted({a or b for a, b in REF.findall(source)}):
        if re.match(r"^(data:|https?:|#)", ref):
            continue
        path = (job.template.parent / ref).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{job.template} references missing file {ref}")
        h.update(ref.encode() + file_digest(path).encode())
    return h.hexdigest()


def stored_hash(path):
    try:
        with Image.open(path) as im:
            return im.text.get(HASH_KEY)
    except (OSError, AttributeError):
        return None


def luminance(rgb):
    c = np.asarray(rgb, float)[:3] / 255
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(c @ [0.2126, 0.7152, 0.0722])


def contrast(a, b):
    hi, lo = sorted([luminance(a), luminance(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def box_slice(r, W, H, grow=0.0):
    x0, y0 = max(0, int(r["x"] - grow)), max(0, int(r["y"] - grow))
    x1, y1 = min(W, int(np.ceil(r["x"] + r["w"] + grow))), min(H, int(np.ceil(r["y"] + r["h"] + grow)))
    return slice(y0, y1), slice(x0, x1)


async def render(browser, job):
    """Returns (image, failures, summary)."""
    W, H = job.size
    page = await browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    try:
        await page.goto(job.template.as_uri(), wait_until="load")
        await page.evaluate(PREPARE_JS, markup(job.text))
        fit = await page.evaluate(AUTOFIT_JS)

        async def shot(css=None, omit=False):
            tag = await page.add_style_tag(content=css) if css else None
            png = await page.screenshot(clip={"x": 0, "y": 0, "width": W, "height": H}, omit_background=omit)
            if tag:
                await tag.evaluate("e => e.remove()")
            return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))

        full = await shot()
        notext = await shot(HIDE_TEXT)
        figure = await shot(FIGURE_ONLY, omit=True) if fit["hasFigure"] else None
    finally:
        await page.close()

    fails = []
    if not fit["ok"]:
        why = f"{len(fit['lines'])} lines (max {fit['maxLines']})"
        if not fit["fits"]:
            why += ", overflows its box"
        fails.append(f"does not fit at the {fit['min']:g}px floor (template size {fit['start']:g}px): {why}")

    cv = fit["canvas"]
    if full.shape[:2] != (H, W) or [round(cv[k]) for k in "xywh"] != [0, 0, W, H]:
        fails.append(f"#canvas is {cv['w']:g}x{cv['h']:g} at {cv['x']:g},{cv['y']:g}; template name says {W}x{H}")

    text_px = np.abs(full[..., :3].astype(int) - notext[..., :3]).max(axis=2) > 48
    share = text_px.mean()
    if share > MAX_TEXT_SHARE:
        fails.append(f"text covers {share:.0%} of the canvas (max {MAX_TEXT_SHARE:.0%})")

    worst = None
    for f in fit["frags"]:
        ys, xs = box_slice(f, W, H)
        under = text_px[ys, xs]
        if under.sum() < 20:
            continue
        bg = notext[ys, xs, :3][under].mean(axis=0)
        fg = [float(v) for v in re.findall(r"[\d.]+", f["color"])[:3]]
        c = contrast(fg, bg)
        worst = c if worst is None else min(worst, c)
    if worst is not None and worst < fit["minContrast"]:
        fails.append(f"contrast {worst:.2f}:1 is below {fit['minContrast']:g}:1")

    if figure is not None:
        alpha = figure[..., 3] > 40
        labels, _ = ndimage.label(alpha)
        keep = np.bincount(labels.ravel()) >= SPECK_PX
        keep[0] = False
        alpha = keep[labels]
        hits = sum(int(alpha[box_slice(l, W, H, fit["collideMargin"])].sum()) for l in fit["lines"])
        if hits:
            fails.append(f"headline overlaps #figure ({hits} px)")

    q = full[..., :3] >> 4
    codes = (q[..., 0].astype(int) << 8 | q[..., 1].astype(int) << 4 | q[..., 2]).ravel()
    if np.bincount(codes).max() / codes.size > 0.99:
        fails.append("canvas is >99% one colour; a layer probably failed to load")

    summary = (f"{fit['size']:g}px, {len(fit['lines'])} lines, "
               f"contrast {worst:.1f}:1, text {share:.0%}" if worst is not None else f"{fit['size']:g}px")
    return full[..., :3], fails, summary


async def process(browser, sem, job, out_dir, check, force):
    out = job.out(out_dir)
    async with sem:
        try:
            digest = inputs_hash(job)
            if not (check or force) and out.exists() and stored_hash(out) == digest:
                return "skip", "up to date"
            image, fails, summary = await render(browser, job)
        except Exception as e:  # attribute every failure to its creative
            return "FAIL", f"{type(e).__name__}: {e}"
    if fails:
        if not check and out.exists():
            out.unlink()
        return "FAIL", "; ".join(fails) + f" [{summary}]"
    if not check:
        info = PngImagePlugin.PngInfo()
        info.add_text(HASH_KEY, digest)
        tmp = out.with_suffix(".tmp.png")
        Image.fromarray(image).save(tmp, pnginfo=info)
        tmp.replace(out)
    return "ok", summary


async def render_all(creatives, out=None, design=None, country=None, variant=None, size=None,
                     check=False, force=False):
    """Render every creative in a copy file that matches the filters.

    Returns (results sorted by key, copy-file errors)."""
    creatives = Path(creatives)
    out = Path(out) if out else creatives.parent / "out"
    jobs, errors = load_jobs(creatives)
    jobs = [j for j in jobs
            if design in (None, j.design) and country in (None, j.country)
            and variant in (None, j.variant) and size in (None, j.template.stem)]
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
    results = [Result(j, s, m) for j, (s, m) in zip(jobs, statuses)]
    return sorted(results, key=lambda r: r.job.key), errors


def run(creatives, **kwargs):
    return asyncio.run(render_all(creatives, **kwargs))
