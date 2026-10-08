# Figure 7 — console readout

One frame with the console open on `show_cursorstat`, the cursor on the map, and the reported coordinate legible.

## Files

| File | Pixels | What it is |
|---|---|---|
| `frame.png` | 1280×720 | Untouched client frame, console open |
| `console_crop.png` | 252×11 | The console line that contains the coordinate |

## Source

New capture, this session. Not an original run and not an existing frame.

The game was already running and already the foreground window. No save was loaded. No save was written. No army was moved.

## Capture conditions

- Game version: not verified against the running build
- Resolution: 1280×720 client (verified before the zoom and before the command)
- Zoom: `CameraPoseDirector.reset_zoom()` returned success. That procedure saturates zoom-in, then steps out `zoom_steps_from_max_in` times. Config value is 14 (`config/default.yaml`). The radar frustum width was not measured afterward, so a match to the locked canonical pose is not verified
- Window focus at the grab: Rome was the foreground window (verified). After the console was closed, focus was Cursor. That was after the frame was saved

## Cursor

The cursor does not appear in the image.

Verified: `grab_rgb_image` uses Windows Graphics Capture with `cursor_capture=False`. A viewing of this frame showed no cursor sprite. The game still reacted to the cursor (the settlement tooltip opened).

Cursor position at the grab, client pixels, from `GetCursorPos` / `ScreenToClient`:

- 545 px from the left, 516 px from the top
- 42.58% from the left, 71.67% from the top

## What is under the cursor

The Arretium settlement badge. Verified by the detector centre used as the aim point, `(545, 516)`, and by the Arretium tooltip in the frame.

## Reader output

Frozen reader `read_console_cursorstat` at commit `8184ba1`. The file blob matches that commit (`530362196c312528b075a15b8d58f7976a39ed64`). Verified.

Read of `frame.png`:

- status: read
- xy: (90, 79)
- confidence: 0.75
- reason: empty

One read. No second reader setting.

## Console crop box

Pixels, x0 y0 x1 y1: `48, 115, 300, 126`

That is the 6 px pos line the reader used (line top y=117) plus a few pixels of the console around it, wide enough to include the coordinate.

## Privacy

Checked by viewing the frame before it was copied here.

- No Windows title bar, desktop, file path, host name, or user name
- The top band is the game console (`Welcome to RomaShell`, the command, and the pos line)
- In-game HUD and the Arretium tooltip are in the frame

## Assumed or not verified

- Game version: not verified
- That this zoom matches the locked canonical pose: not verified (reset returned success; frustum width was not checked)
- Region id on the pos line: not recorded. The reader does not return it
