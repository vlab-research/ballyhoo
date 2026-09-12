import pytest

from ballyhoo.providers import MissingCredential, openverse, pexels
from ballyhoo.provenance import problems

PEXELS_PAGE = {
    "page": 1, "per_page": 2, "next_page": "https://api.pexels.com/v1/search/?page=2&per_page=2&query=x",
    "photos": [{
        "id": 101, "width": 3066, "height": 3968, "url": "https://www.pexels.com/photo/market-101/",
        "photographer": "Jane Doe", "photographer_url": "https://www.pexels.com/@jane", "alt": "A woman at a stall",
        "src": {"original": "https://images.pexels.com/photos/101/p.jpeg", "large": "https://images.pexels.com/l.jpeg"},
    }, {
        "id": 102, "width": 2000, "height": 2000, "url": "https://www.pexels.com/photo/102/", "alt": "",
        "photographer": "Juma K", "photographer_url": "https://www.pexels.com/@juma",
        "src": {"original": "https://images.pexels.com/photos/102/p.png", "large": "https://images.pexels.com/m.jpeg"},
    }],
}

OPENVERSE_PAGE = {
    "result_count": 3, "page_count": 1, "page": 1,
    "results": [
        {"id": "4bd0e5a2-0000-4000-8000-000000000001", "title": "Grandmother", "license": "cc0", "license_version": "1.0",
         "license_url": "https://creativecommons.org/publicdomain/zero/1.0/", "creator": "A. Photographer",
         "creator_url": None, "url": "https://live.staticflickr.com/1/a.jpg", "width": 1024, "height": 683,
         "foreign_landing_url": "https://www.flickr.com/photos/x/1", "source": "flickr",
         "thumbnail": "https://api.openverse.org/v1/images/4bd0e5a2-0000-4000-8000-000000000001/thumb/"},
        {"id": "4bd0e5a2-0000-4000-8000-000000000002", "license": "by", "creator": "B", "width": 10, "height": 10},
        {"id": "4bd0e5a2-0000-4000-8000-000000000003", "license": "pdm", "creator": "", "width": 10, "height": 10},
    ],
}


def test_pexels_sends_the_key_as_the_authorization_header_and_caps_the_page_size():
    request = pexels.search_request("older woman phone", 2, 200, {"PEXELS_API_KEY": "k"})
    assert request.url == "https://api.pexels.com/v1/search"
    assert request.headers == {"Authorization": "k"}
    assert request.params == {"query": "older woman phone", "page": 2, "per_page": 80}


def test_a_missing_key_names_the_variable_rather_than_skipping_the_provider():
    with pytest.raises(MissingCredential, match="PEXELS_API_KEY is not set in the environment"):
        pexels.search_request("x", 1, 10, {"PEXELS_API_KEY": " "})


def test_pexels_results_become_candidates_whose_records_are_complete_once_kept():
    found, more = pexels.parse_search(PEXELS_PAGE, "older woman phone")
    assert more and [c.id for c in found] == ["pexels-101", "pexels-102"]
    first = found[0]
    assert (first.width, first.height, first.full) == (3066, 3968, "https://images.pexels.com/photos/101/p.jpeg")
    assert first.provenance["alt"] == "A woman at a stall" and "alt" not in found[1].provenance
    kept = {**first.provenance, "sha256": "0" * 64, "fetched": "2026-09-12", "picked": {"by": "A", "on": "2026-09-12"}}
    assert problems(kept, "0" * 64) == []


def test_openverse_asks_only_for_licences_an_ad_can_use_without_a_credit():
    request = openverse.search_request("grandmother phone", 1, 40, {})
    assert request.headers == {}
    assert request.params == {"q": "grandmother phone", "page": 1, "page_size": 20, "license": "cc0,pdm",
                              "mature": "false"}


def test_openverse_drops_results_it_cannot_credit_or_use():
    found, more = openverse.parse_search(OPENVERSE_PAGE, "grandmother phone")
    assert not more
    [c] = found
    assert c.id == "openverse-4bd0e5a2-0000-4000-8000-000000000001"
    assert c.provenance == {
        "source": "stock", "provider": "openverse", "id": "4bd0e5a2-0000-4000-8000-000000000001",
        "page_url": "https://www.flickr.com/photos/x/1", "creator": "A. Photographer", "licence": "CC0 1.0",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/", "query": "grandmother phone",
        "title": "Grandmother", "host": "flickr"}
