"""The smoke photo template, and `ballyhoo preview` on runs sourced from the fake provider."""
import datetime
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from ballyhoo import art, cli, provenance, render

REPO = Path(__file__).parents[2]
SMOKE_DESIGNS = REPO / "smoke" / "designs"
HIND = REPO / "tests" / "fixtures" / "lac" / "library" / "fonts" / "Hind-Bold.ttf"
TODAY = datetime.date.today().isoformat()
BAND = "photo-band/1080x1080"
COPY = "Take a short survey and get *KES 100* airtime."
ONE_NEED = "ke-woman:\n  need: A woman.\n  search: {fake: bright village}\n"


def source(tmp_path, capsys, designs, needs):
    """A run sourced from the fake provider, one result per query, previewing with the photo-band template."""
    brief = tmp_path / "study" / "brief.yaml"
    brief.parent.mkdir()
    brief.write_text(f"designs: {designs}\ndefaults:\n  n: 1\n  preview: {{templates: [{BAND}], copy: '{COPY}'}}\n"
                     + needs)
    cli.main(["source", str(brief), "--seed", "1"])
    capsys.readouterr()
    return brief.parent / "runs" / f"{TODAY}-1"


@pytest.mark.browser
def test_the_smoke_template_renders_on_its_own_with_its_placeholder(tmp_path):
    copy = tmp_path / "creatives.yaml"
    copy.write_text(f'designs: {SMOKE_DESIGNS}\nphoto-band:\n  KE:\n    airtime: "{COPY}"\n')
    [result], errors = render.run(copy, check=True)
    assert errors == []
    assert (result.status, result.lines) == ("ok", 2), result.message
    assert result.message.endswith(", scene 1.00x")


@pytest.mark.browser
def test_preview_renders_every_candidate_and_records_what_the_checks_found(sent, tmp_path, capsys):
    run = source(tmp_path, capsys, SMOKE_DESIGNS, """
ke-woman:
  need: A Kenyan woman aged 60 or more, using a phone.
  search:
    fake: [bright village, dark village, small village]
  generate:
    fake: A woman in bright light.
down:
  need: Anything.
  search: {fake: error}
""")
    manifest = (run / "manifest.yaml").read_text()
    need = run / "ke-woman"
    generated = yaml.safe_load((need / "candidates.yaml").read_text())["candidates"][3]["id"]

    assert cli.main(["preview", str(run)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "skip  down: no candidates in this run"
    assert out[-1] == "4 previews: 2 pass, 2 fail, 0 errors"

    checks = yaml.safe_load((need / "checks.yaml").read_text())
    assert (checks["copy"], checks["templates"]) == (COPY, [BAND])
    assert checks["summary"] == {"candidates": 4, "pass": 2, "fail": 2}
    previews = {id_: c["previews"][BAND] for id_, c in checks["candidates"].items()}
    assert {id_: p["status"] for id_, p in previews.items()} == {
        "fake-bright-2": "pass", "fake-dark-2": "fail", "fake-small-2": "fail", generated: "pass"}
    [contrast] = previews["fake-dark-2"]["failures"]
    assert contrast.startswith("contrast ") and contrast.endswith(" is below 3:1")
    assert previews["fake-small-2"]["failures"] == [
        "#scene is upscaled 2.70x (max 1.25x): a 400x400 image in a 1080x1080 box with object-fit: cover"]
    # 0.90x is the 1600x1200 candidate's scale; the 1080 px placeholder it replaced would be 1.00x.
    assert previews["fake-bright-2"]["summary"].endswith(", scene 0.90x")

    assert sorted(p.name for p in (need / "previews").iterdir()) == sorted(
        Path(p["file"]).name for p in previews.values())
    with Image.open(need / previews["fake-dark-2"]["file"]) as im:
        assert im.size == (1080, 1080)
    assert not (run / "down").exists()
    assert list(tmp_path.rglob("out")) == []
    assert (run / "manifest.yaml").read_text() == manifest
    page = (run / "review.html").read_text()
    assert '"editable": false' in page and '"fake-dark-2"' in page, "a run can be viewed without the server"


def test_a_template_without_a_scene_is_an_error_and_nothing_is_rendered(sent, tmp_path, capsys):
    designs = tmp_path / "designs"
    shutil.copytree(SMOKE_DESIGNS, designs)
    template = designs / "photo-band" / "1080x1080.html"
    template.write_text(template.read_text().replace('<img id="scene"', '<img id="photo"'))
    run = source(tmp_path, capsys, designs, ONE_NEED)

    assert cli.main(["preview", str(run)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        'FAIL  photo-band/1080x1080: it has no #scene; candidates go into an <img id="scene">']
    assert not (run / "ke-woman" / "previews").exists() and not (run / "ke-woman" / "checks.yaml").exists()


@pytest.mark.browser
def test_the_image_a_candidate_replaces_needs_no_provenance_but_the_templates_other_images_do(sent, tmp_path, capsys):
    design = tmp_path / "designs" / "photo-band"
    design.mkdir(parents=True)
    shutil.copy(SMOKE_DESIGNS / "photo-band" / "scene-placeholder.png", design)  # and not its provenance
    html = (SMOKE_DESIGNS / "photo-band" / "1080x1080.html").read_text()
    html = html.replace("../../../tests/fixtures/lac/library/fonts/Hind-Bold.ttf", HIND.as_posix()).replace(
        '<div id="band"></div>',
        '<div id="band"></div>\n  <img id="logo" src="logo.png" style="left: 900px; top: 960px; width: 120px; height: 80px">')
    (design / "1080x1080.html").write_text(html)
    logo = design / "logo.png"
    Image.new("RGB", (120, 80), (30, 90, 160)).save(logo)
    run = source(tmp_path, capsys, tmp_path / "designs", ONE_NEED)

    assert cli.main(["preview", str(run)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "FAIL  photo-band/1080x1080: logo.png has no provenance: expected logo.png.provenance.yaml beside it"]

    art.write_sidecar(logo, provenance.made(art.file_digest(logo), "test_preview.py", "test fixture"))
    assert cli.main(["preview", str(run)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "1 previews: 1 pass, 0 fail, 0 errors"
