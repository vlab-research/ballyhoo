"""The review page: runs' candidates, what the checks found and the verdicts, as data for review.html.

Pure. The shell loads each run's brief, manifest, each need's candidates.yaml
and checks.yaml, verdicts.yaml and agent-verdicts.yaml, and lists the files in
each run with their modification times. This module orders the runs, says which
have finished previewing and what each asked that the run before did not, digests
the runs' state so the page can tell a new round has arrived, and builds the
page's data, the summary of verdicts per need, provider and query or prompt, and
the page itself from the template. runs.py writes the page into a run;
review_server.py serves it for a run or a directory of runs.
"""
import difflib
import hashlib
import json
import re

from .preview import URL
from .verdicts import FILE, ISSUES, VERDICTS

PAGE = "review.html"
MARK = "__BALLYHOO_DATA__"  # where the template takes its data
RUN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d+)")
CONTEXT = 3  # words of unchanged prompt kept either side of a change


def run_name(name):
    """A run folder's (date, number), or None when the name is not `<date>-<n>`."""
    m = RUN_NAME.fullmatch(name)
    return (m[1], int(m[2])) if m else None


def is_run(name, has_manifest):
    """Whether a folder in a runs directory is a run: it has a manifest, or is named as one still being sourced."""
    return has_manifest or run_name(name) is not None


def run_order(names):
    """Run names newest first: by date, then number (2026-09-24-10 after -9); other names last."""
    named = sorted((n for n in names if run_name(n)), key=run_name, reverse=True)
    return named + sorted((n for n in names if not run_name(n)), reverse=True)


def newest(files):
    """The newest modification time among a run's files, given as (path relative to the run, mtime) pairs.

    The files the review page itself writes, verdicts.yaml and review.html, and temporary files
    are left out: a save must not look like a new round. None when no file counts.
    """
    times = [t for path, t in files
             if path not in (FILE, PAGE) and not any(part.startswith(".") for part in path.split("/"))]
    return max(times, default=None)


def run_status(has_manifest, with_candidates, previewed):
    """"sourcing" until the manifest is written, "previewing" until every need with candidates has a
    checks.yaml, then "ready". `with_candidates` and `previewed` are need folder names."""
    if not has_manifest:
        return "sourcing"
    return "ready" if set(with_candidates) <= set(previewed) else "previewing"


def state(runs):
    """What the page polls to notice a new round: each run's name, newest file time and status, newest
    run first, and a digest of them to compare. `runs` holds {"name", "mtime", "status"} dicts."""
    by_name = {r["name"]: r for r in runs}
    ordered = [by_name[n] for n in run_order(list(by_name))]
    digest = hashlib.sha256(json.dumps(ordered, sort_keys=True).encode()).hexdigest()[:16]
    return {"runs": ordered, "digest": digest}


def asks(requests):
    """What a run asked each provider for, from its manifest's requests: need -> (kind, provider) -> texts."""
    result = {}
    for r in requests:
        text = r["query"] if r["kind"] == "search" else r["prompt"]
        texts = result.setdefault(r["need"], {}).setdefault((r["kind"], r["provider"]), [])
        if text not in texts:
            texts.append(text)
    return result


def word_diff(before, after, context=CONTEXT):
    """Two texts' difference by word: ["=", "-" or "+", text] segments, with unchanged runs of more
    than `context` words either side of a change cut to them and "…"."""
    a, b = before.split(), after.split()
    segments = []
    opcodes = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    for n, (op, i1, i2, j1, j2) in enumerate(opcodes):
        if op == "equal":
            words = a[i1:i2]
            first, last = n == 0, n == len(opcodes) - 1
            if first and last:
                keep = words
            elif first:
                keep = (["…"] + words[-context:]) if len(words) > context else words
            elif last:
                keep = (words[:context] + ["…"]) if len(words) > context else words
            else:
                keep = (words[:context] + ["…"] + words[-context:]) if len(words) > 2 * context + 1 else words
            segments.append(["=", " ".join(keep)])
        else:
            if i2 > i1:
                segments.append(["-", " ".join(a[i1:i2])])
            if j2 > j1:
                segments.append(["+", " ".join(b[j1:j2])])
    return segments


def changes(before, after):
    """What a run asked that the run before it did not, per need, from both runs' `asks`.

    A list of {"need", "change"}: "new" or "gone" for a need only one run asked for; otherwise
    "changed" with "asks", one per kind and provider that differ, each {"kind", "provider"} with
    "diff" (word_diff) when one prompt or query became another, else "added" and "removed" texts.
    """
    result = []
    for need in [*after, *(n for n in before if n not in after)]:
        if need not in before:
            result.append({"need": need, "change": "new"})
        elif need not in after:
            result.append({"need": need, "change": "gone"})
        else:
            differ = []
            for key in [*after[need], *(k for k in before[need] if k not in after[need])]:
                old, new = before[need].get(key, []), after[need].get(key, [])
                added, removed = [t for t in new if t not in old], [t for t in old if t not in new]
                if not added and not removed:
                    continue
                entry = {"kind": key[0], "provider": key[1]}
                if len(added) == len(removed) == 1:
                    entry["diff"] = word_diff(removed[0], added[0])
                else:
                    entry.update(added=added, removed=removed)
                differ.append(entry)
            if differ:
                result.append({"need": need, "change": "changed", "asks": differ})
    return result


def _counts(verdicts):
    """Tallies of some candidates' verdicts, where None means unrated."""
    rated = [v for v in verdicts if v is not None]
    return {"candidates": len(verdicts), **{name: sum(v.verdict == name for v in rated) for name in VERDICTS},
            "unrated": len(verdicts) - len(rated),
            "issues": {i: n for i in ISSUES if (n := sum(i in v.issues for v in rated))}}


def summary(found, verdicts):
    """Per need, per provider, and per query or prompt: the candidates found and their verdicts' tallies.

    `found` maps each need with candidates to them; `verdicts` may be None, when every candidate is
    unrated. A candidate that several queries found counts once in its need and provider, and once
    in each of those queries.
    """
    result = {}
    for need, candidates in found.items():
        rated = [verdicts.get(need, c.id) if verdicts else None for c in candidates]
        providers = {}
        for c, verdict in zip(candidates, rated):
            p = providers.setdefault(c.provenance.get("provider"), {"all": [], "queries": {}, "prompts": {}})
            p["all"].append(verdict)
            for query in c.queries:
                p["queries"].setdefault(query, []).append(verdict)
            if c.provenance.get("prompt"):
                p["prompts"].setdefault(c.provenance["prompt"], []).append(verdict)
        result[need] = {**_counts(rated), "providers": {
            name: {**_counts(p["all"]),
                   **{kind: {text: _counts(v) for text, v in p[kind].items()} for kind in ("queries", "prompts") if p[kind]}}
            for name, p in providers.items()}}
    return result


def _tally(counts):
    rate = f" ({counts['keep'] / counts['candidates']:.0%})" if counts["candidates"] else ""
    issues = ", ".join(f"{i} {n}" for i, n in counts["issues"].items())
    return (f"{counts['candidates']} found, {counts['keep']} keep{rate}, {counts['maybe']} maybe, "
            f"{counts['drop']} drop, {counts['unrated']} unrated" + (f"; issues: {issues}" if issues else ""))


def summary_lines(summary):
    """The summary as `ballyhoo review --summary` prints it."""
    lines = []
    for need, s in summary.items():
        lines.append(f"{need}: {_tally(s)}")
        for provider, p in s["providers"].items():
            lines.append(f"  {provider}: {_tally(p)}")
            for kind, label in (("queries", "query"), ("prompts", "prompt")):
                lines += [f"    {label} {text!r}: {_tally(counts)}" for text, counts in p.get(kind, {}).items()]
    return lines


def _path(folder, ref):
    """A file in a need's folder as a path relative to the page; a URL as it is."""
    return ref if ref.startswith(URL) else f"{folder}/{ref}"


def _verdict(v):
    return None if v is None else {"verdict": v.verdict, "issues": list(v.issues), "note": v.note}


def _candidate(need, folder, c, checked, verdicts, agent):
    record = c.provenance
    return {
        "id": c.id, "width": c.width, "height": c.height, "thumb": _path(folder, c.thumb),
        "full": _path(folder, c.full),
        "source": record.get("source"), "provider": record.get("provider"),
        "queries": list(c.queries), "prompt": record.get("prompt"),
        "alt": record.get("alt") or record.get("title"),  # Pexels describes a photo in alt, Openverse in title
        **{k: record.get(k) for k in ("creator", "creator_url", "page_url", "licence", "licence_url", "model", "seed",
                                      "style")},
        "cutout": c.cutout and {"file": _path(folder, c.cutout.file), "key": list(c.cutout.key),
                                "pass": c.cutout.ok, "failures": list(c.cutout.failures)},
        "previewed": checked is not None,
        "pass": checked.get("pass") if checked else None,
        "previews": [{"template": template, "status": p.get("status"),
                      "file": _path(folder, p["file"]) if p.get("file") else None,
                      "summary": p.get("summary"), "failures": list(p.get("failures", []))}
                     for template, p in (checked or {}).get("previews", {}).items()],
        "verdict": _verdict(verdicts.get(need, c.id) if verdicts else None),
        "agent": _verdict(agent.get(need, c.id) if agent else None),
    }


def run_data(needs, found, checks, verdicts, agent, base=""):
    """One run's part of the review page's data.

    `needs` maps each need in the run's brief to its text, in brief order; `found` maps each need
    with a candidates file to its candidates; `checks` maps each previewed need to its loaded
    checks.yaml; `verdicts` and `agent` are the run's verdicts and agent verdicts, or None. `base`
    is the run folder's path from the page, with its trailing slash: empty for a page in the run.
    """
    tallies = summary(found, verdicts)
    return {
        "rated_by": verdicts.rated_by if verdicts else None,
        "rated_on": verdicts.rated_on.isoformat() if verdicts else None,
        "agent": {"rated_by": agent.rated_by, "rated_on": agent.rated_on.isoformat()} if agent else None,
        "needs": [{"name": name, "need": text, "has_candidates": name in found, "previewed": name in checks,
                   "copy": checks[name].get("copy") if name in checks else None, "summary": tallies.get(name),
                   "candidates": [_candidate(name, f"{base}{name}", c,
                                             checks.get(name, {}).get("candidates", {}).get(c.id), verdicts, agent)
                                  for c in found.get(name, [])]}
                  for name, text in needs.items()],
    }


def page_data(runs, editable, digest):
    """The review page's data: its runs newest first, the newest sourced one open and the rest folded.

    Each of `runs` is {"name", "status", "errors", "requests", "data"}: `requests` is the manifest's,
    or None when there is no readable manifest; `data` is run_data, or None when the run cannot be
    shown yet or has errors. Each run's changes are against the next older run with requests, and
    None for the oldest. `editable` says whether a server is behind the page to save to; `digest` is
    the state digest the page compares with /state's.
    """
    by_name = {r["name"]: r for r in runs}
    ordered = [by_name[n] for n in run_order(list(by_name))]
    opened = next((r["name"] for r in ordered if r["status"] != "sourcing"), None)
    shown = []
    for i, r in enumerate(ordered):
        older = next((o for o in ordered[i + 1:] if o["requests"] is not None), None)
        date, number = run_name(r["name"]) or (None, None)
        shown.append({
            "name": r["name"], "date": date, "number": number, "status": r["status"], "errors": list(r["errors"]),
            "open": r["name"] == opened,
            "changes": changes(asks(older["requests"]), asks(r["requests"]))
            if older and r["requests"] is not None else None,
            **(r["data"] or {"rated_by": None, "rated_on": None, "agent": None, "needs": []})})
    return {"editable": editable, "verdicts": list(VERDICTS), "issues": dict(ISSUES), "state": digest, "runs": shown}


def page(template, data):
    """The review page: the template with its data embedded as JSON.

    `<` is escaped so that no text in the data, such as a note holding "</script>", can end the element.
    """
    if template.count(MARK) != 1:
        raise ValueError(f"the review page template must hold {MARK} exactly once")
    return template.replace(MARK, json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
