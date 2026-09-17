"""The committed smoke brief stays runnable: it parses, its templates exist, and its requests build. No network."""
import re
from pathlib import Path

from ballyhoo import brief, cli, runs

SMOKE = Path(__file__).parents[2] / "smoke" / "brief.yaml"
ENV = {"PEXELS_API_KEY": "unsent", "GOOGLE_CLOUD_PROJECT": "unsent"}
# docs/creative-rules.md: no one looks older than middle age, so a need, query or prompt never asks for it.
TOO_OLD = re.compile(r"\b(elderly|old|seniors?|grand(mother|father)s?|sixties|seventies|eighties|5[6-9]|[6-9]\d)\b",
                     re.IGNORECASE)


def test_the_smoke_brief_parses_and_its_preview_templates_exist():
    needs, designs, errors = runs.load(SMOKE, cli.PROVIDERS)
    assert errors == []
    assert [n.name for n in needs] == ["ea-woman", "na-man", "na-woman", "na-woman-drawn"]
    assert all(n.templates and n.copy for n in needs)
    assert all((designs / f"{t}.html").is_file() for n in needs for t in n.templates)


def test_the_smoke_brief_searches_pexels_for_free_and_draws_one_need_with_gemini():
    jobs, costs, errors = runs.plan(SMOKE, cli.PROVIDERS, ENV, None, 1, 1.0, False)
    assert errors == []
    assert {(j.provider, j.kind) for j in jobs} == {("pexels", "search"), ("gemini", "generate")}
    [drawing] = [j for j in jobs if j.kind == "generate"]
    assert (drawing.need, drawing.style, drawing.drawing, drawing.n) == ("na-woman-drawn", "precise-pastel", True, 2)
    assert round(sum(costs), 3) == 0.202, "twelve free searches, and two Gemini images at 2K"


def test_the_smoke_brief_exercises_the_orientation_option_on_one_query():
    jobs, _, _ = runs.plan(SMOKE, cli.PROVIDERS, ENV, None, 1, 1.0, False)
    assert [j.text for j in jobs if j.options == {"orientation": "square"}] == ["middle aged arab man portrait"]


def test_the_smoke_brief_draws_the_need_stock_has_never_served_into_the_figure_template():
    needs, designs, _ = runs.load(SMOKE, cli.PROVIDERS)
    [drawn] = [n for n in needs if n.generate]
    assert drawn.name == "na-woman-drawn" and drawn.templates == ("figure-band/1080x1080",)
    assert not drawn.search, "stock has no unveiled North African woman of this age, which is why she is drawn"
    assert '<img id="figure"' in (designs / f"{drawn.templates[0]}.html").read_text()


def test_the_smoke_brief_asks_for_no_one_older_than_middle_age():
    needs, _, _ = runs.load(SMOKE, cli.PROVIDERS)
    texts = [n.need for n in needs] + [q.text for n in needs for queries in n.search.values() for q in queries] \
        + [j.text for j in brief.expand(needs, cli.PROVIDERS, 1)]  # every prompt as it would be sent, style and all
    assert [t for t in texts if TOO_OLD.search(t)] == []
