"""Diplomatic standing in belief (offline seed + live updates).

Standing is per faction relative to the player: at_war | neutral | ally | unknown.
Attack *priority* is a separate tier order (rebels first) — see ``attack_tier``.
Used by the expansion picker; map war-confirm Yes flips a target to at_war.
"""

from __future__ import annotations

from typing import Any, Literal

from comstar_game_ai.agent.belief.store import BeliefStore

DiplomaticStanding = Literal["at_war", "neutral", "ally", "unknown"]

#: Diplomatic table only (rebels may still be stored as neutral).
STANDING_RANK: dict[DiplomaticStanding, int] = {
    "at_war": 0,
    "neutral": 1,
    "ally": 2,
    "unknown": 3,
}

#: Attack target tiers. Exhaust an earlier tier before considering a later one.
AttackTier = Literal["rebel", "enemy", "neutral", "ally", "unknown"]

ATTACK_TIER_RANK: dict[AttackTier, int] = {
    "rebel": 0,
    "enemy": 1,
    "neutral": 2,
    "ally": 3,
    "unknown": 4,
}

_BELIEF_KEY = "diplomatic_standing"
_PLAYER_KEY = "player_faction"

#: Rebels are never allies for expansion ranking.
_REBEL_TOKENS = frozenset({"slave", "rebels", "rebel"})


def normalize_standing(raw: str | None) -> DiplomaticStanding:
    text = (raw or "").strip().lower().replace(" ", "_")
    if text in {"at_war", "war", "enemy", "hostile"}:
        return "at_war"
    if text in {"ally", "allied", "allies"}:
        return "ally"
    if text in {"neutral", "peace"}:
        return "neutral"
    if text in {"rebel", "rebels", "slave"}:
        # Diplomatic table has no rebel row; callers use attack_tier for priority.
        return "neutral"
    return "unknown"


def standing_rank(standing: DiplomaticStanding | str) -> int:
    return STANDING_RANK.get(normalize_standing(str(standing)), 3)


def is_rebel_faction(faction: str) -> bool:
    name = (faction or "").strip().lower()
    return name in _REBEL_TOKENS or name.endswith("_rebels")


def attack_tier(
    *,
    faction: str = "",
    standing: DiplomaticStanding | str | None = None,
) -> AttackTier:
    """Map owner + diplomatic standing to the attack priority tier.

    Order (exhaust each before the next): rebel → enemy → neutral → ally.
    Faction identity decides rebel; standing decides the rest.
    """
    if is_rebel_faction(faction):
        return "rebel"
    text = (standing or "").strip().lower().replace(" ", "_")
    if text in {"rebel", "rebels", "slave"}:
        return "rebel"
    s = normalize_standing(standing)
    if s == "at_war":
        return "enemy"
    if s == "ally":
        return "ally"
    if s == "neutral":
        return "neutral"
    return "unknown"


def attack_tier_rank(
    *,
    faction: str = "",
    standing: DiplomaticStanding | str | None = None,
) -> int:
    return ATTACK_TIER_RANK[attack_tier(faction=faction, standing=standing)]


def get_player_faction(belief: BeliefStore) -> str:
    raw = belief.faction_beliefs.get(_PLAYER_KEY)
    if isinstance(raw, dict):
        return str(raw.get("name") or "").strip().lower()
    if isinstance(raw, str):
        return raw.strip().lower()
    return ""


def set_player_faction(belief: BeliefStore, faction: str) -> None:
    belief.faction_beliefs[_PLAYER_KEY] = {"name": (faction or "").strip().lower()}


def get_standings(belief: BeliefStore) -> dict[str, DiplomaticStanding]:
    raw = belief.faction_beliefs.get(_BELIEF_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, DiplomaticStanding] = {}
    for key, value in raw.items():
        out[str(key).strip().lower()] = normalize_standing(str(value))
    return out


_ROMAN_HOUSES = frozenset({"julii", "brutii", "scipii", "senate"})


def _is_roman_house(faction: str) -> bool:
    name = (faction or "").strip().lower()
    if name.startswith("romans_"):
        name = name[len("romans_") :]
    return name in _ROMAN_HOUSES


def get_standing(belief: BeliefStore, faction: str) -> DiplomaticStanding:
    name = (faction or "").strip().lower()
    if not name:
        return "unknown"
    standings = get_standings(belief)
    if name in standings:
        return standings[name]
    # Roman house aliases: romans_julii ↔ julii
    if name.startswith("romans_"):
        short = name[len("romans_") :]
        if short in standings:
            return standings[short]
    else:
        long = f"romans_{name}"
        if long in standings:
            return standings[long]
    # Fellow Roman houses are allies even if descr_strat pairs were incomplete.
    player = get_player_faction(belief)
    if player and _is_roman_house(player) and _is_roman_house(name) and name != player:
        player_short = player[len("romans_") :] if player.startswith("romans_") else player
        name_short = name[len("romans_") :] if name.startswith("romans_") else name
        if player_short != name_short:
            return "ally"
    if is_rebel_faction(name):
        return "neutral"
    return "unknown"


def set_standing(belief: BeliefStore, faction: str, standing: DiplomaticStanding) -> None:
    name = (faction or "").strip().lower()
    if not name:
        return
    table = dict(get_standings(belief))
    table[name] = normalize_standing(standing)
    belief.faction_beliefs[_BELIEF_KEY] = table


def seed_standings_from_allies(
    belief: BeliefStore,
    *,
    player_faction: str,
    ally_pairs: list[tuple[str, str]],
    known_factions: set[str] | None = None,
) -> dict[str, DiplomaticStanding]:
    """Write opening standings: ally pairs → ally; everyone else → neutral.

    ``faction_relationships`` in descr_strat lists opening alliances. Factions not
    listed default to neutral. Rebels are never seeded as ally.
    """
    player = (player_faction or "").strip().lower()
    set_player_faction(belief, player)
    allies: set[str] = set()
    for a, b in ally_pairs:
        left = (a or "").strip().lower()
        right = (b or "").strip().lower()
        if not left or not right:
            continue
        if left == player:
            allies.add(right)
        elif right == player:
            allies.add(left)

    factions = set(known_factions or set())
    factions.update(allies)
    for s in belief.get_settlements():
        owner = (s.owner or "").strip().lower()
        if owner and owner != player:
            factions.add(owner)

    table: dict[str, DiplomaticStanding] = {}
    for faction in sorted(factions):
        if faction == player or faction == f"romans_{player}" or player == f"romans_{faction}":
            continue
        if is_rebel_faction(faction):
            table[faction] = "neutral"
        elif faction in allies:
            table[faction] = "ally"
        elif _is_roman_house(player) and _is_roman_house(faction):
            table[faction] = "ally"
        else:
            table[faction] = "neutral"
    belief.faction_beliefs[_BELIEF_KEY] = table
    return table


def mark_at_war(belief: BeliefStore, faction: str) -> None:
    """After confirming a declare-war dialog."""
    set_standing(belief, faction, "at_war")


def standing_to_dict(belief: BeliefStore) -> dict[str, Any]:
    return {
        "player_faction": get_player_faction(belief),
        "standings": dict(get_standings(belief)),
    }
