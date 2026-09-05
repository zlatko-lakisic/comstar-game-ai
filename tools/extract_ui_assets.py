#!/usr/bin/env python3
"""Extract the game's own UI art into kb/cards/ as PNGs with alpha preserved.

The install is a better vision corpus than any screenshot source, wiki or our own:
these are the exact pixels the renderer composites, and because the TGAs carry an
alpha channel each one doubles as a shape mask. A screenshot of the same asset has
it already flattened onto a background, so matching against one means re-deriving,
lossily, information that is sitting right here.

Three mod roots ship overlapping art (base, Barbarian Invasion, Alexander) and each
ships its units twice -- Remastered's own art plus the 2004 originals under
*_classic, which the game will draw instead when the classic UI toggle is on. Both
are extracted because either may be what ends up on screen.

    python tools/extract_ui_assets.py                  # to kb/cards/
    python tools/extract_ui_assets.py --only ui        # UI chrome only, skip units
    python tools/extract_ui_assets.py --dry-run

Writes an index.json joining every unit card to its export_descr_unit.txt entry, so
a card can be named and its stats looked up rather than merely matched.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

DEFAULT_INSTALL = (
    r"C:\Program Files (x86)\Steam\steamapps\common"
    r"\Total War ROME REMASTERED\Contents\Resources\Data"
)

# Mod roots, in precedence order. A key present in several is attributed to the
# first, which keeps base-game names from being relabelled as expansion content.
MOD_ROOTS = (("base", ""), ("bi", "bi"), ("alexander", "alexander"))

# Per-faction unit art. The same key recurs across faction directories with
# different colouring, so faction is part of a card's identity, not a duplicate.
UNIT_DIRS = ("units", "units_classic", "unit_info", "unit_info_classic")

# Flat UI chrome. cursors and messages are the valuable ones: both join to string
# tables we already parse, which turns an image match into a known game concept.
UI_DIRS = (
    "cursors",
    "buttons",
    "building_icons",
    "faction_icons",
    "icons",
    "pips",
    "indicators",
    "messages",
    "wonders",
    "ancillaries_cards",
    "family_tree",
    "logos",
    "resources",
)


def read_game_text(path):
    """Decode a game text file, which may be UTF-16 with or without a BOM."""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_edu(path):
    """Yield {type, dictionary, category, class} per unit in an export_descr_unit.txt.

    Only the identifying fields are read. A full stat parse belongs with the rest of
    the unit model, not in an image extractor.
    """
    fields = ("dictionary", "category", "class", "soldier")
    entries, cur = [], None
    for line in read_game_text(path).splitlines():
        stripped = line.split(";")[0].strip()
        if not stripped:
            continue
        head = re.match(r"^type\s+(.+)$", stripped)
        if head:
            if cur:
                entries.append(cur)
            cur = {"type": head.group(1).strip()}
            continue
        if cur is None:
            continue
        for field in fields:
            match = re.match(r"^%s\s+(.+)$" % field, stripped)
            if match:
                cur.setdefault(field, match.group(1).split(",")[0].strip())
    if cur:
        entries.append(cur)
    return entries


def build_edu_index(install):
    """Map every name a card file might use to the unit entry behind it.

    Card stems match either the dictionary key or the type with spaces underscored;
    both are indexed. Roughly a quarter match neither -- art the install still ships
    but no unit references -- and those are kept, just unnamed.
    """
    index, per_mod = {}, {}
    for mod, sub in MOD_ROOTS:
        path = os.path.join(install, sub, "data", "export_descr_unit.txt")
        if not os.path.exists(path):
            continue
        entries = parse_edu(path)
        per_mod[mod] = len(entries)
        for entry in entries:
            record = dict(entry, mod=mod)
            for alias in (entry.get("dictionary"), entry["type"].replace(" ", "_")):
                if alias:
                    index.setdefault(alias, record)
    return index, per_mod


def convert(src, dest, dry_run):
    """Write a TGA as PNG, preserving alpha. Returns (width, height, mode)."""
    from PIL import Image

    with Image.open(src) as im:
        if im.mode not in ("RGBA", "LA"):
            im = im.convert("RGBA")
        size, mode = im.size, im.mode
        if not dry_run:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            im.save(dest, "PNG", optimize=True)
    return size[0], size[1], mode


def iter_unit_art(install):
    """Yield (mod, art, faction, stem, unit_key, kind, path) per unit image.

    Cards are prefixed '#', portraits suffixed '_info', and the install does not
    keep them strictly separate -- several unit_info directories also hold a card.
    So `kind` follows the filename rather than the directory, and `stem` is kept
    verbatim: collapsing it to the join key would have two files in one directory
    claim one output name, silently discarding whichever was written first.
    """
    for mod, sub in MOD_ROOTS:
        for art in UNIT_DIRS:
            root = os.path.join(install, sub, "data", "ui", art)
            if not os.path.isdir(root):
                continue
            for faction in sorted(os.listdir(root)):
                fdir = os.path.join(root, faction)
                if not os.path.isdir(fdir):
                    continue
                for name in sorted(os.listdir(fdir)):
                    if not name.lower().endswith(".tga"):
                        continue
                    stem = os.path.splitext(name)[0].lstrip("#")
                    if stem.endswith("_info"):
                        unit_key, kind = stem[: -len("_info")], "portrait"
                    else:
                        unit_key, kind = stem, "card"
                    yield mod, art, faction, stem, unit_key, kind, os.path.join(fdir, name)


def iter_ui_art(install):
    """Yield (mod, category, relative_name, path) for flat UI chrome."""
    for mod, sub in MOD_ROOTS:
        for category in UI_DIRS:
            root = os.path.join(install, sub, "data", "ui", category)
            if not os.path.isdir(root):
                continue
            for dirpath, _, names in os.walk(root):
                for name in sorted(names):
                    if not name.lower().endswith((".tga", ".png")):
                        continue
                    rel = os.path.relpath(os.path.join(dirpath, name), root)
                    yield mod, category, rel, os.path.join(dirpath, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", default=DEFAULT_INSTALL)
    ap.add_argument("--out", default=os.path.join("kb", "cards"))
    ap.add_argument("--only", choices=("units", "ui"), help="extract one half only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.install):
        print("install not found: %s" % args.install, file=sys.stderr)
        return 2

    edu, per_mod = build_edu_index(args.install)
    print("export_descr_unit.txt: %s" % ", ".join(
        "%s=%d" % (m, n) for m, n in per_mod.items()) or "none found")
    print("  %d distinct lookup names\n" % len(edu))

    units, ui = [], []
    art_counts, matched, unmatched = Counter(), set(), set()

    if args.only != "ui":
        for mod, art, faction, stem, unit_key, kind, src in iter_unit_art(args.install):
            dest = os.path.join(args.out, "units", mod, art, faction, stem + ".png")
            width, height, mode = convert(src, dest, args.dry_run)
            entry = edu.get(unit_key)
            (matched if entry else unmatched).add(unit_key)
            art_counts[(mod, art)] += 1
            units.append({
                "unit_key": unit_key,
                "kind": kind,
                "mod": mod,
                "art": art,
                "faction": faction,
                "path": os.path.relpath(dest, args.out).replace("\\", "/"),
                "width": width,
                "height": height,
                "mode": mode,
                "edu_type": entry["type"] if entry else None,
                "edu_category": entry.get("category") if entry else None,
                "edu_class": entry.get("class") if entry else None,
                "edu_mod": entry["mod"] if entry else None,
            })

    if args.only != "units":
        for mod, category, rel, src in iter_ui_art(args.install):
            stem = os.path.splitext(rel)[0].replace("\\", "/")
            dest = os.path.join(args.out, "ui", mod, category, stem + ".png")
            width, height, mode = convert(src, dest, args.dry_run)
            art_counts[(mod, category)] += 1
            ui.append({
                "name": stem,
                "mod": mod,
                "category": category,
                "path": os.path.relpath(dest, args.out).replace("\\", "/"),
                "width": width,
                "height": height,
                "mode": mode,
            })

    for (mod, art), count in sorted(art_counts.items()):
        print("  %-10s %-20s %5d" % (mod, art, count))

    total = len(units) + len(ui)
    print("\nunit images: %d   ui images: %d   total: %d" % (len(units), len(ui), total))
    if units:
        named = len(matched)
        print("distinct unit keys: %d named via EDU, %d unnamed (%.0f%% named)" % (
            named, len(unmatched), 100.0 * named / max(1, named + len(unmatched))))

    index = {
        "install": args.install,
        "edu_entries_per_mod": per_mod,
        "counts": {"unit_images": len(units), "ui_images": len(ui), "total": total},
        "unit_keys_named": sorted(matched),
        "unit_keys_unnamed": sorted(unmatched),
        "units": units,
        "ui": ui,
    }
    if not args.dry_run:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "index.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=1, sort_keys=False)
        print("\nwrote %s" % path)
    else:
        print("\ndry run -- nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
