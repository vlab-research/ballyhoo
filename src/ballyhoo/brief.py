"""The brief: what imagery a study needs, and the requests that source it.

Pure. The shell loads the YAML, finds which templates exist, and passes in the
provider registry and the environment. This module validates the brief, expands
it into source jobs (assembling a drawing's prompt from its style), estimates
their cost, checks that every request can be built before any is sent, and names
the run.

A generation that names a style is a drawing: its prompt is assembled rather
than written out, and it is cut out of its ground, so the ground the remover
needs is part of the prompt.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cutout import BACKGROUND
from .providers import MissingCredential

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SIZE = re.compile(r"^([1-9]\d*)x([1-9]\d*)$")
TEMPLATE = re.compile(r"^([^/]+)/([1-9]\d*)x([1-9]\d*)$")
DEFAULT_DESIGNS = "designs"
RESERVED = ("designs", "defaults", "styles")
SETTINGS = ("n", "size", "prompt_suffix", "preview")
NEED_KEYS = ("need", "search", "generate", *SETTINGS)
PREVIEW_KEYS = ("templates", "copy")
STYLE_KEYS = ("style", "guards", "framing")
GENERATE_KEYS = ("prompt", "style", "subject", "model", "seed")
SEARCH_KEYS = ("query",)
DEFAULT_N = 2
UNSENT_TOKEN = "unsent"  # stands in for a provider token when a request is built only to check it


@dataclass(frozen=True)
class Query:
    text: str
    options: dict = field(default_factory=dict)  # the provider's own search options, such as Pexels's orientation


@dataclass(frozen=True)
class Style:
    """How a drawing is drawn: the words that stay the same whoever the subject is."""
    name: str
    style: str             # the style itself, in the author's words
    guards: str | None     # what this style must not draw, such as a technical drawing's dimension lines
    framing: str | None    # how the figure sits in the frame


@dataclass(frozen=True)
class Need:
    name: str
    need: str             # what the image must show: what a person rates candidates against
    search: dict          # provider -> tuple of Query
    generate: dict        # provider -> {"prompt", "model", "seed", "options"}; model and seed may be None
    n: int
    size: tuple | None    # (width, height) to generate; None when the need only searches
    prompt_suffix: str | None
    templates: tuple      # preview templates, "<design>/<W>x<H>"
    copy: str | None      # the headline previews are rendered with


@dataclass(frozen=True)
class Job:
    need: str
    provider: str
    kind: str             # "search" or "generate"
    text: str             # the query, or the prompt as sent, suffix included
    n: int                # results for a search, images for a generation
    width: int | None = None
    height: int | None = None
    model: str | None = None
    seed: int | None = None  # the first seed: a generation's images use seed .. seed + n - 1
    options: dict = field(default_factory=dict)
    style: str | None = None  # the style a drawing is in; None when the prompt was written out

    @property
    def seeds(self):
        return list(range(self.seed, self.seed + self.n)) if self.kind == "generate" else []

    @property
    def drawing(self):
        """A generation in a style is a drawing, and a drawing is cut out of its ground."""
        return self.style is not None


def designs_dir(data, brief_dir):
    """Where a loaded brief's designs live, relative to the brief. Returns (path, errors)."""
    if not isinstance(data, dict):
        return None, ["expected a map of need names to needs"]
    designs = data.get("designs", DEFAULT_DESIGNS)
    if not isinstance(designs, str) or not designs.strip():
        return None, ["designs must be the path to the directory of designs (the name is reserved, so no need "
                      "can use it)"]
    return Path(brief_dir) / designs, []


def _unknown(where, raw, allowed):
    unknown = [k for k in raw if k not in allowed]
    if not unknown:
        return []
    return [f"{where}: unknown key{'s' if len(unknown) > 1 else ''} {', '.join(repr(k) for k in unknown)}"]


def _blank(value):
    return not isinstance(value, str) or not value.strip()


def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def _settings(where, raw, templates, root):
    """The settings present in a need or in defaults, validated. Returns (settings, errors)."""
    found, errors = {}, []
    if "n" in raw:
        if _whole(raw["n"], 1):
            found["n"] = raw["n"]
        else:
            errors.append(f"{where}: n must be a whole number of at least 1")
    if "size" in raw:
        m = SIZE.match(str(raw["size"])) if isinstance(raw["size"], str) else None
        if m:
            found["size"] = (int(m[1]), int(m[2]))
        else:
            errors.append(f"{where}: size must be <width>x<height>, e.g. 1080x1080")
    if "prompt_suffix" in raw:
        if _blank(raw["prompt_suffix"]):
            errors.append(f"{where}: prompt_suffix must be text")
        else:
            found["prompt_suffix"] = raw["prompt_suffix"].strip()
    if "preview" in raw:
        preview, problems = _preview(f"{where}/preview", raw["preview"], templates, root)
        errors += problems
        if not problems:
            found["preview"] = preview
    return found, errors


def _preview(where, raw, templates, root):
    if not isinstance(raw, dict):
        return None, [f"{where}: expected a map with templates and copy"]
    errors = _unknown(where, raw, PREVIEW_KEYS)
    names = raw.get("templates")
    if not isinstance(names, list) or not names or not all(isinstance(t, str) and TEMPLATE.match(t) for t in names):
        errors.append(f"{where}: templates must be a list of <design>/<W>x<H>, e.g. photo-band/1080x1080")
        names = []
    for name in names:
        if name not in templates:
            errors.append(f"{where}: template {name} does not exist"
                          + (f": expected {Path(root) / name}.html" if root else ""))
    if _blank(raw.get("copy")):
        errors.append(f"{where}: copy is required: the headline to preview candidates with")
    return (tuple(names), str(raw.get("copy", "")).strip()), errors


def _styles(raw):
    """The named styles drawings can be prompted in. Returns (styles by name, errors)."""
    if raw is None:
        return {}, []
    if not isinstance(raw, dict) or not raw:
        return {}, ["styles must be a map of style names to styles (the name is reserved, so no need can use it)"]
    found, errors = {}, []
    for name, spec in raw.items():
        where = f"styles/{name}"
        problems = [] if isinstance(name, str) and SLUG.match(name) else [f"{where}: style names are lowercase slugs"]
        if not isinstance(spec, dict):
            errors += problems + [f"{where}: expected a map with style, and optionally guards and framing"]
            continue
        problems += _unknown(where, spec, STYLE_KEYS)
        if _blank(spec.get("style")):
            problems.append(f"{where}: style is required: how the drawing is drawn, in the author's own words")
        problems += [f"{where}: {key} must be text" for key in ("guards", "framing")
                     if key in spec and _blank(spec[key])]
        errors += problems
        if not problems:
            found[name] = Style(name, spec["style"].strip(),
                                *((spec[k].strip() if k in spec else None) for k in ("guards", "framing")))
    return found, errors


def drawing_prompt(subject, style, constraints=None, background=BACKGROUND):
    """A drawing's prompt: what to draw, how, what not to draw, how it is framed, and what it stands on.

    `constraints` is the brief's prompt_suffix. `background` is the remover's, not the author's: the
    key needs a flat green ground, so the prompt that makes one belongs with the key (cutout.py).
    """
    parts = (subject, style.style, style.guards, style.framing, constraints, background)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _provider_problem(name, providers, method, verb):
    if name not in providers:
        return f"unknown provider (known: {', '.join(sorted(providers))})"
    if not hasattr(providers[name], method):
        return f"{name} cannot {verb}"
    return None


def _query(where, raw, provider, options):
    """One search: a query, or a map with the query and the provider's own search options."""
    if not isinstance(raw, dict):
        if _blank(raw):
            return None, [f"{where}: expected a query, or a map with query and {provider}'s search options"]
        return Query(raw.strip()), []
    accepted = SEARCH_KEYS + tuple(options)
    unknown = [k for k in raw if k not in accepted]
    problems = [f"{where}: unknown option{'s' if len(unknown) > 1 else ''} {', '.join(repr(k) for k in unknown)}; "
                f"{provider} searches take {', '.join(accepted)}"] if unknown else []
    if _blank(raw.get("query")):
        problems.append(f"{where}: query is required")
    if problems:
        return None, problems
    return Query(raw["query"].strip(), {k: raw[k] for k in options if k in raw}), []


def _search(where, raw, providers):
    if not isinstance(raw, dict) or not raw:
        return {}, [f"{where}: expected a map of provider -> query, or list of queries"]
    found, errors = {}, []
    for provider, queries in raw.items():
        label = f"{where}/{provider}"
        problem = _provider_problem(provider, providers, "search_request", "search")
        if problem:
            errors.append(f"{label}: {problem}")
        queries = [queries] if isinstance(queries, (str, dict)) else queries
        if not isinstance(queries, list) or not queries:
            errors.append(f"{label}: expected a query, or a list of queries")
            continue
        options = getattr(providers.get(provider), "SEARCH_OPTIONS", ())
        parsed, problems = [], []
        for i, raw_query in enumerate(queries, 1):
            query, more = _query(f"{label} query {i}", raw_query, provider, options)
            problems += more
            if query:
                parsed.append(query)
        errors += problems
        if not problem and not problems:
            found[provider] = tuple(parsed)
    return found, errors


def _drawing(label, spec, styles):
    """The style a generation draws in, with what stops it. Returns (Style or None, problems)."""
    if "style" not in spec:
        if "subject" in spec:
            return None, [f"{label}: subject needs a style; without one, write the whole prompt"]
        return None, [] if not _blank(spec.get("prompt")) else [f"{label}: prompt is required"]
    known = ", ".join(sorted(styles)) or "none: name them under styles"
    problems = [] if spec["style"] in styles else [f"{label}: unknown style {spec['style']!r} (known: {known})"]
    if "prompt" in spec:
        problems.append(f"{label}: a style draws a subject, so write subject, not prompt")
    if _blank(spec.get("subject")):
        problems.append(f"{label}: subject is required with a style: the line saying who or what to draw")
    return styles.get(spec["style"]), problems


def _generate(where, raw, providers, styles):
    if not isinstance(raw, dict) or not raw:
        return {}, [f"{where}: expected a map of provider -> prompt"]
    found, errors = {}, []
    for provider, spec in raw.items():
        label = f"{where}/{provider}"
        problem = _provider_problem(provider, providers, "generate_request", "generate")
        problems = [f"{label}: {problem}"] if problem else []
        spec = {"prompt": spec} if isinstance(spec, str) else spec
        if not isinstance(spec, dict):
            errors += problems + [f"{label}: expected a prompt, or a map with prompt and options"]
            continue
        options = getattr(providers.get(provider), "OPTIONS", ())
        if not problem:
            problems += _unknown(label, spec, GENERATE_KEYS + tuple(options))
        style, more = _drawing(label, spec, styles)
        problems += more
        if "model" in spec and _blank(spec["model"]):
            problems.append(f"{label}: model must be a model name")
        if "seed" in spec and not _whole(spec["seed"], 0):
            problems.append(f"{label}: seed must be a whole number")
        errors += problems
        if not problems:
            found[provider] = {"prompt": None if style else spec["prompt"].strip(),
                               "subject": spec["subject"].strip() if style else None, "style": style,
                               "model": spec.get("model"), "seed": spec.get("seed"),
                               "options": {k: spec[k] for k in options if k in spec}}
    return found, errors


def _need(name, raw, base, templates, providers, styles, root):
    where = str(name)
    errors = [] if isinstance(name, str) and SLUG.match(name) else [f"{where}: need names are lowercase slugs"]
    if not isinstance(raw, dict):
        return None, errors + [f"{where}: expected a map with need, and search or generate"]
    errors += _unknown(where, raw, NEED_KEYS)
    if _blank(raw.get("need")):
        errors.append(f"{where}: need is required: say what the image must show")
    if "search" not in raw and "generate" not in raw:
        errors.append(f"{where}: needs search or generate, or both")
    own, problems = _settings(where, raw, templates, root)
    errors += problems
    settings = {**base, **own}
    search, problems = _search(f"{where}/search", raw["search"], providers) if "search" in raw else ({}, [])
    errors += problems
    generate, problems = _generate(f"{where}/generate", raw["generate"], providers, styles) \
        if "generate" in raw else ({}, [])
    errors += problems
    templates_, copy = settings.get("preview", ((), None))
    size = settings.get("size") or (tuple(int(g) for g in TEMPLATE.match(templates_[0]).groups()[1:])
                                    if templates_ else None)
    if "generate" in raw and size is None and "size" not in raw:
        errors.append(f"{where}: size is needed to generate: set size, or preview templates to take it from")
    if errors:
        return None, errors
    return Need(where, raw["need"].strip(), search, generate, settings.get("n", DEFAULT_N),
                size if generate else None, settings.get("prompt_suffix"), templates_, copy), []


def parse(data, templates, providers, root=None):
    """Validate a loaded brief. Returns (needs, errors).

    `templates` holds the templates that exist, as "<design>/<W>x<H>"; `providers` maps each
    provider's name to its module; `root` is the designs directory, for messages. Every mistake is
    reported, and a need with one is left out while the others still parse.
    """
    if not isinstance(data, dict):
        return [], ["expected a map of need names to needs"]
    styles, errors = _styles(data.get("styles"))
    defaults = data.get("defaults", {})
    if isinstance(defaults, dict):
        errors += [e + (" (the name is reserved, so no need can use it)"
                        if {"need", "search", "generate"} & set(defaults) else "")
                   for e in _unknown("defaults", defaults, SETTINGS)]
        base, problems = _settings("defaults", defaults, templates, root)
        errors += problems
    else:
        errors.append("defaults must be a map of settings every need shares (the name is reserved, so no need "
                      "can use it)")
        base = {}
    names = [name for name in data if name not in RESERVED]
    if not names:
        errors.append(f"no needs: name at least one need besides {', '.join(RESERVED[:-1])} and {RESERVED[-1]}")
    needs = []
    for name in names:
        need, problems = _need(name, data[name], base, templates, providers, styles, root)
        errors += problems
        if need:
            needs.append(need)
    return needs, errors


def expand(needs, providers, seed):
    """The source jobs, in brief order: each need's searches, then its generations.

    `seed` is the first seed of every generation whose brief sets none; the shell draws it.
    """
    jobs = []
    for need in needs:
        for provider, queries in need.search.items():
            jobs += [Job(need.name, provider, "search", q.text, need.n, options=dict(q.options)) for q in queries]
        for provider, spec in need.generate.items():
            style = spec["style"]
            prompt = drawing_prompt(spec["subject"], style, need.prompt_suffix) if style else \
                (f"{spec['prompt']} {need.prompt_suffix}" if need.prompt_suffix else spec["prompt"])
            jobs.append(Job(need.name, provider, "generate", prompt, need.n, *need.size,
                            model=spec["model"] or providers[provider].MODEL,
                            seed=seed if spec["seed"] is None else spec["seed"], options=spec["options"],
                            style=style.name if style else None))
    return jobs


def select(jobs, names, providers):
    """The jobs for the providers named with --providers (all of them when None). Returns (jobs, errors)."""
    if names is None:
        return jobs, []
    errors = [f"--providers: unknown provider {n} (known: {', '.join(sorted(providers))})"
              for n in names if n not in providers]
    chosen = [j for j in jobs if j.provider in names]
    if not errors and not chosen:
        errors.append(f"--providers {','.join(names)}: the brief asks none of them for anything")
    return chosen, errors


def cost(job, provider):
    """Estimated USD for a job, or None when the provider has no published price for it."""
    if job.kind == "search":
        return provider.search_price(job.n)
    unit = provider.image_price(job.model, job.width, job.height, **job.options)
    return None if unit is None else unit * job.n


def spend_problems(jobs, costs, max_cost, allow_unpriced):
    """Why the jobs must not run: an estimate over the limit, or a price nobody publishes."""
    total = round(sum(c for c in costs if c is not None), 6)
    errors = []
    if total > max_cost:
        errors.append(f"the estimated cost, ${total:.2f}, is over --max-cost ${max_cost:.2f}")
    if not allow_unpriced:
        errors += [f"{j.need}/{j.provider}: {j.model} has no published price, so the estimate cannot include it; "
                   "pass --allow-unpriced to run it anyway" for j, c in zip(jobs, costs) if c is None]
    return errors


def request_problems(jobs, providers, env):
    """What would stop a job's requests being built: a missing credential, or an option the provider refuses.

    Building a request sends nothing, so this can run before anything is spent. A problem many
    jobs share is reported once.
    """
    found = []
    for job in jobs:
        provider = providers[job.provider]
        try:
            if job.kind == "search":
                provider.search_request(job.text, 1, job.n, env, **job.options)
            else:
                if hasattr(provider, "token_request"):
                    provider.token_request(env)
                provider.generate_request(job.text, job.seed, job.width, job.height, env, UNSENT_TOKEN,
                                          model=job.model, **job.options)
        except MissingCredential as e:
            message = str(e)
        except ValueError as e:
            message = f"{job.need}/{job.provider}: {e}"
        else:
            continue
        if message not in found:
            found.append(message)
    return found


def describe(job):
    """A job as data: what --plan prints and the manifest records."""
    if job.kind == "search":
        return {"need": job.need, "provider": job.provider, "kind": job.kind, "query": job.text, "n": job.n,
                **job.options}
    return {"need": job.need, "provider": job.provider, "kind": job.kind, "model": job.model,
            **({"style": job.style} if job.style else {}), "size": f"{job.width}x{job.height}", **job.options,
            "seeds": job.seeds, "prompt": job.text}


def run_name(today, existing):
    """`<date>-<n>`: n is one more than the highest n already used that day, so a run is never reused."""
    prefix = f"{today.isoformat()}-"
    used = [int(name[len(prefix):]) for name in existing
            if name.startswith(prefix) and name[len(prefix):].isdigit()]
    return f"{prefix}{max(used, default=0) + 1}"
