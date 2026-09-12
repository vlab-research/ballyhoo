import argparse
import re
import secrets
from pathlib import Path

from . import art, candidates, provenance, render, sourcing
from .providers import MissingCredential, gemini, openverse, pexels

STOCK = {"openverse": openverse, "pexels": pexels}
GENERATORS = {"gemini": gemini}


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
    g.add_argument("--model", help=f"default: {gemini.MODEL}")
    g.add_argument("--image-size", choices=gemini.IMAGE_SIZES, default="2K", help="Gemini's resolution (default 2K)")
    g.add_argument("--out", type=Path, required=True, help="the candidates directory; images are appended")
    g.set_defaults(run=run_generate)

    k = sub.add_parser("keep", help="copy picked candidates into the art library with their provenance")
    k.add_argument("candidates", type=Path, help="a candidates.yaml")
    k.add_argument("picks", nargs="+", help="<candidate id> or <candidate id>=<file name>")
    k.add_argument("--to", type=Path, required=True, help="the art directory, e.g. scenes/")
    k.add_argument("--picked-by", required=True, help="the person who picked them")
    k.set_defaults(run=run_keep)

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
    seed = secrets.randbelow(2**31) if args.seed is None else args.seed
    with sourcing.client() as http:
        try:
            found, errors = sourcing.generate(http, GENERATORS[args.provider], args.prompt, args.n, seed,
                                              int(size[1]), int(size[2]), args.out, model=args.model,
                                              image_size=args.image_size)
        except (MissingCredential, ValueError) as e:
            print(f"FAIL  {e}")
            return 1
        merged, sheets = sourcing.add_candidates(args.out, found, http)
    for e in errors:
        print(f"FAIL  {e}")
    print(f"{len(found)} generated (seeds from {seed}), {len(merged)} candidates in {args.out / candidates.FILE}")
    for sheet in sheets:
        print(f"sheet {sheet}")
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
