import numpy as np
import pytest

from ballyhoo.checks import (SlotImage, blank_failures, canvas_failures, contrast_ratio, drawn_scale, evaluate,
                             figure_mask, fit_failures, glyph_pixels, overlap_px, parse_css_color, slot_images,
                             swap_failures, upscale_failures, worst_contrast)
from ballyhoo.fit import Fit, Fragment, Rect, Settings

CREAM, TEAL, BLUE, BLACK = (238, 225, 208), (1, 59, 73), (0, 140, 187), (0, 0, 0)
NAVY = (0, 0, 160)
SETTINGS = Settings(start=79, min_size=56, max_lines=2)


def canvas(h, w, colour):
    return np.full((h, w, 3), colour, np.uint8)


def forced(notext, glyph_regions):
    """The render with its text forced black, and forced white."""
    black, white = notext.copy(), notext.copy()
    for r in glyph_regions:
        black[r], white[r] = BLACK, (255, 255, 255)
    return black, white


def test_contrast_ratio_matches_wcag_reference_values():
    assert contrast_ratio(BLACK, (255, 255, 255)) == pytest.approx(21)
    assert contrast_ratio((118, 118, 118), (255, 255, 255)) == pytest.approx(4.54, abs=0.01)  # #767676
    assert contrast_ratio((255, 255, 255), (118, 118, 118)) == contrast_ratio((118, 118, 118), (255, 255, 255))


def test_css_colours_come_from_the_browser_as_rgb_or_rgba():
    assert parse_css_color("rgb(0, 140, 187)") == (0, 140, 187)
    assert parse_css_color("rgba(217, 46, 46, 0.5)") == (217, 46, 46)
    with pytest.raises(ValueError, match="unsupported CSS colour"):
        parse_css_color("color(display-p3 1 0 0)")


def test_glyphs_are_where_black_and_white_text_differ_ignoring_faint_antialiasing():
    black, white = forced(canvas(10, 10, CREAM), [(0, 0)])
    black[0, 1], white[0, 1] = (220, 208, 192), (240, 228, 212)  # an edge pixel with ~8% coverage
    mask = glyph_pixels(black, white)
    assert mask[0, 0] and not mask[0, 1] and mask.sum() == 1


def test_text_nearly_the_colour_of_its_background_is_found_and_fails_contrast():
    # Comparing the render with and without its text misses this case: the glyphs
    # barely change the pixels, so the text looked absent and was never judged.
    notext = canvas(40, 100, CREAM)
    glyphs = (slice(10, 30), slice(5, 95))
    full = notext.copy()
    full[glyphs] = (225, 212, 196)  # 13 levels off the cream
    assert (np.abs(full.astype(int) - notext.astype(int)).max(axis=2) <= 48).all()
    mask = glyph_pixels(*forced(notext, [glyphs]))
    assert mask.sum() == 20 * 90
    fragment = Fragment(Rect(0, 0, 100, 40), "rgb(225, 212, 196)")
    assert worst_contrast([fragment], mask, notext) < 1.2


def test_contrast_is_judged_against_what_is_behind_the_glyphs_not_the_whole_line():
    # The line's rect spans cream and teal, but the glyphs sit only on the cream.
    notext = canvas(40, 100, CREAM)
    notext[:, 50:] = TEAL
    fragment = Fragment(Rect(0, 0, 100, 40), "rgb(0, 0, 0)")
    worst = worst_contrast([fragment], glyph_pixels(*forced(notext, [(slice(10, 30), slice(5, 45))])), notext)
    assert worst == pytest.approx(contrast_ratio(BLACK, CREAM))


def test_worst_contrast_is_the_weakest_fragment_and_ignores_ones_without_glyphs():
    notext = canvas(40, 300, CREAM)
    notext[:, 100:200] = TEAL
    glyphs = glyph_pixels(*forced(notext, [
        (slice(10, 30), slice(10, 90)),    # black on cream: strong
        (slice(10, 30), slice(110, 190)),  # blue drifting onto teal: weak
        (slice(20, 24), slice(250, 254)),  # a full stop: too few pixels to judge
    ]))
    fragments = [Fragment(Rect(0, 0, 100, 40), "rgb(0, 0, 0)"),
                 Fragment(Rect(100, 0, 100, 40), "rgb(0, 140, 187)"),
                 Fragment(Rect(200, 0, 100, 40), "rgb(237, 224, 207)")]
    worst = worst_contrast(fragments, glyphs, notext)
    assert worst == pytest.approx(contrast_ratio(BLUE, TEAL))
    assert worst_contrast([], glyphs, notext) is None


def test_figure_mask_drops_background_removal_specks_but_keeps_real_parts():
    alpha = np.zeros((300, 300), np.uint8)
    alpha[100:300, 100:300] = 255   # the figure
    alpha[10:20, 10:20] = 125       # a 100 px speck, like the one above man-scarf's head
    alpha[10:40, 200:220] = 255     # a 600 px detached part (a raised hand): real
    alpha[50:60, 10:60] = 30        # too faint to count at all
    mask = figure_mask(alpha)
    assert mask[200, 200] and mask[20, 210]
    assert not mask[15, 15] and not mask[55, 30]
    assert mask.sum() == 200 * 200 + 600


def test_collision_counts_figure_pixels_under_line_boxes_grown_by_the_margin():
    mask = np.zeros((100, 100), bool)
    mask[50:, 50:] = True
    line = Rect(0, 0, 48, 48)  # stops 2px short of the figure in both directions
    assert overlap_px([line], mask, margin=0) == 0
    assert overlap_px([line], mask, margin=4) == 4  # grown to 52x52: a 2x2 corner of the figure
    assert overlap_px([Rect(0, 0, 48, 48), Rect(60, 60, 10, 10)], mask, margin=0) == 100


def test_a_figure_pixel_between_two_lines_counts_once():
    mask = np.zeros((60, 100), bool)
    mask[20:30, :] = True  # the figure, between two lines whose margins overlap
    lines = [Rect(0, 0, 100, 24), Rect(0, 26, 100, 24)]
    assert overlap_px(lines, mask, margin=4) == 1000


def test_fit_failure_says_how_far_it_got_and_why():
    lines = tuple(Rect(0, i * 90, 900, 90) for i in range(3))
    assert fit_failures(Fit(False, 56, lines, (), True), SETTINGS) == [
        "does not fit at the 56px floor (template size 79px): 3 lines (max 2), overflows its box"]
    assert fit_failures(Fit(False, 56, lines, (), False), SETTINGS) == [
        "does not fit at the 56px floor (template size 79px): 3 lines (max 2)"]
    assert fit_failures(Fit(True, 70, lines[:2], (), False), SETTINGS) == []


def test_canvas_must_be_the_size_in_the_template_name_at_the_origin():
    assert canvas_failures((1080, 1080, 3), Rect(0, 0, 1080, 1080), (1080, 1080)) == []
    assert canvas_failures((1080, 1080, 3), Rect(8, 8, 1080, 1080), (1080, 1080)) == [
        "#canvas is 1080x1080 at 8,8; template name says 1080x1080"]  # body margin left in
    assert canvas_failures((1000, 1080, 3), Rect(0, 0, 1080, 1000), (1080, 1080)) != []


def test_a_blank_canvas_is_caught_through_compression_noise():
    rng = np.random.default_rng(0)
    noisy = (np.array((230, 216, 200)) + rng.integers(-3, 4, (100, 100, 3))).astype(np.uint8)
    assert blank_failures(noisy) == ["canvas is >99% one colour; a layer probably failed to load"]
    noisy[:10, :10] = TEAL  # 1% of something else
    assert blank_failures(noisy) == []


def placed(natural, box=(1080, 1080), object_fit="cover", src="file:///run/ke/originals/fake-1.jpg"):
    return SlotImage("scene", Rect(0, 0, *box), natural, object_fit, src)


@pytest.mark.parametrize("natural, box, object_fit, scale", [
    ((1600, 1200), (1080, 1080), "cover", (0.9, 0.9)),
    ((400, 400), (1080, 1080), "cover", (2.7, 2.7)),
    ((2000, 500), (1000, 1000), "cover", (2.0, 2.0)),    # a wide image in a square: its height decides
    ((2000, 500), (1000, 1000), "contain", (0.5, 0.5)),  # ...and contained, its width does
    ((600, 1000), (1000, 1000), "fill", (1000 / 600, 1.0)),
    ((400, 400), (1080, 1080), "none", (1.0, 1.0)),
    ((400, 400), (1080, 1080), "scale-down", (1.0, 1.0)),
    ((2000, 2000), (1000, 1000), "scale-down", (0.5, 0.5)),
])
def test_drawn_scale_follows_object_fit(natural, box, object_fit, scale):
    assert drawn_scale(placed(natural, box, object_fit)) == pytest.approx(scale)


def test_a_scene_fails_only_when_drawn_more_than_one_and_a_quarter_times_its_size():
    assert upscale_failures(placed((864, 864))) == []  # exactly 1.25x
    assert upscale_failures(placed((860, 860))) == [
        "#scene is upscaled 1.26x (max 1.25x): a 860x860 image in a 1080x1080 box with object-fit: cover"]
    assert upscale_failures(placed((400, 400))) == [
        "#scene is upscaled 2.70x (max 1.25x): a 400x400 image in a 1080x1080 box with object-fit: cover"]


def test_a_stretched_scene_fails_on_the_direction_it_is_stretched_in():
    assert upscale_failures(placed((600, 1000), (1000, 1000), "fill")) == [
        "#scene is upscaled 1.67x across and 1.00x down (max 1.25x): a 600x1000 image in a 1000x1000 box "
        "with object-fit: fill"]
    assert upscale_failures(placed((1000, 600), (1000, 1000), "contain")) == []


def test_an_unknown_object_fit_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="unsupported object-fit 'stretch'"):
        drawn_scale(placed((400, 400), object_fit="stretch"))


def test_a_slot_must_be_an_img():
    box = {"x": 0, "y": 0, "w": 1080, "h": 1080}
    images, errors = slot_images([
        {"slot": "scene", "tag": "img", "box": box, "naturalWidth": 1600, "naturalHeight": 1200,
         "objectFit": "cover", "src": "file:///a.jpg"}])
    assert (images, errors) == ([SlotImage("scene", Rect(0, 0, 1080, 1080), (1600, 1200), "cover", "file:///a.jpg")], [])
    assert slot_images([{"slot": "scene", "tag": "div", "box": box}]) == ([], ["#scene must be an <img>, not a <div>"])


def test_a_swapped_slot_must_show_the_image_put_into_it():
    image = placed((1600, 1200), src="file:///run/a.jpg")
    assert swap_failures([image], "scene", "file:///run/a.jpg") == []
    assert swap_failures([image], "scene", "file:///run/b.jpg") == [
        "#scene shows file:///run/a.jpg, not the image put into it (file:///run/b.jpg)"]


def scene(glyphs_on, text_colour, figure_at=None, text_rows=slice(10, 30)):
    """A 100x100 cream canvas with one line of 'text' and, optionally, a figure."""
    notext = canvas(100, 100, CREAM)
    notext[60:, :] = TEAL
    full = notext.copy()
    full[text_rows, glyphs_on] = text_colour
    alpha = None
    if figure_at is not None:
        alpha = np.zeros((100, 100), np.uint8)
        alpha[figure_at] = 255
    return (full, notext, *forced(notext, [(text_rows, glyphs_on)]), alpha)


def test_a_clean_creative_passes_with_a_summary():
    shots = scene(slice(10, 30), BLACK, figure_at=(slice(40, 100), slice(40, 100)))
    fit = Fit(True, 70, (Rect(5, 5, 30, 30),), (Fragment(Rect(5, 5, 30, 30), "rgb(0, 0, 0)"),), False)
    failures, summary = evaluate(fit, SETTINGS, Rect(0, 0, 100, 100), (100, 100), *shots)
    assert failures == []
    assert summary == f"70px, 1 lines, contrast {contrast_ratio(BLACK, CREAM):.1f}:1, text 4%"


def test_an_upscaled_scene_is_reported_with_the_other_checks_and_its_scale_summarised():
    shots = scene(slice(10, 30), BLACK)
    fit = Fit(True, 70, (Rect(5, 5, 30, 30),), (Fragment(Rect(5, 5, 30, 30), "rgb(0, 0, 0)"),), False)
    small = placed((40, 40), box=(100, 100))
    failures, summary = evaluate(fit, SETTINGS, Rect(0, 0, 100, 100), (100, 100), *shots, images=[small])
    assert failures == upscale_failures(small)
    assert summary.endswith(", scene 2.50x")


def test_every_failing_check_is_reported_not_just_the_first():
    # Too long, on the wrong canvas, a quarter of it text, navy on the teal hills
    # (1.1:1), and across the figure.
    shots = scene(slice(0, 100), NAVY, figure_at=(slice(70, 90), slice(0, 100)), text_rows=slice(65, 90))
    lines = (Rect(0, 0, 100, 20), Rect(0, 20, 100, 20), Rect(0, 60, 100, 35))
    fit = Fit(False, 56, lines, (Fragment(lines[2], "rgb(0, 0, 160)"),), True)
    failures, _ = evaluate(fit, SETTINGS, Rect(0, 0, 100, 90), (100, 100), *shots)
    assert [f.split(" ")[0] for f in failures] == ["does", "#canvas", "text", "contrast", "headline"]
    assert failures[2] == "text covers 25% of the canvas (max 20%)"
    assert failures[3].startswith("contrast 1.") and failures[3].endswith("is below 3:1")
    assert failures[4] == "headline overlaps #figure (2000 px)"
