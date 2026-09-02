"""Shared configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or repo_root() / "config" / "default.yaml"
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    local = repo_root() / "config" / "local.yaml"
    if local.is_file():
        with local.open(encoding="utf-8") as fh:
            local_data = yaml.safe_load(fh) or {}
        data = _deep_merge(data, local_data)
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def mtls_material_path(config: dict[str, Any] | None = None) -> Path:
    cfg = config or load_config()
    rel = cfg["ao"]["mtls_material_dir"]
    return repo_root() / rel
