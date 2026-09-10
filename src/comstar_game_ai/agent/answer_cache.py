"""Assert AGENTIC_ANSWER_CACHE is off — silent failure 3.7 / C7."""

from __future__ import annotations

import logging
import os
from typing import Any

_LOGGER = logging.getLogger(__name__)


def assert_answer_cache_disabled(config: dict[str, Any] | None = None) -> None:
    """Fail loudly if the answer cache could short-circuit a director call.

    The same question text in a different board state must never return a cached
    reply. Check env and config; do not rely on configuration being correct.
    """
    env_val = (os.environ.get("AGENTIC_ANSWER_CACHE") or "").strip().lower()
    if env_val in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            "AGENTIC_ANSWER_CACHE is enabled in the environment; "
            "disable it before starting the campaign director"
        )

    if config is not None:
        ao = config.get("ao") if isinstance(config, dict) else None
        if isinstance(ao, dict):
            for key in ("answer_cache", "AGENTIC_ANSWER_CACHE", "agentic_answer_cache"):
                val = ao.get(key)
                if val in (True, 1, "1", "true", "on"):
                    raise RuntimeError(
                        f"ao.{key} enables the answer cache; disable it (C7)"
                    )

    _LOGGER.info("AGENTIC_ANSWER_CACHE asserted disabled")
