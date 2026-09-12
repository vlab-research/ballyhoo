import argparse
from pathlib import Path

from . import art, provenance, render


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
