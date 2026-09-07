"""Every agent call, end to end, against a bridge that records what was sent.

This is the layer that runs without ada. It exercises the real question text, the
real context builder and the real parser, and only the transport is a stand-in — so
the things that broke a 20-turn run are all checkable here:

- the campaign director being asked for JSON on the prose path, where a sanitizer
  unwraps the object to one field and returns `normal` with `ok: true`;
- a JSON-mode call asking for MCP tools the pipeline cannot run;
- a directive fabricated out of whatever word came back;
- a brief that carried a turn number and no map.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from comstar_game_ai.agent.directive import (
    ADVANCING_OBJECTIVES,
    CAMPAIGN_OBJECTIVES,
    NEUTRAL_OBJECTIVE,
)
from comstar_game_ai.agent.reach import director as agent_director
from comstar_game_ai.agent.reach.session import ReachSession


class RecordingBridge:
    """Stands in for `SessionBridge`, keeping every frame and replying on cue."""

    def __init__(self, answer: str = "{}", *, mcps: tuple[str, ...] = ()) -> None:
        self.answer = answer
        self.frames: list[dict[str, Any]] = []
        self.registered_mcp_ids = mcps
        self.cancelled: list[str] = []

    @property
    def is_active(self) -> bool:
        return True

    async def direct_agent(self, **frame: Any) -> dict[str, Any]:
        self.frames.append(frame)
        return {"ok": True, "text": self.answer}

    async def cancel(self, question_id: str) -> None:
        self.cancelled.append(question_id)

    @property
    def frame(self) -> dict[str, Any]:
        assert len(self.frames) == 1, f"expected one call, saw {len(self.frames)}"
        return self.frames[0]


def _session(bridge: RecordingBridge) -> ReachSession:
    return ReachSession(bridge=bridge, enable_game_query=False)


def _directive_answer(objective: str = "take_settlement", **extra: Any) -> str:
    """Shaped like a real JSON-mode answer: flat, and only what the schema asks for."""
    payload: dict[str, Any] = {
        "objective": objective,
        "reason": "Segesta is weakly held and Flavius is the nearer general.",
        "horizon": "short",
        "risk_posture": 0.2,
    }
    payload.update(extra)
    return json.dumps(payload)


# --- the campaign director -------------------------------------------------


async def test_the_campaign_director_is_asked_on_the_json_channel(campaign_brief: str):
    from comstar_game_ai.agent.reach.prompts import campaign_directive_question

    bridge = RecordingBridge(_directive_answer())
    directive = await agent_director.call_campaign_director(
        _session(bridge),
        text=campaign_directive_question(3, "julii"),
        context=campaign_brief,
        question_id="campaign-3",
    )

    frame = bridge.frame
    assert frame["agent_provider_id"] == "client.campaign_director"
    assert frame["response_format"] == {"type": "json_object"}
    assert directive.intent.objective == "take_settlement"
    assert directive.commentary.startswith("Segesta")


async def test_the_campaign_director_is_constrained_to_campaign_objectives():
    """The enum is a decoding constraint, so this is what it can possibly answer."""
    bridge = RecordingBridge(_directive_answer())
    await agent_director.call_campaign_director(
        _session(bridge), text="q", context="c", question_id="q-1"
    )

    objective = bridge.frame["json_schema"]["properties"]["objective"]
    assert objective["enum"] == list(CAMPAIGN_OBJECTIVES)


async def test_no_json_mode_call_asks_for_tools_it_cannot_run():
    """JSON mode runs no crew, so a requested MCP is a request the engine refuses."""
    bridge = RecordingBridge(_directive_answer(), mcps=("client.game_query",))
    await agent_director.call_campaign_director(
        _session(bridge), text="q", context="c", question_id="q-1"
    )

    assert bridge.frame["mcp_provider_ids"] == []


async def test_a_sanitized_answer_is_a_missing_directive_not_a_new_one():
    """`normal` is what the prose sanitizer left of a real directive."""
    bridge = RecordingBridge("normal")
    directive = await agent_director.call_campaign_director(
        _session(bridge), text="q", context="c", question_id="q-1"
    )

    assert directive.intent.objective == NEUTRAL_OBJECTIVE
    assert directive.commentary == "malformed_json"
    assert directive.intent.objective not in ADVANCING_OBJECTIVES


async def test_giving_up_locally_also_tells_the_engine_to_stop():
    """The engine runs one job at a time, install-wide, and keeps running an
    abandoned one to completion. A quiet timeout therefore holds the only slot until
    dead work finishes, and the next turn's directive queues behind an answer nobody
    will read."""

    class Slow(RecordingBridge):
        async def direct_agent(self, **frame: Any) -> dict[str, Any]:
            raise TimeoutError("too slow")

    bridge = Slow()
    directive = await agent_director.call_campaign_director(
        _session(bridge), text="q", context="c", question_id="q-slow"
    )

    assert bridge.cancelled == ["q-slow"]
    assert "timeout:" in directive.commentary


@pytest.mark.parametrize(
    "call",
    [
        lambda s, qid: agent_director.call_opponent_modeler(
            s, faction="gauls", question_id=qid
        ),
        lambda s, qid: agent_director.call_post_mortem(s, outcome="defeat", question_id=qid),
        lambda s, qid: agent_director.call_narrator(s, text="a moment", question_id=qid),
    ],
    ids=["structured", "prose", "narrator"],
)
async def test_no_agent_leaves_the_slot_held_on_timeout(call):
    class Slow(RecordingBridge):
        async def direct_agent(self, **frame: Any) -> dict[str, Any]:
            raise TimeoutError("too slow")

    bridge = Slow()
    await call(_session(bridge), "q-slow")

    assert bridge.cancelled == ["q-slow"]


async def test_an_engine_refusal_reaches_the_caller_as_neutral():
    from ao_reach.run_status import ReachRunError

    class Refusing(RecordingBridge):
        async def direct_agent(self, **frame: Any) -> dict[str, Any]:
            raise ReachRunError("unknown catalog id", code="invalid_request")

    directive = await agent_director.call_campaign_director(
        _session(Refusing()), text="q", context="c", question_id="q-1"
    )

    assert directive.intent.objective == NEUTRAL_OBJECTIVE
    assert "invalid_request" in directive.commentary


# --- the brief the directors read ------------------------------------------


def test_the_campaign_brief_shows_the_director_its_own_faction(campaign_brief: str):
    """The defect behind twenty turns of "hold": the map was never in the prompt."""
    brief = json.loads(campaign_brief)
    belief = brief["belief"]

    assert belief["is_empty"] is False
    assert belief["counts"]["own_characters"] == 2
    assert belief["counts"]["own_settlements"] == 1
    assert {c["name"] for c in belief["own_characters"]} == {
        "Flavius Julius",
        "Vibius Julius",
    }
    assert "arretium" in {s["name"] for s in belief["own_settlements"]}


def test_the_campaign_brief_separates_what_is_ours_from_what_is_not(campaign_brief: str):
    belief = json.loads(campaign_brief)["belief"]

    assert {s["name"] for s in belief["other_settlements"]} == {
        "segesta",
        "patavium",
        "mediolanium",
    }
    assert all(s["at"] for s in belief["other_settlements"])


async def test_an_empty_map_is_decided_without_asking_a_model(empty_belief, tmp_path):
    """No GPU call, and no instruction in the prompt about what to do with nothing.

    Carrying that instruction was worse than useless: the model reached for it on a
    turn where the map was full, answering "hold, the map is empty" with two idle
    generals and three reachable towns in the brief.
    """
    from comstar_game_ai.agent.runtime import AgentRuntime
    from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

    bridge = RecordingBridge(_directive_answer("attack"))
    runtime = AgentRuntime(
        directive_store=DirectiveStore(path=tmp_path / "directive.json"),
        session=ReachSession(bridge=bridge, enable_game_query=False),
    )
    runtime._fresh_belief = lambda: empty_belief  # type: ignore[method-assign]

    await runtime.deliberate_campaign_turn(1)

    assert bridge.frames == [], "asked a model about an empty map"
    stored = runtime.directive_store.read()
    assert stored is not None
    assert stored.to_directive().intent.objective == NEUTRAL_OBJECTIVE
    assert stored.to_directive().commentary == "belief_empty"


def test_the_prompt_carries_no_canned_answer_for_an_empty_map():
    from comstar_game_ai.agent.reach.prompts import campaign_directive_question

    question = campaign_directive_question(3, "julii").lower()

    assert "empty" not in question


def test_an_empty_brief_says_it_is_empty(empty_belief):
    from comstar_game_ai.agent.reach.context_builder import (
        ObservableContext,
        build_observable_brief,
    )

    brief = json.loads(
        build_observable_brief(
            ObservableContext(phase="campaign", turn=1, player_faction="julii"),
            empty_belief,
        )
    )

    assert brief["belief"]["is_empty"] is True
    assert brief["belief"]["counts"]["own_characters"] == 0


def test_the_question_tells_the_model_what_its_answer_will_do():
    """A model choosing a word without knowing the consequence is not deciding."""
    from comstar_game_ai.agent.reach.prompts import campaign_directive_question

    question = campaign_directive_question(3, "julii")

    assert "keep every character where it stands" in question
    for objective in CAMPAIGN_OBJECTIVES:
        assert objective in question, objective


def test_the_question_does_not_restate_the_schema():
    """Every token is read twice on the way in — once here, once as the grammar."""
    from comstar_game_ai.agent.reach.prompts import campaign_directive_question

    question = campaign_directive_question(3, "julii")

    assert '"type"' not in question
    assert "JSON" not in question
    assert len(question) < 900, len(question)


# --- the battle director ---------------------------------------------------


async def test_the_battle_director_gets_battle_objectives_only(battle_brief: str):
    from comstar_game_ai.agent.reach.prompts import battle_directive_question

    bridge = RecordingBridge(_directive_answer("annihilate"))
    directive = await agent_director.call_battle_director(
        _session(bridge),
        text=battle_directive_question(2, "segesta-assault"),
        context=battle_brief,
        question_id="battle-2",
    )

    offered = bridge.frame["json_schema"]["properties"]["objective"]["enum"]
    assert "annihilate" in offered
    assert "take_settlement" not in offered
    assert directive.intent.objective == "annihilate"


async def test_a_stale_battle_question_is_cancelled_before_the_next_one():
    bridge = RecordingBridge(_directive_answer("hold"))
    await agent_director.call_battle_director(
        _session(bridge),
        text="q",
        context="c",
        question_id="battle-3",
        stale_question_ids=["battle-2"],
    )

    assert bridge.cancelled == ["battle-2"]


# --- the analysts ----------------------------------------------------------


async def test_the_opponent_modeler_returns_a_read_not_prose(campaign_brief: str):
    answer = json.dumps(
        {
            "faction": "gauls",
            "posture": "aggressive",
            "likely_intent": "Push south from Mediolanium before Arretium reinforces.",
            "evidence": ["two stacks moved toward Patavium"],
            "confidence": 0.6,
        }
    )
    bridge = RecordingBridge(answer)
    read = await agent_director.call_opponent_modeler(
        _session(bridge), faction="gauls", context=campaign_brief, question_id="opp-1"
    )

    assert bridge.frame["agent_provider_id"] == "client.opponent_modeler"
    assert bridge.frame["response_format"] == {"type": "json_object"}
    assert read["posture"] == "aggressive"
    assert "gauls" in bridge.frame["text"]


async def test_the_consolidator_returns_proposals(after_action_context: str):
    answer = json.dumps(
        {
            "proposals": [
                {
                    "heading": "Never move a general alone",
                    "body": "Attach two units before advancing a general.",
                    "confidence": 0.8,
                }
            ]
        }
    )
    bridge = RecordingBridge(answer)
    result = await agent_director.call_consolidator(
        _session(bridge), record_count=3, context=after_action_context, question_id="con-1"
    )

    assert bridge.frame["agent_provider_id"] == "client.consolidator"
    assert result["proposals"][0]["heading"] == "Never move a general alone"


async def test_the_doctrine_ingestor_sorts_sections_by_destination(doctrine_document: str):
    answer = json.dumps(
        {
            "sections": [
                {"title": "Siege economics", "destination": "rule", "why": "checkable"},
                {"title": "Generals", "destination": "doctrine", "why": "standing"},
                {"title": "The Julii opening", "destination": "corpus", "why": "reference"},
            ]
        }
    )
    bridge = RecordingBridge(answer)
    result = await agent_director.call_doctrine_ingestor(
        _session(bridge),
        document_name="julii_opening.md",
        context=doctrine_document,
        question_id="doc-1",
    )

    assert {s["destination"] for s in result["sections"]} == {"rule", "doctrine", "corpus"}


async def test_an_unparseable_analysis_is_empty_rather_than_invented():
    """There is no neutral opponent read, so `{}` is the only honest answer."""
    bridge = RecordingBridge("I could not tell you.")
    read = await agent_director.call_opponent_modeler(
        _session(bridge), faction="gauls", context="", question_id="opp-1"
    )

    assert read == {}


# --- the prose agents ------------------------------------------------------


async def test_the_post_mortem_stays_on_the_prose_channel(after_action_context: str):
    """A person reads this, so sanitizing it is what the sanitizer is for."""
    bridge = RecordingBridge("The deficit was upkeep, not construction.")
    text = await agent_director.call_post_mortem(
        _session(bridge), outcome="defeat", context=after_action_context, question_id="pm-1"
    )

    assert "response_format" not in bridge.frame or bridge.frame["response_format"] is None
    assert text.startswith("The deficit")


async def test_the_narrator_never_breaks_the_turn():
    class Broken(RecordingBridge):
        async def direct_agent(self, **frame: Any) -> dict[str, Any]:
            raise TimeoutError("model busy")

    from comstar_game_ai.agent.reach.prompts import narrator_question

    text = await agent_director.call_narrator(
        _session(Broken()),
        text=narrator_question("Segesta fell to Flavius"),
        question_id="nar-1",
    )

    assert text == ""


@pytest.mark.parametrize(
    "agent_id",
    [
        agent_director.BATTLE_DIRECTOR,
        agent_director.CAMPAIGN_DIRECTOR,
        agent_director.OPPONENT_MODELER,
        agent_director.NARRATOR,
        agent_director.MODAL_VISION,
        agent_director.CONSOLIDATOR,
        agent_director.DOCTRINE_INGESTOR,
        agent_director.POST_MORTEM,
    ],
)
def test_every_registered_agent_has_a_way_to_be_called(agent_id: str):
    """Four of these were declared, packed, registered — and unreachable in code."""
    callers = {
        agent_director.BATTLE_DIRECTOR: agent_director.call_battle_director,
        agent_director.CAMPAIGN_DIRECTOR: agent_director.call_campaign_director,
        agent_director.OPPONENT_MODELER: agent_director.call_opponent_modeler,
        agent_director.NARRATOR: agent_director.call_narrator,
        agent_director.MODAL_VISION: agent_director.call_modal_vision,
        agent_director.CONSOLIDATOR: agent_director.call_consolidator,
        agent_director.DOCTRINE_INGESTOR: agent_director.call_doctrine_ingestor,
        agent_director.POST_MORTEM: agent_director.call_post_mortem,
    }
    assert callable(callers[agent_id])
