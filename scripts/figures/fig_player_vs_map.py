"""White-paper figure 1: the player's view beside the game's map coordinates.

The left panel is the untouched frame
docs/figures/whitepaper-part1/fig04-plaque-styles/full_frame.png, with a hollow
circle at each hand-measured badge centre from
docs/settlement-detector-handoff.md section 1.1.

The right panel plots the same settlements at the map coordinates returned by
load_start_position. A settlement with no coordinate is omitted.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from comstar_game_ai.game_io.campaign.start_position import load_start_position

FRAME_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig04-plaque-styles" / "full_frame.png"
PNG_PATH = ROOT / "docs" / "figures" / "whitepaper-part1" / "fig01-player-vs-map" / "fig01.png"
FONT_DIR = Path(__file__).resolve().parent / "fonts"

OUT_W = 2560
OUT_H = 1440

# Hand-measured badge centres, docs/settlement-detector-handoff.md section 1.1.
MEASURED = {
    "Segesta": (0.151, 0.456),
    "Arretium": (0.466, 0.628),
    "Patavium": (0.570, 0.285),
    "Ariminum": (0.699, 0.528),
}
SETTLEMENTS = ("Segesta", "Arretium", "Patavium", "Ariminum")

# Same face size and colours as scripts/figures/fig_vlm_miss.py.
TEAL = (0x0F, 0x52, 0x57, 255)
WHITE = (255, 255, 255, 255)
INK = (16, 20, 24, 255)  # pill RGB from that figure, opaque for text on white
GRID = (208, 214, 216, 255)
FONT_PX = 22
CIRCLE_R = 14
STROKE = 3
HALO = 1
DASH_ON = 8
DASH_OFF = 6
LINE_W = 2
DOT_R = 8

MIN_MARGIN = 48
PANEL_GAP = 72
CAPTION_GAP = 20
RIGHT_PAD = 16
AXIS_PAD = 3
LABEL_GAP = 10

LEFT_CAPTION = "What the player sees"
RIGHT_CAPTION = "Where the game places the same settlements"

# Incoming lines arrive from the left, so labels prefer the other sides.
LABEL_SIDES = {
    "Segesta": ("above", "below", "right", "left"),
    "Arretium": ("below", "left", "above", "right"),
    "Patavium": ("above", "right", "below", "left"),
    "Ariminum": ("above", "right", "below", "left"),
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


def load_rows() -> tuple[list[dict], list[str]]:
    """Map coordinates from load_start_position. Skip a settlement that has none."""
    start = load_start_position()
    if start is None:
        raise SystemExit("load_start_position returned no campaign setup; no coordinates to plot")
    rows: list[dict] = []
    skipped: list[str] = []
    for name in SETTLEMENTS:
        region = start.region_of_settlement(name)
        if region is None or region.x is None or region.y is None:
            skipped.append(name)
            continue
        fx, fy = MEASURED[name]
        rows.append(
            {
                "name": name,
                "region": region.key,
                "x": region.x,
                "y": region.y,
                "fx": fx,
                "fy": fy,
                "label": f"{name} ({region.x}, {region.y})",
            }
        )
    return rows, skipped


def axis_limits(rows: list[dict]) -> tuple[int, int, int, int]:
    xs = [row["x"] for row in rows]
    ys = [row["y"] for row in rows]
    return min(xs) - AXIS_PAD, max(xs) + AXIS_PAD, min(ys) - AXIS_PAD, max(ys) + AXIS_PAD


def choose_layout(
    font: ImageFont.FreeTypeFont, rows: list[dict]
) -> dict[str, float]:
    x_min, x_max, y_min, y_max = axis_limits(rows)
    span_x = x_max - x_min
    span_y = y_max - y_min
    y_label_w = max(text_box(font, str(v))[0] for v in range(y_min, y_max + 1))
    x_label_h = max(text_box(font, str(v))[1] for v in range(x_min, x_max + 1))
    caption_h = max(text_box(font, LEFT_CAPTION)[1], text_box(font, RIGHT_CAPTION)[1])
    y_gutter = y_label_w + 14
    x_gutter = x_label_h + 20
    widest_tick = max(text_box(font, str(v))[0] for v in range(x_min, x_max + 1))

    chosen: dict[str, float] | None = None
    for frame_h in range(9 * 40, OUT_H, 9):
        frame_w = frame_h * 16 // 9
        plot_h = frame_h - x_gutter
        if plot_h < 200:
            continue
        plot_w = int(round(plot_h * span_x / span_y))
        if plot_w / span_x < widest_tick + 8:
            continue
        row_w = frame_w + PANEL_GAP + y_gutter + plot_w + RIGHT_PAD
        row_h = frame_h + CAPTION_GAP + caption_h
        if row_w > OUT_W - 2 * MIN_MARGIN or row_h > OUT_H - 2 * MIN_MARGIN:
            continue
        chosen = {
            "frame_w": frame_w,
            "frame_h": frame_h,
            "plot_w": plot_w,
            "plot_h": plot_h,
            "y_gutter": y_gutter,
            "x_gutter": x_gutter,
            "row_w": row_w,
            "row_h": row_h,
            "caption_h": caption_h,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        }
    if chosen is None:
        raise SystemExit("No layout fits 2560x1440")
    origin_x = (OUT_W - int(chosen["row_w"])) // 2
    origin_y = (OUT_H - int(chosen["row_h"])) // 2
    chosen["frame_x"] = origin_x
    chosen["frame_y"] = origin_y
    chosen["plot_x"] = origin_x + chosen["frame_w"] + PANEL_GAP + chosen["y_gutter"]
    chosen["plot_y"] = origin_y
    return chosen


def data_to_px(layout: dict[str, float], x: float, y: float) -> tuple[float, float]:
    span_x = layout["x_max"] - layout["x_min"]
    span_y = layout["y_max"] - layout["y_min"]
    px = layout["plot_x"] + (x - layout["x_min"]) / span_x * layout["plot_w"]
    py = layout["plot_y"] + (layout["y_max"] - y) / span_y * layout["plot_h"]
    return px, py


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


def dashed_line(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    t = 0.0
    drawing = True
    while t < length - 0.01:
        span = DASH_ON if drawing else DASH_OFF
        t2 = min(length, t + span)
        if drawing:
            draw.line(
                [(x0 + ux * t, y0 + uy * t), (x0 + ux * t2, y0 + uy * t2)],
                fill=fill,
                width=width,
            )
        drawing = not drawing
        t = t2


def shorten(
    p0: tuple[float, float], p1: tuple[float, float], r0: float, r1: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= r0 + r1 + 1:
        return None
    ux, uy = dx / length, dy / length
    return (p0[0] + ux * r0, p0[1] + uy * r0), (p1[0] - ux * r1, p1[1] - uy * r1)


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
    edges = ((corners[0], corners[1]), (corners[1], corners[2]), (corners[2], corners[3]), (corners[3], corners[0]))
    return any(segments_intersect(p0, p1, a, b) for a, b in edges)


def place_label(
    side: str, cx: float, cy: float, width: int, height: int
) -> tuple[float, float]:
    gap = DOT_R + LABEL_GAP
    if side == "above":
        return cx - width / 2, cy - gap - height
    if side == "below":
        return cx - width / 2, cy + gap
    if side == "left":
        return cx - gap - width, cy - height / 2
    if side == "right":
        return cx + gap, cy - height / 2
    raise SystemExit(f"Unknown label side {side}")


def layout_labels(font: ImageFont.FreeTypeFont, layout: dict[str, float], rows: list[dict]) -> None:
    plot = (
        layout["plot_x"] + 4,
        layout["plot_y"] + 4,
        layout["plot_x"] + layout["plot_w"] - 4,
        layout["plot_y"] + layout["plot_h"] - 4,
    )
    placed: list[tuple[float, float, float, float]] = []
    ring_r = CIRCLE_R + STROKE / 2 + HALO
    for row in rows:
        tw, th, bbox = text_box(font, row["label"])
        cx, cy = row["dot"]
        line = row["line"]
        found = None
        for side in LABEL_SIDES[row["name"]]:
            x, y = place_label(side, cx, cy, tw, th)
            rect = (x, y, x + tw, y + th)
            if rect[0] < plot[0] or rect[1] < plot[1] or rect[2] > plot[2] or rect[3] > plot[3]:
                continue
            if any(rects_overlap(rect, other, 8) for other in placed):
                continue
            if any(hits_disk(rect, other["dot"][0], other["dot"][1], DOT_R + 6) for other in rows):
                continue
            if line is not None and segment_hits_rect(line[0], line[1], rect):
                continue
            found = (side, rect, bbox)
            break
        if found is None:
            raise SystemExit(f"No clear place for the {row['name']} label")
        side, rect, bbox = found
        placed.append(rect)
        row["side"] = side
        row["label_rect"] = rect
        row["bbox"] = bbox


def draw_grid(draw: ImageDraw.ImageDraw, layout: dict[str, float]) -> None:
    x_min = int(layout["x_min"])
    x_max = int(layout["x_max"])
    y_min = int(layout["y_min"])
    y_max = int(layout["y_max"])
    for x in range(x_min, x_max + 1):
        px, bottom = data_to_px(layout, x, y_min)
        top = data_to_px(layout, x, y_max)[1]
        draw.line([(px, top), (px, bottom)], fill=GRID, width=1)
    for y in range(y_min, y_max + 1):
        left, py = data_to_px(layout, x_min, y)
        right = data_to_px(layout, x_max, y)[0]
        draw.line([(left, py), (right, py)], fill=GRID, width=1)

    left, top = data_to_px(layout, x_min, y_max)
    right, bottom = data_to_px(layout, x_max, y_min)
    draw.rectangle((left, top, right, bottom), outline=INK, width=1)


def draw_ink(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    ink_x: float,
    ink_y: float,
    text: str,
    *,
    plate: bool,
) -> None:
    """Draw text. A white plate keeps a connector from cutting an axis number."""
    tw, th, bbox = text_box(font, text)
    if plate:
        pad = 2
        draw.rectangle((ink_x - pad, ink_y - pad, ink_x + tw + pad, ink_y + th + pad), fill=WHITE)
    draw.text((ink_x - bbox[0], ink_y - bbox[1]), text, font=font, fill=INK)


def draw_ticks(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, layout: dict[str, float]) -> None:
    x_min = int(layout["x_min"])
    x_max = int(layout["x_max"])
    y_min = int(layout["y_min"])
    y_max = int(layout["y_max"])
    for x in range(x_min, x_max + 1):
        px, py = data_to_px(layout, x, y_min)
        label = str(x)
        tw, th, _ = text_box(font, label)
        draw_ink(draw, font, px - tw / 2, py + 12, label, plate=True)
    for y in range(y_min, y_max + 1):
        px, py = data_to_px(layout, x_min, y)
        label = str(y)
        tw, th, _ = text_box(font, label)
        draw_ink(draw, font, px - 10 - tw, py - th / 2, label, plate=True)


def draw_caption(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    text: str,
    center_x: float,
    top: float,
) -> None:
    tw, _, bbox = text_box(font, text)
    draw.text((center_x - tw / 2 - bbox[0], top - bbox[1]), text, font=font, fill=INK)


def render(font: ImageFont.FreeTypeFont, rows: list[dict]) -> Image.Image:
    layout = choose_layout(font, rows)
    frame = Image.open(FRAME_PATH)
    if frame.size != (1280, 720):
        raise SystemExit(f"Base frame is {frame.size}, expected 1280x720")
    scaled = frame.resize((int(layout["frame_w"]), int(layout["frame_h"])), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (OUT_W, OUT_H), WHITE)
    canvas.paste(scaled, (int(round(layout["frame_x"])), int(round(layout["frame_y"]))))

    for row in rows:
        row["circle"] = (
            layout["frame_x"] + row["fx"] * layout["frame_w"],
            layout["frame_y"] + row["fy"] * layout["frame_h"],
        )
        row["dot"] = data_to_px(layout, row["x"], row["y"])
        ring_r = CIRCLE_R + STROKE / 2 + HALO
        row["line"] = shorten(row["circle"], row["dot"], ring_r, DOT_R)

    layout_labels(font, layout, rows)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_grid(draw, layout)
    for row in rows:
        line = row["line"]
        if line is None:
            continue
        dashed_line(draw, line[0], line[1], WHITE, LINE_W + 2)
    for row in rows:
        line = row["line"]
        if line is None:
            continue
        dashed_line(draw, line[0], line[1], TEAL, LINE_W)
    for row in rows:
        paint_ring(overlay, row["circle"][0], row["circle"][1])
    draw = ImageDraw.Draw(overlay)
    for row in rows:
        cx, cy = row["dot"]
        draw.ellipse((cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R), fill=TEAL)
    draw_ticks(draw, font, layout)
    for row in rows:
        x0, y0, _, _ = row["label_rect"]
        draw_ink(draw, font, x0, y0, row["label"], plate=False)
    caption_top = layout["frame_y"] + layout["frame_h"] + CAPTION_GAP
    draw_caption(
        draw,
        font,
        LEFT_CAPTION,
        layout["frame_x"] + layout["frame_w"] / 2,
        caption_top,
    )
    draw_caption(
        draw,
        font,
        RIGHT_CAPTION,
        layout["plot_x"] + layout["plot_w"] / 2,
        caption_top,
    )

    framed = Image.alpha_composite(canvas, overlay).convert("RGB")
    if framed.size != (OUT_W, OUT_H):
        raise SystemExit(f"Output is {framed.size}")
    return framed


def main() -> None:
    rows, skipped = load_rows()
    for name in skipped:
        print(f"SKIP {name}: load_start_position has no coordinate")
    if not rows:
        raise SystemExit("No settlement had a coordinate")
    font_path, family = find_font()
    font = ImageFont.truetype(str(font_path), FONT_PX)
    image = render(font, rows)
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PNG_PATH, format="PNG")
    print(f"font {family} {font_path}")
    print(f"{'settlement':<12} {'badge':<16} {'map':<12} region")
    for row in rows:
        print(
            f"{row['name']:<12} ({row['fx']:.3f}, {row['fy']:.3f})  "
            f"({row['x']}, {row['y']})  {row['region']}  label {row['side']}"
        )
    print(f"png {PNG_PATH} {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
