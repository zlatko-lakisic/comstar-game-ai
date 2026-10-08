"""White-paper figure 7: the console readout with the cursor marked.

The base is the untouched frame
docs/figures/whitepaper-part1/fig07-console-readout/frame.png.
The ring is the cursor position recorded in that folder's manifest.
The leader ends on the console line box from the same manifest.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FRAME_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig07-console-readout" / "frame.png"
PNG_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig07-console-readout" / "fig07.png"
FONT_DIR = Path(__file__).resolve().parent / "fonts"

OUT_W = 2560
OUT_H = 1440
FRAME_W = 1280
FRAME_H = 720

# Cursor at the grab, from the figure 7 manifest.
CURSOR = (545, 516)
# The pos line is y=117 to 122 and its glyphs end at x=179.
# The help line under it runs to x=286, so a straight line from the cursor
# would cross that help line. The leader comes in to the right of the help
# line, then runs along the pos row to the glyphs.
LINE_END = (188, 120)
LINE_ELBOW = (300, 120)

TEAL = (0x0F, 0x52, 0x57, 255)
WHITE = (255, 255, 255, 255)
INK = (16, 20, 24, 255)
FONT_PX = 22
CIRCLE_R = 14
STROKE = 3
HALO = 1
LINE_W = 2

MIN_MARGIN = 48
CAPTION_GAP = 20

CAPTION = "Marker shows the cursor position. The capture does not include the cursor."


def find_font() -> tuple[Path, str]:
    """Prefer an installed Inter, otherwise the DejaVu Sans file beside this script."""
    names = (
        "Inter-Regular.otf",
        "Inter-Regular.ttf",
        "Inter.otf",
        "Inter.ttf",
    )
    windows = Path("C:/Windows/Fonts")
    local = Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
    folders = [windows, local]
    for folder in folders:
        if not folder.is_dir():
            continue
        for name in names:
            path = folder / name
            if path.is_file():
                return path, "Inter"
    bundled = FONT_DIR / "DejaVuSans.ttf"
    if bundled.is_file():
        return bundled, "DejaVu Sans"
    raise SystemExit(f"No Inter font, and {bundled} is missing")


def text_box(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, tuple[int, int, int, int]]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox


def choose_layout(font: ImageFont.FreeTypeFont) -> dict[str, float]:
    caption_h = text_box(font, CAPTION)[1]
    frame_h = OUT_H - 2 * MIN_MARGIN - CAPTION_GAP - caption_h
    frame_w = frame_h * 16 // 9
    max_w = OUT_W - 2 * MIN_MARGIN
    if frame_w > max_w:
        frame_w = max_w
        frame_h = frame_w * 9 // 16
    row_h = frame_h + CAPTION_GAP + caption_h
    return {
        "frame_w": frame_w,
        "frame_h": frame_h,
        "frame_x": (OUT_W - frame_w) / 2,
        "frame_y": (OUT_H - row_h) / 2,
        "caption_h": caption_h,
    }


def src_to_out(layout: dict[str, float], x: float, y: float) -> tuple[float, float]:
    return (
        layout["frame_x"] + x / FRAME_W * layout["frame_w"],
        layout["frame_y"] + y / FRAME_H * layout["frame_h"],
    )


def paint_mark(overlay: Image.Image, draw_shape) -> None:
    """Draw a mark with a 1 px white halo, matching fig_vlm_miss."""
    layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    draw_shape(ImageDraw.Draw(layer))
    hard = layer.getchannel("A").point(lambda a: 255 if a > 128 else 0)
    halo = Image.new("RGBA", overlay.size, (255, 255, 255, 0))
    halo.putalpha(hard.filter(ImageFilter.MaxFilter(3)))
    overlay.alpha_composite(halo)
    overlay.alpha_composite(layer)


def paint_ring(overlay: Image.Image, x: float, y: float) -> None:
    box = (x - CIRCLE_R, y - CIRCLE_R, x + CIRCLE_R, y + CIRCLE_R)

    def draw_shape(draw: ImageDraw.ImageDraw) -> None:
        draw.ellipse(box, outline=TEAL, width=STROKE)

    paint_mark(overlay, draw_shape)


def shorten(
    p0: tuple[float, float], p1: tuple[float, float], r1: float
) -> tuple[float, float]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= r1 + 1:
        raise SystemExit("Leader is shorter than the ring")
    ux, uy = dx / length, dy / length
    return (p1[0] - ux * r1, p1[1] - uy * r1)


def render(font: ImageFont.FreeTypeFont) -> Image.Image:
    layout = choose_layout(font)
    frame = Image.open(FRAME_PATH)
    if frame.size != (FRAME_W, FRAME_H):
        raise SystemExit(f"Base frame is {frame.size}, expected {FRAME_W}x{FRAME_H}")
    scaled = frame.resize(
        (int(layout["frame_w"]), int(layout["frame_h"])), Image.Resampling.LANCZOS
    )
    canvas = Image.new("RGBA", (OUT_W, OUT_H), WHITE)
    canvas.paste(scaled, (int(round(layout["frame_x"])), int(round(layout["frame_y"]))))

    cursor = src_to_out(layout, CURSOR[0], CURSOR[1])
    console = src_to_out(layout, LINE_END[0], LINE_END[1])
    elbow = src_to_out(layout, LINE_ELBOW[0], LINE_ELBOW[1])
    ring_r = CIRCLE_R + STROKE / 2 + HALO
    stop = shorten(elbow, cursor, ring_r)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.line([console, elbow, stop], fill=WHITE, width=LINE_W + 2)
    draw.line([console, elbow, stop], fill=TEAL, width=LINE_W)
    paint_ring(overlay, cursor[0], cursor[1])

    draw = ImageDraw.Draw(overlay)
    tw, _, bbox = text_box(font, CAPTION)
    caption_top = layout["frame_y"] + layout["frame_h"] + CAPTION_GAP
    center = layout["frame_x"] + layout["frame_w"] / 2
    draw.text((center - tw / 2 - bbox[0], caption_top - bbox[1]), CAPTION, font=font, fill=INK)

    framed = Image.alpha_composite(canvas, overlay).convert("RGB")
    if framed.size != (OUT_W, OUT_H):
        raise SystemExit(f"Output is {framed.size}")
    return framed


def main() -> None:
    font_path, family = find_font()
    font = ImageFont.truetype(str(font_path), FONT_PX)
    image = render(font)
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PNG_PATH, format="PNG")
    print(f"font {family} {font_path}")
    print(f"cursor {CURSOR[0]}, {CURSOR[1]}")
    print(f"console line end {LINE_END[0]}, {LINE_END[1]}")
    print(f"png {PNG_PATH} {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
