"""`keep --verdicts` on a drawing: the art library gets the cut-out, not the green it was drawn on.

The run is sourced from the fake provider through a mock transport. No network, no browser.
"""
import datetime
import hashlib
from pathlib import Path

import yaml

from ballyhoo import art, candidates, cli, provenance

SMOKE_DESIGNS = Path(__file__).parents[2] / "smoke" / "designs"
TODAY = datetime.datetime.now(datetime.timezone.utc).date()  # a run is named for its UTC day
BRIEF = f"""designs: {SMOKE_DESIGNS}
defaults:
  n: 1
  preview: {{templates: [figure-band/1080x1080], copy: Take a short survey.}}
styles:
  pastel-hand:
    style: The picture is hand drawn, extremely detailed, pastel palette.
na-woman:
  need: A woman who reads as North African, drawn.
  generate:
    fake: {{style: pastel-hand, subject: 'figure: a woman in her fifties.'}}
"""


def test_keeping_a_drawing_keeps_its_cut_out_with_the_style_the_key_and_the_generation_behind_it(
        sent, tmp_path, capsys):
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(BRIEF)
    assert cli.main(["source", str(brief), "--seed", "1"]) == 0
    capsys.readouterr()
    run = brief.parent / "runs" / f"{TODAY.isoformat()}-1"
    [drawn], _ = candidates.load(yaml.safe_load((run / "na-woman" / "candidates.yaml").read_text()))
    (run / "verdicts.yaml").write_text(yaml.safe_dump({"rated_by": "A. Author", "rated_on": TODAY, "needs": {
        "na-woman": {drawn.id: {"verdict": "keep"}}}}))

    characters = tmp_path / "characters"
    assert cli.main(["keep", str(run), "--verdicts", "--need", "na-woman", "--to", str(characters)]) == 0
    image = characters / f"{drawn.id}.png"
    assert capsys.readouterr().out.splitlines() == [f"ok    {image}"]
    assert image.read_bytes() == (run / "na-woman" / drawn.cutout.file).read_bytes(), "the cut-out, not the green"

    record = yaml.safe_load(art.sidecar(image).read_text())
    assert provenance.problems(record, art.file_digest(image)) == []
    assert (record["style"], record["key_colour"]) == ("pastel-hand", [10, 200, 20])
    assert record["picked"] == {"by": "A. Author", "on": TODAY} and "fetched" not in record
    assert record["raw_sha256"] == hashlib.sha256((run / "na-woman" / drawn.full).read_bytes()).hexdigest()
    assert record["sha256"] != record["raw_sha256"], "a cut-out is not the file the model sent"
