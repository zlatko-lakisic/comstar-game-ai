from PIL import Image, ImageDraw

from comstar_game_ai.game_io.campaign.modal import (
    ModalHandler,
    _parse_modal_vision_result,
    localize_colored_modal_buttons,
)


def test_parse_modal_vision_result_valid():
    raw = """
    {
      "request_id": "modal-abc",
      "modal_kind": "diplomacy",
      "dialog_bounds_norm": [0.22, 0.18, 0.78, 0.86],
      "candidates": [
        {"action": "reject", "x_norm": 0.51, "y_norm": 0.78, "confidence": 0.88},
        {"action": "accept", "x_norm": 0.58, "y_norm": 0.78, "confidence": 0.51}
      ]
    }
    """
    result = _parse_modal_vision_result(raw, request_id="fallback")
    assert result is not None
    assert result.request_id == "modal-abc"
    assert result.modal_kind == "diplomacy"
    assert len(result.candidates) == 2


def test_parse_modal_vision_result_invalid_json():
    assert _parse_modal_vision_result("{oops", request_id="r1") is None


def test_parse_modal_vision_result_enveloped_json():
    raw = (
        'MODAL_JSON:{"modal_kind":"diplomacy","dialog_bounds_norm":[0.2,0.2,0.8,0.9],'
        '"candidates":[{"action":"reject","x_norm":0.5,"y_norm":0.8,"confidence":0.9}]}'
    )
    result = _parse_modal_vision_result(raw, request_id="r-envelope")
    assert result is not None
    assert result.modal_kind == "diplomacy"
    assert result.best_safe is not None


def test_choose_safe_candidate_blocks_low_margin():
    handler = ModalHandler(min_confidence=0.70, min_margin=0.10)
    raw = """
    {
      "modal_kind": "diplomacy",
      "dialog_bounds_norm": [0.20, 0.20, 0.80, 0.90],
      "candidates": [
        {"action": "reject", "x_norm": 0.50, "y_norm": 0.79, "confidence": 0.76},
        {"action": "accept", "x_norm": 0.56, "y_norm": 0.79, "confidence": 0.71}
      ]
    }
    """
    result = _parse_modal_vision_result(raw, request_id="r2")
    assert result is not None
    assert handler._choose_safe_candidate(result) is None


def test_choose_safe_candidate_accepts_high_confidence_reject():
    handler = ModalHandler(min_confidence=0.70, min_margin=0.10)
    raw = """
    {
      "modal_kind": "diplomacy",
      "dialog_bounds_norm": [0.20, 0.20, 0.80, 0.90],
      "candidates": [
        {"action": "reject", "x_norm": 0.49, "y_norm": 0.79, "confidence": 0.91},
        {"action": "accept", "x_norm": 0.58, "y_norm": 0.79, "confidence": 0.42}
      ]
    }
    """
    result = _parse_modal_vision_result(raw, request_id="r3")
    assert result is not None
    choice = handler._choose_safe_candidate(result)
    assert choice is not None
    assert choice.action == "reject"


def test_localize_colored_diplomacy_buttons():
    image = Image.new("RGB", (1000, 600), (35, 55, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((250, 80, 750, 520), fill=(220, 205, 170))
    # Saturated filled glyphs (thin strokes under-detect with cream gating).
    draw.ellipse((430, 440, 470, 480), fill=(25, 160, 40))
    draw.ellipse((490, 440, 530, 480), fill=(190, 30, 25))

    candidates = localize_colored_modal_buttons(image)
    accept = next(c for c in candidates if c.action == "accept")
    reject = next(c for c in candidates if c.action == "reject")
    assert 0.42 < accept.x_norm < 0.48
    assert 0.48 < reject.x_norm < 0.54
    assert abs(accept.y_norm - reject.y_norm) < 0.03


def test_localize_closing_dialog_reject_only():
    """Closing scroll has a red X without a green check — must still be found."""
    image = Image.new("RGB", (1000, 600), (35, 55, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((250, 80, 750, 520), fill=(220, 205, 170))
    draw.ellipse((515, 440, 555, 480), fill=(190, 30, 25))

    candidates = localize_colored_modal_buttons(image)
    reject = next((c for c in candidates if c.action == "reject"), None)
    accept = next((c for c in candidates if c.action == "accept"), None)
    assert reject is not None
    assert accept is None
    assert 0.50 < reject.x_norm < 0.60


def test_map_terrain_does_not_fake_diplomacy_buttons():
    """Open map greens/browns must not be treated as accept/reject."""
    image = Image.new("RGB", (1000, 600), (40, 70, 45))
    draw = ImageDraw.Draw(image)
    # Terrain blotches in the old center-footer ROI.
    draw.ellipse((420, 430, 480, 490), fill=(60, 130, 55))
    draw.ellipse((500, 430, 560, 490), fill=(160, 70, 40))
    assert localize_colored_modal_buttons(image) == ()


def _sunlit_map(width=1000, height=600):
    """Bright coastal map: sand, grassland and ochre earth, no dimmed centre."""
    image = Image.new("RGB", (width, height), (60, 120, 175))  # sea
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 200, 850, 520), fill=(205, 190, 150))  # sunlit sand
    draw.rectangle((200, 240, 800, 500), fill=(100, 150, 70))  # grassland
    return image, draw


def test_sunlit_map_is_not_a_scroll():
    """Terrain passes a per-pixel cream test; it must fail the scroll test."""
    from comstar_game_ai.game_io.campaign.modal import centered_scroll_present

    image, _ = _sunlit_map()
    assert centered_scroll_present(image) is False


def test_grass_beside_ochre_earth_is_not_a_diplomacy_offer():
    """Regression: the live failure that blocked End Turn for a full attempt.

    Grassland supplied the 'green accept' and ochre dry earth the 'red reject',
    reported at x 0.636/0.656 on an open campaign map.
    """
    image, draw = _sunlit_map()
    draw.ellipse((610, 430, 665, 480), fill=(105, 155, 70))  # lush grass
    draw.ellipse((640, 425, 690, 475), fill=(170, 110, 70))  # ploughed earth
    assert localize_colored_modal_buttons(image) == ()


def test_real_negotiation_layout_still_detected():
    """Calibrated to a live negotiation: accept 0.453, reject 0.496, y 0.779."""
    width, height = 1000, 600
    image = Image.new("RGB", (width, height), (30, 32, 38))  # dimmed map
    draw = ImageDraw.Draw(image)
    draw.rectangle((260, 90, 740, 500), fill=(228, 216, 186))  # scroll
    draw.ellipse((443, 456, 463, 476), fill=(60, 150, 60))  # green check
    draw.ellipse((486, 456, 506, 476), fill=(190, 30, 25))  # red X
    draw.ellipse((530, 456, 550, 476), fill=(150, 130, 100))  # records icon

    candidates = localize_colored_modal_buttons(image)
    accept = next(c for c in candidates if c.action == "accept")
    reject = next(c for c in candidates if c.action == "reject")
    assert abs(accept.x_norm - 0.453) < 0.02
    assert abs(reject.x_norm - 0.496) < 0.02
    assert abs(reject.y_norm - 0.777) < 0.02


def test_offset_button_pair_outside_centre_is_rejected():
    """A real footer row is centred; a pair out at x 0.64 cannot be one."""
    width, height = 1000, 600
    image = Image.new("RGB", (width, height), (30, 32, 38))
    draw = ImageDraw.Draw(image)
    draw.rectangle((260, 90, 740, 500), fill=(228, 216, 186))
    draw.ellipse((626, 456, 646, 476), fill=(60, 150, 60))
    draw.ellipse((646, 452, 666, 472), fill=(190, 30, 25))
    assert localize_colored_modal_buttons(image) == ()


def test_left_decision_buttons_need_a_panel():
    """Green/red terrain pairs in the left region are not alert decisions."""
    from comstar_game_ai.game_io.campaign.modal import localize_left_panel_decision_buttons

    image, draw = _sunlit_map()
    draw.ellipse((300, 400, 340, 440), fill=(40, 150, 50))
    draw.ellipse((360, 400, 400, 440), fill=(190, 35, 30))
    assert localize_left_panel_decision_buttons(image) == ()


def test_left_dock_red_noise_is_not_diplomacy_reject():
    """Left-side red chrome must not become a lone diplomacy reject."""
    image = Image.new("RGB", (1000, 600), (35, 55, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 40, 260, 520), fill=(220, 205, 170))
    draw.ellipse((80, 440, 120, 480), fill=(190, 30, 25))
    assert localize_colored_modal_buttons(image) == ()


def test_localize_left_alert_decision_buttons():
    from comstar_game_ai.game_io.campaign.modal import localize_left_panel_decision_buttons

    image = Image.new("RGB", (1000, 600), (35, 55, 40))
    draw = ImageDraw.Draw(image)
    # Left dock + detail pane parchment.
    draw.rectangle((40, 60, 450, 520), fill=(220, 205, 170))
    draw.ellipse((300, 400, 340, 440), fill=(40, 150, 50))
    draw.ellipse((360, 400, 400, 440), fill=(190, 35, 30))
    candidates = localize_left_panel_decision_buttons(image)
    accept = next(c for c in candidates if c.action == "accept")
    reject = next(c for c in candidates if c.action == "reject")
    assert 0.28 < accept.x_norm < 0.36
    assert 0.34 < reject.x_norm < 0.42
    assert abs(accept.y_norm - reject.y_norm) < 0.05


def _panel_with_close_x(width=1000, height=600, panel_left=8, panel_right=300, panel_top=60):
    """Cream panel with a gold close X centred on its top-right corner."""
    image = Image.new("RGB", (width, height), (30, 50, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((panel_left, panel_top, panel_right, height - 40), fill=(220, 205, 170))
    draw.ellipse(
        (panel_right - 12, panel_top - 2, panel_right + 12, panel_top + 22), fill=(205, 150, 51)
    )
    return image, draw


def test_panel_close_x_finds_corner_gold_x():
    from comstar_game_ai.game_io.campaign.modal import localize_panel_close_x

    image, _ = _panel_with_close_x()
    close = localize_panel_close_x(image)
    assert close is not None
    assert close.action == "close"
    assert abs(close.x_norm - 0.300) < 0.02
    assert abs(close.y_norm - 0.117) < 0.03


def test_panel_close_x_found_on_centred_panel():
    """Settlement panels start near x 0.26, so the search cannot require a left anchor."""
    from comstar_game_ai.game_io.campaign.modal import localize_panel_close_x

    image, draw = _panel_with_close_x(panel_left=260, panel_right=740, panel_top=120)
    # Faction crest on the map just outside the panel — gold, but not the close X.
    draw.ellipse((762, 130, 800, 168), fill=(198, 148, 55))
    close = localize_panel_close_x(image)
    assert close is not None
    assert abs(close.x_norm - 0.740) < 0.02
    assert abs(close.y_norm - 0.217) < 0.03


def test_panel_close_x_ignores_larger_gold_badge_below():
    """The alerts trumpet badge is a bigger gold blob than the close X above it."""
    from comstar_game_ai.game_io.campaign.modal import localize_panel_close_x

    image, draw = _panel_with_close_x()
    draw.ellipse((288, 150, 336, 198), fill=(200, 149, 58))
    close = localize_panel_close_x(image)
    assert close is not None
    assert close.y_norm < 0.20


def test_panel_close_x_absent_without_panel():
    from comstar_game_ai.game_io.campaign.modal import localize_panel_close_x

    image = Image.new("RGB", (1000, 600), (35, 60, 45))
    ImageDraw.Draw(image).ellipse((300, 60, 324, 84), fill=(205, 150, 51))
    assert localize_panel_close_x(image) is None


def test_panel_bounds_ignores_clear_map():
    from comstar_game_ai.game_io.campaign.modal import panel_bounds

    image, _ = _sunlit_map()
    assert panel_bounds(image) is None


def test_notice_card_in_left_dock_is_not_blocking():
    """A senate mission / alert card asks nothing and leaves the map playable."""
    from comstar_game_ai.game_io.campaign.modal import blocking_ui_present, panel_bounds

    image, draw = _panel_with_close_x(panel_left=0, panel_right=310, panel_top=71)
    # Artwork and text blocks break up the parchment on a real card.
    draw.rectangle((10, 130, 290, 250), fill=(90, 70, 60))
    draw.rectangle((20, 300, 280, 420), fill=(70, 60, 55))
    assert panel_bounds(image) is not None
    assert blocking_ui_present(image) is False


def test_panel_over_map_centre_is_blocking():
    """Settlement / building browser scrolls swallow input, so they must be closed."""
    from comstar_game_ai.game_io.campaign.modal import blocking_ui_present

    image, _ = _panel_with_close_x(panel_left=260, panel_right=740, panel_top=120)
    assert blocking_ui_present(image) is True


def test_decision_buttons_in_left_dock_are_blocking():
    from comstar_game_ai.game_io.campaign.modal import blocking_ui_present

    image = Image.new("RGB", (1000, 600), (35, 55, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 60, 450, 520), fill=(220, 205, 170))
    draw.ellipse((300, 400, 340, 440), fill=(40, 150, 50))
    draw.ellipse((360, 400, 400, 440), fill=(190, 35, 30))
    assert blocking_ui_present(image) is True


def test_centred_panel_green_red_lines_are_not_decisions():
    """The building browser's construction tree is full of green and red lines."""
    from comstar_game_ai.game_io.campaign.modal import localize_left_panel_decision_buttons

    image, draw = _panel_with_close_x(panel_left=260, panel_right=740, panel_top=120)
    for y in (300, 340, 380):
        draw.line((300, y, 460, y), fill=(40, 150, 50), width=6)
        draw.line((470, y, 520, y), fill=(190, 35, 30), width=6)
    draw.ellipse((330, 480, 370, 520), fill=(40, 150, 50))
    draw.ellipse((390, 480, 430, 520), fill=(190, 35, 30))
    assert localize_left_panel_decision_buttons(image) == ()


def test_diplomacy_two_step_clicks_reject_then_end_talks(monkeypatch):
    """Offer reject, then lone end-talks X — both clicks must happen."""
    from comstar_game_ai.game_io.campaign import modal as modal_mod
    from comstar_game_ai.game_io.campaign.modal import ModalHandler
    from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification

    offer = (
        modal_mod.ModalActionCandidate("accept", 0.45, 0.78, 0.9),
        modal_mod.ModalActionCandidate("reject", 0.52, 0.78, 0.9),
    )
    closing = (modal_mod.ModalActionCandidate("reject", 0.54, 0.78, 0.9),)
    calls = {"n": 0, "clicks": []}

    def fake_localize(_image):
        calls["n"] += 1
        if calls["n"] == 1:
            return offer
        if calls["n"] == 2:
            return closing
        return ()

    class FakeInput:
        def click_client_norm(self, hwnd, x_norm, y_norm, dwell_ms=40):
            calls["clicks"].append((round(x_norm, 2), round(y_norm, 2)))
            return True

        def tap_key(self, *args, **kwargs):
            return True

    monkeypatch.setattr(modal_mod, "localize_diplomacy_footer_buttons", fake_localize)
    monkeypatch.setattr(modal_mod, "left_overlay_parchment_ratio", lambda _im: 0.0)
    monkeypatch.setattr(modal_mod, "grab_rgb_image", lambda _hwnd: object())
    monkeypatch.setattr(
        modal_mod,
        "grab_and_classify",
        lambda _hwnd: UiClassification(mode=CampaignUiMode.CAMPAIGN_MAP, confidence=0.8),
    )

    handler = ModalHandler(input_controller=FakeInput(), settle_s=0.0)
    result = handler._click_visual_dismiss(1, object())
    assert result is not None
    assert calls["clicks"] == [(0.52, 0.78), (0.54, 0.78)]


def test_vision_crop_follows_left_dock():
    """Left panels must not be cropped away before Ada sees them."""
    from comstar_game_ai.game_io.campaign.modal import (
        CENTER_CROP_BOUNDS,
        LEFT_CROP_BOUNDS,
        vision_crop_bounds,
    )

    clear_map = Image.new("RGB", (1000, 600), (35, 55, 40))
    assert vision_crop_bounds(clear_map, "campaign_map") == CENTER_CROP_BOUNDS

    with_dock = Image.new("RGB", (1000, 600), (35, 55, 40))
    ImageDraw.Draw(with_dock).rectangle((20, 60, 270, 520), fill=(220, 205, 170))
    assert vision_crop_bounds(with_dock, "modal") == LEFT_CROP_BOUNDS


def test_modal_vision_prompt_names_rome_panels():
    from comstar_game_ai.game_io.campaign.modal import (
        LEFT_CROP_BOUNDS,
        build_modal_vision_prompt,
    )

    prompt = build_modal_vision_prompt(
        ui_mode="left_overlay_panel",
        crop_bounds=LEFT_CROP_BOUNDS,
    )
    assert "MODAL_JSON:" in prompt
    assert "LEFT side" in prompt
    assert "left_alert_panel" in prompt
    assert "diplomacy_negotiation" in prompt
    # llava echoed a request id back as its whole answer when one was in the skeleton.
    assert "request_id" not in prompt
    # Every example must itself parse, or the model is being shown bad JSON.
    # The last three occurrences are the worked examples; earlier ones are the prose
    # instruction and the placeholder skeleton.
    examples = [chunk.splitlines()[0] for chunk in prompt.split("MODAL_JSON:")[-3:]]
    parsed = [_parse_modal_vision_result(f"MODAL_JSON:{e}", request_id="fallback") for e in examples]
    assert all(p is not None for p in parsed)
    assert [p.modal_kind for p in parsed] == ["none", "diplomacy_negotiation", "left_alert_panel"]
    # llava parrots the final example when it cannot read the frame, so that example
    # must be the common panel case rather than "no modal here".
    assert parsed[-1].candidates[0].action == "close"


def test_handle_prefers_ada_over_pixel_localization(monkeypatch):
    """Ada recognizes the panel; the pixel localizer is only a fallback."""
    from comstar_game_ai.game_io.campaign import modal as modal_mod
    from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification

    clicks: list[tuple[float, float]] = []

    class FakeInput:
        def click_client_norm(self, hwnd, x_norm, y_norm, dwell_ms=40):
            clicks.append((round(x_norm, 2), round(y_norm, 2)))
            return True

        def tap_key(self, *args, **kwargs):
            return True

    def fail_pixel(_image):
        raise AssertionError("pixel localization ran before Ada")

    monkeypatch.setattr(modal_mod, "grab_rgb_image", lambda _hwnd: Image.new("RGB", (100, 60)))
    monkeypatch.setattr(
        modal_mod,
        "grab_and_classify",
        lambda _hwnd: UiClassification(mode=CampaignUiMode.CAMPAIGN_MAP, confidence=0.8),
    )
    monkeypatch.setattr(modal_mod, "left_overlay_parchment_ratio", lambda _im: 0.0)
    monkeypatch.setattr(modal_mod, "localize_diplomacy_footer_buttons", fail_pixel)
    monkeypatch.setattr(modal_mod, "localize_left_panel_decision_buttons", fail_pixel)

    handler = ModalHandler(
        input_controller=FakeInput(),
        settle_s=0.0,
        use_ada_vision=True,
        min_confidence=0.70,
        min_margin=0.10,
    )
    monkeypatch.setattr(
        handler,
        "_query_modal_vision_sync",
        lambda *a, **k: modal_mod.ModalVisionResult(
            request_id="r",
            modal_kind="left_alert_panel",
            candidates=(modal_mod.ModalActionCandidate("reject", 0.31, 0.66, 0.86),),
            dialog_bounds_norm=(0.05, 0.10, 0.55, 0.85),
        ),
    )

    handler.handle(1, UiClassification(mode=CampaignUiMode.MODAL, confidence=0.8))
    assert clicks == [(0.31, 0.66)]

