"""Split the 158 non-Big5 (5-league) gap players into per-batch input JSON
files for subagent web-lookup. Each batch ~22 players max."""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(os.path.dirname(HERE), "processed")
GAPS = os.path.join(PROC, "player_form_non_big5_target_gaps.csv")
STAGE = os.path.join(os.path.dirname(HERE), "raw", "club_player_form", "footystats_staging")
os.makedirs(STAGE, exist_ok=True)

LEAGUES = {
    "Saudi Pro League": ("SAU", 22),
    "Eredivisie": ("NED", 22),
    "Primeira Liga": ("POR", 27),
    "Qatar Stars League": ("QAT", 22),
    "Persian Gulf Pro League": ("IRN", 23),
}

by_league = {k: [] for k in LEAGUES}
with open(GAPS, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["target_league"] in by_league:
            by_league[r["target_league"]].append({
                "national_team": r["team"],
                "team_code": r["team_code"],
                "group": r["group"],
                "roster_player": r["player"],
                "roster_position": r["position"],
                "roster_club": r["club"],
                "league": r["target_league"],
            })

manifest = []
for league, (code, cap) in LEAGUES.items():
    players = by_league[league]
    for i in range(0, len(players), cap):
        chunk = players[i:i + cap]
        idx = i // cap + 1
        name = f"in_{code}_{idx}.json"
        with open(os.path.join(STAGE, name), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)
        manifest.append((name, league, len(chunk)))

print("STAGE:", STAGE)
for n, lg, c in manifest:
    print(f"  {n}: {lg} ({c})")
print("total players:", sum(c for _, _, c in manifest))
