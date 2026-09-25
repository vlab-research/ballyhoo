"""Comparisons: which of two candidates catches the eye, and the ranking they make.

Pure. "Is this eye-catching" is a comparative judgement, so the pairwise page
shows a person two candidates of one need and records which won;
comparisons.yaml holds those judgements, and `keep --from comparisons` takes its
picks from the ranking they make. The shell loads the file and knows the run's
candidates; this module decides whether a comparisons list is valid, what it
ranks, which pair to ask about next, and what it picks.

A tie means the rater cannot separate the two, not that both are good.
"""
import datetime
import math
from collections import Counter
from dataclasses import dataclass

FILE = "comparisons.yaml"
WINNERS = ("a", "b", "tie")
ROUNDS = 4  # comparisons per candidate the default budget aims at: enough to separate a field, short enough to finish
KEYS = ("rated_by", "rated_on", "comparisons")
ENTRY_KEYS = ("need", "a", "b", "winner")


@dataclass(frozen=True)
class Comparison:
    need: str
    a: str       # a candidate id
    b: str       # another candidate of the same need
    winner: str  # a, b, or tie: the rater cannot separate them

    @property
    def pair(self):
        """The two candidates, whichever side each was shown on."""
        return frozenset((self.a, self.b))

    def points(self, candidate):
        """What the comparison scores for one of its candidates: a win 1, a tie a half, a loss 0."""
        if self.winner == "tie":
            return 0.5
        return 1.0 if getattr(self, self.winner) == candidate else 0.0


@dataclass(frozen=True)
class Comparisons:
    rated_by: str
    rated_on: datetime.date
    comparisons: tuple

    def of(self, need):
        """The comparisons of one need, in the order they were made."""
        return [c for c in self.comparisons if c.need == need]


@dataclass(frozen=True)
class Rank:
    """One candidate's place in a need's ranking."""
    id: str
    score: float | None  # the win rate, a tie counting a half; None when it has never been compared
    comparisons: int
    wins: int
    losses: int
    ties: int
    strength: float      # what the candidates it beat scored: the tie-break


@dataclass(frozen=True)
class Progress:
    """How far a need's comparisons have got, and what to ask next."""
    done: int         # comparisons made
    budget: int       # comparisons this need is worth
    seen: int         # candidates compared at least once
    candidates: int
    pair: tuple | None  # the next pair, or None when the budget is reached or every pair is compared


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


def _entry(where, raw, run):
    """One comparison. Returns (Comparison or None, errors). `run` maps each need with candidates to its ids."""
    if not isinstance(raw, dict):
        return None, [f"{where}: expected a map with need, a, b and winner"]
    errors = _unknown(f"{where}: ", raw, ENTRY_KEYS)
    need, a, b, winner = (raw.get(k) for k in ENTRY_KEYS)
    if need not in run:
        errors.append(f"{where}: {need!r} is not a need with candidates in this run")
    else:
        for side, candidate in (("a", a), ("b", b)):
            if candidate not in run[need]:
                errors.append(f"{where}: {side} {candidate!r} is not a candidate of {need} in this run")
    if a is not None and a == b:
        errors.append(f"{where}: a and b are the same candidate, {a!r}")
    if winner not in WINNERS:
        errors.append(f"{where}: winner must be a, b or tie, not {winner!r}")
    if errors:
        return None, errors
    return Comparison(need, a, b, winner), []


def parse(data, run):
    """Validate a loaded comparisons map. Returns (Comparisons or None, errors); every problem is reported.

    `run` maps each need that has candidates to its candidates' ids.
    """
    if not isinstance(data, dict):
        return None, ["expected a map with rated_by, rated_on and comparisons"]
    errors = _unknown("", data, KEYS)
    rated_by = data.get("rated_by")
    if not isinstance(rated_by, str) or not rated_by.strip():
        errors.append("rated_by is required: the name of whoever compared")
    rated_on = _date(data.get("rated_on"))
    if rated_on is None:
        errors.append(f"rated_on must be a date, e.g. 2026-09-16, not {data.get('rated_on')!r}")
    raw = data.get("comparisons", [])
    if not isinstance(raw, list):
        return None, errors + ["comparisons must be a list of {need, a, b, winner}"]
    made = []
    for n, entry in enumerate(raw, 1):
        comparison, problems = _entry(f"comparison {n}", entry, run)
        errors += problems
        if comparison:
            made.append(comparison)
    if errors:
        return None, errors
    return Comparisons(rated_by.strip(), rated_on, tuple(made)), []


def dump(comparisons):
    """A comparisons map as data, for YAML."""
    return {"rated_by": comparisons.rated_by, "rated_on": comparisons.rated_on,
            "comparisons": [{k: getattr(c, k) for k in ENTRY_KEYS} for c in comparisons.comparisons]}


def as_json(comparisons):
    """A comparisons map as data for JSON, whose dates are strings."""
    return {**dump(comparisons), "rated_on": comparisons.rated_on.isoformat()}


def with_comparison(existing, rated_by, rated_on, entry):
    """The file's data with one more comparison appended, to validate and write whole.

    `entry` is the map the page posted, passed on as it is so that its own mistakes are reported.
    """
    made = as_json(existing)["comparisons"] if existing else []
    return {"rated_by": rated_by, "rated_on": rated_on, "comparisons": [*made, entry]}


def without_last(existing, need):
    """The file's data with the need's last comparison dropped. Returns (data, errors)."""
    made = as_json(existing)["comparisons"] if existing else []
    for i in reversed(range(len(made))):
        if made[i]["need"] == need:
            return {"rated_by": existing.rated_by, "rated_on": existing.rated_on.isoformat(),
                    "comparisons": [*made[:i], *made[i + 1:]]}, []
    return None, [f"{need}: nothing to undo"]


def rank(candidate_ids, comparisons):
    """A need's candidates, best first. Returns Ranks; `comparisons` are that need's own.

    The score is the win rate with a tie counting a half, which is what a person can check by hand.
    Equal scores are broken by strength, what the candidates it beat themselves scored, so a win over
    a strong candidate counts for more; equal again, by id, which is stable and arbitrary. A cycle
    (a beats b, b beats c, c beats a) leaves every candidate on the same score and the same strength,
    so it comes out as the tie it is, ordered by id: the method does not invent a winner.
    """
    played = {c: [] for c in candidate_ids}  # candidate -> (opponent, points)
    for comparison in comparisons:
        for candidate, opponent in ((comparison.a, comparison.b), (comparison.b, comparison.a)):
            if candidate in played:
                played[candidate].append((opponent, comparison.points(candidate)))
    scores = {c: (sum(p for _, p in games) / len(games) if games else None) for c, games in played.items()}
    ranks = [Rank(c, scores[c], len(games),
                  sum(p == 1 for _, p in games), sum(p == 0 for _, p in games), sum(p == 0.5 for _, p in games),
                  sum(p * (scores.get(o) or 0) for o, p in games))
             for c, games in played.items()]
    return sorted(ranks, key=lambda r: (r.score is None, -(r.score or 0), -r.strength, r.id))


def budget(candidates, rounds=ROUNDS):
    """How many comparisons a need is worth: about `rounds` per candidate, and never more than every pair."""
    return min(candidates * (candidates - 1) // 2, math.ceil(candidates * rounds / 2))


def next_pair(candidate_ids, comparisons):
    """The pair to compare next, or None when every pair has been compared.

    The candidate with the fewest comparisons comes first, since the ranking rests least on it; its
    partner is the one that is itself little compared and near it in the ranking, because a pair a
    long way apart is one whose answer is already known. A pair is never asked twice, and never pairs
    a candidate with itself.
    """
    if len(candidate_ids) < 2:
        return None
    index = {c: i for i, c in enumerate(candidate_ids)}
    done = {c.pair for c in comparisons}
    counts = Counter()
    for c in comparisons:
        counts.update((c.a, c.b))
    place = {r.id: i for i, r in enumerate(rank(candidate_ids, comparisons))}
    for a in sorted(candidate_ids, key=lambda c: (counts[c], index[c])):
        partners = [b for b in candidate_ids if b != a and frozenset((a, b)) not in done]
        if partners:
            b = min(partners, key=lambda b: (counts[b], abs(place[b] - place[a]), index[b]))
            return tuple(sorted((a, b), key=index.get))
    return None


def progress(candidate_ids, comparisons, rounds=ROUNDS):
    """How far a need has got, and the pair to show next. `comparisons` are that need's own."""
    total = budget(len(candidate_ids), rounds)
    done = len(comparisons)
    seen = len({c for comparison in comparisons for c in comparison.pair} & set(candidate_ids))
    return Progress(done, total, seen, len(candidate_ids),
                    next_pair(candidate_ids, comparisons) if done < total else None)


def keep_plan(comparisons, needs, need, top):
    """The candidates `keep --from comparisons --top` keeps: the need's best-ranked. Returns (ids, errors).

    `comparisons` is the run's comparisons.yaml, None when it has none; `needs` maps each need with
    candidates to its ids.
    """
    if comparisons is None:
        return [], [f"no {FILE} in this run; compare them first: ballyhoo review RUN --pairs"]
    if need not in needs:
        return [], [f"{need}: not a need with candidates in this run (needs: {', '.join(needs) or 'none'})"]
    ids = needs[need]
    if top > len(ids):
        return [], [f"{need}: --top {top} is more than the {len(ids)} candidates this need has"]
    ranking = rank(ids, comparisons.of(need))
    uncompared = [r.id for r in ranking if r.score is None]
    if uncompared:
        return [], [f"{need}: {len(uncompared)} of {len(ids)} candidates have never been compared "
                    f"({', '.join(uncompared[:5])}{', …' if len(uncompared) > 5 else ''}); "
                    f"a ranking that leaves them out is not a ranking of the need"]
    return [r.id for r in ranking[:top]], []
