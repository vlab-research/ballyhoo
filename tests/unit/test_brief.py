import datetime
from pathlib import Path

import pytest
import yaml

from ballyhoo import brief
from ballyhoo.brief import Job
from ballyhoo.providers import fal, firefly, gemini, openverse, pexels

PROVIDERS = {p.NAME: p for p in (fal, firefly, gemini, openverse, pexels)}
TEMPLATES = {"photo-band/1080x1080", "photo-band/1080x1350", "photo-side/1080x1080"}

BRIEF = """
defaults:
  n: 2
  size: 1080x1080
  prompt_suffix: No text anywhere.
  preview:
    templates: [photo-band/1080x1080]
    copy: Take a short survey.

ke-older-woman:
  need: A Kenyan woman aged 60 or more, rural, using a phone.
  search:
    pexels: older african woman phone
    openverse: [grandmother phone, elder phone]
  generate:
    gemini: A Kenyan woman in her sixties reading her phone.
    fal:
      prompt: A Kenyan woman in her sixties.
      model: fal-ai/flux-2-max

ma-older-man:
  need: A Moroccan man aged 60 or more.
  generate:
    gemini: {prompt: A Moroccan man in his sixties., image_size: 1K, seed: 81}
  n: 4
  prompt_suffix: Plain background.
  preview:
    templates: [photo-side/1080x1080]
    copy: Encuesta corta.
"""


def parse(text, templates=TEMPLATES):
    return brief.parse(yaml.safe_load(text), templates, PROVIDERS, root=Path("/lib/designs"))


def jobs_of(text, seed=7):
    needs, errors = parse(text)
    assert errors == []
    return brief.expand(needs, PROVIDERS, seed)


def test_a_brief_expands_into_one_job_per_query_and_one_per_prompt_with_defaults_overridable_per_need():
    assert jobs_of(BRIEF) == [
        Job("ke-older-woman", "pexels", "search", "older african woman phone", 2),
        Job("ke-older-woman", "openverse", "search", "grandmother phone", 2),
        Job("ke-older-woman", "openverse", "search", "elder phone", 2),
        Job("ke-older-woman", "gemini", "generate", "A Kenyan woman in her sixties reading her phone. No text anywhere.",
            2, 1080, 1080, model="gemini-3.1-flash-image", seed=7),
        Job("ke-older-woman", "fal", "generate", "A Kenyan woman in her sixties. No text anywhere.", 2, 1080, 1080,
            model="fal-ai/flux-2-max", seed=7),
        Job("ma-older-man", "gemini", "generate", "A Moroccan man in his sixties. Plain background.", 4, 1080, 1080,
            model="gemini-3.1-flash-image", seed=81, options={"image_size": "1K"}),
    ]
    needs, _ = parse(BRIEF)
    assert [(n.name, n.templates, n.copy) for n in needs] == [
        ("ke-older-woman", ("photo-band/1080x1080",), "Take a short survey."),
        ("ma-older-man", ("photo-side/1080x1080",), "Encuesta corta.")]
    assert needs[0].need == "A Kenyan woman aged 60 or more, rural, using a phone."


def test_without_a_size_a_generation_takes_the_first_preview_templates_and_n_defaults_to_two():
    [job] = jobs_of("ke:\n  need: x\n  generate: {fal: A woman in bright light.}\n"
                    "  preview: {templates: [photo-band/1080x1350, photo-band/1080x1080], copy: Hola.}\n")
    assert (job.width, job.height, job.n, job.seeds) == (1080, 1350, 2, [7, 8])


def test_every_mistake_in_a_brief_is_reported_together_and_the_sound_needs_still_parse():
    needs, errors = parse("""
defaults:
  n: 0
  need: Everyone
  preview: {templates: [photo-band/1200x628], copy: Take a short survey.}
Ke-Woman:
  need: A Kenyan woman.
  search: {pexels: woman phone}
ke-man:
  search:
    unsplash: man phone
    gemini: man phone
ke-family:
  need: A family.
ke-farmer:
  need: A farmer.
  colour: warm
  size: square
  generate:
    fal: {prompt: A farmer., image_size: 1K}
    gemini: {model: "", seed: -1}
    firefly: A farmer.
ma-man:
  need: A Moroccan man.
  search: {pexels: older man phone morocco}
""")
    assert [n.name for n in needs] == ["ma-man"]
    assert errors == [
        "defaults: unknown key 'need' (the name is reserved, so no need can use it)",
        "defaults: n must be a whole number of at least 1",
        "defaults/preview: template photo-band/1200x628 does not exist: expected /lib/designs/photo-band/1200x628.html",
        "Ke-Woman: need names are lowercase slugs",
        "ke-man: need is required: say what the image must show",
        "ke-man/search/unsplash: unknown provider (known: fal, firefly, gemini, openverse, pexels)",
        "ke-man/search/gemini: gemini cannot search",
        "ke-family: needs search or generate, or both",
        "ke-farmer: unknown key 'colour'",
        "ke-farmer: size must be <width>x<height>, e.g. 1080x1080",
        "ke-farmer/generate/fal: unknown key 'image_size'",
        "ke-farmer/generate/gemini: prompt is required",
        "ke-farmer/generate/gemini: model must be a model name",
        "ke-farmer/generate/gemini: seed must be a whole number",
    ]


def test_a_query_can_carry_its_providers_search_options_and_the_job_and_the_plan_record_them():
    jobs = jobs_of("ke:\n  need: x\n  search:\n    pexels:\n"
                   "      - middle aged arab man portrait\n"
                   "      - {query: moroccan man shop owner, orientation: square}\n")
    assert jobs == [Job("ke", "pexels", "search", "middle aged arab man portrait", 2),
                    Job("ke", "pexels", "search", "moroccan man shop owner", 2, options={"orientation": "square"})]
    assert brief.describe(jobs[1]) == {"need": "ke", "provider": "pexels", "kind": "search", "n": 2,
                                       "query": "moroccan man shop owner", "orientation": "square"}


def test_an_option_a_provider_does_not_take_names_it_and_lists_the_ones_it_does():
    _, errors = parse("""
ke:
  need: x
  search:
    pexels:
      - {query: a, colour: warm, size: large}
      - {orientation: square}
      - ''
    openverse:
      - {query: b, orientation: square}
""")
    assert errors == [
        "ke/search/pexels query 1: unknown options 'colour', 'size'; pexels searches take query, orientation",
        "ke/search/pexels query 2: query is required",
        "ke/search/pexels query 3: expected a query, or a map with query and pexels's search options",
        "ke/search/openverse query 1: unknown option 'orientation'; openverse searches take query",
    ]


def test_an_option_value_the_provider_cannot_use_stops_the_run_before_anything_is_sent():
    jobs = jobs_of("ke:\n  need: x\n  search: {pexels: {query: a, orientation: sideways}}\n")
    assert brief.request_problems(jobs, PROVIDERS, {"PEXELS_API_KEY": "k"}) == [
        "ke/pexels: orientation 'sideways' must be one of landscape, portrait, square"]


def test_generating_needs_a_size_and_queries_and_prompts_must_be_text():
    _, errors = parse("ke:\n  need: x\n  generate: {gemini: A woman.}\n  search: {pexels: []}\n")
    assert errors == ["ke/search/pexels: expected a query, or a list of queries",
                      "ke: size is needed to generate: set size, or preview templates to take it from"]
    _, errors = parse("ke:\n  need: x\n  generate: [gemini]\n  preview: {templates: photo-band/1080x1080}\n")
    assert errors == ["ke/preview: templates must be a list of <design>/<W>x<H>, e.g. photo-band/1080x1080",
                      "ke/preview: copy is required: the headline to preview candidates with",
                      "ke/generate: expected a map of provider -> prompt",
                      "ke: size is needed to generate: set size, or preview templates to take it from"]


def test_designs_and_defaults_are_reserved_and_a_brief_needs_a_need():
    assert brief.designs_dir({"ke": {}}, "/study") == (Path("/study/designs"), [])
    assert brief.designs_dir({"designs": "../library/designs"}, "/study") == (Path("/study/../library/designs"), [])
    assert brief.designs_dir({"designs": {"need": "x"}}, "/study")[1] == [
        "designs must be the path to the directory of designs (the name is reserved, so no need can use it)"]
    assert brief.designs_dir(["ke"], "/study")[1] == ["expected a map of need names to needs"]
    assert parse("designs: designs\n")[1] == ["no needs: name at least one need besides designs and defaults"]
    assert parse("defaults: [n]\nke: {need: x, search: {pexels: y}}\n")[1] == [
        "defaults must be a map of settings every need shares (the name is reserved, so no need can use it)"]


def test_the_estimate_prices_each_job_and_marks_what_has_no_published_price():
    jobs = jobs_of(BRIEF + "ke-firefly:\n  need: x\n  generate: {firefly: A farmer.}\n")
    costs = [brief.cost(j, PROVIDERS[j.provider]) for j in jobs]
    assert costs[:6] == pytest.approx([0, 0, 0, 2 * 0.101, 2 * 0.10, 4 * 0.067])
    assert costs[6] is None
    assert brief.spend_problems(jobs, costs, max_cost=2, allow_unpriced=True) == []
    assert brief.spend_problems(jobs, costs, max_cost=0.5, allow_unpriced=False) == [
        "the estimated cost, $0.67, is over --max-cost $0.50",
        "ke-firefly/firefly: image5 has no published price, so the estimate cannot include it; "
        "pass --allow-unpriced to run it anyway"]


def test_an_estimate_exactly_at_the_limit_is_allowed():
    jobs = [Job("ke", "gemini", "generate", "x", 3, 1080, 1080, model="gemini-3.1-flash-image", seed=1,
                options={"image_size": "1K"})]
    costs = [0.1 + 0.2]
    assert brief.spend_problems(jobs, costs, max_cost=0.3, allow_unpriced=False) == []


def test_requests_that_cannot_be_built_are_reported_once_before_anything_is_sent():
    jobs = jobs_of("ke:\n  need: x\n  size: 1200x628\n  search: {pexels: [a, b]}\n"
                   "  generate: {gemini: A woman., firefly: A woman., fal: A woman.}\n")
    assert brief.request_problems(jobs, PROVIDERS, {"GOOGLE_CLOUD_PROJECT": "p"}) == [
        "PEXELS_API_KEY is not set in the environment",
        "ke/gemini: 1200x628 is 300:157; Gemini generates 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9",
        "FIREFLY_SERVICES_CLIENT_ID is not set in the environment",
        "FAL_KEY is not set in the environment",
    ]
    env = {"PEXELS_API_KEY": "k", "GOOGLE_CLOUD_PROJECT": "p", "FAL_KEY": "k"}
    assert brief.request_problems(jobs_of(BRIEF), PROVIDERS, env) == []


def test_providers_narrows_the_jobs_and_names_what_it_does_not_know():
    jobs = jobs_of(BRIEF)
    chosen, errors = brief.select(jobs, ["pexels", "fal"], PROVIDERS)
    assert errors == [] and [(j.provider, j.kind) for j in chosen] == [("pexels", "search"), ("fal", "generate")]
    assert brief.select(jobs, None, PROVIDERS) == (jobs, [])
    assert brief.select(jobs, ["pexel"], PROVIDERS)[1] == [
        "--providers: unknown provider pexel (known: fal, firefly, gemini, openverse, pexels)"]
    assert brief.select(jobs, ["firefly"], PROVIDERS) == ([], ["--providers firefly: the brief asks none of them for "
                                                               "anything"])


def test_a_job_is_described_as_the_request_it_makes():
    search, *_, generation = jobs_of(BRIEF, seed=40)
    assert brief.describe(search) == {"need": "ke-older-woman", "provider": "pexels", "kind": "search",
                                      "query": "older african woman phone", "n": 2}
    assert brief.describe(generation) == {"need": "ma-older-man", "provider": "gemini", "kind": "generate",
                                          "model": "gemini-3.1-flash-image", "size": "1080x1080", "image_size": "1K",
                                          "seeds": [81, 82, 83, 84], "prompt": "A Moroccan man in his sixties. Plain background."}


def test_runs_are_numbered_from_one_each_day_and_never_reuse_a_number():
    today = datetime.date(2026, 9, 14)
    assert brief.run_name(today, []) == "2026-09-14-1"
    assert brief.run_name(today, ["2026-09-14-1", "2026-09-14-3", "2026-09-13-7", "notes", "2026-09-14-x"]) == (
        "2026-09-14-4")
