import datetime

from ballyhoo.verdicts import ISSUES, Verdict, Verdicts, as_json, dump, keep_plan, marked, merge, parse, picks

RUN = {"ke-woman": ["fake-1", "fake-2", "fake-3"], "ma-man": ["fake-1", "gemini-abc"]}
ON = datetime.date(2026, 9, 14)


def data(needs, rated_by="A. Author", rated_on=ON):
    return {"rated_by": rated_by, "rated_on": rated_on, "needs": needs}


def test_a_valid_map_parses_and_round_trips():
    raw = data({"ke-woman": {"fake-1": {"verdict": "keep", "issues": ["crop"], "note": " Good face. "},
                             "fake-2": {"verdict": "drop"}},
                "ma-man": {"fake-1": {"verdict": "maybe", "issues": []}}})
    verdicts, errors = parse(raw, RUN)
    assert errors == []
    assert verdicts == Verdicts("A. Author", ON, {
        "ke-woman": {"fake-1": Verdict("keep", ("crop",), "Good face."), "fake-2": Verdict("drop")},
        "ma-man": {"fake-1": Verdict("maybe")}})
    assert dump(verdicts)["needs"]["ma-man"] == {"fake-1": {"verdict": "maybe"}}
    assert parse(dump(verdicts), RUN) == (verdicts, [])
    assert parse(as_json(verdicts), RUN) == (verdicts, [])


def test_the_same_photo_under_two_needs_is_rated_against_each_need_separately():
    verdicts, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}},
                              "ma-man": {"fake-1": {"verdict": "drop", "issues": ["off-brief"]}}}), RUN)
    assert verdicts.get("ke-woman", "fake-1").verdict == "keep"
    assert verdicts.get("ma-man", "fake-1").verdict == "drop"
    assert verdicts.get("ma-man", "gemini-abc") is None


def test_rated_on_is_a_date_from_yaml_or_an_iso_string_from_json_but_not_a_time():
    assert parse(data({}, rated_on="2026-09-14"), RUN)[0].rated_on == ON
    assert parse(data({}, rated_on=datetime.datetime(2026, 9, 14, 10, 0)), RUN)[1] == [
        "rated_on must be a date, e.g. 2026-09-14, not datetime.datetime(2026, 9, 14, 10, 0)"]


def test_every_problem_is_reported_together():
    raw = {"rated_by": "  ", "rated_on": "yesterday", "colour": "blue", "needs": {
        "ke-woman": {
            "fake-9": {"verdict": "keep"},
            "fake-1": {"verdict": "yes", "issues": ["blurry", "age", "age"], "note": 3, "stars": 5},
            "fake-2": "keep",
            "fake-3": {"issues": "text"},
        },
        "nowhere": {"fake-1": {"verdict": "keep"}},
        "ma-man": ["gemini-abc"],
    }}
    verdicts, errors = parse(raw, RUN)
    assert verdicts is None
    assert errors == [
        "unknown key 'colour'",
        "rated_by is required: the name of whoever rated",
        "rated_on must be a date, e.g. 2026-09-14, not 'yesterday'",
        "ke-woman/fake-9: not a candidate of ke-woman in this run",
        "ke-woman/fake-1: unknown key 'stars'",
        "ke-woman/fake-1: verdict must be keep, maybe or drop, not 'yes'",
        f"ke-woman/fake-1: unknown issue 'blurry' (known: {', '.join(ISSUES)})",
        "ke-woman/fake-1: an issue is listed twice",
        "ke-woman/fake-1: note must be text",
        "ke-woman/fake-2: expected a map with verdict, and optionally issues and note",
        "ke-woman/fake-3: verdict must be keep, maybe or drop, not None",
        "ke-woman/fake-3: issues must be a list",
        "nowhere: not a need with candidates in this run",
        "ma-man: expected a map of candidate id -> verdict",
    ]


def test_a_map_that_is_not_one_says_so():
    assert parse(["keep"], RUN) == (None, ["expected a map with rated_by, rated_on and needs"])
    assert parse(data(["fake-1"]), RUN) == (None, ["needs must be a map of need -> candidate id -> verdict"])


def test_the_age_issue_is_on_the_fixed_list():
    assert list(ISSUES) == ["minor", "age", "text", "tourist", "poverty", "artefact", "off-brief", "style", "brand",
                            "crop"]


def test_picks_are_the_needs_keeps():
    verdicts, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}, "fake-2": {"verdict": "maybe"},
                                           "fake-3": {"verdict": "keep"}},
                              "ma-man": {"fake-1": {"verdict": "drop"}}}), RUN)
    assert picks(verdicts, "ke-woman") == ["fake-1", "fake-3"]
    assert picks(verdicts, "ma-man") == []
    assert keep_plan(verdicts, False, RUN, "ke-woman") == (["fake-1", "fake-3"], [])


def test_keep_refuses_no_verdicts_agent_verdicts_an_unknown_need_and_a_need_with_no_keeps():
    verdicts, _ = parse(data({"ma-man": {"fake-1": {"verdict": "drop"}}}), RUN)
    assert keep_plan(None, False, RUN, "ke-woman") == (
        [], ["no verdicts.yaml in this run; rate the run first: ballyhoo review RUN"])
    assert keep_plan(None, True, RUN, "ke-woman") == (
        [], ["no verdicts.yaml in this run; agent-verdicts.yaml is not picks: a pick names the person who made it, "
             "so a person rates in verdicts.yaml"])
    assert keep_plan(verdicts, False, RUN, "ke-man") == (
        [], ["ke-man: not a need with candidates in this run (needs: ke-woman, ma-man)"])
    assert keep_plan(verdicts, False, RUN, "ma-man") == ([], ["ma-man: no candidate is rated keep in verdicts.yaml"])


LATER = datetime.date(2026, 9, 15)


def mark(candidate, entry, need="ke-woman", rated_by="A. Author"):
    return {"rated_by": rated_by, "need": need, "candidate": candidate, "entry": entry}


def test_a_first_mark_starts_the_runs_verdicts_under_the_raters_name():
    verdicts, errors = merge(None, mark("fake-2", {"verdict": "keep", "issues": ["crop"]}, rated_by=" A. Author "),
                             RUN, ON)
    assert errors == []
    assert verdicts == Verdicts("A. Author", ON, {"ke-woman": {"fake-2": Verdict("keep", ("crop",))}})


def test_a_mark_replaces_that_candidates_entry_keeps_the_others_and_dates_the_file_today():
    current, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}, "fake-2": {"verdict": "drop"}},
                             "ma-man": {"fake-1": {"verdict": "maybe"}}}), RUN)
    verdicts, errors = merge(current, mark("fake-2", {"verdict": "maybe", "note": "Better cropped."}), RUN, LATER)
    assert errors == []
    assert verdicts.rated_on == LATER
    assert verdicts.needs == {"ke-woman": {"fake-1": Verdict("keep"), "fake-2": Verdict("maybe", (), "Better cropped.")},
                              "ma-man": {"fake-1": Verdict("maybe")}}


def test_clearing_a_mark_removes_the_entry_and_a_need_left_empty():
    current, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}}, "ma-man": {"fake-1": {"verdict": "drop"}}}), RUN)
    verdicts, errors = merge(current, mark("fake-1", None, need="ma-man"), RUN, ON)
    assert errors == [] and verdicts.needs == {"ke-woman": {"fake-1": Verdict("keep")}}
    assert merge(current, mark("fake-3", None), RUN, ON) == (current, [])


def test_a_run_whose_last_mark_is_cleared_is_rated_by_nobody():
    current, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}}}), RUN)
    cleared, _ = merge(current, mark("fake-1", None), RUN, ON)
    assert not marked(cleared) and not marked(None) and marked(current)
    verdicts, errors = merge(cleared, mark("fake-1", {"verdict": "drop"}, rated_by="B. Other"), RUN, ON)
    assert errors == [] and verdicts.rated_by == "B. Other"


def test_a_mark_from_a_second_person_is_refused():
    current, _ = parse(data({"ke-woman": {"fake-1": {"verdict": "keep"}}}), RUN)
    assert merge(current, mark("fake-2", {"verdict": "keep"}, rated_by="B. Other"), RUN, ON) == (None, [
        "this run is rated by A. Author, and one person rates a run, so a mark from B. Other is not saved"])


def test_a_mark_is_validated_with_the_whole_file_and_every_problem_reported():
    assert merge(None, {"rated_by": "", "need": ["ke-woman"], "entry": "keep", "run": "x"}, RUN, ON) == (None, [
        "unknown key 'run'", "rated_by is required: the name of whoever rated", "need and candidate must be named",
        "entry must be a verdict map, or null to clear the mark"])
    assert merge(None, "keep", RUN, ON) == (None, ["a mark is a map with rated_by, need, candidate, entry"])
    assert merge(None, mark("fake-1", {"issues": ["crop"]}), RUN, ON) == (None, [
        "choose keep, maybe or drop: issues and a note are saved with a verdict"])
    assert merge(None, mark("fake-9", {"verdict": "keep", "issues": ["blurry"]}), RUN, ON) == (None, [
        "ke-woman/fake-9: not a candidate of ke-woman in this run",
        f"ke-woman/fake-9: unknown issue 'blurry' (known: {', '.join(ISSUES)})"])
    assert merge(None, mark("fake-1", {"verdict": "keep"}, need="down"), RUN, ON)[1] == [
        "down: not a need with candidates in this run"]
