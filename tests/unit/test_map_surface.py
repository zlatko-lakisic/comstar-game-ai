"""Unit tests for Z3 map surface statistics."""

from __future__ import annotations

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.map_surface import (
    check_map_surface,
    measure_map_surface,
)


def _textured_map(size: tuple[int, int] = (640, 360)) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size)
    pix = [
        (
            40 + (x * 13 + y * 7) % 90,
            70 + (x * 3 + y * 11) % 100,
            35 + (x * 5 + y) % 70,
        )
        for y in range(h)
        for x in range(w)
    ]
    im.putdata(pix)
    return im


def _overlay_with_legends(size: tuple[int, int] = (640, 360)) -> Image.Image:
    """Remastered-like: translucent-ish map + parchment legends on both edges."""
    im = _textured_map(size)
    draw = ImageDraw.Draw(im)
    # Left settlements legend + right factions legend (warm parchment).
    draw.rectangle((4, 40, int(size[0] * 0.15), int(size[1] * 0.55)), fill=(220, 200, 160))
    draw.rectangle(
        (int(size[0] * 0.85), 70, size[0] - 4, int(size[1] * 0.70)),
        fill=(215, 195, 155),
    )
    return im


def test_textured_map_not_overlay():
    check = check_map_surface(_textured_map())
    assert not check.is_map_overlay
    assert check.stats.legend_warm_left < 0.12
    assert check.stats.legend_warm_right < 0.12


def test_legend_panels_flag_overlay():
    check = check_map_surface(_overlay_with_legends())
    assert check.is_map_overlay
    assert "legend" in check.detail
    assert check.stats.legend_warm_left >= 0.12
    assert check.stats.legend_warm_right >= 0.12


def test_live_fixture_frames_if_present():
    from pathlib import Path

    base = Path("data/runtime/zoom_surface_sweep/20260911-114746")
    three_d = base / "00_max_in.jpg"
    overlay = base / "56_wheel_out.jpg"
    if not three_d.is_file() or not overlay.is_file():
        return
    assert not check_map_surface(Image.open(three_d)).is_map_overlay
    ov = check_map_surface(Image.open(overlay))
    assert ov.is_map_overlay
    assert ov.stats.legend_warm_left > measure_map_surface(Image.open(three_d)).legend_warm_left
