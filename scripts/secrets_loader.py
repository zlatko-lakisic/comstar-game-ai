"""Load gitignored secrets from .cursor/secrets/.reach-enroll."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_reach_enroll() -> dict[str, str]:
    path = repo_root() / ".cursor" / "secrets" / ".reach-enroll"
    if not path.is_file():
        raise FileNotFoundError(f"missing enroll config: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def material_dir() -> Path:
    cfg = load_reach_enroll()
    rel = cfg.get("MATERIAL_DIR", ".cursor/secrets/mtls/comstar-game-ai")
    return repo_root() / rel
