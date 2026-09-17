import datetime

import pytest

from ballyhoo.candidates import (Candidate, Cutout, cell_origin, displayed_size, dump, extension, fit, kept_record,
                                 load, merge, parse_picks, plan_keep, sheet_size, sheets, with_cutout, with_original,
                                 with_search_options)
from ballyhoo.provenance import problems

TODAY = datetime.date(2026, 9, 12)
SHA = "c" * 64


def stock(n):
    return Candidate(f"pexels-{n}", 3000, 2000, f"https://images.example/{n}.jpeg",
                     f"https://images.example/{n}-medium.jpeg",
                     {"source": "stock", "provider": "pexels", "id": str(n), "page_url": f"https://pexels.example/{n}",
                      "creator": "Jane Doe", "licence": "Pexels License", "licence_url": "https://pexels.example/license",
                      "query": "older woman phone"})


GENERATED = Candidate("gemini-3f9a0c1d2e4b", 1024, 1024, "generated/gemini-3f9a0c1d2e4b.jpg",
                      "generated/gemini-3f9a0c1d2e4b.jpg",
                      {"source": "generated", "provider": "gemini", "model": "gemini-3.1-flash-image",
                       "prompt": "An older woman reading her phone", "seed": 3, "generated": TODAY})


def test_a_second_search_appends_so_numbers_on_earlier_sheets_stay_true():
    first = [stock(1), stock(2)]
    merged = merge(first, [stock(2), stock(3), stock(3)])
    assert [c.id for c in merged] == ["pexels-1", "pexels-2", "pexels-3"]
    assert [e["n"] for e in dump(merged)["candidates"]] == [1, 2, 3]


def test_the_candidates_file_round_trips_and_names_each_thumbnail():
    data = dump([stock(1), GENERATED])
    assert data["candidates"][1]["thumb"] == "thumbs/gemini-3f9a0c1d2e4b.jpg"
    assert load(data) == ([stock(1), GENERATED], [])


def test_a_damaged_candidates_file_reports_every_bad_entry():
    data = dump([stock(1), stock(2), stock(3)])
    del data["candidates"][0]["full"]
    data["candidates"][2]["id"] = "no provider"
    found, errors = load(data)
    assert [c.id for c in found] == ["pexels-2"]
    assert errors == ["candidate 1: missing full", "candidate 3: id 'no provider' is not <provider>-<id>"]
    assert load({"candidates": "x"}) == ([], ["expected a map holding a list of candidates"])


def test_picks_are_ids_with_an_optional_file_name():
    assert parse_picks(["pexels-1", "pexels-2=ke-woman-market"]) == (
        [("pexels-1", None), ("pexels-2", "ke-woman-market")], [])
    assert parse_picks(["7", "pexels-3="])[1] == [
        "7: expected <candidate id> or <candidate id>=<file name>",
        "pexels-3=: expected <candidate id> or <candidate id>=<file name>"]


def test_keeping_names_files_and_refuses_unknown_ids_bad_names_and_taken_names():
    candidates = [stock(1), stock(2), stock(3), GENERATED]
    picks = [("pexels-1", "ke-woman"), ("pexels-9", None), ("pexels-2", "Woman 2"), ("pexels-3", "ma-man"),
             ("gemini-3f9a0c1d2e4b", "ke-woman")]
    keeps, errors = plan_keep(candidates, picks, taken={"ma-man"})
    assert [(k.candidate.id, k.name) for k in keeps] == [("pexels-1", "ke-woman")]
    assert errors == ["pexels-9: not among these candidates",
                      "pexels-2: file name 'Woman 2' must be a lowercase slug",
                      "pexels-3: ma-man is already taken in the art directory",
                      "gemini-3f9a0c1d2e4b: ke-woman is already taken in the art directory"]
    assert plan_keep(candidates, [("pexels-1", None)], taken=set())[0][0].name == "pexels-1"


def test_the_extension_comes_from_the_bytes_not_the_url():
    assert extension(b"\xff\xd8\xff\xe0rest") == ".jpg"
    assert extension(b"\x89PNG\r\n\x1a\nrest") == ".png"
    assert extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"
    with pytest.raises(ValueError, match="not a JPEG, PNG or WebP"):
        extension(b"<html>rate limited</html>")


def test_a_kept_stock_photo_records_the_fetch_and_the_person_who_picked_it():
    record, found = kept_record(stock(1), SHA, "A. Author", TODAY)
    assert found == []
    assert list(record)[:2] == ["source", "sha256"]
    assert record["fetched"] == TODAY and record["picked"] == {"by": "A. Author", "on": TODAY}
    assert problems(record, SHA) == []


def test_a_kept_generated_image_has_no_fetch_date_and_still_needs_a_picker():
    record, found = kept_record(GENERATED, SHA, "A. Author", TODAY)
    assert found == [] and "fetched" not in record
    assert kept_record(GENERATED, SHA, "  ", TODAY)[1] == [
        "provenance picked needs by (the person who picked it) and on (a date)"]


def test_a_drawing_names_its_cut_out_and_records_the_key_the_style_and_the_generation_it_came_from():
    drawn = with_cutout(GENERATED, (9, 193, 18), ["2 stray specks in the mask"], "pastel-hand", "a" * 64)
    assert drawn.cutout == Cutout("cutouts/gemini-3f9a0c1d2e4b.png", (9, 193, 18), ("2 stray specks in the mask",))
    assert drawn.cutout.ok is False and Cutout("f.png", (9, 193, 18)).ok is True
    assert drawn.image == "cutouts/gemini-3f9a0c1d2e4b.png", "a drawing is previewed and kept as its cut-out"
    assert GENERATED.image == GENERATED.full == "generated/gemini-3f9a0c1d2e4b.jpg"
    assert [drawn.provenance[k] for k in ("style", "key_colour", "raw_sha256")] == ["pastel-hand", [9, 193, 18], "a" * 64]
    assert load(dump([drawn])) == ([drawn], [])

    record, problems = kept_record(drawn, SHA, "A. Author", TODAY)
    assert problems == [] and record["sha256"] == SHA
    assert [record[k] for k in ("style", "key_colour", "raw_sha256")] == ["pastel-hand", [9, 193, 18], "a" * 64]


def test_a_cut_out_that_does_not_say_what_was_keyed_out_is_an_error():
    data = dump([with_cutout(GENERATED, (9, 193, 18), [], "pastel-hand", "a" * 64)])
    assert data["candidates"][0]["cutout"]["mask"] == {"pass": True}
    del data["candidates"][0]["cutout"]["key"]
    assert load(data) == ([], ["candidate 1: cutout must name its file and the key colour it was cut out with"])


def test_contact_sheets_hold_twenty_in_a_grid_of_five():
    assert sheets(45) == [range(0, 20), range(20, 40), range(40, 45)]
    assert sheets(0) == []
    assert sheet_size(20) == (1600, 1280) and sheet_size(5) == (1600, 320)
    assert cell_origin(0) == (0, 0) and cell_origin(7) == (640, 320)


def test_each_stock_candidate_shows_the_query_that_found_it_beside_its_id():
    entries = dump([stock(1), GENERATED])["candidates"]
    assert list(entries[0])[:4] == ["n", "id", "query", "queries"] and entries[0]["query"] == "older woman phone"
    assert "query" not in entries[1] and "queries" not in entries[1]


def again(candidate, query):
    return Candidate(candidate.id, 1, 1, "https://images.example/other.jpeg", "https://images.example/other.jpeg",
                     {**candidate.provenance, "query": query})


def test_a_photo_another_search_finds_again_records_that_search_and_keeps_its_first_query_as_provenance():
    first = with_original(stock(1), ".jpg", 3000, 2000)
    merged = merge([first], [again(first, "grandmother phone"), again(first, "older woman phone"),
                             again(first, "kenyan woman")])
    [c] = merged
    assert c.queries == ("older woman phone", "grandmother phone", "kenyan woman")
    assert c.query == c.provenance["query"] == "older woman phone"
    assert (c.full, c.width) == ("originals/pexels-1.jpg", 3000), "the rest of the record is the first one's"
    assert dump(merged)["candidates"][0]["queries"] == ["older woman phone", "grandmother phone", "kenyan woman"]
    assert load(dump(merged)) == (merged, [])
    assert merge([GENERATED], [GENERATED]) == [GENERATED]


def test_queries_that_do_not_start_with_the_provenance_query_are_an_error():
    data = dump([stock(1)])
    data["candidates"][0]["queries"] = ["grandmother phone", "older woman phone"]
    assert load(data) == ([], ["candidate 1: queries must be a list starting with its provenance query, "
                               "'older woman phone'"])


def test_a_downloaded_original_is_what_the_candidate_names_and_its_record_keeps_the_url_fetched():
    local = with_original(stock(1), ".jpg", 2000, 3000)
    assert (local.full, local.preview, local.width, local.height) == (
        "originals/pexels-1.jpg", "originals/pexels-1.jpg", 2000, 3000)
    assert local.provenance == {**stock(1).provenance, "download_url": "https://images.example/1.jpeg"}
    assert kept_record(local, SHA, "A. Author", TODAY)[1] == []


def test_a_candidate_records_the_search_options_that_found_it_beside_its_query():
    plain = stock(1)
    assert with_search_options(plain, {}) is plain
    square = with_search_options(plain, {"orientation": "square"})
    assert square.provenance["search_options"] == {"orientation": "square"}
    assert square.query == "older woman phone" and square.id == plain.id
    assert kept_record(square, SHA, "A. Author", TODAY)[1] == []


def test_a_quarter_turn_in_exif_swaps_the_displayed_width_and_height():
    assert displayed_size(4000, 3000, 6) == (3000, 4000)
    assert displayed_size(4000, 3000, 1) == displayed_size(4000, 3000, None) == (4000, 3000)


def test_thumbnails_shrink_to_fit_keeping_aspect_but_never_grow():
    assert fit(3000, 2000, 640) == (640, 427)
    assert fit(2000, 3000, 320) == (213, 320)
    assert fit(200, 100, 640) == (200, 100)
