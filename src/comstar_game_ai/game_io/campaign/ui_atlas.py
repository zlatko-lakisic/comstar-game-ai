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
        opened_by=(
            "tree disc at (0.934, 0.968) with a settlement selected, or right-click "
            "the Construction <6> disc. No key binding."
        ),
        geometry=PanelGeometry(left=0.26, right=0.74, top=0.21, close_x=(0.752, 0.196)),
        evidence=(
            "125 corpus frames; spans the centre and covers the End Turn control",
            "ignored 40+ Escape presses, so CLOSE_X is the only dismissal",
            "log line: 'Uknown settlement levelbuilding_browser_scroll scroll opened'",
            "live Julii turn 1: data/runtime/sweep/town_browser.png "
            "panel=(492, 1427, 223) after clicking the tree disc",
        ),
        note=(
            "The unlock line. Columns are settlement tiers with population "
            "thresholds; colour is built, grey is not. Green connectors are open "
            "paths. A red chain is a missing gate, not accept/reject — decision "
            "detection must not run inside it. Hover an icon for cost, time, and "
            "who it trains. Right-click opens the Building Information Scroll. "
            "Close with this parchment's X, not Escape."
        ),
    ),
    PanelEntry(
        id="event_log",
        name_key="SMT_EVENT_LOG",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN, Dismiss.CLOSE_X),
        status=Status.VERIFIED,
        opened_by=(
            "four category discs on the left edge (Alerts, News, Reports, Missions); "
            "hover or click pops the parchment to the right"
        ),
        shortcut_action="toggle_news_panel",
        geometry=PanelGeometry(left=0.00, right=0.163, top=0.066, close_x=(0.160, 0.077)),
        evidence=(
            "live Julii turn 1: data/runtime/sweep/dock_switch_opened.png, "
            "dock_tab_hover_1..4.png, dock_switch_2..4.png, dock_chrome2_filter.png",
            "close X at (0.160, 0.077) collapsed it: dock_switch_after_close_x.png",
            "clicking the already-selected Alerts tab also collapsed it",
        ),
        note=(
            "The container behind Alerts / News / Reports / Missions. String tables "
            "name it Event Log; the tab tooltips use those four English words. "
            "`toggle_news_panel` exists in descr_shortcuts.txt but is unbound in "
            "moderntw, so the discs are the opener. Clicking the selected tab "
            "toggles the dock shut — do not click Alerts again to 'make sure' it "
            "is open. Escape was not used: Escape on a closed dock is the pause "
            "menu. See campaign/left_dock.py for the four centres. Filters "
            "(funnel, tooltip 'Select which type of messages you receive') changes "
            "incoming messages — do not click it."
        ),
    ),
    PanelEntry(
        id="senate_mission_card",
        name_key="SMT_OPEN_SENATE_WINDOW",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN, Dismiss.CLOSE_X),
        status=Status.VERIFIED,
        opened_by="Missions tab of the Event Log, or pushed by the Senate at turn start",
        tab_of="event_log",
        geometry=PanelGeometry(left=0.00, right=0.16, top=0.07, close_x=(0.160, 0.077)),
        evidence=(
            "73 corpus frames over a dim night map",
            "live Missions tab: data/runtime/sweep/dock_switch_4.png — Take Segesta, 10 turns",
            "no glyph pair, map stayed playable and the turn proceeded",
        ),
        note=(
            "Not the Senate window (that is `senate_window`, Ctrl+2). This is the "
            "Missions tab of the Event Log: same parchment frame, different body. "
            "Conflating it with the Senate overview makes a harmless notice look "
            "like a panel that needs closing."
        ),
    ),
    PanelEntry(
        id="senate_window",
        name_key="SMT_OPEN_SENATE_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by="second crest on the overview tab strip, or Ctrl+2",
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
        opened_by=(
            "left-click a diplomat onto a target once the cursor glyph changes "
            "(2004 strings still say right-click), or an AI faction opens talks"
        ),
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
        opened_by=(
            "construction disc on the settlement footer, or 6 with a settlement selected"
        ),
        shortcut_action="construction_button",
        requires="a settlement selected on the map",
        geometry=PanelGeometry(left=0.855, right=1.0, top=0.44, close_x=(0.857, 0.452)),
        evidence=(
            "guided sweep: data/runtime/sweep/settlement_panel.png, hover_constr_c1.png",
            "6 pressed on a bare map does nothing; with Arretium selected it opens",
            "live footer tooltip: data/runtime/sweep/tt_f902.png 'Construction <6>'",
        ),
        note=(
            "Not a window. It docks against the right edge as a grid of building icons "
            "with a Repair grid beneath, and leaves the map playable, so it is a notice "
            "by behaviour despite being a construction control. Hovering an icon yields "
            "the building's name, cost, build time and effect list "
            "(TMT_CONSTRUCTION_HELP: left-click queues, right-click for information). "
            "A left-click queues the build and spends money. The icon grid reflows "
            "after a queue — do not reuse old card coordinates. Buildings have no "
            "upkeep; income changes when they complete. Live hovers this turn were "
            "10% under EDB (Practice Range 1080 vs 1200). Right-click opens "
            "building details. The Construction disc tooltip also offers "
            "right-click to open the Building Browser. The same disc opens FIELD "
            "CONSTRUCTION when a named general is selected on own land."
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
            "right-edge dock of unit cards over a Retrain grid. Hover reads name, "
            "size, cost, time, and a down-arrow upkeep. A left-click queues and "
            "spends; right-click opens unit details; Alt+right-click is the wiki. "
            "Arretium this turn offered Peasants (100/100), Town Watch (150/100), "
            "Hastati (440/170), a port warship, and Diplomat — no spy. Upkeep "
            "hits when the unit exists, not when it is queued."
        ),
    ),
    PanelEntry(
        id="mercenary_recruitment",
        name_key="SMT_OPEN_MERCENARY_RECRUITMENT",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="mercenary button while an army is selected",
        note=(
            "The Mercenaries grid also sits under FIELD CONSTRUCTION when a named "
            "general is selected on the map. It was empty in Etruria this turn, so "
            "this parchment as its own window is still unseen."
        ),
    ),
    PanelEntry(
        id="field_construction",
        name_key="SMT_SELECT_FORT_OR_WATCHTOWER",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.VERIFIED,
        opened_by=(
            "Construction <6> disc with a named general selected on own land, "
            "not inside a town"
        ),
        shortcut_action="construction_button",
        requires="a named general on own land, not in a town or at sea",
        geometry=PanelGeometry(left=0.82, right=1.0, top=0.40, close_x=(0.830, 0.419)),
        evidence=(
            "live Julii turn 1: data/runtime/sweep/army_construct_click.png, "
            "crop_field_con_zoom.png after Construction <6> with Flavius in the field",
        ),
        note=(
            "Right-edge dock titled FIELD CONSTRUCTION. Watchtower is the left "
            "card (200), fort the right (500). A card click spends. Official "
            "reject strings are TMT_FIELD_CONSTRUCTION_TEST_*. The same disc "
            "opens the town construction dock when a settlement is selected. "
            "Map orders are a left-click on the target once the cursor glyph "
            "changes (sword for an army); the 2004 cursor strings still say "
            "Right click."
        ),
    ),
    PanelEntry(
        id="diplomacy_window",
        name_key="SMT_OPEN_DIPLOMACY_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by="third crest on the overview tab strip, or Ctrl+3",
        shortcut_action="diplomacy_overview_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/diplomacy_window.png",
            "titles itself 'Factions'; tab 3 of the overview frame",
        ),
        note=(
            "The game titles this tab 'Factions', not diplomacy, and it conducts none: "
            "it reports standing. Sub-tabs are Ranking and Diplomatic Standing — the "
            "latter's own tooltip reads 'the state of relations between all factions'. "
            "Selecting our crest there shows reputation (80% on turn 1), a treasury "
            "word ('Boundless'), rows for Allies / Enemies / Trade Partners / Trade "
            "Embargo / Protectorates, and a territory minimap. Actual negotiation "
            "happens in `diplomatic_negotiations`, a decision panel."
        ),
    ),
    PanelEntry(
        id="finance_window",
        name_key="SMT_OPEN_FINANCE_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by="fourth crest on the overview tab strip, or Ctrl+4",
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
            "read-only as far as an unattended agent is concerned. The Family Tree "
            "sub-tab's tooltip is 'Your faction's lineage with an option to set the "
            "faction heir' — that option is a permanent succession change, not a view."
        ),
    ),
    PanelEntry(
        id="faction_summary",
        name_key="SMT_FACTION_BUTTON_TOOLTIP",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by=(
            "faction standard at the bottom-left of the HUD, or Ctrl+1; "
            "right-click the standard instead locates the capital"
        ),
        shortcut_action="faction_overview_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/faction_summary.png",
            "titles itself 'Faction Summary'; tab 1 of the overview frame",
        ),
        note=(
            "The tab the whole frame is named after, and the one the bottom-left "
            "standard opens onto. Carries the faction leader with his three attribute "
            "rows, the victory conditions, the current Senate mission with a locate "
            "button, faction stats, six ranking rows, and a Diplomacy block listing "
            "Allies, Enemies, Trade Partners and Trade Embargoes as crests. The seven "
            "round icons along the top of the dialog are the other overview tabs, not "
            "a second menu. Closed by the red X at the dialog's top-right, or Escape."
        ),
    ),
    PanelEntry(
        id="lists_scroll",
        name_key="SMT_SHOW_FACTION_LISTS",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by="fifth crest on the overview tab strip, or Ctrl+5",
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
            "with a filter dropdown. Military Forces lists generals and admirals; a row "
            "hover shows stack upkeep (Flavius 368 this turn). Double-click or the "
            "locate disc frames the stack and closes Lists. Agents lists Diplomats, "
            "Merchants and Assassins; the detail pane has a hooded Agent Hub disc and "
            "a locate magnifier. Locate closes Lists and selects the agent on the map. "
            "The settlement detail pane "
            "holds Automanage / Construction / Recruitment checkboxes and a tax-rate "
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
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by="sixth crest on the overview tab strip, or Ctrl+6",
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
            "scoped, and the only tab whose purpose is to move something rather than read it. "
            "The centre strip on a selected agent's map HUD is a different surface: it "
            "is labelled 'Your Agents' / 'Other Factions' Agents' and lists who is at "
            "that place, not this character's followers."
        ),
    ),
    PanelEntry(
        id="agent_hub",
        name_key="",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by=(
            "seventh crest on the overview tab strip, Ctrl+7, or the hooded disc "
            "on a selected agent's send-list footer"
        ),
        shortcut_action="agent_hub_button",
        tab_of="overview_window",
        geometry=OVERVIEW_FRAME,
        evidence=(
            "guided sweep: data/runtime/sweep/agent_hub.png",
            "live: data/runtime/sweep/agent_hub_ctrl7.png",
            "titles itself 'Agent Hub'; tab 7 of the overview frame",
        ),
        note=(
            "Bound to Ctrl+7 in both keysets but named by no shipped string: a Remastered "
            "addition the original text tables predate, and capture is the only way to "
            "name it. Type / Location / Status filters over the faction's agents, a "
            "'Send Agent to' list of missions with success percentages and turn counts, "
            "and a right-hand briefing (target, known buildings, missing intel as '?'). "
            "The one tab with a commit button — a gold Confirm at the footer that "
            "dispatches the agent for real. The map-selection SEND EMISSARY / SEND SPY "
            "list is a different surface: it is not this dialog, though its hooded "
            "footer disc opens it. The hourglass at the screen corner is End Turn."
        ),
    ),
    PanelEntry(
        id="campaign_map_overlays",
        name_key="toggle_overlays",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by=(
            "eye-and-scroll disc at the top-right of the HUD (tooltip: 'Map Overlay "
            "<Tab>'), or Tab in the moderntw keyset, Ctrl+Tab in default"
        ),
        shortcut_action="campaign_map_overlays_button",
        geometry=PanelGeometry(left=0.0, right=0.123, top=0.368, close_x=None),
        evidence=(
            "HUD click: data/runtime/sweep/hud_eye_open.png",
            "Escape closed it: data/runtime/sweep/ovl_after_escape.png",
            "eye toggle closed it: data/runtime/sweep/ovl_after_eye_toggle.png",
            "layer legends: data/runtime/sweep/crop_legend_*.png and crop_rleg_*.png",
        ),
        note=(
            "Not a parchment dialog, so there is no close X — Escape leaves it, and "
            "clicking the eye again toggles it off. Twelve layer buttons sit along the "
            "bottom edge. Square indicators are checkboxes — independent on/off for "
            "feature layers (Settlements, Armies, Agents, Fortifications, trade routes, "
            "Trade Goods), and several can be drawn at once. Round indicators are radio "
            "buttons — exclusive views (Factions, Diplomacy, Activity, and three siblings "
            "whose clicks selected Activity last). Diplomacy's legend is richer "
            "than a settlement hover: Player / Ally / Ally of Ally / Neutral / Enemy / "
            "Ally of Enemy. Each legend collapses via a chevron on its own header. "
            "Alt+click on a layer button opens the Steam wiki — do not. "
            "Read-only as a map: a click inside the view moved the camera not at all. "
            "See campaign/map_overlay.py for the twelve centres."
        ),
    ),
    PanelEntry(
        id="character_scroll",
        name_key="SMT_SHOW_CHARACTER_INFO",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.VERIFIED,
        opened_by=(
            "the enabled left-HUD button on a selected character; tooltip "
            "'Character's traits and Followers'"
        ),
        requires="a selected character",
        hazard="Alt+click on that HUD button opens the Steam wiki, same as F1.",
        geometry=PanelGeometry(
            left=0.256, right=0.743, top=0.261, close_x=(0.740, 0.275)
        ),
        evidence=(
            "live: data/runtime/sweep/agent_left_info.png",
            "close X at (0.740, 0.275) returned campaign_map",
        ),
        note=(
            "Titles itself with the character's type — 'DIPLOMAT' on Sextus Antio. "
            "Same left/right as the overview frame, but the top sits lower "
            "(0.261 vs 0.123), so it is not a Ctrl+N tab. Two interior tabs, "
            "STATS and TRAITS & FOLLOWERS. The traits page showed the Diplomatic "
            "trait (+3 Influence) and Followers: None. Close with the gold X on "
            "this parchment's top-right, not the overview-tab X above it."
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
