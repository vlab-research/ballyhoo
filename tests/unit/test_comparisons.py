import dataclasses
import datetime

from ballyhoo.comparisons import (Comparison, Comparisons, budget, dump, keep_plan, next_pair, parse, progress, rank,
                                  with_comparison, without_last)

RUN = {"n": ["p1", "p2", "p3", "p4"], "other": ["q1", "q2"]}
ON = datetime.date(2026, 9, 16)


def made(*results, need="n"):
    """Comparisons written as 'p1>p2' (p1 won) or 'p1=p2' (they could not be separated)."""
    out = []
    for result in results:
        if ">" in result:
            a, b = result.split(">")
            out.append(Comparison(need, a, b, "a"))
        else:
            a, b = result.split("=")
            out.append(Comparison(need, a, b, "tie"))
    return out


def data(comparisons, rated_by="A. Author", rated_on=ON):
    return {"rated_by": rated_by, "rated_on": rated_on, "comparisons": comparisons}


def ids(ranking):
    return [r.id for r in ranking]


def test_a_valid_list_parses_and_round_trips():
    raw = data([{"need": "n", "a": "p1", "b": "p2", "winner": "a"},
                {"need": "other", "a": "q1", "b": "q2", "winner": "tie"}])
    comparisons, errors = parse(raw, RUN)
    assert errors == []
    assert comparisons == Comparisons("A. Author", ON, (Comparison("n", "p1", "p2", "a"),
                                                        Comparison("other", "q1", "q2", "tie")))
    assert comparisons.of("n") == [Comparison("n", "p1", "p2", "a")]
    assert parse(dump(comparisons), RUN) == (comparisons, [])


def test_every_problem_is_reported_together():
    raw = {"rated_by": " ", "rated_on": "soon", "colour": "blue", "comparisons": [
        {"need": "n", "a": "p1", "b": "p2", "winner": "left"},
        {"need": "nowhere", "a": "p1", "b": "p2", "winner": "a"},
        {"need": "n", "a": "p1", "b": "p1", "winner": "a"},
        {"need": "n", "a": "p9", "b": "q1", "winner": "b", "note": "hm"},
        "p1 beats p2",
    ]}
    comparisons, errors = parse(raw, RUN)
    assert comparisons is None
    assert errors == [
        "unknown key 'colour'",
        "rated_by is required: the name of whoever compared",
        "rated_on must be a date, e.g. 2026-09-16, not 'soon'",
        "comparison 1: winner must be a, b or tie, not 'left'",
        "comparison 2: 'nowhere' is not a need with candidates in this run",
        "comparison 3: a and b are the same candidate, 'p1'",
        "comparison 4: unknown key 'note'",
        "comparison 4: a 'p9' is not a candidate of n in this run",
        "comparison 4: b 'q1' is not a candidate of n in this run",
        "comparison 5: expected a map with need, a, b and winner",
    ]


def test_a_map_that_is_not_one_says_so():
    assert parse(["p1>p2"], RUN) == (None, ["expected a map with rated_by, rated_on and comparisons"])
    assert parse(data({"n": "p1>p2"}), RUN) == (None, ["comparisons must be a list of {need, a, b, winner}"])


def test_the_ranking_is_the_win_rate_with_a_tie_counting_a_half():
    ranking = rank(RUN["n"], made("p1>p2", "p1>p3", "p2>p3", "p3=p4"))
    assert ids(ranking) == ["p1", "p2", "p4", "p3"]
    assert [(r.comparisons, r.wins, r.losses, r.ties) for r in ranking] == [
        (2, 2, 0, 0), (2, 1, 1, 0), (1, 0, 0, 1), (3, 0, 2, 1)]
    assert [round(r.score, 3) for r in ranking] == [1.0, 0.5, 0.5, 0.167]


def test_a_win_over_a_strong_candidate_breaks_a_tie_between_equal_scores():
    # p2 and p4 both score 0.5, but p2's win was over p3, who has won something, and p4 only drew with p3.
    ranking = {r.id: r for r in rank(RUN["n"], made("p1>p2", "p1>p3", "p2>p3", "p3=p4"))}
    assert ranking["p2"].score == ranking["p4"].score
    assert ranking["p2"].strength > ranking["p4"].strength


def test_a_cycle_comes_out_as_the_tie_it_is():
    ranking = rank(["p1", "p2", "p3"], made("p1>p2", "p2>p3", "p3>p1"))
    assert [(r.score, r.strength) for r in ranking] == [(0.5, 0.5), (0.5, 0.5), (0.5, 0.5)]
    assert ids(ranking) == ["p1", "p2", "p3"], "nothing separates them, so the order is by id"


def test_a_candidate_that_has_never_been_compared_is_ranked_last_with_no_score():
    ranking = rank(RUN["n"], made("p1>p2"))
    assert ids(ranking) == ["p1", "p2", "p3", "p4"]
    assert [(r.score, r.comparisons) for r in ranking[2:]] == [(None, 0), (None, 0)]


def test_the_next_pair_is_the_least_compared_then_the_nearest_in_the_ranking():
    assert next_pair(RUN["n"], []) == ("p1", "p2")
    assert next_pair(RUN["n"], made("p1>p2")) == ("p3", "p4"), "the two nobody has compared come next"
    assert next_pair(RUN["n"], made("p1>p2", "p3>p4")) == ("p1", "p3"), "then the two winners, who are neighbours"
    assert next_pair(["p1"], []) is None


def test_a_pair_is_never_asked_twice_and_every_pair_ends_the_asking():
    asked, comparisons = [], []
    while (pair := next_pair(RUN["n"], comparisons)) is not None:
        assert pair not in asked and pair[0] != pair[1]
        asked.append(pair)
        comparisons.append(Comparison("n", pair[0], pair[1], "a"))
    assert len(asked) == 6, "four candidates make six pairs"


def test_the_budget_is_about_four_comparisons_a_candidate_and_never_more_than_every_pair():
    assert [budget(n) for n in (0, 1, 2, 3, 4, 96)] == [0, 0, 1, 3, 6, 192]
    assert budget(96, rounds=2) == 96


def test_progress_counts_what_is_done_and_stops_at_the_budget():
    assert dataclasses.astuple(progress(RUN["n"], [])) == (0, 6, 0, 4, ("p1", "p2"))
    assert dataclasses.astuple(progress(RUN["n"], made("p1>p2", "p3>p4"))) == (2, 6, 4, 4, ("p1", "p3"))
    assert progress(RUN["n"], made("p1>p2", "p3>p4"), rounds=1).pair is None, "the budget is reached"


def test_keep_takes_the_needs_best_ranked():
    comparisons = Comparisons("A. Author", ON, tuple(made("p1>p2", "p1>p3", "p2>p3", "p3=p4")))
    assert keep_plan(comparisons, RUN, "n", 2) == (["p1", "p2"], [])
    assert keep_plan(comparisons, RUN, "n", 4) == (["p1", "p2", "p4", "p3"], [])


def test_keep_refuses_no_comparisons_an_unknown_need_too_large_a_top_and_a_candidate_never_compared():
    comparisons = Comparisons("A. Author", ON, tuple(made("p1>p2", "p3=p4")))
    assert keep_plan(None, RUN, "n", 1) == (
        [], ["no comparisons.yaml in this run; compare them first: ballyhoo review RUN --pairs"])
    assert keep_plan(comparisons, RUN, "nowhere", 1) == (
        [], ["nowhere: not a need with candidates in this run (needs: n, other)"])
    assert keep_plan(comparisons, RUN, "n", 5) == (
        [], ["n: --top 5 is more than the 4 candidates this need has"])
    assert keep_plan(comparisons, RUN, "other", 1) == (
        [], ["other: 2 of 2 candidates have never been compared (q1, q2); "
             "a ranking that leaves them out is not a ranking of the need"])


def test_one_comparison_is_added_at_a_time_and_the_last_can_be_undone():
    entry = {"need": "n", "a": "p2", "b": "p3", "winner": "tie"}
    assert with_comparison(None, "A. Author", "2026-09-16", entry) == data([entry], rated_on="2026-09-16")
    comparisons, _ = parse(with_comparison(None, "A. Author", "2026-09-16", entry), RUN)
    first = {"need": "n", "a": "p1", "b": "p2", "winner": "a"}
    assert with_comparison(comparisons, "A. Author", "2026-09-17", first) == data([entry, first],
                                                                                  rated_on="2026-09-17")
    assert without_last(comparisons, "n") == (data([], rated_on="2026-09-16"), [])
    assert without_last(comparisons, "other") == (None, ["other: nothing to undo"])
    assert without_last(None, "n") == (None, ["n: nothing to undo"])
