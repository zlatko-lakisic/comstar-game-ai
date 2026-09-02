"""Compose JPEG views for Reach multimodal calls."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

# Reach caps: 16 images, 4 MiB each, 20 MiB total (see docs/design/bottlenecks.md)
MAX_IMAGES = 16
MAX_BYTES_PER_IMAGE = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_JPEG_QUALITY = 80


@dataclass
class ViewBudget:
    max_images: int = 6
    max_total_bytes: int = MAX_TOTAL_BYTES
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    jpeg_quality: int = DEFAULT_JPEG_QUALITY


@dataclass
class ViewLayer:
    """One layer placed on a composed canvas."""

    image: Image.Image
    box: tuple[int, int, int, int] | None = None  # left, top, right, bottom on canvas
    label: str = ""


def _fit_canvas(image: Image.Image, width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), color=(16, 16, 20))
    src = image.convert("RGB")
    src.thumbnail((width, height), Image.Resampling.LANCZOS)
    offset = ((width - src.width) // 2, (height - src.height) // 2)
    canvas.paste(src, offset)
    return canvas


def compose_canvas(
    layers: list[ViewLayer],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Image.Image:
    """Stack layers onto a single canvas."""
    canvas = Image.new("RGB", (width, height), color=(16, 16, 20))
    for layer in layers:
        src = layer.image.convert("RGB")
        if layer.box:
            left, top, right, bottom = layer.box
            target_w = max(1, right - left)
            target_h = max(1, bottom - top)
            src.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            canvas.paste(src, (left, top))
        else:
            fitted = _fit_canvas(src, width, height)
            canvas = Image.blend(canvas, fitted, alpha=0.85) if len(layers) > 1 else fitted
    return canvas


def encode_jpeg(image: Image.Image, *, quality: int = DEFAULT_JPEG_QUALITY) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _to_reach_image(data: bytes, name: str) -> dict[str, Any]:
    return {
        "mimeType": "image/jpeg",
        "dataBase64": base64.b64encode(data).decode("ascii"),
        "name": name,
    }


def compose_reach_images(
    views: list[Image.Image],
    budget: ViewBudget | None = None,
    *,
    names: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Encode views as Reach direct_agent images, enforcing byte budgets."""
    cfg = budget or ViewBudget()
    limit = min(cfg.max_images, MAX_IMAGES)
    selected = views[:limit]

    out: list[dict[str, Any]] = []
    total_bytes = 0
    dropped = 0

    for idx, view in enumerate(selected):
        data = encode_jpeg(view, quality=cfg.jpeg_quality)
        if len(data) > MAX_BYTES_PER_IMAGE:
            quality = cfg.jpeg_quality
            while len(data) > MAX_BYTES_PER_IMAGE and quality > 40:
                quality -= 10
                data = encode_jpeg(view, quality=quality)
        if total_bytes + len(data) > cfg.max_total_bytes:
            dropped += 1
            continue
        if len(data) > MAX_BYTES_PER_IMAGE:
            dropped += 1
            continue
        name = names[idx] if names and idx < len(names) else f"view_{idx + 1}"
        out.append(_to_reach_image(data, name))
        total_bytes += len(data)

    stats = {
        "encoded": len(out),
        "dropped": dropped + max(0, len(views) - limit),
        "total_bytes": total_bytes,
    }
    return out, stats


def compose_views_from_layers(
    layer_groups: list[list[ViewLayer]],
    budget: ViewBudget | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build one canvas per layer group and encode for Reach."""
    canvases = [compose_canvas(group) for group in layer_groups]
    return compose_reach_images(canvases, budget)
