"""Synthetic input helpers."""

from comstar_game_ai.game_io.input.coords import CoordinateTransform
from comstar_game_ai.game_io.input.diff_actuator import DiffActuator, OrderDiff, UnitOrder, compute_order_diff
from comstar_game_ai.game_io.input.send_input import SendInputController, normalize_key_name, virtual_key_for

__all__ = [
    "CoordinateTransform",
    "DiffActuator",
    "OrderDiff",
    "SendInputController",
    "UnitOrder",
    "compute_order_diff",
    "normalize_key_name",
    "virtual_key_for",
]
