"""`ballyhoo source`: briefs through the fake provider and a mock transport. No network, no browser."""
import datetime

import pytest
import yaml
from PIL import Image

from ballyhoo import candidates, cli

TODAY = datetime.date.today().isoformat()
PREVIEW = "defaults:\n  preview: {templates: [photo-band/1080x1080], copy: Take a short survey.}\n"


@pytest.fixture
def study(tmp_path):
    """A study folder with one template; returns a function writing its brief."""
    template = tmp_path / "designs" / "photo-band" / "1080x1080.html"
    template.parent.mkdir(parents=True)
    template.write_text("<div id=canvas></div>")

    def write(text):
        path = tmp_path / "brief.yaml"
        path.write_text(text)
        return path
    return write


def test_a_brief_with_every_kind_of_mistake_reports_them_all_and_sends_nothing(sent, study, capsys):
    path = study("""
defaults:
  need: Everyone
  preview: {templates: [photo-band/1080x1080, photo-band/1200x628], copy: Hola.}
Ke-Woman:
  need: A woman.
  search: {fake: bright village}
ke-man:
  search: {pexels: bright town}
  mood: warm
ke-family:
  need: A family.
""")
    assert cli.main(["source", str(path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  defaults: unknown key 'need' (the name is reserved, so no need can use it)",
        f"FAIL  defaults/preview: template photo-band/1200x628 does not exist: expected "
        f"{path.parent / 'designs' / 'photo-band' / '1200x628'}.html",
        "FAIL  Ke-Woman: need names are lowercase slugs",
        "FAIL  ke-man: unknown key 'mood'",
        "FAIL  ke-man: need is required: say what the image must show",
        "FAIL  ke-man/search/pexels: unknown provider (known: fake)",
        "FAIL  ke-family: needs search or generate, or both",
    ]
    assert sent == [] and not (path.parent / "runs").exists()


def test_plan_prints_each_request_and_the_estimate_and_sends_and_writes_nothing(sent, study, capsys):
    path = study(PREVIEW + "ke-woman:\n  need: A woman.\n  search: {fake: [bright village, bright old village]}\n"
                 "  generate: {fake: A woman in bright light.}\n")
    assert cli.main(["source", str(path), "--plan", "--seed", "40"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "plan  ke-woman/fake search, 2 results, $0.00",
        "        query: bright village",
        "plan  ke-woman/fake search, 2 results, $0.00",
        "        query: bright old village",
        "plan  ke-woman/fake generate, 2 images, $0.50",
        "        model: fake-image-1",
        "        size: 1080x1080",
        "        seeds: [40, 41]",
        "        prompt: A woman in bright light.",
        "3 requests, estimated $0.50 (--max-cost $2.00)",
    ]
    assert sent == [] and not (path.parent / "runs").exists()


def test_a_run_over_the_limit_or_with_no_published_price_stops_before_any_request(sent, study, capsys):
    path = study(PREVIEW + "ke-woman:\n  need: A woman.\n  n: 10\n  generate: {fake: A woman in bright light.}\n"
                 "ma-man:\n  need: A man.\n  generate: {fake: {prompt: A bright man., model: fake-image-unpriced}}\n")
    assert cli.main(["source", str(path)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  the estimated cost, $2.50, is over --max-cost $2.00",
        "FAIL  ma-man/fake: fake-image-unpriced has no published price, so the estimate cannot include it; "
        "pass --allow-unpriced to run it anyway",
    ]
    assert cli.main(["source", str(path), "--max-cost", "3", "--allow-unpriced", "--plan"]) == 0
    assert sent == [] and not (path.parent / "runs").exists()


def test_a_run_records_refusals_and_http_errors_and_the_other_needs_still_run(sent, study, capsys):
    path = study(PREVIEW + """
  n: 2
ke-woman:
  need: A Kenyan woman.
  search:
    fake: [bright village, bright old village]
  generate:
    fake: {prompt: A woman in a dark room., seed: 12}
down:
  need: Anything.
  search: {fake: error}
ma-man:
  need: A Moroccan man.
  generate: {fake: A small picture of a man.}
""")
    assert cli.main(["source", str(path), "--seed", "100"]) == 1
    out = capsys.readouterr().out.splitlines()
    run = path.parent / "runs" / f"{TODAY}-1"
    assert out == [
        f"done  ke-woman/fake search: 2 results, 2 new in {out[0].split(' in ')[1]}",
        f"done  ke-woman/fake search: 2 results, 1 new in {out[1].split(' in ')[1]}",
        f"done  ke-woman/fake generate: 1 images, 1 refused in {out[2].split(' in ')[1]}",
        f"done  down/fake search: nothing in {out[3].split(' in ')[1]}",
        f"done  ma-man/fake generate: 2 images, 0 refused in {out[4].split(' in ')[1]}",
        "FAIL  ke-woman/fake generate: seed 13: seed 13 is always refused",
        "FAIL  down/fake search 'error': HTTPStatusError: 503 from https://fake.test/search: the fake provider is down",
        f"run {run}: 5 requests, 2 errors",
    ]
    assert sorted(p.name for p in path.parent.joinpath("runs").iterdir()) == [f"{TODAY}-1"]
    assert (run / "brief.yaml").read_text() == path.read_text()

    manifest = yaml.safe_load((run / "manifest.yaml").read_text())
    assert manifest["brief"] == "../../brief.yaml"
    assert manifest["estimated_cost_usd"] == 1.0 and len(manifest["ballyhoo"]) == 64
    assert manifest["started"] <= manifest["finished"]
    keys = ("need", "kind", "query", "results", "new", "already_found", "images", "refused", "seeds")
    assert [{k: r[k] for k in keys if k in r} for r in manifest["requests"]] == [
        {"need": "ke-woman", "kind": "search", "query": "bright village", "results": 2, "new": 2, "already_found": 0},
        {"need": "ke-woman", "kind": "search", "query": "bright old village", "results": 2, "new": 1,
         "already_found": 1},
        {"need": "ke-woman", "kind": "generate", "images": 1, "refused": 1, "seeds": [12, 13]},
        {"need": "down", "kind": "search", "query": "error"},
        {"need": "ma-man", "kind": "generate", "images": 2, "refused": 0, "seeds": [100, 101]},
    ]
    assert manifest["errors"] == [line[len("FAIL  "):] for line in out[5:7]]

    need = run / "ke-woman"
    data = yaml.safe_load((need / "candidates.yaml").read_text())
    assert [(e["id"], e.get("query"), e.get("queries")) for e in data["candidates"]] == [
        ("fake-bright-2", "bright village", ["bright village"]),
        ("fake-bright-3", "bright village", ["bright village", "bright old village"]),
        ("fake-bright-4", "bright old village", ["bright old village"]), (data["candidates"][3]["id"], None, None)]
    found, errors = candidates.load(data)
    assert errors == []
    assert (found[0].full, found[0].width, found[0].height) == ("originals/fake-bright-2.jpg", 1600, 1200)
    assert found[0].provenance["download_url"] == "https://fake.test/images/bright/bright-2.jpg"
    assert sorted(p.name for p in (need / "originals").iterdir()) == [
        "fake-bright-2.jpg", "fake-bright-3.jpg", "fake-bright-4.jpg"]
    assert len(list((need / "generated").iterdir())) == 1 and len(list((need / "thumbs").iterdir())) == 4
    assert (need / "sheet-01.png").is_file()
    downloads = [r.url.path for r in sent if r.url.path.startswith("/images/")]
    assert len(downloads) == 3, "a photo an earlier query found is not downloaded again"

    small, _ = candidates.load(yaml.safe_load((run / "ma-man" / "candidates.yaml").read_text()))
    assert [(c.width, c.height) for c in small] == [(400, 400), (400, 400)]
    with Image.open(run / "ma-man" / small[0].full) as im:
        assert im.size == (400, 400)


def test_a_second_run_gets_a_new_folder_and_leaves_the_first_alone(sent, study, capsys):
    path = study(PREVIEW + "ke-woman:\n  need: A woman.\n  search: {fake: bright village}\n")
    out = path.parent / "elsewhere"
    assert cli.main(["source", str(path), "--out", str(out)]) == 0
    first = (out / f"{TODAY}-1" / "manifest.yaml").read_text()
    assert cli.main(["source", str(path), "--out", str(out), "--providers", "fake"]) == 0
    assert sorted(p.name for p in out.iterdir()) == [f"{TODAY}-1", f"{TODAY}-2"]
    assert (out / f"{TODAY}-1" / "manifest.yaml").read_text() == first
    assert not (path.parent / "runs").exists()
