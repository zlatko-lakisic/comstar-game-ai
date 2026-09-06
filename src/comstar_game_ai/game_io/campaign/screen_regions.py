"""Where the parts of the campaign screen are.

The atlas in `ui_atlas` says what each *panel* is. This says where the persistent
furniture lives: the map viewport, the radar and its zoom controls, the readouts,
the HUD tabs, the event dock. A reasoning model that knows Z zooms in still cannot
click the radar unless something tells it where the radar is.

Every bound is normalised against the CLIENT rect on a 16:9 client area.

**Read the `precision` field before clicking.** `end_turn_button`,
`map_overlay_button` and `faction_standard_button` have been verified by a
working actuation. The rest were read off a 0.01 coordinate grid laid
over a single 1920x1080 frame, so they carry roughly +/-0.005 and, more importantly,
have never been proven by a click that did the intended thing. They are good enough
to *look near* and to reason with, and not good enough to trust blind — which is the
same rule the End Turn work arrived at the hard way after a cascade of five guessed
positions opened the building browser and wedged a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Precision(Enum):
    #: Confirmed by an actuation that produced the intended effect.
    VERIFIED = "verified"
    #: Read off a coordinate grid on a real frame. Never clicked.
    MEASURED = "measured"


class RegionKind(Enum):
    #: The world. Clicks here move units and change game state.
    VIEWPORT = "viewport"
    #: A clickable control.
    BUTTON = "button"
    #: Displays information; clicking is pointless or harmful.
    READOUT = "readout"
    #: A container holding other things.
    CHROME = "chrome"


@dataclass(frozen=True)
class Region:
    id: str
    kind: RegionKind
    #: (x0, y0, x1, y1) normalised against the client rect.
    bounds: tuple[float, float, float, float]
    purpose: str
    precision: Precision = Precision.MEASURED
    #: The `descr_shortcuts.txt` action this control corresponds to, when there is one.
    action: str = ""
    note: str = ""

    @property
    def centre(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.bounds
        return (round((x0 + x1) / 2, 4), round((y0 + y1) / 2, 4))

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.bounds
        return x0 <= x <= x1 and y0 <= y <= y1


REGIONS: tuple[Region, ...] = (
    Region(
        id="map_viewport",
        kind=RegionKind.VIEWPORT,
        bounds=(0.0, 0.055, 1.0, 0.94),
        purpose=(
            "The campaign world. Select a character, then left-click a target "
            "once the cursor glyph changes (sword for an army attack)."
        ),
        note=(
            "This is the base layer, not an exclusive area: the radar and other HUD "
            "furniture are drawn on top of it and swallow clicks that land on them. "
            "Resolve a point with region_at rather than testing this rectangle, which "
            "answers 'is the map under here', not 'will a click reach the map'. A click "
            "meant for the HUD that does reach the map mutates game state instead of "
            "doing nothing."
        ),
    ),
    Region(
        id="radar",
        kind=RegionKind.BUTTON,
        bounds=(0.879, 0.055, 0.998, 0.185),
        purpose=(
            "Strategic minimap of the whole world. Clicking a point jumps the camera "
            "there, which is the cheap way to traverse the map."
        ),
        note=(
            "A red trapezoid drawn on it is the live camera frustum, so the radar "
            "reports where the camera is looking as well as accepting where to go. "
            "Panning with WASD covers a fraction of this per press; a radar click "
            "crosses the map in one action. Toggle with toggle_radar; "
            "toggle_hires_radar gives a fullscreen version. "
            "It also carries the faction-coloured ownership of everything explored, in "
            "the same palette the overlay legend states, so our own territory can be "
            "found on it without opening anything — and hovering it returns a tooltip "
            "naming the region and its owning faction, which makes it a zero-risk survey "
            "instrument as well as a control. Read positions off it by sampling, not by "
            "eye: it is about 228 px wide for the whole Mediterranean, so an eyeballed "
            "click can miss a province by a long march."
        ),
    ),
    Region(
        id="radar_zoom_in",
        kind=RegionKind.BUTTON,
        bounds=(0.865, 0.062, 0.878, 0.085),
        purpose="Zoom the campaign camera in. Mouse equivalent of the zoom_in key.",
        action="zoom_in",
    ),
    Region(
        id="radar_zoom_out",
        kind=RegionKind.BUTTON,
        bounds=(0.865, 0.090, 0.878, 0.111),
        purpose="Zoom the campaign camera out. Mouse equivalent of the zoom_out key.",
        action="zoom_out",
    ),
    Region(
        id="radar_compass",
        kind=RegionKind.BUTTON,
        bounds=(0.865, 0.152, 0.879, 0.175),
        purpose="Reset camera bearing to north. Mouse equivalent of point_to_north.",
        action="point_to_north",
        note="Worth pressing before any bearing-dependent reasoning: after a rotation "
        "the map's compass directions no longer match the screen axes.",
    ),
    Region(
        id="treasury_readout",
        kind=RegionKind.READOUT,
        bounds=(0.868, 0.005, 0.945, 0.030),
        purpose="Current treasury and net income per turn, e.g. '8830 (+469)'.",
        note="Income sign is the fastest available read on whether the economy is failing.",
    ),
    Region(
        id="date_readout",
        kind=RegionKind.READOUT,
        bounds=(0.868, 0.030, 0.925, 0.055),
        purpose="Season and year, e.g. a snowflake and '267 BC'.",
        note=(
            "Two turns per year, summer then winter. Useful as a sanity check on turn "
            "counting but NOT as the turn clock: the autosaves are the clock."
        ),
    ),
    Region(
        id="map_overlay_button",
        kind=RegionKind.BUTTON,
        bounds=(0.968, 0.005, 1.0, 0.055),
        purpose="Toggles the campaign map overlay. The eye-and-scroll disc at the top-right.",
        precision=Precision.VERIFIED,
        action="campaign_map_overlays_button",
        note=(
            "Tooltip reads 'Map Overlay <Tab>'. This is not the advisor — that was a "
            "misread of the same disc. Escape or a second click leaves the overlay; "
            "there is no dialog X because the overlay is not a dialog."
        ),
    ),
    Region(
        id="faction_leader_button",
        kind=RegionKind.BUTTON,
        bounds=(0.0, 0.0, 0.033, 0.055),
        purpose="Faction leader portrait; opens the faction summary window.",
        action="faction_overview_button",
    ),
    Region(
        id="ledger_button",
        kind=RegionKind.BUTTON,
        bounds=(0.037, 0.010, 0.055, 0.036),
        purpose="Book disc in the top-left cluster; opens the faction lists/ledger scroll.",
        action="lists_button",
    ),
    Region(
        id="help_button",
        kind=RegionKind.BUTTON,
        bounds=(0.060, 0.010, 0.078, 0.036),
        purpose="Question-mark disc; opens the help window.",
        action="show_help",
    ),
    Region(
        id="menu_button",
        kind=RegionKind.BUTTON,
        bounds=(0.083, 0.010, 0.101, 0.036),
        purpose="Three-bars disc; opens the game options menu.",
        action="",
        note="Hazardous: the options window can change resolution and input settings.",
    ),
    Region(
        id="event_dock_icons",
        kind=RegionKind.CHROME,
        bounds=(0.0, 0.10, 0.028, 0.36),
        purpose=(
            "Collapsed Event Log: four category discs (Alerts, News, Reports, Missions) "
            "down the left edge. Click or hover pops the parchment out; the discs ride "
            "to the panel's right edge and become tabs."
        ),
        precision=Precision.VERIFIED,
        action="toggle_news_panel",
        note=(
            "Centres in campaign/left_dock.py. When the dock is open the same discs "
            "sit near x 0.17, so this collapsed strip is empty. The discs are gold "
            "and round, which is exactly what a panel close X looks like — the "
            "close-X search must not be run over this strip. A 9+ badge was on "
            "Missions this turn. Clicking the already-selected tab collapses the dock."
        ),
    ),
    Region(
        id="faction_standard_button",
        kind=RegionKind.BUTTON,
        bounds=(0.0, 0.925, 0.055, 0.998),
        purpose=(
            "Faction standard at the bottom-left. Opens Faction Summary; right-click "
            "locates the capital."
        ),
        precision=Precision.VERIFIED,
        action="faction_overview_button",
        note=(
            "Tooltip: 'Faction Summary. [Right Click Icon] to locate faction capital.' "
            "Previously recorded as the Senate disc — Senate is the second tab of the "
            "window this opens, not a separate HUD button on this layout."
        ),
    ),
    Region(
        id="hud_tab_buildings",
        kind=RegionKind.BUTTON,
        bounds=(0.425, 0.945, 0.448, 0.99),
        purpose="Temple disc; shows the buildings tab for the selection.",
        action="buildings_button",
    ),
    Region(
        id="hud_tab_army",
        kind=RegionKind.BUTTON,
        bounds=(0.468, 0.945, 0.492, 0.99),
        purpose="Soldier disc; shows the units tab for the selection.",
        action="army_button",
    ),
    Region(
        id="hud_tab_agents",
        kind=RegionKind.BUTTON,
        bounds=(0.512, 0.945, 0.536, 0.99),
        purpose=(
            "Hooded-figure disc; shows the agents tab. Lights when a spy or "
            "diplomat is selected."
        ),
        action="agents_button",
    ),
    Region(
        id="hud_tab_fleets",
        kind=RegionKind.BUTTON,
        bounds=(0.556, 0.945, 0.580, 0.99),
        purpose="Ship disc; shows the fleets/passengers tab.",
        action="fleets_button",
    ),
    Region(
        id="end_turn_button",
        kind=RegionKind.BUTTON,
        bounds=(0.963, 0.945, 0.997, 0.998),
        purpose="Ends the turn. The round disc at the far bottom-right.",
        precision=Precision.VERIFIED,
        action="end_turn",
        note=(
            "Icon is state dependent — a red horn and a cream hourglass have both been "
            "seen at this centre. Identify by position and round shape, never colour. "
            "Shift+Enter does the same thing without a click and is bound in both "
            "keysets, which is why it is the primary actuation."
        ),
    ),
    Region(
        id="bottom_hud_bar",
        kind=RegionKind.CHROME,
        bounds=(0.0, 0.94, 1.0, 1.0),
        purpose="The bottom HUD band holding the tabs, selection cards and End Turn.",
        note="Not a continuous strip: it has gaps that show map through them.",
    ),
    Region(
        id="settlement_recruit_button",
        kind=RegionKind.BUTTON,
        bounds=(0.866, 0.948, 0.890, 0.988),
        purpose="Banner-plus disc. Tooltip: 'Recruitment <5>'. Opens the training dock.",
        action="recruitment_button",
        note="Needs a settlement selected. A card click inside the dock queues and spends.",
    ),
    Region(
        id="settlement_construct_button",
        kind=RegionKind.BUTTON,
        bounds=(0.890, 0.948, 0.914, 0.988),
        purpose="Building-plus disc. Tooltip: 'Construction <6>'. Opens the construction dock.",
        action="construction_button",
        note="Right-click opens the Building Browser. A card click inside the dock queues and spends.",
    ),
    Region(
        id="building_browser_button",
        kind=RegionKind.BUTTON,
        bounds=(0.922, 0.948, 0.946, 0.988),
        purpose="Tree disc. Tooltip: 'Building Browser'. Opens the unlock-line parchment.",
        precision=Precision.VERIFIED,
        note=(
            "Clicked on Julii turn 1: town_browser.png panel=(492, 1427, 223). "
            "No key binding. Close with the parchment X, not Escape."
        ),
    ),
    Region(
        id="agent_traits_button",
        kind=RegionKind.BUTTON,
        bounds=(0.078, 0.948, 0.102, 0.975),
        purpose=(
            "Left-HUD button on a selected character. Tooltip: 'Character's traits "
            "and Followers'. Opens the character scroll."
        ),
        precision=Precision.VERIFIED,
        note="Alt+click opens the Steam wiki. See campaign/agents.py.",
    ),
    Region(
        id="agent_disband_button",
        kind=RegionKind.BUTTON,
        bounds=(0.702, 0.925, 0.728, 0.955),
        purpose="Boot on the selected-agent centre strip. Disbands the character.",
        action="disband",
        note="Never clicked. Delete is bound to the same action. Do not press either.",
    ),
    Region(
        id="agent_send_list",
        kind=RegionKind.CHROME,
        bounds=(0.84, 0.74, 0.97, 0.92),
        purpose=(
            "Right-hand send list on a selected agent: SEND EMISSARY or SEND SPY. "
            "A row click stages the path; Assign commits."
        ),
        note="Confirm is on the footer, left of End Turn. The corner hourglass is End Turn.",
    ),
)

BY_ID: dict[str, Region] = {r.id: r for r in REGIONS}


def region_at(x: float, y: float) -> Region | None:
    """The most specific region containing a point, or None.

    Smallest-area wins so that a button inside the HUD bar beats the bar itself.
    """
    hits = [r for r in REGIONS if r.contains(x, y)]
    if not hits:
        return None

    def area(region: Region) -> float:
        x0, y0, x1, y1 = region.bounds
        return (x1 - x0) * (y1 - y0)

    return min(hits, key=area)


def buttons() -> tuple[Region, ...]:
    return tuple(r for r in REGIONS if r.kind is RegionKind.BUTTON)


def unverified() -> tuple[Region, ...]:
    """Regions never confirmed by a click. Everything except End Turn, so far."""
    return tuple(r for r in REGIONS if r.precision is not Precision.VERIFIED)
