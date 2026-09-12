import pytest

from ballyhoo.providers import MissingCredential, fal

ENV = {"FAL_KEY": "k"}


def test_a_generation_is_queued_with_the_key_the_exact_size_and_png_output():
    request = fal.generate_request("An older Moroccan man with his phone", 5, 1080, 1350, ENV)
    assert (request.method, request.url) == ("POST", "https://queue.fal.run/fal-ai/flux-2-pro")
    assert request.headers == {"Authorization": "Key k"}
    assert request.json == {"prompt": "An older Moroccan man with his phone", "seed": 5,
                            "image_size": {"width": 1080, "height": 1350}, "output_format": "png"}
    assert fal.generate_request("x", 1, 8, 8, ENV, model="fal-ai/flux-2-max").url.endswith("/fal-ai/flux-2-max")


def test_a_missing_key_names_the_variable():
    with pytest.raises(MissingCredential, match="FAL_KEY is not set"):
        fal.generate_request("x", 1, 1080, 1080, {})


def test_polling_follows_the_urls_fal_returns_and_waits_until_completed():
    status_url, result_url = fal.parse_submission({"request_id": "r1", "status_url": "https://queue.fal.run/s",
                                                   "response_url": "https://queue.fal.run/r"})
    assert fal.poll_request(status_url, ENV).headers == {"Authorization": "Key k"}
    assert fal.parse_status({"status": "IN_QUEUE", "queue_position": 3}) is False
    assert fal.parse_status({"status": "IN_PROGRESS"}) is False
    assert fal.parse_status({"status": "COMPLETED"}) is True
    with pytest.raises(fal.Refused, match="unexpected queue status 'CANCELLED'"):
        fal.parse_status({"status": "CANCELLED"})


def test_the_result_is_the_first_image_unless_it_failed_or_was_flagged():
    image = {"url": "https://v3.fal.media/files/a.png", "width": 1080, "height": 1350, "content_type": "image/png"}
    assert fal.parse_result({"images": [image], "seed": 5}) == "https://v3.fal.media/files/a.png"
    with pytest.raises(fal.Refused, match="safety checker"):
        fal.parse_result({"images": [image], "has_nsfw_concepts": [True]})
    with pytest.raises(fal.Refused, match="generation failed: prompt too long"):
        fal.parse_result({"detail": "prompt too long"})
    with pytest.raises(fal.Refused, match="no image"):
        fal.parse_result({"images": []})
