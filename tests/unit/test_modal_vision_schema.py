"""The modal vision call has to run in JSON mode, like the directors do.

A live run logged twelve vision calls and zero usable results. The replies were
`none` and `nothing over the map` — the second being verbatim the `reason` string
out of the prompt's own clear-map example. The model had read the screen right
every time; the engine's sanitizer, whose job is to make an answer speakable,
unwrapped each JSON object down to the one prose field worth reading aloud.

Twenty-five seconds a call, and the pixel localizers did all the work.
"""

from __future__ import annotations

import json

import pytest

from comstar_game_ai.agent.reach.director import (
    JSON_OBJECT_RESPONSE_FORMAT,
    modal_vision_schema,
)
from comstar_game_ai.game_io.campaign.modal import _parse_modal_vision_result


def test_the_schema_admits_a_clear_map():
    """The common answer, and the cheapest: complete in a dozen tokens."""
    payload = {"modal_kind": "none", "reason": "nothing over the map", "candidates": []}
    parsed = _parse_modal_vision_result(json.dumps(payload), request_id="r1")

    assert parsed is not None
    assert parsed.modal_kind == "none"
    assert parsed.candidates == ()


def test_the_schema_admits_a_scroll_with_two_buttons():
    payload = {
        "modal_kind": "diplomacy_negotiation",
        "reason": "green check and red X in scroll footer",
        "dialog_bounds_norm": [0.28, 0.20, 0.74, 0.84],
        "candidates": [
            {"action": "accept", "x_norm": 0.47, "y_norm": 0.77, "confidence": 0.80},
            {"action": "reject", "x_norm": 0.53, "y_norm": 0.77, "confidence": 0.85},
        ],
    }
    parsed = _parse_modal_vision_result(json.dumps(payload), request_id="r2")

    assert parsed is not None
    assert [c.action for c in parsed.candidates] == ["accept", "reject"]
    assert parsed.dialog_bounds_norm == (0.28, 0.20, 0.74, 0.84)


def test_only_the_kind_and_reason_are_required():
    """Under constrained decoding a required field is generated, not considered.

    Requiring `candidates` would collect invented buttons on a clear map, and the
    handler clicks what it is given — the one failure here that costs a run.
    """
    schema = modal_vision_schema()

    assert schema["required"] == ["modal_kind", "reason"]


def test_the_candidate_array_is_bounded():
    """A grammar only ever offers valid next tokens, so an open array is an
    invitation to keep going. A directive call answered in 115 tokens once and ran
    to 11,400 on the next, repeating itself inside an array."""
    schema = modal_vision_schema()

    assert schema["properties"]["candidates"]["maxItems"] == 3
    bounds = schema["properties"]["dialog_bounds_norm"]
    assert bounds["minItems"] == bounds["maxItems"] == 4


def test_the_kinds_match_what_the_parser_treats_as_empty():
    """`_parse_modal_vision_result` discards a result with no candidates unless the
    kind is one of the "nothing to click" ones. A kind the enum can produce but the
    parser rejects would throw away a correct reading of a clear screen."""
    kinds = set(modal_vision_schema()["properties"]["modal_kind"]["enum"])

    assert "none" in kinds
    for empty_kind in ("none", "campaign_map", "main_menu"):
        payload = {"modal_kind": empty_kind, "reason": "clear", "candidates": []}
        assert _parse_modal_vision_result(json.dumps(payload), request_id="r") is not None


def test_a_panel_kind_with_no_buttons_is_rejected():
    """Naming a blocking panel while locating nothing is not an answer the handler
    can use; the pixel localizers should get the frame instead."""
    payload = {"modal_kind": "diplomacy_negotiation", "reason": "a scroll", "candidates": []}

    assert _parse_modal_vision_result(json.dumps(payload), request_id="r") is None


def test_json_mode_is_the_object_form():
    assert JSON_OBJECT_RESPONSE_FORMAT == {"type": "json_object"}


@pytest.mark.parametrize("action", ["accept", "reject", "close", "continue"])
def test_every_action_the_handler_acts_on_is_in_the_enum(action):
    actions = set(
        modal_vision_schema()["properties"]["candidates"]["items"]["properties"]["action"]["enum"]
    )

    assert action in actions
