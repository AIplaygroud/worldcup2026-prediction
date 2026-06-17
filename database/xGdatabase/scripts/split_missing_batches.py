"""Split the remaining `missing` players (from player_form_summary.csv) into
per-cluster batch input JSON files for subagent FootyStats lookup.

Two tiers:
  - xg_leagues: European mid + Americas leagues where FootyStats exposes xG.
  - try_leagues: low-weight leagues (Middle East / Africa domestic) - light
    attempt, basic stats acceptable, no over-trying.
Anything not in either list is left alone (low ROI / Big5-country non-Understat).
"""
import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(os.path.dirname(HERE), "processed")
SUMMARY = os.path.join(PROC, "player_form_summary.csv")
STAGE = os.path.join(os.path.dirname(HERE), "raw", "club_player_form", "footystats_staging")
os.makedirs(STAGE, exist_ok=True)

# country code -> (league label, tier)  tier in {"xg","try"}
CLUSTERS = {
    "BEL": ("Belgian Pro League", "xg"),
    "CZE": ("Czech First League", "xg"),
    "SCO": ("Scottish Premiership", "xg"),
    "DEN": ("Danish Superliga", "xg"),
    "SUI": ("Swiss Super League", "xg"),
    "GRE": ("Greek Super League", "xg"),
    "NOR": ("Norwegian Eliteserien", "xg"),
    "AUT": ("Austrian Bundesliga", "xg"),
    "MEX": ("Liga MX", "xg"),
    "BRA": ("Brazil Serie A", "xg"),
    "ARG": ("Argentine Primera", "xg"),
    # low-weight: light attempt only
    "EGY": ("Egyptian Premier League", "try"),
    "RSA": ("South Africa PSL", "try"),
    "UZB": ("Uzbekistan Super League", "try"),
    "UAE": ("UAE Pro League", "try"),
    "IRQ": ("Iraq Stars League", "try"),
    "JOR": ("Jordanian Pro League", "try"),
}
CAP = 22


def club_country(club):
    m = re.search(r"\(([A-Z]{3})\)\s*$", club or "")
    return m.group(1) if m else "???"


buckets = defaultdict(list)
with open(SUMMARY, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["source_layer"] != "missing":
            continue
        code = club_country(r["club"])
        if code not in CLUSTERS:
            continue
        league, tier = CLUSTERS[code]
        buckets[code].append({
            "national_team": r["team"],
            "team_code": r["team_code"],
            "group": r["group"],
            "roster_player": r["player"],
            "roster_position": r["position"],
            "roster_club": r["club"],
            "league": league,
            "_tier": tier,
        })

manifest = []
for code, players in sorted(buckets.items()):
    tier = CLUSTERS[code][1]
    for i in range(0, len(players), CAP):
        chunk = players[i:i + CAP]
        idx = i // CAP + 1
        name = f"in_MIS_{tier}_{code}_{idx}.json"
        with open(os.path.join(STAGE, name), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)
        manifest.append((name, CLUSTERS[code][0], tier, len(chunk)))

print("STAGE:", STAGE)
xg_total = try_total = 0
for n, lg, tier, c in manifest:
    print(f"  {n}: {lg} [{tier}] ({c})")
    if tier == "xg":
        xg_total += c
    else:
        try_total += c
print(f"\nxg-tier players: {xg_total}")
print(f"try-tier players: {try_total}")
print(f"total batched: {xg_total + try_total}")
