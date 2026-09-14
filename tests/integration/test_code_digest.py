"""The render cache's code digest, over the package's real files: no browser."""
from ballyhoo import cache, render


def test_the_render_digest_covers_the_modules_rendering_imports_and_not_sourcing():
    modules = cache.code_modules("render.py", render.package_sources())
    assert {"render.py", "art.py", "cache.py", "checks.py", "copyfile.py", "fit.py", "provenance.py",
            "__init__.py"} <= set(modules)
    assert not {"cli.py", "sourcing.py", "candidates.py"} & set(modules)
    assert not [m for m in modules if m.startswith("providers/")]
