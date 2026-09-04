"""Overlay files are packed and sent over the Reach websocket as JSON.

An unquoted ISO date in any overlay YAML parses as datetime.date, which json.dumps
refuses, and the failure surfaces far from its cause: session registration dies and
every agent call reports 'Object of type date is not JSON serializable'.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
import yaml

OVERLAY_ROOT = Path(__file__).resolve().parents[2] / "overlay"
OVERLAY_YAML = sorted(OVERLAY_ROOT.rglob("*.yaml"))


def _non_json_values(node: object, path: str = "$") -> list[str]:
    """Paths of values json.dumps cannot encode, with their type."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                found.append(f"{path}.<key {key!r}> is {type(key).__name__}")
            found.extend(_non_json_values(value, f"{path}.{key}"))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            found.extend(_non_json_values(value, f"{path}[{index}]"))
    elif not isinstance(node, (str, int, float, bool, type(None))):
        found.append(f"{path} is {type(node).__name__} ({node!r})")
    return found


def test_overlay_root_has_yaml_to_check():
    assert OVERLAY_YAML, f"no overlay YAML found under {OVERLAY_ROOT}"


@pytest.mark.parametrize("path", OVERLAY_YAML, ids=lambda p: p.name)
def test_overlay_yaml_is_json_serializable(path: Path):
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    offenders = _non_json_values(parsed)
    assert not offenders, f"{path.name} holds values JSON cannot encode: {offenders}"
    json.dumps(parsed)


def _dates(node: object, path: str = "$") -> list[str]:
    """Paths of date/datetime values, which YAML produces from unquoted ISO dates."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(_dates(value, f"{path}.{key}"))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            found.extend(_dates(value, f"{path}[{index}]"))
    elif isinstance(node, (datetime.date, datetime.datetime)):
        found.append(f"{path} = {node!r}")
    return found


@pytest.mark.parametrize("path", OVERLAY_YAML, ids=lambda p: p.name)
def test_overlay_yaml_dates_are_quoted_strings(path: Path):
    """Guards the specific slip: `verified: 2026-09-04` instead of a quoted string."""
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert not _dates(parsed), f"{path.name} has unquoted date values: {_dates(parsed)}"


def test_packed_overlay_is_json_serializable():
    """Highest-fidelity check: this is the structure the Reach bridge sends."""
    from ao_reach.overlay_packer import OverlayPacker

    pack = OverlayPacker().pack(OVERLAY_ROOT)
    for part in (pack.agents, getattr(pack, "skills", None), getattr(pack, "mcps", None)):
        if part is None:
            continue
        offenders = _non_json_values(part)
        assert not offenders, f"packed overlay holds unencodable values: {offenders}"
        json.dumps(part)


def test_detects_an_unquoted_date(tmp_path: Path):
    """The check itself must fail on the shape that broke the run."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: sample\nfacts:\n  - verified: 2026-09-04\n", encoding="utf-8")
    parsed = yaml.safe_load(bad.read_text(encoding="utf-8"))
    assert isinstance(parsed["facts"][0]["verified"], datetime.date)
    assert _non_json_values(parsed)
    with pytest.raises(TypeError):
        json.dumps(parsed)
