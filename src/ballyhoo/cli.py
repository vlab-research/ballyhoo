import argparse
from pathlib import Path

from . import render


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
    args = ap.parse_args(argv)

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
