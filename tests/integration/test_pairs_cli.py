"""`ballyhoo review --pairs` and `keep --from comparisons` on a run sourced from the fake provider.

The review server runs for real on an ephemeral port in a thread, driven with httpx. The need that
is "previewed" has a checks.yaml written by hand, over preview PNGs drawn here, so the page has an
ad to show for one candidate and only the photo for another.
"""
import datetime
import threading
from pathlib import Path

import httpx
import pytest
import yaml
from PIL import Image
from playwright.sync_api import expect, sync_playwright

import fake_provider
from ballyhoo import art, cli, comparisons, provenance, render, review_server

SMOKE_DESIGNS = Path(__file__).parents[2] / "smoke" / "designs"
TODAY = datetime.date.today()
BAND = "photo-band/1080x1080"
BRIEF = f"""designs: {SMOKE_DESIGNS}
defaults:
  preview: {{templates: [{BAND}], copy: Take a short survey.}}
ke-woman:
  need: A Kenyan woman in her fifties, using a phone.
  search:
    fake: [bright village, bright old village]
ma-man:
  need: A Moroccan man in his fifties.
  generate: {{fake: A man in bright light.}}
down:
  need: Anything.
  search: {{fake: error}}
"""
PREVIEWS = {"fake-bright-2": "pass", "fake-bright-3": "fail"}
CHECKS = {"copy": "Take a short survey.", "templates": [BAND], "candidates": {
    id_: {"pass": status == "pass", "previews": {BAND: {
        "status": status, "file": f"previews/{id_}_photo-band_1080x1080.png", "summary": "84px"}}}
    for id_, status in PREVIEWS.items()}}
NAMED = ["fake-bright-2", "fake-bright-3", "fake-bright-4"]  # ke-woman's candidates, in candidates.yaml order


@pytest.fixture
def run(sent, tmp_path, capsys):
    """A run whose ke-woman need has three candidates, two of them previewed into an ad."""
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(BRIEF)
    cli.main(["source", str(brief), "--seed", "1"])
    capsys.readouterr()
    run = brief.parent / "runs" / f"{TODAY.isoformat()}-1"
    (run / "ke-woman" / "checks.yaml").write_text(yaml.safe_dump(CHECKS))
    previews = run / "ke-woman" / "previews"
    previews.mkdir()
    for id_ in PREVIEWS:
        Image.new("RGB", (1080, 1080), (222, 205, 180)).save(previews / f"{id_}_photo-band_1080x1080.png")
    return run


@pytest.fixture
def served(run):
    server = review_server.make_server(run, {"fake": fake_provider})
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with httpx.Client(base_url=review_server.url(server)) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def embedded(html):
    start = html.index('<script id="data" type="application/json">') + len('<script id="data" type="application/json">')
    return yaml.safe_load(html[start:html.index("</script>", start)])


def files(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def started(run):
    """The day the run started, and so the day its originals were downloaded. It is UTC, and today may not be."""
    return datetime.date.fromisoformat(str(yaml.safe_load((run / "manifest.yaml").read_text())["started"])[:10])


def candidate_ids(run, need):
    return [c["id"] for c in yaml.safe_load((run / need / "candidates.yaml").read_text())["candidates"]]


def compare(client, a, b, winner, need="ke-woman", rated_by="A. Author"):
    return client.post("/comparisons", json={"rated_by": rated_by, "rated_on": TODAY.isoformat(),
                                             "need": need, "a": a, "b": b, "winner": winner})


def test_the_pairwise_page_shows_a_pair_of_one_need_as_the_ads_they_make(run, served):
    page = served.get("/pairs")
    assert (page.status_code, page.headers["content-type"]) == (200, "text/html; charset=utf-8")
    data = embedded(page.text)
    assert [n["name"] for n in data["needs"]] == ["ke-woman", "ma-man"], "a need with no candidates has nothing to compare"
    woman = data["needs"][0]
    assert woman["need"] == "A Kenyan woman in her fifties, using a phone."
    assert [(c["id"], c["image"], c["previewed"]) for c in woman["candidates"]] == [
        ("fake-bright-2", "ke-woman/previews/fake-bright-2_photo-band_1080x1080.png", True),
        ("fake-bright-3", "ke-woman/previews/fake-bright-3_photo-band_1080x1080.png", True),
        ("fake-bright-4", "ke-woman/thumbs/fake-bright-4.jpg", False)]
    assert woman["state"]["pair"] == ["fake-bright-2", "fake-bright-3"]
    assert (woman["state"]["done"], woman["state"]["budget"], woman["state"]["seen"]) == (0, 3, 0)
    assert [r["score"] for r in woman["state"]["ranking"]] == [None, None, None]
    assert data["rated_by"] is None
    assert served.get(f"/{woman['candidates'][0]['image']}").status_code == 200


def test_each_comparison_is_saved_as_it_is_made_and_the_reply_carries_the_next_pair(run, served):
    reply = compare(served, "fake-bright-2", "fake-bright-3", "a")
    assert reply.status_code == 200, reply.text
    assert reply.json()["saved"] == "comparisons.yaml"
    assert yaml.safe_load((run / "comparisons.yaml").read_text()) == {
        "rated_by": "A. Author", "rated_on": TODAY,
        "comparisons": [{"need": "ke-woman", "a": "fake-bright-2", "b": "fake-bright-3", "winner": "a"}]}
    state = reply.json()["state"]
    assert (state["done"], state["seen"], state["pair"]) == (1, 2, ["fake-bright-3", "fake-bright-4"])
    assert [(r["id"], r["score"]) for r in state["ranking"]] == [
        ("fake-bright-2", 1.0), ("fake-bright-3", 0.0), ("fake-bright-4", None)]

    assert compare(served, *state["pair"], "tie").status_code == 200
    last = compare(served, "fake-bright-2", "fake-bright-4", "a").json()["state"]
    assert (last["done"], last["budget"], last["pair"]) == (3, 3, None), "the budget is reached"
    assert [r["id"] for r in last["ranking"]] == NAMED
    assert embedded(served.get("/pairs").text)["rated_by"] == "A. Author"
    assert [p.name for p in run.iterdir() if p.name.endswith(".tmp")] == []


def test_an_invalid_comparison_is_refused_with_every_problem_and_writes_nothing(run, served):
    before = files(run)
    reply = served.post("/comparisons", json={"rated_by": " ", "rated_on": TODAY.isoformat(),
                                              "need": "ke-woman", "a": "fake-bright-9", "b": "fake-bright-9",
                                              "winner": "left"})
    assert reply.status_code == 400
    assert reply.json()["errors"] == [
        "rated_by is required: the name of whoever compared",
        "comparison 1: a 'fake-bright-9' is not a candidate of ke-woman in this run",
        "comparison 1: b 'fake-bright-9' is not a candidate of ke-woman in this run",
        "comparison 1: a and b are the same candidate, 'fake-bright-9'",
        "comparison 1: winner must be a, b or tie, not 'left'"]
    assert compare(served, "fake-bright-2", "fake-bright-2", "a").status_code == 400
    assert compare(served, "fake-bright-2", "gemini-abc", "a", need="ma-man").status_code == 400
    assert served.post("/comparisons", content=b"{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert served.post("/nowhere", json={}).status_code == 404
    assert files(run) == before


def test_undo_drops_the_last_comparison_of_that_need(run, served):
    compare(served, "fake-bright-2", "fake-bright-3", "a")
    reply = compare(served, "fake-bright-3", "fake-bright-4", "b")
    assert reply.json()["state"]["done"] == 2

    undone = served.post("/comparisons/undo", json={"need": "ke-woman"})
    assert undone.status_code == 200, undone.text
    assert undone.json()["state"]["done"] == 1
    assert [c["b"] for c in yaml.safe_load((run / "comparisons.yaml").read_text())["comparisons"]] == ["fake-bright-3"]

    assert served.post("/comparisons/undo", json={"need": "ma-man"}).status_code == 400
    assert served.post("/comparisons/undo", json={"need": "down"}).json()["errors"] == [
        "down: not a need with candidates in this run"]


def test_keep_from_comparisons_keeps_the_best_ranked_as_picked_by_whoever_compared(run, served, tmp_path, capsys):
    compare(served, "fake-bright-2", "fake-bright-3", "a")
    compare(served, "fake-bright-3", "fake-bright-4", "tie")
    compare(served, "fake-bright-2", "fake-bright-4", "a")

    scenes = tmp_path / "scenes"
    keep = ["keep", str(run), "--from", "comparisons", "--need", "ke-woman", "--to", str(scenes)]
    assert cli.main(keep + ["--top", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"ok    {scenes / 'fake-bright-2.jpg'}",
                                                    f"ok    {scenes / 'fake-bright-3.jpg'}"]
    for name in ("fake-bright-2", "fake-bright-3"):
        image = scenes / f"{name}.jpg"
        assert image.read_bytes() == (run / "ke-woman" / "originals" / f"{name}.jpg").read_bytes()
        record = yaml.safe_load(art.sidecar(image).read_text())
        assert provenance.problems(record, art.file_digest(image)) == []
        assert (record["picked"], record["fetched"]) == ({"by": "A. Author", "on": TODAY}, started(run))


def test_keep_from_comparisons_refuses_a_run_with_none_an_unknown_need_and_a_candidate_never_compared(
        run, served, tmp_path, capsys):
    scenes = tmp_path / "scenes"
    keep = ["keep", str(run), "--from", "comparisons", "--to", str(scenes), "--top", "1", "--need"]

    assert cli.main(keep + ["ke-woman"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  no comparisons.yaml in this run; compare them first: ballyhoo review RUN --pairs"]

    compare(served, "fake-bright-2", "fake-bright-3", "a")
    assert cli.main(keep + ["ke-woman"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  ke-woman: 1 of 3 candidates have never been compared (fake-bright-4); "
        "a ranking that leaves them out is not a ranking of the need"]

    assert cli.main(keep + ["down"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  down: not a need with candidates in this run (needs: ke-woman, ma-man)"]

    compare(served, "fake-bright-3", "fake-bright-4", "a")
    assert cli.main(["keep", str(run), "--from", "comparisons", "--need", "ke-woman", "--top", "4",
                     "--to", str(scenes)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  ke-woman: --top 4 is more than the 3 candidates this need has"]
    assert not scenes.exists()

    for argv in (["--top", "1"], ["--need", "ke-woman"],
                 ["--need", "ke-woman", "--top", "1", "--picked-by", "A. Author"],
                 ["--need", "ke-woman", "--top", "1", "fake-bright-2"]):
        with pytest.raises(SystemExit):
            cli.main(["keep", str(run), "--from", "comparisons", "--to", str(scenes), *argv])
    with pytest.raises(SystemExit):
        cli.main(["keep", str(run), "--verdicts", "--need", "ke-woman", "--top", "1", "--to", str(scenes)])
    capsys.readouterr()


def test_the_summary_prints_each_needs_ranking(run, served, capsys):
    assert cli.main(["review", str(run), "--summary", "--pairs"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "comparisons.yaml: none in this run, so nothing is ranked",
        "ke-woman: 0 of 3 compared, 0 of 3 candidates seen",
        *[f"   -. {id_}  never compared" for id_ in NAMED],
        "ma-man: 0 of 1 compared, 0 of 2 candidates seen",
        *[f"   -. {id_}  never compared" for id_ in sorted(candidate_ids(run, "ma-man"))],
        "skip  down: no candidates in this run",
    ]

    compare(served, "fake-bright-2", "fake-bright-3", "a")
    assert cli.main(["review", str(run), "--summary", "--pairs"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"comparisons.yaml: compared by A. Author on {TODAY}"
    assert out[1:4] == ["ke-woman: 1 of 3 compared, 2 of 3 candidates seen",
                        "   1. fake-bright-2  score 1.00, 1 comparisons (1W 0L 0T)",
                        "   2. fake-bright-3  score 0.00, 1 comparisons (0W 1L 0T)"]
    with pytest.raises(SystemExit):
        cli.main(["review", str(run), "--summary", "--pairs", "--agent"])
    capsys.readouterr()


@pytest.mark.browser
def test_a_person_compares_on_the_page_at_phone_width_and_the_comparison_is_written(run, served, tmp_path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=render.chrome_path())
        try:
            page = browser.new_page(viewport={"width": 400, "height": 800})
            page.goto(f"{served.base_url}pairs")
            expect(page.locator("#progress")).to_have_text("0 of 3 compared · 0 of 3 candidates seen")
            cards = page.locator(".card")
            expect(cards).to_have_count(2)
            assert cards.first.bounding_box()["width"] > 300, "a card fills the width of a phone"

            cards.first.click()
            expect(page.locator("#errors")).to_contain_text("Enter your name")
            assert not (run / comparisons.FILE).exists()

            page.get_by_label("Your name").fill("A. Author")
            cards.first.click()
            expect(page.locator("#progress")).to_have_text("1 of 3 compared · 2 of 3 candidates seen")
            page.screenshot(path=tmp_path / "pairs-phone.png")

            page.get_by_role("button", name="Ranking").click()
            expect(page.locator("#ranking")).to_contain_text("fake-bright-2")
            page.keyboard.press("u")
            expect(page.locator("#progress")).to_have_text("0 of 3 compared · 0 of 3 candidates seen")
            page.keyboard.press("ArrowRight")
            expect(page.locator("#progress")).to_have_text("1 of 3 compared · 2 of 3 candidates seen")
        finally:
            browser.close()
    assert yaml.safe_load((run / comparisons.FILE).read_text()) == {
        "rated_by": "A. Author", "rated_on": TODAY,
        "comparisons": [{"need": "ke-woman", "a": "fake-bright-2", "b": "fake-bright-3", "winner": "b"}]}
