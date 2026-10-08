"""White-paper figure 8: screen points and the map positions the game reported.

The base is the untouched frame
docs/figures/whitepaper-part1/fig08-probe-grid/background_after.png.
Probes 07, 08, and 11 are left out. No line is fitted.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FRAME_PATH = (
    ROOT / "docs" / "figures" / "whitepaper-part1" / "fig08-probe-grid" / "background_after.png"
)
CSV_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig08-probe-grid" / "probes.csv"
PNG_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig08-probe-grid" / "fig08.png"
FONT_DIR = Path(__file__).resolve().parent / "fonts"

OUT_W = 2560
OUT_H = 1440
FRAME_W = 1280
FRAME_H = 720

KEEP = ("01", "02", "03", "04", "05", "06", "09", "10", "12")
EXCLUDED = ("07", "08", "11")
COLS = (200, 600, 1000)
ROWS = (239, 419, 579)

TEAL = (0x0F, 0x52, 0x57, 255)
WHITE = (255, 255, 255, 255)
INK = (16, 20, 24, 255)
PILL = (16, 20, 24, 210)
FONT_PX = 22
LABEL_PX = 16
CIRCLE_R = 14
STROKE = 3
HALO = 1
DOT_R = 8
LINE_W = 2
PAD_X = 8
PAD_Y = 4
LABEL_GAP = 8

MIN_MARGIN = 48
CAPTION_GAP = 20

CAPTION = "Each point pairs a screen position with the map position the game reported."

# Incoming grid lines run through the dot, so the label sits off those lines.
LABEL_SIDES = {
    "01": ("above", "right", "left", "below"),
    "02": ("above", "right", "left", "below"),
    "03": ("above", "left", "right", "below"),
    "04": ("above", "right", "below", "left"),
    "05": ("above", "right", "left", "below"),
    "06": ("left", "above", "right", "below"),
    "09": ("left", "above", "below", "right"),
    "10": ("right", "below", "above", "left"),
    "12": ("below", "right", "left", "above"),
}


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


def load_probes() -> list[dict]:
    rows = []
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        for item in csv.DictReader(handle):
            probe_id = item["probe_id"]
            if probe_id in EXCLUDED:
                continue
            if probe_id not in KEEP:
                raise SystemExit(f"Unexpected probe {probe_id}")
            rows.append(
                {
                    "id": probe_id,
                    "role": item["role"],
                    "pixel_x": int(item["pixel_x"]),
                    "pixel_y": int(item["pixel_y"]),
                    "map_x": int(item["map_x"]),
                    "map_y": int(item["map_y"]),
                    "label": f"{int(item['map_x'])}, {int(item['map_y'])}",
                }
            )
    found = [row["id"] for row in rows]
    if found != list(KEEP):
        raise SystemExit(f"Probe order is {found}, expected {list(KEEP)}")
    return rows


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


def paint_dot(overlay: Image.Image, x: float, y: float) -> None:
    box = (x - DOT_R, y - DOT_R, x + DOT_R, y + DOT_R)

    def draw_shape(draw: ImageDraw.ImageDraw) -> None:
        draw.ellipse(box, fill=TEAL)

    paint_mark(overlay, draw_shape)


def shorten(
    p0: tuple[float, float], p1: tuple[float, float], r0: float, r1: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= r0 + r1 + 1:
        return None
    ux, uy = dx / length, dy / length
    return (p0[0] + ux * r0, p0[1] + uy * r0), (p1[0] - ux * r1, p1[1] - uy * r1)


def grid_segments(rows: list[dict]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    by_pos = {(row["pixel_x"], row["pixel_y"]): row for row in rows if row["role"] == "grid"}
    dot_r = DOT_R + HALO
    segments = []
    for y in ROWS:
        for left, right in zip(COLS, COLS[1:]):
            a = by_pos.get((left, y))
            b = by_pos.get((right, y))
            if a is None or b is None:
                continue
            segment = shorten(a["out"], b["out"], dot_r, dot_r)
            if segment is not None:
                segments.append(segment)
    for x in COLS:
        for top, bottom in zip(ROWS, ROWS[1:]):
            a = by_pos.get((x, top))
            b = by_pos.get((x, bottom))
            if a is None or b is None:
                continue
            segment = shorten(a["out"], b["out"], dot_r, dot_r)
            if segment is not None:
                segments.append(segment)
    return segments


def rects_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float], gap: float = 4
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + gap <= bx0 or bx1 + gap <= ax0 or ay1 + gap <= by0 or by1 + gap <= ay0)


def hits_disk(rect: tuple[float, float, float, float], cx: float, cy: float, radius: float) -> bool:
    x0, y0, x1, y1 = rect
    nx = min(max(cx, x0), x1)
    ny = min(max(cy, y0), y1)
    return math.hypot(nx - cx, ny - cy) < radius


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(
    p0: tuple[float, float],
    p1: tuple[float, float],
    q0: tuple[float, float],
    q1: tuple[float, float],
) -> bool:
    o1, o2 = _orient(p0, p1, q0), _orient(p0, p1, q1)
    o3, o4 = _orient(q0, q1, p0), _orient(q0, q1, p1)
    return o1 * o2 < 0 and o3 * o4 < 0


def segment_hits_rect(
    p0: tuple[float, float], p1: tuple[float, float], rect: tuple[float, float, float, float]
) -> bool:
    x0, y0, x1, y1 = rect
    if x0 <= p0[0] <= x1 and y0 <= p0[1] <= y1:
        return True
    if x0 <= p1[0] <= x1 and y0 <= p1[1] <= y1:
        return True
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    edges = (
        (corners[0], corners[1]),
        (corners[1], corners[2]),
        (corners[2], corners[3]),
        (corners[3], corners[0]),
    )
    return any(segments_intersect(p0, p1, a, b) for a, b in edges)


def place_label(side: str, cx: float, cy: float, width: int, height: int, radius: float) -> tuple[float, float]:
    gap = radius + LABEL_GAP
    if side == "above":
        return cx - width / 2, cy - gap - height
    if side == "below":
        return cx - width / 2, cy + gap
    if side == "left":
        return cx - gap - width, cy - height / 2
    if side == "right":
        return cx + gap, cy - height / 2
    raise SystemExit(f"Unknown label side {side}")


def layout_labels(
    font: ImageFont.FreeTypeFont,
    layout: dict[str, float],
    rows: list[dict],
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> None:
    frame = (
        layout["frame_x"] + 8,
        layout["frame_y"] + 8,
        layout["frame_x"] + layout["frame_w"] - 8,
        layout["frame_y"] + layout["frame_h"] - 8,
    )
    placed: list[tuple[float, float, float, float]] = []
    for row in rows:
        tw, th, bbox = text_box(font, row["label"])
        pw, ph = tw + PAD_X * 2, th + PAD_Y * 2
        cx, cy = row["out"]
        radius = CIRCLE_R + STROKE / 2 + HALO if row["role"] == "held_out" else DOT_R + HALO
        found = None
        for side in LABEL_SIDES[row["id"]]:
            x, y = place_label(side, cx, cy, pw, ph, radius)
            rect = (x, y, x + pw, y + ph)
            if rect[0] < frame[0] or rect[1] < frame[1] or rect[2] > frame[2] or rect[3] > frame[3]:
                continue
            if any(rects_overlap(rect, other, 6) for other in placed):
                continue
            if any(hits_disk(rect, other["out"][0], other["out"][1], radius) for other in rows):
                continue
            if any(segment_hits_rect(a, b, rect) for a, b in segments):
                continue
            found = (side, rect, bbox)
            break
        if found is None:
            raise SystemExit(f"No clear place for probe {row['id']}")
        side, rect, bbox = found
        placed.append(rect)
        row["side"] = side
        row["pill"] = rect
        row["bbox"] = bbox


def render(font: ImageFont.FreeTypeFont, label_font: ImageFont.FreeTypeFont, rows: list[dict]) -> Image.Image:
    layout = choose_layout(font)
    frame = Image.open(FRAME_PATH)
    if frame.size != (FRAME_W, FRAME_H):
        raise SystemExit(f"Base frame is {frame.size}, expected {FRAME_W}x{FRAME_H}")
    scaled = frame.resize(
        (int(layout["frame_w"]), int(layout["frame_h"])), Image.Resampling.LANCZOS
    )
    canvas = Image.new("RGBA", (OUT_W, OUT_H), WHITE)
    canvas.paste(scaled, (int(round(layout["frame_x"])), int(round(layout["frame_y"]))))

    for row in rows:
        row["out"] = src_to_out(layout, row["pixel_x"], row["pixel_y"])
    segments = grid_segments(rows)
    layout_labels(label_font, layout, rows, segments)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for segment in segments:
        draw.line(segment, fill=WHITE, width=LINE_W + 2)
    for segment in segments:
        draw.line(segment, fill=TEAL, width=LINE_W)
    for row in rows:
        if row["role"] == "grid":
            paint_dot(overlay, row["out"][0], row["out"][1])
        elif row["role"] == "held_out":
            paint_ring(overlay, row["out"][0], row["out"][1])
        else:
            raise SystemExit(f"Unknown role {row['role']}")

    draw = ImageDraw.Draw(overlay)
    for row in rows:
        x0, y0, x1, y1 = row["pill"]
        bbox = row["bbox"]
        draw.rounded_rectangle((x0, y0, x1, y1), radius=(y1 - y0) / 2, fill=PILL)
        draw.text(
            (x0 + PAD_X - bbox[0], y0 + PAD_Y - bbox[1]),
            row["label"],
            font=label_font,
            fill=WHITE,
        )
    tw, _, bbox = text_box(font, CAPTION)
    caption_top = layout["frame_y"] + layout["frame_h"] + CAPTION_GAP
    center = layout["frame_x"] + layout["frame_w"] / 2
    draw.text((center - tw / 2 - bbox[0], caption_top - bbox[1]), CAPTION, font=font, fill=INK)

    framed = Image.alpha_composite(canvas, overlay).convert("RGB")
    if framed.size != (OUT_W, OUT_H):
        raise SystemExit(f"Output is {framed.size}")
    return framed


def main() -> None:
    rows = load_probes()
    font_path, family = find_font()
    font = ImageFont.truetype(str(font_path), FONT_PX)
    label_font = ImageFont.truetype(str(font_path), LABEL_PX)
    image = render(font, label_font, rows)
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PNG_PATH, format="PNG")
    print(f"font {family} {font_path}")
    print(f"segments {len(grid_segments(rows))}")
    for row in rows:
        print(
            f"{row['id']} {row['role']} pixel {row['pixel_x']}, {row['pixel_y']} "
            f"label {row['label']} side {row['side']}"
        )
    print(f"png {PNG_PATH} {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
