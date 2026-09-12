"""Image providers: the requests each API needs, and candidates from its replies.

Pure. Each provider module builds Requests and parses JSON; sourcing.py sends
them. Credentials come from the environment the shell passes in, and a missing
one is an error naming the variable, never a skipped provider.
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


def credential(env, name):
    value = (env.get(name) or "").strip()
    if not value:
        raise MissingCredential(f"{name} is not set in the environment")
    return value
