"""Measured campaign outcomes: when we did X, Y happened.

This is the long-term experience corpus for UI and camera work — case-based, not
doctrine. Each record is a specific action and the measured result, with a valence
so retrieval can surface failures as well as successes (C9). The narrative is
payload; the action/outcome/valence triple is what later retrieval should match.

Durable UI rules that always apply also live in `campaign_ui_facts.yaml`. Records
here stay tied to an observation so they can be revised if a later campaign
contradicts them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Valence(Enum):
    #: The action did what we needed, or is a safe default.
    GOOD = "good"
    #: The action mutated state we did not want, or stranded the session.
    BAD = "bad"
    #: Useful once you know it, surprising if you do not.
    MIXED = "mixed"


@dataclass(frozen=True)
class Learning:
    id: str
    action: str
    outcome: str
    valence: Valence
    lesson: str
    evidence: str
    #: True when later campaigns have no reason to expect a different result.
    durable: bool = True


LEARNINGS: tuple[Learning, ...] = (
    Learning(
        id="escape_on_clear_map_pauses",
        action="Press Escape on a campaign map with no parchment open",
        outcome="Pause menu and Help Sheet opened. First item is Return to Game.",
        valence=Valence.BAD,
        lesson=(
            "Do not use Escape to find out whether a panel is open. Prefer that "
            "panel's close X. If the pause menu is up, click Return to Game — do not "
            "click Exit."
        ),
        evidence="data/runtime/sweep/dock_clear.png after Escape on a clear map",
    ),
    Learning(
        id="selected_event_log_tab_toggles_shut",
        action="Click the already-selected Event Log tab",
        outcome="The dock collapsed. Later clicks at the open-tab x landed on the map.",
        valence=Valence.MIXED,
        lesson=(
            "Clicking the selected tab is a valid close, alongside the gold X. Do not "
            "click Alerts again to 'make sure' it is open."
        ),
        evidence="dock_walk: dock_tab_open_1.png measured panel=None after that click",
    ),
    Learning(
        id="event_log_hover_or_click_opens",
        action="Hover or click a collapsed left-edge Event Log disc",
        outcome="Parchment slid out to the right; the four discs rode to its right edge.",
        valence=Valence.GOOD,
        lesson="The discs are the opener. toggle_news_panel is unbound in moderntw.",
        evidence="dock_switch_opened.png; hover on the horn also opened it",
    ),
    Learning(
        id="event_log_close_x_works",
        action="Click the gold X at (0.160, 0.077) on the open Event Log",
        outcome="Dock collapsed. Mode stayed campaign_map.",
        valence=Valence.GOOD,
        lesson="Prefer this X over Escape. Same corner as the old senate_mission_card.",
        evidence="dock_switch_after_close_x.png",
    ),
    Learning(
        id="home_recovers_the_camera",
        action="Press Home from an arbitrary camera",
        outcome="Capital framed in one press. The capital was also selected.",
        valence=Valence.GOOD,
        lesson="Home is the recovery primitive. It also changes selection.",
        evidence="navigation sweep; capital_zoom bound to Home in both keysets",
    ),
    Learning(
        id="settlement_tooltip_is_authoritative",
        action="Hover Segesta, Patavium, and Rome",
        outcome="Tooltips said (At war) / (Neutral) / (Ally).",
        valence=Valence.GOOD,
        lesson="Colour picks what to hover; the tooltip decides owner and standing.",
        evidence="settlements.py cross-check on Julii turn 1",
    ),
    Learning(
        id="tooltip_figures_are_not_economy",
        action="Read the three unlabelled figures on a settlement hover",
        outcome="Coin 184 next to Lists population 3500 / income 1710 for the same town.",
        valence=Valence.BAD,
        lesson="Population and income come from Lists, not from the hover figures.",
        evidence="guided settlement identification, Julii turn 1",
    ),
    Learning(
        id="label_pill_rgb_is_not_the_legend",
        action="Match a map label-pill colour to the overlay standing legend",
        outcome="The RGBs disagree. A colour match would mis-tag standing.",
        valence=Valence.BAD,
        lesson="Pills are a prefilter. Overlay legend and tooltip are the keys.",
        evidence="settlements.LABEL_PILL_COLOURS vs overlay legend samples",
    ),
    Learning(
        id="overlay_is_not_a_clickable_map",
        action="Click inside the Map Overlay view, hoping to jump the camera",
        outcome="Camera did not move.",
        valence=Valence.MIXED,
        lesson="The overlay is a legend, not a navigator. Use Home, Lists locate, or the radar.",
        evidence="map overlay guided sweep",
    ),
    Learning(
        id="alt_click_overlay_opens_wiki",
        action="Alt+click an overlay layer button",
        outcome="Steam wiki overlay opened — same hazard as F1.",
        valence=Valence.BAD,
        lesson="Never Alt+click a layer. Hold-Alt-to-expand-tooltip is a different control.",
        evidence="map_overlay.py note; F1 help_window is EXTERNAL for the same reason",
    ),
    Learning(
        id="guessed_hud_clicks_open_the_browser",
        action="Click unverified positions near End Turn",
        outcome="Five guessed candidates missed; one opened the building browser and wedged the run.",
        valence=Valence.BAD,
        lesson="Locate a control before clicking it. Never sweep candidate coordinates.",
        evidence="never_blind_click_the_hud in campaign_ui_facts.yaml",
    ),
    Learning(
        id="lists_third_footer_sets_capital",
        action="Click the third footer button on the Lists settlement pane",
        outcome="Would permanently change the faction capital.",
        valence=Valence.BAD,
        lesson="First footer locates. Second explores the battle map. Third sets capital. Use the first.",
        evidence="hover_lists_btn1..3.png; lists_scroll note",
    ),
    Learning(
        id="family_tree_can_set_the_heir",
        action="Click in the Family Tree sub-tab of Finance & Family",
        outcome="The tab's own tooltip offers setting the faction heir — a succession change.",
        valence=Valence.BAD,
        lesson="Read the tree. Do not click a character to 'inspect' them there.",
        evidence="Finance & Family hover; SMT family-tree tooltip",
    ),
    Learning(
        id="event_log_filters_change_incoming_mail",
        action="Click the Filters funnel on the Event Log",
        outcome="Not clicked. Tooltip: 'Select which type of messages you receive.'",
        valence=Valence.BAD,
        lesson="The funnel is a setting, not a view. Do not click it while reading.",
        evidence="dock_chrome2_filter.png",
    ),
    Learning(
        id="senate_mission_agrees_across_surfaces",
        action="Read the mission on Faction Summary and again on Event Log → Missions",
        outcome="Both showed Take Settlement Segesta, 10 turns, richly rewarded.",
        valence=Valence.GOOD,
        lesson="Either surface is enough. The Event Log card is the same notice, not a second mission.",
        evidence="fs_tab_1 / dock_switch_4.png, Julii turn 1",
    ),
    Learning(
        id="agent_drag_previews_path",
        action="Hold left mouse on a diplomat, drag toward a road, then release back on him",
        outcome="A green path appeared while held. On release he was still idle at Arretium.",
        valence=Valence.GOOD,
        lesson=(
            "Drag-hold is the preview. Release on the character to cancel. A click "
            "on a destination is an order — do not click the map just to look."
        ),
        evidence="agent_path_preview.png / agent_path_released.png",
    ),
    Learning(
        id="traits_button_opens_character_scroll",
        action="Click the enabled left-HUD button on Sextus Antio",
        outcome=(
            "Character scroll titled DIPLOMAT opened (panel top 0.261). Traits & "
            "Followers showed Diplomatic +3 and Followers: None."
        ),
        valence=Valence.GOOD,
        lesson="That button is the extra-info pane. Close with its own X, not the overview-tab X.",
        evidence="agent_left_info.png; close at (0.740, 0.275)",
    ),
    Learning(
        id="agent_hub_confirm_dispatches",
        action="Open Agent Hub (Ctrl+7) with a Send Agent row highlighted",
        outcome="Gold Confirm sat on the briefing. Not clicked. The first row was Negotiate with Tarentum, 3 turns.",
        valence=Valence.BAD,
        lesson="Confirm sends the agent. Close with the overview X. The map SEND list is a second dispatcher.",
        evidence="agent_hub_ctrl7.png",
    ),
    Learning(
        id="disband_boot_is_live",
        action="Inspect the selected-agent HUD boot without clicking it",
        outcome="Boot sits on the centre strip. Delete is bound to the same action.",
        valence=Valence.BAD,
        lesson="The boot disbands the character. Do not click it or press Delete.",
        evidence="agent_located_0.png / agent_located_1.png",
    ),
    Learning(
        id="send_list_is_three_clicks",
        action="Click Spy on Patavium, then Confirm, then Assign",
        outcome=(
            "Row drew a green/red path to Patavium. Confirm opened 'Send Agent to: "
            "Patavium' with Cancel Mission. Assign committed: Lists shows Target: "
            "Patavium and Cancel Mission; location flipped from Ariminum to Patavium. "
            "The same three clicks sent Sextus Antio to negotiate with Patavium."
        ),
        valence=Valence.GOOD,
        lesson=(
            "Row stages, Confirm opens the briefing, Assign commits. The corner "
            "hourglass is End Turn — Confirm sits left of it at about (0.90, 0.93)."
        ),
        evidence="spy_send_patavium.png / spy_assigned_patavium.png / crop_agent_lists_detail_0.png",
    ),
    Learning(
        id="spy_on_nearest_gallic_character",
        action="Pick the Gallic model standing on the road next to the spy and send to Eporedorix",
        outcome=(
            "Mission assigned to Eporedorix. Senaculus of Sabis was the first "
            "character row on SEND SPY and carried the shorter turn glyph."
        ),
        valence=Valence.BAD,
        lesson=(
            "Do not infer distance from who looks nearest on the 3D map. Read the "
            "SEND-list turn glyph. Closest is a read; it is not automatically the "
            "right target."
        ),
        evidence="spy_located_now.png SEND list vs spy_on_gallic.png map hover",
    ),
    Learning(
        id="send_list_turn_glyph_is_distance",
        action="Compare SEND SPY character rows after the spy reached Patavium",
        outcome=(
            "Senaculus of Sabis sat above Eporedorix and showed the smaller turn "
            "count. The path line on the map did not decide who was nearer."
        ),
        valence=Valence.GOOD,
        lesson=(
            "Distance is the `[n]` glyph on the send row. Compare glyphs within "
            "characters or within settlements, not across types."
        ),
        evidence="spy_located_now.png SEND SPY list; Senaculus first character row",
    ),
    Learning(
        id="building_browser_tree_disc_opens",
        action="Click the tree disc at (0.934, 0.968) with Arretium selected",
        outcome="Building Browser opened. Escape does not close it.",
        valence=Valence.GOOD,
        lesson="That disc is the opener. Close with the parchment X.",
        evidence="town_browser.png panel=(492, 1427, 223); tt_f934.png",
    ),
    Learning(
        id="map_order_waits_for_the_cursor_glyph",
        action="Left-click Segesta's nameplate with Flavius selected",
        outcome="Selected Enemy SEGESTA Village.",
        valence=Valence.MIXED,
        lesson="Wait for the sword cursor.",
        evidence="army_sword_on_segesta.png / army_attack_segesta2.png; operator: left-click after glyph",
    ),
    Learning(
        id="map_click_on_the_general_narrows_the_stack",
        action="Reselect Flavius with a map click, then attack",
        outcome="The HUD showed one unit card, so the order would have sent the bodyguard alone",
        valence=Valence.BAD,
        lesson=(
            "A selected general is not a selected army. Reacquire through Lists → "
            "Military Forces → locate, and count unit cards before ordering an attack."
        ),
        evidence="field_selected.png single card vs army_lists.png Flavius Julius, 5 units",
    ),
    Learning(
        id="attack_glyph_is_a_change_not_a_value",
        action="Compare the cursor handle over own land and over the rebel stack",
        outcome="It changed, and the click on the changed handle issued the attack",
        valence=Valence.MIXED,
        lesson=(
            "Baseline the cursor in the same session and watch it change. The handle "
            "identifies the glyph within one session only, so a stored number is not "
            "evidence of a target."
        ),
        evidence="cur_land.bmp vs cur_stack_0.24_0.38.bmp; attack issued on the changed handle",
    ),
    Learning(
        id="auto_resolve_clears_battle_deployment",
        action="Click auto-resolve at (0.43, 0.72) on Battle Deployment",
        outcome="The battle resolved and the campaign map came back",
        valence=Valence.GOOD,
        lesson=(
            "Auto-resolve is the only safe answer while there is no battle loop. "
            "Resolve it before the modal handler, which reads it as an ordinary "
            "parchment panel and would click a decision button."
        ),
        evidence="prebattle_now2.png then autoresolve_result2.png back on the map",
    ),
    Learning(
        id="logging_off_makes_the_run_blind",
        action="Run 20 turns against a Rome launched without enable_logging",
        outcome="Zero belief records: no scripting_log.txt at all, message_log frozen at launch",
        valence=Valence.BAD,
        lesson=(
            "Check that the log is growing before a run, not that the mod is enabled. "
            "comstar-telemetry loaded and wrote nothing, because script_log output "
            "needs the game's logging switch. Autosave filenames were the only turn "
            "evidence left, and nothing recorded what changed in the campaign."
        ),
        evidence=(
            "20260906 run: mod_loading.txt shows comstar-telemetry enabled; "
            "message_log.txt mtime = launch time, 'Logging disabled' in its header; "
            "belief_history=0 armies=0 settlements=0"
        ),
    ),
    Learning(
        id="empty_belief_reads_as_a_decision",
        action="Plan a turn with no characters or settlements in belief",
        outcome="No moves planned, and the trail looked identical to a deliberate hold",
        valence=Valence.BAD,
        lesson=(
            "A blind run and a cautious run are indistinguishable unless belief counts "
            "are reported per turn. _planned_moves needs both a character and a "
            "settlement, so an empty store silently disables movement whatever the "
            "directive says."
        ),
        evidence="20260906 run: 20 turns of 'halt_ai julii, list_characters, run_ai' with belief empty",
    ),
    Learning(
        id="ai_turn_banner_reads_as_a_modal",
        action="Classify the screen while another faction takes its turn",
        outcome="modal / left_overlay_panel at 0.69-0.84 confidence, with nothing to dismiss",
        valence=Valence.BAD,
        lesson=(
            "The between-turns faction banner is a wait state, not a panel. Each one "
            "cost a 180s-timeout vision call that answered 'nothing over the map', and "
            "the handler then clicked by geometry anyway."
        ),
        evidence="dialog-6/10/20 frames: Rebels, Numidia and Gaul turn banners over the map",
    ),
    Learning(
        id="parked_cursor_makes_its_own_panel",
        action="Leave the cursor where the last click landed on the map",
        outcome="A character tooltip opened under it and classified as a modal",
        valence=Valence.BAD,
        lesson=(
            "Park the cursor on neutral chrome after clicking. Rome's hover tooltips "
            "are parchment, so our own idle pointer manufactures the panels the loop "
            "then tries to dismiss."
        ),
        evidence="dialog-16 frame: Numerius Flaminius tooltip under a cursor left on the map",
    ),
    Learning(
        id="passive_turns_drift_into_deficit",
        action="End 20 turns without managing the economy",
        outcome="Net income -191: expenditure was salaries and upkeep alone, +287 in one turn",
        valence=Valence.MIXED,
        lesson=(
            "Ending turns is not neutral. Ten in-game years of family growth add "
            "generals, each with a bodyguard and a salary, while recruitment and "
            "construction stayed at 0 — so the deficit came from time passing, not "
            "from anything the loop ordered."
        ),
        evidence=(
            "tip_alt2.png Financial Overview at 261 BC: income 4360 "
            "(taxes 1949, trade 541, farming 1536, other 334) vs upkeep 4551"
        ),
    ),
    Learning(
        id="field_construction_opens_from_the_town_disc",
        action="Click Construction <6> with Flavius in the field",
        outcome="Watchtower and fort cards opened.",
        valence=Valence.GOOD,
        lesson="A card click spends.",
        evidence="army_construct_click.png / crop_field_con_zoom.png",
    ),
)

BY_ID: dict[str, Learning] = {item.id: item for item in LEARNINGS}


def by_valence(valence: Valence) -> tuple[Learning, ...]:
    return tuple(item for item in LEARNINGS if item.valence is valence)
