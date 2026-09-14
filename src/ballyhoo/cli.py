import argparse
import os
import re
import secrets
from pathlib import Path

from . import art, brief, candidates, provenance, render, runs, sourcing
from .providers import MissingCredential, fal, firefly, gemini, openverse, pexels

PROVIDERS = {p.NAME: p for p in (fal, firefly, gemini, openverse, pexels)}
STOCK = {name: p for name, p in PROVIDERS.items() if hasattr(p, "search_request")}
GENERATORS = {name: p for name, p in PROVIDERS.items() if hasattr(p, "generate_request")}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ballyhoo", description="An AI design studio for recruitment ads.")
    sub = ap.add_subparsers(dest="command", required=True)

    r = sub.add_parser("render", help="render and check the creatives in a copy file",
                       description=render.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    r.add_argument("creatives", nargs="?", type=Path, default=Path("creatives.yaml"),
                   help="the copy file (default: ./creatives.yaml)")
    r.add_argument("--design")
    r.add_argument("--country")
    r.add_argument("--variant")
    r.add_argument("--size", help="e.g. 1080x1080")
    r.add_argument("--check", action="store_true", help="render and check everything, write nothing")
    r.add_argument("--force", action="store_true", help="re-render even if up to date")
    r.add_argument("--out", type=Path, help="output directory (default: out/ next to the copy file)")
    r.set_defaults(run=run_render)

    p = sub.add_parser("provenance", help="record where images came from")
    psub = p.add_subparsers(dest="action", required=True)
    m = psub.add_parser("made", help="write provenance for images a person made, such as a partner's art")
    m.add_argument("images", nargs="+", type=Path)
    m.add_argument("--by", required=True, help="who made them, and the document they came from")
    m.add_argument("--rights", required=True, help="on what terms we use them")
    m.set_defaults(run=run_provenance_made)

    s = sub.add_parser("stock", help="search stock-photo APIs for candidates")
    ssub = s.add_subparsers(dest="action", required=True)
    q = ssub.add_parser("search", help="add search results to a candidates directory")
    q.add_argument("query")
    q.add_argument("--provider", required=True, choices=sorted(STOCK))
    q.add_argument("--n", type=int, default=20, help="how many results (default 20)")
    q.add_argument("--out", type=Path, required=True, help="the candidates directory; results are appended")
    q.set_defaults(run=run_stock_search)

    g = sub.add_parser("generate", help="generate candidate images with an image model")
    g.add_argument("prompt")
    g.add_argument("--provider", required=True, choices=sorted(GENERATORS))
    g.add_argument("--size", required=True, help="the shape to generate, e.g. 1080x1350")
    g.add_argument("--n", type=int, default=4, help="how many images, one seed each (default 4)")
    g.add_argument("--seed", type=int, help="the first seed (default: random)")
    g.add_argument("--model", help=", ".join(f"{name} default: {p.MODEL}" for name, p in sorted(GENERATORS.items())))
    g.add_argument("--image-size", choices=gemini.IMAGE_SIZES, help="Gemini only: its resolution (default 2K)")
    g.add_argument("--out", type=Path, required=True, help="the candidates directory; images are appended")
    g.set_defaults(run=run_generate)

    k = sub.add_parser("keep", help="copy picked candidates into the art library with their provenance")
    k.add_argument("candidates", type=Path, help="a candidates.yaml")
    k.add_argument("picks", nargs="+", help="<candidate id> or <candidate id>=<file name>")
    k.add_argument("--to", type=Path, required=True, help="the art directory, e.g. scenes/")
    k.add_argument("--picked-by", required=True, help="the person who picked them")
    k.set_defaults(run=run_keep)

    b = sub.add_parser("source", help="search and generate what a brief asks for, into a new run folder")
    b.add_argument("brief", type=Path)
    b.add_argument("--plan", action="store_true", help="print each request and the estimated cost; send and write nothing")
    b.add_argument("--providers", help="only these providers, e.g. pexels,gemini")
    b.add_argument("--max-cost", type=float, default=2.0, help="refuse a run estimated above this many USD (default 2)")
    b.add_argument("--allow-unpriced", action="store_true", help="run providers with no published price, such as firefly")
    b.add_argument("--seed", type=int, help="the first seed of generations whose brief sets none (default: random)")
    b.add_argument("--out", type=Path, help="the directory runs go in (default: runs/ next to the brief)")
    b.set_defaults(run=run_source)

    args = ap.parse_args(argv)
    return args.run(ap, args)


def run_render(ap, args):
    if not args.creatives.is_file():
        ap.error(f"{args.creatives}: no such copy file")
    results, errors = render.run(args.creatives, out=args.out, design=args.design, country=args.country,
                                 variant=args.variant, size=args.size, check=args.check, force=args.force)
    for e in errors:
        print(f"FAIL  {e}")
    for res in results:
        print(f"{res.status:<5} {res.job.key}  {res.message}")
    failed = sum(res.status == "FAIL" for res in results)
    print(f"{len(results)} creatives, {failed} failed")
    return 1 if errors or failed else 0


def run_provenance_made(ap, args):
    """Writes every sidecar or, if any image cannot have one, none."""
    errors = []
    for image in args.images:
        if not image.is_file():
            errors.append(f"{image}: no such file")
        elif not provenance.image_refs([image.name]):
            errors.append(f"{image}: not an image")
        elif art.sidecar(image).exists():
            errors.append(f"{image}: already has provenance; edit or delete {art.sidecar(image).name} by hand")
    for e in errors:
        print(f"FAIL  {e}")
    if errors:
        return 1
    for image in args.images:
        art.write_sidecar(image, provenance.made(art.file_digest(image), args.by, args.rights))
        print(f"ok    {art.sidecar(image)}")
    return 0


def run_stock_search(ap, args):
    with sourcing.client() as http:
        try:
            found = sourcing.search(http, STOCK[args.provider], args.query, args.n)
        except MissingCredential as e:
            print(f"FAIL  {e}")
            return 1
        merged, sheets = sourcing.add_candidates(args.out, found, http)
    print(f"{len(found)} found, {len(merged)} candidates in {args.out / candidates.FILE}")
    for sheet in sheets:
        print(f"sheet {sheet}")
    return 0


def run_generate(ap, args):
    size = re.fullmatch(r"(\d+)x(\d+)", args.size)
    if not size:
        ap.error(f"--size {args.size!r}: expected <width>x<height>")
    provider = GENERATORS[args.provider]
    options = {}
    if provider is gemini:
        options["image_size"] = args.image_size or gemini.IMAGE_SIZE
    elif args.image_size:
        ap.error(f"--image-size applies to gemini, not {args.provider}")
    seed = secrets.randbelow(2**31) if args.seed is None else args.seed
    with sourcing.client() as http:
        try:
            found, refused, errors = sourcing.generate(http, provider, args.prompt, args.n, seed, int(size[1]),
                                                       int(size[2]), args.out, model=args.model, **options)
        except (MissingCredential, ValueError) as e:
            print(f"FAIL  {e}")
            return 1
        merged, sheets = sourcing.add_candidates(args.out, found, http)
    for e in refused + errors:
        print(f"FAIL  {e}")
    print(f"{len(found)} generated (seeds from {seed}), {len(merged)} candidates in {args.out / candidates.FILE}")
    for sheet in sheets:
        print(f"sheet {sheet}")
    return 1 if refused or errors else 0


def print_plan(jobs, costs, max_cost):
    for job, cost in zip(jobs, costs):
        price = "no published price" if cost is None else f"${cost:.2f}"
        count = f"{job.n} {'results' if job.kind == 'search' else 'images'}"
        print(f"plan  {job.need}/{job.provider} {job.kind}, {count}, {price}")
        for key, value in brief.describe(job).items():
            if key not in ("need", "provider", "kind", "n"):
                print(f"        {key}: {value}")
    estimate = sum(c for c in costs if c is not None)
    print(f"{len(jobs)} requests, estimated ${estimate:.2f} (--max-cost ${max_cost:.2f})")


def run_source(ap, args):
    if not args.brief.is_file():
        ap.error(f"{args.brief}: no such brief")
    only = None
    if args.providers is not None:
        only = [p.strip() for p in args.providers.split(",") if p.strip()]
        if not only:
            ap.error("--providers needs at least one provider name")
    seed = secrets.randbelow(2**31) if args.seed is None else args.seed
    jobs, costs, errors = runs.plan(args.brief, PROVIDERS, os.environ, only, seed, args.max_cost, args.allow_unpriced)
    if args.plan:
        print_plan(jobs, costs, args.max_cost)
    for e in errors:
        print(f"FAIL  {e}")
    if errors or args.plan:
        return 1 if errors else 0
    with sourcing.client() as http:
        run, records, errors = runs.source(args.brief, jobs, costs, PROVIDERS, http, os.environ, out=args.out)
    for r in records:
        found = f"{r['results']} results, {r['new']} new" if "results" in r else \
            f"{r['images']} images, {r['refused']} refused" if "images" in r else "nothing"
        print(f"done  {r['need']}/{r['provider']} {r['kind']}: {found} in {r['seconds']} s")
    for e in errors:
        print(f"FAIL  {e}")
    print(f"run {run}: {len(records)} requests, {len(errors)} errors")
    return 1 if errors else 0


def run_keep(ap, args):
    if not args.picked_by.strip():
        ap.error("--picked-by must name the person who picked")
    picks, errors = candidates.parse_picks(args.picks)
    written = []
    if picks:
        with sourcing.client() as http:
            written, keep_errors = sourcing.keep(args.candidates, picks, args.to, args.picked_by, http)
        errors += keep_errors
    for path in written:
        print(f"ok    {path}")
    for e in errors:
        print(f"FAIL  {e}")
    return 1 if errors else 0
