"""Image providers: the requests each API needs, and candidates from its replies.

Pure. Each provider module builds Requests and parses JSON; sourcing.py sends
them. Credentials come from the environment the shell passes in, and a missing
one is an error naming the variable, never a skipped provider.

Every provider has NAME and PRICE (what it charges, with the date that was
checked and where). A stock provider has search_request, parse_search and
search_price. A generator has generate_request, image_price (None when there is
no published price), and either parse_image (the reply holds the image) or
parse_submission, poll_request, parse_status and parse_result (it queues). A
generator that needs a token first has token_request and parse_token.

A provider that takes options beyond the query, or beyond the model and seed,
lists them: SEARCH_OPTIONS for a search, OPTIONS for a generation. They arrive
as keyword arguments to the request builder, which raises ValueError on a value
it cannot use, so a brief is stopped by a bad option before anything is sent.
"""
from dataclasses import dataclass, field


class MissingCredential(Exception):
    pass


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    json: dict | None = None
    data: dict | None = None  # a form body


def credential(env, name):
    value = (env.get(name) or "").strip()
    if not value:
        raise MissingCredential(f"{name} is not set in the environment")
    return value
