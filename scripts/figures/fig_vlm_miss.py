"""Draw the settlement-miss figure for the 2026-09-11 probe frame.

Reads the raw model response and the frame the probe saved from the image
it sent. Measured centres are the hand-measured fractions in
docs/settlement-detector-handoff.md section 1.1.
"""

from __future__ import annotations

import base64
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "runtime" / "view_besiege" / "20260911-220517_qwen3vl_raw.txt"
FRAME_PATH = ROOT / "data" / "runtime" / "view_besiege" / "20260911-220517_qwen3vl_frame.jpg"
PNG_PATH = ROOT / "docs" / "figures" / "fig3_vlm_miss.png"
SVG_PATH = ROOT / "docs" / "figures" / "fig3_vlm_miss.svg"
FONT_DIR = Path(__file__).resolve().parent / "fonts"

FRAME_W = 1280
FRAME_H = 720
SCALE = 2
OUT_W = FRAME_W * SCALE
OUT_H = FRAME_H * SCALE

# Hand-measured badge centres, docs/settlement-detector-handoff.md section 1.1.
# tests/unit/test_settlement_detector.py copies three of these and calls them
# hand-measured. They are not the detector's output on this frame.
MEASURED = {
    "Segesta": (0.151, 0.456),
    "Arretium": (0.466, 0.628),
    "Patavium": (0.570, 0.285),
    "Ariminum": (0.699, 0.528),
}

# The raw response spells Arretium as ARRETUM.
MODEL_NAMES = {
    "SEGESTA": "Segesta",
    "ARRETIUM": "Arretium",
    "ARRETUM": "Arretium",
    "PATAVIUM": "Patavium",
    "ARIMINUM": "Ariminum",
}

TEAL = (0x0F, 0x52, 0x57, 255)
ORANGE = (0xC2, 0x41, 0x0C, 255)
WHITE = (255, 255, 255, 255)
GRID = (255, 255, 255, 64)  # 64/255 = 0.251
PILL = (16, 20, 24, 210)
FONT_PX = 22
CIRCLE_R = 14
STROKE = 3
HALO = 1
X_ARM = 8
DASH_ON = 8
DASH_OFF = 6
LINE_W = 2
PAD_X = 10
PAD_Y = 6
MARKER_CLEAR = 22
LABEL_GAP = 10

# Side of the measured centre the label sits on.
LABEL_SIDE = {
    "Segesta": "left",
    "Arretium": "below",
    "Patavium": "above",
    "Ariminum": "below",
}


def round_px(value: float) -> int:
    """Round half up to a whole pixel."""
    return int(math.floor(value + 0.5))


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


def load_model() -> dict[str, tuple[float, float]]:
    payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("Raw response is not a list")
    found: dict[str, tuple[float, float]] = {}
    for item in payload:
        raw_name = str(item.get("name", "")).strip().upper()
        name = MODEL_NAMES.get(raw_name)
        if name is None:
            raise SystemExit(f"Unmapped settlement name {raw_name!r}")
        if name in found:
            raise SystemExit(f"Duplicate settlement {name}")
        found[name] = (float(item["x"]), float(item["y"]))
    missing = [name for name in MEASURED if name not in found]
    if missing:
        raise SystemExit(f"Raw response missing {missing}")
    return found


def misses(model: dict[str, tuple[float, float]]) -> list[dict]:
    rows = []
    for name, (mx, my) in MEASURED.items():
        vx, vy = model[name]
        dx = (vx - mx) * FRAME_W
        dy = (vy - my) * FRAME_H
        dist = math.hypot(dx, dy)
        rows.append(
            {
                "name": name,
                "measured": (mx * FRAME_W, my * FRAME_H),
                "model": (vx * FRAME_W, vy * FRAME_H),
                "miss": dist,
                "label": f"{name}, {round_px(dist)} px",
                "measured_xy": (mx * OUT_W, my * OUT_H),
                "model_xy": (vx * OUT_W, vy * OUT_H),
            }
        )
    return rows


def text_box(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, tuple[int, int, int, int]]:
    bbox = font.getbbox(text)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height, bbox


def pill_size(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, tuple[int, int, int, int]]:
    tw, th, bbox = text_box(font, text)
    return tw + PAD_X * 2, th + PAD_Y * 2, bbox


def place_label(side: str, cx: float, cy: float, width: int, height: int) -> tuple[float, float]:
    if side == "left":
        return cx - MARKER_CLEAR - LABEL_GAP - width, cy - height / 2
    if side == "right":
        return cx + MARKER_CLEAR + LABEL_GAP, cy - height / 2
    if side == "above":
        return cx - width / 2, cy - MARKER_CLEAR - LABEL_GAP - height
    if side == "below":
        return cx - width / 2, cy + MARKER_CLEAR + LABEL_GAP
    raise SystemExit(f"Unknown label side {side}")


def rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], gap: float = 4) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + gap <= bx0 or bx1 + gap <= ax0 or ay1 + gap <= by0 or by1 + gap <= ay0)


def hits_disk(rect: tuple[float, float, float, float], cx: float, cy: float, radius: float) -> bool:
    x0, y0, x1, y1 = rect
    nx = min(max(cx, x0), x1)
    ny = min(max(cy, y0), y1)
    return math.hypot(nx - cx, ny - cy) < radius


def layout_labels(font: ImageFont.FreeTypeFont, rows: list[dict]) -> list[dict]:
    placed = []
    boxes = []
    for row in rows:
        width, height, bbox = pill_size(font, row["label"])
        cx, cy = row["measured_xy"]
        x, y = place_label(LABEL_SIDE[row["name"]], cx, cy, width, height)
        rect = (x, y, x + width, y + height)
        if x < 8 or y < 8 or x + width > OUT_W - 8 or y + height > OUT_H - 8:
            raise SystemExit(f"{row['name']} label falls outside the frame: {rect}")
        for other in boxes:
            if rects_overlap(rect, other):
                raise SystemExit(f"{row['name']} label overlaps another label")
        for point in (row["measured_xy"], row["model_xy"]):
            if hits_disk(rect, point[0], point[1], MARKER_CLEAR):
                raise SystemExit(f"{row['name']} label covers a marker")
        boxes.append(rect)
        placed.append({**row, "pill": rect, "bbox": bbox, "text_w": width - PAD_X * 2, "text_h": height - PAD_Y * 2})
    return placed


def grid_coords() -> tuple[list[int], list[int]]:
    xs = []
    ys = []
    for i in range(21):
        x = int(round(i * 0.05 * OUT_W))
        y = int(round(i * 0.05 * OUT_H))
        if 0 <= x < OUT_W:
            xs.append(x)
        if 0 <= y < OUT_H:
            ys.append(y)
    return xs, ys


def _x_lines(x: float, y: float) -> tuple[tuple[tuple[float, float], tuple[float, float]], tuple[tuple[float, float], tuple[float, float]]]:
    return (
        ((x - X_ARM, y - X_ARM), (x + X_ARM, y + X_ARM)),
        ((x - X_ARM, y + X_ARM), (x + X_ARM, y - X_ARM)),
    )


def paint_mark(overlay: Image.Image, draw_shape) -> None:
    """Draw a mark with a 1 px white halo. Pillow's stroke width does not leave that halo on a diagonal."""
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


def paint_x(overlay: Image.Image, x: float, y: float) -> None:
    lines = _x_lines(x, y)

    def draw_shape(draw: ImageDraw.ImageDraw) -> None:
        for p0, p1 in lines:
            draw.line([p0, p1], fill=ORANGE, width=STROKE)

    paint_mark(overlay, draw_shape)


def blend_hline(overlay: Image.Image, x0: float, x1: float, y: float) -> None:
    """1 px white at 25% opacity, composited onto the pixels already in the overlay."""
    px = overlay.load()
    yy = int(round(y))
    src_a = GRID[3] / 255
    for xx in range(int(round(min(x0, x1))), int(round(max(x0, x1))) + 1):
        dr, dg, db, da = px[xx, yy]
        dst_a = da / 255
        out_a = src_a + dst_a * (1 - src_a)
        if out_a <= 0:
            continue
        def channel(src: int, dst: int) -> int:
            return int(round((src * src_a + dst * dst_a * (1 - src_a)) / out_a))

        px[xx, yy] = (channel(255, dr), channel(255, dg), channel(255, db), int(round(out_a * 255)))


def dashed_line(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    fill: tuple[int, int, int, int],
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
                width=LINE_W,
            )
        drawing = not drawing
        t = t2


def paint_grid(overlay: Image.Image) -> None:
    px = overlay.load()
    xs, ys = grid_coords()
    w, h = overlay.size
    for x in xs:
        for y in range(h):
            px[x, y] = GRID
    for y in ys:
        for x in range(w):
            px[x, y] = GRID


def legend_box(font: ImageFont.FreeTypeFont) -> tuple[tuple[float, float, float, float], list[str]]:
    lines = ["Measured position", "Model's answer", "0.05 grid"]
    text_w = max(text_box(font, line)[0] for line in lines)
    row_h = max(FONT_PX + 8, CIRCLE_R * 2 + STROKE + HALO * 2 + 8)
    pad = 16
    swatch = CIRCLE_R * 2 + 16
    width = pad + swatch + 12 + text_w + pad
    height = pad + row_h * len(lines) + pad
    x0 = 24
    y0 = OUT_H - 24 - height
    return (x0, y0, x0 + width, y0 + height), lines


def draw_legend(
    overlay: Image.Image,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    panel: tuple[float, float, float, float],
) -> None:
    x0, y0, x1, y1 = panel
    draw.rounded_rectangle((x0, y0, x1, y1), radius=12, fill=PILL)
    lines = ["Measured position", "Model's answer", "0.05 grid"]
    row_h = (y1 - y0 - 32) / 3
    swatch_cx = x0 + 16 + CIRCLE_R
    for i, line in enumerate(lines):
        cy = y0 + 16 + row_h * i + row_h / 2
        if i == 0:
            paint_ring(overlay, swatch_cx, cy)
        elif i == 1:
            paint_x(overlay, swatch_cx, cy)
        else:
            blend_hline(overlay, swatch_cx - 16, swatch_cx + 16, cy)
        tw, th, bbox = text_box(font, line)
        tx = x0 + 16 + CIRCLE_R * 2 + 16 + 12
        ty = cy - th / 2 - bbox[1]
        draw.text((tx, ty), line, font=font, fill=WHITE)


def render_png(base: Image.Image, font: ImageFont.FreeTypeFont, rows: list[dict]) -> Image.Image:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    paint_grid(overlay)
    draw = ImageDraw.Draw(overlay)
    for row in rows:
        x, y = row["measured_xy"]
        paint_ring(overlay, x, y)
    for row in rows:
        x, y = row["model_xy"]
        paint_x(overlay, x, y)
    for row in rows:
        dashed_line(draw, row["model_xy"], row["measured_xy"], ORANGE)
    for row in rows:
        x0, y0, x1, y1 = row["pill"]
        draw.rounded_rectangle((x0, y0, x1, y1), radius=(y1 - y0) / 2, fill=PILL)
        _, _, bbox = text_box(font, row["label"])
        draw.text((x0 + PAD_X - bbox[0], y0 + PAD_Y - bbox[1]), row["label"], font=font, fill=WHITE)
    panel, _ = legend_box(font)
    draw_legend(overlay, draw, font, panel)
    # Labels must stay clear of the legend panel.
    for row in rows:
        if rects_overlap(row["pill"], panel, gap=0):
            raise SystemExit(f"{row['name']} label overlaps the legend")
    framed = base.convert("RGBA")
    return Image.alpha_composite(framed, overlay).convert("RGB")


def svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_svg(background_png: bytes, font_bytes: bytes, family: str, font: ImageFont.FreeTypeFont, rows: list[dict]) -> str:
    ascent, _descent = font.getmetrics()
    image_b64 = base64.b64encode(background_png).decode("ascii")
    font_b64 = base64.b64encode(font_bytes).decode("ascii")
    xs, ys = grid_coords()
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{OUT_W}" height="{OUT_H}" viewBox="0 0 {OUT_W} {OUT_H}">',
        "<defs>",
        "<style>",
        "@font-face {",
        f"  font-family: '{family}';",
        f"  src: url('data:font/ttf;base64,{font_b64}') format('truetype');",
        "}",
        "</style>",
        "</defs>",
        (
            f'<image x="0" y="0" width="{OUT_W}" height="{OUT_H}" '
            f'href="data:image/png;base64,{image_b64}" image-rendering="pixelated"/>'
        ),
    ]
    for x in xs:
        parts.append(
            f'<line x1="{x}" y1="0" x2="{x}" y2="{OUT_H}" stroke="#ffffff" '
            'stroke-opacity="0.25" stroke-width="1" shape-rendering="crispEdges"/>'
        )
    for y in ys:
        parts.append(
            f'<line x1="0" y1="{y}" x2="{OUT_W}" y2="{y}" stroke="#ffffff" '
            'stroke-opacity="0.25" stroke-width="1" shape-rendering="crispEdges"/>'
        )
    for row in rows:
        x, y = row["measured_xy"]
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{CIRCLE_R}" fill="none" '
            f'stroke="#ffffff" stroke-width="{STROKE + HALO * 2}"/>'
        )
        parts.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{CIRCLE_R}" fill="none" '
            f'stroke="#0F5257" stroke-width="{STROKE}"/>'
        )
    for row in rows:
        x, y = row["model_xy"]
        parts.append(
            f'<line x1="{x - X_ARM:.2f}" y1="{y - X_ARM:.2f}" x2="{x + X_ARM:.2f}" y2="{y + X_ARM:.2f}" '
            f'stroke="#ffffff" stroke-width="{STROKE + HALO * 2}" stroke-linecap="butt"/>'
        )
        parts.append(
            f'<line x1="{x - X_ARM:.2f}" y1="{y + X_ARM:.2f}" x2="{x + X_ARM:.2f}" y2="{y - X_ARM:.2f}" '
            f'stroke="#ffffff" stroke-width="{STROKE + HALO * 2}" stroke-linecap="butt"/>'
        )
        parts.append(
            f'<line x1="{x - X_ARM:.2f}" y1="{y - X_ARM:.2f}" x2="{x + X_ARM:.2f}" y2="{y + X_ARM:.2f}" '
            f'stroke="#C2410C" stroke-width="{STROKE}" stroke-linecap="butt"/>'
        )
        parts.append(
            f'<line x1="{x - X_ARM:.2f}" y1="{y + X_ARM:.2f}" x2="{x + X_ARM:.2f}" y2="{y - X_ARM:.2f}" '
            f'stroke="#C2410C" stroke-width="{STROKE}" stroke-linecap="butt"/>'
        )
    for row in rows:
        x0, y0 = row["model_xy"]
        x1, y1 = row["measured_xy"]
        parts.append(
            f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
            f'stroke="#C2410C" stroke-width="{LINE_W}" stroke-dasharray="{DASH_ON} {DASH_OFF}" '
            'stroke-linecap="butt"/>'
        )
    for row in rows:
        x0, y0, x1, y1 = row["pill"]
        h = y1 - y0
        parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{h:.2f}" '
            f'rx="{h / 2:.2f}" fill="#101418" fill-opacity="{210 / 255:.4f}"/>'
        )
        _, _, bbox = text_box(font, row["label"])
        tx = x0 + PAD_X - bbox[0]
        ty = y0 + PAD_Y - bbox[1] + ascent
        parts.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" fill="#ffffff" font-family="{family}" '
            f'font-size="{FONT_PX}">{svg_escape(row["label"])}</text>'
        )
    panel, lines = legend_box(font)
    x0, y0, x1, y1 = panel
    parts.append(
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
        f'rx="12" fill="#101418" fill-opacity="{210 / 255:.4f}"/>'
    )
    row_h = (y1 - y0 - 32) / 3
    swatch_cx = x0 + 16 + CIRCLE_R
    for i, line in enumerate(lines):
        cy = y0 + 16 + row_h * i + row_h / 2
        if i == 0:
            parts.append(
                f'<circle cx="{swatch_cx:.2f}" cy="{cy:.2f}" r="{CIRCLE_R}" fill="none" '
                f'stroke="#ffffff" stroke-width="{STROKE + HALO * 2}"/>'
            )
            parts.append(
                f'<circle cx="{swatch_cx:.2f}" cy="{cy:.2f}" r="{CIRCLE_R}" fill="none" '
                f'stroke="#0F5257" stroke-width="{STROKE}"/>'
            )
        elif i == 1:
            parts.append(
                f'<g stroke-linecap="butt">'
                f'<line x1="{swatch_cx - X_ARM:.2f}" y1="{cy - X_ARM:.2f}" x2="{swatch_cx + X_ARM:.2f}" y2="{cy + X_ARM:.2f}" stroke="#ffffff" stroke-width="{STROKE + HALO * 2}"/>'
                f'<line x1="{swatch_cx - X_ARM:.2f}" y1="{cy + X_ARM:.2f}" x2="{swatch_cx + X_ARM:.2f}" y2="{cy - X_ARM:.2f}" stroke="#ffffff" stroke-width="{STROKE + HALO * 2}"/>'
                f'<line x1="{swatch_cx - X_ARM:.2f}" y1="{cy - X_ARM:.2f}" x2="{swatch_cx + X_ARM:.2f}" y2="{cy + X_ARM:.2f}" stroke="#C2410C" stroke-width="{STROKE}"/>'
                f'<line x1="{swatch_cx - X_ARM:.2f}" y1="{cy + X_ARM:.2f}" x2="{swatch_cx + X_ARM:.2f}" y2="{cy - X_ARM:.2f}" stroke="#C2410C" stroke-width="{STROKE}"/>'
                f"</g>"
            )
        else:
            parts.append(
                f'<line x1="{swatch_cx - 16:.2f}" y1="{cy:.2f}" x2="{swatch_cx + 16:.2f}" y2="{cy:.2f}" '
                'stroke="#ffffff" stroke-opacity="0.25" stroke-width="1" shape-rendering="crispEdges"/>'
            )
        tw, th, bbox = text_box(font, line)
        tx = x0 + 16 + CIRCLE_R * 2 + 16 + 12
        ty = cy - th / 2 - bbox[1] + ascent
        del tw
        parts.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" fill="#ffffff" font-family="{family}" '
            f'font-size="{FONT_PX}">{svg_escape(line)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def unchanged_pixel(source: Image.Image, scaled: Image.Image, result: Image.Image) -> None:
    """A pixel off the grid and away from overlays must match the doubled frame."""
    sx, sy = 10, 10
    src = source.getpixel((sx, sy))
    for ox in (0, 1):
        for oy in (0, 1):
            doubled = scaled.getpixel((sx * SCALE + ox, sy * SCALE + oy))
            final = result.getpixel((sx * SCALE + ox, sy * SCALE + oy))
            if doubled != src or final != src:
                raise SystemExit(f"Background pixel changed at {(sx, sy)}: {src} {doubled} {final}")


def main() -> None:
    if not RAW_PATH.is_file():
        raise SystemExit(f"Missing raw response {RAW_PATH}")
    if not FRAME_PATH.is_file():
        raise SystemExit(f"Missing frame {FRAME_PATH}")
    model = load_model()
    rows = misses(model)
    font_path, family = find_font()
    font = ImageFont.truetype(str(font_path), FONT_PX)
    rows = layout_labels(font, rows)

    frame = Image.open(FRAME_PATH)
    if frame.size != (FRAME_W, FRAME_H):
        raise SystemExit(f"Frame is {frame.size}, expected {FRAME_W}x{FRAME_H}")
    if frame.mode != "RGB":
        raise SystemExit(f"Frame mode is {frame.mode}, expected RGB")
    scaled = frame.resize((OUT_W, OUT_H), Image.Resampling.NEAREST)
    result = render_png(scaled, font, rows)
    if result.size != (OUT_W, OUT_H):
        raise SystemExit(f"Output is {result.size}")
    unchanged_pixel(frame, scaled, result)

    buf = io.BytesIO()
    scaled.save(buf, format="PNG")
    svg = render_svg(buf.getvalue(), font_path.read_bytes(), family, font, rows)

    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.save(PNG_PATH, format="PNG")
    SVG_PATH.write_text(svg, encoding="utf-8")

    print(f"font {family} {font_path}")
    print(f"{'settlement':<12} {'measured px':<22} {'model px':<22} {'miss px':>8} {'label'}")
    for row in rows:
        mx, my = row["measured"]
        vx, vy = row["model"]
        print(
            f"{row['name']:<12} ({mx:7.2f}, {my:7.2f})   ({vx:7.2f}, {vy:7.2f})   "
            f"{row['miss']:8.2f}  {row['label']}"
        )
    print(f"png {PNG_PATH} {PNG_PATH.stat().st_size} bytes {result.size[0]}x{result.size[1]}")
    print(f"svg {SVG_PATH} {SVG_PATH.stat().st_size} bytes {OUT_W}x{OUT_H}")


if __name__ == "__main__":
    main()
