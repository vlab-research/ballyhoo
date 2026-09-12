"""Image providers: the requests each API needs, and candidates from its replies.

Pure. Each provider module builds Requests and parses JSON; sourcing.py sends
them. Credentials come from the environment the shell passes in, and a missing
one is an error naming the variable, never a skipped provider.

A stock provider has search_request and parse_search. A generator has
generate_request and either parse_image (the reply holds the image) or
parse_submission, poll_request, parse_status and parse_result (it queues).
A generator that needs a token first has token_request and parse_token.
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
