import json

import pytest

from comstar_game_ai.agent.directive import (
    ADVANCING_OBJECTIVES,
    CAMPAIGN_OBJECTIVES,
    DIRECTIVE_OBSERVATIONS,
    NEUTRAL_OBJECTIVE,
    battle_directive_schema,
    campaign_directive_schema,
    downgrade_infeasible,
    neutral_directive,
    parse_directive,
)


def test_neutral_directive_default():
    d = neutral_directive("timeout")
    assert d.intent.objective == NEUTRAL_OBJECTIVE
    assert "timeout" in d.commentary


def test_parse_valid_directive():
    payload = {
        "intent": {
            "objective": "annihilate",
            "acceptable_own_losses": 0.35,
            "required_enemy_losses": 0.90,
        },
        "horizon": "short",
        "risk_posture": -0.5,
        "valid_for_plies": 4,
        "play_id": "hammer_anvil",
        "play_params": {"flank": "left"},
    }
    d = parse_directive(json.dumps(payload))
    assert d.intent.objective == "annihilate"
    assert d.play_id == "hammer_anvil"
    assert d.play_params["flank"] == "left"


def test_malformed_returns_neutral():
    d = parse_directive("not json at all")
    assert d.intent.objective == NEUTRAL_OBJECTIVE


def test_parse_fenced_json():
    d = parse_directive('```json\n{"intent":{"objective":"besiege"},"valid_for_plies":2}\n```')
    assert d.intent.objective == "besiege"
    assert d.valid_for_plies == 2


def test_parse_inline_json_wrapped_in_prose():
    d = parse_directive(
        'Use this: {"intent":{"objective":"reinforce"},"commentary":"wrapped"}'
    )
    assert d.intent.objective == "reinforce"
    assert d.commentary == "wrapped"


@pytest.mark.parametrize("answer", ["hold", "normal", "set_objective", "win", "expand"])
def test_a_bare_word_is_not_a_directive(answer: str):
    """These arrived live, from a sanitizer that had unwrapped the real answer.

    Reading them as decisions was worse than losing them: the run reported an
    objective the model never chose. `hold` is still the outcome, but it now arrives
    through the neutral path and says why, so a silent channel is visible as one.
    """
    d = parse_directive(answer)
    assert d.intent.objective == NEUTRAL_OBJECTIVE
    assert d.commentary == "malformed_json"
    assert d.valid_for_plies == 1


def test_an_empty_answer_says_it_was_empty():
    assert parse_directive("").commentary == "empty"


def test_the_campaign_schema_offers_only_objectives_the_planner_understands():
    """An enum is a decoding constraint, so anything listed here gets chosen."""
    schema = campaign_directive_schema()
    offered = set(schema["properties"]["objective"]["enum"])

    assert offered == set(CAMPAIGN_OBJECTIVES)
    # Both halves have to be reachable, or the enum is quietly a single choice.
    assert offered & ADVANCING_OBJECTIVES
    assert offered - ADVANCING_OBJECTIVES


def test_the_campaign_schema_offers_no_battle_verbs():
    offered = set(campaign_directive_schema()["properties"]["objective"]["enum"])

    assert not offered & {"annihilate", "break_and_pursue", "win_cheaply"}
    assert "annihilate" in set(
        battle_directive_schema()["properties"]["objective"]["enum"]
    )


def test_the_campaign_schema_has_no_removed_labels():
    offered = set(campaign_directive_schema()["properties"]["objective"]["enum"])
    assert not offered & {"expand", "attack", "take_settlement", "fortify"}


@pytest.mark.parametrize("schema", [battle_directive_schema()])
def test_battle_only_unbounded_field_is_the_reason(schema: dict):
    """A grammar only offers valid next tokens, so an unbounded field invites a loop."""
    free_text = [
        name
        for name, prop in schema["properties"].items()
        if prop.get("type") == "string" and "enum" not in prop
    ]
    assert free_text == ["reason"]
    assert not [p for p in schema["properties"].values() if p.get("type") == "array"]


def test_campaign_schema_required_fields():
    schema = campaign_directive_schema()
    assert set(schema["required"]) == {"objective", "because"}
    assert "commit_until_turn" not in schema["properties"]


def test_the_schema_stays_inside_what_ollama_can_constrain():
    """The engine hands this straight to Ollama as `format`; unsupported keywords
    become rules the model never sees while writing."""
    allowed = {"type", "properties", "required", "items", "enum"}

    def walk(node: dict) -> None:
        assert set(node) <= allowed, set(node) - allowed
        for sub in (node.get("properties") or {}).values():
            walk(sub)
        if isinstance(node.get("items"), dict):
            walk(node["items"])

    walk(campaign_directive_schema())
    walk(battle_directive_schema())


def test_a_schema_shaped_campaign_answer_parses():
    answer = json.dumps(
        {
            "question_id": "q-1",
            "objective": "besiege",
            "actor": "gen_01",
            "target": "set_14",
            "expects": {"turns_to_reach": 3, "garrison_at_arrival": "weaker"},
            "because": "set_14 is open and gen_01 is free",
        }
    )

    d = parse_directive(answer)
    assert d.intent.objective == "besiege"
    assert d.intent.objective in ADVANCING_OBJECTIVES
    assert "set_14" in d.commentary
    assert d.play_params.get("actor") == "gen_01"
    assert d.play_params.get("target") == "set_14"


def test_the_nested_contract_still_parses():
    """The battle plays and every hand-written directive use the full shape."""
    d = parse_directive(
        json.dumps(
            {
                "intent": {"objective": "annihilate", "acceptable_own_losses": 0.4},
                "focus_actions": ["list_units"],
                "commentary": "they are broken",
            }
        )
    )

    assert d.intent.objective == "annihilate"
    assert d.intent.acceptable_own_losses == 0.4
    assert d.focus_actions == ["list_units"]
    assert d.commentary == "they are broken"


def test_downgrade_annihilation():
    payload = {"intent": {"objective": "annihilate"}}
    d = parse_directive(json.dumps(payload))
    d2 = downgrade_infeasible(d, own_strength=100, enemy_strength=200)
    assert d2.intent.objective == "win_cheaply"


def test_directive_observations_unchanged():
    assert "list_characters" in DIRECTIVE_OBSERVATIONS
