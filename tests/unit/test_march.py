"""Mouse march destination math and vision-first click path — no Rome required."""

from __future__ import annotations

from PIL import Image

from comstar_game_ai.game_io.campaign.combat import StackSelection
from comstar_game_ai.game_io.campaign.map_target_vision import MapTargetHit
from comstar_game_ai.game_io.campaign.march import (
    FAR_STEP_NORMS,
    NEAR_STEP_NORMS,
    MarchDirector,
)


def test_destination_is_east_of_centre_when_target_is_east():
    click = MarchDirector.destination_norm(
        from_x=100, from_y=100, to_x=110, to_y=100, step_norm=0.16
    )
    assert click is not None
    assert click[0] > 0.50
    assert abs(click[1] - 0.48) < 0.02


def test_destination_flips_map_north_to_screen_up():
    click = MarchDirector.destination_norm(
        from_x=100, from_y=100, to_x=100, to_y=110, step_norm=0.16
    )
    assert click is not None
    assert click[1] < 0.48  # higher map Y → upper screen


def test_one_tile_step_toward_target():
    assert MarchDirector.one_tile_step(
        from_x=100, from_y=100, to_x=110, to_y=100
    ) == (101.0, 100.0)


def test_already_at_target_has_no_destination():
    assert (
        MarchDirector.destination_norm(from_x=5, from_y=5, to_x=5, to_y=5) is None
    )


def test_near_target_probes_settlement_first():
    steps = MarchDirector.step_candidates(8.0)
    assert steps == NEAR_STEP_NORMS
    # Nameplate distance before long overshoot (0.38 used to go first and clamp).
    assert steps[0] <= 0.28
    assert 0.38 in steps
    assert steps.index(0.38) > steps.index(steps[0])


def test_far_target_probes_land_first():
    steps = MarchDirector.step_candidates(40.0)
    assert steps == FAR_STEP_NORMS
    assert steps[0] <= 0.16


def test_long_probe_reaches_segesta_style_offset():
    """Framed army at centre; Segesta sat ~0.28 norm west in live attack evidence."""
    click = MarchDirector.destination_norm(
        from_x=100, from_y=100, to_x=90, to_y=110, step_norm=0.28
    )
    assert click is not None
    assert click[0] < 0.50
    assert click[1] < 0.48
    # Roughly the measured (0.24, 0.38) ballpark when bearing is NW.
    assert abs(click[0] - 0.30) < 0.08


def test_edge_clamped_probe_is_flagged():
    packed = MarchDirector.destination_norm_ex(
        from_x=89, from_y=82, to_x=83, to_y=84, step_norm=0.38
    )
    assert packed is not None
    click, clamped = packed
    assert clamped
    assert click[0] == 0.15
    assert abs(click[1] - 0.360) < 0.02


def test_mid_probe_for_flavius_segesta_is_not_clamped():
    packed = MarchDirector.destination_norm_ex(
        from_x=89, from_y=82, to_x=83, to_y=84, step_norm=0.26
    )
    assert packed is not None
    click, clamped = packed
    assert not clamped
    assert click[0] > 0.15
    assert click[0] < 0.40


def test_march_uses_vision_point_when_glyph_changes(capsys):
    frame = Image.new("RGB", (640, 360), (30, 40, 20))
    expected = (0.237, 0.500)
    baseline, sword = 1001, 2002
    handle = {"v": baseline}
    clicks: list[tuple[int, int]] = []

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            nx, ny = x / 1000.0, y / 1000.0
            if abs(nx - expected[0]) < 0.08 and abs(ny - expected[1]) < 0.08:
                handle["v"] = sword
            else:
                handle["v"] = baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x, y))

        def right_click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x, y))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

        def tap_key(self, *args, **kwargs):
            return True

    def locate(_image: Image.Image, label: str) -> MapTargetHit:
        assert label == "Segesta"
        return MapTargetHit(
            found=True,
            label=label,
            x_norm=expected[0],
            y_norm=expected[1],
            confidence=0.9,
            reason="test",
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
        window_size=lambda: (1296, 759),
        use_map_projection=False,
        allow_legacy_geometry=True,
        use_vision_besiege=False,
    )
    director.acquire_any_stack = (  # type: ignore[method-assign]
        lambda preferred_row=None: StackSelection(unit_cards=5, safe_to_attack=True)
    )

    outcome = director.march(
        from_x=100,
        from_y=100,
        to_x=90,
        to_y=110,
        character_name="Flavius Julius",
        target_label="Segesta",
    )

    assert outcome.ordered and outcome.vision_used and outcome.cursor_changed
    assert outcome.click_norm == expected
    assert outcome.button == "right"
    assert clicks
    out = capsys.readouterr().out
    assert "MARCH client=1296x759" in out
    assert "MARCH vision: hit" in out
    assert "MARCH ordered click=(0.237,0.500)" in out
    assert "button=right" in out


def test_march_skips_edge_clamped_glyph_for_in_frame_probe(capsys):
    """0.38 clamp (mountains) must not win when a mid probe also shows a glyph."""
    frame = Image.new("RGB", (640, 360), (30, 40, 20))
    baseline, boots = 11, 22
    handle = {"v": baseline}
    clicks: list[tuple[float, float]] = []

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            nx, ny = x / 1000.0, y / 1000.0
            # Glyph anywhere left of centre (both clamp and mid probes).
            handle["v"] = boots if nx < 0.45 else baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x / 1000.0, y / 1000.0))

        def right_click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x / 1000.0, y / 1000.0))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

        def tap_key(self, *args, **kwargs):
            return True

    director = MarchDirector(
        hwnd=1,
        controller=FakeController(),
        capture=lambda: frame,
        cursor_handle=lambda: handle["v"],
        to_screen=lambda x, y: (int(x * 1000), int(y * 1000)),
        sleep=lambda _s: None,
        hover_dwell_s=0.0,
        order_settle_s=0.0,
        locate_target=lambda _im, _label: MapTargetHit(
            found=False, label="segesta", reason="not_visible"
        ),
        window_size=lambda: (1000, 1000),
        use_map_projection=False,
        allow_legacy_geometry=True,
        use_vision_besiege=False,
    )
    director.acquire_any_stack = (  # type: ignore[method-assign]
        lambda preferred_row=None: StackSelection(unit_cards=4, safe_to_attack=True)
    )

    outcome = director.march(
        from_x=89,
        from_y=82,
        to_x=83,
        to_y=84,
        target_label="segesta",
    )

    assert outcome.ordered and not outcome.vision_used
    assert outcome.click_norm is not None
    # Must not be the left-edge clamp that hit the Alps in the live run.
    assert outcome.click_norm[0] > 0.15 + 1e-6
    out = capsys.readouterr().out
    assert "clamp" in out or "MARCH ordered" in out


def test_march_falls_back_to_geometry_when_vision_misses(capsys):
    frame = Image.new("RGB", (640, 360), (30, 40, 20))
    baseline, sword = 11, 22
    handle = {"v": baseline}
    geo_clicks: list[tuple[float, float]] = []

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            # Any map probe off centre → glyph (geometry path).
            nx, ny = x / 1000.0, y / 1000.0
            if abs(nx - 0.50) > 0.05 or abs(ny - 0.48) > 0.05:
                handle["v"] = sword
            else:
                handle["v"] = baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            geo_clicks.append((x / 1000.0, y / 1000.0))

        def right_click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            geo_clicks.append((x / 1000.0, y / 1000.0))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

        def tap_key(self, *args, **kwargs):
            return True

    director = MarchDirector(
        hwnd=1,
        controller=FakeController(),
        capture=lambda: frame,
        cursor_handle=lambda: handle["v"],
        to_screen=lambda x, y: (int(x * 1000), int(y * 1000)),
        sleep=lambda _s: None,
        hover_dwell_s=0.0,
        order_settle_s=0.0,
        locate_target=lambda _im, _label: MapTargetHit(
            found=False, label="Segesta", reason="not_visible"
        ),
        window_size=lambda: (800, 600),
        use_map_projection=False,
        allow_legacy_geometry=True,
        use_vision_besiege=False,
    )
    director.acquire_any_stack = (  # type: ignore[method-assign]
        lambda preferred_row=None: StackSelection(unit_cards=4, safe_to_attack=True)
    )

    outcome = director.march(
        from_x=100,
        from_y=100,
        to_x=110,
        to_y=100,
        target_label="Segesta",
    )

    assert outcome.ordered
    assert not outcome.vision_used
    assert outcome.click_norm is not None
    assert outcome.click_norm[0] > 0.50
    assert outcome.button == "right"
    out = capsys.readouterr().out
    assert "MARCH vision: miss" in out
    assert "MARCH ordered click=" in out


def test_projection_path_frames_calibrates_and_right_clicks(capsys):
    """Near target: army_anchor after locate → glyph → right-click (no radar jump)."""
    frame = Image.new("RGB", (640, 360), (30, 40, 20))
    baseline, boots = 7, 9
    handle = {"v": baseline}
    clicks: list[tuple[float, float]] = []
    radar_clicks: list[tuple[float, float]] = []

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            nx, ny = x / 1000.0, y / 1000.0
            # Glyph along army-anchor Segesta bearing (undershoot → full).
            if 0.40 <= nx <= 0.48 and 0.40 <= ny <= 0.52:
                handle["v"] = boots
            else:
                handle["v"] = baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            raise AssertionError("destination must be right-click, not left")

        def right_click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x / 1000.0, y / 1000.0))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            radar_clicks.append((x, y))
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

        def tap_key(self, *args, **kwargs):
            return True

    director = MarchDirector(
        hwnd=1,
        controller=FakeController(),
        capture=lambda: frame,
        cursor_handle=lambda: handle["v"],
        to_screen=lambda x, y: (int(x * 1000), int(y * 1000)),
        sleep=lambda _s: None,
        hover_dwell_s=0.0,
        order_settle_s=0.0,
        locate_target=None,
        window_size=lambda: (1000, 1000),
        use_map_projection=True,
        allow_legacy_geometry=False,
        anchor_scale=0.01,
        require_canonical_pose=False,
    )
    director.acquire_ordered_stack = (  # type: ignore[method-assign]
        lambda **kwargs: (
            StackSelection(unit_cards=5, safe_to_attack=True),
            (0.30, 0.455),
            "frustum",
            (89.0, 82.0),
        )
    )

    outcome = director.march(
        from_x=89,
        from_y=82,
        to_x=83,
        to_y=84,
        character_name="Flavius Julius",
        target_label="Segesta",
    )

    assert outcome.ordered
    assert outcome.button == "right"
    assert outcome.calib_mode == "army_anchor"
    assert outcome.projection_consistent
    assert outcome.click_norm is not None
    assert outcome.click_norm[0] < 0.50  # west of Flavius
    assert outcome.click_norm[0] > 0.25  # not overshot into the gulf
    assert outcome.click_norm[1] < 0.58  # above army HUD
    assert not radar_clicks, "near target must not radar-jump"
    assert clicks
    out = capsys.readouterr().out
    assert "army_anchor" in out
    assert "button=right" in out


def test_wrong_lists_row_skipped_when_frustum_mismatches():
    calls: list[tuple[float, float]] = []
    row_box: dict[str, tuple[float, float] | None] = {"r": None}

    class Combat:
        def acquire_stack(self, row):
            row_box["r"] = row
            calls.append(row)
            return StackSelection(unit_cards=3, safe_to_attack=True)

    combat = Combat()
    director = MarchDirector(hwnd=1, controller=object(), sleep=lambda _s: None)
    director._combat_director = lambda: combat  # type: ignore[method-assign]
    director._grab = lambda: Image.new("RGB", (64, 64), (0, 0, 0))  # type: ignore[method-assign]

    matches = {(0.30, 0.415): False, (0.30, 0.455): True}

    def frustum_match(_image, _from_xy):
        return matches.get(row_box["r"])  # type: ignore[arg-type]

    director._frustum_matches_army = frustum_match  # type: ignore[method-assign]

    got = director.acquire_ordered_stack(
        from_x=89.0,
        from_y=82.0,
        preferred_row=(0.30, 0.415),
        character_name="Flavius Julius",
    )
    assert got is not None
    selection, row, mode, centre = got
    assert selection.unit_cards == 3
    assert row == (0.30, 0.455)
    assert mode == "frustum"
    assert calls[0] == (0.30, 0.415)
    assert (0.30, 0.455) in calls


def test_near_settlement_threshold_matches_frustum_gate():
    from comstar_game_ai.game_io.campaign import march as march_mod

    assert march_mod.ARMY_FRUSTUM_MATCH_MAP == 12.0
    assert march_mod.NEAR_SETTLEMENT_MAP_DIST == 8.0


def test_arretium_to_segesta_is_far_with_live_from():
    """Live Flavius at Arretium must not take the near army-anchor path to Segesta."""
    dist = MarchDirector.map_distance(
        from_x=67.5, from_y=87.1, to_x=83.0, to_y=84.0
    )
    from comstar_game_ai.game_io.campaign.march import NEAR_SETTLEMENT_MAP_DIST

    assert dist > NEAR_SETTLEMENT_MAP_DIST

    dist2 = MarchDirector.map_distance(
        from_x=72.8, from_y=87.1, to_x=83.0, to_y=84.0
    )
    assert dist2 > NEAR_SETTLEMENT_MAP_DIST


def test_projection_forces_far_when_dest_outside_viewport(capsys):
    """Army-anchor click outside viewport → radar frame (far path)."""
    frame = Image.new("RGB", (640, 360), (30, 40, 20))
    baseline, boots = 7, 9
    handle = {"v": baseline}
    radar_clicks: list[tuple[float, float]] = []
    clicks: list[tuple[float, float]] = []

    class FakeController:
        def move_mouse(self, x: int, y: int) -> None:
            nx, ny = x / 1000.0, y / 1000.0
            if 0.40 <= nx <= 0.60 and 0.40 <= ny <= 0.55:
                handle["v"] = boots
            else:
                handle["v"] = baseline

        def click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            raise AssertionError("destination must be right-click")

        def right_click(self, x: int, y: int, dwell_ms: int = 0, settle_ms: int = 0) -> None:
            clicks.append((x / 1000.0, y / 1000.0))

        def click_client_norm(self, hwnd, x, y, dwell_ms=0):
            radar_clicks.append((x, y))
            return True

        def chord_scancode(self, *args, **kwargs):
            return True

        def tap_key(self, *args, **kwargs):
            return True

    director = MarchDirector(
        hwnd=1,
        controller=FakeController(),
        capture=lambda: frame,
        cursor_handle=lambda: handle["v"],
        to_screen=lambda x, y: (int(x * 1000), int(y * 1000)),
        sleep=lambda _s: None,
        hover_dwell_s=0.0,
        order_settle_s=0.0,
        locate_target=None,
        window_size=lambda: (1000, 1000),
        use_map_projection=True,
        allow_legacy_geometry=False,
        # Tiny scale → even a short map delta projects outside the viewport.
        anchor_scale=0.05,
        require_canonical_pose=False,
    )
    director.acquire_ordered_stack = (  # type: ignore[method-assign]
        lambda **kwargs: (
            StackSelection(unit_cards=5, safe_to_attack=True),
            (0.30, 0.455),
            "frustum",
            (50.0, 50.0),
        )
    )

    outcome = director.march(
        from_x=50,
        from_y=50,
        to_x=80,
        to_y=50,
        character_name="Flavius Julius",
        target_label="far-settlement",
    )
    assert radar_clicks, "must radar-frame when army-anchor misses viewport"
    out = capsys.readouterr().out
    assert "radar framing" in out or "MARCH frame:" in out
    if outcome.ordered:
        assert outcome.projection_consistent
        assert outcome.calib_mode in {"frustum", "dest_anchor", "dest_anchor_retry"}


def test_issue_click_omits_step_when_not_projection_consistent():
    director = MarchDirector(
        hwnd=1,
        controller=type(
            "C",
            (),
            {
                "right_click": lambda self, *a, **k: None,
                "click": lambda self, *a, **k: None,
            },
        )(),
        to_screen=lambda x, y: (100, 100),
        sleep=lambda _s: None,
        order_settle_s=0.0,
    )
    outcome = director._issue_click(
        click=(0.4, 0.4),
        from_x=89,
        from_y=82,
        to_x=83,
        to_y=84,
        unit_cards=2,
        character_name="Flavius Julius",
        cursor_changed=True,
        vision_used=False,
        calib_mode="army_anchor",
        live_from_xy=(89.0, 82.0),
        projection_consistent=False,
        belief_refresh_ok=True,
    )
    assert outcome.ordered
    assert outcome.step_to is None
    assert not outcome.projection_consistent
