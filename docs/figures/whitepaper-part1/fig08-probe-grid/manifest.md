# Figure 8 — probe grid

Raw pixel and map pairs for an illustration of how pixels relate to map coordinates.

**Figure only, not calibration data.** No homography, affine, or other mapping was fit. No residuals were computed.

## Files

| File | Pixels |
|---|---|
| `background.png` | 1280×720 |
| `background_after.png` | 1280×720 |
| `probe_01.png` … `probe_12.png` | 1280×720 each |
| `probes.csv` | the twelve reader results |

Nothing is drawn on the frames.

## Source

New capture, this session. The zoom was left where figure 7 set it. The camera was then panned west, twice, with the existing pan path (key A, console closed): 0.45 s, then 0.28 s. It was not zoomed again and not panned after `background.png`.

No save was loaded or written. No army was moved.

## Capture conditions

- Game version: see the session report. Not written onto these frames
- Resolution: 1280×720 client (verified on the background grab and on every probe)
- Zoom: the figure 7 `reset_zoom()` result, unchanged during this step. Frustum width was not measured
- Console: closed for both backgrounds (verified with the console-edge check). Open during the probe frames, because that is when `show_cursorstat` is read

## Cursor

The cursor does not appear in the images. Capture is Windows Graphics Capture with `cursor_capture=False`. Verified in code, and no cursor sprite was seen on the frames that were viewed.

Positions below are the cursor at the grab (`GetCursorPos` / `ScreenToClient`), as percent of the 1280×720 frame. The aim was one pixel lower on probes 01–11. Probe 12 matched the aim.

| Probe | Role | x from left | y from top |
|---|---|---|---|
| 01 | grid | 15.62% (200 px) | 33.19% (239 px) |
| 02 | grid | 46.88% (600 px) | 33.19% (239 px) |
| 03 | grid | 78.12% (1000 px) | 33.19% (239 px) |
| 04 | grid | 15.62% (200 px) | 58.19% (419 px) |
| 05 | grid | 46.88% (600 px) | 58.19% (419 px) |
| 06 | grid | 78.12% (1000 px) | 58.19% (419 px) |
| 07 | grid | 15.62% (200 px) | 80.42% (579 px) |
| 08 | grid | 46.88% (600 px) | 80.42% (579 px) |
| 09 | grid | 78.12% (1000 px) | 80.42% (579 px) |
| 10 | held out | 31.25% (400 px) | 45.69% (329 px) |
| 11 | held out | 60.94% (780 px) | 70.69% (509 px) |
| 12 | held out | 35.16% (450 px) | 34.72% (250 px) |

The held-out points are not on the grid lines x = 200, 600, 1000 or y = 239, 419, 579.

The grid sits inside the map: right of the side buttons, left of the minimap, below the console band, above the bottom bar. `detect_settlements` on the coast frame found no badges.

## Reader output

Frozen reader `read_console_cursorstat` at commit `8184ba1`. One call per probe. No second setting. No probe was refused.

| Probe | Status | xy | Confidence |
|---|---|---|---|
| 01 | read | (35, 91) | 0.778 |
| 02 | read | (49, 91) | 0.833 |
| 03 | read | (63, 91) | 0.833 |
| 04 | read | (38, 82) | 0.778 |
| 05 | read | (49, 82) | 0.778 |
| 06 | read | (61, 82) | 0.833 |
| 07 | read | (61, 82) | 0.833 |
| 08 | read | (61, 82) | 0.833 |
| 09 | read | (59, 77) | 0.667 |
| 10 | read | (43, 86) | 0.778 |
| 11 | read | (43, 86) | 0.778 |
| 12 | read | (44, 90) | 0.778 |

On probes 07, 08, and 11 the console picture shows a later pos line under the line this reader returned. Those later lines were not written into the table. Verified by viewing those three frames. The values above are the frozen reader's return only.

## Camera check

`background_after.png` was taken with the console closed, after the last probe.

The coast, ridge, and shoreline are in the same place on both backgrounds. Verified by viewing both frames. A fixed land patch (x 200–450, y 360–520) has mean absolute channel difference 0.65. The camera did not move.

`background.png` also shows a Textiles tooltip. The cursor was over that resource when the clean-console frame was taken. `background_after.png` does not show that tooltip. That difference is the tooltip, not a pan.

## Privacy

Checked by viewing `background.png`, `background_after.png`, and the console bands of probes 06, 07, 08, and 11.

- No Windows title bar, desktop, file path, host name, or user name
- In-game HUD, the Textiles tooltip, and the game console are present

## Assumed or not verified

- Game version of this running build, beyond the executable file properties in the session report: not verified from inside the game
- That this zoom still matches the locked canonical pose: not verified
- The digits on the later console lines that the reader did not return: seen on the pictures, not reader output
