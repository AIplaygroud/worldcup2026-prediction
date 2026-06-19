from __future__ import annotations

import argparse
from pathlib import Path
from eventflow_source_common import read_csv, write_csv

FIELDS = ["source_id", "source_name", "source_type", "authority_score", "default_use", "risk_note"]

AUTHORITY = {
    "official_technical": 1.00,
    "official_match": 0.95,
    "open_event_data": 0.95,
    "open_results_odds": 0.85,
    "live_commentary": 0.75,
    "professional_media": 0.70,
    "player_profile": 0.65,
    "fan_blog": 0.35,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="database/source_registry/free_source_registry.csv")
    parser.add_argument("--out", default="database/eventflow/processed/source_signal_quality.csv")
    args = parser.parse_args()

    rows = read_csv(Path(args.registry))
    out = []
    for r in rows:
        typ = r.get("source_type", "")
        score = AUTHORITY.get(typ, 0.5)
        out.append({
            "source_id": r.get("source_id", ""),
            "source_name": r.get("source_name", ""),
            "source_type": typ,
            "authority_score": score,
            "default_use": r.get("expected_use", ""),
            "risk_note": r.get("store_policy", ""),
        })
    write_csv(Path(args.out), out, FIELDS)
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
