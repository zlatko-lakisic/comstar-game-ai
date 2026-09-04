"""Synthetic-image tests for campaign UI classification."""

from __future__ import annotations

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.orders import CampaignPlanner
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, classify_campaign_image
from comstar_game_ai.game_io.state_machine import GameState, GameStateDetector
from comstar_game_ai.agent.belief.entities import Character, ExistenceStatus, Settlement
from comstar_game_ai.agent.belief.store import BeliefStore


def _map_image(w: int = 320, h: int = 200) -> Image.Image:
    img = Image.new("RGB", (w, h), (40, 80, 40))
    px = img.load()
    for y in range(h):
        for x in range(w):
            # High-variance terrain: greens / browns / blues
            r = (x * 17 + y * 3) % 90
            g = 70 + (x * 11 + y * 13) % 120
            b = 30 + (x * 5 + y * 19) % 80
            px[x, y] = (r, g, b)
    return img


def _modal_image(w: int = 320, h: int = 200) -> Image.Image:
    img = Image.new("RGB", (w, h), (20, 18, 16))
    draw = ImageDraw.Draw(img)
    draw.rectangle((int(w * 0.28), int(h * 0.20), int(w * 0.72), int(h * 0.80)), fill=(198, 168, 118))
    return img


def _pause_image(w: int = 320, h: int = 200) -> Image.Image:
    return Image.new("RGB", (w, h), (18, 18, 20))


def test_classify_map():
    result = classify_campaign_image(_map_image())
    assert result.mode == CampaignUiMode.CAMPAIGN_MAP
    assert result.center_variance >= 0.005


def test_classify_modal():
    result = classify_campaign_image(_modal_image())
    assert result.mode == CampaignUiMode.MODAL
    assert result.parchment_ratio >= 0.12


def test_classify_pause():
    result = classify_campaign_image(_pause_image())
    assert result.mode == CampaignUiMode.PAUSE


def _dim_night_map(w: int = 320, h: int = 200) -> Image.Image:
    """Winter/night stratmap: dim, nearly flat centre under a lit HUD frame."""
    img = Image.new("RGB", (w, h), (20, 30, 25))
    px = img.load()
    for y in range(h):
        for x in range(w):
            # Coarse night terrain: shadowed hills against dim water, so the centre
            # keeps real structure (variance ~0.003) at a low overall luminance.
            block = ((x // 24) + (y // 20)) % 3
            base = (10, 16, 14) if block == 0 else ((28, 40, 30) if block == 1 else (50, 66, 56))
            px[x, y] = (
                base[0] + (x * 3 + y) % 10,
                base[1] + (x + y * 3) % 12,
                base[2] + (x + y) % 8,
            )
    draw = ImageDraw.Draw(img)
    for box in ((0, 0, w, int(h * 0.06)), (0, int(h * 0.94), w, h)):
        draw.rectangle(box, fill=(150, 140, 120))
    return img


def test_dim_night_map_is_still_the_campaign_map():
    """A dark winter camera used to fall through to unknown and stall the turn."""
    result = classify_campaign_image(_dim_night_map())
    assert result.mode == CampaignUiMode.CAMPAIGN_MAP
    assert result.center_luminance < 0.18


def test_dim_map_still_allows_orders():
    det = GameStateDetector()
    det.state = GameState.CAMPAIGN_MAP
    det.apply_ui_classification(classify_campaign_image(_dim_night_map()))
    assert det.allows_campaign_orders()


def test_black_capture_is_unknown_and_does_not_block_map():
    black = Image.new("RGB", (320, 200), (0, 0, 0))
    result = classify_campaign_image(black)
    assert result.mode == CampaignUiMode.UNKNOWN
    det = GameStateDetector()
    det.state = GameState.CAMPAIGN_MAP
    det.apply_ui_classification(result)
    assert det.state == GameState.CAMPAIGN_MAP
    assert det.allows_campaign_orders()


def test_apply_ui_sets_modal_and_blocks_orders():
    det = GameStateDetector()
    det.state = GameState.CAMPAIGN_MAP
    det.apply_ui_classification(classify_campaign_image(_modal_image()))
    assert det.state == GameState.CAMPAIGN_MODAL
    assert not det.allows_campaign_orders()


def test_planner_no_coords_is_observe_only():
    planner = CampaignPlanner()
    orders = planner.plan(BeliefStore())
    cmds = [o.command for o in orders]
    assert cmds[0].startswith("halt_ai")
    assert "list_characters" in cmds
    assert cmds[-1] == "run_ai"
    assert not any(o.kind == "move_character" for o in orders)


def test_planner_moves_one_tile_when_coords_known():
    store = BeliefStore()
    store.update(
        Character(
            entity_id="flavius",
            provenance="test",
            existence=ExistenceStatus.OBSERVED_PRESENT,
            name="Flavius Julius",
            faction="julii",
            x=10,
            y=10,
        )
    )
    store.update(
        Settlement(
            entity_id="arretium",
            provenance="test",
            existence=ExistenceStatus.OBSERVED_PRESENT,
            region="Etruria",
            owner="julii",
            x=12,
            y=11,
        )
    )
    planner = CampaignPlanner()
    moves = [o for o in planner.plan(store) if o.kind == "move_character"]
    assert len(moves) == 1
    assert "Flavius Julius" in moves[0].command
    assert "11,11" in moves[0].command
