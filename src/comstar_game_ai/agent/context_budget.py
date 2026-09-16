"""Composed-prompt length vs Ollama num_ctx (F4).

Ollama truncates from the front of the prompt when the context window is
exceeded, silently. ROLE / OBJECTIVES are then the first content dropped —
exactly the failure mode where a model redefines "candidates".
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from comstar_game_ai.shared.config import repo_root

_LOGGER = logging.getLogger(__name__)

#: Rough token estimate when no real tokenizer is available (chars / 4).
_CHARS_PER_TOKEN = 4.0

#: Safety margin: composed prompt must fit under num_ctx with this headroom.
DEFAULT_MARGIN_TOKENS = 512

#: Fallback when the provider YAML does not declare num_ctx.
DEFAULT_NUM_CTX = 8192


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN)) if text else 0


def campaign_director_yaml_path() -> Path:
    return repo_root() / "overlay" / "agent_providers" / "campaign_director.yaml"


def read_provider_num_ctx(path: Path | None = None) -> int:
    target = path or campaign_director_yaml_path()
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw = data.get("num_ctx")
    if raw is None and isinstance(data.get("options"), dict):
        raw = data["options"].get("num_ctx")
    try:
        return int(raw) if raw is not None else DEFAULT_NUM_CTX
    except (TypeError, ValueError):
        return DEFAULT_NUM_CTX


def read_provider_temperature(path: Path | None = None) -> float | None:
    target = path or campaign_director_yaml_path()
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw = data.get("temperature")
    if raw is None and isinstance(data.get("options"), dict):
        raw = data["options"].get("temperature")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def assert_num_ctx_sufficient(
    *,
    composed_prompt: str,
    num_ctx: int | None = None,
    margin_tokens: int = DEFAULT_MARGIN_TOKENS,
) -> dict[str, Any]:
    """Fail loudly at startup / pre-call if the window cannot hold the prompt."""
    ctx = int(num_ctx if num_ctx is not None else read_provider_num_ctx())
    tokens = estimate_tokens(composed_prompt)
    needed = tokens + int(margin_tokens)
    info = {
        "composed_tokens_est": tokens,
        "num_ctx": ctx,
        "margin_tokens": int(margin_tokens),
        "needed": needed,
    }
    if needed > ctx:
        raise RuntimeError(
            f"campaign director num_ctx={ctx} is too small for composed prompt "
            f"~{tokens} tokens (+{margin_tokens} margin); raise num_ctx or shrink the brief"
        )
    return info


def log_prompt_budget(
    *,
    turn: int,
    question_id: str,
    composed_prompt: str,
    num_ctx: int | None = None,
) -> dict[str, Any]:
    ctx = int(num_ctx if num_ctx is not None else read_provider_num_ctx())
    tokens = estimate_tokens(composed_prompt)
    info = {
        "turn": turn,
        "question_id": question_id,
        "composed_tokens_est": tokens,
        "num_ctx": ctx,
        "chars": len(composed_prompt),
    }
    _LOGGER.info(
        "turn %s prompt budget: composed_tokens_est=%s num_ctx=%s question_id=%s",
        turn,
        tokens,
        ctx,
        question_id,
    )
    return info


def max_composed_length_sample(
    *,
    backstory: str,
    payload_text: str,
    question_text: str,
) -> str:
    """What the model actually sees: stable backstory + turn question + payload."""
    return f"{backstory}\n\n{question_text}\n\n{payload_text}"
