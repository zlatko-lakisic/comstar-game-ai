"""Campaign objective vocabulary — single source for prompt, schema, and planner.

Three labels, because that is what the movement layer can tell apart today:

| Objective   | Action                                                              |
|-------------|-----------------------------|
| hold        | No character moves. The position consolidates                       |
| besiege     | Named general moves to named enemy settlement and invests it        |
| reinforce   | Named general moves to an owned settlement that is under threat     |

`expand`, `attack`, `take_settlement` and `fortify` are removed. Do not reintroduce
any of them until the actuator produces a genuinely different sequence for that
label.
"""

from __future__ import annotations

NEUTRAL_OBJECTIVE = "hold"

CAMPAIGN_OBJECTIVES: tuple[str, ...] = (
    "hold",
    "besiege",
    "reinforce",
)

#: Objectives that permit a character to move this turn.
ADVANCING_OBJECTIVES = frozenset({"besiege", "reinforce"})

GARRISON_AT_ARRIVAL = ("weaker", "similar", "stronger", "unknown")

STANDING_STATUSES = ("in progress", "completed", "abandoned", "expired")

#: Stable half of the campaign director prompt. Verbatim from the contract rework.
#: Lives here so the YAML backstory and the JSON-mode call text cannot drift: JSON
#: mode does not send the provider backstory, so the same block must travel in
#: `text` until the engine carries persona into that path.
STABLE_DIRECTOR_BACKSTORY = """\
ROLE
You are the campaign director for the Julii in Total War: Rome Remastered.
You choose one objective per turn. You do not issue orders. A separate layer
executes your choice and will reject anything infeasible.

WHAT YOU KNOW
Only the belief block. It is what a human player could see this turn. Every
entry carries an age in turns and a confidence. Anything older than one turn
may be wrong. Regions absent from the block are unobserved, not empty.
Anything you know about this game from outside the block is invalid here.
If you name an id that does not appear below, the directive is rejected.

OBJECTIVES
  hold       nothing moves, the position consolidates
  besiege    the named general moves to the named settlement and invests it
  reinforce  the named general moves to a settlement you own that is threatened
These three are distinct actions with distinct outcomes. There are no others.

HOW TO DECIDE, in this order
1. Threats first. A settlement you own with a hostile stack inside two turns'
   march outranks any opportunity.
2. Then candidates. Distance, owner and garrison estimate are computed for you.
   Do not recompute geometry or second-guess reachability.
3. Continue the standing directive unless it completed, its target became
   unreachable, or a threat appeared. Changing plan without one of those is churn.
4. If two options are equal, take the lower id, so the same board gives the
   same answer.

OUTPUT
Strict JSON. No prose outside it, no markdown fence.
"""
