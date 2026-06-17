#!/usr/bin/env python3
"""Assign per-team `recommended_weight` to International Friendlies rows.

The plan (`必拉/应拉/可拉但降权`) requires friendly matches to be downweighted
below 2026 qualifiers (1.00) and continental tournaments (0.80), and to be
tiered by team strength rather than a flat value:

    strong national teams : 0.40 - 0.60
    weak teams / heavy rotation : 0.20 - 0.40

This script maps every friendly team to a strength tier and writes the tier
weight back into `context_xg_summary.csv`. It is idempotent: weights are always
re-derived from the tier table below, so it can be re-run after data refreshes.

World Cup 2026 teams are tiered to match `skill.md` (夺冠热门 / 一线强队 /
二线-东道主 / 中游-新军); non-participating teams are tiered by general national
-team strength since they only ever serve as opponent context.

NOTE: weights are per *team*, not per *match*. The plan's "大规模轮换比赛给低
权重" nuance is a per-match concern that the team-aggregated FootyStats table
cannot express; apply an extra discount manually for known rotation friendlies.
"""

from __future__ import annotations

import csv
from pathlib import Path

PROCESSED = Path(__file__).resolve().parent.parent / "processed"
SUMMARY_CSV = PROCESSED / "context_xg_summary.csv"
COVERAGE_CSV = PROCESSED / "context_xg_coverage.csv"

FRIENDLY_COMPETITION = "International Friendlies"
DEFAULT_WEIGHT = 0.30  # fallback for any team not explicitly tiered

# tier label -> (weight, [teams])
TIERS: dict[str, tuple[float, list[str]]] = {
    "elite": (0.55, ["England", "Argentina"]),
    "high": (0.50, ["Portugal", "Senegal"]),
    "upper": (0.45, ["Russia", "Hungary", "Chile", "Nigeria", "Austria", "Iceland"]),
    "mid": (0.40, ["Venezuela", "Algeria", "Burkina Faso", "Bolivia",
                   "Costa Rica", "Angola"]),
    "low_mid": (0.35, ["Azerbaijan", "Armenia", "Belarus", "China", "Benin",
                       "Kazakhstan", "Saudi Arabia", "Palestine", "Iraq",
                       "Congo DR", "Syria", "Bahrain"]),
    "low": (0.30, ["Tanzania", "Sierra Leone", "Tajikistan", "Indonesia",
                   "Rwanda", "Thailand", "India", "Togo", "Kyrgyzstan",
                   "Trinidad and Tobago", "Guatemala"]),
    "weak": (0.22, ["Hong Kong", "Liberia", "Moldova", "San Marino",
                    "Afghanistan", "Pakistan", "Cambodia",
                    "Central African Republic", "Malawi", "Ethiopia",
                    "Mozambique"]),
}

# Build team -> (weight, tier) lookup.
TEAM_WEIGHT: dict[str, tuple[float, str]] = {}
for tier, (weight, teams) in TIERS.items():
    for team in teams:
        TEAM_WEIGHT[team] = (weight, tier)


def weight_for(team: str) -> tuple[float, str]:
    return TEAM_WEIGHT.get(team, (DEFAULT_WEIGHT, "unrated"))


def update_summary() -> tuple[int, list[str]]:
    with SUMMARY_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    fieldnames = list(rows[0].keys())

    updated = 0
    unrated: list[str] = []
    for row in rows:
        if row.get("competition") != FRIENDLY_COMPETITION:
            continue
        team = row.get("team", "")
        weight, tier = weight_for(team)
        if tier == "unrated":
            unrated.append(team)
        row["recommended_weight"] = f"{weight:.2f}"
        note = row.get("notes", "")
        base = note.split(" | strength tier:")[0]
        row["notes"] = f"{base} | strength tier: {tier} (w={weight:.2f})"
        updated += 1

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return updated, unrated


def update_coverage() -> None:
    with COVERAGE_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    fieldnames = list(rows[0].keys())

    weights = sorted({w for w, _ in TEAM_WEIGHT.values()})
    rng = f"{weights[0]:.2f}-{weights[-1]:.2f}"
    for row in rows:
        if row.get("competition") == FRIENDLY_COMPETITION:
            row["recommended_weight"] = rng
            row["notes"] = (
                "Per-team strength-tiered weights "
                f"({rng}); see recommended_weight per row in "
                "context_xg_summary.csv. Weights are per team, not per match."
            )

    with COVERAGE_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    updated, unrated = update_summary()
    update_coverage()
    print(f"Tiered recommended_weight for {updated} friendly rows.")
    if unrated:
        print(f"Unrated (fell back to {DEFAULT_WEIGHT:.2f}): {', '.join(unrated)}")
    else:
        print("All friendly teams matched an explicit strength tier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
