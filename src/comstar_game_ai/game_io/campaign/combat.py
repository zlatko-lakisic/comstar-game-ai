"""Campaign combat: acquire the whole stack, issue the order, resolve the battle.

Measured on the live Julii siege of Segesta. Three things there were not obvious:

1. A selected general is not a selected army. Clicking the general's model on the
   map narrows the selection to his bodyguard, and the attack that follows sends one
   unit in alone. `army.attack_safe_stack_selected` is the gate, and the only
   reliable reacquire is Lists → Military Forces → locate.
2. The attack tell is the cursor glyph, not a button. Rome swaps the cursor to a
   sword when the hovered pixel is a valid target; a click before that selects the
   settlement nameplate instead. `HCURSOR` handles are per-session, so the sword
   cannot be a constant — it is learned by baselining the cursor over open land and
   watching for it to change.
3. Battle Deployment reads as a plain MODAL to `classify_campaign_image`, so the
   generic modal handler is willing to click a decision button on it. Getting that
   wrong hands control to the battle map, which no loop can drive yet. Auto-resolve
   is the one safe answer, so resolve the panel before the modal handler sees it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from comstar_game_ai.game_io.campaign import army
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, classify_campaign_image, grab_rgb_image

if TYPE_CHECKING:
    from PIL import Image

    from comstar_game_ai.game_io.input.send_input import SendInputController

_LOGGER = logging.getLogger(__name__)

#: Lists panel, Military Forces sub-tab. Ctrl+5 opens Lists on Remastered.
LISTS_OPEN_CHORD = ("ctrl", "5")

#: Open own land near the map centre, used to baseline the "not a target" cursor.
NEUTRAL_CURSOR_PROBE = (0.50, 0.42)

#: Battle Deployment footer. Auto-resolve is the left button; the centre withdraws
#: and the right one drops into the battle map, so only this point is ever clicked.
AUTO_RESOLVE_BUTTON = (0.43, 0.72)

#: Siege panel footer: lift (0.42), assault (0.50), maintain (0.58).
SIEGE_ASSAULT_BUTTON = (0.50, 0.62)


@dataclass(frozen=True)
class StackSelection:
    """What the HUD says is selected, and whether that is enough to attack with."""

    unit_cards: int
    safe_to_attack: bool
    reason: str = ""


@dataclass(frozen=True)
class AttackOutcome:
    ordered: bool
    battle_resolved: bool
    reason: str
    unit_cards: int = 0


def battle_deployment_present(image: Image.Image) -> bool:
    """Whether the frame shows the pre-battle Battle Deployment panel.

    Geometry, because there is no OCR here: the atlas measured the panel spanning
    0.16–0.83 of the width with its top edge at 0.35. A settlement or building scroll
    is just as wide but starts far higher, which is what the top-edge floor excludes.
    """
    from comstar_game_ai.game_io.campaign.modal import panel_bounds

    bounds = panel_bounds(image)
    if bounds is None:
        return False
    left, right, top = bounds
    width, height = image.size
    return (
        left <= width * 0.30
        and right >= width * 0.70
        and height * 0.24 <= top <= height * 0.55
    )


def read_cursor_handle() -> int:
    """Current `HCURSOR`, or 0 when it cannot be read.

    The handle identifies the glyph within one session only. Callers must compare it
    against a baseline they took themselves rather than against a stored number.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("hCursor", wintypes.HANDLE),
                ("ptScreenPos", wintypes.POINT),
            ]

        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not ctypes.windll.user32.GetCursorInfo(ctypes.byref(info)):
            return 0
        return int(info.hCursor or 0)
    except Exception:
        return 0


def client_norm_to_screen(hwnd: int, x_norm: float, y_norm: float) -> tuple[int, int] | None:
    try:
        import win32gui

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        point = (
            int(round(x_norm * max(right - left, 1))),
            int(round(y_norm * max(bottom - top, 1))),
        )
        return win32gui.ClientToScreen(hwnd, point)
    except Exception:
        return None


@dataclass
class CombatDirector:
    """Attack and battle handling for the campaign loop.

    Every dependency is injectable so the decisions can be tested without Rome: the
    capture, the cursor read, and the client-to-screen transform are the only pieces
    that need a live game.
    """

    hwnd: int | None = None
    controller: SendInputController | None = None
    capture: Callable[[], Image.Image | None] | None = None
    cursor_handle: Callable[[], int] = read_cursor_handle
    to_screen: Callable[[float, float], tuple[int, int] | None] | None = None
    sleep: Callable[[float], None] = time.sleep
    minimum_units: int = army.MIN_SAFE_ATTACK_UNITS
    hover_dwell_s: float = 1.6
    order_settle_s: float = 6.0
    battle_timeout_s: float = 120.0
    # Resolving a battle can watch the panel for two minutes. Silence that long
    # reads as a wedged process, and the watchdog ended a run on turn 29 for it.
    on_heartbeat: Callable[[], None] | None = None
    last_reason: str = field(default="", init=False)

    def _heartbeat(self) -> None:
        if self.on_heartbeat is None:
            return
        try:
            self.on_heartbeat()
        except Exception:  # noqa: BLE001 - a watchdog must not lose us the battle
            _LOGGER.warning("combat heartbeat failed", exc_info=True)

    def _grab(self) -> Image.Image | None:
        if self.capture is not None:
            return self.capture()
        return grab_rgb_image(self.hwnd)

    def _screen(self, point: tuple[float, float]) -> tuple[int, int] | None:
        if self.to_screen is not None:
            return self.to_screen(*point)
        if self.hwnd is None:
            return None
        return client_norm_to_screen(self.hwnd, *point)

    def _click_norm(self, point: tuple[float, float]) -> bool:
        if self.controller is None or self.hwnd is None:
            return False
        return bool(self.controller.click_client_norm(self.hwnd, point[0], point[1], dwell_ms=60))

    def _hover(self, point: tuple[float, float]) -> bool:
        """Park the cursor and let Rome notice.

        Two moves, because the game samples the cursor on its own frame tick and a
        single move followed immediately by a read returns the previous glyph.
        """
        if self.controller is None:
            return False
        screen = self._screen(point)
        if screen is None:
            return False
        self.controller.move_mouse(*screen)
        self.sleep(0.15)
        self.controller.move_mouse(*screen)
        self.sleep(self.hover_dwell_s)
        return True

    def selected_stack(self) -> StackSelection:
        """Read the bottom HUD and decide whether the selection can safely attack."""
        image = self._grab()
        if image is None:
            return StackSelection(unit_cards=0, safe_to_attack=False, reason="no_capture")
        cards = army.count_selected_unit_cards(image)
        safe = army.attack_requires_full_stack(cards, minimum_units=self.minimum_units)
        return StackSelection(
            unit_cards=cards,
            safe_to_attack=safe,
            reason="" if safe else f"only {cards} unit card(s) selected",
        )

    def acquire_stack(self, lists_row_norm: tuple[float, float]) -> StackSelection:
        """Reacquire a whole army via Lists → Military Forces → locate.

        The locate disc frames the stack and closes Lists, which selects the army
        rather than the single model a map click would have narrowed it to.
        """
        if self.controller is None or self.hwnd is None:
            return StackSelection(unit_cards=0, safe_to_attack=False, reason="no_controller")
        self.controller.chord_scancode(*LISTS_OPEN_CHORD, hwnd=self.hwnd)
        self.sleep(1.4)
        self._click_norm(army.LISTS_MILITARY_TAB)
        self.sleep(1.0)
        self._click_norm(lists_row_norm)
        self.sleep(0.8)
        self._click_norm(army.LISTS_LOCATE)
        self.sleep(1.8)
        return self.selected_stack()

    def attack(
        self,
        target_norm: tuple[float, float],
        *,
        neutral_norm: tuple[float, float] = NEUTRAL_CURSOR_PROBE,
    ) -> AttackOutcome:
        """Order an attack on a map point, but only on the game's own evidence.

        Refuses unless the HUD shows a full stack and the cursor turns into a target
        glyph over the point. Both checks fail closed: an unreadable cursor is treated
        as "not a target", because the click that follows a wrong guess either selects
        an enemy settlement or, on a neutral stack, declares a war.
        """
        selection = self.selected_stack()
        if not selection.safe_to_attack:
            return self._refuse("stack_not_selected: " + selection.reason, selection.unit_cards)

        self._hover(neutral_norm)
        baseline = self.cursor_handle()
        if not self._hover(target_norm):
            return self._refuse("hover_failed", selection.unit_cards)
        hovered = self.cursor_handle()
        if hovered == 0 or baseline == 0:
            return self._refuse("cursor_unreadable", selection.unit_cards)
        if hovered == baseline:
            return self._refuse("no_attack_cursor", selection.unit_cards)

        after_hover = self.selected_stack()
        if not after_hover.safe_to_attack:
            return self._refuse("selection_lost_before_click: " + after_hover.reason, after_hover.unit_cards)

        screen = self._screen(target_norm)
        if screen is None or self.controller is None:
            return self._refuse("no_screen_coords", selection.unit_cards)
        self.controller.click(*screen, dwell_ms=120, settle_ms=450)
        self.sleep(self.order_settle_s)

        resolved = self.resolve_battle()
        self.last_reason = "ordered"
        return AttackOutcome(
            ordered=True,
            battle_resolved=resolved,
            reason="ordered",
            unit_cards=selection.unit_cards,
        )

    def assault_siege(self) -> AttackOutcome:
        """Click Assault on an open siege panel and resolve the battle it opens."""
        if not self._click_norm(SIEGE_ASSAULT_BUTTON):
            return self._refuse("assault_click_failed")
        self.sleep(self.order_settle_s)
        resolved = self.resolve_battle()
        return AttackOutcome(ordered=True, battle_resolved=resolved, reason="assault")

    def battle_pending(self) -> bool:
        image = self._grab()
        return bool(image is not None and battle_deployment_present(image))

    def resolve_battle(self) -> bool:
        """Auto-resolve a pending Battle Deployment panel; True once it is gone.

        No panel is success, not failure: an attack can open a siege instead of a
        battle, and a battle can already have been resolved by the time we look.
        """
        image = self._grab()
        if image is None:
            return False
        if not battle_deployment_present(image):
            return True

        _LOGGER.info("battle deployment up — auto-resolving")
        if not self._click_norm(AUTO_RESOLVE_BUTTON):
            return False

        deadline = time.monotonic() + self.battle_timeout_s
        while time.monotonic() < deadline:
            self._heartbeat()
            self.sleep(2.0)
            frame = self._grab()
            if frame is None:
                continue
            if not battle_deployment_present(frame):
                mode = classify_campaign_image(frame).mode
                _LOGGER.info("battle resolved, ui=%s", mode.value)
                return mode != CampaignUiMode.UNKNOWN
        _LOGGER.warning("timed out waiting for the battle panel to clear")
        return False

    def _refuse(self, reason: str, unit_cards: int = 0) -> AttackOutcome:
        self.last_reason = reason
        _LOGGER.info("attack refused: %s", reason)
        return AttackOutcome(ordered=False, battle_resolved=False, reason=reason, unit_cards=unit_cards)
