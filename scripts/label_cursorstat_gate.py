"""Record pos-line labels from the picture alone.

Shows a fixed crop of the console band and stores the x, y you type, or
unreadable. It does not import the reader and it does not display a
coordinate, a confidence, or the seek target.

    python scripts/label_cursorstat_gate.py --session 20261003-gate17

The 20261006 gate19 through gate24 sessions, and 20261008-gate25 and
gate26, show only the even frames (00, 02, ... 42). Odd frames stay
unlabeled and are not part of the test set.

Type two integers, or the word unreadable, and press Enter. Alt-Left
goes back one frame. Progress is written after every frame.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps, ImageTk

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "data" / "runtime" / "cursorstat_sessions"

# Fixed band on a 1280x720 frame. Not chosen by the reader.
# Covers the reader search rows y=80..149, plus y=150. PIL's bottom is exclusive.
_CROP = (20, 80, 780, 151)
_SCALE = 3
_PAIR = re.compile(r"^(\d+)\s+(\d+)$")
_FRAME_INDEX = re.compile(r"_(\d+)\.png$")
# One cross is 44 frames. The operator labels the even indices only.
_EVEN_ONLY = frozenset(
    {
        "20261006-gate19",
        "20261006-gate20",
        "20261006-gate21",
        "20261006-gate22",
        "20261006-gate23",
        "20261006-gate24",
        "20261008-gate25",
        "20261008-gate26",
    }
)


def in_test_set(session_id: str, row: dict) -> bool:
    """Odd frames of the 20261006 gates are kept out of the test set."""
    if session_id not in _EVEN_ONLY:
        return True
    match = _FRAME_INDEX.search(str(row.get("file", "")))
    return match is not None and int(match.group(1)) % 2 == 0


def _crop(path: Path) -> Image.Image:
    image = Image.open(path).convert("L")
    band = ImageOps.autocontrast(image.crop(_CROP))
    return band.resize(
        (band.width * _SCALE, band.height * _SCALE),
        Image.Resampling.NEAREST,
    )


def _load(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"FAIL: {path} has no frames")
    return rows


def _save(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _entry_text(row: dict) -> str:
    if row.get("operator_mark") == "unreadable":
        return "unreadable"
    xy = row.get("xy")
    if row.get("label_source") == "operator" and isinstance(xy, list) and len(xy) == 2:
        return f"{xy[0]} {xy[1]}"
    return ""


def _apply(row: dict, text: str) -> str | None:
    stripped = text.strip().lower()
    if stripped in {"u", "unreadable"}:
        row["xy"] = None
        row["label_source"] = "operator"
        row["operator_mark"] = "unreadable"
        return None
    match = _PAIR.match(text.strip())
    if match is None:
        return "Type two integers, or unreadable"
    row["xy"] = [int(match.group(1)), int(match.group(2))]
    row["label_source"] = "operator"
    row.pop("operator_mark", None)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="20261003-gate17")
    args = parser.parse_args(argv)
    session = SESSIONS / args.session
    labels_path = session / "labels.json"
    if not labels_path.is_file():
        print(f"FAIL: missing {labels_path}", flush=True)
        return 1
    rows = _load(labels_path)
    shown = [row for row in rows if in_test_set(args.session, row)]
    if not shown:
        print(f"FAIL: {args.session} has no frames to label", flush=True)
        return 1
    index = 0
    for i, row in enumerate(shown):
        if row.get("label_source") != "operator":
            index = i
            break
    else:
        index = 0

    import tkinter as tk

    root = tk.Tk()
    root.title("Pos line")
    status = tk.StringVar()
    error = tk.StringVar()
    photo_holder: dict[str, ImageTk.PhotoImage] = {}

    head = tk.Label(root, textvariable=status, font=("Segoe UI", 14))
    head.pack(padx=12, pady=(12, 4))
    picture = tk.Label(root)
    picture.pack(padx=12, pady=4)
    hint = tk.Label(
        root,
        text="Type the two numbers on the pos line, or unreadable, then Enter. Alt-Left goes back.",
        font=("Segoe UI", 11),
    )
    hint.pack(padx=12, pady=4)
    entry = tk.Entry(root, font=("Consolas", 18), width=24)
    entry.pack(padx=12, pady=4)
    err = tk.Label(root, textvariable=error, fg="#8a1f1f", font=("Segoe UI", 11))
    err.pack(padx=12, pady=(0, 8))

    def show() -> None:
        row = shown[index]
        frame = session / row["file"]
        photo = ImageTk.PhotoImage(_crop(frame))
        photo_holder["photo"] = photo
        picture.configure(image=photo)
        status.set(f"{index + 1} / {len(shown)}")
        error.set("")
        entry.delete(0, tk.END)
        entry.insert(0, _entry_text(row))
        entry.focus_set()
        entry.icursor(tk.END)

    def commit(text: str) -> None:
        problem = _apply(shown[index], text)
        if problem:
            error.set(problem)
            return
        _save(labels_path, rows)
        if index + 1 < len(shown):
            nonlocal_advance(1)
        else:
            error.set("Last frame saved")

    def nonlocal_advance(step: int) -> None:
        nonlocal index
        index = min(len(shown) - 1, max(0, index + step))
        show()

    def on_return(_event: object) -> str:
        commit(entry.get())
        return "break"

    def on_unreadable(_event: object | None = None) -> None:
        commit("unreadable")

    def on_back(_event: object) -> str:
        nonlocal_advance(-1)
        return "break"

    entry.bind("<Return>", on_return)
    entry.bind("<Alt-Left>", on_back)
    buttons = tk.Frame(root)
    buttons.pack(pady=(0, 12))
    tk.Button(buttons, text="Save", command=lambda: commit(entry.get())).pack(side=tk.LEFT, padx=6)
    tk.Button(buttons, text="Unreadable", command=on_unreadable).pack(side=tk.LEFT, padx=6)
    tk.Button(buttons, text="Back", command=lambda: nonlocal_advance(-1)).pack(side=tk.LEFT, padx=6)

    show()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
