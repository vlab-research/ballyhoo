"""Verdicts: a person's rating of each candidate in a run, against its need.

Pure. verdicts.yaml is the one human input ballyhoo reads: the review page
writes it, and `keep --verdicts` takes its picks from it. An agent may rate a
run too, in agent-verdicts.yaml, in the same format; the page shows those as
hints, and they are never picks, because a pick names a person. The shell
loads the files and knows the run's candidates; this module decides whether a
verdicts map is valid, and what it picks.
"""
import datetime
from dataclasses import dataclass, field

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
KEYS = ("rated_by", "rated_on", "needs", "notes")
ENTRY_KEYS = ("verdict", "issues", "note")
MARK_KEYS = ("rated_by", "need", "candidate", "entry", "note")


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
    notes: dict = field(default_factory=dict)  # need -> a note on the need's candidates as a whole

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
    notes, problems = _notes(data.get("notes", {}), run)
    errors += problems
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
    return Verdicts(rated_by.strip(), rated_on, needs, notes), []


def _notes(raw, run):
    """The notes on needs as a whole: need -> text. An empty note is no note. Returns (notes, errors)."""
    if not isinstance(raw, dict):
        return {}, ["notes must be a map of need -> text"]
    notes, errors = {}, []
    for need, note in raw.items():
        if need not in run:
            errors.append(f"notes/{need}: not a need with candidates in this run")
        elif note is not None and not isinstance(note, str):
            errors.append(f"notes/{need}: a note must be text")
        elif (note or "").strip():
            notes[need] = note.strip()
    return notes, errors


def dump(verdicts):
    """A verdicts map as data, for YAML: empty issues and notes are left out."""
    return {"rated_by": verdicts.rated_by, "rated_on": verdicts.rated_on,
            "needs": {need: {c: {"verdict": v.verdict, **({"issues": list(v.issues)} if v.issues else {}),
                                 **({"note": v.note} if v.note else {})}
                             for c, v in entries.items()}
                      for need, entries in verdicts.needs.items()},
            **({"notes": dict(verdicts.notes)} if verdicts.notes else {})}


def as_json(verdicts):
    """A verdicts map as data for JSON, whose dates are strings."""
    return {**dump(verdicts), "rated_on": verdicts.rated_on.isoformat()}


def marked(verdicts):
    """Whether a verdicts map rates any candidate or notes any need. A run with neither is rated by nobody."""
    return verdicts is not None and (any(verdicts.needs.values()) or bool(verdicts.notes))


def merge(current, mark, run, today):
    """A run's verdicts with one mark from the review page merged in. Returns (Verdicts or None, errors).

    `current` is the run's verdicts, None when it has none. `mark` is what the page posted: rated_by,
    need, and either candidate and entry, the candidate's verdict map as in the file or None to clear
    its mark, or note, the need's note, empty to clear it. `run` is as parse takes it. One person
    rates a run, so a mark from anyone but the person who rated it is refused; a note is a mark too.
    The merged map is validated whole, by parse, and is dated `today`.
    """
    if not isinstance(mark, dict):
        return None, ["a mark is a map with rated_by, need, and candidate and entry, or note"]
    errors = _unknown("", mark, MARK_KEYS)
    rated_by, need, candidate, entry, note = (mark.get(k) for k in MARK_KEYS)
    noting = "note" in mark
    if not isinstance(rated_by, str) or not rated_by.strip():
        errors.append("rated_by is required: the name of whoever rated")
    if noting:
        if "candidate" in mark or "entry" in mark:
            errors.append("a mark is a note on a need or a verdict on a candidate, not both")
        if not isinstance(need, str):
            errors.append("need must be named")
    else:
        if not isinstance(need, str) or not isinstance(candidate, str):
            errors.append("need and candidate must be named")
        if entry is not None and not isinstance(entry, dict):
            errors.append("entry must be a verdict map, or null to clear the mark")
        elif entry is not None and entry.get("verdict") is None:
            errors.append("choose keep, maybe or drop: issues and a note are saved with a verdict")
    if errors:
        return None, errors
    rated_by = rated_by.strip()
    if marked(current) and current.rated_by != rated_by:
        return None, [f"this run is rated by {current.rated_by}, and one person rates a run, "
                      f"so a mark from {rated_by} is not saved"]
    before = dump(current) if current else {}
    needs, notes = before.get("needs", {}), before.get("notes", {})
    if noting:
        notes[need] = note
    elif entry is None:
        needs.get(need, {}).pop(candidate, None)
        if need in needs and not needs[need]:
            del needs[need]
    else:
        needs.setdefault(need, {})[candidate] = entry
    return parse({"rated_by": rated_by, "rated_on": today, "needs": needs, "notes": notes}, run)


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
