"""Every agent, live against ada, judged on whether the answer is usable.

Run with `pytest tests/e2e -m integration_ada --run-integration-ada`.

These assertions are deliberately about adequacy rather than absence of exceptions.
The suite this replaces asserted that `run_deliberate_once` returned 0 — which it does
on every failure path, because a failed directive call returns a neutral directive and
the run carries on. It passed happily through twenty turns of a broken channel.

So here, a neutral directive is a failure. `neutral_directive` stamps its reason into
`commentary` (`malformed_json`, `timeout:…`, `reach_error:…`), and every one of those
means no model decided anything.
"""

from __future__ import annotations

import pytest

from comstar_game_ai.agent.directive import (
    ADVANCING_OBJECTIVES,
    BATTLE_OBJECTIVES,
    CAMPAIGN_OBJECTIVES,
    Directive,
)
from comstar_game_ai.agent.reach import director as agent_director
from comstar_game_ai.agent.reach.context_builder import (
    ObservableContext,
    build_observable_brief,
)
from comstar_game_ai.agent.reach.prompts import (
    battle_directive_question,
    campaign_directive_question,
    narrator_question,
)

#: The loop scope has to match `live_session`'s, or the bridge's receive task sits on
#: a loop these tests never run, and every call fails as a timeout the engine can
#: prove it answered. See the fixture.
pytestmark = [
    pytest.mark.integration_ada,
    pytest.mark.asyncio(loop_scope="module"),
]

#: Exactly what `neutral_directive` writes when no model decided. Matched precisely
#: rather than by substring, because the model's own reasons are free text and it
#: turned out to have a good one that contained a marker: asked about an empty map it
#: answered "map is empty", and a loose check called that a failure.
BARE_FALLBACKS = frozenset({"empty", "malformed_json", "not_object", "unfenced_json"})
PREFIXED_FALLBACKS = ("timeout:", "reach_error:", "error:")


def assert_a_model_decided_this(directive: Directive) -> None:
    reason = directive.commentary.strip()

    assert reason, "no reason given: nothing explained the choice"
    assert reason not in BARE_FALLBACKS, f"directive is a fallback, not a decision: {reason!r}"
    assert not reason.startswith(PREFIXED_FALLBACKS), (
        f"directive is a fallback, not a decision: {reason!r}"
    )


async def test_the_campaign_director_decides_from_the_map(live_session, campaign_brief):
    directive = await agent_director.call_campaign_director(
        live_session,
        text=campaign_directive_question(3, "julii"),
        context=campaign_brief,
        question_id="e2e-campaign-3",
    )

    assert_a_model_decided_this(directive)
    assert directive.intent.objective in CAMPAIGN_OBJECTIVES
    assert all(a in {"list_characters", "list_units"} for a in directive.focus_actions)
    print(f"\ncampaign_director: {directive.intent.objective} — {directive.commentary}")


async def test_the_campaign_director_advances_when_there_is_something_to_take(
    live_session, campaign_brief
):
    """Two free generals, one town held, three within reach.

    Holding here is a defensible answer for a human, but it is the answer we got for
    twenty turns from a director that could see nothing, so the test is what tells
    those two situations apart.
    """
    directive = await agent_director.call_campaign_director(
        live_session,
        text=campaign_directive_question(3, "julii"),
        context=campaign_brief,
        question_id="e2e-campaign-advance",
    )

    assert_a_model_decided_this(directive)
    assert directive.intent.objective in ADVANCING_OBJECTIVES, (
        f"chose {directive.intent.objective} with two idle generals and three "
        f"reachable towns: {directive.commentary}"
    )


async def test_the_campaign_director_names_what_it_decided_from(live_session, campaign_brief):
    """Grounding, not eloquence: the reason has to point at something in the brief.

    The failure this catches is a model answering from the shape of the question
    rather than from the map — which it did, confidently, when the prompt contained
    a sentence about empty maps that it could reach for instead of looking.
    """
    directive = await agent_director.call_campaign_director(
        live_session,
        text=campaign_directive_question(3, "julii"),
        context=campaign_brief,
        question_id="e2e-campaign-grounded",
    )

    assert_a_model_decided_this(directive)
    named = (
        "arretium",
        "ariminum",
        "segesta",
        "patavium",
        "mediolanium",
        "flavius",
        "vibius",
        "quintus",
        "lucius",
    )
    assert any(name in directive.commentary.lower() for name in named), (
        f"reason names nothing on the map: {directive.commentary!r}"
    )


async def test_the_battle_director_decides_a_battle(live_session, battle_brief):
    directive = await agent_director.call_battle_director(
        live_session,
        text=battle_directive_question(2, "segesta-assault"),
        context=battle_brief,
        question_id="e2e-battle-2",
    )

    assert_a_model_decided_this(directive)
    assert directive.intent.objective in BATTLE_OBJECTIVES
    assert 0.0 <= directive.intent.acceptable_own_losses <= 1.0
    print(f"\nbattle_director: {directive.intent.objective} — {directive.commentary}")


async def test_the_opponent_modeler_reads_a_faction(live_session, campaign_brief):
    read = await agent_director.call_opponent_modeler(
        live_session, faction="gauls", context=campaign_brief, question_id="e2e-opp"
    )

    assert read, "opponent read came back empty"
    assert read["posture"] in {
        "passive",
        "defensive",
        "opportunistic",
        "aggressive",
        "unknown",
    }
    assert str(read.get("likely_intent") or "").strip()
    assert 0.0 <= float(read["confidence"]) <= 1.0
    print(f"\nopponent_modeler: {read['posture']} — {read['likely_intent']}")


async def test_the_consolidator_generalises_across_records(live_session, after_action_context):
    result = await agent_director.call_consolidator(
        live_session,
        record_count=3,
        context=after_action_context,
        question_id="e2e-consolidator",
    )

    proposals = result.get("proposals") or []
    assert proposals, "no doctrine proposed from three records"
    for proposal in proposals:
        assert str(proposal.get("heading") or "").strip()
        assert str(proposal.get("body") or "").strip()
        assert 0.0 <= float(proposal.get("confidence", -1)) <= 1.0
    print(f"\nconsolidator: {[p['heading'] for p in proposals]}")


async def test_the_doctrine_ingestor_sorts_a_document(live_session, doctrine_document):
    result = await agent_director.call_doctrine_ingestor(
        live_session,
        document_name="julii_opening.md",
        context=doctrine_document,
        question_id="e2e-doctrine",
    )

    sections = result.get("sections") or []
    assert sections, "document came back unsorted"
    assert all(s["destination"] in {"rule", "doctrine", "corpus"} for s in sections)
    print(f"\ndoctrine_ingestor: {[(s['title'], s['destination']) for s in sections]}")


async def test_the_post_mortem_explains_from_the_records(live_session, after_action_context):
    text = await agent_director.call_post_mortem(
        live_session,
        outcome="a campaign that stalled in deficit",
        context=after_action_context,
        question_id="e2e-postmortem",
    )

    assert len(text) > 80, f"post-mortem too thin to be an explanation: {text!r}"
    # The records say the deficit was upkeep from new family members. An answer that
    # touches none of that is not reading them.
    assert any(
        word in text.lower()
        for word in ("upkeep", "bodyguard", "family", "general", "deficit", "income")
    ), text
    print(f"\npost_mortem: {text[:200]}")


async def test_the_narrator_says_one_thing(live_session):
    text = await agent_director.call_narrator(
        live_session,
        text=narrator_question("Segesta fell to Flavius Julius after a short assault"),
        question_id="e2e-narrator",
    )

    assert text.strip(), "narrator returned nothing"
    assert len(text) < 600, f"narrator wrote an essay: {text!r}"
    print(f"\nnarrator: {text}")


async def test_the_vision_agent_answers_in_the_shape_the_parser_expects(live_session):
    """The channel, not the eyesight: image encoding out, parseable JSON back.

    Accuracy on real dialogs is settled in front of the game; what can break silently
    here is the transport — a vision model that answers in prose, or an image the
    engine never routes to a multimodal completion.
    """
    from comstar_game_ai.game_io.campaign.modal import (
        _parse_modal_vision_result,
        build_modal_vision_prompt,
        vision_crop_bounds,
    )

    image = _diplomacy_scroll()
    crop_bounds = vision_crop_bounds(image)
    from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images

    images, _ = compose_reach_images(
        [image], budget=ViewBudget(max_images=1, width=1280, height=720, jpeg_quality=85)
    )
    assert images, "nothing to send"

    text = await agent_director.call_modal_vision(
        live_session,
        text=build_modal_vision_prompt(ui_mode="", crop_bounds=crop_bounds),
        context="turn=3. Independently inspect the pixels.",
        question_id="e2e-vision",
        images=images,
        timeout=90.0,
        raise_errors=True,
    )

    assert text.strip(), "vision agent returned nothing"
    parsed = _parse_modal_vision_result(text, request_id="e2e-vision")
    assert parsed is not None, f"unparseable vision answer: {text[:400]!r}"
    print(f"\nmodal_vision: kind={parsed.modal_kind} candidates={len(parsed.candidates)}")


def _diplomacy_scroll():
    """A parchment panel with a green check and a red X, drawn rather than captured.

    Enough of the real thing to exercise the channel without committing a screenshot
    of someone's campaign to the repository.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1920, 1080), (18, 20, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle((660, 300, 1260, 780), fill=(226, 205, 160), outline=(120, 96, 54), width=6)
    draw.rectangle((700, 360, 1220, 620), fill=(214, 191, 145))
    draw.ellipse((820, 680, 890, 750), fill=(86, 138, 62), outline=(40, 70, 30), width=4)
    draw.line((836, 715, 852, 735), fill=(240, 240, 220), width=8)
    draw.line((852, 735, 878, 695), fill=(240, 240, 220), width=8)
    draw.ellipse((1010, 680, 1080, 750), fill=(158, 52, 44), outline=(80, 24, 20), width=4)
    draw.line((1028, 698, 1062, 732), fill=(240, 240, 220), width=8)
    draw.line((1062, 698, 1028, 732), fill=(240, 240, 220), width=8)
    return image
