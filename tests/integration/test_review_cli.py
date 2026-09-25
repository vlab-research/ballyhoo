"""`ballyhoo review` and `keep --verdicts` on a run sourced from the fake provider.

The review server runs for real on an ephemeral port in a thread, driven with httpx. No browser: the
need that is "previewed" has a checks.yaml written by hand.
"""
import contextlib
import datetime
import http.client
import re
import shutil
import threading
from pathlib import Path

import httpx
import pytest
import yaml
from playwright.sync_api import expect, sync_playwright

import fake_provider
from ballyhoo import art, cli, provenance, render, review_server, verdicts

SMOKE_DESIGNS = Path(__file__).parents[2] / "smoke" / "designs"
TODAY = datetime.datetime.now(datetime.timezone.utc).date()  # a run is named for its UTC day
RATED_ON = datetime.date.today()  # the server dates a mark with the rater's own day, which is not the run's
BAND = "photo-band/1080x1080"
AGENT = "claude-code (claude-opus-5)"
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
CHECKS = {"copy": "Take a short survey.", "templates": [BAND], "summary": {"candidates": 3, "pass": 1, "fail": 1},
          "candidates": {
              "fake-bright-2": {"pass": True, "previews": {BAND: {
                  "status": "pass", "file": "previews/fake-bright-2_photo-band_1080x1080.png", "summary": "84px"}}},
              "fake-bright-3": {"pass": False, "previews": {BAND: {
                  "status": "fail", "file": "previews/fake-bright-3_photo-band_1080x1080.png", "summary": "84px",
                  "failures": ["contrast 1.17:1 is below 3:1"]}}}}}


@pytest.fixture
def run(sent, tmp_path, capsys):
    """A run whose ke-woman need was previewed: bright-2 from one query, bright-3 from both, bright-4 from the second."""
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(BRIEF)
    cli.main(["source", str(brief), "--seed", "1"])
    capsys.readouterr()
    run = brief.parent / "runs" / f"{TODAY.isoformat()}-1"
    (run / "ke-woman" / "checks.yaml").write_text(yaml.safe_dump(CHECKS))
    return run


@contextlib.contextmanager
def serving(folder):
    server = review_server.make_server(folder, {"fake": fake_provider})
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with httpx.Client(base_url=review_server.url(server)) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def served(run):
    with serving(run) as client:
        yield client


def marking(client, run, candidate, entry, need="ke-woman", rated_by="A. Author"):
    return client.post("/verdicts", json={"run": run, "rated_by": rated_by, "need": need, "candidate": candidate,
                                          "entry": entry})


def embedded(html):
    start = html.index('<script id="data" type="application/json">') + len('<script id="data" type="application/json">')
    return yaml.safe_load(html[start:html.index("</script>", start)])


def files(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def raw_get(client, path):
    """GET a path exactly as written: httpx would resolve dot segments before sending."""
    connection = http.client.HTTPConnection(client.base_url.host, client.base_url.port)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_the_page_shows_the_run_as_it_is_and_serves_its_files_but_nothing_outside_it(run, served):
    (run.parents[1] / "secret.txt").write_text("not the run's")

    page = served.get("/")
    assert (page.status_code, page.headers["content-type"]) == (200, "text/html; charset=utf-8")
    data = embedded(page.text)
    assert data["editable"] is True
    [shown] = data["runs"]
    assert (shown["name"], shown["status"], shown["open"]) == (run.name, "previewing", True)
    assert [(n["name"], n["previewed"], len(n["candidates"])) for n in shown["needs"]] == [
        ("ke-woman", True, 3), ("ma-man", False, 2), ("down", False, 0)]
    two, three, four = shown["needs"][0]["candidates"]
    assert (three["id"], three["queries"], three["pass"], three["previews"][0]["failures"]) == (
        "fake-bright-3", ["bright village", "bright old village"], False, ["contrast 1.17:1 is below 3:1"])
    assert (four["previewed"], four["pass"]) == (False, None)
    assert [c["name"] for n in shown["needs"] for c in n["candidates"]] == ["1.1", "1.2", "1.3", "1.4", "1.5"]

    thumb = served.get(f"/{two['thumb']}")
    assert (thumb.status_code, thumb.headers["content-type"]) == (200, "image/jpeg")
    assert thumb.content == (run / two["thumb"]).read_bytes()
    assert raw_get(served, "/ke-woman/../manifest.yaml") == 200, "dot segments reach the server and resolve"

    assert raw_get(served, "/../../secret.txt") == 404
    for path in ("/%2e%2e/%2e%2e/secret.txt", "/ke-woman/..%2f..%2f..%2fsecret.txt", "/%2Fetc%2Fpasswd",
                 "/ke-woman/%00", "/nothing.png"):
        assert served.get(path).status_code == 404, path
    assert served.get("/", headers={"Host": "rebound.example"}).status_code == 403


def test_a_server_on_a_briefs_runs_shows_each_run_as_it_is_made_newest_first(sent, tmp_path, capsys):
    study = tmp_path / "study"
    runs = study / "runs"
    runs.mkdir(parents=True)
    brief = study / "brief.yaml"
    brief.write_text(BRIEF)
    with serving(runs) as served:
        empty = served.get("/state").json()
        assert empty["runs"] == [] and embedded(served.get("/").text)["runs"] == []

        cli.main(["source", str(brief), "--seed", "1"])
        capsys.readouterr()
        first = f"{TODAY.isoformat()}-1"
        state = served.get("/state").json()
        assert [(r["name"], r["status"]) for r in state["runs"]] == [(first, "previewing")]
        assert state["digest"] != empty["digest"]
        page = embedded(served.get("/").text)
        assert page["state"] == state["digest"]
        [shown] = page["runs"]
        assert (shown["name"], shown["open"], shown["changes"]) == (first, True, None)
        thumb = shown["needs"][0]["candidates"][0]["thumb"]
        assert thumb.startswith(f"{first}/ke-woman/thumbs/")
        assert served.get(f"/{thumb}").content == (runs / thumb).read_bytes()
        assert raw_get(served, "/../brief.yaml") == 404
        assert served.get("/%2e%2e/brief.yaml").status_code == 404

        for need in ("ke-woman", "ma-man"):
            (runs / first / need / "checks.yaml").write_text(yaml.safe_dump({"candidates": {}}))
        ready = served.get("/state").json()
        assert [r["status"] for r in ready["runs"]] == ["ready"]
        reply = marking(served, first, "fake-bright-2", {"verdict": "keep"})
        assert reply.status_code == 200, reply.text
        assert served.get("/state").json() == ready, "a save is not a new round"

        brief.write_text(BRIEF.replace("bright old village", "bright old town"))
        cli.main(["source", str(brief), "--seed", "1"])
        capsys.readouterr()
        second = f"{TODAY.isoformat()}-2"
        assert [r["name"] for r in served.get("/state").json()["runs"]] == [second, first]
        newer, older = embedded(served.get("/").text)["runs"]
        assert (newer["name"], newer["open"], older["name"], older["open"]) == (second, True, first, False)
        assert newer["changes"] == [{"need": "ke-woman", "change": "changed", "asks": [
            {"kind": "search", "provider": "fake", "diff": [["=", "bright old"], ["-", "village"], ["+", "town"]]}]}]
        assert older["rated_by"] == "A. Author" and newer["rated_by"] is None
        assert marking(served, second, "fake-bright-2", {"verdict": "drop"}, rated_by="B. Other").status_code == 200
        assert yaml.safe_load((runs / second / "verdicts.yaml").read_text())["rated_by"] == "B. Other"


def test_an_invalid_mark_is_refused_with_every_problem_and_writes_nothing(run, served):
    before = files(run)
    reply = marking(served, run.name, "fake-bright-9", {"verdict": "keep", "issues": ["blurry"]}, rated_by=" ")
    assert reply.status_code == 400
    assert reply.json()["errors"] == ["rated_by is required: the name of whoever rated"]
    reply = marking(served, run.name, "fake-bright-9", {"verdict": "keep", "issues": ["blurry"]})
    assert reply.json()["errors"] == [
        "ke-woman/fake-bright-9: not a candidate of ke-woman in this run",
        f"ke-woman/fake-bright-9: unknown issue 'blurry' (known: {', '.join(verdicts.ISSUES)})"]
    assert marking(served, run.name, "fake-bright-2", {"issues": ["crop"]}).json()["errors"] == [
        "choose keep, maybe or drop: issues and a note are saved with a verdict"]
    assert served.post("/verdicts", content=b'{"run": "x"}', headers={"Content-Type": "text/plain"}).status_code == 415
    assert served.post("/verdicts", content=b"{not json", headers={"Content-Type": "application/json"}).status_code == 400
    assert served.post("/verdicts", json=["a list"]).status_code == 400
    for elsewhere in ("..", "2026-01-01-1", None):
        assert marking(served, elsewhere, "fake-bright-2", {"verdict": "keep"}).status_code == 404, elsewhere
    assert served.post(f"/verdicts?run={run.name}", json={"run": "..", "rated_by": "A"}).status_code == 404
    assert served.post("/elsewhere", json={}).status_code == 404
    assert files(run) == before


def test_a_mark_from_a_second_person_is_refused_until_the_first_clears_every_mark(run, served):
    assert marking(served, run.name, "fake-bright-2", {"verdict": "keep"}).status_code == 200
    saved = (run / "verdicts.yaml").read_text()
    reply = marking(served, run.name, "fake-bright-3", {"verdict": "drop"}, rated_by="B. Other")
    assert (reply.status_code, reply.json()["errors"]) == (400, [
        "this run is rated by A. Author, and one person rates a run, so a mark from B. Other is not saved"])
    assert (run / "verdicts.yaml").read_text() == saved

    reply = marking(served, run.name, "fake-bright-2", None)
    assert reply.status_code == 200 and (reply.json()["rated_by"], reply.json()["rated_on"]) == (None, None)
    assert not (run / "verdicts.yaml").exists()
    assert marking(served, run.name, "fake-bright-3", {"verdict": "drop"}, rated_by="B. Other").status_code == 200


def test_each_mark_merges_into_verdicts_and_keep_takes_the_keeps_as_picked_by_the_rater(run, served, tmp_path, capsys):
    marks = {"fake-bright-2": {"verdict": "keep"},
             "fake-bright-3": {"verdict": "keep", "issues": ["crop"], "note": "Just room for the headline."},
             "fake-bright-4": {"verdict": "drop", "issues": ["age"]}}
    for candidate, entry in marks.items():
        reply = marking(served, run.name, candidate, entry)
        assert reply.status_code == 200, reply.text
    assert marking(served, run.name, "fake-bright-4", {"verdict": "maybe"}).status_code == 200
    assert marking(served, run.name, "fake-bright-4", None).status_code == 200
    assert marking(served, run.name, "fake-bright-4", {"verdict": "drop", "issues": ["age"]}).status_code == 200
    reply = marking(served, run.name, "fake-bright-2", {"verdict": "keep"}).json()
    assert (reply["saved"], reply["rated_by"], reply["rated_on"]) == ("verdicts.yaml", "A. Author", RATED_ON.isoformat())
    summary = reply["summary"]
    assert {q: (c["candidates"], c["keep"], c["drop"]) for q, c in summary["ke-woman"]["providers"]["fake"]["queries"].items()} \
        == {"bright village": (2, 2, 0), "bright old village": (2, 1, 1)}
    assert summary["ma-man"]["unrated"] == 2

    assert yaml.safe_load((run / "verdicts.yaml").read_text()) == {
        "rated_by": "A. Author", "rated_on": RATED_ON, "needs": {"ke-woman": marks}}
    assert [p.name for p in run.iterdir() if p.name.endswith(".tmp")] == []
    static = embedded((run / "review.html").read_text())
    assert static["editable"] is False and static["runs"][0]["needs"][0]["candidates"][1]["verdict"]["issues"] == ["crop"]
    assert embedded(served.get("/").text)["runs"][0]["rated_by"] == "A. Author"

    scenes = tmp_path / "scenes"
    keep = ["keep", str(run), "--verdicts", "--need", "ke-woman", "--to", str(scenes)]
    assert cli.main(keep) == 0
    assert capsys.readouterr().out.splitlines() == [f"ok    {scenes / 'fake-bright-2.jpg'}",
                                                    f"ok    {scenes / 'fake-bright-3.jpg'}"]
    for name in ("fake-bright-2", "fake-bright-3"):
        image = scenes / f"{name}.jpg"
        assert image.read_bytes() == (run / "ke-woman" / "originals" / f"{name}.jpg").read_bytes()
        record = yaml.safe_load(art.sidecar(image).read_text())
        assert provenance.problems(record, art.file_digest(image)) == []
        assert (record["picked"], record["fetched"], record["query"]) == (
            {"by": "A. Author", "on": TODAY}, TODAY, "bright village")

    assert cli.main(keep) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  fake-bright-2: fake-bright-2 is already taken in the art directory",
        "FAIL  fake-bright-3: fake-bright-3 is already taken in the art directory"]


def test_keep_refuses_a_run_without_verdicts_agent_verdicts_an_unknown_need_and_a_need_with_no_keeps(
        run, tmp_path, capsys):
    scenes = tmp_path / "scenes"
    keep = ["keep", str(run), "--verdicts", "--to", str(scenes), "--need"]

    assert cli.main(keep + ["ke-woman"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  no verdicts.yaml in this run; rate the run first: ballyhoo review RUN"]

    (run / "agent-verdicts.yaml").write_text(yaml.safe_dump({"rated_by": AGENT, "rated_on": TODAY, "needs": {
        "ke-woman": {"fake-bright-2": {"verdict": "keep"}}}}))
    assert cli.main(keep + ["ke-woman"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  no verdicts.yaml in this run; agent-verdicts.yaml is not picks: a pick names the person who made it, "
        "so a person rates in verdicts.yaml"]

    (run / "verdicts.yaml").write_text(yaml.safe_dump({"rated_by": "A. Author", "rated_on": TODAY, "needs": {
        "ke-woman": {"fake-bright-2": {"verdict": "maybe"}}}}))
    assert cli.main(keep + ["ke-woman"]) == 1
    assert capsys.readouterr().out.splitlines() == ["FAIL  ke-woman: no candidate is rated keep in verdicts.yaml"]
    assert cli.main(keep + ["down"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  down: not a need with candidates in this run (needs: ke-woman, ma-man)"]
    assert not scenes.exists()

    with pytest.raises(SystemExit):
        cli.main(["keep", str(run), "fake-bright-2", "--verdicts", "--need", "ke-woman", "--to", str(scenes)])
    with pytest.raises(SystemExit):
        cli.main(["keep", str(run), "--verdicts", "--need", "ke-woman", "--picked-by", AGENT, "--to", str(scenes)])
    capsys.readouterr()


def test_keep_still_takes_picks_named_on_the_command_line(run, tmp_path, capsys):
    scenes = tmp_path / "scenes"
    assert cli.main(["keep", str(run / "ke-woman" / "candidates.yaml"), "fake-bright-4=ke-woman-village",
                     "--to", str(scenes), "--picked-by", "B. Person"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"ok    {scenes / 'ke-woman-village.jpg'}"]
    assert yaml.safe_load(art.sidecar(scenes / "ke-woman-village.jpg").read_text())["picked"]["by"] == "B. Person"


def test_keep_takes_candidates_by_name_from_a_run_its_runs_directory_or_its_brief(run, tmp_path, capsys):
    """The run's candidates are named 1.1 to 1.3 (ke-woman: fake-bright-2 to -4) and 1.4, 1.5 (ma-man)."""
    scenes, brief = tmp_path / "scenes", run.parents[1] / "brief.yaml"
    keep = ["--to", str(scenes), "--picked-by", "B. Person"]

    assert cli.main(["keep", str(brief), "1.2", "1.4=ma-man-light"] + keep) == 0
    [bright, drawn] = capsys.readouterr().out.splitlines()
    assert bright == f"ok    {scenes / 'fake-bright-3.jpg'}  (1.2: {run.name}/ke-woman/fake-bright-3)"
    assert drawn.startswith(f"ok    {scenes / 'ma-man-light'}.") and f"  (1.4: {run.name}/ma-man/" in drawn
    assert (scenes / "fake-bright-3.jpg").read_bytes() == (run / "ke-woman" / "originals" / "fake-bright-3.jpg").read_bytes()
    record = yaml.safe_load(art.sidecar(scenes / "fake-bright-3.jpg").read_text())
    assert (record["picked"]["by"], record["fetched"], record["query"]) == ("B. Person", TODAY, "bright village")

    assert cli.main(["keep", str(run.parent), f"{run.name}.3"] + keep) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"ok    {scenes / 'fake-bright-4.jpg'}  ({run.name}.3: {run.name}/ke-woman/fake-bright-4)"]
    assert cli.main(["keep", str(run), "1"] + keep) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"ok    {scenes / 'fake-bright-2.jpg'}  (1: {run.name}/ke-woman/fake-bright-2)"]

    cli.main(["source", str(brief), "--seed", "1"])
    capsys.readouterr()
    shutil.copytree(run, run.parent / "2000-01-01-1")
    kept = files(scenes)
    assert cli.main(["keep", str(run.parent), "1.5", "2.9", "3.1", "4"] + keep) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"FAIL  1.5: runs {run.name}, 2000-01-01-1 are all numbered 1; name one, such as {run.name}.5",
        f"FAIL  2.9: {TODAY.isoformat()}-2 has candidates {TODAY.isoformat()}-2.1 to {TODAY.isoformat()}-2.5",
        f"FAIL  3.1: no run 3 among {TODAY.isoformat()}-2, {run.name}, 2000-01-01-1",
        "FAIL  4: name the run too, such as 3.4"]
    assert files(scenes) == kept, "one name that picks nothing keeps nothing"
    with pytest.raises(SystemExit):
        cli.main(["keep", str(tmp_path / "nothing"), "1.1"] + keep)
    capsys.readouterr()


def test_review_summary_prints_the_tallies_of_either_verdicts_file(run, capsys):
    assert cli.main(["review", str(run), "--summary"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "verdicts.yaml: none in this run, so every candidate is unrated",
        "skip  down: no candidates in this run",
        "ke-woman: 3 found, 0 keep (0%), 0 maybe, 0 drop, 3 unrated",
        "  fake: 3 found, 0 keep (0%), 0 maybe, 0 drop, 3 unrated",
        "    query 'bright village': 2 found, 0 keep (0%), 0 maybe, 0 drop, 2 unrated",
        "    query 'bright old village': 2 found, 0 keep (0%), 0 maybe, 0 drop, 2 unrated",
        "ma-man: 2 found, 0 keep (0%), 0 maybe, 0 drop, 2 unrated",
        "  fake: 2 found, 0 keep (0%), 0 maybe, 0 drop, 2 unrated",
        "    prompt 'A man in bright light.': 2 found, 0 keep (0%), 0 maybe, 0 drop, 2 unrated",
    ]

    (run / "agent-verdicts.yaml").write_text(yaml.safe_dump({"rated_by": AGENT, "rated_on": TODAY, "needs": {
        "ke-woman": {"fake-bright-3": {"verdict": "drop", "issues": ["age"]},
                     "fake-bright-4": {"verdict": "keep"}}}}))
    assert cli.main(["review", str(run), "--summary", "--agent"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"agent-verdicts.yaml: rated by {AGENT} on {TODAY}"
    assert out[4:6] == [
        "    query 'bright village': 2 found, 0 keep (0%), 0 maybe, 1 drop, 1 unrated; issues: age 1",
        "    query 'bright old village': 2 found, 1 keep (50%), 0 maybe, 1 drop, 0 unrated; issues: age 1"]

    (run / "verdicts.yaml").write_text(yaml.safe_dump({"rated_by": "A. Author", "rated_on": "soon", "needs": {}}))
    assert cli.main(["review", str(run), "--summary"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"FAIL  {run.resolve() / 'verdicts.yaml'}: rated_on must be a date, e.g. 2026-09-14, not 'soon'"]
    with pytest.raises(SystemExit):
        cli.main(["review", str(run), "--agent"])


def test_review_serves_the_runs_next_to_a_brief(tmp_path, monkeypatch, capsys):
    brief = tmp_path / "brief.yaml"
    brief.write_text(BRIEF)
    served = []
    monkeypatch.setattr(cli, "serve", lambda folder, *args: served.append(folder) or 0)
    assert cli.main(["review", str(brief)]) == 0
    assert served == [tmp_path / "runs"] and (tmp_path / "runs").is_dir()
    assert cli.main(["review", str(tmp_path / "runs")]) == 0
    with pytest.raises(SystemExit):
        cli.main(["review", str(tmp_path / "nothing")])
    capsys.readouterr()


def test_review_summary_of_a_brief_names_every_runs_candidates_with_their_verdicts_and_notes(sent, tmp_path, capsys):
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(BRIEF)
    assert cli.main(["review", str(brief), "--summary"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"0 runs in {brief.parent / 'runs'}, newest first, with each one's verdicts.yaml"]
    assert not (brief.parent / "runs").exists(), "a summary makes nothing"

    for _ in range(2):
        cli.main(["source", str(brief), "--seed", "1"])
    runs = brief.parent / "runs"
    first, second = (f"{TODAY.isoformat()}-{n}" for n in (1, 2))
    for need in ("ke-woman", "ma-man"):
        (runs / second / need / "checks.yaml").write_text(yaml.safe_dump(CHECKS))
    (runs / second / "verdicts.yaml").write_text(yaml.safe_dump({
        "rated_by": "A. Author", "rated_on": TODAY,
        "needs": {"ke-woman": {"fake-bright-3": {"verdict": "drop", "issues": ["age"]},
                               "fake-bright-4": {"verdict": "keep", "note": "Warm."}}},
        "notes": {"ma-man": "None of these look 50."}}))
    capsys.readouterr()
    assert cli.main(["review", str(brief), "--summary"]) == 0
    summary = capsys.readouterr().out.splitlines()
    assert summary == [
        f"2 runs in {runs}, newest first, with each one's verdicts.yaml",
        f"{second}: rated by A. Author on {TODAY}",
        "  ke-woman: 3 candidates: 1 keep, 1 drop, 1 unrated",
        "    2.3 keep; note: Warm.",
        "    2.2 drop; issues: age",
        "    unrated: 2.1",
        "  ma-man: 2 candidates: 2 unrated",
        "    note: None of these look 50.",
        "    unrated: 2.4, 2.5",
        "  down: no candidates",
        f"{first}: not rated; previewing, checks not written yet",
        "  ke-woman: 3 candidates: 3 unrated",
        "    unrated: 1.1 to 1.3",
        "  ma-man: 2 candidates: 2 unrated",
        "    unrated: 1.4, 1.5",
        "  down: no candidates",
    ]
    assert cli.main(["review", str(runs), "--summary"]) == 0
    assert capsys.readouterr().out.splitlines() == summary

    (runs / first / "agent-verdicts.yaml").write_text(yaml.safe_dump({"rated_by": AGENT, "rated_on": TODAY, "needs": {
        "ma-man": {"fake-6d6f64c7e81a": {"verdict": "maybe"}}}}))
    (runs / second / "verdicts.yaml").write_text("rated_by: [")
    assert cli.main(["review", str(runs), "--summary", "--agent"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == [f"2 runs in {runs}, newest first, with each one's agent-verdicts.yaml",
                         f"{second}: not rated", "  ke-woman: 3 candidates: 3 unrated"]
    assert lines[7:13] == [f"{first}: rated by {AGENT} on {TODAY}; previewing, checks not written yet",
                           "  ke-woman: 3 candidates: 3 unrated", "    unrated: 1.1 to 1.3",
                           "  ma-man: 2 candidates: 1 maybe, 1 unrated", "    1.4 maybe", "    unrated: 1.5"]
    assert cli.main(["review", str(runs), "--summary"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == f"{second}: cannot be read"
    assert lines[2].startswith(f"  error: {runs / second / 'verdicts.yaml'}: while parsing")
    assert f"{first}: not rated; previewing, checks not written yet" in lines, "one broken run hides no other"


@pytest.mark.browser
def test_each_mark_on_the_page_is_saved_as_it_is_made(run, served, tmp_path):
    tile = f'article[data-key="{run.name}/ke-woman/{{}}"]'.format

    def on_disk():
        return yaml.safe_load((run / "verdicts.yaml").read_text())["needs"]["ke-woman"]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=render.chrome_path())
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(str(served.base_url))
            three = page.locator(tile("fake-bright-3"))
            three.get_by_role("button", name="keep").click()
            expect(three.locator(".saved-state")).to_have_text("not saved: enter your name at the top to save")
            expect(three).to_have_class(re.compile(r"\bunsaved\b"))
            expect(page.get_by_label("Your name")).to_be_focused()
            assert not (run / "verdicts.yaml").exists()

            page.get_by_label("Your name").fill("A. Author")
            page.keyboard.press("Enter")
            expect(three.locator(".saved-state")).to_have_text("saved")
            expect(three).not_to_have_class(re.compile(r"\bunsaved\b"))
            assert on_disk() == {"fake-bright-3": {"verdict": "keep"}}

            three.get_by_label("crop").check()
            three.get_by_placeholder("note").fill("Just room for the headline.")
            page.locator(f'{tile("fake-bright-2")} .head code').click()
            page.keyboard.press("d")
            expect(page.locator("#status")).to_have_text("every mark is saved to verdicts.yaml")
            expect(page.locator(f"#run-{run.name} .run-meta")).to_contain_text(f"rated by A. Author on {RATED_ON}")
            assert on_disk() == {"fake-bright-2": {"verdict": "drop"},
                                 "fake-bright-3": {"verdict": "keep", "issues": ["crop"],
                                                   "note": "Just room for the headline."}}
            page.keyboard.press("d")
            expect(page.locator(f'{tile("fake-bright-2")} .saved-state')).to_have_text("cleared")
            assert "fake-bright-2" not in on_disk()

            need_note = page.locator(f'[id="need-{run.name}/ma-man"] .need-note')
            need_note.get_by_label("note on ma-man").fill("None of these look 50.")
            expect(need_note.locator(".saved-state")).to_have_text("not saved yet")
            expect(need_note.locator(".saved-state")).to_have_text("saved")
            assert yaml.safe_load((run / "verdicts.yaml").read_text())["notes"] == {"ma-man": "None of these look 50."}
            page.screenshot(path=tmp_path / "review.png")

            page.reload()
            expect(page.get_by_label("Your name")).to_have_value("A. Author")
            expect(page.get_by_label("note on ma-man")).to_have_value("None of these look 50.")
            page.get_by_label("Your name").fill("B. Other")
            page.keyboard.press("Enter")
            four = page.locator(tile("fake-bright-4"))
            four.get_by_role("button", name="maybe").click()
            expect(four.locator(".saved-state")).to_have_text(
                "not saved: this run is rated by A. Author, and one person rates a run, so a mark from B. Other is not saved")
            expect(four).to_have_class(re.compile(r"\bunsaved\b"))
            expect(page.locator("#status")).to_have_text("1 mark not saved")
            assert "fake-bright-4" not in on_disk()

            static = browser.new_page()
            static.goto((run / "review.html").as_uri())
            expect(static.locator("#banner")).to_be_visible()
            keep = static.locator(f'{tile("fake-bright-3")} button.keep')
            expect(keep).to_be_disabled()
            expect(keep).to_have_attribute("aria-pressed", "true")
            expect(static.get_by_label("note on ma-man")).to_be_disabled()
            expect(static.get_by_label("note on ma-man")).to_have_value("None of these look 50.")
        finally:
            browser.close()
    assert yaml.safe_load((run / "verdicts.yaml").read_text()) == {
        "rated_by": "A. Author", "rated_on": RATED_ON, "needs": {"ke-woman": {
            "fake-bright-3": {"verdict": "keep", "issues": ["crop"], "note": "Just room for the headline."}}},
        "notes": {"ma-man": "None of these look 50."}}


@pytest.mark.browser
def test_the_runs_page_folds_older_runs_filters_by_verdict_and_offers_a_new_round(sent, tmp_path, capsys):
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(BRIEF)
    runs = brief.parent / "runs"
    for _ in range(2):
        cli.main(["source", str(brief), "--seed", "1"])
    capsys.readouterr()
    first, second, third = (f"{TODAY.isoformat()}-{n}" for n in (1, 2, 3))
    (runs / second / "verdicts.yaml").write_text(yaml.safe_dump({"rated_by": "A. Author", "rated_on": TODAY, "needs": {
        "ke-woman": {"fake-bright-2": {"verdict": "keep"}, "fake-bright-3": {"verdict": "drop"}}}}))
    tile = 'article[data-key="{}/ke-woman/{}"]'.format
    with serving(runs) as served, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=render.chrome_path())
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(str(served.base_url))
            expect(page.locator("details.run > summary h2")).to_have_text([second, first])
            expect(page.locator(f"#run-{second}")).to_have_attribute("open", "")
            expect(page.locator(tile(first, "fake-bright-2"))).to_be_hidden()
            expect(page.locator(tile(second, "fake-bright-2"))).to_be_visible()
            expect(page.locator(f'{tile(second, "fake-bright-3")} .head .name')).to_have_text("2.2")

            page.get_by_label("unrated").check()
            expect(page.locator(tile(second, "fake-bright-2"))).to_be_hidden()
            expect(page.locator(tile(second, "fake-bright-4"))).to_be_visible()
            page.get_by_label("hide dropped").check()
            expect(page.locator(tile(second, "fake-bright-2"))).to_be_visible()
            expect(page.locator(tile(second, "fake-bright-3"))).to_be_hidden()
            page.get_by_label("keep", exact=True).check()
            expect(page.locator(tile(second, "fake-bright-4"))).to_be_hidden()
            page.get_by_label("all").check()

            expect(page.get_by_role("button", name="New round: show it")).to_be_hidden()
            cli.main(["source", str(brief), "--seed", "1"])
            capsys.readouterr()
            offer = page.get_by_role("button", name="New round: show it")
            expect(offer).to_be_visible(timeout=10_000)
            offer.click()
            expect(page.locator("details.run > summary h2")).to_have_text([third, second, first])
            expect(page.locator(f"#run-{third}")).to_have_attribute("open", "")
            page.screenshot(path=tmp_path / "runs.png")
        finally:
            browser.close()
