# Figure 4 — two plaque styles

One source frame containing a settlement plaque drawn as a solid cream card and a settlement plaque drawn as a translucent label. Crops cover the badge and the plaque.

## Files

| File | Pixels | What it is |
|---|---|---|
| `full_frame.png` | 1280×720 | Source frame, no further crop or drawing |
| `crop_card.png` | 196×112 | Solid cream card. Settlement: Arretium |
| `crop_translucent.png` | 196×112 | Translucent label. Settlement: Segesta |

Both crops are the same size. They were cut from `full_frame.png` at native resolution.

## Source

Existing frame. Not a new capture.

- Path: `data/runtime/view_besiege/20260911-220517_qwen3vl_frame.jpg`
- Filename stamp: 2026-09-11 22:05:17
- File timestamp: 2026-09-11 22:05:17 (verified from the file's last-write time)

The probe script saved that file as JPEG quality 85 (`scripts/_probe_qwen3vl_scan.py`). `full_frame.png` is a PNG of those decoded pixels. The pre-JPEG buffer was not kept. Verified by reading the script.

## Capture conditions

- Game version: not verified for this frame
- Resolution: 1280×720 (verified from the pixel size)
- Zoom: not re-measured. `docs/settlement-detector-handoff.md` (2026-09-11) states this frame is not the canonical pose. Assumed from that document.

## Cursor

The cursor does not appear in the image.

- Verified by viewing the full frame: no cursor sprite.
- The probe used `grab_rgb_image`, which uses Windows Graphics Capture with `cursor_capture=False` (`src/comstar_game_ai/game_io/capture/wgc_capture.py`). That flag has been in the file since commit `6cd6e2d` (2026-09-11 09:46), before this frame. Verified in git.

## Positions (percent of the 1280×720 frame)

Badge centres from `detect_settlements` on this frame. Verified by running the detector.

| Settlement | Crop | x from left | y from top |
|---|---|---|---|
| Arretium | `crop_card.png` | 45.7% (585 px) | 62.6% (451 px) |
| Segesta | `crop_translucent.png` | 14.1% (181 px) | 46.4% (334 px) |

## Crop boxes (pixels, x0 y0 x1 y1)

| File | Box | Padding note |
|---|---|---|
| `crop_card.png` | 540, 404, 736, 516 | About 20 px of terrain around the badge and the cream card |
| `crop_translucent.png` | 142, 282, 338, 394 | Same 196×112 size. The label is shorter than the card, so the terrain margin is larger |

## Reader

No reader output. This figure does not use `show_cursorstat`.

## Privacy

Checked before saving. Verified by viewing the full frame and by an empty EXIF block.

- No Windows title bar. The frame is the 1280×720 client.
- No desktop, overlay panel, file path, host name, or user name.
- In-game HUD is present (date, treasury, side buttons, minimap). That is the game's own interface.

## Assumed or not verified

- Game version: not verified
- Zoom: assumed not canonical, from `docs/settlement-detector-handoff.md`. Not re-measured
- A handoff and `tests/unit/test_settlement_detector.py` say a debug reticle covers the Segesta badge. A 4× view of that badge in this session showed the ring and emblem, and no separate crosshair. Not verified that a reticle is present. The detector found the badge
- The other two plaques in the same frame (Ariminum, cream card; Patavium, translucent label) were not cropped
