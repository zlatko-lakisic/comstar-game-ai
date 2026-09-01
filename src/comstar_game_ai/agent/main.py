"""Process B entrypoint — agent runtime and AO Reach client."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from comstar_game_ai.agent.reach.client import check_ada_health
from comstar_game_ai.agent.reach.session import ReachSession, overlay_root
from comstar_game_ai.shared.config import load_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
_LOGGER = logging.getLogger(__name__)


async def _health_check() -> int:
    health = await check_ada_health()
    print(json.dumps(health, indent=2))
    return 0 if health.get("ok") else 1


async def _register_overlay(*, hold_seconds: float) -> int:
    session = ReachSession()
    try:
        await session.start()
        print(
            json.dumps(
                {
                    "ok": True,
                    "overlay_root": str(overlay_root()),
                    "agents": session.bridge.registered_agent_ids,
                    "mcps": session.bridge.registered_mcp_ids,
                },
                indent=2,
            )
        )
        if hold_seconds > 0:
            await asyncio.sleep(hold_seconds)
        return 0
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("overlay registration failed: %s", exc)
        return 1
    finally:
        await session.stop(clear_remote=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comstar agent runtime (Process B)")
    parser.add_argument("--health", action="store_true", help="Probe AO engine health via mTLS")
    parser.add_argument(
        "--register-overlay",
        action="store_true",
        help="Register session overlay with AO and exit",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.0,
        help="Keep overlay registered for N seconds before clearing (with --register-overlay)",
    )
    args = parser.parse_args(argv)

    _ = load_config()

    if args.health:
        return asyncio.run(_health_check())
    if args.register_overlay:
        return asyncio.run(_register_overlay(hold_seconds=args.hold_seconds))

    print(
        "Process B stub — use --health or --register-overlay.\n"
        "Full battle/campaign loop not implemented yet.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
