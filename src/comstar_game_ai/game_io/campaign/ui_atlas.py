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

        Decision panels do not: the check/X/counter trio at the bottom centre
        replaces the corner dismiss button. This is why a close-X search returning
        nothing is a classification signal rather than a detector failure — the
        nine diplomacy frames in the corpus were unidentified for exactly this
        reason, having been searched for a button the panel never had.
        """
        return self.panel_class is not PanelClass.DECISION


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
        status=Status.UNSEEN,
        opened_by="laurel-wreath button at the bottom-left of the HUD",
        shortcut_action="senate_button",
        note="Roman factions only; it is where standing missions and Senate favour live.",
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
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="construction button on the settlement scroll",
        shortcut_action="construction_button",
    ),
    PanelEntry(
        id="training_window",
        name_key="SMT_OPEN_TRAINING_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="recruitment button on the settlement scroll",
        shortcut_action="recruitment_button",
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
        status=Status.UNSEEN,
        opened_by="diplomacy button on the bottom-left HUD",
        shortcut_action="diplomacy_overview_button",
    ),
    PanelEntry(
        id="finance_window",
        name_key="SMT_OPEN_FINANCE_WINDOW",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="coin button on the bottom-left HUD",
        shortcut_action="finances_button",
    ),
    PanelEntry(
        id="faction_summary",
        name_key="SMT_FACTION_BUTTON_TOOLTIP",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="faction button on the bottom-left HUD; right-click instead locates the capital",
        shortcut_action="faction_overview_button",
    ),
    PanelEntry(
        id="lists_scroll",
        name_key="SMT_SHOW_FACTION_LISTS",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="lists button on the bottom-left HUD",
        shortcut_action="lists_button",
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
        dismiss=(Dismiss.CLOSE_X, Dismiss.ESCAPE),
        status=Status.UNSEEN,
        opened_by="the show_help shortcut key",
        shortcut_action="show_help",
    ),
    PanelEntry(
        id="retinue_panel",
        name_key="SMT_ANCILLARIES",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="retinue button on the bottom-left HUD",
        shortcut_action="retinue_button",
        note=(
            "Rome calls retinue members ancillaries. They attach to a named character "
            "and modify his traits, so this panel is character-scoped, not faction-scoped."
        ),
    ),
    PanelEntry(
        id="agent_hub",
        name_key="",
        panel_class=PanelClass.OBSTRUCTING,
        dismiss=(Dismiss.CLOSE_X,),
        status=Status.UNSEEN,
        opened_by="agent hub button on the bottom-left HUD",
        shortcut_action="agent_hub_button",
        note=(
            "Bound to Ctrl+7 in both keysets but named by no shipped string: a "
            "Remastered addition the original text tables predate. Its existence is "
            "known only from the binding database, so it must be named by capture."
        ),
    ),
    PanelEntry(
        id="campaign_map_overlays",
        name_key="toggle_overlays",
        panel_class=PanelClass.NOTICE,
        dismiss=(Dismiss.LEAVE_OPEN,),
        status=Status.UNSEEN,
        opened_by="the campaign_map_overlays_button, bound to Tab",
        shortcut_action="campaign_map_overlays_button",
        note=(
            "Recolours the map itself rather than opening a scroll, which is why it is "
            "a notice: nothing is covered and nothing needs dismissing. Toggling it "
            "changes every colour the perception layer sees, so any pixel heuristic "
            "calibrated on the normal map is invalid while an overlay is active."
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
