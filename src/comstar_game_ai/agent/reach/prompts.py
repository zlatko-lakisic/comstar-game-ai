"""What each agent is asked, in one place, so a test can ask the same thing.

Campaign: the stable half lives in `campaign_vocab.STABLE_DIRECTOR_BACKSTORY` and
the provider YAML backstory. The per-turn question only carries identity; the
variable board state is the composed payload in `context`.
"""

from __future__ import annotations

from comstar_game_ai.agent.campaign_vocab import STABLE_DIRECTOR_BACKSTORY


def campaign_directive_question(turn: int, player_faction: str = "julii", *, question_id: str = "") -> str:
    """Per-turn question. Stable instructions are prepended for JSON mode."""
    qid = question_id or f"campaign-{turn}"
    return (
        f"{STABLE_DIRECTOR_BACKSTORY}\n"
        f"\n"
        f"TURN\n"
        f"Faction {player_faction}. Turn {turn}. question_id={qid}.\n"
        f"The variable board state is in context. Echo question_id. "
        f"Strict JSON matching the schema. No markdown fence.\n"
    )


def battle_directive_question(tick: int, battle_id: str) -> str:
    return (
        f"Battle {battle_id}, tick {tick}. Choose this tick's battle objective "
        f"from the provided context alone. Return one JSON object."
    )


def opponent_read_question(faction: str) -> str:
    return f"Read the posture of faction {faction}. Return one JSON object."


def consolidation_question(record_count: int) -> str:
    return (
        f"Consolidate {record_count} after-action records into doctrine proposals. "
        f"Return one JSON object."
    )


def doctrine_triage_question(document_name: str) -> str:
    return f"Triage doctrine document {document_name}. Return one JSON object."


def post_mortem_question(battle_id: str) -> str:
    return f"Post-mortem for battle {battle_id}. Return one JSON object."


def narrator_question(summary: str) -> str:
    """Cosmetic prose for the overlay; names are fine here."""
    return f"Narrate briefly: {summary}"
