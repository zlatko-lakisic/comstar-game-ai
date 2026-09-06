"""The Event Log dock: Alerts, News, Reports and Missions.

Four category discs sit on the left edge of the campaign map. Hovering or clicking
one slides a parchment out to the right; the discs ride with it and become tabs on
the panel's right edge. The on-screen tab titles and hover tooltips name the four
categories. The shipped tables call the container the Event Log
(`SMT_EVENT_LOG`); the shortcut action is `toggle_news_panel`, unbound in the
moderntw keyset, so the discs are the only way to open it.

The dock is a notice: the map stays playable and End Turn still works. Close it
with the gold X on the parchment's top-right corner, or by clicking the already
selected tab — that click toggles the dock shut. Escape was not used to dismiss
it. Escape on a *closed* dock is the pause menu.

Empty Alerts / News / Reports share one layout (title, Filters funnel, two
untitled footer discs). Missions replaces that body with the Senate mission card
(artwork, objective, turns remaining, locate magnifier). Do not invent names for
the empty-list footer discs; do not click Filters (it changes which messages
arrive); do not click the burning-scrolls disc.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DockTab:
    id: str
    #: On-screen title when this tab is selected, as drawn on the parchment.
    title: str
    #: First line of the hover tooltip — the game's own category name.
    tooltip_title: str
    tooltip_body: str
    #: Centre while the dock is collapsed against the left edge.
    closed_centre: tuple[float, float]
    #: Centre once the parchment is out and the discs sit on its right edge.
    open_centre: tuple[float, float]
    what_it_shows: str
    note: str = ""


#: Collapsed discs from dock_after_resume.png; open centres keep those y values
#: and sit just past the measured parchment right edge (313/1920 = 0.163).
TABS: tuple[DockTab, ...] = (
    DockTab(
        id="alerts",
        title="ALERTS",
        tooltip_title="Alerts",
        tooltip_body="Highlights the most important information about running your empire",
        closed_centre=(0.0130, 0.1315),
        open_centre=(0.1720, 0.1315),
        what_it_shows="Empty this turn: 'NO ALERTS'. Same chrome as News and Reports.",
    ),
    DockTab(
        id="news",
        title="NEWS",
        tooltip_title="News",
        tooltip_body="Brings information about all factions, including yours",
        closed_centre=(0.0130, 0.2056),
        open_centre=(0.1720, 0.2056),
        what_it_shows="Empty this turn: 'NO NEWS'. Same chrome as Alerts and Reports.",
    ),
    DockTab(
        id="reports",
        title="REPORTS",
        tooltip_title="Reports",
        tooltip_body="On recruitment and construction, as well as the End Of Turn Report",
        closed_centre=(0.0130, 0.2685),
        open_centre=(0.1720, 0.2685),
        what_it_shows="Empty this turn: 'NO REPORTS'. Same chrome as Alerts and News.",
    ),
    DockTab(
        id="missions",
        title="SENATE MISSION ASSIGNED",
        tooltip_title="Missions",
        tooltip_body="Details your current Senate missions, if any",
        closed_centre=(0.0130, 0.3213),
        open_centre=(0.1720, 0.3213),
        what_it_shows=(
            "The Senate mission card: Take Settlement Segesta, 10 turns remaining, "
            "reward promised on success. A locate magnifier sits on the card footer. "
            "The tab carried a 9+ badge while only this one card was visible."
        ),
        note=(
            "This is the same frame the corpus recorded as senate_mission_card. "
            "It is a tab of the Event Log, not a separate window, and not the "
            "Senate overview (Ctrl+2)."
        ),
    ),
)

BY_ID: dict[str, DockTab] = {tab.id: tab for tab in TABS}

#: Parchment edges and close X measured on the open Alerts dock, 1920x1080.
PANEL_LEFT = 0.00
PANEL_RIGHT = 0.163
PANEL_TOP = 0.066
CLOSE_X = (0.160, 0.077)

#: Filters funnel, left of the close X. Tooltip: 'Filters / Select which type of
#: messages you receive.' Do not click — it changes incoming messages.
FILTER_CENTRE = (0.148, 0.082)


def closed_centres() -> tuple[tuple[float, float], ...]:
    return tuple(tab.closed_centre for tab in TABS)


def open_centres() -> tuple[tuple[float, float], ...]:
    return tuple(tab.open_centre for tab in TABS)
