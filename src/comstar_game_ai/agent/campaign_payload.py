"""Per-turn campaign director payload.

Ids only. Order matches the decision procedure: standing → threats → hold →
generals → candidates → treasury. Proper nouns are asserted absent.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_contract import CampaignDirective
from comstar_game_ai.agent.campaign_ids import (
    CampaignIdMap,
    sync_id_map_from_belief,
)
from comstar_game_ai.agent.json_safe import assert_json_round_trip, dumps_json_safe
from comstar_game_ai.agent.predictors.campaign_board import (
    Candidate,
    Threat,
    build_candidates,
    build_threats,
    estimate_garrison,
    turns_to_reach,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class StandingDirectiveView:
    objective: str
    actor: str | None
    target: str | None
    issued_turn: int
    commit_until_turn: int
    status: str
    turns_from_target: int | None = None

    def to_payload_block(self) -> str:
        if self.objective == "hold" or not self.actor:
            return f"hold, issued turn {self.issued_turn}, status: {self.status}"
        line = (
            f"{self.objective} {self.actor} -> {self.target}, "
            f"committed until turn {self.commit_until_turn}, issued turn {self.issued_turn}, "
            f"status: {self.status}"
        )
        if self.turns_from_target is not None:
            line += f", {self.turns_from_target} turns from target"
        return line


@dataclass
class CampaignPayload:
    question_id: str
    turn: int
    state_hash: str
    standing: StandingDirectiveView | None
    threats: list[Threat]
    you_hold: list[str]
    generals_free: list[str]
    candidates: list[Candidate]
    treasury: int | None
    income: int | None
    allowed_ids: set[str] = field(default_factory=set)
    id_map: CampaignIdMap = field(default_factory=CampaignIdMap)
    text: str = ""

    def belief_block_for_hash(self) -> str:
        """The belief portion that state_hash covers."""
        threat_lines = [th.to_payload_line() for th in self.threats] or ["none observed"]
        candidate_lines = [c.to_payload_line() for c in self.candidates] or ["(none)"]
        return "\n".join(
            [
                "THREATS",
                *threat_lines,
                "",
                "YOU HOLD",
                *self.you_hold,
                "",
                "GENERALS FREE",
                *self.generals_free,
                "",
                "CANDIDATES",
                *candidate_lines,
            ]
        )


def _own_faction(player_faction: str) -> set[str]:
    f = (player_faction or "julii").strip().lower()
    return {f, f"romans_{f}"}


def compute_state_hash(belief_block: str) -> str:
    return hashlib.sha256(belief_block.encode("utf-8")).hexdigest()[:8]


def assert_no_proper_nouns(payload_text: str, id_map: CampaignIdMap) -> None:
    """Acceptance 9: no settlement/general/faction name from the map appears."""
    import re

    offenders: list[str] = []
    for name in id_map.proper_nouns():
        if len(name) < 3:
            continue
        if name.lower().startswith(("set_", "gen_", "fac_")):
            continue
        # Whole-token match so `julii` does not false-positive inside `fac_julii`.
        if re.search(rf"(?<![a-z0-9_]){re.escape(name.lower())}(?![a-z0-9_])", payload_text.lower()):
            offenders.append(name)
    if offenders:
        raise AssertionError(
            f"proper nouns reached the director payload: {sorted(set(offenders))}"
        )


def compose_campaign_payload(
    *,
    belief: BeliefStore,
    question_id: str,
    turn: int,
    player_faction: str = "julii",
    standing: StandingDirectiveView | None = None,
    treasury: int | None = None,
    income: int | None = None,
    id_map: CampaignIdMap | None = None,
) -> CampaignPayload:
    """Build the per-turn payload. Dates are JSON-sanitised; nouns are asserted out."""
    id_map = sync_id_map_from_belief(belief, id_map)
    mine = _own_faction(player_faction)

    threats = build_threats(
        belief, id_map, player_faction=player_faction, current_turn=turn
    )
    candidates = build_candidates(
        belief, id_map, player_faction=player_faction, current_turn=turn
    )

    you_hold: list[str] = []
    for s in belief.get_settlements():
        if not any(m in (s.owner or "").lower() for m in mine):
            continue
        sid = id_map.settlement_id(s)
        garrison, _ = estimate_garrison(s)
        unrest = (s.attributes or {}).get("unrest", "low")
        age = int((s.attributes or {}).get("last_seen_turn", turn) or turn)
        age_turns = max(0, turn - age) if isinstance(age, int) else 0
        you_hold.append(
            f"{sid}  garrison {garrison}  unrest {unrest}  age {age_turns}"
        )
    you_hold.sort()

    generals_free: list[str] = []
    for c in belief.get_characters():
        if c.faction.strip().lower() not in mine:
            continue
        if not (c.x or c.y):
            continue
        role = (c.role or "").lower()
        if role and role not in {"", "general", "leader", "heir", "named character"}:
            continue
        gid = id_map.general_id(c)
        # Nearest owned or candidate settlement for "near / at" without names.
        near_id = None
        near_turns = None
        best = 10**9
        for s in belief.get_settlements():
            if not (s.x or s.y):
                continue
            t = turns_to_reach(from_x=c.x, from_y=c.y, to_x=s.x, to_y=s.y)
            if t < best:
                best = t
                near_id = id_map.settlement_id(s)
                near_turns = t
        strength = "moderate"
        if near_id is not None and near_turns == 0:
            generals_free.append(f"{gid}  at {near_id}, idle, strength {strength}")
        elif near_id is not None:
            generals_free.append(
                f"{gid}  near {near_id}, {near_turns} turns out, strength {strength}"
            )
        else:
            generals_free.append(f"{gid}  idle, strength {strength}")
    generals_free.sort()

    hold_lines = you_hold or ["(none)"]
    general_lines = generals_free or ["(none)"]
    threat_lines = [th.to_payload_line() for th in threats] or ["none observed"]
    candidate_lines = [c.to_payload_line() for c in candidates] or ["(none)"]
    belief_block = "\n".join(
        [
            "THREATS",
            *threat_lines,
            "",
            "YOU HOLD",
            *hold_lines,
            "",
            "GENERALS FREE",
            *general_lines,
            "",
            "CANDIDATES",
            *candidate_lines,
        ]
    )
    state_hash = compute_state_hash(belief_block)

    standing_block = (
        standing.to_payload_block() if standing is not None else "none"
    )
    treasury_line = ""
    if treasury is not None or income is not None:
        t = f"TREASURY {treasury}" if treasury is not None else "TREASURY unknown"
        i = f"INCOME {income:+d}" if income is not None else ""
        treasury_line = f"\n{t}   {i}".rstrip()

    text = (
        f"question_id: {question_id}\n"
        f"turn: {turn}\n"
        f"state_hash: {state_hash}\n"
        f"\n"
        f"STANDING DIRECTIVE\n"
        f"{standing_block}\n"
        f"\n"
        f"{belief_block}"
        f"{treasury_line}\n"
    )

    # C0: round-trip through JSON so a date never reaches Reach.
    assert_json_round_trip({"payload": text, "turn": turn, "question_id": question_id})
    # C9a / acceptance 9.
    assert_no_proper_nouns(text, id_map)

    allowed = id_map.all_ids()
    # Also allow ids that appear in the payload text itself.
    for token in text.split():
        if token.startswith(("gen_", "set_", "fac_")):
            allowed.add(token.strip(",").lower())

    return CampaignPayload(
        question_id=question_id,
        turn=turn,
        state_hash=state_hash,
        standing=standing,
        threats=threats,
        you_hold=you_hold,
        generals_free=generals_free,
        candidates=candidates,
        treasury=treasury,
        income=income,
        allowed_ids=allowed,
        id_map=id_map,
        text=text,
    )


def pathfinder_turns_for(
    payload: CampaignPayload,
    *,
    actor: str | None,
    target: str | None,
) -> int | None:
    """Look up computed turns for an actor→target pair from the candidate list."""
    if not actor or not target:
        return None
    for c in payload.candidates:
        if c.settlement_id == target and c.nearest_general_id == actor:
            return c.turns_to_reach
        if c.settlement_id == target:
            return c.turns_to_reach
    return None


def predictor_garrison_for(payload: CampaignPayload, target: str | None) -> str | None:
    if not target:
        return None
    for c in payload.candidates:
        if c.settlement_id == target:
            return c.garrison
    return None


def dumps_payload_for_reach(payload: CampaignPayload) -> str:
    """Context string handed to Reach — already noun-checked and JSON-safe."""
    return dumps_json_safe({"campaign_payload": payload.text})
