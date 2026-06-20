#!/usr/bin/env python3
"""Phase 05B: formal R2 prediction with standings integrity guard (Phase 06C)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from standings_integrity_guard import enforce_or_exit  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 05B formal R2 prediction (integrity-gated)")
    ap.add_argument("--match-id", required=True)
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--mode", default="balanced", choices=["safe", "balanced", "hit_hunting"])
    ap.add_argument("--snapshot-id", default="")
    ap.add_argument("--allow-partial-standings", action="store_true", help="Smoke test / backtest only")
    ap.add_argument("--smoke-test", action="store_true", help="Alias for controlled partial run")
    ap.add_argument("--preflight-only", action="store_true")
    ap.add_argument("--skip-build", action="store_true", default=True)
    ap.add_argument("--no-skip-build", dest="skip_build", action="store_false")
    args = ap.parse_args()

    snap = args.snapshot_id or None
    partial = args.allow_partial_standings or args.smoke_test
    enforce_or_exit(snap, args.match_id, allow_partial=partial, smoke_test=args.smoke_test)

    cmd = [
        sys.executable,
        str(SCRIPTS / "run_phase05A_r2_prediction.py"),
        "--match-id", args.match_id,
        "--home", args.home,
        "--away", args.away,
        "--mode", args.mode,
    ]
    if args.preflight_only:
        cmd.append("--preflight-only")
    if args.skip_build:
        cmd.append("--skip-build")
    else:
        cmd.append("--no-skip-build")

    raise SystemExit(subprocess.call(cmd, cwd=ROOT))


if __name__ == "__main__":
    main()
