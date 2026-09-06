"""Selected agents on the campaign map: range, path, HUD, and how they are sent.

Clicking a spy or diplomat paints a green movement range for the rest of this
turn. A destination click, or a held left-drag from the character, draws the
path the agent will take. Releasing the drag back on the character cancelled
the order; releasing off the character is expected to issue it. Do not click a
destination just to look.

The selection HUD is three parchments, not one:

* **Left.** Name, type, location, age, and the type's skill (Influence for a
  diplomat, Subterfuge for a spy). Three small buttons sit under the portrait.
  The enabled one this turn opened the character scroll; its tooltip is
  'Character's traits and Followers'. Alt+click is the wiki. The other two
  were gray. Official strings for a gray bodyguard button are
  `TMT_NO_BODYGUARD_UNIT_TO_VIEW` / `TMT_SHOW_GENERAL_UNIT_DETAILS`.
* **Centre.** Header with cycle arrows. Two slot rows labelled 'Your Agents'
  and 'Other Factions' Agents' — agents at this place, not the overview
  Move Followers tab. The hooded HUD tab is lit. A magnifier on the right of
  this strip focuses the camera. The boot to its right is Disband.
* **Right.** A send list titled by type: 'SEND EMISSARY' with 'Negotiate with
  …', or 'SEND SPY' with 'Spy on …'. Each row shows a success percentage and
  a turn glyph. The glyph is travel time — that is how far the target is.
  Do not infer closeness from who stands next to the agent on the 3D map.
  Closest is a read, not a reason to send. Sending is three clicks: the row
  draws the path, the send-panel Confirm opens 'Send Agent to: <target>',
  and Assign commits. A hooded disc on that footer opens the overview Agent
  Hub (Ctrl+7). The hourglass at the screen corner is End Turn, not Confirm.

The boot Disbands. The direct send is a left-click on the map target once
the cursor glyph changes. The 2004 cursor strings (`diplomacy_mission`,
`spy_mission`, `assassination_mission`) still say 'Right click to …';
Remastered issues the order on that left-click. The SEND list is the other
dispatcher: row, Confirm, Assign. No assassin was on the map this turn, so
an assassin send-list title was not read.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentKind:
    id: str
    #: On-screen type word (`ST_DIPLOMAT` / `ST_SPY` / `ST_ASSASSIN`).
    type_name: str
    #: Title of the right-hand send list when this type is selected.
    send_title: str
    #: Verb on each send-list row.
    send_verb: str
    skill_name: str
    #: Cursor-action tooltip key for a right-click mission.
    mission_action: str


#: Assassin send-list title was not on screen this turn. The verb is the
#: shipped `SMT_ASSASSINATE`; do not invent a 'SEND …' heading for it.
KINDS: tuple[AgentKind, ...] = (
    AgentKind(
        id="diplomat",
        type_name="Diplomat",
        send_title="SEND EMISSARY",
        send_verb="Negotiate with",
        skill_name="Influence",
        mission_action="diplomacy_mission",
    ),
    AgentKind(
        id="spy",
        type_name="Spy",
        send_title="SEND SPY",
        send_verb="Spy on",
        skill_name="Subterfuge",
        mission_action="spy_mission",
    ),
    AgentKind(
        id="assassin",
        type_name="Assassin",
        send_title="",
        send_verb="Assassinate",
        skill_name="",
        mission_action="assassination_mission",
    ),
)


@dataclass(frozen=True)
class HudControl:
    id: str
    centre: tuple[float, float]
    purpose: str
    #: Empty when the control is safe to hover; a warning when a click mutates.
    hazard: str = ""


#: Centres measured on agent_located_0.png (diplomat) and confirmed against
#: the spy frame. Hover first; several sit next to the map.
CONTROLS: tuple[HudControl, ...] = (
    HudControl(
        id="traits_followers",
        centre=(0.090, 0.960),
        purpose=(
            "Left-panel button. Tooltip: 'Character's traits and Followers'. "
            "Opens the character scroll on TRAITS & FOLLOWERS."
        ),
        hazard="Alt+click opens the Steam wiki, same as F1.",
    ),
    HudControl(
        id="bodyguard",
        centre=(0.120, 0.960),
        purpose=(
            "Left-panel button, gray this turn on both agents. Official disabled "
            "string is 'There is no bodyguard unit to view for this character'."
        ),
    ),
    HudControl(
        id="left_third",
        centre=(0.140, 0.960),
        purpose=(
            "Left-panel button, gray this turn. Official names nearby are "
            "'Show this character's information scroll' and the family-tree "
            "tooltip; the hover did not land cleanly enough to pick one."
        ),
        hazard="Do not click to find out. Family Tree can set the faction heir.",
    ),
    HudControl(
        id="locate",
        centre=(0.655, 0.940),
        purpose="Magnifier on the centre strip. Frames the selected agent.",
    ),
    HudControl(
        id="disband",
        centre=(0.715, 0.940),
        purpose="Boot on the bottom-right of the centre strip. Disbands the agent.",
        hazard="Permanent. Delete is bound to the same action. Do not press either.",
    ),
    HudControl(
        id="send_hub",
        centre=(0.855, 0.960),
        purpose=(
            "Hooded disc on the send-list footer. Opens the overview Agent Hub, "
            "the same dialog as Ctrl+7."
        ),
        hazard="The Hub's Confirm button dispatches. Close with the overview X.",
    ),
    HudControl(
        id="send_confirm",
        centre=(0.900, 0.930),
        purpose=(
            "Gold Confirm on the send-list footer after a row is selected. "
            "Opens 'Send Agent to: <target>' with Cancel Mission and Assign. "
            "Not the corner hourglass."
        ),
        hazard="Next step toward dispatch. End Turn is further right at (0.980, 0.971).",
    ),
    HudControl(
        id="assign_mission",
        centre=(0.830, 0.940),
        purpose=(
            "Assign this mission to <name>. Commits the staged send. Both the "
            "spy and the diplomat were assigned this way to Patavium."
        ),
        hazard="This is the commit. Lists then shows Target and Cancel Mission.",
    ),
)

#: Character scroll opened from the traits button. Same left/right as the
#: overview frame, but the top sits lower, so it is not a Ctrl+N tab.
CHARACTER_SCROLL_LEFT = 0.256
CHARACTER_SCROLL_RIGHT = 0.743
CHARACTER_SCROLL_TOP = 0.261
CHARACTER_SCROLL_CLOSE_X = (0.740, 0.275)

#: Right-hand send list on the selection HUD. A row click stages; Assign commits.
SEND_LIST_BOUNDS = (0.84, 0.74, 0.97, 0.92)
SEND_FIRST_ROW = (0.90, 0.800)
#: Travel time drawn on each row as `[1]`, `[2]`, … . Smaller is nearer.
#: Character rows and settlement rows are mixed; compare glyphs within a type.
SEND_DISTANCE_READ = "turn_glyph"

#: Lists → Agents sub-tab and the two discs on the agent detail pane.
#: Footer button 3 on the Settlements pane sets the capital — never that one.
LISTS_AGENTS_TAB = (0.65, 0.259)
LISTS_LOCATE = (0.72, 0.52)
LISTS_HUB = (0.68, 0.52)

BY_KIND: dict[str, AgentKind] = {kind.id: kind for kind in KINDS}
BY_CONTROL: dict[str, HudControl] = {control.id: control for control in CONTROLS}


def seen_kinds() -> tuple[AgentKind, ...]:
    """Types whose send-list title was read off the screen this turn."""
    return tuple(kind for kind in KINDS if kind.send_title)


def mutating_controls() -> tuple[HudControl, ...]:
    return tuple(control for control in CONTROLS if control.hazard)
