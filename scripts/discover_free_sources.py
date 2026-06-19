"""Create a match-level URL seed file.

This script intentionally does not bypass paywalls, login walls, or robots.txt. It creates
an auditable list of URLs for downstream extraction. You may fill URLs manually or extend
this script with a search API you are allowed to use.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

DEFAULT_SOURCES = [
    "fifa_training_centre",
    "fifa_match_centre",
    "espn_match_commentary",
    "the_guardian_match_report",
    "world_soccer_talk_previews",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--home", default="")
    parser.add_argument("--away", default="")
    parser.add_argument("--out", default="database/eventflow/raw_sources/source_url_seeds.csv")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    exists = out.exists()
    with out.open("a", encoding="utf-8", newline="") as f:
        fieldnames = ["match_id", "home_team", "away_team", "source_id", "source_url", "source_title", "notes"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for source_id in DEFAULT_SOURCES:
            writer.writerow({
                "match_id": args.match_id,
                "home_team": args.home,
                "away_team": args.away,
                "source_id": source_id,
                "source_url": "",
                "source_title": "",
                "notes": "Fill URL manually or via allowed search API. Store metadata and signals, not full text.",
            })
    print(f"Wrote/updated {out}")

if __name__ == "__main__":
    main()
