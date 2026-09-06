"""Where each campaign question is answered, and what looks like an answer but is not.

The atlas says what a panel is. This says which surface to *read* for a given
question. Several surfaces often show a number that looks like the same fact;
only one of them is authoritative, and trusting the others is how the agent
plans on a coin figure of 184 while Lists says the town's income is 1710.

Surfaces are named by the atlas / region / overlay id when one exists. A few
reads have no panel id — a settlement hover, the treasury HUD — and are named
here as such rather than invented as panels.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InfoSource:
    id: str
    #: The question the agent is actually asking.
    question: str
    #: Atlas panel id, region id, overlay layer id, or a named primitive.
    surface: str
    #: How to get the answer without mutating the campaign.
    how: str
    #: What this surface is the right place to read.
    reads: str
    #: What looks like the same fact and is not.
    trap: str = ""


SOURCES: tuple[InfoSource, ...] = (
    InfoSource(
        id="settlement_owner",
        question="Who owns this settlement, and how do we stand with them?",
        surface="settlement_hover",
        how="Hover the settlement on the 3D map until the tooltip fires. Do not click.",
        reads=(
            "Name, owning faction, tier, and a standing suffix: (At war), (Neutral), "
            "(Ally). No suffix means it is ours. Owned towns also offer "
            "'x2 to get further information'."
        ),
        trap="Pills are a prefilter, not a verdict. Never infer owner from colour alone.",
    ),
    InfoSource(
        id="settlement_activity",
        question="Which of our towns still need orders?",
        surface="map_overlay.settlements",
        how="Open Map Overlay (eye, or Tab). Settlements is a checkbox — leave it ticked.",
        reads=(
            "Activity states the hover cannot give: recruiting or constructing, "
            "upgrade possible, settlement idle. Idle is the cheapest 'needs orders' read."
        ),
        trap="The overlay replaces the 3D map. A click inside the view does not move the camera.",
    ),
    InfoSource(
        id="settlement_economy",
        question="What is this owned settlement's population and income?",
        surface="lists_scroll",
        how="Ctrl+5, Settlements row. Read the detail pane. Close with the dialog X or Escape.",
        reads="Authoritative population and income for towns we own.",
        trap="Hover figures are not population or income. Coin 184 sat next to Lists 3500 / 1710.",
    ),
    InfoSource(
        id="treasury",
        question="How much money do we have this turn?",
        surface="treasury_readout",
        how="Read the top-right HUD. No panel.",
        reads="Current treasury and the signed per-turn change, e.g. 5000 (+442).",
        trap="Finance's 'Boundless' is a band, not a number.",
    ),
    InfoSource(
        id="finance_breakdown",
        question="Where is the money coming from and going?",
        surface="finance_window",
        how="Ctrl+4, Financial Overview. Expand a row's chevron. Do not touch Automanage.",
        reads="Labelled income and expenditure lines.",
        trap="Automanage radios change how the faction is run.",
    ),
    InfoSource(
        id="allies_and_enemies",
        question="Who are we allied with, and who are we at war with?",
        surface="diplomacy_window",
        how="Ctrl+3, Diplomatic Standing, select our crest.",
        reads=(
            "Reputation, treasury band, rows for Allies / Enemies / Trade Partners / "
            "Trade Embargo / Protectorates, plus a territory minimap."
        ),
        trap=(
            "This tab reports standing; it does not negotiate. Talks are "
            "`diplomatic_negotiations`, a decision panel with no close X."
        ),
    ),
    InfoSource(
        id="diplomacy_on_the_map",
        question="How does a foreign settlement stand relative to us, including indirect ties?",
        surface="map_overlay.diplomacy",
        how="Open Map Overlay. Diplomacy is a radio — it replaces Factions, it does not add a layer.",
        reads=(
            "Six standings the hover never says: Player, Ally, Ally of Ally, Neutral, "
            "Enemy, Ally of Enemy."
        ),
        trap="A hover says Ally / At war / Neutral only. SMT_ALLIES reads 'Allies' (legend), not 'Ally'.",
    ),
    InfoSource(
        id="senate_mission",
        question="What has the Senate asked us to do, and how long is left?",
        surface="event_log.missions",
        how=(
            "Left-edge eagle disc, or Faction Summary (Ctrl+1). Same card both places "
            "this turn. Close the dock with its X, not Escape."
        ),
        reads="Objective, target, turns remaining, reward line. Locate magnifier frames the target.",
        trap="This is not the Senate overview (Ctrl+2). The 9+ badge may outnumber the visible cards.",
    ),
    InfoSource(
        id="faction_summary",
        question="Who leads us, what are we trying to win, and what is the headline state?",
        surface="faction_summary",
        how="Bottom-left standard, or Ctrl+1. Close with the red X or Escape.",
        reads=(
            "Leader and three attribute rows, victory conditions, current Senate mission "
            "with locate, faction stats, ranking rows, diplomacy crests."
        ),
        trap="The seven top crests are other tabs.",
    ),
    InfoSource(
        id="senate_offices",
        question="How popular are we with the Senate and the People, and which offices are open?",
        surface="senate_window",
        how="Second crest on the overview strip, or Ctrl+2. Policy / Current Standing.",
        reads="Senate & People popularity and the offices list.",
        trap="The Policy grid is a selector.",
    ),
    InfoSource(
        id="region_owner_without_moving",
        question="Who owns a province we are not looking at?",
        surface="radar",
        how="Hover the radar. Do not click unless the camera should jump.",
        reads="Tooltip names the region and its owning faction. Camera stays put.",
        trap="A radar click is coarse.",
    ),
    InfoSource(
        id="find_capital",
        question="Where is our capital, and how do we recover a lost camera?",
        surface="capital_zoom",
        how="Press Home. One press from anywhere.",
        reads="Frames the capital. Also selects it, so the HUD switches to that governor.",
        trap="Home is recovery, not a free look. It changes selection.",
    ),
    InfoSource(
        id="find_owned_settlement",
        question="How do we frame a town we own that is not the capital?",
        surface="lists_scroll",
        how="Ctrl+5, Settlements, first footer. Close the dialog after.",
        reads="Camera jumps to that settlement.",
        trap="The third footer button sets the faction capital permanently. Do not click it.",
    ),
    InfoSource(
        id="pending_alerts",
        question="What urgent empire problems is the game flagging?",
        surface="event_log.alerts",
        how="Left-edge horn disc. Tooltip: 'Highlights the most important information about running your empire'.",
        reads="Alert cards, or 'NO ALERTS' when the list is empty.",
        trap="Clicking the already-selected tab collapses the dock. Do not click Filters.",
    ),
    InfoSource(
        id="pending_news",
        question="What happened to us and to other factions?",
        surface="event_log.news",
        how="Left-edge sealed-scrolls disc. Tooltip: 'Brings information about all factions, including yours'.",
        reads="News cards, or 'NO NEWS'.",
        trap="Same dismiss rules as Alerts. Empty on Julii turn 1.",
    ),
    InfoSource(
        id="pending_reports",
        question="What built, recruited, or arrived in the end-of-turn report?",
        surface="event_log.reports",
        how=(
            "Left-edge coins disc. Tooltip: 'On recruitment and construction, as well "
            "as the End Of Turn Report'."
        ),
        reads="Construction, recruitment, and end-of-turn report cards, or 'NO REPORTS'.",
        trap="Same dismiss rules as Alerts. Empty on Julii turn 1 before anything has built.",
    ),
    InfoSource(
        id="build_options",
        question="What can this settlement build, and what does a building do?",
        surface="construction_window",
        how="Select the town, press 6. Hover an icon.",
        reads="Name, cost, build time, and the effect list from the hover.",
        trap="A left-click queues the spend. Right-click opens details.",
    ),
    InfoSource(
        id="recruit_options",
        question="What can this settlement recruit?",
        surface="training_window",
        how="Select the town, press 5. Hover a card.",
        reads="Name, size, produce cost, down-arrow upkeep, time, and the recruit/retrain grids.",
        trap="A left-click queues the unit and spends money.",
    ),
    InfoSource(
        id="building_unlock_line",
        question="What unlocks a building, unit, or agent in this town?",
        surface="building_browser",
        how="Tree disc (0.934, 0.968) or right-click Construction.",
        reads=(
            "Tier columns with population thresholds, colour vs grey, and who "
            "each building trains. Diplomat is the Villa; Spy is the Market; "
            "Assassin is the Forum."
        ),
        trap="Green and red tree lines are not accept/reject.",
    ),
    InfoSource(
        id="agent_identity",
        question="Who is this spy or diplomat, and what can they do this turn?",
        surface="agent_selection_hud",
        how="Click the character, or Lists → Agents → locate. Do not click Disband.",
        reads=(
            "Left card: name, type, location, age, Influence or Subterfuge. Green "
            "range on the map. Right list titles SEND EMISSARY or SEND SPY with "
            "success % and turns-to-arrive."
        ),
        trap=(
            "The centre strip is agents at this place, not this character's followers. "
            "Followers are on the character scroll. The corner hourglass is End Turn, "
            "not Confirm."
        ),
    ),
    InfoSource(
        id="agent_traits",
        question="What traits and followers does this character have?",
        surface="character_scroll",
        how="Click the traits HUD button. Close with that parchment's X at (0.740, 0.275).",
        reads="Type title, STATS / TRAITS & FOLLOWERS tabs, trait text and follower slots.",
        trap="Alt+click opens the Steam wiki.",
    ),
    InfoSource(
        id="agent_roster",
        question="Which agents do we have, and where are they?",
        surface="lists_scroll",
        how="Ctrl+5, Agents sub-tab. Locate closes Lists and selects the agent. Or Ctrl+7.",
        reads="Type, name, location, skill. Agent Hub repeats the roster next to Send Agent to.",
        trap=(
            "A SEND-list row only stages the path. Assign commits. After that, "
            "Lists shows Cancel Mission — that undoes the send. Do not click it "
            "while reading."
        ),
    ),
    InfoSource(
        id="agent_target_distance",
        question="How far is a send target, and which one is nearest?",
        surface="agent_selection_hud",
        how=(
            "Select the agent. Read the turn glyph on each SEND EMISSARY / SEND SPY "
            "row. Do not click Assign unless the send is intended."
        ),
        reads=(
            "Turns-to-arrive: `[1]`, `[2]`, … . The smaller glyph is nearer. "
            "Among characters, the first character row with the smallest glyph "
            "is the closest person."
        ),
        trap=(
            "A model standing next to the spy on the 3D map is not the distance "
            "read. Eyeballing picked Eporedorix; Senaculus of Sabis was the first "
            "character row and the shorter glyph. Closest is a fact, not a policy."
        ),
    ),
    InfoSource(
        id="army_roster",
        question="Which armies and fleets do we have?",
        surface="lists_scroll",
        how="Ctrl+5, Military Forces. Hover a row for upkeep. Locate or double-click to frame.",
        reads="Name, unit count, command/management/influence, stack upkeep on hover.",
        trap="The Settlements footer 3 sets the capital. Use Military Forces locate.",
    ),
    InfoSource(
        id="map_order",
        question="How do we send an army or agent to a map target?",
        surface="map_viewport",
        how="Select the character, hover until the cursor glyph changes, then left-click.",
        reads="Sword cursor is an army attack. Town attack is a siege; a field army is Battle Deployment.",
        trap=(
            "2004 cursor strings say Right click. A nameplate click before the "
            "sword selects the town. Do not click a Gallic stack."
        ),
    ),
)

BY_ID: dict[str, InfoSource] = {source.id: source for source in SOURCES}
