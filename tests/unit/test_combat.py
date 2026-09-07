"""Combat director: what it refuses, and what it does once the game agrees."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.combat import (
    AUTO_RESOLVE_BUTTON,
    CombatDirector,
    battle_deployment_present,
)

LAND_CURSOR = 111
SWORD_CURSOR = 222


def army_hud_image(card_count: int, *, size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Map frame with `card_count` selected unit cards in the bottom-centre strip."""
    image = Image.new("RGB", size, (20, 40, 20))
    draw = ImageDraw.Draw(image)
    width, height = size
    x0, y0, y1 = int(width * 0.25), int(height * 0.84), int(height * 0.96)
    for index in range(card_count):
        left = x0 + index * 86
        draw.rectangle((left, y0, left + 76, y1), fill=(180, 140, 90))
    return image


def battle_panel_image(*, size: tuple[int, int] = (1920, 1080)) -> Image.Image:
    """Battle Deployment: cream panel spanning 0.16-0.83, top edge at 0.35."""
    image = Image.new("RGB", size, (24, 30, 26))
    width, height = size
    ImageDraw.Draw(image).rectangle(
        (int(width * 0.16), int(height * 0.35), int(width * 0.83), int(height * 0.88)),
        fill=(220, 205, 170),
    )
    return image


@dataclass
class FakeController:
    """Records what would have been sent, so intent can be asserted without Rome."""

    clicks_norm: list[tuple[float, float]] = field(default_factory=list)
    screen_clicks: list[tuple[int, int]] = field(default_factory=list)
    moves: list[tuple[int, int]] = field(default_factory=list)
    chords: list[tuple[str, str]] = field(default_factory=list)

    def click_client_norm(self, _hwnd, x_norm, y_norm, *, dwell_ms=30):
        self.clicks_norm.append((round(x_norm, 3), round(y_norm, 3)))
        return True

    def click(self, x, y, *, dwell_ms=80, settle_ms=120):
        self.screen_clicks.append((x, y))
        return True

    def move_mouse(self, x, y):
        self.moves.append((x, y))
        return True

    def chord_scancode(self, modifier, key, *, dwell_ms=30, hwnd=None):
        self.chords.append((modifier, key))
        return True


def director(
    frames,
    *,
    cursors=(LAND_CURSOR, SWORD_CURSOR),
    controller: FakeController | None = None,
) -> tuple[CombatDirector, FakeController]:
    """A director whose capture and cursor reads walk fixed sequences.

    The last entry of each sequence repeats, so a test only has to describe the
    frames it cares about.
    """
    controller = controller or FakeController()
    frame_list = list(frames)
    cursor_list = list(cursors)

    def capture():
        return frame_list.pop(0) if len(frame_list) > 1 else frame_list[0]

    def cursor():
        return cursor_list.pop(0) if len(cursor_list) > 1 else cursor_list[0]

    return (
        CombatDirector(
            hwnd=1,
            controller=controller,
            capture=capture,
            cursor_handle=cursor,
            to_screen=lambda x, y: (int(x * 1920), int(y * 1080)),
            sleep=lambda _s: None,
            hover_dwell_s=0.0,
            order_settle_s=0.0,
            battle_timeout_s=1.0,
        ),
        controller,
    )


def test_battle_deployment_is_recognised_by_its_geometry():
    assert battle_deployment_present(battle_panel_image()) is True


def test_a_clear_map_is_not_a_battle_panel():
    assert battle_deployment_present(army_hud_image(6)) is False


def test_a_settlement_scroll_is_not_a_battle_panel():
    """Just as wide, but it starts far higher up the screen."""
    image = Image.new("RGB", (1920, 1080), (24, 30, 26))
    ImageDraw.Draw(image).rectangle((300, 140, 1600, 900), fill=(220, 205, 170))
    assert battle_deployment_present(image) is False


def test_a_lone_general_is_never_attacked_with():
    combat, controller = director([army_hud_image(1)])
    outcome = combat.attack((0.26, 0.38))
    assert outcome.ordered is False
    assert "stack_not_selected" in outcome.reason
    assert controller.screen_clicks == []


def test_no_attack_glyph_means_no_click():
    """The cursor never changed, so the point is not a target — nameplate or water."""
    combat, controller = director([army_hud_image(8)], cursors=(LAND_CURSOR, LAND_CURSOR))
    outcome = combat.attack((0.26, 0.38))
    assert (outcome.ordered, outcome.reason) == (False, "no_attack_cursor")
    assert controller.screen_clicks == []


def test_an_unreadable_cursor_fails_closed():
    combat, controller = director([army_hud_image(8)], cursors=(0, 0))
    outcome = combat.attack((0.26, 0.38))
    assert (outcome.ordered, outcome.reason) == (False, "cursor_unreadable")
    assert controller.screen_clicks == []


def test_a_full_stack_over_a_target_attacks_and_auto_resolves():
    frames = [
        army_hud_image(8),  # selection check
        army_hud_image(8),  # re-check after the hover
        battle_panel_image(),  # the order opened Battle Deployment
        army_hud_image(8),  # panel gone after auto-resolve
    ]
    combat, controller = director(frames)
    outcome = combat.attack((0.26, 0.38))

    assert (outcome.ordered, outcome.battle_resolved) == (True, True)
    assert outcome.unit_cards == 8
    assert controller.screen_clicks == [(499, 410)]
    assert AUTO_RESOLVE_BUTTON in controller.clicks_norm


def test_selection_lost_between_hover_and_click_is_not_attacked():
    frames = [army_hud_image(8), army_hud_image(1), army_hud_image(1)]
    combat, controller = director(frames)
    outcome = combat.attack((0.26, 0.38))
    assert outcome.ordered is False
    assert "selection_lost_before_click" in outcome.reason
    assert controller.screen_clicks == []


def test_resolve_battle_is_a_no_op_without_a_panel():
    """An attack can open a siege panel instead, and that must not be clicked."""
    combat, controller = director([army_hud_image(8)])
    assert combat.resolve_battle() is True
    assert controller.clicks_norm == []


def test_resolve_battle_reports_failure_when_the_panel_stays():
    combat, controller = director([battle_panel_image()])
    assert combat.resolve_battle() is False
    assert controller.clicks_norm.count(AUTO_RESOLVE_BUTTON) == 1


def test_acquire_stack_goes_through_lists_military_forces():
    from comstar_game_ai.game_io.campaign import army

    combat, controller = director([army_hud_image(7)])
    selection = combat.acquire_stack((0.30, 0.415))

    assert (selection.unit_cards, selection.safe_to_attack) == (7, True)
    assert controller.chords == [("ctrl", "5")]
    assert controller.clicks_norm == [
        army.LISTS_MILITARY_TAB,
        (0.3, 0.415),
        army.LISTS_LOCATE,
    ]
