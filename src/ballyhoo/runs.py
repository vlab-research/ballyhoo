"""Runs: a brief sourced into a new folder, which only preview and review write into afterwards.

The shell for brief.py, preview.py, verdicts.py and review.py. It reads the
brief and finds its templates, runs each source job through sourcing.py into its
need's folder (downloading stock originals), and writes the manifest. Previewing
a run renders each candidate into its need's templates through render.py,
writing previews/ and checks.yaml into the need's folder, and review.html into
the run. Reviewing reads what the page shows, merges each mark into verdicts.yaml, and keeps the
candidates it rates keep. The pure modules decide; this module carries it out.
"""
import asyncio
import datetime
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image
from playwright.async_api import async_playwright

from . import art, brief, cache, candidates, names, preview, render, review, sourcing, verdicts

BRIEF = "brief.yaml"
MANIFEST = "manifest.yaml"
RUNS = "runs"
TEMPLATE = Path(__file__).with_name(review.PAGE)


def load(path, providers, base=None):
    """The needs in a brief file, and its designs directory. Returns (needs, designs, errors).

    Relative paths resolve against `base`, by default the brief's own directory.
    """
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return [], None, [f"{path}: {e}"]
    root, errors = brief.designs_dir(data, path.parent if base is None else base)
    if errors:
        return [], None, [f"{path}: {e}" for e in errors]
    root = root.resolve()
    templates = {f"{t.parent.name}/{t.stem}" for t in root.glob("*/*.html")}
    needs, errors = brief.parse(data, templates, providers, root)
    return needs, root, errors


def plan(path, providers, env, only, seed, max_cost, allow_unpriced):
    """What sourcing a brief would send and cost, without sending anything.

    Returns (jobs, costs, errors). Run the jobs only when there are no errors.
    """
    needs, _, errors = load(path, providers)
    jobs, problems = brief.select(brief.expand(needs, providers, seed), only, providers)
    costs = [brief.cost(j, providers[j.provider]) for j in jobs]
    errors += problems + brief.request_problems(jobs, providers, env)
    errors += brief.spend_problems(jobs, costs, max_cost, allow_unpriced)
    return jobs, costs, errors


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    """A run's day, in UTC as its timestamps are: named for a local day, a run holds another day's manifest."""
    return datetime.datetime.now(datetime.timezone.utc).date()


def write_atomically(path, text):
    """Write a file whole, by renaming a finished temporary file over it, so no reader sees half of one."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def new_run(runs_dir, today):
    """A new, empty run folder. It is made without exist_ok, so two runs can never share one."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    run = runs_dir / brief.run_name(today, [p.name for p in runs_dir.iterdir()])
    run.mkdir()
    return run


def run_job(job, provider, directory, http, env, today, sleep, known):
    """Send one job's requests and add what they found to its need's folder.

    Returns (the manifest's record of the job, errors naming the job). `known` holds the candidate
    ids already in the folder: a photo that an earlier query found is counted as already found, is
    not downloaded again, keeps the earlier query in its record, and adds this query to its queries.
    """
    label = f"{job.need}/{job.provider} search {job.text!r}" if job.kind == "search" else \
        f"{job.need}/{job.provider} generate"
    record, problems = brief.describe(job), []
    start = time.monotonic()
    try:
        if job.kind == "search":
            results = sourcing.search(http, provider, job.text, job.n, env=env, **job.options)
            new = [c for c in results if c.id not in known]
            record.update(results=len(results), new=len(new), already_found=len(results) - len(new))
            found, problems = sourcing.download_originals(http, directory, new)
            found += [c for c in results if c.id in known]
        else:
            found, refused, problems = sourcing.generate(
                http, provider, job.text, job.n, job.seed, job.width, job.height, directory, env=env, today=today,
                sleep=sleep, model=job.model, style=job.style, **job.options)
            record.update(images=len(found), refused=len(refused))
            if job.drawing:
                record.update(cut_out=sum(c.cutout is not None for c in found),
                              mask_failed=sum(1 for c in found if c.cutout and not c.cutout.ok))
            problems = refused + problems
        merged, _ = sourcing.add_candidates(directory, found, http)
        known.update(c.id for c in merged)
    except Exception as e:  # whatever one provider does, the other jobs still run and the manifest is written
        problems.append(f"{type(e).__name__}: {e}")
    record["seconds"] = round(time.monotonic() - start, 1)
    return record, [f"{label}: {p}" for p in problems]


def source(path, jobs, costs, providers, http, env, out=None, today=None, sleep=time.sleep):
    """Run the jobs into a new run folder: a copy of the brief, a folder per need, and manifest.yaml.

    Returns (run folder, request records, errors). One job's failure is recorded and the others
    still run.
    """
    path = Path(path).resolve()
    today = today or _today()
    run = new_run(Path(out) if out else path.parent / RUNS, today)
    shutil.copyfile(path, run / BRIEF)
    started, records, errors, known = _now(), [], [], {}
    try:
        for job, cost in zip(jobs, costs):
            record, problems = run_job(job, providers[job.provider], run / job.need, http, env, today, sleep,
                                       known.setdefault(job.need, set()))
            records.append({**record, "estimated_usd": None if cost is None else round(cost, 4)})
            errors += problems
    finally:
        manifest = {"brief": os.path.relpath(path, run), "started": started, "finished": _now(),
                    "ballyhoo": render.package_digest(),
                    "estimated_cost_usd": round(sum(c for c in costs if c is not None), 4),
                    "requests": records, "errors": errors}
        write_atomically(run / MANIFEST, yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return run, records, errors


def _manifest(run):
    try:
        return yaml.safe_load((Path(run) / MANIFEST).read_text()), []
    except (OSError, yaml.YAMLError) as e:
        return None, [f"{run}: not a run folder: {e}"]


def read(run, providers):
    """What a run holds. Returns (needs, designs, found, checks, errors).

    `found` maps each need with a candidates file to its candidates, and `checks` each previewed
    need to its loaded checks.yaml.
    """
    run = Path(run)
    manifest, errors = _manifest(run)
    if errors:
        return [], None, {}, {}, errors
    # The run's copy of the brief keeps the original's relative paths, so they resolve beside the original.
    needs, designs, errors = load(run / BRIEF, providers, (run / manifest["brief"]).parent)
    found, checks = {}, {}
    for need in needs:
        path = run / need.name / candidates.FILE
        if path.is_file():
            found[need.name], problems = candidates.load(yaml.safe_load(path.read_text()))
            errors += [f"{path}: {p}" for p in problems]
        path = run / need.name / preview.CHECKS
        if path.is_file():
            checks[need.name] = yaml.safe_load(path.read_text())
    return needs, designs, found, checks, errors


def candidate_ids(found):
    return {need: [c.id for c in found_] for need, found_ in found.items()}


def read_verdicts(run, found, name=verdicts.FILE):
    """A run's verdicts.yaml, or with `name` its agent-verdicts.yaml, validated against its candidates.

    Returns (Verdicts, or None when the run has no such file, errors).
    """
    path = Path(run) / name
    if not path.is_file():
        return None, []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return None, [f"{path}: {e}"]
    parsed, errors = verdicts.parse(data, candidate_ids(found))
    return parsed, [f"{path}: {e}" for e in errors]


@dataclass(frozen=True)
class Review:
    """What a run's review page shows."""
    name: str        # the run folder's name
    needs: dict      # need -> what it asks for, in brief order
    found: dict      # need -> candidates, for each need with a candidates file
    checks: dict     # need -> loaded checks.yaml, for each previewed need
    verdicts: object  # verdicts.Verdicts from verdicts.yaml, or None
    agent: object     # verdicts.Verdicts from agent-verdicts.yaml, or None


def read_review(run, providers):
    """What a run's review page shows, as it is on disk. Returns (Review or None, errors)."""
    run = Path(run).resolve()
    needs, _, found, checks, errors = read(run, providers)
    person, problems = read_verdicts(run, found)
    agent, more = read_verdicts(run, found, verdicts.AGENT_FILE)
    errors += problems + more
    if errors:
        return None, errors
    return Review(run.name, {n.name: n.need for n in needs}, found, checks, person, agent), []


def is_run(path):
    """Whether a folder is a run: it has a manifest, or is named as one still being sourced."""
    return path.is_dir() and review.is_run(path.name, (path / MANIFEST).is_file())


def run_folders(runs_dir):
    """The runs in a runs directory, in no particular order."""
    return [p for p in Path(runs_dir).iterdir() if not p.name.startswith(".") and is_run(p)]


def _files(run):
    """Every file under a run as (path relative to it, modification time in ns)."""
    for directory, _, names in os.walk(run):
        for name in names:
            path = Path(directory) / name
            try:
                yield path.relative_to(run).as_posix(), path.stat().st_mtime_ns
            except FileNotFoundError:  # a temporary file renamed into place between listing and stat
                continue


def run_state(run):
    """A run's name, newest file time and status, as review.state takes them."""
    run = Path(run)
    folders = [p for p in run.iterdir() if p.is_dir()]
    return {"name": run.name, "mtime": review.newest(_files(run)),
            "status": review.run_status((run / MANIFEST).is_file(),
                                        [p.name for p in folders if (p / candidates.FILE).is_file()],
                                        [p.name for p in folders if (p / preview.CHECKS).is_file()])}


def served(root, single):
    """The runs a review server shows: the run itself, or every run in the runs directory."""
    return [Path(root)] if single else run_folders(root)


def state(root, single):
    """What /state answers: see review.state."""
    return review.state([run_state(run) for run in served(root, single)])


def _page_run(run, status, providers, base):
    """One run as review.page_data takes it. A run that cannot be read carries its errors instead of
    its data, so one broken run does not hide the others."""
    entry = {"name": run.name, "status": status, "errors": [], "requests": None, "data": None}
    if status == "sourcing":
        return entry
    try:
        manifest, errors = _manifest(run)
        if errors:
            return {**entry, "errors": errors}
        r, errors = read_review(run, providers)
    except (OSError, yaml.YAMLError) as e:  # a file being written as the page is read
        return {**entry, "errors": [f"{run}: {e}"]}
    entry["requests"] = manifest.get("requests") or []
    if errors:
        return {**entry, "errors": errors}
    return {**entry, "data": review.run_data(r.needs, r.found, r.checks, r.verdicts, r.agent, base)}


def served_page(root, single, providers):
    """The review page a server shows for a run, or for every run in a runs directory, as on disk now."""
    root = Path(root)
    entries, states = [], []
    for run in served(root, single):
        s = run_state(run)
        states.append(s)
        entries.append(_page_run(run, s["status"], providers, "" if single else f"{run.name}/"))
    data = review.page_data(entries, editable=True, digest=review.state(states)["digest"])
    return review.page(TEMPLATE.read_text(), data)


def summaries(runs_dir, providers, name=verdicts.FILE):
    """Every run in a runs directory as review.runs_summary_lines takes it, with its verdicts.yaml, or with
    `name` its agent-verdicts.yaml. A run that cannot be read carries its errors instead."""
    result = []
    for run in run_folders(runs_dir):
        status = run_state(run)["status"]
        entry = {"name": run.name, "status": status, "errors": [], "needs": [], "found": {}, "verdicts": None}
        if status != "sourcing":
            try:
                needs, _, found, _, errors = read(run, providers)
                rated, problems = read_verdicts(run, found, name) if not errors else (None, [])
            except (OSError, yaml.YAMLError) as e:  # a file being written as the runs are read
                errors, problems = [f"{run}: {e}"], []
            if errors or problems:
                entry["errors"] = errors + problems
            else:
                entry.update(needs=[n.name for n in needs], found=candidate_ids(found), verdicts=rated)
        result.append(entry)
    return result


def review_page(run, r):
    """The read-only review.html written into a run, showing that run alone."""
    s = run_state(run)
    entry = {"name": r.name, "status": s["status"], "errors": [], "requests": None,
             "data": review.run_data(r.needs, r.found, r.checks, r.verdicts, r.agent)}
    return review.page(TEMPLATE.read_text(),
                       review.page_data([entry], editable=False, digest=review.state([s])["digest"]))


def write_review(run, providers):
    """Write the run's read-only review.html. Returns errors, and writes nothing when there are any."""
    r, errors = read_review(run, providers)
    if not errors:
        write_atomically(Path(run) / review.PAGE, review_page(run, r))
    return errors


def save_mark(run, providers, mark, today):
    """Merge one mark the page posted into verdicts.yaml, or write nothing (see verdicts.merge).

    Returns (reply, errors): the reply names the file, who rated the run and when, and holds the new
    summary. A run left with no marks has its verdicts.yaml removed. review.html is rewritten to show
    the verdicts too.
    """
    run = Path(run).resolve()
    needs, _, found, checks, errors = read(run, providers)
    person, problems = read_verdicts(run, found)
    agent, more = read_verdicts(run, found, verdicts.AGENT_FILE)
    errors += problems + more
    if not errors:
        merged, errors = verdicts.merge(person, mark, candidate_ids(found), today)
    if errors:
        return None, errors
    if not verdicts.marked(merged):
        merged = None
        (run / verdicts.FILE).unlink(missing_ok=True)
    else:
        write_atomically(run / verdicts.FILE,
                         yaml.safe_dump(verdicts.dump(merged), sort_keys=False, allow_unicode=True))
    r = Review(run.name, {n.name: n.need for n in needs}, found, checks, merged, agent)
    write_atomically(run / review.PAGE, review_page(run, r))
    return {"saved": verdicts.FILE, "rated_by": merged.rated_by if merged else None,
            "rated_on": merged.rated_on.isoformat() if merged else None,
            "summary": review.summary(found, merged)}, []


def keep_verdicts(run, need, to_dir, providers, http):
    """Keep every candidate of `need` that verdicts.yaml rates keep, as picked by whoever rated it.

    The files are the run's own bytes. Returns (written paths, errors).
    """
    run = Path(run)
    _, _, found, _, errors = read(run, providers)
    person, problems = read_verdicts(run, found)
    errors += problems
    if errors:
        return [], errors
    ids, errors = verdicts.keep_plan(person, (run / verdicts.AGENT_FILE).is_file(), list(found), need)
    if errors:
        return [], errors
    return sourcing.keep(run / need / candidates.FILE, [(i, None) for i in ids], to_dir, person.rated_by, http,
                         today=person.rated_on, fetched=_fetched(run))


def _fetched(run):
    """The day a run's stock originals were downloaded: source downloads them as the run starts."""
    manifest, _ = _manifest(run)
    return datetime.date.fromisoformat(str(manifest["started"])[:10])


def resolve_names(path, picks, providers):
    """Which candidate each named pick is, among the runs at `path`: a run folder, where a bare number
    names a candidate too, a runs directory, or a brief, whose runs are the runs/ beside it.

    `picks` are (name, file name or None). Returns ([(name, run folder, need, candidate id, file name
    or None)], errors). A run is read only when a name picks it.
    """
    path = Path(path)
    single = is_run(path)
    root = path.parent / RUNS if path.is_file() else path
    folders = {p.name: p for p in ([path] if single else run_folders(root) if root.is_dir() else [])}
    orders, resolved, errors = {}, [], []
    for name, file in picks:
        found, error = names.pick_run(name, list(folders), single)
        if error:
            errors.append(error)
            continue
        run, number = found
        if run not in orders:
            needs, _, cands, _, problems = read(folders[run], providers)
            errors += problems
            orders[run] = None if problems else [(n.name, [c.id for c in cands.get(n.name, [])]) for n in needs]
        if orders[run] is None:
            errors.append(f"{name}: {run} cannot be read")
            continue
        pick, error = names.pick_candidate(name, run, number, orders[run])
        if error:
            errors.append(error)
        else:
            resolved.append((name, folders[run], *pick, file))
    return resolved, errors


def keep_named(path, picks, to_dir, picked_by, providers, http):
    """Keep the candidates that named picks name (see resolve_names), or nothing when any name picks none:
    one name that is wrong, such as a run number from another day, puts the others in doubt too.

    Returns ([(name, run folder, need, candidate id, written path)], errors).
    """
    resolved, errors = resolve_names(path, picks, providers)
    if errors:
        return [], errors
    written = []
    for name, run, need, id_, file in resolved:
        paths, problems = sourcing.keep(run / need / candidates.FILE, [(id_, file)], to_dir, picked_by, http,
                                        fetched=_fetched(run))
        written += [(name, run, need, id_, p) for p in paths]
        errors += [f"{name}: {p}" for p in problems]
    return written, errors


def template_problems(designs, name, slot):
    """What stops a template previewing a candidate in `slot`: no slot, or a file it shows that is
    missing or unsourced.

    The image in the slot is not shown in a preview, so it is not required. Any other image is, that
    slot's neighbour included: a drawing put into #figure still leaves the template's #scene showing.
    """
    path = designs / f"{name}.html"
    source = path.read_text()
    problems = preview.slot_problems(name, source, slot)
    if problems:
        return problems
    exempt = [preview.slot_src(source, slot)]
    missing = [r for r in cache.template_refs(source) if r not in exempt and not (path.parent / r).resolve().is_file()]
    return ([f"{name}: references missing file {r}" for r in missing]
            + [f"{name}: {p}" for p in art.unsourced_images(path, exempt)])


async def _render_preview(browser, sem, folder, designs, p):
    async with sem:
        try:
            image, failures, summary, _ = await render.render(browser, designs / f"{p.template}.html", p.copy,
                                                              (p.slot, folder / p.image))
        except Exception as e:  # attribute every failure to its preview
            return preview.Outcome(p, (), None, f"{type(e).__name__}: {e}")
    out = folder / p.file
    out.parent.mkdir(exist_ok=True)
    Image.fromarray(image).save(out)
    return preview.Outcome(p, tuple(failures), summary)


async def _render_previews(run, designs, previews):
    sem = asyncio.Semaphore(render.WORKERS)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=render.chrome_path(), args=render.CHROME_ARGS)
        try:
            return await asyncio.gather(*(_render_preview(browser, sem, run / p.need, designs, p) for p in previews))
        finally:
            await browser.close()


def render_previews(run, providers):
    """Render each candidate in a run into its need's preview templates, and check each render.

    Writes <need>/previews/, whatever the checks say, <need>/checks.yaml and the run's review.html;
    nothing outside the run, and not the manifest. Returns (outcomes, names of needs with no
    candidates, errors). When there are errors before rendering, nothing is rendered or written;
    a verdicts file that is not valid for the run is an error after rendering, and stops only
    review.html.
    """
    run = Path(run)
    needs, designs, found, _, errors = read(run, providers)
    checked = {pair: template_problems(designs, *pair) for pair in preview.wanted(needs, found)}
    previews, problems = preview.plan(needs, found, checked)
    errors += problems
    empty = [need.name for need in needs if need.name not in found]
    if errors:
        return [], empty, errors
    for name in found:
        for stale in (run / name / preview.PREVIEWS).glob("*.png"):
            stale.unlink()
    outcomes = asyncio.run(_render_previews(run, designs, previews))
    ballyhoo, previewed = render.package_digest(), _now()
    for need in needs:
        if need.name in found:
            data = preview.checks_data(need, [o for o in outcomes if o.preview.need == need.name], ballyhoo, previewed)
            write_atomically(run / need.name / preview.CHECKS, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return outcomes, empty, write_review(run, providers)
