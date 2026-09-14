import pytest

from ballyhoo.cache import code_modules, inputs_digest, should_render, template_refs


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


PACKAGE = {
    "__init__.py": "",
    "render.py": "import numpy as np\nfrom . import art, fit\nfrom .copyfile import Job\n",
    "art.py": "from . import cache, provenance\n",
    "cache.py": "import ast\n",
    "fit.py": "from .render import Job  # a cycle\n",
    "copyfile.py": "",
    "provenance.py": "",
    "sourcing.py": "from . import art\nfrom .providers import Request\n",
    "cli.py": "from . import render, sourcing\n",
    "providers/__init__.py": "",
    "providers/pexels.py": "from ..candidates import Candidate\nfrom . import Request\n",
    "candidates.py": "from . import provenance\n",
}


def test_the_code_a_render_runs_is_what_it_imports_from_the_package_and_nothing_else():
    assert code_modules("render.py", PACKAGE) == [
        "__init__.py", "art.py", "cache.py", "copyfile.py", "fit.py", "provenance.py", "render.py"]


def test_imports_resolve_through_subpackages_and_parent_packages():
    assert code_modules("sourcing.py", PACKAGE) == [
        "__init__.py", "art.py", "cache.py", "provenance.py", "providers/__init__.py", "sourcing.py"]
    assert code_modules("providers/pexels.py", PACKAGE) == [
        "__init__.py", "candidates.py", "provenance.py", "providers/__init__.py", "providers/pexels.py"]
