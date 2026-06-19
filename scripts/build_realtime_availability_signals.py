#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build or validate realtime_availability_signals.csv from structured inputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import EVENTFLOW_DB, ROOT, read_csv, snum, write_csv
from realtime_availability_common import check_lambda_eligibility, normalize_role_group

SIGNAL_FIELDS = [
    "match_id", "team", "opponent", "player", "signal_type", "status",
    "role", "role_group", "importance_tier", "replacement", "replacement_quality",
    "evidence_grade", "confirmed", "source_count", "minutes_expected_delta",
    "lambda_side", "eligibility_for_lambda", "eventflow_only", "exclusion_reason",
    "notes", "updated_at",
]

RAW_SIGNALS = EVENTFLOW_DB.parent / "realtime_availability_signals.csv"
PROCESSED_ADJ = EVENTFLOW_DB / "realtime_availability_adjustments.csv"


def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: row.get(k, "") for k in SIGNAL_FIELDS}
    out["role_group"] = normalize_role_group(snum(row, "role_group") or snum(row, "role"))
    eligible, reason, ef_only = check_lambda_eligibility(out)
    out["eligibility_for_lambda"] = str(eligible).lower()
    out["eventflow_only"] = str(ef_only).lower()
    out["exclusion_reason"] = reason
    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    return out


def build_signals(match_id: str = "") -> List[Dict[str, Any]]:
    rows = read_csv(RAW_SIGNALS)
    if match_id:
        rows = [r for r in rows if snum(r, "match_id") == match_id]
    return [enrich_row(r) for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate/enrich realtime availability signals")
    ap.add_argument("--match-id", default="")
    ap.add_argument("--export", default=str(RAW_SIGNALS))
    args = ap.parse_args()

    enriched = build_signals(args.match_id)
    write_csv(args.export, enriched, fieldnames=SIGNAL_FIELDS)
    n_eligible = sum(1 for r in enriched if str(r.get("eligibility_for_lambda", "")).lower() == "true")
    print(f"Wrote {len(enriched)} signals ({n_eligible} lambda-eligible) -> {args.export}")


if __name__ == "__main__":
    main()
