"""Settlement view-scan parse/rank (no Lists, no seed, no model coords)."""

from __future__ import annotations

from comstar_game_ai.game_io.campaign.map_target_vision import (
    SettlementViewHit,
    build_settlement_scan_prompt,
    map_target_vision_schema,
    normalize_view_standing,
    parse_settlement_scan,
    rank_attackable_settlements,
    settlement_scan_schema,
)


def test_normalize_view_standing():
    assert normalize_view_standing("enemy") == "at_war"
    assert normalize_view_standing("ours") == "ours"
    assert normalize_view_standing("allied") == "ally"
    assert normalize_view_standing("rebels") == "rebel"


def test_parse_settlement_scan_ignores_legacy_coords():
    raw = """
    {"settlements":[
      {"label":"Segesta","region":"Liguria","colour":"green","standing":"at_war","confidence":0.9,"x_norm":0.2,"y_norm":0.5},
      {"label":"Arretium","region":"Etruria","colour":"red","standing":"ours","confidence":0.8},
      {"name":"Patavium","region":"Venetia","colour":"green","standing":"neutral","confidence":0.7}
    ],"reason":"ok"}
    """
    hits = parse_settlement_scan(raw)
    assert len(hits) == 3
    assert hits[0].label == "Segesta" and hits[0].standing == "at_war"
    assert hits[0].colour == "green" and hits[0].region == "Liguria"
    assert hits[0].click_norm is None
    assert hits[2].label == "Patavium"


def test_rank_skips_ours_and_orders_rebel_then_enemy():
    hits = [
        SettlementViewHit("Arretium", 0.5, 0.5, "ours", 0.9),
        SettlementViewHit("Patavium", 0.7, 0.4, "neutral", 0.8),
        SettlementViewHit("Segesta", 0.2, 0.5, "at_war", 0.7),
        SettlementViewHit("Capua", 0.3, 0.6, "ally", 0.6),
        SettlementViewHit("Mutina", 0.8, 0.5, "rebel", 0.5),
    ]
    ranked = rank_attackable_settlements(hits)
    assert [h.label for h in ranked] == ["Mutina", "Segesta", "Patavium", "Capua"]


def test_rank_prefer_label_boosts_within_or_across():
    hits = [
        SettlementViewHit("Patavium", 0.7, 0.4, "neutral", 0.9),
        SettlementViewHit("Segesta", 0.2, 0.5, "neutral", 0.5),
    ]
    ranked = rank_attackable_settlements(hits, prefer_label="Segesta")
    assert ranked[0].label == "Segesta"


def test_scan_prompt_has_no_coordinates_and_mentions_plaque():
    text = build_settlement_scan_prompt(prefer_label="Segesta")
    assert "plaque" in text.lower()
    assert "at_war" in text
    assert "Segesta" in text
    assert "Lists" in text or "minimap" in text.lower()
    assert "Do NOT report coordinates" in text
    # Shape / required fields must not ask for a click point.
    assert '"x_norm"' not in text
    assert '"y_norm"' not in text
    assert '"x":' not in text and '"y":' not in text


def test_schemas_omit_coordinate_fields():
    single = map_target_vision_schema()
    scan = settlement_scan_schema()
    for schema in (single, scan["properties"]["settlements"]["items"]):
        props = schema["properties"]
        assert "x" not in props and "y" not in props
        assert "x_norm" not in props and "y_norm" not in props
