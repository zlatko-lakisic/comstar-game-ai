"""Process A entrypoint."""

from __future__ import annotations

import argparse
import sys

from comstar_game_ai.game_io.preconditions import check_preconditions
from comstar_game_ai.game_io.runtime import GameIoRuntime
from comstar_game_ai.game_io.self_tests import run_self_tests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comstar Game I/O service")
    parser.add_argument("--self-test-only", action="store_true", help="Run Phase 0 self-tests and exit")
    parser.add_argument("--require-game", action="store_true", help="Fail if Rome is not running")
    parser.add_argument("--run-campaign", action="store_true", help="Run hardcoded campaign driver")
    parser.add_argument("--run-battle", action="store_true", help="Run battle freeze loop driver")
    parser.add_argument("--service", action="store_true", help="Run capture + hotkey service until killed")
    parser.add_argument("--turns", type=int, default=20, help="Campaign turns (default 20)")
    parser.add_argument("--battle-ticks", type=int, default=120, help="Max battle ticks")
    parser.add_argument("--dry-run", action="store_true", help="Allow running without game window")
    args = parser.parse_args(argv)

    if args.self_test_only:
        result = run_self_tests(require_game=args.require_game)
        for name, passed in result.tests.items():
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}")
        for msg in result.messages:
            print(f"  note: {msg}")
        return 0 if result.ok else 1

    runtime = GameIoRuntime(
        turns=args.turns,
        battle_ticks=args.battle_ticks,
        require_game=not args.dry_run and (args.require_game or args.run_campaign or args.run_battle or args.service),
    )

    if args.run_campaign:
        result = runtime.run_campaign(turns=args.turns)
        print(result)
        return 0 if result.get("ok") else 1

    if args.run_battle:
        result = runtime.run_battle(max_ticks=args.battle_ticks)
        print(result)
        return 0 if result.get("ok") else 1

    if args.service:
        runtime.run_service()
        return 0

    pre = check_preconditions(require_game=args.require_game)
    if not pre.ok:
        for f in pre.failures:
            print(f"precondition failed: {f}", file=sys.stderr)
        return 1
    print("preconditions OK — use --service, --run-campaign, or --run-battle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
