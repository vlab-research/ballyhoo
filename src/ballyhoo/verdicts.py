"""Verdicts: a person's rating of each candidate in a run, against its need.

Pure. verdicts.yaml is the one human input ballyhoo reads: the review page
writes it, and `keep --verdicts` takes its picks from it. An agent may rate a
run too, in agent-verdicts.yaml, in the same format; the page shows those as
hints, and they are never picks, because a pick names a person. The shell
loads the files and knows the run's candidates; this module decides whether a
verdicts map is valid, and what it picks.
"""
import datetime
from dataclasses import dataclass

FILE = "verdicts.yaml"
AGENT_FILE = "agent-verdicts.yaml"
VERDICTS = ("keep", "maybe", "drop")
ISSUES = {
    "minor": "someone could read as under 18",
    "age": "someone reads as older than middle age",
    "text": "text or lettering in the image",
    "tourist": "tourist imagery: landmarks, postcard scenes",
    "poverty": "poverty imagery",
    "artefact": "a visible artefact: hands, phones, faces",
    "off-brief": "does not show what the need asks for",
    "style": "clashes with the campaign",
    "brand": "a visible brand or logo",
    "crop": "no room for the headline",
}
KEYS = ("rated_by", "rated_on", "needs")
ENTRY_KEYS = ("verdict", "issues", "note")


@dataclass(frozen=True)
class Verdict:
    verdict: str        # keep, maybe or drop
    issues: tuple = ()  # from ISSUES
    note: str | None = None


@dataclass(frozen=True)
class Verdicts:
    rated_by: str
    rated_on: datetime.date
    needs: dict  # need -> candidate id -> Verdict

    def get(self, need, candidate):
        return self.needs.get(need, {}).get(candidate)


def _date(value):
    """A date from YAML (a date) or JSON (an ISO string); None if it is not one. A time of day is not a date."""
    if isinstance(value, datetime.datetime):
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _unknown(where, raw, allowed):
    unknown = [k for k in raw if k not in allowed]
    return [f"{where}unknown key{'s' if len(unknown) > 1 else ''} {', '.join(repr(k) for k in unknown)}"] \
        if unknown else []


def _entry(where, raw):
    """One candidate's verdict. Returns (Verdict or None, errors)."""
    if not isinstance(raw, dict):
        return None, [f"{where}: expected a map with verdict, and optionally issues and note"]
    errors = _unknown(f"{where}: ", raw, ENTRY_KEYS)
    if raw.get("verdict") not in VERDICTS:
        errors.append(f"{where}: verdict must be keep, maybe or drop, not {raw.get('verdict')!r}")
    issues = raw.get("issues", [])
    if not isinstance(issues, list):
        errors.append(f"{where}: issues must be a list")
        issues = []
    for issue in issues:
        if issue not in ISSUES:
            errors.append(f"{where}: unknown issue {issue!r} (known: {', '.join(ISSUES)})")
    if len(set(map(str, issues))) < len(issues):
        errors.append(f"{where}: an issue is listed twice")
    note = raw.get("note")
    if note is not None and not isinstance(note, str):
        errors.append(f"{where}: note must be text")
    if errors:
        return None, errors
    return Verdict(raw["verdict"], tuple(issues), (note or "").strip() or None), []


def parse(data, run):
    """Validate a loaded verdicts map. Returns (Verdicts or None, errors); every problem is reported.

    `run` maps each need that has candidates to its candidates' ids.
    """
    if not isinstance(data, dict):
        return None, ["expected a map with rated_by, rated_on and needs"]
    errors = _unknown("", data, KEYS)
    rated_by = data.get("rated_by")
    if not isinstance(rated_by, str) or not rated_by.strip():
        errors.append("rated_by is required: the name of whoever rated")
    rated_on = _date(data.get("rated_on"))
    if rated_on is None:
        errors.append(f"rated_on must be a date, e.g. 2026-09-14, not {data.get('rated_on')!r}")
    raw_needs = data.get("needs", {})
    if not isinstance(raw_needs, dict):
        return None, errors + ["needs must be a map of need -> candidate id -> verdict"]
    needs = {}
    for need, raw in raw_needs.items():
        if need not in run:
            errors.append(f"{need}: not a need with candidates in this run")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{need}: expected a map of candidate id -> verdict")
            continue
        needs[need] = {}
        for candidate, entry in raw.items():
            where = f"{need}/{candidate}"
            verdict, problems = _entry(where, entry)
            if candidate not in run[need]:
                problems.insert(0, f"{where}: not a candidate of {need} in this run")
            errors += problems
            if verdict and not problems:
                needs[need][candidate] = verdict
    if errors:
        return None, errors
    return Verdicts(rated_by.strip(), rated_on, needs), []


def dump(verdicts):
    """A verdicts map as data, for YAML: empty issues and notes are left out."""
    return {"rated_by": verdicts.rated_by, "rated_on": verdicts.rated_on,
            "needs": {need: {c: {"verdict": v.verdict, **({"issues": list(v.issues)} if v.issues else {}),
                                 **({"note": v.note} if v.note else {})}
                             for c, v in entries.items()}
                      for need, entries in verdicts.needs.items()}}


def as_json(verdicts):
    """A verdicts map as data for JSON, whose dates are strings."""
    return {**dump(verdicts), "rated_on": verdicts.rated_on.isoformat()}


def picks(verdicts, need):
    """The ids of the need's candidates rated keep."""
    return [c for c, v in verdicts.needs.get(need, {}).items() if v.verdict == "keep"]


def keep_plan(verdicts, agent_rated, needs, need):
    """The candidates `keep --verdicts --need` keeps. Returns (ids, errors).

    `verdicts` is the run's verdicts.yaml, None when it has none; `agent_rated` says whether it has
    agent-verdicts.yaml; `needs` holds the needs with candidates.
    """
    if verdicts is None:
        why = (f"{AGENT_FILE} is not picks: a pick names the person who made it, so a person rates in {FILE}"
               if agent_rated else "rate the run first: ballyhoo review RUN")
        return [], [f"no {FILE} in this run; {why}"]
    if need not in needs:
        return [], [f"{need}: not a need with candidates in this run (needs: {', '.join(needs) or 'none'})"]
    ids = picks(verdicts, need)
    if not ids:
        return [], [f"{need}: no candidate is rated keep in {FILE}"]
    return ids, []
