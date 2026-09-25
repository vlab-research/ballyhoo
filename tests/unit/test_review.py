import datetime
import json

import pytest

from ballyhoo.candidates import Candidate, Cutout
from ballyhoo.review import (asks, changes, is_run, newest, page, page_data, run_data, run_name, run_order, run_status,
                             state, summary, summary_lines, word_diff)
from ballyhoo.verdicts import Verdict, Verdicts

ON = datetime.date(2026, 9, 14)
BAND = "photo-band/1080x1080"


def stock(n, *queries, alt=None):
    record = {"source": "stock", "provider": "pexels", "id": str(n), "page_url": f"https://pexels.example/{n}",
              "creator": "Jane Doe", "creator_url": "https://pexels.example/@jane", "licence": "Pexels License",
              "licence_url": "https://pexels.example/license", "query": queries[0],
              **({"alt": alt} if alt else {})}
    path = f"originals/pexels-{n}.jpg"
    return Candidate(f"pexels-{n}", 3000, 2000, path, path, record, tuple(queries[1:]))


GENERATED = Candidate("gemini-abc", 1024, 1024, "generated/gemini-abc.png", "generated/gemini-abc.png",
                      {"source": "generated", "provider": "gemini", "model": "gemini-3.1-flash-image",
                       "prompt": "A woman in her fifties.", "seed": 7, "generated": ON})
OPENVERSE = Candidate("openverse-x1", 800, 600, "https://images.example/x1.jpg", "https://images.example/x1-t.jpg",
                      {"source": "stock", "provider": "openverse", "id": "x1", "query": "man", "title": "A man"})
FOUND = {"ke-woman": [stock(1, "woman phone", "kenyan woman", alt="A woman on a phone"), stock(2, "woman phone"),
                      stock(3, "kenyan woman"), GENERATED],
         "ma-man": [OPENVERSE]}
VERDICTS = Verdicts("A. Author", ON, {"ke-woman": {"pexels-1": Verdict("keep", ("crop",), "Tight."),
                                                   "pexels-2": Verdict("drop", ("text", "age")),
                                                   "gemini-abc": Verdict("maybe", ("age",))}})
AGENT = Verdicts("claude-code (claude-opus-5)", ON, {"ke-woman": {"pexels-2": Verdict("drop", ("age",), "Looks 70.")}})
CHECKS = {"ke-woman": {"copy": "Take a short survey.", "templates": [BAND], "candidates": {
    "pexels-1": {"pass": False, "previews": {BAND: {
        "status": "fail", "file": "previews/pexels-1_photo-band_1080x1080.png", "summary": "84px, 2 lines",
        "failures": ["contrast 1.17:1 is below 3:1"]}}},
    "pexels-2": {"pass": True, "previews": {BAND: {
        "status": "pass", "file": "previews/pexels-2_photo-band_1080x1080.png", "summary": "84px, 2 lines"}}},
    "gemini-abc": {"pass": False, "previews": {BAND: {"status": "error", "failures": ["TimeoutError: slow"]}}},
}}}


def counts(found, keep=0, maybe=0, drop=0, unrated=0, **issues):
    return {"candidates": found, "keep": keep, "maybe": maybe, "drop": drop, "unrated": unrated, "issues": issues}


def test_the_summary_credits_every_query_that_found_a_candidate_and_counts_it_once_for_its_provider():
    result = summary(FOUND, VERDICTS)
    woman = result["ke-woman"]
    assert {k: v for k, v in woman.items() if k != "providers"} == counts(4, 1, 1, 1, 1, age=2, text=1, crop=1)
    pexels = woman["providers"]["pexels"]
    assert {k: v for k, v in pexels.items() if k != "queries"} == counts(3, 1, 0, 1, 1, age=1, text=1, crop=1)
    assert pexels["queries"] == {"woman phone": counts(2, 1, 0, 1, 0, age=1, text=1, crop=1),
                                 "kenyan woman": counts(2, 1, 0, 0, 1, crop=1)}
    assert "prompts" not in pexels
    assert woman["providers"]["gemini"] == {**counts(1, maybe=1, age=1),
                                            "prompts": {"A woman in her fifties.": counts(1, maybe=1, age=1)}}
    assert list(woman["issues"]) == ["age", "text", "crop"], "issues in the fixed list's order"
    assert result["ma-man"]["providers"]["openverse"]["queries"] == {"man": counts(1, unrated=1)}


def test_a_run_nobody_has_rated_is_all_unrated():
    assert summary(FOUND, None)["ke-woman"]["providers"]["pexels"]["queries"]["woman phone"] == counts(2, unrated=2)


def test_the_summary_prints_one_line_per_need_provider_and_query_or_prompt():
    assert summary_lines(summary(FOUND, VERDICTS)) == [
        "ke-woman: 4 found, 1 keep (25%), 1 maybe, 1 drop, 1 unrated; issues: age 2, text 1, crop 1",
        "  pexels: 3 found, 1 keep (33%), 0 maybe, 1 drop, 1 unrated; issues: age 1, text 1, crop 1",
        "    query 'woman phone': 2 found, 1 keep (50%), 0 maybe, 1 drop, 0 unrated; issues: age 1, text 1, crop 1",
        "    query 'kenyan woman': 2 found, 1 keep (50%), 0 maybe, 0 drop, 1 unrated; issues: crop 1",
        "  gemini: 1 found, 0 keep (0%), 1 maybe, 0 drop, 0 unrated; issues: age 1",
        "    prompt 'A woman in her fifties.': 1 found, 0 keep (0%), 1 maybe, 0 drop, 0 unrated; issues: age 1",
        "ma-man: 1 found, 0 keep (0%), 0 maybe, 0 drop, 1 unrated",
        "  openverse: 1 found, 0 keep (0%), 0 maybe, 0 drop, 1 unrated",
        "    query 'man': 1 found, 0 keep (0%), 0 maybe, 0 drop, 1 unrated",
    ]


def data():
    needs = {"ke-woman": "A Kenyan woman.", "ma-man": "A Moroccan man.", "down": "Anything."}
    return run_data(needs, FOUND, CHECKS, VERDICTS, AGENT)


def test_the_page_groups_candidates_by_need_in_brief_order_and_marks_what_was_not_previewed():
    d = data()
    assert (d["rated_by"], d["rated_on"]) == ("A. Author", "2026-09-14")
    assert d["agent"] == {"rated_by": "claude-code (claude-opus-5)", "rated_on": "2026-09-14"}
    assert [(n["name"], n["need"], n["has_candidates"], n["previewed"], len(n["candidates"])) for n in d["needs"]] == [
        ("ke-woman", "A Kenyan woman.", True, True, 4), ("ma-man", "A Moroccan man.", True, False, 1),
        ("down", "Anything.", False, False, 0)]
    assert d["needs"][0]["copy"] == "Take a short survey."
    assert d["needs"][0]["summary"] == summary(FOUND, VERDICTS)["ke-woman"] and d["needs"][2]["summary"] is None
    [man] = d["needs"][1]["candidates"]
    assert (man["previewed"], man["pass"], man["previews"]) == (False, None, [])
    assert (man["alt"], man["full"], man["thumb"]) == ("A man", "https://images.example/x1.jpg",
                                                      "ma-man/thumbs/openverse-x1.jpg")


def test_each_candidate_carries_its_files_checks_source_and_verdicts_with_the_agents_as_a_separate_hint():
    one, two, three, generated = data()["needs"][0]["candidates"]
    assert (one["thumb"], one["full"], one["width"], one["height"]) == (
        "ke-woman/thumbs/pexels-1.jpg", "ke-woman/originals/pexels-1.jpg", 3000, 2000)
    assert (one["previewed"], one["pass"]) == (True, False)
    assert one["previews"] == [{"template": BAND, "status": "fail",
                                "file": "ke-woman/previews/pexels-1_photo-band_1080x1080.png",
                                "summary": "84px, 2 lines", "failures": ["contrast 1.17:1 is below 3:1"]}]
    assert (one["provider"], one["queries"], one["prompt"], one["alt"]) == (
        "pexels", ["woman phone", "kenyan woman"], None, "A woman on a phone")
    assert (one["creator"], one["licence"], one["page_url"]) == ("Jane Doe", "Pexels License", "https://pexels.example/1")
    assert one["verdict"] == {"verdict": "keep", "issues": ["crop"], "note": "Tight."} and one["agent"] is None
    assert two["verdict"] == {"verdict": "drop", "issues": ["text", "age"], "note": None}
    assert two["agent"] == {"verdict": "drop", "issues": ["age"], "note": "Looks 70."}
    assert three["verdict"] is None and three["previewed"] is False
    assert generated["previews"] == [{"template": BAND, "status": "error", "file": None, "summary": None,
                                      "failures": ["TimeoutError: slow"]}]
    assert (generated["queries"], generated["prompt"], generated["model"], generated["seed"]) == (
        [], "A woman in her fifties.", "gemini-3.1-flash-image", 7)


DRAWN = Candidate("gemini-def", 1080, 1080, "generated/gemini-def.png", "generated/gemini-def.png",
                  {"source": "generated", "provider": "gemini", "model": "gemini-3.1-flash-image",
                   "prompt": "A woman in her fifties. Hand drawn.", "seed": 8, "generated": ON,
                   "style": "pastel-hand", "key_colour": [9, 193, 18], "raw_sha256": "a" * 64},
                  cutout=Cutout("cutouts/gemini-def.png", (9, 193, 18), ("2 stray specks in the mask",)))


def test_a_drawing_shows_its_cut_out_the_colour_keyed_out_and_what_the_mask_check_found():
    [drawn] = run_data({"na-woman": "A woman."}, {"na-woman": [DRAWN]}, {}, None, None)["needs"][0]["candidates"]
    assert drawn["cutout"] == {"file": "na-woman/cutouts/gemini-def.png", "key": [9, 193, 18], "pass": False,
                               "failures": ["2 stray specks in the mask"]}
    assert (drawn["style"], drawn["full"]) == ("pastel-hand", "na-woman/generated/gemini-def.png")
    assert data()["needs"][0]["candidates"][0]["cutout"] is None, "a photograph has no cut-out"


def test_each_need_carries_the_persons_note_on_it():
    noted = Verdicts("A. Author", ON, VERDICTS.needs, {"ma-man": "None of these look 50."})
    agent = Verdicts(AGENT.rated_by, ON, AGENT.needs, {"ke-woman": "Try older."})
    needs = run_data({"ke-woman": "A Kenyan woman.", "ma-man": "A Moroccan man."}, FOUND, CHECKS, noted, agent)["needs"]
    assert [n["note"] for n in needs] == [None, "None of these look 50."]
    assert run_data({"ma-man": "A Moroccan man."}, FOUND, CHECKS, None, agent)["needs"][0]["note"] is None


def test_the_agents_verdicts_never_stand_in_for_a_persons():
    d = run_data({"ke-woman": "A Kenyan woman."}, FOUND, CHECKS, None, AGENT)
    assert d["rated_by"] is None
    assert [c["verdict"] for c in d["needs"][0]["candidates"]] == [None, None, None, None]
    assert d["needs"][0]["summary"]["unrated"] == 4


def test_a_page_of_many_runs_finds_each_runs_files_under_its_own_folder():
    [one] = run_data({"ke-woman": "A Kenyan woman."}, FOUND, CHECKS, None, None, base="2026-09-14-1/")["needs"][0][
        "candidates"][:1]
    assert (one["thumb"], one["previews"][0]["file"]) == (
        "2026-09-14-1/ke-woman/thumbs/pexels-1.jpg", "2026-09-14-1/ke-woman/previews/pexels-1_photo-band_1080x1080.png")
    [openverse] = run_data({"ma-man": "A man."}, FOUND, {}, None, None, base="r/")["needs"][0]["candidates"]
    assert openverse["full"] == "https://images.example/x1.jpg", "a URL is not a file in the run"


def entry(name, status="ready", requests=(), data=None, errors=()):
    return {"name": name, "status": status, "errors": list(errors),
            "requests": None if requests is None else list(requests), "data": data}


def test_the_page_shows_runs_newest_first_with_the_newest_sourced_one_open_and_what_each_changed():
    first = [search("a", "woman"), generate("a", "A woman in green.")]
    second = [search("a", "woman"), generate("a", "A woman in blue.")]
    runs = [entry("2026-09-24-1", requests=first, data=data()), entry("2026-09-24-2", requests=second),
            entry("2026-09-24-10", requests=None, errors=["2026-09-24-10: not a run folder: gone"]),
            entry("2026-09-25-1", status="sourcing", requests=None)]
    d = page_data(runs, editable=True, digest="abc")
    assert (d["editable"], d["state"], d["verdicts"]) == (True, "abc", ["keep", "maybe", "drop"])
    assert [(r["name"], r["date"], r["number"], r["status"], r["open"]) for r in d["runs"]] == [
        ("2026-09-25-1", "2026-09-25", 1, "sourcing", False), ("2026-09-24-10", "2026-09-24", 10, "ready", True),
        ("2026-09-24-2", "2026-09-24", 2, "ready", False), ("2026-09-24-1", "2026-09-24", 1, "ready", False)]
    sourcing, broken, two, one = d["runs"]
    assert (sourcing["changes"], sourcing["needs"], broken["changes"]) == (None, [], None)
    assert broken["errors"] == ["2026-09-24-10: not a run folder: gone"]
    assert two["changes"] == [{"need": "a", "change": "changed", "asks": [
        {"kind": "generate", "provider": "gemini", "diff": [["=", "A woman in"], ["-", "green."], ["+", "blue."]]}]}]
    assert one["changes"] is None, "the oldest run has nothing to compare with"
    assert one["rated_by"] == "A. Author" and [n["name"] for n in one["needs"]] == ["ke-woman", "ma-man", "down"]
    assert page_data([], editable=True, digest="x")["runs"] == []


def test_each_candidate_is_named_by_its_number_in_the_run_with_its_run_short_where_that_is_unambiguous():
    found = {"ke-woman": FOUND["ke-woman"][:2], "ma-man": FOUND["ma-man"]}
    one = run_data({"ke-woman": "A Kenyan woman.", "down": "Anything.", "ma-man": "A Moroccan man."}, found, {},
                   None, None)
    assert [[c["number"] for c in n["candidates"]] for n in one["needs"]] == [[1, 2], [], [3]]
    d = page_data([entry("2026-09-24-3", data=one), entry("2026-09-25-1", data=one), entry("2026-09-24-1", data=one)],
                  editable=True, digest="x")
    assert [[c["name"] for n in r["needs"] for c in n["candidates"]] for r in d["runs"]] == [
        ["2026-09-25-1.1", "2026-09-25-1.2", "2026-09-25-1.3"], ["3.1", "3.2", "3.3"],
        ["2026-09-24-1.1", "2026-09-24-1.2", "2026-09-24-1.3"]]


def test_the_page_embeds_its_data_so_no_text_in_it_can_end_the_script():
    template = '<script id="data" type="application/json">__BALLYHOO_DATA__</script>'
    html = page(template, {"note": "</script><b>ñ"})
    assert "</script><b>" not in html and html.count("</script>") == 1
    assert json.loads(html[len('<script id="data" type="application/json">'):-len("</script>")]) == {
        "note": "</script><b>ñ"}
    with pytest.raises(ValueError):
        page("<p>no data</p>", {})


def test_runs_are_ordered_newest_first_by_date_then_number():
    names = ["2026-09-24-2", "2026-09-24-10", "notes", "2026-09-25-1", "2026-09-24-9"]
    assert run_order(names) == ["2026-09-25-1", "2026-09-24-10", "2026-09-24-9", "2026-09-24-2", "notes"]
    assert run_name("2026-09-24-10") == ("2026-09-24", 10) and run_name("2026-09-24") is None


def test_a_folder_is_a_run_when_it_has_a_manifest_or_a_run_name():
    assert is_run("2026-09-24-1", False) and is_run("by-hand", True)
    assert not is_run("sheets", False)


def test_the_newest_file_time_ignores_what_the_page_writes_and_temporary_files():
    files = [("manifest.yaml", 10), ("ke-woman/checks.yaml", 30), ("verdicts.yaml", 90), ("review.html", 80),
             (".verdicts.yaml.x.tmp", 70), ("ke-woman/.candidates.yaml.y.tmp", 60), ("agent-verdicts.yaml", 20)]
    assert newest(files) == 30
    assert newest([("verdicts.yaml", 5)]) is None and newest([]) is None


def test_a_run_is_sourcing_until_its_manifest_then_previewing_until_every_need_with_candidates_is_checked():
    assert run_status(False, ["a"], ["a"]) == "sourcing"
    assert run_status(True, ["a", "b"], ["a"]) == "previewing"
    assert run_status(True, ["a", "b"], ["a", "b"]) == "ready"
    assert run_status(True, [], []) == "ready", "a run whose every request failed has nothing to preview"


def test_the_state_orders_runs_and_its_digest_changes_with_any_of_them():
    one = {"name": "2026-09-24-1", "mtime": 1, "status": "ready"}
    two = {"name": "2026-09-24-2", "mtime": 2, "status": "previewing"}
    s = state([one, two])
    assert s["runs"] == [two, one]
    assert state([two, one])["digest"] == s["digest"]
    assert state([one, {**two, "status": "ready"}])["digest"] != s["digest"]
    assert state([one, {**two, "mtime": 3}])["digest"] != s["digest"]
    assert state([one])["digest"] != s["digest"]


def search(need, query, provider="pexels"):
    return {"need": need, "provider": provider, "kind": "search", "query": query, "n": 5}


def generate(need, prompt, provider="gemini"):
    return {"need": need, "provider": provider, "kind": "generate", "model": "m", "size": "1x1", "seeds": [1],
            "prompt": prompt}


def test_asks_group_a_runs_requests_by_need_kind_and_provider():
    assert asks([search("a", "woman"), search("a", "woman"), search("a", "old woman"), generate("a", "A woman.")]) == {
        "a": {("search", "pexels"): ["woman", "old woman"], ("generate", "gemini"): ["A woman."]}}


def test_a_prompt_diff_keeps_a_few_words_either_side_of_each_change():
    before = "They are relaxed and happy together, smiling easily, leaning into each other, one of them holding a phone."
    after = "They are relaxed and happy together, leaning into each other, one of them holding a phone. No text."
    assert word_diff(before, after) == [
        ["=", "… and happy together,"], ["-", "smiling easily,"],
        ["=", "leaning into each … holding a phone."], ["+", "No text."]]
    assert word_diff("a b", "a c") == [["=", "a"], ["-", "b"], ["+", "c"]]


def test_changes_name_new_and_gone_needs_and_what_each_kept_need_asks_differently():
    before = asks([search("a", "woman"), search("a", "old woman"), generate("a", "A woman in green."),
                   generate("b", "A man."), search("c", "same")])
    after = asks([search("a", "woman"), search("a", "grey woman"), generate("a", "A woman in blue."),
                  generate("a", "A woman.", provider="fal"), search("c", "same"), generate("d", "New.")])
    assert changes(before, after) == [
        {"need": "a", "change": "changed", "asks": [
            {"kind": "search", "provider": "pexels", "diff": [["-", "old"], ["+", "grey"], ["=", "woman"]]},
            {"kind": "generate", "provider": "gemini", "diff": [["=", "A woman in"], ["-", "green."], ["+", "blue."]]},
            {"kind": "generate", "provider": "fal", "added": ["A woman."], "removed": []}]},
        {"need": "d", "change": "new"},
        {"need": "b", "change": "gone"}]
    assert changes(after, after) == []
