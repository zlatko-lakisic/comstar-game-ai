"""Decide the next camera pan from a center-tile map coordinate.

D pans east, A west, W north, S south. A press does not move a fixed
distance. Each step is chosen from the last measured map change for that
key. The center tile is read again after the pan. A seek is finished when
both axes are within ``CLOSE_MAP_UNITS``.
"""

from __future__ import annotations

from dataclasses import dataclass

CLOSE_MAP_UNITS = 3
PROBE_HOLD_S = 0.20
MIN_HOLD_S = 0.08
MAX_HOLD_S = 0.60

_OPPOSITE = {"a": "d", "d": "a", "w": "s", "s": "w"}
# Map y increases north. These signs are the bindings, used until a
# real move replaces them. A probe used to try D and W first, which
# walked the wrong way off the edge of the readable map.
_SIGN = {"d": (1.0, 0.0), "a": (-1.0, 0.0), "w": (0.0, 1.0), "s": (0.0, -1.0)}


@dataclass(frozen=True)
class SeekMove:
    """One pan, or a stop."""

    kind: str
    key: str = ""
    hold_s: float = 0.0


_DEFAULT_SPEED = 45.0


def estimate_after(
    key: str,
    before: tuple[int, int],
    hold_s: float,
    rates: dict[str, tuple[float, float]],
) -> tuple[int, int]:
    """Where a pan should land when the console cannot be read.

    Uses the measured rate for ``key``. An unmeasured key uses the known
    sign at ``_DEFAULT_SPEED`` map units per second, which matched the
    pans that could be read.
    """
    if key in rates and rates[key] != (0.0, 0.0):
        dx, dy = rates[key]
    else:
        sx, sy = _SIGN[key]
        dx, dy = sx * _DEFAULT_SPEED, sy * _DEFAULT_SPEED
    return (
        int(round(before[0] + dx * hold_s)),
        int(round(before[1] + dy * hold_s)),
    )


def close_enough(
    current: tuple[int, int],
    target: tuple[int, int],
    limit: int = CLOSE_MAP_UNITS,
) -> bool:
    return max(abs(target[0] - current[0]), abs(target[1] - current[1])) <= limit


def record_rate(
    rates: dict[str, tuple[float, float]],
    measured: set[str],
    key: str,
    before: tuple[int, int],
    after: tuple[int, int],
    hold_s: float,
) -> bool:
    """Store map units per second for ``key``. A move under 1 unit is ignored."""
    if hold_s <= 0:
        return False
    dx = after[0] - before[0]
    dy = after[1] - before[1]
    if max(abs(dx), abs(dy)) < 1:
        return False
    per_s = (dx / hold_s, dy / hold_s)
    rates[key] = per_s
    measured.add(key)
    opposite = _OPPOSITE[key]
    if opposite not in measured:
        rates[opposite] = (-per_s[0], -per_s[1])
    return True


def choose_move(
    current: tuple[int, int],
    target: tuple[int, int],
    rates: dict[str, tuple[float, float]],
) -> SeekMove:
    """Pick the WASD key that shrinks the error, or a short probe if none is known.

    D is east, A west, W north, S south. The key's measured delta is what
    decides the step, so a yawed camera still gets the key that reduces
    map x or map y.
    """
    if close_enough(current, target):
        return SeekMove("done")
    error_x = target[0] - current[0]
    error_y = target[1] - current[1]
    best_key = ""
    best_gain = 0.0
    measured_rate: tuple[float, float] | None = None
    # A 4-unit y error at a high rate outscores a 26-unit x error, so the
    # seek bobbed north and south and never went west. Once an axis is
    # inside the close limit, only the other axis is moved.
    need_x = abs(error_x) > CLOSE_MAP_UNITS
    need_y = abs(error_y) > CLOSE_MAP_UNITS
    for key, sign in _SIGN.items():
        if key in rates and rates[key] == (0.0, 0.0):
            continue
        dx, dy = rates.get(key, sign)
        if need_x and not need_y and abs(dx) < abs(dy):
            continue
        if need_y and not need_x and abs(dy) < abs(dx):
            continue
        gain = error_x * dx + error_y * dy
        if gain > best_gain:
            best_key = key
            best_gain = gain
            measured_rate = rates[key] if key in rates else None
    if not best_key:
        return SeekMove("stuck")
    if measured_rate is None:
        return SeekMove("move", best_key, PROBE_HOLD_S)
    dx, dy = measured_rate
    if abs(dx) >= abs(dy) and abs(dx) > 1e-6:
        hold = error_x / dx
    elif abs(dy) > 1e-6:
        hold = error_y / dy
    else:
        hold = PROBE_HOLD_S
    if hold <= 0:
        hold = PROBE_HOLD_S
    hold = min(MAX_HOLD_S, max(MIN_HOLD_S, hold))
    return SeekMove("move", best_key, hold)
