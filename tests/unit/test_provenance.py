import datetime

import pytest

from ballyhoo.provenance import image_refs, made, problems, sidecar_name

SHA = "a" * 64
STOCK = {
    "source": "stock", "sha256": SHA, "provider": "pexels", "id": "3573351",
    "page_url": "https://www.pexels.com/photo/3573351/", "creator": "Lukas Rodriguez",
    "licence": "Pexels License", "licence_url": "https://www.pexels.com/license/",
    "query": "older woman phone kenya", "fetched": datetime.date(2026, 9, 12),
    "picked": {"by": "A. Author", "on": datetime.date(2026, 9, 12)},
}
GENERATED = {
    "source": "generated", "sha256": SHA, "provider": "gemini", "model": "gemini-3.1-flash-image",
    "prompt": "An older Kenyan woman reading her phone at a market stall", "seed": 7,
    "generated": "2026-09-12", "picked": {"by": "A. Author", "on": "2026-09-12"},
}


def test_images_need_provenance_but_fonts_and_stylesheets_do_not():
    refs = ["../../fonts/Hind-Bold.ttf", "../../scenes/market.JPG", "band.png", "shared.css", "hills.svg"]
    assert image_refs(refs) == ["../../scenes/market.JPG", "band.png", "hills.svg"]


def test_the_sidecar_sits_beside_the_image_with_the_image_name_in_full():
    assert sidecar_name("market.jpg") == "market.jpg.provenance.yaml"


@pytest.mark.parametrize("record", [STOCK, GENERATED, made(SHA, "The partner's designer", "Made for vlab ads")])
def test_a_complete_record_for_this_file_has_no_problems(record):
    assert problems(record, SHA) == []


def test_every_missing_field_is_named():
    record = {**STOCK, "creator": "  ", "licence_url": None}
    del record["query"]
    assert problems(record, SHA) == ["provenance is missing creator, licence_url, query"]


def test_a_stock_photo_or_generated_image_needs_the_person_who_picked_it():
    unpicked = {k: v for k, v in GENERATED.items() if k != "picked"}
    assert problems(unpicked, SHA) == ["provenance is missing picked"]
    assert problems({**STOCK, "picked": {"by": "", "on": "2026-09-12"}}, SHA) == [
        "provenance picked needs by (the person who picked it) and on (a date)"]
    assert problems({**STOCK, "picked": "yes"}, SHA) != []


def test_a_record_written_for_another_file_is_rejected():
    assert problems(STOCK, "b" * 64) == [
        "provenance sha256 is not this file's: the image changed after its provenance was written"]


def test_an_unknown_source_is_rejected_rather_than_guessed():
    assert problems({**STOCK, "source": "partner"}, SHA) == [
        "provenance source must be one of made, stock, generated, not 'partner'"]
    assert problems(["stock"], SHA) == ["provenance must be a map"]


def test_dates_and_seeds_are_typed():
    assert problems({**STOCK, "fetched": "last week"}, SHA) == ["provenance fetched must be a date"]
    assert problems({**GENERATED, "seed": "7"}, SHA) == ["provenance seed must be a whole number"]
    assert problems({**GENERATED, "seed": True}, SHA) == ["provenance seed must be a whole number"]
    assert problems({**GENERATED, "seed": 0}, SHA) == []
