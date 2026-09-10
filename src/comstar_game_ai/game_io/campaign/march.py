"""Campaign map marches: select the stack with the mouse, then click a destination.

Console ``move_character`` is not how a player moves an army on Remastered, and
SendInput returning true after typing it does not mean Rome moved anyone. This
module plays the same surface End Turn and attack already use:

1. Lists → Military Forces → row → locate (whole stack, camera framed)
2. Left-click a land point in the map direction of the target once the cursor
   glyph changes from the open-land baseline

Attack uses the sword glyph and measured settlement norms. March uses any
cursor change over open land toward the target, short of the settlement itself
so we do not declare a siege by accident on the first step.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from comstar_game_ai.game_io.campaign.combat import (
    NEUTRAL_CURSOR_PROBE,
    CombatDirector,
    StackSelection,
    client_norm_to_screen,
    read_cursor_handle,
)
from comstar_game_ai.game_io.campaign.ui_mode import grab_rgb_image

if TYPE_CHECKING:
    from PIL import Image

    from comstar_game_ai.game_io.input.send_input import SendInputController

_LOGGER = logging.getLogger(__name__)

#: First Military Forces rows measured for Julii (see test_campaign_combat_step).
#: Without OCR we try these in order until a stack is selected.
DEFAULT_LISTS_ROWS: tuple[tuple[float, float], ...] = (
    (0.30, 0.415),
    (0.30, 0.455),
    (0.30, 0.495),
    (0.30, 0.535),
)

#: After locate, the stack sits near the view centre. Click this far (norm) along
#: the map bearing toward the target — short of a settlement nameplate.
MARCH_STEP_NORM = 0.16

#: Map Y increases north; client Y increases down. Flip when projecting.
MAP_Y_TO_SCREEN_SIGN = -1.0


@dataclass(frozen=True)
class MarchOutcome:
    ordered: bool
    reason: str
    unit_cards: int = 0
    click_norm: tuple[float, float] | None = None
    step_to: tuple[float, float] | None = None


@dataclass
class MarchDirector:
    """Mouse march for campaign armies. Dependencies injectable for tests."""

    hwnd: int | None = None
    controller: SendInputController | None = None
    capture: Callable[[], Image.Image | None] | None = None
    cursor_handle: Callable[[], int] = read_cursor_handle
    to_screen: Callable[[float, float], tuple[int, int] | None] | None = None
    sleep: Callable[[float], None] = time.sleep
    hover_dwell_s: float = 1.2
    order_settle_s: float = 3.0
    lists_rows: tuple[tuple[float, float], ...] = DEFAULT_LISTS_ROWS
    step_norm: float = MARCH_STEP_NORM
    on_heartbeat: Callable[[], None] | None = None
    last_reason: str = field(default="", init=False)
    _combat: CombatDirector | None = field(default=None, init=False, repr=False)

    def _combat_director(self) -> CombatDirector:
        if self._combat is None:
            self._combat = CombatDirector(
                hwnd=self.hwnd,
                controller=self.controller,
                capture=self.capture,
                cursor_handle=self.cursor_handle,
                to_screen=self.to_screen,
                sleep=self.sleep,
                hover_dwell_s=self.hover_dwell_s,
                order_settle_s=self.order_settle_s,
                on_heartbeat=self.on_heartbeat,
            )
        return self._combat

    def _heartbeat(self) -> None:
        if self.on_heartbeat is None:
            return
        try:
            self.on_heartbeat()
        except Exception:  # noqa: BLE001
            _LOGGER.warning("march heartbeat failed", exc_info=True)

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

    def acquire_any_stack(
        self, preferred_row: tuple[float, float] | None = None
    ) -> StackSelection | None:
        """Lists → Military Forces → locate until the HUD shows a selection."""
        combat = self._combat_director()
        rows: list[tuple[float, float]] = []
        if preferred_row is not None:
            rows.append(preferred_row)
        rows.extend(self.lists_rows)
        seen: set[tuple[float, float]] = set()
        for row in rows:
            if row in seen:
                continue
            seen.add(row)
            self._heartbeat()
            selection = combat.acquire_stack(row)
            if selection.unit_cards >= 1:
                return selection
            _LOGGER.info("march: lists row %s did not select a stack (%s)", row, selection.reason)
        return None

    @staticmethod
    def destination_norm(
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        step_norm: float = MARCH_STEP_NORM,
        origin: tuple[float, float] = (0.50, 0.48),
    ) -> tuple[float, float] | None:
        """Screen click near the framed stack, along the map bearing to the target."""
        dx = float(to_x) - float(from_x)
        dy = (float(to_y) - float(from_y)) * MAP_Y_TO_SCREEN_SIGN
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return None
        ux, uy = dx / length, dy / length
        xn = origin[0] + ux * step_norm
        yn = origin[1] + uy * step_norm
        xn = min(0.85, max(0.15, xn))
        yn = min(0.82, max(0.18, yn))
        return (xn, yn)

    @staticmethod
    def one_tile_step(
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
    ) -> tuple[float, float] | None:
        """Belief estimate after a successful march click (one map tile toward target)."""
        dx = 0 if abs(to_x - from_x) < 0.5 else (1 if to_x > from_x else -1)
        dy = 0 if abs(to_y - from_y) < 0.5 else (1 if to_y > from_y else -1)
        if dx == 0 and dy == 0:
            return None
        return (from_x + dx, from_y + dy)

    def march(
        self,
        *,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        lists_row: tuple[float, float] | None = None,
        character_name: str = "",
    ) -> MarchOutcome:
        """Select a stack and left-click a step toward the target."""
        if self.controller is None or self.hwnd is None:
            return self._refuse("no_controller")

        selection = self.acquire_any_stack(lists_row)
        if selection is None or selection.unit_cards < 1:
            return self._refuse("stack_not_selected")

        click = self.destination_norm(
            from_x=from_x,
            from_y=from_y,
            to_x=to_x,
            to_y=to_y,
            step_norm=self.step_norm,
        )
        if click is None:
            return self._refuse("already_at_target", selection.unit_cards)

        self._hover(NEUTRAL_CURSOR_PROBE)
        baseline = self.cursor_handle()
        if not self._hover(click):
            return self._refuse("hover_failed", selection.unit_cards)
        hovered = self.cursor_handle()
        if hovered == 0 or baseline == 0:
            return self._refuse("cursor_unreadable", selection.unit_cards)
        if hovered == baseline:
            # Try a shorter step — cursor may not change at long range.
            shorter = self.destination_norm(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                step_norm=self.step_norm * 0.55,
            )
            if shorter is None or shorter == click:
                return self._refuse("no_move_cursor", selection.unit_cards)
            click = shorter
            if not self._hover(click):
                return self._refuse("hover_failed_short", selection.unit_cards)
            hovered = self.cursor_handle()
            if hovered == 0 or hovered == baseline:
                return self._refuse("no_move_cursor", selection.unit_cards)

        screen = self._screen(click)
        if screen is None:
            return self._refuse("no_screen_coords", selection.unit_cards)

        self.controller.click(*screen, dwell_ms=120, settle_ms=450)
        self.sleep(self.order_settle_s)
        self._heartbeat()

        step = self.one_tile_step(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y)
        who = character_name or "stack"
        self.last_reason = "ordered"
        _LOGGER.info(
            "march ordered for %s click=(%.3f,%.3f) step=%s cards=%s",
            who,
            click[0],
            click[1],
            step,
            selection.unit_cards,
        )
        return MarchOutcome(
            ordered=True,
            reason="ordered",
            unit_cards=selection.unit_cards,
            click_norm=click,
            step_to=step,
        )

    def _refuse(self, reason: str, unit_cards: int = 0) -> MarchOutcome:
        self.last_reason = reason
        _LOGGER.info("march refused: %s", reason)
        return MarchOutcome(ordered=False, reason=reason, unit_cards=unit_cards)
