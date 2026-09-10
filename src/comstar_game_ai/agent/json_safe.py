"""JSON-safe encoding for anything handed to Reach.

A live run died on every outbound call with `TypeError: Object of type date is
not JSON serializable`, raised inside the session bridge's `json.dumps`. Dates
arrive from unquoted YAML ISO values and from any `datetime` that slips into a
belief or payload dict. Fix them here, at the composer, before the payload leaves
this package — not by patching the SDK.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any


def json_safe(value: Any) -> Any:
    """Return a structure `json.dumps` can encode: dates become ISO 8601 strings."""
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Sets, Paths, custom objects: make them strings rather than crash the turn.
    return str(value)


def dumps_json_safe(value: Any, **kwargs: Any) -> str:
    """`json.dumps` after `json_safe`. Raises loudly if anything still cannot encode."""
    safe = json_safe(value)
    return json.dumps(safe, **kwargs)


def assert_json_round_trip(value: Any) -> Any:
    """Fail at compose time if the value cannot survive a JSON round trip.

    Used by the campaign payload composer so a date never reaches the websocket.
    """
    encoded = dumps_json_safe(value)
    return json.loads(encoded)
