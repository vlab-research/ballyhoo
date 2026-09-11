import pytest

from ballyhoo.cache import inputs_digest, should_render, template_refs


def test_template_refs_are_the_local_files_a_template_loads():
    source = """
      <img id="hills" src="../../backgrounds/wave-hills.png">
      <link rel="stylesheet" href='shared.css'>
      <style>
        @font-face { src: url("../../fonts/Hind-Bold.ttf"); }
        #band { mask: url(band.png) 0 0, url( 'band.png' ) 0 0; }
        #dot { background: url(data:image/png;base64,iVBORw0KGgo=); }
      </style>
      <img src="https://cdn.example.com/logo.png">
      <a href="#canvas">skip</a>
    """
    assert template_refs(source) == ["../../backgrounds/wave-hills.png", "../../fonts/Hind-Bold.ttf",
                                     "band.png", "shared.css"]


BASE = dict(code="c1", text="Hola.", template="<html>", ref_digests={"hills.png": "d1", "Hind.ttf": "d2"})


@pytest.mark.parametrize("change", [
    {"code": "c2"},
    {"text": "Chau."},
    {"template": "<html> "},
    {"ref_digests": {"hills.png": "d1-edited", "Hind.ttf": "d2"}},
    {"ref_digests": {"hills2.png": "d1", "Hind.ttf": "d2"}},
    {"ref_digests": {"hills.png": "d1"}},
])
def test_changing_any_input_changes_the_digest(change):
    assert inputs_digest(**{**BASE, **change}) != inputs_digest(**BASE)


def test_digest_does_not_depend_on_reference_order():
    reordered = {"Hind.ttf": "d2", "hills.png": "d1"}
    assert inputs_digest(**{**BASE, "ref_digests": reordered}) == inputs_digest(**BASE)


def test_moving_characters_between_inputs_changes_the_digest():
    assert inputs_digest("c", "ab", "c", {}) != inputs_digest("c", "a", "bc", {})


@pytest.mark.parametrize("stored, check, force, render", [
    ("h", False, False, False),  # up to date: skip
    ("old", False, False, True),  # inputs changed
    (None, False, False, True),  # never rendered
    ("h", True, False, True),  # --check renders to verify, even when up to date
    ("h", False, True, True),  # --force
])
def test_only_an_up_to_date_normal_run_is_skipped(stored, check, force, render):
    assert should_render(stored, "h", check=check, force=force) is render
