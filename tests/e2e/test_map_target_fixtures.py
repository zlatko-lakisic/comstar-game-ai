"""Map-target vision channel + fixture screenshots — no Ada required.

Uses the whole-screen Julii frames under tests/fixtures/frames/map_targets/
(annotated in manifest.json from live sweep captures). The channel test checks
the prompt/schema/parser; the fixture tests check that annotated Segesta points
are usable as click targets for MarchDirector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from comstar_game_ai.agent.reach import director as agent_director
from comstar_game_ai.agent.reach.session import ReachSession
from comstar_game_ai.game_io.campaign.map_target_vision import (
    MapTargetHit,
    bearing_quadrant,
    build_map_target_prompt,
    locate_from_manifest,
    map_target_vision_schema,
    parse_map_target_result,
)
from comstar_game_ai.game_io.campaign.march import MarchDirector
from comstar_game_ai.game_io.campaign.combat import StackSelection
from tests.e2e.test_agent_channels import RecordingBridge

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "frames" / "map_targets"
MANIFEST_PATH = FIXTURES / "manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _session(bridge: RecordingBridge) -> ReachSession:
    return ReachSession(bridge=bridge, enable_game_query=False)


def _answer(*, found: bool = True) -> str:
    return json.dumps(
        {
            "found": found,
            "label": "Segesta",
            "region": "Liguria",
            "colour": "green",
            "confidence": 0.85 if found else 0.0,
            "standing": "at_war" if found else "unknown",
            "reason": "green SEGESTA plaque" if found else "not visible",
        }
    )


@pytest.mark.asyncio
async def test_map_target_vision_is_asked_on_the_json_channel_with_an_image():
    bridge = RecordingBridge(_answer())
    images = [{"mime_type": "image/jpeg", "data": "abc"}]
    text = await agent_director.call_map_target_vision(
        _session(bridge),
        text=build_map_target_prompt(label="Segesta", hint_quadrant="left"),
        question_id="map-segesta",
        images=images,
    )

    frame = bridge.frame
    assert frame["agent_provider_id"] == "client.map_target_vision"
    assert frame["response_format"] == {"type": "json_object"}
    assert frame["images"] == images
    assert "Segesta" in frame["text"]
    schema = frame["json_schema"]
    assert schema["required"] == ["found", "label", "reason"]
    assert "x_norm" not in schema["properties"]
    assert "y_norm" not in schema["properties"]
    assert "x" not in schema["properties"]
    assert "y" not in schema["properties"]
    hit = parse_map_target_result(text, expected_label="Segesta")
    assert hit is not None and hit.found
    assert hit.click_norm is None
    assert hit.colour == "green"
    assert "Do NOT report coordinates" in frame["text"]
    assert "x_norm" not in frame["text"]
    assert "y_norm" not in frame["text"]


def test_map_target_schema_matches_module():
    assert agent_director.map_target_vision_schema() == map_target_vision_schema()


def test_bearing_quadrant_for_segesta_west_of_flavius():
    # Map: Segesta west/north of Flavius → screen left (and up).
    assert "left" in bearing_quadrant(from_x=100, from_y=100, to_x=90, to_y=110)


@pytest.mark.parametrize("fixture_name", sorted(_manifest().keys()))
def test_manifest_oracle_locates_segesta_on_each_fixture(fixture_name: str):
    manifest = _manifest()
    path = FIXTURES / fixture_name
    assert path.is_file(), f"missing fixture {path}"
    image = Image.open(path)
    assert image.size[0] >= 640 and image.size[1] >= 360

    entry = manifest[fixture_name]
    hit = locate_from_manifest(
        fixture_name=fixture_name, label="Segesta", manifest=manifest
    )
    assert hit.found
    assert hit.click_norm is not None
    assert abs(hit.x_norm - float(entry["x_norm"])) < 1e-6
    assert abs(hit.y_norm - float(entry["y_norm"])) < 1e-6

    # Annotated point must sit inside the image (sanity for the crop we verified).
    w, h = image.size
    px, py = int(hit.x_norm * w), int(hit.y_norm * h)
    assert 0 <= px < w and 0 <= py < h


@pytest.mark.parametrize("fixture_name", sorted(_manifest().keys()))
def test_march_clicks_manifest_segesta_when_vision_and_glyph_agree(
    fixture_name: str, monkeypatch: pytest.MonkeyPatch
):
    """End-to-end march path: fixture frame → oracle locate → glyph → click."""
    manifest = _manifest()
    entry = manifest[fixture_name]
    frame = Image.open(FIXTURES / fixture_name)
    expected = (float(entry["x_norm"]), float(entry["y_norm"]))
    clicks: list[tuple[int, int]] = []
    baseline, sword = 1001, 2002
    handle = {"v": baseline}

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            # Within radius of annotated Segesta → sword glyph.
            nx, ny = x / 1000.0, y / 1000.0
            if abs(nx - expected[0]) < 0.08 and abs(ny - expected[1]) < 0.08:
                handle["v"] = sword
            else:
                handle["v"] = baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x, y))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            return True

        def right_click_client_norm(self, hwnd, x, y, dwell_ms=0):
            clicks.append((int(x * 1000), int(y * 1000)))
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

    def locate(image: Image.Image, label: str) -> MapTargetHit:
        assert image.size == frame.size
        return locate_from_manifest(
            fixture_name=fixture_name, label=label, manifest=manifest
        )

    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.combat.client_norm_to_screen",
        lambda hwnd, x, y: (int(x * 1000), int(y * 1000)),
    )
    monkeypatch.setattr(
        "comstar_game_ai.game_io.campaign.besiege_actuation.read_cursor_handle",
        lambda: handle["v"],
    )

    director = MarchDirector(
        hwnd=1,
        controller=FakeController(),
        capture=lambda: frame,
        cursor_handle=lambda: handle["v"],
        to_screen=lambda x, y: (int(x * 1000), int(y * 1000)),
        sleep=lambda _s: None,
        hover_dwell_s=0.0,
        order_settle_s=0.0,
        locate_target=locate,
        map_vision_min_confidence=0.55,
    )
    director.acquire_any_stack = lambda preferred_row=None: StackSelection(  # type: ignore[method-assign]
        unit_cards=5, safe_to_attack=True, reason="fixture"
    )
    director._combat_director = lambda: type(  # type: ignore[method-assign]
        "CD",
        (),
        {
            "selected_stack": lambda self=None: StackSelection(
                unit_cards=5, safe_to_attack=True, reason="fixture"
            )
        },
    )()

    outcome = director.march(
        from_x=100,
        from_y=100,
        to_x=90,
        to_y=110,
        character_name="Flavius Julius",
        target_label="Segesta",
    )

    assert outcome.ordered
    assert outcome.vision_used
    assert outcome.cursor_changed
    assert outcome.click_norm is not None
    assert abs(outcome.click_norm[0] - expected[0]) < 0.01
    assert abs(outcome.click_norm[1] - expected[1]) < 0.01
    assert clicks, "expected a destination click"
