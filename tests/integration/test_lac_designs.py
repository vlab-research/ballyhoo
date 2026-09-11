"""The real LAC designs, with stand-in art. Each test after the first is a bug
found while building those ads."""
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from ballyhoo import checks, render

pytestmark = pytest.mark.browser

EXPECTED = Path(__file__).parents[1] / "fixtures" / "lac" / "expected.yaml"
HILLS_MAN_PILOT = 'hills-man:\n  AR:\n    pilot: "Sumate a la encuesta y ganá $3.000 de saldo."\n'


def test_every_lac_creative_passes_at_its_recorded_size_and_line_count(lac_study, request):
    results, errors = render.run(lac_study / "creatives.yaml", check=True)
    assert errors == []
    assert {r.job.key: r.message for r in results if r.status != "ok"} == {}
    layout = {r.job.key: f"{r.size:g}px, {r.lines} lines" for r in results}
    if request.config.getoption("--update-expected"):
        EXPECTED.write_text(yaml.safe_dump(layout, sort_keys=True))
    assert layout == yaml.safe_load(EXPECTED.read_text())


def test_tight_line_height_fits_at_the_template_size(lac_case):
    # Measured as the font's content area, this headline overflowed at every size.
    [result], _ = render.run(lac_case(HILLS_MAN_PILOT), check=True)
    assert (result.status, result.size, result.lines) == ("ok", 79, 4)


def test_a_mask_speck_under_the_headline_is_not_a_collision(lac_case, monkeypatch):
    copy = lac_case(HILLS_MAN_PILOT)
    [result], _ = render.run(copy, check=True)
    assert result.status == "ok"
    monkeypatch.setattr(checks, "SPECK_PX", 1)  # proves the speck really is under the headline
    [result], _ = render.run(copy, check=True)
    assert result.status == "FAIL" and "overlaps #figure" in result.message


def test_the_band_mask_loads_from_a_local_file(lac_case):
    # Without --allow-file-access-from-files the CORS-mode mask fetch fails and the
    # band silently disappears.
    copy = lac_case('cats-band:\n  HN:\n    recarga: "Tu opinión cuenta: encuesta corta con *L 90 de recarga*."\n')
    [result], _ = render.run(copy)
    assert result.status == "ok"
    png = np.asarray(Image.open(copy.parent / "out" / "cats-band_HN_recarga_1080x1080.png").convert("RGB"))
    r, g, b = png[40:70, 0:40].reshape(-1, 3).mean(axis=0)  # inside the band, left of the text
    assert r > 200 and g > 200 and b < 140, (r, g, b)


def test_a_headline_box_reaching_below_the_womans_hairline_collides(lac_case):
    copy = lac_case('hills-woman:\n  HN:\n    sin-monto: "Tu opinión cuenta: encuesta corta con recarga para tu celular."\n',
                    [("hills-woman", "height: 216px;", "height: 240px;")])
    [result], _ = render.run(copy, check=True)
    assert result.status == "FAIL" and "overlaps #figure" in result.message


def test_the_couple_at_the_partners_position_collides_with_a_full_second_line(lac_case):
    copy = lac_case('zigzag-couple:\n  HN:\n    recarga: "Tu opinión cuenta: encuesta corta con *L 90 de recarga*."\n',
                    [("zigzag-couple", "left: 240px; top: 245px;", "left: 240px; top: 220px;"),
                     ("zigzag-couple", "left: 48px; top: 16px; width: 1000px; height: 250px;",
                      "left: 48px; top: 20px; width: 1000px; height: 260px;")])
    [result], _ = render.run(copy, check=True)
    assert result.status == "FAIL" and "overlaps #figure" in result.message


def test_missing_art_fails_loudly_and_names_the_file(lac_case):
    copy = lac_case('dogs-band:\n  AR:\n    recarga: "Hola."\n')
    (copy.parent / "library" / "characters" / "cool-dogs.png").unlink()
    [result], _ = render.run(copy)
    assert result.status == "FAIL" and "references missing file ../../characters/cool-dogs.png" in result.message
