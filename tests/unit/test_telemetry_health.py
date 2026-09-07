"""The preflight that stops a blind run before it spends twenty turns."""

from __future__ import annotations

from comstar_game_ai.game_io.logs.telemetry_health import telemetry_health

_DISABLED_HEADER = """
==== message log start, build date: Jan 17 2022 ===
Mods Disabled: No
Active Mods:
comstar-telemetry

Logging disabled, use `enable_logging` command line argument to recieve enable logging
"""

_ENABLED_HEADER = """
==== message log start, build date: Jan 17 2022 ===
Active Mods:
comstar-telemetry
Turn 4 End
"""


def _write(tmp_path, message: str | None, script: str | None):
    message_log = tmp_path / "message_log.txt"
    script_log = tmp_path / "scripting_log.txt"
    if message is not None:
        message_log.write_text(message, encoding="utf-8")
    if script is not None:
        script_log.write_text(script, encoding="utf-8")
    return telemetry_health(message_log_path=message_log, script_log_path=script_log)


def test_both_channels_present_is_ok(tmp_path):
    health = _write(tmp_path, _ENABLED_HEADER, "event=NewTurnStart faction=julii\n")
    assert health.ok
    assert "both present" in health.detail


def test_the_header_confessing_logging_is_off_is_not_ok(tmp_path):
    """The only self-report we get: the file exists but will never grow."""
    health = _write(tmp_path, _DISABLED_HEADER, "event=NewTurnStart\n")

    assert not health.ok
    assert not health.message_log
    assert "logging is disabled" in health.detail


def test_a_missing_script_log_is_not_ok(tmp_path):
    health = _write(tmp_path, _ENABLED_HEADER, None)

    assert not health.ok
    assert health.message_log
    assert "verbose_script_logging" in health.detail


def test_a_missing_message_log_is_not_ok(tmp_path):
    health = _write(tmp_path, None, "event=NewTurnStart\n")

    assert not health.ok
    assert "no message_log.txt" in health.detail


def test_both_failures_are_reported_together(tmp_path):
    """One run, one message: an operator should not have to fix these one at a time."""
    health = _write(tmp_path, _DISABLED_HEADER, None)

    assert "logging is disabled" in health.detail
    assert "verbose_script_logging" in health.detail
    assert health.summary.startswith("telemetry degraded")
