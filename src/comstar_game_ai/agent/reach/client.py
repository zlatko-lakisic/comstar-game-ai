"""AO Reach client helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ao_reach.mtls import ReachMtlsConfig, load_reach_mtls_material
from ao_reach.session_bridge import probe_health

from comstar_game_ai.shared.config import load_config, mtls_material_path


def reach_mtls_config(config: dict[str, Any] | None = None) -> ReachMtlsConfig:
    cfg = config or load_config()
    material_dir = mtls_material_path(cfg)
    return ReachMtlsConfig(material_dir=str(material_dir))


def load_mtls_material(config: dict[str, Any] | None = None):
    return load_reach_mtls_material(reach_mtls_config(config))


async def check_ada_health(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    base_url = cfg["ao"]["base_url"]
    mtls = reach_mtls_config(cfg)
    return await probe_health(base_url, mtls=mtls)
