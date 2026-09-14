import pytest

from ballyhoo.providers import fal, firefly, gemini, openverse, pexels


def test_gemini_prices_each_image_by_model_and_resolution():
    assert gemini.image_price("gemini-3.1-flash-image", 1080, 1080, image_size="1K") == 0.067
    assert gemini.image_price("gemini-3.1-flash-image", 1080, 1350) == 0.101
    assert gemini.image_price("gemini-3-pro-image", 1080, 1080, image_size="4K") == 0.24
    assert gemini.image_price("gemini-9-image", 1080, 1080) is None


@pytest.mark.parametrize("model, width, height, usd", [
    ("fal-ai/flux-2-pro", 1024, 1024, 0.03),
    ("fal-ai/flux-2-pro", 512, 512, 0.03),
    ("fal-ai/flux-2-pro", 1080, 1080, 0.045),
    ("fal-ai/flux-2-pro", 1920, 1080, 0.045),
    ("fal-ai/flux-2-max", 1024, 1024, 0.07),
    ("fal-ai/flux-2-max", 1920, 1080, 0.10),
])
def test_fal_prices_by_megapixel_rounded_up_as_its_model_pages_show(model, width, height, usd):
    assert fal.image_price(model, width, height) == pytest.approx(usd)


def test_a_model_or_provider_with_no_published_price_is_unpriced_not_free():
    assert fal.image_price("fal-ai/flux-3", 1024, 1024) is None
    assert firefly.image_price("image5", 1080, 1080) is None


def test_stock_searches_are_free():
    assert pexels.search_price(200) == 0 and openverse.search_price(40) == 0
