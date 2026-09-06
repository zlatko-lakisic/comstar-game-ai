"""Read Rome's shipped string tables.

The game documents its own UI in `data/text/*.txt`: `tooltips.txt` explains what
each element means, `cursor_action_tooltips.txt` is the complete campaign action
vocabulary, `shortcut.txt` names every keyboard shortcut. Reading those is how the
campaign UI atlas gets real names and purposes instead of names invented from
pixels.

The format is Creative Assembly's loc_parser output, and it has two traps that
would corrupt the data silently:

1. **Comments are conditional.** The file header says so outright: "There must be
   a comment on the first line if tag delimiters and comments are included in the
   rest of the file." Ten shipped files — `credits.txt`, `date_format.txt` and
   their localisations — do not declare one, and stripping U+00AC from those would
   mangle content rather than remove comments.
2. **Comments can appear mid-line**, after a value. Rare (one line in
   `shortcut.txt`, two in `strat.txt`) and therefore easy to ship a parser that
   quietly appends "¬ Mid line comment" to a tooltip.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

#: U+00AC NOT SIGN. The header of `shortcut.txt` calls it "whatever character this
#: is at the start", which is as close to a specification as the format gets.
COMMENT_CHAR = "\u00ac"

_ENTRY_RE = re.compile(r"^\s*\{(?P<key>[^}]*)\}(?P<value>.*)$")

#: The tables that describe the campaign map. Ordered most to least specific so a
#: key defined in several tables resolves to the campaign meaning first.
CAMPAIGN_TABLES: tuple[str, ...] = (
    "tooltips",
    "cursor_action_tooltips",
    "strat",
    "diplomacy",
    "event_titles",
    "event_strings",
    "shortcut",
    "shared",
    "expanded",
    "menu_english",
)

_TEXT_DIR_SUFFIX = Path("Contents/Resources/Data/data/text")

_STEAM_LIBRARY_ROOTS = (
    r"C:/Program Files (x86)/Steam/steamapps/common",
    r"C:/Program Files/Steam/steamapps/common",
    r"C:/Steam/steamapps/common",
    r"D:/Steam/steamapps/common",
    r"D:/SteamLibrary/steamapps/common",
    r"E:/Steam/steamapps/common",
    r"E:/SteamLibrary/steamapps/common",
)

_GAME_DIR_NAMES = ("Total War ROME REMASTERED",)


@dataclass(frozen=True)
class StringTable:
    """One parsed string table."""

    name: str
    entries: dict[str, str]
    comments_enabled: bool
    path: Path | None = None

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.entries.get(key, default)

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, key: object) -> bool:
        return key in self.entries


def decode_string_file(raw: bytes) -> str:
    """Decode a shipped text file, which is UTF-16 LE with a BOM.

    Falls back rather than raising: a table that fails to decode should cost one
    table, not the whole atlas.
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_string_table(text: str, *, name: str = "", path: Path | None = None) -> StringTable:
    """Parse loc_parser text into key/value entries."""
    lines = text.replace("\ufeff", "").splitlines()

    # Conditional comments: only honoured when the first line declares one.
    comments_enabled = bool(lines) and lines[0].lstrip().startswith(COMMENT_CHAR)

    entries: dict[str, str] = {}
    last_key: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            last_key = None
            continue
        if comments_enabled and stripped.startswith(COMMENT_CHAR):
            last_key = None
            continue

        match = _ENTRY_RE.match(line)
        if match is None:
            # A bare line continues the previous value: long descriptions in
            # export_buildings and export_advice wrap across lines.
            if last_key is not None:
                continuation = _strip_inline_comment(stripped, comments_enabled)
                if continuation:
                    entries[last_key] = f"{entries[last_key]} {continuation}".strip()
            continue

        key = match.group("key").strip()
        value = _strip_inline_comment(match.group("value"), comments_enabled).strip()
        if not key:
            continue
        # First definition wins; the tables occasionally repeat a key and the
        # earlier one is the one the game shows.
        entries.setdefault(key, value)
        last_key = key

    return StringTable(name=name, entries=entries, comments_enabled=comments_enabled, path=path)


def _strip_inline_comment(value: str, comments_enabled: bool) -> str:
    if not comments_enabled:
        return value
    head, _, _ = value.partition(COMMENT_CHAR)
    return head


def load_string_table(path: str | Path) -> StringTable:
    path = Path(path)
    return parse_string_table(
        decode_string_file(path.read_bytes()), name=path.stem, path=path
    )


def default_text_dir() -> Path | None:
    """Locate the shipped `data/text` directory.

    Explicit configuration wins, then the environment, then a search of the usual
    Steam library locations — the install is not always on C:.
    """
    from comstar_game_ai.shared.config import load_config

    configured = (load_config().get("paths") or {}).get("rome_text")
    if configured:
        candidate = Path(os.path.expandvars(str(configured)))
        if candidate.is_dir():
            return candidate
        _LOGGER.warning("paths.rome_text is set but not a directory: %s", candidate)

    from_env = os.environ.get("COMSTAR_ROME_TEXT")
    if from_env:
        candidate = Path(os.path.expandvars(from_env))
        if candidate.is_dir():
            return candidate

    for root in _STEAM_LIBRARY_ROOTS:
        for game in _GAME_DIR_NAMES:
            candidate = Path(root) / game / _TEXT_DIR_SUFFIX
            if candidate.is_dir():
                return candidate
    return None


def load_campaign_tables(
    text_dir: str | Path | None = None,
    names: tuple[str, ...] = CAMPAIGN_TABLES,
) -> dict[str, StringTable]:
    """Load the campaign-relevant tables. Missing tables are skipped, not fatal."""
    directory = Path(text_dir) if text_dir is not None else default_text_dir()
    if directory is None:
        _LOGGER.warning("Rome text directory not found — the atlas will have no names")
        return {}

    tables: dict[str, StringTable] = {}
    for name in names:
        path = directory / f"{name}.txt"
        if not path.is_file():
            _LOGGER.debug("string table absent: %s", path)
            continue
        try:
            tables[name] = load_string_table(path)
        except Exception as exc:
            _LOGGER.warning("could not read %s: %s", path, exc)
    return tables


def lookup(tables: dict[str, StringTable], key: str) -> tuple[str, str] | None:
    """First (table name, value) for `key`, searching in CAMPAIGN_TABLES order."""
    for name in CAMPAIGN_TABLES:
        table = tables.get(name)
        if table is not None and key in table:
            return name, table.entries[key]
    for name, table in tables.items():
        if key in table:
            return name, table.entries[key]
    return None
