import shutil
from pathlib import Path

import pytest

import lac_art

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption("--update-expected", action="store_true",
                     help="rewrite tests/fixtures/lac/expected.yaml from this run")


@pytest.fixture(scope="session")
def lac_study(tmp_path_factory):
    """The LAC fixture with stand-in art, in a temporary directory."""
    root = tmp_path_factory.mktemp("lac")
    shutil.copytree(FIXTURES / "lac", root, dirs_exist_ok=True)
    lac_art.write_all(root / "library")
    return root


@pytest.fixture
def lac_case(tmp_path, lac_study):
    """A private copy of the LAC fixture with one copy file and optional template edits."""
    def make(copy, template_edits=()):
        root = tmp_path / "lac"
        shutil.copytree(lac_study, root)
        for design, old, new in template_edits:
            template = root / "library" / "designs" / design / "1080x1080.html"
            source = template.read_text()
            assert old in source, f"{design} template no longer contains {old!r}"
            template.write_text(source.replace(old, new))
        copy_file = root / "case.yaml"
        copy_file.write_text("designs: library/designs\n" + copy)
        return copy_file
    return make
