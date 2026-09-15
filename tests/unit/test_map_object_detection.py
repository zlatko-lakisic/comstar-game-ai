"""Unit tests for AO object-detection JSON parsing helpers."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.map_object_detection import (
    Detection,
    filter_labels,
    nearest,
    pair_badge_to_oval,
    parse_detection_payload,
)


def test_parse_detection_payload_round_trip():
    raw = {
        "detections": [
            {
                "label": "army_stack",
                "score": 0.91,
                "box_xyxy": [10.0, 20.0, 40.0, 60.0],
            },
            {
                "label": "settlement_badge",
                "score": 0.5,
                "box_xyxy": [100, 100, 120, 120],
            },
        ],
        "image": {"width": 1280, "height": 720, "name": "frame.jpg"},
        "model": {
            "provider_id": "client.detect_rtw_campaign",
            "inference_ms": 12.5,
        },
    }
    result = parse_detection_payload(raw)
    assert len(result.detections) == 2
    assert result.image_width == 1280
    assert result.inference_ms == 12.5
    army = result.detections[0]
    assert army.label == "army_stack"
    assert army.centre_px() == (25, 40)
    nx, ny = army.centre_norm(1280, 720)
    assert 0.01 < nx < 0.03
    assert 0.05 < ny < 0.06


def test_parse_fenced_json_and_empty():
    assert parse_detection_payload("").detections == []
    fenced = '```json\n{"detections":[{"label":"ship","score":0.8,"box_xyxy":[1,2,3,4]}]}\n```'
    assert parse_detection_payload(fenced).detections[0].label == "ship"


def test_filter_nearest_pair():
    a = Detection("army_stack", 0.9, (0, 0, 10, 10))
    b = Detection("army_stack", 0.8, (100, 100, 110, 110))
    badge = Detection("settlement_badge", 0.9, (50, 50, 60, 60))
    oval = Detection("settlement_oval", 0.9, (55, 70, 90, 100))
    assert nearest([a, b], x=5, y=5) is a
    armies = filter_labels([a, b, badge], ["army_stack"])
    assert armies == [a, b]
    pairs = pair_badge_to_oval([badge], [oval], max_dist_px=40.0)
    assert pairs[0][1] is oval
