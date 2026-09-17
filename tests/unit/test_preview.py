from ballyhoo.brief import Need
from ballyhoo.candidates import Candidate, Cutout
from ballyhoo.preview import Outcome, Preview, checks_data, plan, slot_for, slot_problems, slot_src, wanted

BAND, SIDE, FIGURES = "photo-band/1080x1080", "photo-side/1200x628", "figure-band/1080x1080"
COPY = "Take a short survey."
NO_SCENE = 'photo-side/1200x628: it has no #scene; a photo goes into an <img id="scene">'
NO_FIGURE = 'photo-side/1200x628: it has no #figure; a drawing goes into an <img id="figure">'
BAND_NO_FIGURE = 'photo-band/1080x1080: it has no #figure; a drawing goes into an <img id="figure">'
FIGURES_NO_SCENE = 'figure-band/1080x1080: it has no #scene; a photo goes into an <img id="scene">'


def need(name="ke-woman", templates=(BAND,)):
    return Need(name, "A woman.", {"fake": ("bright village",)}, {}, 2, None, None, tuple(templates), COPY)


def candidate(id_, full=None):
    full = full or f"originals/{id_}.jpg"
    return Candidate(id_, 1600, 1200, full, full, {"source": "stock"})


def drawing(id_):
    path = f"generated/{id_}.png"
    return Candidate(id_, 1080, 1080, path, path, {"source": "generated"},
                     cutout=Cutout(f"cutouts/{id_}.png", (9, 193, 18)))


def test_a_template_takes_a_candidate_only_in_an_img_with_that_slots_id():
    band = '<div id="canvas"><img id="scene" src="scene-placeholder.png"></div>'
    assert slot_problems(BAND, band, "scene") == []
    assert slot_src(band, "scene") == "scene-placeholder.png"
    assert slot_src("<img class=photo id=scene src=a.jpg />", "scene") == "a.jpg"
    assert slot_problems(SIDE, '<div id="canvas"><img id="photo" src="p.png"></div>', "scene") == [NO_SCENE]
    assert slot_problems(SIDE, '<!-- <img id="scene" src="p.png"> --><div id="canvas"></div>', "scene") == [NO_SCENE]
    assert slot_problems(SIDE, band, "figure") == [NO_FIGURE]
    assert slot_problems(BAND, '<div id="scene"></div>', "scene") == [
        'photo-band/1080x1080: its #scene is a <div>; a photo goes into an <img id="scene">']
    assert slot_src('<div id="scene"></div>', "scene") is None


def test_each_candidate_goes_into_each_of_its_needs_templates_named_by_id_design_and_size():
    generated = candidate("fal-e7cf824177a6", "generated/fal-e7cf824177a6.png")
    previews, errors = plan([need(templates=(BAND, SIDE))], {"ke-woman": [candidate("fake-bright-2"), generated]},
                            {(BAND, "scene"): [], (BAND, "figure"): [BAND_NO_FIGURE],
                             (SIDE, "scene"): [], (SIDE, "figure"): [NO_FIGURE]})
    assert errors == []
    assert [(p.candidate, p.template, p.image, p.file) for p in previews] == [
        ("fake-bright-2", BAND, "originals/fake-bright-2.jpg", "previews/fake-bright-2_photo-band_1080x1080.png"),
        ("fake-bright-2", SIDE, "originals/fake-bright-2.jpg", "previews/fake-bright-2_photo-side_1200x628.png"),
        ("fal-e7cf824177a6", BAND, "generated/fal-e7cf824177a6.png",
         "previews/fal-e7cf824177a6_photo-band_1080x1080.png"),
        ("fal-e7cf824177a6", SIDE, "generated/fal-e7cf824177a6.png",
         "previews/fal-e7cf824177a6_photo-side_1200x628.png"),
    ]
    assert {(p.need, p.slot, p.copy) for p in previews} == {("ke-woman", "scene", COPY)}


def test_a_drawing_previews_as_its_cut_out_in_the_figure_slot_and_a_photo_in_the_scene():
    needs = [need(templates=(BAND, FIGURES))]
    found = {"ke-woman": [candidate("fake-bright-2"), drawing("fake-3f9a0c1d")]}
    checked = {(BAND, "scene"): [], (BAND, "figure"): [BAND_NO_FIGURE],
               (FIGURES, "scene"): [FIGURES_NO_SCENE], (FIGURES, "figure"): []}
    assert wanted(needs, found) == list(checked)
    assert [slot_for(c) for c in found["ke-woman"]] == ["scene", "figure"]

    previews, errors = plan(needs, found, checked)
    assert errors == [], "a template that takes the other kind is passed over, not a mistake"
    assert [(p.candidate, p.template, p.slot, p.image, p.file) for p in previews] == [
        ("fake-bright-2", BAND, "scene", "originals/fake-bright-2.jpg",
         "previews/fake-bright-2_photo-band_1080x1080.png"),
        ("fake-3f9a0c1d", FIGURES, "figure", "cutouts/fake-3f9a0c1d.png",
         "previews/fake-3f9a0c1d_figure-band_1080x1080.png"),
    ]


def test_a_kind_none_of_a_needs_templates_takes_is_an_error_naming_what_they_lack():
    assert plan([need(templates=(BAND,))], {"ke-woman": [drawing("fake-3f9a0c1d")]},
                {(BAND, "scene"): [], (BAND, "figure"): [BAND_NO_FIGURE]}) == ([], [BAND_NO_FIGURE])


def test_a_need_with_no_candidates_is_left_out_and_every_problem_is_reported_together():
    needs = [need("ke-woman"), need("ma-man", templates=()), need("down"),
             need("ke-man", templates=(SIDE,)), need("ke-elder", templates=(SIDE,))]
    found = {"ke-woman": [candidate("fake-bright-2"), candidate("pexels-9", "https://images.pexels.com/9/original")],
             "ma-man": [candidate("fake-dark-2")], "ke-man": [candidate("fake-bright-3")],
             "ke-elder": [candidate("fake-bright-4")]}
    previews, errors = plan(needs, found, {(BAND, "scene"): [], (BAND, "figure"): [BAND_NO_FIGURE],
                                           (SIDE, "scene"): [NO_SCENE], (SIDE, "figure"): [NO_FIGURE]})
    assert errors == [
        "ke-woman/pexels-9: its image is not in the run, only at https://images.pexels.com/9/original",
        "ma-man: the brief names no preview templates for it",
        NO_SCENE,
    ]
    assert "down" not in {p.need for p in previews}


def test_previews_that_would_overwrite_each_other_are_an_error():
    a, b = "c/1080x1080", "b_c/1080x1080"
    _, errors = plan([need(templates=(a, b))], {"ke-woman": [candidate("fake-a_b"), candidate("fake-a")]},
                     {(a, "scene"): [], (a, "figure"): [f"{a}: no figure"],
                      (b, "scene"): [], (b, "figure"): [f"{b}: no figure"]})
    assert errors == ["ke-woman: two previews would both be previews/fake-a_b_c_1080x1080.png"]


def test_checks_record_each_preview_and_a_candidate_passes_only_when_all_its_previews_do():
    def preview(id_, template):
        return Preview("ke-woman", id_, f"originals/{id_}.jpg", template, "scene", COPY)

    outcomes = [
        Outcome(preview("fake-bright-2", BAND), (), "84px, 2 lines, contrast 5.6:1, text 3%, scene 0.90x"),
        Outcome(preview("fake-bright-2", SIDE), (), "60px, 2 lines, contrast 5.6:1, text 4%, scene 0.75x"),
        Outcome(preview("fake-dark-2", BAND), ("contrast 1.17:1 is below 3:1",), "84px, 2 lines, contrast 1.2:1"),
        Outcome(preview("fake-dark-2", SIDE), (), "60px, 2 lines, contrast 4.0:1, text 4%, scene 0.75x"),
        Outcome(preview("fake-gone-2", BAND), (), None, "Error: image failed to load: file:///run/fake-gone-2.jpg"),
    ]
    assert [o.status for o in outcomes] == ["pass", "pass", "fail", "pass", "error"]
    data = checks_data(need(templates=(BAND, SIDE)), outcomes, "abc123", "2026-09-14T10:00:00Z")
    assert data == {
        "copy": COPY, "templates": [BAND, SIDE], "previewed": "2026-09-14T10:00:00Z", "ballyhoo": "abc123",
        "summary": {"candidates": 3, "pass": 1, "fail": 2},
        "candidates": {
            "fake-bright-2": {"pass": True, "previews": {
                BAND: {"status": "pass", "file": "previews/fake-bright-2_photo-band_1080x1080.png",
                       "summary": "84px, 2 lines, contrast 5.6:1, text 3%, scene 0.90x"},
                SIDE: {"status": "pass", "file": "previews/fake-bright-2_photo-side_1200x628.png",
                       "summary": "60px, 2 lines, contrast 5.6:1, text 4%, scene 0.75x"}}},
            "fake-dark-2": {"pass": False, "previews": {
                BAND: {"status": "fail", "file": "previews/fake-dark-2_photo-band_1080x1080.png",
                       "summary": "84px, 2 lines, contrast 1.2:1", "failures": ["contrast 1.17:1 is below 3:1"]},
                SIDE: {"status": "pass", "file": "previews/fake-dark-2_photo-side_1200x628.png",
                       "summary": "60px, 2 lines, contrast 4.0:1, text 4%, scene 0.75x"}}},
            "fake-gone-2": {"pass": False, "previews": {
                BAND: {"status": "error",
                       "failures": ["Error: image failed to load: file:///run/fake-gone-2.jpg"]}}},
        },
    }
