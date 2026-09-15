"""Cross-process Ada yield lock — actuation holds Ada; director waits for release.

Ada's GPU broker runs one request at a time across the whole install. Process A
(map-target vision during a march) must not share the slot with the campaign
director. Actuation writes this lock for the vision+click window; deliberation
waits for release before every AO call so each director turn still completes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_LOGGER = logging.getLogger(__name__)

LOCK_NAME = "ada_yield.lock"
DEFAULT_LOCK_PATH = Path("data/runtime") / LOCK_NAME


def lock_path() -> Path:
    return DEFAULT_LOCK_PATH


def is_held() -> bool:
    return lock_path().is_file()


def wait_until_released(*, timeout_s: float = 600.0, poll_s: float = 0.5) -> bool:
    """Block until the yield lock is gone, or ``timeout_s`` elapses.

    Returns True when Ada is free for a director call. False means the holder
    never released — caller should not skip the turn silently.
    """
    deadline = time.time() + max(0.0, float(timeout_s))
    if not is_held():
        return True
    _LOGGER.info("ada yield: waiting for release (timeout %.0fs)", timeout_s)
    while time.time() < deadline:
        if not is_held():
            _LOGGER.info("ada yield: released — director may proceed")
            return True
        time.sleep(max(0.05, float(poll_s)))
    _LOGGER.warning("ada yield: still held after %.0fs", timeout_s)
    return False


def acquire(*, holder: str, reason: str = "") -> None:
    """Create the lock file. Idempotent for the same process holder."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "holder": holder,
        "reason": reason,
        "pid": os.getpid(),
        "ts": time.time(),
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    _LOGGER.info("ada yield acquired holder=%s reason=%s", holder, reason or "-")


def release(*, holder: str | None = None) -> None:
    path = lock_path()
    if not path.is_file():
        return
    if holder is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if str(data.get("holder") or "") not in {"", holder}:
                _LOGGER.warning(
                    "ada yield release skipped — held by %s not %s",
                    data.get("holder"),
                    holder,
                )
                return
        except (OSError, json.JSONDecodeError):
            pass
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        # Python < 3.8 missing_ok — we are on 3.11+, keep for clarity.
        if path.exists():
            path.unlink()
    _LOGGER.info("ada yield released holder=%s", holder or "-")


@contextmanager
def held(*, holder: str, reason: str = "") -> Iterator[None]:
    acquire(holder=holder, reason=reason)
    try:
        yield
    finally:
        release(holder=holder)
