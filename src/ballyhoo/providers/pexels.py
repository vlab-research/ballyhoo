"""Pexels photo search (https://www.pexels.com/api/documentation/).

Its licence forbids showing someone as suffering from or medicating for an
ailment, political use, and implying that a pictured person endorses anything.
Nothing has to be requested when a photo is used.
"""
from ..candidates import Candidate
from . import Request, credential

KEY = "PEXELS_API_KEY"
MAX_PER_PAGE = 80
LICENCE = ("Pexels License", "https://www.pexels.com/license/")


def search_request(query, page, per_page, env):
    return Request("GET", "https://api.pexels.com/v1/search",
                   params={"query": query, "page": page, "per_page": min(per_page, MAX_PER_PAGE)},
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
