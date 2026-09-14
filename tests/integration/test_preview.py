"""The smoke photo template and previews, through a real browser."""
from pathlib import Path

import pytest

from ballyhoo import render

pytestmark = pytest.mark.browser

SMOKE_DESIGNS = Path(__file__).parents[2] / "smoke" / "designs"


def test_the_smoke_template_renders_on_its_own_with_its_placeholder(tmp_path):
    copy = tmp_path / "creatives.yaml"
    copy.write_text(f'designs: {SMOKE_DESIGNS}\nphoto-band:\n  KE:\n    airtime: "Take a short survey and get *KES 100* airtime."\n')
    [result], errors = render.run(copy, check=True)
    assert errors == []
    assert (result.status, result.lines) == ("ok", 2), result.message
    assert result.message.endswith(", scene 1.00x")
