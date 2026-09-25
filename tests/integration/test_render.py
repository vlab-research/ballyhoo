"""Phase 1 acceptance criteria (docs/design.md), end to end through a real browser."""
import asyncio

import numpy as np
import pytest
from playwright.async_api import async_playwright
from PIL import Image

from ballyhoo import art, provenance, render

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
    figure = design / "figure.png"
    Image.new("RGBA", (200, 250), (40, 60, 80, 255)).save(figure)
    art.write_sidecar(figure, provenance.made(art.file_digest(figure), "test_render.py", "test fixture"))
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


def test_an_image_without_provenance_fails_even_when_its_png_is_up_to_date(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Hola."\n')
    [result], _ = render.run(f)
    png = tmp_path / "out" / "demo_AR_uno_400x400.png"
    assert result.status == "ok" and png.exists()

    art.sidecar(tmp_path / "designs" / "demo" / "figure.png").unlink()
    [result], _ = render.run(f)
    assert result.status == "FAIL"
    assert result.message == "figure.png has no provenance: expected figure.png.provenance.yaml beside it"
    assert not png.exists()


def test_a_scene_drawn_larger_than_its_image_fails_saying_how_much(tmp_path):
    template = TEMPLATE.replace("#figure {", "#scene { left: 0; top: 0; width: 400px; height: 400px; object-fit: cover; }\n"
                                "  #figure {").replace('<img id="figure"', '<img id="scene" src="scene.png">\n  <img id="figure"')
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Hola."\n', template)
    scene = tmp_path / "designs" / "demo" / "scene.png"

    def scene_of(side):
        Image.new("RGB", (side, side), (230, 230, 225)).save(scene)
        art.sidecar(scene).unlink(missing_ok=True)
        art.write_sidecar(scene, provenance.made(art.file_digest(scene), "test_render.py", "test fixture"))

    scene_of(400)
    [result], _ = render.run(f, check=True)
    assert result.status == "ok" and result.message.endswith(", scene 1.00x")
    scene_of(100)
    [result], _ = render.run(f, check=True)
    assert result.status == "FAIL"
    assert result.message.startswith(
        "#scene is upscaled 4.00x (max 1.25x): a 100x100 image in a 400x400 box with object-fit: cover [")


def test_an_image_replaced_under_its_old_provenance_fails(tmp_path):
    f = project(tmp_path, 'demo:\n  AR:\n    uno: "Hola."\n')
    Image.new("RGBA", (200, 250), (200, 60, 80, 255)).save(tmp_path / "designs" / "demo" / "figure.png")
    [result], _ = render.run(f)
    assert result.status == "FAIL" and "figure.png: provenance sha256 is not this file's" in result.message


def test_a_drawing_put_into_the_figure_slot_keeps_its_shape_and_stands_on_the_slots_bottom_edge(tmp_path):
    square = TEMPLATE.replace("top: 150px; width: 200px; height: 250px;", "top: 200px; width: 200px; height: 200px;")
    project(tmp_path, 'demo:\n  AR:\n    uno: "Hola."\n', square)
    drawing = tmp_path / "drawing.png"
    Image.new("RGBA", (300, 400), (200, 60, 80, 255)).save(drawing)  # 3:4, in a 200x200 slot

    async def preview():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=render.chrome_path(), args=render.CHROME_ARGS)
            try:
                return await render.render(browser, tmp_path / "designs" / "demo" / "400x400.html", "Hola.",
                                           swap=("figure", drawing))
            finally:
                await browser.close()

    image, failures, _, _ = asyncio.run(preview())
    assert failures == []
    ys, xs = np.nonzero((np.abs(image.astype(int) - (200, 60, 80)).max(axis=2) < 8))
    left, right, top, bottom = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    assert abs((right - left) / (bottom - top) - 3 / 4) < 0.02, "a 3:4 drawing is not stretched to a square slot"
    assert (bottom - top, bottom) == (200, 400), "it fills the slot's height and stands on its bottom edge"
    assert abs((left + right) / 2 - 300) <= 1, "it is centred across the slot"
