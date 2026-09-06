"""Read Rome's real key bindings from `data/text/descr_shortcuts.txt`.

`shortcut.txt` only holds *descriptions* ("Toggle radar visibility"). The bindings
themselves live in `descr_shortcuts.txt`, which is the file that answers questions
like "how do I zoom the campaign map" (Z and X) or "how do I end the turn"
(Shift+Enter). Reading it means the agent's control vocabulary is the game's own
rather than a guess.

Format:

    keyset moderntw
        strat
            zoom_in     Z                     repeating
            end_turn    ENTER   SHIFT
        end
    end

followed by a top-level `mappings` block that maps each action to the subsystem
handling it (`step_l camera`, `buildings_button hud_show_buildings_tab`).

Four traps worth naming, because each produces plausible-looking wrong output
rather than an error:

1. **The third column is not always a required modifier.** `CTRL` and `SHIFT` are
   requirements, but `ANY`, `NOT_CTRL` and `ALLOW_SHIFT` are *constraints* on the
   modifier state. Reading `step_l A NOT_CTRL` as "press Ctrl+A" would select all
   units instead of panning left.
2. **`NONE` means unbound**, and a lot of actions are `NONE`. They are real
   features with no default key, not parse failures.
3. **Keysets are never closed.** Each section ends with `end`, but the keyset
   itself is closed implicitly by the next top-level keyword — either another
   `keyset` or `mappings`. Waiting for a keyset `end` swallows the mappings block
   into the last keyset as if the handler names were key names.
4. **The `default` keyset has a fourth column** holding an alternate key
   (`step_l LEFT ANY NUM_4`), so the numpad bindings are only visible if that
   column is read. `moderntw` never uses it.

Nesting is read from indent depth: top-level keywords at 0, sections at 1, entries
at 2. A single-token line is otherwise ambiguous, since `mappings` contains both
section names and actions that have no handler.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

COMMENT_CHAR = ";"

#: Third-column values that require a modifier to be held.
REQUIRED_MODIFIERS = {"CTRL", "SHIFT", "ALT", "RALT"}

#: Third-column values that constrain modifier state without requiring one.
MODIFIER_CONSTRAINTS = {"ANY", "NONE", "NOT_CTRL", "NOT_SHIFT", "NOT_ALT", "ALLOW_SHIFT", "ALLOW_CTRL"}

_FLAGS = {"repeating", "hidden", "locked"}

#: Rome's key names to the names this project's input layer uses.
_KEY_NAMES: dict[str, str] = {
    "ENTER": "enter",
    "NUM_ENTER": "enter",
    "ESC": "escape",
    "TAB": "tab",
    "SPACE": "space",
    "BACKSPACE": "backspace",
    "DEL": "delete",
    "INS": "insert",
    "HOME": "home",
    "END": "end",
    "PAGE_UP": "pageup",
    "PAGE_DOWN": "pagedown",
    "EQUALS": "=",
    "MINUS": "-",
    "COMMA": ",",
    "FULL_STOP": ".",
    "SLASH": "/",
    "BACKSLASH": "\\",
    "SEMI_COLON": ";",
    "APOSTROPHE": "'",
    "HASH": "#",
    "OPEN_BRACKET": "[",
    "CLOSE_BRACKET": "]",
    "GRAVE": "`",
    "GRAVE_ACCENT": "`",
    "BACK_APOSTROPHE": "`",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "CRSR_UP": "up",
    "CRSR_DOWN": "down",
    "CRSR_LEFT": "left",
    "CRSR_RIGHT": "right",
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
    "PAUSE": "pause",
    "SCROLL_LOCK": "scrolllock",
    "CAPS_LOCK": "capslock",
    "NUM_LOCK": "numlock",
}


def _translate_key(raw: str) -> str | None:
    """Rome's key name in this project's vocabulary, or None when unbound."""
    key = raw.strip().upper()
    if not key or key == "NONE":
        return None
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    if re.fullmatch(r"F\d{1,2}", key):
        return key.lower()
    if re.fullmatch(r"NUM_\d", key):
        return f"num{key[-1]}"
    if re.fullmatch(r"[A-Z0-9]", key):
        return key.lower()
    _LOGGER.debug("unmapped key name: %s", raw)
    return key.lower()


@dataclass(frozen=True)
class Binding:
    """One action bound to one key, within a keyset and section."""

    keyset: str
    section: str
    action: str
    #: None when the action ships unbound.
    key: str | None
    #: Only set when a modifier must be held. Constraints do not appear here.
    modifier: str | None
    #: The raw third column, kept because constraints carry real meaning.
    modifier_raw: str
    flags: frozenset[str]
    #: Secondary key, used by the `default` keyset for its numpad bindings.
    alternate_key: str | None = None

    @property
    def bound(self) -> bool:
        return self.key is not None or self.held_modifier is not None

    @property
    def repeating(self) -> bool:
        """True when holding the key repeats the action, as with camera movement."""
        return "repeating" in self.flags

    @property
    def hidden(self) -> bool:
        return "hidden" in self.flags

    @property
    def held_modifier(self) -> str | None:
        """The modifier when it *is* the binding rather than a qualifier.

        `cam_speed NONE SHIFT locked` has no key: holding Shift is the whole
        control. Read naively it looks unbound, which would lose the campaign map's
        only speed modifier.
        """
        if self.key is None and self.modifier and "locked" in self.flags:
            return self.modifier
        return None

    @property
    def chord(self) -> str | None:
        """The keystroke to send, e.g. `ctrl+1`, `shift+enter`, `z`."""
        if self.key is None:
            return self.held_modifier
        return f"{self.modifier}+{self.key}" if self.modifier else self.key


@dataclass(frozen=True)
class ShortcutDatabase:
    """Every keyset, plus the action-to-handler map from the global sections."""

    keysets: dict[str, dict[str, tuple[Binding, ...]]]
    #: (section, action) -> handling subsystem, e.g. ("strat", "step_l") -> "camera".
    handlers: dict[tuple[str, str], str]
    path: Path | None = None

    def sections(self, keyset: str) -> tuple[str, ...]:
        return tuple(self.keysets.get(keyset, {}))

    def bindings(self, keyset: str, section: str | None = None) -> tuple[Binding, ...]:
        found = self.keysets.get(keyset, {})
        if section is not None:
            return found.get(section, ())
        return tuple(b for group in found.values() for b in group)

    def find(self, action: str, *, keyset: str | None = None) -> tuple[Binding, ...]:
        """Every binding for an action. Actions recur across sections and keysets."""
        names = (keyset,) if keyset else tuple(self.keysets)
        return tuple(
            b
            for name in names
            for b in self.bindings(name)
            if b.action == action
        )

    def handler(self, section: str, action: str) -> str | None:
        return self.handlers.get((section, action))


def _split(line: str) -> list[str]:
    return [part for part in re.split(r"[\t ]+", line.strip()) if part]


def _depth(line: str) -> int:
    """Nesting level: 0 top-level keyword, 1 section, 2 entry."""
    stripped = line.lstrip("\t")
    tabs = len(line) - len(stripped)
    if tabs:
        return tabs
    spaces = len(line) - len(line.lstrip(" "))
    return spaces // 4


def parse_shortcuts(text: str, *, path: Path | None = None) -> ShortcutDatabase:
    """Parse the binding database."""
    keysets: dict[str, dict[str, tuple[Binding, ...]]] = {}
    handlers: dict[tuple[str, str], str] = {}

    keyset: str | None = None
    in_mappings = False
    section: str | None = None
    current: list[Binding] = []

    def close_section() -> None:
        nonlocal section, current
        if keyset is not None and section is not None:
            # Merge rather than replace: the `default` keyset declares `misc` twice,
            # the second one empty, and replacing would silently drop the first.
            group = keysets.setdefault(keyset, {})
            group[section] = group.get(section, ()) + tuple(current)
        section = None
        current = []

    for raw in text.splitlines():
        line = raw.split(COMMENT_CHAR, 1)[0]
        if not line.strip():
            continue
        parts = _split(line)
        depth = _depth(line)

        if depth == 0:
            # A top-level keyword implicitly closes whatever block was open.
            close_section()
            if parts[0] == "keyset":
                keyset = parts[1] if len(parts) > 1 else "unnamed"
                keysets.setdefault(keyset, {})
                in_mappings = False
            elif parts[0] == "mappings":
                keyset = None
                in_mappings = True
            continue

        if parts[0] == "end":
            close_section()
            continue

        if depth == 1:
            close_section()
            section = parts[0]
            continue

        if section is None:
            continue

        if in_mappings:
            handlers[(section, parts[0])] = parts[1] if len(parts) > 1 else ""
            continue

        if keyset is None:
            continue

        action = parts[0]
        key = _translate_key(parts[1]) if len(parts) > 1 else None
        modifier: str | None = None
        modifier_raw = ""
        alternate: str | None = None
        flags: set[str] = set()

        for extra in parts[2:]:
            token = extra.strip()
            if token.lower() in _FLAGS:
                flags.add(token.lower())
            elif token.upper() in REQUIRED_MODIFIERS:
                modifier = token.lower()
                modifier_raw = token.upper()
            elif token.upper() in MODIFIER_CONSTRAINTS:
                modifier_raw = token.upper()
            elif alternate is None:
                # The `default` keyset's fourth column: an alternate key.
                alternate = _translate_key(token)
            else:
                _LOGGER.debug("unrecognised token %r on %s", token, action)

        current.append(
            Binding(
                keyset=keyset,
                section=section,
                action=action,
                key=key,
                modifier=modifier,
                modifier_raw=modifier_raw,
                flags=frozenset(flags),
                alternate_key=alternate,
            )
        )

    close_section()
    return ShortcutDatabase(keysets=keysets, handlers=handlers, path=path)


def default_shortcuts_path() -> Path | None:
    from comstar_game_ai.game_io.campaign.rome_strings import default_text_dir

    text_dir = default_text_dir()
    if text_dir is None:
        return None
    candidate = text_dir / "descr_shortcuts.txt"
    return candidate if candidate.is_file() else None


def load_shortcuts(path: str | Path | None = None) -> ShortcutDatabase | None:
    """Load the binding database, or None when the install is not present."""
    resolved = Path(path) if path is not None else default_shortcuts_path()
    if resolved is None:
        _LOGGER.warning("descr_shortcuts.txt not found — no authoritative bindings")
        return None
    try:
        # Latin-1 rather than UTF-16: unlike the string tables this one is plain ASCII.
        text = resolved.read_text(encoding="latin-1")
    except OSError as exc:
        _LOGGER.warning("could not read %s: %s", resolved, exc)
        return None
    return parse_shortcuts(text, path=resolved)


#: Campaign-map camera actions, which is what "traverse the map" means mechanically.
#: Panning is defined in `misc` but routed to the camera by the global strat section,
#: so it does not appear in the strat keyset section and must be named explicitly.
CAMERA_ACTIONS: tuple[str, ...] = (
    "step_fwd",
    "step_bck",
    "step_l",
    "step_r",
    "zoom_in",
    "zoom_out",
    "rot_l",
    "rot_r",
    "point_to_north",
    "capital_zoom",
    "cam_speed",
)


def camera_bindings(
    db: ShortcutDatabase, *, keyset: str = "moderntw"
) -> dict[str, Binding]:
    """The traversal controls, resolved across the sections that define them."""
    out: dict[str, Binding] = {}
    for action in CAMERA_ACTIONS:
        for binding in db.find(action, keyset=keyset):
            # Prefer strat, then misc: the same action can be bound per context.
            if action in out and binding.section != "strat":
                continue
            out[action] = binding
    return out


def unbound(db: ShortcutDatabase, *, keyset: str = "moderntw") -> tuple[Binding, ...]:
    """Actions that ship with no key. Real features, available only via the mouse."""
    return tuple(b for b in db.bindings(keyset) if not b.bound)
