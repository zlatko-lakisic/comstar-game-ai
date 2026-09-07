"""What each agent is asked, in one place, so a test can ask the same thing.

Two rules were learned the expensive way and shape everything here.

**Say what the answer does.** The campaign director's `objective` decides whether an
army may move, and for twenty turns nothing in the prompt said so. A model choosing a
word without knowing its consequence is not making the decision we think we asked for.

**Do not restate the schema in prose.** In JSON mode the engine appends the schema and
hands it to the model as decoding constraints, so a hand-written copy in the question
is one more thing to drift. The question explains meaning and consequence; the schema
carries shape.
"""

from __future__ import annotations

from comstar_game_ai.agent.directive import ADVANCING_OBJECTIVES, CAMPAIGN_OBJECTIVES

# Derived, not typed out: the prompt's account of which objectives move an army has
# to be the same one the planner enforces, or it teaches the model a false rule.
_ADVANCING = tuple(o for o in CAMPAIGN_OBJECTIVES if o in ADVANCING_OBJECTIVES)
_HOLDING = tuple(o for o in CAMPAIGN_OBJECTIVES if o not in ADVANCING_OBJECTIVES)


def campaign_directive_question(turn: int, player_faction: str = "julii") -> str:
    """The turn-boundary strategic decision.

    Short on purpose. The context carries a belief brief and the engine appends the
    schema, and on a shared GPU the prompt was taking about fifty seconds to evaluate
    before the model wrote a token — so anything here that the schema already says is
    paid for twice and explains nothing.
    """
    advancing = ", ".join(_ADVANCING)
    holding = ", ".join(_HOLDING)
    return (
        f"You direct the {player_faction} faction in Total War: ROME REMASTERED, "
        f"turn {turn}. Choose this turn's objective from the provided context alone.\n\n"
        f"The choice has one consequence: {holding} keep every character where it "
        f"stands, while {advancing} let one general step toward the nearest "
        "settlement he does not own.\n\n"
        "Weigh the belief block: what you hold, which generals are free, and what "
        "stands near them. Advance when something is worth reaching and a general "
        "can reach it; hold when the position needs consolidating instead. Name the "
        "settlement or general you based the choice on, in one short sentence."
    )


def battle_directive_question(tick: int, battle_id: str) -> str:
    return (
        "You command the Roman line in a live Total War: ROME REMASTERED battle "
        f"({battle_id}, tick {tick}). Choose the intent from the provided context "
        "alone.\n\n"
        "The objective sets how much of the army you are willing to spend, and "
        "risk_posture runs from -1 (cautious) to 1 (reckless). The tick is short: "
        "decide with what you can see. Give one short sentence as the reason."
    )


def opponent_read_question(faction: str) -> str:
    return (
        f"Read the {faction} faction's intent from the evidence in the provided "
        "context, and nothing else.\n\n"
        "Report what their movements and holdings suggest they are trying to do, how "
        "aggressive they are, and what would change your read. Where the evidence is "
        "thin, say it is thin — a confident read of an empty map is worse than none, "
        "because it will be acted on."
    )


def narrator_question(moment: str) -> str:
    return (
        "Narrate this moment from the campaign in one or two terse sentences, in the "
        "voice of a Roman chronicler. No preamble, no lists, no restating the prompt.\n\n"
        f"Moment: {moment}"
    )


def consolidation_question(record_count: int) -> str:
    return (
        f"The provided context holds {record_count} after-action records from played "
        "campaigns. Propose doctrine that would have changed the outcome.\n\n"
        "Each proposal needs a heading, a body that states the rule in the imperative, "
        "and a confidence between 0 and 1 reflecting how much evidence stands behind "
        "it. Generalise across records — a rule drawn from a single battle is an "
        "anecdote. Propose nothing rather than padding the list."
    )


def doctrine_triage_question(document_name: str) -> str:
    return (
        f"Triage sections of the strategy document '{document_name}' in the provided "
        "context by where each belongs.\n\n"
        "- rule: a deterministic condition and action, checkable in code\n"
        "- doctrine: standing guidance worth carrying into every decision\n"
        "- corpus: reference detail, worth retrieving only when a question touches it\n\n"
        "Judge each section on what it is, not on how strongly it is written."
    )


def post_mortem_question(outcome: str) -> str:
    return (
        f"The campaign ended in {outcome}. Explain why, from the records in the "
        "provided context.\n\n"
        "Name the decisions that led there and the turns they were taken on. Prefer "
        "the uncomfortable explanation that fits the records over the flattering one "
        "that does not, and separate what the records show from what you infer. If "
        "the records do not explain the outcome, say what is missing."
    )
