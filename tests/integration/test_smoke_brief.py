"""The committed smoke brief stays runnable: it parses, its templates exist, and its requests build. No network."""
import re
from pathlib import Path

from ballyhoo import cli, runs

SMOKE = Path(__file__).parents[2] / "smoke" / "brief.yaml"
# docs/creative-rules.md: no one looks older than middle age, so a need or query never asks for it.
TOO_OLD = re.compile(r"\b(elderly|old|seniors?|grand(mother|father)s?|sixties|seventies|eighties|5[6-9]|[6-9]\d)\b",
                     re.IGNORECASE)


def test_the_smoke_brief_parses_and_its_preview_templates_exist():
    needs, designs, errors = runs.load(SMOKE, cli.PROVIDERS)
    assert errors == []
    assert [n.name for n in needs] == ["ke-woman", "ma-man", "ma-woman"]
    assert all(n.templates and n.copy for n in needs)
    assert all((designs / f"{t}.html").is_file() for n in needs for t in n.templates)


def test_the_smoke_brief_only_searches_pexels_and_every_request_builds_for_free():
    jobs, costs, errors = runs.plan(SMOKE, cli.PROVIDERS, {"PEXELS_API_KEY": "unsent"}, None, 1, 0.0, False)
    assert errors == []
    assert {(j.provider, j.kind) for j in jobs} == {("pexels", "search")}
    assert sum(costs) == 0


def test_the_smoke_brief_asks_for_no_one_older_than_middle_age():
    needs, _, _ = runs.load(SMOKE, cli.PROVIDERS)
    texts = [n.need for n in needs] + [q.text for n in needs for queries in n.search.values() for q in queries]
    assert [t for t in texts if TOO_OLD.search(t)] == []
