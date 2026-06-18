#!/usr/bin/env python3
"""Resolve FIFA World Cup 2026 round-of-32 bracket via Annex C lookup.

Usage:
  python resolve_round_of_32.py --third-groups EFGHIJKL
  python resolve_round_of_32.py --standings database/competition/group_standings.csv
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANNEX = ROOT / "database" / "competition" / "annex_c_round_of_32.csv"
DEFAULT_STANDINGS = ROOT / "database" / "competition" / "group_standings.csv"

GROUPS = list("ABCDEFGHIJKL")
WINNER_SLOTS = ["1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"]
WINNER_MATCH = {"1A": 79, "1B": 85, "1D": 81, "1E": 74, "1G": 82, "1I": 77, "1K": 87, "1L": 80}

FIXED = [
    (73, "2A", "2B"),
    (75, "1F", "2C"),
    (76, "1C", "2F"),
    (78, "2E", "2I"),
    (83, "2K", "2L"),
    (84, "1H", "2J"),
    (86, "1J", "2H"),
    (88, "2D", "2G"),
]


def load_annex() -> dict[str, dict]:
    rows = list(csv.DictReader(ANNEX.open(encoding="utf-8")))
    return {r["advancing_groups"]: r for r in rows}


def third_place_key(groups: list[str]) -> str:
    if len(groups) != 8:
        raise ValueError(f"need exactly 8 advancing third-place groups, got {len(groups)}")
    return "".join(sorted(groups))


def rank_third_places(standings_path: pathlib.Path) -> list[tuple[str, dict]]:
    by_group: dict[str, dict] = {}
    for row in csv.DictReader(standings_path.open(encoding="utf-8")):
        if int(row["rank"]) == 3:
            by_group[row["group"]] = row
    if len(by_group) != 12:
        raise ValueError(f"expected 12 third-placed teams, found {len(by_group)}")

    def key(row: dict):
        return (
            -int(row["points"]),
            -int(row["goal_difference"]),
            -int(row["goals_for"]),
        )

    ranked = sorted(by_group.items(), key=lambda x: key(x[1]))
    return ranked


def advancing_from_standings(standings_path: pathlib.Path) -> list[str]:
    ranked = rank_third_places(standings_path)
    return [g for g, _ in ranked[:8]]


def resolve_bracket(advancing_groups: list[str], annex_row: dict) -> list[dict]:
    matches = []
    for match_no, home, away in FIXED:
        matches.append({"match": match_no, "home": home, "away": away, "type": "fixed"})

    for slot in WINNER_SLOTS:
        match_no = WINNER_MATCH[slot]
        third = annex_row[f"vs_{slot}"]
        matches.append({
            "match": match_no,
            "home": slot,
            "away": third,
            "type": "annex_c",
            "advancing_groups": annex_row["advancing_groups"],
        })

    matches.sort(key=lambda m: m["match"])
    return matches


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Resolve WC2026 round-of-32 via Annex C")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--third-groups", help="8 advancing third-place groups, e.g. EFGHIJKL or E,F,G,H,I,J,K,L")
    g.add_argument("--standings", type=pathlib.Path, help="group_standings.csv with final ranks")
    p.add_argument("--json", action="store_true", help="print JSON instead of table")
    args = p.parse_args(argv)

    annex = load_annex()

    if args.third_groups:
        raw = args.third_groups.replace(",", "").replace(" ", "").upper()
        advancing = list(raw)
    else:
        advancing = advancing_from_standings(args.standings)

    key = third_place_key(advancing)
    if key not in annex:
        print(f"error: no Annex C row for advancing groups {key}", file=sys.stderr)
        return 1

    row = annex[key]
    matches = resolve_bracket(advancing, row)

    if args.json:
        import json
        print(json.dumps({
            "option": int(row["option"]),
            "advancing_groups": row["advancing_groups"],
            "eliminated_groups": row["eliminated_groups"],
            "matches": matches,
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"Annex C option {row['option']}")
    print(f"Advancing 3rd-place groups: {row['advancing_groups']}")
    print(f"Eliminated 3rd-place groups: {row['eliminated_groups']}")
    print()
    for m in matches:
        print(f"M{m['match']:02d}: {m['home']} vs {m['away']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
