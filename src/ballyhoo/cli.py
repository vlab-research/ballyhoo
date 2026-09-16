import argparse
import os
import re
import secrets
from pathlib import Path

from . import art, brief, candidates, provenance, render, review, review_server, runs, sourcing, verdicts
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
    q.add_argument("--orientation", choices=pexels.ORIENTATIONS, help="pexels only: the shape of the results")
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

    k = sub.add_parser("keep", help="copy picked candidates into the art library with their provenance",
                       usage="ballyhoo keep CANDIDATES PICK... --to DIR --picked-by NAME\n"
                             "       ballyhoo keep RUN --verdicts --need NEED --to DIR")
    k.add_argument("path", metavar="CANDIDATES|RUN", type=Path, help="a candidates.yaml; with --verdicts, a run folder")
    k.add_argument("picks", nargs="*", help="<candidate id> or <candidate id>=<file name>")
    k.add_argument("--to", type=Path, required=True, help="the art directory, e.g. scenes/")
    k.add_argument("--picked-by", help="the person who picked them")
    k.add_argument("--verdicts", action="store_true",
                   help="keep every candidate of --need that the run's verdicts.yaml rates keep, picked by whoever rated")
    k.add_argument("--need", help="with --verdicts: the need whose keeps to keep")
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

    v = sub.add_parser("preview", help="render a run's candidates into its brief's preview templates, and check them")
    v.add_argument("folder", metavar="run", type=Path, help="a run folder that source made")
    v.set_defaults(run=run_preview)

    w = sub.add_parser("review", help="serve a run's review page on 127.0.0.1, where a person rates its candidates")
    w.add_argument("folder", metavar="run", type=Path, help="a run folder that source made")
    w.add_argument("--port", type=int, default=0, help="the port to serve on (default 0: any free port)")
    w.add_argument("--summary", action="store_true",
                   help="print keep, maybe and drop counts per need, provider and query or prompt, and exit")
    w.add_argument("--agent", action="store_true", help=f"with --summary: count {verdicts.AGENT_FILE} instead")
    w.set_defaults(run=run_review)

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
    provider = STOCK[args.provider]
    options = {}
    if args.orientation:
        if "orientation" not in getattr(provider, "SEARCH_OPTIONS", ()):
            takes = sorted(n for n, p in STOCK.items() if "orientation" in getattr(p, "SEARCH_OPTIONS", ()))
            ap.error(f"--orientation applies to {', '.join(takes)}, not {args.provider}")
        options["orientation"] = args.orientation
    with sourcing.client() as http:
        try:
            found = sourcing.search(http, provider, args.query, args.n, **options)
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


def run_preview(ap, args):
    if not args.folder.is_dir():
        ap.error(f"{args.folder}: no such run folder")
    outcomes, empty, errors = runs.render_previews(args.folder, PROVIDERS)
    for name in empty:
        print(f"skip  {name}: no candidates in this run")
    for o in outcomes:
        p = o.preview
        detail = o.error or ("; ".join(o.failures) + f" [{o.summary}]" if o.failures else o.summary)
        print(f"{o.status:<5} {p.need}/{p.candidate} {p.template}  {detail}")
    for e in errors:
        print(f"FAIL  {e}")
    if errors:
        return 1
    count = {s: sum(o.status == s for o in outcomes) for s in ("pass", "fail", "error")}
    print(f"{len(outcomes)} previews: {count['pass']} pass, {count['fail']} fail, {count['error']} errors")
    return 1 if count["error"] else 0


def run_review(ap, args):
    if not args.folder.is_dir():
        ap.error(f"{args.folder}: no such run folder")
    if args.agent and not args.summary:
        ap.error("--agent applies only with --summary: the page shows the agent's verdicts as hints")
    r, errors = runs.read_review(args.folder, PROVIDERS)
    for e in errors:
        print(f"FAIL  {e}")
    if errors:
        return 1
    if args.summary:
        name, rated = (verdicts.AGENT_FILE, r.agent) if args.agent else (verdicts.FILE, r.verdicts)
        print(f"{name}: rated by {rated.rated_by} on {rated.rated_on}" if rated else
              f"{name}: none in this run, so every candidate is unrated")
        for need in r.needs:
            if need not in r.found:
                print(f"skip  {need}: no candidates in this run")
        for line in review.summary_lines(review.summary(r.found, rated)):
            print(line)
        return 0
    server = review_server.make_server(args.folder, PROVIDERS, args.port)
    print(f"review {args.folder} at {review_server.url(server)}  (saves {args.folder / verdicts.FILE}; Ctrl+C stops)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def run_keep(ap, args):
    if args.verdicts:
        if args.picks or args.picked_by is not None:
            ap.error(f"--verdicts takes the picks, and who picked them, from the run's {verdicts.FILE}: "
                     "name no picks and no --picked-by")
        if not args.need:
            ap.error("--verdicts needs --need: the need whose keeps to keep")
        if not args.path.is_dir():
            ap.error(f"{args.path}: no such run folder")
        with sourcing.client() as http:
            written, errors = runs.keep_verdicts(args.path, args.need, args.to, PROVIDERS, http)
    else:
        if args.need:
            ap.error("--need applies only with --verdicts")
        if not args.picks:
            ap.error("name at least one pick, or keep what a run's verdicts rate keep with --verdicts --need")
        if args.picked_by is None or not args.picked_by.strip():
            ap.error("--picked-by must name the person who picked")
        picks, errors = candidates.parse_picks(args.picks)
        written = []
        if picks:
            with sourcing.client() as http:
                written, keep_errors = sourcing.keep(args.path, picks, args.to, args.picked_by, http)
            errors += keep_errors
    for path in written:
        print(f"ok    {path}")
    for e in errors:
        print(f"FAIL  {e}")
    return 1 if errors else 0
