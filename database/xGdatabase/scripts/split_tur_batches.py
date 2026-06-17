"""Split the 37 Super Lig (Turkey) gap players into per-batch input JSON files
for subagent FootyStats lookup. Mirrors split_footystats_batches.py format."""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(os.path.dirname(HERE), "processed")
GAPS = os.path.join(PROC, "player_form_non_big5_target_gaps.csv")
STAGE = os.path.join(os.path.dirname(HERE), "raw", "club_player_form", "footystats_staging")
os.makedirs(STAGE, exist_ok=True)

CAP = 19  # -> 2 batches (19 + 18)

players = []
with open(GAPS, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["target_league"] == "Super Lig":
            players.append({
                "national_team": r["team"],
                "team_code": r["team_code"],
                "group": r["group"],
                "roster_player": r["player"],
                "roster_position": r["position"],
                "roster_club": r["club"],
                "league": r["target_league"],
            })

manifest = []
for i in range(0, len(players), CAP):
    chunk = players[i:i + CAP]
    idx = i // CAP + 1
    name = f"in_TUR_{idx}.json"
    with open(os.path.join(STAGE, name), "w", encoding="utf-8") as f:
        json.dump(chunk, f, ensure_ascii=False, indent=2)
    manifest.append((name, len(chunk)))

print("STAGE:", STAGE)
for n, c in manifest:
    print(f"  {n}: Super Lig ({c})")
print("total players:", len(players))
