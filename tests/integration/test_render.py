"""Phase 1 acceptance criteria (docs/design.md), end to end through a real browser."""
import pytest
from PIL import Image

from ballyhoo import render

pytestmark = pytest.mark.browser

TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<style>
  html, body { margin: 0; }
  #canvas { position: relative; width: 400px; height: 400px; overflow: hidden; background: #ffffff; }
  #canvas > * { position: absolute; margin: 0; }
  #figure { left: 200px; top: 150px; width: 200px; height: 250px; }
  #headline { left: 20px; top: 20px; width: 360px; height: 120px; font: 700 40px/1.1 sans-serif; color: #000; }
  #headline em { font-style: normal; color: #b00; }
</style>
<div id="canvas">
  <img id="figure" src="figure.png">
  <h1 id="headline" data-min-size="20" data-max-lines="2">{{text}}</h1>
</div>
"""


def project(root, copy, template=TEMPLATE):
    design = root / "designs" / "demo"
    design.mkdir(parents=True)
    (design / "400x400.html").write_text(template)
    Image.new("RGBA", (200, 250), (40, 60, 80, 255)).save(design / "figure.png")
    creatives = root / "creatives.yaml"
    creatives.write_text(copy)
    return creatives


def statuses(results):
    return {r.job.variant: r.status for r in results}


def test_editing_one_string_rerenders_only_that_variant(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Una encuesta *corta*."\n    dos: "Tu opinión cuenta."\n')
    results, errors = render.run(f)
    assert not errors and statuses(results) == {"uno": "ok", "dos": "ok"}
    uno = (tmp_path / "out" / "demo_AR_uno_400x400.png").read_bytes()

    results, _ = render.run(f)
    assert statuses(results) == {"uno": "skip", "dos": "skip"}

    f.write_text(f.read_text().replace("Tu opinión cuenta.", "Tu opinión importa."))
    results, _ = render.run(f)
    assert statuses(results) == {"uno": "skip", "dos": "ok"}
    assert (tmp_path / "out" / "demo_AR_uno_400x400.png").read_bytes() == uno


def test_adding_a_variant_first_renames_and_rerenders_nothing(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Una encuesta corta."\n')
    render.run(f)
    f.write_text('demo:\n  AR:\n    cero: "Nueva."\n    uno: "Una encuesta corta."\n')
    results, _ = render.run(f)
    assert statuses(results) == {"cero": "ok", "uno": "skip"}


def test_overlong_headline_fails_alone_and_is_not_written(tmp_path):
    long = " ".join(["palabra"] * 40)
    f = project(tmp_path, f'demo:\n  HN:\n    corta: "Hola."\n    larga: "{long}"\n')
    results, _ = render.run(f)
    assert statuses(results) == {"corta": "ok", "larga": "FAIL"}
    [failed] = [r for r in results if r.status == "FAIL"]
    assert failed.job.key == "demo/HN/larga/400x400"
    assert "does not fit at the 20px floor" in failed.message
    assert not (tmp_path / "out" / "demo_HN_larga_400x400.png").exists()


def test_a_creative_that_starts_failing_loses_its_old_png(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Hola."\n')
    render.run(f)
    png = tmp_path / "out" / "demo_AR_uno_400x400.png"
    assert png.exists()
    f.write_text('demo:\n  AR:\n    uno: "' + " ".join(["palabra"] * 40) + '"\n')
    render.run(f)
    assert not png.exists()


def test_headline_over_the_figure_fails(tmp_path):
    template = TEMPLATE.replace("left: 20px; top: 20px;", "left: 20px; top: 220px;")
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Una encuesta corta para vos."\n', template)
    [result], _ = render.run(f)
    assert result.status == "FAIL" and "overlaps #figure" in result.message


def test_variants_must_be_a_named_map(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    - "Una encuesta corta."\n')
    results, errors = render.run(f)
    assert results == [] and any("named map" in e for e in errors)


def test_check_writes_nothing(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Una encuesta corta."\n')
    [result], _ = render.run(f, check=True)
    assert result.status == "ok" and not (tmp_path / "out").exists()


def test_designs_path_is_relative_to_the_copy_file(tmp_path):
    project(tmp_path / "library", 'demo: {}\n')
    study = tmp_path / "study"
    study.mkdir()
    copy = study / "creatives.yaml"
    copy.write_text('designs: ../library/designs\ndemo:\n  AR:\n    uno: "Hola."\n')
    [result], errors = render.run(copy)
    assert not errors and result.status == "ok"
    assert (study / "out" / "demo_AR_uno_400x400.png").exists()
