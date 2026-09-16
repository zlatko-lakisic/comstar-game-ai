"""One-shot: dump camera-related descr_shortcuts bindings."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.rome_shortcuts import (
    CAMERA_ACTIONS,
    camera_bindings,
    load_shortcuts,
)


def main() -> None:
    db = load_shortcuts()
    if db is None:
        print("no descr_shortcuts.txt")
        return
    print("path", db.path)
    cams = camera_bindings(db)
    for action in CAMERA_ACTIONS:
        binding = cams.get(action)
        if binding is None:
            found = db.find(action)
            print(
                f"{action:20} MISSING "
                f"find={[(x.section, x.key, x.bound) for x in found[:4]]}"
            )
            continue
        print(
            f"{action:20} section={binding.section} key={binding.key!r} "
            f"mod={binding.modifier!r} chord={binding.chord!r} "
            f"bound={binding.bound} repeating={binding.repeating}"
        )
    print("--- related ---")
    seen: set[str] = set()
    for binding in db.bindings("moderntw"):
        name = binding.action.lower()
        if not any(
            token in name
            for token in ("tilt", "pitch", "rot", "zoom", "north", "cam", "angle", "view")
        ):
            continue
        if binding.action in seen:
            continue
        seen.add(binding.action)
        for hit in db.find(binding.action, keyset="moderntw"):
            print(
                f"{hit.action:24} section={hit.section:8} "
                f"key={hit.key!r:12} chord={hit.chord!r} bound={hit.bound}"
            )


if __name__ == "__main__":
    main()
