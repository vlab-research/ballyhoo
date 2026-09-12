"""Gemini image generation on Vertex AI, through generateContent.

Vertex, not the Gemini Developer API: person controls work only there, and
Google's generative AI indemnity covers GA models on Vertex only. The project
that pays is named by GOOGLE_CLOUD_PROJECT, never taken from gcloud's default.
Images come back opaque and usually as JPEG; they are kept as delivered, since
re-encoding breaks their C2PA credentials. The seed is best effort only.
"""
import base64
import math

from . import Request, credential

NAME = "gemini"
AUTH = "google-adc"
PROJECT = "GOOGLE_CLOUD_PROJECT"
MODEL = "gemini-3.1-flash-image"
IMAGE_SIZES = ("1K", "2K", "4K")
ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


class Refused(Exception):
    pass


def aspect_ratio(width, height):
    """The supported ratio a size reduces to exactly, e.g. 1080x1350 -> 4:5."""
    g = math.gcd(width, height)
    ratio = f"{width // g}:{height // g}"
    if ratio not in ASPECT_RATIOS:
        raise ValueError(f"{width}x{height} is {ratio}; Gemini generates {', '.join(ASPECT_RATIOS)}")
    return ratio


def generate_request(prompt, seed, width, height, env, token, model=MODEL, image_size="2K"):
    if image_size not in IMAGE_SIZES:
        raise ValueError(f"image size {image_size!r} must be one of {', '.join(IMAGE_SIZES)}")
    project = credential(env, PROJECT)
    url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global"
           f"/publishers/google/models/{model}:generateContent")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "seed": seed,
            "imageConfig": {"aspectRatio": aspect_ratio(width, height), "imageSize": image_size,
                            "personGeneration": "ALLOW_ADULT"},
        },
    }
    return Request("POST", url, headers={"Authorization": f"Bearer {token}"}, json=body)


def parse_image(payload):
    """The first image's bytes. A refusal comes back as text or a block reason, never as an error status."""
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise Refused(f"prompt refused: {reason}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    for part in parts:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    said = " ".join(p["text"].strip() for p in parts if p.get("text"))
    raise Refused(f"no image (finish reason {candidates[0].get('finishReason')})" + (f": {said}" if said else ""))
