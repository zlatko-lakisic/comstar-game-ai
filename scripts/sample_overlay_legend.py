"""Sample the strategic overlay's legend swatches so the colour tables are measured.

The overlay encodes everything an agent wants to know about a settlement in the
colour of its map icon, and the legends on either edge are the key. Reading the key
off the screen beats hardcoding RGB triples: the swatch is drawn by the same code
that tints the icon, so a sampled swatch cannot disagree with the map, and a mod or
a patch that recolours a faction updates both at once.

Run against a frame captured with the overlay up (Tab).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Sampled from a 1920x1080 client area, normalised so other resolutions still hit
# the swatch. Both legends dock to a screen edge, so these ride the edge with it.
SETTLEMENT_SWATCHES: dict[str, tuple[float, float]] = {
    "working": (0.0305, 0.7667),
    "upgradeable": (0.0305, 0.8056),
    "idle": (0.0305, 0.8444),
    "ally": (0.0305, 0.9065),
    "enemy": (0.0305, 0.9454),
    "neutral": (0.0305, 0.9843),
}

FACTION_SWATCHES: dict[str, tuple[float, float]] = {
    "greek_cities": (0.8934, 0.6019),
    "rebels": (0.8934, 0.6389),
    "julii": (0.8934, 0.6766),
    "spqr": (0.8934, 0.7142),
    "scipii": (0.8934, 0.7519),
    "seleucid": (0.8934, 0.7901),
    "brutii": (0.8934, 0.8284),
    "macedon": (0.8934, 0.8667),
    "egypt": (0.8934, 0.9049),
    "carthage": (0.8934, 0.9432),
    "gaul": (0.8934, 0.9803),
}


def sample(image: Image.Image, nx: float, ny: float, *, half: int = 4) -> tuple[int, int, int]:
    """Median-ish sample of a swatch, so an anti-aliased border cannot skew it."""
    w, h = image.size
    cx, cy = int(round(nx * w)), int(round(ny * h))
    patch = image.crop((cx - half, cy - half, cx + half + 1, cy + half + 1))
    rgb = patch.convert("RGB")
    pixels = [rgb.getpixel((ix, iy)) for iy in range(rgb.height) for ix in range(rgb.width)]
    pixels.sort(key=lambda p: p[0] + p[1] + p[2])
    return pixels[len(pixels) // 2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame", type=Path)
    args = parser.parse_args()

    image = Image.open(args.frame).convert("RGB")
    print(f"{args.frame} {image.size[0]}x{image.size[1]}")

    for title, table in (("settlement states", SETTLEMENT_SWATCHES), ("factions", FACTION_SWATCHES)):
        print(f"\n{title}")
        seen: dict[tuple[int, int, int], str] = {}
        for name, (nx, ny) in table.items():
            rgb = sample(image, nx, ny)
            clash = seen.get(rgb)
            seen[rgb] = name
            note = f"  <-- identical to {clash}" if clash else ""
            print(f"  {name:<14} rgb{rgb} #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
