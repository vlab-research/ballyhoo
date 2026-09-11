"""The copy file: which creatives exist.

Pure. The shell loads the YAML and finds the templates; this module validates
the copy and expands it into one job per design x country x variant x template.
"""
import html
import re
from dataclasses import dataclass
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TEMPLATE_NAME = re.compile(r"^(\d+)x(\d+)\.html$")
RESERVED = frozenset({"designs"})
DEFAULT_DESIGNS = "designs"


@dataclass(frozen=True)
class Job:
    design: str
    country: str
    variant: str
    text: str
    template: Path

    @property
    def size(self):
        return template_size(self.template.name)

    @property
    def key(self):
        """design/country/variant/size: the name this creative is known by downstream."""
        return f"{self.design}/{self.country}/{self.variant}/{self.template.stem}"

    @property
    def out_name(self):
        return f"{self.design}_{self.country}_{self.variant}_{self.template.stem}.png"


def template_size(name):
    """(width, height) from a template file name such as 1080x1350.html, else None."""
    m = TEMPLATE_NAME.match(name)
    return (int(m.group(1)), int(m.group(2))) if m else None


def designs_dir(data, copy_dir):
    """Where a loaded copy file's designs live, relative to the copy file. Returns (path, errors)."""
    if not isinstance(data, dict):
        return None, ["expected a map of design -> country -> variant -> text"]
    designs = data.get("designs", DEFAULT_DESIGNS)
    if not isinstance(designs, str) or not designs.strip():
        return None, ["designs must be a path to the directory of designs"]
    return Path(copy_dir) / designs, []


def design_names(data):
    return [str(name) for name in data if name not in RESERVED]


def variant_problem(variant, text):
    if not isinstance(variant, str) or not SLUG.match(variant):
        return "variant names are lowercase slugs"
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if text.count("*") % 2:
        return f"unbalanced * in {text!r}"
    return None


def parse(data, templates, root=None):
    """Expand a loaded copy file into jobs.

    `templates` maps each design name to the paths found in its directory; names
    that are not <W>x<H>.html are ignored. Returns (jobs, errors). An error in one
    design, country or variant is reported and the rest still expand.
    """
    jobs, errors = [], []
    for design, countries in data.items():
        if design in RESERVED:
            continue
        design = str(design)
        found = sorted(Path(p) for p in templates.get(design, ()) if template_size(Path(p).name))
        if not found:
            where = f" in {Path(root) / design}" if root else ""
            errors.append(f"{design}: no <W>x<H>.html templates{where}")
            continue
        if not isinstance(countries, dict):
            errors.append(f"{design}: expected a map of country -> variants")
            continue
        for country, variants in countries.items():
            if not isinstance(country, str):
                errors.append(f"{design}/{country}: country must be a string (quote it; YAML reads NO as false)")
            elif not isinstance(variants, dict):
                # A list would make output keys depend on position; see docs/design.md.
                errors.append(f"{design}/{country}: variants must be a named map, not a {type(variants).__name__}")
            else:
                for variant, text in variants.items():
                    problem = variant_problem(variant, text)
                    if problem:
                        errors.append(f"{design}/{country}/{variant}: {problem}")
                    else:
                        jobs += [Job(design, country, variant, text.strip(), t) for t in found]
    return jobs, errors


def select(jobs, design=None, country=None, variant=None, size=None):
    return [j for j in jobs
            if design in (None, j.design) and country in (None, j.country)
            and variant in (None, j.variant) and size in (None, j.template.stem)]


def markup(text):
    """HTML for a headline: escaped, with *words* as <em>. The template styles <em>."""
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", html.escape(text))
