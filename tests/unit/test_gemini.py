import base64
import datetime

import pytest

from ballyhoo.candidates import generated_candidate, kept_record
from ballyhoo.providers import MissingCredential
from ballyhoo.providers.gemini import Refused, aspect_ratio, generate_request, parse_image

ENV = {"GOOGLE_CLOUD_PROJECT": "study-project"}


def test_a_size_reduces_to_one_of_geminis_aspect_ratios_or_is_refused():
    assert aspect_ratio(1080, 1350) == "4:5"
    assert aspect_ratio(1080, 1080) == "1:1"
    assert aspect_ratio(1920, 1080) == "16:9"
    with pytest.raises(ValueError, match="1200x628 is 300:157; Gemini generates 1:1, "):
        aspect_ratio(1200, 628)


def test_the_request_names_the_paying_project_and_asks_for_an_image_of_adults_only():
    request = generate_request("An older woman reading her phone", 7, 1080, 1350, ENV, "tok")
    assert request.method == "POST"
    assert request.url == ("https://aiplatform.googleapis.com/v1/projects/study-project/locations/global"
                           "/publishers/google/models/gemini-3.1-flash-image:generateContent")
    assert request.headers == {"Authorization": "Bearer tok"}
    assert request.json["contents"] == [{"role": "user", "parts": [{"text": "An older woman reading her phone"}]}]
    assert request.json["generationConfig"] == {
        "responseModalities": ["IMAGE"], "seed": 7,
        "imageConfig": {"aspectRatio": "4:5", "imageSize": "2K", "personGeneration": "ALLOW_ADULT"}}


def test_the_project_is_never_guessed():
    with pytest.raises(MissingCredential, match="GOOGLE_CLOUD_PROJECT"):
        generate_request("x", 1, 1080, 1080, {}, "tok")
    with pytest.raises(ValueError, match="image size '8K'"):
        generate_request("x", 1, 1080, 1080, ENV, "tok", image_size="8K")


def test_the_image_is_returned_as_the_bytes_delivered():
    payload = {"candidates": [{"content": {"parts": [
        {"text": "Here is your image."},
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(b"\xff\xd8\xffjpeg").decode()}}]},
        "finishReason": "STOP"}]}
    assert parse_image(payload) == b"\xff\xd8\xffjpeg"


def test_a_refusal_says_why_whether_blocked_or_answered_in_text():
    with pytest.raises(Refused, match="prompt refused: PROHIBITED_CONTENT"):
        parse_image({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}})
    with pytest.raises(Refused, match=r"no image \(finish reason IMAGE_SAFETY\)"):
        parse_image({"candidates": [{"finishReason": "IMAGE_SAFETY"}]})
    with pytest.raises(Refused, match=r"no image \(finish reason STOP\): I can't draw that."):
        parse_image({"candidates": [{"content": {"parts": [{"text": "I can't draw that."}]}, "finishReason": "STOP"}]})


def test_a_generated_candidate_is_named_by_its_content_and_is_complete_once_picked():
    today = datetime.date(2026, 9, 12)
    c = generated_candidate("gemini", "gemini-3.1-flash-image", "An older woman", 7, "ab" * 32, ".jpg", 1856, 2304,
                            today)
    assert c.id == "gemini-abababababab" and c.full == c.preview == "generated/gemini-abababababab.jpg"
    assert kept_record(c, "ab" * 32, "A. Author", today)[1] == []
