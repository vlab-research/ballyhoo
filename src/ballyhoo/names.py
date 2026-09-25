"""Runs' names, and candidates' names: `<run>.<n>`, such as 3.4, one name for an image on the review
page and in a thread.

Pure. A run folder is named `<date>-<number>`, numbered from 1 each day. A candidate's `n` counts
through its run: the needs in the order of the run's brief.yaml, and within each need its candidates
in candidates.yaml order. It is not candidates.yaml's own `n`, which starts again at 1 in every need.
The run part is the run's number where that picks one run, else its folder name: 2026-09-24-3.4 is
the full name of 3.4.
"""
import re

RUN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d+)")
NAME = re.compile(r"(?:(.+)\.)?(\d+)")


def run_name(name):
    """A run folder's (date, number), or None when the name is not `<date>-<n>`."""
    m = RUN_NAME.fullmatch(name)
    return (m[1], int(m[2])) if m else None


def run_order(names):
    """Run names newest first: by date, then number (2026-09-24-10 after -9); other names last."""
    named = sorted((n for n in names if run_name(n)), key=run_name, reverse=True)
    return named + sorted((n for n in names if not run_name(n)), reverse=True)


def numbers(order):
    """Each candidate's number in its run, from the run's needs in brief order, each with its candidate ids."""
    return {(need, id_): n for n, (need, id_) in enumerate(((need, id_) for need, ids in order for id_ in ids), 1)}


def runs_named(part, runs):
    """The runs a name's run part picks: the run of that folder name, else every run of that number."""
    if part in runs:
        return [part]
    return [r for r in runs if part.isdigit() and run_name(r) and run_name(r)[1] == int(part)]


def prefixes(runs):
    """Run -> the run part of its candidates' names among these runs: its number where that picks it alone."""
    short = {r: str(run_name(r)[1]) for r in runs if run_name(r)}
    return {r: short[r] if r in short and runs_named(short[r], runs) == [r] else r for r in runs}


def parse(name):
    """A candidate's name as (run part, or None for a bare number, number), or None when it is not a name."""
    m = NAME.fullmatch(name)
    return (m[1], int(m[2])) if m and int(m[2]) > 0 else None


def parse_picks(args):
    """`<name>` or `<name>=<file name>` arguments. Returns ([(name, file name or None)], errors)."""
    picks, errors = [], []
    for arg in args:
        name, eq, file = arg.partition("=")
        if parse(name) is None or (eq and not file):
            errors.append(f"{arg}: expected a candidate's name, such as 3.4 or 2026-09-24-3.4, "
                          "or <name>=<file name>")
        else:
            picks.append((name, file or None))
    return picks, errors


def pick_run(name, runs, single):
    """The run and number a name picks among `runs`. Returns ((run, number) or None, error or None).

    A bare number names a candidate only when there is a `single` run to find it in.
    """
    parsed = parse(name)
    if parsed is None:
        return None, f"{name}: not a candidate's name, such as 3.4 or 2026-09-24-3.4"
    part, number = parsed
    if part is None:
        if single:
            return (runs[0], number), None
        return None, f"{name}: name the run too, such as 3.{number}"
    matched = runs_named(part, runs)
    if not matched:
        return None, f"{name}: no run {part}" + (f" among {', '.join(run_order(runs))}" if runs else ": no runs")
    if len(matched) > 1:
        full = [f"{r}.{number}" for r in run_order(matched)]
        return None, f"{name}: runs {', '.join(run_order(matched))} are all numbered {part}; name one, such as {full[0]}"
    return (matched[0], number), None


def pick_candidate(name, run, number, order):
    """The (need, candidate id) a run's number names, given the run's needs in brief order with their
    candidate ids. Returns (pick or None, error or None)."""
    by_number = {n: pair for pair, n in numbers(order).items()}
    if number in by_number:
        return by_number[number], None
    if not by_number:
        return None, f"{name}: {run} has no candidates"
    return None, f"{name}: {run} has candidates {run}.1 to {run}.{len(by_number)}"
