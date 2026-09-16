"""Search, contact sheets and keep, against a mock HTTP transport: no network, no browser."""
import datetime
import io
import json

import httpx
import yaml
from PIL import Image

from ballyhoo import art, sourcing
from ballyhoo.provenance import problems
from ballyhoo.providers import fal, firefly, gemini, pexels

TODAY = datetime.date(2026, 9, 12)


def jpeg(colour, size=(900, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "JPEG")
    return buf.getvalue()


def photo(i):
    return {"id": i, "width": 3000, "height": 2000, "url": f"https://www.pexels.com/photo/{i}/", "alt": f"photo {i}",
            "photographer": "Jane Doe", "photographer_url": "https://www.pexels.com/@jane",
            "src": {"original": f"https://images.pexels.com/{i}/original", "large": f"https://images.pexels.com/{i}/large"}}


class FakePexels:
    """Pages of two photos, 1 to 5; every image URL serves a JPEG."""

    def __init__(self):
        self.searches = []
        self.orientations = []

    def __call__(self, request):
        if request.url.host == "api.pexels.com":
            assert request.headers["Authorization"] == "test-key"
            page = int(request.url.params["page"])
            self.searches.append((request.url.params["query"], page))
            self.orientations.append(request.url.params.get("orientation"))
            ids = [i for i in range(1, 6)][(page - 1) * 2:page * 2]
            return httpx.Response(200, json={"photos": [photo(i) for i in ids], "next_page": "more" if page < 3 else None})
        return httpx.Response(200, content=jpeg((40 * int(request.url.path.split("/")[1]), 90, 90)))


def run_search(tmp_path, fake, query, n):
    with sourcing.client(transport=httpx.MockTransport(fake)) as http:
        found = sourcing.search(http, pexels, query, n, env={"PEXELS_API_KEY": "test-key"})
        return sourcing.add_candidates(tmp_path / "cands", found, http)


def test_search_pages_until_it_has_enough_and_writes_candidates_thumbnails_and_a_sheet(tmp_path):
    fake = FakePexels()
    merged, sheets = run_search(tmp_path, fake, "older woman phone", 3)
    assert fake.searches == [("older woman phone", 1), ("older woman phone", 2)]
    assert [c.id for c in merged] == ["pexels-1", "pexels-2", "pexels-3"]
    data = yaml.safe_load((tmp_path / "cands" / "candidates.yaml").read_text())
    assert [(e["n"], e["id"], e["thumb"]) for e in data["candidates"]] == [
        (1, "pexels-1", "thumbs/pexels-1.jpg"), (2, "pexels-2", "thumbs/pexels-2.jpg"),
        (3, "pexels-3", "thumbs/pexels-3.jpg")]
    with Image.open(tmp_path / "cands" / "thumbs" / "pexels-1.jpg") as thumb:
        assert thumb.size == (640, 427)
    assert [p.name for p in sheets] == ["sheet-01.png"]
    with Image.open(sheets[0]) as sheet:
        assert sheet.size == (1600, 320)


def test_a_search_that_finds_nothing_still_writes_an_empty_candidates_file(tmp_path):
    def nothing(request):
        return httpx.Response(200, json={"photos": [], "next_page": None})

    merged, sheets = run_search(tmp_path, nothing, "nobody", 5)
    assert merged == [] and sheets == []
    assert yaml.safe_load((tmp_path / "cands" / "candidates.yaml").read_text()) == {"candidates": []}


def test_a_search_sends_the_providers_options_and_every_record_keeps_them(tmp_path):
    fake = FakePexels()
    with sourcing.client(transport=httpx.MockTransport(fake)) as http:
        found = sourcing.search(http, pexels, "arab man portrait", 2, env={"PEXELS_API_KEY": "test-key"},
                                orientation="square")
    assert fake.orientations == ["square"]
    assert [c.provenance["search_options"] for c in found] == [{"orientation": "square"}] * 2
    assert "search_options" not in run_search(tmp_path, FakePexels(), "arab man portrait", 2)[0][0].provenance


def test_a_second_search_into_the_same_directory_keeps_the_numbers(tmp_path):
    run_search(tmp_path, FakePexels(), "older woman phone", 2)
    merged, _ = run_search(tmp_path, FakePexels(), "grandmother phone", 4)
    assert [c.id for c in merged] == ["pexels-1", "pexels-2", "pexels-3", "pexels-4"]
    assert merged[0].provenance["query"] == "older woman phone"
    assert merged[3].provenance["query"] == "grandmother phone"


def test_keep_writes_the_bytes_as_delivered_with_a_valid_sidecar(tmp_path):
    fake = FakePexels()
    run_search(tmp_path, fake, "older woman phone", 2)
    to = tmp_path / "library" / "scenes"
    with sourcing.client(transport=httpx.MockTransport(fake)) as http:
        written, errors = sourcing.keep(tmp_path / "cands" / "candidates.yaml", [("pexels-2", "ke-woman-market")],
                                        to, "A. Author", http, today=TODAY)
    assert errors == [] and written == [to / "ke-woman-market.jpg"]
    assert written[0].read_bytes() == jpeg((80, 90, 90))
    record = yaml.safe_load(art.sidecar(written[0]).read_text())
    assert problems(record, art.file_digest(written[0])) == []
    assert record["picked"] == {"by": "A. Author", "on": TODAY} and record["page_url"] == "https://www.pexels.com/photo/2/"


def test_keep_never_overwrites_art_and_reports_every_bad_pick(tmp_path):
    fake = FakePexels()
    run_search(tmp_path, fake, "older woman phone", 2)
    to = tmp_path / "scenes"
    to.mkdir()
    (to / "ke-woman.jpg").write_bytes(b"someone else's photo")
    with sourcing.client(transport=httpx.MockTransport(fake)) as http:
        written, errors = sourcing.keep(tmp_path / "cands" / "candidates.yaml",
                                        [("pexels-1", "ke-woman"), ("pexels-7", None), ("pexels-2", None)],
                                        to, "A. Author", http, today=TODAY)
    assert [p.name for p in written] == ["pexels-2.jpg"]
    assert errors == ["pexels-1: ke-woman is already taken in the art directory", "pexels-7: not among these candidates"]
    assert (to / "ke-woman.jpg").read_bytes() == b"someone else's photo"


def test_generate_keeps_each_image_as_delivered_and_reports_refusals_without_stopping(tmp_path, monkeypatch):
    monkeypatch.setattr(sourcing, "google_token", lambda: "tok")
    images = {1: jpeg((200, 30, 30), (1024, 1280)), 3: jpeg((30, 200, 30), (1024, 1280))}

    def fake_gemini(request):
        assert request.headers["Authorization"] == "Bearer tok"
        seed = json.loads(request.content)["generationConfig"]["seed"]
        if seed not in images:
            return httpx.Response(200, json={"candidates": [{"finishReason": "IMAGE_SAFETY"}]})
        data = __import__("base64").b64encode(images[seed]).decode()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": data}}]}}]})

    out = tmp_path / "cands"
    with sourcing.client(transport=httpx.MockTransport(fake_gemini)) as http:
        found, refused, errors = sourcing.generate(http, gemini, "An older woman reading her phone", 3, 1, 1080, 1350,
                                                   out, env={"GOOGLE_CLOUD_PROJECT": "p"}, today=TODAY)
        merged, _ = sourcing.add_candidates(out, found, http)
    assert refused == ["seed 2: no image (finish reason IMAGE_SAFETY)"] and errors == []
    assert [c.provenance["seed"] for c in merged] == [1, 3]
    assert (out / merged[0].full).read_bytes() == images[1]
    assert (merged[0].width, merged[0].height) == (1024, 1280)

    written, errors = sourcing.keep(out / "candidates.yaml", [(merged[1].id, "ke-woman-generated")],
                                    tmp_path / "scenes", "A. Author", http=None, today=TODAY)
    assert errors == [] and written[0].read_bytes() == images[3]
    record = yaml.safe_load(art.sidecar(written[0]).read_text())
    assert (record["source"], record["seed"], record["model"]) == ("generated", 3, "gemini-3.1-flash-image")


def test_generate_stops_at_an_http_error_rather_than_repeating_it(tmp_path, monkeypatch):
    monkeypatch.setattr(sourcing, "google_token", lambda: "tok")
    calls = []

    def forbidden(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"message": "Permission denied on project p"}})

    with sourcing.client(transport=httpx.MockTransport(forbidden)) as http:
        found, refused, errors = sourcing.generate(http, gemini, "x", 4, 1, 1080, 1080, tmp_path,
                                                   env={"GOOGLE_CLOUD_PROJECT": "p"})
    assert found == refused == [] and len(calls) == 1
    assert errors[0].startswith("seed 1: 403 from https://aiplatform.googleapis.com/") and "Permission denied" in errors[0]


def test_a_queued_generation_is_polled_until_done_then_downloaded_without_credentials(tmp_path):
    png = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 20, 20)).save(png, "PNG")
    polls, slept = [], []

    def fake_fal(request):
        if request.url.path == "/fal-ai/flux-2-pro":
            assert request.headers["Authorization"] == "Key k"
            return httpx.Response(200, json={"status_url": "https://queue.fal.run/s", "response_url": "https://queue.fal.run/r"})
        if request.url.path == "/s":
            polls.append(1)
            return httpx.Response(200, json={"status": "COMPLETED" if len(polls) == 3 else "IN_PROGRESS"})
        if request.url.path == "/r":
            return httpx.Response(200, json={"images": [{"url": "https://v3.fal.media/files/a.png"}], "seed": 1})
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=png.getvalue())

    with sourcing.client(transport=httpx.MockTransport(fake_fal)) as http:
        found, refused, errors = sourcing.generate(http, fal, "An older man in the Atlas", 1, 1, 1080, 1350, tmp_path,
                                                   env={"FAL_KEY": "k"}, sleep=slept.append)
    assert refused == errors == [] and len(polls) == 3 and slept == [2, 2]
    assert found[0].provenance["model"] == "fal-ai/flux-2-pro"
    assert (tmp_path / found[0].full).read_bytes() == png.getvalue()


def test_firefly_trades_its_client_credentials_for_a_token_once_per_run(tmp_path):
    tokens, generations = [], []

    def fake_firefly(request):
        if request.url.host == "ims-na1.adobelogin.com":
            tokens.append(request.content)
            return httpx.Response(200, json={"access_token": "t", "expires_in": 86399})
        if request.url.path == "/v4/images/generate-async":
            assert (request.headers["Authorization"], request.headers["x-api-key"]) == ("Bearer t", "cid")
            generations.append(json.loads(request.content)["seeds"])
            return httpx.Response(202, json={"links": {"result": {"href": "https://firefly-api.adobe.io/v3/status/j"}}})
        if request.url.path == "/v3/status/j":
            return httpx.Response(200, json={"status": "succeeded", "result": {"outputs": [
                {"image": {"url": f"https://s3.example/{len(generations)}.jpg"}}]}})
        assert "Authorization" not in request.headers and "x-api-key" not in request.headers
        return httpx.Response(200, content=jpeg((10 * len(generations), 0, 0), (1024, 1024)))

    env = {"FIREFLY_SERVICES_CLIENT_ID": "cid", "FIREFLY_SERVICES_CLIENT_SECRET": "secret"}
    with sourcing.client(transport=httpx.MockTransport(fake_firefly)) as http:
        found, refused, errors = sourcing.generate(http, firefly, "A family at home", 2, 5, 1080, 1080, tmp_path,
                                                   env=env, sleep=lambda s: None)
    assert refused == errors == [] and len(tokens) == 1 and generations == [[5], [6]]
    assert [c.provenance["seed"] for c in found] == [5, 6]


def test_an_error_page_instead_of_an_image_is_not_kept(tmp_path):
    fake = FakePexels()
    run_search(tmp_path, fake, "older woman phone", 1)

    def html_instead(request):
        return httpx.Response(200, content=b"<html>rate limited</html>")

    with sourcing.client(transport=httpx.MockTransport(html_instead)) as http:
        written, errors = sourcing.keep(tmp_path / "cands" / "candidates.yaml", [("pexels-1", None)],
                                        tmp_path / "scenes", "A. Author", http, today=TODAY)
    assert written == [] and errors == ["pexels-1: ValueError: not a JPEG, PNG or WebP image"]
    assert not (tmp_path / "scenes").exists()
