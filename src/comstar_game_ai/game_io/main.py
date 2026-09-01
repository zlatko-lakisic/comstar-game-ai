"""Process A entrypoint."""

from __future__ import annotations

import argparse
import sys

from comstar_game_ai.game_io.preconditions import check_preconditions
from comstar_game_ai.game_io.self_tests import run_self_tests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comstar Game I/O service")
    parser.add_argument("--self-test-only", action="store_true", help="Run Phase 0 self-tests and exit")
    parser.add_argument("--require-game", action="store_true", help="Fail if Rome is not running")
    args = parser.parse_args(argv)

    if args.self_test_only:
        result = run_self_tests(require_game=args.require_game)
        for name, passed in result.tests.items():
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}")
        for msg in result.messages:
            print(f"  note: {msg}")
        return 0 if result.ok else 1

    pre = check_preconditions(require_game=True)
    if not pre.ok:
        for f in pre.failures:
            print(f"precondition failed: {f}", file=sys.stderr)
        return 1
    print("preconditions OK — full game loop not implemented yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
