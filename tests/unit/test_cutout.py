"""The chroma key and the mask check, on images drawn here: no model, no service, no browser."""
import numpy as np

from ballyhoo.cutout import cut_out, key_colour, mask_problems

GREEN = (10, 200, 20)
SKIN = (222, 176, 140)
SHIRT = (0, 80, 30)     # a green the drawing itself is made of, far enough from the key to survive it
W = H = 240
BODY = (slice(60, 200), slice(80, 160))  # 11200 px of 57600: 19% of the image
INSIDE = (slice(70, 190), slice(90, 150))  # the body away from its edge, which despill reaches


def ground(colour=GREEN):
    return np.full((H, W, 3), colour, np.uint8)


def figure(colour=SKIN, ground_colour=GREEN):
    image = ground(ground_colour)
    image[BODY] = colour
    return image


def opaque(image):
    """The image as RGBA with nothing cut out: what a model returns when it is asked for transparency."""
    return np.dstack([image, np.full(image.shape[:2], 255, np.uint8)])


def test_a_clean_figure_on_green_keys_out_to_the_figure_alone():
    image, key = cut_out(figure())
    assert key == GREEN
    alpha = image[..., 3]
    assert (alpha[BODY] == 255).all()
    assert alpha[0, 0] == 0 and alpha[H - 1, W - 1] == 0
    assert round(float((alpha == 0).mean()), 2) == 0.81
    assert mask_problems(image, key) == []


def test_the_key_colour_is_read_from_the_border_so_a_figure_in_the_middle_does_not_move_it():
    assert key_colour(figure()) == GREEN
    assert key_colour(figure(ground_colour=(9, 193, 18))) == (9, 193, 18)
    assert key_colour(figure(ground_colour=(8, 251, 5))) == (8, 251, 5)


def test_green_blended_into_the_edges_is_taken_out_and_the_rest_despilled():
    spilled = figure()
    half = tuple((a + b) // 2 for a, b in zip(GREEN, SKIN))
    spilled[58:202, 78:162] = half  # a two-pixel ring of half key, half drawing, around the body
    spilled[BODY] = SKIN

    image, key = cut_out(spilled)
    ring = image[59, 79]
    assert ring[3] == 255, "half the key away is the drawing, not the ground"
    assert ring[1] <= (int(ring[0]) + int(ring[2])) / 2, "the ring is no longer green"
    assert mask_problems(image, key) == []
    assert mask_problems(opaque(spilled), key) != [], "the same image uncut is not a cut-out"


def test_specks_the_key_left_behind_are_reported_with_the_largest():
    speckled = figure()
    speckled[10:20, 10:30] = SKIN   # 200 px
    speckled[220:225, 200:210] = SKIN  # 50 px
    image, key = cut_out(speckled)
    assert mask_problems(image, key) == [
        "2 stray specks in the mask (largest 200 px, under 500 px is a speck): ground the key left behind"]


def test_an_image_with_nothing_cut_out_of_it_fails():
    assert mask_problems(opaque(figure()), GREEN) == [
        "0% of the image is transparent (expected 5% to 95%)",
        "80.56% of the figure is still the key's green (max 0.30%)",
        "100% of the figure's edge is still the key's green (max 2%)",
        "the mask and a plain colour key agree on 19% of the figure (min 90%)",
    ]


def test_a_cut_out_that_kept_almost_nothing_fails():
    nearly_empty = ground()
    nearly_empty[100:110, 100:140] = SKIN
    image, key = cut_out(nearly_empty)
    assert mask_problems(image, key) == ["99% of the image is transparent (expected 5% to 95%)",
                                         "1 stray speck in the mask (largest 400 px, under 500 px is a speck): "
                                         "ground the key left behind"]


def test_a_drawing_on_anything_but_green_is_reported_rather_than_keyed_silently():
    image, key = cut_out(figure(colour=(40, 40, 60), ground_colour=(240, 240, 235)))
    assert key == (240, 240, 235)
    assert mask_problems(image, key)[0] == ("the ground is (240, 240, 235), not chroma-key green: "
                                            "the drawing was not generated on green")


def test_green_in_the_drawing_itself_is_kept_and_reported_for_a_person_to_judge():
    image, key = cut_out(figure(colour=SHIRT))
    assert (image[INSIDE][..., :3] == SHIRT).all(), "a green the key cannot reach is the artist's, not spill"
    [painted] = mask_problems(image, key)
    assert painted.endswith("of the figure is green light painted on to it (max 0.15%): no remover takes that out")
