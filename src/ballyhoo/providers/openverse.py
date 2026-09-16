"""Openverse image search (https://api.openverse.org/v1/), anonymously.

Only CC0 and Public Domain Mark images: CC BY and the other licences need a
credit that an ad cannot carry. Openverse does not verify licences, so the
record keeps the page the image came from for checking by hand.
"""
import math

from ..candidates import Candidate
from . import Request

NAME = "openverse"
MAX_PAGE_SIZE = 20  # the most an anonymous request may ask for
SEARCH_OPTIONS = ()  # so an option named for Openverse in a brief is an error, never ignored
LICENCES = {"cc0": "CC0", "pdm": "Public Domain Mark"}
PRICE = {"checked": "2026-09-14", "source": "https://docs.openverse.org/api/reference/authentication_and_throttling.html",
         "per_request": 0.0}


def search_price(n):
    """USD for a search of `n` results: Openverse charges nothing for anonymous requests."""
    return PRICE["per_request"] * math.ceil(n / MAX_PAGE_SIZE)


def search_request(query, page, per_page, env):
    return Request("GET", "https://api.openverse.org/v1/images/",
                   params={"q": query, "page": page, "page_size": min(per_page, MAX_PAGE_SIZE),
                           "license": ",".join(LICENCES), "mature": "false"})


def parse_search(payload, query):
    """Returns (candidates, whether there is another page).

    Results without a creator, a size or a licence we can use are not candidates.
    """
    found = []
    for r in payload.get("results", []):
        if r.get("license") not in LICENCES or not (r.get("creator") and r.get("width") and r.get("height")):
            continue
        record = {"source": "stock", "provider": "openverse", "id": r["id"], "page_url": r["foreign_landing_url"],
                  "creator": r["creator"], "licence": f"{LICENCES[r['license']]} {r.get('license_version', '')}".strip(),
                  "licence_url": r["license_url"], "query": query}
        if r.get("creator_url"):
            record["creator_url"] = r["creator_url"]
        for key in ("title", "source"):
            if r.get(key):
                record["host" if key == "source" else key] = r[key]
        found.append(Candidate(f"openverse-{r['id']}", r["width"], r["height"], r["url"], r["thumbnail"], record))
    return found, payload.get("page", 1) < payload.get("page_count", 0)
