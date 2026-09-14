"""Adobe Firefly Services image generation, Image 5 (https://developer.adobe.com/firefly-services/docs/firefly-api/).

OAuth server-to-server: trade the client id and secret for a 24-hour token,
submit to generate-async, poll the status URL until it succeeds, then download
the pre-signed image URL, which expires in an hour. Firefly Services needs an
Adobe enterprise contract and allows about 4 requests a minute, so polling is
slow. Adobe requires Content Credentials on every output and forbids removing
them; the image is kept as delivered.
"""
import math

from . import Request, credential

NAME = "firefly"
CLIENT_ID = "FIREFLY_SERVICES_CLIENT_ID"
CLIENT_SECRET = "FIREFLY_SERVICES_CLIENT_SECRET"
MODEL = "image5"
POLL_SECONDS = 15
SCOPES = "openid,AdobeID,session,additional_info,read_organizations,firefly_api,ff_apis"
ASPECT_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16")
UNFINISHED = ("pending", "running", "cancel_pending")
# Adobe publishes no per-image price for the API: it comes with an enterprise contract.
PRICE = {"checked": "2026-09-14", "source": "https://developer.adobe.com/firefly-services/docs/firefly-api/",
         "per_image": {}}


class Refused(Exception):
    pass


def image_price(model, width, height):
    """None: an estimate cannot include Firefly."""
    return PRICE["per_image"].get(model)


def token_request(env):
    return Request("POST", "https://ims-na1.adobelogin.com/ims/token/v3", data={
        "grant_type": "client_credentials", "client_id": credential(env, CLIENT_ID),
        "client_secret": credential(env, CLIENT_SECRET), "scope": SCOPES})


def parse_token(payload):
    return payload["access_token"]


def aspect_ratio(width, height):
    g = math.gcd(width, height)
    ratio = f"{width // g}:{height // g}"
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"{width}x{height} is {ratio}; Firefly Image 5 generates {', '.join(ASPECT_RATIOS)}")
    return ratio


def _headers(env, token):
    return {"Authorization": f"Bearer {token}", "x-api-key": credential(env, CLIENT_ID)}


def generate_request(prompt, seed, width, height, env, token, model=MODEL):
    if model != MODEL:
        raise ValueError(f"only Firefly {MODEL} is supported, not {model!r}")
    return Request("POST", "https://firefly-api.adobe.io/v4/images/generate-async",
                   headers={**_headers(env, token), "x-model-version": model},
                   json={"prompt": prompt, "aspectRatio": aspect_ratio(width, height), "numVariations": 1,
                         "seeds": [seed]})


def parse_submission(payload):
    """(status URL, result URL): the status reply carries the result."""
    url = payload["links"]["result"]["href"]
    return url, url


def poll_request(url, env, token=None):
    return Request("GET", url, headers=_headers(env, token))


def parse_status(payload):
    status = payload.get("status")
    if status == "succeeded":
        return True
    if status in UNFINISHED:
        return False
    raise Refused(f"job {status}: {payload.get('error_code', '')} {payload.get('message', '')}".strip())


def parse_result(payload):
    outputs = (payload.get("result") or {}).get("outputs") or []
    if not outputs:
        raise Refused("no image in the result")
    return outputs[0]["image"]["url"]
