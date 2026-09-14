import datetime

import pytest

from ballyhoo.candidates import (Candidate, cell_origin, displayed_size, dump, extension, fit, kept_record, load,
                                 merge, parse_picks, plan_keep, sheet_size, sheets, with_original)
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


def test_contact_sheets_hold_twenty_in_a_grid_of_five():
    assert sheets(45) == [range(0, 20), range(20, 40), range(40, 45)]
    assert sheets(0) == []
    assert sheet_size(20) == (1600, 1280) and sheet_size(5) == (1600, 320)
    assert cell_origin(0) == (0, 0) and cell_origin(7) == (640, 320)


def test_each_stock_candidate_shows_the_query_that_found_it_beside_its_id():
    entries = dump([stock(1), GENERATED])["candidates"]
    assert list(entries[0])[:3] == ["n", "id", "query"] and entries[0]["query"] == "older woman phone"
    assert "query" not in entries[1]


def test_a_downloaded_original_is_what_the_candidate_names_and_its_record_keeps_the_url_fetched():
    local = with_original(stock(1), ".jpg", 2000, 3000)
    assert (local.full, local.preview, local.width, local.height) == (
        "originals/pexels-1.jpg", "originals/pexels-1.jpg", 2000, 3000)
    assert local.provenance == {**stock(1).provenance, "download_url": "https://images.example/1.jpeg"}
    assert kept_record(local, SHA, "A. Author", TODAY)[1] == []


def test_a_quarter_turn_in_exif_swaps_the_displayed_width_and_height():
    assert displayed_size(4000, 3000, 6) == (3000, 4000)
    assert displayed_size(4000, 3000, 1) == displayed_size(4000, 3000, None) == (4000, 3000)


def test_thumbnails_shrink_to_fit_keeping_aspect_but_never_grow():
    assert fit(3000, 2000, 640) == (640, 427)
    assert fit(2000, 3000, 320) == (213, 320)
    assert fit(200, 100, 640) == (200, 100)
