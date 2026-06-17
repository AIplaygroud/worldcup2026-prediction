"""Merge all FootyStats subagent batch outputs into the main supplement CSV.
Drops empty 'not-found' rows, computes per90, validates, prints a summary."""
import csv
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROC = os.path.join(ROOT, "processed")
STAGE = os.path.join(ROOT, "raw", "club_player_form", "footystats_staging")
OUT = os.path.join(PROC, "player_form_non_big5_footystats_supplement.csv")

FIELDS = [
    "national_team", "team_code", "group", "roster_player", "roster_position",
    "roster_club", "matched_player", "club", "league", "season",
    "matches_played", "minutes", "goals", "assists", "shots", "key_passes",
    "xg", "npxg", "xa", "xg_per90", "xa_per90", "source", "source_url",
    "last_verified", "match_confidence", "recommended_weight", "notes",
]


def num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def per90(v, minutes):
    v, m = num(v), num(minutes)
    if v is None or not m:
        return ""
    return round(v / m * 90, 3)


def has_data(r):
    return any(num(r.get(k)) is not None for k in ("minutes", "matches_played", "goals", "xg"))


rows = {}
dropped = []
per_file = {}
for path in sorted(glob.glob(os.path.join(STAGE, "out_*.json"))):
    data = json.load(open(path, encoding="utf-8"))
    kept = 0
    for r in data:
        if not has_data(r):
            dropped.append(r.get("roster_player", "?"))
            continue
        row = {k: r.get(k, "") for k in FIELDS}
        row["xg_per90"] = per90(row.get("xg"), row.get("minutes"))
        row["xa_per90"] = per90(row.get("xa"), row.get("minutes"))
        rows[row["roster_player"]] = row
        kept += 1
    per_file[os.path.basename(path)] = (len(data), kept)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    for r in rows.values():
        w.writerow(r)

print("=== per-file (total_in_json / kept) ===")
for k, (t, kept) in per_file.items():
    print(f"  {k}: {t} / {kept}")
print(f"\nTOTAL rows written: {len(rows)}")
print(f"Dropped empty/not-found rows: {len(dropped)}")

# breakdown by league + xG presence
by_lg = {}
for r in rows.values():
    lg = r["league"]
    d = by_lg.setdefault(lg, {"n": 0, "xg": 0})
    d["n"] += 1
    if num(r.get("xg")) is not None:
        d["xg"] += 1
print("\n=== by league (rows / with xG) ===")
for lg, d in sorted(by_lg.items()):
    print(f"  {lg}: {d['n']} / {d['xg']}")
print("\nOUTPUT:", OUT)
