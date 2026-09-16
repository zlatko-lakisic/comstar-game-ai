"""Parse ``show_cursorstat`` console / log output into map coordinates."""

from __future__ import annotations

import re

_CURSORSTAT_PATTERNS = (
    re.compile(
        r"(?i)cursor[^0-9\-]*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)"
    ),
    re.compile(
        r"(?i)(?:x|pos(?:ition)?)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*[,;\s]+"
        r"(?:y\s*[:=]?\s*)?(-?\d+(?:\.\d+)?)"
    ),
    re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)"),
)


def parse_cursorstat_text(text: str) -> tuple[float, float] | None:
    """Return the last plausible map (x, y) found in ``text``, or None."""
    found: tuple[float, float] | None = None
    for line in (text or "").splitlines():
        for pat in _CURSORSTAT_PATTERNS:
            m = pat.search(line)
            if m:
                found = (float(m.group(1)), float(m.group(2)))
    return found
