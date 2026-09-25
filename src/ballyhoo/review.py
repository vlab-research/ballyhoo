"""The review pages: a run's candidates, what the checks found and the verdicts, as data for the templates.

Pure. The shell loads the run's brief, each need's candidates.yaml and
checks.yaml, verdicts.yaml, agent-verdicts.yaml and comparisons.yaml. This
module builds each page's data, the summary of verdicts per need, provider and
query or prompt, and the page itself from its template. runs.py writes the
review page into the run; review_server.py serves both.
"""
import json

from . import comparisons
from .preview import URL
from .verdicts import ISSUES, VERDICTS

PAGE = "review.html"
PAIRS_PAGE = "review-pairs.html"
MARK = "__BALLYHOO_DATA__"  # where a template takes its data


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


def ranking_lines(ranking):
    """A need's ranking as `ballyhoo review --summary --pairs` prints it, best first."""
    lines = []
    for place, r in enumerate(ranking, 1):
        stands = "never compared" if r["score"] is None else \
            f"score {r['score']:.2f}, {r['comparisons']} comparisons ({r['wins']}W {r['losses']}L {r['ties']}T)"
        lines.append(f"{'   -' if r['score'] is None else f'{place:4}'}. {r['id']}  {stands}")
    return lines


def _path(need, ref):
    """A file in a need's folder as a path relative to the run, where the page is; a URL as it is."""
    return ref if ref.startswith(URL) else f"{need}/{ref}"


def _verdict(v):
    return None if v is None else {"verdict": v.verdict, "issues": list(v.issues), "note": v.note}


def _candidate(need, c, checked, verdicts, agent):
    record = c.provenance
    return {
        "id": c.id, "width": c.width, "height": c.height, "thumb": _path(need, c.thumb), "full": _path(need, c.full),
        "source": record.get("source"), "provider": record.get("provider"),
        "queries": list(c.queries), "prompt": record.get("prompt"),
        "alt": record.get("alt") or record.get("title"),  # Pexels describes a photo in alt, Openverse in title
        **{k: record.get(k) for k in ("creator", "creator_url", "page_url", "licence", "licence_url", "model", "seed")},
        "previewed": checked is not None,
        "pass": checked.get("pass") if checked else None,
        "previews": [{"template": template, "status": p.get("status"),
                      "file": _path(need, p["file"]) if p.get("file") else None,
                      "summary": p.get("summary"), "failures": list(p.get("failures", []))}
                     for template, p in (checked or {}).get("previews", {}).items()],
        "verdict": _verdict(verdicts.get(need, c.id) if verdicts else None),
        "agent": _verdict(agent.get(need, c.id) if agent else None),
    }


def page_data(run, needs, found, checks, verdicts, agent, editable):
    """The review page's data.

    `run` is the run's name; `needs` maps each need in the brief to its text, in brief order; `found`
    maps each need with a candidates file to its candidates; `checks` maps each previewed need to its
    loaded checks.yaml; `verdicts` and `agent` are the run's verdicts and agent verdicts, or None.
    `editable` says whether a server is behind the page to save to.
    """
    tallies = summary(found, verdicts)
    return {
        "run": run, "editable": editable, "verdicts": list(VERDICTS), "issues": dict(ISSUES),
        "rated_by": verdicts.rated_by if verdicts else None,
        "rated_on": verdicts.rated_on.isoformat() if verdicts else None,
        "agent": {"rated_by": agent.rated_by, "rated_on": agent.rated_on.isoformat()} if agent else None,
        "needs": [{"name": name, "need": text, "has_candidates": name in found, "previewed": name in checks,
                   "copy": checks[name].get("copy") if name in checks else None, "summary": tallies.get(name),
                   "candidates": [_candidate(name, c, checks.get(name, {}).get("candidates", {}).get(c.id),
                                             verdicts, agent) for c in found.get(name, [])]}
                  for name, text in needs.items()],
    }


def _pair_candidate(need, c, checked):
    """One candidate as the pairwise page shows it: the ad it makes if it has been previewed, else the image itself."""
    rendered = [p for p in (checked or {}).get("previews", {}).values() if p.get("file")]
    return {"id": c.id, "alt": c.provenance.get("alt") or c.provenance.get("title") or c.id,
            "image": _path(need, rendered[0]["file"] if rendered else c.thumb),
            "previewed": bool(rendered)}


def ranking_data(ranking):
    """A need's ranking as the page shows it, best first."""
    return [{"id": r.id, "score": r.score, "comparisons": r.comparisons,
             "wins": r.wins, "losses": r.losses, "ties": r.ties} for r in ranking]


def need_state(candidate_ids, made):
    """A need's progress, the pair to compare next and the ranking so far: what a page shows and each save returns."""
    p = comparisons.progress(candidate_ids, made)
    return {"done": p.done, "budget": p.budget, "seen": p.seen, "candidates": p.candidates,
            "pair": list(p.pair) if p.pair else None, "ranking": ranking_data(comparisons.rank(candidate_ids, made))}


def pairs_data(run, needs, found, checks, made):
    """The pairwise page's data: per need, its candidates and where its comparisons have got to.

    A need with no candidates is left out, since there is nothing to compare. `made` is the run's
    comparisons, or None when nobody has compared yet.
    """
    return {
        "run": run, "winners": list(comparisons.WINNERS),
        "rated_by": made.rated_by if made else None,
        "rated_on": made.rated_on.isoformat() if made else None,
        "needs": [{"name": name, "need": needs[name],
                   "candidates": [_pair_candidate(name, c, checks.get(name, {}).get("candidates", {}).get(c.id))
                                  for c in found[name]],
                   "state": need_state([c.id for c in found[name]], made.of(name) if made else [])}
                  for name in needs if name in found],
    }


def page(template, data):
    """The review page: the template with its data embedded as JSON.

    `<` is escaped so that no text in the data, such as a note holding "</script>", can end the element.
    """
    if template.count(MARK) != 1:
        raise ValueError(f"the review page template must hold {MARK} exactly once")
    return template.replace(MARK, json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"))
