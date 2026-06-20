#!/usr/bin/env python3
"""Load standings snapshot integrity status for formal prediction gating."""
from __future__ import annotations

import sys
from pathlib import Path

from group_state_common import ROOT, read_csv

INTEGRITY_PATH = ROOT / "database" / "competition" / "runtime" / "standings_snapshot_integrity.csv"
INTEGRITY_REPORT = ROOT / "outputs" / "phase06C_standings_integrity" / "standings_snapshot_integrity_report.md"


def load_integrity_status(snapshot_id: str | None = None) -> dict[str, str] | None:
    rows = read_csv(INTEGRITY_PATH)
    if not rows:
        return None
    if snapshot_id:
        for r in rows:
            if r.get("snapshot_id") == snapshot_id:
                return r
    return rows[-1]


def check_formal_prediction_allowed(
    snapshot_id: str | None = None,
    match_id: str | None = None,
    allow_partial: bool = False,
    smoke_test: bool = False,
) -> tuple[bool, str, dict[str, str] | None]:
    """Return (allowed, message, integrity_row)."""
    row = load_integrity_status(snapshot_id)
    if row is None:
        return False, f"No integrity file at {INTEGRITY_PATH}; run Phase 06C validation first.", None

    formal = row.get("formal_prediction_allowed", "false")
    if formal == "true":
        return True, "Standings snapshot complete.", row

    if formal == "partial_only" and (allow_partial or smoke_test):
        if match_id:
            mapping = {
                r["internal_match_id"]: r["group"]
                for r in read_csv(ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv")
            }
            grp = mapping.get(match_id, "")
            affected = set((row.get("affected_groups") or "").split("|")) - {""}
            if grp in affected:
                return False, (
                    f"Match {match_id} (Group {grp}) is in affected_groups {sorted(affected)}; "
                    "group-local incentive not allowed until backfill."
                ), row
        return True, "Partial-only mode: cross-group third-place and route avoidance disabled.", row

    if formal == "false":
        return False, (
            f"Formal prediction blocked (status={row.get('snapshot_status')}). "
            f"Backfill missing results or re-run with --allow-partial-standings for smoke tests. "
            f"Report: {INTEGRITY_REPORT}"
        ), row

    return False, f"Unknown formal_prediction_allowed={formal}", row


def enforce_or_exit(
    snapshot_id: str | None = None,
    match_id: str | None = None,
    allow_partial: bool = False,
    smoke_test: bool = False,
) -> dict[str, str]:
    ok, msg, row = check_formal_prediction_allowed(snapshot_id, match_id, allow_partial, smoke_test)
    if not ok:
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    if row and row.get("formal_prediction_allowed") == "partial_only":
        print(f"WARNING: {msg}", file=sys.stderr)
    return row or {}
