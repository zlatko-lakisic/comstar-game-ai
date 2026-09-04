"""Block until Rome message_log shows Julii campaign map is loaded."""

from __future__ import annotations

import argparse
import sys

from comstar_game_ai.game_io.logs.campaign_probe import wait_for_campaign_ready
from comstar_game_ai.game_io.logs.message_log import default_message_log_path
from comstar_game_ai.shared.config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait for Julii campaign map in message_log")
    parser.add_argument("--timeout", type=float, default=1800.0, help="Max wait seconds (default 30 min)")
    parser.add_argument("--poll", type=float, default=2.0, help="Poll interval seconds")
    args = parser.parse_args(argv)

    cfg = load_config()
    faction = cfg.get("campaign", {}).get("player_faction", "julii")
    print(f"INFO watching {default_message_log_path()} for {faction} campaign...", flush=True)

    ok, turn = wait_for_campaign_ready(
        player_faction=faction,
        timeout_s=args.timeout,
        poll_s=args.poll,
        log_fn=lambda msg: print(msg, flush=True),
    )
    if not ok:
        print("FAIL timed out waiting for campaign load", flush=True)
        return 1

    print(f"OK  campaign ready turn={turn}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
