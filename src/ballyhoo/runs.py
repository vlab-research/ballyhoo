"""Runs: a brief sourced into a new folder, which nothing writes into afterwards.

The shell for brief.py. It reads the brief and finds its templates, runs each
source job through sourcing.py into its need's folder (downloading stock
originals), and writes the manifest. brief.py decides what runs and whether it
may; this module carries it out.
"""
import datetime
import os
import shutil
import time
from pathlib import Path

import yaml

from . import brief, render, sourcing

BRIEF = "brief.yaml"
MANIFEST = "manifest.yaml"
RUNS = "runs"


def load(path, providers):
    """The needs in a brief file. Returns (needs, errors)."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        return [], [f"{path}: {e}"]
    root, errors = brief.designs_dir(data, path.parent)
    if errors:
        return [], [f"{path}: {e}" for e in errors]
    root = root.resolve()
    templates = {f"{t.parent.name}/{t.stem}" for t in root.glob("*/*.html")}
    return brief.parse(data, templates, providers, root)


def plan(path, providers, env, only, seed, max_cost, allow_unpriced):
    """What sourcing a brief would send and cost, without sending anything.

    Returns (jobs, costs, errors). Run the jobs only when there are no errors.
    """
    needs, errors = load(path, providers)
    jobs, problems = brief.select(brief.expand(needs, providers, seed), only, providers)
    costs = [brief.cost(j, providers[j.provider]) for j in jobs]
    errors += problems + brief.request_problems(jobs, providers, env)
    errors += brief.spend_problems(jobs, costs, max_cost, allow_unpriced)
    return jobs, costs, errors


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    not downloaded again, and keeps the earlier query in its record.
    """
    label = f"{job.need}/{job.provider} search {job.text!r}" if job.kind == "search" else \
        f"{job.need}/{job.provider} generate"
    record, problems = brief.describe(job), []
    start = time.monotonic()
    try:
        if job.kind == "search":
            results = sourcing.search(http, provider, job.text, job.n, env=env)
            new = [c for c in results if c.id not in known]
            record.update(results=len(results), new=len(new), already_found=len(results) - len(new))
            found, problems = sourcing.download_originals(http, directory, new)
        else:
            found, refused, problems = sourcing.generate(
                http, provider, job.text, job.n, job.seed, job.width, job.height, directory, env=env, today=today,
                sleep=sleep, model=job.model, **job.options)
            record.update(images=len(found), refused=len(refused))
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
    today = today or datetime.date.today()
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
        (run / MANIFEST).write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return run, records, errors
