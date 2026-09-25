from ballyhoo.names import numbers, parse, pick_candidate, pick_run, prefixes

ORDER = [("singles", ["gemini-a", "gemini-b", "gemini-c"]), ("empty", []), ("couples", ["gemini-a", "pexels-1"])]
RUNS = ["2026-09-24-1", "2026-09-24-3", "2026-09-25-1", "2026-09-25-2", "notes"]


def test_a_candidates_number_counts_through_its_run_in_brief_order_and_is_unique_where_its_need_n_is_not():
    assert numbers(ORDER) == {("singles", "gemini-a"): 1, ("singles", "gemini-b"): 2, ("singles", "gemini-c"): 3,
                              ("couples", "gemini-a"): 4, ("couples", "pexels-1"): 5}
    assert numbers([]) == {}


def test_a_name_is_a_number_after_a_run_number_or_a_runs_full_name():
    assert parse("3.4") == ("3", 4)
    assert parse("2026-09-24-3.4") == ("2026-09-24-3", 4)
    assert parse("4") == (None, 4)
    assert parse("notes.12") == ("notes", 12)
    for bad in ("3.0", "3.", ".4", "3.x", "2026-09-24-3", "pexels-1", ""):
        assert parse(bad) is None, bad


def test_the_page_shortens_a_run_to_its_number_only_where_no_other_run_has_it():
    assert prefixes(RUNS) == {"2026-09-24-1": "2026-09-24-1", "2026-09-24-3": "3", "2026-09-25-1": "2026-09-25-1",
                              "2026-09-25-2": "2", "notes": "notes"}
    assert prefixes(["2026-09-25-1"]) == {"2026-09-25-1": "1"}
    assert prefixes(["2026-09-25-3", "3"]) == {"2026-09-25-3": "2026-09-25-3", "3": "3"}, \
        "3.4 is the folder named 3's"


def test_every_name_the_page_shows_picks_its_own_run():
    for runs in (RUNS, ["2026-09-25-3", "3"]):
        for run, prefix in prefixes(runs).items():
            assert pick_run(f"{prefix}.2", runs, single=False) == ((run, 2), None)


def test_a_name_picks_one_run_by_number_or_full_name_and_says_what_it_matched_when_it_cannot():
    assert pick_run("3.4", RUNS, single=False) == (("2026-09-24-3", 4), None)
    assert pick_run("2026-09-25-1.4", RUNS, single=False) == (("2026-09-25-1", 4), None)
    assert pick_run("1.4", RUNS, single=False) == (None, (
        "1.4: runs 2026-09-25-1, 2026-09-24-1 are all numbered 1; name one, such as 2026-09-25-1.4"))
    assert pick_run("7.4", RUNS, single=False) == (None, (
        "7.4: no run 7 among 2026-09-25-2, 2026-09-25-1, 2026-09-24-3, 2026-09-24-1, notes"))
    assert pick_run("7.4", [], single=False) == (None, "7.4: no run 7: no runs")
    assert pick_run("4", RUNS, single=False) == (None, "4: name the run too, such as 3.4")
    assert pick_run("pexels-1", RUNS, single=False) == (
        None, "pexels-1: not a candidate's name, such as 3.4 or 2026-09-24-3.4")


def test_in_one_run_a_bare_number_names_a_candidate_and_a_name_must_be_that_runs():
    one = ["2026-09-24-3"]
    assert pick_run("4", one, single=True) == (("2026-09-24-3", 4), None)
    assert pick_run("3.4", one, single=True) == (("2026-09-24-3", 4), None)
    assert pick_run("2.4", one, single=True) == (None, "2.4: no run 2 among 2026-09-24-3")


def test_a_number_picks_its_need_and_candidate_or_says_what_the_run_has():
    assert pick_candidate("3.4", "2026-09-24-3", 4, ORDER) == (("couples", "gemini-a"), None)
    assert pick_candidate("3.1", "2026-09-24-3", 1, ORDER) == (("singles", "gemini-a"), None)
    assert pick_candidate("3.6", "2026-09-24-3", 6, ORDER) == (
        None, "3.6: 2026-09-24-3 has candidates 2026-09-24-3.1 to 2026-09-24-3.5")
    assert pick_candidate("3.1", "2026-09-24-3", 1, [("empty", [])]) == (None, "3.1: 2026-09-24-3 has no candidates")
