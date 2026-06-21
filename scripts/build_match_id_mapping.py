#!/usr/bin/env python3
"""Generate wc2026_match_id_mapping.csv from group fixtures."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from group_state_common import kickoff_utc_from_fixture_row  # noqa: E402

fx = ROOT / "database/competition/wc2026_group_fixtures.csv"
out = ROOT / "database/competition/wc2026_match_id_mapping.csv"
rows = []
with fx.open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        fid = r["fifa_match_id"]
        grp = r["group"]
        internal = f"WC2026-{grp}{fid}"
        ko_utc = kickoff_utc_from_fixture_row(r)
        rows.append({
            "internal_match_id": internal,
            "fifa_match_id": fid,
            "group": grp,
            "round": r["round"],
            "home_team": r["home_team_en"],
            "away_team": r["away_team_en"],
            "kickoff_utc": ko_utc.strftime("%Y-%m-%dT%H:%M:%SZ") if ko_utc else "",
            "kickoff_local": f"{r['match_date']} {r['kickoff_local']}",
            "kickoff_et": f"{r['match_date']} {r['kickoff_et']}",
            "kickoff_time": f"{r['match_date']} {r['kickoff_local']}",
            "source_url": r.get("source_url", ""),
        })
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"Wrote {len(rows)} rows -> {out}")
