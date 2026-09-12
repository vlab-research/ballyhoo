"""FLUX on fal.ai, through fal's queue (https://fal.ai/docs/model-apis/model-endpoints/queue).

Submit, poll the status URL until COMPLETED, read the result, download the
image. Result URLs last at least seven days, but the image is saved as soon as
it is ready. fal's copies carry no C2PA credentials; BFL's own API adds them.
"""
from . import Request, credential

NAME = "fal"
KEY = "FAL_KEY"
MODEL = "fal-ai/flux-2-pro"


class Refused(Exception):
    pass


def _auth(env):
    return {"Authorization": f"Key {credential(env, KEY)}"}


def generate_request(prompt, seed, width, height, env, token=None, model=MODEL):
    return Request("POST", f"https://queue.fal.run/{model}", headers=_auth(env),
                   json={"prompt": prompt, "seed": seed, "image_size": {"width": width, "height": height},
                         "output_format": "png"})


def parse_submission(payload):
    """(status URL, result URL) for a queued request."""
    return payload["status_url"], payload["response_url"]


def poll_request(url, env, token=None):
    return Request("GET", url, headers=_auth(env))


def parse_status(payload):
    """Whether the request has finished."""
    status = payload.get("status")
    if status == "COMPLETED":
        return True
    if status in ("IN_QUEUE", "IN_PROGRESS"):
        return False
    raise Refused(f"unexpected queue status {status!r}")


def parse_result(payload):
    """The image URL."""
    if payload.get("detail"):
        raise Refused(f"generation failed: {payload['detail']}")
    images = payload.get("images") or []
    if not images:
        raise Refused("no image in the result")
    if any(payload.get("has_nsfw_concepts") or []):
        raise Refused("fal's safety checker flagged the image")
    return images[0]["url"]
