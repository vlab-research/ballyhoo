import pytest

from ballyhoo.fit import (Fragment, Measurement, Rect, Settings, candidate_sizes, choose, group_lines, inside,
                          line_box, measurement_from_page, parse_settings)

BLACK = "rgb(0, 0, 0)"


def test_tight_line_height_is_measured_as_the_line_box_not_the_content_area():
    # Manrope ExtraBold at 79px reports a 108px-tall text rect; with line-height 1
    # it overhangs a 79px line by 14.5px above and below. The hills-man headline
    # failed to fit at any size until this was measured as the line box.
    content = Rect(36, 15.5, 500, 108)
    headline = Rect(36, 30, 600, 420)
    assert not inside([content], headline)
    assert line_box(content, 79) == Rect(36, 30, 500, 79)
    assert inside([line_box(content, 79)], headline)


def test_page_measurements_become_line_boxes_unless_line_height_is_normal():
    raw = {"size": 79, "box": {"x": 0, "y": 0, "w": 600, "h": 400}, "boxes": [],
           "fragments": [{"x": 0, "y": 15.5, "w": 300, "h": 108, "lineHeight": 79, "color": BLACK},
                         {"x": 0, "y": 200, "w": 300, "h": 108, "lineHeight": None, "color": BLACK}]}
    m = measurement_from_page(raw)
    assert [f.rect for f in m.fragments] == [Rect(0, 30, 300, 79), Rect(0, 200, 300, 108)]


def test_text_and_emphasis_on_one_line_are_one_line():
    # "corta con " + "L 90 de recarga" + "." are three text nodes on one line
    fragments = [Rect(48, 80, 300, 90), Rect(348, 80, 250, 90), Rect(598, 80, 20, 90)]
    assert group_lines(fragments) == [Rect(48, 80, 570, 90)]


def test_emphasis_that_wraps_counts_on_both_lines():
    fragments = [Rect(48, 80, 700, 90), Rect(748, 80, 200, 90), Rect(48, 170, 400, 90)]
    assert group_lines(fragments) == [Rect(48, 80, 900, 90), Rect(48, 170, 400, 90)]


def test_lines_are_told_apart_by_vertical_centre_not_top():
    taller_emphasis = [Rect(0, 100, 200, 80), Rect(200, 90, 200, 100)]  # same centre, different heights
    assert len(group_lines(taller_emphasis)) == 1
    next_line = [Rect(0, 100, 200, 80), Rect(0, 185, 200, 80)]
    assert len(group_lines(next_line)) == 2


def test_inside_allows_half_a_pixel_of_layout_rounding_and_nothing_more():
    box = Rect(0, 0, 100, 100)
    assert inside([Rect(-0.5, 0, 100.5, 100.5)], box)
    assert not inside([Rect(0, 0, 101, 100)], box)
    assert not inside([], box)


HEADLINE = Rect(48, 40, 1000, 260)


def measured(size, lines, width=900, boxes=()):
    lh = size * 1.14
    top = HEADLINE.y + (HEADLINE.h - lines * lh) / 2  # centred, as the band designs do
    fragments = tuple(Fragment(Rect(48, top + i * lh, width, lh), BLACK) for i in range(lines))
    return Measurement(size, fragments, tuple(boxes), HEADLINE)


def test_chooses_the_largest_size_that_fits_in_the_line_limit():
    fit = choose([measured(79, 3), measured(78, 3), measured(77, 2), measured(76, 2)], max_lines=2)
    assert fit.ok and fit.size == 77 and len(fit.lines) == 2 and not fit.overflows


def test_measurement_order_does_not_matter():
    shuffled = [measured(76, 2), measured(79, 3), measured(77, 2), measured(78, 3)]
    assert choose(shuffled, max_lines=2).size == 77


def test_a_headline_too_long_at_every_size_reports_the_floor():
    fit = choose([measured(79, 3), measured(56, 3, width=1200)], max_lines=2)
    assert not fit.ok and fit.size == 56 and len(fit.lines) == 3 and fit.overflows


def test_too_many_lines_fails_even_when_the_text_is_inside_the_box():
    fit = choose([measured(40, 5)], max_lines=4)
    assert not fit.ok and not fit.overflows


def test_per_line_boxes_must_fit_too():
    # kids-boxes: glyphs fit, but the yellow box's padding pokes past the headline
    poking = measured(80, 2, width=990, boxes=[Rect(38, 100, 1015, 100)])
    fits = measured(76, 2, width=940, boxes=[Rect(38, 100, 965, 100)])
    assert choose([poking, fits], max_lines=2).size == 76


def test_template_settings_with_defaults_and_candidate_sizes():
    settings, errors = parse_settings({"minSize": "56", "maxLines": "2"}, start=79)
    assert errors == []
    assert settings == Settings(start=79, min_size=56, max_lines=2, min_contrast=3.0, collide_margin=4.0)
    assert candidate_sizes(settings) == list(range(79, 55, -1))
    assert candidate_sizes(Settings(79.6, 55.5, 2)) == list(range(79, 55, -1))


def test_every_bad_setting_is_reported():
    settings, errors = parse_settings(
        {"minSize": "big", "maxLines": "2.5", "minContrast": "-1", "collideMargin": "0"}, start=79)
    assert settings is None
    assert errors == [
        "data-min-size='big' must be a positive number",
        "data-max-lines='2.5' must be a positive whole number",
        "data-min-contrast='-1' must be a positive number",
    ]


def test_missing_settings_and_a_template_size_below_its_floor_are_errors():
    assert parse_settings({}, start=79)[1] == ["#headline needs data-min-size", "#headline needs data-max-lines"]
    assert parse_settings({"minSize": "56", "maxLines": "2"}, start=40)[1] == [
        "#headline font-size 40px is below data-min-size 56"]


def test_choosing_from_nothing_is_a_programming_error():
    with pytest.raises(ValueError):
        choose([], max_lines=2)
