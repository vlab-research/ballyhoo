import pytest

from ballyhoo.providers import MissingCredential, firefly

ENV = {"FIREFLY_SERVICES_CLIENT_ID": "cid", "FIREFLY_SERVICES_CLIENT_SECRET": "secret"}


def test_the_token_comes_from_the_client_credentials_as_a_form():
    request = firefly.token_request(ENV)
    assert (request.method, request.url) == ("POST", "https://ims-na1.adobelogin.com/ims/token/v3")
    assert request.data["grant_type"] == "client_credentials" and request.data["client_id"] == "cid"
    assert "firefly_api" in request.data["scope"].split(",")
    assert firefly.parse_token({"access_token": "t", "expires_in": 86399}) == "t"
    with pytest.raises(MissingCredential, match="FIREFLY_SERVICES_CLIENT_SECRET"):
        firefly.token_request({"FIREFLY_SERVICES_CLIENT_ID": "cid"})


def test_a_generation_sends_the_token_the_client_id_and_the_model_version():
    request = firefly.generate_request("A family at home in Morocco", 9, 1080, 1080, ENV, "t")
    assert request.url == "https://firefly-api.adobe.io/v4/images/generate-async"
    assert request.headers == {"Authorization": "Bearer t", "x-api-key": "cid", "x-model-version": "image5"}
    assert request.json == {"prompt": "A family at home in Morocco", "aspectRatio": "1:1", "numVariations": 1,
                            "seeds": [9]}


def test_shapes_image5_cannot_generate_are_refused_before_any_request():
    with pytest.raises(ValueError, match="1080x1350 is 4:5; Firefly Image 5 generates 1:1, 4:3, 3:4"):
        firefly.generate_request("x", 1, 1080, 1350, ENV, "t")
    with pytest.raises(ValueError, match="only Firefly image5"):
        firefly.generate_request("x", 1, 1080, 1080, ENV, "t", model="image4_ultra")


def test_the_job_is_polled_until_it_succeeds_and_a_failure_says_why():
    status_url, result_url = firefly.parse_submission(
        {"links": {"result": {"href": "https://firefly-api.adobe.io/v3/status/job-1"}}, "progress": 0})
    assert status_url == result_url == "https://firefly-api.adobe.io/v3/status/job-1"
    assert firefly.poll_request(status_url, ENV, "t").headers == {"Authorization": "Bearer t", "x-api-key": "cid"}
    assert firefly.parse_status({"status": "running"}) is False
    assert firefly.parse_status({"status": "succeeded"}) is True
    with pytest.raises(firefly.Refused, match="job failed: prompt_unsafe The prompt is unsafe"):
        firefly.parse_status({"status": "failed", "error_code": "prompt_unsafe", "message": "The prompt is unsafe"})
    succeeded = {"status": "succeeded", "result": {"outputs": [{"seed": 9, "image": {"url": "https://s3.example/a"}}]}}
    assert firefly.parse_result(succeeded) == "https://s3.example/a"
