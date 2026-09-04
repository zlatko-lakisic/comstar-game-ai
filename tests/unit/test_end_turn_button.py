from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.end_turn import (
    END_TURN_CLICK_CANDIDATES,
    localize_end_turn_button,
)


def _hud_with_horn(width=1920, height=1080, centre=(1882, 1050), radius=27):
    """Campaign map with the cream bottom HUD bar and the red End Turn horn disc."""
    image = Image.new("RGB", (width, height), (40, 90, 110))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, int(height * 0.965), width, height), fill=(228, 216, 186))
    cx, cy = centre
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(165, 35, 40))
    return image, draw


def test_locates_horn_button():
    image, _ = _hud_with_horn()
    located = localize_end_turn_button(image)
    assert located is not None
    assert abs(located[0] - 0.980) < 0.01
    assert abs(located[1] - 0.972) < 0.01


def test_no_button_on_clear_corner():
    image = Image.new("RGB", (1920, 1080), (40, 90, 110))
    assert localize_end_turn_button(image) is None


def test_red_rooftops_are_not_the_button():
    """Terracotta settlement roofs are red but never a disc filling the corner."""
    image = Image.new("RGB", (1920, 1080), (60, 110, 70))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1720, 1030, 1900, 1042), fill=(170, 45, 40))
    assert localize_end_turn_button(image) is None


def test_static_fallback_sits_on_the_button():
    """The hardcoded fallback must land inside the disc, not on the HUD bar beside it."""
    image, _ = _hud_with_horn()
    width, height = image.size
    for x_norm, y_norm in END_TURN_CLICK_CANDIDATES:
        px, py = int(width * x_norm), int(height * y_norm)
        assert image.getpixel((px, py)) == (165, 35, 40)
