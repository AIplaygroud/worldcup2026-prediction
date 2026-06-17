"""
Idempotent appender for the FootyStats-sourced non-Big5 player form supplement.

Usage: python append_footystats_rows.py <rows.json>
Each row in the JSON is a dict; missing fields default to "".
Rows whose roster_player already exists in the output are replaced (idempotent).
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(os.path.dirname(HERE), "processed")
OUT = os.path.join(PROC, "player_form_non_big5_footystats_supplement.csv")

FIELDS = [
    "national_team", "team_code", "group", "roster_player", "roster_position",
    "roster_club", "matched_player", "club", "league", "season",
    "matches_played", "minutes", "goals", "assists", "shots", "key_passes",
    "xg", "npxg", "xa", "xg_per90", "xa_per90", "source", "source_url",
    "last_verified", "match_confidence", "recommended_weight", "notes",
]


def load_existing():
    rows = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rows[r["roster_player"]] = r
    return rows


def per90(v, minutes):
    try:
        v = float(v)
        m = float(minutes)
        if m <= 0:
            return ""
        return round(v / m * 90, 3)
    except (TypeError, ValueError):
        return ""


def main():
    incoming = json.load(open(sys.argv[1], encoding="utf-8"))
    existing = load_existing()
    for r in incoming:
        row = {k: r.get(k, "") for k in FIELDS}
        if not row.get("xg_per90"):
            row["xg_per90"] = per90(row.get("xg"), row.get("minutes"))
        if not row.get("xa_per90"):
            row["xa_per90"] = per90(row.get("xa"), row.get("minutes"))
        existing[row["roster_player"]] = row
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for rp in existing.values():
            w.writerow({k: rp.get(k, "") for k in FIELDS})
    print(f"total rows now: {len(existing)}  (added/updated {len(incoming)})")


if __name__ == "__main__":
    main()
