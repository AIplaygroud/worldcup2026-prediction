from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from eventflow_htft import resolve_source_notes_path


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--home", default="")
    parser.add_argument("--away", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    notes = args.notes or resolve_source_notes_path(args.match_id)
    if not Path(notes).exists():
        print(f"Missing {notes}. Create per-match file or global source_notes.csv first.")
        sys.exit(1)

    run([sys.executable, "scripts/score_source_quality.py"])
    run([
        sys.executable, "scripts/extract_source_signals.py",
        "--match-id", args.match_id,
        "--infile", notes,
        "--append",
    ])
    run([sys.executable, "scripts/cross_source_validate_signals.py"])
    run([
        sys.executable, "scripts/fuse_signals_to_eventflow.py",
        "--match-id", args.match_id,
        "--home", args.home, "--away", args.away,
    ])

if __name__ == "__main__":
    main()
