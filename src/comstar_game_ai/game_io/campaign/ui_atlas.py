"""The campaign UI atlas: what each panel is, what it is for, how to leave it.

Three sources have to agree before an entry is trustworthy, and each covers a gap
the others cannot:

* **Rome's string tables** name a panel and say what it is for. `strat.txt` carries
  the strat-map tooltips, so the game itself states that the scroll spanning the
  centre is the "Building Browser" and that the coin button opens the "finances
  window". Entries therefore store string *keys*, never English text: the name is
  resolved from the install at read time, which keeps a localised install correct
  and makes it impossible for the atlas to drift from the game.
* **Measured frames** supply geometry. No string table knows where a panel lands or
  where its close button sits, and those are the numbers an actuator needs.
* **Observed behaviour** supplies dismissal. Whether Escape works is a property of
  the running game that neither of the other two sources records; it was learned by
  watching the building browser ignore forty-odd Escape presses.

`status` is deliberately part of the schema rather than tracked elsewhere. An entry
the failure corpus has never contained is still a real panel, and saying so in the
atlas is what turns the atlas into the guided-capture worklist: everything
`UNSEEN` is a panel to go and open on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from comstar_game_ai.game_io.campaign.rome_strings import StringTable, lookup


class PanelClass(Enum):
    """Whether the panel needs answering, closing, or neither.

    This is the distinction that cost Phase 2 the most time: treating every panel
    as a modal strands the turn on a card that is asking nothing.
    """

    #: Shows a check/X glyph pair and must be answered before the game continues.
    DECISION = "decision"
    #: Asks nothing, leaves the map playable and End Turn working. Safe to ignore.
    NOTICE = "notice"
    #: Asks nothing but swallows input and hides the HUD. Must be closed.
    OBSTRUCTING = "obstructing"


class Dismiss(Enum):
    """How to leave a panel, in the order the strategy should be attempted."""

    #: The round gold crossed-swords button on the panel's top-right corner.
    CLOSE_X = "close_x"
    #: Escape. Only for panels where it is known to work — see `advisor`.
    ESCAPE = "escape"
    #: One of the decision glyphs. Which one is a policy decision, not a UI fact.
    DECISION_BUTTON = "decision_button"
    #: Nothing to do; the panel does not block and may be left on screen.
    LEAVE_OPEN = "leave_open"


class Status(Enum):
    """How much of this entry is measured rather than inferred."""

    #: Geometry measured from frames and dismissal confirmed against the game.
    VERIFIED = "verified"
    #: Named by the game's strings, but never yet captured. Needs guided capture.
    UNSEEN = "unseen"
    #: Opened, and found not to be an in-game panel at all. `help_window` is the
    #: case: its shortcut hands off to the Steam overlay. Such an entry has been
    #: investigated, so it is not capture work, but it has no geometry to measure
    #: and no close button to find, so it is not a verified panel either. Recorded
    #: rather than deleted so the hazard is not rediscovered the hard way.
    EXTERNAL = "external"


@dataclass(frozen=True)
class PanelGeometry:
    """Normalised against the CLIENT rect, measured on a 16:9 client area.

    Anchors to look near, not constants to click blindly.
    """

    left: float
    right: float
    top: float
    close_x: tuple[float, float] | None = None

    def spans_centre(self) -> bool:
        return self.left < 0.5 < self.right


@dataclass(frozen=True)
class PanelEntry:
    """One campaign panel, joined across the three sources."""

    id: str
    #: Key naming the panel, or the key of the tooltip on the button that opens it.
    #: Empty for UI that Remastered added and the shipped tables never named — a real
    #: category, and better represented as absent than as an invented key.
    name_key: str
    panel_class: PanelClass
    dismiss: tuple[Dismiss, ...]
    status: Status
    #: How the panel comes up. Prose, because the game does not encode it.
    opened_by: str = ""
    #: The `descr_shortcuts.txt` action that opens it, when a key does.
    shortcut_action: str = ""
    #: Set when this panel is a tab of a shared window rather than a window of its
    #: own. Seven entries here are tabs of one frame, which is why they all measure
    #: to identical geometry; treating them as separate windows means seven copies
    #: of one close button and a detector that cannot tell which tab is showing.
    tab_of: str = ""
    #: What must already be true for the shortcut to do anything. Empty means the
    #: shortcut works from a bare campaign map.
    requires: str = ""
    #: Why this panel must not be opened by an unattended agent.
    hazard: str = ""
    geometry: PanelGeometry | None = None
    #: Frames or log lines backing the measured parts of this entry.
    evidence: tuple[str, ...] = ()
    #: Set when the panel's own name is unhelpful without context.
    note: str = ""

    def name(self, tables: dict[str, StringTable]) -> str | None:
        """The game's own words for this panel, or None when it has none."""
        if not self.name_key:
            return None
        found = lookup(tables, self.name_key)
        return None if found is None else found[1]

    @property
    def blocking(self) -> bool:
        """True when the turn cannot continue while this panel is up.

        Decision panels block for a different reason than obstructing ones — they
        are waiting for an answer rather than swallowing input — but both stop the
        turn, and callers deciding whether to act care only that they must.
        """
        return self.panel_class in (PanelClass.OBSTRUCTING, PanelClass.DECISION)

    @property
    def expects_close_x(self) -> bool:
        """Whether this panel should have a close button at all.

        Tied to how the panel is dismissed rather than to its class. Decision panels
        have none — the check/X/counter trio at the bottom centre replaces the corner
        button — which is why a close-X search returning nothing is a classification
        signal rather than a detector failure: the nine diplomacy frames in the corpus
        went unidentified having been searched for a button the panel never had.

        But class alone is too blunt. `campaign_map_overlays` is a notice with no close
        button either, because it is left by pressing Tab again rather than dismissed,
        and demanding a close X of it would mean inventing coordinates for a control
        that does not exist.
        """
        return Dismiss.CLOSE_X in self.dismiss


#: The one frame behind all seven Ctrl+N tabs, measured during the guided sweep.
#:
#: Every one of the seven measured to these numbers to the pixel, which is the
#: evidence that they are tabs and not windows. The game says so too: a loading-screen
#: tip describes Move Followers as "the Move Followers tab of the Faction Summary
#: panel". The tab strip is the row of seven round crests along the top edge.
OVERVIEW_FRAME = PanelGeometry(left=0.257, right=0.743, top=0.123, close_x=(0.740, 0.139))

#: Where the tab strip's crests sit, left to right, as Ctrl+1 through Ctrl+7.
OVERVIEW_TAB_CENTRES: tuple[tuple[float, float], ...] = (
    (0.303, 0.172), (0.368, 0.172), (0.434, 0.172), (0.499, 0.172),
    (0.564, 0.172), (0.630, 0.172), (0.695, 0.172),
)

#: The panels reachable from the campaign map.
#:
#: Every `name_key` resolves in a stock install — `test_ui_atlas` asserts it, which
#: is what stops a plausible-looking but invented key from shipping.
ATLAS: tuple[PanelEntry, ...] = (
    PanelEntry(
        id="building_browser",
        name_key="SMT_BUILDING_BROWSER",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="settlement scroll, or a stray click in the lower-right HUD",
        geometry=PanelGeometry(left=0.26, right=0.74, top=0.21, close_x=(0.752, 0.196)),
        evidence=(
            "125 corpus frames; spans the centre and covers the End Turn control",
            "ignored 40+ Escape presses, so CLOSE_X is the only dismissal",
            "log line: 'Uknown settlement levelbuilding_browser_scroll scroll opened'",
        ),
        note=(
            "Its construction tree is full of green and red connector lines that mimic "
            "decision glyphs, so decision detection must not run inside it."
        ),
    ),
    PanelEntry(
        id="senate_mission_card",
        name_key="SMT_OPEN_SENATE_WINDOW",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN, Dismiss.CLOSE_X),
        status=Status.VERIFIED,
        opened_by="pushed by the Senate at the start of a Roman turn",
        geometry=PanelGeometry(left=0.00, right=0.16, top=0.07, close_x=(0.160, 0.077)),
        evidence=(
            "73 corpus frames over a dim night map",
            "no glyph pair, map stayed playable and the turn proceeded",
        ),
        note=(
            "Not the Senate window. This is the card the Senate pushes into the left "
            "dock when it assigns a mission; the window it refers to is `senate_window` "
            "and opens on Ctrl+2. Conflating them makes a harmless notice look like a "
            "panel that needs closing."
        ),
    ),
    PanelEntry(
        id="senate_window",
        name_key="SMT_OPEN_SENATE_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="laurel-wreath button at the bottom-left of the HUD, or Ctrl+2",
        shortcut_action="senate_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/senate_window.png",
            "titles itself 'The Senate'; tab 2 of the overview frame",
        ),
        note=(
            "Roman factions only. Two sub-tabs, Policy and Current Standing. Policy "
            "shows a grid of faction crests; selecting one shows the Senate's opinion "
            "of that faction, so the grid is a selector and not a set of buttons."
        ),
    ),
    PanelEntry(
        id="left_dock_notice",
        name_key="ST_ADVISOR_BUTTON_ZOOM_TO",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN, Dismiss.CLOSE_X),
        status=Status.VERIFIED,
        opened_by="event and alert cards stack against the left edge each turn",
        geometry=PanelGeometry(left=0.03, right=0.33, top=0.07, close_x=(0.327, 0.077)),
        evidence=(
            "12 corpus frames over a lit map",
            "a vertical strip of gold category icons sits to their right and is not the close X",
        ),
        note="Cards carry their event's own title from event_titles, not a fixed name.",
    ),
    PanelEntry(
        id="diplomatic_negotiations",
        name_key="diplomacy_mission",
        panel_class=PanelClass.DECISION,
        dismiss=(Dismiss.DECISION_BUTTON,),
        status=Status.VERIFIED,
        opened_by="right-click a diplomat onto a target, or an AI faction opens talks",
        geometry=PanelGeometry(left=0.20, right=0.76, top=0.13, close_x=None),
        evidence=(
            "9 corpus frames, right edge measured 0.75-0.79 across them",
            "titled 'Diplomatic Negotiations', Julii vs Gaul, 'Their offers: Trade rights'",
            "three footer buttons at bottom centre: accept, reject, counter-offer",
            "frames: modal-unresolved-modal-07e22ed4f3-raw.png and 8 siblings",
        ),
        note=(
            "Three scrolls in one: faction heir on the left, the negotiation in the "
            "centre, the diplomat on the right, which is why the measured span is "
            "wider than the centre scroll. Offers are read from SMT_THEIR_OFFERS and "
            "SMT_YOUR_OFFERS. localize_diplomacy_footer_buttons already targets it."
        ),
    ),
    PanelEntry(
        id="battle_deployment",
        name_key="SMT_BATTLE_DEPLOYMENT",
        panel_class=PanelClass.DECISION,
        dismiss=(Dismiss.DECISION_BUTTON,),
        status=Status.VERIFIED,
        opened_by="attacking or being attacked on the campaign map",
        geometry=PanelGeometry(left=0.16, right=0.83, top=0.35, close_x=None),
        evidence=(
            "1 corpus frame, from the battle entered at the end of the 25-turn run",
            "Julii 200 soldiers vs Gaul 1148, footer offers auto-resolve, withdraw, fight",
            "a 'Fight night battle' checkbox sits below the footer buttons",
            "frame: modal-unresolved-modal-1be29c6f10-raw.png",
        ),
        note=(
            "The campaign/battle boundary, so Phase 5 starts here. Answering it wrong "
            "is expensive and irreversible: 'fight' hands control to the battle map "
            "with no campaign loop able to drive it yet."
        ),
    ),
    PanelEntry(
        id="advisor",
        name_key="ST_ADVISOR_BUTTON_DISMISS",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.ESCAPE,),
        status=Status.UNSEEN,
        opened_by="the advisor interrupts on scripted events and new mechanics",
        note=(
            "The one panel where Escape is documented: the game's own button reads "
            "'Dismiss advice [ESC]'. Escape being unreliable elsewhere is not a fact "
            "about Escape, it is a fact about the other panels."
        ),
    ),
    PanelEntry(
        id="construction_window",
        name_key="SMT_OPEN_CONSTRUCTION_WINDOW",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="construction button on the settlement scroll, or 6 with a settlement selected",
        shortcut_action="construction_button",
        requires="a settlement selected on the map",
        geometry=PanelGeometry(left=0.855, right=1.0, top=0.44, close_x=(0.857, 0.452)),
        evidence=(
            "guided sweep: data/runtime/sweep/settlement_panel.png, hover_constr_c1.png",
            "6 pressed on a bare map does nothing; with Arretium selected it opens",
        ),
        note=(
            "Not a window. It docks against the right edge as a grid of building icons "
            "with a Repair grid beneath, and leaves the map playable, so it is a notice "
            "by behaviour despite being a construction control. Hovering an icon yields "
            "the building's name, cost, build time and full effect list, which is how to "
            "read the options without clicking: a click queues the build and spends money."
        ),
    ),
    PanelEntry(
        id="training_window",
        name_key="SMT_OPEN_TRAINING_WINDOW",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="recruitment button on the settlement scroll, or 5 with a settlement selected",
        shortcut_action="recruitment_button",
        requires="a settlement selected on the map",
        geometry=PanelGeometry(left=0.855, right=1.0, top=0.44, close_x=(0.857, 0.452)),
        evidence=(
            "guided sweep: data/runtime/sweep/training_window.png",
            "right-edge dock titled 'Recruitment' with a 'Retrain' grid beneath",
        ),
        note=(
            "The recruitment counterpart of construction_window and the same shape: a "
            "right-edge dock of unit cards. The bottom bar gains a queue readout ('1/20') "
            "while it is open. Unit cards match the extracted install art under "
            "kb/cards/units, so a card can be identified rather than merely located."
        ),
    ),
    PanelEntry(
        id="mercenary_recruitment",
        name_key="SMT_OPEN_MERCENARY_RECRUITMENT",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="mercenary button while an army is selected",
    ),
    PanelEntry(
        id="diplomacy_window",
        name_key="SMT_OPEN_DIPLOMACY_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="diplomacy button on the bottom-left HUD, or Ctrl+3",
        shortcut_action="diplomacy_overview_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/diplomacy_window.png",
            "titles itself 'Factions'; tab 3 of the overview frame",
        ),
        note=(
            "The game titles this tab 'Factions', not diplomacy, and it conducts none: "
            "it reports standing. Sub-tabs are Ranking and Diplomatic Standing, and the "
            "detail pane carries a reputation bar, a territory minimap, and rows for "
            "allies, enemies, trade partners, embargoes and protectorates. Actual "
            "negotiation happens in `diplomatic_negotiations`, a decision panel."
        ),
    ),
    PanelEntry(
        id="finance_window",
        name_key="SMT_OPEN_FINANCE_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="coin button on the bottom-left HUD, or Ctrl+4",
        shortcut_action="finances_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/finance_window.png",
            "titles itself 'Finance & Family'; tab 4 of the overview frame",
        ),
        note=(
            "Sub-tabs are Financial Overview and Family Tree. Income and expenditure "
            "rows carry a chevron that expands a breakdown. The footer holds an "
            "Automanage checkbox, Automanage Tax / Everything radios and an AI Spend "
            "Policy slider — all of which change how the faction is run, so they are "
            "read-only as far as an unattended agent is concerned."
        ),
    ),
    PanelEntry(
        id="faction_summary",
        name_key="SMT_FACTION_BUTTON_TOOLTIP",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="faction button on the bottom-left HUD, or Ctrl+1; right-click instead locates the capital",
        shortcut_action="faction_overview_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/faction_summary.png",
            "titles itself 'Faction Summary'; tab 1 of the overview frame",
        ),
        note=(
            "The tab the whole frame is named after. Carries the faction leader with his "
            "three attribute rows, the victory conditions, the current Senate mission with "
            "a locate button, faction stats, six ranking rows, and diplomatic standing. "
            "The densest single source of faction state available without acting."
        ),
    ),
    PanelEntry(
        id="lists_scroll",
        name_key="SMT_SHOW_FACTION_LISTS",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="lists button on the bottom-left HUD, or Ctrl+5",
        shortcut_action="lists_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/lists_scroll.png",
            "titles itself 'Lists'; tab 5 of the overview frame",
            "button tooltips captured in hover_lists_btn1..3.png",
        ),
        note=(
            "Sub-tabs are Settlements, Military Forces and Agents, over a sortable list "
            "with a filter dropdown. The settlement detail pane holds the per-settlement "
            "controls: Automanage / Construction / Recruitment checkboxes and a tax-rate "
            "stepper. Of its three footer buttons the game names the first two 'Locate "
            "position of settlement' and 'Explore settlement on Battle Map', but the third "
            "is 'Make this settlement the faction capital' — a permanent change sitting "
            "one icon away from two harmless ones."
        ),
    ),
    PanelEntry(
        id="options_window",
        name_key="SMT_OPEN_OPTIONS_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.UNSEEN,
        opened_by="options button on the bottom-left HUD",
        note="Hazardous to explore: it can change resolution and input settings.",
    ),
    PanelEntry(
        id="help_window",
        name_key="show_help",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.ESCAPE,),
        status=Status.EXTERNAL,
        opened_by="F1",
        shortcut_action="show_help",
        hazard=(
            "F1 does not open an in-game panel. It asks Steam to open the wiki in the "
            "overlay browser, which covers the entire screen, is outside the game's UI "
            "so no panel detector can see it, and clears only on Shift+Tab. On this "
            "install the browser then fails with 'BrowserView.Create initial URL not "
            "valid', so the payoff is nil and the cost is a blind agent."
        ),
        evidence=("guided sweep: data/runtime/sweep/fixed_f1.png shows the Steam overlay",),
        note="Left in the atlas precisely so the hazard is recorded rather than rediscovered.",
    ),
    PanelEntry(
        id="retinue_panel",
        name_key="SMT_ANCILLARIES",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="retinue button on the bottom-left HUD, or Ctrl+6",
        shortcut_action="retinue_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/retinue_panel.png",
            "titles itself 'Move Followers'; tab 6 of the overview frame",
            "a loading-screen tip calls it a tab of the Faction Summary panel",
        ),
        note=(
            "Rome calls retinue members ancillaries and this tab calls them followers. "
            "Two filtered lists — faction characters and their followers — over a detail "
            "pane showing the selected character's traits. Character-scoped, not faction-"
            "scoped, and the only tab whose purpose is to move something rather than read it."
        ),
    ),
    PanelEntry(
        id="agent_hub",
        name_key="",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by="agent hub button on the bottom-left HUD, or Ctrl+7",
        shortcut_action="agent_hub_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/agent_hub.png",
            "titles itself 'Agent Hub'; tab 7 of the overview frame",
        ),
        note=(
            "Bound to Ctrl+7 in both keysets but named by no shipped string: a Remastered "
            "addition the original text tables predate, and capture is the only way to "
            "name it. Three filter dropdowns over an agent list, with a 'Send Agent to' "
            "list of missions carrying success percentages. The one tab with a commit "
            "button — a gold Confirm at the footer that dispatches the agent for real."
        ),
    ),
    PanelEntry(
        id="campaign_map_overlays",
        name_key="toggle_overlays",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN,),
        status=Status.VERIFIED,
        opened_by="Tab in the moderntw keyset, Ctrl+Tab in default",
        shortcut_action="campaign_map_overlays_button",
        geometry=PanelGeometry(left=0.0, right=0.123, top=0.368, close_x=None),
        evidence=(
            "guided sweep: data/runtime/sweep/recover_1.png",
            "measured geometry is the left legend, the only panel-like region it adds",
        ),
        note=(
            "Replaces the map with a framed strategic view rather than opening a scroll, "
            "so nothing needs dismissing — Tab again leaves it. Two legends dock at the "
            "edges and both are checkbox filters, not keys: settlement tiers, alerts, and "
            "the states 'Recruiting or constructing', 'Upgrade possible' and 'Settlement "
            "idle' on the left; per-faction colours on the right. Those three states are "
            "the cheapest read available of which settlements still need orders. It "
            "recolours everything the perception layer sees, so any pixel heuristic "
            "calibrated on the normal map is invalid while it is up."
        ),
    ),
)

BY_ID: dict[str, PanelEntry] = {entry.id: entry for entry in ATLAS}


def unseen() -> tuple[PanelEntry, ...]:
    """Panels the game names but the corpus has never shown.

    This is the guided-capture worklist.
    """
    return tuple(e for e in ATLAS if e.status is Status.UNSEEN)


def verified() -> tuple[PanelEntry, ...]:
    return tuple(e for e in ATLAS if e.status is Status.VERIFIED)


@dataclass(frozen=True)
class PanelMatch:
    """An observed panel matched against the atlas."""

    entry: PanelEntry
    #: Normalised geometric distance; 0.0 is an exact match on all three edges.
    distance: float


def match_geometry(
    left: float,
    right: float,
    top: float,
    *,
    tolerance: float = 0.06,
) -> PanelMatch | None:
    """Match measured panel edges to an atlas entry.

    Returns None rather than a poor guess: an unmatched panel is a finding worth
    recording, and inventing an identity for it would hide exactly the panels the
    guided-capture pass needs to find.
    """
    best: PanelMatch | None = None
    for entry in ATLAS:
        geometry = entry.geometry
        if geometry is None:
            continue
        distance = max(
            abs(geometry.left - left),
            abs(geometry.right - right),
            abs(geometry.top - top),
        )
        if distance > tolerance:
            continue
        if best is None or distance < best.distance:
            best = PanelMatch(entry=entry, distance=distance)
    return best
