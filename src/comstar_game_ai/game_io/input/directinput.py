"""DirectInput-friendly input for games (pydirectinput)."""

from __future__ import annotations

import logging
import time

_LOGGER = logging.getLogger(__name__)

try:
    import pydirectinput as _pdi

    _pdi.FAILSAFE = False
    _pdi.PAUSE = 0.02
    _HAS_PDI = True
except ImportError:
    _pdi = None  # type: ignore[assignment]
    _HAS_PDI = False


def directinput_available() -> bool:
    return _HAS_PDI


def hotkey_shift_enter(*, pause_s: float = 0.08) -> bool:
    if not _HAS_PDI:
        return False
    try:
        _pdi.keyDown("shiftleft")
        time.sleep(pause_s)
        _pdi.press("enter")
        time.sleep(pause_s)
        _pdi.keyUp("shiftleft")
        return True
    except Exception as exc:
        _LOGGER.warning("pydirectinput shift+enter failed: %s", exc)
        return False


def tap_key(key: str, *, pause_s: float = 0.05) -> bool:
    if not _HAS_PDI:
        return False
    try:
        _pdi.press(key)
        time.sleep(pause_s)
        return True
    except Exception as exc:
        _LOGGER.warning("pydirectinput tap %r failed: %s", key, exc)
        return False


def click_screen(x: int, y: int, *, clicks: int = 1) -> bool:
    if not _HAS_PDI:
        return False
    try:
        _pdi.moveTo(x, y)
        time.sleep(0.05)
        for _ in range(clicks):
            _pdi.click(x, y)
            time.sleep(0.05)
        return True
    except Exception as exc:
        _LOGGER.warning("pydirectinput click failed: %s", exc)
        return False
