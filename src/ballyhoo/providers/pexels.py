"""Pexels photo search (https://www.pexels.com/api/documentation/).

Its licence forbids showing someone as suffering from or medicating for an
ailment, political use, and implying that a pictured person endorses anything.
Nothing has to be requested when a photo is used.

Of its filters only `orientation` is offered. `size` changes nothing: results
are already far larger than an ad, and the original is downloaded whatever it
says. `color` selects the palette documentary photography already has, which
`docs/creative-rules.md` § Audience bars.
"""
import math

from ..candidates import Candidate
from . import Request, credential

NAME = "pexels"
KEY = "PEXELS_API_KEY"
MAX_PER_PAGE = 80
SEARCH_OPTIONS = ("orientation",)
ORIENTATIONS = ("landscape", "portrait", "square")
LICENCE = ("Pexels License", "https://www.pexels.com/license/")
PRICE = {"checked": "2026-09-14", "source": "https://www.pexels.com/api/documentation/", "per_request": 0.0}


def search_price(n):
    """USD for a search of `n` results: the API is free."""
    return PRICE["per_request"] * math.ceil(n / MAX_PER_PAGE)


def search_request(query, page, per_page, env, orientation=None):
    if orientation is not None and orientation not in ORIENTATIONS:
        raise ValueError(f"orientation {orientation!r} must be one of {', '.join(ORIENTATIONS)}")
    params = {"query": query, "page": page, "per_page": min(per_page, MAX_PER_PAGE)}
    if orientation:
        params["orientation"] = orientation
    return Request("GET", "https://api.pexels.com/v1/search", params=params,
                   headers={"Authorization": credential(env, KEY)})


def parse_search(payload, query):
    """Returns (candidates, whether there is another page)."""
    found = []
    for photo in payload.get("photos", []):
        record = {"source": "stock", "provider": "pexels", "id": str(photo["id"]), "page_url": photo["url"],
                  "creator": photo["photographer"], "creator_url": photo["photographer_url"],
                  "licence": LICENCE[0], "licence_url": LICENCE[1], "query": query}
        if photo.get("alt"):
            record["alt"] = photo["alt"]
        found.append(Candidate(f"pexels-{photo['id']}", photo["width"], photo["height"],
                               photo["src"]["original"], photo["src"]["large"], record))
    return found, bool(payload.get("next_page"))
