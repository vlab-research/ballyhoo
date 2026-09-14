import datetime
import json

import pytest

from ballyhoo.candidates import Candidate
from ballyhoo.review import page, page_data, summary, summary_lines
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
    return page_data("2026-09-14-1", needs, FOUND, CHECKS, VERDICTS, AGENT, editable=True)


def test_the_page_groups_candidates_by_need_in_brief_order_and_marks_what_was_not_previewed():
    d = data()
    assert (d["run"], d["editable"], d["rated_by"], d["rated_on"]) == ("2026-09-14-1", True, "A. Author", "2026-09-14")
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


def test_the_agents_verdicts_never_stand_in_for_a_persons():
    d = page_data("r", {"ke-woman": "A Kenyan woman."}, FOUND, CHECKS, None, AGENT, editable=True)
    assert d["rated_by"] is None
    assert [c["verdict"] for c in d["needs"][0]["candidates"]] == [None, None, None, None]
    assert d["needs"][0]["summary"]["unrated"] == 4


def test_the_page_embeds_its_data_so_no_text_in_it_can_end_the_script():
    template = '<script id="data" type="application/json">__BALLYHOO_DATA__</script>'
    html = page(template, {"note": "</script><b>ñ"})
    assert "</script><b>" not in html and html.count("</script>") == 1
    assert json.loads(html[len('<script id="data" type="application/json">'):-len("</script>")]) == {
        "note": "</script><b>ñ"}
    with pytest.raises(ValueError):
        page("<p>no data</p>", {})
