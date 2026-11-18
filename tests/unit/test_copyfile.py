from pathlib import Path

import yaml

from ballyhoo.copyfile import designs_dir, design_names, markup, parse, select

TEMPLATES = {
    "cats-band": [Path("/lib/cats-band/1080x1080.html"), Path("/lib/cats-band/1080x1350.html"),
                  Path("/lib/cats-band/notes.html")],
    "dogs-band": [Path("/lib/dogs-band/1080x1080.html")],
}


def expand(text, templates=TEMPLATES, root=None):
    return parse(yaml.safe_load(text), templates, root)


def test_one_creative_per_variant_per_template_size():
    jobs, errors = expand('cats-band:\n  AR:\n    recarga: "Hola."\n    sin-monto: "Chau."\n')
    assert errors == []
    assert sorted(j.key for j in jobs) == [
        "cats-band/AR/recarga/1080x1080", "cats-band/AR/recarga/1080x1350",
        "cats-band/AR/sin-monto/1080x1080", "cats-band/AR/sin-monto/1080x1350",
    ]
    assert {j.out_name for j in jobs if j.variant == "recarga"} == {
        "cats-band_AR_recarga_1080x1080.png", "cats-band_AR_recarga_1080x1350.png"}
    assert {j.size for j in jobs} == {(1080, 1080), (1080, 1350)}


def test_variants_as_a_list_are_rejected_because_keys_would_depend_on_position():
    jobs, errors = expand('cats-band:\n  AR:\n    - "Hola."\n    - "Chau."\n')
    assert jobs == []
    assert errors == ["cats-band/AR: variants must be a named map, not a list"]


def test_adding_a_variant_first_leaves_existing_creatives_unchanged():
    before, _ = expand('cats-band:\n  AR:\n    recarga: "Hola."\n')
    after, _ = expand('cats-band:\n  AR:\n    nueva: "Nueva."\n    recarga: "Hola."\n')
    assert set(before) <= set(after)
    assert {j.variant for j in set(after) - set(before)} == {"nueva"}


def test_country_codes_must_be_strings_because_yaml_reads_NO_as_false():
    jobs, errors = expand('cats-band:\n  NO:\n    hei: "Hei."\n')
    assert jobs == []
    assert errors == ["cats-band/False: country must be a string (quote it; YAML reads NO as false)"]


def test_a_country_missing_from_a_design_is_skipped_not_borrowed():
    jobs, errors = expand('cats-band:\n  AR: {a: "Hola."}\n  HN: {a: "Hola, HN."}\ndogs-band:\n  AR: {a: "Hola."}\n')
    assert errors == []
    assert {(j.design, j.country) for j in jobs} == {("cats-band", "AR"), ("cats-band", "HN"), ("dogs-band", "AR")}


def test_every_problem_is_reported_and_valid_variants_still_expand():
    jobs, errors = expand(
        'cats-band:\n'
        '  AR:\n'
        '    Recarga: "Hola."\n'
        '    vacia: "   "\n'
        '    rota: "Una *recarga."\n'
        '    bien: "Una *recarga*."\n'
        'hamster-band:\n'
        '  AR: {bien: "Hola."}\n'
        'dogs-band: "not a map"\n',
        root=Path("/lib"))
    assert {j.variant for j in jobs} == {"bien"} and {j.design for j in jobs} == {"cats-band"}
    assert errors == [
        "cats-band/AR/Recarga: variant names are lowercase slugs",
        "cats-band/AR/vacia: text must be a non-empty string",
        "cats-band/AR/rota: unbalanced * in 'Una *recarga.'",
        "hamster-band: no <W>x<H>.html templates in /lib/hamster-band",
        "dogs-band: expected a map of country -> variants",
    ]


def test_yaml_aliases_share_one_block_of_copy_between_designs():
    jobs, errors = expand('cats-band: &copy\n  AR: {recarga: "  Hola.  "}\ndogs-band: *copy\n')
    assert errors == []
    assert {(j.design, j.text) for j in jobs} == {("cats-band", "Hola."), ("dogs-band", "Hola.")}


def test_the_designs_path_is_relative_to_the_copy_file_and_is_not_a_design():
    data = yaml.safe_load('designs: ../../library/designs\ncats-band:\n  AR: {a: "Hola."}\n')
    assert designs_dir(data, Path("/studies/lac/ads")) == (Path("/studies/lac/ads/../../library/designs"), [])
    assert design_names(data) == ["cats-band"]
    jobs, errors = parse(data, TEMPLATES)
    assert errors == [] and {j.design for j in jobs} == {"cats-band"}

    assert designs_dir({"cats-band": {}}, Path("/s")) == (Path("/s/designs"), [])
    assert designs_dir({"designs": 7}, Path("/s")) == (None, ["designs must be a path to the directory of designs"])
    assert designs_dir(["cats-band"], Path("/s"))[1] == ["expected a map of design -> country -> variant -> text"]


def test_select_narrows_by_design_country_variant_and_size():
    jobs, _ = expand('cats-band:\n  AR: {a: "x", b: "y"}\n  HN: {a: "z"}\ndogs-band:\n  AR: {a: "w"}\n')
    chosen = select(jobs, country="AR", variant="a", size="1080x1080")
    assert {j.key for j in chosen} == {"cats-band/AR/a/1080x1080", "dogs-band/AR/a/1080x1080"}
    assert select(jobs) == jobs


def test_markup_escapes_html_before_marking_emphasis():
    assert markup("Gana <b>*$3.000 & más*</b>") == "Gana &lt;b&gt;<em>$3.000 &amp; más</em>&lt;/b&gt;"


def test_markup_marks_each_emphasis_separately():
    assert markup("*Tu opinión cuenta.* Respondé *ya*.") == "<em>Tu opinión cuenta.</em> Respondé <em>ya</em>."


def test_a_variant_map_carries_fine_print_and_a_plain_string_carries_none():
    jobs, errors = expand('dogs-band:\n  MA:\n    con:\n      headline: "Hola."\n      fine_print: " Letra chica. "\n'
                          '    sin: "Hola."\n')
    assert errors == []
    assert {j.variant: (j.text, j.fine_print) for j in jobs} == {"con": ("Hola.", "Letra chica."), "sin": ("Hola.", None)}


def test_a_variant_map_needs_a_headline_and_takes_no_other_keys():
    jobs, errors = expand('dogs-band:\n  MA:\n    a:\n      fine_print: "Letra chica."\n'
                          '    b:\n      headline: "Hola."\n      small: "x"\n    c:\n      headline: "Hola."\n      fine_print: ""\n')
    assert jobs == []
    assert errors == ["dogs-band/MA/a: text must be a non-empty string",
                      "dogs-band/MA/b: unknown keys small: a variant map takes headline and fine_print",
                      "dogs-band/MA/c: fine_print must be a non-empty string"]
